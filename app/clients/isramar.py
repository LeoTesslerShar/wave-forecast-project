"""ISRAMAR Hadera buoy -- undocumented endpoint, discovered via Yuvartz/yam-palta and
independently confirmed (docs/DATA_SOURCES.md). Returns exactly ONE current reading, no
history parameter -- there is nothing to backfill here; a missed fetch is a permanent gap.

Response shape (docs/DATA_SOURCES.md, tests/fixtures/isramar_hadera_2026-09-13.json):
  {"datetime": "2026-09-13 14:00 UTC",
   "parameters": [{"name": "Significant wave height", "units": "m", "values": [0.42]}, ...]}
"""
import re
from datetime import UTC, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.clients.errors import UpstreamError
from app.settings import get_settings

_PARAM_NAMES = {
    "wave_height": "Significant wave height",
    "wave_period": "Peak wave period",
    "wave_max": "Maximal wave height",
}

_DT_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})")


def _retrying(max_retries: int):
    return retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception_type((httpx.HTTPError, UpstreamError)),
    )


async def fetch_hadera(client: httpx.AsyncClient) -> dict:
    settings = get_settings()

    @_retrying(settings.http_max_retries)
    async def _call() -> dict:
        resp = await client.get(
            settings.isramar_hadera_url,
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": "surf-alert-system/0.1 (research use)"},
        )
        if resp.status_code != 200:
            raise UpstreamError(f"isramar hadera {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    try:
        return await _call()
    except httpx.HTTPError as exc:
        # Normalises connection-level failures (DNS, refused, timeout) the same way as
        # HTTP-status failures -- callers only ever need to catch UpstreamError. Found
        # missing during Phase 1's dead-buoy acceptance check: a raw ConnectError was
        # escaping past the per-source try/except in app/ingestion/runner.py.
        raise UpstreamError(f"{exc.__class__.__name__}: {exc}") from exc


def parse_reading(payload: dict) -> dict | None:
    """Returns None if the payload has no parseable reading -- callers must not write a
    row for a None result (mirrors the reference fetcher's own "keep existing on bad parse"
    precaution, see scripts/probe/reference_yam-palta_fetch-buoy.mjs)."""
    m = _DT_RE.match(payload.get("datetime", ""))
    if not m:
        return None
    y, mo, d, h, mi = (int(x) for x in m.groups())
    observed_at = datetime(y, mo, d, h, mi, tzinfo=UTC)

    params = {p.get("name"): p for p in payload.get("parameters", [])}

    def _val(key: str) -> float | None:
        p = params.get(_PARAM_NAMES[key])
        if not p or not p.get("values"):
            return None
        v = p["values"][0]
        try:
            v = float(v)
        except (TypeError, ValueError):
            return None
        # Sensor/format glitch guard -- same bound as the reference fetcher.
        if not (0 <= v < 30):
            return None
        return v

    wave_height = _val("wave_height")
    if wave_height is None:
        return None

    return {
        "observed_at": observed_at,
        "wave_height": wave_height,
        "wave_period": _val("wave_period"),
        "wave_max": _val("wave_max"),
    }
