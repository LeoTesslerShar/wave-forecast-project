from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_session
from app.models import Beach
from app.queries import get_latest_forecasts
from app.schemas import BeachOut, ForecastOut
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
