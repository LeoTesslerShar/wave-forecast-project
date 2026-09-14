import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# Phase 5's frontend is served as its own container on a different port -- CORS is
# ordinary cross-origin wiring for that, not new business logic (PROMPT.md section 3's
# "do not invent new backend logic" is about scoring/matching rules, not this).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(beaches.router)
app.include_router(buoys.router)
app.include_router(alerting.router)
