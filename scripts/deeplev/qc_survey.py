"""Survey time coverage, QC flags and value ranges before deciding an extraction policy."""
import sys
import numpy as np
import pandas as pd
import xarray as xr

ds = xr.open_dataset(sys.argv[1], decode_timedelta=False)
t = pd.to_datetime(ds["time"].values)

print("=== TIME ===")
print(f"  n={len(t)}  first={t.min()}  last={t.max()}")
d = pd.Series(t).diff().dt.total_seconds().dropna()
print(f"  step seconds: median={d.median():.0f} min={d.min():.0f} max={d.max():.0f}")
print(f"  span days={(t.max()-t.min()).total_seconds()/86400:.1f}  expected hourly rows={(t.max()-t.min()).total_seconds()/3600:.0f}")

print("\n=== STATUS / QC FLAGS (count nonzero) ===")
for name in sorted(ds.data_vars):
    if name.startswith(("Status_", "SurfaceDetection_")) or name == "QI":
        v = np.asarray(ds[name].values, dtype="float64")
        nz = int(np.nansum(v != 0))
        print(f"  {name:32s} nonzero={nz:6d} ({100*nz/len(v):5.1f}%)  min={np.nanmin(v):g} max={np.nanmax(v):g}")

print("\n=== BULK PARAMETER RANGES (raw, no QC) ===")
for name in ["Height_Hm0", "Height_Hmax", "Height_H3", "Period_Tp", "Period_Tm02",
             "Direction_MeanDir", "Direction_DirTp", "Pressure", "Temperature"]:
    v = np.asarray(ds[name].values, dtype="float64")
    finite = np.isfinite(v)
    print(f"  {name:20s} finite={finite.sum():5d}/{len(v)} "
          f"min={np.nanmin(v):8.2f} p50={np.nanpercentile(v,50):8.2f} "
          f"p99={np.nanpercentile(v,99):8.2f} max={np.nanmax(v):8.2f}")
