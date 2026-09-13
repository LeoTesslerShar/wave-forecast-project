// REFERENCE COPY, not part of this project's shipped code. Sourced verbatim from the
// public repo https://github.com/Yuvartz/yam-palta (scripts/fetch-buoy.mjs, master
// branch, fetched 2026-09-13) per docs/DATA_SOURCES.md and planning doc section 4.4 —
// kept here so the ISRAMAR endpoint it discovered is cited and reproducible, not
// reverse-engineered from memory. Do not modify; write our own fetcher in app code.
//
// Fetches the real measured wave data from the ISRAMAR Hadera buoy, and writes
// docs/data/hadera-waves.json (same-origin for the static app, no CORS).
// This is a MEASUREMENT (a real buoy), not a forecast — the app uses it as a
// reality-check / anchor against the Open-Meteo forecast ensemble.
// Run hourly by .github/workflows/buoy.yml. Data © ISRAMAR / IOLR.

import { writeFileSync, mkdirSync, readFileSync, existsSync } from "node:fs";

const SRC = "https://isramar.ocean.org.il/isramar2009/station/data/Hadera_Hs_Per.json";
const OUT = "docs/data/hadera-waves.json";

// The buoy sits off Hadera (central Israeli coast). Significant wave height is
// fairly uniform alongshore on the open coast, so this is a good regional anchor
// for Netanya/Herzliya/Tel Aviv — less so for sheltered Haifa bay or the far south.
const STATION = { name: "מצוף חדרה", lat: 32.470, lon: 34.880 };

const pick = (params, name) => {
  const p = (params || []).find(x => x.name === name);
  const v = p && Array.isArray(p.values) ? p.values[0] : null;
  const n = v == null ? null : Number(v);
  // NaN would survive a `== null` check and serialize to null, clobbering good data;
  // negative or absurd wave values mean a sensor/format glitch, not a measurement.
  return n != null && Number.isFinite(n) && n >= 0 && n < 30 ? n : null;
};

// "2026-06-27 18:00 UTC" -> ISO string the browser can parse reliably.
function toISO(dt) {
  if (!dt) return null;
  const m = dt.match(/(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:00Z` : null;
}

async function main() {
  const res = await fetch(SRC, { headers: { "User-Agent": "yam-palata/1.0 (+github pages personal app)" } });
  if (!res.ok) throw new Error("fetch failed: " + res.status);
  const raw = await res.json();

  const measured = {
    waveHeight: pick(raw.parameters, "Significant wave height"), // Hs, metres
    wavePeriod: pick(raw.parameters, "Peak wave period"),        // seconds
    waveMax: pick(raw.parameters, "Maximal wave height"),        // metres
    measuredAt: toISO(raw.datetime),
  };

  if (measured.waveHeight == null) {
    // Don't overwrite good data with a bad/empty parse (transient issue / layout change).
    if (existsSync(OUT)) { console.error("no wave height parsed; keeping existing file"); return; }
  }

  const out = {
    updated: new Date().toISOString(),
    source: "ISRAMAR — Hadera buoy",
    sourceUrl: "https://isramar.ocean.org.il/isramar2009/station/HaderaRDI.aspx",
    station: STATION,
    measured,
  };

  // Keep timestamps stable when the measurement is unchanged, to avoid noise commits.
  if (existsSync(OUT)) {
    try {
      const prev = JSON.parse(readFileSync(OUT, "utf8"));
      if (JSON.stringify(prev.measured) === JSON.stringify(measured)) { console.log("no change"); return; }
    } catch (e) {}
  }

  mkdirSync("docs/data", { recursive: true });
  writeFileSync(OUT, JSON.stringify(out, null, 2) + "\n");
  console.log(`wrote Hs=${measured.waveHeight}m (period ${measured.wavePeriod}s) to ${OUT}`);
}

main().catch(e => { console.error(e); process.exit(1); });
