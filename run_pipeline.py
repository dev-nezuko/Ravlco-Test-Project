"""End-to-end pipeline execution runner for live demonstrations and testing.

Usage:
    python run_pipeline.py            # Run end-to-end pipeline with standard demo batch
    python run_pipeline.py --live     # Fetch live records from Socrata/TxDOT APIs
    python run_pipeline.py --help
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb

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
from src.transforms.moco_silver import (
    enforce_crash_grain,
    flag_out_of_envelope,
    harmonize_substance_abuse,
)
from src.transforms.txdot_silver import resolve_coordinates


def run_pipeline(live: bool = False, db_path: str = "data/crash_analytics.duckdb") -> None:
    """Execute end-to-end ingestion, transform, gold loading, compliance, and scoring."""
    print("=" * 75)
    print("🚀 CRASH-TO-CONTACT PIPELINE RUNNER")
    print(f"   Mode: {'LIVE API INGESTION' if live else 'STANDARDIZED MULTI-SOURCE DEMO'}")
    print(f"   Target Database: {db_path}")
    print("=" * 75)

    # 1. Initialize Gold Database & Schema
    Path("data").mkdir(exist_ok=True)
    conn = duckdb.connect(db_path)
    init_gold_database(conn)
    print("✅ Initialized DuckDB Gold dimensional schema (fact_crash, fact_party, dim_*)")

    # 2. Ingestion / Data Sourcing
    if live:
        print("\n📡 Fetching live records from Montgomery County Socrata API...")
        try:
            from src.ingestion.moco_ingester import ingest_dataset
            count = ingest_dataset("bhju-22kf", "report_number", "crash_date_time")
            print(f"   Fetched {count} live incidents.")
        except Exception as e:
            print(f"   Live API notice: {e}. Falling back to sample batch.")
            live = False

    # Sample data representing the three assignment jurisdictions
    raw_crashes = [
        # MoCo Crash 1: Rockville Pike, Severe Injury, Day 35 (Eligible for Day 31+ Direct Mail)
        {
            "crash_id": "MD_2024_001",
            "source_system": "moco",
            "source_record_id": "MCPD_R001",
            "crash_timestamp": datetime(2024, 6, 1, 14, 30, tzinfo=timezone.utc),
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
        # MoCo Crash 2: Bethesda, Day 12 (Inside 30-Day Blackout Window)
        {
            "crash_id": "MD_2024_002",
            "source_system": "moco",
            "source_record_id": "MCPD_R002",
            "crash_timestamp": datetime(2024, 6, 24, 18, 15, tzinfo=timezone.utc),
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
        # TxDOT Crash: Austin, TX (Barred by Texas Barratry Tex. Penal Code § 38.12)
        {
            "crash_id": "TX_2024_003",
            "source_system": "txdot",
            "source_record_id": "TXDOT_189420",
            "crash_timestamp": datetime(2024, 6, 10, 9, 0, tzinfo=timezone.utc),
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
        # FARS Crash: Fatal Crash (National Fatal Archives - Ethical bar on outreach)
        {
            "crash_id": "FARS_2024_004",
            "source_system": "fars",
            "source_record_id": "FARS_240019",
            "crash_timestamp": datetime(2024, 5, 15, 23, 45, tzinfo=timezone.utc),
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

    raw_parties = [
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

    print("\n⚙️  Processing Silver transforms & Geospatial enrichment...")
    eval_time = datetime(2024, 7, 6, 12, 0, tzinfo=timezone.utc)

    # 3. Process & Insert Crashes into Gold Layer
    for c in raw_crashes:
        lat, lon = c["latitude"], c["longitude"]
        kabc0 = crosswalk_severity(c["raw_severity"], c["source_system"]).value
        tz_iana = get_iana_timezone(lat, lon)
        h3_8, h3_9 = get_h3_indices(lat, lon)
        census = enrich_census_demographics(lat, lon)
        road = snap_crash_to_roadway(lat, lon)
        weather = infer_weather_observation(c["crash_timestamp"], c["weather"], c["surface"])

        county_fips = census.county_fips if census else None
        tract_geoid = census.geoid if census else None

        # Insert Location Dimension
        conn.execute(
            """
            INSERT OR REPLACE INTO dim_location (
                location_id, latitude, longitude, state_abbr, county_fips,
                census_tract_geoid, h3_res8, h3_res9, nearest_road_name,
                speed_limit, timezone_iana
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                f"LOC_{c['crash_id']}",
                lat,
                lon,
                c["source_system"][:2].upper(),
                county_fips,
                tract_geoid,
                h3_8,
                h3_9,
                road.road_name if road else "UNKNOWN",
                road.speed_limit_mph if road else 35,
                tz_iana,
            ],
        )

        # Insert Fact Crash
        conn.execute(
            """
            INSERT OR REPLACE INTO fact_crash (
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
                kabc0,
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

    print("   Inserted crashes and spatial dimensions.")

    # 4. Compliance Gate & Lead Scoring
    print("\n⚖️  Running Compliance Gate & Lead Prioritization Engine...")
    for p in raw_parties:
        crash_meta = next(c for c in raw_crashes if c["crash_id"] == p["crash_id"])
        kabc0 = crosswalk_severity(p["raw_severity"], p["source_system"]).value

        # Compliance Evaluation
        status, reasons = evaluate_party_eligibility(
            party={
                "party_id": p["party_id"],
                "source_system": p["source_system"],
                "person_type": p["person_type"],
                "injury_severity": kabc0,
                "age": p["age"],
            },
            crash={
                "crash_id": crash_meta["crash_id"],
                "source_system": crash_meta["source_system"],
                "crash_timestamp": crash_meta["crash_timestamp"],
                "severity_kabc0": kabc0,
                "timezone_iana": get_iana_timezone(crash_meta["latitude"], crash_meta["longitude"]),
            },
            channel=ContactChannel.DIRECT_MAIL,
            evaluation_time=eval_time,
        )

        # Lead Scoring
        scored = score_lead(
            party={"party_id": p["party_id"], "contact_eligibility_status": status, "injury_severity": kabc0},
            crash=crash_meta,
            evaluation_time=eval_time,
        )

        # Insert Fact Party
        conn.execute(
            """
            INSERT OR REPLACE INTO fact_party (
                party_id, crash_id, source_system, person_type, age, sex,
                injury_severity, contact_eligibility_status, ineligibility_reasons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                p["party_id"],
                p["crash_id"],
                p["source_system"],
                p["person_type"],
                p["age"],
                p["sex"],
                kabc0,
                status,
                reasons,
            ],
        )

    print("   Evaluated parties against Texas Barratry, Maryland Moratorium, TCPA.")

    # 5. Output Live Results
    print("\n" + "=" * 75)
    print("📊 LIVE DATABASE STATUS & COMPLIANCE SUMMARY")
    print("=" * 75)

    df_summary = conn.execute(
        """
        SELECT 
            p.party_id,
            c.source_system,
            c.crash_date,
            s.severity_name,
            p.contact_eligibility_status,
            COALESCE(array_to_string(p.ineligibility_reasons, '; '), 'NONE (PASSED)') AS legal_citations,
            loc.nearest_road_name,
            loc.timezone_iana
        FROM fact_party p
        JOIN fact_crash c ON p.crash_id = c.crash_id
        JOIN dim_severity s ON p.injury_severity = s.severity_code
        JOIN dim_location loc ON c.crash_id = REPLACE(loc.location_id, 'LOC_', '')
        ORDER BY p.party_id
        """
    ).fetchdf()

    print(df_summary.to_string(index=False))
    print("=" * 75)
    print(f"\n🎉 Pipeline run complete! Database ready for live querying at: {db_path}\n")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Crash-to-Contact pipeline")
    parser.add_argument("--live", action="store_true", help="Fetch live data from public APIs")
    parser.add_argument("--db", default="data/crash_analytics.duckdb", help="DuckDB path")
    args = parser.parse_args()
    run_pipeline(live=args.live, db_path=args.db)
