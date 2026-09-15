"""Loads the committed OSM coastline/structure extracts
(scripts/exposure/{coastline,structures}.geojson -- see
scripts/exposure/fetch_coastline.py for provenance). Cached at module level; these files
are small (~130KB / ~100KB) and static."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "exposure"

Line = list[tuple[float, float]]  # list of (lat, lon)


def _load_lines(path: Path) -> list[Line]:
    data = json.loads(path.read_text(encoding="utf-8"))
    lines: list[Line] = []
    for feature in data["features"]:
        coords = feature["geometry"]["coordinates"]  # [[lon, lat], ...]
        lines.append([(lat, lon) for lon, lat in coords])
    return lines


@lru_cache
def coastline_lines() -> tuple[Line, ...]:
    return tuple(_load_lines(DATA_DIR / "coastline.geojson"))


@lru_cache
def structure_lines() -> tuple[Line, ...]:
    return tuple(_load_lines(DATA_DIR / "structures.geojson"))


@lru_cache
def structure_kinds() -> tuple[str, ...]:
    """`properties.tags.man_made` for each feature in structures.geojson, in the SAME
    feature order as structure_lines() -- app/exposure/obstruction.py indexes into both by
    position (struct_idx) and depends on this alignment. "unknown" when the tag is absent,
    never a crash or a silently dropped structure. Used to weight obstruction by structure
    type (a piled pier is not a wave barrier the way a solid breakwater/groyne is) --
    see OBSTRUCTION_TYPE_WEIGHT in obstruction.py and docs/DECISIONS.md."""
    data = json.loads((DATA_DIR / "structures.geojson").read_text(encoding="utf-8"))
    return tuple(f.get("properties", {}).get("tags", {}).get("man_made", "unknown") for f in data["features"])
