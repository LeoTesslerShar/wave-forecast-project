# Data sources — Phase 0 verification

Probed 2026-09-13. Every claim below is backed by a live HTTP call, quoted verbatim or
summarized with the exact fields observed, and a fixture committed under
`tests/fixtures/` or a script under `scripts/probe/`. Where a claim could not be verified
by a live call, it is marked **unresolved** rather than guessed.

---

## Open-Meteo Marine — live/current forecast

| Field | Value |
|---|---|
| Endpoint | `https://marine-api.open-meteo.com/v1/marine` |
| Auth | None. Free tier, no key. |
| Documented | Yes — https://open-meteo.com/en/docs/marine-weather-api |
| Update cadence | Standard forecast run cadence (not independently timed here) |
| Rate limits | <10,000 calls/day, 5,000/hour, 600/minute for non-commercial free use |
| Licence | CC-BY 4.0. Attribution to DWD *and* Open-Meteo required. Non-commercial only — no ads/subscriptions/commercial-entity use on the free tier. |
| Probe | `GET /v1/marine?latitude=32.08&longitude=34.75&hourly=wave_height&forecast_days=1` → HTTP 200, full hourly series returned. Fixture: `tests/fixtures/open_meteo_forecast_2026-09-13.json`. |
| Stability verdict | Solid for live/current use — a scheduled job can depend on this for present and future forecasts. |

## Open-Meteo Marine — historical archive (`start_date`/`end_date`, default model)

**This is the decisive probe of the whole phase.**

| Date requested | Result |
|---|---|
| 1990, 2000, 2010, 2015, 2020-01-01, 2021-06-01 | HTTP 200, but every hourly value **null** (wave_height, wave_direction, wave_period, swell_wave_height) |
| 2021-10-01 | HTTP 200, **21/24 hours non-null** — archive boundary falls inside this day |
| 2022-01-01 onward, 2024-01-01 | HTTP 200, fully populated |

Fixture: `tests/fixtures/open_meteo_archive_boundary_2021-10-01.json`.

**Conclusion: the operational-model historical archive starts approximately 1 Oct 2021**,
matching Open-Meteo's own documentation that MFWAM (the underlying operational wave
model) archive begins October 2021. Before that date there is simply nothing — not a
thin sample, zero.

### Reanalysis vs forecast-as-issued — the distinction that matters for Phase 3

Open-Meteo also exposes `models=era5_ocean`, ERA5-Ocean reanalysis, documented back to
1940. Probed at 1990-01-01, 2000-01-01, 2010-01-01, 2015-01-01, 2021-06-01: **all
returned full non-null data** (fixture: `tests/fixtures/open_meteo_era5_ocean_2010-01-01.json`).
So a long series exists — but ERA5-Ocean is a **reanalysis**, reconstructed from
observations after the fact. It has no lead time and was never "issued" as a prediction.
Training a bias-correction model on it would teach the model to match a retrospective
reconstruction, not to correct an actual forecast's real-world error — a different problem
than the one this project is trying to solve.

The API also exposes `wave_height_previous_dayN` (N = 1, 3, 7) — the forecast issued N
days ago for the currently active forecast window, which looked like it might be a
lead-time-aware historical archive. Tested directly: requesting these fields together
with a historical `start_date`/`end_date=2024-01-01` returns **HTTP 200 with every
`previous_dayN` value null** — confirmed with a saved response
(`tests/fixtures/open_meteo_previous_day7_historical_null.json`). The `previous_dayN`
fields only work against the live rolling forecast window, not the historical archive.

**Consequence:** Open-Meteo has no mechanism, at any date, to retrieve "what the forecast
said with a 24-hour lead time, issued on a specific past date." Historical
forecast-as-issued data, with the lead-time structure Phase 3 needs, does not exist and
cannot be reconstructed from this source. The only way to obtain it is to start capturing
it prospectively — record `issued_at` at fetch time, forward, from the day Phase 1 goes
live.

---

## ISRAMAR — Hadera buoy

| Field | Value |
|---|---|
| Endpoint | `https://isramar.ocean.org.il/isramar2009/station/data/Hadera_Hs_Per.json` |
| Documented | No — undocumented. Discovered by reading `Yuvartz/yam-palta`'s `scripts/fetch-buoy.mjs` (fetched directly from `raw.githubusercontent.com/Yuvartz/yam-palta/master/scripts/fetch-buoy.mjs`), then independently confirmed by calling the same URL ourselves. |
| Auth | None |
| Response shape | JSON, e.g. `{"datetime": "2026-09-13 14:00 UTC", "parameters": [{"name": "Significant wave height", "units": "m", "values": [0.42]}, {"name": "Peak wave period", "units": "s", "values": [5.9]}, {"name": "Maximal wave height", "units": "m", "values": [0.5334]}]}`. Fixture: `tests/fixtures/isramar_hadera_2026-09-13.json`. |
| History | None. The endpoint returns exactly one current reading — `values` is always a single-element array, no date-range parameter exists. `fetch-buoy.mjs` itself confirms this: it fetches this same URL hourly via a GitHub Action and overwrites a single-record file each run, explicitly to accumulate a series over time going forward, not to fetch history. |
| Update cadence | Appears hourly (matches yam-palta's hourly cron and our probe's timestamp being current to the hour). No documented SLA. |
| `robots.txt` | `https://isramar.ocean.org.il/robots.txt` disallows only unrelated `/PERSEUS_Data/*Download*`/`Admin*` paths. The station JSON path used here is not disallowed. |
| Licence | Explicit restriction found on the station page (`HaderaRDI.aspx`): "(c) Israel Oceanographic & Limnological Research. All Rights Reserved" plus Hebrew text stating data may not be used without IOLR's written permission. |
| Stability verdict | Technically reliable enough that a third party (`yam-palta`) has run it hourly without apparent issue, but undocumented and unauthorized-by-default per the licence notice above. |

**Action required before production use:** request written permission from IOLR before
relying on this feed beyond personal/research testing. `yam-palta` uses it without
apparent permission as prior art, but this project should not inherit that risk silently
— hard rule 3 (no scraping of sources that prohibit it) applies to the use, not just the
technical access. Flagging this for the user to actually contact IOLR; this is not
something a coding session can resolve on its own.

## CAMERI ADVA — Ashdod & Haifa buoys

| Field | Value |
|---|---|
| Buoys | Ashdod (Datawell Directional Waverider MkIII, ~24 m depth, since 1992), Haifa (same buoy type, ~24 m depth, since 1993), Eilat (DWR4, since March 2023 — out of scope, not a surf coast) |
| Interface | ADVA / SeAdvisor web portal — https://www.cameri-eng.com/adva/ |
| Cadence | Every 30 minutes, "Last 48 Hours" shown in the UI |
| Bulk historical export | Not found. The ADVA page states "API available" but the only access path offered is "Contact us today to get ADVA SeAdvisor access" — a gated request process, not self-serve. No public documentation of request format, response shape, or historical depth was found. |
| Terms | The buoy-measurements page states data is "not intended for academic, commercial, or operational use without prior written consent." |
| `robots.txt` | `https://www.cameri-eng.com/robots.txt` is a standard WordPress robots file; does not block the relevant pages. Irrelevant here since there is no scrapeable data endpoint — the barrier is the missing/gated API, not a crawl restriction. |
| Verdict | UI-view only from the outside. Programmatic access exists in principle ("API available") but requires direct institutional contact and written consent — outside what this session can obtain. Treat CAMERI (Ashdod, Haifa) as unavailable for this project unless the user separately contacts CAMERI and obtains API credentials. |

## Buoy siting (Q4)

| Buoy | Depth | Offshore distance |
|---|---|---|
| Ashdod | 24 m (confirmed, CAMERI) | Unresolved — not stated in any public CAMERI page found |
| Haifa | 24 m (confirmed, CAMERI) | Unresolved |
| Hadera | Unresolved | Unresolved. Note: the Hadera station is described by ISRAMAR as a "Sea-Level Observing Station" (GLOSS #80) sited near the Orot Rabin power station's cooling-water intake harbour (breakwaters of 810 m and 340 m per third-party sources), which raises a real possibility that Hadera's wave reading is taken in a more sheltered, shallower location than the deep-water CAMERI buoys — this needs confirmation before treating Hadera as directly comparable to Ashdod/Haifa in Phase 2's bias analysis. Flag it as an assumption to check, not a fact to assume. |

## Licensing summary (Q5)

- **Open-Meteo:** CC-BY 4.0, attribution to DWD + Open-Meteo required, redistribution of derived values permitted under that licence, non-commercial free-tier constraints apply (no ads/subscriptions).
- **IOLR/ISRAMAR:** "All rights reserved," explicit no-use-without-written-permission notice. Real constraint — see action item above.
- **CAMERI:** Written consent required for anything beyond viewing. Moot in practice since no bulk data is reachable without that consent anyway.

---

## Scope verdict

**1. How many historical forecast-to-measurement pairs exist today, with real lead time?**

Zero. Not "thin" — zero, from every source:
- Open-Meteo's forecast-as-issued history does not exist before approximately Oct 2021,
  and even after that date the API has no mechanism to retrieve a past forecast as it was
  issued with a real lead time — only the single archived analysis-like value, or the
  ERA5 reanalysis (which has no lead time by construction).
- ISRAMAR Hadera has no historical endpoint at all — one live reading only.
- CAMERI Ashdod/Haifa bulk export requires institutional permission not obtainable in this
  session.

**2. Is Phase 3 (trained calibration model) viable as originally written?**

No, not today. There is no dataset to split chronologically because there is no
historical `(issued_at, valid_at, measured)` triple available from any source, at any
volume. This is exactly the "both Q1 and Q2 come back badly" scenario the planning doc's
section 9 anticipated, and its instruction applies: re-scope around Phases 1, 4 and 5.

**3. The re-scope.**

- **Phase 1** ingests going forward only: real `issued_at` forecast snapshots per beach,
  and Hadera buoy readings (pending the IOLR permission action item above — until
  resolved, ingest it but keep the data internal/non-redistributed). Ashdod/Haifa are not
  wired up in Phase 1 pending CAMERI API access; the schema still models them (`buoys`
  table, `source` column) so they can be added later without a migration.
- **Phase 2** becomes a live-accumulating characterization: it reports on whatever history
  has actually accumulated since Phase 1 went live, refreshed periodically, rather than a
  one-time historical study. Its first runs will have very little data and should say so
  plainly rather than compute statistics on near-empty buckets.
- **Phase 3** goes straight to the fallback already anticipated in
  `prompts/phase-3-calibration.md` section 6 — a live bias tracker (bucketed running bias
  by direction/height/lead-time, served once a bucket passes a minimum n) — rather than
  attempting to train a model on data that does not exist. A trained model becomes a
  later addition once enough live history has accumulated; the results doc should include
  a dated projection of when that might be.
- **Phases 4 and 5** are unaffected by this finding — they don't depend on historical
  forecast/measurement pairs — and become the project's primary source of near-term value,
  per the planning doc's own contingency.

Editing `prompts/phase-1-ingestion.md`, `prompts/phase-2-alignment.md`, and
`prompts/phase-3-calibration.md` now to reflect this, per this phase's own instruction to
update downstream prompts rather than silently deviate from them.
