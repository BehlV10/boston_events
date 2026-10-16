# Boston Events — Community Submission Cloudflare Worker

This lightweight serverless function receives community event submissions from the website UI, verifies the anti-bot honeypot and optional Turnstile CAPTCHA, and triggers the GitHub Actions workflow to add the event and publish the site.

## Setup in 2 Minutes (100% Free)

1. **Log in to Cloudflare**: Go to [dash.cloudflare.com](https://dash.cloudflare.com/) and click **Workers & Pages** → **Create application** → **Create Worker**.
2. **Name the Worker**: e.g., `boston-events-submissions`.
3. **Paste the Code**: Click **Edit Code** and replace the contents with [`worker.js`](worker.js). Click **Deploy**.
4. **Set Environment Variables**:
   In your Worker's dashboard, go to **Settings** → **Variables and Secrets**:
   * `GITHUB_REPO`: `BehlV10/boston_events`
   * `GITHUB_TOKEN`: A GitHub Personal Access Token (PAT) with `repo` or `actions:write` scope (generate one at [github.com/settings/tokens](https://github.com/settings/tokens)).
   * *(Optional)* `TURNSTILE_SECRET_KEY`: If you want Cloudflare Turnstile anti-bot verification.
5. **Add to Website**:
   Copy your Worker URL (e.g. `https://boston-events-submissions.your-subdomain.workers.dev`).
   In [`index.html`](../index.html) or [`template.py`](../template.py), you can set:
   ```html
   <script>
     window.EVENT_SUBMISSION_ENDPOINT = "https://boston-events-submissions.your-subdomain.workers.dev";
   </script>
   ```

Even without the worker configured yet, submissions immediately appear for the user who submitted them via browser storage!
