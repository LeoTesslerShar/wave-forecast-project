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
curve (the actual table is in `docs/BIAS_ANALYSIS.md`, not invented). **The honest value of
this system is convenience, beach discrimination and quality judgement -- not superior
wave-height accuracy.** Full story in [`PROMPT.md`](PROMPT.md) section 1.

## What is validated, and what is not

| Layer | Basis | Status |
|---|---|---|
| Offshore wave height | Open-Meteo marine forecast | **Validated** -- MAE 0.091m, correlation 0.973 against 8,212 hours of DeepLev measurement ([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) |
| Alert threshold calibration | The same measured GO/DON'T-GO table | **Validated** -- real interpolated percentages, not invented ones |
| Beach exposure (shoreline geometry) | OSM coastline + directional trigonometry | **Heuristic** -- no ground truth at any beach, ever (`confidence.exposure: "unvalidated_heuristic"` on every response) |
| Obstruction (breakwaters/piers) | Coarse proximity ray-cast | **Heuristic** -- judgement-call thresholds |
| Surf quality (wind/period/chop) | Weighted rules, wind-dominant | **Heuristic** -- no training data exists to fit a model to |

This split is permanent, not a placeholder for "will validate later." No ground truth
exists at any Israeli beach and none is coming -- see Known limitations.

## Status: Phase 4 (alerting) complete

| Phase | Status |
|---|---|
| 0 -- data source verification | done, historical record ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)) |
| 0.5 -- DeepLev spike | done, historical record ([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) |
| 1 -- ingestion | done: forecast (wave + wind) + Hadera buoy, scheduled, idempotent, gap-backfilled |
| 2 -- beach exposure | done: shoreline bearing from OSM coastline, directional + obstruction scoring, beach ranking |
| 3 -- surf quality scoring | done: wind, period, chop ratio combined into an hour-by-hour verdict |
| **4 -- alerting** | **this build**: subscriptions, deduplication, calibrated threshold, Web Push |
| 5 -- frontend | not built -- the only phase left |

## What exists right now

**Phase 1 -- ingestion.** Scheduled (APScheduler, every `INGESTION_SCHEDULE_MINUTES`,
default 3h): wave height/period/direction + swell/wind-sea split from
`marine-api.open-meteo.com/v1/marine`; wind speed/direction/gusts from
`api.open-meteo.com/v1/forecast` (a *different* endpoint -- the marine API doesn't carry
10m wind); the Hadera buoy (ISRAMAR) hourly, the only buoy with an accessible feed (see
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md); IOLR's licence is unresolved, ingested for
personal/research use only). Idempotent upserts, gap detection + backfill for missed runs
(not deep history -- there is none to recover), graceful per-source degradation. `GET
/health`, `GET /beaches`, `GET /beaches/{id}/forecast`, `GET /buoys/{id}/measurements`.

**Phase 2 -- beach exposure** (`app/exposure/`). `shoreline_bearing` computed per beach
from OSM coastline geometry (`scripts/exposure/compute_bearings.py`) and written into
`data/beaches.yml`. Directional exposure (cosine of swell-vs-shoreline angle) plus a
coarse obstruction ray-cast against OSM breakwaters/piers/groynes. `GET
/beaches/{id}/exposure` and `GET /conditions` (**all beaches ranked for the same hour** --
the primary product surface: geometry can defensibly say Herzliya beats Bat Yam under a
given swell, not that Herzliya will be exactly 1.2m).

**Phase 3 -- surf quality scoring** (`app/quality/`). Height alone doesn't say whether a
session is worth having -- wind (the decisive factor, scored by angle to shoreline: offshore
grooms, onshore chops, light wind is glassy), period (thresholds sized for this coast's
short-fetch wind-swell, not a long-fetch ocean coast), and chop ratio (free from data
already ingested) combine into one hour-by-hour verdict. `GET /beaches/{id}/quality`.
Encodes the local pattern explicitly: the storm peak is often the worst hour, the following
dawn -- once the land breeze turns offshore -- is when it cleans up.

**Phase 4 -- alerting** (`app/alerting/`):

- `POST /subscriptions` -- beach, min/max height, preferred swell direction range
  (wraps correctly across 0/360), a daily local time window (Asia/Jerusalem, may cross
  midnight), an `operating_point`.
- **Deduplication** (`app/alerting/runner.py`, `material_change.py`): one alert per
  qualifying window per subscription. Never re-sent unless conditions change materially
  (height moves >=0.3m, the verdict label changes, or the window shifts >=1h); a
  cancellation when a previously-alerted window stops qualifying; contiguous qualifying
  hours cluster into one window, not one alert per hour.
- **Idempotent under concurrency**: a real Postgres row lock (`SELECT ... FOR UPDATE`) on
  the subscription serialises overlapping evaluations -- verified against two genuinely
  concurrent connections, not simulated (`tests/test_alerting_idempotency.py`).
- **Calibrated threshold** (`app/alerting/calibration.py`): does NOT correct the displayed
  height. Interpolates the real measured GO/DON'T-GO table
  (`docs/BIAS_ANALYSIS.md`) for the user's actual threshold to decide how far below it to
  also alert (`strict`/`balanced`/`generous`), and says so explicitly in the alert text
  when the calibrated fallback -- not the user's literal bar -- is what fired.
- **DST-safe**: `zoneinfo`, never a fixed UTC offset. Tested against Israel's real 2026
  transition dates (found by scanning zoneinfo, not guessed).
- **Web Push**: `pywebpush`, VAPID keys from env. 404/410 deactivates the subscription
  rather than retrying forever.
- `GET /subscriptions/{id}/status` -- a checkable "nothing qualifying" status, distinct
  from silence that looks like the system stopped working (`docs/BIAS_ANALYSIS.md`: only
  26% of hours reach 1m annually; September, 1.3%).

- 86 tests, no live network (every upstream mocked from a committed fixture; the geometry
  and alerting-concurrency tests run against real committed data / a real Postgres, not
  mocks).

## What is NOT built yet

A frontend. Every API response already carries `method`/`confidence` fields so no future
caller ever sees an unlabelled number.

## Running it

```
cp .env.example .env      # already done in this repo for local dev; real deploys should not commit .env
docker compose up -d
```

First boot runs Alembic migrations, seeds beaches/buoys from `data/beaches.yml`, then starts
serving. Ingestion and alert evaluation fire on the schedule; nothing blocks startup.

```
curl http://localhost:8000/health
curl http://localhost:8000/beaches
curl "http://localhost:8000/beaches/herzliya/forecast?hours=24"
curl "http://localhost:8000/beaches/herzliya/exposure?hours=24"
curl "http://localhost:8000/conditions"                          # all beaches ranked for the next hour
curl "http://localhost:8000/beaches/herzliya/quality?hours=24"   # size+period+wind+chop verdict, per hour

curl -X POST http://localhost:8000/subscriptions -H 'content-type: application/json' -d '{
  "user_id": "u1", "beach_id": "herzliya", "min_height": 1.0,
  "time_window_start": "06:00:00", "time_window_end": "09:00:00", "operating_point": "balanced"
}'
curl "http://localhost:8000/subscriptions/1/status"
```

Web Push needs real VAPID keys (`VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` in `.env`) to
actually deliver; without them, alerts are still computed and logged, just not delivered
(graceful degradation, hard rule 7).

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
- No ground truth exists at any actual Israeli beach. Beach exposure and quality scoring
  are geometry and local knowledge, not measurement, labelled as such in every API
  response, permanently, by design.
- Two beaches' shoreline bearings (`netanya`, `ashdod`) were computed from a thin
  coastline window and flagged in `data/beaches.yml` for manual review -- no visual map
  review was performed in this session (no map-viewing tool was available). Cross-checked
  for consistency against neighbouring beaches instead; see `docs/DECISIONS.md`.
- Obstruction detection thresholds, quality-verdict weights/caps, and material-change
  thresholds are all judgement calls with no ground truth to tune them against -- every
  one is named as a constant and defended in `docs/DECISIONS.md`.
- `issued_at` is the ingestion fetch time, not a real forecast-issue time -- neither
  upstream exposes one. Forecast-error-vs-lead-time is therefore still unmeasured; it only
  accrues from when ingestion started running.
- Push delivery failures other than 404/410 are logged, not queued for retry -- a real
  retry-with-backoff queue is future work.
