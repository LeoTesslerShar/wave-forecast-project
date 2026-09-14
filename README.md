# Surf Alert System

A backend that watches the surf for a handful of Israeli beaches and pushes an alert when a
session is actually worth driving to -- ranked against your other beaches, scored for
quality, not just size.

**This is not what the project set out to build, and that's on the record, not hidden.**
The original plan was to bias-correct the regional wave forecast against measured buoy
history. A spike against 11,161 hours of real measurement
([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) found that premise mostly false: in the
0.5-1.5 m band this project's user actually surfs, the offshore model is already accurate
(bias -0.001 m, MAE 0.091 m, 90% of errors within +/-0.19 m). There is no forecast bias to
correct where it matters.

What the spike found instead: the model misses 13-21% of real sessions at the top of the
surfable range because it compresses extremes. That's not a number to correct -- it's a
threshold trade-off the user can tune, calibrated against the measured hit/false-alarm
curve. **The honest value of this system is convenience, beach discrimination and quality
judgement -- not superior wave-height accuracy.** Full story in
[`PROMPT.md`](PROMPT.md) section 1.

## Status: Phase 1 (ingestion) complete

| Phase | Status |
|---|---|
| 0 -- data source verification | done, historical record ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)) |
| 0.5 -- DeepLev spike | done, historical record ([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) |
| **1 -- ingestion** | **this build**: forecast (wave + wind) + Hadera buoy, scheduled, idempotent, gap-backfilled |
| 2 -- beach exposure | not built |
| 3 -- surf quality scoring | not built |
| 4 -- alerting | not built |
| 5 -- frontend | not built |

## What exists right now

- Scheduled ingestion (APScheduler, every `INGESTION_SCHEDULE_MINUTES`, default 3h) of:
  - Wave height/period/direction + swell/wind-sea split, per beach, from
    `marine-api.open-meteo.com/v1/marine`
  - Wind speed/direction/gusts, per beach, from `api.open-meteo.com/v1/forecast` (a
    **different** endpoint -- the marine API doesn't carry 10m wind)
  - The Hadera buoy (ISRAMAR), hourly -- the only buoy with an accessible feed; see
    [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md). **Licence note:** IOLR's data carries an
    "all rights reserved" notice with no written permission obtained yet -- this data is
    ingested for personal/research use and must not be redistributed.
- Idempotent upserts on `(beach_id, issued_at, valid_at)` for forecasts,
  `(buoy_id, observed_at)` for measurements.
- Gap detection + backfill for missed scheduled runs (not deep history -- there is none to
  recover; see [`docs/DECISIONS.md`](docs/DECISIONS.md)). Backfilled rows are flagged.
- Graceful degradation: a dead upstream (wave, wind, or the buoy) fails only that source,
  logs it to `ingestion_runs`, and never blocks the others or crashes the app.
- `GET /health`, `GET /beaches`, `GET /beaches/{id}/forecast`,
  `GET /buoys/{id}/measurements`.
- 19 tests, no live network (every upstream response mocked from a committed fixture).

## What is NOT built yet

Beach exposure scoring, surf quality scoring, alerting/subscriptions, and any frontend.
Every forecast response already carries a `method: "raw"` field so no future caller ever
sees an unlabelled number once those layers exist.

## Running it

```
cp .env.example .env      # already done in this repo for local dev; real deploys should not commit .env
docker compose up -d
```

First boot runs Alembic migrations, seeds beaches/buoys from `data/beaches.yml`, then starts
serving. Ingestion fires on the schedule; nothing blocks startup waiting for it.

```
curl http://localhost:8000/health
curl http://localhost:8000/beaches
curl "http://localhost:8000/beaches/herzliya/forecast?hours=24"
```

Tests (needs Postgres + Redis reachable -- `docker compose up -d postgres redis` then run
outside the container, or `docker compose run --rm api pytest`):

```
docker compose run --rm api pytest -v
```

## Known limitations

- Offshore forecast accuracy is validated at exactly one point (DeepLev, 50 km off Haifa,
  data through March 2024). Applying it elsewhere on the coast, or trusting it against
  today's model behaviour, is an assumption -- see
  [`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md) limitations.
- No ground truth exists at any actual Israeli beach. Everything from Phase 2 onward
  (exposure, quality scoring) is geometry and local knowledge, not measurement, and will be
  labelled as such in every API response, by design, permanently.
- `issued_at` is the ingestion fetch time, not a real forecast-issue time -- neither
  upstream exposes one. See [`docs/DECISIONS.md`](docs/DECISIONS.md).
