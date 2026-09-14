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
