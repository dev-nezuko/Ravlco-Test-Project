"""Montgomery County silver-layer transforms.

Applies data quality fixes to raw MoCo data and produces cleaned,
validated records ready for the gold dimensional model.

Handles all four known MoCo defects documented in the assignment:
  1. Out-of-envelope coordinates in bhju-22kf
  2. Mixed driver_substance_abuse dictionary in mmzv-x632
  3. Report number disagreement between Incidents and Drivers
  4. Grain fan-out — crash-level aggregation must come from Incidents, not Drivers
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Montgomery County bounding box (generous envelope) ───────────────────
# Montgomery County, MD roughly spans:
#   Latitude:  38.93 – 39.35 N
#   Longitude: 76.90 – 77.55 W
# We use a generous envelope with a ~10 km buffer to allow for GPS drift
# near borders, but still catch records hundreds of miles away.
MOCO_BOUNDS = {
    "lat_min": 38.85,
    "lat_max": 39.45,
    "lon_min": -77.65,
    "lon_max": -76.80,
}


# ── 1. Coordinate envelope check ────────────────────────────────────────


def flag_out_of_envelope(
    records: list[dict[str, Any]],
    lat_field: str = "latitude",
    lon_field: str = "longitude",
) -> list[dict[str, Any]]:
    """Flag records with coordinates outside Montgomery County's envelope.

    Does NOT drop records — instead adds a ``coord_quality`` field:
      - "valid"         — within the generous MoCo envelope
      - "out_of_bounds" — outside the envelope (may be data entry error,
                          or a legitimate crash on a road near the border)
      - "missing"       — null/zero coordinates

    Why not drop: Some out-of-bounds records may be legitimate (crashes
    involving MoCo residents on nearby roads). Dropping silently would be
    a data quality decision with compliance implications. We flag and let
    downstream layers decide.

    Returns:
        Records with ``coord_quality`` and ``coord_distance_from_centroid_km``
        fields added.
    """
    flagged = 0
    missing = 0

    for record in records:
        lat = record.get(lat_field)
        lon = record.get(lon_field)

        if lat is None or lon is None:
            record["coord_quality"] = "missing"
            record["coord_distance_from_centroid_km"] = None
            missing += 1
            continue

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            record["coord_quality"] = "missing"
            record["coord_distance_from_centroid_km"] = None
            missing += 1
            continue

        if (
            MOCO_BOUNDS["lat_min"] <= lat <= MOCO_BOUNDS["lat_max"]
            and MOCO_BOUNDS["lon_min"] <= lon <= MOCO_BOUNDS["lon_max"]
        ):
            record["coord_quality"] = "valid"
        else:
            record["coord_quality"] = "out_of_bounds"
            flagged += 1

        # Approximate distance from MoCo centroid for quality reporting
        centroid_lat = (MOCO_BOUNDS["lat_min"] + MOCO_BOUNDS["lat_max"]) / 2
        centroid_lon = (MOCO_BOUNDS["lon_min"] + MOCO_BOUNDS["lon_max"]) / 2
        record["coord_distance_from_centroid_km"] = _haversine_km(
            lat, lon, centroid_lat, centroid_lon
        )

    logger.info(
        "Coordinate envelope check: %d valid, %d out_of_bounds, %d missing "
        "(total %d)",
        len(records) - flagged - missing,
        flagged,
        missing,
        len(records),
    )
    return records


# ── 2. driver_substance_abuse dictionary harmonization ───────────────────

# Old scheme (pre-2024): uppercase, single value
#   e.g. "NONE DETECTED", "ALCOHOL PRESENT", "ILLEGAL DRUG PRESENT",
#        "MEDICATION PRESENT", "COMBINATION PRESENT", "OTHER", "UNKNOWN"
#
# New scheme (post-2024): title case, comma-joined pair
#   e.g. "Not Suspect of Alcohol Use, Not Suspect of Drug Use"
#        "Suspected Alcohol Use, Not Suspect of Drug Use"
#
# Null spellings across both schemes:
#   "UNKNOWN", "Unknown", "", None, "N/A"
#
# The cutover overlaps around Jan 2024 — both schemes coexist for several
# days. A hardcoded date is wrong; we detect by pattern.

OLD_SCHEME_PATTERN = re.compile(r"^[A-Z\s]+$")  # ALL CAPS = old scheme
NULL_VALUES = {"UNKNOWN", "Unknown", "N/A", "", "NONE", None}

# Harmonized categories
SUBSTANCE_MAP_OLD = {
    "NONE DETECTED": ("no_alcohol", "no_drug"),
    "ALCOHOL PRESENT": ("alcohol_present", "unknown_drug"),
    "ALCOHOL CONTRIBUTED": ("alcohol_contributed", "unknown_drug"),
    "ILLEGAL DRUG PRESENT": ("unknown_alcohol", "drug_present"),
    "MEDICATION PRESENT": ("unknown_alcohol", "medication_present"),
    "COMBINATION PRESENT": ("alcohol_present", "drug_present"),
    "OTHER": ("unknown_alcohol", "unknown_drug"),
}


def harmonize_substance_abuse(
    records: list[dict[str, Any]],
    field: str = "driver_substance_abuse",
) -> list[dict[str, Any]]:
    """Harmonize the mixed driver_substance_abuse dictionary.

    Produces two standardized fields:
      - ``substance_alcohol_status``: no_alcohol | alcohol_present |
        alcohol_contributed | suspected_alcohol | unknown_alcohol
      - ``substance_drug_status``: no_drug | drug_present |
        medication_present | suspected_drug | unknown_drug

    Also adds ``substance_scheme``: "old" | "new" | "null" to track provenance.
    """
    old_count = 0
    new_count = 0
    null_count = 0

    for record in records:
        raw = record.get(field)

        # Handle nulls
        if raw in NULL_VALUES or raw is None:
            record["substance_alcohol_status"] = "unknown_alcohol"
            record["substance_drug_status"] = "unknown_drug"
            record["substance_scheme"] = "null"
            null_count += 1
            continue

        raw = str(raw).strip()

        # Detect scheme by pattern
        if OLD_SCHEME_PATTERN.match(raw):
            # Old scheme: single uppercase value
            mapped = SUBSTANCE_MAP_OLD.get(raw, ("unknown_alcohol", "unknown_drug"))
            record["substance_alcohol_status"] = mapped[0]
            record["substance_drug_status"] = mapped[1]
            record["substance_scheme"] = "old"
            old_count += 1
        else:
            # New scheme: comma-separated pair like
            # "Not Suspect of Alcohol Use, Not Suspect of Drug Use"
            record["substance_scheme"] = "new"
            _parse_new_scheme(record, raw)
            new_count += 1

    logger.info(
        "Substance abuse harmonization: %d old scheme, %d new scheme, "
        "%d null (total %d)",
        old_count,
        new_count,
        null_count,
        len(records),
    )
    return records


def _parse_new_scheme(record: dict[str, Any], raw: str) -> None:
    """Parse the new comma-joined substance abuse scheme.

    Example: "Suspected Alcohol Use, Not Suspect of Drug Use"
    The comma is embedded in the value, so naive CSV splitting would break.
    We split on ", " and classify each part.
    """
    parts = [p.strip() for p in raw.split(",")]

    alcohol = "unknown_alcohol"
    drug = "unknown_drug"

    for part in parts:
        part_lower = part.lower()
        if "alcohol" in part_lower:
            if "not suspect" in part_lower or "no" in part_lower:
                alcohol = "no_alcohol"
            elif "suspected" in part_lower or "suspect" in part_lower:
                alcohol = "suspected_alcohol"
            else:
                alcohol = "alcohol_present"
        elif "drug" in part_lower:
            if "not suspect" in part_lower or "no" in part_lower:
                drug = "no_drug"
            elif "suspected" in part_lower or "suspect" in part_lower:
                drug = "suspected_drug"
            else:
                drug = "drug_present"

    record["substance_alcohol_status"] = alcohol
    record["substance_drug_status"] = drug


# ── 3. Report number anti-join ───────────────────────────────────────────


def quantify_report_number_disagreement(
    incidents: list[dict[str, Any]],
    drivers: list[dict[str, Any]],
    non_motorists: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Quantify the report_number disagreement between Incidents and Drivers.

    The assignment warns that an inner join silently drops crashes. This
    function computes the anti-join in both directions and reports the
    disagreement.

    Returns:
        Dict with counts and the orphan report_number sets.
    """
    incident_ids = {r["report_number"] for r in incidents if r.get("report_number")}
    driver_ids = {r["report_number"] for r in drivers if r.get("report_number")}

    incidents_only = incident_ids - driver_ids
    drivers_only = driver_ids - incident_ids
    shared = incident_ids & driver_ids

    result = {
        "incident_report_numbers": len(incident_ids),
        "driver_report_numbers": len(driver_ids),
        "shared": len(shared),
        "incidents_only": len(incidents_only),
        "drivers_only": len(drivers_only),
        "incidents_only_sample": sorted(list(incidents_only))[:10],
        "drivers_only_sample": sorted(list(drivers_only))[:10],
    }

    if non_motorists:
        nm_ids = {r["report_number"] for r in non_motorists if r.get("report_number")}
        result["non_motorist_report_numbers"] = len(nm_ids)
        result["nm_only"] = len(nm_ids - incident_ids - driver_ids)

    logger.info(
        "Report number disagreement: %d shared, %d incidents-only, %d drivers-only",
        result["shared"],
        result["incidents_only"],
        result["drivers_only"],
    )
    return result


# ── 4. Grain enforcement ────────────────────────────────────────────────


def enforce_crash_grain(
    incidents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure exactly one row per crash (by report_number) in incidents.

    If duplicates exist, keep the most recent version (by crash_date_time).
    This enforces the grain documented in the bronze contract.
    """
    seen: dict[str, dict[str, Any]] = {}
    duplicates = 0

    for record in incidents:
        rn = record.get("report_number")
        if rn is None:
            continue

        if rn in seen:
            duplicates += 1
            # Keep the one with the later crash_date_time
            existing_dt = seen[rn].get("crash_date_time", "")
            new_dt = record.get("crash_date_time", "")
            if new_dt > existing_dt:
                seen[rn] = record
        else:
            seen[rn] = record

    if duplicates:
        logger.warning(
            "Grain enforcement: found %d duplicate report_numbers in incidents, "
            "kept most recent version",
            duplicates,
        )

    return list(seen.values())


def validate_driver_grain(
    drivers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Validate that drivers table has one row per (report_number, person_id).

    Logs warnings for any violations but does not drop records — the
    downstream model needs to handle multi-driver crashes correctly.
    """
    seen: set[tuple[str, str]] = set()
    duplicates = 0

    for record in drivers:
        key = (
            record.get("report_number", ""),
            record.get("person_id", ""),
        )
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)

    if duplicates:
        logger.warning(
            "Driver grain violation: %d duplicate (report_number, person_id) "
            "pairs found",
            duplicates,
        )
    else:
        logger.info("Driver grain validated: %d unique keys", len(seen))

    return drivers


# ── Utility ──────────────────────────────────────────────────────────────

import math

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate great-circle distance in km using the haversine formula."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
