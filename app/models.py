"""Schema per prompts/phase-1-ingestion.md section 2.

Key decisions recorded in docs/DECISIONS.md:
  - issued_at/valid_at kept distinct always (PROMPT.md hard rule 6); issued_at is the
    fetch time, since neither Open-Meteo endpoint exposes a real issue time.
  - latest_forecast access path uses a composite index (beach_id, valid_at, issued_at DESC)
    with a DISTINCT ON query, not a materialised view -- see docs/DECISIONS.md for why.
  - measurements keeps Hs (wave_height), Tp (wave_period) and Hmax (wave_max) as separate
    columns -- never merged, per the Hs/Hmax distinction in docs/DATA_SOURCES.md.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Beach(Base):
    __tablename__ = "beaches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    # Left NULL until Phase 2 computes it from OSM coastline geometry.
    shoreline_bearing: Mapped[float | None] = mapped_column(Float, nullable=True)
    obstruction_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    coordinate_source: Mapped[str | None] = mapped_column(Text, nullable=True)

    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="beach")


class Buoy(Base):
    __tablename__ = "buoys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # 'isramar' | 'cameri'
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    licence_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    measurements: Mapped[list["Measurement"]] = relationship(back_populates="buoy")


class Forecast(Base):
    """One row per (beach, issued_at, valid_at). issued_at is the fetch time -- neither
    Open-Meteo endpoint exposes a real issue time (docs/DATA_SOURCES.md, docs/DECISIONS.md).
    Wave and wind come from two different upstream calls and are merged into this one row;
    either half may be NULL if its upstream failed this run (see wind_fetch_failed)."""

    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint("beach_id", "issued_at", "valid_at", name="uq_forecast_natural_key"),
        # Supports `DISTINCT ON (beach_id, valid_at) ... ORDER BY beach_id, valid_at,
        # issued_at DESC` -- the latest-forecast access path. See docs/DECISIONS.md.
        Index("ix_forecast_latest", "beach_id", "valid_at", "issued_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    beach_id: Mapped[str] = mapped_column(ForeignKey("beaches.id"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- wave (marine-api.open-meteo.com/v1/marine) ---
    wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_source_model: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- wind (api.open-meteo.com/v1/forecast) ---
    wind_speed_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_gusts_10m: Mapped[float | None] = mapped_column(Float, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # True when a past valid_at was refetched during backfill: the value is "what the
    # forecast says now for that past hour", NOT what was actually forecast at the time.
    backfilled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True when the wind upstream failed this run and wind_* columns are NULL as a result
    # (as opposed to being genuinely not-yet-fetched). Distinguishes "known missing" from
    # "not attempted".
    wind_fetch_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    wave_fetch_failed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    beach: Mapped["Beach"] = relationship(back_populates="forecasts")


class Measurement(Base):
    """Hadera buoy readings. Hs (wave_height), Tp (wave_period) and Hmax (wave_max) are
    kept as separate columns deliberately -- see docs/DATA_SOURCES.md on why Hs and Hmax
    must never be merged into one generic wave_height."""

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("buoy_id", "observed_at", name="uq_measurement_natural_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buoy_id: Mapped[str] = mapped_column(ForeignKey("buoys.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)  # Hs
    wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)  # Tp
    wave_max: Mapped[float | None] = mapped_column(Float, nullable=True)  # Hmax
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    buoy: Mapped["Buoy"] = relationship(back_populates="measurements")


class IngestionRun(Base):
    """One row per ingestion attempt for one source. `/health` and gap detection both read
    this table -- it makes "did the run actually happen" a query instead of a log grep."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # 'wave' | 'wind' | 'buoy:<id>'
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # 'success' | 'failed' | 'partial'
    rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
