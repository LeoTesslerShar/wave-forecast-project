import { useEffect, useState } from "react";
import { api } from "../api.js";
import { bestHourForDate, localHourLabel, todayLocalDateString } from "../dateUtils.js";
import { ConfidenceBadge, RangedValue, VerdictBadge } from "../components/Badges.jsx";

/** The primary view -- "which beach, today." Ranking is a client-side sort of the
 * already-computed quality_score (Phase 3); nothing here recomputes size, wind, chop or
 * verdict -- prompts/phase-5-ui.md section 3. */
export default function RankedBeachList() {
  const [date, setDate] = useState(todayLocalDateString());
  const [rows, setRows] = useState(null); // null = loading
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);

    (async () => {
      try {
        const beaches = await api.listBeaches();
        const results = await Promise.all(
          beaches.map(async (beach) => {
            try {
              const hourly = await api.getBeachQuality(beach.id, 168);
              const best = bestHourForDate(hourly, date);
              return best ? { beach, best } : null;
            } catch {
              return null; // one beach's fetch failing doesn't break the whole list
            }
          }),
        );
        if (cancelled) return;
        const ranked = results
          .filter(Boolean)
          .sort((a, b) => b.best.quality_score - a.best.quality_score);
        setRows(ranked);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [date]);

  return (
    <div>
      <div className="toolbar">
        <label>
          Day:{" "}
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
      </div>

      {error && <p className="error">Could not load beaches: {error}</p>}
      {rows === null && !error && <p className="muted">Loading...</p>}
      {rows !== null && rows.length === 0 && (
        <p className="muted">
          No forecast data for any beach on {date} yet -- outside the ingestion horizon, or
          the pipeline hasn't run recently. This is expected, not an error (see
          `/health` and each subscription's `/status`).
        </p>
      )}

      <div className="beach-list">
        {rows &&
          rows.map(({ beach, best }) => (
            <div className="beach-card" key={beach.id}>
              <div className="beach-card-header">
                <h3>{beach.name}</h3>
                <VerdictBadge verdict={best.quality_verdict} />
              </div>
              <div className="beach-card-body">
                <div>
                  <span className="label">Size</span>
                  <RangedValue
                    estimate={best.size.wave_height_estimate}
                    range={best.size.wave_height_range}
                    confidence={best.size.confidence.exposure}
                  />
                </div>
                <div>
                  <span className="label">Wind</span>
                  {best.wind.speed_kmh != null ? (
                    <span>
                      {best.wind.speed_kmh.toFixed(0)} km/h, {best.wind.relation_to_shore}
                      {best.wind.gusty ? " (gusty)" : ""}
                      <ConfidenceBadge confidence="measured_forecast" />
                    </span>
                  ) : (
                    <span className="muted">no data</span>
                  )}
                </div>
                <div>
                  <span className="label">Period</span>
                  <span>
                    {best.period_s != null ? `${best.period_s.toFixed(1)}s` : "no data"} (
                    {best.period_band})
                  </span>
                </div>
                <div>
                  <span className="label">Chop</span>
                  <span>{best.chop_band}</span>
                </div>
                <div className="best-hour">Best window: {localHourLabel(best.valid_at)} local</div>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
