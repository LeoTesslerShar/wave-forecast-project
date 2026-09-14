from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Buoy, Measurement
from app.schemas import MeasurementOut

router = APIRouter()


@router.get("/buoys/{buoy_id}/measurements", response_model=list[MeasurementOut])
async def buoy_measurements(
    buoy_id: str,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[Measurement]:
    buoy = await session.get(Buoy, buoy_id)
    if buoy is None:
        raise HTTPException(status_code=404, detail=f"unknown buoy '{buoy_id}'")

    now = datetime.now(UTC)
    from_ = from_ or (now - timedelta(days=7))
    to = to or now

    stmt = (
        select(Measurement)
        .where(
            Measurement.buoy_id == buoy_id,
            Measurement.observed_at >= from_,
            Measurement.observed_at <= to,
        )
        .order_by(Measurement.observed_at)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
