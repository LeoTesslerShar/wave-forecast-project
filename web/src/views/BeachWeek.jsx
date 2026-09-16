import WaveChart from "../components/WaveChart.jsx";
import { WeatherIcon, WindArrowIcon } from "../components/Icons.jsx";
import { bestHourForDate, hoursAtIntervalForDate, localHourOfDay, nextLocalDates, todayOrTomorrowLabel } from "../dateUtils.js";
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

/** One beach's 7-day outlook: a wave-height+score chart across the whole week, then one
 * row per day -- a SUMMARY of that day (best hour's score/wind, the day's full height
 * range, the midday weather) in the same pill-table language as BeachDay's hourly table,
 * not a different design per screen. Clicking a day drills into BeachDay's full detail. */
export default function BeachWeek({ beach, rows, onSelectDay, onBack }) {
  if (!beach) return <p className="muted">טוען...</p>;

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        &rlm;&larr; חזרה לרשימה
      </button>
      <h2>{beach.name_he || beach.name}</h2>

      {rows === null && <p className="muted">טוען תחזית...</p>}

      {rows !== null && <WaveChart rows={rows} />}

      {rows !== null && (
        <div className="day-table-scroll">
          <table className="day-table beach-list-table">
            <thead>
              <tr>
                <th>יום</th>
                <th>מזג אוויר</th>
                <th>גובה גלישה</th>
                <th>ציון</th>
                <th>רוח</th>
              </tr>
            </thead>
            <tbody>
              {nextLocalDates(7).map((date) => {
                const dayHours = hoursAtIntervalForDate(rows, date);
                if (dayHours.length === 0) return null;
                const best = bestHourForDate(rows, date);
                // Midday-most hour available, for a representative weather/temperature
                // reading -- a day's weather is shown as one icon, not one per 3h slot.
                const midday = dayHours.reduce((closest, h) =>
                  Math.abs(localHourOfDay(h.valid_at) - 13) < Math.abs(localHourOfDay(closest.valid_at) - 13) ? h : closest,
                );
                const heights = dayHours.flatMap((h) => h.size.surf_height_range || []).filter((v) => v != null);
                return (
                  <tr key={date} className="beach-list-row" onClick={() => onSelectDay(date)}>
                    <td className="cell-beach-name">{todayOrTomorrowLabel(date)}</td>
                    <td className="cell-hour" title={midday.weather_label}>
                      <WeatherIcon iconKey={midday.weather_icon} isDay={isDaytime(midday.valid_at)} size={18} />
                      <span className="muted cell-temp">
                        {midday.temperature_c != null ? <Num>{Math.round(midday.temperature_c)}°</Num> : "--"}
                      </span>
                    </td>
                    <td>
                      <span className="pill pill-blue">
                        {heights.length > 0 ? (
                          <Num>
                            {Math.round(Math.min(...heights) * 100)}-{Math.round(Math.max(...heights) * 100)} ס"מ
                          </Num>
                        ) : (
                          "--"
                        )}
                      </span>
                    </td>
                    <td>
                      {best ? (
                        <span className={`pill score-fill ${VERDICT_FILL_CLASS[best.quality_verdict] || ""}`}>
                          <Num>{best.quality_score.toFixed(1)}</Num>
                        </span>
                      ) : (
                        "--"
                      )}
                    </td>
                    <td>
                      {best ? (
                        <span className={`pill wind-pill ${windPillClass(best.wind.speed_kmh, best.wind.relation_to_shore)}`}>
                          <WindArrowIcon directionDeg={best.wind.direction_deg} />
                          {best.wind.speed_kmh != null ? `${best.wind.speed_kmh.toFixed(0)} קמ"ש` : "--"}
                        </span>
                      ) : (
                        "--"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
