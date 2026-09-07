"""End-to-end checks of the demo pipeline runner against a temporary DuckDB file."""

import duckdb

from run_pipeline import run_pipeline


def _rows(db_path, sql):
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_rerun_replaces_demo_rows(tmp_path):
    db = tmp_path / "gold.duckdb"
    run_pipeline(db_path=str(db))
    run_pipeline(db_path=str(db))

    counts = _rows(
        db,
        "SELECT (SELECT count(*) FROM fact_crash), (SELECT count(*) FROM fact_party), "
        "(SELECT count(*) FROM dim_location)",
    )
    assert counts == [(4, 4, 4)]


def test_location_state_comes_from_coordinates(tmp_path):
    db = tmp_path / "gold.duckdb"
    run_pipeline(db_path=str(db))

    states = dict(_rows(db, "SELECT location_id, state_abbr FROM dim_location"))
    assert states == {
        "LOC_MD_2024_001": "MD",
        "LOC_MD_2024_002": "MD",
        "LOC_TX_2024_003": "TX",
        "LOC_FARS_2024_004": "MD",
    }


def test_crash_far_from_sample_roads_gets_no_road(tmp_path):
    db = tmp_path / "gold.duckdb"
    run_pipeline(db_path=str(db))

    road = _rows(
        db,
        "SELECT nearest_road_name, speed_limit FROM dim_location "
        "WHERE location_id = 'LOC_TX_2024_003'",
    )
    assert road == [(None, None)]


def test_lead_scores_are_persisted_and_gated(tmp_path):
    db = tmp_path / "gold.duckdb"
    run_pipeline(db_path=str(db))

    scores = {
        party_id: (status, score, tier)
        for party_id, status, score, tier in _rows(
            db,
            "SELECT party_id, contact_eligibility_status, lead_score, priority_tier "
            "FROM fact_party",
        )
    }
    status, score, tier = scores["P_MD_001"]
    assert status == "ELIGIBLE"
    assert score > 0
    assert tier in {"HIGH", "MEDIUM", "LOW"}
    for party_id in ("P_MD_002", "P_TX_003", "P_FARS_004"):
        assert scores[party_id] == ("INELIGIBLE", 0.0, "DISQUALIFIED")
