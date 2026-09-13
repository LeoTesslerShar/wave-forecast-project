# Phase 3 — Calibration model

Read `PROMPT.md`, `docs/PLANNING.md` (§6 Phase 3), `docs/DATA_SOURCES.md`, and
`docs/BIAS_ANALYSIS.md` first.

**Superseded by the Phase 0 correction: build the trained model in section B. It is the
main event, not a deferred one.** DeepLev gives roughly 15,000 hourly (model, measured)
pairs across two full winters, which is enough to train and validate properly
(`docs/DATA_SOURCES.md`).

Section A (the live bucketed bias tracker) is still built, but its role has changed: it is
no longer a substitute for a model, it is the **staleness check on one**. DeepLev coverage
ends March 2024 and today is 2026 — the tracker is what tells you whether a correction
trained on 2021-24 data still holds against the model as it behaves now. Build B, then A,
and have A report drift against B.

**One dimension stays out of the model:** lead time. Open-Meteo has no forecast-as-issued
archive (tested directly), so historical pairs have no meaningful lead-time spread. Do not
put lead time in the historical feature set — it would be a constant wearing a variable's
name. It enters only once live accumulation provides it.

Hard rule 2 governs this entire phase: the baseline is the raw uncorrected forecast, and
whatever the comparison says is what gets reported.

---

## A. Live bias tracker — the staleness check on section B

As Phase 1 accumulates forecasts and Hadera measurements, continuously compute and store
running bias by direction bucket, height regime and lead time (same bucket definitions as
Phase 2). Serve the bucketed correction from it once a bucket passes a stated minimum n,
falling back to raw below that threshold — this reuses hard rule 7's degrade-gracefully
pattern: a thin bucket is a degraded-data condition, not an error.

- A `calibrate()` path used by the forecast API: look up the bucket for the current
  forecast's direction/height/lead-time, apply its running bias correction if n is
  sufficient, else pass the raw value through unchanged.
- **Every response carries `method`** — `"bucket_corrected"` when a correction was applied,
  `"raw"` when it fell back — plus the bucket's current n and the correction applied, so a
  caller can see exactly what happened to the number (hard rule 1).
- `docs/CALIBRATION_RESULTS.md`: current bucket table (bias, n, last-updated) and a
  **dated projection** of when accumulated history would plausibly support a trained
  model — tie this to Phase 2's own verdict rather than inventing a separate one.
- Update the README's headline calibration claim to match reality: "no trained model yet;
  serving a live-accumulating bucketed bias correction, described in
  docs/CALIBRATION_RESULTS.md" — not the language of a validated model.

This is a legitimate, complete outcome for this phase — not a stopgap to apologize for. It
is also a more honest system than a model fitted to a handful of pairs would be.

### Acceptance checks for section A

Run and paste:

1. Bucket table output showing bias, n, and last-updated per bucket, however sparse it
   is today.
2. An API response showing `method: "bucket_corrected"` for a bucket with enough data.
3. The same endpoint, or a different bucket, showing `method: "raw"` with the reason
   (bucket n below threshold) stated in the response.
4. `docker compose run --rm api pytest`.

## Then stop

Report both: the trained model's test-set performance against baseline (section B), and the
live tracker's current drift against it (section A). If the live drift is large, the
historical correction has gone stale and that is the headline, not a footnote.

---

## B. Trained model — build this

Train on DeepLev-derived pairs. Read `docs/BIAS_ANALYSIS.md` first for which features
actually showed structure.

## 1. Setup

- **Features:** forecast wave height, wave period, wave direction (as sin/cos, not degrees
  — 359° and 1° are adjacent, and a tree or a linear model will not know that), wind speed
  and direction, month (also cyclical), station id, and anything Phase 2 found predictive.
  **Not lead time** — see the header; historical pairs have no lead-time spread.
- **Target:** measured wave height. Period optionally, as a second model, only after height
  works.
- **Baseline:** raw forecast wave height, unmodified. Its MAE and RMSE on the test set are
  the number to beat, and they are computed first, before any model exists.

## 2. Chronological validation — enforced, not intended

A random train/test split on time series leaks the future into the past and produces a
meaningless score. The planning doc says this matters; this prompt makes it mechanical.

- Split by time: train on earlier, test on later. State the cut date and the resulting
  sizes. **The DeepLev deployments hand you a naturally clean split: train on deployments
  7-8 (to 30 Aug 2022), test on deployment 9 (23 Feb 2023 - 5 Mar 2024).** They are
  separated by a ~6-month physical gap in which the instrument was not in the water, so
  leakage across the boundary is structurally impossible rather than merely asserted. Use
  it unless there is a reason not to, and say so if you deviate.
- **Write a test that fails if `max(train.valid_at) >= min(test.valid_at)`.** It runs in
  CI. Discipline is not a safeguard; an assertion is.
- Any cross-validation uses expanding-window / forward-chaining folds, never `KFold` or
  `train_test_split` with shuffling. If `sklearn.model_selection.train_test_split` appears
  anywhere in this phase's code, it is a bug.
- Watch for leakage through the back door too: features computed over the full dataset
  (global means, scalers fitted before splitting) leak just as effectively as a bad split.
  Fit every transform inside the training fold.

## 3. Models

In this order, reporting each:

1. **Constant bias correction** — subtract the mean error. The dumbest possible correction.
   If it captures most of the available gain, that is a finding worth stating, and it makes
   every fancier model justify itself.
2. **Linear regression** on the feature set.
3. **Gradient boosting** (LightGBM or sklearn's `HistGradientBoosting`). Tune modestly;
   hyperparameter search across a small dataset is another way to overfit the test set.

Report per-model MAE and RMSE against the baseline, plus the breakdown by height regime —
a model that improves the flat-day numbers while getting worse on the days that matter for
surfing is not an improvement for this application, and the headline average will hide it.

## 4. Results — `docs/CALIBRATION_RESULTS.md`

- The table: baseline, constant, linear, GBM × MAE, RMSE, and % change vs baseline.
- Same table broken down by height regime and by lead time.
- Feature importances / coefficients, with the caveat that importance is not causation.
- Residual plots for the chosen model.
- **The verdict in plain language**, including if it is negative. "Gradient boosting
  reduced MAE by 3% over the raw forecast, which is within the noise of a sample this size"
  is a publishable and honest result. Inflating it is the one thing this project cannot do.
- Also summarise the headline number in the README, whatever it is.

## 5. Serving

- Versioned model artefacts (joblib + a metadata JSON: training window, feature list, git
  SHA, metrics). Artefacts are gitignored; the metadata is committed.
- A `calibrate()` path used by the forecast API, returning the corrected value **plus the
  model version and a `method: "calibrated"` marker**.
- **Fallback:** no artefact loaded, a feature missing, or the model erroring → serve the
  raw forecast with `method: "raw"` and log it. Never fail the request, never silently
  serve a raw number labelled as calibrated (hard rules 1 and 7).
- A guard on input ranges: if an input falls outside the training distribution, fall back
  to raw rather than extrapolating. Say so in the response.

---

## Acceptance checks for section B

Run and paste:

1. The training run output: split dates, set sizes, and the full results table.
2. The chronological-split test passing, plus proof it actually catches a violation —
   deliberately shuffle the split and show the test failing.
3. `grep -rn "train_test_split" .` returning nothing (or only a comment explaining why not).
4. An API response showing the calibrated value with `method` and `model_version`.
5. The fallback: remove the artefact, hit the same endpoint, show `method: "raw"` and a
   200 response.
6. `docker compose run --rm api pytest`.
