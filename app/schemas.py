from datetime import datetime, time

from pydantic import BaseModel, field_validator


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
    wave_period: float | None  # MEAN period (Tm) -- see app/models.py Forecast
    wave_peak_period: float | None  # real peak period (Tp), second model, may be absent
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


class ExposureComponents(BaseModel):
    offshore_raw: float | None
    exposure_factor: float
    directional_factor: float
    obstruction: float


class ExposureConfidence(BaseModel):
    offshore_raw: str = "measured_accurate"  # docs/BIAS_ANALYSIS.md -- MAE 0.091m in the surfable band
    exposure: str = "unvalidated_heuristic"  # hard rule 1 -- no ground truth at any beach
    # Contains "unvalidated" so the frontend's isEstimate() check (web/src/components/
    # Badges.jsx) marks it the same as every other heuristic, not "measured" -- it is a
    # further, unmeasured conversion layered on top of exposure, not a new measurement.
    surf_height: str = "unvalidated_local_surf_convention_from_significant_height"


class ExposureEstimateOut(BaseModel):
    """prompts/phase-2-exposure.md section 3. Every field here is required on any response
    that applies exposure to a forecast -- see the honest-labelling requirement. The range
    is never narrower than the measured offshore spread (docs/BIAS_ANALYSIS.md, ~+/-0.19-
    0.25m 90% interval) -- exposure adds uncertainty, it never subtracts it.

    wave_height_estimate/_range are significant wave height (Hs) -- what the offshore model
    outputs and what docs/BIAS_ANALYSIS.md's accuracy numbers and app/quality/size.py's
    band boundaries are calibrated against; never change what these two mean.
    surf_height_estimate/_range are a separate, purely derived conversion into what Israeli
    surf reports actually quote -- the waves breaking at the beach, which on this
    short-period wind-sea coast come in BELOW the deep-water Hs (app/exposure/apply.py
    SURF_HEIGHT_FACTOR, docs/DECISIONS.md). Display only, never used in scoring."""

    beach_id: str
    valid_at: datetime
    wave_height_estimate: float | None
    wave_height_range: tuple[float, float] | None
    surf_height_estimate: float | None
    surf_height_range: tuple[float, float] | None
    method: str
    components: ExposureComponents
    confidence: ExposureConfidence
    exposure_basis: str


class QualityWindOut(BaseModel):
    speed_kmh: float | None
    direction_deg: float | None
    relation_to_shore: str  # "onshore" | "cross-shore" | "offshore" | "glassy" | "unknown"
    gusts_kmh: float | None
    gusty: bool


class QualityConfidence(BaseModel):
    """prompts/phase-3-quality.md section 5. `size` and `quality_verdict` are always
    unvalidated_heuristic -- hard rule 1 -- guaranteed the same way as
    ExposureConfidence.exposure: grepped in tests/test_quality_api.py."""

    size: str = "unvalidated_heuristic"
    period: str
    wind: str = "measured_forecast"
    chop: str = "unvalidated_heuristic"
    quality_verdict: str = "unvalidated_heuristic"


class QualityOut(BaseModel):
    """prompts/phase-3-quality.md section 5. Every component is visible individually --
    no opaque single number -- plus the combined verdict and confidence markers throughout."""

    beach_id: str
    valid_at: datetime
    size: ExposureEstimateOut
    period_s: float | None
    period_band: str
    wind: QualityWindOut
    # The direction the SWELL (not wind) is arriving from -- was only on ForecastOut before;
    # added here so the day-by-day UI doesn't have to fetch and join two endpoints for one
    # field (prompts/phase-5-ui.md section 3, "no client-side derivation of API data").
    swell_direction_deg: float | None
    chop_ratio: float | None
    chop_band: str
    quality_score: float  # 0..10 -- see app/quality/verdict.py
    quality_verdict: str  # "flat" | "poor" | "fair" | "good" | "excellent"
    quality_reasoning: str
    confidence: QualityConfidence


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


class SubscriptionCreate(BaseModel):
    """prompts/phase-4-alerting.md section 1. Validation here, not just at the DB layer --
    sane height ranges, direction ranges that wrap correctly, time windows that may cross
    midnight (validated for parseability; wrap/crossing itself is legal, not an error)."""

    user_id: str
    beach_id: str
    min_height: float | None = None
    max_height: float | None = None
    swell_dir_min: float | None = None
    swell_dir_max: float | None = None
    time_window_start: time
    time_window_end: time
    operating_point: str = "balanced"

    @field_validator("max_height")
    @classmethod
    def _max_above_min(cls, v, info):
        min_h = info.data.get("min_height")
        if v is not None and min_h is not None and v < min_h:
            raise ValueError("max_height must be >= min_height")
        return v

    @field_validator("min_height", "max_height")
    @classmethod
    def _height_sane(cls, v):
        if v is not None and not (0 <= v <= 20):
            raise ValueError("height must be between 0 and 20m")
        return v

    @field_validator("swell_dir_min", "swell_dir_max")
    @classmethod
    def _direction_sane(cls, v):
        if v is not None and not (0 <= v < 360):
            raise ValueError("direction must be in [0, 360)")
        return v

    @field_validator("operating_point")
    @classmethod
    def _operating_point_known(cls, v):
        if v not in ("strict", "balanced", "generous"):
            raise ValueError("operating_point must be one of strict, balanced, generous")
        return v


class SubscriptionOut(BaseModel):
    id: int
    user_id: str
    beach_id: str
    min_height: float | None
    max_height: float | None
    swell_dir_min: float | None
    swell_dir_max: float | None
    time_window_start: time
    time_window_end: time
    operating_point: str
    active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class PushSubscriptionCreate(BaseModel):
    user_id: str
    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionOut(BaseModel):
    id: int
    user_id: str
    endpoint: str
    active: bool
    model_config = {"from_attributes": True}


class SubscriptionStatusOut(BaseModel):
    subscription_id: int
    active: bool
    system_healthy: bool
    last_alert_kind: str | None
    last_alert_at: datetime | None
    last_alert_target_date: str | None
    currently_alerted: bool
    message: str
