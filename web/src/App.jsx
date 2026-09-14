import { useState } from "react";
import RankedBeachList from "./views/RankedBeachList.jsx";
import SingleBeachBreakdown from "./views/SingleBeachBreakdown.jsx";
import SubscriptionForm from "./views/SubscriptionForm.jsx";

const TABS = [
  { key: "ranked", label: "Beaches today", component: RankedBeachList },
  { key: "breakdown", label: "Beach detail", component: SingleBeachBreakdown },
  { key: "subscribe", label: "Alerts", component: SubscriptionForm },
];

export default function App() {
  const [tab, setTab] = useState("ranked");
  const Active = TABS.find((t) => t.key === tab).component;

  return (
    <div className="app">
      <header className="app-header">
        <h1>Surf Alert</h1>
        <p className="tagline">
          Convenience and beach discrimination, not superior wave-height accuracy --
          heuristic values are always marked "estimate."
        </p>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={t.key === tab ? "tab active" : "tab"}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        <Active />
      </main>
    </div>
  );
}
