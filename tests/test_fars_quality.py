"""Tests for FARS data quality defects — sentinel values."""

import pytest

from src.transforms.fars_silver import (
    construct_timestamps,
    replace_coordinate_sentinels,
    replace_integer_sentinels,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def records_with_sentinel_coords():
    """FARS records with sentinel coordinate values."""
    return [
        # Valid coordinates (Washington DC area)
        {"STATE": 11, "ST_CASE": 1, "LATITUDE": 38.9072, "LONGITUD": -77.0369},
        # 77.7777 sentinel — would place crash at ~78°N (Arctic Ocean)
        {"STATE": 48, "ST_CASE": 2, "LATITUDE": 77.7777, "LONGITUD": -97.0},
        # 88.8888 sentinel
        {"STATE": 24, "ST_CASE": 3, "LATITUDE": 88.8888, "LONGITUD": 88.8888},
        # 99.9999 sentinel
        {"STATE": 12, "ST_CASE": 4, "LATITUDE": 99.9999, "LONGITUD": 99.9999},
        # Already null
        {"STATE": 48, "ST_CASE": 5, "LATITUDE": None, "LONGITUD": None},
    ]


@pytest.fixture
def records_with_sentinel_integers():
    """FARS records with sentinel integer values."""
    return [
        {
            "STATE": 24,
            "ST_CASE": 1,
            "AGE": 35,
            "HOUR": 14,
            "MINUTE": 30,
            "WEATHER": 1,
            "DRINKING": 0,
        },
        {
            "STATE": 24,
            "ST_CASE": 2,
            "AGE": 999,
            "HOUR": 99,
            "MINUTE": 99,
            "WEATHER": 9,
            "DRINKING": 9,
        },
        {
            "STATE": 24,
            "ST_CASE": 3,
            "AGE": 998,
            "HOUR": 8,
            "MINUTE": 15,
            "WEATHER": 8,
            "DRINKING": 0,
        },
    ]


# ── Test: Coordinate sentinels ──────────────────────────────────────────


class TestCoordinateSentinels:
    def test_raw_data_has_sentinel_coords(self, records_with_sentinel_coords):
        """The defect exists: sentinel values look like real coordinates."""
        lats = [r["LATITUDE"] for r in records_with_sentinel_coords if r["LATITUDE"]]
        assert 77.7777 in lats, "Expected 77.7777 sentinel"
        assert 88.8888 in lats, "Expected 88.8888 sentinel"
        assert 99.9999 in lats, "Expected 99.9999 sentinel"

    def test_sentinels_replaced_with_null(self, records_with_sentinel_coords):
        """After transform, sentinel coords are None."""
        result = replace_coordinate_sentinels(records_with_sentinel_coords)

        # Valid record preserved
        r1 = result[0]
        assert r1["LATITUDE"] == 38.9072
        assert r1["coord_quality"] == "valid"

        # Sentinels replaced
        for r in result[1:4]:
            assert r["LATITUDE"] is None
            assert r["LONGITUD"] is None
            assert r["coord_quality"] == "sentinel_removed"

    def test_already_null_handled(self, records_with_sentinel_coords):
        """Records with null coords are flagged as missing."""
        result = replace_coordinate_sentinels(records_with_sentinel_coords)
        r5 = result[4]
        assert r5["coord_quality"] == "missing"


# ── Test: Integer sentinels ─────────────────────────────────────────────


class TestIntegerSentinels:
    def test_raw_data_has_sentinel_integers(self, records_with_sentinel_integers):
        """The defect exists: 998/999/99/9 used for unknown."""
        ages = [r["AGE"] for r in records_with_sentinel_integers]
        assert 999 in ages
        assert 998 in ages

    def test_sentinels_replaced(self, records_with_sentinel_integers):
        """After transform, sentinel integers are None."""
        result = replace_integer_sentinels(records_with_sentinel_integers)

        # Valid record preserved
        assert result[0]["AGE"] == 35
        assert result[0]["HOUR"] == 14
        assert result[0]["WEATHER"] == 1

        # Sentinels replaced
        assert result[1]["AGE"] is None
        assert result[1]["HOUR"] is None
        assert result[1]["WEATHER"] is None
        assert result[1]["DRINKING"] is None

        # Partial sentinels
        assert result[2]["AGE"] is None  # 998
        assert result[2]["HOUR"] == 8  # Valid
        assert result[2]["WEATHER"] is None  # 8-fill


# ── Test: Timestamps ────────────────────────────────────────────────────


class TestTimestamps:
    def test_complete_timestamp(self):
        records = [{"YEAR": 2024, "MONTH": 3, "DAY": 15, "HOUR": 14, "MINUTE": 30}]
        result = construct_timestamps(records)
        assert result[0]["crash_timestamp"] == "2024-03-15T14:30:00"
        assert result[0]["timestamp_quality"] == "complete"

    def test_sentinel_hour_produces_date_only(self):
        """After sentinel replacement, unknown hour → date-only timestamp."""
        records = [{"YEAR": 2024, "MONTH": 3, "DAY": 15, "HOUR": None, "MINUTE": None}]
        result = construct_timestamps(records)
        assert result[0]["timestamp_quality"] == "date_only"
        assert result[0]["crash_timestamp"] == "2024-03-15T00:00:00"
