"""Bronze-layer data contracts for TxDOT CRIS ArcGIS FeatureServer.

The TxDOT endpoint returns ~190 columns. Many are integer code IDs
(e.g. ``wthr_cond_id``, ``light_cond_id``) that are meaningless without
the CRIS lookup tables, which are not publicly available. We model the
structurally important fields and allow extras.

NOTE: Dates are ``esriFieldTypeString`` (not date objects). Numeric codes
are integers without lookup labels. See DATA_QUALITY.md.
"""

from __future__ import annotations

from pydantic import BaseModel


class TxDOTCrash(BaseModel):
    """Schema contract for TxDOT CRIS crash records.

    Grain: one row per crash, keyed by ``crash_id``.
    OBJECTID is the ArcGIS-assigned sequential ID (used for pagination).
    """

    OBJECTID: int
    crash_id: int | None = None

    # Dates — stored as strings in the source (esriFieldTypeString)
    crash_date: str | None = None
    crash_time: str | None = None

    # Two competing coordinate pairs (see DATA_QUALITY.md):
    # Officer-reported (frequently null)
    rpt_latitude: float | None = None
    rpt_longitude: float | None = None
    # CRIS-derived (more complete)
    latitude: float | None = None
    longitude: float | None = None

    located_fl: str | None = None  # "Y"/"N" — whether CRIS geocoded

    # Severity and counts
    crash_sev_id: int | None = None  # Integer code, no label
    tot_injry_cnt: int | None = None
    death_cnt: int | None = None

    # Flags
    bicyclist_involved_fl: str | None = None  # Only ~14,535 of 3.09M are "Y"
    amend_supp_fl: str | None = None  # Amended/supplemental report flag (SCD2 trigger)

    # Road
    street_name: str | None = None
    speed_limit: int | None = None

    # County / city codes (integer IDs)
    rpt_county_id: int | None = None
    rpt_city_id: int | None = None

    model_config = {"extra": "allow"}  # ~190 columns total; we model key ones
