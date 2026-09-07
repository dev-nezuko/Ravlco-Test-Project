"""Coordinate Reference System (CRS) constants and reprojection utilities.

Standard Projections:
- EPSG:4326 — WGS 84 (Geographic latitude/longitude in decimal degrees)
- EPSG:5070 — NAD83 / CONUS Albers Equal Area (Meters; optimal for national distance/area queries)
- EPSG:26985 — NAD83 / Maryland State Plane (Meters; local precision for Montgomery County)
- EPSG:3081 — NAD83 / Texas Statewide Centric Equal Area (Meters; Texas-wide operations)
- EPSG:3857 — WGS 84 / Pseudo-Mercator (Meters; web map tile visualization)
"""

from __future__ import annotations

import math

try:
    from pyproj import Transformer

    _HAS_PYPROJ = True
except ImportError:
    _HAS_PYPROJ = False

WGS84_EPSG = 4326
CONUS_ALBERS_EPSG = 5070
MARYLAND_SP_EPSG = 26985
TEXAS_SP_EPSG = 3081
WEB_MERCATOR_EPSG = 3857

# Bounding boxes for state validation [min_lat, min_lon, max_lat, max_lon]
BOUNDS_MONTGOMERY_MD = (38.98, -77.53, 39.36, -76.88)
BOUNDS_TEXAS = (25.83, -106.65, 36.50, -93.50)
BOUNDS_CONUS = (24.39, -125.00, 49.38, -66.93)


def is_in_bounding_box(
    lat: float | None, lon: float | None, bounds: tuple[float, float, float, float]
) -> bool:
    """Check whether a (lat, lon) coordinate is within specified bounding box."""
    if lat is None or lon is None:
        return False
    min_lat, min_lon, max_lat, max_lon = bounds
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def reproject_point(
    lat: float, lon: float, from_epsg: int = WGS84_EPSG, to_epsg: int = CONUS_ALBERS_EPSG
) -> tuple[float, float]:
    """Reproject a point from one CRS to another.

    Returns (x, y) coordinates in target CRS units (typically meters).
    Falls back to spherical approximation if pyproj is unavailable.
    """
    if _HAS_PYPROJ:
        transformer = Transformer.from_crs(f"EPSG:{from_epsg}", f"EPSG:{to_epsg}", always_xy=True)
        x, y = transformer.transform(lon, lat)
        return x, y

    # Fallback: Spherical Web Mercator approximation (EPSG:3857)
    R = 6378137.0
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y
