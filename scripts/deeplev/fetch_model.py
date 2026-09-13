"""Fetch the Open-Meteo marine archive at the DeepLev coordinates for a date range.

NOTE: this is the archived operational-model value -- ONE value per valid_at,
analysis-like, NOT a forecast issued with a lead time. Pairing it with DeepLev
measures MODEL-vs-REALITY bias, not forecast error growth. See docs/DATA_SOURCES.md.
"""
import sys, json, time, urllib.request, urllib.error
from pathlib import Path
import pandas as pd

LAT, LON = 33.05, 34.48          # DeepLev mooring
BASE = "https://marine-api.open-meteo.com/v1/marine"
HOURLY = ["wave_height", "wave_direction", "wave_period",
          "swell_wave_height", "swell_wave_direction", "swell_wave_period",
          "wind_wave_height", "wind_wave_direction", "wind_wave_period"]

def fetch(start, end, retries=4):
    url = (f"{BASE}?latitude={LAT}&longitude={LON}"
           f"&hourly={','.join(HOURLY)}&start_date={start}&end_date={end}")
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  retry {attempt+1} after {wait}s ({e})")
            time.sleep(wait)

if __name__ == "__main__":
    start, end, out = sys.argv[1], sys.argv[2], sys.argv[3]
    j = fetch(start, end)
    h = j["hourly"]
    df = pd.DataFrame(h)
    df["valid_at"] = pd.to_datetime(df.pop("time"))
    df = df[["valid_at"] + HOURLY]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"grid point returned : ({j['latitude']}, {j['longitude']})  requested ({LAT}, {LON})")
    print(f"rows                : {len(df)}  {df.valid_at.min()} -> {df.valid_at.max()}")
    for c in HOURLY:
        print(f"  {c:24s} nonnull={df[c].notna().sum():5d} ({100*df[c].notna().mean():5.1f}%)")
    print(f"written             : {out}")
