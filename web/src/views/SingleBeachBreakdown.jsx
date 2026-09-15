import { useEffect, useState } from "react";
import { api } from "../api.js";
import { localDateString, localHourLabel, localHourOfDay, todayLocalDateString } from "../dateUtils.js";

// Shown at a 3-hour cadence (00, 03, 06, ... local) rather than every hour -- enough to see
// how a window develops without a 24-row dropdown for one day.
const HOUR_INTERVAL = 3;
import { ConfidenceBadge, RangedValue, VerdictBadge } from "../components/Badges.jsx";

/** Every component from Phase 3's API response, for one beach, one hour -- "readable in
 * five seconds," not a chart dashboard. prompts/phase-5-ui.md section 1. */
export default function SingleBeachBreakdown() {
  const [beaches, setBeaches] = useState([]);
  const [beachId, setBeachId] = useState("");
  const [date, setDate] = useState(todayLocalDateString());
  const [hourly, setHourly] = useState(null);
  const [selectedIso, setSelectedIso] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .listBeaches()
      .then((list) => {
        setBeaches(list);
        if (list.length > 0) setBeachId(list[0].id);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!beachId) return;
    setHourly(null);
    setError(null);
    api
      .getBeachQuality(beachId, 168)
      .then((rows) => {
        setHourly(rows);
        const onDate = rows.filter(
          (r) => localDateString(r.valid_at) === date && localHourOfDay(r.valid_at) % HOUR_INTERVAL === 0,
        );
        setSelectedIso(onDate.length > 0 ? onDate[0].valid_at : rows[0]?.valid_at || "");
      })
      .catch((e) => setError(e.message));
  }, [beachId, date]);

  const hoursForDate = (hourly || []).filter(
    (r) => localDateString(r.valid_at) === date && localHourOfDay(r.valid_at) % HOUR_INTERVAL === 0,
  );
  const selected = (hourly || []).find((r) => r.valid_at === selectedIso);

  return (
    <div>
      <div className="toolbar">
        <label>
          Beach:{" "}
          <select value={beachId} onChange={(e) => setBeachId(e.target.value)}>
            {beaches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Day: <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          Hour:{" "}
          <select value={selectedIso} onChange={(e) => setSelectedIso(e.target.value)}>
            {hoursForDate.map((r) => (
              <option key={r.valid_at} value={r.valid_at}>
                {localHourLabel(r.valid_at)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}
      {hourly === null && !error && <p className="muted">Loading...</p>}
      {hourly !== null && hoursForDate.length === 0 && (
        <p className="muted">No forecast data for this beach on {date}.</p>
      )}

      {selected && (
        <div className="breakdown-card">
          <div className="breakdown-header">
            <h2>{beaches.find((b) => b.id === beachId)?.name}</h2>
            <span className="muted">{localHourLabel(selected.valid_at)} local</span>
          </div>

          <div className="breakdown-verdict">
            <VerdictBadge verdict={selected.quality_verdict} />
            <span className="muted">score {selected.quality_score.toFixed(2)}</span>
          </div>
          <p className="reasoning">{selected.quality_reasoning}</p>

          <table className="breakdown-table">
            <tbody>
              <tr>
                <th>Size (surf height)</th>
                <td>
                  <RangedValue
                    estimate={selected.size.surf_height_estimate}
                    range={selected.size.surf_height_range}
                    confidence={selected.size.confidence.surf_height}
                  />
                </td>
              </tr>
              <tr>
                <th>Offshore raw</th>
                <td>
                  {selected.size.components.offshore_raw != null
                    ? `${selected.size.components.offshore_raw.toFixed(2)}m`
                    : "no data"}
                  <ConfidenceBadge confidence={selected.size.confidence.offshore_raw} />
                </td>
              </tr>
              <tr>
                <th>Exposure basis</th>
                <td className="muted">{selected.size.exposure_basis}</td>
              </tr>
              <tr>
                <th>Period</th>
                <td>
                  {selected.period_s != null ? `${selected.period_s.toFixed(1)}s` : "no data"} (
                  {selected.period_band})
                  <ConfidenceBadge confidence={selected.confidence.period} />
                </td>
              </tr>
              <tr>
                <th>Wind</th>
                <td>
                  {selected.wind.speed_kmh != null ? (
                    <>
                      {selected.wind.speed_kmh.toFixed(0)} km/h from{" "}
                      {selected.wind.direction_deg?.toFixed(0)}&deg; ({selected.wind.relation_to_shore}
                      {selected.wind.gusty ? ", gusty" : ""}), gusts{" "}
                      {selected.wind.gusts_kmh?.toFixed(0)} km/h
                    </>
                  ) : (
                    "no data"
                  )}
                  <ConfidenceBadge confidence={selected.confidence.wind} />
                </td>
              </tr>
              <tr>
                <th>Chop ratio</th>
                <td>
                  {selected.chop_ratio != null ? selected.chop_ratio.toFixed(2) : "no data"} (
                  {selected.chop_band})
                  <ConfidenceBadge confidence={selected.confidence.chop} />
                </td>
              </tr>
              <tr>
                <th>Quality verdict</th>
                <td>
                  {selected.quality_verdict}
                  <ConfidenceBadge confidence={selected.confidence.quality_verdict} />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
