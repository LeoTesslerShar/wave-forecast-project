# Phase 4 — Subscriptions, deduplication, calibrated threshold and Web Push

Read `PROMPT.md`, `docs/PLANNING.md` (section 6 "Phase 5" in the original plan, section 7),
and `docs/BIAS_ANALYSIS.md` first. Phase 3's quality score is the input this phase alerts on.

The alert is the visible surface of the project, but the engineering here is the
**deduplication**. Forecasts refresh every few hours; the same Tuesday-morning window will
match a subscription six times before it arrives. A system that pushes six notifications
has failed, and so has one that suppresses the update when the window disappears.

**New in this phase: the calibrated threshold.** `docs/BIAS_ANALYSIS.md` measured that the
offshore model under-calls the top of the surfable range -- at a 1.5 m bar it misses 20.8%
of real sessions; at 1.0 m, 13.1%. A naive `forecast_height >= user_threshold` check
inherits that miss rate. Section 6 below is how this phase fixes that without pretending to
correct the physics.

---

## 1. Subscriptions

- CRUD over `subscriptions`: beach, min/max height, preferred swell direction range, time
  window (local time, e.g. 06:00–09:00), active flag.
- Identity: a simple opaque user identifier is enough (planning doc §8 — no full auth in
  this project). Keep the boundary clean enough that real auth could slot in later.
- Validation: sane height ranges, direction ranges that wrap correctly across 0°/360°,
  time windows that may cross midnight.

## 2. Evaluation

On every forecast refresh, re-evaluate active subscriptions against the current quality
score (Phase 2 exposure + Phase 3 quality output, including the `method` marker).

- Matching runs against the **latest** forecast per `valid_at` -- the access path built in
  Phase 1.
- The notification carries the same honesty markers the API does (hard rule 1). If the
  number is exposure-adjusted, the alert says it is an estimate, and shows the measured
  range, not a bare decimal.

## 3. Deduplication — the core problem

State every rule as code in one module, with the thresholds as named constants in one place.

1. **Never re-alert for a `valid_at` window already alerted on** for that subscription.
   `alerts_sent` holds `(subscription_id, valid_at, sent_at, conditions_snapshot)` — the
   snapshot is what makes rule 2 possible, so store the actual conditions, not a boolean.
2. **Unless conditions changed materially.** Define the threshold explicitly and defend it:
   e.g. height changed by more than X m, or the window's start/end moved by more than Y
   hours. A forecast drifting 1.4 m → 1.45 m is not news. A 1.4 m → 2.2 m upgrade is.
3. **Send a cancellation** when a previously alerted window stops qualifying. Silence after
   a promise is worse than a correction — someone made plans.
4. **Idempotent delivery** (hard rule / planning doc §7): a crash mid-send, or two evaluation
   runs overlapping, must not double-send. Take a lock or make the send conditional on a
   write that the DB serialises.
5. **Cluster contiguous hours into one window.** Six good hours on Tuesday is one alert
   about a Tuesday window, not six hourly alerts. Define the contiguity rule.

## 4. Timezones

- Everything stored UTC. Evaluate user time windows in **Asia/Jerusalem**, DST-aware, via
  `zoneinfo` — never a fixed UTC offset. Israel's DST transitions will break a hardcoded
  offset twice a year, and the failure looks like "the 07:00 alert fired at 06:00".
- Test explicitly across a DST boundary in both directions.

## 5. Web Push

- VAPID keys from env, never committed (hard rule 4). `.env.example` lists the names only.
- Push subscription storage, `pywebpush` delivery.
- **Expiry handling:** 404/410 from the push service means the subscription is dead —
  deactivate it rather than retrying forever. Other failures retry with backoff.
- Payload: beach, window in local time, the height **range** (not a bare decimal), the
  quality score with its components, the honesty marker, deep link.

## 6. Calibrated threshold -- the fix for the model's known miss rate

Do not correct the forecast height. Instead, let the matching threshold absorb the
measured miss rate, and make that trade-off a visible user choice, not a silent fudge.

- From `docs/BIAS_ANALYSIS.md`'s GO/DON'T-GO table, derive a small number of named
  operating points (e.g. `strict`, `balanced`, `generous`) mapping to how far below the
  user's stated threshold the system should also alert, with the real trade-off numbers
  attached (e.g. "generous: catches roughly 13% more real sessions at your bar, roughly 8%
  more trips that don't pan out" -- use the actual measured percentages, not invented
  ones).
- Store the chosen operating point per subscription, default to `balanced`.
- The alert payload states which operating point fired and, when it fired *below* the
  user's literal threshold, says so explicitly -- "you asked for >=1.5 m; this is 1.35 m,
  alerted under the `generous` setting because forecasts at this level under-call roughly 1
  time in 5." No alert should look like the user's exact threshold was met when it was the
  calibrated fallback that actually fired.
- This entire mechanism only touches *which forecasts trigger an alert*. It must never
  change the displayed height itself -- that stays the raw offshore value plus the Phase 2
  exposure adjustment, honestly labelled. Do not let the threshold calibration leak into
  the number shown; keep it confined to the matching decision.

## 7. Seasonal sanity

`docs/BIAS_ANALYSIS.md` found only 26% of hours reach 1 m annually, and September sees it
1.3% of the time. The evaluation job should not need special-casing for this -- a
`>= threshold` check naturally goes quiet in summer -- but the **UI and any digest/summary
notification** should make an extended flat spell visible as "nothing meeting your
criteria this week" rather than silence that looks like the system stopped working. Cover
this with a test: a multi-week window with no qualifying hours produces a status a user can
check, not just an absence of pushes.

---

## Acceptance checks

Run and paste:

1. **The dedup test, as a scenario:** simulate 6 forecast refreshes over one target window
   where conditions drift slightly, then improve materially, then drop below threshold.
   Assert exactly: one initial alert, one material-change alert, one cancellation, and no
   others. Show the assertion and the output.
2. A DST-boundary test in both directions.
3. An idempotency test: run the evaluation job twice concurrently over the same state,
   assert one send.
4. A 410-response test showing the subscription is deactivated, not retried.
5. **Calibrated threshold test:** a forecast at, say, 1.35 m with a subscription set to
   >=1.5 m and `generous` fires; the same forecast with `strict` does not. The alert text
   for the fired case names the gap and the calibration reason.
6. **Seasonal sanity test:** a multi-week all-flat window produces a checkable
   "nothing qualifying" status, no crash, no spam.
7. An end-to-end run: create a subscription, force a matching forecast, show the push
   attempt in the logs with its full payload (range, quality components, operating point).
8. `docker compose run --rm api pytest`.

## Then

Final pass on the README: what the system does now (see `PROMPT.md` section 1 for the
honest framing -- convenience and beach discrimination, not superior wave-height accuracy),
what is validated versus heuristic, the measured result from `docs/BIAS_ANALYSIS.md`, and
the known limitations -- one offshore validation point (DeepLev, off Haifa), no ground
truth at any beach. Then report where the project stands. Phase 5 (thin UI) is the only
phase left.
