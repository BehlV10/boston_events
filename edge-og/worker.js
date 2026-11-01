/**
 * Cloudflare Worker for Dynamic OpenGraph (OG) Image Generation.
 *
 * Deploy with Wrangler:
 *   cd edge-og && npx wrangler deploy
 *
 * Usage:
 *   https://<worker-subdomain>.workers.dev/og?title=Event+Title&venue=The+Sinclair&city=Cambridge&date=Nov+7&badge=Live+Music
 *
 * Generates an optimized 1200x630 vector SVG preview card on the edge with zero cold start.
 */

export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return new Response("OK", { status: 200 });
    }

    if (url.pathname !== "/og" && url.pathname !== "/api/og" && url.pathname !== "/") {
      return new Response("Not found", { status: 404 });
    }

    // Extract query parameters
    const title = (url.searchParams.get("title") || "Live Greater Boston Events").slice(0, 75);
    const venue = (url.searchParams.get("venue") || "Boston & Cambridge Stages").slice(0, 50);
    const city = (url.searchParams.get("city") || "Boston, MA").slice(0, 30);
    const date = (url.searchParams.get("date") || "Live Calendar").slice(0, 35);
    const badge = (url.searchParams.get("badge") || "VERIFIED EVENT").slice(0, 25).toUpperCase();
    const count = url.searchParams.get("count");

    // Escape helper for SVG safety
    const esc = (str) =>
      String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&apos;");

    // Split title into two lines if long
    let line1 = title;
    let line2 = "";
    if (title.length > 36) {
      const words = title.split(" ");
      let cur = "";
      for (const w of words) {
        if ((cur + " " + w).trim().length <= 36) {
          cur = (cur + " " + w).trim();
        } else {
          if (!line1 || line1 === title) line1 = cur;
          line2 = (line2 + " " + w).trim();
        }
      }
    }

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630">
  <defs>
    <linearGradient id="top-bar" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="33%" stop-color="#06b6d4" />
      <stop offset="66%" stop-color="#6366f1" />
      <stop offset="100%" stop-color="#a855f7" />
    </linearGradient>
    <radialGradient id="glow-right" cx="85%" cy="20%" r="50%">
      <stop offset="0%" stop-color="#1e3a5f" stop-opacity="0.45" />
      <stop offset="100%" stop-color="#0b0f17" stop-opacity="0" />
    </radialGradient>
    <radialGradient id="glow-left" cx="15%" cy="85%" r="50%">
      <stop offset="0%" stop-color="#132338" stop-opacity="0.4" />
      <stop offset="100%" stop-color="#0b0f17" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- Background -->
  <rect width="1200" height="630" fill="#0b0f17" />
  <rect width="1200" height="630" fill="url(#glow-right)" />
  <rect width="1200" height="630" fill="url(#glow-left)" />

  <!-- Top accent gradient strip -->
  <rect x="0" y="0" width="1200" height="8" fill="url(#top-bar)" />

  <!-- Outer Card Frame -->
  <rect x="40" y="36" width="1120" height="558" rx="24" fill="none" stroke="#1e293b" stroke-width="2" />

  <!-- Pill Badge: Category/Status -->
  <g transform="translate(80, 78)">
    <rect width="210" height="38" rx="8" fill="#064e3b" stroke="#10b981" stroke-width="1.5" />
    <circle cx="20" cy="19" r="5" fill="#34d399" />
    <text x="34" y="25" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="16" font-weight="700" fill="#34d399" letter-spacing="1.2">${esc(badge)}</text>
  </g>

  ${count ? `
  <!-- Count Pill -->
  <g transform="translate(305, 78)">
    <rect width="160" height="38" rx="8" fill="#1e293b" />
    <text x="80" y="24" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="15" font-weight="700" fill="#94a3b8" text-anchor="middle">${esc(count)} SHOWS</text>
  </g>` : ""}

  <!-- Date / Time Line -->
  <g transform="translate(80, 160)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="22" font-weight="700" fill="#38bdf8" letter-spacing="0.8">📅 ${esc(date)}</text>
  </g>

  <!-- Main Headline Title (Wrapped) -->
  <g transform="translate(80, 230)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="46" font-weight="900" fill="#ffffff" letter-spacing="-0.5">${esc(line1)}</text>
    ${line2 ? `<text y="62" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="46" font-weight="900" fill="#ffffff" letter-spacing="-0.5">${esc(line2)}</text>` : ""}
  </g>

  <!-- Venue & Neighborhood Info -->
  <g transform="translate(80, ${line2 ? 370 : 320})">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="24" font-weight="500" fill="#94a3b8">📍 ${esc(venue)} · <tspan fill="#e2e8f0" font-weight="700">${esc(city)}</tspan></text>
  </g>

  <!-- Bottom Divider -->
  <line x1="80" y1="495" x2="1120" y2="495" stroke="#1e293b" stroke-width="1.5" />

  <!-- Footer Branding -->
  <g transform="translate(80, 538)">
    <text font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="800" fill="#f8fafc">WICKED BOSTON EVENTS</text>
    <text x="270" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" fill="#64748b">·</text>
    <text x="290" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="700" fill="#10b981">OFFICIAL BOX OFFICE LINKS</text>
    <text x="590" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" fill="#64748b">·</text>
    <text x="610" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="18" font-weight="600" fill="#94a3b8">ZERO TICKET FEES</text>
  </g>
</svg>`;

    return new Response(svg, {
      status: 200,
      headers: {
        "Content-Type": "image/svg+xml",
        "Cache-Control": "public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400",
      },
    });
  },
};
