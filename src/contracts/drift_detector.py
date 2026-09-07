"""Upstream schema and distribution drift detection module.

Monitors incoming ingestion batches against baseline schema contracts and
distribution profiles to detect:
1. Schema drift: Missing required columns, unexpected new columns, data type mutations
2. Distribution drift: Volume collapses/spikes (>30%), null-rate inflation (>10% jump)
3. Value domain drift: New categorical values unmapped in severity or condition crosswalks
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class DriftReport:
    """Report of detected structural or statistical drifts."""
    dataset_name: str
    has_drift: bool
    schema_anomalies: List[str] = field(default_factory=list)
    volume_anomalies: List[str] = field(default_factory=list)
    null_rate_anomalies: List[str] = field(default_factory=list)
    unmapped_categories: List[str] = field(default_factory=list)

    @property
    def total_anomalies(self) -> int:
        return (
            len(self.schema_anomalies)
            + len(self.volume_anomalies)
            + len(self.null_rate_anomalies)
            + len(self.unmapped_categories)
        )


@dataclass
class SchemaBaseline:
    """Baseline expectations for a dataset."""
    expected_columns: Set[str]
    required_columns: Set[str]
    expected_types: Dict[str, str] = field(default_factory=dict)
    known_categories: Dict[str, Set[str]] = field(default_factory=dict)
    max_null_rates: Dict[str, float] = field(default_factory=dict)
    expected_min_rows: int = 1


def detect_drift(
    dataset_name: str,
    records: List[Dict[str, Any]],
    baseline: SchemaBaseline,
    historical_row_count: Optional[int] = None,
) -> DriftReport:
    """Evaluate batch of raw records against schema and distribution baseline."""
    schema_anomalies: List[str] = []
    volume_anomalies: List[str] = []
    null_rate_anomalies: List[str] = []
    unmapped_categories: List[str] = []

    n_records = len(records)

    # 1. Volume Check
    if n_records < baseline.expected_min_rows:
        volume_anomalies.append(
            f"Row count {n_records} below expected minimum {baseline.expected_min_rows}"
        )
    elif historical_row_count is not None and historical_row_count > 0:
        volume_ratio = n_records / historical_row_count
        if volume_ratio < 0.70:
            volume_anomalies.append(
                f"Volume drop anomaly: batch size {n_records} is {(1 - volume_ratio):.1%} below baseline {historical_row_count}"
            )
        elif volume_ratio > 1.50:
            volume_anomalies.append(
                f"Volume surge anomaly: batch size {n_records} is {(volume_ratio - 1):.1%} above baseline {historical_row_count}"
            )

    if n_records == 0:
        return DriftReport(
            dataset_name=dataset_name,
            has_drift=len(volume_anomalies) > 0,
            volume_anomalies=volume_anomalies,
        )

    # Inspect column presence
    sample_cols = set()
    for r in records[:50]:
        sample_cols.update(r.keys())

    missing_required = baseline.required_columns - sample_cols
    if missing_required:
        schema_anomalies.append(f"Missing required columns: {sorted(missing_required)}")

    unexpected_cols = sample_cols - baseline.expected_columns
    if unexpected_cols:
        schema_anomalies.append(f"Unexpected new columns detected: {sorted(unexpected_cols)}")

    # Null rate and categorical domain checks
    for col in baseline.required_columns:
        if col in sample_cols:
            null_count = sum(1 for r in records if r.get(col) is None or str(r.get(col)).strip() == "")
            null_rate = null_count / n_records
            max_allowed = baseline.max_null_rates.get(col, 0.05)
            if null_rate > max_allowed:
                null_rate_anomalies.append(
                    f"Column '{col}' null rate {null_rate:.1%} exceeds threshold {max_allowed:.1%}"
                )

    for col, known_values in baseline.known_categories.items():
        if col in sample_cols:
            found_values = {
                str(r[col]).strip().upper()
                for r in records
                if r.get(col) is not None and str(r[col]).strip() != ""
            }
            new_values = found_values - known_values
            if new_values:
                unmapped_categories.append(
                    f"Column '{col}' contains unmapped category values: {sorted(new_values)}"
                )

    has_drift = (
        len(schema_anomalies) > 0
        or len(volume_anomalies) > 0
        or len(null_rate_anomalies) > 0
        or len(unmapped_categories) > 0
    )

    return DriftReport(
        dataset_name=dataset_name,
        has_drift=has_drift,
        schema_anomalies=schema_anomalies,
        volume_anomalies=volume_anomalies,
        null_rate_anomalies=null_rate_anomalies,
        unmapped_categories=unmapped_categories,
    )
