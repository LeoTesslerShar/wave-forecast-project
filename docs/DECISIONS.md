# Decisions log

Dated entries for anything the planning doc or a phase prompt left open (PROMPT.md
definition of done).

## 2026-09-14 -- Phase 1

### `issued_at` = fetch time, not a real issue time

Neither Open-Meteo endpoint (`marine-api.open-meteo.com/v1/marine`,
`api.open-meteo.com/v1/forecast`) exposes when the underlying model run was actually
issued -- confirmed in `docs/DATA_SOURCES.md`. `Forecast.issued_at` is therefore the
ingestion run's own timestamp, passed explicitly into `ingest_forecasts_for_beach` rather
than read from the clock per-row (this is also what makes idempotent re-runs possible --
retrying the same logical run with the same `issued_at` upserts onto the same natural key).

Consequence: "lead time" (`valid_at - issued_at`) means "hours between when we polled and
the hour being forecast," not "hours since the model run that produced this value." That is
the best available proxy and it only accrues meaning going forward -- there is still no
historical forecast-as-issued archive to backfill it from.

### Latest-forecast access path: `DISTINCT ON` + composite index, not a materialised view

`GET /beaches/{id}/forecast` needs "the newest `issued_at` row per `valid_at`," a query
that gets more expensive as history grows if done naively (e.g. a correlated subquery per
row). Chose a Postgres `DISTINCT ON (valid_at) ... ORDER BY valid_at, issued_at DESC` query
(`app/queries.py`) backed by a composite index `ix_forecast_latest (beach_id, valid_at,
issued_at)`.

Rejected: a materialised view refreshed on ingestion. Would need an explicit
`REFRESH MATERIALIZED VIEW` after every ingestion run (another thing to forget or get out
of sync), and buys nothing at this data volume (one row per beach per hour per ingestion
run -- tens of thousands of rows, not millions). Revisit if the index-backed query shows up
in a slow-query log; the acceptance check for this phase includes an `EXPLAIN ANALYZE`
confirming it uses `ix_forecast_latest` today.

### `measurements` keeps only the Hadera buoy live; Ashdod/Haifa modelled but inactive

Per `docs/DATA_SOURCES.md`, ISRAMAR's Hadera endpoint is the only buoy source reachable
without an institutional request. Ashdod and Haifa exist as `Buoy` rows with
`source='cameri'`, `active=False` so a future session can wire them up without a schema
migration, but nothing polls them.

### Hadera data carries an unresolved licence restriction

The IOLR "All Rights Reserved" notice on the Hadera station page has not been cleared with
written permission (`docs/DATA_SOURCES.md`). `app/seed.py` logs a startup warning for any
buoy whose `licence_note` mentions "written permission." The measurements table exists and
is populated for personal/research use; nothing in this codebase redistributes it.

### `/health` staleness threshold

A source is marked `"stale"` if its last successful run is older than
`3 x INGESTION_SCHEDULE_MINUTES` (`app/api/health.py`). Chosen to absorb exactly one missed
scheduled run without flapping the whole system to "degraded" on ordinary jitter, while
still catching a source that has been silently dead for a while.

### Backfill is day-granularity, capped at `BACKFILL_MAX_DAYS` (default 3)

`find_gap_days` checks whole days for zero forecast rows, not individual missing hours.
Simpler, and sufficient for "did a scheduled run get missed" -- a partial day with some
rows present almost never happens under normal operation (a run either fires for all
beaches or the process is down). If sub-day gaps turn out to matter in practice, this is
the place to revisit.
