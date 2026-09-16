import { WeatherIcon, WindArrowIcon } from "../components/Icons.jsx";
import { localHourOfDay, nearestSlotTo } from "../dateUtils.js";
import { Num } from "../labels.jsx";

const VERDICT_FILL_CLASS = {
  flat: "fill-flat",
  poor: "fill-poor",
  fair: "fill-fair",
  good: "fill-good",
  excellent: "fill-excellent",
};

function isDaytime(isoTimestamp) {
  const h = localHourOfDay(isoTimestamp);
  return h >= 6 && h < 18;
}

function windPillClass(speedKmh, relation) {
  if (speedKmh == null) return "wind-calm";
  if (relation === "offshore" || relation === "glassy") {
    return speedKmh < 50 ? "wind-calm" : "wind-strong";
  }
  if (speedKmh < 12) return "wind-calm";
  if (speedKmh < 25) return "wind-moderate";
  return "wind-strong";
}

/** The primary view -- current conditions (nearest hour to now), one row per beach,
 * styled the same pill-table language as BeachDay's hourly table so the whole app reads as
 * one consistent design, not a different look per screen. Deliberately dense, unlike the
 * old RankedBeachList's ~150px cards -- prompts/phase-5-ui.md section 3 still governs:
 * nothing here recomputes size/wind/quality, only picks which already-computed hour to
 * show and how to sort the rows. */
export default function BeachList({ beaches, error, qualityByBeach, onSelectBeach }) {
  if (error) return <p className="error">שגיאה בטעינת רשימת החופים: {error}</p>;
  if (beaches.length === 0) return <p className="muted">טוען...</p>;

  const rows = beaches
    .map((beach) => {
      const data = qualityByBeach[beach.id];
      const now = Array.isArray(data) ? nearestSlotTo(data) : null;
      return { beach, now, loading: data === "loading" || data === undefined, failed: data instanceof Error };
    })
    .sort((a, b) => (b.now?.quality_score ?? -1) - (a.now?.quality_score ?? -1));

  return (
    <div className="day-table-scroll">
      <table className="day-table beach-list-table">
        <thead>
          <tr>
            <th>חוף</th>
            <th>מזג אוויר</th>
            <th>גובה גלישה</th>
            <th>ציון</th>
            <th>רוח</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ beach, now, loading, failed }) => (
            <tr key={beach.id} className="beach-list-row" onClick={() => now && onSelectBeach(beach.id)}>
              <td className="cell-beach-name">{beach.name_he || beach.name}</td>
              {now ? (
                <>
                  <td className="cell-hour" title={now.weather_label}>
                    <WeatherIcon iconKey={now.weather_icon} isDay={isDaytime(now.valid_at)} size={18} />
                    <span className="muted cell-temp">
                      {now.temperature_c != null ? <Num>{Math.round(now.temperature_c)}°</Num> : "--"}
                    </span>
                  </td>
                  <td>
                    <span className="pill pill-blue">
                      {now.size.surf_height_range ? (
                        <Num>
                          {Math.round(now.size.surf_height_range[0] * 100)}-
                          {Math.round(now.size.surf_height_range[1] * 100)} ס"מ
                        </Num>
                      ) : (
                        "--"
                      )}
                    </span>
                  </td>
                  <td>
                    <span className={`pill score-fill ${VERDICT_FILL_CLASS[now.quality_verdict] || ""}`}>
                      <Num>{now.quality_score.toFixed(1)}</Num>
                    </span>
                  </td>
                  <td>
                    <span className={`pill wind-pill ${windPillClass(now.wind.speed_kmh, now.wind.relation_to_shore)}`}>
                      <WindArrowIcon directionDeg={now.wind.direction_deg} />
                      <Num>{now.wind.speed_kmh != null ? now.wind.speed_kmh.toFixed(0) : "--"} קמ"ש</Num>
                    </span>
                  </td>
                </>
              ) : (
                <td colSpan={4} className="muted">
                  {failed ? "שגיאה בטעינה" : loading ? "טוען..." : "אין נתונים"}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
