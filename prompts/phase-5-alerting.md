# Phase 5 — Subscriptions, deduplication and Web Push

Read `PROMPT.md` and `docs/PLANNING.md` (§6 Phase 5, §7) first.

The alert is the visible surface of the project, but the engineering here is the
**deduplication**. Forecasts refresh every few hours; the same Tuesday-morning window will
match a subscription six times before it arrives. A system that pushes six notifications
has failed, and so has one that suppresses the update when the window disappears.

---

## 1. Subscriptions

- CRUD over `subscriptions`: beach, min/max height, preferred swell direction range, time
  window (local time, e.g. 06:00–09:00), active flag.
- Identity: a simple opaque user identifier is enough (planning doc §8 — no full auth in
  this project). Keep the boundary clean enough that real auth could slot in later.
- Validation: sane height ranges, direction ranges that wrap correctly across 0°/360°,
  time windows that may cross midnight.

## 2. Evaluation

On every forecast refresh, re-evaluate active subscriptions against the current calibrated
forecast (Phase 3 + Phase 4 output, including the `method` marker).

- Matching runs against the **latest** forecast per `valid_at` — the access path built in
  Phase 1 §2.
- The notification carries the same honesty markers the API does (hard rule 1). If the
  number is exposure-adjusted, the alert says it is an estimate.

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
- Payload: beach, window in local time, expected height, the honesty marker, deep link.

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
5. An end-to-end run: create a subscription, force a matching forecast, show the push
   attempt in the logs with its payload.
6. `docker compose run --rm api pytest`.

## Then

Final pass on the README: what the system does, what is validated versus heuristic, what
the measured calibration result actually was (hard rule 2), and the known limitations —
deep-water buoys, three of them, no ground truth at the break. Then report where the
project stands.
