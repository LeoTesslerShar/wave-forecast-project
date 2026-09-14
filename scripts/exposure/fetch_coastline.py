"""One-off fetch of Israeli Mediterranean coastline geometry from OpenStreetMap
(prompts/phase-2-exposure.md section 1: "prefer the committed extract so the build is
reproducible and does not hammer Overpass").

Source: Overpass API, `way["natural"="coastline"]` within a bounding box covering the
Israeli coast from Ashdod to Haifa with margin. Queried 2026-09-14 via
overpass.openstreetmap.fr (the main instance and the kumi.systems mirror both timed out
under load; the French mirror answered).

Run once; output is committed at scripts/exposure/coastline.geojson. Re-run only if the
beach list expands beyond the current bounding box, or the extract needs refreshing.
"""
import json
from pathlib import Path

def _convert(raw_path: Path, out_path: Path, source_tag: str) -> int:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    features = []
    for el in raw["elements"]:
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
        features.append(
            {
                "type": "Feature",
                "properties": {"osm_id": el["id"], "tags": el.get("tags", {})},
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "properties": {
            "source": source_tag,
            "queried_via": "overpass.openstreetmap.fr",
            "queried_at": "2026-09-14",
            "bbox": [31.6, 34.2, 32.9, 35.2],
            "licence": "ODbL -- (c) OpenStreetMap contributors",
        },
        "features": features,
    }
    out_path.write_text(json.dumps(geojson), encoding="utf-8")
    return len(features)


def main() -> None:
    d = Path(__file__).parent
    n1 = _convert(d / "coastline_raw.json", d / "coastline.geojson", "OpenStreetMap, natural=coastline")
    print(f"wrote {n1} coastline segments to coastline.geojson")
    n2 = _convert(
        d / "structures_raw.json",
        d / "structures.geojson",
        "OpenStreetMap, man_made=breakwater|pier|groyne",
    )
    print(f"wrote {n2} structure segments to structures.geojson")


if __name__ == "__main__":
    main()
