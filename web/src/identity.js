// A stable per-browser user id, generated once and kept in localStorage -- both the
// subscription form and the per-slot watch button need one, and today only the form has a
// free-text box with no persistence. Falls back to an in-memory id (not persisted) if
// localStorage is unavailable (private browsing, blocked storage) rather than throwing --
// the app must still work for the session, just without cross-visit persistence.

const KEY = "surf_alert_user_id";
let memoryFallback = null;

function randomId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `u-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getUserId() {
  try {
    let id = localStorage.getItem(KEY);
    if (!id) {
      id = randomId();
      localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    if (!memoryFallback) memoryFallback = randomId();
    return memoryFallback;
  }
}
