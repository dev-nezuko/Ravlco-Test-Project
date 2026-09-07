"""Lead qualification and multidimensional priority scoring engine.

Computes a composite actionable score (0 - 100) for accident leads.

Scoring Rules & Integrity:
1. Hard Gate: If a party is marked 'INELIGIBLE' by the compliance engine,
   the lead score is hard-clamped to 0.0 with priority 'DISQUALIFIED'.
2. Scoring Dimensions:
   - Severity Score (up to 40 pts): Suspected Serious (A) = 40, Minor (B) = 25, Possible (C) = 10
   - Incident Dynamics (up to 20 pts): Commercial vehicle (+10), Multi-vehicle (+5),
     Hit-and-run victim (+5)
   - Vulnerable Road User (up to 15 pts): Pedestrian or Bicyclist (+15)
   - Spatial Corridor Risk (up to 15 pts): significant Gi* hotspot (+15), otherwise
     interstate/arterial road class (+8)
   - Recency & Temporal Factor (up to 10 pts): Exponential decay post-day-30 window
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class LeadScoreResult:
    """Detailed breakdown of lead priority score."""

    party_id: str
    crash_id: str
    composite_score: float  # 0.0 - 100.0
    priority_tier: str  # 'HIGH', 'MEDIUM', 'LOW', 'DISQUALIFIED'
    severity_points: float
    dynamics_points: float
    vulnerable_user_points: float
    spatial_risk_points: float
    recency_points: float
    is_actionable: bool
    score_factors: list[str] = field(default_factory=list)
    disqualification_reasons: list[str] = field(default_factory=list)


def calculate_recency_points(
    crash_timestamp: datetime | None,
    eval_timestamp: datetime,
    max_points: float = 10.0,
    half_life_days: float = 45.0,
) -> float:
    """Compute recency points with exponential decay after the 30-day blackout."""
    if crash_timestamp is None:
        return 5.0

    days_elapsed = (eval_timestamp - crash_timestamp).total_seconds() / 86400.0
    if days_elapsed < 30.0:
        # Inside blackout window
        return 0.0

    # Days active beyond the 30-day moratorium
    active_days = days_elapsed - 30.0
    decay = math.exp(-math.log(2) * (active_days / half_life_days))
    return round(max_points * decay, 2)


def score_lead(
    party: dict[str, Any],
    crash: dict[str, Any],
    spatial_hotspot_p_val: float | None = None,
    evaluation_time: datetime | None = None,
) -> LeadScoreResult:
    """Calculate composite lead score and priority tier for a party.

    Parameters
    ----------
    party:
        fact_party dictionary with injury_severity, person_type, eligibility.
    crash:
        fact_crash dictionary with dynamics, vehicle_count, road attributes.
    spatial_hotspot_p_val:
        p-value from Getis-Ord Gi* analysis (if <0.05, cell is a significant hotspot).
    evaluation_time:
        Evaluation timestamp.
    """
    party_id = party.get("party_id", "UNKNOWN")
    crash_id = crash.get("crash_id", "UNKNOWN")
    eval_time = evaluation_time or datetime.now(UTC)

    # Compliance Hard Gate
    eligibility_status = party.get("contact_eligibility_status", "PENDING_REVIEW")
    ineligibility_reasons = party.get("ineligibility_reasons", [])

    if eligibility_status == "INELIGIBLE":
        return LeadScoreResult(
            party_id=party_id,
            crash_id=crash_id,
            composite_score=0.0,
            priority_tier="DISQUALIFIED",
            severity_points=0.0,
            dynamics_points=0.0,
            vulnerable_user_points=0.0,
            spatial_risk_points=0.0,
            recency_points=0.0,
            is_actionable=False,
            score_factors=["COMPLIANCE_DISQUALIFIED"],
            disqualification_reasons=ineligibility_reasons,
        )

    score_factors: list[str] = []

    # 1. Severity Points (up to 40)
    sev = party.get("injury_severity", crash.get("severity_kabc0", "U"))
    severity_points = 0.0
    if sev == "A":  # Suspected Serious
        severity_points = 40.0
        score_factors.append("SERIOUS_INJURY (+40)")
    elif sev == "B":  # Suspected Minor
        severity_points = 25.0
        score_factors.append("MINOR_INJURY (+25)")
    elif sev == "C":  # Possible
        severity_points = 10.0
        score_factors.append("POSSIBLE_INJURY (+10)")

    # 2. Crash Dynamics (up to 20)
    dynamics_points = 0.0
    if crash.get("is_commercial_vehicle", False):
        dynamics_points += 10.0
        score_factors.append("COMMERCIAL_VEHICLE (+10)")
    if crash.get("vehicle_count", 1) >= 2:
        dynamics_points += 5.0
        score_factors.append("MULTI_VEHICLE (+5)")
    if crash.get("is_hit_and_run", False):
        dynamics_points += 5.0
        score_factors.append("HIT_AND_RUN (+5)")
    dynamics_points = min(dynamics_points, 20.0)

    # 3. Vulnerable Road User (up to 15)
    vulnerable_user_points = 0.0
    ptype = str(party.get("person_type", "")).upper()
    if (
        ptype in ("PEDESTRIAN", "BICYCLIST")
        or crash.get("is_pedestrian_involved")
        or crash.get("is_bicyclist_involved")
    ):
        vulnerable_user_points = 15.0
        score_factors.append("VULNERABLE_ROAD_USER (+15)")

    # 4. Spatial Corridor Risk (up to 15)
    spatial_risk_points = 0.0
    if spatial_hotspot_p_val is not None and spatial_hotspot_p_val < 0.05:
        spatial_risk_points = 15.0
        score_factors.append("HOTSPOT_CORRIDOR (+15)")
    elif crash.get("functional_class") in ("INTERSTATE", "ARTERIAL"):
        spatial_risk_points = 8.0
        score_factors.append("MAJOR_ARTERIAL (+8)")

    # 5. Recency Factor (up to 10)
    crash_time = crash.get("crash_timestamp")
    recency_points = calculate_recency_points(crash_time, eval_time)
    if recency_points > 0:
        score_factors.append(f"RECENCY_FACTOR (+{recency_points:.1f})")

    # Composite Sum
    total = round(
        severity_points
        + dynamics_points
        + vulnerable_user_points
        + spatial_risk_points
        + recency_points,
        1,
    )
    composite_score = min(100.0, max(0.0, total))

    if composite_score >= 60.0:
        tier = "HIGH"
    elif composite_score >= 35.0:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    return LeadScoreResult(
        party_id=party_id,
        crash_id=crash_id,
        composite_score=composite_score,
        priority_tier=tier,
        severity_points=severity_points,
        dynamics_points=dynamics_points,
        vulnerable_user_points=vulnerable_user_points,
        spatial_risk_points=spatial_risk_points,
        recency_points=recency_points,
        is_actionable=True,
        score_factors=score_factors,
    )
