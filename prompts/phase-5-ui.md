# Phase 5 — Thin frontend

Read `PROMPT.md` first. This is the last phase. By now every API this UI calls already
exists (Phases 1-4); this phase is presentation only.

**Explicitly not the point of the project** (`PROMPT.md` §3). Do not spend effort here that
a backend phase could have used, and do not let this phase invent new backend logic —
if the UI needs data the API doesn't provide, that's a bug in an earlier phase, not a
reason to compute it client-side.

---

## 1. Scope

Three views, React, minimal styling:

- **Beach list, ranked for a chosen day** — the primary view. Calls Phase 2/3's ranked
  output; shows quality verdict, size range, wind, per beach, sorted best-to-worst for the
  selected day. This is the view that answers "which beach, today."
- **Single-beach breakdown** — the full component detail from Phase 3's API response
  (size, period, wind, chop ratio, confidence markers) for one beach, one time window. Not
  a chart-heavy dashboard — a readable breakdown a surfer can scan in five seconds.
- **Subscription form** — beach(es), threshold, time window, operating point
  (`strict`/`balanced`/`generous` from Phase 4 §6), submit to the Phase 4 API.

## 2. The honesty requirement carries into the UI

Hard rule 1 does not stop at the API boundary. Every screen that shows a heuristic value
(size estimate, quality verdict) must visually distinguish it from anything measured —
not buried in a tooltip nobody opens. A simple convention is enough: an explicit "estimate"
label or icon next to any exposure/quality-derived number, consistently applied. Do not
render a range as if it were a precise decimal — show the range.

## 3. What NOT to build

- No client-side scoring logic — Phase 3 owns quality scoring.
- No separate state store duplicating what the API already returns.
- No auth beyond whatever minimal identifier Phase 4's subscription API expects.
- No mobile app — this is a responsive web page, consistent with the planning doc's Web
  Push decision (no app store dependency).

---

## Acceptance checks

Run and paste:

1. The ranked beach list for a real day, screenshot or rendered HTML, showing at least
   three beaches with visibly different quality verdicts.
2. The single-beach breakdown view showing every component from Phase 3's API response,
   with the "estimate" marker visibly distinct from measured values.
3. A subscription created through the form, confirmed via the Phase 4 API that it was
   stored correctly.
4. The page rendering sanely with zero qualifying beaches (the seasonal-flat case from
   Phase 4 §7) — no broken empty state.
5. `docker compose up` serving the frontend alongside the API from a clean state.

## Then

This closes the build. Final README pass: what the whole system does end to end, the
honest framing from `PROMPT.md` §1, how to run it, and what's still not validated (and
never will be, by design — no ground truth exists at any Israeli beach).
