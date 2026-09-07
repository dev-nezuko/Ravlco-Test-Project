"""Tests for compliance gates, Texas barratry, Maryland moratorium, and TCPA rules."""

from datetime import datetime, timedelta, timezone
import pytest

from src.compliance.eligibility import build_standard_compliance_engine, evaluate_party_eligibility
from src.compliance.ruleset import ContactChannel, PartyEvaluationContext


def test_texas_barratry_and_statutory_suppression():
    """Verify that Texas records are completely barred from direct solicitation."""
    crash = {
        "crash_id": "TX_CRASH_001",
        "source_system": "txdot",
        "crash_timestamp": datetime(2024, 6, 1, tzinfo=timezone.utc),
        "severity_kabc0": "B",
    }
    party = {
        "party_id": "TX_PARTY_001",
        "source_system": "txdot",
        "person_type": "DRIVER",
        "injury_severity": "B",
        "age": 35,
    }

    eval_time = datetime(2024, 8, 1, tzinfo=timezone.utc)  # Even months later
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.DIRECT_MAIL, evaluation_time=eval_time
    )

    assert status == "INELIGIBLE"
    assert "TEX_PENAL_CODE_38_12" in reasons
    assert "TEX_TRANSP_CODE_550_065" in reasons


def test_maryland_live_call_prohibition():
    """Verify Maryland bans live phone calls and SMS outreach."""
    crash = {
        "crash_id": "MD_CRASH_001",
        "source_system": "moco",
        "crash_timestamp": datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc),
        "severity_kabc0": "C",
        "timezone_iana": "America/New_York",
    }
    party = {
        "party_id": "MD_PARTY_001",
        "source_system": "moco",
        "person_type": "DRIVER",
        "injury_severity": "C",
        "age": 40,
    }

    # Live call attempted on Day 45
    eval_time = datetime(2024, 7, 16, 14, 0, tzinfo=timezone.utc)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.LIVE_CALL, evaluation_time=eval_time
    )

    assert status == "INELIGIBLE"
    assert "MD_BUS_OCC_PROF_10_605" in reasons


def test_maryland_30_day_blackout_window_moratorium():
    """Verify direct mail is blocked within 30 days and permitted after Day 30."""
    t_crash = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
    crash = {
        "crash_id": "MD_CRASH_002",
        "source_system": "moco",
        "crash_timestamp": t_crash,
        "severity_kabc0": "B",
    }
    party = {
        "party_id": "MD_PARTY_002",
        "source_system": "moco",
        "person_type": "DRIVER",
        "injury_severity": "B",
        "age": 30,
    }

    # Day 15 post-crash: should be INELIGIBLE
    t_day15 = t_crash + timedelta(days=15)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.DIRECT_MAIL, evaluation_time=t_day15
    )
    assert status == "INELIGIBLE"
    assert "MD_BUS_OCC_PROF_10_605_30_DAY" in reasons

    # Day 35 post-crash: should be ELIGIBLE
    t_day35 = t_crash + timedelta(days=35)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.DIRECT_MAIL, evaluation_time=t_day35
    )
    assert status == "ELIGIBLE"
    assert len(reasons) == 0


def test_fars_fatality_suppression():
    """Verify FARS fatal crash records are suppressed from outreach."""
    crash = {
        "crash_id": "FARS_001",
        "source_system": "fars",
        "crash_timestamp": datetime(2024, 5, 1, tzinfo=timezone.utc),
        "severity_kabc0": "K",
    }
    party = {
        "party_id": "FARS_PARTY_001",
        "source_system": "fars",
        "person_type": "DRIVER",
        "injury_severity": "K",
        "age": 50,
    }

    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.DIRECT_MAIL
    )
    assert status == "INELIGIBLE"
    assert "NHTSA_FARS_FATALITY_ETHICS" in reasons


def test_tcpa_calling_hours_restriction():
    """Verify TCPA blocks outreach outside 8:00 AM - 9:00 PM local recipient time."""
    crash = {
        "crash_id": "CRASH_003",
        "source_system": "other",
        "crash_timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "timezone_iana": "America/New_York",
    }
    party = {
        "party_id": "PARTY_003",
        "source_system": "other",
        "person_type": "DRIVER",
        "injury_severity": "C",
        "age": 35,
        "is_on_dnc_registry": False,
        "dnc_scrub_timestamp": datetime(2024, 6, 1, tzinfo=timezone.utc),
    }

    # 6:00 AM Eastern (11:00 UTC) -> outside window
    eval_early = datetime(2024, 6, 15, 11, 0, tzinfo=timezone.utc)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.LIVE_CALL, evaluation_time=eval_early
    )
    assert status == "INELIGIBLE"
    assert "47_CFR_64_1200_C_1" in reasons


def test_minor_protection():
    """Verify parties under 18 are rejected."""
    crash = {
        "crash_id": "MD_CRASH_004",
        "source_system": "moco",
        "crash_timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    party = {
        "party_id": "PARTY_MINOR",
        "source_system": "moco",
        "person_type": "PASSENGER",
        "injury_severity": "C",
        "age": 16,  # Minor
    }

    eval_time = datetime(2024, 3, 1, tzinfo=timezone.utc)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.DIRECT_MAIL, evaluation_time=eval_time
    )
    assert status == "INELIGIBLE"
    assert "ETHICS_MINOR_PROTECTION" in reasons


def test_missing_dnc_scrub_blocks_phone_outreach():
    """A party with no DNC scrub on record must not pass the DNC gate for calls."""
    crash = {
        "crash_id": "CRASH_005",
        "source_system": "other",
        "crash_timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        "timezone_iana": "America/New_York",
    }
    party = {
        "party_id": "PARTY_005",
        "source_system": "other",
        "person_type": "DRIVER",
        "injury_severity": "C",
        "age": 40,
    }
    midday_eastern = datetime(2024, 6, 15, 16, 0, tzinfo=timezone.utc)

    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.LIVE_CALL, evaluation_time=midday_eastern
    )
    assert status == "INELIGIBLE"
    assert reasons == ["47_CFR_64_1200_C_2"]

    party["dnc_scrub_timestamp"] = midday_eastern - timedelta(days=3)
    status, reasons = evaluate_party_eligibility(
        party, crash, channel=ContactChannel.LIVE_CALL, evaluation_time=midday_eastern
    )
    assert status == "ELIGIBLE"
    assert reasons == []
