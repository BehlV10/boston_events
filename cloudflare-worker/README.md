# Boston Events — Submission Worker

A Cloudflare Worker behind the site's **Add to Boston Events** form. It:

- **`POST /` (event or venue submission):** checks the honeypot and optional Turnstile CAPTCHA, then triggers the `community-event.yml` GitHub Action, which adds the event and republishes the site.
- **`POST /extract-flyer`:** reads an uploaded flyer image with Gemini (`gemini-3.5-flash-lite`, on the Gemini API's free tier) and returns the form fields for the visitor to check before publishing.
- **`GET /api/upvotes`, `POST /api/upvote`:** upvote counts.

When a submission includes the venue's or organizer's **website** (usually read off a flyer), the GitHub Action tries the repo's generic scrapers (JSON-LD, iCal, Squarespace, WordPress Events Calendar, Eventbrite organizer pages) on it. If one finds upcoming events, the Action opens a PR adding the site to `discovered_sources.json`. Nothing is scraped until that PR is merged.

## Deploy

Needs Node 20+ and a Cloudflare account.

```bash
cd cloudflare-worker
npm install
npx wrangler login

# One-time: create the KV namespaces, then paste the printed ids into wrangler.toml
npx wrangler kv namespace create UPVOTES
npx wrangler kv namespace create FLYER_LIMITS

# Secrets (prompted, never committed)
npx wrangler secret put GITHUB_TOKEN        # fine-grained PAT: Actions read/write on BehlV10/boston_events
npx wrangler secret put GEMINI_API_KEY      # from aistudio.google.com/apikey; enables flyer reading
# optional: npx wrangler secret put TURNSTILE_SECRET_KEY

npm run deploy
```

Then connect the site to the worker:

1. In the GitHub repo, go to **Settings → Secrets and variables → Actions → Variables**.
2. Add `EVENT_SUBMISSION_ENDPOINT` set to the worker URL that `npm run deploy` printed, e.g. `https://boston-events-submissions.<you>.workers.dev`.
3. Run the **Scrape events and deploy site** workflow, or wait for the next build.

The flyer upload box only appears on the site once that variable is set.

For the automatic scraper PRs, also enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**.

## Spending limits and auditing

Five layers, from strictest to softest:

1. **Free tier, no billing (the hard cap).** The `GEMINI_API_KEY` comes from a Google AI Studio project with billing **not** enabled, so it can't cost anything. When Google's free daily quota runs out, calls fail and visitors fill in the form by hand until it resets (midnight Pacific). Don't enable billing on that project unless you mean to pay. Note that on the free tier, Google may use submitted images to improve its products.
2. **Daily budget:** the worker tallies what each call would cost at paid Gemini rates (from the token counts the API returns) and stops reading flyers for the day at `FLYER_DAILY_BUDGET_USD` ($1 by default, several hundred flyers). On the free tier this is just another cap; it matters if billing is ever turned on. After that it returns "paused for today" and the form still works by hand.
3. **Daily counts:** 15 reads per IP and 400 in total per day (`FLYER_DAILY_LIMIT_*`).
4. **Burst limit:** 3 reads per minute per IP (the `FLYER_RATE_LIMITER` binding in `wrangler.toml`).
5. **Origin check:** reads are only accepted from the site's own origins (`ALLOWED_ORIGINS`). Scripts can fake this header, which is why the limits above exist.

Layers 2–4 are approximate. KV and the rate limiter are eventually consistent and per data center, so a burst can slip a few calls past them. Layer 1 is the real guarantee.

To switch models, change `GEMINI_MODEL` in `wrangler.toml` and redeploy.

Optional: set `TURNSTILE_SECRET_KEY` to require a Turnstile token on flyer reads. The site doesn't render the widget yet, so only set it after adding the widget.

### Audit log

Every flyer request is logged for 30 days in the `FLYER_LIMITS` KV namespace, whether it succeeded, failed or was blocked. Each entry has the time, a hashed IP (salted per day, so the raw address is never stored), the token counts and cost, the event name read, and any error.

To read it, set an admin token once:

```bash
npx wrangler secret put ADMIN_TOKEN   # any long random string, e.g. from: openssl rand -hex 24
```

Then:

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://<worker-url>/admin/flyer-usage            # today
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://<worker-url>/admin/flyer-usage?day=2026-11-20"
```

It returns that day's request count, successes, spend vs. budget, the busiest hashed IPs, and every entry. Without the token, the endpoint returns 404.

To raise or lower a limit, edit the value in `wrangler.toml` and run `npm run deploy`.

**KV write quota:** each read makes about 4 KV writes. The Workers free plan allows 1,000 writes a day, so it covers about 250 flyers a day. The $5/month paid plan removes that limit in practice.

## Test

```bash
npm test                                   # flyer reader + spend limits (fake API, nothing billed)
npx wrangler deploy --dry-run --outdir dist  # bundle check
```
