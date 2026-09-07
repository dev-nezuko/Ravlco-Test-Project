"""FARS silver-layer transforms.

Handles the key FARS defect documented in the assignment:
  - Sentinel values used instead of NULLs:
    * Coordinates: 77.7777, 88.8888, 99.9999 → these place crashes in the
      Arctic Ocean, the Atlantic, or off the coast of Africa if loaded naively
    * Age: 998, 999 → unknown
    * Hour: 99 → unknown
    * 7/8/9-fill in coded fields → unknown/not reported

Also handles restatement tracking: FARS silently revises prior-year files
in place. The ingester detects changed hashes; this transform layer handles
the diff and tracks what changed.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Sentinel values ─────────────────────────────────────────────────────

# Coordinate sentinels — these are NOT real locations
COORD_SENTINELS = {
    77.7777,
    77.7778,  # Unknown (common)
    88.8888,
    88.8889,  # Not reported
    99.9999,
    99.9998,  # Blanks / not applicable
    0.0,  # Some records use 0.0 for unknown
}

# Tolerance for floating-point comparison
COORD_SENTINEL_TOLERANCE = 0.001

# Integer sentinel patterns
AGE_SENTINELS = {998, 999}  # Unknown age
HOUR_SENTINELS = {99}  # Unknown hour
MINUTE_SENTINELS = {99}  # Unknown minute
GENERIC_UNKNOWN_CODES = {7, 8, 9}  # Common 7/8/9-fill for coded fields

# Fields that use 7/8/9-fill for unknown values
SEVEN_EIGHT_NINE_FIELDS = [
    "WEATHER",
    "LGT_COND",
    "CF1",
    "CF2",
    "CF3",
    "DRINKING",
    "DRUGS",
    "SEX",
    "DR_DRINK",
    "SPEEDREL",
]


# ── 1. Sentinel replacement ─────────────────────────────────────────────


def replace_coordinate_sentinels(
    records: list[dict[str, Any]],
    lat_field: str = "LATITUDE",
    lon_field: str = "LONGITUD",  # Note: FARS uses LONGITUD not LONGITUDE
) -> list[dict[str, Any]]:
    """Replace sentinel coordinate values with None.

    FARS encodes unknown coordinates as 77.7777, 88.8888, 99.9999 (and
    slight variations). Loading these naively places crashes in the Arctic
    Ocean (77°N), the Atlantic (88°N doesn't exist, wraps), or off the
    coast of Africa (0°N, 99°E equivalent).

    Returns records with sentinel coords replaced by None and a
    ``coord_quality`` field added.
    """
    replaced = 0
    valid = 0

    for record in records:
        lat = record.get(lat_field)
        lon = record.get(lon_field)

        lat_is_sentinel = _is_coord_sentinel(lat)
        lon_is_sentinel = _is_coord_sentinel(lon)

        if lat_is_sentinel or lon_is_sentinel:
            record[lat_field] = None
            record[lon_field] = None
            record["coord_quality"] = "sentinel_removed"
            replaced += 1
        elif lat is None or lon is None:
            record["coord_quality"] = "missing"
        else:
            # Validate that coordinates are within CONUS bounds
            try:
                lat_f, lon_f = float(lat), float(lon)
                if 24.0 <= lat_f <= 50.0 and -125.0 <= lon_f <= -66.0:
                    record["coord_quality"] = "valid"
                    valid += 1
                else:
                    # Could be Alaska, Hawaii, or territories — flag but keep
                    record["coord_quality"] = "outside_conus"
            except (ValueError, TypeError):
                record["coord_quality"] = "invalid"

    logger.info(
        "FARS coordinate sentinels: %d replaced, %d valid, %d other (total %d)",
        replaced,
        valid,
        len(records) - replaced - valid,
        len(records),
    )
    return records


def replace_integer_sentinels(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace sentinel integer values with None across coded fields.

    Handles:
      - AGE 998/999 → None
      - HOUR 99, MINUTE 99 → None
      - 7/8/9-fill in WEATHER, LGT_COND, DRINKING, DRUGS, SEX, etc.
    """
    replacements = 0

    for record in records:
        # Age
        age = record.get("AGE")
        if age is not None and int(age) in AGE_SENTINELS:
            record["AGE"] = None
            replacements += 1

        # Hour / Minute
        hour = record.get("HOUR")
        if hour is not None and int(hour) in HOUR_SENTINELS:
            record["HOUR"] = None
            replacements += 1

        minute = record.get("MINUTE")
        if minute is not None and int(minute) in MINUTE_SENTINELS:
            record["MINUTE"] = None
            replacements += 1

        # 7/8/9-fill fields
        for field in SEVEN_EIGHT_NINE_FIELDS:
            val = record.get(field)
            if val is not None:
                try:
                    val_int = int(val)
                    # For single-digit coded fields, 7/8/9 are unknown
                    # For multi-digit fields (e.g. WEATHER), 98/99 are unknown
                    if val_int in {7, 8, 9, 97, 98, 99}:
                        record[field] = None
                        replacements += 1
                except (ValueError, TypeError):
                    pass

    logger.info(
        "FARS integer sentinels: %d total replacements across %d records",
        replacements,
        len(records),
    )
    return records


# ── 2. Restatement tracking ─────────────────────────────────────────────


def detect_restatements(
    new_records: list[dict[str, Any]],
    existing_records: list[dict[str, Any]],
    key_fields: tuple[str, ...] = ("STATE", "ST_CASE"),
) -> dict[str, Any]:
    """Compare new FARS data against previous load to detect restatements.

    FARS silently revises prior-year files (e.g., the 2023 file was last
    modified 2026-04-01). This function identifies:
      - New records not in the previous load
      - Removed records no longer in the new file
      - Changed records where field values differ

    Returns a summary with counts and sample changed records.
    """

    def make_key(record: dict) -> tuple:
        return tuple(record.get(f) for f in key_fields)

    old_by_key = {make_key(r): r for r in existing_records}
    new_by_key = {make_key(r): r for r in new_records}

    old_keys = set(old_by_key.keys())
    new_keys = set(new_by_key.keys())

    added = new_keys - old_keys
    removed = old_keys - new_keys
    common = old_keys & new_keys

    changed = []
    for key in common:
        old_r = old_by_key[key]
        new_r = new_by_key[key]
        diffs = _diff_records(old_r, new_r)
        if diffs:
            changed.append(
                {
                    "key": key,
                    "changes": diffs,
                }
            )

    result = {
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "unchanged_count": len(common) - len(changed),
        "added_sample": [new_by_key[k] for k in sorted(list(added))[:5]],
        "removed_sample": [old_by_key[k] for k in sorted(list(removed))[:5]],
        "changed_sample": changed[:5],
    }

    logger.info(
        "FARS restatement check: %d added, %d removed, %d changed, %d unchanged",
        result["added_count"],
        result["removed_count"],
        result["changed_count"],
        result["unchanged_count"],
    )
    return result


# ── 3. Timestamp construction ───────────────────────────────────────────


def construct_timestamps(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Construct a crash timestamp from FARS YEAR/MONTH/DAY/HOUR/MINUTE fields.

    Unknown components (sentinel-replaced to None) result in a partial
    timestamp. We store both the constructed datetime (if complete) and
    the individual fields for transparency.
    """
    complete = 0
    partial = 0

    for record in records:
        year = record.get("YEAR")
        month = record.get("MONTH")
        day = record.get("DAY")
        hour = record.get("HOUR")
        minute = record.get("MINUTE")

        if all(v is not None for v in [year, month, day, hour, minute]):
            try:
                dt = datetime(
                    int(year),
                    int(month),
                    int(day),
                    int(hour),
                    int(minute),
                )
                record["crash_timestamp"] = dt.isoformat()
                record["timestamp_quality"] = "complete"
                complete += 1
            except ValueError:
                record["crash_timestamp"] = None
                record["timestamp_quality"] = "invalid"
                partial += 1
        elif all(v is not None for v in [year, month, day]):
            try:
                dt = datetime(int(year), int(month), int(day))
                record["crash_timestamp"] = dt.isoformat()
                record["timestamp_quality"] = "date_only"
                partial += 1
            except ValueError:
                record["crash_timestamp"] = None
                record["timestamp_quality"] = "invalid"
                partial += 1
        else:
            record["crash_timestamp"] = None
            record["timestamp_quality"] = "insufficient"
            partial += 1

    logger.info(
        "FARS timestamps: %d complete, %d partial/missing (total %d)",
        complete,
        partial,
        len(records),
    )
    return records


# ── Utilities ────────────────────────────────────────────────────────────


def _is_coord_sentinel(value: Any) -> bool:
    """Check if a coordinate value is a known FARS sentinel."""
    if value is None:
        return False
    try:
        v = float(value)
        return any(abs(v - s) < COORD_SENTINEL_TOLERANCE for s in COORD_SENTINELS)
    except (ValueError, TypeError):
        return False


def _diff_records(old: dict, new: dict) -> list[dict[str, Any]]:
    """Find fields that differ between two records."""
    diffs = []
    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        old_val = old.get(key)
        new_val = new.get(key)
        if old_val != new_val:
            diffs.append(
                {
                    "field": key,
                    "old": old_val,
                    "new": new_val,
                }
            )
    return diffs
