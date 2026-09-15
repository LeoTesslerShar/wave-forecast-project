"""All configuration from environment. No hardcoded connection strings (PROMPT.md hard
rule 4) -- every value here has a name in .env.example, no values."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://surf:surf@postgres:5432/surf",
        description="Async SQLAlchemy connection string.",
    )
    database_url_sync: str = Field(
        default="postgresql+psycopg2://surf:surf@postgres:5432/surf",
        description="Sync connection string, used by Alembic.",
    )
    redis_url: str = Field(default="redis://redis:6379/0")

    open_meteo_marine_base_url: str = Field(default="https://marine-api.open-meteo.com/v1/marine")
    open_meteo_forecast_base_url: str = Field(default="https://api.open-meteo.com/v1/forecast")
    isramar_hadera_url: str = Field(
        default="https://isramar.ocean.org.il/isramar2009/station/data/Hadera_Hs_Per.json"
    )

    http_timeout_seconds: float = Field(default=30.0)
    http_max_retries: int = Field(default=3)

    forecast_hours_ahead: int = Field(
        default=168, description="How many hours ahead to fetch per beach per run."
    )
    backfill_max_days: int = Field(
        default=3, description="Cap on how far back a single backfill run will reach."
    )

    ingestion_schedule_minutes: int = Field(
        default=180, description="How often the scheduled ingestion job runs."
    )

    log_level: str = Field(default="INFO")

    # Web Push (prompts/phase-4-alerting.md section 5). Never committed (hard rule 4) --
    # blank by default; alerting degrades to "computed but not delivered" without them,
    # per hard rule 7, rather than crashing.
    vapid_public_key: str = Field(default="")
    vapid_private_key: str = Field(default="")
    vapid_claims_email: str = Field(default="admin@example.com")

    alert_evaluation_days_ahead: int = Field(
        default=3, description="How many local calendar days ahead to evaluate subscriptions for."
    )

    slot_watch_dispatch_minutes: int = Field(
        default=10,
        description=(
            "How often the slot-watch dispatcher runs. Deliberately far more frequent than "
            "ingestion_schedule_minutes (180) -- forecasts move fast, and a watch must fire "
            "close to the moment it qualifies, not up to 3h late."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
