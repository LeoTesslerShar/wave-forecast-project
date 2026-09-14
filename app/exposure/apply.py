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
