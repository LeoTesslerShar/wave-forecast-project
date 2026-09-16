import { useEffect, useState } from "react";
import { api } from "../api.js";
import { localHourLabel } from "../dateUtils.js";
import { getUserEmail, getUserId, setUserEmail } from "../identity.js";
import { Num } from "../labels.jsx";

const OPERATING_POINTS = [
  { value: "strict", label: "מדויק", hint: "התראה רק בדיוק על הרף שקבעת" },
  { value: "balanced", label: "מאוזן (ברירת מחדל)", hint: "נוטה קצת מתחת לרף כדי לתפוס גם גלישות גבוליות" },
  { value: "generous", label: "נדיב", hint: "נוטה עוד יותר מתחת לרף -- תופס יותר גלישות אמיתיות, גם יותר התראות שווא" },
];

/** Standing recurring-criteria alerts (Beach + threshold + time window), alongside the
 * per-slot watches created from BeachDay's "התרע לי" buttons -- two different tools: a
 * standing rule vs. a one-off watch on a specific slot. */
export default function SubscriptionForm() {
  const [beaches, setBeaches] = useState([]);
  const [userId] = useState(getUserId());
  const [email, setEmail] = useState(getUserEmail());
  const [beachId, setBeachId] = useState("");
  const [minHeight, setMinHeight] = useState("1.0");
  const [maxHeight, setMaxHeight] = useState("");
  const [windowStart, setWindowStart] = useState("06:00");
  const [windowEnd, setWindowEnd] = useState("09:00");
  const [operatingPoint, setOperatingPoint] = useState("balanced");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { ok: bool, message: string }
  const [subscriptions, setSubscriptions] = useState(null);
  const [slotWatches, setSlotWatches] = useState(null);

  useEffect(() => {
    api.listBeaches().then((list) => {
      setBeaches(list);
      if (list.length > 0) setBeachId(list[0].id);
    });
    refreshSubscriptions();
    refreshSlotWatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function beachName(id) {
    return beaches.find((b) => b.id === id)?.name_he || id;
  }

  async function refreshSubscriptions() {
    try {
      setSubscriptions(await api.listSubscriptions(userId));
    } catch {
      setSubscriptions(null);
    }
  }

  async function refreshSlotWatches() {
    try {
      const list = await api.listSlotWatches(userId);
      setSlotWatches(list.filter((w) => w.status === "pending" || w.status === "alerted"));
    } catch {
      setSlotWatches(null);
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
        email: email || null,
        min_height: minHeight === "" ? null : Number(minHeight),
        max_height: maxHeight === "" ? null : Number(maxHeight),
        time_window_start: `${windowStart}:00`,
        time_window_end: `${windowEnd}:00`,
        operating_point: operatingPoint,
      };
      const created = await api.createSubscription(body);
      setResult({ ok: true, message: `נוצר מנוי #${created.id}.` });
      await refreshSubscriptions();
    } catch (err) {
      setResult({ ok: false, message: err.message });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate(id) {
    await api.setSubscriptionActive(id, false);
    await refreshSubscriptions();
  }

  async function handleCancelWatch(id) {
    await api.cancelSlotWatch(id);
    await refreshSlotWatches();
  }

  return (
    <div className="subscription-view">
      <form className="subscription-form" onSubmit={handleSubmit}>
        <label>
          אימייל להתראות (לא חובה)
          <input
            type="email"
            placeholder="name@example.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setUserEmail(e.target.value);
            }}
          />
        </label>
        <p className="muted small">
          בלי אימייל תגיעו רק התראות דחיפה בדפדפן. אם תמלאו אימייל, הוא יחול על המנוי הזה
          ועל כל מעקב שעה שתיצרו מעכשיו בעמוד של יום ספציפי.
        </p>

        <label>
          חוף
          <select value={beachId} onChange={(e) => setBeachId(e.target.value)}>
            {beaches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name_he || b.name}
              </option>
            ))}
          </select>
        </label>

        <div className="form-row">
          <label>
            גובה מינימלי (מ')
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
            גובה מקסימלי (מ', לא חובה)
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
            תחילת חלון
            <input type="time" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} />
          </label>
          <label>
            סוף חלון
            <input type="time" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} />
          </label>
        </div>
        <p className="muted small">חלון שמסתיים לפני שהוא מתחיל (למשל 22:00-02:00) חוצה חצות -- זה תקין.</p>

        <fieldset>
          <legend>רגישות התראה</legend>
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
            ההגדרה המכוילת לעולם לא משנה את הגובה המוצג -- היא רק מרחיבה אילו תחזיות מפעילות
            התראה, וההתראה עצמה מציינת כשזה קורה מתחת לרף המדויק שביקשת.
          </p>
        </fieldset>

        <button type="submit" disabled={submitting || !beachId}>
          {submitting ? "יוצר..." : "צור מנוי"}
        </button>

        {result && <p className={result.ok ? "success" : "error"}>{result.message}</p>}
      </form>

      <div className="subscription-lists">
        {subscriptions !== null && (
          <div className="subscription-list">
            <h3>המנויים שלי</h3>
            {subscriptions.length === 0 && <p className="muted">אין עדיין.</p>}
            {subscriptions.map((s) => (
              <div className="subscription-row" key={s.id}>
                <span>
                  #{s.id} {beachName(s.beach_id)} <Num>&ge;{s.min_height ?? "-"}מ'</Num>{" "}
                  <Num>
                    {s.time_window_start}-{s.time_window_end}
                  </Num>{" "}
                  ({OPERATING_POINTS.find((o) => o.value === s.operating_point)?.label || s.operating_point}){" "}
                  {s.active ? "" : "(לא פעיל)"}
                </span>
                {s.active && <button onClick={() => handleDeactivate(s.id)}>בטל</button>}
              </div>
            ))}
          </div>
        )}

        {slotWatches !== null && (
          <div className="subscription-list">
            <h3>מעקבים על שעה ספציפית</h3>
            {slotWatches.length === 0 && <p className="muted">אין עדיין -- לוחצים "התרע לי" על שעה בעמוד היום.</p>}
            {slotWatches.map((w) => (
              <div className="subscription-row" key={w.id}>
                <span>
                  {beachName(w.beach_id)} <Num>{localHourLabel(w.valid_at)}</Num>{" "}
                  {w.status === "alerted" ? "(הותרעת -- ממתין לשינוי)" : "(ממתין)"}
                </span>
                <button onClick={() => handleCancelWatch(w.id)}>בטל</button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
