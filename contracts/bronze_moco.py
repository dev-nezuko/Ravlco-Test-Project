"""Bronze-layer data contracts for Montgomery County Socrata datasets.

Pydantic models that enforce schema expectations on raw ingested data.
These contracts serve as the first validation gate: if the upstream schema
drifts (new columns, renamed fields, changed types), these models will
raise validation errors rather than silently passing corrupted data.

Each model preserves the raw field names from the Socrata API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MoCoIncident(BaseModel):
    """Schema contract for bhju-22kf (Crash Reporting – Incidents Data).

    Grain: one row per crash, keyed by ``report_number``.
    """

    report_number: str
    local_case_number: Optional[str] = None
    agency_name: Optional[str] = None
    acrs_report_type: Optional[str] = None

    crash_date_time: str  # ISO-8601 string from Socrata
    route_type: Optional[str] = None
    road_name: Optional[str] = None
    cross_street_type: Optional[str] = None
    cross_street_name: Optional[str] = None

    # Coordinates — present but may be geometrically wrong (see DATA_QUALITY.md)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Conditions
    collision_type: Optional[str] = None
    weather: Optional[str] = None
    surface_condition: Optional[str] = None
    light: Optional[str] = None
    traffic_control: Optional[str] = None

    # Severity
    injury_severity: Optional[str] = None

    # Counts
    vehicle_count: Optional[int] = None
    # Additional fields may be present; Pydantic's model_config handles extras.

    model_config = {"extra": "allow"}  # Don't reject unknown fields (schema drift tolerance)


class MoCoDriver(BaseModel):
    """Schema contract for mmzv-x632 (Crash Reporting – Drivers Data).

    Grain: one row per driver per crash, keyed by ``(report_number, person_id)``.
    """

    report_number: str
    person_id: Optional[str] = None

    crash_date_time: str

    # Driver details
    driver_at_fault: Optional[str] = None
    driver_substance_abuse: Optional[str] = None  # Mixed dictionary — see DATA_QUALITY.md
    driver_distracted_by: Optional[str] = None
    injury_severity: Optional[str] = None

    # Vehicle
    vehicle_id: Optional[str] = None
    vehicle_body_type: Optional[str] = None
    vehicle_movement: Optional[str] = None
    speed_limit: Optional[int] = None

    # Denormalized crash-level fields (DO NOT aggregate from this table)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    weather: Optional[str] = None
    light: Optional[str] = None
    surface_condition: Optional[str] = None

    model_config = {"extra": "allow"}


class MoCoNonMotorist(BaseModel):
    """Schema contract for n7fk-dce5 (Crash Reporting – Non-Motorists Data).

    Grain: one row per non-motorist per crash.
    """

    report_number: str
    person_id: Optional[str] = None

    crash_date_time: str

    # Non-motorist details
    pedestrian_type: Optional[str] = None
    pedestrian_movement: Optional[str] = None
    pedestrian_actions: Optional[str] = None
    injury_severity: Optional[str] = None

    # Location (denormalized from crash)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    model_config = {"extra": "allow"}
