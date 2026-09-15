// Local-date helpers for Asia/Jerusalem -- display/grouping only, matching the timezone
// convention already established server-side (app/alerting/timewindow.py). No business
// logic: this never decides what qualifies, only which calendar day an hour belongs to.

const TZ = "Asia/Jerusalem";

const dateFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: TZ,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}); // en-CA gives YYYY-MM-DD directly

export function localDateString(isoTimestamp) {
  return dateFormatter.format(new Date(isoTimestamp));
}

export function todayLocalDateString() {
  return dateFormatter.format(new Date());
}

export function localHourLabel(isoTimestamp) {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoTimestamp));
}

/** Local (Asia/Jerusalem) hour of day, 0-23 -- used to thin an hourly series down to a
 * fixed interval (e.g. every 3rd hour) without drifting across a UTC offset change. */
export function localHourOfDay(isoTimestamp) {
  return Number(
    new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", hourCycle: "h23" }).format(
      new Date(isoTimestamp),
    ),
  );
}

/** The best (highest quality_score) hour, among `hours`, that falls on `dateString`
 * (local). Sorting/selecting an already-server-computed field -- not scoring. */
export function bestHourForDate(hours, dateString) {
  const onDate = hours.filter((h) => localDateString(h.valid_at) === dateString);
  if (onDate.length === 0) return null;
  return onDate.reduce((best, h) => (h.quality_score > best.quality_score ? h : best));
}

// Shown at a 3-hour cadence (00, 03, 06, ... local) -- enough to see how a window develops
// without a 24-row list for one day. DST-safe: filters on the LOCAL hour of day, not a
// fixed index into the array, so a DST transition never shifts which hours are shown.
export const HOUR_INTERVAL = 3;

/** `hours` thinned to every HOUR_INTERVAL-th local hour on `dateString`. The one helper
 * both the week view (picking a representative day) and the day view (the row list) use --
 * previously duplicated inline in SingleBeachBreakdown.jsx. */
export function hoursAtIntervalForDate(hours, dateString) {
  return hours.filter(
    (h) => localDateString(h.valid_at) === dateString && localHourOfDay(h.valid_at) % HOUR_INTERVAL === 0,
  );
}

/** The single hour in `hours` whose valid_at is closest to `when` (a Date, defaults to
 * now) -- "current conditions" for the compact beach list, as opposed to
 * bestHourForDate's "best hour of the day". */
export function nearestSlotTo(hours, when = new Date()) {
  if (!hours || hours.length === 0) return null;
  const targetMs = when.getTime();
  return hours.reduce((best, h) => {
    const d = Math.abs(new Date(h.valid_at).getTime() - targetMs);
    const bestD = Math.abs(new Date(best.valid_at).getTime() - targetMs);
    return d < bestD ? h : best;
  });
}

/** The next `n` local calendar dates starting today, as YYYY-MM-DD strings -- the week
 * view's day rows. */
export function nextLocalDates(n) {
  const today = todayLocalDateString();
  const [y, m, d] = today.split("-").map(Number);
  const base = new Date(Date.UTC(y, m - 1, d));
  const dates = [];
  for (let i = 0; i < n; i++) {
    const dt = new Date(base);
    dt.setUTCDate(dt.getUTCDate() + i);
    dates.push(dt.toISOString().slice(0, 10));
  }
  return dates;
}

const hebrewDateFormatter = new Intl.DateTimeFormat("he-IL", {
  timeZone: TZ,
  weekday: "short",
  day: "numeric",
  month: "numeric",
});

/** `dateString` (YYYY-MM-DD, the internal grouping key -- never changes) rendered as a
 * Hebrew day label, e.g. "ג׳ 17/9". Display only. */
export function hebrewDateLabel(dateString) {
  // Construct at local noon to avoid any UTC-midnight rollback near the date boundary.
  return hebrewDateFormatter.format(new Date(`${dateString}T12:00:00Z`));
}

export function todayOrTomorrowLabel(dateString) {
  const today = todayLocalDateString();
  if (dateString === today) return "היום";
  const [y, m, d] = today.split("-").map(Number);
  const tomorrow = new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
  if (dateString === tomorrow) return "מחר";
  return hebrewDateLabel(dateString);
}
