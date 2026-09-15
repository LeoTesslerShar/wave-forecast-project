// Minimal Web Push service worker. The payload shape is app/alerting/notification.py's
// build_payload / app/alerting/slot_watch.py's _build_payload -- both always carry `title`,
// so that's the only field this trusts without a fallback.

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: event.data ? event.data.text() : "עדכון גלישה" };
  }

  const title = data.title || "עדכון גלישה";
  const body = data.quality_reasoning || data.calibration_note || "";

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/favicon.ico",
      data,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/");
    }),
  );
});
