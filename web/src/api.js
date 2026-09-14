// Thin fetch wrappers over the existing API (Phases 1-4). No scoring, no matching logic --
// prompts/phase-5-ui.md section 3: "if the UI needs data the API doesn't provide, that's a
// bug in an earlier phase, not a reason to compute it client-side."

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* body wasn't JSON -- keep statusText */
    }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listBeaches: () => request("/beaches"),

  // The full per-hour component breakdown from Phase 3 -- size/period/wind/chop/verdict,
  // with confidence markers throughout. This is the ONLY data source for both the ranked
  // list (sorted client-side by the already-computed quality_score) and the single-beach
  // breakdown view.
  getBeachQuality: (beachId, hours = 96) =>
    request(`/beaches/${encodeURIComponent(beachId)}/quality?hours=${hours}`),

  createSubscription: (body) =>
    request("/subscriptions", { method: "POST", body: JSON.stringify(body) }),

  listSubscriptions: (userId) =>
    request(`/subscriptions?user_id=${encodeURIComponent(userId)}`),

  setSubscriptionActive: (id, active) =>
    request(`/subscriptions/${id}?active=${active}`, { method: "PATCH" }),

  getSubscriptionStatus: (id) => request(`/subscriptions/${id}/status`),
};

export { BASE_URL };
