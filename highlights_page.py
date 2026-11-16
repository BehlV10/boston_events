"""The public highlights page (/boston-event-highlights/): the best few events each day.

Picks come from the same ranking as the Reddit roundups (scripts/generate_weekday_reddit_roundup.py,
mode="range"): every hand-written highlights.json pick with its note, then the strongest other
listings per city. The page carries MAX_DAYS days; a date picker shows DEFAULT_DAYS by default
and never more than MAX_DAYS. Hidden days are in the HTML too, so search engines see them all.
"""
import importlib.util
import json
import os
from datetime import datetime, timedelta
from html import escape

from template import EASTERN, _main_hub_nav, build_seo_meta_tags, get_site_url

ROOT = os.path.dirname(os.path.abspath(__file__))
SLUG = "boston-event-highlights"
DEFAULT_DAYS = 14
MAX_DAYS = 21
CITY_LABELS = {"boston": "Boston", "cambridge": "Cambridge", "somerville": "Somerville"}
TITLE = "Boston Event Highlights: The Best Things to Do Each Day"
DESCRIPTION = ("A short, hand-picked list of the best concerts, comedy, film, markets and free events "
               "in Boston, Cambridge & Somerville for each of the next three weeks, with a line on why each is worth going to.")


def _roundup():
    spec = importlib.util.spec_from_file_location(
        "generate_weekday_reddit_roundup", os.path.join(ROOT, "scripts", "generate_weekday_reddit_roundup.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _safe_url(u):
    return u if isinstance(u, str) and u.startswith(("https://", "http://")) else ""


def build_highlight_days(today=None):
    """[{"date": date, "picks": [row, ...]}, ...] for MAX_DAYS days from today, plus run rows.
    A row: title, url, venue, time, sort, price, area, city, note, curated."""
    r = _roundup()
    today = today or datetime.now(EASTERN).date()
    days = [today + timedelta(days=i) for i in range(MAX_DAYS)]
    res = r.build_roundup("range", days=days, picks_only=True)

    def row(e):
        hl = e.get("_highlight") or {}
        t = e["_time"]
        return {
            "title": r._clean_title(e["name"]),
            "url": _safe_url(r._clean_url(e.get("url") or "")),
            "venue": r._city_venue(e),
            "time": r._time(e),
            "sort": t.strftime("%H:%M") if r._time(e) else "00:00",
            "price": r._price(e),
            "area": r._area(e),
            "city": e.get("_city") or "boston",
            "note": r._blurb(e, res["boilerplate"]),
            "curated": bool(hl),
        }

    out = []
    for d in days:
        picks = [row(e) for c in CITY_LABELS for e in res["days"][d].get(c, [])]
        picks.sort(key=lambda p: (p["sort"], not p["curated"], p["title"]))
        out.append({"date": d, "picks": picks})

    runs = []
    for evs in res["runs"].values():
        evs = sorted(evs, key=lambda e: e["_time"])
        first = row(evs[0])
        first["from"] = evs[0]["_time"].date()
        first["to"] = evs[-1]["_time"].date()
        first["price"] = next((r._price(x) for x in evs if r._price(x)), "")
        runs.append(first)
    runs.sort(key=lambda x: (x["from"], x["title"]))
    return out, runs


def _pick_html(p):
    title = escape(p["title"])
    head = f'<a href="{escape(p["url"])}" target="_blank" rel="noopener">{title}</a>' if p["url"] else title
    meta = " · ".join(escape(x) for x in (p["venue"], p["price"], p["area"]) if x)
    badge = '<span class="pick-badge" title="Hand-picked by the editor">✨ Pick</span>' if p["curated"] else ""
    note = f'<p class="pick-note">{escape(p["note"])}</p>' if p["note"] else ""
    when = escape(p["time"]) if p["time"] else "All day"
    return (f'<li class="pick" data-city="{p["city"]}" data-curated="{int(p["curated"])}">'
            f'<span class="pick-time">{when}</span>'
            f'<div class="pick-body"><div class="pick-title">{head}{badge}</div>'
            f'<div class="pick-meta">{meta}</div>{note}</div></li>')


def render_highlights_page(site_url=None, today=None, days=None, runs=None):
    site_url = (site_url or get_site_url()).rstrip("/")
    today = today or datetime.now(EASTERN).date()
    if days is None:
        days, runs = build_highlight_days(today)
    runs = runs or []
    meta = build_seo_meta_tags(site_url=site_url, title=f"{TITLE} · Wicked Boston Events",
                               description=DESCRIPTION, path=f"{SLUG}/", image_url=f"{site_url}/og-image.jpg?v=2")

    sections = []
    for i, day in enumerate(days):
        d = day["date"]
        items = "".join(_pick_html(p) for p in day["picks"]) or '<li class="pick-empty">Nothing picked yet for this day.</li>'
        curated = sum(p["curated"] for p in day["picks"])
        hidden = " hidden" if i >= DEFAULT_DAYS else ""
        sections.append(
            f'<section class="day" data-date="{d.isoformat()}"{hidden}>'
            f'<h2><span class="day-name">{d.strftime("%A")}</span> {d.strftime("%B %-d")}'
            f'<span class="day-count">{len(day["picks"])} picks{f" · {curated} ✨" if curated else ""}</span></h2>'
            f'<ul class="picks">{items}</ul></section>')

    run_items = "".join(_run_html(x) for x in runs)
    runs_html = (f'<section class="runs" id="runs"><h2>Running through these dates</h2><ul class="run-list">{run_items}</ul></section>'
                 if runs else "")

    first, last = days[0]["date"], days[-1]["date"]
    default_to = days[min(DEFAULT_DAYS, len(days)) - 1]["date"]
    total = sum(len(d["picks"]) for d in days[:DEFAULT_DAYS])
    ld = {
        "@context": "https://schema.org", "@type": "CollectionPage", "name": TITLE, "description": DESCRIPTION,
        "url": f"{site_url}/{SLUG}/",
        "isPartOf": {"@type": "WebSite", "name": "Wicked Boston Events", "url": f"{site_url}/"},
    }
    ld_json = json.dumps(ld).replace("</", "<\\/")
    nav = _main_hub_nav(SLUG)
    built = datetime.now(EASTERN).strftime("%b %-d, %-I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(TITLE)} · Wicked Boston Events</title>
{meta}
<script type="application/ld+json">{ld_json}</script>
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<script>try{{if(localStorage.getItem('boston_events_theme')==='light')document.documentElement.setAttribute('data-theme','light')}}catch(e){{}}</script>
<style>
  :root {{
    --bg: #0c0e14; --card: #151822; --card-2: #1c202e; --fg: #eef1f8; --muted: #8e96a8;
    --accent: #5d9bff; --border: rgba(255,255,255,0.08); --gold: #f5c35b; --gold-bg: rgba(245,195,91,0.12);
  }}
  [data-theme="light"] {{
    --bg: #f5f6fa; --card: #ffffff; --card-2: #eef1f7; --fg: #10131c; --muted: #5a6275;
    --accent: #2563eb; --border: #dfe3ec; --gold: #92400e; --gold-bg: #fdf3d7;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg); line-height: 1.5;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  a {{ color: var(--accent); }}
  header {{ background: var(--card); border-bottom: 1px solid var(--border); padding: 14px 20px;
    display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
  .logo {{ font-size: 16px; font-weight: 800; color: var(--fg); text-decoration: none; }}
  .logo span {{ color: var(--accent); }}
  .hub-nav {{ display: flex; gap: 12px; font-size: 13px; flex-wrap: wrap; }}
  .hub-nav a {{ color: var(--muted); text-decoration: none; }}
  .hub-nav a:hover, .hub-nav a.active {{ color: var(--accent); font-weight: 600; }}
  main {{ max-width: 860px; margin: 0 auto; padding: 28px 16px 60px; }}
  h1 {{ font-size: clamp(26px, 5vw, 36px); line-height: 1.15; margin: 0 0 8px; letter-spacing: -0.01em; }}
  .lede {{ color: var(--muted); margin: 0 0 22px; max-width: 640px; }}
  .controls {{ position: sticky; top: 0; z-index: 5; background: var(--bg); padding: 12px 0 14px;
    border-bottom: 1px solid var(--border); margin-bottom: 8px; }}
  .range {{ display: flex; gap: 10px; align-items: end; flex-wrap: wrap; }}
  .range label {{ display: flex; flex-direction: column; font-size: 12px; color: var(--muted); gap: 4px; }}
  .range input[type=date] {{ background: var(--card); color: var(--fg); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 9px; font: inherit; font-size: 14px; color-scheme: dark; }}
  [data-theme="light"] .range input[type=date] {{ color-scheme: light; }}
  .chips {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }}
  .chip {{ background: var(--card); color: var(--fg); border: 1px solid var(--border); border-radius: 999px;
    padding: 5px 12px; font: inherit; font-size: 13px; cursor: pointer; }}
  .chip[aria-pressed="true"] {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
  .chip-sep {{ width: 1px; background: var(--border); margin: 2px 4px; }}
  .status {{ font-size: 13px; color: var(--muted); margin-top: 10px; }}
  .day {{ margin-top: 26px; }}
  .day h2 {{ font-size: 19px; margin: 0 0 10px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }}
  .day-name {{ color: var(--accent); }}
  .day-count {{ font-size: 12px; font-weight: 500; color: var(--muted); margin-left: auto; }}
  .picks, .run-list {{ list-style: none; margin: 0; padding: 0; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }}
  .pick {{ display: grid; grid-template-columns: 70px 1fr; gap: 10px; padding: 11px 14px; border-top: 1px solid var(--border); }}
  .pick:first-child {{ border-top: 0; }}
  .pick[data-curated="1"] {{ background: linear-gradient(90deg, var(--gold-bg), transparent 60%); }}
  .pick-time {{ font-size: 13px; font-weight: 600; color: var(--muted); padding-top: 1px; white-space: nowrap; }}
  .pick-title {{ font-weight: 650; overflow-wrap: anywhere; }}
  .pick-title a {{ color: var(--fg); text-decoration: none; }}
  .pick-title a:hover {{ color: var(--accent); text-decoration: underline; }}
  .pick-badge {{ display: inline-block; margin-left: 8px; font-size: 11px; font-weight: 600; color: var(--gold);
    border: 1px solid currentColor; border-radius: 999px; padding: 0 7px; vertical-align: 2px; }}
  .pick-meta {{ font-size: 13px; color: var(--muted); overflow-wrap: anywhere; }}
  .pick-note {{ margin: 4px 0 0; font-size: 14px; }}
  .pick-empty {{ padding: 12px 14px; color: var(--muted); }}
  .runs {{ margin-top: 34px; }}
  .runs h2 {{ font-size: 19px; margin: 0 0 10px; }}
  .run {{ padding: 11px 14px; border-top: 1px solid var(--border); }}
  .run:first-child {{ border-top: 0; }}
  .empty-range {{ margin-top: 26px; color: var(--muted); }}
  footer {{ max-width: 860px; margin: 0 auto; padding: 0 16px 40px; font-size: 13px; color: var(--muted); }}
  @media (max-width: 520px) {{
    .pick {{ grid-template-columns: 1fr; gap: 2px; }}
    .controls {{ position: static; }}
    header {{ padding: 12px 16px; }}
  }}
</style>
</head>
<body>
<header>
  <a class="logo" href="../">Wicked <span>Boston</span> Events</a>
{nav}
</header>
<main>
  <h1>Boston Event Highlights</h1>
  <p class="lede">The best few things to do each day in Boston, Cambridge &amp; Somerville. Picks marked ✨ are
  hand-chosen with a note on why they're worth it; the rest are the strongest listings from 300+ local calendars.
  For everything, see the <a href="../">full calendar</a>.</p>

  <div class="controls" role="region" aria-label="Choose dates">
    <div class="range">
      <label>From <input type="date" id="from" value="{first.isoformat()}" min="{first.isoformat()}" max="{last.isoformat()}"></label>
      <label>To <input type="date" id="to" value="{default_to.isoformat()}" min="{first.isoformat()}" max="{last.isoformat()}"></label>
    </div>
    <div class="chips" id="presets">
      <button class="chip" data-preset="weekend" aria-pressed="false">This weekend</button>
      <button class="chip" data-preset="7" aria-pressed="false">Next 7 days</button>
      <button class="chip" data-preset="14" aria-pressed="true">Next 2 weeks</button>
      <button class="chip" data-preset="21" aria-pressed="false">Next 3 weeks</button>
      <span class="chip-sep" aria-hidden="true"></span>
      <button class="chip" data-city="all" aria-pressed="true">All cities</button>
      <button class="chip" data-city="boston" aria-pressed="false">Boston</button>
      <button class="chip" data-city="cambridge" aria-pressed="false">Cambridge</button>
      <button class="chip" data-city="somerville" aria-pressed="false">Somerville</button>
      <span class="chip-sep" aria-hidden="true"></span>
      <button class="chip" id="curated" aria-pressed="false">✨ Picks only</button>
    </div>
    <div class="status" id="status" aria-live="polite">{total} picks over {min(DEFAULT_DAYS, len(days))} days</div>
  </div>

  {"".join(sections)}
  <p class="empty-range" id="empty" hidden>Nothing matches these filters. Try more dates or all cities.</p>
  {runs_html}
</main>
<footer>Updated {escape(built)}. Ranges up to {MAX_DAYS} days. Spot something we missed? Tell us on Instagram at @wickedbostonevents.</footer>
<script>
(function () {{
  var MAX = {MAX_DAYS}, DAY = 864e5;
  var from = document.getElementById('from'), to = document.getElementById('to');
  var days = [].slice.call(document.querySelectorAll('.day'));
  var runs = [].slice.call(document.querySelectorAll('.run'));
  var status = document.getElementById('status'), empty = document.getElementById('empty');
  var city = 'all', curatedOnly = false;
  function iso(d) {{ return d.toISOString().slice(0, 10); }}
  function parse(s) {{ return new Date(s + 'T12:00:00Z'); }}
  function add(s, n) {{ return iso(new Date(parse(s).getTime() + n * DAY)); }}
  // The page is static: start from today's Boston date, not the build date
  var today;
  try {{ today = new Intl.DateTimeFormat('en-CA', {{timeZone: 'America/New_York'}}).format(new Date()); }} catch (e) {{ today = from.min; }}
  if (today > from.min && today <= from.max) {{ from.min = to.min = today; }}
  var lo = from.min, hi = from.max;
  function clamp(s) {{ return s < lo ? lo : (s > hi ? hi : s); }}
  function setRange(a, b) {{
    a = clamp(a); b = clamp(b);
    if (b < a) b = a;
    if (b > add(a, MAX - 1)) b = add(a, MAX - 1);
    from.value = a; to.value = b; apply();
  }}
  function press(sel, el) {{ document.querySelectorAll(sel).forEach(function (b) {{ b.setAttribute('aria-pressed', b === el ? 'true' : 'false'); }}); }}
  function apply() {{
    var a = from.value, b = to.value, shown = 0, nd = 0;
    days.forEach(function (sec) {{
      var d = sec.dataset.date, inRange = d >= a && d <= b, n = 0, c = 0;
      sec.querySelectorAll('.pick').forEach(function (li) {{
        var ok = (city === 'all' || li.dataset.city === city) && (!curatedOnly || li.dataset.curated === '1');
        li.hidden = !ok; if (ok) {{ n++; if (li.dataset.curated === '1') c++; }}
      }});
      var dc = sec.querySelector('.day-count');
      if (dc) dc.textContent = n + ' pick' + (n === 1 ? '' : 's') + (c ? ' · ' + c + ' ✨' : '');
      sec.hidden = !inRange || n === 0;
      if (!sec.hidden) {{ shown += n; nd++; }}
    }});
    runs.forEach(function (li) {{
      li.hidden = li.dataset.to < a || li.dataset.from > b || (city !== 'all' && li.dataset.city !== city);
    }});
    var rs = document.getElementById('runs');
    if (rs) rs.hidden = runs.every(function (li) {{ return li.hidden; }});
    empty.hidden = shown > 0;
    status.textContent = shown + ' picks over ' + nd + ' day' + (nd === 1 ? '' : 's');
    var h = 'from=' + a + '&to=' + b + (city !== 'all' ? '&city=' + city : '') + (curatedOnly ? '&picks=1' : '');
    try {{ history.replaceState(null, '', '#' + h); }} catch (e) {{}}
  }}
  document.getElementById('presets').addEventListener('click', function (ev) {{
    var b = ev.target.closest('button'); if (!b) return;
    if (b.dataset.preset) {{
      press('[data-preset]', b);
      if (b.dataset.preset === 'weekend') {{
        var wd = parse(lo).getUTCDay(), fri = add(lo, wd === 0 ? -2 : (wd === 6 ? -1 : 5 - wd));
        setRange(fri < lo ? lo : fri, add(fri, 2));
      }} else setRange(lo, add(lo, +b.dataset.preset - 1));
    }} else if (b.dataset.city) {{ city = b.dataset.city; press('[data-city]', b); apply(); }}
    else if (b.id === 'curated') {{ curatedOnly = !curatedOnly; b.setAttribute('aria-pressed', String(curatedOnly)); apply(); }}
  }});
  function manual() {{ press('[data-preset]', null); setRange(from.value || lo, to.value || from.value || lo); }}
  from.addEventListener('change', manual); to.addEventListener('change', manual);
  var q = {{}};
  location.hash.slice(1).split('&').forEach(function (kv) {{ var p = kv.split('='); if (p[0]) q[p[0]] = decodeURIComponent(p[1] || ''); }});
  if (q.city && /^(boston|cambridge|somerville)$/.test(q.city)) {{ city = q.city; press('[data-city]', document.querySelector('[data-city="' + city + '"]')); }}
  if (q.picks === '1') {{ curatedOnly = true; document.getElementById('curated').setAttribute('aria-pressed', 'true'); }}
  if (q.from || q.to) {{ press('[data-preset]', null); setRange(q.from || lo, q.to || add(q.from || lo, {DEFAULT_DAYS - 1})); }}
  else setRange(lo, add(lo, {DEFAULT_DAYS - 1}));
}})();
</script>
</body>
</html>
"""


def _run_html(x):
    title = escape(x["title"])
    head = f'<a href="{escape(x["url"])}" target="_blank" rel="noopener">{title}</a>' if x["url"] else title
    meta = " · ".join(escape(s) for s in (x["venue"], _run_span(x), x["price"]) if s)
    note = f'<p class="pick-note">{escape(x["note"])}</p>' if x["note"] else ""
    return (f'<li class="run" data-from="{x["from"].isoformat()}" data-to="{x["to"].isoformat()}" data-city="{x["city"]}">'
            f'<div class="pick-title">{head}</div><div class="pick-meta">{meta}</div>{note}</li>')


def _run_span(x):
    a, b = x["from"], x["to"]
    if a == b:
        return a.strftime("%a %b %-d")
    return f"{a.strftime('%b %-d')} – {b.strftime('%b %-d') if b.month != a.month else b.strftime('%-d')}"


def write_highlights_page(base_dir, site_url=None):
    html = render_highlights_page(site_url)
    d = os.path.join(base_dir, SLUG)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {SLUG}/index.html: {len(html):,} bytes")
    return html
