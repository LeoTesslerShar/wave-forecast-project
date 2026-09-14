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

## Status: Phase 3 (surf quality scoring) complete

| Phase | Status |
|---|---|
| 0 -- data source verification | done, historical record ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)) |
| 0.5 -- DeepLev spike | done, historical record ([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) |
| 1 -- ingestion | done: forecast (wave + wind) + Hadera buoy, scheduled, idempotent, gap-backfilled |
| 2 -- beach exposure | done: shoreline bearing from OSM coastline, directional + obstruction scoring, beach ranking |
| **3 -- surf quality scoring** | **this build**: wind, period, chop ratio combined into an hour-by-hour verdict |
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

**Phase 2 -- beach exposure** (`app/exposure/`), the main technical differentiator now that
the offshore forecast itself needs no correction (`docs/BIAS_ANALYSIS.md`):

- `shoreline_bearing` computed per beach from OSM coastline geometry
  (`scripts/exposure/coastline.geojson`, a committed extract -- see
  `scripts/exposure/fetch_coastline.py` for provenance) and written into
  `data/beaches.yml` by `scripts/exposure/compute_bearings.py`.
- Directional exposure: cosine of the angle between swell arrival and the shoreline
  normal, clamped to zero beyond 90 degrees.
- Obstruction: a coarse ray-cast against OSM breakwaters/piers/groynes
  (`scripts/exposure/structures.geojson`).
- `GET /beaches/{id}/exposure` -- exposure-adjusted estimate per hour, full
  `components`/`confidence` breakdown (prompts/phase-2-exposure.md section 3).
- `GET /conditions` -- **all beaches ranked for the same hour**, best first. This, not a
  single beach's absolute height, is the primary product surface going forward: geometry
  can defensibly say Herzliya beats Bat Yam under a given swell; it cannot defensibly say
  Herzliya will be exactly 1.2m.
- Every exposure-derived number carries `confidence.exposure: "unvalidated_heuristic"` and
  a `wave_height_range` never narrower than the offshore forecast's own measured
  uncertainty (~+/-0.25m, `docs/BIAS_ANALYSIS.md`) -- hard rule 1.

**Phase 3 -- surf quality scoring** (`app/quality/`): height alone doesn't say whether a
session is worth having -- wind and chop do. Combines Phase 2's exposure-adjusted size with
wind, period and chop ratio into one hour-by-hour verdict:

- **Wind** (`app/quality/wind.py`) -- the decisive factor. Scored by the angle between
  wind direction and the beach's shoreline normal: offshore grooms the face (best),
  onshore chops it up (worst), light wind (<8 km/h) is glassy regardless of direction, a
  large gust/mean spread is flagged and penalised.
- **Period** (`app/quality/period.py`) -- thresholds tuned for the Eastern Mediterranean's
  short-fetch wind-swell character, not imported from a long-fetch ocean coast.
- **Chop ratio** (`app/quality/chop.py`) -- `wind_wave_height / total`, free from data
  already ingested in Phase 1. A "good" height that's mostly wind-chop scores worse than
  the same height as clean groundswell.
- **Combiner** (`app/quality/verdict.py`) -- a weighted sum (wind weighted highest) for
  fine-grained ranking, capped by explicit rules (onshore wind and choppy conditions cap
  the verdict at "fair" no matter how the arithmetic comes out) -- not a fitted model, no
  ground truth exists to fit one to.
- `GET /beaches/{id}/quality` -- every component visible individually (size, period, wind,
  chop) plus the combined verdict and reasoning, hour-by-hour (a stormy afternoon's big
  number never leaks into the following dawn's score).
- Encodes the local pattern explicitly: off Israel the swell arrives *with* the westerly
  wind that generated it, so the storm peak itself is often the worst hour to go, and the
  following dawn -- once the land breeze turns offshore -- is when it cleans up. Verified
  directly: a storm-peak test case scores "fair" (capped by onshore wind) while the
  following dawn with smaller, cleaner swell scores "excellent."

- 41 tests, no live network.

## What is NOT built yet

Alerting/subscriptions and any frontend. Every forecast response already carries a
`method` field so no future caller ever sees an unlabelled number.

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
curl "http://localhost:8000/beaches/herzliya/exposure?hours=24"
curl "http://localhost:8000/conditions"      # all beaches ranked for the next hour
curl "http://localhost:8000/beaches/herzliya/quality?hours=24"   # size+period+wind+chop verdict, per hour
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
- Two beaches' shoreline bearings (`netanya`, `ashdod`) were computed from a thin coastline
  window and flagged in `data/beaches.yml` for manual review -- no visual map review was
  performed in this session (no map-viewing tool was available). Their values were
  cross-checked for consistency against neighbouring beaches instead; see
  `docs/DECISIONS.md`.
- Obstruction detection thresholds (range, lateral distance, strength) are judgement calls
  with no ground truth to tune them against -- see `docs/DECISIONS.md`.
- `issued_at` is the ingestion fetch time, not a real forecast-issue time -- neither
  upstream exposes one. See [`docs/DECISIONS.md`](docs/DECISIONS.md).
