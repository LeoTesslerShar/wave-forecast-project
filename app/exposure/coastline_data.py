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
