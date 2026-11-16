// Spend controls on /extract-flyer: burst limiter, daily caps, dollar budget, audit log, admin view.
// The Anthropic API is faked by intercepting fetch, so nothing is billed.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import worker from "../worker.js";
import { costUsd } from "../flyer.js";

class FakeKV {
  constructor() { this.m = new Map(); }
  async get(k) { return this.m.has(k) ? this.m.get(k).v : null; }
  async put(k, v, opts = {}) { this.m.set(k, { v, metadata: opts.metadata }); }
  async list({ prefix }) {
    const keys = [...this.m.entries()].filter(([k]) => k.startsWith(prefix)).map(([name, e]) => ({ name, metadata: e.metadata }));
    return { keys, list_complete: true };
  }
}

const ORIGIN = "https://www.wickedbostonevents.com";
const IMG = Buffer.from("fake-jpeg-bytes").toString("base64");
const FIELDS = { is_event_flyer: true, name: "Swing Night", venue: "The Rockwell", address: null, city: "somerville",
  date: "2026-12-05", start_time: "20:00", price: "$10", category: "dance", ticket_url: null,
  website: "https://therockwell.org", description: null, guessed_fields: [] };

let realFetch, apiCalls;
beforeEach(() => {
  realFetch = globalThis.fetch;
  apiCalls = 0;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /api\.anthropic\.com/);
    apiCalls++;
    return new Response(JSON.stringify({
      id: "msg_test", type: "message", role: "assistant", model: "claude-haiku-5-5",
      content: [{ type: "text", text: JSON.stringify(FIELDS) }], stop_reason: "end_turn", stop_sequence: null,
      usage: { input_tokens: 2000, output_tokens: 400 },
    }), { status: 200, headers: { "content-type": "application/json", "request-id": "req_test" } });
  };
});
afterEach(() => { globalThis.fetch = realFetch; });

function env(over = {}) {
  return { ANTHROPIC_API_KEY: "sk-test", FLYER_LIMITS: new FakeKV(), ALLOWED_ORIGINS: ORIGIN,
           ADMIN_TOKEN: "admin-secret", FLYER_DAILY_LIMIT_PER_IP: "15", FLYER_DAILY_LIMIT_TOTAL: "400",
           FLYER_DAILY_BUDGET_USD: "1", ...over };
}
const flyer = (ip = "203.0.113.5") => new Request("https://w.example/extract-flyer", {
  method: "POST", body: JSON.stringify({ image: IMG, media_type: "image/jpeg" }),
  headers: { Origin: ORIGIN, "CF-Connecting-IP": ip, "Content-Type": "application/json" } });
const usage = (e, token = "admin-secret") => worker.fetch(new Request("https://w.example/admin/flyer-usage",
  { headers: token ? { Authorization: `Bearer ${token}` } : {} }), e, {});

test("cost uses Haiku 5.5 rates", () => {
  assert.equal(costUsd({ input_tokens: 1_000_000, output_tokens: 1_000_000 }), 0.6);
  assert.equal(costUsd(null), 0);
});

test("a successful read is audited, tallied, and the IP is stored hashed", async () => {
  const e = env();
  const r = await worker.fetch(flyer(), e, {});
  assert.equal(r.status, 200, await r.clone().text());
  assert.equal((await r.json()).fields.name, "Swing Night");
  const report = await (await usage(e)).json();
  assert.equal(report.requests, 1);
  assert.equal(report.ok, 1);
  assert.equal(report.spend_usd, 0.0004);
  assert.equal(report.rows[0].name, "Swing Night");
  assert.doesNotMatch(JSON.stringify(report), /203\.0\.113\.5/);
});

test("per-IP daily cap blocks before calling Claude", async () => {
  const e = env({ FLYER_DAILY_LIMIT_PER_IP: "2" });
  for (let i = 0; i < 2; i++) assert.equal((await worker.fetch(flyer(), e, {})).status, 200);
  const r = await worker.fetch(flyer(), e, {});
  assert.equal(r.status, 429);
  assert.equal(apiCalls, 2);
  assert.equal((await worker.fetch(flyer("198.51.100.9"), e, {})).status, 200, "other visitors unaffected");
});

test("daily dollar budget pauses reading for everyone", async () => {
  const e = env({ FLYER_DAILY_BUDGET_USD: "0.0005" });
  assert.equal((await worker.fetch(flyer("198.51.100.1"), e, {})).status, 200);   // spends $0.0004
  assert.equal((await worker.fetch(flyer("198.51.100.2"), e, {})).status, 200);   // $0.0004 < budget, allowed
  const r = await worker.fetch(flyer("198.51.100.3"), e, {});                      // $0.0008 >= budget
  assert.equal(r.status, 429);
  assert.match((await r.json()).error, /paused for today/);
  assert.equal(apiCalls, 2);
});

test("burst limiter rejects without spending", async () => {
  const e = env({ FLYER_RATE_LIMITER: { limit: async () => ({ success: false }) } });
  const r = await worker.fetch(flyer(), e, {});
  assert.equal(r.status, 429);
  assert.equal(apiCalls, 0);
  const report = await (await usage(e)).json();
  assert.equal(report.rows[0].err, "rate_limited");
});

test("other sites can't use the endpoint", async () => {
  const e = env();
  const req = new Request("https://w.example/extract-flyer", { method: "POST",
    body: JSON.stringify({ image: IMG, media_type: "image/jpeg" }), headers: { Origin: "https://evil.example" } });
  assert.equal((await worker.fetch(req, e, {})).status, 403);
  assert.equal(apiCalls, 0);
});

test("usage report needs the admin token", async () => {
  assert.equal((await usage(env(), null)).status, 404);
  assert.equal((await usage(env(), "wrong")).status, 404);
  assert.equal((await usage(env({ ADMIN_TOKEN: undefined }), "")).status, 404);
});
