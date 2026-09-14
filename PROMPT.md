# Surf Alert System — master build prompt

This file is the standing context for every build session on this project. It is not a
phase task. The work happens in `prompts/phase-N-*.md`, pasted one at a time.

**If you are a Claude Code session starting work here: read this file, then read
[docs/PLANNING.md](docs/PLANNING.md) in full, then read the single phase prompt you were
given. Do not start the next phase on your own initiative.**

---

## 1. What is being built

A continuously running backend that watches the surf for a handful of Israeli beaches and
pushes an alert when a session is actually worth driving to — ranked against the user's
other beaches, scored for quality, not just size.

```
Open-Meteo marine (height, period, swell/wind-sea split)   |
Open-Meteo forecast (wind speed/direction/gusts)           |
                                                             v
                              [1] beach exposure   shoreline bearing vs swell angle   HEURISTIC
                                                             v
                              [2] surf quality     size + period + wind + chop ratio  HEURISTIC
                                                             v
                              [3] decision         user threshold, time window,
                                                    calibrated hit/false-alarm point  MEASURED
                                                             v
                                                           alert
```

**This is not what the project set out to build, and that is on the record, not hidden.**
The original premise (`docs/PLANNING.md`) was to bias-correct the regional forecast against
measured buoy history. A spike against 11,161 hours of real measurement
(`docs/BIAS_ANALYSIS.md`) tested that premise and found it mostly false: in the height band
this user actually surfs (0.5-1.5 m), the model is already accurate to +/-0.19 m (90% of
hours) with essentially zero mean bias. There is no forecast error to correct where it
matters. That result is published, not buried, and it is why the value chain above looks
different from `docs/PLANNING.md`'s.

What the spike found instead: the model **misses 13-21% of real sessions** at the top of
the surfable range because it compresses extremes (reads 2.95 m when reality is 3.4 m).
That is not a number to correct — no correction shrinks the underlying +/-0.25 m spread —
it is a **threshold trade-off** the user can tune, calibrated against the measured
hit/false-alarm curve. That is what layer 3 above does, and it is the only layer backed by
measurement. Layers 1 and 2 are defensible physics and local surf knowledge (the local
pattern: swell arrives with the wind that made it, so the prized window is usually the dawn
after, once the land breeze turns offshore), not validated against ground truth, and are
labelled as such everywhere they surface — hard rule 1 below.

**The honest value of this system is convenience, beach discrimination and quality
judgement — not superior wave-height accuracy.** Any claim beyond that is false and not to
be made, in code, docs, or UI copy.

**This is a backend/systems project, not a data-science notebook.** When a decision is a
toss-up, favour "a service that runs continuously and degrades gracefully" over "an
analysis that was run once".

`docs/PLANNING.md` is the original spec and stays as the historical record of the starting
premise. `docs/BIAS_ANALYSIS.md` is what actually happened when that premise was tested.
Where either disagrees with this file, **this file wins** — it reflects what the data
supported, which the planning doc could not have known in advance.

---

## 2. Environment — stated, not to be guessed

| Fact | Value |
|---|---|
| Project root | `C:\Users\leote\Wave_Forecast_Project` |
| OS | Windows 11 |
| Shell | PowerShell 5.1 — **no `&&`, no `\|\|`, no ternary, no `??`**. Use `A; if ($?) { B }`. A Bash tool (Git Bash) is also available and takes POSIX syntax. |
| Python | 3.13, invoked as `py -3.13` or `py`. **`python` is not on PATH** — the bare name hits the Microsoft Store stub. Inside Docker and inside an activated venv, `python` is fine. |
| Node | 20.20.2 |
| Docker | 29.4, Compose v5.1.1 (`docker compose`, not `docker-compose`) |
| Git | 2.47 — repo initialised, first commits done (Phase 0, 0.5) |

Long strings for commit messages: use a single-quoted PowerShell here-string with the
closing `'@` at column 0, or use the Bash tool with a heredoc.

---

## 3. Stack — already decided, do not re-litigate

- **API + pipeline:** Python 3.13, FastAPI, SQLAlchemy 2.x, Alembic migrations, Pydantic
  settings from env.
- **Storage:** PostgreSQL. Plain Postgres by default. TimescaleDB only if a phase shows a
  concrete query that needs it, and the reason gets written down.
- **Scheduling:** APScheduler in-process to start. If you move to a separate worker,
  record the trigger and the reasoning in `docs/DECISIONS.md`.
- **Cache:** Redis, for served forecast responses only.
- **Notifications:** Web Push with VAPID (`pywebpush`). No native apps, no app store.
- **Frontend:** React, minimal — beach list ranked by quality, per-beach breakdown, subscription
  form. Explicitly not the point of the project. Do not spend effort here that a backend
  phase could have used.
- **Deploy:** Docker Compose, targeting a free-tier host.
- **CI:** GitHub Actions running tests + lint on push.
- **Testing:** pytest. HTTP to upstreams is mocked from committed fixtures in unit tests;
  a small separately-marked set of live-network tests may exist but must never gate CI.

---

## 4. Hard rules

These are binding in every phase. A phase is not done if it violates one.

1. **Never present heuristic output as validated output.** Beach exposure and surf
   quality scoring (layers 1-2) are geometry and local knowledge, not measurement.
   Anywhere their output surfaces — API response, UI, docs, logs — it carries a marker
   saying so. Layer 3's threshold calibration is the only layer backed by measurement
   (`docs/BIAS_ANALYSIS.md`); it does not launder the layers beneath it.
2. **Report performance against the raw-forecast baseline, whatever the number is.** This
   is how the project already found that bias correction wasn't viable in the surfable
   range (`docs/BIAS_ANALYSIS.md`) — the same discipline applies to the quality scorer
   (layer 2) and the threshold calibration (layer 3): if a component doesn't demonstrably
   help, that goes in the docs, not just in a commit that quietly drops it.
3. **No scraping of sources that prohibit it.** Check terms and `robots.txt` before
   fetching. No commercial surf-forecast sites, ever.
4. **No credentials, session cookies, API keys or VAPID private keys in the repository.**
   `.env` is gitignored from the first commit; `.env.example` carries the key names only.
5. **Every claim about an upstream data source is backed by evidence in the repo** — a
   committed sample payload, a recorded HTTP status, a dated note of what was requested.
   Never "the API supports X" from recollection. If you did not call it, you do not know.
6. **`issued_at` and `valid_at` are never collapsed** — not in a table, not in a query,
   not in an API response, not in a CSV export. The same target hour is forecast many
   times; that history is exactly what makes bias analysis and alert dedup possible.
7. **Graceful degradation is a feature, not error handling.** If the buoy feed is down,
   the system serves raw forecasts and says that it is doing so. Nothing 500s because an
   upstream is having a bad day.

---

## 5. Definition of done — applies to every phase

A phase is complete when all of these are true:

- [ ] Tests pass: `docker compose run --rm api pytest` green.
- [ ] `docker compose up` works from a clean state (`docker compose down -v` first).
- [ ] Every acceptance check in that phase's prompt has been **run**, with the real output
      pasted into your final message. Not described — pasted.
- [ ] New env vars appear in `.env.example`.
- [ ] `README.md` updated: what exists now, how to run it, what is not built yet.
- [ ] Any decision that the planning doc left open is recorded in `docs/DECISIONS.md` as a
      dated entry: what was chosen, what was rejected, why.
- [ ] Anything that turned out differently from what the phase prompt assumed is called
      out explicitly in your final message.

---

## 6. How to run the phases

```
prompts/phase-0-verify.md        DONE — data source verification; historical record
prompts/phase-0.5-deeplev.md     DONE — spike that tested the bias-correction premise
                                  and found it false in the surfable range; produced
                                  docs/BIAS_ANALYSIS.md. Not re-run; historical record.
prompts/phase-1-ingestion.md     the foundation — forecast + wind + buoy ingestion
prompts/phase-2-exposure.md      per-beach geometry (heuristic) — the main differentiator
prompts/phase-3-quality.md       surf quality scoring: size + period + wind + chop ratio
prompts/phase-4-alerting.md      subscriptions, dedup, calibrated threshold, Web Push
prompts/phase-5-ui.md            thin frontend — beach list, breakdown, subscription form
```

Workflow: paste one phase prompt into a session → review the diff → commit → next phase.
One phase per session where practical; the context stays clean and the review stays real.

**Phases 0 and 0.5 are done and are not re-run.** They exist so a later session
understands why the system looks like this — read them for context, not as a task.
`docs/DATA_SOURCES.md` and `docs/BIAS_ANALYSIS.md` are their outputs and are load-bearing:
every later phase's honesty claims cite them.

If a phase discovers something that invalidates a later phase's assumptions, **edit that
later phase's prompt file** as part of your work and say what you changed. Do not silently
deviate from a written prompt, and do not carry out a plan you have just learned is wrong.
This project has already done this once — see section 1 — and it produced a better result
than plowing ahead would have.

---

## 7. Standing instruction on honesty

This project's whole premise is that existing apps show unvalidated numbers with false
confidence. A build that does the same thing with better branding has failed.

So: when a source is unavailable, when a sample is too small to conclude anything, when a
model does not beat baseline, when a heuristic is a guess — write that down in the
deliverable, in the place a reader would look. Not in a comment, not only in chat. The
honest version of this project is more interesting than the polished one.
