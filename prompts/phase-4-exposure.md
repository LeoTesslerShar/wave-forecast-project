# Phase 4 — Per-beach exposure layer

Read `PROMPT.md` and `docs/PLANNING.md` (§6 Phase 4, §3) first.

**Hard rule 1 is the defining constraint of this phase.** Everything built here is a
geometric heuristic with no ground truth behind it — there are no instrumented buoys at the
beaches, so nothing in this layer is validated and nothing from it may be presented as if
it were. Build it anyway: it encodes the real observation that the same swell is mediocre
at Bat Yam and excellent at Herzliya. Just label it honestly everywhere it surfaces.

---

## 1. Shoreline bearing

- Pull Israeli coastline geometry from OpenStreetMap (Overpass query for
  `natural=coastline`, or a committed GeoJSON extract — prefer the committed extract so the
  build is reproducible and does not hammer Overpass; record the extract date and source).
- For each beach, find the nearest coastline segment and compute the **shoreline normal**:
  the compass bearing the beach faces out to sea. Handle the ambiguity of which side is sea
  explicitly — for the Israeli Mediterranean coast the seaward normal points broadly west,
  which gives you a sanity check to assert in a test.
- Smooth over a window of coastline rather than a single segment. OSM coastline vertices
  are irregular and one short segment can be 40° off the real orientation of the beach.
  State the window length used.
- Write the result to `beaches.shoreline_bearing` via a script, not by hand. Then **review
  every value against a map** and record any manual override, with the reason, in
  `data/beaches.yml`. A wrong bearing is invisible in the code and obvious on a map.

## 2. Exposure score

```
exposure = f(angular difference between swell direction and shoreline normal) × (1 − obstruction)
```

- Define `f` explicitly and document the shape. A cosine of the angular difference,
  clamped at zero beyond ±90°, is a reasonable starting point — swell arriving parallel to
  the shore or from behind it does not reach the break.
- Angular arithmetic: wrap correctly, and be unambiguous about whether swell direction is
  the direction waves come *from* (meteorological convention, usual) or go *to*. Getting
  this backwards inverts every score and produces a plausible-looking, entirely wrong
  system. Assert the convention in a test using a known case.
- **Obstruction:** ray-cast from the beach point toward the swell source; check for
  intersection with coastline or structures (marinas, breakwaters, jetties — OSM
  `man_made=breakwater`, `man_made=pier`) within a stated range. Reduce the score on a hit.
  Where a spot's obstruction is locally known but not in OSM, allow a manual entry in
  `data/beaches.yml` with `obstruction_notes` — and mark it as manual.
- Score range `0..1`, with a documented meaning for the endpoints.

## 3. Surfacing it — the honest-labelling requirement

Every forecast response carrying an exposure-adjusted value must carry, at minimum:

```json
{
  "wave_height_calibrated": 1.2,
  "method": "calibrated+heuristic_exposure",
  "components": {
    "raw": 1.5,
    "bias_correction": -0.3,
    "exposure_factor": 0.8
  },
  "confidence": {
    "bias_correction": "validated",
    "exposure": "unvalidated_heuristic"
  },
  "exposure_basis": "shoreline bearing 265°, swell from 290°, no obstruction modelled"
}
```

Shape it as you like, but these properties are required:

- the raw and the adjusted values are **both** visible — a consumer can always see what was
  done to the number;
- the exposure component is explicitly marked unvalidated;
- the basis is human-readable, so a surfer who knows the spot can tell when the model is
  wrong about it.

Same in the UI: the exposure adjustment is visibly flagged as an estimate, not rendered as
another decimal place of certainty. Same in the README and the API docs.

---

## Acceptance checks

Run and paste:

1. The computed bearing for all 8–12 beaches, with a sanity assertion that each faces
   broadly seaward.
2. A worked example for two beaches with contrasting orientations under the same swell —
   Bat Yam vs Herzliya is the case from the planning doc — showing different exposure
   scores and the reason.
3. The direction-convention test, and a test showing an offshore/parallel swell scores ~0.
4. An API response containing the full `components` / `confidence` structure.
5. A grep or test proving no endpoint returns an exposure-adjusted value without the
   unvalidated marker.
6. `docker compose run --rm api pytest`.

## Then stop

State plainly in your report which parts of the layer are geometry and which are guesswork,
and what it would take to validate any of it.
