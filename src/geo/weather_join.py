"""Weather standardisation for crash records.

Maps police-reported weather and road-surface descriptions onto a small set
of standard conditions. No reanalysis archive (e.g. ERA5) is queried yet, so
the measured fields (temperature, precipitation, wind) are left as None.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class WeatherObservation:
    """Historical weather at crash time and location."""
    temperature_f: Optional[float]
    precipitation_inches: Optional[float]
    weather_condition: str  # 'CLEAR', 'RAIN', 'SNOW', 'FOG', 'SEVERE_STORM'
    surface_condition: str  # 'DRY', 'WET', 'ICE_SNOW'
    wind_speed_mph: Optional[float]
    is_adverse_weather: bool


# Mapping of raw weather descriptions to standardized condition
RAW_WEATHER_MAP: Dict[str, str] = {
    "CLEAR": "CLEAR",
    "CLOUDY": "CLEAR",
    "OVERCAST": "CLEAR",
    "RAINING": "RAIN",
    "RAIN": "RAIN",
    "DRIZZLE": "RAIN",
    "SNOWING": "SNOW",
    "SNOW": "SNOW",
    "SLEET": "SNOW",
    "FREEZING RAIN": "SNOW",
    "FOG, SMOG, SMOKE": "FOG",
    "FOG": "FOG",
    "SEVERE WINDS": "SEVERE_STORM",
    "BLOWING SAND, SOIL, DIRT": "FOG",
    "OTHER": "CLEAR",
    "UNKNOWN": "CLEAR",
}


def infer_weather_observation(
    crash_timestamp: Optional[datetime],
    raw_weather_desc: Optional[str] = None,
    raw_surface_desc: Optional[str] = None,
) -> WeatherObservation:
    """Standardise the police-reported weather and surface for one crash."""
    clean_desc = (raw_weather_desc or "CLEAR").strip().upper()
    cond = RAW_WEATHER_MAP.get(clean_desc, "CLEAR")

    clean_surf = (raw_surface_desc or "DRY").strip().upper()
    if "WET" in clean_surf or "WATER" in clean_surf:
        surface = "WET"
    elif "ICE" in clean_surf or "SNOW" in clean_surf or "SLUSH" in clean_surf:
        surface = "ICE_SNOW"
    else:
        surface = "DRY"

    is_adverse = cond in ("RAIN", "SNOW", "FOG", "SEVERE_STORM") or surface != "DRY"

    return WeatherObservation(
        temperature_f=None,
        precipitation_inches=None,
        weather_condition=cond,
        surface_condition=surface,
        wind_speed_mph=None,
        is_adverse_weather=is_adverse,
    )
