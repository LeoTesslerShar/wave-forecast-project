# Phase 2 — Historical alignment and bias characterisation

Read `PROMPT.md`, `docs/PLANNING.md` (§6 Phase 2), `docs/DATA_SOURCES.md`, and the Phase 1
schema first.

This phase produces a result that **stands alone even if Phase 3 is never built**: a
written, evidenced account of where the wave model is systematically wrong off the Israeli
coast. Treat it as the deliverable, not as feature engineering for the next phase.

**Updated after the Phase 0 correction (`docs/DATA_SOURCES.md`):** this is a real
historical study, on real data. Ground truth is **DeepLev** — roughly 21 months overlapping
the Open-Meteo archive, about 15,000 hourly pairs across two full winters (deployments 7,
8, 9). Hadera is an optional supplementary station, tiny by comparison; Ashdod/Haifa remain
unavailable.

Two things this phase measures, which must not be conflated:

- **Model-vs-reality bias** — what DeepLev supports. The archived Open-Meteo value is one
  analysis-like value per `valid_at`, not a forecast issued with a lead time. This is the
  bulk of the stage-1 claim and it is fully analysable today.
- **Forecast error growth with lead time** — *not* obtainable historically. Open-Meteo has
  no forecast-as-issued archive (tested directly). This dimension only becomes available
  from live accumulation after Phase 1 goes live, so report it as pending, not as zero.

Build it so it reruns on demand: the DeepLev portion is static and will not change, but the
live-accumulated portion grows, and the lead-time section fills in over time.

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
- **station** — DeepLev for the historical study; keep the column so Hadera and, if access
  is ever granted, Ashdod/Haifa slot in without a schema change. Never pool stations into a
  single bias number without showing the per-station split: they are different instruments
  at different depths and distances offshore.

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
- **A limitations section.** DeepLev sits 50 km off *Haifa* — applying its correction
  150 km south off Ashdod assumes the model's bias is regionally coherent, which is
  defensible for open-coast deep water in one basin but is an assumption, not a result.
  Coverage ends March 2024, so the correction may be stale against a model that has since
  changed. A submerged ADCP is not a surface-following waverider. Deployment 8 has
  documented data loss. And deep water is not the surf break: this validates the *offshore*
  layer only — the per-beach translation in Phase 4 stays unvalidated regardless of how good
  these numbers look.
- A one-paragraph verdict on whether there is exploitable structure for Phase 3, and which
  features look predictive. Also **cross-check against prior art**: the DeepLev ESSD paper
  compared these same observations against CMEMS-WAM and found strong Hs correlation, a
  negative mean-period bias, and model underestimation of high waves. If our findings
  disagree sharply with a peer-reviewed comparison, the default assumption is that ours are
  wrong — investigate before publishing the disagreement.

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
