"""TxDOT CRIS silver-layer transforms.

Handles the known TxDOT defects documented in the assignment:
  1. Two competing coordinate pairs — precedence rule with located_fl
  2. Amended reports — SCD2 strategy for idempotent restatement handling
  3. String dates — parse esriFieldTypeString dates to proper datetimes
  4. Integer code dictionaries — document the ~60 meaningless *_id columns
"""

from __future__ import annotations

import logging
import math
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── 1. Coordinate precedence ────────────────────────────────────────────


def resolve_coordinates(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Apply coordinate precedence rule for TxDOT's two coordinate pairs.

    Precedence:
      1. CRIS-derived (``latitude``/``longitude``) — more complete, geocoded
         by TxDOT's internal system
      2. Officer-reported (``rpt_latitude``/``rpt_longitude``) — frequently
         null, sometimes inaccurate

    The ``located_fl`` flag ("Y"/"N") indicates whether CRIS successfully
    geocoded the crash. When located_fl="Y" and CRIS coords are present,
    those are authoritative. When located_fl="N", officer-reported coords
    are the only option (if present).

    Adds:
      - ``resolved_latitude``, ``resolved_longitude`` — the chosen pair
      - ``coord_source`` — "cris" | "officer" | "none"
      - ``coord_conflict`` — True if both pairs present and disagree by >500 m
      - ``coord_divergence_meters`` — distance between the pairs, or None
      - ``coord_quality_flag`` — "MISSING" when neither pair is usable
    """
    cris_used = 0
    officer_used = 0
    no_coords = 0
    conflicts = 0

    for record in records:
        attrs = record.get("attributes", record)  # Handle both raw and flattened

        cris_lat = attrs.get("latitude")
        cris_lon = attrs.get("longitude")
        rpt_lat = attrs.get("rpt_latitude")
        rpt_lon = attrs.get("rpt_longitude")
        cris_located = attrs.get("located_fl") == "Y"

        cris_valid = _is_valid_coord(cris_lat, cris_lon)
        rpt_valid = _is_valid_coord(rpt_lat, rpt_lon)

        # Check for conflict between the two pairs
        if cris_valid and rpt_valid:
            dist = _approx_distance_m(cris_lat, cris_lon, rpt_lat, rpt_lon)
            attrs["coord_divergence_meters"] = round(dist, 1)
            attrs["coord_conflict"] = dist > 500  # >500m = meaningful disagreement
            if attrs["coord_conflict"]:
                conflicts += 1
        else:
            attrs["coord_divergence_meters"] = None
            attrs["coord_conflict"] = False

        # CRIS coordinates are authoritative only when CRIS says it geocoded the crash.
        if cris_valid and cris_located:
            attrs["resolved_latitude"] = cris_lat
            attrs["resolved_longitude"] = cris_lon
            attrs["coord_source"] = "cris"
            cris_used += 1
        elif rpt_valid:
            attrs["resolved_latitude"] = rpt_lat
            attrs["resolved_longitude"] = rpt_lon
            attrs["coord_source"] = "officer"
            officer_used += 1
        else:
            attrs["resolved_latitude"] = None
            attrs["resolved_longitude"] = None
            attrs["coord_source"] = "none"
            attrs["coord_quality_flag"] = "MISSING"
            no_coords += 1

    logger.info(
        "TxDOT coordinate resolution: %d CRIS, %d officer, %d none, %d conflicts",
        cris_used,
        officer_used,
        no_coords,
        conflicts,
    )
    return records


# ── 2. SCD2 for amended reports ─────────────────────────────────────────


def apply_scd2_amendments(
    records: list[dict[str, Any]],
    existing_records: dict[int, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Handle amended/supplemental reports with SCD2 versioning.

    TxDOT exposes ``amend_supp_fl`` to indicate an amended or supplemental
    report. Late amendments change history, making this a slowly-changing-
    dimension problem, not an append problem.

    Each record gets:
      - ``version``: incrementing version number
      - ``is_current``: True for the latest version
      - ``valid_from``: timestamp this version was first seen
      - ``valid_to``: timestamp this version was superseded (None if current)

    Args:
        records: New/updated records from the latest pull.
        existing_records: Previously loaded records keyed by crash_id.

    Returns:
        All records (existing + new versions) with SCD2 metadata.
    """
    if existing_records is None:
        existing_records = {}

    output = []
    new_count = 0
    amended_count = 0
    now = datetime.now(UTC).isoformat()

    for record in records:
        attrs = record.get("attributes", record)
        crash_id = attrs.get("crash_id")

        if crash_id is None:
            # No crash_id — treat as new
            attrs["version"] = 1
            attrs["is_current"] = True
            attrs["valid_from"] = now
            attrs["valid_to"] = None
            output.append(record)
            new_count += 1
            continue

        if crash_id in existing_records:
            existing = existing_records[crash_id]
            existing_attrs = existing.get("attributes", existing)

            is_amended = attrs.get("amend_supp_fl") == "Y"

            if is_amended or _record_changed(existing_attrs, attrs):
                # Close out the old version
                existing_attrs["is_current"] = False
                existing_attrs["valid_to"] = now
                output.append(existing)

                # Create new version
                prev_version = existing_attrs.get("version", 1)
                attrs["version"] = prev_version + 1
                attrs["is_current"] = True
                attrs["valid_from"] = now
                attrs["valid_to"] = None
                output.append(record)
                amended_count += 1
            else:
                # No change — keep existing as-is
                output.append(existing)
        else:
            # New crash_id
            attrs["version"] = 1
            attrs["is_current"] = True
            attrs["valid_from"] = now
            attrs["valid_to"] = None
            output.append(record)
            new_count += 1

    logger.info(
        "SCD2 amendments: %d new, %d amended (total output: %d)",
        new_count,
        amended_count,
        len(output),
    )
    return output


def _record_changed(old: dict, new: dict) -> bool:
    """Check if a record has materially changed (ignoring metadata fields)."""
    skip_fields = {
        "version",
        "is_current",
        "valid_from",
        "valid_to",
        "OBJECTID",
        "resolved_latitude",
        "resolved_longitude",
        "coord_source",
        "coord_conflict",
    }
    for key in new:
        if key in skip_fields:
            continue
        if old.get(key) != new.get(key):
            return True
    return False


# ── 3. String date parsing ──────────────────────────────────────────────

# TxDOT dates are esriFieldTypeString in various formats
DATE_PATTERNS = [
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "%Y-%m-%d"),
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "%m/%d/%Y"),
    (re.compile(r"^\d{8}$"), "%Y%m%d"),
]


def parse_string_dates(
    records: list[dict[str, Any]],
    date_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Parse TxDOT string-typed date fields into ISO-8601 strings.

    TxDOT declares dates as ``esriFieldTypeString``, so they arrive as
    raw strings in various formats. We normalize to ISO-8601.

    Args:
        date_fields: List of field names to parse. Defaults to common date fields.
    """
    if date_fields is None:
        date_fields = ["crash_date"]

    parse_failures = 0

    for record in records:
        attrs = record.get("attributes", record)
        for field in date_fields:
            raw = attrs.get(field)
            if raw is None:
                continue

            raw = str(raw).strip()
            parsed = None

            for pattern, fmt in DATE_PATTERNS:
                if pattern.match(raw):
                    try:
                        parsed = datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                    break

            if parsed:
                attrs[f"{field}_parsed"] = parsed
            else:
                attrs[f"{field}_parsed"] = None
                parse_failures += 1

    if parse_failures:
        logger.warning(
            "TxDOT date parsing: %d failures across %d records",
            parse_failures,
            len(records),
        )
    return records


# ── 4. Integer code dictionary documentation ────────────────────────────

# These columns are integer IDs with no publicly available lookup table.
# The CRIS Automated Interface guide lists some mappings, but the full
# set requires access to the CRIS system, which is behind authentication.
# We document them here for transparency.
UNDOCUMENTED_CODE_COLUMNS = [
    "wthr_cond_id",
    "light_cond_id",
    "road_part_adj_id",
    "road_relat_id",
    "road_type_id",
    "rpt_road_part_id",
    "surf_cond_id",
    "surf_type_id",
    "traffic_cntl_id",
    "harm_evnt_id",
    "intrsct_relat_id",
    "fhe_collsn_id",
    "obj_struck_id",
    "othr_factr_id",
    "road_algn_id",
    "road_cls_id",
    "rr_relat_fl",
    "pop_group_id",
    "investigat_agency_id",
    "investigat_area_id",
    "crash_sev_id",
    "rpt_block_num",
    "rpt_hwy_num",
    "rpt_sec_block_num",
    "rpt_sec_hwy_num",
    # ... approximately 60 total columns are integer codes
]


# ── Utilities ────────────────────────────────────────────────────────────


def _is_valid_coord(lat: Any, lon: Any) -> bool:
    """Check if a coordinate pair is non-null and within plausible Texas bounds."""
    if lat is None or lon is None:
        return False
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return False
    # Texas roughly: 25.8–36.5°N, 93.5–106.6°W
    return 25.0 <= lat <= 37.0 and -107.0 <= lon <= -93.0


def _approx_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Quick approximate distance in meters (equirectangular projection)."""
    earth_radius_m = 6371000
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.sqrt(x * x + y * y) * earth_radius_m
