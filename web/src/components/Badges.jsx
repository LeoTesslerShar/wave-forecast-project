// Honesty markers -- prompts/phase-5-ui.md section 2. Hard rule 1 does not stop at the
// API boundary: every heuristic number is visually distinct from a measured one, using
// ONE consistent convention across all three views, not buried in a tooltip.

/** True for any confidence string the backend marks as a heuristic, not a measurement --
 * e.g. "unvalidated_heuristic". Measured values look like "measured_accurate",
 * "measured_forecast", or "measured_uncertainty ~1s". */
function isEstimate(confidence) {
  return typeof confidence === "string" && confidence.includes("unvalidated");
}

export function ConfidenceBadge({ confidence }) {
  const estimate = isEstimate(confidence);
  return (
    <span
      className={estimate ? "badge badge-estimate" : "badge badge-measured"}
      title={confidence}
    >
      {estimate ? "estimate" : "measured"}
    </span>
  );
}

/** A value that must always show its range, never a bare decimal (section 2) -- used for
 * the exposure-adjusted size everywhere it appears. */
export function RangedValue({ estimate, range, unit = "m", confidence }) {
  if (estimate == null) return <span className="muted">no data</span>;
  return (
    <span className="ranged-value">
      <strong>
        {estimate.toFixed(2)}
        {unit}
      </strong>
      {range && (
        <span className="range">
          {" "}
          ({range[0].toFixed(2)}–{range[1].toFixed(2)}
          {unit})
        </span>
      )}
      {confidence && <ConfidenceBadge confidence={confidence} />}
    </span>
  );
}

const VERDICT_CLASS = {
  flat: "verdict-flat",
  poor: "verdict-poor",
  fair: "verdict-fair",
  good: "verdict-good",
  excellent: "verdict-excellent",
};

export function VerdictBadge({ verdict }) {
  return (
    <span className={`verdict ${VERDICT_CLASS[verdict] || ""}`}>
      {verdict}
      <ConfidenceBadge confidence="unvalidated_heuristic" />
    </span>
  );
}
