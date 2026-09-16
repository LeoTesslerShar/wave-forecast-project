// A humorous, surfer-voice summary of one day -- morning/noon/evening mood (collapsed into
// one sentence when they all agree, instead of repeating the same phrase three times) plus
// the day's peak hour, when there is one worth mentioning. Purely presentational text
// generation (not a scoring/business calculation), built client-side from the already-
// computed per-hour quality_verdict/quality_score -- it never re-derives or overrides them,
// only picks representative hours and phrases what they already say.
import { localHourLabel, localHourOfDay } from "./dateUtils.js";

// Keyed on the backend's own quality_verdict identifiers (app/quality/verdict.py) -- those
// stay English on the wire; this is the one place that turns them into a punchy Hebrew
// sentence for this specific summary line (distinct from labels.jsx's plain VERDICT_HE,
// which is used for badges/table cells, not prose). Two dictionaries: PERIOD_MOOD for a
// clause attached to a specific part of the day ("בבוקר X"), DAY_MOOD for when the whole
// day agrees and gets one sentence instead of three identical clauses.
const PERIOD_MOOD = {
  flat: "שטוח לגמרי",
  poor: "חלש, בקושי מרטיב סנפירים",
  fair: "סביר, לא מרשים אבל גם לא נורא",
  good: "טוב, שווה לצאת",
  excellent: "מעולה, תבטלו תוכניות",
};

const DAY_MOOD = {
  flat: "היום שטוח מהבוקר עד הערב -- שיהיה לכם יום נעים ביבשה.",
  poor: "היום חלש לאורך כל השעות -- לא ממש שווה לצאת.",
  fair: "היום סביר-סביר לאורך כל השעות, לא מרשים אבל גם לא מביך.",
  good: "יום טוב מהבוקר ועד הערב -- תצאו מתי שנוח לכם.",
  excellent: "יום מעולה מהבוקר ועד הערב -- כל שעה שווה, אל תתמהמהו.",
};

const PERIOD_LABELS = [
  { label: "בבוקר", targetHour: 8 },
  { label: "בצהריים", targetHour: 13 },
  { label: "בערב", targetHour: 19 },
];

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

/** `dayHours` is one day's already-fetched, already-scored 3-hour-interval rows (the same
 * list BeachDay's table renders). Returns null for an empty day rather than an empty
 * sentence. */
export function buildDaySummary(dayHours) {
  if (!dayHours || dayHours.length === 0) return null;

  const periods = PERIOD_LABELS.map((p) => ({ label: p.label, hour: closestHourTo(dayHours, p.targetHour) }));

  let body;
  if (periods.every((p) => p.hour.quality_verdict === periods[0].hour.quality_verdict)) {
    // All three agree -- one sentence for the whole day, not the same clause three times.
    body = DAY_MOOD[periods[0].hour.quality_verdict] || `היום ${periods[0].hour.quality_verdict} לאורך כל השעות.`;
  } else {
    // Merge adjacent periods that share a verdict ("בבוקר ובצהריים X, ובערב Y") rather than
    // always listing three separate clauses even when two of them say the same thing.
    const groups = [];
    for (const p of periods) {
      const last = groups[groups.length - 1];
      if (last && last.verdict === p.hour.quality_verdict) {
        last.labels.push(p.label);
      } else {
        groups.push({ verdict: p.hour.quality_verdict, labels: [p.label] });
      }
    }
    body = groups
      .map((g, i) => {
        const labels = g.labels.map((l, j) => (j === 0 ? (i === 0 ? l : `ו${l}`) : l)).join(" ו");
        const mood = PERIOD_MOOD[g.verdict] || g.verdict;
        return `${labels} ${mood}`;
      })
      .join(", ");
    body += ".";
  }

  const peak = dayHours.reduce((best, h) => (h.quality_score > best.quality_score ? h : best));
  if (peak.quality_score >= PEAK_WORTH_REPORTING_SCORE) {
    body += ` השיא של היום: ${localHourLabel(peak.valid_at)}, ציון ${peak.quality_score.toFixed(1)} -- זו השעה לתפוס.`;
  }
  return body;
}
