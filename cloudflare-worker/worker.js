/**
 * Cloudflare Worker: Event Submission Proxy for Boston Events
 * Accepts POST /submit-event from the frontend, validates the event,
 * and triggers a GitHub Action repository_dispatch to automatically rebuild and publish the site.
 * POST /extract-flyer reads an uploaded flyer image with Gemini and returns form fields to review.
 * Deploy with `npm run deploy` (see README.md).
 */
import { costUsd, extractFlyer, FlyerError } from "./flyer.js";

function bostonToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

const DAY_TTL = { expirationTtl: 60 * 60 * 48 };
const AUDIT_TTL = { expirationTtl: 60 * 60 * 24 * 30 };

/** Soft daily caps in KV (eventually consistent; the per-minute limiter and Gemini's own
 * free-tier quota cover bursts). Returns an error message, or null to go ahead. */
async function checkFlyerQuota(env, ip, day) {
  const perIp = parseInt(env.FLYER_DAILY_LIMIT_PER_IP || "15", 10);
  const total = parseInt(env.FLYER_DAILY_LIMIT_TOTAL || "400", 10);
  const budget = parseFloat(env.FLYER_DAILY_BUDGET_USD || "1");
  const [ipCount, totalCount, spent] = await Promise.all([
    env.FLYER_LIMITS.get(`ip:${ip}:${day}`).then((v) => parseInt(v || "0", 10)),
    env.FLYER_LIMITS.get(`total:${day}`).then((v) => parseInt(v || "0", 10)),
    env.FLYER_LIMITS.get(`spend:${day}`).then((v) => parseFloat(v || "0")),
  ]);
  if (ipCount >= perIp) return "You've reached today's flyer limit. Please fill in the form by hand.";
  if (totalCount >= total || spent >= budget) return "Flyer reading is paused for today. Please fill in the form by hand.";
  await Promise.all([
    env.FLYER_LIMITS.put(`ip:${ip}:${day}`, String(ipCount + 1), DAY_TTL),
    env.FLYER_LIMITS.put(`total:${day}`, String(totalCount + 1), DAY_TTL),
  ]);
  return null;
}

async function addSpend(env, day, usd) {
  if (!usd) return;
  const spent = parseFloat((await env.FLYER_LIMITS.get(`spend:${day}`)) || "0");
  await env.FLYER_LIMITS.put(`spend:${day}`, (spent + usd).toFixed(6), DAY_TTL);
}

/** Hash IPs before storing them: enough to spot one address hammering the endpoint, without keeping it. */
async function hashIp(ip, day, salt) {
  const data = new TextEncoder().encode(`${salt || "flyer"}:${day}:${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest).slice(0, 6)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** One audit row per flyer request, kept 30 days; the data lives in the key's metadata so a list() reads it all. */
async function audit(env, day, row) {
  const key = `log:${day}:${new Date().toISOString()}:${crypto.randomUUID().slice(0, 8)}`;
  await env.FLYER_LIMITS.put(key, "", { ...AUDIT_TTL, metadata: row });
}

async function handleFlyerUsage(request, env, url) {
  const auth = request.headers.get("Authorization") || "";
  if (!env.ADMIN_TOKEN || !env.FLYER_LIMITS || auth !== `Bearer ${env.ADMIN_TOKEN}`) {
    return new Response("Not found", { status: 404 });
  }
  const day = /^\d{4}-\d{2}-\d{2}$/.test(url.searchParams.get("day") || "") ? url.searchParams.get("day") : bostonToday();
  const rows = [];
  let cursor;
  do {
    const page = await env.FLYER_LIMITS.list({ prefix: `log:${day}:`, cursor });
    for (const k of page.keys) rows.push({ at: k.name.split(":").slice(2, -1).join(":"), ...(k.metadata || {}) });
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor && rows.length < 5000);
  const byIp = {};
  for (const r of rows) byIp[r.ip] = (byIp[r.ip] || 0) + 1;
  const body = {
    day,
    requests: rows.length,
    ok: rows.filter((r) => r.ok).length,
    spend_usd: parseFloat((await env.FLYER_LIMITS.get(`spend:${day}`)) || "0"),
    budget_usd: parseFloat(env.FLYER_DAILY_BUDGET_USD || "1"),
    top_ips: Object.entries(byIp).sort((a, b) => b[1] - a[1]).slice(0, 10),
    rows,
  };
  return new Response(JSON.stringify(body, null, 2), { headers: { "Content-Type": "application/json" } });
}

async function verifyTurnstile(env, token) {
  const resp = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ secret: env.TURNSTILE_SECRET_KEY, response: token }),
  });
  return (await resp.json()).success === true;
}

async function handleExtractFlyer(request, env, corsHeaders) {
  const json = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", ...corsHeaders } });

  const allowed = (env.ALLOWED_ORIGINS || "").split(",").map((s) => s.trim()).filter(Boolean);
  const origin = request.headers.get("Origin") || "";
  if (allowed.length && !allowed.includes(origin)) {
    return json({ error: "Flyer upload is only available on the Wicked Boston Events site." }, 403);
  }
  if (!env.GEMINI_API_KEY || !env.FLYER_LIMITS) {
    return json({ error: "Flyer upload isn't set up yet. Please fill in the form by hand." }, 503);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Invalid request." }, 400);
  }
  if (env.TURNSTILE_SECRET_KEY && !(body.turnstileToken && (await verifyTurnstile(env, body.turnstileToken)))) {
    return json({ error: "CAPTCHA verification failed" }, 400);
  }

  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const day = bostonToday();
  const ipHash = await hashIp(ip, day, env.AUDIT_SALT);

  // Per-minute burst limit (Cloudflare rate limiting binding; approximate, per data center).
  if (env.FLYER_RATE_LIMITER && !(await env.FLYER_RATE_LIMITER.limit({ key: ip })).success) {
    await audit(env, day, { ip: ipHash, ok: false, err: "rate_limited" });
    return json({ error: "Too many flyers at once. Please wait a minute and try again." }, 429);
  }
  const quotaError = await checkFlyerQuota(env, ip, day);
  if (quotaError) {
    await audit(env, day, { ip: ipHash, ok: false, err: "daily_limit" });
    return json({ error: quotaError }, 429);
  }

  let usage = null;
  let result;
  try {
    const out = await extractFlyer({ apiKey: env.GEMINI_API_KEY, model: env.GEMINI_MODEL }, { image: body.image, mediaType: body.media_type, today: day });
    usage = out.usage;
    result = json({ success: true, fields: out.fields });
    await audit(env, day, { ip: ipHash, ok: true, in: usage?.input_tokens, out: usage?.output_tokens,
                            usd: +costUsd(usage).toFixed(6), name: (out.fields.name || "").slice(0, 60) });
  } catch (err) {
    usage = err.usage || null;
    const known = err instanceof FlyerError;
    if (!known) console.error("extract-flyer failed", err);
    result = known ? json({ error: err.message }, err.status)
                   : json({ error: "Couldn't read the flyer. Please fill in the form by hand." }, 500);
    await audit(env, day, { ip: ipHash, ok: false, err: known ? err.message.slice(0, 60) : "server_error",
                            in: usage?.input_tokens, out: usage?.output_tokens, usd: +costUsd(usage).toFixed(6) });
  }
  await addSpend(env, day, costUsd(usage));
  return result;
}

export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/admin/flyer-usage") {
      return handleFlyerUsage(request, env, url);
    }
    if (request.method === "POST" && url.pathname === "/extract-flyer") {
      const origin = request.headers.get("Origin") || "";
      return handleExtractFlyer(request, env, origin ? { ...corsHeaders, "Access-Control-Allow-Origin": origin, Vary: "Origin" } : corsHeaders);
    }

    // 1. Upvotes API (GET /api/upvotes)
    if (url.pathname === "/api/upvotes" && request.method === "GET") {
      let upvotes = {};
      if (env.UPVOTES) {
        try {
          const stored = await env.UPVOTES.get("upvotes_map", { type: "json" });
          if (stored && typeof stored === "object") upvotes = stored;
        } catch (_) {}
      }
      return new Response(JSON.stringify(upvotes), {
        status: 200,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    // 2. Upvote action (POST /api/upvote)
    if (url.pathname === "/api/upvote" && request.method === "POST") {
      try {
        const body = await request.json();
        const evId = body.id;
        const action = body.action || "add";
        if (!evId || typeof evId !== "string") {
          return new Response(JSON.stringify({ error: "Missing event id" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        let votes = (action === "remove") ? 0 : 1;
        if (env.UPVOTES) {
          let map = {};
          try {
            const raw = await env.UPVOTES.get("upvotes_map", { type: "json" });
            if (raw && typeof raw === "object") map = raw;
          } catch (_) {}

          const current = parseInt(map[evId] || "0", 10);
          if (action === "remove") {
            votes = Math.max(0, current - 1);
          } else {
            votes = current + 1;
          }

          if (votes === 0) {
            delete map[evId];
          } else {
            map[evId] = votes;
          }

          await env.UPVOTES.put("upvotes_map", JSON.stringify(map));
        }

        return new Response(JSON.stringify({ success: true, id: evId, votes }), {
          status: 200,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      } catch (err) {
        return new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
    }

    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "Method not allowed" }), {
        status: 405,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }

    try {
      const body = await request.json();

      // 1. Anti-bot honeypot check
      if (body._hp_company) {
        return new Response(JSON.stringify({ success: true, message: "Received" }), {
          status: 200,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      // 2. Cloudflare Turnstile CAPTCHA verification (if secret configured)
      if (env.TURNSTILE_SECRET_KEY && body.turnstileToken) {
        const turnstileResp = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            secret: env.TURNSTILE_SECRET_KEY,
            response: body.turnstileToken,
          }),
        });
        const turnstileResult = await turnstileResp.json();
        if (!turnstileResult.success) {
          return new Response(JSON.stringify({ error: "CAPTCHA verification failed" }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }
      }

      const GITHUB_REPO = env.GITHUB_REPO || "BehlV10/boston_events";
      const GITHUB_TOKEN = env.GITHUB_TOKEN; // Personal Access Token with repo/actions scope

      // Handle Venue Suggestion
      if (body.type === "suggest_venue") {
        const name = (body.name || "").trim().slice(0, 150);
        const url = (body.url || "").trim();
        const city = (body.city || "other").trim().toLowerCase();
        const category = (body.category || "music").trim().toLowerCase();
        const address = (body.address || "").trim().slice(0, 150);
        const notes = (body.notes || "").trim().slice(0, 500);

        if (!name || name.length < 2) {
          return new Response(JSON.stringify({ error: "Venue name must be at least 2 characters." }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }
        if (!url || !url.startsWith("http")) {
          return new Response(JSON.stringify({ error: "Valid venue website link is required." }), {
            status: 400,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }

        const venuePayload = { name, url, city, category, address, notes };

        if (GITHUB_TOKEN) {
          const ghResp = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
            method: "POST",
            headers: {
              "Accept": "application/vnd.github.v3+json",
              "Authorization": `Bearer ${GITHUB_TOKEN}`,
              "User-Agent": "BostonEvents-Worker",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              event_type: "suggest-venue",
              client_payload: venuePayload,
            }),
          });

          if (!ghResp.ok) {
            const errText = await ghResp.text();
            return new Response(JSON.stringify({ error: `GitHub dispatch failed: ${errText}` }), {
              status: 502,
              headers: { "Content-Type": "application/json", ...corsHeaders },
            });
          }
        }

        return new Response(JSON.stringify({
          success: true,
          message: "Venue suggestion received! It will be reviewed for automatic scraping.",
          venue: venuePayload,
        }), {
          status: 200,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      // 3. Validate required fields for Community Event
      const name = (body.name || "").trim().slice(0, 150);
      const venue = (body.venue || "").trim().slice(0, 150);
      const date = (body.date || "").trim();
      const url = (body.url || "").trim();
      const category = (body.category || "other").trim().toLowerCase();
      const price = (body.price || "").trim().slice(0, 50);
      const city = (body.city || "").trim().toLowerCase();
      const description = (body.description || "").trim().slice(0, 500);
      const address = (body.address || "").trim().slice(0, 150);
      const website = (body.website || "").trim().slice(0, 500);

      if (!name || name.length < 2) {
        return new Response(JSON.stringify({ error: "Event name must be at least 2 characters." }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
      if (!venue || venue.length < 2) {
        return new Response(JSON.stringify({ error: "Venue name must be at least 2 characters." }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }
      if (!date) {
        return new Response(JSON.stringify({ error: "Event date is required." }), {
          status: 400,
          headers: { "Content-Type": "application/json", ...corsHeaders },
        });
      }

      const eventPayload = {
        name,
        venue,
        date,
        url,
        category,
        price: price || null,
        city: city || null,
        description: description || "",
        address: address || "",
        website: /^https?:\/\//i.test(website) ? website : "",
        _is_community: true,
      };

      // 4. Trigger GitHub Action via repository_dispatch (GITHUB_REPO / GITHUB_TOKEN set above)

      if (GITHUB_TOKEN) {
        const ghResp = await fetch(`https://api.github.com/repos/${GITHUB_REPO}/dispatches`, {
          method: "POST",
          headers: {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": `Bearer ${GITHUB_TOKEN}`,
            "User-Agent": "BostonEvents-Worker",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            event_type: "community-event",
            client_payload: eventPayload,
          }),
        });

        if (!ghResp.ok) {
          const errText = await ghResp.text();
          return new Response(JSON.stringify({ error: `GitHub dispatch failed: ${errText}` }), {
            status: 502,
            headers: { "Content-Type": "application/json", ...corsHeaders },
          });
        }
      }

      return new Response(JSON.stringify({
        success: true,
        message: "Event submitted successfully! It has been added to the build queue.",
        event: eventPayload,
      }), {
        status: 200,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json", ...corsHeaders },
      });
    }
  },
};
