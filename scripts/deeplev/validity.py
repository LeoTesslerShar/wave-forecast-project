"""Quantify how much of the file is real data vs the -9 fill sentinel."""
import sys
import numpy as np
import pandas as pd
import xarray as xr

ds = xr.open_dataset(sys.argv[1], decode_timedelta=False)
t = pd.to_datetime(ds["time"].values)
FILL = -9.0

def col(n):
    return np.asarray(ds[n].values, dtype="float64")

print("=== VALID (!= -9) COUNTS ===")
for name in ["Height_Hm0", "Height_Hmax", "Height_H3", "Period_Tp", "Period_Tm02",
             "Period_Tz", "Direction_MeanDir", "Direction_DirTp"]:
    v = col(name)
    ok = np.isclose(v, FILL) == False
    print(f"  {name:20s} valid={ok.sum():5d}/{len(v)} ({100*ok.mean():5.1f}%)")

hm0 = col("Height_Hm0")
valid = ~np.isclose(hm0, FILL)

print(f"\n=== QI vs Hm0 validity ===")
qi = col("QI")
for q in sorted(set(qi.astype(int))):
    m = qi.astype(int) == q
    print(f"  QI={q}: n={m.sum():5d}  Hm0 valid in {100*valid[m].mean():5.1f}%")

print(f"\n=== Status flags vs Hm0 validity ===")
for name in ["Status_Unreasonable_Estimate", "Status_AST_Loss_High",
             "Status_Low_Pressure", "Status_Direction_Ambiguity"]:
    f = col(name).astype(int)
    for val in (0, 1):
        m = f == val
        if m.sum():
            print(f"  {name}={val}: n={m.sum():5d}  Hm0 valid in {100*valid[m].mean():5.1f}%")

print(f"\n=== Hm0 where valid ===")
h = hm0[valid]
print(f"  n={len(h)} min={h.min():.2f} p50={np.percentile(h,50):.2f} "
      f"p95={np.percentile(h,95):.2f} max={h.max():.2f}")

print(f"\n=== monthly valid Hm0 (seasonality sanity check) ===")
df = pd.DataFrame({"t": t, "hm0": hm0, "valid": valid})
g = df[df.valid].groupby(df[df.valid].t.dt.to_period("M"))["hm0"]
print(g.agg(["count", "mean", "max"]).round(2).to_string())

print(f"\n=== valid-data time span ===")
tv = t[valid]
print(f"  first={tv.min()}  last={tv.max()}")
print(f"  contiguous? largest gap = {pd.Series(tv).diff().max()}")
