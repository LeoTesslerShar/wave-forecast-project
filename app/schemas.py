from datetime import datetime

from pydantic import BaseModel


class BeachOut(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    shoreline_bearing: float | None
    model_config = {"from_attributes": True}


class ForecastOut(BaseModel):
    """Every forecast response carries issued_at alongside valid_at (hard rule 6) and a
    `method` field -- "raw" in Phase 1. Phases 2/3 change its value; having the field
    present from the start means no caller ever sees an unlabelled number."""

    beach_id: str
    issued_at: datetime
    valid_at: datetime
    method: str = "raw"

    wave_height: float | None
    wave_direction: float | None
    wave_period: float | None
    swell_wave_height: float | None
    swell_wave_direction: float | None
    swell_wave_period: float | None
    wind_wave_height: float | None
    wind_wave_direction: float | None
    wind_wave_period: float | None

    wind_speed_10m: float | None
    wind_direction_10m: float | None
    wind_gusts_10m: float | None

    backfilled: bool
    wave_fetch_failed: bool
    wind_fetch_failed: bool

    model_config = {"from_attributes": True}


class MeasurementOut(BaseModel):
    buoy_id: str
    observed_at: datetime
    wave_height: float | None
    wave_period: float | None
    wave_max: float | None
    model_config = {"from_attributes": True}


class HealthSource(BaseModel):
    source: str
    status: str
    last_success_at: datetime | None
    age_seconds: float | None


class HealthOut(BaseModel):
    status: str  # "ok" | "degraded" | "down"
    database: bool
    redis: bool
    sources: list[HealthSource]
