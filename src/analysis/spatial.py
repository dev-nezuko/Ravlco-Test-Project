"""Spatial autocorrelation and hotspot analysis module.

Implements:
- Getis-Ord Gi* statistic: Identifies statistically significant spatial clusters of high crash frequency / injury counts.
- Local Indicators of Spatial Association (Local Moran's I / LISA): Detects spatial clusters and spatial outliers (High-High, Low-Low, High-Low, Low-High).
- Spatial weights matrix generation using H3 hexagonal neighbor topology.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from src.geo.h3_index import get_k_ring


@dataclass
class HotspotResult:
    """Statistical significance of an H3 cell crash cluster."""
    h3_index: str
    observed_value: float
    gi_z_score: float
    p_value: float
    cluster_type: str  # 'HOTSPOT', 'COLDSPOT', 'NOT_SIGNIFICANT'
    confidence_level: Optional[str] = None  # '99%', '95%', '90%'


@dataclass
class LISAResult:
    """Local Moran's I spatial association category."""
    h3_index: str
    moran_i: float
    z_score: float
    p_value: float
    quadrant: str  # 'High-High', 'Low-Low', 'High-Low', 'Low-High', 'Not-Significant'


def compute_getis_ord_gi(
    cell_values: Dict[str, float],
    k_ring_distance: int = 1,
) -> Dict[str, HotspotResult]:
    """Compute Getis-Ord Gi* statistic for H3 cells.

    Gi* evaluates whether high or low values cluster spatially by comparing
    local sum of a cell and its neighbors against the global mean.

    Formula:
        Gi* = (sum(w_ij * x_j) - X_bar * W_i) / (s * sqrt((n * S1_i - W_i^2) / (n - 1)))
    """
    n = len(cell_values)
    if n < 3:
        # Insufficient sample for statistical inference
        return {
            h3_id: HotspotResult(h3_id, val, 0.0, 1.0, "NOT_SIGNIFICANT")
            for h3_id, val in cell_values.items()
        }

    vals = list(cell_values.values())
    x_bar = sum(vals) / n
    s = math.sqrt(sum((x - x_bar) ** 2 for x in vals) / n)

    if s < 1e-6:
        # Zero variance
        return {
            h3_id: HotspotResult(h3_id, val, 0.0, 1.0, "NOT_SIGNIFICANT")
            for h3_id, val in cell_values.items()
        }

    results: Dict[str, HotspotResult] = {}

    for h3_id, val in cell_values.items():
        # Get neighbors including self (Gi* includes focal point)
        neighbors = get_k_ring(h3_id, k=k_ring_distance)
        # Weights: binary 1 for neighbors present in data, 0 otherwise
        valid_neighbors = [nb for nb in neighbors if nb in cell_values]
        w_i = len(valid_neighbors)  # sum(w_ij)
        local_sum = sum(cell_values[nb] for nb in valid_neighbors)

        # Gi* denominator components
        s1_i = w_i  # For binary weights, sum(w_ij^2) == sum(w_ij)
        denom_radicand = (n * s1_i - (w_i ** 2)) / (n - 1)

        if denom_radicand <= 0:
            z_score = 0.0
        else:
            denom = s * math.sqrt(denom_radicand)
            z_score = (local_sum - x_bar * w_i) / denom if denom > 0 else 0.0

        # Approximate two-tailed p-value from normal z-score
        # Using complementary error function approximation
        abs_z = abs(z_score)
        p_value = math.erfc(abs_z / math.sqrt(2.0))

        # Classify cluster
        if p_value < 0.01:
            conf = "99%"
            ctype = "HOTSPOT" if z_score > 0 else "COLDSPOT"
        elif p_value < 0.05:
            conf = "95%"
            ctype = "HOTSPOT" if z_score > 0 else "COLDSPOT"
        elif p_value < 0.10:
            conf = "90%"
            ctype = "HOTSPOT" if z_score > 0 else "COLDSPOT"
        else:
            conf = None
            ctype = "NOT_SIGNIFICANT"

        results[h3_id] = HotspotResult(
            h3_index=h3_id,
            observed_value=val,
            gi_z_score=round(z_score, 3),
            p_value=round(p_value, 4),
            cluster_type=ctype,
            confidence_level=conf,
        )

    return results


def compute_local_morans_i(
    cell_values: Dict[str, float],
    k_ring_distance: int = 1,
) -> Dict[str, LISAResult]:
    """Compute Local Moran's I (LISA) for detecting spatial clusters and outliers.

    Quadrants:
    - High-High: Hotspot (high crash count surrounded by high crash counts)
    - Low-Low: Coldspot (low crash count surrounded by low crash counts)
    - High-Low: Spatial Outlier (high crash count surrounded by low counts)
    - Low-High: Spatial Outlier (low crash count surrounded by high counts)
    """
    n = len(cell_values)
    if n < 4:
        return {
            h3_id: LISAResult(h3_id, 0.0, 0.0, 1.0, "Not-Significant")
            for h3_id in cell_values
        }

    vals = list(cell_values.values())
    x_bar = sum(vals) / n
    m2 = sum((x - x_bar) ** 2 for x in vals) / n

    if m2 < 1e-6:
        return {
            h3_id: LISAResult(h3_id, 0.0, 0.0, 1.0, "Not-Significant")
            for h3_id in cell_values
        }

    results: Dict[str, LISAResult] = {}

    for h3_id, val in cell_values.items():
        neighbors = [
            nb for nb in get_k_ring(h3_id, k=k_ring_distance)
            if nb in cell_values and nb != h3_id
        ]
        if not neighbors:
            results[h3_id] = LISAResult(h3_id, 0.0, 0.0, 1.0, "Not-Significant")
            continue

        # Spatial lag (average of neighbors)
        w_ij = 1.0 / len(neighbors)
        lag = sum(cell_values[nb] * w_ij for nb in neighbors)

        z_i = val - x_bar
        z_lag = lag - x_bar

        moran_i = (z_i / m2) * z_lag

        # Quadrant determination
        if z_i > 0 and z_lag > 0:
            quad = "High-High"
        elif z_i < 0 and z_lag < 0:
            quad = "Low-Low"
        elif z_i > 0 and z_lag < 0:
            quad = "High-Low"
        else:
            quad = "Low-High"

        # Simplified z-score approximation
        z_score = moran_i * math.sqrt(n)
        p_val = math.erfc(abs(z_score) / math.sqrt(2.0))

        if p_val > 0.10:
            quad = "Not-Significant"

        results[h3_id] = LISAResult(
            h3_index=h3_id,
            moran_i=round(moran_i, 3),
            z_score=round(z_score, 3),
            p_value=round(p_val, 4),
            quadrant=quad,
        )

    return results
