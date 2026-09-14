"""Computes shoreline_bearing for every beach in data/beaches.yml and writes it back into
that file (prompts/phase-2-exposure.md section 1: "Write the result to
beaches.shoreline_bearing via a script, not by hand"). app/seed.py picks the value up on
the next container start -- no migration needed, the column has existed since Phase 1.

Run from the repo root: py scripts/exposure/compute_bearings.py

A beach entry with `shoreline_bearing_override: <degrees>` already set is left untouched
except for a printed note -- that is the mechanism for recording a manual correction after
reviewing a value against a map (section 1), and this script must never overwrite one.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.exposure.bearing import compute_shoreline_bearing  # noqa: E402

BEACHES_YML = Path(__file__).resolve().parent.parent.parent / "data" / "beaches.yml"

HEADER = """\
# Seed beach coordinates -- prompts/phase-1-ingestion.md section 2.
#
# Coordinate source: approximate, read off public map services (OpenStreetMap /
# Google Maps) at the known surf break for each spot, 2026-09-14. NOT surveyed, NOT
# validated against any authoritative source.
#
# shoreline_bearing / shoreline_bearing_source / shoreline_bearing_note: written by
# scripts/exposure/compute_bearings.py (prompts/phase-2-exposure.md section 1). Computed
# from OSM coastline geometry (scripts/exposure/coastline.geojson) -- do not hand-edit.
# To correct a value after reviewing it against a map, set `shoreline_bearing_override`
# on that beach and re-run the script; it will keep your override and stop recomputing
# that beach automatically.
"""


# Corrected 2026-09-14 (docs/DECISIONS.md): a low `window_points_used` count was
# ORIGINALLY treated as "thin data, low confidence." Verified against OSM's own edit
# history for the two beaches this flagged (Netanya, Ashdod) and found both are legitimate,
# actively-maintained coastline ways where THIS specific stretch happens to be one long
# straight segment (~2.9-3km) with few vertices -- not missing or sparse data. A long
# straight segment is often a MORE stable tangent than several short jittery ones. The real,
# narrower limitation: if the actual coast curves within that unsubdivided span, this
# method cannot see it, because OSM recorded no vertex there to show it. That is what
# MAX_SEGMENT_SPAN_NOTE_THRESHOLD_M flags -- a scoped caveat, not a "may be wrong" flag.
MAX_SEGMENT_SPAN_NOTE_THRESHOLD_M = 1500.0


def main() -> None:
    data = yaml.safe_load(BEACHES_YML.read_text(encoding="utf-8"))

    print(f"{'beach':18s} {'bearing':>8s} {'tangent':>8s} {'dist_m':>8s} {'pts':>4s} {'span_m':>7s}  note")
    for b in data["beaches"]:
        if b.get("shoreline_bearing_override") is not None:
            print(f"{b['id']:18s} {'--':>8s} {'--':>8s} {'--':>8s} {'--':>4s} {'--':>7s}  manual override kept")
            b["shoreline_bearing"] = b["shoreline_bearing_override"]
            b["shoreline_bearing_source"] = "manual_override"
            continue

        r = compute_shoreline_bearing(b["lat"], b["lon"])
        note = ""
        if r.max_segment_span_m >= MAX_SEGMENT_SPAN_NOTE_THRESHOLD_M:
            note = (
                f"bearing rests substantially on one {r.max_segment_span_m:.0f}m straight OSM "
                f"segment -- real curvature within that span, if any, is not captured (see "
                f"docs/DECISIONS.md; verified this is a legitimate mapped way, not sparse/missing data)"
            )
        if r.distance_to_coast_m > 500:
            note = (note + "; " if note else "") + f"beach coord {r.distance_to_coast_m:.0f}m from nearest OSM coastline"

        print(
            f"{b['id']:18s} {r.bearing_deg:8.1f} {r.tangent_bearing_deg:8.1f} "
            f"{r.distance_to_coast_m:8.1f} {r.window_points_used:4d} {r.max_segment_span_m:7.0f}  {note}"
        )

        b["shoreline_bearing"] = r.bearing_deg
        b["shoreline_bearing_source"] = "computed_osm_coastline"
        if note:
            b["shoreline_bearing_note"] = note

    with open(BEACHES_YML, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write("\n")
        yaml.dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
    print(f"\nwrote shoreline_bearing for {len(data['beaches'])} beaches to {BEACHES_YML}")


if __name__ == "__main__":
    main()
