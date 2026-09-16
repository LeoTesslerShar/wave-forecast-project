import { localDateString, todayOrTomorrowLabel } from "../dateUtils.js";

const WIDTH = 700;
const HEIGHT = 160;
const PAD_TOP = 26;
const PAD_BOTTOM = 8;
const PAD_SIDE = 4;

/** Dependency-free inline SVG chart -- no charting library added (this project keeps two
 * runtime dependencies on purpose). Two lines sharing one x-axis (hour index): surf height
 * (its own min/max scale) and score (fixed 0..10 scale, so the 0..10 axis always means the
 * same thing chart to chart). Height is drawn first/behind, score drawn on top in the
 * accent colour, since the score is the number the user is scanning for.
 *
 * X-axis is labelled by DAY, not hour -- one name centred over each day's own span -- and
 * each day's peak height and peak score are called out with their number directly on the
 * chart, rather than making the reader hover or cross-reference a table. */
export default function WaveChart({ rows }) {
  if (!rows || rows.length < 2) return null;

  const heights = rows.map((r) => r.size.surf_height_estimate ?? 0);
  const scores = rows.map((r) => r.quality_score ?? 0);
  const hMax = Math.max(0.5, ...heights);
  const n = rows.length;

  // Mirrored: SVG coordinate space is always LTR (x increases rightward) regardless of the
  // page's dir="rtl" -- unlike flex/grid, an <svg> does not auto-flip its own drawing
  // coordinates. Index 0 (today/the earliest hour) is placed at the RIGHT edge and time
  // runs right-to-left, matching how the rest of the page reads.
  const x = (i) => WIDTH - PAD_SIDE - (i / (n - 1)) * (WIDTH - 2 * PAD_SIDE);
  const yHeight = (v) => PAD_TOP + (1 - v / hMax) * (HEIGHT - PAD_TOP - PAD_BOTTOM);
  const yScore = (v) => PAD_TOP + (1 - v / 10) * (HEIGHT - PAD_TOP - PAD_BOTTOM);

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
            y2={HEIGHT - PAD_BOTTOM}
            stroke="#e5e7eb"
            strokeWidth="1"
          />
        ))}

        {days.map((d) => (
          <text
            key={d.date}
            x={(x(d.start) + x(d.end)) / 2}
            y={14}
            textAnchor="middle"
            fontSize="11"
            fontWeight="700"
            fill="#4b5563"
          >
            {todayOrTomorrowLabel(d.date)}
          </text>
        ))}

        <path d={heightPath} fill="none" stroke="#0a6fb5" strokeWidth="2" opacity="0.55" />
        <path d={scorePath} fill="none" stroke="#166534" strokeWidth="2.5" />

        {peaks.map((p) => (
          <g key={`h-${p.date}`}>
            <circle cx={x(p.heightIdx)} cy={yHeight(heights[p.heightIdx])} r="2.5" fill="#0a6fb5" />
            <text
              x={x(p.heightIdx)}
              y={yHeight(heights[p.heightIdx]) - 7}
              textAnchor="middle"
              fontSize="10"
              fontWeight="600"
              fill="#0a6fb5"
            >
              {Math.round(heights[p.heightIdx] * 100)}
            </text>
          </g>
        ))}
        {peaks.map((p) => (
          <g key={`s-${p.date}`}>
            <circle cx={x(p.scoreIdx)} cy={yScore(scores[p.scoreIdx])} r="2.5" fill="#166534" />
            <text
              x={x(p.scoreIdx)}
              y={yScore(scores[p.scoreIdx]) - 7}
              textAnchor="middle"
              fontSize="10"
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
