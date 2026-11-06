import assert from "node:assert/strict";
import { test } from "node:test";
import { cleanSchedule, embedded, expiresAt, preview, scheduleId } from "./worker.js";

const NOW = 1794000000;
const DAY = 86400;

test("events more than a day past are removed", () => {
  const out = cleanSchedule({ e: [["Old", NOW - DAY - 1, "", "", 0], ["Recent", NOW - DAY + 1, "", "", 0]] }, NOW);
  assert.deepEqual(out.e.map(row => row[0]), ["Recent"]);
});

test("only expected fields survive and links must be web links", () => {
  const out = cleanSchedule({ n: "  Sam  ", x: 1, e: [["Show", NOW, "Venue", "javascript:alert(1)", 0, "extra"], "junk", [null, NOW]] }, NOW);
  assert.deepEqual(out, { v: 1, n: "Sam", e: [["Show", NOW, "Venue", "", 0]] });
});

test("the same schedule always gets the same short id", async () => {
  assert.equal(await scheduleId("a"), await scheduleId("a"));
  assert.notEqual(await scheduleId("a"), await scheduleId("b"));
  assert.match(await scheduleId("a"), /^[0-9A-Za-z]{7}$/);
});

test("a schedule expires a day after its last event", () => {
  assert.equal(expiresAt({ e: [["a", NOW + 10, "", "", 0], ["b", NOW + 500, "", "", 0]] }, NOW), NOW + 500 + DAY);
  assert.equal(expiresAt({ e: [["a", NOW - DAY + 1, "", "", 0]] }, NOW), NOW + 120);
  assert.equal(expiresAt({ e: [["a", NOW + 900 * DAY, "", "", 0]] }, NOW), NOW + 366 * DAY);
});

test("a title can't break out of the embedded data", () => {
  assert.ok(!embedded({ e: [["</script><script>alert(1)</script>"]] }).includes("<"));
});

test("the preview names the person and the days", () => {
  const friday = 1794009600; // Nov 6, 2026
  const out = preview({ n: "Sam", e: [["a", friday, "", "", 0], ["b", friday + DAY, "", "", 0]] });
  assert.equal(out.title, "Sam's weekend");
  assert.equal(out.description, "2 events · Fri, Nov 6 to Sat, Nov 7");
});
