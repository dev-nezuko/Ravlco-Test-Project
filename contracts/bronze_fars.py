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

    STATE: int  # FIPS state code
    ST_CASE: int  # Case number within state-year (natural key component)
    STATENAME: str | None = None

    # Temporal
    YEAR: int | None = None
    MONTH: int | None = None
    DAY: int | None = None
    HOUR: int | None = None  # 99 = unknown
    MINUTE: int | None = None  # 99 = unknown

    # Location — SENTINEL VALUES, NOT NULLS
    LATITUDE: float | None = None  # 77.7777/88.8888/99.9999 = unknown
    LONGITUD: float | None = None  # Same sentinels (note: LONGITUD not LONGITUDE)

    # Severity
    FATALS: int | None = None
    PERSONS: int | None = None
    DRUNK_DR: int | None = None

    # Road
    ROUTE: int | None = None
    TWAY_ID: str | None = None

    # Conditions
    WEATHER: int | None = None  # Code — see FARS Analytical Manual
    LGT_COND: int | None = None  # Light condition code
    CF1: int | None = None  # Contributing factor

    # County
    COUNTY: int | None = None

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
    AGE: int | None = None  # 998/999 = unknown
    SEX: int | None = None  # 1=Male, 2=Female, 8/9=unknown
    PER_TYP: int | None = None  # Person type code
    INJ_SEV: int | None = None  # Injury severity (KABCO)

    # Alcohol/drugs
    DRINKING: int | None = None
    DRUGS: int | None = None

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
    MAKE: int | None = None
    MODEL: int | None = None
    MOD_YEAR: int | None = None  # 9999 = unknown
    BODY_TYP: int | None = None

    # Driver
    DR_DRINK: int | None = None
    SPEEDREL: int | None = None

    model_config = {"extra": "allow"}
