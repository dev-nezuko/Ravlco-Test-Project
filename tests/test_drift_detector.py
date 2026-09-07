"""Tests for upstream schema and distribution drift detection."""

import pytest

from src.contracts.drift_detector import SchemaBaseline, detect_drift


@pytest.fixture
def sample_baseline():
    return SchemaBaseline(
        expected_columns={
            "report_number",
            "crash_date",
            "injury_severity",
            "latitude",
            "longitude",
        },
        required_columns={"report_number", "crash_date"},
        known_categories={"injury_severity": {"FATAL", "SERIOUS", "MINOR", "NONE", "UNKNOWN"}},
        max_null_rates={"crash_date": 0.01},
        expected_min_rows=5,
    )


def test_drift_detector_normal_batch(sample_baseline):
    records = [
        {
            "report_number": f"R_{i}",
            "crash_date": "2024-01-01",
            "injury_severity": "MINOR",
            "latitude": 39.0,
            "longitude": -77.1,
        }
        for i in range(10)
    ]
    report = detect_drift("test_ds", records, sample_baseline, historical_row_count=10)
    assert report.has_drift is False
    assert report.total_anomalies == 0


def test_drift_detector_missing_required_column(sample_baseline):
    # Missing 'crash_date'
    records = [{"report_number": f"R_{i}", "injury_severity": "MINOR"} for i in range(10)]
    report = detect_drift("test_ds", records, sample_baseline)
    assert report.has_drift is True
    assert any("crash_date" in s for s in report.schema_anomalies)


def test_drift_detector_unmapped_category(sample_baseline):
    records = [
        {
            "report_number": f"R_{i}",
            "crash_date": "2024-01-01",
            "injury_severity": "NEW_UNSEEN_VALUE",
        }
        for i in range(10)
    ]
    report = detect_drift("test_ds", records, sample_baseline)
    assert report.has_drift is True
    assert any("NEW_UNSEEN_VALUE" in s for s in report.unmapped_categories)


def test_drift_detector_volume_collapse(sample_baseline):
    # Only 2 rows when baseline history was 100 (>30% drop)
    records = [
        {"report_number": "R_1", "crash_date": "2024-01-01"},
        {"report_number": "R_2", "crash_date": "2024-01-01"},
    ]
    report = detect_drift("test_ds", records, sample_baseline, historical_row_count=100)
    assert report.has_drift is True
    assert any("Volume drop" in v for v in report.volume_anomalies)
