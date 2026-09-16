// A humorous, surfer-voice summary of one day -- morning/noon/evening mood plus the day's
// peak hour, when there is one worth mentioning. Purely presentational text generation
// (not a scoring/business calculation), built client-side from the already-computed
// per-hour quality_verdict/quality_score -- it never re-derives or overrides them, only
// picks representative hours and phrases what they already say.
import { localHourLabel, localHourOfDay } from "./dateUtils.js";

// Keyed on the backend's own quality_verdict identifiers (app/quality/verdict.py) -- those
// stay English on the wire; this is the one place that turns them into a punchy Hebrew
// sentence for this specific summary line (distinct from labels.jsx's plain VERDICT_HE,
// which is used for badges/table cells, not prose).
const VERDICT_HUMOR = {
  flat: "שטוח כמו לוח גיהוץ",
  poor: "חלש, בקושי מרטיב סנפירים",
  fair: "סביר, יהיה כיף קטן",
  good: "טוב, שווה לקחת את הגלשן",
  excellent: "מעולה, אל תפספסו!",
};

// A peak is only worth calling out if it's actually good -- otherwise "the peak of a flat
// day" is just a less-flat flat hour, not something worth telling a surfer to plan around.
const PEAK_WORTH_REPORTING_SCORE = 6.0;

function closestHourTo(hours, targetLocalHour) {
  return hours.reduce((best, h) =>
    Math.abs(localHourOfDay(h.valid_at) - targetLocalHour) < Math.abs(localHourOfDay(best.valid_at) - targetLocalHour)
      ? h
      : best,
  );
}

function moodFor(hour) {
  return VERDICT_HUMOR[hour.quality_verdict] || hour.quality_verdict;
}

/** `dayHours` is one day's already-fetched, already-scored 3-hour-interval rows (the same
 * list BeachDay's table renders). Returns null for an empty day rather than an empty
 * sentence. */
export function buildDaySummary(dayHours) {
  if (!dayHours || dayHours.length === 0) return null;

  const morning = closestHourTo(dayHours, 8);
  const noon = closestHourTo(dayHours, 13);
  const evening = closestHourTo(dayHours, 19);
  const peak = dayHours.reduce((best, h) => (h.quality_score > best.quality_score ? h : best));

  const sentence = `בבוקר ${moodFor(morning)}, בצהריים ${moodFor(noon)}, ובערב ${moodFor(evening)}.`;

  if (peak.quality_score >= PEAK_WORTH_REPORTING_SCORE) {
    return `${sentence} השיא של היום ב-${localHourLabel(peak.valid_at)} עם ציון ${peak.quality_score.toFixed(1)} -- שם שמים את הדגל.`;
  }
  return sentence;
}
