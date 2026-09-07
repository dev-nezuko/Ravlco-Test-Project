"""Bronze-layer data contracts for TxDOT CRIS ArcGIS FeatureServer.

The TxDOT endpoint returns ~190 columns. Many are integer code IDs
(e.g. ``wthr_cond_id``, ``light_cond_id``) that are meaningless without
the CRIS lookup tables, which are not publicly available. We model the
structurally important fields and allow extras.

NOTE: Dates are ``esriFieldTypeString`` (not date objects). Numeric codes
are integers without lookup labels. See DATA_QUALITY.md.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class TxDOTCrash(BaseModel):
    """Schema contract for TxDOT CRIS crash records.

    Grain: one row per crash, keyed by ``crash_id``.
    OBJECTID is the ArcGIS-assigned sequential ID (used for pagination).
    """

    OBJECTID: int
    crash_id: Optional[int] = None

    # Dates — stored as strings in the source (esriFieldTypeString)
    crash_date: Optional[str] = None
    crash_time: Optional[str] = None

    # Two competing coordinate pairs (see DATA_QUALITY.md):
    # Officer-reported (frequently null)
    rpt_latitude: Optional[float] = None
    rpt_longitude: Optional[float] = None
    # CRIS-derived (more complete)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    located_fl: Optional[str] = None  # "Y"/"N" — whether CRIS geocoded

    # Severity and counts
    crash_sev_id: Optional[int] = None  # Integer code, no label
    tot_injry_cnt: Optional[int] = None
    death_cnt: Optional[int] = None

    # Flags
    bicyclist_involved_fl: Optional[str] = None  # Only ~14,535 of 3.09M are "Y"
    amend_supp_fl: Optional[str] = None  # Amended/supplemental report flag (SCD2 trigger)

    # Road
    street_name: Optional[str] = None
    speed_limit: Optional[int] = None

    # County / city codes (integer IDs)
    rpt_county_id: Optional[int] = None
    rpt_city_id: Optional[int] = None

    model_config = {"extra": "allow"}  # ~190 columns total; we model key ones
