"""Roadway network snapping and linear referencing.

Snaps crash coordinates to the nearest roadway segment, computes offset distance,
and derives functional classification (Interstate, Arterial, Collector, Local).

Key Capabilities:
- Distinguishes intersection vs. mid-block crashes
- Identifies off-network incidents (parking lots, driveways, off-road)
- Infers road class and baseline statutory speed limits
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class RoadSegment:
    """Roadway line segment for snapping."""

    segment_id: str
    road_name: str
    functional_class: str  # 'INTERSTATE', 'ARTERIAL', 'COLLECTOR', 'LOCAL'
    speed_limit_mph: int
    coords: list[tuple[float, float]]  # List of (lat, lon)


@dataclass
class SnapResult:
    """Result of snapping a crash point to a road network."""

    road_name: str
    functional_class: str
    speed_limit_mph: int
    distance_to_road_meters: float
    snapped_lat: float
    snapped_lon: float
    is_intersection: bool
    is_off_network: bool


# Representative arterial network segments for Rockville / Montgomery County
SAMPLE_MOCO_ROADS = [
    RoadSegment(
        segment_id="MD_355",
        road_name="MD 355 / Rockville Pike",
        functional_class="ARTERIAL",
        speed_limit_mph=40,
        coords=[(39.060, -77.125), (39.085, -77.153), (39.105, -77.170)],
    ),
    RoadSegment(
        segment_id="I_270",
        road_name="Interstate 270",
        functional_class="INTERSTATE",
        speed_limit_mph=65,
        coords=[(39.040, -77.130), (39.080, -77.160), (39.120, -77.200)],
    ),
    RoadSegment(
        segment_id="MD_28",
        road_name="MD 28 / Norbeck Rd",
        functional_class="ARTERIAL",
        speed_limit_mph=45,
        coords=[(39.085, -77.153), (39.090, -77.100), (39.100, -77.050)],
    ),
]


def _point_to_line_segment_dist(
    plat: float, plon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float, float]:
    """Calculate orthogonal distance from point (plat, plon) to line segment (lat1, lon1)-(lat2, lon2).

    Returns (distance_meters, snapped_lat, snapped_lon).
    """
    # Approximate equirectangular projection to meters
    deg_to_m_lat = 111139.0
    deg_to_m_lon = 111139.0 * math.cos(math.radians(plat))

    px = (plon - lon1) * deg_to_m_lon
    py = (plat - lat1) * deg_to_m_lat
    dx = (lon2 - lon1) * deg_to_m_lon
    dy = (lat2 - lat1) * deg_to_m_lat

    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq < 1e-6:
        dist = math.sqrt(px * px + py * py)
        return dist, lat1, lon1

    # Project point onto segment
    t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
    proj_x = t * dx
    proj_y = t * dy

    dist = math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2)
    snapped_lon = lon1 + (proj_x / deg_to_m_lon)
    snapped_lat = lat1 + (proj_y / deg_to_m_lat)

    return dist, snapped_lat, snapped_lon


def snap_crash_to_roadway(
    lat: float | None,
    lon: float | None,
    road_segments: list[RoadSegment] | None = None,
    max_snap_distance_m: float = 50.0,
) -> SnapResult | None:
    """Snap a crash location to the nearest roadway segment."""
    if lat is None or lon is None:
        return None

    segments = road_segments or SAMPLE_MOCO_ROADS
    best_dist = float("inf")
    best_snap = (lat, lon)
    best_seg: RoadSegment | None = None

    for seg in segments:
        for i in range(len(seg.coords) - 1):
            lat1, lon1 = seg.coords[i]
            lat2, lon2 = seg.coords[i + 1]
            dist, s_lat, s_lon = _point_to_line_segment_dist(lat, lon, lat1, lon1, lat2, lon2)
            if dist < best_dist:
                best_dist = dist
                best_snap = (s_lat, s_lon)
                best_seg = seg

    if best_seg is None:
        return None

    is_off_network = best_dist > max_snap_distance_m
    is_intersection = best_dist <= 25.0 and any(
        math.sqrt((lat - clat) ** 2 + (lon - clon) ** 2) * 111139.0 < 30.0
        for clat, clon in best_seg.coords
    )

    return SnapResult(
        road_name=best_seg.road_name,
        functional_class=best_seg.functional_class,
        speed_limit_mph=best_seg.speed_limit_mph,
        distance_to_road_meters=round(best_dist, 2),
        snapped_lat=round(best_snap[0], 6),
        snapped_lon=round(best_snap[1], 6),
        is_intersection=is_intersection,
        is_off_network=is_off_network,
    )
