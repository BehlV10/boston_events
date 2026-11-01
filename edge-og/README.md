# Dynamic OpenGraph (OG) Card Generator on Cloudflare Workers

This serverless edge worker auto-generates customized social preview cards on the fly whenever a link is shared on iMessage, Slack, Discord, Twitter/X, or Facebook.

### Deploy in 30 Seconds

1. Make sure you have Node.js / npm installed:
   ```bash
   cd edge-og
   npx wrangler login
   npx wrangler deploy
   ```
2. Your worker will be live at `https://wicked-boston-events-og.<your-subdomain>.workers.dev/og`.

### Example Query

```
https://wicked-boston-events-og.<your-subdomain>.workers.dev/og?title=Beach+Bunny+Live&venue=The+Sinclair&city=Cambridge&date=Tonight+8:00+PM&badge=Live+Music
```
Returns a crisp 1200x630 branded SVG card cached at Cloudflare edge with global sub-10ms delivery.
