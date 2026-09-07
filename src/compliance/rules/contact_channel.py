"""Contact channel, TCPA, DNC, and consumer protection rules.

Authorities:
- 47 U.S.C. § 227 (TCPA)
- 47 CFR § 64.1200 (Delivery Restrictions & Calling Hours)
- FCC 18-177 (Reassigned Numbers Database Order)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from src.compliance.ruleset import (
    ComplianceRule,
    ContactChannel,
    PartyEvaluationContext,
    RuleVerdict,
)
from src.geo.timezone import get_local_datetime, is_within_statutory_contact_hours


class TCPAHoursRule(ComplianceRule):
    """Enforce TCPA permitted calling hours (8:00 AM - 9:00 PM local recipient time).

    Authority: 47 CFR § 64.1200(c)(1).
    """
    rule_id = "TCPA_CALLING_HOURS"
    citation = "47_CFR_64_1200_C_1"
    description = "TCPA permitted contact hours (08:00 - 21:00 recipient local time)"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.channel in (ContactChannel.LIVE_CALL, ContactChannel.AUTOMATED_CALL, ContactChannel.SMS):
            tz_str = ctx.recipient_timezone or "America/New_York"
            local_dt = get_local_datetime(ctx.evaluation_timestamp, tz_str)

            if not is_within_statutory_contact_hours(local_dt):
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason=f"Current recipient local time ({local_dt.strftime('%H:%M %Z')}) is outside TCPA permitted window (08:00-21:00)",
                )

        return RuleVerdict(self.rule_id, True, self.citation, "Within statutory contact hours or mail")


class DNCRegistryRule(ComplianceRule):
    """Enforce National Do Not Call Registry scrubbing.

    Authority: 47 CFR § 64.1200(c)(2). Scrub must be within trailing 31 days.
    """
    rule_id = "DNC_REGISTRY_CHECK"
    citation = "47_CFR_64_1200_C_2"
    description = "National Do Not Call Registry scrubbing"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.channel in (ContactChannel.LIVE_CALL, ContactChannel.AUTOMATED_CALL, ContactChannel.SMS):
            if ctx.is_on_dnc_registry:
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="Recipient telephone number is registered on National Do Not Call list",
                )

            if ctx.dnc_scrub_timestamp is None or (
                ctx.evaluation_timestamp - ctx.dnc_scrub_timestamp > timedelta(days=31)
            ):
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="DNC scrub is stale (>31 days old) or missing",
                )

        return RuleVerdict(self.rule_id, True, self.citation, "DNC scrub valid")


class ReassignedNumbersRule(ComplianceRule):
    """Enforce FCC Reassigned Numbers Database (RND) query safe harbor.

    Authority: FCC Order 18-177.
    """
    rule_id = "RND_SAFE_HARBOR"
    citation = "FCC_18_177_RND"
    description = "FCC Reassigned Numbers Database verification"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.channel in (ContactChannel.LIVE_CALL, ContactChannel.AUTOMATED_CALL, ContactChannel.SMS):
            if not ctx.is_rnd_valid:
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="Telephone number flagged as reassigned in FCC Reassigned Numbers Database",
                )
        return RuleVerdict(self.rule_id, True, self.citation, "RND verified")


class WirelessConsentRule(ComplianceRule):
    """Enforce Prior Express Written Consent (PEWC) for wireless telemarketing.

    Authority: 47 U.S.C. § 227(b)(1)(A).
    """
    rule_id = "TCPA_WIRELESS_PEWC"
    citation = "47_USC_227_B_1_A"
    description = "Mandatory PEWC for wireless telephone communications"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.channel in (ContactChannel.AUTOMATED_CALL, ContactChannel.SMS):
            if ctx.is_wireless and not ctx.has_pewc:
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="Automated call or SMS to wireless number requires Prior Express Written Consent (PEWC)",
                )
        return RuleVerdict(self.rule_id, True, self.citation, "Consent satisfied or landline/mail")


class MinorProtectionRule(ComplianceRule):
    """Ethical and legal protection prohibiting solicitation of minors (<18)."""
    rule_id = "MINOR_PROTECTION"
    citation = "ETHICS_MINOR_PROTECTION"
    description = "Prohibition of direct solicitation of minor accident victims"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.age is not None and ctx.age < 18:
            return RuleVerdict(
                rule_id=self.rule_id,
                is_passed=False,
                citation=self.citation,
                reason=f"Party age ({ctx.age}) is under 18; direct solicitation of minors is prohibited",
            )
        return RuleVerdict(self.rule_id, True, self.citation, "Adult party or age unknown")
