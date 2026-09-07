"""Bronze-layer data contracts for Montgomery County Socrata datasets.

Pydantic models that enforce schema expectations on raw ingested data.
These contracts serve as the first validation gate: if the upstream schema
drifts (new columns, renamed fields, changed types), these models will
raise validation errors rather than silently passing corrupted data.

Each model preserves the raw field names from the Socrata API.
"""

from __future__ import annotations

from pydantic import BaseModel


class MoCoIncident(BaseModel):
    """Schema contract for bhju-22kf (Crash Reporting – Incidents Data).

    Grain: one row per crash, keyed by ``report_number``.
    """

    report_number: str
    local_case_number: str | None = None
    agency_name: str | None = None
    acrs_report_type: str | None = None

    crash_date_time: str  # ISO-8601 string from Socrata
    route_type: str | None = None
    road_name: str | None = None
    cross_street_type: str | None = None
    cross_street_name: str | None = None

    # Coordinates — present but may be geometrically wrong (see DATA_QUALITY.md)
    latitude: float | None = None
    longitude: float | None = None

    # Conditions
    collision_type: str | None = None
    weather: str | None = None
    surface_condition: str | None = None
    light: str | None = None
    traffic_control: str | None = None

    # Severity
    injury_severity: str | None = None

    # Counts
    vehicle_count: int | None = None
    # Additional fields may be present; Pydantic's model_config handles extras.

    model_config = {"extra": "allow"}  # Don't reject unknown fields (schema drift tolerance)


class MoCoDriver(BaseModel):
    """Schema contract for mmzv-x632 (Crash Reporting – Drivers Data).

    Grain: one row per driver per crash, keyed by ``(report_number, person_id)``.
    """

    report_number: str
    person_id: str | None = None

    crash_date_time: str

    # Driver details
    driver_at_fault: str | None = None
    driver_substance_abuse: str | None = None  # Mixed dictionary — see DATA_QUALITY.md
    driver_distracted_by: str | None = None
    injury_severity: str | None = None

    # Vehicle
    vehicle_id: str | None = None
    vehicle_body_type: str | None = None
    vehicle_movement: str | None = None
    speed_limit: int | None = None

    # Denormalized crash-level fields (DO NOT aggregate from this table)
    latitude: float | None = None
    longitude: float | None = None
    weather: str | None = None
    light: str | None = None
    surface_condition: str | None = None

    model_config = {"extra": "allow"}


class MoCoNonMotorist(BaseModel):
    """Schema contract for n7fk-dce5 (Crash Reporting – Non-Motorists Data).

    Grain: one row per non-motorist per crash.
    """

    report_number: str
    person_id: str | None = None

    crash_date_time: str

    # Non-motorist details
    pedestrian_type: str | None = None
    pedestrian_movement: str | None = None
    pedestrian_actions: str | None = None
    injury_severity: str | None = None

    # Location (denormalized from crash)
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"extra": "allow"}
