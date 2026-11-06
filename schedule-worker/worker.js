// Short links for My Schedule. POST /api/schedule saves a schedule and returns /s/<id>; GET /s/<id>
// serves the normal /schedule/ page with that schedule embedded and a link preview filled in.
// The id is a hash of the schedule, so the same list always gets the same link.

const DAY = 86400;
const TZ = "America/New_York";
const MAX_BYTES = 32768;
const MAX_EVENTS = 100;
const MAX_LINKS_PER_HOUR = 40; // per visitor
const ALLOWED_ORIGINS = ["https://www.wickedbostonevents.com", "https://wickedbostonevents.com"];
const BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

function webLink(value) {
  try {
    const url = new URL(String(value));
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : "";
  } catch {
    return "";
  }
}

// Whoever calls the API writes this data, so keep only the expected fields, and only upcoming events
// or ones that passed less than a day ago.
export function cleanSchedule(body, now) {
  const rows = body && Array.isArray(body.e) ? body.e : [];
  const events = [];
  for (const row of rows) {
    if (!Array.isArray(row)) continue;
    const title = String(row[0] || "").trim().slice(0, 200);
    const epoch = Math.floor(Number(row[1]));
    if (!title || !Number.isFinite(epoch) || epoch < now - DAY) continue;
    events.push([title, epoch, String(row[2] || "").slice(0, 120), webLink(row[3]), row[4] ? 1 : 0]);
  }
  events.sort((a, b) => a[1] - b[1]);
  return { v: 1, n: String((body && body.n) || "").trim().slice(0, 40), e: events.slice(0, MAX_EVENTS) };
}

export async function scheduleId(text, length = 7) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  let number = 0n;
  for (const byte of digest) number = (number << 8n) | BigInt(byte);
  let id = "";
  for (let i = 0; i < length; i++) {
    id += BASE62[Number(number % 62n)];
    number /= 62n;
  }
  return id;
}

// The whole schedule is deleted a day after its last event.
export function expiresAt(schedule, now) {
  const last = schedule.e[schedule.e.length - 1][1];
  return Math.max(now + 120, Math.min(last + DAY, now + 366 * DAY));
}

function dayLabel(epoch, options) {
  return new Intl.DateTimeFormat("en-US", { timeZone: TZ, ...options }).format(new Date(epoch * 1000));
}

export function preview(schedule) {
  const days = [...new Set(schedule.e.map(row => dayLabel(row[1], { weekday: "short", month: "short", day: "numeric" })))];
  const weekend = days.length <= 3 && days.every(day => /^(Fri|Sat|Sun)/.test(day));
  const kind = weekend ? "weekend" : "schedule";
  const count = schedule.e.length;
  const title = schedule.n
    ? `${schedule.n}${/s$/i.test(schedule.n) ? "'" : "'s"} ${kind}`
    : weekend ? "A weekend plan" : "A schedule";
  const span = days.length > 1 ? `${days[0]} to ${days[days.length - 1]}` : days[0];
  return { title, description: `${count} ${count === 1 ? "event" : "events"} · ${span}` };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

// Counted per Cloudflare location, which is enough to stop one script filling the store.
async function overHourlyLimit(request) {
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const key = new Request(`https://rate-limit.invalid/${encodeURIComponent(ip)}/${Math.floor(Date.now() / 3600000)}`);
  const hit = await caches.default.match(key);
  const count = hit ? Number(await hit.text()) : 0;
  if (count >= MAX_LINKS_PER_HOUR) return true;
  await caches.default.put(key, new Response(String(count + 1), { headers: { "Cache-Control": "max-age=3600" } }));
  return false;
}

async function createLink(request, env) {
  if (!ALLOWED_ORIGINS.includes(request.headers.get("Origin"))) return json({ error: "Not allowed" }, 403);
  if (Number(request.headers.get("Content-Length") || 0) > MAX_BYTES) return json({ error: "Too large" }, 413);
  const text = await request.text();
  if (text.length > MAX_BYTES) return json({ error: "Too large" }, 413);

  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return json({ error: "Not JSON" }, 400);
  }
  const now = Math.floor(Date.now() / 1000);
  const schedule = cleanSchedule(body, now);
  if (!schedule.e.length) return json({ error: "No upcoming events" }, 400);
  if (await overHourlyLimit(request)) return json({ error: "Too many links" }, 429);

  const value = JSON.stringify(schedule);
  for (let length = 7; length <= 12; length++) {
    const id = await scheduleId(value, length);
    const existing = await env.SCHEDULES.get(id);
    if (existing === null) await env.SCHEDULES.put(id, value, { expiration: expiresAt(schedule, now) });
    if (existing === null || existing === value) return json({ url: `${new URL(request.url).origin}/s/${id}` });
  }
  return json({ error: "Try again" }, 500);
}

// Keeps a title like "</script>" from ending the embedded data early.
export function embedded(schedule) {
  return JSON.stringify(schedule).replace(/</g, "\\u003c");
}

class SetContent {
  constructor(value) { this.value = value; }
  element(element) { element.setInnerContent(this.value); }
}

class SetMeta {
  constructor(value) { this.value = value; }
  element(element) { element.setAttribute("content", this.value); }
}

async function showSchedule(id, url, env) {
  const stored = /^[0-9A-Za-z]{7,12}$/.test(id) ? await env.SCHEDULES.get(id, "json") : null;
  const schedule = stored && cleanSchedule(stored, Math.floor(Date.now() / 1000));
  const found = Boolean(schedule && schedule.e.length);

  const page = await fetch(`${url.origin}/schedule/`);
  if (!page.ok) return new Response("Please try again in a minute.", { status: 502 });

  const headers = new Headers(page.headers);
  headers.set("Content-Type", "text/html; charset=utf-8");
  headers.set("Cache-Control", "public, max-age=300");
  headers.set("X-Robots-Tag", "noindex");
  const response = new Response(page.body, { status: found ? 200 : 404, headers });
  if (!found) return response;

  const { title, description } = preview(schedule);
  return new HTMLRewriter()
    .on("title", new SetContent(`${title} | Wicked Boston Events`))
    .on('meta[name="description"]', new SetMeta(description))
    .on('meta[property="og:title"]', new SetMeta(title))
    .on('meta[property="og:description"]', new SetMeta(description))
    .on("head", {
      element(head) {
        head.append(`<script type="application/json" id="schedule-data">${embedded(schedule)}</script>`, { html: true });
      },
    })
    .transform(response);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/api/schedule") {
      if (request.method !== "POST") return json({ error: "Use POST" }, 405);
      return createLink(request, env);
    }
    const match = url.pathname.match(/^\/s\/([^/]*)\/?$/);
    if (match && (request.method === "GET" || request.method === "HEAD")) return showSchedule(match[1], url, env);
    return new Response("Not found", { status: 404 });
  },
};
