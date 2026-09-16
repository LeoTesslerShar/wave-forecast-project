import WaveChart from "../components/WaveChart.jsx";
import { MoonIcon, SunIcon } from "../components/Icons.jsx";
import { hoursAtIntervalForDate, localHourLabel, localHourOfDay, nextLocalDates, todayOrTomorrowLabel } from "../dateUtils.js";
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

/** One beach's 7-day outlook. A wave-height+score chart across the whole week first, then
 * one row PER DAY -- each row itself a strip of the day's 3-hour slots (icon, score,
 * height), not a single summary number, so the day's shape is visible at a glance before
 * drilling in. Clicking a day expands into BeachDay's full 9-column table. */
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
        <div className="week-list">
          {nextLocalDates(7).map((date) => {
            const dayHours = hoursAtIntervalForDate(rows, date);
            if (dayHours.length === 0) return null;
            return (
              <button key={date} className="week-day-row" onClick={() => onSelectDay(date)}>
                <div className="week-day-row-label">{todayOrTomorrowLabel(date)}</div>
                <div className="week-day-row-strip">
                  {dayHours.map((h) => (
                    <div className="week-hour-cell" key={h.valid_at}>
                      <div className="week-hour-icon">{isDaytime(h.valid_at) ? <SunIcon size={14} /> : <MoonIcon size={14} />}</div>
                      <div className="week-hour-time muted">
                        <Num>{localHourLabel(h.valid_at)}</Num>
                      </div>
                      <div className={`week-hour-score ${VERDICT_FILL_CLASS[h.quality_verdict] || ""}`}>
                        <Num>{h.quality_score.toFixed(1)}</Num>
                      </div>
                      <div className="week-hour-height muted">
                        {h.size.surf_height_estimate != null ? <Num>{Math.round(h.size.surf_height_estimate * 100)}</Num> : "--"}
                      </div>
                    </div>
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
