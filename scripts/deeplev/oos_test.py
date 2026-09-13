"""Out-of-sample test: fit a bias correction on deployment 8, evaluate on deployment 9.

The two deployments are separated by a ~6-month gap during which the instrument was
not in the water (30 Aug 2022 -> 23 Feb 2023), so leakage across the split is
structurally impossible, not merely asserted.

CRITICAL: corrections are keyed on MODEL height, never on measured height. The
measured value is unknown at prediction time; binning on it would produce a
correction that cannot be applied in production and an inflated score.
"""
import numpy as np
import pandas as pd

def load(meas, model):
    m = pd.read_parquet(meas).rename(columns={"observed_at": "valid_at"})
    f = pd.read_parquet(model)
    df = f.merge(m, on="valid_at", how="inner")
    return df[df.hm0_m.notna()].copy()

def metrics(pred, truth, label):
    e = pred - truth
    return {"model": label, "n": len(e), "bias": e.mean(),
            "MAE": e.abs().mean(), "RMSE": np.sqrt((e ** 2).mean())}

train = load("data/processed/105561_hourly.parquet",
             "data/processed/openmeteo_deeplev_dep8.parquet")
test = load("data/processed/116859_hourly.parquet",
            "data/processed/openmeteo_deeplev_dep9.parquet")

print(f"TRAIN (deployment 8): n={len(train)}  {train.valid_at.min()} -> {train.valid_at.max()}")
print(f"TEST  (deployment 9): n={len(test)}  {test.valid_at.min()} -> {test.valid_at.max()}")
assert train.valid_at.max() < test.valid_at.min(), "CHRONOLOGY VIOLATED"
gap = (test.valid_at.min() - train.valid_at.max()).days
print(f"gap between train end and test start: {gap} days -- no leakage possible")

# ---- fit on TRAIN only -------------------------------------------------
const = (train.wave_height - train.hm0_m).mean()

b, a = np.polyfit(train.wave_height, train.hm0_m, 1)   # measured ~ a + b*model

EDGES = [0, 0.5, 1.0, 1.5, 2.0, 3.0, 99]
train["mbin"] = pd.cut(train.wave_height, EDGES)
binned = (train.wave_height - train.hm0_m).groupby(train.mbin, observed=True).mean()

print(f"\nfitted on train:")
print(f"  constant offset : {const:+.3f} m")
print(f"  linear          : measured = {a:.3f} + {b:.3f} * model")
print(f"  binned offsets by MODEL height:")
for k, v in binned.items():
    n = (train.mbin == k).sum()
    print(f"    {str(k):14s} n={n:5d}  offset={v:+.3f} m")

# ---- apply to TEST -----------------------------------------------------
test["mbin"] = pd.cut(test.wave_height, EDGES)
test_binned_off = test.mbin.map(binned).astype(float).fillna(const)

rows = [
    metrics(test.wave_height, test.hm0_m, "baseline (raw model)"),
    metrics(test.wave_height - const, test.hm0_m, "constant offset"),
    metrics(a + b * test.wave_height, test.hm0_m, "linear"),
    metrics(test.wave_height - test_binned_off, test.hm0_m, "binned by model height"),
]
r = pd.DataFrame(rows).set_index("model").round(4)
base_mae, base_rmse = r.loc["baseline (raw model)", ["MAE", "RMSE"]]
r["MAE %chg"] = ((r.MAE - base_mae) / base_mae * 100).round(1)
r["RMSE %chg"] = ((r.RMSE - base_rmse) / base_rmse * 100).round(1)

print(f"\n=== OUT-OF-SAMPLE RESULTS ON DEPLOYMENT 9 (n={len(test)}) ===")
print(r.to_string())

# Does it help where it matters for surf? Split by measured regime.
print(f"\n=== MAE by measured regime: baseline vs best correction ===")
test["regime"] = pd.cut(test.hm0_m, [0, 0.5, 1.0, 1.5, 2.5, 99],
                        labels=["flat <0.5", "small 0.5-1", "rideable 1-1.5",
                                "good 1.5-2.5", "big >2.5"])
out = []
for name, g in test.groupby("regime", observed=True):
    gb = g.mbin.map(binned).astype(float).fillna(const)
    out.append({
        "regime": name, "n": len(g),
        "baseline MAE": (g.wave_height - g.hm0_m).abs().mean(),
        "linear MAE": (a + b * g.wave_height - g.hm0_m).abs().mean(),
        "binned MAE": (g.wave_height - gb - g.hm0_m).abs().mean(),
    })
print(pd.DataFrame(out).set_index("regime").round(3).to_string())
