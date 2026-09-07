"""High-level party eligibility evaluation orchestrator.

Instantiates the standard compliance pipeline and evaluates parties against
all federal and state statutory gates, recording comprehensive audit trails.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.compliance.rules.barratry import (
    MarylandLiveContactBarratryRule,
    TexasBarratryRule,
)
from src.compliance.rules.blackout_windows import MarylandThirtyDayBlackoutRule
from src.compliance.rules.contact_channel import (
    DNCRegistryRule,
    MinorProtectionRule,
    ReassignedNumbersRule,
    TCPAHoursRule,
    WirelessConsentRule,
)
from src.compliance.rules.source_gates import (
    DPPAGate,
    FARSFatalityGate,
    TexasCrashReportGate,
)
from src.compliance.ruleset import (
    ComplianceEngine,
    ContactChannel,
    EvaluationSummary,
    PartyEvaluationContext,
)


def build_standard_compliance_engine() -> ComplianceEngine:
    """Construct the comprehensive compliance engine with all statutory gates."""
    engine = ComplianceEngine()
    # Source gates
    engine.register_rule(DPPAGate())
    engine.register_rule(TexasCrashReportGate())
    engine.register_rule(FARSFatalityGate())
    # Barratry gates
    engine.register_rule(TexasBarratryRule())
    engine.register_rule(MarylandLiveContactBarratryRule())
    # Blackout & Moratorium gates
    engine.register_rule(MarylandThirtyDayBlackoutRule())
    # Channel & Consumer Protection gates
    engine.register_rule(TCPAHoursRule())
    engine.register_rule(DNCRegistryRule())
    engine.register_rule(ReassignedNumbersRule())
    engine.register_rule(WirelessConsentRule())
    engine.register_rule(MinorProtectionRule())
    return engine


def evaluate_party_eligibility(
    party: dict[str, Any],
    crash: dict[str, Any],
    channel: ContactChannel = ContactChannel.DIRECT_MAIL,
    evaluation_time: datetime | None = None,
    engine: ComplianceEngine | None = None,
) -> tuple[str, list[str]]:
    """Evaluate a party for contact eligibility.

    Parameters
    ----------
    party:
        Dictionary representing fact_party record.
    crash:
        Dictionary representing fact_crash record.
    channel:
        Proposed contact channel (default: DIRECT_MAIL).
    evaluation_time:
        Timestamp of evaluation (default: now UTC).
    engine:
        Optional custom ComplianceEngine instance.

    Returns
    -------
    (status, ineligibility_reasons)
        status: 'ELIGIBLE' or 'INELIGIBLE'
        ineligibility_reasons: List of statutory citation codes
    """
    eval_engine = engine or build_standard_compliance_engine()
    eval_time = evaluation_time or datetime.now(UTC)

    # Infer state from source or crash
    source = party.get("source_system", crash.get("source_system", "unknown"))
    if source == "txdot":
        state = "TX"
    elif source == "moco":
        state = "MD"
    else:
        state = crash.get("state", "OTHER")

    # Build context
    ctx = PartyEvaluationContext(
        party_id=party.get("party_id", "UNKNOWN"),
        crash_id=crash.get("crash_id", "UNKNOWN"),
        source_system=source,
        state=state,
        crash_timestamp=crash.get("crash_timestamp"),
        evaluation_timestamp=eval_time,
        person_type=party.get("person_type", "DRIVER"),
        injury_severity=party.get("injury_severity", crash.get("severity_kabc0", "U")),
        age=party.get("age"),
        channel=channel,
        phone_number=party.get("phone_number"),
        is_wireless=party.get("is_wireless", False),
        has_pewc=party.get("has_pewc", False),
        is_on_dnc_registry=party.get("is_on_dnc_registry", False),
        dnc_scrub_timestamp=party.get("dnc_scrub_timestamp"),
        is_rnd_valid=party.get("is_rnd_valid", True),
        recipient_timezone=crash.get("timezone_iana"),
        attributes=party.get("attributes", {}),
    )

    summary: EvaluationSummary = eval_engine.evaluate(ctx)

    return summary.status, summary.ineligibility_citations
