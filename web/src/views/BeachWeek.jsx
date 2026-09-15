import { ScoreBadge } from "../components/Badges.jsx";
import { bestHourForDate, hoursAtIntervalForDate, nextLocalDates, todayOrTomorrowLabel } from "../dateUtils.js";
import { Num } from "../labels.jsx";

/** One beach's 7-day outlook -- a daily row per local calendar date, each showing the
 * day's best hour (bestHourForDate, already server-scored) and its surf-height range
 * across the 3-hourly slots that day. Clicking a day drills into BeachDay. */
export default function BeachWeek({ beach, rows, onSelectDay, onBack }) {
  if (!beach) return <p className="muted">טוען...</p>;

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        &rlm;&larr; חזרה לרשימה
      </button>
      <h2>{beach.name_he || beach.name}</h2>

      {rows === null && <p className="muted">טוען תחזית...</p>}

      {rows !== null && (
        <div className="week-list">
          {nextLocalDates(7).map((date) => {
            const best = bestHourForDate(rows, date);
            const dayHours = hoursAtIntervalForDate(rows, date);
            const heights = dayHours
              .map((h) => h.size.surf_height_estimate)
              .filter((v) => v != null);
            return (
              <button
                key={date}
                className="week-row"
                onClick={() => onSelectDay(date)}
                disabled={dayHours.length === 0}
              >
                <span className="week-row-date">{todayOrTomorrowLabel(date)}</span>
                {best ? (
                  <>
                    <ScoreBadge score={best.quality_score} verdict={best.quality_verdict} />
                    <span className="muted">
                      {heights.length > 0 ? (
                        <Num>
                          {Math.min(...heights).toFixed(2)}–{Math.max(...heights).toFixed(2)}מ'
                        </Num>
                      ) : (
                        "אין נתונים"
                      )}
                    </span>
                  </>
                ) : (
                  <span className="muted">אין תחזית</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
