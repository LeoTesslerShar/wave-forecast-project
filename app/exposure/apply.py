"""Combines a Beach's shoreline_bearing with one Forecast row into the exposure-adjusted
estimate shape from prompts/phase-2-exposure.md section 3. The only place in the codebase
that builds this response shape -- API routes call this, not scoring.py directly, so the
honest-labelling requirement (every field always present) can't be bypassed accidentally.
"""
from app.exposure.scoring import compute_exposure
from app.models import Beach, Forecast
from app.schemas import ExposureComponents, ExposureConfidence, ExposureEstimateOut

# docs/BIAS_ANALYSIS.md: on the healthy DeepLev deployment, 90% of offshore-model errors
# fell within this half-width. Never narrow the displayed range below it -- exposure adds
# uncertainty on top of the offshore forecast, it does not remove the offshore forecast's
# own measured uncertainty.
OFFSHORE_UNCERTAINTY_M = 0.25

# Open-Meteo's wave_height (and everything this module derives from it) is significant
# wave height (Hs) -- the average of the highest third of waves, the oceanographic
# convention docs/BIAS_ANALYSIS.md was validated against. Surf apps/surfers commonly
# describe a session by face height instead -- closer to the biggest wave you'd actually
# see in a set, not the statistical average -- which runs well above Hs. This project's own
# Hadera buoy fixture reports both for the same moment (Significant 0.42m, Maximal 0.53m,
# docs/DATA_SOURCES.md) but that is a single sample, not enough to fit a ratio from. Using
# the standard Rayleigh-distributed-sea-state approximation instead: for N independent
# waves, the expected largest is Hs * sqrt(0.5 * ln(N)); N=1000 (~a few hours at a typical
# 8-10s period, i.e. "the biggest wave of the session") gives ~1.86, rounded down slightly
# to the more commonly cited surf-forecasting rule of thumb. This is a judgement call with
# no ground truth to tune it against, same caveat as OBSTRUCTION_LATERAL_THRESHOLD_M --
# see docs/DECISIONS.md. Never used in scoring (app/quality/size.py bands stay on Hs) --
# display only.
FACE_HEIGHT_MULTIPLIER = 1.8


def build_exposure_estimate(beach: Beach, forecast: Forecast) -> ExposureEstimateOut:
    offshore_raw = forecast.wave_height
    swell_direction = forecast.swell_wave_direction or forecast.wave_direction

    if offshore_raw is None or swell_direction is None:
        # Wave data itself is missing this hour (wave_fetch_failed, or a genuinely thin
        # upstream response) -- nothing to adjust. Say so plainly rather than fabricate 0s.
        return ExposureEstimateOut(
            beach_id=beach.id,
            valid_at=forecast.valid_at,
            wave_height_estimate=None,
            wave_height_range=None,
            face_height_estimate=None,
            face_height_range=None,
            method="raw_offshore_unavailable",
            components=ExposureComponents(
                offshore_raw=None, exposure_factor=0.0, directional_factor=0.0, obstruction=0.0
            ),
            confidence=ExposureConfidence(offshore_raw="unavailable"),
            exposure_basis="no wave/swell direction data for this hour",
        )

    result = compute_exposure(beach.lat, beach.lon, beach.shoreline_bearing, swell_direction)

    estimate = round(offshore_raw * result.exposure_factor, 2)
    lo = round(max(0.0, estimate - OFFSHORE_UNCERTAINTY_M), 2)
    hi = round(estimate + OFFSHORE_UNCERTAINTY_M, 2)

    face_estimate = round(estimate * FACE_HEIGHT_MULTIPLIER, 2)
    face_lo = round(max(0.0, lo * FACE_HEIGHT_MULTIPLIER), 2)
    face_hi = round(hi * FACE_HEIGHT_MULTIPLIER, 2)

    bearing_str = (
        f"{beach.shoreline_bearing:.0f}deg" if beach.shoreline_bearing is not None else "unknown"
    )
    obstruction_str = (
        f"obstruction detected (-{result.obstruction:.0%})" if result.obstruction > 0 else "no obstruction modelled"
    )
    basis = (
        f"shoreline bearing {bearing_str}, swell from {swell_direction:.0f}deg "
        f"(angular diff {result.angular_difference_deg:.0f}deg), {obstruction_str}"
    )

    return ExposureEstimateOut(
        beach_id=beach.id,
        valid_at=forecast.valid_at,
        wave_height_estimate=estimate,
        wave_height_range=(lo, hi),
        face_height_estimate=face_estimate,
        face_height_range=(face_lo, face_hi),
        method="raw_offshore+heuristic_exposure" if beach.shoreline_bearing is not None else result.method,
        components=ExposureComponents(
            offshore_raw=offshore_raw,
            exposure_factor=result.exposure_factor,
            directional_factor=result.directional_factor,
            obstruction=result.obstruction,
        ),
        confidence=ExposureConfidence(),
        exposure_basis=basis,
    )
