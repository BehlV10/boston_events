# My Schedule short links

Turns a shared schedule into a link like `wickedbostonevents.com/s/x7Kq2pA` and fills in its link
preview. Each schedule is deleted a day after its last event, and events are dropped from the page
24 hours after they start. Until this is deployed, or whenever it's unavailable, the Share button
gives the long link instead.

## Deploy

The store is already set up, so after changing the Worker:

```bash
cd schedule-worker
npx wrangler login
npx wrangler deploy
```

No secrets are needed. Cloudflare's free tier allows 1,000 new links a day.

## Test

```bash
node --test schedule-worker/worker.test.mjs
```
