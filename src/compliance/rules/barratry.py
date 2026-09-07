"""Anti-barratry and direct solicitation prohibition rules.

Statutory Authorities:
- Texas Penal Code § 38.12 (Barratry and Solicitation of Professional Employment)
- Maryland Business Occupations & Professions Code § 10-605
- Maryland Attorneys' Rules of Professional Conduct (MARPC Rule 19-307.3)
"""

from __future__ import annotations

from src.compliance.ruleset import (
    ComplianceRule,
    ContactChannel,
    PartyEvaluationContext,
    RuleVerdict,
)


class TexasBarratryRule(ComplianceRule):
    """Enforce Texas Penal Code § 38.12.

    Barratry is a third-degree felony in Texas. It prohibits contacting an
    accident victim or their family within 30 days of an accident, or using
    accident reports obtained from law enforcement to solicit professional employment
    (legal, medical, chiropractic, or investigative).
    """

    rule_id = "TX_BARRATRY_PENAL_38_12"
    citation = "TEX_PENAL_CODE_38_12"
    description = "Texas criminal barratry bar on accident victim solicitation"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.state == "TX" or ctx.source_system == "txdot":
            return RuleVerdict(
                rule_id=self.rule_id,
                is_passed=False,
                citation=self.citation,
                reason="Direct contact of Texas accident victims is a felony under Tex. Penal Code § 38.12",
            )
        return RuleVerdict(self.rule_id, True, self.citation, "Non-Texas jurisdiction")


class MarylandLiveContactBarratryRule(ComplianceRule):
    """Enforce Maryland Bus. Occ. & Prof. § 10-605 and MARPC Rule 19-307.3.

    Absolute prohibition on live telephone calls, in-person solicitation,
    or real-time electronic contact to prospective clients known to need legal
    services in a specific accident matter.
    """

    rule_id = "MD_LIVE_CONTACT_BARRATRY"
    citation = "MD_BUS_OCC_PROF_10_605"
    description = "Maryland ban on live telephone / in-person accident solicitation"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.state == "MD" or ctx.source_system == "moco":
            if ctx.channel in (
                ContactChannel.LIVE_CALL,
                ContactChannel.AUTOMATED_CALL,
                ContactChannel.SMS,
            ):
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="Live telephone, autodialed call, or SMS outreach to accident victims is prohibited in Maryland",
                )
        return RuleVerdict(self.rule_id, True, self.citation, "Permissible channel or non-MD")
