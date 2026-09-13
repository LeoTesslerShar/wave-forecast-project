# Data sources — Phase 0 verification

Probed 2026-09-13. Every claim below is backed by a live HTTP call, quoted verbatim or
summarized with the exact fields observed, and a fixture committed under
`tests/fixtures/` or a script under `scripts/probe/`. Where a claim could not be verified
by a live call, it is marked **unresolved** rather than guessed.

---

## CORRECTION — 2026-09-13, same day, superseding the scope verdict below

**The Scope verdict at the bottom of this document is wrong. Read this first.**

It concluded "zero historical (forecast, measurement) pairs exist anywhere." What was
actually verified was narrower: zero pairs from the three sources the planning doc named
(CAMERI, ISRAMAR, Open-Meteo). The check was scoped to that list and then generalised from
it, instead of asking the broader question — *who else measures waves off Israel?* That
generalisation was not evidence-backed, which is a violation of hard rule 5 by the very
document meant to enforce it.

**What was missed: the DeepLev station** (full section below). A peer-reviewed, CC BY 4.0,
freely downloadable multi-year wave dataset from a deep-water mooring off Haifa, whose
coverage overlaps the Open-Meteo archive by roughly 21 months — approximately 15,000
hourly (model, measured) pairs across two full winters.

**What still stands from the original verdict:**

- There is no forecast-as-issued history with lead time, at any date, from Open-Meteo.
  Directly tested; `previous_dayN` returns null on historical dates. Lead-time bias
  remains obtainable only by accumulating forward.
- ISRAMAR Hadera has no history endpoint — live readings only.
- CAMERI Ashdod/Haifa bulk export remains gated behind institutional permission.

**What changes as a result:**

- Bias by swell direction, season and height regime — the bulk of the stage-1 claim — is
  trainable on historical data *today*. Phase 2 is a real historical study again, and
  Phase 3 section B (trained model) is the live path, not a deferred one.
- The IOLR written-permission blocker leaves the critical path: DeepLev is CC BY 4.0, so
  ISRAMAR Hadera becomes an optional supplementary source rather than the only ground truth.

The original verdict is left in place below, unedited and marked superseded, rather than
quietly rewritten.

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

## DeepLev — deep Levantine moored station (the source Phase 0 initially missed)

| Field | Value |
|---|---|
| What | Subsurface moored research station, first deployed Nov 2016. Up-looking Nortek Signature 500 ADCP mounted at ~30 m depth on a mooring in ~1470 m of water, deriving surface wave parameters. |
| Location | 33.05 N, 34.48 E — approximately 50 km offshore Haifa |
| Operator | IOLR / University of Haifa and partners |
| Publication | Earth System Science Data (2024), doi:10.5194/essd-16-2659-2024 |
| Data DOI | https://doi.org/10.17882/96904 (SEANOE repository) |
| Auth | None. Direct download, no registration. Verified 2026-09-13: HTTP 200 with real content-lengths on all three relevant files. |
| Licence | **CC BY 4.0** — attribution only. This is what removes the IOLR written-permission blocker from the critical path. |
| Format | NetCDF4, one file per deployment |
| Parameters | Significant wave height, maximal wave height, peak period, mean period (Tm02), energy period, peak direction, mean direction; plus 1D frequency spectra and 2D directional spectra |
| Resolution | Primarily 17-minute averages from 2 Hz sampling (one deployment at 4 Hz); frequency range 0.02-0.45 Hz |

### Deployment coverage vs the Open-Meteo archive (which starts ~1 Oct 2021)

| Deployment | File | Size | Coverage | Overlap with Open-Meteo |
|---|---|---|---|---|
| 1 | `105534.nc` | 265 MB | 16 Nov 2016 - 12 May 2017 | none |
| 2 | `105535.nc` | 262 MB | 1 Jun 2017 - 25 Nov 2017 | none |
| 3 | `105551.nc` | 1 GB | 4 Dec 2017 - 28 Apr 2018 | none |
| 4 | `105554.nc` | 2 GB | 31 Jul 2018 - 28 Mar 2019 | none (and significant data loss) |
| 5 | `105555.nc` | 323 MB | 13 May 2019 - 18 Dec 2019 | none |
| 6 | `105556.nc` | 625 MB | 18 Feb 2020 - 16 Sep 2020 | none |
| **7** | `105557.nc` | 1.15 GB | 27 Oct 2020 - 3 Nov 2021 | **~34 days** |
| **8** | `105561.nc` | 0.76 GB | 27 Dec 2021 - 30 Aug 2022 | **all 247 days** (documented data loss — verify) |
| **9** | `116859.nc` | 1.17 GB | 23 Feb 2023 - 5 Mar 2024 | **all 377 days** |

Download URL pattern: `https://www.seanoe.org/data/00857/96904/data/<id>.nc`

**Usable total: ~21 months, ~15,000 hourly (model, measured) pairs, spanning two full
winters.** Only deployments 7, 8 and 9 are worth downloading (~3.1 GB); 1-6 predate the
forecast archive entirely.

### Why an offshore station is the right instrument here

A wave in 1470 m of water has not interacted with the seabed, so DeepLev measures pure
deep-water sea state — precisely the quantity a global wave model computes. Comparing
model output against it isolates **model error**. A 24 m or nearshore buoy measures waves
already transformed by shoaling, refraction and bottom friction, so that comparison would
conflate model bias with coastal physics the model never attempted to resolve. Planning
doc section 4.1 already concluded stage 1 calibration is regional rather than per-beach;
DeepLev is a better regional instrument for that job than the three buoys it named.

### Known limitations — carry these into every write-up

- **Location:** off Haifa. Applying a correction learned here 150 km south off Ashdod
  assumes the model's bias is regionally coherent. Defensible for open-coast deep water in
  a single basin, but an assumption to state, not a proven fact.
- **Staleness:** coverage ends March 2024; today is September 2026. Open-Meteo's underlying
  models have likely changed since. The live bias tracker is the check on whether a
  historically-trained correction still holds.
- **Instrument:** a submerged ADCP inferring surface waves is not a surface-following
  waverider. Different error characteristics. ADCP depth varied 27-39 m across deployments,
  which the paper notes affects directional data quality; some deployments have ambiguous
  directional percentages.
- **Gaps:** deployments 4 and 8 are documented as having significant data loss. Deployment
  8 is one we need — quantify its actual gap structure during extraction rather than
  assuming 247 clean days.
- **Prior art:** the ESSD paper itself compares these observations against CMEMS-WAM
  (Nov 2016 - Jun 2021), finding strong Hs correlation, a negative bias in mean period, and
  model underestimation of high waves. Read it before trusting our own numbers — if our
  bias analysis disagrees sharply with a peer-reviewed comparison, ours is likely wrong.

### Attribution required (CC BY 4.0)

Haim Nir, Toledo Yaron, Mayzel Boaz, Grigorieva Vika, Soffer Rotem, Katz Timor, Alkalay
Ronen, Biton Eli, Lazar Ayah, Gildor Hezi, Berman-Frank Ilana, Weinstein Yishai, Herut
Barak (2016). Surface waves data from a submerged ADCP in the "DeepLev" Eastern Levantine
station. SEANOE. https://doi.org/10.17882/96904

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

## Scope verdict  — SUPERSEDED, see the CORRECTION at the top of this file

> **This section is wrong and is retained only as a record.** It generalised from the
> three sources the planning doc named to "every source," without checking whether other
> organisations measure waves off Israel. They do — see the DeepLev section above, which
> provides roughly 21 months of overlapping measured data. The specific findings about
> Open-Meteo, ISRAMAR and CAMERI below remain accurate; only the sweeping conclusion and
> the re-scope it triggered are withdrawn.

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
