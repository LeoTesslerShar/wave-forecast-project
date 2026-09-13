# Surf Alert System — master build prompt

This file is the standing context for every build session on this project. It is not a
phase task. The work happens in `prompts/phase-N-*.md`, pasted one at a time.

**If you are a Claude Code session starting work here: read this file, then read
[docs/PLANNING.md](docs/PLANNING.md) in full, then read the single phase prompt you were
given. Do not start the next phase on your own initiative.**

---

## 1. What is being built

A continuously running backend that turns a generic regional wave forecast into a
specific, honest answer to "is it worth surfing at *this* beach on Tuesday morning".

```
raw model forecast (Open-Meteo Marine)
    -> [1] bias correction      trained on measured buoy history   VALIDATED
    -> [2] per-beach exposure   shoreline bearing vs swell angle   HEURISTIC, UNVALIDATED
    -> [3] user criteria match  beach, height, direction, time
    -> alert (Web Push)
```

The alert is the visible surface. The value is in stages 1 and 2 and in the pipeline that
keeps them fed. **This is a backend/systems project, not a data-science notebook.** When a
decision is a toss-up, favour "a service that runs continuously and degrades gracefully"
over "an analysis that was run once".

`docs/PLANNING.md` is the canonical spec. Where this file and the planning doc disagree,
the planning doc wins and you should flag the contradiction.

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
| Git | 2.47 — repo is **not** initialised yet; Phase 1 does that |

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
- **Frontend:** React, minimal — beach list, current calibrated conditions, subscription
  form. Explicitly not the point of the project. Do not spend effort here that a backend
  phase could have used.
- **Deploy:** Docker Compose, targeting a free-tier host.
- **CI:** GitHub Actions running tests + lint on push.
- **Testing:** pytest. HTTP to upstreams is mocked from committed fixtures in unit tests;
  a small separately-marked set of live-network tests may exist but must never gate CI.

---

## 4. Hard rules

These are binding in every phase. A phase is not done if it violates one.

1. **Never present heuristic output as validated output.** The per-beach exposure layer
   (stage 2) is geometry and intuition, not measurement. Anywhere its output surfaces —
   API response, UI, docs, logs — it carries a marker saying so.
2. **Report model performance against the raw-forecast baseline, whatever the number is.**
   If the calibration does not beat the uncorrected forecast, that goes in the results
   table and in the README. A clearly measured negative result is a legitimate outcome and
   a better story than an inflated one.
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
prompts/phase-0-verify.md        gate — answer the open questions against live APIs
prompts/phase-1-ingestion.md     the foundation; everything depends on it
prompts/phase-2-alignment.md     forecast <-> measurement pairs, bias characterisation
prompts/phase-3-calibration.md   the model, chronologically validated
prompts/phase-4-exposure.md      per-beach geometry (heuristic)
prompts/phase-5-alerting.md      subscriptions, dedup, Web Push
```

Workflow: paste one phase prompt into a session → review the diff → commit → next phase.
One phase per session where practical; the context stays clean and the review stays real.

**Phase 0 is a gate, not a formality.** Its verdict decides whether Phase 3 is viable at
all. Do not start Phase 1 before `docs/DATA_SOURCES.md` exists with real probe output in it.

If a phase discovers something that invalidates a later phase's assumptions, **edit that
later phase's prompt file** as part of your work and say what you changed. Do not silently
deviate from a written prompt, and do not carry out a plan you have just learned is wrong.

---

## 7. Standing instruction on honesty

This project's whole premise is that existing apps show unvalidated numbers with false
confidence. A build that does the same thing with better branding has failed.

So: when a source is unavailable, when a sample is too small to conclude anything, when a
model does not beat baseline, when a heuristic is a guess — write that down in the
deliverable, in the place a reader would look. Not in a comment, not only in chat. The
honest version of this project is more interesting than the polished one.
