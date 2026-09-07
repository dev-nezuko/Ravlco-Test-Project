"""Interactive DuckDB query helper and presentation tool for live demonstrations.

Usage:
    python query_db.py               # Interactive menu of interviewer queries
    python query_db.py --sql "..."   # Run a one-liner SQL query directly
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

DEFAULT_DB = "data/crash_analytics.duckdb"

PRESET_QUERIES = {
    "1": (
        "Table Record Counts & Overview",
        """
        SELECT 'fact_crash' AS table_name, count(*) AS row_count FROM fact_crash
        UNION ALL
        SELECT 'fact_party' AS table_name, count(*) AS row_count FROM fact_party
        UNION ALL
        SELECT 'dim_location' AS table_name, count(*) AS row_count FROM dim_location
        UNION ALL
        SELECT 'dim_severity' AS table_name, count(*) AS row_count FROM dim_severity;
        """,
    ),
    "2": (
        "Harmonized KABCO Severity Distribution (FHWA / ANSI D16.1)",
        """
        SELECT
            s.severity_code,
            s.severity_name,
            s.rank,
            count(c.crash_id) AS total_crashes,
            round(count(c.crash_id) * 100.0 / sum(count(c.crash_id)) OVER(), 1) AS pct_of_total
        FROM dim_severity s
        LEFT JOIN fact_crash c ON s.severity_code = c.severity_kabc0
        GROUP BY s.severity_code, s.severity_name, s.rank
        ORDER BY s.rank DESC;
        """,
    ),
    "3": (
        "Compliance Gate Breakdown: Status & Statutory Citations",
        """
        SELECT
            p.source_system,
            p.contact_eligibility_status,
            COALESCE(array_to_string(p.ineligibility_reasons, '; '), 'NONE (PASSED)') AS citations,
            count(*) AS party_count
        FROM fact_party p
        GROUP BY p.source_system, p.contact_eligibility_status, citations
        ORDER BY p.source_system;
        """,
    ),
    "4": (
        "Geospatial Enrichment: H3 Hexagonal Indices, Road Snapping & Timezones",
        """
        SELECT
            c.crash_id,
            c.source_system,
            loc.nearest_road_name,
            loc.speed_limit,
            loc.h3_res8,
            loc.h3_res9,
            loc.timezone_iana,
            c.weather_condition,
            c.road_condition
        FROM fact_crash c
        JOIN dim_location loc ON c.crash_id = REPLACE(loc.location_id, 'LOC_', '')
        ORDER BY c.crash_id;
        """,
    ),
    "5": (
        "Actionable Scored Leads vs Disqualified Records",
        """
        SELECT
            p.party_id,
            p.crash_id,
            p.source_system,
            p.contact_eligibility_status,
            s.severity_name,
            p.age,
            loc.nearest_road_name
        FROM fact_party p
        JOIN dim_severity s ON p.injury_severity = s.severity_code
        JOIN dim_location loc ON p.crash_id = REPLACE(loc.location_id, 'LOC_', '')
        ORDER BY p.contact_eligibility_status ASC, p.party_id;
        """,
    ),
}


def execute_query(conn: duckdb.DuckDBPyConnection, sql: str, title: str = "") -> None:
    """Print SQL query results formatted as a clean table."""
    print("\n" + "─" * 75)
    if title:
        print(f"📋 {title}")
    print("─" * 75)
    print(f"SQL: {sql.strip()}\n")
    try:
        df = conn.execute(sql).fetchdf()
        if df.empty:
            print("   (0 rows returned)")
        else:
            print(df.to_string(index=False))
    except Exception as e:
        print(f"❌ Error executing query: {e}")
    print("─" * 75)


def interactive_menu(db_path: str) -> None:
    if not Path(db_path).exists():
        print(f"❌ Database not found at '{db_path}'.")
        print("💡 Run the pipeline first to generate the database:")
        print("   python run_pipeline.py\n")
        return

    conn = duckdb.connect(db_path, read_only=True)

    while True:
        print("\n" + "=" * 60)
        print("🔍 CRASH ANALYTICS — LIVE DUCKDB QUERY CONSOLE")
        print(f"   Database: {db_path}")
        print("=" * 60)
        for k, (title, _) in PRESET_QUERIES.items():
            print(f"  [{k}] {title}")
        print("  [S] Custom SQL query")
        print("  [Q] Exit")
        print("=" * 60)

        choice = input("\nEnter choice [1-5, S, Q]: ").strip()
        if choice.lower() in ("q", "quit", "exit"):
            print("Exiting query console. Goodbye!")
            break

        if choice in PRESET_QUERIES:
            title, sql = PRESET_QUERIES[choice]
            execute_query(conn, sql, title)
        elif choice.lower() == "s":
            custom_sql = input("\nEnter SQL query: ").strip()
            if custom_sql:
                execute_query(conn, custom_sql, "Custom Query Result")
        else:
            print("Invalid selection. Try again.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query DuckDB Crash Database")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to DuckDB database")
    parser.add_argument("--sql", help="Run a one-shot SQL query and exit")
    args = parser.parse_args()

    if args.sql:
        if not Path(args.db).exists():
            print(f"❌ Database '{args.db}' not found. Run 'python run_pipeline.py' first.")
            sys.exit(1)
        c = duckdb.connect(args.db, read_only=True)
        execute_query(c, args.sql, "Query Result")
        c.close()
    else:
        interactive_menu(args.db)
