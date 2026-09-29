"""APScheduler in-process, per PROMPT.md section 3 ("APScheduler in-process to start").
Two independent jobs on two different cadences:
  - ingestion_cycle: fetch fresh forecasts, then re-evaluate standing Subscriptions against
    whatever was just written -- prompts/phase-4-alerting.md section 2.
  - slot_watch_dispatch: re-check every open SlotWatch far more often than forecasts even
    refresh (app/settings.py slot_watch_dispatch_minutes, default 10 vs. ingestion's 180) --
    a watch must fire close to the moment it qualifies, not up to 3h late. Polling a
    Postgres table on a short interval, rather than scheduling a one-off APScheduler `date`
    job per watch, is deliberate: the default job store is in-memory, so a one-off job
    would be silently lost on any restart/redeploy, and every worker process would end up
    firing its own copy. A `SELECT ... FOR UPDATE SKIP LOCKED` poll (app/alerting/
    slot_watch.py) has neither problem.
"""
import logging
from datetime import UTC, datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.alerting.runner import run_alert_evaluation
from app.alerting.slot_watch import run_due_slot_watches
from app.db import SessionLocal
from app.ingestion.runner import run_full_ingestion_cycle
from app.logging_utils import log_event
from app.settings import get_settings

logger = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None


async def _ingestion_job() -> None:
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


async def _slot_watch_job() -> None:
    async with SessionLocal() as session:
        try:
            summary = await run_due_slot_watches(session)
            log_event(logger, logging.INFO, "scheduled slot watch dispatch complete", **summary)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, logging.ERROR, "scheduled slot watch dispatch raised", error=str(exc))


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    settings = get_settings()
    _scheduler = AsyncIOScheduler()
    # misfire_grace_time=None: a dev machine that sleeps freezes the container's wall clock
    # along with it. APScheduler's default grace window (a few seconds) is always blown by
    # the time it wakes, so without this the job doesn't just run late -- it's skipped
    # entirely, rescheduled for the NEXT interval boundary, which can be hours further out
    # still. None disables the grace check so a late-woken job runs immediately instead of
    # silently skipping (docs/DECISIONS.md).
    _scheduler.add_job(
        _ingestion_job,
        "interval",
        minutes=settings.ingestion_schedule_minutes,
        id="ingestion_cycle",
        misfire_grace_time=None,
        next_run_time=datetime.now(UTC),  # also run once immediately on every process start
    )
    _scheduler.add_job(
        _slot_watch_job,
        "interval",
        minutes=settings.slot_watch_dispatch_minutes,
        id="slot_watch_dispatch",
        misfire_grace_time=None,
    )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
