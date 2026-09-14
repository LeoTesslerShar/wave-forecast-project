# Bias analysis — Open-Meteo marine model vs DeepLev measurements

First pass, 2026-09-13. Produced by the Step 0.5 spike, before Phase 1 exists.
Reproduce with the scripts in `scripts/deeplev/` (see *Reproducing* at the end).

**Read the verdict at the bottom before quoting any number from this document.**

---

## What is being compared

| | |
|---|---|
| Model | Open-Meteo marine archive `wave_height`, at 33.04 N, 34.46 E — the grid cell containing the DeepLev mooring (~2 km from it) |
| Measured | DeepLev `Height_Hm0`, significant wave height, subsurface ADCP at ~30 m in ~1470 m water, 50 km off Haifa |
| Sign convention | **error = model − measured.** Positive means the model over-predicts. |
| Pairing | Exact hour match. DeepLev samples at a constant 512 s past the hour; rounded to nearest hour, so the pairing is unambiguous. |

**This measures model-vs-reality bias, not forecast error.** The Open-Meteo archive returns
one analysis-like value per hour, not a forecast issued with a lead time — no such archive
exists (`docs/DATA_SOURCES.md`). Real forecast error at 24–72 h lead will be substantially
larger than anything below, and is not measurable until live accumulation starts.

Like is compared with like: model significant height against measured Hm0. Hmax is never
compared against model wave height — different quantities.

## Data quality — the first real finding

| Deployment | Period | Records | Valid Hm0 | Recovery | Pairs overlapping Open-Meteo |
|---|---|---|---|---|---|
| 7 (`105557.nc`) | 27 Oct 2020 – 3 Nov 2021 | 8,921 | 8,791 | 98.5% | **787** (archive starts Oct 2021) |
| 8 (`105561.nc`) | 27 Dec 2021 – 30 Aug 2022 | 5,905 | 2,162 | **36.6%** | 2,162 |
| 9 (`116859.nc`) | 23 Feb 2023 – 5 Mar 2024 | 9,008 | 8,212 | **91.2%** | 8,212 |

**Total usable pairs: 11,161.** Deployment 7 is healthy but mostly predates the Open-Meteo
archive, so only its last five weeks are usable. Deployments 1–6 (Nov 2016 – Sep 2020) have
no operational-model overlap at all; only ERA5-Ocean reanalysis covers that era, which is
not what the product would serve.

Deployment 8 is badly degraded, as the ESSD paper warned. `QI == 4` and
`Status_AST_Loss_High == 1` coincide exactly with the missing Hm0 — the acoustic surface
tracking failed on 63% of records — and there is one continuous 53-day outage. Fill value
is `-9.0`, not NaN; reading the file naively would silently treat `-9 m` waves as data.

This is not a cosmetic difference, and it drives the whole analysis (see below).

## Per-deployment agreement

| | Dep 7 (n=787) | Deployment 8 (n=2,162) | Deployment 9 (n=8,212) |
|---|---|---|---|
| Measured mean | 0.782 m | 0.960 m | 0.857 m |
| Model mean | 0.839 m | 1.093 m | 0.852 m |
| **Bias** | +0.057 m | **+0.133 m** | **−0.004 m** |
| MAE | 0.107 m | 0.255 m | 0.119 m |
| RMSE | 0.135 m | 0.441 m | 0.173 m |
| Correlation | 0.916 | 0.862 | **0.973** |
| Scatter index | 0.173 | 0.459 | **0.201** |

Deployments 7 and 9 — the two with healthy instruments — both show small bias and low
scatter. Deployment 8, the degraded one, is the outlier on every metric.

On the healthiest deployment (9) the model is **essentially unbiased** — 4 mm mean error — with a
scatter index of 20%, which is a normal-to-good result by published wave-model validation
standards. The apparent +0.133 m bias in deployment 8 is almost certainly a **selection
artifact** of the failing instrument, not a property of the model: it does not reproduce on
good data, and the 36.6% of records that survived AST failure are unlikely to be a
representative sample of sea states.

**Consequence: deployment 8 must not be used as training data.** Doing so was tested
directly and produced actively harmful corrections (below).

## The real signal: range compression

Bias by measured height regime, all three deployments:

| Regime | Dep 7 bias (n) | Dep 8 bias (n) | Dep 9 bias (n) |
|---|---|---|---|
| flat < 0.5 m | +0.103 (151) | +0.261 (602) | +0.086 (2,553) |
| small 0.5–1 m | +0.079 (478) | +0.163 (835) | +0.021 (3,516) |
| rideable 1–1.5 m | −0.030 (137) | +0.098 (387) | −0.065 (1,224) |
| good 1.5–2.5 m | −0.178 (21, thin) | +0.033 (258) | −0.207 (654) |
| **big > 2.5 m** | — | **−0.642 (80)** | **−0.432 (265)** |

Same monotonic pattern in all three, on independent data spanning 2021 to 2024: **the model
over-predicts small seas and under-predicts big ones — it compresses the range.** At the
top end it is reading 2.95 m when reality is 3.38 m.

This is a known wave-model signature, and it **independently reproduces the ESSD paper's
own CMEMS-WAM comparison**, which found "model underestimation of high waves." Agreement
with peer-reviewed prior art is the main reason to trust this pipeline.

Direction shows no comparable structure on healthy data — sector biases on deployment 9
range only −0.085 to +0.060 m, with the dominant W (n=2,793) and NW (n=1,689) sectors at
−0.034 and −0.000. The planning doc's hypothesis that bias depends strongly on swell
direction is **not supported here**. Height regime is the axis that matters.

## Does correcting it actually work?

### Test 1 — train on deployment 8, test on deployment 9: **failed**

201-day physical gap between the two, so leakage is impossible. Every correction made
things worse on the 8,212-record test set:

| Correction | MAE change | RMSE change |
|---|---|---|
| constant offset | **+30.6%** | +27.9% |
| linear | +27.8% | +29.3% |
| binned by model height | +26.2% | +32.1% |

Confirms the deployment-8 bias is an artifact. A correction fitted to it encodes the
instrument's failure mode and damages good forecasts.

### Test 2 — chronological split within deployment 9: **works, modestly**

Train Feb–Sep 2023 (n=4,927), test Sep 2023 – Mar 2024 (n=3,285). Corrections keyed on
**model** height — the only thing known at prediction time.

Fitted: `measured = −0.153 + 1.185 × model`. **Slope 1.185 > 1** — exactly the range
expansion needed to undo the compression.

| Correction | bias | MAE | RMSE | MAE change | RMSE change |
|---|---|---|---|---|---|
| baseline (raw model) | −0.022 | 0.1306 | 0.1908 | — | — |
| constant offset | −0.029 | 0.1300 | 0.1917 | −0.5% | +0.5% |
| **linear** | +0.001 | 0.1214 | 0.1697 | **−7.0%** | **−11.1%** |
| quadratic | +0.008 | 0.1220 | 0.1762 | −6.6% | −7.7% |
| **binned by model height** | +0.006 | 0.1210 | 0.1714 | **−7.3%** | **−10.2%** |

A real out-of-sample gain of ~7% MAE and ~10–11% RMSE, consistent across two independent
methods. The constant offset does nothing, as expected when mean bias is already zero.

### Where the gain actually lands — the part that matters for surf

MAE by measured regime on the held-out test set:

| Regime | n | baseline | binned correction | change |
|---|---|---|---|---|
| flat < 0.5 m | 994 | 0.104 | 0.073 | **−30%** |
| small 0.5–1 m | 1,180 | 0.079 | 0.090 | +14% |
| rideable 1–1.5 m | 586 | 0.137 | 0.161 | **+18%** |
| good 1.5–2.5 m | 342 | 0.212 | 0.221 | +4% |
| **big > 2.5 m** | 183 | 0.432 | 0.264 | **−39%** |

The correction helps a lot at both extremes and **hurts in the 0.5–1.5 m middle** — which
includes the everyday rideable band. The headline −7% conceals both effects. Any
implementation must either accept that trade or apply the correction only outside the
mid-range, and must justify the choice explicitly.

## Verdict

**The project's founding premise is only partly supported, and the honest version of the
story is different from the one in the planning doc.**

1. The planning doc's opening claim — "the forecast says 1.5 m, the actual measured height
   is 1.1 m" — **does not hold at this location**. Open-Meteo is good: correlation 0.973,
   mean bias ~0, MAE 0.12 m against 8,212 hours of quality-controlled deep-water
   measurement. There is no large systematic offset to remove.
2. **There is** a real, reproducible, physically-recognised bias: range compression.
   Over-predicts flat, under-predicts big. Confirmed on two independent deployments and
   consistent with published literature.
3. Correcting it beats the raw baseline out-of-sample by ~7% MAE / ~11% RMSE. Modest in
   absolute terms — the mean gain is under 1 cm — but **concentrated where it counts: 39%
   MAE reduction above 2.5 m**, and it costs accuracy in the mid-range.
4. So the defensible pitch is not "surf apps show you wrong numbers and we fix them." It is
   **"the model is accurate on average but systematically flattens the extremes, and the
   extremes are exactly what a surfer plans around."** That is a smaller claim, and a true
   one.

**Go/no-go for the calibration layer: GO, with reduced ambition and an honest headline.**
Worth building, worth labelling precisely, not worth overselling.

## What this means for the product

This analysis is the reason the system described in `PROMPT.md` looks different from
`docs/PLANNING.md`'s original plan. Concretely:

- **No bias-correction layer was built.** There is nothing to correct in the 0.5-1.5 m band
  a real surfer cares about. Building one anyway would mean presenting a heuristic as
  validated -- exactly what hard rule 1 forbids.
- **The miss-rate finding (13-21% of sessions missed at the top of the range) became a
  threshold calibration, not a height correction.** See `prompts/phase-4-alerting.md`
  section 6: the user picks an operating point (`strict`/`balanced`/`generous`) trading
  false alarms for caught sessions, using the real GO/DON'T-GO numbers above. The displayed
  height is never adjusted by this -- only which forecasts trigger an alert.
- **The measured spread (roughly +/-0.19-0.25 m, 90% interval) sets a floor on how narrow
  any displayed range may be.** No downstream heuristic (beach exposure, quality scoring)
  may present a number more precise than this without its own evidence.
- **Beach exposure (`prompts/phase-2-exposure.md`) and surf quality (`prompts/phase-3-quality.md`,
  wind + chop ratio) became the main technical work**, since offshore height itself carries
  little remaining signal to extract in the range that matters.

## Limitations

- **One location.** DeepLev is 50 km off Haifa. Applying this correction 150 km south off
  Ashdod assumes regionally coherent model bias — plausible for open-coast deep water in
  one basin, unverified.
- **Analysis, not forecast.** The archived value has no lead time. Real 24–72 h forecast
  error will be much larger than 0.12 m, and bias correction may matter considerably more
  there than these numbers suggest. Unmeasurable until live accumulation runs — a strong
  argument for starting Phase 1 promptly.
- **Train and test share a deployment** in test 2 — same instrument, same configuration.
  Weaker than a cross-deployment result, which the data does not currently support.
- **Staleness.** Data ends March 2024; today is September 2026. The model may have changed.
- **Deep water is not the surf break.** This validates the offshore layer only. The
  per-beach translation stays unvalidated, permanently.
- **Deployment 7** contributes only 787 pairs (five weeks); it confirms the regime pattern
  but is too short to train on, and its `good 1.5–2.5 m` cell (n=21) is below the reporting
  threshold.

## Reproducing

```
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install xarray netCDF4 pandas pyarrow
# download deployments to data/raw/ (gitignored) from
#   https://www.seanoe.org/data/00857/96904/data/{105557,105561,116859}.nc
.venv/Scripts/python.exe scripts/deeplev/extract.py     data/raw/116859.nc
.venv/Scripts/python.exe scripts/deeplev/fetch_model.py 2023-02-23 2024-03-05 \
    data/processed/openmeteo_deeplev_dep9.parquet
.venv/Scripts/python.exe scripts/deeplev/bias.py \
    data/processed/116859_hourly.parquet data/processed/openmeteo_deeplev_dep9.parquet
.venv/Scripts/python.exe scripts/deeplev/split_test.py
```

## Attribution

Wave measurements: Haim Nir, Toledo Yaron, Mayzel Boaz, Grigorieva Vika, Soffer Rotem,
Katz Timor, Alkalay Ronen, Biton Eli, Lazar Ayah, Gildor Hezi, Berman-Frank Ilana,
Weinstein Yishai, Herut Barak (2016). *Surface waves data from a submerged ADCP in the
"DeepLev" Eastern Levantine station.* SEANOE. https://doi.org/10.17882/96904 (CC BY 4.0)

Forecast/analysis data: Open-Meteo marine API (CC BY 4.0), derived from DWD and partner
wave models.
