// Event and venue submissions forward to GitHub's repository_dispatch, which rejects a
// client_payload with more than 10 top-level fields.
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../worker.js";

async function dispatched(body) {
  const real = globalThis.fetch;
  let sent = null;
  globalThis.fetch = async (url, init) => {
    if (String(url).includes("api.github.com")) { sent = JSON.parse(init.body); return new Response(null, { status: 204 }); }
    return new Response(JSON.stringify({ success: true }), { status: 200 });   // Turnstile etc.
  };
  try {
    const r = await worker.fetch(new Request("https://w.example/", { method: "POST", body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", Origin: "https://www.wickedbostonevents.com" } }),
      { GITHUB_TOKEN: "t", GITHUB_REPO: "BehlV10/boston_events" }, {});
    return { status: r.status, sent };
  } finally {
    globalThis.fetch = real;
  }
}

test("a full event submission dispatches at most 10 fields", async () => {
  const { status, sent } = await dispatched({
    name: "Swing Night", venue: "The Rockwell", date: "2026-12-05T19:30:00", url: "https://therockwell.org",
    category: "dance", price: "$10", city: "somerville", description: "Live band.", address: "255 Elm St",
    website: "https://therockwell.org", _is_community: true, submitted_at: "2026-11-16T05:00:00Z", extra: "x",
  });
  assert.equal(status, 200);
  assert.equal(sent.event_type, "community-event");
  assert.ok(Object.keys(sent.client_payload).length <= 10, Object.keys(sent.client_payload).join(","));
  assert.equal(sent.client_payload.website, "https://therockwell.org");
});

test("a venue suggestion dispatches at most 10 fields", async () => {
  const { sent } = await dispatched({ type: "suggest_venue", name: "New Venue", url: "https://new.example",
    city: "boston", category: "music", address: "1 Main St", notes: "great shows" });
  assert.equal(sent.event_type, "suggest-venue");
  assert.ok(Object.keys(sent.client_payload).length <= 10);
});
