"""Bronze-layer data contracts for NHTSA FARS bulk CSV data.

FARS uses a wide, code-heavy schema where missing/unknown values are
encoded as sentinel integers (77.7777, 88.8888, 99.9999 for coordinates;
998/999 for age; 99 for hour; 7/8/9-fill for coded fields) rather than
NULL. These must be detected and mapped to NULL in the silver layer.

Key FARS tables ingested from each year's ZIP:
  - ACCIDENT.csv  — one row per fatal crash (primary fact)
  - PERSON.csv    — one row per person involved
  - VEHICLE.csv   — one row per vehicle
  - (others: CEVENT, DAMAGE, DISTRACT, DRIMPAIR, etc.)
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# Known FARS sentinel values for coordinates
COORD_SENTINELS = {77.7777, 88.8888, 99.9999, 77.7778, 88.8889, 99.9998}

# Known FARS sentinel values for integer codes
AGE_UNKNOWN = {998, 999}
HOUR_UNKNOWN = {99}


class FARSAccident(BaseModel):
    """Schema contract for FARS ACCIDENT.csv.

    Grain: one row per fatal crash, keyed by ``(STATE, ST_CASE)``.
    """

    STATE: int       # FIPS state code
    ST_CASE: int     # Case number within state-year (natural key component)
    STATENAME: Optional[str] = None

    # Temporal
    YEAR: Optional[int] = None
    MONTH: Optional[int] = None
    DAY: Optional[int] = None
    HOUR: Optional[int] = None    # 99 = unknown
    MINUTE: Optional[int] = None  # 99 = unknown

    # Location — SENTINEL VALUES, NOT NULLS
    LATITUDE: Optional[float] = None   # 77.7777/88.8888/99.9999 = unknown
    LONGITUD: Optional[float] = None   # Same sentinels (note: LONGITUD not LONGITUDE)

    # Severity
    FATALS: Optional[int] = None
    PERSONS: Optional[int] = None
    DRUNK_DR: Optional[int] = None

    # Road
    ROUTE: Optional[int] = None
    TWAY_ID: Optional[str] = None

    # Conditions
    WEATHER: Optional[int] = None  # Code — see FARS Analytical Manual
    LGT_COND: Optional[int] = None  # Light condition code
    CF1: Optional[int] = None      # Contributing factor

    # County
    COUNTY: Optional[int] = None

    model_config = {"extra": "allow"}


class FARSPerson(BaseModel):
    """Schema contract for FARS PERSON.csv.

    Grain: one row per person involved in a fatal crash.
    Key: ``(STATE, ST_CASE, VEH_NO, PER_NO)``.
    """

    STATE: int
    ST_CASE: int
    VEH_NO: int
    PER_NO: int

    # Demographics — sentinel-coded
    AGE: Optional[int] = None       # 998/999 = unknown
    SEX: Optional[int] = None       # 1=Male, 2=Female, 8/9=unknown
    PER_TYP: Optional[int] = None   # Person type code
    INJ_SEV: Optional[int] = None   # Injury severity (KABCO)

    # Alcohol/drugs
    DRINKING: Optional[int] = None
    DRUGS: Optional[int] = None

    model_config = {"extra": "allow"}


class FARSVehicle(BaseModel):
    """Schema contract for FARS VEHICLE.csv.

    Grain: one row per vehicle in a fatal crash.
    Key: ``(STATE, ST_CASE, VEH_NO)``.
    """

    STATE: int
    ST_CASE: int
    VEH_NO: int

    # Vehicle
    MAKE: Optional[int] = None
    MODEL: Optional[int] = None
    MOD_YEAR: Optional[int] = None  # 9999 = unknown
    BODY_TYP: Optional[int] = None

    # Driver
    DR_DRINK: Optional[int] = None
    SPEEDREL: Optional[int] = None

    model_config = {"extra": "allow"}
