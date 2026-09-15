import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./index.css";

// Register the service worker eagerly (idempotent -- a repeat call with the same script
// URL is a no-op) so it's ready by the time a user first taps "watch". Does NOT request
// notification permission here -- that stays lazy, in src/push.js, triggered by the watch
// tap itself, so the browser's permission prompt has obvious context.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* push just won't work until a watch tap retries registration -- not fatal on load */
  });
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
