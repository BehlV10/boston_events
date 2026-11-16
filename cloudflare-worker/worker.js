/**
 * Cloudflare Worker: Event Submission Proxy for Boston Events
 * Accepts POST /submit-event from the frontend, validates the event,
 * and triggers a GitHub Action repository_dispatch to automatically rebuild and publish the site.
 * POST /extract-flyer reads an uploaded flyer image with Claude and returns form fields to review.
 * Deploy with `npm run deploy` (see README.md).
 */
import Anthropic from "@anthropic-ai/sdk";
import { extractFlyer, FlyerError } from "./flyer.js";

function bostonToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

/** Soft daily caps in KV (eventually consistent, which is fine for limiting cost). */
async function takeFlyerQuota(env, ip) {
  const day = bostonToday();
  const perIp = parseInt(env.FLYER_DAILY_LIMIT_PER_IP || "15", 10);
  const total = parseInt(env.FLYER_DAILY_LIMIT_TOTAL || "400", 10);
  const ipKey = `ip:${ip}:${day}`;
  const totalKey = `total:${day}`;
  const [ipCount, totalCount] = await Promise.all([
    env.FLYER_LIMITS.get(ipKey).then((v) => parseInt(v || "0", 10)),
    env.FLYER_LIMITS.get(totalKey).then((v) => parseInt(v || "0", 10)),
  ]);
  if (ipCount >= perIp || totalCount >= total) return false;
  const ttl = { expirationTtl: 60 * 60 * 48 };
  await Promise.all([
    env.FLYER_LIMITS.put(ipKey, String(ipCount + 1), ttl),
    env.FLYER_LIMITS.put(totalKey, String(totalCount + 1), ttl),
  ]);
  return true;
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
  if (!env.ANTHROPIC_API_KEY || !env.FLYER_LIMITS) {
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
  if (!(await takeFlyerQuota(env, ip))) {
    return json({ error: "Daily flyer limit reached. Please fill in the form by hand." }, 429);
  }

  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, maxRetries: 1, timeout: 45_000 });
  try {
    const { fields } = await extractFlyer(client, {
      image: body.image,
      mediaType: body.media_type,
      today: bostonToday(),
    });
    return json({ success: true, fields });
  } catch (err) {
    if (err instanceof FlyerError) return json({ error: err.message }, err.status);
    console.error("extract-flyer failed", err);
    return json({ error: "Couldn't read the flyer. Please fill in the form by hand." }, 500);
  }
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
