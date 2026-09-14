"""Builds the full quality response from a Beach + Forecast row -- combines Phase 2's
exposure estimate (size) with wind/period/chop (this phase). The only place that builds
this response shape, same discipline as app/exposure/apply.py: API routes call this, not
the sub-scorers directly, so the honest-labelling requirement can't be bypassed.
"""
from app.exposure.apply import build_exposure_estimate
from app.models import Beach, Forecast
from app.quality.chop import classify_chop
from app.quality.period import PERIOD_UNCERTAINTY_S, classify_period
from app.quality.size import classify_size
from app.quality.verdict import combine
from app.quality.wind import classify_wind
from app.schemas import QualityConfidence, QualityOut, QualityWindOut


def build_quality(beach: Beach, forecast: Forecast) -> QualityOut:
    exposure = build_exposure_estimate(beach, forecast)

    size_q = classify_size(exposure.wave_height_estimate)

    # app/quality/period.py's bands are written for PEAK period (Tp). forecast.wave_period
    # is the MEAN period (Tm) from a different model and runs ~20-25% lower, so feeding it
    # in unflagged silently under-rated every forecast -- see docs/DECISIONS.md. Prefer the
    # real Tp; fall back to the mean only when it is genuinely missing, and say which was
    # used rather than presenting the two as interchangeable.
    period_s = forecast.wave_peak_period if forecast.wave_peak_period is not None else forecast.wave_period
    period_is_peak = forecast.wave_peak_period is not None
    period_q = classify_period(period_s)
    wind_q = classify_wind(
        wind_speed_kmh=forecast.wind_speed_10m,
        wind_direction_from=forecast.wind_direction_10m,
        wind_gusts_kmh=forecast.wind_gusts_10m,
        shoreline_bearing=beach.shoreline_bearing,
    )
    chop_q = classify_chop(forecast.swell_wave_height, forecast.wind_wave_height)

    verdict = combine(size_q, period_q, wind_q, chop_q)

    return QualityOut(
        beach_id=beach.id,
        valid_at=forecast.valid_at,
        size=exposure,
        period_s=period_s,
        period_band=period_q.band,
        wind=QualityWindOut(
            speed_kmh=forecast.wind_speed_10m,
            direction_deg=forecast.wind_direction_10m,
            relation_to_shore=wind_q.relation_to_shore,
            gusts_kmh=forecast.wind_gusts_10m,
            gusty=wind_q.gusty,
        ),
        chop_ratio=chop_q.ratio,
        chop_band=chop_q.band,
        quality_score=verdict.quality_score,
        quality_verdict=verdict.verdict,
        quality_reasoning=verdict.reasoning,
        confidence=QualityConfidence(
            size="unvalidated_heuristic",
            period=(
                f"measured_peak_period_tp ~{PERIOD_UNCERTAINTY_S:.0f}s"
                if period_is_peak
                else "substituted_mean_period_tm -- peak period unavailable, bands assume Tp so this reads LOW"
            ),
            wind="measured_forecast",
            chop="unvalidated_heuristic",
            quality_verdict="unvalidated_heuristic",
        ),
    )
