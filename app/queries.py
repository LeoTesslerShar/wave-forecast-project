"""The latest-forecast access path (prompts/phase-1-ingestion.md section 2): a
`DISTINCT ON (valid_at) ... ORDER BY valid_at, issued_at DESC` query backed by the
`ix_forecast_latest (beach_id, valid_at, issued_at)` index. See docs/DECISIONS.md for why
this was chosen over a materialised view."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Forecast


async def get_latest_forecasts(
    session: AsyncSession, beach_id: str, start: datetime, end: datetime
) -> list[Forecast]:
    stmt = (
        select(Forecast)
        .distinct(Forecast.valid_at)
        .where(
            Forecast.beach_id == beach_id,
            Forecast.valid_at >= start,
            Forecast.valid_at <= end,
        )
        .order_by(Forecast.valid_at, Forecast.issued_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
