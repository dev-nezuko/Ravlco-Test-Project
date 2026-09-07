"""Tests for lead qualification scoring and spatial autocorrelation (Getis-Ord Gi*, LISA)."""

from datetime import UTC, datetime, timedelta

from src.analysis.spatial import compute_getis_ord_gi, compute_local_morans_i
from src.scoring.lead_score import calculate_recency_points, score_lead


def test_lead_scoring_eligible_high_priority():
    t_crash = datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    eval_time = t_crash + timedelta(days=35)  # Day 35

    crash = {
        "crash_id": "CRASH_HIGH",
        "severity_kabc0": "A",
        "vehicle_count": 2,
        "is_commercial_vehicle": True,
        "functional_class": "ARTERIAL",
        "crash_timestamp": t_crash,
    }
    party = {
        "party_id": "PARTY_HIGH",
        "contact_eligibility_status": "ELIGIBLE",
        "injury_severity": "A",
        "person_type": "DRIVER",
    }

    result = score_lead(party, crash, evaluation_time=eval_time)
    assert result.is_actionable is True
    assert result.priority_tier == "HIGH"
    assert result.composite_score >= 60.0
    assert result.severity_points == 40.0
    assert result.dynamics_points >= 15.0


def test_lead_scoring_compliance_hard_gate():
    """Verify ineligible leads receive composite score 0.0 and DISQUALIFIED tier."""
    crash = {
        "crash_id": "CRASH_DISQ",
        "severity_kabc0": "A",
        "vehicle_count": 3,
        "is_commercial_vehicle": True,
    }
    party = {
        "party_id": "PARTY_DISQ",
        "contact_eligibility_status": "INELIGIBLE",
        "ineligibility_reasons": ["TEX_PENAL_CODE_38_12", "TEX_TRANSP_CODE_550_065"],
        "injury_severity": "A",
        "person_type": "DRIVER",
    }

    result = score_lead(party, crash)
    assert result.is_actionable is False
    assert result.composite_score == 0.0
    assert result.priority_tier == "DISQUALIFIED"
    assert "TEX_PENAL_CODE_38_12" in result.disqualification_reasons


def test_recency_decay():
    t_crash = datetime(2024, 1, 1, tzinfo=UTC)
    # Day 15 (blackout) -> 0 pts
    assert calculate_recency_points(t_crash, t_crash + timedelta(days=15)) == 0.0

    # Day 31 -> near full points (~10 pts)
    pts_day31 = calculate_recency_points(t_crash, t_crash + timedelta(days=31))
    assert pts_day31 > 9.0

    # Day 75 -> decayed
    pts_day75 = calculate_recency_points(t_crash, t_crash + timedelta(days=75))
    assert pts_day75 < pts_day31


def test_getis_ord_gi_hotspot():
    # Synthetic grid of 6 H3 cells with one heavy concentration
    cells = {
        "8826856235fffff": 100.0,  # Center hotspot
        "8826856237fffff": 80.0,
        "8826856231fffff": 5.0,
        "8826856233fffff": 2.0,
        "8826856239fffff": 1.0,
        "882685623bfffff": 0.0,
    }

    gi_results = compute_getis_ord_gi(cells)
    assert "8826856235fffff" in gi_results
    center = gi_results["8826856235fffff"]
    assert center.gi_z_score > 0
    assert center.observed_value == 100.0


def test_local_morans_i():
    cells = {
        "8826856235fffff": 50.0,
        "8826856237fffff": 45.0,
        "8826856231fffff": 2.0,
        "8826856233fffff": 1.0,
        "8826856239fffff": 3.0,
    }
    lisa_results = compute_local_morans_i(cells)
    assert len(lisa_results) == 5
