"""Reframe: not "how many cm is the model off" but "how often does it get the
GO / DON'T-GO call wrong" -- in the height range a surfer actually surfs.

Wasted trip   = model says GO, reality says no  (false positive)
Missed session= model says no, reality says GO  (false negative)
"""
import numpy as np
import pandas as pd

m = pd.read_parquet("data/processed/116859_hourly.parquet").rename(
    columns={"observed_at": "valid_at"})
f = pd.read_parquet("data/processed/openmeteo_deeplev_dep9.parquet")
df = f.merge(m, on="valid_at", how="inner")
df = df[df.hm0_m.notna()].copy()

print(f"n = {len(df)} hours, {df.valid_at.min().date()} -> {df.valid_at.max().date()}\n")

print("=== 1. HOW GOOD IS THE MODEL IN THE SURFABLE BAND (0.5-1.5 m measured)? ===")
band = df[(df.hm0_m >= 0.5) & (df.hm0_m <= 1.5)]
e = band.wave_height - band.hm0_m
print(f"  n={len(band)}  bias={e.mean():+.3f} m  MAE={e.abs().mean():.3f} m  "
      f"RMSE={np.sqrt((e**2).mean()):.3f} m")
print(f"  90% of errors fall within +/- {np.percentile(e.abs(), 90):.3f} m")
print(f"  fraction of hours model is within 10cm: {(e.abs() <= 0.10).mean():.1%}")
print(f"  fraction of hours model is within 20cm: {(e.abs() <= 0.20).mean():.1%}")

print("\n=== 2. GO / DON'T-GO ACCURACY at various thresholds ===")
print("   (model says >= T, reality says >= T)")
rows = []
for T in [0.6, 0.8, 1.0, 1.2, 1.5]:
    model_go = df.wave_height >= T
    real_go = df.hm0_m >= T
    tp = (model_go & real_go).sum()
    fp = (model_go & ~real_go).sum()
    fn = (~model_go & real_go).sum()
    tn = (~model_go & ~real_go).sum()
    rows.append({
        "threshold_m": T,
        "real GO hours": int(real_go.sum()),
        "model GO hours": int(model_go.sum()),
        "wasted trips %": round(100 * fp / max(model_go.sum(), 1), 1),
        "missed sessions %": round(100 * fn / max(real_go.sum(), 1), 1),
        "agreement %": round(100 * (tp + tn) / len(df), 1),
    })
print(pd.DataFrame(rows).set_index("threshold_m").to_string())

print("\n=== 3. WHEN THE MODEL SAYS ~1.0-1.2 m, WHAT IS REALITY? ===")
sel = df[(df.wave_height >= 1.0) & (df.wave_height <= 1.2)]
q = sel.hm0_m.quantile([.05, .25, .5, .75, .95]).round(2)
print(f"  n={len(sel)}   actual Hm0 percentiles:")
print(f"    5%={q[.05]}  25%={q[.25]}  median={q[.5]}  75%={q[.75]}  95%={q[.95]}")
print(f"  -> when the app says '1.0-1.2m', reality is between "
      f"{q[.05]} and {q[.95]} m 90% of the time")

print("\n=== 4. WAVE PERIOD -- drives surf QUALITY at small sizes ===")
pe = df[df.tp_s.notna()]
err_tp = pe.wave_period - pe.tp_s
print(f"  peak period  n={len(pe)}  bias={err_tp.mean():+.2f} s  MAE={err_tp.abs().mean():.2f} s")
pm = df[df.tm02_s.notna()]
err_tm = pm.wave_period - pm.tm02_s
print(f"  (model wave_period vs measured Tm02: bias={err_tm.mean():+.2f} s "
      f"MAE={err_tm.abs().mean():.2f} s -- different definitions, shown for context)")

print("\n=== 5. HOW OFTEN IS IT EVEN SURFABLE OFF ISRAEL? ===")
for T in [0.5, 0.8, 1.0, 1.5, 2.0]:
    print(f"  measured Hm0 >= {T} m : {100*(df.hm0_m >= T).mean():5.1f}% of hours")
df["month"] = df.valid_at.dt.month
season = df.groupby("month").apply(
    lambda g: pd.Series({"n": len(g), "% >=1.0m": round(100*(g.hm0_m >= 1.0).mean(), 1),
                         "mean Hm0": round(g.hm0_m.mean(), 2)}), include_groups=False)
print("\n  by month:")
print(season.to_string())
