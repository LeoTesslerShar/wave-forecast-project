"""Schema per prompts/phase-1-ingestion.md section 2.

Key decisions recorded in docs/DECISIONS.md:
  - issued_at/valid_at kept distinct always (PROMPT.md hard rule 6); issued_at is the
    fetch time, since neither Open-Meteo endpoint exposes a real issue time.
  - latest_forecast access path uses a composite index (beach_id, valid_at, issued_at DESC)
    with a DISTINCT ON query, not a materialised view -- see docs/DECISIONS.md for why.
  - measurements keeps Hs (wave_height), Tp (wave_period) and Hmax (wave_max) as separate
    columns -- never merged, per the Hs/Hmax distinction in docs/DATA_SOURCES.md.
"""
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Beach(Base):
    __tablename__ = "beaches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Hebrew display name -- the UI is Hebrew/RTL only, no i18n framework (docs/DECISIONS.md).
    # Nullable so an unseeded/unknown beach never breaks the API; the frontend falls back to
    # `name` if this is absent rather than showing a blank.
    name_he: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    # MEAN period (Tm) -- Open-Meteo best_match's `wave_period`. Note this is NOT the same
    # quantity as Measurement.wave_period below, which is the buoy's real Tp; the two share
    # a name because the upstreams do, and merging or comparing them would be wrong.
    wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Real peak period (Tp), from a second model -- see app/clients/open_meteo_marine.py
    # PEAK_PERIOD_MODEL. Nullable: it comes from a separate request that is allowed to fail
    # independently, and quality scoring falls back to wave_period when it is absent.
    wave_peak_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_direction: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_wave_period: Mapped[float | None] = mapped_column(Float, nullable=True)
    wave_source_model: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- wind + weather (api.open-meteo.com/v1/forecast -- same request as wind) ---
    wind_speed_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_gusts_10m: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Raw WMO 4677 weather code -- app/quality/weather.py maps it to a Hebrew label/icon.
    # Stored as the raw code, not the translated label, same discipline as everywhere else
    # in this schema (store what was measured, translate at the display layer).
    weather_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

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


class Subscription(Base):
    """A user's surf-alert criteria -- prompts/phase-4-alerting.md section 1. `user_id` is
    a simple opaque identifier (planning doc section 8 -- no full auth in this project).

    `time_window_start`/`time_window_end` are LOCAL wall-clock times (Asia/Jerusalem);
    `end <= start` means the window crosses midnight -- see app/alerting/timewindow.py.
    """

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    beach_id: Mapped[str] = mapped_column(ForeignKey("beaches.id"), nullable=False)
    # Optional second delivery channel alongside Web Push (app/alerting/email.py) -- opt-in
    # per subscription, not a global account setting, since this project has no real user
    # accounts (just the opaque user_id above). Null means "push only".
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    min_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Preferred swell direction range in degrees, may wrap across 0/360 (e.g. min=300,
    # max=30 means "300 through 360 through 30"). Both null means "no preference".
    swell_dir_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    swell_dir_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    time_window_start: Mapped[time] = mapped_column(Time, nullable=False)
    time_window_end: Mapped[time] = mapped_column(Time, nullable=False)

    # "strict" | "balanced" | "generous" -- app/alerting/calibration.py
    operating_point: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    beach: Mapped["Beach"] = relationship()


class PushSubscription(Base):
    """A registered Web Push endpoint (one per browser/device) -- prompts/phase-4-alerting.md
    section 5. Not tied to a single Subscription -- one user's devices receive alerts for
    all of that user's active Subscriptions."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AlertSent(Base):
    """Append-only log of every alert decision actually acted on (send or deliberate
    silence is NOT logged here -- only sends: initial alerts, material-change updates, and
    cancellations). `target_date` + `subscription_id` identifies "the same window" across
    repeated evaluation runs, per prompts/phase-4-alerting.md section 3 -- the latest row
    for a (subscription_id, target_date) pair is the current state to compare the next
    evaluation against. `conditions_snapshot` stores what was actually said, not a
    boolean, so material-change comparison has real numbers to work from.
    """

    __tablename__ = "alerts_sent"
    __table_args__ = (
        Index("ix_alerts_sent_latest", "subscription_id", "target_date", "sent_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id"), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # 'alert' | 'update' | 'cancellation'
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    conditions_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SlotWatch(Base):
    """A user watching ONE specific forecast slot for one beach -- distinct from
    Subscription (a standing, recurring criteria rule evaluated against every day). Tapping
    "alert me" on an hourly slot in the UI creates one of these.

    Not a fixed-offset reminder: it stays dormant until `watch_from` (= valid_at minus
    app/alerting/slot_watch.py's WATCH_LEAD_HOURS, stored rather than computed so the lead
    is auditable and independently tunable later), then is re-evaluated on every dispatcher
    tick and fires the moment the slot's quality_score crosses QUALIFY_SCORE -- not before,
    because Israeli coastal forecasts move too fast to trust much earlier than that. If it
    was alerted and the slot later falls back below the bar, one cancellation is sent and
    status moves to 'cancelled' -- see docs/DECISIONS.md.

    Deliberately its own table, not an extension of Subscription: Subscription's
    time_window_start/end are NOT NULL local wall-clock Time columns describing a recurring
    window, not a single absolute instant, and AlertSent.subscription_id is a NOT NULL FK --
    neither fits a one-off watch on a specific slot without weakening an existing invariant.
    """

    __tablename__ = "slot_watches"
    __table_args__ = (
        UniqueConstraint("user_id", "beach_id", "valid_at", name="uq_slot_watch_slot"),
        # The dispatcher's due-query: status='pending' or 'alerted' AND watch_from <= now.
        Index("ix_slot_watch_due", "status", "watch_from"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    beach_id: Mapped[str] = mapped_column(ForeignKey("beaches.id"), nullable=False)
    # Optional second delivery channel alongside Web Push (app/alerting/email.py) -- opt-in
    # per watch. Null means "push only".
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    watch_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # 'pending' (dormant or watching, not yet qualified) | 'alerted' (qualified, pushed) |
    # 'cancelled' (qualified then fell back below the bar, cancellation pushed) |
    # 'expired' (valid_at passed while still pending -- never qualified, no message sent).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # What was actually said when the watch last fired (alert or cancellation) -- needed to
    # detect the alerted -> cancelled transition, mirrors AlertSent.conditions_snapshot.
    conditions_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    beach: Mapped["Beach"] = relationship()
