"""Decisive go/no-go: chronological split WITHIN deployment 9 (the only healthy,
substantial data), fitting corrections that target the range-compression structure
seen consistently in both deployments.

Deployment 8 is excluded from training: 36.6% instrument recovery, and its apparent
+0.133 m overall bias is not reproduced on healthy data, so it is most likely a
selection artifact of acoustic-surface-tracking failure rather than model error.

All corrections are keyed on MODEL height -- the only thing known at prediction time.
"""
import numpy as np
import pandas as pd

m = pd.read_parquet("data/processed/116859_hourly.parquet").rename(
    columns={"observed_at": "valid_at"})
f = pd.read_parquet("data/processed/openmeteo_deeplev_dep9.parquet")
df = f.merge(m, on="valid_at", how="inner")
df = df[df.hm0_m.notna()].sort_values("valid_at").reset_index(drop=True)

cut = df.valid_at.quantile(0.6)
train, test = df[df.valid_at <= cut], df[df.valid_at > cut]
assert train.valid_at.max() < test.valid_at.min()
print(f"TRAIN n={len(train)}  {train.valid_at.min()} -> {train.valid_at.max()}")
print(f"TEST  n={len(test)}  {test.valid_at.min()} -> {test.valid_at.max()}")
print(f"chronological, no overlap\n")

# --- fits on TRAIN only ---
const = (train.wave_height - train.hm0_m).mean()
b, a = np.polyfit(train.wave_height, train.hm0_m, 1)
# quadratic, to let the correction bend with height rather than only tilt
q = np.polyfit(train.wave_height, train.hm0_m, 2)

EDGES = [0, 0.4, 0.7, 1.0, 1.5, 2.0, 2.5, 3.5, 99]
train_bin = pd.cut(train.wave_height, EDGES)
binned = (train.wave_height - train.hm0_m).groupby(train_bin, observed=True).mean()
counts = train_bin.value_counts().sort_index()
print("binned offsets fitted on train (model - measured, by MODEL height):")
for k in binned.index:
    print(f"  {str(k):14s} n={counts[k]:5d}  offset={binned[k]:+.3f} m")
print(f"\nlinear    : measured = {a:.4f} + {b:.4f} * model")
print(f"quadratic : measured = {q[2]:.4f} + {q[1]:.4f}*m + {q[0]:.4f}*m^2")
print(f"constant  : {const:+.4f} m")

def report(pred, truth, label, base=None):
    e = pred - truth
    mae, rmse = e.abs().mean(), np.sqrt((e ** 2).mean())
    row = {"model": label, "bias": e.mean(), "MAE": mae, "RMSE": rmse}
    if base:
        row["MAE %chg"] = round((mae - base[0]) / base[0] * 100, 1)
        row["RMSE %chg"] = round((rmse - base[1]) / base[1] * 100, 1)
    return row

base_e = test.wave_height - test.hm0_m
base = (base_e.abs().mean(), np.sqrt((base_e ** 2).mean()))
test_off = pd.cut(test.wave_height, EDGES).map(binned).astype(float).fillna(const)

rows = [
    report(test.wave_height, test.hm0_m, "baseline (raw model)"),
    report(test.wave_height - const, test.hm0_m, "constant offset", base),
    report(a + b * test.wave_height, test.hm0_m, "linear", base),
    report(np.polyval(q, test.wave_height), test.hm0_m, "quadratic", base),
    report(test.wave_height - test_off, test.hm0_m, "binned by model height", base),
]
print(f"\n=== OUT-OF-SAMPLE ON HELD-OUT TAIL OF DEPLOYMENT 9 (n={len(test)}) ===")
print(pd.DataFrame(rows).set_index("model").round(4).to_string())

print(f"\n=== MAE by measured regime (does it help where surf happens?) ===")
test = test.copy()
test["regime"] = pd.cut(test.hm0_m, [0, 0.5, 1.0, 1.5, 2.5, 99],
                        labels=["flat <0.5", "small 0.5-1", "rideable 1-1.5",
                                "good 1.5-2.5", "big >2.5"])
out = []
for name, g in test.groupby("regime", observed=True):
    go = pd.cut(g.wave_height, EDGES).map(binned).astype(float).fillna(const)
    out.append({"regime": name, "n": len(g),
                "baseline": (g.wave_height - g.hm0_m).abs().mean(),
                "quadratic": (np.polyval(q, g.wave_height) - g.hm0_m).abs().mean(),
                "binned": (g.wave_height - go - g.hm0_m).abs().mean()})
print(pd.DataFrame(out).set_index("regime").round(3).to_string())
