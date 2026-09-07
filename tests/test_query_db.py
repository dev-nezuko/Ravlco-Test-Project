"""Command-line checks for query_db.py against a freshly built demo database."""

import subprocess
import sys
from pathlib import Path

import pytest

from run_pipeline import run_pipeline

QUERY_DB = Path(__file__).resolve().parent.parent / "query_db.py"


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("query") / "gold.duckdb"
    run_pipeline(db_path=str(db))
    return db


def _query(*args):
    return subprocess.run(
        [sys.executable, str(QUERY_DB), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize("preset", ["1", "2", "3", "4", "5"])
def test_every_preset_runs(demo_db, preset):
    result = _query("--db", str(demo_db), "--preset", preset)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Query failed" not in result.stdout


def test_scored_leads_preset_lists_the_eligible_party_first(demo_db):
    result = _query("--db", str(demo_db), "--preset", "5")
    rows = [line for line in result.stdout.splitlines() if line.strip().startswith("P_")]
    assert rows[0].split()[0] == "P_MD_001"


def test_bad_sql_exits_nonzero(demo_db):
    result = _query("--db", str(demo_db), "--sql", "SELECT * FROM no_such_table")
    assert result.returncode == 1
    assert "Query failed" in result.stdout


def test_missing_database_exits_nonzero(tmp_path):
    result = _query("--db", str(tmp_path / "absent.duckdb"), "--preset", "1")
    assert result.returncode == 1
