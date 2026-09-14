# Phase 3 — Surf quality scoring

Read `PROMPT.md`, `docs/BIAS_ANALYSIS.md`, and `prompts/phase-2-exposure.md` (its output is
this phase's input) first.

**This phase did not exist in the original plan.** It was added because the DeepLev spike
showed offshore height is already forecast accurately, and height alone does not tell you
if a session is worth having — wind and chop do. A 1.2 m sea that is mostly wind-chop is
mush; the same height as clean swell is a good day. This is the piece that makes the
difference between "an app that shows a number" and "an app that tells you whether to go."

---

## 1. Inputs

All should already be flowing from Phase 1:

- Exposure-adjusted height + range from Phase 2 (heuristic, labelled as such)
- `wave_period` (`Tp`) — `docs/BIAS_ANALYSIS.md` measured ~0.97 s MAE against DeepLev; carry
  that into the confidence shown for period, same as the height range
- `swell_wave_height` / `wind_wave_height` split — already fetched by Phase 1, unused until
  now
- `wind_speed_10m`, `wind_direction_10m`, `wind_gusts_10m` — from
  `api.open-meteo.com/v1/forecast` (a **different endpoint** than the marine archive; verify
  it is actually being ingested per-beach in Phase 1, since the marine endpoint alone does
  not carry 10 m wind)
- Beach `shoreline_bearing` from Phase 2

## 2. Components — each visible individually, no opaque single number

Do not collapse this into one hidden "quality: 7/10." Every component the score is built
from must be inspectable in the API response — a surfer who knows the spot needs to be
able to see *why* the score is what it is and disagree with one part of it.

### Size
The Phase 2 exposure-adjusted height, shown as the range it already is — never a bare
decimal (`docs/BIAS_ANALYSIS.md` measured roughly ±0.25 m spread even on the raw offshore
value; the beach-level range should not be narrower than that).

### Period
Longer period = more organized, more powerful. For the Eastern Mediterranean's typical
short-fetch wind swell, define thresholds explicitly and justify them (e.g. under ~6 s is
weak wind-chop, ~6-8 s is workable, 8 s+ is a good period for this coast) — do not import
thresholds tuned for a long-fetch ocean coast without checking they make sense here against
what `docs/BIAS_ANALYSIS.md`'s period data actually showed.

### Wind — the decisive quality factor
Score from the angle between wind direction and the beach's shoreline normal (from Phase 2):

- **Offshore** (wind blowing from land to sea, roughly opposite the shoreline normal) —
  grooms the wave face, holds it up longer. Best quality regardless of size.
- **Onshore** (wind blowing with the shoreline normal) — chops up the face, degrades
  quality even on a good swell.
- **Cross-shore** — intermediate, direction-dependent on which way it drags the face.
- **Light wind** (below roughly 8-10 km/h) — glassy regardless of direction; define the
  actual cutoff and state it.
- **Gusts:** a large gust/mean spread signals instability even if the mean direction looks
  good. Flag it, don't just average it away.

**The local pattern to encode explicitly, not leave implicit:** off Israel the swell
typically arrives *with* the westerly wind that generated it — so the storm peak itself is
often onshore and messy, while the *following dawn*, once the overnight land breeze turns
offshore, is when it cleans up. A scorer that only looks at "biggest swell this week" and
ignores the wind at that exact hour will recommend the wrong session. Score hour-by-hour,
not day-by-day, and do not let a good headline height from earlier in a stormy window leak
into a later hour's score.

### Chop ratio
`wind_wave_height / (swell_wave_height + wind_wave_height)` (or however Phase 1 stored the
split). Low ratio = clean groundswell face even at modest size. High ratio = wind-driven
slop even at a "good" total height. This is free — the components are already ingested —
and probably separates good/bad days better than total height alone.

## 3. Combining components

- Keep the combination simple and explainable (a weighted score or a small decision table),
  not a black-box model — there is no training data to fit one to, and hard rule 1 governs:
  an opaque score is a heuristic wearing false precision.
- Every component appears in the API response individually, plus the combined verdict.
- Document the weighting/logic in `docs/DECISIONS.md` with the reasoning, since it is a
  judgment call with no ground truth to tune it against.

## 4. The acceptance test the whole idea rests on

**A storm-peak hour (large swell, strong onshore wind) must score worse than the following
dawn (smaller swell, light offshore wind).** Construct this as a concrete test case with
real numbers, not just an assertion. If the scorer rates the storm peak higher, the wind
term is wrong or under-weighted — fix it before anything downstream depends on this score.
This is more important than any other single test in this phase.

## 5. API shape

```json
{
  "beach_id": "herzliya",
  "valid_at": "2026-01-15T06:00:00Z",
  "size": {"estimate_m": 1.3, "range_m": [1.1, 1.6], "method": "raw_offshore+heuristic_exposure"},
  "period_s": 8.2,
  "wind": {"speed_kmh": 8, "direction_deg": 301, "relation_to_shore": "offshore", "gusts_kmh": 12},
  "chop_ratio": 0.12,
  "quality_verdict": "good",
  "quality_reasoning": "clean offshore wind, low chop, workable period",
  "confidence": {
    "size": "unvalidated_heuristic",
    "period": "measured_uncertainty ~1s",
    "wind": "measured_forecast",
    "quality_verdict": "unvalidated_heuristic"
  }
}
```

Shape as you like; the properties that are required are: every component visible
individually, the combined verdict, and confidence markers throughout — none of this
layer is validated (hard rule 1), and the response must not let a reader mistake it for
validated.

---

## Acceptance checks

Run and paste:

1. **The storm-vs-dawn test from section 4**, with real component values, showing the dawn
   hour scoring higher.
2. A worked example across a full day showing the score vary hour-by-hour as wind rotates
   from onshore (afternoon storm) to offshore (dawn) — not a single daily number.
3. A response showing all components individually plus the combined verdict.
4. A test that a high chop ratio degrades the verdict even when total height is "good".
5. A grep or test proving no quality-verdict response omits its confidence markers.
6. `docker compose run --rm api pytest`.

## Then stop

Report which component (size, period, wind, chop) the test cases show driving the verdict
most, and whether the storm-vs-dawn test needed tuning to pass — if it did, say what was
tuned and why, since there is no ground truth to validate the tuning against.
