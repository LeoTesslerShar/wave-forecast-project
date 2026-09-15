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

/** Size, specifically: shows surf height as the headline number (what Israeli surf reports
 * quote -- the waves breaking at the beach), with the significant-height offshore figure
 * kept visible underneath, labelled -- surf height is a derived conversion
 * (app/exposure/apply.py SURF_HEIGHT_FACTOR, docs/DECISIONS.md), never the number
 * app/quality/size.py's bands or docs/BIAS_ANALYSIS.md's accuracy claims are based on. */
export function SizeValue({ size }) {
  if (size?.surf_height_estimate == null) return <span className="muted">no data</span>;
  return (
    <span className="ranged-value">
      <RangedValue
        estimate={size.surf_height_estimate}
        range={size.surf_height_range}
        confidence={size.confidence.surf_height}
      />
      <span className="muted" style={{ display: "block", fontSize: "0.85em" }}>
        Hs (offshore model): {size.wave_height_estimate?.toFixed(2)}m
        <ConfidenceBadge confidence={size.confidence.exposure} />
      </span>
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
