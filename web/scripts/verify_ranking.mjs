// One-off verification script (not part of the app) proving the RankedBeachList view's
// data flow against the REAL live API: fetch beaches, fetch quality per beach, pick the
// best hour for today (Asia/Jerusalem), sort by quality_score -- reusing the actual
// dateUtils.js the component imports, not a reimplementation.
import { bestHourForDate, todayLocalDateString } from "../src/dateUtils.js";

const BASE = "http://localhost:8000";

const beaches = await (await fetch(`${BASE}/beaches`)).json();
const date = todayLocalDateString();
console.log(`today (Asia/Jerusalem): ${date}`);
console.log(`beaches: ${beaches.length}`);

const results = [];
for (const beach of beaches) {
  const hourly = await (await fetch(`${BASE}/beaches/${beach.id}/quality?hours=96`)).json();
  const best = bestHourForDate(hourly, date);
  if (best) results.push({ beach, best });
}

results.sort((a, b) => b.best.quality_score - a.best.quality_score);

console.log("\nranked beach list (what RankedBeachList.jsx would render):");
for (const { beach, best } of results) {
  console.log(
    `  ${beach.name.padEnd(20)} verdict=${best.quality_verdict.padEnd(10)} ` +
      `score=${best.quality_score.toFixed(2)} size=${best.size.wave_height_estimate}m ` +
      `(${best.size.wave_height_range[0]}-${best.size.wave_height_range[1]}m) ` +
      `wind=${best.wind.relation_to_shore} at ${best.valid_at}`,
  );
}
