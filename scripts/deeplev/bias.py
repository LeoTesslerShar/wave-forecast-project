"""Join DeepLev measurements to the Open-Meteo archive and characterise model bias.

error = model - measured, so POSITIVE bias means the model OVER-predicts.
Compares like with like: model significant wave height vs measured Hm0.
Hmax is NOT compared against model wave_height -- different quantities.
"""
import sys
import numpy as np
import pandas as pd

MIN_N = 30   # cells below this are reported as insufficient, never as a value

def load(meas_path, model_path):
    m = pd.read_parquet(meas_path).rename(columns={"observed_at": "valid_at"})
    f = pd.read_parquet(model_path)
    df = f.merge(m, on="valid_at", how="inner")
    return df[df.hm0_m.notna()].copy()

def stats(g):
    e = g["err"]
    return pd.Series({
        "n": len(e),
        "bias": e.mean(),
        "MAE": e.abs().mean(),
        "RMSE": np.sqrt((e ** 2).mean()),
        "meas_mean": g["hm0_m"].mean(),
        "model_mean": g["wave_height"].mean(),
    })

def show(df, by, label):
    t = df.groupby(by, observed=True).apply(stats, include_groups=False).round(3)
    t["n"] = t["n"].astype(int)
    t["status"] = np.where(t.n >= MIN_N, "", "INSUFFICIENT")
    print(f"\n=== {label} ===")
    print(t.to_string())

if __name__ == "__main__":
    df = load(sys.argv[1], sys.argv[2])
    df["err"] = df.wave_height - df.hm0_m

    print(f"paired rows (valid Hm0 + model): {len(df)}")
    print(f"period: {df.valid_at.min()} -> {df.valid_at.max()}")

    e = df.err
    print(f"\n=== OVERALL (model - measured, positive = model over-predicts) ===")
    print(f"  n          : {len(e)}")
    print(f"  meas  mean : {df.hm0_m.mean():.3f} m   (median {df.hm0_m.median():.3f})")
    print(f"  model mean : {df.wave_height.mean():.3f} m   (median {df.wave_height.median():.3f})")
    print(f"  bias       : {e.mean():+.3f} m")
    print(f"  MAE        : {e.abs().mean():.3f} m")
    print(f"  RMSE       : {np.sqrt((e**2).mean()):.3f} m")
    print(f"  corr       : {df.wave_height.corr(df.hm0_m):.3f}")
    print(f"  scatter index (RMSE/mean_meas): {np.sqrt((e**2).mean())/df.hm0_m.mean():.3f}")

    # Height regime -- thresholds chosen for surf relevance, stated explicitly.
    df["regime"] = pd.cut(df.hm0_m, [0, 0.5, 1.0, 1.5, 2.5, 99],
                          labels=["flat <0.5", "small 0.5-1", "rideable 1-1.5",
                                  "good 1.5-2.5", "big >2.5"])
    show(df, "regime", "BY MEASURED HEIGHT REGIME")

    # Direction: measured mean direction, 45-degree compass sectors.
    d = df[df.mean_dir_deg.notna()].copy()
    d["sector"] = pd.cut((d.mean_dir_deg + 22.5) % 360, np.arange(0, 361, 45),
                         labels=["N", "NE", "E", "SE", "S", "SW", "W", "NW"], right=False)
    show(d, "sector", "BY MEASURED SWELL DIRECTION SECTOR")

    df["month"] = df.valid_at.dt.month
    show(df, "month", "BY MONTH")
