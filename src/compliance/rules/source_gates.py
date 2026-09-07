"""Source-level compliance gates (DPPA, Texas §550.065, Maryland §4-320, FARS).

Statutory References:
- 18 U.S.C. § 2721 et seq. (Driver's Privacy Protection Act)
- Tex. Transp. Code § 550.065 (Release of Crash Reports)
- Md. Code Ann., Gen. Prov. § 4-320 (MVA Records Protection)
"""

from __future__ import annotations

from src.compliance.ruleset import ComplianceRule, PartyEvaluationContext, RuleVerdict


class DPPAGate(ComplianceRule):
    """Enforce Driver's Privacy Protection Act (18 U.S.C. § 2721).

    Prohibits obtaining or using personal information derived from state
    motor vehicle department records for commercial solicitation without express consent.
    """

    rule_id = "DPPA_18_USC_2721"
    citation = "18_USC_2721"
    description = "Driver's Privacy Protection Act commercial solicitation bar"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        # If record includes direct DMV lookup data without consent, flag violation
        has_dmv_pii = ctx.attributes.get("sourced_from_dmv", False)
        if has_dmv_pii and not ctx.has_pewc:
            return RuleVerdict(
                rule_id=self.rule_id,
                is_passed=False,
                citation=self.citation,
                reason=(
                    "Personal information obtained from DMV/MVA records without express consent "
                    "under DPPA"
                ),
            )
        return RuleVerdict(self.rule_id, True, self.citation, "DPPA permissible")


class TexasCrashReportGate(ComplianceRule):
    """Enforce Texas Transportation Code § 550.065.

    Accident reports released by TxDOT or law enforcement agencies are privileged
    and confidential. Commercial marketing solicitation using these records is unlawful.
    """

    rule_id = "TX_TRANSP_550_065"
    citation = "TEX_TRANSP_CODE_550_065"
    description = "Texas crash report commercial solicitation prohibition"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.state == "TX" or ctx.source_system == "txdot":
            return RuleVerdict(
                rule_id=self.rule_id,
                is_passed=False,
                citation=self.citation,
                reason=(
                    "Texas crash reports cannot be used for commercial solicitation under Tex. "
                    "Transp. Code § 550.065"
                ),
            )
        return RuleVerdict(self.rule_id, True, self.citation, "Non-Texas source")


class FARSFatalityGate(ComplianceRule):
    """Suppress direct contact to FARS fatality records.

    NHTSA FARS contains only fatal crashes (Killed parties). Direct marketing
    to deceased persons or grieving families is prohibited under state ethics rules.
    """

    rule_id = "FARS_FATALITY_GATE"
    citation = "NHTSA_FARS_FATALITY_ETHICS"
    description = "Prohibition of direct solicitation to FARS fatal crash victims"

    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        if ctx.source_system == "fars" or ctx.injury_severity == "K":
            return RuleVerdict(
                rule_id=self.rule_id,
                is_passed=False,
                citation=self.citation,
                reason=(
                    "Fatal crash victims/families cannot be contacted via unsolicited commercial "
                    "outreach"
                ),
            )
        return RuleVerdict(self.rule_id, True, self.citation, "Non-fatal record")
