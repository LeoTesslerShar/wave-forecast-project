"""APScheduler in-process, per PROMPT.md section 3 ("APScheduler in-process to start").
Runs the full ingestion cycle (backfill -> forecasts -> buoy) on a fixed interval, then
alert evaluation against whatever the ingestion cycle just wrote -- prompts/phase-4-alerting.md
section 2, "on every forecast refresh, re-evaluate active subscriptions"."""
import logging

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.alerting.runner import run_alert_evaluation
from app.db import SessionLocal
from app.ingestion.runner import run_full_ingestion_cycle
from app.logging_utils import log_event
from app.settings import get_settings

logger = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _job() -> None:
    async with SessionLocal() as session, httpx.AsyncClient() as client:
        try:
            summary = await run_full_ingestion_cycle(session, client)
            log_event(logger, logging.INFO, "scheduled ingestion cycle complete", **summary)
        except Exception as exc:  # noqa: BLE001 -- a scheduled job must never crash the process
            log_event(logger, logging.ERROR, "scheduled ingestion cycle raised", error=str(exc))

    async with SessionLocal() as session:
        try:
            summary = await run_alert_evaluation(session)
            log_event(logger, logging.INFO, "scheduled alert evaluation complete", **summary)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, logging.ERROR, "scheduled alert evaluation raised", error=str(exc))


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    settings = get_settings()
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _job,
        "interval",
        minutes=settings.ingestion_schedule_minutes,
        id="ingestion_cycle",
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
