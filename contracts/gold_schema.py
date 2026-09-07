"""Gold-layer data contracts.

Pydantic models that strictly validate fact and dimension records before loading
into the Gold DuckDB / GeoParquet tables.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class DimSeverityRecord(BaseModel):
    """Contract for dim_severity row."""
    severity_code: Literal["K", "A", "B", "C", "O", "U"]
    severity_name: str
    description: str
    rank: int = Field(ge=0, le=5)


class DimLocationRecord(BaseModel):
    """Contract for dim_location row."""
    location_id: str
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    state_abbr: Optional[str] = Field(default=None, min_length=2, max_length=2)
    county_name: Optional[str] = None
    county_fips: Optional[str] = Field(default=None, min_length=5, max_length=5)
    census_tract_geoid: Optional[str] = Field(default=None, min_length=11, max_length=11)
    h3_res8: Optional[str] = Field(default=None, min_length=15, max_length=15)
    h3_res9: Optional[str] = Field(default=None, min_length=15, max_length=15)
    nearest_road_name: Optional[str] = None
    nearest_road_dist_m: Optional[float] = Field(default=None, ge=0.0)
    speed_limit: Optional[int] = Field(default=None, ge=0, le=120)
    functional_class: Optional[str] = None
    timezone_iana: Optional[str] = None


class FactCrashRecord(BaseModel):
    """Contract for fact_crash row."""
    crash_id: str
    source_system: Literal["moco", "txdot", "fars"]
    source_record_id: str
    crash_timestamp: Optional[datetime] = None
    crash_date: Optional[date] = None
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    severity_kabc0: Literal["K", "A", "B", "C", "O", "U"]
    fatality_count: int = Field(default=0, ge=0)
    injury_count: int = Field(default=0, ge=0)
    vehicle_count: int = Field(default=1, ge=1)
    collision_type: Optional[str] = None
    weather_condition: Optional[str] = None
    light_condition: Optional[str] = None
    road_condition: Optional[str] = None
    county_fips: Optional[str] = Field(default=None, min_length=5, max_length=5)
    census_tract_geoid: Optional[str] = Field(default=None, min_length=11, max_length=11)
    h3_res8: Optional[str] = None
    h3_res9: Optional[str] = None
    is_pedestrian_involved: bool = False
    is_bicyclist_involved: bool = False
    is_commercial_vehicle: bool = False
    is_hit_and_run: bool = False
    coord_quality_flag: Literal["VALID", "MISSING", "OUT_OF_BOUNDS", "CONFLICT"] = "VALID"
    entity_cluster_id: Optional[str] = None


class FactPartyRecord(BaseModel):
    """Contract for fact_party row."""
    party_id: str
    crash_id: str
    source_system: Literal["moco", "txdot", "fars"]
    source_person_id: Optional[str] = None
    person_type: Literal["DRIVER", "PASSENGER", "PEDESTRIAN", "BICYCLIST", "OTHER"]
    vehicle_unit_number: int = Field(default=1, ge=1)
    age: Optional[int] = Field(default=None, ge=0, le=125)
    sex: Optional[Literal["M", "F", "U"]] = "U"
    injury_severity: Literal["K", "A", "B", "C", "O", "U"]
    substance_suspected: bool = False
    substance_test_result: Optional[str] = None
    safety_equipment_used: Optional[str] = None
    ejection_status: Optional[str] = None
    contact_eligibility_status: Literal["ELIGIBLE", "INELIGIBLE", "PENDING_REVIEW"] = "PENDING_REVIEW"
    ineligibility_reasons: List[str] = Field(default_factory=list)

    @field_validator("age")
    @classmethod
    def validate_no_fars_sentinels(cls, v: Optional[int]) -> Optional[int]:
        """Ensure sentinels like 998/999 were cleaned in the silver layer."""
        if v is not None and v > 120:
            raise ValueError(f"Age {v} exceeds human lifespan, likely uncleaned sentinel")
        return v
