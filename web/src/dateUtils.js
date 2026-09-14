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

/** The best (highest quality_score) hour, among `hours`, that falls on `dateString`
 * (local). Sorting/selecting an already-server-computed field -- not scoring. */
export function bestHourForDate(hours, dateString) {
  const onDate = hours.filter((h) => localDateString(h.valid_at) === dateString);
  if (onDate.length === 0) return null;
  return onDate.reduce((best, h) => (h.quality_score > best.quality_score ? h : best));
}
