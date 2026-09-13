# Phase 0 — Verify the data sources before building anything

Read `PROMPT.md` and `docs/PLANNING.md` first. This phase answers section 9 of the
planning doc.

**No pipeline code in this phase.** Throwaway probe scripts are fine and belong in
`scripts/probe/`. The deliverable is evidence and a decision.

---

## Why this is a gate

The project's headline claim — that the forecast can be bias-corrected against measured
reality — needs a training set of forecast↔measurement pairs covering enough history to
validate chronologically. That set may not exist. If the Open-Meteo marine archive is
shallow for the Eastern Med, or the buoy history is not exportable, Phase 3 is not a
model-training phase and pretending otherwise wastes the project.

Find out now, cheaply, before schema design encodes an assumption that is false.

---

## The five questions

### Q1 — CAMERI ADVA: bulk historical export?

Ashdod buoy (data from 1992) and Haifa buoy (from 1993), parameters Hmax, Tp, wave
direction. ADVA is the web interface.

Establish: is there a programmatic or bulk export path (CSV/API/download link), or is it
view-only in the UI? What date ranges can be pulled in one request? What format? Is there
an account, licence, or request process?

If it is UI-only, say so plainly and record what a realistic manual export would yield
(how many rows, how much clicking). Do not invent an API that you have not seen respond.

### Q2 — Open-Meteo Marine: how deep is the archive?

The forecast endpoint is free and keyless. What matters here is **history**, for a
coordinate off the Israeli coast (use ~32.08 N, 34.75 E, Tel Aviv).

Establish, by actually calling it:
- the earliest date that returns real data, not nulls — binary-search the start date;
- which variables are populated that far back. Wave height, wave direction, wave period,
  swell height/direction/period and wind may have different coverage. A field that exists
  in the response schema but is null for 2018 is not coverage;
- the archive endpoint vs the forecast endpoint — which one serves past dates, what its
  spatial resolution is over the Eastern Med, and which underlying model it comes from;
- rate limits and the terms for non-commercial use.

**Critical distinction to nail down and write up:** an archive of *past forecasts* is not
the same as a *reanalysis* of past conditions. Bias correction needs forecast-as-issued,
with a real lead time, to learn how the model errs. A reanalysis product has no lead time
and is fitted to observations — training on it teaches a different thing entirely.
Determine which one is actually available and state the consequence for Phase 3 directly.
If only reanalysis is available historically, then the usable forecast↔measurement pairs
start accumulating from the day Phase 1 goes live, and Phase 3 must be re-scoped.

### Q3 — ISRAMAR Hadera buoy: documented endpoint or not?

Read `Yuvartz/yam-palta`'s `scripts/fetch-buoy.mjs` on GitHub first (planning doc §4.4) —
it already fetches this buoy hourly, so the access path exists. Then establish
independently:

- the exact URL and response shape (JSON? HTML? CSV?);
- whether it is a documented public endpoint or an internal one the site's own frontend
  calls — and if undocumented, how fragile that makes it and what the fallback is;
- update cadence, and how much history a single request returns;
- whether any *historical* archive is reachable, or only a recent rolling window. This is
  as decisive as Q2: a 7-day rolling window means there is no historical ground truth to
  train against, only a live feed to accumulate.

### Q4 — Buoy siting

For each of Ashdod, Haifa, Hadera: measurement depth and distance offshore, and which
wave parameters each actually reports (significant height Hs vs max height Hmax matters —
they are not interchangeable and must not be joined as if they were).

Also confirm the planning doc's stated limitation: there are no instrumented buoys at the
beaches themselves. This is what makes stage 1 calibration *regional* rather than
per-beach, and the README needs to say it.

### Q5 — Licensing and attribution

IOLR/ISRAMAR and Open-Meteo terms: what attribution is required, what redistribution is
permitted, whether storing and re-serving derived values is allowed. Check `robots.txt`
and terms of use for every host you intend to fetch from on a schedule.

If anything prohibits automated access, that source is out — hard rule 3. Say so and move
on; do not look for a workaround.

---

## Deliverables

### `docs/DATA_SOURCES.md`

One section per source (Open-Meteo forecast, Open-Meteo archive, ISRAMAR Hadera, CAMERI
Ashdod, CAMERI Haifa), each with:

| Field | |
|---|---|
| Endpoint / access path | exact URL or "UI only, no programmatic access" |
| Auth | none / key / account / request process |
| Documented? | yes, with link — or "undocumented, discovered via <source>" |
| Update cadence | |
| History depth | the earliest date that returned real data, and how you established it |
| Variables actually populated | not the schema — what came back non-null |
| Rate limits | |
| Licence / attribution | with link |
| Stability verdict | can a scheduled job depend on this, and what breaks if it changes |
| Probe record | date, request made, HTTP status, link to the committed fixture |

### `tests/fixtures/`

A real sample response per source, committed, named so its origin is obvious
(`isramar_hadera_2026-09-13.json`). These become the mocks for Phase 1's tests.

### `scripts/probe/`

The throwaway scripts you used, committed so the numbers are reproducible. They do not
need to be pretty. They do need to run.

### The scope verdict — the most important section

Close `docs/DATA_SOURCES.md` with a section headed **Scope verdict** answering:

1. How many forecast↔measurement pairs can realistically be assembled *today*, from
   history, with real lead times? Give a number and show the arithmetic.
2. Is Phase 3 (trained calibration model) viable on that? Yes / no / only for these buoys
   / only after N months of live accumulation.
3. If not viable as written: state the re-scope. Per planning doc §9, the fallback is a
   live-accumulating bias tracker — Phase 1 starts recording forecast-vs-measurement
   deltas from day one, Phase 2 reports on whatever has accumulated, Phase 3 waits — with
   the project's weight moving to Phases 1, 4 and 5.

**Make this call and write it down.** Do not hedge it into a paragraph that lets a future
session proceed as if nothing happened. If the answer is bad, the answer is bad, and
knowing it on day one is the point of this phase.

---

## Acceptance checks

Run these and paste the real output:

1. A single command that re-runs every probe and prints, per source: HTTP status, earliest
   date with real data, and the variables that came back non-null.
2. `git status` showing the committed fixtures.
3. The Scope verdict section, quoted in full in your final message.

## Then stop

Do not start Phase 1. Report the verdict and wait. If the verdict changes what Phase 1,
2 or 3 should do, **edit those prompt files** (`prompts/phase-N-*.md`) to match reality and
say exactly what you changed and why.
