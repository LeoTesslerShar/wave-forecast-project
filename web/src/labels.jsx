// Hebrew display strings for every backend IDENTIFIER the UI shows -- the identifiers
// themselves (quality_verdict, period_band, chop_band, relation_to_shore, confidence
// strings) stay English on the wire, because tests and backend logic depend on their exact
// values (docs/DECISIONS.md, the Hebrew/RTL entry). This is the one place that maps them to
// what the user reads. An unrecognised value falls back to itself rather than crashing or
// showing blank -- a future backend value should degrade visibly, not silently disappear.

export const VERDICT_HE = {
  flat: "שטוח",
  poor: "חלש",
  fair: "סביר",
  good: "טוב",
  excellent: "מצוין",
};

export const CHOP_HE = {
  clean: "נקי",
  mixed: "מעורב",
  choppy: "סחוף",
  unknown: "לא ידוע",
};

export const PERIOD_HE = {
  weak: "חלש",
  workable: "סביר",
  good: "טוב",
  unknown: "לא ידוע",
};

export const WIND_RELATION_HE = {
  offshore: "אופשור",
  onshore: "אונשור",
  "cross-shore": "צדדית",
  glassy: "חלק",
  unknown: "לא ידוע",
};

export const CONFIDENCE_HE = {
  estimate: "הערכה",
  measured: "נמדד",
};

export function heLabel(dict, key) {
  return dict[key] ?? key;
}

/** Wraps a Latin/numeric fragment (a measurement, a time, a degree value) so it renders
 * correctly INSIDE surrounding Hebrew text. Without this, mixed Hebrew+number strings can
 * render with the number's internal digit order flipped or the fragment displaced relative
 * to the Hebrew around it -- the single most common way an RTL UI visibly breaks. Every
 * place a number/unit is printed alongside Hebrew text should go through this, not be
 * concatenated into a template string directly. */
export function Num({ children }) {
  return (
    <span dir="ltr" style={{ unicodeBidi: "isolate" }}>
      {children}
    </span>
  );
}
