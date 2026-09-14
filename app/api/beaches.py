from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_session
from app.exposure.apply import build_exposure_estimate
from app.models import Beach
from app.quality.apply import build_quality
from app.queries import get_latest_forecasts
from app.schemas import BeachOut, ExposureEstimateOut, ForecastOut, QualityOut
from app.settings import get_settings

router = APIRouter()


@router.get("/beaches", response_model=list[BeachOut])
async def list_beaches(session: AsyncSession = Depends(get_session)) -> list[Beach]:
    result = await session.execute(select(Beach))
    return list(result.scalars().all())


@router.get("/beaches/{beach_id}/forecast", response_model=list[ForecastOut])
async def beach_forecast(
    beach_id: str, hours: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[ForecastOut]:
    beach = await session.get(Beach, beach_id)
    if beach is None:
        raise HTTPException(status_code=404, detail=f"unknown beach '{beach_id}'")

    settings = get_settings()
    hours = hours or settings.forecast_hours_ahead

    cache_key = f"forecast:{beach_id}:{hours}"
    cached = await cache.cache_get(cache_key)
    if cached is not None:
        return [ForecastOut.model_validate(row) for row in cached]

    now = datetime.now(UTC)
    rows = await get_latest_forecasts(session, beach_id, now, now + timedelta(hours=hours))
    out = [ForecastOut.model_validate(r) for r in rows]

    await cache.cache_set(cache_key, [o.model_dump() for o in out], ttl_seconds=900)
    return out


@router.get("/beaches/{beach_id}/exposure", response_model=list[ExposureEstimateOut])
async def beach_exposure(
    beach_id: str, hours: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[ExposureEstimateOut]:
    """Exposure-adjusted estimate per hour -- prompts/phase-2-exposure.md section 3. Not
    cached (unlike /forecast): the estimate is cheap to compute and correctness here
    matters more than a cache-invalidation bug silently serving a stale exposure model."""
    beach = await session.get(Beach, beach_id)
    if beach is None:
        raise HTTPException(status_code=404, detail=f"unknown beach '{beach_id}'")

    settings = get_settings()
    hours = hours or settings.forecast_hours_ahead

    now = datetime.now(UTC)
    rows = await get_latest_forecasts(session, beach_id, now, now + timedelta(hours=hours))
    return [build_exposure_estimate(beach, r) for r in rows]


@router.get("/beaches/{beach_id}/quality", response_model=list[QualityOut])
async def beach_quality(
    beach_id: str, hours: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[QualityOut]:
    """Surf quality per hour -- prompts/phase-3-quality.md. Hour-by-hour, not a daily
    aggregate: wind rotates through a stormy window, and a good headline height earlier
    must not leak into a later hour's verdict (section 2, "the local pattern"). Not cached,
    same reasoning as /exposure."""
    beach = await session.get(Beach, beach_id)
    if beach is None:
        raise HTTPException(status_code=404, detail=f"unknown beach '{beach_id}'")

    settings = get_settings()
    hours = hours or settings.forecast_hours_ahead

    now = datetime.now(UTC)
    rows = await get_latest_forecasts(session, beach_id, now, now + timedelta(hours=hours))
    return [build_quality(beach, r) for r in rows]


@router.get("/conditions", response_model=list[ExposureEstimateOut])
async def ranked_conditions(
    at: datetime | None = None, session: AsyncSession = Depends(get_session)
) -> list[ExposureEstimateOut]:
    """All beaches, exposure-adjusted, for the same target hour -- ranked best first.

    prompts/phase-2-exposure.md: "the primary product surface is beaches ranked for the
    same hour, not a single beach's estimated height presented as fact." This is that
    surface. `at` defaults to the next full hour; each beach uses whatever the latest
    forecast is for the closest valid_at to it.
    """
    target = at or (datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    window_start = target - timedelta(minutes=30)
    window_end = target + timedelta(minutes=30)

    beaches = list((await session.execute(select(Beach))).scalars().all())

    estimates: list[ExposureEstimateOut] = []
    for beach in beaches:
        rows = await get_latest_forecasts(session, beach.id, window_start, window_end)
        if not rows:
            continue
        closest = min(rows, key=lambda r: abs((r.valid_at - target).total_seconds()))
        estimates.append(build_exposure_estimate(beach, closest))

    estimates.sort(key=lambda e: (e.wave_height_estimate is None, -(e.wave_height_estimate or 0)))
    return estimates
