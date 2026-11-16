# Boston Events — Submission Worker

A Cloudflare Worker behind the site's **Add to Boston Events** form. It:

- **`POST /` (event or venue submission):** checks the honeypot and optional Turnstile CAPTCHA, then triggers the `community-event.yml` GitHub Action, which adds the event and republishes the site.
- **`POST /extract-flyer`:** reads an uploaded flyer image with Claude Haiku 5.5 (`claude-haiku-5-5`) and returns the form fields for the visitor to check before publishing. Each read costs a fraction of a cent.
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
npx wrangler secret put ANTHROPIC_API_KEY   # from console.anthropic.com; enables flyer reading
# optional: npx wrangler secret put TURNSTILE_SECRET_KEY

npm run deploy
```

Then connect the site to the worker:

1. In the GitHub repo, go to **Settings → Secrets and variables → Actions → Variables**.
2. Add `EVENT_SUBMISSION_ENDPOINT` set to the worker URL that `npm run deploy` printed, e.g. `https://boston-events-submissions.<you>.workers.dev`.
3. Run the **Scrape events and deploy site** workflow, or wait for the next build.

The flyer upload box only appears on the site once that variable is set.

For the automatic scraper PRs, also enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**.

## Limits and safety

- **Origins:** flyer reads are only accepted from the site's own origins (`ALLOWED_ORIGINS` in `wrangler.toml`).
- **Daily caps:** 15 reads per IP and 400 in total per day (`FLYER_DAILY_LIMIT_*`), counted in the `FLYER_LIMITS` KV namespace. Without that namespace or an API key, the endpoint returns 503 and the form still works by hand.
- **Turnstile:** if `TURNSTILE_SECRET_KEY` is set, flyer reads require a Turnstile token. The site doesn't render the widget yet, so only set this secret after adding the widget.
- **Model output:** the model's output is constrained to a fixed schema. Dates, times and URLs are re-validated in the worker, and the visitor reviews everything before it's submitted.

## Test

```bash
npm test                                   # unit tests for the flyer reader (no API calls)
npx wrangler deploy --dry-run --outdir dist  # bundle check
```
