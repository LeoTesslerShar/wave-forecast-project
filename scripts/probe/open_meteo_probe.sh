#!/usr/bin/env bash
# Phase 0 probe: establishes the Open-Meteo Marine historical archive boundary and the
# reanalysis-vs-forecast-as-issued distinction documented in docs/DATA_SOURCES.md.
# Run from repo root. Requires curl and node (used only for JSON parsing, no deps).
set -euo pipefail

LAT=32.08
LON=34.75
BASE="https://marine-api.open-meteo.com/v1/marine"
TMP="$(mktemp -u -p . _om_probe_XXXX.json)"
trap 'rm -f "$TMP"' EXIT

nonnull() {
  node -e "
const j=JSON.parse(require('fs').readFileSync('$TMP','utf8'));
const h=j.hourly||{};
const wh=h.wave_height||h.wave_height_previous_day7||[];
console.log('nonnull '+wh.filter(v=>v!==null).length+'/'+wh.length+'  sample@12:', wh[12]);
"
}

echo "=== A. default (operational) model: does history exist? ==="
for d in 1990-01-01 2000-01-01 2010-01-01 2015-01-01 2020-01-01 2021-06-01 2021-10-01 2022-01-01 2024-01-01; do
  curl -s -m 30 "$BASE?latitude=$LAT&longitude=$LON&hourly=wave_height,wave_direction,wave_period,swell_wave_height&start_date=$d&end_date=$d" -o "$TMP"
  printf '%s  ' "$d"; nonnull
done

echo
echo "=== B. era5_ocean (reanalysis): does history exist further back? ==="
for d in 1990-01-01 2000-01-01 2010-01-01 2015-01-01 2021-06-01; do
  curl -s -m 30 "$BASE?latitude=$LAT&longitude=$LON&hourly=wave_height,wave_direction&start_date=$d&end_date=$d&models=era5_ocean" -o "$TMP"
  printf '%s  ' "$d"; nonnull
done

echo
echo "=== C. previous_dayN on a HISTORICAL date (does forecast-as-issued archive exist?) ==="
curl -s -m 30 "$BASE?latitude=$LAT&longitude=$LON&hourly=wave_height,wave_height_previous_day1,wave_height_previous_day3,wave_height_previous_day7&start_date=2024-01-01&end_date=2024-01-01" -o "$TMP"
cat "$TMP"
echo
echo "(expect every previous_dayN value null — confirms no historical forecast-as-issued archive)"
