# Surf Alert System

A backend + Hebrew/RTL web app that watches the surf for a handful of Israeli beaches and
tells you, in plain language, when a session is actually worth driving to -- ranked against
your other beaches, scored 0-10 for quality (not just size), with push and email alerts.

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
| Surf quality score (0-10) | Weighted sum + two explicit ceiling curves, wind-dominant | **Heuristic**, deliberately not a fitted model -- no training data exists to fit one to |
| Body-reference / board recommendation / weather | Derived display fields from the same forecast data | **Heuristic** -- presentation only, not a separate model |

This split is permanent, not a placeholder for "will validate later." No ground truth
exists at any Israeli beach and none is coming -- see Known limitations.

## Status: complete -- 5 backend phases + a full Hebrew/RTL frontend rebuild

| Phase | Status |
|---|---|
| 0 -- data source verification | done, historical record ([`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md)) |
| 0.5 -- DeepLev spike | done, historical record ([`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md)) |
| 1 -- ingestion | done: forecast (wave + wind + weather) + Hadera buoy, scheduled, idempotent, gap-backfilled |
| 2 -- beach exposure | done: shoreline bearing from OSM coastline, directional + obstruction scoring, beach ranking |
| 3 -- surf quality scoring | done: 0-10 score, wind/size ceiling curves, period, chop combined into an hour-by-hour verdict |
| 4 -- alerting | done: standing subscriptions + per-slot watches, deduplication, calibrated threshold, Web Push **and email** |
| 5 -- frontend | done, then substantially rebuilt: Hebrew/RTL drill-down UI (beach list -> week -> day), wave-height/score chart, humor summaries |

This closes the build. What follows is the end-to-end picture of the finished system.

## What exists right now

**Phase 1 -- ingestion.** Scheduled (APScheduler, every `INGESTION_SCHEDULE_MINUTES`,
default 3h): wave height/period/direction + swell/wind-sea split from
`marine-api.open-meteo.com/v1/marine`; wind speed/direction/gusts + temperature + WMO
weather code from `api.open-meteo.com/v1/forecast` (a *different* endpoint -- the marine API
doesn't carry 10m wind); the Hadera buoy (ISRAMAR) hourly, the only buoy with an accessible
feed (see [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md); IOLR's licence is unresolved,
ingested for personal/research use only). Idempotent upserts, gap detection + backfill for
missed runs (not deep history -- there is none to recover), graceful per-source degradation.
`GET /health`, `GET /beaches`, `GET /beaches/{id}/forecast`, `GET /buoys/{id}/measurements`.

**Phase 2 -- beach exposure** (`app/exposure/`). `shoreline_bearing` computed per beach
from OSM coastline geometry (`scripts/exposure/compute_bearings.py`) and written into
`data/beaches.yml`. Directional exposure (cosine of swell-vs-shoreline angle) plus a
coarse obstruction ray-cast against OSM breakwaters/piers/groynes. `GET
/beaches/{id}/exposure` and `GET /conditions` (**all beaches ranked for the same hour** --
the primary product surface: geometry can defensibly say Herzliya beats Bat Yam under a
given swell, not that Herzliya will be exactly 1.2m).

**Phase 3 -- surf quality scoring, 0-10** (`app/quality/`). Height alone doesn't say
whether a session is worth having. A weighted sum (wind 0.40 / size 0.25 / chop 0.25 /
period 0.10, `app/quality/verdict.py`) produces a raw score, which is then clamped by two
**explicit ceiling curves** applied to the number itself, not just the verdict word (ranking,
alert clustering and best-hour selection all sort on the raw number, so a word-only cap would
still let a flat day win a ranking):

- **Size ceiling**, keyed on the *displayed* surf height (0.8 x Hs, not the raw offshore
  measurement) -- a small day cannot read as a top score no matter how clean everything else
  is. Piecewise-linear, anchored at the user's own real-world calibration point: **1.0 m with
  light wind reads 7.0**, not a flat step-bucket value -- nearby hours read 6.8, 7.2, etc.
  rather than all repeating the same number.
- **Wind ceiling**, keyed on direction-relative-to-shore + raw speed: onshore/cross-shore
  caps hard as it strengthens (it wrecks the wave face); offshore is left mostly alone until
  it gets strong enough to hold the face up too much. Gusty conditions subtract a further
  penalty from whichever ceiling applied.

On top of the ceilings, two word-only caps still apply (onshore wind and choppy conditions
each cap the verdict at "fair" regardless of the number) and the reasoning sentence names
whichever ceiling or cap actually bound the result. Encodes the local pattern explicitly: the
storm peak is often the worst hour, the following dawn -- once the land breeze turns offshore
-- is when it cleans up. `GET /beaches/{id}/quality` also returns three derived,
**display-only** fields built from the same data (never a second scoring pass): a 5-band
body-reference size (קרסול/ברך/מותן/כתף/ראש), a board recommendation (שורט/לונגבורד/סופט),
and a weather icon + Hebrew label from the WMO code already in the forecast row.

**Phase 4 -- alerting** (`app/alerting/`). Two independent tools, not one:

- **Standing subscriptions** (`POST /subscriptions`) -- beach, min/max height, preferred
  swell direction range (wraps correctly across 0/360), a daily local time window (Asia/
  Jerusalem, may cross midnight), an `operating_point`.
- **Per-slot watches** (`POST /slot-watches`) -- tap a specific hour in the day view and get
  alerted the moment *that hour* crosses a qualifying score, evaluated only once it's within
  the near-term forecast window (forecasts move too fast to trust further out); a
  cancellation push if a previously-alerted slot later falls back below the bar.
- **Deduplication** (`app/alerting/runner.py`, `material_change.py`): one alert per
  qualifying window per subscription. Never re-sent unless conditions change materially
  (height moves >=0.3m, the verdict label changes, or the window shifts >=1h); contiguous
  qualifying hours cluster into one window, not one alert per hour.
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
- **Two independent delivery channels**, both opt-in and both degrading gracefully when
  unconfigured (hard rule 7 -- one channel being down/unset never blocks the other):
  - **Web Push** (`pywebpush`, VAPID keys from env). 404/410 deactivates the subscription
    rather than retrying forever.
  - **Email** (`app/alerting/email.py`, stdlib `smtplib` + STARTTLS, Gmail-app-password
    convention). Per-subscription and per-slot-watch, not a global setting; logs a warning
    and returns `False` instead of raising when SMTP credentials are blank.
- `GET /subscriptions/{id}/status` -- a checkable "nothing qualifying" status, distinct
  from silence that looks like the system stopped working (`docs/BIAS_ANALYSIS.md`: only
  26% of hours reach 1m annually; September, 1.3%).
- 115 backend tests, no live network (every upstream mocked from a committed fixture; the
  geometry, alerting-concurrency and email tests run against real committed data / a real
  Postgres, not mocks).

**Phase 5 -- frontend** (`web/`), React + Vite (two runtime dependencies, deliberately:
`react` and `react-dom` -- no router, no charting library, no i18n framework), served as its
own nginx container so the existing API routes never had to move. Presentation only -- no
scoring, matching or business logic lives here; every number shown is exactly what an
existing Phase 1-4 endpoint already returned (`docs/DECISIONS.md`).

Hebrew, RTL, single language throughout (`lang="he" dir="rtl"`) -- no translation files or
toggle. Navigation is hand-rolled in `App.jsx` as `{view, beachId, date}` state, not a router:

- **Beach list** (`views/BeachList.jsx`) -- the primary view. For each beach, takes the
  current hour's already-computed `quality_score` from `GET /beaches/{id}/quality` and sorts
  beaches by it (a display sort, not new scoring). Score, height range, wind and verdict per
  beach, one clickable row each.
- **Beach week** (`views/BeachWeek.jsx`) -- a centred wave-hero banner (beach name + date
  inside a blue banner with a wave-shaped bottom edge, `components/WaveHero.jsx`), then a
  7-day wave-height/score chart (`components/WaveChart.jsx`, dependency-free inline SVG:
  height and score share one x-axis, the height line dark blue, the axis domain padded above
  the real data max so the peak point and its label never sit at the chart's literal top
  edge, and the x-axis manually mirrored since SVG coordinate space doesn't auto-flip under
  `dir="rtl"` the way flex/grid does), then one row per day.
- **Beach day** (`views/BeachDay.jsx`) -- one date, 3-hour intervals, a 9-column table (hour,
  wave-height range, score, body-reference, board recommendation, swell height, period, wind
  speed, wind direction), a "watch this hour" toggle per row, and a short humor sentence
  above the table (`daySummary.js`) covering morning/noon/evening -- collapsed to a single
  sentence when all three periods agree, and naming the day's peak hour only when it's
  actually worth reporting (score >= 6.0).
- **Subscription form** (`views/SubscriptionForm.jsx`) -- beach, min/max height, time window,
  operating point (with the strict/balanced/generous trade-off explained), optional email,
  posts to `POST /subscriptions`; lists and can deactivate standing subscriptions and
  cancel per-slot watches.
- **One honesty-marker convention everywhere**: derived/estimated values (size, score, body
  reference, board recommendation) are always labelled as estimates in the summary text next
  to them; wind, swell, period, temperature and weather come straight from the forecast
  model and are not separately badged. A range is always shown as a range, never a bare
  decimal.
- `<Num>` (`labels.jsx`) bidi-isolates only genuinely ambiguous fragments -- a value+dash+value
  range like "40-70" -- not plain "value + Hebrew unit" pairs, which read correctly in normal
  RTL flow on their own and previously broke when force-wrapped.
- Verified against the real running API, not just code review:
  `web/scripts/verify_ranking.mjs` (imports the actual `dateUtils.js` the component uses)
  and `web/scripts/verify_subscription.mjs` reproduce the ranked list and the
  create-and-confirm subscription flow against live data.

## Running it

```
cp .env.example .env      # already done in this repo for local dev; real deploys should not commit .env
docker compose up -d
```

First boot runs Alembic migrations, seeds beaches/buoys from `data/beaches.yml`, builds and
serves the frontend, and starts the API. Ingestion and alert evaluation fire on the
schedule; nothing blocks startup.

- Frontend: **http://localhost:3000**
- API: **http://localhost:8000**

```
curl http://localhost:8000/health
curl http://localhost:8000/beaches
curl "http://localhost:8000/beaches/herzliya/forecast?hours=24"
curl "http://localhost:8000/beaches/herzliya/exposure?hours=24"
curl "http://localhost:8000/conditions"                          # all beaches ranked for the next hour
curl "http://localhost:8000/beaches/herzliya/quality?hours=24"   # 0-10 score + size/period/wind/chop verdict, per hour

curl -X POST http://localhost:8000/subscriptions -H 'content-type: application/json' -d '{
  "user_id": "u1", "beach_id": "herzliya", "min_height": 1.0,
  "time_window_start": "06:00:00", "time_window_end": "09:00:00", "operating_point": "balanced"
}'
curl "http://localhost:8000/subscriptions/1/status"

curl -X POST http://localhost:8000/slot-watches -H 'content-type: application/json' -d '{
  "user_id": "u1", "beach_id": "herzliya", "valid_at": "2026-09-23T06:00:00Z"
}'
```

Web Push needs real VAPID keys (`VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` in `.env`) to
actually deliver; without them, alerts are still computed and logged, just not delivered
(graceful degradation, hard rule 7). Generate a real pair with:

```
docker compose exec api python scripts/alerting/generate_vapid_keys.py
```

It round-trips the key through pywebpush's own loader before printing anything, and the
generated format has been confirmed to reach a real push service (a live request against
`fcm.googleapis.com` with a fake subscription returned a genuine `410 Gone`, not a
key-format error -- see `docs/DECISIONS.md`).

Email alerts need `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM` in `.env`
(a Gmail address + an [app password](https://myaccount.google.com/apppasswords), not the
account password, is the expected setup). Without them, email delivery is skipped and logged
the same way push is when VAPID is unset -- an unconfigured channel never blocks the other
one. Email is opt-in per subscription/watch (an email field in the form, not a global
setting), never required.

Backend tests (needs Postgres + Redis reachable -- `docker compose up -d postgres redis`
then run outside the container, or `docker compose run --rm api pytest`):

```
docker compose run --rm api pytest -v
```

Frontend build check (no browser test suite -- `npm run build` catches syntax/import
errors; behaviour is verified against the live API by the scripts in `web/scripts/`):

```
cd web && npm install && npm run build
```

## Known limitations

- Offshore forecast accuracy is validated at exactly one point (DeepLev, 50 km off Haifa,
  data through March 2024). Applying it elsewhere on the coast, or trusting it against
  today's model behaviour, is an assumption -- see
  [`docs/BIAS_ANALYSIS.md`](docs/BIAS_ANALYSIS.md) limitations.
- No ground truth exists at any actual Israeli beach. Beach exposure and quality scoring
  are geometry and local knowledge, not measurement, labelled as such in every API
  response and in the frontend's honesty note, permanently, by design.
- Two beaches' shoreline bearings (`netanya`, `ashdod`) originally read "thin window, low
  confidence" -- revisited via OSM's own way history (no map-viewing tool was available,
  but the OSM edit history was): both rest on legitimate, actively-maintained coastline
  ways that happen to be one long straight ~2-2.4km segment at that point, not sparse
  data. The bearing values were not wrong; the diagnostic mischaracterised them, and a real
  bug in that diagnostic (capping the reported segment length at the window's own budget)
  was found and fixed while correcting it. See `docs/DECISIONS.md` for the full story.
  Genuine, narrower caveat that remains: this method cannot see coastline curvature that
  falls between two OSM vertices, which for these two beaches spans ~2-2.4km.
- Obstruction detection thresholds, the quality-score weights and both ceiling curves, and
  material-change thresholds are all judgement calls with no ground truth to tune them
  against -- every one is named as a constant and defended in `docs/DECISIONS.md`. The size
  ceiling's one grounded anchor is the user's own stated calibration point (1.0 m + light
  wind = 7.0); everything else on both curves is interpolated around it, not separately
  measured.
- `issued_at` is the ingestion fetch time, not a real forecast-issue time -- neither
  upstream exposes one. Forecast-error-vs-lead-time is therefore still unmeasured; it only
  accrues from when ingestion started running.
- Push delivery failures other than 404/410 are logged, not queued for retry -- a real
  retry-with-backoff queue is future work. Email delivery failures (SMTP errors after
  credentials are configured) are likewise logged, not retried.
- The frontend has no browser-based automated test suite. Verified instead by: a clean
  production build with no errors, the served container returning real built HTML/JS,
  the two live-API scripts in `web/scripts/`, and manual browser verification of the
  drill-down navigation, chart and RTL layout during this project's later sessions.
- Body-reference bands, board recommendations and the humor day-summary sentences are all
  presentation-layer heuristics with no independent validation beyond "reads correctly in
  Hebrew" -- they are explicitly derived from already-validated-or-labelled numbers, not a
  new source of truth.

## More detail

[`docs/DECISIONS.md`](docs/DECISIONS.md) is a dated, append-only log of every non-obvious
judgement call and bug fix across the whole build -- the weight/ceiling constants, the RTL
and bidi-isolation fixes, the scoring recalibration story, why per-slot watches are a
separate table from standing subscriptions, why email is opt-in per-subscription rather than
a global setting, and more. This README is the current-state summary; `docs/DECISIONS.md` is
the "why," in the order it actually happened.
