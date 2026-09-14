// Verifies SubscriptionForm.jsx's exact request body against the real live API --
// acceptance check 3: "a subscription created through the form, confirmed via the Phase 4
// API that it was stored correctly."
const BASE = "http://localhost:8000";

const userId = "web_ui_verify_user";
const body = {
  user_id: userId,
  beach_id: "herzliya",
  min_height: 1.0,
  max_height: null,
  time_window_start: "06:00:00",
  time_window_end: "09:00:00",
  operating_point: "generous",
};

const createRes = await fetch(`${BASE}/subscriptions`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});
const created = await createRes.json();
console.log("POST /subscriptions ->", createRes.status, created);

const listRes = await fetch(`${BASE}/subscriptions?user_id=${userId}`);
const list = await listRes.json();
console.log("\nGET /subscriptions?user_id= ->", listRes.status, list);

const ok =
  createRes.status === 201 &&
  list.length === 1 &&
  list[0].beach_id === "herzliya" &&
  list[0].min_height === 1.0 &&
  list[0].operating_point === "generous" &&
  list[0].time_window_start === "06:00:00" &&
  list[0].active === true;

console.log(`\nVERIFIED STORED CORRECTLY: ${ok}`);
process.exit(ok ? 0 : 1);
