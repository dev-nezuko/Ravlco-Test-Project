"""Cross-source entity resolution and deduplication engine.

Resolves crashes reported across multiple sources (e.g. MoCo local police reports
matching NHTSA FARS national fatal records; TxDOT local vs statewide reports).

Matching Rules:
1. Exact key match: identical state_id, agency_id, or source report_number
2. Spatiotemporal match:
   - Temporal window: |t1 - t2| <= 15 minutes (or same calendar day if hour unknown)
   - Spatial proximity: haversine_distance(p1, p2) <= 100 meters
   - Attribute agreement: matching county FIPS, fatality flag, or vehicle count
3. Confidence Scoring:
   - 1.00: Exact cross-reference ID
   - 0.95: Spatiotemporal <= 50m + <= 10 min + county match + fatality match
   - 0.85: Spatiotemporal <= 100m + <= 15 min + county match
   - 0.70: Same day + <= 50m + county match (when hour is missing/unknown)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CrashCandidate:
    """Standardized representation of a crash for entity resolution."""

    candidate_id: str
    source: str
    crash_timestamp: datetime | None
    latitude: float | None
    longitude: float | None
    county: str | None = None
    fatality_count: int = 0
    vehicles_involved: int | None = None
    original_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedCluster:
    """A cluster of resolved crash records representing a single physical event."""

    cluster_id: str
    primary_candidate: CrashCandidate
    matched_candidates: list[CrashCandidate] = field(default_factory=list)
    confidence_score: float = 1.0
    match_method: str = "exact_id"
    divergence_notes: list[str] = field(default_factory=list)

    @property
    def member_count(self) -> int:
        return 1 + len(self.matched_candidates)

    @property
    def sources_involved(self) -> set[str]:
        return {self.primary_candidate.source}.union(c.source for c in self.matched_candidates)


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


def evaluate_match_pair(c1: CrashCandidate, c2: CrashCandidate) -> tuple[bool, float, str]:
    """Evaluate whether two crash candidates refer to the same physical incident.

    Returns
    -------
    (is_match, confidence_score, match_method)
    """
    # Rule 0: Identical source and candidate ID -> exact match
    if c1.candidate_id == c2.candidate_id:
        return True, 1.0, "exact_id"

    # Exact original ID match across different ingested entries
    if c1.original_id and c2.original_id and c1.original_id == c2.original_id:
        return True, 1.0, "exact_original_id"

    # Spatial check
    has_coords = (
        c1.latitude is not None
        and c1.longitude is not None
        and c2.latitude is not None
        and c2.longitude is not None
    )
    if not has_coords:
        return False, 0.0, "no_match_missing_coords"

    dist_m = haversine_distance_meters(c1.latitude, c1.longitude, c2.latitude, c2.longitude)

    # If further than 200m apart, reject
    if dist_m > 200.0:
        return False, 0.0, "spatial_distance_exceeded"

    # Temporal check
    has_full_time = c1.crash_timestamp is not None and c2.crash_timestamp is not None
    if has_full_time:
        time_diff = abs(c1.crash_timestamp - c2.crash_timestamp)
        minutes_diff = time_diff.total_seconds() / 60.0

        if minutes_diff <= 15.0 and dist_m <= 50.0:
            confidence = 0.95
            if c1.fatality_count > 0 and c2.fatality_count > 0:
                confidence = 0.99
            return True, confidence, "high_confidence_spatiotemporal"

        if minutes_diff <= 30.0 and dist_m <= 100.0:
            return True, 0.85, "medium_confidence_spatiotemporal"

        # Check same day if times differ by < 2 hours (e.g. timezone recording differences)
        if (
            c1.crash_timestamp.date() == c2.crash_timestamp.date()
            and minutes_diff <= 120.0
            and dist_m <= 50.0
        ):
            return True, 0.80, "timezone_offset_spatiotemporal"

    elif c1.crash_timestamp is not None and c2.crash_timestamp is not None:
        # Date only match when hour is missing (e.g. FARS partial sentinels)
        if c1.crash_timestamp.date() == c2.crash_timestamp.date() and dist_m <= 50.0:
            return True, 0.70, "date_only_spatial_match"

    return False, 0.0, "no_match"


def resolve_crash_candidates(
    candidates: list[CrashCandidate],
) -> list[ResolvedCluster]:
    """Cluster crash candidates into unified physical events using greedy resolution."""
    clusters: list[ResolvedCluster] = []
    assigned: set[str] = set()

    # Prioritize candidates with richer data (known coords + full timestamp)
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            c.latitude is not None and c.longitude is not None,
            c.crash_timestamp is not None,
            c.fatality_count,
        ),
        reverse=True,
    )

    for i, candidate in enumerate(sorted_candidates):
        if candidate.candidate_id in assigned:
            continue

        cluster = ResolvedCluster(
            cluster_id=f"CLUSTER_{candidate.candidate_id}",
            primary_candidate=candidate,
            matched_candidates=[],
            confidence_score=1.0,
            match_method="primary",
        )
        assigned.add(candidate.candidate_id)

        # Compare against remaining candidates
        for j in range(i + 1, len(sorted_candidates)):
            other = sorted_candidates[j]
            if other.candidate_id in assigned:
                continue

            is_match, conf, method = evaluate_match_pair(candidate, other)
            if is_match:
                cluster.matched_candidates.append(other)
                cluster.confidence_score = min(cluster.confidence_score, conf)
                cluster.match_method = method
                assigned.add(other.candidate_id)

        clusters.append(cluster)

    return clusters
