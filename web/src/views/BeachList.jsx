import { ScoreBadge, SizeValueCompact } from "../components/Badges.jsx";
import { nearestSlotTo } from "../dateUtils.js";
import { Num, WIND_RELATION_HE } from "../labels.jsx";

/** The primary view -- compact, one line per beach, current conditions (nearest hour to
 * now), clickable through to that beach's week. Deliberately dense (Surfline-style list),
 * unlike the old RankedBeachList's ~150px cards -- prompts/phase-5-ui.md section 3 still
 * governs: nothing here recomputes size/wind/quality, only picks which already-computed
 * hour to show and how to sort the rows. */
export default function BeachList({ beaches, error, qualityByBeach, onSelectBeach }) {
  if (error) return <p className="error">שגיאה בטעינת רשימת החופים: {error}</p>;
  if (beaches.length === 0) return <p className="muted">טוען...</p>;

  const rows = beaches
    .map((beach) => {
      const data = qualityByBeach[beach.id];
      const now = Array.isArray(data) ? nearestSlotTo(data) : null;
      return { beach, now, loading: data === "loading" || data === undefined, failed: data instanceof Error };
    })
    .sort((a, b) => (b.now?.quality_score ?? -1) - (a.now?.quality_score ?? -1));

  return (
    <div className="beach-list-compact">
      {rows.map(({ beach, now, loading, failed }) => (
        <button
          key={beach.id}
          className="beach-row"
          onClick={() => onSelectBeach(beach.id)}
          disabled={!now}
        >
          <span className="beach-row-name">{beach.name_he || beach.name}</span>
          {now ? (
            <>
              <ScoreBadge score={now.quality_score} verdict={now.quality_verdict} />
              <span className="beach-row-size">
                <SizeValueCompact size={now.size} />
              </span>
              <span className="beach-row-wind muted">
                {now.wind.speed_kmh != null ? (
                  <>
                    <Num>{now.wind.speed_kmh.toFixed(0)} קמ"ש</Num>{" "}
                    {WIND_RELATION_HE[now.wind.relation_to_shore] || now.wind.relation_to_shore}
                  </>
                ) : (
                  "אין נתוני רוח"
                )}
              </span>
            </>
          ) : (
            <span className="muted">{failed ? "שגיאה בטעינה" : loading ? "טוען..." : "אין נתונים"}</span>
          )}
        </button>
      ))}
    </div>
  );
}
