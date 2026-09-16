import { localDateString, todayOrTomorrowLabel } from "../dateUtils.js";

const WIDTH = 900;
const HEIGHT = 240;
const PAD_TOP = 18; // the day-name label row
// Extra vertical room reserved ABOVE the highest possible data point, so the actual peak
// (and its number, drawn above the point) never sits at the literal top edge of the chart
// or collides with the day-name row -- the exact "highest value must not be the highest
// point on the board" fix.
const LABEL_HEADROOM = 26;
const PAD_BOTTOM = 12;
const PAD_SIDE = 6;

const PLOT_TOP = PAD_TOP + LABEL_HEADROOM;
const PLOT_BOTTOM = HEIGHT - PAD_BOTTOM;

/** Dependency-free inline SVG chart -- no charting library added (this project keeps two
 * runtime dependencies on purpose). Two lines sharing one x-axis (hour index): surf height
 * (its own min/max scale, with headroom -- see PLOT_TOP) and score (fixed 0..10 scale, so
 * the 0..10 axis always means the same thing chart to chart, also with headroom). Height is
 * drawn first/behind, score drawn on top in the accent colour, since the score is the
 * number the user is scanning for.
 *
 * `vector-effect="non-scaling-stroke"` on every stroked/circular element: the SVG is
 * stretched to fill its container via `preserveAspectRatio="none"` (the container's actual
 * width varies per screen, the height is fixed), which scales x and y by DIFFERENT
 * factors -- without this, that non-uniform scale visibly distorts stroke widths and turns
 * the round peak markers into ellipses. WIDTH/HEIGHT are also chosen closer to this chart's
 * typical real on-screen ratio than the first version's much flatter box, so the distortion
 * that remains is small either way.
 *
 * X-axis is labelled by DAY, not hour -- one name centred over each day's own span -- and
 * each day's peak height and peak score are called out with their number directly on the
 * chart, rather than making the reader hover or cross-reference a table. */
export default function WaveChart({ rows }) {
  if (!rows || rows.length < 2) return null;

  const heights = rows.map((r) => r.size.surf_height_estimate ?? 0);
  const scores = rows.map((r) => r.quality_score ?? 0);
  // Headroom on the height axis too: the domain max is set ABOVE the real data max (not
  // exactly at it), so the tallest point on the height line also sits below PLOT_TOP.
  const hMax = Math.max(0.5, ...heights) * 1.25;
  const n = rows.length;

  // Mirrored: SVG coordinate space is always LTR (x increases rightward) regardless of the
  // page's dir="rtl" -- unlike flex/grid, an <svg> does not auto-flip its own drawing
  // coordinates. Index 0 (today/the earliest hour) is placed at the RIGHT edge and time
  // runs right-to-left, matching how the rest of the page reads.
  const x = (i) => WIDTH - PAD_SIDE - (i / (n - 1)) * (WIDTH - 2 * PAD_SIDE);
  const yHeight = (v) => PLOT_TOP + (1 - v / hMax) * (PLOT_BOTTOM - PLOT_TOP);
  // Score's domain is fixed 0..10, but scores this project actually produces rarely sit
  // above ~8-9 in practice -- still reserve the same headroom so a rare 10.0 doesn't clip.
  const yScore = (v) => PLOT_TOP + (1 - v / 10.6) * (PLOT_BOTTOM - PLOT_TOP);

  const heightPath = heights.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yHeight(v).toFixed(1)}`).join(" ");
  const scorePath = scores.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yScore(v).toFixed(1)}`).join(" ");

  // Group row indices by local calendar day, in order -- gives each day's own x-range for
  // the label position and the peak search below.
  const days = [];
  rows.forEach((r, i) => {
    const d = localDateString(r.valid_at);
    const last = days[days.length - 1];
    if (last && last.date === d) {
      last.end = i;
    } else {
      days.push({ date: d, start: i, end: i });
    }
  });

  const peaks = days.map((day) => {
    let hi = day.start;
    let si = day.start;
    for (let i = day.start; i <= day.end; i++) {
      if (heights[i] > heights[hi]) hi = i;
      if (scores[i] > scores[si]) si = i;
    }
    return { ...day, heightIdx: hi, scoreIdx: si };
  });

  return (
    <div className="wave-chart">
      <div className="wave-chart-legend">
        <span className="wave-chart-legend-item">
          <span className="wave-chart-swatch wave-chart-swatch-height" /> גובה גלישה
        </span>
        <span className="wave-chart-legend-item">
          <span className="wave-chart-swatch wave-chart-swatch-score" /> ציון
        </span>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} preserveAspectRatio="none" className="wave-chart-svg">
        {days.slice(1).map((d) => (
          <line
            key={d.date}
            x1={x(d.start)}
            x2={x(d.start)}
            y1={PAD_TOP}
            y2={PLOT_BOTTOM}
            stroke="#e5e7eb"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {days.map((d) => (
          <text
            key={d.date}
            x={(x(d.start) + x(d.end)) / 2}
            y={PAD_TOP}
            textAnchor="middle"
            fontSize="13"
            fontWeight="700"
            fill="#4b5563"
          >
            {todayOrTomorrowLabel(d.date)}
          </text>
        ))}

        <path d={heightPath} fill="none" stroke="#0a6fb5" strokeWidth="2.5" opacity="0.55" vectorEffect="non-scaling-stroke" />
        <path d={scorePath} fill="none" stroke="#166534" strokeWidth="3" vectorEffect="non-scaling-stroke" />

        {peaks.map((p) => (
          <g key={`h-${p.date}`}>
            <circle cx={x(p.heightIdx)} cy={yHeight(heights[p.heightIdx])} r="3" fill="#0a6fb5" vectorEffect="non-scaling-stroke" />
            <text
              x={x(p.heightIdx)}
              y={yHeight(heights[p.heightIdx]) - 9}
              textAnchor="middle"
              fontSize="12"
              fontWeight="600"
              fill="#0a6fb5"
            >
              {heights[p.heightIdx].toFixed(2)} מ'
            </text>
          </g>
        ))}
        {peaks.map((p) => (
          <g key={`s-${p.date}`}>
            <circle cx={x(p.scoreIdx)} cy={yScore(scores[p.scoreIdx])} r="3" fill="#166534" vectorEffect="non-scaling-stroke" />
            <text
              x={x(p.scoreIdx)}
              y={yScore(scores[p.scoreIdx]) - 9}
              textAnchor="middle"
              fontSize="12"
              fontWeight="700"
              fill="#166534"
            >
              {scores[p.scoreIdx].toFixed(1)}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}
