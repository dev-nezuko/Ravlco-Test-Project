"""Tests for Montgomery County data quality defects.

Each test demonstrates that the defect exists in raw data and is
handled correctly after the silver transform.
"""

import pytest

from src.transforms.moco_silver import (
    enforce_crash_grain,
    flag_out_of_envelope,
    harmonize_substance_abuse,
    quantify_report_number_disagreement,
    validate_driver_grain,
)

# ── Fixtures: synthetic data mimicking real defects ──────────────────────


@pytest.fixture
def raw_incidents_with_bad_coords():
    """Incidents with coordinates outside Montgomery County."""
    return [
        # Valid: inside MoCo
        {
            "report_number": "R001",
            "latitude": 39.1,
            "longitude": -77.2,
            "crash_date_time": "2024-01-15",
        },
        # Defect: ~150 miles away (Philadelphia area)
        {
            "report_number": "R002",
            "latitude": 39.95,
            "longitude": -75.17,
            "crash_date_time": "2024-01-16",
        },
        # Defect: in Florida
        {
            "report_number": "R003",
            "latitude": 25.76,
            "longitude": -80.19,
            "crash_date_time": "2024-01-17",
        },
        # Valid: near border (Rockville)
        {
            "report_number": "R004",
            "latitude": 39.08,
            "longitude": -77.15,
            "crash_date_time": "2024-01-18",
        },
    ]


@pytest.fixture
def raw_drivers_mixed_substance():
    """Drivers with mixed old/new substance abuse dictionary."""
    return [
        # Old scheme (pre-2024)
        {
            "report_number": "R001",
            "person_id": "P1",
            "driver_substance_abuse": "NONE DETECTED",
            "crash_date_time": "2023-06-01",
        },
        {
            "report_number": "R002",
            "person_id": "P1",
            "driver_substance_abuse": "ALCOHOL PRESENT",
            "crash_date_time": "2023-07-01",
        },
        # New scheme (post-2024)
        {
            "report_number": "R003",
            "person_id": "P1",
            "driver_substance_abuse": "Not Suspect of Alcohol Use, Not Suspect of Drug Use",
            "crash_date_time": "2024-03-01",
        },
        {
            "report_number": "R004",
            "person_id": "P1",
            "driver_substance_abuse": "Suspected Alcohol Use, Not Suspect of Drug Use",
            "crash_date_time": "2024-04-01",
        },
        # Overlap window (Jan 2024) — both schemes coexist
        {
            "report_number": "R005",
            "person_id": "P1",
            "driver_substance_abuse": "NONE DETECTED",
            "crash_date_time": "2024-01-02",
        },
        {
            "report_number": "R006",
            "person_id": "P1",
            "driver_substance_abuse": "Not Suspect of Alcohol Use, Not Suspect of Drug Use",
            "crash_date_time": "2024-01-03",
        },
        # Null spellings
        {
            "report_number": "R007",
            "person_id": "P1",
            "driver_substance_abuse": "UNKNOWN",
            "crash_date_time": "2023-05-01",
        },
        {
            "report_number": "R008",
            "person_id": "P1",
            "driver_substance_abuse": None,
            "crash_date_time": "2023-04-01",
        },
        {
            "report_number": "R009",
            "person_id": "P1",
            "driver_substance_abuse": "N/A",
            "crash_date_time": "2023-03-01",
        },
    ]


@pytest.fixture
def incidents_and_drivers_with_disagreement():
    """Incidents and Drivers that disagree on report_number universe."""
    incidents = [
        {"report_number": "R001", "crash_date_time": "2024-01-01"},
        {"report_number": "R002", "crash_date_time": "2024-01-02"},
        {"report_number": "R003", "crash_date_time": "2024-01-03"},  # Incidents-only
    ]
    drivers = [
        {"report_number": "R001", "person_id": "P1", "crash_date_time": "2024-01-01"},
        {"report_number": "R002", "person_id": "P1", "crash_date_time": "2024-01-02"},
        {
            "report_number": "R004",
            "person_id": "P1",
            "crash_date_time": "2024-01-04",
        },  # Drivers-only
    ]
    return incidents, drivers


# ── Test 1: Coordinate envelope ─────────────────────────────────────────


class TestCoordinateEnvelope:
    """Verify that out-of-envelope coordinates are detected and flagged."""

    def test_raw_data_has_out_of_bounds(self, raw_incidents_with_bad_coords):
        """The defect exists: raw data has coords outside MoCo."""
        lats = [r["latitude"] for r in raw_incidents_with_bad_coords]
        # Philadelphia and Florida coords are present
        assert any(lat < 30 for lat in lats), "Expected Florida-range latitude"
        assert any(lat > 39.4 for lat in lats), "Expected Philly-range latitude"

    def test_transform_flags_out_of_bounds(self, raw_incidents_with_bad_coords):
        """After transform, out-of-bounds records are flagged, not dropped."""
        result = flag_out_of_envelope(raw_incidents_with_bad_coords)

        # All records are preserved (not dropped)
        assert len(result) == 4

        # Valid records are marked valid
        valid = [r for r in result if r["coord_quality"] == "valid"]
        assert len(valid) == 2  # R001, R004

        # Out-of-bounds records are flagged
        oob = [r for r in result if r["coord_quality"] == "out_of_bounds"]
        assert len(oob) == 2  # R002 (Philly), R003 (Florida)

    def test_distance_computed(self, raw_incidents_with_bad_coords):
        """Distance from centroid is computed for quality reporting."""
        result = flag_out_of_envelope(raw_incidents_with_bad_coords)
        for r in result:
            assert "coord_distance_from_centroid_km" in r
            if r["coord_quality"] == "out_of_bounds":
                assert r["coord_distance_from_centroid_km"] > 50  # Well outside


# ── Test 2: Substance abuse dictionary ──────────────────────────────────


class TestSubstanceAbuse:
    """Verify that mixed substance abuse dictionaries are harmonized."""

    def test_raw_data_has_mixed_schemes(self, raw_drivers_mixed_substance):
        """The defect exists: both old and new schemes are present."""
        values = [
            r["driver_substance_abuse"]
            for r in raw_drivers_mixed_substance
            if r["driver_substance_abuse"]
        ]
        has_old = any(v == v.upper() and v not in {"N/A", "UNKNOWN"} for v in values if v)
        has_new = any("," in v for v in values if v)
        assert has_old, "Expected old-scheme (CAPS) values"
        assert has_new, "Expected new-scheme (comma-joined) values"

    def test_transform_harmonizes_both_schemes(self, raw_drivers_mixed_substance):
        """After transform, both schemes map to standardized fields."""
        result = harmonize_substance_abuse(raw_drivers_mixed_substance)

        for r in result:
            assert "substance_alcohol_status" in r
            assert "substance_drug_status" in r
            assert "substance_scheme" in r

    def test_old_scheme_mapped_correctly(self, raw_drivers_mixed_substance):
        """Old scheme values produce correct harmonized output."""
        result = harmonize_substance_abuse(raw_drivers_mixed_substance)

        r001 = next(r for r in result if r["report_number"] == "R001")
        assert r001["substance_alcohol_status"] == "no_alcohol"
        assert r001["substance_drug_status"] == "no_drug"
        assert r001["substance_scheme"] == "old"

        r002 = next(r for r in result if r["report_number"] == "R002")
        assert r002["substance_alcohol_status"] == "alcohol_present"
        assert r002["substance_scheme"] == "old"

    def test_new_scheme_mapped_correctly(self, raw_drivers_mixed_substance):
        """New scheme values produce correct harmonized output."""
        result = harmonize_substance_abuse(raw_drivers_mixed_substance)

        r003 = next(r for r in result if r["report_number"] == "R003")
        assert r003["substance_alcohol_status"] == "no_alcohol"
        assert r003["substance_drug_status"] == "no_drug"
        assert r003["substance_scheme"] == "new"

        r004 = next(r for r in result if r["report_number"] == "R004")
        assert r004["substance_alcohol_status"] == "suspected_alcohol"
        assert r004["substance_scheme"] == "new"

    def test_null_spellings_handled(self, raw_drivers_mixed_substance):
        """All null variants map to unknown status."""
        result = harmonize_substance_abuse(raw_drivers_mixed_substance)

        for rn in ["R007", "R008", "R009"]:
            r = next(r for r in result if r["report_number"] == rn)
            assert r["substance_scheme"] == "null"
            assert r["substance_alcohol_status"] == "unknown_alcohol"

    def test_overlap_window_handled(self, raw_drivers_mixed_substance):
        """Both schemes in the Jan 2024 overlap are handled by pattern, not date."""
        result = harmonize_substance_abuse(raw_drivers_mixed_substance)

        r005 = next(r for r in result if r["report_number"] == "R005")
        assert r005["substance_scheme"] == "old"  # CAPS → old

        r006 = next(r for r in result if r["report_number"] == "R006")
        assert r006["substance_scheme"] == "new"  # comma-joined → new


# ── Test 3: Report number disagreement ──────────────────────────────────


class TestReportNumberDisagreement:
    """Verify that the Incidents/Drivers anti-join is quantified."""

    def test_raw_data_disagrees(self, incidents_and_drivers_with_disagreement):
        """The defect exists: Incidents and Drivers have different report_number sets."""
        incidents, drivers = incidents_and_drivers_with_disagreement
        incident_ids = {r["report_number"] for r in incidents}
        driver_ids = {r["report_number"] for r in drivers}
        assert incident_ids != driver_ids

    def test_disagreement_quantified(self, incidents_and_drivers_with_disagreement):
        """After analysis, the disagreement is fully quantified."""
        incidents, drivers = incidents_and_drivers_with_disagreement
        result = quantify_report_number_disagreement(incidents, drivers)

        assert result["incidents_only"] == 1  # R003
        assert result["drivers_only"] == 1  # R004
        assert result["shared"] == 2  # R001, R002


# ── Test 4: Grain enforcement ───────────────────────────────────────────


class TestGrainEnforcement:
    """Verify crash-level grain is enforced on Incidents."""

    def test_duplicates_deduplicated(self):
        """Duplicate report_numbers in incidents are resolved."""
        incidents = [
            {"report_number": "R001", "crash_date_time": "2024-01-01T10:00:00", "weather": "CLEAR"},
            {
                "report_number": "R001",
                "crash_date_time": "2024-01-01T10:00:00",
                "weather": "RAIN",
            },  # Duplicate
            {"report_number": "R002", "crash_date_time": "2024-01-02T11:00:00", "weather": "CLEAR"},
        ]
        result = enforce_crash_grain(incidents)
        assert len(result) == 2  # One per report_number

    def test_driver_grain_validated(self):
        """Driver grain (report_number, person_id) is checked."""
        drivers = [
            {"report_number": "R001", "person_id": "P1"},
            {"report_number": "R001", "person_id": "P2"},  # Different person, OK
            {"report_number": "R002", "person_id": "P1"},
        ]
        result = validate_driver_grain(drivers)
        assert len(result) == 3  # All valid, no duplicates
