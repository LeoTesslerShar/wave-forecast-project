"""Test fixtures. DB tests run against a real Postgres, but in a DEDICATED test database
(the configured DB name + "_test"), never the app's own database -- see docs/DECISIONS.md.
Running pytest with DATABASE_URL pointed at a live docker-compose stack must never touch
that stack's real seeded/ingested data; this was found the hard way during Phase 1's
acceptance run, when a local `pytest` invocation silently DROP-ALL'd the running app's
real data because it shared the connection string with the docker-compose `api` service.

Schema is created fresh per test via SQLAlchemy metadata, not via Alembic, to keep tests
fast and independent of migration history. No live network in any test (PROMPT.md section
3); every upstream call is mocked with respx from committed fixtures.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base
from app.settings import get_settings

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _test_db_url_and_name() -> tuple[str, str]:
    """The app's own DB name with a `_test` suffix -- e.g. `surf` -> `surf_test`. Computed
    from settings rather than hardcoded so CI (which also uses DATABASE_URL=.../surf) and
    local runs against docker-compose's Postgres both land in an isolated database."""
    raw = get_settings().database_url.replace("+asyncpg", "")
    parts = urlsplit(raw)
    base_name = parts.path.lstrip("/")
    test_name = f"{base_name}_test"
    test_path = f"/{test_name}"
    test_url = urlunsplit((parts.scheme, parts.netloc, test_path, parts.query, parts.fragment))
    return test_url, test_name


async def _ensure_test_database_exists(test_db_name: str) -> None:
    settings = get_settings()
    raw = settings.database_url.replace("postgresql+asyncpg", "postgresql")
    parts = urlsplit(raw)
    admin_dsn = urlunsplit((parts.scheme, parts.netloc, "/postgres", "", ""))

    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", test_db_name
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    test_url, test_name = _test_db_url_and_name()
    await _ensure_test_database_exists(test_name)

    engine = create_async_engine(f"{test_url.replace('postgresql', 'postgresql+asyncpg', 1)}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def marine_fixture() -> dict:
    return load_fixture("open_meteo_marine_full_2026-09-14.json")


@pytest.fixture
def wind_fixture() -> dict:
    return load_fixture("open_meteo_wind_2026-09-14.json")


@pytest.fixture
def hadera_fixture() -> dict:
    return load_fixture("isramar_hadera_2026-09-13.json")
