# Phase 1 — Ingestion pipeline

Read `PROMPT.md`, `docs/PLANNING.md` (§5, §6 Phase 1, §7) and `docs/DATA_SOURCES.md` first.

**Do not start this phase if `docs/DATA_SOURCES.md` does not exist.** Phase 0 is a gate.
Build against the endpoints and response shapes it actually recorded, not against what
this prompt assumes.

This is the foundation. Everything later reads from what this phase writes, so the parts
that look like plumbing — idempotency, gap detection, the `issued_at`/`valid_at` pair —
are the actual deliverable.

**Updated after the Phase 0 correction (see `docs/DATA_SOURCES.md`):**

- There is still **no historical forecast-as-issued data** — lead-time pairs accumulate only
  from the day this goes live, so backfill means catching *missed scheduled runs*, not
  reconstructing history.
- But there **is** substantial historical *measurement* data: **DeepLev**, ~21 months
  overlapping the Open-Meteo archive, arriving as bulk NetCDF rather than a live feed.

So the schema must serve two shapes of measurement at once, and this is the main thing to
get right in this phase:

1. **Live trickle** — Hadera, one reading per hour, arriving forever.
2. **Bulk historical import** — DeepLev, ~15k hourly rows landing in one go, from files.

Requirements that follow, all of which are cheaper now than as a migration later:

- `measurements` carries a **station** reference, not a "buoy" assumption — DeepLev is a
  subsurface ADCP mooring, not a buoy, and the instrument type changes how its error should
  be read.
- **Instrument and provenance columns:** instrument type, deployment id, measurement depth,
  distance offshore, and whether the row arrived live or by bulk import. Phase 2 needs to
  split on all of these; recovering them later is impossible.
- **Parameter identity is explicit.** DeepLev reports Hm0, Hmax, Tp, Tm02, energy period,
  peak *and* mean direction. Hadera reports Hs, Tp, Hmax. These are not interchangeable —
  Hs/Hm0 vs Hmax especially. One column per distinct parameter, or an explicit
  parameter-type column; never a generic `wave_height` that silently mixes them.
- Only the Hadera buoy is wired as a live feed. Ashdod/Haifa stay modelled but inactive.

---

## Scope

Repo skeleton, schema, scheduled ingestion of forecasts and buoy measurements, backfill,
and a read API thin enough to prove the data is there. No calibration, no exposure
scoring, no alerts, no frontend.

---

## 1. Repository skeleton

- `git init`, first commit. `.gitignore` covering `.env`, `__pycache__`, `.venv`,
  model artefacts, `node_modules`.
- `docker-compose.yml`: `api`, `postgres`, `redis`. Named volumes. Healthchecks on
  postgres and redis, with `api` depending on them being healthy.
- `Dockerfile` for the API. Pinned dependencies (`requirements.txt` or `pyproject.toml` +
  lock — pick one and be consistent).
- `.env.example` with every key name, no values.
- Settings via Pydantic `BaseSettings`. No hardcoded connection strings anywhere.
- Alembic wired up, first migration generated from the models.
- `pytest` configured and running in the container.
- GitHub Actions workflow: install, lint, run tests on push. Tests must not need network.
- `README.md`: what this is, how to run it, what exists so far.

---

## 2. Schema

Follow the data-model sketch in planning doc §5. Specific requirements beyond it:

**`forecasts` — the important one.**

- Both `issued_at` and `valid_at`, both `timestamptz`, both indexed. Hard rule 6: they are
  never collapsed. The same `valid_at` will hold many rows with different `issued_at`, and
  that redundancy is the point — it is what Phase 2 mines and what Phase 5 dedups against.
- Natural key: `(beach_id, issued_at, valid_at)` with a unique constraint. Ingestion
  upserts on it.
- A **`latest_forecast(beach_id, valid_at)`** access path that does not degrade as history
  grows. Implement it deliberately — a composite index supporting
  `DISTINCT ON (beach_id, valid_at) ... ORDER BY beach_id, valid_at, issued_at DESC`, or a
  materialised latest-view, your call — and write down which you chose and why in
  `docs/DECISIONS.md`. Do not leave "get the latest forecast" as an unindexed sort.
- Store the source model name and the fetch timestamp per row. When a phase later asks
  "which model produced this", the answer must be in the data.

**`measurements`.**

- Natural key `(buoy_id, observed_at)`, unique.
- Store the parameter as measured, with its actual meaning. If a buoy reports Hmax and
  another reports Hs, **they get different columns or an explicit parameter-type column**.
  Do not merge them into one `wave_height` and lose the distinction — Phase 2 joins on
  this and a silent Hs/Hmax mixture would invalidate every result downstream.

**`buoys`, `beaches`.**

- `beaches.shoreline_bearing` nullable, left NULL in this phase — Phase 4 fills it.
- `beaches` seeded via migration or a seed script from a committed
  `data/beaches.yml`: 8–12 Israeli surf spots with coordinates — Bat Yam, Herzliya,
  Palmachim, Netanya, Ashdod, Hadera, Olga, Tel Aviv (Hilton), and others you can source
  coordinates for. Note the coordinate source in the file.
- `ingestion_runs` (not in the sketch, add it): `source`, `started_at`, `finished_at`,
  `status`, `rows_written`, `window_start`, `window_end`, `error`. Gap detection and the
  health endpoint both read this, and it makes "did the 04:00 run actually happen" a
  query instead of a log grep.

All timestamps `timestamptz`, all stored UTC. No naive datetimes anywhere in the codebase.

---

## 3. Ingestion

**Forecast fetch.** All configured beach coordinates, on a schedule (APScheduler, see
`PROMPT.md` §3). Open-Meteo does not expose a real issue time (`docs/DATA_SOURCES.md`
confirmed there is no forecast-as-issued archive at all, live or historical) — use the
fetch time as `issued_at` and **document that substitution in `docs/DECISIONS.md`**,
because it defines what "lead time" means for every later phase.

**Buoy fetch — Hadera only.** Per `docs/DATA_SOURCES.md`, only ISRAMAR's Hadera endpoint
(`.../station/data/Hadera_Hs_Per.json`) is reachable without institutional permission.
Ingest it hourly, storing `waveHeight` (Hs) and `wavePeriod` distinctly from `waveMax`
(Hmax) — do not conflate them. The endpoint returns exactly one current reading with no
history parameter, so this fetch *is* the entire historical record from now on — treat
missing a scheduled fetch as a permanent gap, not a recoverable one (see backfill note
below). **Do not redistribute this data outside personal/research use** — the licence
notice found in Phase 0 requires written IOLR permission the user has not yet obtained;
log a visible startup warning saying so. Do not wire up Ashdod or Haifa — no accessible
endpoint exists for them (CAMERI requires a gated API request); model them in the schema
(`buoys` row with `source='cameri'`, inactive) so adding them later needs no migration.

**Requirements, all of them testable:**

- **Idempotent writes.** Re-running ingestion over the same window writes zero new rows.
  Upsert on the natural keys above. This is tested, not assumed.
- **Retry with backoff** on upstream failure, with a cap. Log each attempt.
- **Graceful degradation** (hard rule 7). A dead buoy source fails that source's run,
  records the failure in `ingestion_runs`, and leaves the forecast pipeline and the API
  untouched. Nothing raises out of the scheduler; nothing 500s.
- **Gap detection and backfill — for missed *scheduled* runs, not deep history.**
  Open-Meteo's forecast endpoint does support recent-past requests (`past_days`, up to 92),
  so a forecast gap from a short outage can be partially refilled — refetching now for a
  past `valid_at` gets *today's* forecast for that hour, not what was actually forecast at
  the time, so backfilled forecast rows must be flagged (e.g. `backfilled=true`) and are
  not equivalent to a row captured live. The Hadera buoy has no history endpoint at all
  (`docs/DATA_SOURCES.md`) — a missed buoy fetch is a permanent gap, full stop; gap
  detection here means *alerting* on the miss (via `ingestion_runs` + `/health`), not
  filling it. Cap any forecast backfill window so a long outage cannot trigger an
  unbounded fetch storm.
- **Structured JSON logging** per run: source, window, duration, rows written, rows
  skipped as duplicates, retries, outcome. One line per run, machine-parseable.

---

## 4. Minimal read API

Enough to prove the pipeline works, no more:

- `GET /health` — DB, Redis, and per-source last-successful-ingestion age. Degraded, not
  down, when a buoy source is stale.
- `GET /beaches`
- `GET /beaches/{id}/forecast` — latest forecast per `valid_at` for the next N hours, via
  the access path from §2. Redis-cached.
- `GET /buoys/{id}/measurements?from=&to=`

Every forecast response includes `issued_at` alongside `valid_at` (hard rule 6) and a
`method` field — `"raw"` at this stage. Phases 3 and 4 will change its value, and having
the field present from the start means no caller ever sees an unlabelled number.

---

## 5. Tests

- Unit tests for the parsers, driven by the Phase 0 fixtures in `tests/fixtures/`. No live
  network in CI.
- **Idempotency test:** ingest a fixture window twice, assert the row count is identical
  and no row was mutated.
- **Degradation test:** buoy source raising / returning 500, assert the run is recorded as
  failed, the forecast run still succeeds, and `/health` reports degraded rather than
  erroring.
- **Backfill test (forecasts only):** delete a window of forecast rows, run gap detection,
  assert it is refilled with rows flagged `backfilled=true`, and that a second run adds
  nothing. No equivalent test for buoy data — there is nothing to backfill it from.
- **Latest-forecast test:** insert three `issued_at` rows for one `valid_at`, assert the
  query returns exactly the newest.

---

## Acceptance checks

Run these against a real `docker compose up` and paste the real output:

1. `docker compose down -v; docker compose up -d` from clean, then `/health` returning OK.
2. Ingestion run once → row count. Run again over the same window → **same row count**.
   Show both numbers.
3. Point the buoy source at a dead host, run ingestion, show: the failure row in
   `ingestion_runs`, `/health` reporting degraded, and `/beaches/{id}/forecast` still
   returning data.
4. `DELETE` a day of forecasts, run gap detection, show the rows restored.
5. `EXPLAIN ANALYZE` on the latest-forecast query, showing it uses the index.
6. `docker compose run --rm api pytest` — full output.

## Then stop

Report what the upstream data actually looked like versus what Phase 0 predicted, then
wait. If anything you found changes Phase 2's assumptions, edit `prompts/phase-2-alignment.md`
and say what you changed.
