"""Wave/swell/wind-sea from marine-api.open-meteo.com/v1/marine.

Verified endpoint and response shape: docs/DATA_SOURCES.md, scripts/deeplev/fetch_model.py.
Historical note: this archive starts ~Oct 2021 and has no forecast-as-issued lead-time
structure (docs/DATA_SOURCES.md) -- a `start_date`/`end_date` request returns the single
best-available value for that hour, not what was forecast at the time. Used here only for
gap-filling recent missed runs (prompts/phase-1-ingestion.md section 3), and every row from
that path is flagged backfilled=True by the caller.
"""
from datetime import UTC, date, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.clients.errors import UpstreamError
from app.settings import get_settings

HOURLY_VARS = [
    "wave_height",
    "wave_direction",
    "wave_period",
    "swell_wave_height",
    "swell_wave_direction",
    "swell_wave_period",
    "wind_wave_height",
    "wind_wave_direction",
    "wind_wave_period",
]


def _retrying(max_retries: int):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((httpx.HTTPError, UpstreamError)),
    )


async def fetch_marine_live(
    client: httpx.AsyncClient, lat: float, lon: float, forecast_days: int
) -> dict:
    """Current forecast for the next `forecast_days` days. issued_at (fetch time) is
    assigned by the caller."""
    settings = get_settings()

    @_retrying(settings.http_max_retries)
    async def _call() -> dict:
        resp = await client.get(
            settings.open_meteo_marine_base_url,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(HOURLY_VARS),
                "forecast_days": forecast_days,
            },
            timeout=settings.http_timeout_seconds,
        )
        if resp.status_code != 200:
            raise UpstreamError(f"open-meteo marine {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    try:
        return await _call()
    except httpx.HTTPError as exc:
        # Normalises connection-level failures (DNS, refused, timeout) the same way as
        # HTTP-status failures -- callers only ever need to catch UpstreamError. Found
        # missing during Phase 1's dead-buoy acceptance check: a raw ConnectError was
        # escaping past the per-source try/except in app/ingestion/runner.py.
        raise UpstreamError(f"{exc.__class__.__name__}: {exc}") from exc


async def fetch_marine_range(
    client: httpx.AsyncClient, lat: float, lon: float, start: date, end: date
) -> dict:
    """Archive value for a past date range. NOT forecast-as-issued -- see module docstring.
    Used only for backfilling missed scheduled runs."""
    settings = get_settings()

    @_retrying(settings.http_max_retries)
    async def _call() -> dict:
        resp = await client.get(
            settings.open_meteo_marine_base_url,
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
            raise UpstreamError(f"open-meteo marine {resp.status_code}: {resp.text[:200]}")
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
    """Turn the {"hourly": {"time": [...], "wave_height": [...], ...}} shape into one dict
    per hour. Missing/null values pass through as None.

    Open-Meteo returns naive timestamps under `timezone: GMT` by default (verified in
    docs/DATA_SOURCES.md probes) -- treated as UTC and made explicitly tz-aware, per the
    "no naive datetimes anywhere in the codebase" rule (prompts/phase-1-ingestion.md)."""
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
