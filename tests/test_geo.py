"""Tests for geospatial enrichment modules (CRS, Timezone, H3, Census, Road Snapping, Weather)."""

from datetime import datetime, timezone
import pytest

from src.geo.census_enrichment import enrich_census_demographics, match_coordinate_to_county
from src.geo.crs import BOUNDS_MONTGOMERY_MD, BOUNDS_TEXAS, is_in_bounding_box, reproject_point
from src.geo.h3_index import get_h3_indices, get_k_ring, point_to_h3
from src.geo.road_snap import snap_crash_to_roadway
from src.geo.timezone import get_iana_timezone, get_local_datetime, is_within_statutory_contact_hours
from src.geo.weather_join import infer_weather_observation


def test_crs_bounding_boxes():
    # Rockville, MD (inside Montgomery County)
    assert is_in_bounding_box(39.084, -77.152, BOUNDS_MONTGOMERY_MD) is True
    # Philadelphia (outside Montgomery County)
    assert is_in_bounding_box(39.952, -75.165, BOUNDS_MONTGOMERY_MD) is False

    # Austin, TX (inside Texas)
    assert is_in_bounding_box(30.267, -97.743, BOUNDS_TEXAS) is True
    # None coordinates
    assert is_in_bounding_box(None, None, BOUNDS_TEXAS) is False


def test_crs_reproject():
    x, y = reproject_point(39.084, -77.152)
    assert isinstance(x, float)
    assert isinstance(y, float)


def test_timezone_derivation():
    # Rockville, MD -> Eastern
    assert get_iana_timezone(39.084, -77.152) == "America/New_York"
    # Austin, TX -> Central
    assert get_iana_timezone(30.267, -97.743) == "America/Chicago"
    # El Paso, TX -> Mountain
    assert get_iana_timezone(31.761, -106.485) == "America/Denver"


def test_statutory_contact_hours():
    # 10:00 AM local -> within window
    dt_valid = datetime(2024, 6, 15, 10, 0)
    assert is_within_statutory_contact_hours(dt_valid) is True

    # 7:30 AM local -> before 8 AM (violates TCPA)
    dt_early = datetime(2024, 6, 15, 7, 30)
    assert is_within_statutory_contact_hours(dt_early) is False

    # 9:15 PM local (21:15) -> after 9 PM (violates TCPA)
    dt_late = datetime(2024, 6, 15, 21, 15)
    assert is_within_statutory_contact_hours(dt_late) is False


def test_h3_indices():
    lat, lon = 39.084, -77.152
    h3_8, h3_9 = get_h3_indices(lat, lon)
    assert h3_8 is not None
    assert h3_9 is not None
    assert len(h3_8) == 15
    assert len(h3_9) == 15

    neighbors = get_k_ring(h3_8, k=1)
    assert len(neighbors) >= 1


def test_census_enrichment():
    lat, lon = 39.084, -77.152
    res = enrich_census_demographics(lat, lon)
    assert res is not None
    assert res.county_fips == "24031"
    assert res.state_fips == "24"
    assert len(res.geoid) == 11
    assert res.median_household_income is not None
    assert res.median_household_income > 100000


def test_road_snapping():
    # Near Rockville Pike (MD 355)
    lat, lon = 39.0845, -77.1525
    result = snap_crash_to_roadway(lat, lon)
    assert result is not None
    assert "Rockville Pike" in result.road_name or "MD" in result.road_name
    assert result.distance_to_road_meters < 50.0
    assert result.speed_limit_mph > 0


def test_weather_join():
    obs = infer_weather_observation(
        datetime(2024, 1, 15, 12, 0),
        raw_weather_desc="RAINING",
        raw_surface_desc="WET",
    )
    assert obs.weather_condition == "RAIN"
    assert obs.surface_condition == "WET"
    assert obs.is_adverse_weather is True
