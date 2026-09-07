"""Versioned compliance rule engine framework.

Defines the abstract Rule interface, evaluation context, result structures,
and composite execution engine for evaluating outbound contact eligibility.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ContactChannel(str, Enum):
    """Outbound communication medium."""

    LIVE_CALL = "LIVE_CALL"
    AUTOMATED_CALL = "AUTOMATED_CALL"
    SMS = "SMS"
    DIRECT_MAIL = "DIRECT_MAIL"
    EMAIL = "EMAIL"


@dataclass
class PartyEvaluationContext:
    """Evaluation context containing party, crash, and channel attributes."""

    party_id: str
    crash_id: str
    source_system: str  # 'moco', 'txdot', 'fars'
    state: str  # 'MD', 'TX', 'OTHER'
    crash_timestamp: datetime | None
    evaluation_timestamp: datetime
    person_type: str  # 'DRIVER', 'PASSENGER', 'PEDESTRIAN', 'BICYCLIST'
    injury_severity: str  # 'K', 'A', 'B', 'C', 'O', 'U'
    age: int | None
    channel: ContactChannel
    # Channel-specific attributes
    phone_number: str | None = None
    is_wireless: bool = False
    has_pewc: bool = False  # Prior Express Written Consent
    is_on_dnc_registry: bool = False
    dnc_scrub_timestamp: datetime | None = None
    is_rnd_valid: bool = True  # Reassigned Numbers Database check
    recipient_timezone: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleVerdict:
    """Individual rule evaluation output."""

    rule_id: str
    is_passed: bool
    citation: str
    reason: str


@dataclass
class EvaluationSummary:
    """Final aggregated compliance determination."""

    is_eligible: bool
    status: str  # 'ELIGIBLE', 'INELIGIBLE'
    violations: list[RuleVerdict] = field(default_factory=list)
    passed_rules: list[RuleVerdict] = field(default_factory=list)

    @property
    def ineligibility_citations(self) -> list[str]:
        return [v.citation for v in self.violations]


class ComplianceRule(ABC):
    """Abstract base class for all statutory and regulatory compliance rules."""

    rule_id: str
    citation: str
    description: str

    @abstractmethod
    def evaluate(self, ctx: PartyEvaluationContext) -> RuleVerdict:
        """Evaluate rule against context. Return RuleVerdict."""
        pass


class ComplianceEngine:
    """Engine executing an ordered chain of compliance gates."""

    def __init__(self, rules: list[ComplianceRule] | None = None) -> None:
        self.rules: list[ComplianceRule] = rules or []

    def register_rule(self, rule: ComplianceRule) -> None:
        self.rules.append(rule)

    def evaluate(self, ctx: PartyEvaluationContext) -> EvaluationSummary:
        violations: list[RuleVerdict] = []
        passed: list[RuleVerdict] = []

        for rule in self.rules:
            verdict = rule.evaluate(ctx)
            if not verdict.is_passed:
                violations.append(verdict)
            else:
                passed.append(verdict)

        is_eligible = len(violations) == 0
        status = "ELIGIBLE" if is_eligible else "INELIGIBLE"

        return EvaluationSummary(
            is_eligible=is_eligible,
            status=status,
            violations=violations,
            passed_rules=passed,
        )
