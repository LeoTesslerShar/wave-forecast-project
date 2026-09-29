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


## 2026-09-14 -- Phase 4

### The GO/DON'T-GO table was in chat but not in the repo -- fixed before building on it

Discovered while starting the calibrated-threshold work: the GO/DON'T-GO table quoted in
the Phase 0.5 conversation (missed-session and wasted-trip percentages at five height
thresholds) was never actually committed to `docs/BIAS_ANALYSIS.md` -- only shown in chat.
Building the calibration module on an uncommitted number would have violated hard rule 5
(every claim backed by evidence in the repo). Re-ran
`scripts/deeplev/decision_quality.py`, confirmed the numbers reproduce exactly, and added
the table to `docs/BIAS_ANALYSIS.md` itself before writing `app/alerting/calibration.py`
against it.

### Calibrated threshold: real interpolation, not one invented global percentage

The phase prompt's own example ("generous: catches roughly 13% more real sessions") is
illustrative language, not a number to hardcode. `app/alerting/calibration.py` instead
interpolates the actual 5-point measured table for whatever threshold a given
subscription sets, so a 1.5m bar and a 0.8m bar get their own honestly-computed figures
rather than one number applied everywhere. Interpolation is linear and clamped at the
table's own ends (0.6-1.5m) -- no extrapolation beyond what was actually measured.

Operating-point offsets themselves (`strict`=0, `balanced`=0.15m, `generous`=0.25m) are
still a judgement call: roughly half and the full width of the offshore forecast's own
measured 90% spread (docs/BIAS_ANALYSIS.md). What is NOT invented is the resulting
caught/wasted percentages shown to the user -- those come from the table.

### Subscription identity: (subscription_id, target_date), not exact window boundaries

A subscription's daily time window (e.g. 06:00-09:00 local) is the anchor for "the same
window" across repeated evaluations, not the exact qualifying-hour boundaries, which can
legitimately shift run to run. This is also *why* window-shift is one of the material-
change triggers (section 3, rule 2) rather than an identity check -- if exact boundaries
were the identity key, a window narrowing from 06:00-09:00 to 07:00-09:00 would look like
a brand new window and re-alert as "initial", rather than being recognised as the same
window with different content.

### Idempotency: a real row lock, not a dedup table or a Redis lock

`evaluate_subscription_for_date` takes `SELECT ... FOR UPDATE` on the Subscription row for
the whole decide-and-maybe-send sequence. Two concurrent evaluations of the same
subscription serialise on Postgres itself; the loser re-reads the freshly committed
AlertSent row and finds nothing material to add. Verified against a real Postgres with two
genuinely concurrent connections (tests/test_alerting_idempotency.py), not simulated.
Chosen over a Redis-based lock or a separate `evaluation_locks` table because the
serialisation only ever needs to matter within the scope of one subscription's own rows,
which a row lock on that exact row provides for free.

### Best-cluster selection: highest average quality score, not longest

When a subscription's window contains more than one separate contiguous qualifying stretch
(a gap in the middle), `app/alerting/matching.py::best_cluster` picks the one with the
higher average `quality_score`, breaking ties by hour count. A short, clean 2-hour dawn
window beats a longer but choppier 4-hour stretch -- judged worth alerting on the better
session, not the longer one. Judgement call, no ground truth to tune it against.

### Push delivery failures are logged, not queued for retry

`send_push` returns `sent | expired | failed`; on `expired` (404/410) the subscription is
deactivated (acceptance check 4). On `failed` (any other error), the failure is logged and
the AlertSent row still gets written -- the DECISION to alert is recorded once per material
change regardless of whether delivery to any specific device succeeded, so a transient push
failure does not cause the subscription to be silently re-evaluated as "not yet alerted"
and spam-retried on the next scheduled cycle. A real retry-with-backoff queue for
transient push failures is future work, out of scope for this phase.


## 2026-09-14 -- Phase 5

### Served as its own container, not mounted into the API

The frontend is a separate `web` service (nginx serving a static Vite build) on its own
port, rather than FastAPI serving static files at `/`. The alternative would have meant
prefixing every existing API route under `/api/*` -- a breaking change to paths already
documented, tested (86 backend tests), and used throughout Phases 1-4. Two services plus
CORS (`app/main.py`) is a few lines; renaming every route is not "thin." CORS itself is
ordinary cross-origin wiring for a separately-served frontend, not the "new backend logic"
prompts/phase-5-ui.md section 3 warns against -- that clause is about scoring/matching
rules, not deployment plumbing.

### Ranking is a client-side SORT of an already-computed field, not client-side scoring

The phase prompt says the ranked beach list should show "quality verdict... sorted
best-to-worst," but no existing endpoint ranks beaches by `quality_score` specifically --
`GET /conditions` (Phase 2) ranks by exposure height only. Rather than add a new ranking
endpoint in this "presentation only" phase, `RankedBeachList.jsx` fetches each beach's
already-computed quality (`GET /beaches/{id}/quality`, Phase 3) and sorts the results by
the `quality_score` field the backend already produced. This is display logic (the same
category as sorting a table by a column), not new business logic -- nothing about wind,
chop, exposure or the verdict itself is recomputed in the browser. Verified end-to-end
against the live API with `web/scripts/verify_ranking.mjs`, which imports the real
`dateUtils.js` the component uses, not a reimplementation.

### "Best hour of the day" picked by max quality_score, for the same reason

For "ranked for a chosen day," each beach's card represents its single best hour that
local calendar day (Asia/Jerusalem) -- `dateUtils.js::bestHourForDate` takes the max of an
already-computed field, mirroring `app/alerting/matching.py::best_cluster`'s own choice in
Phase 4 (highest score, not first or longest). Consistent with how the backend already
treats "the best opportunity in a window," not a new heuristic.

### One consistent honesty-marker convention across all three views

`components/Badges.jsx` is the ONLY place that decides whether a confidence string counts
as "estimate" or "measured" (`confidence.includes("unvalidated")`). Every view imports it
rather than reimplementing the check -- found and fixed one accidental duplicate
(`ConfidenceBadgeInline`) in `RankedBeachList.jsx` during review before it could drift out
of sync with the real component.

### Accepted: Vite's esbuild dev-server advisory, not upgraded to Vite 6/7

`npm audit` flags a moderate/high advisory in esbuild (any website can send requests to a
running `vite dev` server and read the response) that persists across the entire Vite
5.x/6.x line -- fixed only in a breaking major version. This project's `vite dev` is a
local development convenience, never the production path (nginx serves a static build in
the shipped container), and a major-version jump was judged not worth it for a "thin"
phase. Bumped to the latest 5.4.x patch first to confirm it wasn't already fixed there.


## 2026-09-14 -- Post-Phase-5 follow-up

### VAPID key generation script, verified against a real push service

Phase 4 shipped `app/alerting/push.py` and `.env.example`'s key names, but left "generate
real VAPID keys" as a manual step with no tooling -- a real gap for anyone actually trying
to run this. Added `scripts/alerting/generate_vapid_keys.py`, which:

- generates a real P-256 keypair (`cryptography`, already a transitive dependency of
  `pywebpush` via `py-vapid` -- no new pin needed);
- round-trips the private key through `pywebpush`'s own `Vapid02.from_string` before
  printing anything, so a key this script prints is guaranteed parseable by
  `app/alerting/push.py`'s actual loading path (`webpush(vapid_private_key=<string>)`,
  which calls the same loader);
- was further confirmed by sending one real `webpush()` call, with a generated key, to a
  fake subscription endpoint at `https://fcm.googleapis.com/fcm/send/...` -- it returned a
  genuine `410 Gone` from Google's real infrastructure, not a key-format rejection,
  proving the generated key format is actually accepted by a live push service, not just
  locally self-consistent.

Never writes keys to a file or prints them anywhere but stdout, for the user to paste into
their own `.env` -- consistent with hard rule 4.


## 2026-09-14 -- Correction to the Phase 2 "thin window" flag

The Phase 2 entry above ("Coastline window is 500m...") flagged Netanya and Ashdod as
"thin window (1-3 points contributing)" and called that low confidence, deferring to a
future visual map review that never happened (no map tool was available in any session).
Revisited without a map tool, but with two things that WERE available: OSM's own way
history, and a closer look at what "few points in the window" actually meant.

**What was actually going on, verified via `https://www.openstreetmap.org/way/<id>`:**
both beaches' bearings rest on legitimate, actively-maintained `natural=coastline` ways
(way 95912704 near Netanya: 99 nodes, 21 edit versions, last touched 11 months ago; way
386066841 near Ashdod: actively maintained, source-tagged, survived a vandalism revert).
Neither is sparse or placeholder data. What actually happened: at both points, the nearest
OSM segment is a single, deliberately-digitised straight run roughly 2-3km long -- so the
+/-250m window never reaches a second vertex in one or both directions, and
`window_points_used` reads as low (1) even though the underlying data is fine. A long
straight segment is not weaker evidence than several short jittery ones; if anything it is
a cleaner tangent. Confirmed the bearing value itself did not need correcting -- an
independent visual/analytical check (OSM history) found no error, only a mischaracterised
diagnostic.

**What was a real bug, found while fixing the diagnostic:** the original
`max_segment_span_m` (added to replace the point-count check) was capped at the window's
own half-width (250m) instead of reporting the segment's true length beyond that point --
so it read exactly 250.0 for both beaches regardless of whether the real segment was 300m
or 3km, which would have produced the same misleadingly-vague "long-ish" signal for every
thin-window case. Fixed in `app/exposure/bearing.py::_windowed_tangent` to report the
actual per-hop distance (`d`) rather than the truncated remaining budget in both the
backward and forward truncation branches. Regression test:
`tests/test_exposure_geometry.py::test_max_segment_span_reports_true_length_not_capped_at_window_budget`.

`scripts/exposure/compute_bearings.py` re-run after the fix: bearings for all 8 beaches are
**numerically unchanged** (this was a diagnostic-only fix). Netanya and Ashdod now carry an
accurate, narrower caveat -- "bearing rests substantially on one ~2-2.4km straight OSM
segment; real curvature within that span, if any, is not captured" -- instead of the
original, overstated "LOW CONFIDENCE... review against a map." The caveat is real (a
method that only sees vertices cannot see curvature between them) but it is not evidence
the value is wrong, and should not have been presented as though it might be without
checking first.

## 2026-09-14 -- Obstruction check was the hidden cost of every beach's quality endpoint

`GET /beaches/{id}/quality?hours=96` measured 2.6s per beach; the ranked-list view (all 8
beaches, fetched in parallel from the browser) took 10.4s end to end -- the "takes a long
time to load" the frontend was showing. Profiled with cProfile
(`docker compose exec api python -c "..."`), root cause was entirely in
`app/exposure/obstruction.py`, in two compounding layers:

1. **Redundant re-projection.** `_distance_to_nearest_structure` re-projected all ~226 OSM
   structure lines from raw lat/lon to local XY on every call, and it was called once per
   ray-cast sample (~2,160 samples for a 96-hour request) -- 5.5 million redundant
   `to_xy()` calls, the dominant cost by far. Fixed with `_projected_structures(ref_lat)`,
   `lru_cache`d.
   **First attempt at this cache rounded `ref_lat` to 0.1 degrees to raise the hit rate
   across nearby beaches -- caught by the test suite as a real correctness bug**: it
   silently flipped Herzliya's obstruction result at a 300 degree swell (clear -> blocked)
   by shifting the coordinate frame just enough to cross the 150m lateral threshold on a
   near-boundary case (`test_bat_yam_vs_herzliya_known_truth` and
   `test_ranked_conditions_orders_herzliya_above_bat_yam` failed). Fixed by keying the
   cache on the **exact** `ref_lat` float instead -- every sample for one beach already
   shares that beach's own literal latitude, so the cache still collapses to one
   computation per beach per process with zero behavioural difference from the uncached
   version. Regression test:
   `tests/test_exposure_obstruction.py::test_projected_structures_cache_gives_identical_results_to_a_fresh_projection`.
   This is the general lesson to carry forward: a cache key that approximates the real
   input can silently move a result across a decision threshold. Round/bucket a cache key
   only when the function's output cannot change within the rounding tolerance -- never
   assume it can't without checking a near-boundary case directly.

2. **Algorithmic complexity, unaffected by the projection fix.** Even with projection
   cached, every ray-cast sample still did a linear scan over every point of every one of
   ~226 structure lines to find the nearest one -- an O(all structures) search for a query
   that only ever needs "is anything within 150m of this one point." Re-profiling after
   fix (1) confirmed `to_xy` had dropped out of the hot path entirely, but
   `_distance_to_nearest_structure` was still the dominant cost (2.785s of 3.855s tottime
   for one 80-row request). Fixed with a uniform spatial grid (`_structure_grid()`): each
   structure segment is bucketed into every 200m grid cell its bounding box overlaps
   (`GRID_CELL_M = 200.0`, chosen as the smallest round number >= the 150m lateral
   threshold); a query (`_within_threshold_of_structure`) only inspects the sample's own
   cell and its 8 neighbours, not all ~226 lines. `GRID_CELL_M >= OBSTRUCTION_LATERAL_THRESHOLD_M`
   is the correctness invariant -- any segment within the threshold of a point must have at
   least one point within the threshold, which places it in the same cell as the query
   point or an immediately adjacent one, so nothing reachable is ever skipped. Checked
   directly (not just via the known-truth cases) in
   `tests/test_exposure_obstruction.py::test_grid_threshold_check_agrees_with_exhaustive_scan`,
   which compares the grid result against the original exhaustive scan across a spread of
   real sample points along each beach's swell ray.

**Measured result** (Docker container rebuilt, `docker compose up -d --build api`):
single-beach `/quality?hours=96` went from 2.6s to ~0.08s; the realistic 8-beaches-in-
parallel ranked-list load went from 10.442s to ~0.36s, cold or warm (the grid fix removed
enough cost that the caching layer barely matters any more). Full suite: 89/89 passing
after both fixes, including the new grid-vs-exhaustive correctness test.

## 2026-09-14 -- Face height added as a labelled derived display value

User comparison against another surf app on the same day showed a large gap: our estimate
0.5m, the other app 1.3m, for what looked like the same beach and hour. Investigated by
pulling our stored offshore forecast, re-querying Open-Meteo marine live to rule out a
staleness bug (confirmed identical, not stale), and comparing across all 8 beaches. Root
cause was not a data bug: Open-Meteo's `wave_height` -- everything this project's exposure
and quality layers are built on -- is **significant wave height (Hs)**, the oceanographic
average of the highest third of waves, the same convention docs/BIAS_ANALYSIS.md validated
against the DeepLev buoy. Surf-facing apps commonly show **face height** instead -- closer
to the biggest wave a surfer would actually describe from a session, not the statistical
average -- which runs well above Hs. That gap (not a model error) plausibly explains most
of the 0.5m vs 1.3m difference; our own beach-specific exposure/obstruction adjustment
accounts for the rest and is unrelated to this.

Added `face_height_estimate`/`face_height_range` to `ExposureEstimateOut`
(`app/exposure/apply.py`, `app/schemas.py`) as a **separate, clearly-labelled display
field** -- `wave_height_estimate`/`wave_height_range` (Hs) are untouched and remain what
`app/quality/size.py`'s band boundaries and every accuracy claim in
docs/BIAS_ANALYSIS.md are calibrated against; face height is never used in scoring,
banding, or alerting, only shown to the user.

**The multiplier itself (`FACE_HEIGHT_MULTIPLIER = 1.8`) is a judgement call, not a fitted
value** -- flagged the same way as `OBSTRUCTION_LATERAL_THRESHOLD_M`. This project's own
Hadera buoy fixture happens to report both Hs and Hmax for the same moment (0.42m / 0.53m,
docs/DATA_SOURCES.md -- ratio 1.27), but that is one sample from one buoy at one sea
state, nowhere near enough to fit a ratio from; querying the live measurements table found
exactly one stored row, same conclusion. Used the standard Rayleigh-distributed-sea-state
approximation instead: for N independent waves the expected largest is
`Hs * sqrt(0.5 * ln(N))`; N=1000 (roughly a few hours at an 8-10s period -- "the biggest
wave of the session") gives ~1.86, rounded to the more commonly cited surf-forecasting
rule of thumb of 1.8. Labelled `confidence.face_height =
"unvalidated_conversion_from_significant_height"` (contains "unvalidated" so the frontend's
existing estimate/measured badge convention, web/src/components/Badges.jsx, picks it up
automatically) -- it is a derived conversion, not a new measurement, and should never be
mistaken for one.

Regression tests: `tests/test_exposure_api.py::test_beach_exposure_response_has_full_components_and_confidence`
now also asserts face height is an exact, fixed multiple of the already-computed Hs
estimate (never an independent computation that could drift out of step), and
`test_face_height_is_a_labelled_multiple_of_significant_height_not_a_new_measurement`
pins the multiplier's sign and the confidence label directly.

## 2026-09-14 -- Two real bugs found from one user report: binary obstruction cliff, Tm/Tp mixup

User report: Palmachim showed 1.12m (face height) for Saturday 19/09, Herzliya only 0.67m
(later 0.5m at a different hour) -- despite Herzliya's offshore forecast being the HIGHER
of the two (0.64m vs 0.62m Hs). Investigated by pulling both beaches' full component
breakdown rather than guessing.

**Bug 1: obstruction was a flat, binary penalty.** `obstruction_fraction` returned exactly
0.0 or the full `OBSTRUCTION_STRENGTH` (40%) depending only on whether the ray's closest
approach to any structure was inside or outside `OBSTRUCTION_LATERAL_THRESHOLD_M` (150m) --
no gradient at all. Swept every 1-degree swell direction against Herzliya and found the
model flips from a full 40% reduction to zero between 295 and 296 degrees, purely because
its beach coordinate sits ~93m from the marina breakwater and the ray's closest approach to
it crosses 150m right there. `tests/test_exposure_geometry.py`'s own known-truth test
(Bat Yam vs Herzliya) sits only 4 degrees off that cliff. Saturday's real forecast (swell
293 degrees) landed on the wrong side of it: a ray grazing the breakwater at 135m (10% short
of clearing the threshold) took the SAME full penalty as a ray crossing dead-center at 0m.

Fixed by grading the reduction linearly by closest approach:
`OBSTRUCTION_STRENGTH * (1 - closest_approach_m / OBSTRUCTION_LATERAL_THRESHOLD_M)`,
clamped to 0 outside the threshold. A direct hit (closest ~0m) still gets the full 40%;
a graze near the edge gets almost nothing; nothing in between is now a cliff. Verified
against Bat Yam, whose ray crosses a real breakwater near dead-center (~13m) at the same
swell direction -- it correctly keeps ~37% (barely graded down from 40%), so this is not a
blanket weakening of obstruction, only removal of the discontinuity. Linear-in-distance is
still a judgement call with no ground truth to fit against, same caveat as the threshold
and check-range constants -- this is a smoother heuristic, not a validated shadow model.
`_within_threshold_of_structure` (boolean) became `_nearest_structure_within` (returns the
distance, or inf outside the threshold) so the caller can grade on it; the grid-index
correctness test was tightened to assert the grid distance is EXACT inside the threshold,
not just a correct yes/no, since the graded penalty now depends on that value directly.
Regression test: `tests/test_exposure_obstruction.py::test_obstruction_is_graded_by_closest_approach_not_all_or_nothing`.

**Bug 2: `forecast.wave_period` is the wrong period.** Open-Meteo's `best_match` marine
model's `wave_period` is MEAN period (Tm), not peak period (Tp) -- confirmed directly by
requesting `wave_peak_period` on `best_match` and getting `None` for every hour. Tm runs
roughly 20-25% below Tp for the same sea state (confirmed: Saturday noon showed Tm 5.6s vs
a real Tp of 6.0s from a different model, and the app was quoting Tm as if it were Tp).
`app/quality/period.py`'s band boundaries (WEAK_PERIOD_S=6, GOOD_PERIOD_S=8) are written
for Tp -- feeding Tm in unflagged silently under-rated every single forecast, and is most
likely the source of the "5s vs 7s" gap against another app reported alongside the
obstruction bug. Separately, `period.py`'s docstring claimed the 1s uncertainty band was
"~0.97s MAE against DeepLev (docs/BIAS_ANALYSIS.md)" -- checked, and that analysis
validates wave HEIGHT only and contains no period comparison at all; the figure looks like
a misreading of the unrelated 0.973 height correlation. Corrected the docstring to say the
uncertainty is assumed, not measured, rather than let a fabricated citation stand.

Fixed by fetching real Tp from a second model, `ecmwf_wam025`, which does carry
`wave_peak_period` (`app/clients/open_meteo_marine.py fetch_peak_period_live`) --
requested and parsed independently of the main wave/wind fetch, allowed to fail on its own
without failing the whole forecast row (same graceful-degradation discipline as every other
upstream). New nullable column `Forecast.wave_peak_period`
(`alembic/versions/427208cad892_add_wave_peak_period_to_forecasts.py`, no backfill --
existing rows genuinely were never given a real Tp and a converted value would fabricate a
measurement that was never made). `app/quality/apply.py` prefers it and falls back to the
mean period only when peak is genuinely absent, and says which one was used in
`confidence.period` (`"measured_peak_period_tp ~1s"` vs `"substituted_mean_period_tm --
peak period unavailable, bands assume Tp so this reads LOW"`) rather than presenting the
two as interchangeable. Height still comes from `best_match`
(docs/BIAS_ANALYSIS.md's validated model, correlation 0.973 against DeepLev) -- height and
period now come from two different models describing the same sea, which is an accepted
tradeoff against inventing an unvalidated Tm->Tp conversion factor where real Tp data
exists instead. Regression test:
`tests/test_quality_api.py::test_peak_period_preferred_over_mean_period_when_available`.

## 2026-09-15 -- Obstruction floor only protected the beach's own coordinate, not the structure

User report: Herzliya 0.9m vs Tel Aviv (Hilton) 0.59m for the same day, both with nearly
identical raw offshore forecasts (~0.46m) and shoreline orientation -- too large a gap for
Israel's short, fairly uniform coastline, and worth checking rather than assuming it was
correct. Pulled the component breakdown: Tel Aviv (Hilton) carried a 25% obstruction
penalty, Herzliya none, and that alone accounted for essentially the whole gap.

Traced it to `OBSTRUCTION_MIN_CHECK_DISTANCE_M`'s exclusion logic. That constant exists
specifically to stop a structure right next to a beach's own coordinate (a marina wall, an
entrance jetty) from being mistaken for an offshore shadow-caster -- but the implementation
only skipped ray SAMPLES within that distance of the beach, not the structure that caused
the problem. Tel Aviv Hilton's beach coordinate sits ~13m from a real breakwater (OSM
`man_made=breakwater`, `area=yes`, a ~180m-long digitised polygon -- almost certainly the
real, small breakwater at Hilton Beach itself). Because that structure has a long
footprint, the ray's first POST-floor sample (300m out along the swell bearing) was still
only ~134m laterally from the SAME nearby structure, so it registered a "hit" anyway --
the floor protected the beach's own coordinate from itself, but not from the thing it was
trying to exclude.

This is the identical failure shape as the graded-obstruction fix from the day before: a
structure genuinely local to the beach being counted as if it were out at sea. Fixed by
excluding the whole structure (every segment of it, at every sample distance) whenever ANY
point of it is closer than `OBSTRUCTION_MIN_CHECK_DISTANCE_M` to the beach's own
coordinate, not just filtering samples near the beach
(`_excluded_structure_indices`, cached on the exact `(lat, lon)` -- same
no-rounding discipline as `_projected_structures`). The grid index
(`_structure_grid`) now tags each bucketed segment with the index of the structure line it
came from, so a query can skip an entire excluded structure cheaply.

Verified this does not weaken genuine, farther-out obstruction: Netanya's groyne (~436m
from its beach coordinate) and Bat Yam's pier (~584m) are both untouched by the change and
still register real, graded obstruction at today's swell. Herzliya's own marina breakwater
(~93m, the case that originally motivated `OBSTRUCTION_MIN_CHECK_DISTANCE_M`) is now
correctly excluded everywhere rather than only near the beach, which also resolves the
near-zero-but-nonzero "grazing" values the previous day's graded-obstruction test measured
for it -- those are now exactly 0.0, and the graded-obstruction test was rewritten to
demonstrate grading against Netanya's real, non-excluded, farther-out structure instead.

Result: Tel Aviv (Hilton) went from 0.59m to 0.79m face height for the same hour, in line
with Herzliya (0.83m), Hadera (0.79m) and Palmachim (0.79m) -- all four have nearly
identical raw offshore height and no genuine nearby obstruction. Netanya (0.54m) and Bat
Yam (0.65m) remain lower, and correctly so: both have a real structure several hundred
metres out that the graded model still detects. The remaining beach-to-beach spread is now
explainable entirely by directional exposure (shoreline bearing vs swell angle) and real,
farther-out structures -- not an artifact of where a beach's coordinate happens to have
been seeded relative to its own local infrastructure.

Regression test:
`tests/test_exposure_obstruction.py::test_structure_near_the_beach_itself_is_excluded_entirely_not_just_near_samples`.

## 2026-09-15 -- Face height multiplier was overshooting; revised 1.8 -> 1.3

User report: today's headline size read ~0.9m across most beaches while "the actual
forecast" showed 0.5-0.6m. Checked live: raw offshore Hs was ~0.42-0.46m across the coast
-- close to the user's 0.5-0.6m reference already -- and the displayed ~0.9m was that Hs
times `FACE_HEIGHT_MULTIPLIER` (1.8, set two entries above). Asked the user directly
whether their 0.5-0.6m reference was itself a face-height figure or a raw/Hs figure, since
the answer changes which side of this is wrong; confirmed it was face height, so the
multiplier itself was overshooting, not a mismatched comparison.

Revised 1.8 -> 1.3. The original 1.8 came from a textbook Rayleigh-sea-state
approximation (N=1000 waves, no local grounding). This project already had one real local
data point that pointed lower -- the Hadera buoy fixture's own Hs/Hmax pair (0.42m /
0.53m, docs/DATA_SOURCES.md, ratio 1.27) -- but it was dismissed at the time as a single
sample, not enough to fit a ratio from on its own. Today's live comparison against another
app lands in the same range (a ratio around 1.15-1.3 given the day's raw Hs and the user's
reported 0.5-0.6m), which promotes that single buoy sample from "too sparse to trust
alone" to "independently corroborated" -- 1.3 was chosen to match it.

Worth noting for anyone revisiting this: the FIRST face-height discussion (the one that
introduced face height at all) compared an apparently much larger gap -- offshore_raw
~0.7m against another app's ~1.3m, a ~1.9x ratio -- which is what originally motivated
1.8. That comparison predates this session's obstruction-cliff bugfix
(docs/DECISIONS.md, "Two real bugs found from one user report"), and the beach in that
comparison (Herzliya) was very likely still under the binary 40% obstruction penalty at
the time, which would have deflated whatever Hs-derived number the user was actually
looking at and inflated the apparent Hs-to-face-height gap. That earlier ratio should be
treated as unreliable, not as competing evidence against the 1.3 chosen here.

Still an unvalidated, judgement-call conversion, same caveat as before -- just recalibrated
against better (if still thin) evidence, and expected to keep moving if a clearer ground
truth turns up.

## 2026-09-15 -- Face height was the wrong concept for this coast; checked against real apps

User asked for the displayed wave size to be checked against the surf services people here
actually use (4surfers, Surfline, GoSurf) rather than adjusted by feel again. Did that. The
answer changed the model, not just the constant -- twice today this number had been tuned
(1.8 -> 1.3) on the assumption that a surf-facing height must be LARGER than the deep-water
significant height. That assumption was wrong for Israel.

**What the sources actually say.** Surfline's own published guidance gives the familiar
rule: surf face height runs about **1.3x the deep-water swell height** -- but states it for
**12-16 second ground swell**, where long-period energy shoals up hard onto the bank. That
qualifier is the whole story. Israel's Mediterranean is a short-fetch **wind sea**: our own
peak periods this week run 4.8-7.0s, nowhere near that regime. Short-period waves shoal far
less, and a large share of the offshore Hs in a wind sea is steep, disorganised chop that
never forms a rideable face at all.

**What the local services show.** GoSurf (gosurf.co.il, Israeli, surfer-facing) published a
7-day Tel Aviv outlook. Compared against our own offshore Hs for the same days:

| Day | GoSurf mid | our Hs mid | ratio |
|---|---|---|---|
| 09-15 | 0.40 m | 0.57 m | 0.70 |
| 09-16 | 0.47 | 0.57 | 0.83 |
| 09-17 | 0.40 | 0.35 | 1.14 |
| 09-18 | 0.30 | 0.47 | 0.64 |
| 09-19 | 0.70 | 0.82 | 0.85 |
| 09-20 | 0.55 | 0.61 | 0.90 |
| 09-21 | 0.30 | 0.50 | 0.60 |

Median 0.83, mean 0.81 -- **below 1.0, not above it.** The old 1.3 was overshooting the
local convention by about 1.6x, which is exactly the "way over the actual forecast"
the user had been reporting.

Cross-checked to rule out plain model disagreement: surf-forecast.com's Tel Aviv figure for
the calibration day (0.5-0.6 m at 6s) tracks our raw Hs (0.52-0.62 m) closely, while
GoSurf's same-day figure is 0.3-0.5 m. Two references agreeing on the deep-water number
while the surfer-facing one sits below it pins the gap on the REPORTING CONVENTION, not on
whose wave model is right. (4surfers and Surfline both return HTTP 403 to automated
fetches, so they could not be sampled directly; Surfline contributed its documented
convention, quoted above, rather than live numbers.)

**Changed:** `FACE_HEIGHT_MULTIPLIER = 1.3` -> `SURF_HEIGHT_FACTOR = 0.8`, and the fields
renamed `face_height_estimate/_range` -> `surf_height_estimate/_range` across the schema,
API, UI and tests. The rename is not cosmetic: a field called "face height" holding a value
BELOW the significant wave height would be a plainly false label, which hard rule 1 forbids
-- what the number now represents is the local surf-report convention (the waves breaking
at the beach), which on this coast is smaller than the deep-water Hs. The UI label follows
("Size (surf height)"), and `confidence.surf_height` still contains "unvalidated" so the
frontend keeps badging it an estimate.

After the change our Tel Aviv range overlaps GoSurf's published range on **every one of the
seven forecast days**. Hs itself is untouched everywhere it is load-bearing
(app/quality/size.py bands, docs/BIAS_ANALYSIS.md's accuracy claims).

**Still open, deliberately.** 0.8 is an empirical fit to ONE local service over ONE week,
not a measurement, and the per-day scatter is wide (0.60-1.14). The physically right answer
is a period-dependent conversion -- the ratio should climb toward the textbook 1.3 if this
coast ever gets a genuine long-period ground swell, and today's data is all 5-7s so it
cannot constrain that end at all. Worth revisiting with a winter storm in the sample.

## 2026-09-15 -- Piers were treated as wave barriers; obstruction strength also recalibrated

User asked why 19/09 showed "surf size 0.46" against "offshore size 0.88" for a beach --
too big a gap for the 0.8x surf-height conversion alone to explain. Traced it: the beach
was Bat Yam, and the gap was two stacked effects -- a 34% obstruction penalty, THEN the
0.8x conversion (0.88 Hs offshore -> 0.57 Hs at the beach after "obstruction" -> 0.46 surf
height). The obstruction was the real bug.

**What was actually there.** The structure driving it is OSM way `109274249`, tagged
`man_made=pier` + `highway=footway` -- a walkway pier standing on piles. Waves pass
straight underneath a piled pier; it is not a wave barrier the way a solid breakwater or
groyne is, but `app/exposure/obstruction.py` treated every OSM `man_made` type identically.
Checked the dataset: of 226 structures, **157 (69%) are tagged `pier`**. Only 4 of those
carry a `highway` tag and 30 are explicitly `floating`, so neither tag reliably separates
piled from solid piers on its own -- but the `pier` type itself is a real, available signal
that most piled structures are not full barriers.

**Verified against GoSurf.** gosurf.co.il's published Bat Yam and Tel Aviv forecasts are
**identical on both sampled days** (today 30-50cm both; Saturday 19/09 60-100cm both) --
these two beaches sit on an open, mostly unobstructed stretch of coast and should track
each other, which the pier bug was actively breaking.

**Fix 1 -- type weighting.** Added `structure_kinds()` (`app/exposure/coastline_data.py`),
index-aligned with `structure_lines()`, exposing each structure's `man_made` tag.
`OBSTRUCTION_TYPE_WEIGHT = {"pier": 0.0}` in `obstruction.py`, default weight `1.0` for any
other/unknown type so an unfamiliar future tag is never silently dropped -- only `pier` is
special-cased. This required changing the grading algorithm: the old version tracked the
single nearest distance across the whole ray and graded once at the end, which is wrong
once distance and type are both in play -- a close zero-weight pier could otherwise mask a
farther-but-real groyne. Replaced with `_max_weighted_severity()`, which computes a
per-structure `weight * (1 - distance/threshold)` severity at each sample and tracks the
**max severity** across the ray, not the min distance.
(`_nearest_structure_within`, the pure-geometry distance function, is untouched and still
backs `test_grid_threshold_check_agrees_with_exhaustive_scan` -- that correctness check
stays type-agnostic on purpose.)

**Fix 2 -- obstruction strength recalibrated, again.** While investigating, also checked
Netanya, which has a genuine (non-piled) groyne obstruction: GoSurf puts Netanya only ~12%
below Tel Aviv/Bat Yam on the same days, while the model (even before this fix) was cutting
it ~29%, about 2.4x too strong. Lowered `OBSTRUCTION_STRENGTH` from `0.4` to `0.2` -- the
maximum possible reduction, for a dead-on hit on a real, full-weight structure. This is the
THIRD time this file records a downward obstruction-strength correction in two days (binary
40% -> graded 40% -> graded 20%); each one was checked against a different piece of real
evidence (Bat-Yam-vs-Herzliya known-truth, then GoSurf comparisons), and the honest reading
is that this constant has no real ground truth behind it at all -- only a shrinking series
of corrections against whatever comparison was available that day.

**Result, measured live (19/09, 06:00-15:00, same swell):**

| Beach | Before | After | GoSurf (same window) |
|---|---|---|---|
| Bat Yam | 0.46 m (obstruction 0.34) | 0.66-0.70 m (obstruction 0.0) | 0.60-1.00 m |
| Netanya | 0.48 m (obstruction 0.29) | 0.57-0.61 m (obstruction 0.14) | 0.50-0.90 m |
| Tel Aviv / Herzliya | 0.69-0.71 m (unaffected) | 0.66-0.71 m (unaffected) | 0.60-1.00 m |

Bat Yam now tracks Tel Aviv/Herzliya almost exactly, matching GoSurf showing them
identical. Netanya sits ~12-15% below the others, matching GoSurf's own gap. Confirmed via
a dedicated test (`test_piers_do_not_count_as_wave_barriers`) that Bat Yam's OTHER real
structure (a breakwater, different from the pier, hit at swell 330-345) is unaffected and
still blocks near-fully -- the fix is type-selective, not a blanket weakening.

94 tests passing, including the updated/new obstruction tests.

## 2026-09-15 -- Quality score rescaled to 0..10 and made conservative with hard ceilings

User report: a small (~0.45m surf height) day across the whole coast was reading "excellent"
in the app. Traced it to two real gaps in `app/quality/verdict.py`:

1. **No size ceiling.** `quality_score` was a pure weighted sum (wind 0.4, size 0.25, chop
   0.25, period 0.10) with no upper bound tied to how big the wave actually was. A 0.5m day
   with clean wind/period/chop scored 0.9375 (old 0..1 scale) -> "excellent". Even 0.4m
   scored 0.85 -> "excellent". In the user's own words: "there are no waves at 0.5."
2. **Wind speed didn't affect the score at all above 8 km/h.** `classify_wind`'s score is a
   pure cosine of wind DIRECTION relative to shore -- a 60 km/h dead-offshore gale scored
   identically to a 9 km/h breeze. Speed only ever showed up as a binary "gusty" multiplier.

**Fix: two hard ceilings on the numeric score, not just the verdict word.** The existing
`_cap()` mechanism only ever clamped the WORD ("excellent" -> "fair"), never the number --
but ranking, alert clustering (`app/alerting/matching.py`) and best-hour selection all sort
on the raw `quality_score`, so a word-only cap would still let a flat day win a ranking or an
alert. Both new ceilings (`SIZE_CEILING`, `WIND_CEILING` in `verdict.py`) clamp the number
itself via `min()`, computed before the ladder, so the word follows correctly.

- `SIZE_CEILING` is keyed on **surf height** (the displayed breaking-wave number,
  `surf_height_estimate`), not on the offshore Hs `classify_size`'s own bands still use --
  the bands stay Hs-based (tied to docs/BIAS_ANALYSIS.md's regimes), only the ceiling looks
  at what the user actually sees. Table (surf height -> max score, 0..10 scale): <0.3m -> 0
  (flat), 0.3-0.5 -> 2, 0.5-0.8 -> 4, 0.8-1.2 -> 7, 1.2-2.0 -> 10, >2.0 -> 8 (big enough to be
  demanding/messy on this coast, not a clean 10).
- `WIND_CEILING` is direction-aware: onshore/cross-shore wind caps hard as it strengthens
  (12-20 km/h -> 6, 20-30 -> 4, >30 -> 2) since it blows straight into the wave face; offshore
  wind is left alone until it gets strong enough to hold waves up too much (>35 km/h -> 6).
  Gusty subtracts a further 2 points from whichever ceiling applied. `WindQuality` gained a
  `speed_kmh` field (previously only direction reached the combiner) to make this possible.
- Both tables are judgement calls with no ground truth to fit against, same caveat as every
  other heuristic constant in this project -- user-approved starting points, not measured.

**Scale changed 0..1 -> 0..10** in the same change, so the score is meant to be read, not
just compared -- it was never surfaced in the UI before. `SCORE_THRESHOLDS` moved to
(8.0 excellent / 6.0 good / 4.0 fair / 0.0 poor).

**A real implementation bug found while testing against the acceptance suite**: the wind
ceiling's speed buckets were initially written in the wrong order/direction (looked like
"faster is worse" was applied backwards), caught by `test_full_day_hour_by_hour_wind_rotation`
losing monotonicity as wind rotated onshore->offshore -- a 14 km/h cross-shore hour scored
worse than a 22 km/h more-onshore hour, which is physically backwards. Fixed the table.

**A legitimate consequence of strict ceilings, not a bug**: `test_high_chop_degrades_verdict_
even_at_good_height` (an existing acceptance test) originally used a 1.3m Hs case where BOTH
the clean and choppy scenarios' raw weighted scores exceeded the 0.8-1.2m surf-height
ceiling bucket (7.0) and saturated to the identical clamped number -- erasing the numeric
gap between them, though the verdict WORD still correctly degraded good->fair via the
existing onshore/choppy `_cap`. Widened the test's size to 1.8m Hs, where the ceiling no
longer binds, so the underlying chop-driven difference is visible again. This is an inherent
tradeoff of coarse ceiling buckets: two different-quality days in the same size bucket can
legitimately clamp to the same number even though their verdict words still differ.

Also removed a special-cased "not enough size or too much wind to surf" message for when a
ceiling clamps the score to exactly 0.0 (e.g. a gusty gale-force onshore blow) -- that is a
different situation from the pre-existing `size.band == "flat"` early return (genuinely no
wave at all) and was overriding real, useful reasoning ("onshore wind chopping up the face,
gusty too...") with a generic sentence. `_score_to_ladder`'s own `(0.0, "poor")` threshold
already handles a zero score correctly without the special case.

Added `swell_direction_deg` to `QualityOut` (was previously only on `ForecastOut`) -- needed
for the planned hourly UI, which must show swell direction without a second client-side
fetch-and-join, per this project's "no client-side derivation of API data" rule.

Verified live: today's ~0.43-0.46m surf heights across all 8 beaches now score exactly 2.0
(capped by size, several further capped by wind) and read "poor" -- not "excellent". 97
tests passing.

## 2026-09-15 -- Per-slot watch alerts: a new table, not an extension of Subscription

User request: an "alert me" button on a specific forecast slot that watches it and pushes
a notification when it qualifies -- distinct from the existing standing `Subscription`
rules (recurring criteria evaluated over a rolling date range). Clarified through follow-up
that this should NOT be a fixed-offset reminder ("push 12h before") but a genuine watch:
dormant until 12h before the slot (forecasts move too fast to trust earlier), then
re-checked as forecasts refresh and fired the moment the slot's `quality_score` crosses
5.0/10 -- with a cancellation pushed if it later falls back below that bar.

**New `slot_watches` table**, not an extension of `Subscription`: `Subscription.time_
window_start/end` are NOT NULL local wall-clock `Time` columns describing a *recurring*
window, not a single absolute instant, and `AlertSent.subscription_id` is a NOT NULL FK --
a one-off watch on a specific slot fits neither without weakening an existing invariant.
State machine: `pending` (dormant or watching, not yet qualified) -> `alerted` (qualified,
pushed) -> `cancelled` (fell back below the bar, cancellation pushed) or -> `expired` (the
slot passed while still pending, never qualified, no message). `watch_from` (=
`valid_at - WATCH_LEAD_HOURS`) is stored rather than computed on the fly, so the lead time
is auditable per-row and independently tunable later without a backfill.
`UniqueConstraint(user_id, beach_id, valid_at)` makes double-tapping the same slot
idempotent -- the API route catches the constraint violation and returns the existing row
rather than erroring.

**Dispatcher polls a table rather than scheduling one-off jobs**, on a new interval job
(`app/scheduler.py`, `settings.slot_watch_dispatch_minutes`, default 10 -- far more
frequent than ingestion's 180, since "forecasts change fast" was the explicit reason for
the 12h/watch-not-reminder design). APScheduler's default job store is in-memory, so a
one-off `date`-trigger job per watch would be silently lost on any restart/redeploy, and
every worker process would fire its own copy. A `SELECT ... FOR UPDATE SKIP LOCKED` poll
against `slot_watches` has neither problem -- `skip_locked` (rather than `runner.py`'s
plain `FOR UPDATE`) lets concurrent ticks skip past a row another tick is already handling
instead of blocking the whole batch behind one slow push.

Renamed `app/alerting/runner.py`'s private `_deliver_to_user` to public `deliver_to_user` --
it is the only code that maps a user to their devices and handles push expiry, and the new
`app/alerting/slot_watch.py` needed to call it without duplicating that lookup.

Added `Beach.name_he` in the same migration (bundled since it touched the same revision
chain, unrelated to slot watches otherwise) -- the UI is Hebrew/RTL only, no i18n
framework, and beach names are data the API owns (`data/beaches.yml` / `app/seed.py`), not
something the frontend should hardcode a translation map for.

6 new tests in `tests/test_slot_watch.py` cover the full state machine against a real
Postgres session (idempotent create, outside-window inaction, below-bar silence,
qualify-fires-once, fall-back-sends-one-cancellation, expiry). 103 tests passing.

## 2026-09-15 -- Hebrew/RTL: the prose/identifier boundary

User request: the UI should be Hebrew, RTL. Single language, no toggle, no i18n framework --
the app has exactly two runtime dependencies and one user, so a translation library would be
overhead with no payoff.

**The boundary that matters: user-facing PROSE is translated; internal IDENTIFIERS are not.**
`quality_verdict` ("flat"/"poor"/"fair"/"good"/"excellent"), `period_band`, `chop_band`,
`relation_to_shore`, every `confidence` string, and all API field names stay exactly as they
are -- tests assert on these values directly (e.g.
`tests/test_quality_api.py::test_no_quality_confidence_ever_marks_verdict_as_validated`
greps the whole `app/` tree for a literal `"unvalidated_heuristic"`), and other backend code
branches on them (`app/quality/verdict.py`'s own `_cap()` compares `chop.band == "choppy"`).
Translating an identifier would either break that logic or force every comparison through a
translation table, for no benefit -- these values are never shown to a user directly, only
looked up through a label map on the frontend.

**What WAS translated, at the point it is generated, because it IS what the user reads:**
`app/quality/verdict.py::_build_reasoning` (the `quality_reasoning` sentence -- e.g. "רוח
חופית מקלקלת את פני הגל, גלישה מעורבת, מחזור חלש, גודל בינוני (מוגבל בגלל גודל קטן מדי)"),
`app/alerting/notification.py::build_payload`'s title/`calibration_note`/`honesty_marker`,
`app/alerting/runner.py`'s inline cancellation payload, and
`app/alerting/slot_watch.py::_build_payload`'s title/`honesty_marker` -- all four are text
that either renders directly in the UI or lands in a push notification, so leaving them
English would mean an otherwise-Hebrew app suddenly switching languages mid-sentence.

**One deliberate exception, left English on purpose:**
`app/alerting/calibration.py::describe_operating_point`'s `description` field. It is
embedded inside `calibration_note` rather than being the primary sentence, and its own test
(`tests/test_alerting_calibration.py`) checks for a literal `"docs/BIAS_ANALYSIS.md"`
substring -- a doc path that has no Hebrew form. Translating the wrapper sentence around it
while leaving this one technical explanation in English was judged an acceptable seam,
since it is the least user-facing piece of the four files above.

Fixing the reasoning translation broke reasoning-substring test assertions that had been
checking for the literal English words "onshore"/"offshore"/"clean"/"chop" -- updated
`tests/test_quality.py` to check for the Hebrew band words instead (e.g. "חופית",
"אופשור", "נקייה", "סחופה"), same intent, now matching what the function actually returns.

Also added `Beach.name_he` usage throughout the payload builders above (`beach.name_he or
beach.name`, never a bare `beach.name`) so a beach without a Hebrew name yet still produces
a readable notification rather than a blank.

Frontend RTL work (labels dictionary, logical CSS properties, bidi number isolation,
`<html lang="he" dir="rtl">`) lands together with the drill-down UI rebuild, since both
touch the same view files -- see the next entry.

103 tests passing.

## 2026-09-15 -- Frontend rebuilt: Surfline-style drill-down, Hebrew/RTL, web push client

Completes the frontend half of the Hebrew/RTL + drill-down + per-slot-watch work (backend
halves recorded in the three entries above). No router added -- `react-router-dom` would be
a third runtime dependency for an app that deliberately has two, and the UI is explicitly
"not the point of the project" (prompts/phase-5-ui.md). Navigation is hand-rolled in
`App.jsx` as a small `{view, beachId, date}` state object instead.

**Data flow.** `getBeachQuality(id, 168)` already returns a full 7 days; the old
`RankedBeachList` fetched this per beach on every date change, and `SingleBeachBreakdown`
re-fetched on every beach/date change too. `App.jsx` now fetches each beach's series ONCE
per session (a `Set` of already-fetched beach ids) and passes it down as props -- the three
new views (`BeachList` -> `BeachWeek` -> `BeachDay`) are pure client-side reductions of that
one cached series, not separate fetches.

**Views**, replacing `RankedBeachList.jsx` (deleted) and folding `SingleBeachBreakdown.jsx`
(deleted) into a drill-down's last step:
- `BeachList.jsx` -- compact one-line rows (name, score badge, surf height, wind), sorted
  by the CURRENT hour's score (`nearestSlotTo`, new in `dateUtils.js`), not "best hour of
  the day" as before. Materially shorter per beach than the old ~150px cards.
- `BeachWeek.jsx` -- 7 daily rows for one beach (`nextLocalDates(7)`, new), each showing
  `bestHourForDate` (already server-scored) and the day's surf-height range.
- `BeachDay.jsx` -- 3-hour interval rows (`hoursAtIntervalForDate`, lifted out of the old
  `SingleBeachBreakdown.jsx` where the same filter predicate was duplicated twice) showing
  exactly wave height / wind speed / swell direction / score, per the user's ask. Tapping a
  row expands it into the full component breakdown in place, rather than navigating to a
  separate tab. Each row carries a watch toggle wired to the new `/slot-watches` endpoints.

**The score is now actually visible.** `quality_score` was computed since Phase 3 but never
rendered anywhere in the UI -- the new `ScoreBadge` (`Badges.jsx`) shows it everywhere a
verdict is shown, coloured off the same ladder so the two never visually disagree.

**Hebrew/RTL, frontend half** (backend prose translation recorded separately above):
`index.html` sets `lang="he" dir="rtl"`; `labels.jsx` is the one place backend IDENTIFIERS
(verdict/band/relation words, confidence strings) get mapped to Hebrew for display, with an
unrecognised value falling back to itself rather than rendering blank. `index.css` audited
for physical-direction properties that don't auto-mirror under `dir="rtl"` (flex/grid
already do) -- `margin-left` -> `margin-inline-start` on `.badge`, `text-align: left` ->
`text-align: start` plus the asymmetric `padding: 6px 10px 6px 0` -> logical
`padding-inline: 0 10px` on `.breakdown-table th`. Numbers/units/times inside Hebrew text
go through a new `<Num>` component (`unicode-bidi: isolate`, `dir="ltr"`) -- without it,
mixed Hebrew+Latin-numeral strings are the single most common way an RTL UI visibly breaks.
Beach names use `beach.name_he || beach.name` throughout, never a bare `name`.

**Web push client stack, previously entirely absent** -- no service worker, no permission
flow, no subscribe call existed anywhere under `web/`, so the "alert me" button the user
asked for would have delivered nothing however correct the backend was. Added:
`web/public/sw.js` (a `push`/`notificationclick` handler; `web/public/` did not exist
before), registered eagerly but harmlessly from `main.jsx` (registering a service worker
does not itself prompt for permission); `src/push.js::ensurePushRegistered()`, called
LAZILY on the first watch tap (not on page load) so the permission prompt has context --
requests `Notification.permission`, fetches the VAPID public key from the new
`GET /push-config` (added alongside the `slot_watches` backend work, since the key
previously never reached the browser at all), and registers the resulting
`PushSubscription` with the existing `/push-subscriptions` endpoint. `src/identity.js`
gives both the watch button and the standing-subscription form a stable
`localStorage`-backed user id, replacing the free-text box with no persistence that existed
before.

**`SubscriptionForm.jsx`** kept as the standing-rules tab (Hebrew now), with a new second
list showing active per-slot watches (created from `BeachDay`) alongside the recurring
subscriptions -- two different tools surfaced in one place: a standing rule vs. a one-off
watch on a specific slot.

**Verification note:** confirmed via `docker compose up -d --build web`, a clean
production `vite build` (which fails on unresolved imports/syntax errors -- none did), live
API responses through the real endpoints (`name_he` present, `quality_score` on the new
0..10 scale, `swell_direction_deg` populated), and a grep across the built JS bundle
confirming no reference to the deleted view files survived. **Not click-tested in an actual
browser** -- no browser automation tool was available in this environment; this is a real
gap relative to this project's own stated practice of testing UI changes live before
calling them done, and is worth a manual pass (especially the RTL number-isolation and the
push permission flow, which cannot be meaningfully verified from the command line at all).

## 2026-09-16 -- Continuous scoring curve, body-reference scale, board recommendation, swell height

User feedback: the score needed to be "better" -- specifically, a real Israeli surfer's own
calibration ("a 1m day with light wind should be about a 7") and a complaint that scores
felt too coarse, not varying hour to hour the way real conditions do.

**Root cause of the coarseness**: `SIZE_CEILING`/`WIND_CEILING` (added the previous day)
were discrete step tables -- every hour in the same bucket (e.g. any surf height from 0.8m
to 1.2m) clamped to the exact same ceiling value, so a whole range of genuinely different
hours all read "7.0". Replaced both with piecewise-linear interpolated curves
(`SIZE_CEILING_CURVE`, `WIND_CEILING_CURVE_ONSHORE/OFFSHORE` in `app/quality/verdict.py`),
reusing the exact interpolation idiom `app/alerting/calibration.py`'s `BIAS_TABLE` already
established in this codebase. The user's stated anchor -- 1.0m surf height, light wind ->
~7/10 -- is now literally one point on the curve (`(1.0, 7.0)` in `SIZE_CEILING_CURVE`),
verified directly: `combine(..., surf_height_m=1.0)` with glassy wind, workable period and
clean chop returns exactly `7.0`. Nearby hours now read `6.8`, `7.2`, etc. instead of
repeating the same clamped number -- no existing test's numeric assertions needed to
change, since they all used inequalities (`<=`, `>=`) against the ceiling behaviour, not
exact equality against the old step values.

**Three new derived fields**, all display-only (never fed back into scoring), all operating
on SURF HEIGHT (the displayed breaking-wave number) rather than the offshore Hs
`app/quality/size.py`'s own bands are calibrated against -- same split already established
for the size ceiling:

- **`body_reference`** (`app/quality/body_reference.py`) -- the surf-community "body
  reference" / Hawaiian scale (קרסול/ankle, ברך/knee, מותניים/waist, ... מעל הראש/overhead).
  A widely-used convention, not invented here, but the exact metre boundaries between bands
  are this project's own judgement call, documented as such.
- **`board_recommendation`** (`app/quality/boards.py`) -- which board types (סופט
  טופ/soft-top, לוח ארוך/longboard, לוח קצר/shortboard) are realistically rideable, gated on
  surf height AND period: very small surf excludes shortboards (not enough push to plane);
  big AND short-period surf excludes longboards (too steep/fast to turn in time), but big
  AND long-period surf still allows one (more time per wave). Another explicit judgement
  call, not derived from anything measured.
- **`swell_height_m`** (new field on `QualityOut`, from `forecast.swell_wave_height`) --
  unlike the two above, this is MEASURED, not derived: the raw upstream swell-only height,
  already fetched and stored, simply not previously exposed at the quality-response level.
  Same rationale as the earlier `swell_direction_deg` addition -- the day-by-day UI needs it
  and must not derive it client-side from a second fetch-and-join.

`QualityConfidence` gained `body_reference`/`board_recommendation` (both hardcoded
`"unvalidated_heuristic"`, same guarantee as `size`/`quality_verdict`).

New test file `tests/test_body_reference_and_boards.py`: band monotonicity, half-open
boundary behaviour (a band's own upper bound belongs to the next band), the short-vs-long
period longboard distinction at the same height, and the no-data-returns-empty path.

110 tests passing.

## 2026-09-16 -- Day-view redesign: pill-styled 9-column table, week strip, height chart

User provided a reference screenshot (a real Israeli surf site's compact daily table) plus
detailed text specs for two things: (1) a compact per-day style (colour-pill wind/height
cells, sun/moon icons) as a general visual reference, and (2) an explicit 9-column layout
for the EXPANDED single-day view, which supersedes the compact style where they conflict --
the user's own follow-up message clarified this ("the picture is for design reference").

**`BeachDay.jsx`** rebuilt around a `<table>` with columns, right-to-left reading order,
exactly as specified: hour, wave height (range, not the single estimate -- explicit user
correction), score, body reference, board recommendation, swell height, period, wind speed,
wind direction. A 10th `מעקב` (watch) column was added beyond the user's 9 -- the per-slot
watch toggle from the previous day's work still needed a home, and a table row was the
natural place for it. Styling per the reference: wind and score cells are solid colour-fill
pills (wind: green/orange/red 3-tier bucket on speed+relation, a purely presentational
categorisation separate from and coarser than `app/quality/verdict.py`'s actual
`WIND_CEILING` curve; score: filled with the same verdict colour ladder used elsewhere,
per the explicit "fill with the score's colour" ask); height is a solid blue pill showing
the range in **centimetres** (the reference photo's own convention, "40-70 ס״מ") rather
than the metres used everywhere else in the app; hour cells show a sun or moon icon (a
rough 06:00-18:00 daytime window, NOT a real sunrise/sunset calculation -- this project has
no astronomical data source, and a precise-looking icon for an approximate window would be
its own small dishonesty).

**No temperature column**, unlike the reference photo. This project has no air-temperature
data source anywhere in the ingestion pipeline -- showing a number would mean inventing one,
which hard rule 1 forbids outright. Flagged here rather than silently dropped.

**Confidence badges were about to be lost, caught before committing**: the reference
design's clean pill table has no room for a per-cell "estimate"/"measured" badge the way
the old detail table did, but dropping that distinction entirely would violate this
project's standing rule that every heuristic number stays visually distinct from a measured
one. Replaced per-cell badges with a single explanatory line under the table naming which
columns are estimates (surf height, score, body reference, boards) vs. which come straight
from the forecast model (wind, swell height, period) -- preserves the honesty requirement's
intent without cluttering the requested design.

**`BeachWeek.jsx`** -- each day is now a horizontal strip of the day's 3-hour slots (sun/
moon icon, hour, **score directly after the hour** per the user's explicit ordering ask,
then height), not a single daily summary number, so a day's shape is visible before
drilling in. The strip shows a single height estimate per slot, not a range -- unlike
`BeachDay`'s table, there isn't room for a range in a ~44px mini-cell; this is a scope
compromise, noted rather than silently made.

**New `WaveChart.jsx`** -- a dependency-free inline SVG line chart (surf height and score
over the visible week), added at the top of the beach page per the request for "a graph of
just the waves height and score." No charting library added, consistent with this project's
deliberately minimal dependency list.

**New `Icons.jsx`** -- sun, moon, a wind arrow (rotated via CSS transform from the wind's
"from" bearing, pointed the intuitive way the wind is blowing toward), and Facebook/
WhatsApp share icons, all inline SVG, no icon library. Share buttons use the Web Share API
where available, falling back to a WhatsApp deep link.

**Google Fonts Heebo** added (`index.html`, `preconnect` + stylesheet link, within this
project's CDN/font allowlist), set as the primary font in `index.css`.

Dead CSS from the previous day-view design (`.day-row`, `.day-row-wrap`, `.breakdown-card`,
`.breakdown-table`, `.reasoning`, `.week-row` and related) removed rather than left behind
once nothing referenced them.

Verified: clean production `vite build`, backend suite still 110/110 (no backend touched in
this entry beyond what the previous entry already covered), and a grep across the built
bundle confirming the new Hebrew column headers and CSS classes are actually present.
**Still not click-tested in an actual browser** -- same caveat as the previous frontend
entry; no browser automation tool is available in this environment.

## 2026-09-16 -- Added air temperature and sky condition (weather_code)

User request: show temperature and sky condition (sunny/cloudy/partly cloudy) per hour and
per day. No prior data source for either existed in this project.

Both come from `api.open-meteo.com/v1/forecast` -- the SAME request already used for wind
(`app/clients/open_meteo_forecast.py`), not a third upstream call. Verified live against
the real API before wiring anything: `temperature_2m` and `weather_code` are genuinely
returned alongside `wind_speed_10m` for the same coordinates/hours.

`weather_code` is the standard WMO 4677 code table -- unlike almost every other heuristic
in this project, translating it (`app/quality/weather.py::classify_weather`) is NOT a
judgement call with no ground truth; it's a published lookup table. Stored as the raw code
on `Forecast.weather_code` (new nullable column, no backfill -- same discipline as every
prior migration touching this table: existing rows genuinely were never fetched with this
field), translated to a Hebrew label + a stable English `icon_key` only at the
`QualityOut` response layer. `temperature_c` is equally MEASURED, not derived.

New `QualityOut` fields: `temperature_c`, `weather_label` (Hebrew), `weather_icon` (English
identifier for the frontend's icon lookup -- kept English for the same reason every other
identifier in this project is, something to match on, not display). New
`QualityConfidence.weather`, hardcoded `"measured_forecast"`.

New `tests/test_weather.py`. 112 tests passing.

## 2026-09-16 -- Frontend: unified pill-table design across beach list/week, chart redesign

User feedback: the beach list and the per-beach day list should look like the day-forecast
table (same pill styling), not a different design per screen; and the week-view chart
should label days, not hours, with the peak height/score called out numerically.

**`BeachList.jsx`** and **`BeachWeek.jsx`** both rebuilt as `<table className="day-table">`
-- the exact same CSS the hourly `BeachDay` table uses -- rather than the flex-row card
layout each had before. `BeachList` shows one row per beach (current conditions, nearest
hour to now); `BeachWeek` shows one row per DAY (not one strip per hour as the previous
iteration had) -- explicitly "just a summary of the day," using the existing
`bestHourForDate` helper for the day's score/wind and the day's full min/max across all its
3-hour slots for the height-range pill. Both reuse the identical wind-pill/height-pill/
score-fill classes and colour logic `BeachDay` already established, so the whole app now
reads as one visual language rather than three.

**Weather + temperature**, wired through from the previous entry's new backend fields: the
hour cell in `BeachDay` (and the equivalent "current"/"midday" cell in `BeachList`/
`BeachWeek`) now shows the REAL weather icon (`WeatherIcon`, new in `Icons.jsx`, resolving
`weather_icon` + day/night into one of seven inline SVGs: clear, partly cloudy, cloudy,
fog, rain, snow, storm) plus the temperature, replacing the earlier version's rough
day/night-only Sun/Moon guess. `BeachWeek`'s one-icon-per-day picks the hour closest to
13:00 local as representative, rather than showing 8 separate weather readings for one day.

**`WaveChart.jsx`** rebuilt: x-axis labels are now day names (`today/tomorrow/weekday`,
centred over that day's own span) instead of hour ticks, and each day's PEAK height and
peak score are marked directly on the chart with a dot and their number, rather than
requiring the reader to hover or cross-reference the table below. (Caught and fixed a real
bug while building this: the rewritten file initially imported `todayOrTomorrowLabel` from
the wrong module -- it lives in `dateUtils.js`, not `labels.jsx` -- which would have failed
the production build; fixed before it ever reached the build step.)

Dead CSS from the prior BeachList/BeachWeek designs (`.beach-row*`, `.beach-list-compact`,
`.week-day-row*`, `.week-hour-*`, `.wave-chart-ticks`) removed once nothing referenced them
-- confirmed via grep across all view files before deleting each block, not assumed.

Verified: clean production build, backend suite unaffected (112/112, nothing backend
touched in this entry), live API shape spot-checked against what the new components
actually read (`weather_icon`, `weather_label`, `temperature_c` all present and correctly
typed), and the new CSS classes/Hebrew strings confirmed present in the built bundle. Same
standing caveat as every frontend entry above: not click-tested in an actual browser.

## 2026-09-16 -- RTL fixes, share buttons removed, simplified labels, day-summary humor line

**Share buttons removed** entirely -- `BeachDay.jsx`'s header, `Icons.jsx`'s Facebook/
WhatsApp icons, and the related CSS, per direct request.

**Real RTL bug fixed, and a real principle correction**: swell height, period and wind
speed were wrapped in the `<Num>` bidi-isolation helper (`dir="ltr"`), which was WRONG for
these three -- forcing a plain "value + short Hebrew unit" pair like "6.1 שנ'" into an LTR
island breaks its flow inside the surrounding RTL row/sentence, it does not fix anything.
`<Num>` exists for genuinely ambiguous cases: a RANGE like the height pill's "40-70", where
two numbers separated by a dash really can reorder under RTL without isolation. A single
number-plus-unit needs no such help -- the Unicode Bidi Algorithm handles an embedded
Western-digit run inside RTL text correctly on its own, which is how the vast majority of
Hebrew web content already renders numbers. Removed `<Num>` from these three columns
(`BeachDay.jsx`) and from the wind-speed pill wherever it's repeated (`BeachList.jsx`,
`BeachWeek.jsx`); left it in place everywhere it wraps an actual range or the score number,
since those are unaffected by this distinction.

**The week/day chart was also silently wrong for RTL**, caught by a direct follow-up
report: an `<svg>` does not auto-mirror its own coordinate space the way flex/grid layouts
do under `dir="rtl"` -- the x-axis was running left-to-right (today on the left) inside an
otherwise fully RTL page. Fixed with one change to `WaveChart.jsx`'s `x(i)` mapping,
mirroring the whole plot so index 0 sits at the right edge and time runs right-to-left,
matching how the rest of the page reads. Worth remembering for any future SVG work in this
app: SVG coordinate space needs an explicit mirror, CSS `dir` does not do it automatically.

**Simplified labels, per direct request**:
- Board recommendation (`app/quality/boards.py`): `SOFT_TOP`/`LONGBOARD`/`SHORTBOARD`
  renamed to the exact Hebrew terms asked for -- סופט / לונגבורד / שורט. Column header in
  `BeachDay.jsx` renamed "לוחות" -> "גלשנים מתאימים". No backend test changes needed --
  the tests import the constants, not hardcoded strings, so they stayed correct through the
  rename automatically.
- Body reference (`app/quality/body_reference.py`): collapsed from the original 10-band
  "above X" scale down to exactly the 5 bands asked for -- קרסול / ברך / מותן / כתף / ראש
  -- with new boundaries at 0.4/0.7/1.1/1.6m surf height. Updated
  `tests/test_body_reference_and_boards.py`'s two band-boundary tests to match (the old
  ones asserted labels -- e.g. "מעל מותניים" -- that no longer exist in the 5-band scheme).

**Tagline replaced** ("נוחות והשוואה בין חופים -- לא דיוק גובה גל עדיף..." -> "בלי
ניחושים. תדעו בדיוק איפה שווה לגלוש היום.") -- more direct, more surf-voice, per request
for something that "pulls the surfer in" more than the original honesty-statement framing.
The honesty framing itself is not lost -- it lives in the confidence badges and the
per-page honesty notes already in place, not the one-line tagline.

**New: a humorous day-summary sentence** (`web/src/daySummary.js`, new), shown at the top
of `BeachDay.jsx` above the table. Purely client-side presentational text generation --
picks the hours closest to 08:00/13:00/19:00 local from the day's already-fetched,
already-scored rows, phrases each one's existing `quality_verdict` (kept as the English
wire identifier everywhere else) through a new Hebrew humor dictionary distinct from
`labels.jsx`'s plain badge labels, and separately calls out the day's peak hour BY TIME
only when it's actually good (`quality_score >= 6.0` -- "worth reporting" per the request,
not just the best of a mediocre day). Never recomputes or overrides the verdict/score
themselves, only picks which already-computed hours to talk about and how.

Verified: backend suite unaffected (112/112 -- board/body-reference relabelling required no
production logic change, only the two test assertions noted above), clean production
frontend build. Same standing caveat as every frontend entry above: not click-tested in an
actual browser, including the RTL chart mirror and the bidi fix -- both are exactly the
kind of thing that's easy to get subtly wrong without visual confirmation, so these are
worth a deliberate look before trusting them fully.

## 2026-09-16 -- Humor sentence rewrite, chart headroom, wave-hero banner, email alerts

**Day-summary humor rewritten and deduplicated.** User feedback: the sentence was weak,
and repeated the same clause three times (morning/noon/evening) whenever they shared a
verdict. `web/src/daySummary.js` now groups ADJACENT periods that share a verdict into one
clause ("בבוקר ובצהריים שטוח לגמרי, ובערב טוב") instead of always listing three, and
collapses to one dedicated whole-day sentence when all three agree, using a separate
`DAY_MOOD` phrasing set rather than an awkward "בבוקר ובצהריים ובערב X." Also rewrote the
phrases themselves and the peak call-out for more voice.

**Graph fixed: headroom, distortion, RTL.** Three real problems, one user report:
- "Too stretched, values go out of view" -- the previous version mapped the actual data max
  directly to the top pixel of the plot area, so a peak point (and its number, drawn ABOVE
  the point) had nowhere to go and visually clipped or collided with the day-name row.
  Fixed by introducing `LABEL_HEADROOM` (reserved space above the plot) and scaling the
  height axis's domain to 1.25x the real max (not the exact max) -- the tallest point on
  the chart now always sits below the very top of the drawable area, satisfying the
  explicit ask ("the highest value shouldn't be the highest point on the board it's drawn
  on") directly rather than by accident.
- Visual distortion from `preserveAspectRatio="none"` scaling x and y by different factors
  (the container's real width varies, the CSS height was fixed) -- added
  `vector-effect="non-scaling-stroke"` to every stroked/circular element so line width and
  the round peak markers stay visually correct regardless of the non-uniform scale, and
  picked a WIDTH/HEIGHT ratio closer to the chart's typical real on-screen proportions so
  what distortion remains is smaller.
- RTL: caught in the same report as a related but separate bug -- an `<svg>` does not
  auto-mirror its own coordinate space under `dir="rtl"` the way flex/grid layouts do, so
  the x-axis was running left-to-right (today on the left) inside an otherwise fully RTL
  page. One-line fix to the `x(i)` mapping, noted in more detail in the entry above.

**New wave-hero banner** (`web/src/components/WaveHero.jsx`) on each beach's own page:
beach name + today's date, centred, inside a simple blue rounded banner with a wave-shaped
bottom edge (one decorative SVG path cut into the bottom of the rectangle -- not a
functional chart, purely visual), replacing the plain `<h2>` that was there before.

**Email alerts -- both the immediate blocker and a real feature.** User hit "שרת ההתראות
עדיין לא הוגדר (חסר מפתח VAPID)" trying to use the watch button, and asked to be able to
receive alerts by email. Two separate things:

1. **The immediate VAPID error is fixed.** Ran the project's own
   `scripts/alerting/generate_vapid_keys.py` (round-trips through `pywebpush`'s own loader
   before printing, so a key it produces is guaranteed to load) and populated
   `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY` in the local `.env` (never committed -- hard rule
   4). `GET /push-config` now returns a real key; Web Push itself works as soon as
   notification permission is granted in a real browser.
2. **Email as a genuinely new, opt-in second delivery channel**, asked directly which
   sending mechanism to build against (a real external-service choice, not something to
   guess at) -- Gmail SMTP with an app password, chosen for zero signup cost against
   credentials the user already has. New `app/alerting/email.py::send_email`, plain stdlib
   `smtplib` + STARTTLS on port 587, no new dependency. New nullable `email` column on both
   `Subscription` and `SlotWatch` (opt-in per subscription/watch, not a global account
   setting -- this project still has no real user accounts, only the existing opaque
   `user_id`). Wired into both delivery paths (`app/alerting/slot_watch.py`'s `_deliver`,
   `app/alerting/runner.py`'s subscription flow) ALONGSIDE push, not instead of it -- a
   watch/subscription with an email set gets both channels; one channel being unconfigured
   (blank `smtp_password`, same degrade-and-log pattern as blank VAPID keys) never blocks
   the other, per hard rule 7. Frontend: `identity.js` gained `getUserEmail`/`setUserEmail`
   (localStorage, parallel to the existing `getUserId`), a new email field in
   `SubscriptionForm.jsx`'s Alerts tab that also applies to future watches created from
   `BeachDay.jsx`. New `tests/test_email.py` (missing-credentials degradation, a real send
   with SMTP mocked, a send failure degrading rather than raising).

**Still needs the user's own action to actually send email**: `SMTP_USER`/`SMTP_PASSWORD`
in `.env` are blank by default (a real Gmail address + a 16-character app password from
Google Account -> Security -> App passwords) -- until filled in, email delivery degrades
silently with a logged warning, same as push did before the VAPID fix above.

115 tests passing. Clean production frontend build; same standing caveat as every frontend
entry above about not being click-tested in an actual browser.

## 2026-09-29 -- Scheduled ingestion silently skipped runs after the dev machine slept

User asked "refresh the data, it's supposed to do that by itself no?" after data had gone
stale multiple times across the week despite `app/scheduler.py` running an interval job
every `INGESTION_SCHEDULE_MINUTES` (180). It was, and the schedule itself was never the
problem -- confirmed from logs it fired correctly every 3h across a full day when the
machine stayed on (2026-09-27 13:28 -> 2026-09-28 13:28, one run each interval).

Root cause was APScheduler's default misfire handling, not a crash or a stopped process.
When the host machine sleeps, the container process freezes with it -- wall-clock time
passes but no CPU time does. On wake, APScheduler sees the interval's fire time is long
past, logs `"Run time of job ... was missed by 0:32:51"`, and -- because no
`misfire_grace_time` was set (APScheduler's tiny default grace window is always blown by a
multi-hour sleep) -- **skips that run entirely** and reschedules for the next interval
boundary, which can be hours further out still. Confirmed directly in the logs: ingestion
went silent for ~16.5h overnight (2026-09-28 15:28 -> 2026-09-29 08:00), and the very next
scheduled ingestion attempt was itself skipped too (`"missed by 0:32:51"`, rescheduled to
10:28), leaving the app stale until a manual trigger.

Fixed with two changes to `start_scheduler()` (`app/scheduler.py`), both judgement calls
appropriate for a single-instance dev deployment, not a clustered production one:

- `misfire_grace_time=None` on both jobs -- disables the grace-window check entirely, so a
  job that wakes up late runs immediately instead of silently skipping to the next boundary.
  Safe here because there is exactly one worker process; the same setting on a multi-worker
  deployment could cause a thundering-herd of simultaneous catch-up runs, which is not this
  project's shape (PROMPT.md, single dev deployment).
- `next_run_time=datetime.now(UTC)` on the ingestion job's `add_job()` call -- also fires
  once immediately on every process start (container create/recreate, not just restart),
  rather than waiting a full first interval before the app has any data at all.

Verified: rebuilt and recreated the `api` container, confirmed in logs that ingestion fired
within the same second the scheduler started (`"Running job \"_ingestion_job\" ... (scheduled
at 2026-09-29 09:03:46...)"`, immediately followed by `"forecast ingestion run complete"`),
`/health` returned to `"ok"` unprompted, and the full 115-test suite still passes (this
touches only scheduler wiring, no test exercises `start_scheduler()` directly).
