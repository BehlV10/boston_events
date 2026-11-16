import { test } from "node:test";
import assert from "node:assert/strict";
import { extractFlyer, cleanFields, costUsd, rollDateForward, FlyerError, FLYER_MODEL } from "../flyer.js";

const IMG = Buffer.from("fake image bytes").toString("base64");
const TODAY = "2026-11-15";

const FIELDS = {
  is_event_flyer: true, name: "Swing Night", venue: "The Rockwell", address: "255 Elm St",
  city: "somerville", date: "2026-11-20", start_time: "20:00", price: "$10", category: "dance",
  ticket_url: "https://example.com/tix", website: "https://therockwell.org", description: "Live band swing dance.",
  guessed_fields: ["city"],
};

/** A fake fetch that answers like Gemini's generateContent. */
function gemini(payload, { status = 200, seen = {} } = {}) {
  return async (url, init) => {
    seen.url = url;
    seen.init = init;
    seen.body = JSON.parse(init.body);
    return new Response(typeof payload === "string" ? payload : JSON.stringify(payload), { status });
  };
}
const reply = (obj, finishReason = "STOP", extraParts = []) => ({
  candidates: [{ content: { role: "model", parts: [...extraParts, { text: typeof obj === "string" ? obj : JSON.stringify(obj) }] }, finishReason }],
  usageMetadata: { promptTokenCount: 1200, candidatesTokenCount: 300, thoughtsTokenCount: 100 },
});

test("sends the image to Gemini with the JSON schema and returns cleaned fields", async () => {
  const seen = {};
  const { fields, usage } = await extractFlyer({ apiKey: "k", fetch: gemini(reply(FIELDS), { seen }) },
    { image: IMG, mediaType: "image/jpeg", today: TODAY });
  assert.equal(fields.name, "Swing Night");
  assert.equal(fields.website, "https://therockwell.org");
  assert.match(seen.url, new RegExp(`/models/${FLYER_MODEL}:generateContent$`));
  assert.equal(seen.init.headers["x-goog-api-key"], "k");
  assert.equal(seen.body.generationConfig.responseMimeType, "application/json");
  assert.ok(seen.body.generationConfig.responseJsonSchema.properties.website);
  const parts = seen.body.contents[0].parts;
  assert.match(parts[0].text, /2026-11-15/);
  assert.deepEqual(parts[1].inlineData, { mimeType: "image/jpeg", data: IMG });
  assert.deepEqual(usage, { input_tokens: 1200, output_tokens: 400 });
});

test("thought parts are ignored and the model can be overridden", async () => {
  const seen = {};
  const { fields } = await extractFlyer({ apiKey: "k", model: "gemini-test", fetch: gemini(reply(FIELDS, "STOP", [{ text: "thinking...", thought: true }]), { seen }) },
    { image: IMG, mediaType: "image/png", today: TODAY });
  assert.equal(fields.name, "Swing Night");
  assert.match(seen.url, /\/models\/gemini-test:generateContent$/);
});

test("blocked, truncated, non-JSON and non-flyer replies become friendly 422s", async () => {
  for (const payload of [
    { promptFeedback: { blockReason: "SAFETY" } },
    reply(FIELDS, "SAFETY"),
    reply('{"is_event_flyer": true, "name": "Sw', "MAX_TOKENS"),
    reply("not json"),
    reply({ ...FIELDS, is_event_flyer: false }),
    { candidates: [] },
  ]) {
    await assert.rejects(extractFlyer({ apiKey: "k", fetch: gemini(payload) }, { image: IMG, mediaType: "image/png", today: TODAY }),
      (e) => e instanceof FlyerError && e.status === 422, JSON.stringify(payload).slice(0, 80));
  }
});

test("API errors map to friendly statuses", async () => {
  const cases = [[429, "quota", 503], [400, "Unable to process input image", 400], [400, "API key not valid", 502], [500, "oops", 502], [403, "denied", 502]];
  for (const [status, text, want] of cases) {
    await assert.rejects(extractFlyer({ apiKey: "k", fetch: gemini(text, { status }) }, { image: IMG, mediaType: "image/png", today: TODAY }),
      (e) => e instanceof FlyerError && e.status === want, `${status} ${text}`);
  }
  await assert.rejects(extractFlyer({ apiKey: "k", fetch: async () => { throw new TypeError("network"); } },
    { image: IMG, mediaType: "image/png", today: TODAY }), (e) => e.status === 502);
});

test("rejects bad media types, bad base64 and oversized images before calling the API", async () => {
  const api = { apiKey: "k", fetch: async () => { throw new Error("should not be called"); } };
  await assert.rejects(extractFlyer(api, { image: IMG, mediaType: "application/pdf", today: "x" }), FlyerError);
  await assert.rejects(extractFlyer(api, { image: "not base64!", mediaType: "image/png", today: "x" }), FlyerError);
  await assert.rejects(extractFlyer(api, { image: "A".repeat(6_000_000), mediaType: "image/png", today: "x" }),
    (e) => e.status === 413);
});

test("cleanFields drops malformed values", () => {
  const f = cleanFields({ ...FIELDS, date: "Nov 20", start_time: "8pm", website: "javascript:alert(1)",
    ticket_url: "ftp://x", city: "brooklyn", category: "rave", guessed_fields: "city" });
  assert.equal(f.date, null);
  assert.equal(f.start_time, null);
  assert.equal(f.website, null);
  assert.equal(f.ticket_url, null);
  assert.equal(f.city, "other");
  assert.equal(f.category, "other");
  assert.deepEqual(f.guessed_fields, []);
});

test("cost is tallied at paid flash-lite rates", () => {
  assert.equal(costUsd({ input_tokens: 1_000_000, output_tokens: 1_000_000 }), 2.8);
  assert.equal(costUsd(null), 0);
});

test("past dates roll forward to the next occurrence and are flagged", () => {
  const f = (date, guessed = []) => rollDateForward({ ...cleanFields(FIELDS), date, guessed_fields: guessed }, "2026-11-15");
  assert.equal(f("2025-12-05").date, "2026-12-05");       // model guessed last year
  assert.deepEqual(f("2025-12-05").guessed_fields, ["date"]);
  assert.equal(f("2026-03-02").date, "2027-03-02");       // month already passed this year
  assert.equal(f("2026-11-15").date, "2026-11-15");       // today stays
  assert.equal(f("2027-01-10", ["city"]).date, "2027-01-10");
  assert.deepEqual(f("2025-11-20", ["date"]).guessed_fields, ["date"]);
  assert.equal(f(null).date, null);
});

test("a wrong-year reply from the model is corrected end to end", async () => {
  const { fields } = await extractFlyer({ apiKey: "k", fetch: gemini(reply({ ...FIELDS, date: "2025-12-05", guessed_fields: [] })) },
    { image: IMG, mediaType: "image/jpeg", today: TODAY });
  assert.equal(fields.date, "2026-12-05");
  assert.ok(fields.guessed_fields.includes("date"));
});
