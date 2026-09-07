"""Tests for Gold layer dimensional models, severity crosswalk, and entity resolution."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from contracts.gold_schema import FactPartyRecord
from src.models.entity_resolution import (
    CrashCandidate,
    evaluate_match_pair,
    haversine_distance_meters,
    resolve_crash_candidates,
)
from src.models.severity_crosswalk import (
    KABCOSeverity,
    aggregate_crash_severity,
    crosswalk_severity,
)

# ── Severity Crosswalk Tests ───────────────────────────────────────────────


def test_moco_severity_crosswalk():
    assert crosswalk_severity("FATAL INJURY", "moco") == KABCOSeverity.FATAL
    assert crosswalk_severity("SUSPECTED SERIOUS INJURY", "moco") == KABCOSeverity.SUSPECTED_SERIOUS
    assert crosswalk_severity("SUSPECTED MINOR INJURY", "moco") == KABCOSeverity.SUSPECTED_MINOR
    assert crosswalk_severity("POSSIBLE INJURY", "moco") == KABCOSeverity.POSSIBLE_INJURY
    assert crosswalk_severity("NO APPARENT INJURY", "moco") == KABCOSeverity.NO_INJURY
    assert crosswalk_severity("UNKNOWN", "moco") == KABCOSeverity.UNKNOWN


def test_txdot_severity_crosswalk():
    assert crosswalk_severity(1, "txdot") == KABCOSeverity.FATAL
    assert crosswalk_severity("1", "txdot") == KABCOSeverity.FATAL
    assert crosswalk_severity(2, "txdot") == KABCOSeverity.SUSPECTED_SERIOUS
    assert crosswalk_severity(3, "txdot") == KABCOSeverity.SUSPECTED_MINOR
    assert crosswalk_severity(4, "txdot") == KABCOSeverity.POSSIBLE_INJURY
    assert crosswalk_severity(5, "txdot") == KABCOSeverity.NO_INJURY
    assert crosswalk_severity(0, "txdot") == KABCOSeverity.UNKNOWN


def test_fars_severity_crosswalk():
    assert crosswalk_severity(4, "fars") == KABCOSeverity.FATAL
    assert crosswalk_severity(3, "fars") == KABCOSeverity.SUSPECTED_SERIOUS
    assert crosswalk_severity(2, "fars") == KABCOSeverity.SUSPECTED_MINOR
    assert crosswalk_severity(1, "fars") == KABCOSeverity.POSSIBLE_INJURY
    assert crosswalk_severity(0, "fars") == KABCOSeverity.NO_INJURY
    assert crosswalk_severity(9, "fars") == KABCOSeverity.UNKNOWN


def test_aggregate_crash_severity():
    party_sevs = [
        KABCOSeverity.NO_INJURY,
        KABCOSeverity.POSSIBLE_INJURY,
        KABCOSeverity.SUSPECTED_SERIOUS,
    ]
    # Highest injury is SUSPECTED_SERIOUS
    assert aggregate_crash_severity(party_sevs) == KABCOSeverity.SUSPECTED_SERIOUS

    party_sevs.append(KABCOSeverity.FATAL)
    assert aggregate_crash_severity(party_sevs) == KABCOSeverity.FATAL


# ── Entity Resolution Tests ────────────────────────────────────────────────


def test_haversine_distance():
    # Known distance: Rockville to Silver Spring (~15 km)
    dist = haversine_distance_meters(39.0840, -77.1528, 38.9907, -77.0261)
    assert 13000 < dist < 17000

    # Same point distance is 0
    assert haversine_distance_meters(30.2672, -97.7431, 30.2672, -97.7431) == 0.0


def test_entity_resolution_matching():
    t0 = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    t1 = datetime(2024, 6, 15, 14, 34, tzinfo=UTC)  # 4 mins later

    c1 = CrashCandidate(
        candidate_id="LOCAL_001",
        source="moco",
        crash_timestamp=t0,
        latitude=39.08400,
        longitude=-77.15280,
        fatality_count=1,
    )
    # 25 meters away, 4 mins later, both fatal
    c2 = CrashCandidate(
        candidate_id="FARS_001",
        source="fars",
        crash_timestamp=t1,
        latitude=39.08420,
        longitude=-77.15270,
        fatality_count=1,
    )

    is_match, conf, method = evaluate_match_pair(c1, c2)
    assert is_match is True
    assert conf >= 0.95
    assert "spatiotemporal" in method

    # Distant point should reject
    c3 = CrashCandidate(
        candidate_id="TX_001",
        source="txdot",
        crash_timestamp=t0,
        latitude=30.2672,
        longitude=-97.7431,
    )
    is_match, _, _ = evaluate_match_pair(c1, c3)
    assert is_match is False


def test_resolve_crash_candidates_clustering():
    t0 = datetime(2024, 6, 15, 14, 30, tzinfo=UTC)
    c1 = CrashCandidate("C1", "moco", t0, 39.084, -77.152, fatality_count=1)
    c2 = CrashCandidate("C2", "fars", t0, 39.0841, -77.1521, fatality_count=1)
    c3 = CrashCandidate("C3", "txdot", t0, 30.267, -97.743, fatality_count=0)

    clusters = resolve_crash_candidates([c1, c2, c3])
    # c1 and c2 should cluster together, c3 separate
    assert len(clusters) == 2
    matched_cluster = next(c for c in clusters if c.primary_candidate.candidate_id == "C1")
    assert matched_cluster.member_count == 2
    assert "fars" in matched_cluster.sources_involved


# ── Gold Contracts Tests ───────────────────────────────────────────────────


def test_gold_fact_party_contract_rejects_sentinel_age():
    # Valid record
    valid = FactPartyRecord(
        party_id="P_001",
        crash_id="C_001",
        source_system="moco",
        person_type="DRIVER",
        age=35,
        injury_severity="A",
    )
    assert valid.age == 35

    # Sentinel age 999 should be rejected
    with pytest.raises(ValidationError):
        FactPartyRecord(
            party_id="P_002",
            crash_id="C_001",
            source_system="fars",
            person_type="DRIVER",
            age=999,
            injury_severity="K",
        )
