"""Run the Crash-to-Contact demo pipeline end to end against a local DuckDB file.

Loads a fixed batch of four synthetic crashes (two Montgomery County, one
TxDOT, one FARS), enriches them, runs every party through the compliance
engine and lead scorer, and writes the results into the gold star schema.
Re-running replaces the demo rows, so the database can be rebuilt any time.

Usage:
    python run_pipeline.py                 # demo batch into data/crash_analytics.duckdb
    python run_pipeline.py --db out.duckdb  # choose another database file
    python run_pipeline.py --live          # also pull MoCo incidents into data/raw/ first
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import httpx
from dotenv import load_dotenv

from src.compliance.eligibility import evaluate_party_eligibility
from src.compliance.ruleset import ContactChannel
from src.geo.census_enrichment import enrich_census_demographics
from src.geo.h3_index import get_h3_indices
from src.geo.road_snap import snap_crash_to_roadway
from src.geo.timezone import get_iana_timezone
from src.geo.weather_join import infer_weather_observation
from src.models.schema import init_gold_database
from src.models.severity_crosswalk import crosswalk_severity
from src.scoring.lead_score import score_lead

# Fixed so the 30-day Maryland blackout outcome is reproducible.
EVALUATION_TIME = datetime(2024, 7, 6, 12, 0, tzinfo=UTC)

DEMO_CRASHES = [
    # MoCo, Rockville Pike, serious injury, 35 days before the evaluation time
    {
        "crash_id": "MD_2024_001",
        "source_system": "moco",
        "source_record_id": "MCPD_R001",
        "crash_timestamp": datetime(2024, 6, 1, 14, 30, tzinfo=UTC),
        "crash_date": datetime(2024, 6, 1).date(),
        "latitude": 39.0845,
        "longitude": -77.1525,
        "raw_severity": "SUSPECTED SERIOUS INJURY",
        "vehicle_count": 2,
        "collision_type": "ANGULAR",
        "is_commercial_vehicle": True,
        "weather": "RAINING",
        "surface": "WET",
    },
    # MoCo, Bethesda, 12 days before evaluation (inside the 30-day blackout)
    {
        "crash_id": "MD_2024_002",
        "source_system": "moco",
        "source_record_id": "MCPD_R002",
        "crash_timestamp": datetime(2024, 6, 24, 18, 15, tzinfo=UTC),
        "crash_date": datetime(2024, 6, 24).date(),
        "latitude": 38.9840,
        "longitude": -77.0940,
        "raw_severity": "SUSPECTED MINOR INJURY",
        "vehicle_count": 1,
        "collision_type": "SINGLE_VEHICLE",
        "is_commercial_vehicle": False,
        "weather": "CLEAR",
        "surface": "DRY",
    },
    # TxDOT, Austin (barred by Tex. Penal Code § 38.12)
    {
        "crash_id": "TX_2024_003",
        "source_system": "txdot",
        "source_record_id": "TXDOT_189420",
        "crash_timestamp": datetime(2024, 6, 10, 9, 0, tzinfo=UTC),
        "crash_date": datetime(2024, 6, 10).date(),
        "latitude": 30.2672,
        "longitude": -97.7431,
        "raw_severity": 2,  # Suspected Serious in CRIS
        "vehicle_count": 2,
        "collision_type": "INTERSECTION",
        "is_commercial_vehicle": False,
        "weather": "CLEAR",
        "surface": "DRY",
    },
    # FARS fatal crash in Montgomery County (fatality gate)
    {
        "crash_id": "FARS_2024_004",
        "source_system": "fars",
        "source_record_id": "FARS_240019",
        "crash_timestamp": datetime(2024, 5, 15, 23, 45, tzinfo=UTC),
        "crash_date": datetime(2024, 5, 15).date(),
        "latitude": 39.1020,
        "longitude": -77.1700,
        "raw_severity": 4,  # Fatal in FARS
        "vehicle_count": 2,
        "collision_type": "HEAD_ON",
        "is_commercial_vehicle": True,
        "weather": "FOG",
        "surface": "WET",
    },
]

DEMO_PARTIES = [
    {
        "party_id": "P_MD_001",
        "crash_id": "MD_2024_001",
        "source_system": "moco",
        "person_type": "DRIVER",
        "age": 38,
        "sex": "M",
        "raw_severity": "SUSPECTED SERIOUS INJURY",
        "phone_number": "301-555-0144",
    },
    {
        "party_id": "P_MD_002",
        "crash_id": "MD_2024_002",
        "source_system": "moco",
        "person_type": "DRIVER",
        "age": 29,
        "sex": "F",
        "raw_severity": "SUSPECTED MINOR INJURY",
        "phone_number": "301-555-0199",
    },
    {
        "party_id": "P_TX_003",
        "crash_id": "TX_2024_003",
        "source_system": "txdot",
        "person_type": "DRIVER",
        "age": 45,
        "sex": "M",
        "raw_severity": 2,
        "phone_number": "512-555-0188",
    },
    {
        "party_id": "P_FARS_004",
        "crash_id": "FARS_2024_004",
        "source_system": "fars",
        "person_type": "DRIVER",
        "age": 52,
        "sex": "M",
        "raw_severity": 4,
        "phone_number": "301-555-0122",
    },
]


SUMMARY_SQL = """
SELECT
    p.party_id,
    c.source_system,
    loc.state_abbr AS state,
    c.crash_date,
    s.severity_name,
    p.contact_eligibility_status AS status,
    p.lead_score,
    p.priority_tier,
    COALESCE(array_to_string(p.ineligibility_reasons, '; '), '') AS citations,
    COALESCE(loc.nearest_road_name, '-') AS nearest_road,
    loc.timezone_iana
FROM fact_party p
JOIN fact_crash c ON p.crash_id = c.crash_id
JOIN dim_severity s ON p.injury_severity = s.severity_code
JOIN dim_location loc ON loc.location_id = 'LOC_' || c.crash_id
ORDER BY p.party_id
"""


def clear_demo_rows(conn: duckdb.DuckDBPyConnection, crash_ids: list[str]) -> None:
    """Delete earlier demo rows, children first, so a re-run does not hit the fact_party FK.

    Each DELETE autocommits: DuckDB rejects deleting a referenced fact_crash
    row in the same transaction that deleted the fact_party rows pointing at it.
    """
    placeholders = ", ".join("?" for _ in crash_ids)
    conn.execute(f"DELETE FROM fact_party WHERE crash_id IN ({placeholders})", crash_ids)
    conn.execute(f"DELETE FROM fact_crash WHERE crash_id IN ({placeholders})", crash_ids)
    conn.execute(
        f"DELETE FROM dim_location WHERE location_id IN ({placeholders})",
        [f"LOC_{cid}" for cid in crash_ids],
    )


def load_crashes(conn: duckdb.DuckDBPyConnection, crashes: list[dict]) -> dict[str, dict]:
    """Enrich each crash and insert it into dim_location and fact_crash.

    Returns the crash records keyed by crash_id, extended with the derived
    attributes (timezone, road class) that the compliance and scoring steps need.
    """
    enriched: dict[str, dict] = {}
    for c in crashes:
        lat, lon = c["latitude"], c["longitude"]
        kabco = crosswalk_severity(c["raw_severity"], c["source_system"]).value
        tz_iana = get_iana_timezone(lat, lon)
        h3_8, h3_9 = get_h3_indices(lat, lon)
        census = enrich_census_demographics(lat, lon)
        snap = snap_crash_to_roadway(lat, lon)
        road = snap if snap is not None and not snap.is_off_network else None
        weather = infer_weather_observation(c["crash_timestamp"], c["weather"], c["surface"])

        county_fips = census.county_fips if census else None
        tract_geoid = census.geoid if census else None

        conn.execute(
            """
            INSERT INTO dim_location (
                location_id, latitude, longitude, state_abbr, county_name, county_fips,
                census_tract_geoid, h3_res8, h3_res9, nearest_road_name,
                nearest_road_dist_m, speed_limit, functional_class, timezone_iana
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                f"LOC_{c['crash_id']}",
                lat,
                lon,
                census.state_abbr if census else None,
                census.county_name if census else None,
                county_fips,
                tract_geoid,
                h3_8,
                h3_9,
                road.road_name if road else None,
                road.distance_to_road_meters if road else None,
                road.speed_limit_mph if road else None,
                road.functional_class if road else None,
                tz_iana,
            ],
        )

        conn.execute(
            """
            INSERT INTO fact_crash (
                crash_id, source_system, source_record_id, crash_timestamp,
                crash_date, latitude, longitude, severity_kabc0, vehicle_count,
                collision_type, weather_condition, road_condition, county_fips,
                census_tract_geoid, h3_res8, h3_res9, is_commercial_vehicle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                c["crash_id"],
                c["source_system"],
                c["source_record_id"],
                c["crash_timestamp"],
                c["crash_date"],
                lat,
                lon,
                kabco,
                c["vehicle_count"],
                c["collision_type"],
                weather.weather_condition,
                weather.surface_condition,
                county_fips,
                tract_geoid,
                h3_8,
                h3_9,
                c["is_commercial_vehicle"],
            ],
        )

        enriched[c["crash_id"]] = {
            **c,
            "severity_kabc0": kabco,
            "timezone_iana": tz_iana,
            "functional_class": road.functional_class if road else None,
        }
    return enriched


def load_parties(
    conn: duckdb.DuckDBPyConnection,
    parties: list[dict],
    crashes: dict[str, dict],
    evaluation_time: datetime,
) -> None:
    """Gate each party through the compliance engine, score it, and insert into fact_party."""
    for p in parties:
        crash = crashes[p["crash_id"]]
        kabco = crosswalk_severity(p["raw_severity"], p["source_system"]).value

        status, reasons = evaluate_party_eligibility(
            party={
                "party_id": p["party_id"],
                "source_system": p["source_system"],
                "person_type": p["person_type"],
                "injury_severity": kabco,
                "age": p["age"],
            },
            crash=crash,
            channel=ContactChannel.DIRECT_MAIL,
            evaluation_time=evaluation_time,
        )
        scored = score_lead(
            party={
                "party_id": p["party_id"],
                "person_type": p["person_type"],
                "contact_eligibility_status": status,
                "ineligibility_reasons": reasons,
                "injury_severity": kabco,
            },
            crash=crash,
            evaluation_time=evaluation_time,
        )

        conn.execute(
            """
            INSERT INTO fact_party (
                party_id, crash_id, source_system, person_type, age, sex,
                injury_severity, contact_eligibility_status, ineligibility_reasons,
                lead_score, priority_tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                p["party_id"],
                p["crash_id"],
                p["source_system"],
                p["person_type"],
                p["age"],
                p["sex"],
                kabco,
                status,
                reasons,
                scored.composite_score,
                scored.priority_tier,
            ],
        )


def fetch_live_moco() -> None:
    """Pull Montgomery County incidents into data/raw/ (bronze only; not loaded into gold)."""
    from src.ingestion.moco_ingester import ingest_dataset

    print("Fetching Montgomery County incidents (bhju-22kf) into data/raw/bronze/moco/ ...")
    try:
        count = ingest_dataset("bhju-22kf", "report_number", "crash_date_time")
    except (httpx.HTTPError, OSError) as exc:
        print(f"  live fetch failed: {exc}")
        return
    print(f"  fetched {count} rows")


def run_pipeline(live: bool = False, db_path: str = "data/crash_analytics.duckdb") -> None:
    """Build the gold schema in ``db_path`` and load the demo batch into it."""
    print(f"Crash-to-Contact demo pipeline -> {db_path}")
    if live:
        fetch_live_moco()

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(db_path)
    try:
        init_gold_database(conn)
        clear_demo_rows(conn, [c["crash_id"] for c in DEMO_CRASHES])
        conn.execute("BEGIN TRANSACTION")
        crashes = load_crashes(conn, DEMO_CRASHES)
        load_parties(conn, DEMO_PARTIES, crashes, EVALUATION_TIME)
        conn.execute("COMMIT")
        print(f"Loaded {len(DEMO_CRASHES)} crashes and {len(DEMO_PARTIES)} parties, "
              f"evaluated at {EVALUATION_TIME.isoformat()} for DIRECT_MAIL.\n")
        print(conn.execute(SUMMARY_SQL).fetchdf().to_string(index=False))
    finally:
        conn.close()


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run the Crash-to-Contact demo pipeline")
    parser.add_argument("--live", action="store_true", help="Also fetch MoCo incidents into data/raw/")
    parser.add_argument("--db", default="data/crash_analytics.duckdb", help="DuckDB file path")
    args = parser.parse_args()
    run_pipeline(live=args.live, db_path=args.db)
