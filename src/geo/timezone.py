"""Coordinate-derived IANA timezone engine.

Determines accurate local time zone from geographic coordinates (WGS84).

Compliance Rationale:
Federal TCPA (47 U.S.C. § 227) and state statutes restrict outbound communications
to between 8:00 AM and 9:00 PM local recipient time. In multi-timezone states like
Texas (which spans America/Chicago and America/Denver in El Paso/Hudspeth counties),
assuming state-level timezone results in premature contact violations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

try:
    from timezonefinder import TimezoneFinder
    _TF = TimezoneFinder()
except ImportError:
    _TF = None


# Heuristic timezone bounding boxes for fallback when timezonefinder is not installed
# Format: (min_lat, min_lon, max_lat, max_lon)
TEXAS_MOUNTAIN_BOX = (31.0, -106.65, 32.05, -104.85)  # El Paso & Hudspeth
EASTERN_CONUS_BOX = (24.0, -85.0, 47.5, -67.0)
CENTRAL_CONUS_BOX = (25.5, -105.0, 49.0, -85.0)
MOUNTAIN_CONUS_BOX = (31.0, -115.0, 49.0, -104.0)
PACIFIC_CONUS_BOX = (32.5, -125.0, 49.0, -114.0)


def get_iana_timezone(lat: Optional[float], lon: Optional[float], state_hint: Optional[str] = None) -> str:
    """Resolve IANA timezone string (e.g. 'America/New_York', 'America/Chicago').

    Parameters
    ----------
    lat:
        Latitude in decimal degrees.
    lon:
        Longitude in decimal degrees.
    state_hint:
        Optional two-letter state abbreviation fallback.

    Returns
    -------
    Valid IANA timezone identifier string. Defaults to 'America/New_York' for MD,
    'America/Chicago' for TX (except West TX which is 'America/Denver').
    """
    if lat is not None and lon is not None:
        if _TF is not None:
            tz_name = _TF.timezone_at(lat=lat, lng=lon)
            if tz_name:
                return tz_name

        # Heuristic fallback based on coordinates
        if (
            TEXAS_MOUNTAIN_BOX[0] <= lat <= TEXAS_MOUNTAIN_BOX[2]
            and TEXAS_MOUNTAIN_BOX[1] <= lon <= TEXAS_MOUNTAIN_BOX[3]
        ):
            return "America/Denver"

        if EASTERN_CONUS_BOX[0] <= lat <= EASTERN_CONUS_BOX[2] and EASTERN_CONUS_BOX[1] <= lon <= EASTERN_CONUS_BOX[3]:
            return "America/New_York"
        if CENTRAL_CONUS_BOX[0] <= lat <= CENTRAL_CONUS_BOX[2] and CENTRAL_CONUS_BOX[1] <= lon <= CENTRAL_CONUS_BOX[3]:
            return "America/Chicago"
        if MOUNTAIN_CONUS_BOX[0] <= lat <= MOUNTAIN_CONUS_BOX[2] and MOUNTAIN_CONUS_BOX[1] <= lon <= MOUNTAIN_CONUS_BOX[3]:
            return "America/Denver"
        if PACIFIC_CONUS_BOX[0] <= lat <= PACIFIC_CONUS_BOX[2] and PACIFIC_CONUS_BOX[1] <= lon <= PACIFIC_CONUS_BOX[3]:
            return "America/Los_Angeles"

    # State hint fallback
    if state_hint:
        sh = state_hint.upper().strip()
        if sh in ("MD", "VA", "DC", "PA", "DE", "NY", "NJ", "NC", "SC", "GA", "FL"):
            return "America/New_York"
        if sh in ("TX", "IL", "MO", "TN", "AL", "MS", "LA", "AR", "OK", "KS", "NE", "IA", "WI", "MN"):
            return "America/Chicago"
        if sh in ("NM", "CO", "WY", "MT", "UT", "AZ"):
            return "America/Denver"
        if sh in ("CA", "WA", "OR", "NV"):
            return "America/Los_Angeles"

    return "America/New_York"


def get_local_datetime(utc_dt: datetime, tz_name: str) -> datetime:
    """Convert UTC datetime to the specified local timezone."""
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = ZoneInfo("America/New_York")

    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)

    return utc_dt.astimezone(zone)


def is_within_statutory_contact_hours(local_dt: datetime) -> bool:
    """Check if local time is between 8:00 AM and 9:00 PM (08:00 - 21:00).

    Statutory Reference: 47 CFR § 64.1200(c)(1) / TCPA Contact Hours.
    """
    hour = local_dt.hour
    return 8 <= hour < 21
