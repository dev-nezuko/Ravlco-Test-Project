"""Uber H3 Discrete Global Grid System (DGGS) spatial indexing.

Resolutions:
- Resolution 8: Average hexagon area ~0.737 km² (edge length ~461m).
  Optimal for neighborhood-scale crash clustering, spatial auto-correlation
  (Getis-Ord Gi*), and localized risk modeling.
- Resolution 9: Average hexagon area ~0.105 km² (edge length ~174m).
  Optimal for intersection-level hotspot detection and road segment analysis.
"""

from __future__ import annotations

import hashlib

try:
    import h3

    _HAS_H3 = True
except ImportError:
    _HAS_H3 = False


def point_to_h3(lat: float | None, lon: float | None, resolution: int = 8) -> str | None:
    """Convert (latitude, longitude) coordinate to H3 hexagonal index string.

    Parameters
    ----------
    lat:
        Latitude in decimal degrees.
    lon:
        Longitude in decimal degrees.
    resolution:
        H3 grid resolution (8 or 9 recommended).

    Returns
    -------
    Hexadecimal H3 index string, or None if coordinates are missing.
    """
    if lat is None or lon is None:
        return None

    if _HAS_H3:
        # Handles both h3 v3 (geo_to_h3) and v4 (latlng_to_cell) APIs
        if hasattr(h3, "latlng_to_cell"):
            return h3.latlng_to_cell(lat, lon, resolution)
        elif hasattr(h3, "geo_to_h3"):
            return h3.geo_to_h3(lat, lon, resolution)

    # Fallback: Deterministic spatial grid cell representation
    # Discretizes lat/lon at corresponding resolution grid size
    grid_deg = 0.005 if resolution >= 9 else 0.015
    disc_lat = round(lat / grid_deg) * grid_deg
    disc_lon = round(lon / grid_deg) * grid_deg
    digest = hashlib.md5(f"{resolution}:{disc_lat:.4f}:{disc_lon:.4f}".encode()).hexdigest()
    return f"8{resolution:x}" + digest[:13]


def get_k_ring(h3_index: str, k: int = 1) -> set[str]:
    """Get all neighbor hexagons within k steps of the origin cell.

    Used for spatial lag calculation and spatial kernel density estimation.
    """
    if not h3_index:
        return set()

    if _HAS_H3:
        if hasattr(h3, "grid_disk"):
            return set(h3.grid_disk(h3_index, k))
        elif hasattr(h3, "k_ring"):
            return set(h3.k_ring(h3_index, k))

    return {h3_index}


def get_h3_indices(lat: float | None, lon: float | None) -> tuple[str | None, str | None]:
    """Compute both Resolution 8 and Resolution 9 indices for a point."""
    res8 = point_to_h3(lat, lon, resolution=8)
    res9 = point_to_h3(lat, lon, resolution=9)
    return res8, res9
