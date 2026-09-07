"""Tests for TxDOT CRIS data quality defects."""

import pytest

from src.transforms.txdot_silver import (
    apply_scd2_amendments,
    parse_string_dates,
    resolve_coordinates,
)


# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def records_with_competing_coords():
    """Records with two competing coordinate pairs."""
    return [
        # Both present, close together → no conflict
        {
            "attributes": {
                "crash_id": 1,
                "latitude": 30.2672, "longitude": -97.7431,
                "rpt_latitude": 30.2670, "rpt_longitude": -97.7430,
                "located_fl": "Y",
            }
        },
        # Both present, far apart → conflict
        {
            "attributes": {
                "crash_id": 2,
                "latitude": 30.2672, "longitude": -97.7431,
                "rpt_latitude": 29.7604, "rpt_longitude": -95.3698,  # Houston vs Austin
                "located_fl": "Y",
            }
        },
        # Only CRIS coords
        {
            "attributes": {
                "crash_id": 3,
                "latitude": 32.7767, "longitude": -96.7970,
                "rpt_latitude": None, "rpt_longitude": None,
                "located_fl": "Y",
            }
        },
        # Only officer coords
        {
            "attributes": {
                "crash_id": 4,
                "latitude": None, "longitude": None,
                "rpt_latitude": 29.4241, "rpt_longitude": -98.4936,
                "located_fl": "N",
            }
        },
        # No coords at all
        {
            "attributes": {
                "crash_id": 5,
                "latitude": None, "longitude": None,
                "rpt_latitude": None, "rpt_longitude": None,
                "located_fl": "N",
            }
        },
    ]


@pytest.fixture
def records_for_scd2():
    """Records simulating an amended report."""
    return [
        {"attributes": {"crash_id": 100, "death_cnt": 1, "amend_supp_fl": "N"}},
        {"attributes": {"crash_id": 200, "death_cnt": 0, "amend_supp_fl": "Y"}},  # Amended
        {"attributes": {"crash_id": 300, "death_cnt": 2, "amend_supp_fl": "N"}},  # New
    ]


# ── Test: Coordinate precedence ─────────────────────────────────────────


class TestCoordinatePrecedence:
    def test_cris_coords_preferred(self, records_with_competing_coords):
        """CRIS-derived coordinates are used when available."""
        result = resolve_coordinates(records_with_competing_coords)
        r1 = result[0]["attributes"]
        assert r1["coord_source"] == "cris"
        assert r1["resolved_latitude"] == 30.2672

    def test_conflict_detected(self, records_with_competing_coords):
        """Coordinate conflict is flagged when pairs disagree by >500m."""
        result = resolve_coordinates(records_with_competing_coords)
        r2 = result[1]["attributes"]
        assert r2["coord_conflict"] is True  # Austin vs Houston

    def test_officer_fallback(self, records_with_competing_coords):
        """Officer coords used when CRIS not available."""
        result = resolve_coordinates(records_with_competing_coords)
        r4 = result[3]["attributes"]
        assert r4["coord_source"] == "officer"
        assert r4["resolved_latitude"] == 29.4241

    def test_no_coords_handled(self, records_with_competing_coords):
        """Records with no coordinates get coord_source='none'."""
        result = resolve_coordinates(records_with_competing_coords)
        r5 = result[4]["attributes"]
        assert r5["coord_source"] == "none"
        assert r5["resolved_latitude"] is None


# ── Test: SCD2 amendments ───────────────────────────────────────────────


class TestSCD2Amendments:
    def test_new_records_get_version_1(self, records_for_scd2):
        """New records (no existing data) are version 1."""
        result = apply_scd2_amendments(records_for_scd2)
        for r in result:
            attrs = r["attributes"]
            assert attrs["version"] >= 1
            assert attrs["is_current"] is True

    def test_amended_record_creates_new_version(self):
        """An amended record supersedes the existing version."""
        existing = {
            200: {"attributes": {"crash_id": 200, "death_cnt": 0, "version": 1, "is_current": True}},
        }
        new_records = [
            {"attributes": {"crash_id": 200, "death_cnt": 1, "amend_supp_fl": "Y"}},
        ]
        result = apply_scd2_amendments(new_records, existing_records=existing)

        versions = [r["attributes"] for r in result]
        old_version = next(v for v in versions if v.get("version") == 1)
        new_version = next(v for v in versions if v.get("version") == 2)

        assert old_version["is_current"] is False
        assert old_version["valid_to"] is not None
        assert new_version["is_current"] is True
        assert new_version["death_cnt"] == 1


# ── Test: String date parsing ───────────────────────────────────────────


class TestStringDates:
    def test_iso_format_parsed(self):
        records = [{"attributes": {"crash_date": "2024-03-15"}}]
        result = parse_string_dates(records)
        assert result[0]["attributes"]["crash_date_parsed"] == "2024-03-15"

    def test_us_format_parsed(self):
        records = [{"attributes": {"crash_date": "03/15/2024"}}]
        result = parse_string_dates(records)
        assert result[0]["attributes"]["crash_date_parsed"] == "2024-03-15"

    def test_null_handled(self):
        records = [{"attributes": {"crash_date": None}}]
        result = parse_string_dates(records)
        assert "crash_date_parsed" not in result[0]["attributes"]
