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

// An OPTIONAL email address -- a second, opt-in alert delivery channel alongside Web Push
// (app/alerting/email.py). Unlike getUserId(), this has no default: absent means "push
// only", and every new subscription/watch reads it fresh rather than caching it, so
// setting it once in the Alerts tab applies to alerts created afterward.
const EMAIL_KEY = "surf_alert_user_email";

export function getUserEmail() {
  try {
    return localStorage.getItem(EMAIL_KEY) || "";
  } catch {
    return "";
  }
}

export function setUserEmail(email) {
  try {
    if (email) localStorage.setItem(EMAIL_KEY, email);
    else localStorage.removeItem(EMAIL_KEY);
  } catch {
    /* localStorage unavailable -- the email just won't persist across visits */
  }
}
