// Web Push client stack -- previously entirely missing (no service worker, no permission
// flow, no subscribe call), which meant "alert me" would deliver nothing however correct
// the backend was (docs/DECISIONS.md). Called lazily on the first watch tap, not on page
// load, so the permission prompt has obvious context rather than firing unexplained.
import { api } from "./api.js";
import { getUserId } from "./identity.js";

// Standard base64url -> Uint8Array conversion -- the Push API wants applicationServerKey
// as bytes, the backend hands the VAPID public key back as base64url text.
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

export function pushSupported() {
  return "serviceWorker" in navigator && "PushManager" in window;
}

let registerPromise = null;

/** Idempotent: safe to call on every watch tap. Resolves once permission is granted, the
 * service worker is registered, and the browser's push subscription is registered with the
 * backend -- or throws with a message worth surfacing to the user (permission denied, no
 * VAPID key configured yet, etc). Concurrent calls share one in-flight attempt. */
export async function ensurePushRegistered() {
  if (!pushSupported()) {
    throw new Error("דפדפן זה לא תומך בהתראות דחיפה");
  }
  if (!registerPromise) {
    registerPromise = _register().catch((err) => {
      registerPromise = null; // allow retrying after a failure
      throw err;
    });
  }
  return registerPromise;
}

async function _register() {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("ההתראות נחסמו -- אי אפשר לשלוח לך עדכונים בלי אישור");
  }

  const registration = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const existing = await registration.pushManager.getSubscription();
  const { vapid_public_key: vapidPublicKey } = await api.getPushConfig();
  if (!vapidPublicKey) {
    throw new Error("שרת ההתראות עדיין לא הוגדר (חסר מפתח VAPID)");
  }

  const subscription =
    existing ||
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    }));

  const json = subscription.toJSON();
  await api.registerPushSubscription({
    user_id: getUserId(),
    endpoint: json.endpoint,
    p256dh: json.keys.p256dh,
    auth: json.keys.auth,
  });
}
