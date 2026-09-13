# Phase 2 — Historical alignment and bias characterisation

Read `PROMPT.md`, `docs/PLANNING.md` (§6 Phase 2), `docs/DATA_SOURCES.md`, and the Phase 1
schema first.

This phase produces a result that **stands alone even if Phase 3 is never built**: a
written, evidenced account of where the wave model is systematically wrong off the Israeli
coast. Treat it as the deliverable, not as feature engineering for the next phase.

**Updated after Phase 0's scope verdict (`docs/DATA_SOURCES.md`):** there was no historical
data to align — zero pre-existing (forecast, measurement) pairs exist anywhere. This phase
therefore runs against whatever has accumulated live since Phase 1 went live, and only
against the Hadera buoy (Ashdod/Haifa are not ingested). It is **not a one-time study** —
build it as a report that reruns on demand and grows as more history accumulates, and say
plainly, every time it runs, how much history it actually has. Early runs will have too
little data to conclude much; that is expected, not a bug to work around.

---

## 1. The join

Pair each forecast with the measurement it was predicting. Every decision here is a
judgement call that silently shapes every number downstream, so each one gets made
explicitly and written into `docs/BIAS_ANALYSIS.md`:

- **Temporal tolerance.** Forecasts are hourly on the hour; measurements may not be. State
  the matching rule (nearest measurement within ±X minutes, or hourly aggregation) and the
  X. Pairs outside tolerance are dropped, and the drop count is reported.
- **Spatial assignment.** Which buoy is ground truth for which forecast point, and on what
  basis — nearest by great-circle distance, with the distances listed. A forecast point
  200 km from its buoy is a different claim than one 15 km away; the distance travels with
  the pair as a column.
- **Parameter compatibility.** Hs vs Hmax (Phase 1 §2). If a buoy reports Hmax and the
  forecast gives significant height, **they are not comparable and must not be joined
  as-is.** Either restrict to compatible parameters, or apply a documented conversion and
  flag every row it touched. Do not quietly compare them.
- **Lead time** = `valid_at - issued_at`, computed per pair and kept as a column. If Phase 1
  had to substitute fetch time for issue time, that caveat is repeated here in the write-up,
  not buried in a decisions file.

Output: a materialised table or view of `(forecast row, measurement row, lead_time,
buoy_distance_km, parameter_type)` pairs, rebuildable with one command.

---

## 2. Characterisation

Error = forecast − measured, per pair. Report **bias (mean error, signed)** and
**dispersion (MAE, RMSE)** separately — a model that is right on average and wrong every
time is a different problem from one that is consistently 0.4 m high, and only the second
is correctable.

Break down by, at minimum:

- **swell direction bucket** (e.g. 30° bins, or the meteorological compass points);
- **season / month**;
- **height regime** (flat / small / rideable / big — pick thresholds that mean something
  for surf, and say what they are);
- **forecast lead time** (0–6 h, 6–24 h, 24–48 h, 48 h+);
- **buoy** — in practice just Hadera for now; keep the column so Ashdod/Haifa slot in
  later without a schema change.

And the interactions worth looking at: direction × height regime, lead time × height
regime. The planning doc's hypothesis is that bias depends on swell direction, season and
height regime — test it, and report if it does not hold.

**Report n for every single cell.** A 0.6 m bias computed from 4 pairs is noise wearing a
number's clothes. Cells below a stated minimum n are shown as insufficient data, not as a
value. This is the most likely way for this phase to produce a confident falsehood, so
guard it deliberately.

---

## 3. Deliverable: `docs/BIAS_ANALYSIS.md`

- Dataset description: date range, total pairs, pairs per buoy, what was dropped and why.
- The charts (matplotlib/seaborn, committed as PNGs under `docs/img/`): error distribution,
  bias by direction bucket, bias by height regime, bias by lead time, forecast-vs-measured
  scatter with the 1:1 line.
- Written findings in plain prose: what is systematically wrong, where, and by how much.
- **A limitations section.** One buoy (Hadera) only, not three — Ashdod and Haifa are
  unavailable (`docs/DATA_SOURCES.md`); Hadera's own depth and offshore distance are
  themselves unresolved, so treat its comparability to a "deep-water regional anchor" as
  unconfirmed, not assumed; the sample is only what has accumulated since Phase 1 launch,
  stated in days/weeks, not a multi-year study.
- A one-paragraph verdict, **dated**, on whether there is enough exploitable structure yet
  for a trained model (Phase 3) to be worth attempting, or whether the live bias tracker
  should keep running as the only calibration mechanism for now. Re-run this verdict each
  time the report regenerates — it should change as history accumulates.

Reproducible end to end from one command against the local DB — `docker compose run --rm
api python -m app.analysis.bias` or equivalent. No notebook-only results; if you use a
notebook to explore, the committed path is still the script.

---

## Acceptance checks

Run and paste:

1. The single rebuild command, showing pair counts and drop counts.
2. The summary table: bias, MAE, RMSE overall and per buoy, with n.
3. One breakdown table (direction buckets), with n per cell and insufficient-data cells
   visibly marked.
4. `docker compose run --rm api pytest` — including a test that the join respects the
   stated tolerance and a test that parameter-incompatible rows are excluded.

## Then stop

Report the verdict from §3 and wait. If the data does not support Phase 3, say so directly
and edit `prompts/phase-3-calibration.md` to match what is actually possible.
