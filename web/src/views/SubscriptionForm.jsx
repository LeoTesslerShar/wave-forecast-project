import { useEffect, useState } from "react";
import { api } from "../api.js";

const OPERATING_POINTS = [
  { value: "strict", label: "Strict", hint: "alert only at your exact bar" },
  { value: "balanced", label: "Balanced (default)", hint: "leans slightly below your bar to catch borderline sessions" },
  { value: "generous", label: "Generous", hint: "leans further below your bar -- catches more real sessions, more false alarms" },
];

/** Beach(es), threshold, time window, operating point -- prompts/phase-5-ui.md section 1.
 * Submits to the existing Phase 4 API; no new backend logic. */
export default function SubscriptionForm() {
  const [beaches, setBeaches] = useState([]);
  const [userId, setUserId] = useState("");
  const [beachId, setBeachId] = useState("");
  const [minHeight, setMinHeight] = useState("1.0");
  const [maxHeight, setMaxHeight] = useState("");
  const [windowStart, setWindowStart] = useState("06:00");
  const [windowEnd, setWindowEnd] = useState("09:00");
  const [operatingPoint, setOperatingPoint] = useState("balanced");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { ok: bool, message: string }
  const [subscriptions, setSubscriptions] = useState(null);

  useEffect(() => {
    api.listBeaches().then((list) => {
      setBeaches(list);
      if (list.length > 0) setBeachId(list[0].id);
    });
  }, []);

  async function refreshSubscriptions(uid) {
    if (!uid) {
      setSubscriptions(null);
      return;
    }
    try {
      setSubscriptions(await api.listSubscriptions(uid));
    } catch {
      setSubscriptions(null);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setResult(null);
    try {
      const body = {
        user_id: userId,
        beach_id: beachId,
        min_height: minHeight === "" ? null : Number(minHeight),
        max_height: maxHeight === "" ? null : Number(maxHeight),
        time_window_start: `${windowStart}:00`,
        time_window_end: `${windowEnd}:00`,
        operating_point: operatingPoint,
      };
      const created = await api.createSubscription(body);
      setResult({ ok: true, message: `Subscription #${created.id} created.` });
      await refreshSubscriptions(userId);
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate(id) {
    await api.setSubscriptionActive(id, false);
    await refreshSubscriptions(userId);
  }

  return (
    <div className="subscription-view">
      <form className="subscription-form" onSubmit={handleSubmit}>
        <label>
          Your identifier
          <input
            type="text"
            required
            placeholder="e.g. an email or any name"
            value={userId}
            onChange={(e) => {
              setUserId(e.target.value);
              refreshSubscriptions(e.target.value);
            }}
          />
        </label>

        <label>
          Beach
          <select value={beachId} onChange={(e) => setBeachId(e.target.value)}>
            {beaches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>

        <div className="form-row">
          <label>
            Min height (m)
            <input
              type="number"
              step="0.1"
              min="0"
              max="20"
              value={minHeight}
              onChange={(e) => setMinHeight(e.target.value)}
            />
          </label>
          <label>
            Max height (m, optional)
            <input
              type="number"
              step="0.1"
              min="0"
              max="20"
              value={maxHeight}
              onChange={(e) => setMaxHeight(e.target.value)}
            />
          </label>
        </div>

        <div className="form-row">
          <label>
            Window start
            <input type="time" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
          </label>
          <label>
            Window end
            <input type="time" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
          </label>
        </div>
        <p className="muted small">
          A window that ends before it starts (e.g. 22:00-02:00) crosses midnight -- that's fine.
        </p>

        <fieldset>
          <legend>Alert sensitivity</legend>
          {OPERATING_POINTS.map((op) => (
            <label key={op.value} className="radio-row">
              <input
                type="radio"
                name="operating_point"
                value={op.value}
                checked={operatingPoint === op.value}
                onChange={() => setOperatingPoint(op.value)}
              />
              <strong>{op.label}</strong> -- {op.hint}
            </label>
          ))}
          <p className="muted small">
            The calibrated fallback never changes the displayed height -- it only widens which
            forecasts trigger an alert, and the alert says so when it fires below your literal
            bar (docs/BIAS_ANALYSIS.md).
          </p>
        </fieldset>

        <button type="submit" disabled={submitting || !userId || !beachId}>
          {submitting ? "Creating..." : "Create subscription"}
        </button>

        {result && <p className={result.ok ? "success" : "error"}>{result.message}</p>}
      </form>

      {subscriptions !== null && (
        <div className="subscription-list">
          <h3>Your subscriptions</h3>
          {subscriptions.length === 0 && <p className="muted">None yet.</p>}
          {subscriptions.map((s) => (
            <div className="subscription-row" key={s.id}>
              <span>
                #{s.id} {s.beach_id} &ge;{s.min_height ?? "-"}m {s.time_window_start}-
                {s.time_window_end} ({s.operating_point}) {s.active ? "" : "(inactive)"}
              </span>
              {s.active && <button onClick={() => handleDeactivate(s.id)}>Deactivate</button>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
