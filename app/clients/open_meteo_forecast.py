"""Wind from api.open-meteo.com/v1/forecast -- a DIFFERENT endpoint than the marine
archive; the marine endpoint does not carry 10m wind (docs/DATA_SOURCES.md,
prompts/phase-1-ingestion.md section 2). Verified working during the Phase 0.5 spike."""
from datetime import UTC, date, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.clients.errors import UpstreamError
from app.settings import get_settings

HOURLY_VARS = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m"]


def _retrying(max_retries: int):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((httpx.HTTPError, UpstreamError)),
    )


async def fetch_wind_live(
    client: httpx.AsyncClient, lat: float, lon: float, forecast_days: int
) -> dict:
    settings = get_settings()

    @_retrying(settings.http_max_retries)
    async def _call() -> dict:
        resp = await client.get(
            settings.open_meteo_forecast_base_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(HOURLY_VARS),
                "forecast_days": forecast_days,
            },
            timeout=settings.http_timeout_seconds,
        )
        if resp.status_code != 200:
            raise UpstreamError(f"open-meteo forecast {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    try:
        return await _call()
    except httpx.HTTPError as exc:
        # Normalises connection-level failures (DNS, refused, timeout) the same way as
        # HTTP-status failures -- callers only ever need to catch UpstreamError. Found
        # missing during Phase 1's dead-buoy acceptance check: a raw ConnectError was
        # escaping past the per-source try/except in app/ingestion/runner.py.
        raise UpstreamError(f"{exc.__class__.__name__}: {exc}") from exc


async def fetch_wind_range(
    client: httpx.AsyncClient, lat: float, lon: float, start: date, end: date
) -> dict:
    settings = get_settings()

    @_retrying(settings.http_max_retries)
    async def _call() -> dict:
        resp = await client.get(
            settings.open_meteo_forecast_base_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(HOURLY_VARS),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            timeout=settings.http_timeout_seconds,
        )
        if resp.status_code != 200:
            raise UpstreamError(f"open-meteo forecast {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    try:
        return await _call()
    except httpx.HTTPError as exc:
        # Normalises connection-level failures (DNS, refused, timeout) the same way as
        # HTTP-status failures -- callers only ever need to catch UpstreamError. Found
        # missing during Phase 1's dead-buoy acceptance check: a raw ConnectError was
        # escaping past the per-source try/except in app/ingestion/runner.py.
        raise UpstreamError(f"{exc.__class__.__name__}: {exc}") from exc


def parse_hourly(payload: dict) -> list[dict]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    rows = []
    for i, t in enumerate(times):
        row = {"valid_at": datetime.fromisoformat(t).replace(tzinfo=UTC)}
        for var in HOURLY_VARS:
            values = hourly.get(var, [])
            row[var] = values[i] if i < len(values) else None
        rows.append(row)
    return rows
