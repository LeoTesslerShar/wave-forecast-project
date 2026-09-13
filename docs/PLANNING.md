# Surf Alert System: Calibrated Wave Forecasting for Israeli Beaches

> Planning document. Intended as context for Claude Code at the start of the project.
> Read fully before writing any code. Several items marked VERIFY must be resolved first.

---

## 1. What this is

A backend system that continuously ingests marine forecast data and real measured
buoy data, corrects the forecast against measurement history, adjusts the result per
specific beach, and pushes an alert when a surf window matching the user's criteria
opens up.

The alert is the visible surface. The value is in the three processing stages behind it.

**This is a backend/systems project, not a data science notebook.** The calibration
model is one module inside a continuously running service. Every architectural decision
should favour "a system that runs and does something" over "an analysis that was run once".

---

## 2. The problem being solved

Every surf app shows the same raw output from the same global wave models. Two known gaps:

1. **Model vs reality.** Global wave models carry systematic bias. The forecast says
   1.5m, the actual measured height is 1.1m. The bias is not random: it tends to depend
   on swell direction, season, and wave height regime.

2. **Regional vs local.** A forecast is issued for a region, but each beach responds
   differently to the same swell depending on the angle its shoreline faces relative to
   the incoming swell direction, plus obstruction from jetties, breakwaters and marinas.
   Real observed example: same swell, mediocre conditions at Bat Yam, excellent at
   Herzliya.

No existing app corrects for either.

---

## 3. Core value chain

Each stage is independently useful and should be built in order.

```
  raw model forecast
        |
        v
  [1] bias correction     <- trained against measured buoy history
        |
        v
  [2] per-beach exposure  <- shoreline bearing vs swell direction, geometric
        |
        v
  [3] user criteria match <- beach, min height, preferred swell direction, time of day
        |
        v
      alert
```

Stage 1 is data-driven and validated. Stage 2 is a geometric heuristic and is NOT
validated. This distinction must be explicit in the code, in the UI, and in any
documentation. Do not present stage 2 output with false precision.

---

## 4. Data sources

### 4.1 Measured wave data (ground truth)

| Source | Location | Active since | Parameters |
|---|---|---|---|
| CAMERI | Ashdod buoy | 1992 | Hmax, Tp, wave direction |
| CAMERI | Haifa buoy | 1993 | Hmax, Tp, wave direction |
| ISRAMAR | Hadera buoy | n/a | wave height, period |

- CAMERI exposes an interface called **ADVA** that allows selecting a buoy, viewing
  near-real-time measurements, and filtering by date range and parameters.
  **VERIFY:** does ADVA support bulk export of historical data, and in what format?
  If it only supports UI viewing, historical training data may be limited to what can
  be exported manually.
- ISRAMAR (Israel Marine Data Center, part of IOLR) hosts the Hadera buoy data. Hadera
  measurement is taken at the Hadera power station, offshore in deep water.
  **VERIFY:** exact offshore distance and depth.
- **Useful reference:** the public GitHub project `Yuvartz/yam-palta` fetches the Hadera
  buoy from ISRAMAR hourly into JSON via a Node script (`scripts/fetch-buoy.mjs`).
  This confirms the data is programmatically accessible rather than image-only.
  Read that script before writing our own fetcher.

**Important limitation, to be stated openly:** there are only three measurement buoys,
all in deep water well offshore. There are no measurement buoys at the beaches
themselves (buoys visible from shore are swimming-boundary markers, not instruments).
Deep-water significant wave height is not the same as what a surfer sees at the break.
This means stage 1 calibration is regional, not per-beach.

### 4.2 Forecast data

- Open-Meteo Marine API: free, no API key, hourly wave height, wave direction, wave
  period, swell components, per coordinate.
- **VERIFY:** how far back the historical archive extends for the Eastern Mediterranean.
  This directly determines training set size. If the archive is short, reduce the
  ambition of stage 1 accordingly rather than overstating results.

### 4.3 Shoreline geometry

- OpenStreetMap coastline data (GeoJSON) to compute the bearing each beach faces,
  meaning the normal to the local shoreline segment.
- Manual coordinates for an initial set of 8 to 12 known Israeli surf spots
  (Bat Yam, Herzliya, Palmachim, Netanya, Ashdod, Hadera, Olga, Tel Aviv, and others).

### 4.4 Prior art to review before starting

`Yuvartz/yam-palta` already does something adjacent: it runs an ensemble of marine
models (MFWAM, ECMWF-WAM) and atmospheric models (ECMWF-IFS, ICON), takes the median,
uses inter-model disagreement as a confidence signal, and displays the Hadera buoy
measurement as a "reality anchor" against the forecast. It targets flat-sea conditions
for swimming, not surf, and it displays the buoy alongside the forecast rather than
using it to train a correction. Our angle differs, but read it first.

---

## 5. Architecture

### Stack

- **Language/runtime:** Python (FastAPI) for the API and pipeline. Consistent with
  existing experience.
- **Storage:** PostgreSQL. Time-series tables for forecasts and measurements.
  Consider TimescaleDB only if genuinely needed, not by default.
- **Scheduling:** a scheduled ingestion job. APScheduler inside the app for simplicity,
  or a separate worker if the workload justifies it. Decide explicitly and record why.
- **Caching:** Redis for served forecast responses.
- **Notifications:** Web Push (VAPID). No app store dependency, works on mobile browsers.
- **Frontend:** React. Minimal. A beach list, current calibrated conditions, and a
  subscription form. The frontend is not the point of this project.
- **Deployment:** Docker Compose. Target a free tier host.
- **CI:** GitHub Actions running tests on push.

### Data model sketch

```
buoys            (id, name, lat, lon, source, active_from)
beaches          (id, name, lat, lon, shoreline_bearing, obstruction_notes)
measurements     (buoy_id, observed_at, wave_height, peak_period, wave_direction)
forecasts        (beach_id | grid_point, issued_at, valid_at, wave_height,
                  wave_direction, wave_period, swell_height, swell_direction, wind_*)
subscriptions    (id, user_id, beach_id, min_height, max_height,
                  preferred_swell_dir_range, time_window, active)
alerts_sent      (subscription_id, valid_at, sent_at, conditions_snapshot)
```

Note the distinction between `issued_at` and `valid_at` on forecasts. The same target
hour gets re-forecast repeatedly. Storing both is what makes bias analysis possible and
what makes alert deduplication tractable. Do not collapse them.

---

## 6. Build order

### Phase 1: Ingestion pipeline

The foundation. Everything else depends on it.

- Scheduled fetch of Open-Meteo forecasts for all configured beach coordinates.
- Scheduled fetch of buoy measurements from ISRAMAR (and CAMERI if exportable).
- Retry with backoff on upstream failure.
- Backfill: on startup, detect gaps in the local record and fill them.
- Idempotent writes: re-running ingestion for the same window must not duplicate rows.
- Structured logging of every ingestion run.

### Phase 2: Historical alignment and gap analysis

- Join stored forecasts to measurements on `valid_at` and nearest buoy.
- Produce a dataset of (predicted, actual) pairs.
- Characterise where the model is systematically wrong: by swell direction bucket, by
  season, by height regime, by forecast lead time.
- Output: a small set of charts plus a written summary. This stands alone as a result
  even if phase 3 is never built.

### Phase 3: Calibration model

- Features: forecast wave height, period, direction, wind speed and direction, lead time,
  month, buoy id.
- Target: measured wave height (and optionally period).
- Model: start with linear regression as a baseline, then gradient boosting.
- **Validation must be chronological**, meaning train on earlier data and test on later
  data. A random train/test split on time series data leaks information and produces a
  meaningless score. This matters.
- Baseline to beat: the raw uncorrected forecast. Report MAE and RMSE against it.
- If the improvement over baseline is small, report that honestly. A negative result,
  clearly measured, is a legitimate outcome and a better interview story than an
  inflated one.

### Phase 4: Per-beach exposure layer

- Compute shoreline bearing per beach from OSM coastline geometry.
- Score = f(angular difference between swell direction and shoreline normal), reduced
  by obstruction.
- Obstruction: ray cast from the beach point toward the swell source and check for
  intersection with nearby coastline or structures.
- This layer is a heuristic. Label it as such in the API response, for example by
  returning a `confidence` or `method` field distinguishing calibrated from heuristic.

### Phase 5: Alerting

- Subscription CRUD.
- Evaluation job: on each forecast refresh, re-evaluate open subscriptions against the
  updated calibrated forecast.
- **Deduplication is the hard part.** Forecasts refresh every few hours. The same
  Tuesday morning window will match repeatedly. Rules to implement:
  - do not re-send for a `valid_at` window already alerted on
  - unless conditions changed materially (define the threshold explicitly)
  - and do send a cancellation if a previously alerted window no longer qualifies
- Timezone correctness. Store UTC, evaluate user time windows in local time.
- Web Push delivery with subscription expiry handling.

---

## 7. Engineering problems worth solving properly

These are the parts that carry the project. Do not paper over them.

- **Idempotency** in both ingestion and alert delivery.
- **Backfill and gap detection** when an upstream source is down for hours.
- **Forecast versioning**: same `valid_at`, many `issued_at`. Query patterns need to
  handle "latest forecast for this hour" efficiently.
- **Alert deduplication and material-change detection.**
- **Chronological validation** of the calibration model.
- **Graceful degradation**: if the buoy feed is down, the system should still serve raw
  forecasts and say so, rather than failing.

---

## 8. Explicitly out of scope

- User-submitted surf ratings. Rejected deliberately: it creates a cold start problem
  with no data to show and no way to validate. Ground truth comes from buoys instead.
- Tide modelling. Mediterranean tidal range is negligible for this purpose.
- Native mobile apps. Web Push covers the need.
- Any scraping of commercial surf forecast sites.
- Multi-user accounts with full auth in phase 1. A simple identifier is enough until
  the core works.

---

## 9. Open questions, resolve before phase 1

1. Does CAMERI ADVA allow programmatic or bulk historical export? What format?
2. How far back does the Open-Meteo Marine historical archive go for the Eastern Med?
3. Does ISRAMAR expose the Hadera buoy through a documented endpoint, or does
   `yam-palta` rely on an undocumented one? If undocumented, how stable is it?
4. What is the actual measurement depth and offshore distance of each buoy?
5. Is there any licensing or attribution requirement on IOLR/ISRAMAR data? IOLR
   publishes attribution requirements for some of its datasets, so check before
   redistributing anything.

Answer these first. If question 1 and question 2 both come back badly, phase 3 shrinks
significantly and the project should be re-scoped around phases 1, 4 and 5 rather than
pretending the calibration is better supported than it is.

---

## 10. Non-negotiables

- Never present heuristic output as validated output.
- Report model performance against the raw-forecast baseline, whatever the number is.
- No scraping of sources that prohibit it.
- No credentials, session cookies, or API keys committed to the repository.
