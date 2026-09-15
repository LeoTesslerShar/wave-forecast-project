import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ConfidenceBadge, RangedValue, ScoreBadge } from "../components/Badges.jsx";
import { hoursAtIntervalForDate, localHourLabel, todayOrTomorrowLabel } from "../dateUtils.js";
import { getUserId } from "../identity.js";
import { CHOP_HE, Num, PERIOD_HE, WIND_RELATION_HE } from "../labels.jsx";
import { ensurePushRegistered } from "../push.js";

/** One day, one beach, 3-hour intervals -- exactly the fields asked for (wave height, wind
 * speed, swell direction, score) plus a per-slot watch toggle. Tapping a row expands it
 * into the full component breakdown (what SingleBeachBreakdown used to show as the whole
 * view) rather than navigating away. */
export default function BeachDay({ beach, rows, date, onBack }) {
  const [expanded, setExpanded] = useState(null); // valid_at of the expanded row
  const [watches, setWatches] = useState(null); // valid_at -> watch row, for THIS beach
  const [busyValidAt, setBusyValidAt] = useState(null);
  const [watchError, setWatchError] = useState(null);

  useEffect(() => {
    if (!beach) return;
    api
      .listSlotWatches(getUserId())
      .then((list) => {
        const map = {};
        for (const w of list) {
          if (w.beach_id === beach.id && (w.status === "pending" || w.status === "alerted")) {
            map[w.valid_at] = w;
          }
        }
        setWatches(map);
      })
      .catch(() => setWatches({}));
  }, [beach]);

  if (!beach) return <p className="muted">טוען...</p>;

  const dayHours = rows === null ? null : hoursAtIntervalForDate(rows, date);

  async function toggleWatch(hour) {
    setWatchError(null);
    setBusyValidAt(hour.valid_at);
    try {
      const existing = watches?.[hour.valid_at];
      if (existing) {
        await api.cancelSlotWatch(existing.id);
        setWatches((prev) => {
          const next = { ...prev };
          delete next[hour.valid_at];
          return next;
        });
      } else {
        await ensurePushRegistered();
        const created = await api.createSlotWatch({
          user_id: getUserId(),
          beach_id: beach.id,
          valid_at: hour.valid_at,
        });
        setWatches((prev) => ({ ...prev, [hour.valid_at]: created }));
      }
    } catch (err) {
      setWatchError(err.message);
    } finally {
      setBusyValidAt(null);
    }
  }

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        &rlm;&larr; חזרה לשבוע
      </button>
      <h2>
        {beach.name_he || beach.name} · {todayOrTomorrowLabel(date)}
      </h2>

      {watchError && <p className="error">{watchError}</p>}
      {dayHours === null && <p className="muted">טוען תחזית...</p>}
      {dayHours !== null && dayHours.length === 0 && <p className="muted">אין תחזית ליום זה.</p>}

      <div className="day-list">
        {dayHours?.map((h) => {
          const watch = watches?.[h.valid_at];
          const isExpanded = expanded === h.valid_at;
          return (
            <div className="day-row-wrap" key={h.valid_at}>
              <button className="day-row" onClick={() => setExpanded(isExpanded ? null : h.valid_at)}>
                <span className="day-row-time">
                  <Num>{localHourLabel(h.valid_at)}</Num>
                </span>
                <span className="day-row-height">
                  {h.size.surf_height_estimate != null ? (
                    <Num>{h.size.surf_height_estimate.toFixed(2)}מ'</Num>
                  ) : (
                    "--"
                  )}
                </span>
                <span className="day-row-wind muted">
                  {h.wind.speed_kmh != null ? <Num>{h.wind.speed_kmh.toFixed(0)} קמ"ש</Num> : "--"}
                </span>
                <span className="day-row-swell muted">
                  {h.swell_direction_deg != null ? <Num>{h.swell_direction_deg.toFixed(0)}°</Num> : "--"}
                </span>
                <ScoreBadge score={h.quality_score} verdict={h.quality_verdict} />
              </button>
              <button
                className={watch ? "watch-btn watching" : "watch-btn"}
                onClick={() => toggleWatch(h)}
                disabled={busyValidAt === h.valid_at}
              >
                {busyValidAt === h.valid_at ? "..." : watch ? "צופה ✓" : "התרע לי"}
              </button>

              {isExpanded && (
                <div className="breakdown-card day-row-detail">
                  <p className="reasoning">{h.quality_reasoning}</p>
                  <table className="breakdown-table">
                    <tbody>
                      <tr>
                        <th>גובה (גובה גלישה)</th>
                        <td>
                          <RangedValue
                            estimate={h.size.surf_height_estimate}
                            range={h.size.surf_height_range}
                            confidence={h.size.confidence.surf_height}
                          />
                        </td>
                      </tr>
                      <tr>
                        <th>גובה מובהק (ים פתוח)</th>
                        <td>
                          {h.size.components.offshore_raw != null ? (
                            <Num>{h.size.components.offshore_raw.toFixed(2)}מ'</Num>
                          ) : (
                            "אין נתונים"
                          )}
                          <ConfidenceBadge confidence={h.size.confidence.offshore_raw} />
                        </td>
                      </tr>
                      <tr>
                        <th>בסיס חשיפה</th>
                        <td className="muted">{h.size.exposure_basis}</td>
                      </tr>
                      <tr>
                        <th>מחזור</th>
                        <td>
                          {h.period_s != null ? <Num>{h.period_s.toFixed(1)} שנ'</Num> : "אין נתונים"} (
                          {PERIOD_HE[h.period_band] || h.period_band})
                          <ConfidenceBadge confidence={h.confidence.period} />
                        </td>
                      </tr>
                      <tr>
                        <th>רוח</th>
                        <td>
                          {h.wind.speed_kmh != null ? (
                            <>
                              <Num>
                                {h.wind.speed_kmh.toFixed(0)} קמ"ש מ-{h.wind.direction_deg?.toFixed(0)}°
                              </Num>{" "}
                              ({WIND_RELATION_HE[h.wind.relation_to_shore] || h.wind.relation_to_shore}
                              {h.wind.gusty ? ", משתנה" : ""}), משבים{" "}
                              <Num>{h.wind.gusts_kmh?.toFixed(0)} קמ"ש</Num>
                            </>
                          ) : (
                            "אין נתונים"
                          )}
                          <ConfidenceBadge confidence={h.confidence.wind} />
                        </td>
                      </tr>
                      <tr>
                        <th>יחס גלישה</th>
                        <td>
                          {h.chop_ratio != null ? h.chop_ratio.toFixed(2) : "אין נתונים"} (
                          {CHOP_HE[h.chop_band] || h.chop_band})
                          <ConfidenceBadge confidence={h.confidence.chop} />
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
