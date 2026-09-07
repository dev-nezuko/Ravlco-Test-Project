"""Statutory cooling-off and blackout window compliance rules.

Authorities:
- Maryland Business Occupations & Professions Code § 10-605 (30-day moratorium)
- Texas Penal Code § 38.12(b)(1) (30-day moratorium)
"""

from __future__ import annotations

from datetime import timedelta

from src.compliance.ruleset import ComplianceRule, PartyEvaluationContext, RuleVerdict


class MarylandThirtyDayBlackoutRule(ComplianceRule):
    """Enforce Maryland 30-day moratorium on accident solicitation communications.

    Under Md. Code, Bus. Occ. & Prof. § 10-605 and MARPC Rule 19-307.3, targeted
    written communication (direct mail) cannot be sent until at least 30 calendar
    days have elapsed since the collision date.
    """

    rule_id = "MD_30_DAY_BLACKOUT"
    citation = "MD_BUS_OCC_PROF_10_605_30_DAY"
    description = "Maryland mandatory 30-day post-crash cooling off moratorium"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.state == "MD" or ctx.source_system == "moco":
            if ctx.crash_timestamp is None:
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason="Missing crash timestamp; cannot verify 30-day moratorium",
                )

            elapsed = ctx.evaluation_timestamp - ctx.crash_timestamp
            if elapsed < timedelta(days=30):
                remaining_days = 30 - elapsed.days
                return RuleVerdict(
                    rule_id=self.rule_id,
                    is_passed=False,
                    citation=self.citation,
                    reason=f"Within Maryland 30-day blackout window ({remaining_days} days remaining)",
                )

        return RuleVerdict(
            self.rule_id, True, self.citation, "Past 30-day blackout period or non-MD"
        )
