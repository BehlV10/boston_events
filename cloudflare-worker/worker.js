/**
 * Cloudflare Worker: Event Submission Proxy for Boston Events
 * Accepts POST /submit-event from the frontend, validates the event,
 * and triggers a GitHub Action repository_dispatch to automatically rebuild and publish the site.
 */

export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
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
        _is_community: true,
      };

      // 4. Trigger GitHub Action via repository_dispatch
      const GITHUB_REPO = env.GITHUB_REPO || "BehlV10/boston_events";
      const GITHUB_TOKEN = env.GITHUB_TOKEN; // Personal Access Token with repo/actions scope

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
