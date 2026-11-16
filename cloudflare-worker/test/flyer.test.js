import { test } from "node:test";
import assert from "node:assert/strict";
import { extractFlyer, cleanFields, FlyerError, FLYER_MODEL } from "../flyer.js";

const IMG = Buffer.from("fake image bytes").toString("base64");

function fakeClient(response, seen = {}) {
  return { messages: { parse: async (params) => { seen.params = params; return response; } } };
}

const FIELDS = {
  is_event_flyer: true, name: "Swing Night", venue: "The Rockwell", address: "255 Elm St",
  city: "somerville", date: "2026-11-20", start_time: "20:00", price: "$10", category: "dance",
  ticket_url: "https://example.com/tix", website: "https://therockwell.org", description: "Live band swing dance.",
  guessed_fields: ["city"],
};

test("returns cleaned fields and sends the image to Haiku at low effort", async () => {
  const seen = {};
  const { fields } = await extractFlyer(fakeClient({ stop_reason: "end_turn", parsed_output: FIELDS }, seen),
    { image: IMG, mediaType: "image/jpeg", today: "2026-11-15" });
  assert.equal(fields.name, "Swing Night");
  assert.equal(fields.website, "https://therockwell.org");
  assert.equal(seen.params.model, FLYER_MODEL);
  assert.equal(seen.params.output_config.effort, "low");
  assert.equal(seen.params.messages[0].content[0].type, "image");
  assert.match(seen.params.messages[0].content[1].text, /2026-11-15/);
});

test("refusals, non-flyers and empty output become friendly errors", async () => {
  for (const resp of [
    { stop_reason: "refusal", parsed_output: null },
    { stop_reason: "max_tokens", parsed_output: null },
    { stop_reason: "end_turn", parsed_output: { ...FIELDS, is_event_flyer: false } },
  ]) {
    await assert.rejects(extractFlyer(fakeClient(resp), { image: IMG, mediaType: "image/png", today: "2026-11-15" }),
      (e) => e instanceof FlyerError && e.status === 422);
  }
});

test("rejects bad media types, bad base64 and oversized images before calling the API", async () => {
  const client = { messages: { parse: async () => { throw new Error("should not be called"); } } };
  await assert.rejects(extractFlyer(client, { image: IMG, mediaType: "application/pdf", today: "x" }), FlyerError);
  await assert.rejects(extractFlyer(client, { image: "not base64!", mediaType: "image/png", today: "x" }), FlyerError);
  await assert.rejects(extractFlyer(client, { image: "A".repeat(6_000_000), mediaType: "image/png", today: "x" }),
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
