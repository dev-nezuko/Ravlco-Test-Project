"""Unified Gold Layer dimensional model schema for DuckDB & GeoParquet.

Tables:
- fact_crash: Crash-level facts, one row per physical collision incident.
- fact_party: Person/victim/driver level facts, one row per involved party.
- dim_severity: Standard KABCO severity dimension.
- dim_location: Geospatial dimension with FIPS, census tract, H3 index, road snap.

Implements Kimball-style star schema optimized for fast analytical aggregations,
spatial queries via DuckDB spatial extension, and compliance eligibility audits.
"""

from __future__ import annotations

from typing import Optional
import duckdb


# ── DuckDB SQL DDL Statements ──────────────────────────────────────────────

DIM_SEVERITY_DDL = """
CREATE TABLE IF NOT EXISTS dim_severity (
    severity_code VARCHAR(1) PRIMARY KEY,
    severity_name VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    rank INTEGER NOT NULL
);
"""

POPULATE_DIM_SEVERITY_SQL = """
INSERT OR REPLACE INTO dim_severity (severity_code, severity_name, description, rank) VALUES
('K', 'Fatal Injury', 'Fatal injury sustained in crash resulting in death within 30 days', 5),
('A', 'Suspected Serious Injury', 'Incapacitating injury preventing normal daily activities', 4),
('B', 'Suspected Minor Injury', 'Evident non-incapacitating injury (bruises, scrapes, cuts)', 3),
('C', 'Possible Injury', 'Complaint of pain, momentary unconsciousness, no visible injury', 2),
('O', 'No Apparent Injury', 'Property damage only or uninjured party', 1),
('U', 'Unknown / Unreported', 'Injury severity unknown or not recorded by reporting agency', 0);
"""

DIM_LOCATION_DDL = """
CREATE TABLE IF NOT EXISTS dim_location (
    location_id VARCHAR PRIMARY KEY,
    latitude DOUBLE,
    longitude DOUBLE,
    state_abbr VARCHAR(2),
    county_name VARCHAR,
    county_fips VARCHAR(5),
    census_tract_geoid VARCHAR(11),
    h3_res8 VARCHAR(15),
    h3_res9 VARCHAR(15),
    nearest_road_name VARCHAR,
    nearest_road_dist_m DOUBLE,
    speed_limit INTEGER,
    functional_class VARCHAR,
    timezone_iana VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

FACT_CRASH_DDL = """
CREATE TABLE IF NOT EXISTS fact_crash (
    crash_id VARCHAR PRIMARY KEY,
    source_system VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    crash_timestamp TIMESTAMP WITH TIME ZONE,
    crash_date DATE,
    latitude DOUBLE,
    longitude DOUBLE,
    severity_kabc0 VARCHAR(1) REFERENCES dim_severity(severity_code),
    fatality_count INTEGER DEFAULT 0,
    injury_count INTEGER DEFAULT 0,
    vehicle_count INTEGER DEFAULT 1,
    collision_type VARCHAR,
    weather_condition VARCHAR,
    light_condition VARCHAR,
    road_condition VARCHAR,
    county_fips VARCHAR(5),
    census_tract_geoid VARCHAR(11),
    h3_res8 VARCHAR(15),
    h3_res9 VARCHAR(15),
    is_pedestrian_involved BOOLEAN DEFAULT FALSE,
    is_bicyclist_involved BOOLEAN DEFAULT FALSE,
    is_commercial_vehicle BOOLEAN DEFAULT FALSE,
    is_hit_and_run BOOLEAN DEFAULT FALSE,
    coord_quality_flag VARCHAR DEFAULT 'VALID',
    entity_cluster_id VARCHAR,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

FACT_PARTY_DDL = """
CREATE TABLE IF NOT EXISTS fact_party (
    party_id VARCHAR PRIMARY KEY,
    crash_id VARCHAR NOT NULL REFERENCES fact_crash(crash_id),
    source_system VARCHAR NOT NULL,
    source_person_id VARCHAR,
    person_type VARCHAR NOT NULL,
    vehicle_unit_number INTEGER DEFAULT 1,
    age INTEGER,
    sex VARCHAR(1),
    injury_severity VARCHAR(1) REFERENCES dim_severity(severity_code),
    substance_suspected BOOLEAN DEFAULT FALSE,
    substance_test_result VARCHAR,
    safety_equipment_used VARCHAR,
    ejection_status VARCHAR,
    contact_eligibility_status VARCHAR DEFAULT 'PENDING_REVIEW',
    ineligibility_reasons VARCHAR[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_fact_crash_timestamp ON fact_crash(crash_timestamp);
CREATE INDEX IF NOT EXISTS idx_fact_crash_h3_res8 ON fact_crash(h3_res8);
CREATE INDEX IF NOT EXISTS idx_fact_crash_county ON fact_crash(county_fips);
CREATE INDEX IF NOT EXISTS idx_fact_crash_severity ON fact_crash(severity_kabc0);
CREATE INDEX IF NOT EXISTS idx_fact_party_crash_id ON fact_party(crash_id);
CREATE INDEX IF NOT EXISTS idx_fact_party_eligibility ON fact_party(contact_eligibility_status);
"""


def init_gold_database(conn: Optional[duckdb.DuckDBPyConnection] = None, db_path: str = ":memory:") -> duckdb.DuckDBPyConnection:
    """Initialize DuckDB database with the gold star schema tables and indexes.

    Parameters
    ----------
    conn:
        Optional existing DuckDB connection.
    db_path:
        File path to DuckDB database, or ':memory:' for in-memory database.

    Returns
    -------
    Connected DuckDB connection with gold schema applied.
    """
    if conn is None:
        conn = duckdb.connect(db_path)

    # Load spatial extension if available
    try:
        conn.execute("INSTALL spatial; LOAD spatial;")
    except Exception:
        pass  # spatial extension may not be installed in minimal test environments

    conn.execute(DIM_SEVERITY_DDL)
    conn.execute(POPULATE_DIM_SEVERITY_SQL)
    conn.execute(DIM_LOCATION_DDL)
    conn.execute(FACT_CRASH_DDL)
    conn.execute(FACT_PARTY_DDL)
    conn.execute(CREATE_INDEXES_SQL)

    return conn
