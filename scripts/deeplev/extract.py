"""Extract QC'd hourly bulk wave parameters from a DeepLev NetCDF deployment file.

QC policy (derived from scripts/deeplev/validity.py output, not assumed):
  -9.0 is the fill sentinel for every bulk parameter.
  QI == 4 corresponds exactly to Hm0 fill (acoustic surface tracking loss);
  QI 1-3 are valid. We filter on the sentinel directly rather than on QI, so
  each parameter is judged on its own availability.
  Direction_* and Period_Tm02 are valid slightly less often than Height_Hm0,
  so a row can have a usable height but no usable direction. Kept as NaN
  rather than dropping the row -- height-only rows still serve the height bias.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

FILL = -9.0
VARS = {
    "Height_Hm0": "hm0_m",
    "Height_Hmax": "hmax_m",
    "Period_Tp": "tp_s",
    "Period_Tm02": "tm02_s",
    "Direction_MeanDir": "mean_dir_deg",
    "Direction_DirTp": "peak_dir_deg",
}

def extract(path):
    ds = xr.open_dataset(path, decode_timedelta=False)
    out = {"time": pd.to_datetime(ds["time"].values)}
    for src, dst in VARS.items():
        v = np.asarray(ds[src].values, dtype="float64")
        v[np.isclose(v, FILL)] = np.nan
        out[dst] = v
    out["qi"] = np.asarray(ds["QI"].values, dtype="float64")
    out["dir_ambiguous"] = np.asarray(
        ds["Status_Direction_Ambiguity"].values, dtype="float64").astype(bool)
    df = pd.DataFrame(out)

    # DeepLev samples at :08:32 past the hour; Open-Meteo is on the hour.
    # Round to nearest hour (max shift 8.5 min) and record the real offset.
    df["observed_at"] = df["time"].dt.round("h")
    df["offset_s"] = (df["time"] - df["observed_at"]).dt.total_seconds()
    df = df.drop(columns=["time"])

    # Physical plausibility guard -- Eastern Med. Anything outside is a sensor
    # glitch, not a measurement, and must not reach the bias analysis.
    bad = (df.hm0_m < 0) | (df.hm0_m > 12)
    df.loc[bad, ["hm0_m", "hmax_m"]] = np.nan
    for c, lo, hi in [("tp_s", 1, 30), ("tm02_s", 1, 30)]:
        df.loc[(df[c] < lo) | (df[c] > hi), c] = np.nan
    for c in ["mean_dir_deg", "peak_dir_deg"]:
        df.loc[(df[c] < 0) | (df[c] > 360), c] = np.nan

    return df.drop_duplicates(subset="observed_at").sort_values("observed_at")

if __name__ == "__main__":
    src = Path(sys.argv[1])
    df = extract(src)
    dest = Path("data/processed") / (src.stem + "_hourly.parquet")
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)

    n = len(df)
    print(f"source        : {src.name}")
    print(f"rows          : {n}")
    print(f"period        : {df.observed_at.min()} -> {df.observed_at.max()}")
    print(f"hour offset   : min={df.offset_s.min():.0f}s max={df.offset_s.max():.0f}s")
    for c in ["hm0_m", "hmax_m", "tp_s", "tm02_s", "mean_dir_deg", "peak_dir_deg"]:
        ok = df[c].notna().sum()
        print(f"  {c:14s} valid={ok:5d} ({100*ok/n:5.1f}%)")
    h = df.hm0_m.dropna()
    print(f"hm0 summary   : n={len(h)} min={h.min():.2f} median={h.median():.2f} max={h.max():.2f}")
    print(f"written       : {dest}")
