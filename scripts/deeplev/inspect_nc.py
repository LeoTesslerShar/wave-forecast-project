"""Dump the structure of a DeepLev NetCDF file. Variable names are undocumented
here, so this prints everything rather than assuming Hm0/Tp naming."""
import sys
import xarray as xr

path = sys.argv[1]
ds = xr.open_dataset(path, decode_timedelta=False)

print("=== DIMENSIONS ===")
for k, v in ds.dims.items():
    print(f"  {k}: {v}")

print("\n=== GLOBAL ATTRS ===")
for k, v in ds.attrs.items():
    s = str(v)
    print(f"  {k}: {s[:200]}")

print("\n=== COORDS ===")
for name, c in ds.coords.items():
    print(f"  {name}  dims={c.dims}  dtype={c.dtype}  shape={c.shape}")

print("\n=== DATA VARIABLES ===")
for name, v in ds.data_vars.items():
    units = v.attrs.get("units", "")
    long_name = v.attrs.get("long_name", v.attrs.get("standard_name", ""))
    print(f"  {name:28s} dims={str(v.dims):30s} shape={str(v.shape):18s} units={units:10s} {long_name[:60]}")
