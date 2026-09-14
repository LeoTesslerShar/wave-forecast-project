import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import alerting, beaches, buoys, health
from app.db import SessionLocal
from app.logging_utils import configure_logging, log_event
from app.scheduler import start_scheduler, stop_scheduler
from app.seed import seed_beaches_and_buoys

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    async with SessionLocal() as session:
        await seed_beaches_and_buoys(session)
    start_scheduler()
    log_event(logger, logging.INFO, "app startup complete")
    yield
    stop_scheduler()


app = FastAPI(title="Surf Alert System -- ingestion API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(beaches.router)
app.include_router(buoys.router)
app.include_router(alerting.router)
