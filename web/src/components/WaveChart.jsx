import { localHourLabel, localDateString } from "../dateUtils.js";
import { Num } from "../labels.jsx";

const WIDTH = 700;
const HEIGHT = 140;
const PAD_TOP = 10;
const PAD_BOTTOM = 20;
const PAD_SIDE = 4;

/** Dependency-free inline SVG chart -- no charting library added (this project keeps two
 * runtime dependencies on purpose). Two lines sharing one x-axis (hour index): surf height
 * (its own min/max scale) and score (fixed 0..10 scale, so the 0..10 axis always means the
 * same thing chart to chart). Height is drawn first/behind, score drawn on top in the
 * accent colour, since the score is the number the user is scanning for. */
export default function WaveChart({ rows }) {
  if (!rows || rows.length < 2) return null;

  const heights = rows.map((r) => r.size.surf_height_estimate ?? 0);
  const scores = rows.map((r) => r.quality_score ?? 0);
  const hMax = Math.max(0.5, ...heights);
  const n = rows.length;

  const x = (i) => PAD_SIDE + (i / (n - 1)) * (WIDTH - 2 * PAD_SIDE);
  const yHeight = (v) => PAD_TOP + (1 - v / hMax) * (HEIGHT - PAD_TOP - PAD_BOTTOM);
  const yScore = (v) => PAD_TOP + (1 - v / 10) * (HEIGHT - PAD_TOP - PAD_BOTTOM);

  const heightPath = heights.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yHeight(v).toFixed(1)}`).join(" ");
  const scorePath = scores.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${yScore(v).toFixed(1)}`).join(" ");

  // A day boundary tick every time the local date changes, so the chart reads as "days"
  // rather than an undifferentiated hourly blur.
  const dayTicks = [];
  let lastDate = null;
  rows.forEach((r, i) => {
    const d = localDateString(r.valid_at);
    if (d !== lastDate) {
      dayTicks.push({ i, label: localHourLabel(r.valid_at) });
      lastDate = d;
    }
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
        {dayTicks.map((t) => (
          <line
            key={t.i}
            x1={x(t.i)}
            x2={x(t.i)}
            y1={PAD_TOP}
            y2={HEIGHT - PAD_BOTTOM}
            stroke="#e5e7eb"
            strokeWidth="1"
          />
        ))}
        <path d={heightPath} fill="none" stroke="#0a6fb5" strokeWidth="2" opacity="0.55" />
        <path d={scorePath} fill="none" stroke="#166534" strokeWidth="2.5" />
      </svg>
      <div className="wave-chart-ticks">
        {dayTicks.map((t) => (
          <span key={t.i} className="muted small" style={{ insetInlineStart: `${(x(t.i) / WIDTH) * 100}%` }}>
            <Num>{t.label}</Num>
          </span>
        ))}
      </div>
    </div>
  );
}
