# Phase 0.5 — DeepLev spike (DONE — historical record, not a task to re-run)

This phase already happened. It is kept as a prompt file because it changed the shape of
every phase after it, and a later session should understand why rather than rediscover it.
**Do not execute this phase again.** Its outputs are committed:

- `docs/BIAS_ANALYSIS.md` — the full findings
- `data/processed/*.parquet` — the derived hourly tables (1.4 MB, committed)
- `scripts/deeplev/*.py` — the extraction and analysis scripts, reproducible against the
  raw NetCDF files (not committed — 3.1 GB, gitignored, downloadable from SEANOE)

## What this phase was for

Phase 0 (`prompts/phase-0-verify.md`) concluded no historical (forecast, measurement)
pairs existed anywhere, checking only the three sources the planning doc named. That
verdict was corrected the same day (`docs/DATA_SOURCES.md`, CORRECTION section at the top):
**DeepLev**, a subsurface mooring 50 km off Haifa, publishes ~21 months of measured wave
data overlapping the Open-Meteo archive — CC BY 4.0, free, no registration.

This phase downloaded it, extracted it correctly (the fill sentinel is `-9.0`, not NaN —
reading naively would treat that as data), and tested whether the project's founding
premise — "the forecast is biased, and we can correct it" — actually held.

## What it found

**It mostly didn't hold, in the range that matters.** Full numbers in
`docs/BIAS_ANALYSIS.md`. Summary:

- In the 0.5-1.5 m band a real surfer cares about, the offshore model is already accurate:
  bias -0.001 m, MAE 0.091 m, over 4,740 measured hours.
- There IS a real, reproducible bias — the model compresses the range, over-predicting flat
  seas and under-predicting big ones (>2.5 m), confirmed across three independent
  deployments spanning 2021-2024 and matching the DeepLev paper's own published comparison
  against CMEMS-WAM.
- A naive height correction does not help in the surfable range and can actively hurt it
  (tested: training on the wrong deployment made things 26-31% worse — see the "trap" in
  `docs/BIAS_ANALYSIS.md`).
- Reframed as a GO/DON'T-GO decision instead of centimetres: at a 1.5 m alert threshold the
  model misses 20.8% of real sessions; at 1.0 m, 13.1%. That is the actionable finding.

## What changed because of it

This is the reason `PROMPT.md` section 1 and every phase prompt after this one look
different from the original plan:

- **Bias correction was dropped as a feature.** There is nothing to correct where the user
  surfs. Building it anyway would be presenting a heuristic as validated — hard rule 1 — and
  the whole point of this project is not doing that.
- **The miss-rate finding became a threshold calibration instead** — see
  `prompts/phase-4-alerting.md` section 6. Not a correction to the displayed number; a
  measured trade-off in which forecasts trigger an alert.
- **Beach exposure (`prompts/phase-2-exposure.md`) got promoted** to the main technical
  differentiator, because it's where the real remaining variance lives.
- **A new surf-quality phase was added** (`prompts/phase-3-quality.md`) — wind and chop
  ratio, which the original plan never had, and which the user identified as necessary
  after seeing the bias-correction result: a wave being the "right" height means nothing if
  the wind has turned it to mush.

## If a future session wants to extend this

- Deployment 7 has only 787 pairs overlapping the archive (5 weeks) — not usable for
  training, only as a third confirmation of the range-compression pattern.
- The gap between DeepLev's coverage ending (March 2024) and now is unmeasured. If enough
  live accumulation has happened by the time this is read, re-running the bias comparison
  against fresh data would show whether the model's behavior has drifted.
- Everything here validates the *offshore* forecast only. Nothing validates the beach-level
  translation — that remains permanently unvalidated, by design, because no ground truth
  exists at any Israeli beach.

## Reproducing (if ever needed)

```
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install xarray netCDF4 pandas pyarrow requests
# download deployments 7, 8, 9 to data/raw/ (gitignored) from
#   https://www.seanoe.org/data/00857/96904/data/{105557,105561,116859}.nc
.venv/Scripts/python.exe scripts/deeplev/extract.py     data/raw/116859.nc
.venv/Scripts/python.exe scripts/deeplev/fetch_model.py 2023-02-23 2024-03-05 \
    data/processed/openmeteo_deeplev_dep9.parquet
.venv/Scripts/python.exe scripts/deeplev/bias.py \
    data/processed/116859_hourly.parquet data/processed/openmeteo_deeplev_dep9.parquet
.venv/Scripts/python.exe scripts/deeplev/split_test.py
.venv/Scripts/python.exe scripts/deeplev/decision_quality.py
```
