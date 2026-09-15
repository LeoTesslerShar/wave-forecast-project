import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import BeachDay from "./views/BeachDay.jsx";
import BeachList from "./views/BeachList.jsx";
import BeachWeek from "./views/BeachWeek.jsx";
import SubscriptionForm from "./views/SubscriptionForm.jsx";

const TABS = [
  { key: "beaches", label: "חופים" },
  { key: "alerts", label: "התראות" },
];

export default function App() {
  const [tab, setTab] = useState("beaches");
  // { view: 'list' } | { view: 'week', beachId } | { view: 'day', beachId, date }
  const [nav, setNav] = useState({ view: "list" });
  const [beaches, setBeaches] = useState([]);
  const [beachesError, setBeachesError] = useState(null);
  const [qualityByBeach, setQualityByBeach] = useState({}); // beachId -> rows | 'loading' | Error
  const fetchedRef = useRef(new Set());

  useEffect(() => {
    api
      .listBeaches()
      .then(setBeaches)
      .catch((e) => setBeachesError(e.message));
  }, []);

  // Fetched once per beach per session, not on every navigation -- the previous per-view
  // fetching pattern issued one 168h request per beach on every date change.
  const ensureQuality = useCallback((beachId) => {
    if (fetchedRef.current.has(beachId)) return;
    fetchedRef.current.add(beachId);
    setQualityByBeach((prev) => ({ ...prev, [beachId]: "loading" }));
    api
      .getBeachQuality(beachId, 168)
      .then((rows) => setQualityByBeach((prev) => ({ ...prev, [beachId]: rows })))
      .catch((e) => {
        fetchedRef.current.delete(beachId);
        setQualityByBeach((prev) => ({ ...prev, [beachId]: e }));
      });
  }, []);

  useEffect(() => {
    beaches.forEach((b) => ensureQuality(b.id));
  }, [beaches, ensureQuality]);

  function renderBeaches() {
    if (nav.view === "week") {
      const beach = beaches.find((b) => b.id === nav.beachId);
      const rows = qualityByBeach[nav.beachId];
      return (
        <BeachWeek
          beach={beach}
          rows={Array.isArray(rows) ? rows : null}
          onSelectDay={(date) => setNav({ view: "day", beachId: nav.beachId, date })}
          onBack={() => setNav({ view: "list" })}
        />
      );
    }
    if (nav.view === "day") {
      const beach = beaches.find((b) => b.id === nav.beachId);
      const rows = qualityByBeach[nav.beachId];
      return (
        <BeachDay
          beach={beach}
          rows={Array.isArray(rows) ? rows : null}
          date={nav.date}
          onBack={() => setNav({ view: "week", beachId: nav.beachId })}
        />
      );
    }
    return (
      <BeachList
        beaches={beaches}
        error={beachesError}
        qualityByBeach={qualityByBeach}
        onSelectBeach={(beachId) => setNav({ view: "week", beachId })}
      />
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>התראות גלישה</h1>
        <p className="tagline">
          נוחות והשוואה בין חופים -- לא דיוק גובה גל עדיף. ערכים משוערים תמיד מסומנים "הערכה".
        </p>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={t.key === tab ? "tab active" : "tab"}
              onClick={() => {
                setTab(t.key);
                if (t.key === "beaches") setNav({ view: "list" });
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main>{tab === "beaches" ? renderBeaches() : <SubscriptionForm />}</main>
    </div>
  );
}
