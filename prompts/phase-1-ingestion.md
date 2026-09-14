# Phase 1 — Ingestion pipeline

Read `PROMPT.md`, `docs/PLANNING.md` (§5, §7 — for the schema sketch and engineering
problems, not the value chain, which `PROMPT.md` §1 has superseded), `docs/DATA_SOURCES.md`,
and `docs/BIAS_ANALYSIS.md` first.

This is the foundation. Everything later reads from what this phase writes, so the parts
that look like plumbing — idempotency, gap detection, the `issued_at`/`valid_at` pair —
are the actual deliverable.

**What changed after Phase 0/0.5 (see `PROMPT.md` §1 for the full story):** the project no
longer builds a bias-correction layer — `docs/BIAS_ANALYSIS.md` found the offshore forecast
is already accurate where the user surfs. So this phase is simpler than an earlier draft
assumed: no bulk historical import, no multi-instrument provenance tracking. What it needs
instead, that the original planning doc never had, is **wind** — the decisive input for
Phase 3's quality scoring.

---

## Scope

Repo skeleton, schema, scheduled ingestion of forecasts (wave + wind) and the Hadera buoy,
backfill, and a read API thin enough to prove the data is there. No exposure scoring
(Phase 2), no quality scoring (Phase 3), no alerts (Phase 4), no frontend (Phase 5).

---

## 1. Repository skeleton

Mostly done already — the repo is initialised (Phase 0/0.5 commits exist). What's new:

- `docker-compose.yml`: `api`, `postgres`, `redis`. Named volumes. Healthchecks on
  postgres and redis, with `api` depending on them being healthy.
- `Dockerfile` for the API. Pinned dependencies (`requirements.txt` or `pyproject.toml` +
  lock — pick one and be consistent).
- `.env.example` with every key name, no values.
- Settings via Pydantic `BaseSettings`. No hardcoded connection strings anywhere.
- Alembic wired up, first migration generated from the models.
- `pytest` configured and running in the container.
- GitHub Actions workflow: install, lint, run tests on push. Tests must not need network.
- `README.md`: what this is, how to run it, what exists so far — open with the honest
  framing from `PROMPT.md` §1, not the original planning doc's premise.

---

## 2. Schema

Follow the data-model sketch in planning doc §5, adjusted as below.

**`forecasts` — the important table.**

- Both `issued_at` and `valid_at`, both `timestamptz`, both indexed. Hard rule 6: they are
  never collapsed. The same `valid_at` will hold many rows with different `issued_at`, and
  that redundancy is what makes future forecast-error-vs-lead-time analysis possible (still
  unmeasured — `docs/DATA_SOURCES.md` confirmed no historical forecast-as-issued archive
  exists anywhere, so this only accrues forward from today).
- Natural key: `(beach_id, issued_at, valid_at)` with a unique constraint. Ingestion
  upserts on it.
- A **`latest_forecast(beach_id, valid_at)`** access path that does not degrade as history
  grows. Implement it deliberately — a composite index supporting
  `DISTINCT ON (beach_id, valid_at) ... ORDER BY beach_id, valid_at, issued_at DESC`, or a
  materialised latest-view, your call — and write down which you chose and why in
  `docs/DECISIONS.md`. Do not leave "get the latest forecast" as an unindexed sort.
- **Wave columns:** `wave_height`, `wave_direction`, `wave_period`, plus the swell/wind-sea
  split — `swell_wave_height`, `swell_wave_direction`, `swell_wave_period`,
  `wind_wave_height`, `wind_wave_direction`, `wind_wave_period`. All fetched from
  `marine-api.open-meteo.com/v1/marine` (verified working, see `docs/DATA_SOURCES.md` and
  `scripts/deeplev/fetch_model.py` for the working call pattern). The split is not optional
  — Phase 3's chop-ratio scoring depends on it, and it costs nothing extra to fetch.
- **Wind columns:** `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m`. **A different
  endpoint** — `api.open-meteo.com/v1/forecast` — the marine endpoint does not carry 10 m
  wind. Verified working during the Phase 0.5 spike (200, real values). Fetch it in the
  same scheduled run as the wave data and store it on the same `forecasts` row, keyed to
  the same `(beach_id, issued_at, valid_at)` — do not create a second forecasts-like table.
- Store the source model name and the fetch timestamp per row. When a phase later asks
  "which model produced this", the answer must be in the data.

**`measurements`.**

- Natural key `(buoy_id, observed_at)`, unique.
- Only the Hadera buoy is wired as a live feed (per `docs/DATA_SOURCES.md`: no accessible
  endpoint for Ashdod/Haifa without a gated CAMERI request). Model them in the schema
  (`buoys` rows with `source='cameri'`, inactive) so adding them later needs no migration.
- Columns: `wave_height` (Hs), `wave_period`, `wave_max` (Hmax) — kept as **separate,
  explicitly named columns**, never merged into one generic `wave_height` that silently
  mixes Hs and Hmax.
- This table is now a nice-to-have reality anchor, not a training source — the bias
  question was already answered by the DeepLev spike (`docs/BIAS_ANALYSIS.md`), which used
  its own separate offline pipeline (`scripts/deeplev/`), not this table. Don't build
  machinery here anticipating a use this table won't actually have.
- **Do not redistribute this data outside personal/research use** — the licence notice
  found in Phase 0 requires written IOLR permission not yet obtained. Log a visible startup
  warning saying so.

**`buoys`, `beaches`.**

- `beaches.shoreline_bearing` nullable, left NULL in this phase — Phase 2 fills it.
- `beaches` seeded via migration or a seed script from a committed
  `data/beaches.yml`: 8–12 Israeli surf spots with coordinates — Bat Yam, Herzliya,
  Palmachim, Netanya, Ashdod, Hadera, Olga, Tel Aviv (Hilton), and others you can source
  coordinates for. Note the coordinate source in the file.
- `ingestion_runs`: `source`, `started_at`, `finished_at`, `status`, `rows_written`,
  `window_start`, `window_end`, `error`. Gap detection and the health endpoint both read
  this, and it makes "did the 04:00 run actually happen" a query instead of a log grep.

All timestamps `timestamptz`, all stored UTC. No naive datetimes anywhere in the codebase.

---

## 3. Ingestion

**Forecast fetch — two upstream calls per beach, one row.** All configured beach
coordinates, on a schedule (APScheduler, see `PROMPT.md` §3):

1. `marine-api.open-meteo.com/v1/marine` for wave height/period/direction + swell/wind-sea
   split.
2. `api.open-meteo.com/v1/forecast` for wind speed/direction/gusts.

Merge both into one `forecasts` row per `(beach_id, issued_at, valid_at)`. Open-Meteo does
not expose a real issue time on either endpoint (`docs/DATA_SOURCES.md`) — use the fetch
time as `issued_at` and **document that substitution in `docs/DECISIONS.md`**, since it
defines what "lead time" means for any future forecast-error analysis.

**Buoy fetch — Hadera only.** `.../station/data/Hadera_Hs_Per.json` (per
`docs/DATA_SOURCES.md`). Ingest it hourly. The endpoint returns exactly one current reading
with no history parameter, so this fetch *is* the entire historical record from now on —
treat missing a scheduled fetch as a permanent gap, not a recoverable one.

**Requirements, all of them testable:**

- **Idempotent writes.** Re-running ingestion over the same window writes zero new rows.
  Upsert on the natural keys above. This is tested, not assumed.
- **Retry with backoff** on upstream failure, with a cap. Log each attempt. Handle the two
  forecast upstreams' failures independently — a wind-endpoint outage should not block wave
  data from being written, and vice versa; a partial row (wave data, null wind) is better
  than no row, as long as it's clearly flagged as partial.
- **Graceful degradation** (hard rule 7). A dead buoy source, or a dead wind source, fails
  that source's run, records the failure in `ingestion_runs`, and leaves the rest of the
  pipeline and the API untouched. Nothing raises out of the scheduler; nothing 500s.
- **Gap detection and backfill — for missed *scheduled* runs, not deep history.**
  Open-Meteo's forecast endpoints support recent-past requests (`past_days`, up to 92), so a
  gap from a short outage can be partially refilled — refetching now for a past `valid_at`
  gets *today's* forecast for that hour, not what was actually forecast at the time, so
  backfilled rows must be flagged (e.g. `backfilled=true`). The Hadera buoy has no history
  endpoint at all — a missed buoy fetch is a permanent gap; gap detection there means
  *alerting* on the miss (via `ingestion_runs` + `/health`), not filling it. Cap any
  forecast backfill window so a long outage cannot trigger an unbounded fetch storm.
- **Structured JSON logging** per run: source, window, duration, rows written, rows
  skipped as duplicates, retries, outcome. One line per run, machine-parseable.

---

## 4. Minimal read API

Enough to prove the pipeline works, no more:

- `GET /health` — DB, Redis, and per-source (wave, wind, buoy) last-successful-ingestion
  age. Degraded, not down, when any one source is stale.
- `GET /beaches`
- `GET /beaches/{id}/forecast` — latest forecast per `valid_at` for the next N hours (wave
  + wind together), via the access path from §2. Redis-cached.
- `GET /buoys/{id}/measurements?from=&to=`

Every forecast response includes `issued_at` alongside `valid_at` (hard rule 6) and a
`method` field — `"raw"` at this stage. Phases 2 and 3 will change its value, and having the
field present from the start means no caller ever sees an unlabelled number.

---

## 5. Tests

- Unit tests for the parsers, driven by fixtures in `tests/fixtures/` (Phase 0's are there
  for the marine/ISRAMAR shapes; add one for the `v1/forecast` wind response). No live
  network in CI.
- **Idempotency test:** ingest a fixture window twice, assert the row count is identical
  and no row was mutated.
- **Degradation test:** each upstream (wave, wind, buoy) independently raising / returning
  500, assert the run is recorded as failed for that source, the rest of the pipeline still
  succeeds, and `/health` reports degraded rather than erroring.
- **Partial-row test:** wind upstream fails but wave upstream succeeds — assert a row is
  still written with wave data present and wind null, flagged appropriately.
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
3. A forecast response showing wave height, the swell/wind-sea split, and wind
   speed/direction/gusts all populated for the same `(beach_id, valid_at)`.
4. Point the buoy source at a dead host, run ingestion, show: the failure row in
   `ingestion_runs`, `/health` reporting degraded, and `/beaches/{id}/forecast` still
   returning data.
5. `DELETE` a day of forecasts, run gap detection, show the rows restored.
6. `EXPLAIN ANALYZE` on the latest-forecast query, showing it uses the index.
7. `docker compose run --rm api pytest` — full output.

## Then stop

Report what the upstream data actually looked like, then wait. If anything you found
changes Phase 2's assumptions, edit `prompts/phase-2-exposure.md` and say what you changed.
