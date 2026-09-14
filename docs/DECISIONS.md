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


## 2026-09-14 -- Phase 2

### Seaward-normal ambiguity resolved by "closer to due west", not a general algorithm

`app/exposure/bearing.py` computes a tangent bearing across a windowed stretch of OSM
coastline, which gives two candidate normals 180 degrees apart -- one seaward, one
inland. Resolved by picking whichever candidate is closer to 270 degrees (west), because
the Israeli Mediterranean coast runs roughly north-south with the sea to the west for the
whole bounding box this project covers. This is a fact about this specific coastline, not
a general land/sea classifier -- ported to a coast of a different orientation, this
resolution rule would need to change (documented in the module itself, and asserted as a
sanity test in tests/test_exposure_geometry.py).

### Coastline window is 500m, not the single nearest OSM segment

Section 1 of the phase prompt warned that one OSM coastline segment can be up to ~40
degrees off the true local orientation. Walking +/-250m of arc length around the nearest
point and taking the tangent across that window absorbs most of that noise. 500m was not
tuned against anything -- it is a judgement call, documented as one. Two beaches
(`netanya`, `ashdod`) landed on a thin window (1-3 points contributing) and are flagged
with `shoreline_bearing_note` in `data/beaches.yml` for manual review; their values were
still cross-checked for consistency against neighbouring beaches' tangents before being
accepted (see the script's own output, captured in the Phase 2 commit message) -- no
visual map review was performed in this session, since no map-viewing tool was available.

### Obstruction: a real bug found via the Bat Yam vs Herzliya acceptance test

The first working version of `app/exposure/obstruction.py` sampled a ray from the beach
coordinate starting at 100m out. Herzliya's seeded coordinate sits ~93m from the marina
breakwater, so the very first sample was still close enough to trigger a "hit" for nearly
every swell direction -- obstruction stopped tracking direction at all and instead just
reflected "is this beach near any structure." Fixed with
`OBSTRUCTION_MIN_CHECK_DISTANCE_M = 300` -- samples closer than 300m to the beach itself
are skipped, since a structure that close is more likely something beside the access point
than a true offshore shadow-caster. `tests/test_exposure_obstruction.py::test_varies_by_direction_not_constant`
is a regression test for this specific failure mode.

`OBSTRUCTION_CHECK_RANGE_M` (1500m), `OBSTRUCTION_LATERAL_THRESHOLD_M` (150m), and
`OBSTRUCTION_STRENGTH` (a flat 0.4 reduction, not a modelled shadow angle) are all
judgement calls with no ground truth to tune them against -- this is exactly the kind of
heuristic hard rule 1 requires labelling, and it is labelled (`confidence.exposure:
"unvalidated_heuristic"` on every API response that uses it).

### Exposure range floor: never narrower than the measured offshore spread

`app/exposure/apply.py` widens the displayed range by a flat +/-0.25m
(`OFFSHORE_UNCERTAINTY_M`), taken directly from `docs/BIAS_ANALYSIS.md`'s measured 90%
error interval on the offshore forecast. Exposure is a multiplicative heuristic on top of
that already-uncertain number; the range must never imply more precision than the
validated layer itself has, so this floor is applied regardless of how confident the
exposure factor looks.

### `/conditions` ranking window: nearest hour, +/-30 minutes

The ranked-conditions endpoint (prompts/phase-2-exposure.md: "the primary product surface
is beaches ranked for the same hour") defaults to the next full hour and pulls each
beach's latest forecast within 30 minutes of it. Since forecasts are hourly, this is
generous enough to always find a match while still meaning "this hour," not "whenever we
last happened to have data." A beach with no forecast in that window is dropped from the
ranking rather than shown with a null height -- consistent with graceful degradation
(hard rule 7): a gap in one beach's data doesn't corrupt the ranking, it just narrows it.


## 2026-09-14 -- Phase 3

### Verdict combiner: weighted sum for ranking, capped by explicit rules for the label

`app/quality/verdict.py` computes a numeric `quality_score` from a weighted sum (wind 0.40,
size 0.25, chop 0.25, period 0.10 -- wind weighted highest per the phase prompt's own
framing of it as "the decisive quality factor"), then maps that score to a five-step
ladder (flat/poor/fair/good/excellent). Two hard caps sit on top of the numeric ladder:
onshore wind and choppy conditions each cap the verdict at "fair," regardless of how the
weighted arithmetic comes out. Verified this cap is not dead code: a hand-constructed case
with excellent size/period/chop and only borderline-onshore wind lands the weighted sum
exactly on the "good" threshold (0.60) and the cap pulls it back to "fair" --
see the test suite's boundary case. Both the weights and the cap threshold are judgement
calls with no ground truth to tune them against (hard rule 1); they are not fitted to
anything.

### Wind: angle drives the label, speed only gates "glassy" and the gust penalty

`app/quality/wind.py` scores wind purely on the angle between its arrival and the
shoreline normal once above `LIGHT_WIND_KMH` (8 km/h) -- a 12 km/h onshore breeze and a
35 km/h onshore gale score identically on the directional component, because the
underlying physics (chop building up the face) is about the direction the energy comes
from, not really an urgent function of magnitude beyond "enough to matter." Speed only
enters twice: below 8 km/h, direction is overridden to "glassy" (near-best regardless of
label); and a gust/mean spread of 15 km/h or more applies a flat 0.8 multiplicative
penalty. Both thresholds are judgement calls.

### Size bands reuse BIAS_ANALYSIS.md's regime boundaries, with one deliberate deviation

`app/quality/size.py` reuses the 0.5/1.0/1.5/2.5m boundaries from
`docs/BIAS_ANALYSIS.md`'s own MAE-by-regime table, so "rideable" means the same thing here
it meant there. The one addition -- a `flat` cutoff at 0.3m rather than that document's own
0.5m "flat" bucket boundary -- reflects that BIAS_ANALYSIS's own 0.5m bucket had a median
around 0.3m within it, i.e. most of that bucket genuinely was closer to flat than to
surfable; 0.3m is this project's own judgement call, not measured.

### Period thresholds are a local judgement call, not imported from elsewhere

6s/8s for weak/workable/good. The phase prompt explicitly warned against importing
thresholds tuned for a long-fetch ocean coast; these were chosen to match the short-fetch
character of Eastern Mediterranean wind-swell, which DeepLev's own period data
(docs/BIAS_ANALYSIS.md) supports as the right order of magnitude, but they are not fitted
to anything -- there is no surf-quality ground truth to fit them to. Bands are 2s wide,
comfortably wider than the ~0.97s period MAE measured against DeepLev, so they do not
imply resolution the forecast does not have.

### `/beaches/{id}/quality` is hour-by-hour by construction, not aggregated

There is no daily rollup anywhere in the quality pipeline. Each hour's Forecast row is
scored independently against that hour's own wind, so a stormy afternoon's big number
cannot leak into the following dawn's verdict -- this is the entire point of the phase
(section 2, "the local pattern"), enforced structurally rather than by discipline.
