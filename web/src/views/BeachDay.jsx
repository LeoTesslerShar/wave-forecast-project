import { useEffect, useState } from "react";
import { api } from "../api.js";
import { FacebookIcon, MoonIcon, SunIcon, WhatsAppIcon, WindArrowIcon } from "../components/Icons.jsx";
import { hebrewDateLabel, hoursAtIntervalForDate, localHourLabel, localHourOfDay, todayOrTomorrowLabel } from "../dateUtils.js";
import { getUserId } from "../identity.js";
import { Num, PERIOD_HE } from "../labels.jsx";
import { ensurePushRegistered } from "../push.js";

const VERDICT_FILL_CLASS = {
  flat: "fill-flat",
  poor: "fill-poor",
  fair: "fill-fair",
  good: "fill-good",
  excellent: "fill-excellent",
};

/** Rough daytime window for the sun/moon icon -- display only, not a real sunrise/sunset
 * calculation (this project has no astronomical data source). Reasonable for this
 * latitude/season without claiming precision it doesn't have. */
function isDaytime(isoTimestamp) {
  const h = localHourOfDay(isoTimestamp);
  return h >= 6 && h < 18;
}

/** Wind cell colour -- a purely presentational 3-tier bucket (green/orange/red), separate
 * from and coarser than app/quality/verdict.py's own WIND_CEILING curve, which is what
 * actually drives the score. This only decides a pill colour. */
function windPillClass(speedKmh, relation) {
  if (speedKmh == null) return "wind-calm";
  if (relation === "offshore" || relation === "glassy") {
    return speedKmh < 50 ? "wind-calm" : "wind-strong";
  }
  if (speedKmh < 12) return "wind-calm";
  if (speedKmh < 25) return "wind-moderate";
  return "wind-strong";
}

function cm(m) {
  return m == null ? null : Math.round(m * 100);
}

function shareText(beachName, dateLabel) {
  return `תחזית גלישה ל${beachName}, ${dateLabel}`;
}

async function share(beachName, dateLabel) {
  const text = shareText(beachName, dateLabel);
  if (navigator.share) {
    try {
      await navigator.share({ title: text, url: location.href });
      return;
    } catch {
      /* user cancelled -- fall through to nothing */
      return;
    }
  }
  window.open(`https://wa.me/?text=${encodeURIComponent(`${text} ${location.href}`)}`, "_blank");
}

/** One day, one beach, 3-hour intervals. Header bar (date + today/tomorrow label + share),
 * then a 9-column table: hour, wave height (range), score, body-reference, boards, swell
 * height, period, wind speed, wind direction -- exactly the fields asked for, in that
 * order. No temperature column: this project has no air-temperature data source, and
 * showing one would mean inventing a number (hard rule 1 forbids it). */
export default function BeachDay({ beach, rows, date, onBack }) {
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
  const nowIso = new Date().toISOString();

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

  const beachName = beach.name_he || beach.name;
  const dateLabel = todayOrTomorrowLabel(date);

  return (
    <div>
      <button className="back-link" onClick={onBack}>
        &rlm;&larr; חזרה לשבוע
      </button>

      <div className="day-header-bar">
        <div className="day-header-date">
          <h2>
            {beachName} · {dateLabel}
          </h2>
          <span className="muted small">
            <Num>{hebrewDateLabel(date)}</Num>
          </span>
        </div>
        <div className="day-header-share">
          <span className="muted small">שתף</span>
          <button className="icon-btn" onClick={() => share(beachName, dateLabel)} title="שתף בוואטסאפ">
            <WhatsAppIcon />
          </button>
          <button
            className="icon-btn"
            onClick={() =>
              window.open(`https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(location.href)}`, "_blank")
            }
            title="שתף בפייסבוק"
          >
            <FacebookIcon />
          </button>
        </div>
      </div>

      {watchError && <p className="error">{watchError}</p>}
      {dayHours === null && <p className="muted">טוען תחזית...</p>}
      {dayHours !== null && dayHours.length === 0 && <p className="muted">אין תחזית ליום זה.</p>}

      {dayHours !== null && dayHours.length > 0 && (
        <div className="day-table-scroll">
          <table className="day-table">
            <thead>
              <tr>
                <th>שעה</th>
                <th>גובה גלישה</th>
                <th>ציון</th>
                <th>יחס לגוף</th>
                <th>לוחות</th>
                <th>גובה סוול</th>
                <th>מחזור</th>
                <th>מהירות רוח</th>
                <th>כיוון רוח</th>
                <th>מעקב</th>
              </tr>
            </thead>
            <tbody>
              {dayHours.map((h, i) => {
                const isNow = h.valid_at <= nowIso && (i === dayHours.length - 1 || dayHours[i + 1].valid_at > nowIso);
                const watch = watches?.[h.valid_at];
                const lo = cm(h.size.surf_height_range?.[0]);
                const hi = cm(h.size.surf_height_range?.[1]);
                return (
                  <tr key={h.valid_at} className={isNow ? "day-row-now" : ""}>
                    <td className="cell-hour">
                      {isDaytime(h.valid_at) ? <SunIcon /> : <MoonIcon />}
                      <span>
                        <Num>{localHourLabel(h.valid_at)}</Num>
                      </span>
                    </td>
                    <td>
                      <span className="pill pill-blue">
                        {lo != null && hi != null ? <Num>{lo}-{hi} ס"מ</Num> : "--"}
                      </span>
                    </td>
                    <td>
                      <span className={`pill score-fill ${VERDICT_FILL_CLASS[h.quality_verdict] || ""}`}>
                        <Num>{h.quality_score.toFixed(1)}</Num>
                      </span>
                    </td>
                    <td>{h.body_reference}</td>
                    <td className="cell-boards">{h.board_recommendation.join(" / ") || "--"}</td>
                    <td>{h.swell_height_m != null ? <Num>{h.swell_height_m.toFixed(2)} מ'</Num> : "--"}</td>
                    <td>
                      {h.period_s != null ? <Num>{h.period_s.toFixed(1)} שנ'</Num> : "--"} (
                      {PERIOD_HE[h.period_band] || h.period_band})
                    </td>
                    <td>
                      <span className={`pill wind-pill ${windPillClass(h.wind.speed_kmh, h.wind.relation_to_shore)}`}>
                        <WindArrowIcon directionDeg={h.wind.direction_deg} />
                        <Num>{h.wind.speed_kmh != null ? h.wind.speed_kmh.toFixed(0) : "--"} קמ"ש</Num>
                      </span>
                    </td>
                    <td>{h.wind.direction_deg != null ? <Num>{h.wind.direction_deg.toFixed(0)}°</Num> : "--"}</td>
                    <td>
                      <button
                        className={watch ? "watch-btn watching" : "watch-btn"}
                        onClick={() => toggleWatch(h)}
                        disabled={busyValidAt === h.valid_at}
                      >
                        {busyValidAt === h.valid_at ? "..." : watch ? "צופה ✓" : "התרע לי"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {dayHours !== null && dayHours.length > 0 && (
        <p className="muted small honesty-note">
          גובה גלישה, ציון, יחס לגוף והמלצת לוחות הם הערכות לא מאומתות של המערכת -- לא
          מדידה. מהירות וכיוון רוח, גובה סוול ומחזור מגיעים ישירות ממודל התחזית.
        </p>
      )}
    </div>
  );
}
