"""Search landing pages for "things to do in Boston":

    /things-to-do-boston/           this week's best picks plus an evergreen guide to the city
    /things-to-do-boston/<month>/   the best picks for the current month and the next two

Picks come from the Highlights page ranking (highlights_page.build_highlight_days): hand-picked
events first, then the strongest other listings. Month URLs carry no year so they keep their
links from one year to the next; the page title names the year. Month pages that fall out of
the window are deleted on the next build.
"""
import json
import os
import shutil
from datetime import date, datetime, timedelta
from html import escape

from highlights_page import PAGE_CSS, _pick_html, _run_html, build_highlight_days
from template import EASTERN, _main_hub_nav, build_seo_meta_tags, get_site_url

SLUG = "things-to-do-boston"
MONTHS_AHEAD = 3          # the current month and the next two
WEEK_PER_DAY = 8          # picks per day on the main guide
MONTH_PER_DAY = 10        # picks per day on a month page
MONTH_SLUGS = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]

# Evergreen guide: (heading, intro, [(name, link or "", one line)]). Links go to official sites or
# to our own guides. Only facts that hold year-round; dated things live in the picks above.
GUIDE = [
    ("Boston classics", "The first-visit list, and still worth it the tenth time.", [
        ("Walk the Freedom Trail", "https://www.thefreedomtrail.org/",
         "A 2.5-mile red line through downtown and the North End past 16 Revolutionary-era sites. Walking it is free."),
        ("Boston Common & the Public Garden", "",
         "America's oldest public park and the garden next door, with the Swan Boats in the warmer months."),
        ("The North End", "",
         "Boston's Italian neighborhood: bakeries, red-sauce dinners, the Paul Revere House and Old North Church."),
        ("Fenway Park", "https://www.mlb.com/redsox/ballpark/tours",
         "Red Sox games run spring through early fall; ballpark tours run year-round."),
        ("Faneuil Hall & Quincy Market", "", "Food hall, street performers and shopping by the waterfront."),
        ("Harvard Square & MIT", "../cambridge/",
         "Across the river in Cambridge: bookstores, Harvard Yard, the MIT campus and a busy music and comedy scene."),
    ]),
    ("Museums", "Most run free or discounted nights; our free events page lists them as they come up.", [
        ("Museum of Fine Arts", "https://www.mfa.org/", "One of the country's great encyclopedic art museums."),
        ("Isabella Stewart Gardner Museum", "https://www.gardnermuseum.org/",
         "A Venetian-style palazzo built around a flowering courtyard, just down the Fenway from the MFA."),
        ("Institute of Contemporary Art", "https://www.icaboston.org/", "Contemporary art on the Seaport waterfront."),
        ("Museum of Science", "https://www.mos.org/", "Hands-on science, a planetarium and an IMAX dome at the Charles River dam."),
        ("New England Aquarium", "https://www.neaq.org/", "The giant ocean tank, penguins and harbor seals on Central Wharf."),
        ("Boston Public Library", "https://www.bpl.org/", "The Copley Square central library is free to visit: Bates Hall, murals and a courtyard."),
    ]),
    ("Outdoors", "Green space without leaving the city.", [
        ("Arnold Arboretum", "https://arboretum.harvard.edu/", "Harvard's 281-acre tree collection in Jamaica Plain, free and open daily."),
        ("Charles River Esplanade", "", "Riverside paths for walking, running and sunsets along Back Bay."),
        ("Boston Harbor Islands", "https://www.bostonharborislands.org/", "Seasonal ferries to beaches, forts and campsites in the harbor."),
        ("Castle Island", "", "A loop walk around Fort Independence in South Boston, with planes landing overhead."),
        ("Minuteman Bikeway", "", "A rail trail from Alewife in Cambridge out through Arlington and Lexington."),
    ]),
]

GUIDE_LINKS = [
    ("../boston-events-today/", "Boston events today & tonight"),
    ("../boston-events-this-weekend/", "Things to do this weekend"),
    ("../free/", "Free events"),
    ("../music/", "Live music"),
    ("../comedy/", "Comedy"),
    ("../markets-festivals-boston/", "Markets & festivals"),
    ("../kids-family-events-boston/", "Kids & family"),
    ("../cambridge/", "Cambridge"),
    ("../somerville/", "Somerville"),
    ("../boston-event-highlights/", "Daily highlights"),
]

EXTRA_CSS = """
  .guide { margin-top: 40px; }
  .guide h2 { font-size: 22px; margin: 0 0 6px; }
  .guide > p { color: var(--muted); margin: 0 0 12px; }
  .guide-list { list-style: none; margin: 0 0 22px; padding: 0; background: var(--card);
    border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
  .guide-list li { padding: 11px 14px; border-top: 1px solid var(--border); }
  .guide-list li:first-child { border-top: 0; }
  .guide-list strong a { color: var(--fg); }
  .link-grid { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 0; padding: 0; list-style: none; }
  .link-grid a { display: inline-block; background: var(--card); border: 1px solid var(--border);
    border-radius: 999px; padding: 6px 12px; font-size: 13px; text-decoration: none; color: var(--fg); }
  .link-grid a:hover { border-color: var(--accent); color: var(--accent); }
  .more { margin: 10px 0 0; font-size: 14px; }
  .faq dt { font-weight: 650; margin-top: 14px; }
  .faq dd { margin: 4px 0 0; color: var(--muted); }
"""


def _month_starts(today, n=MONTHS_AHEAD):
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_days(first, today):
    nxt = date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)
    start = max(first, today)
    return [start + timedelta(days=i) for i in range((nxt - start).days)]


def _trim(picks, n):
    """The day's top n, hand picks first, shown in time order."""
    keep = sorted(picks, key=lambda p: not p["curated"])[:n]
    return sorted(keep, key=lambda p: (p["sort"], p["title"]))


def _day_sections(days, per_day, heading="h3"):
    out = []
    for day in days:
        picks = _trim(day["picks"], per_day)
        if not picks:
            continue
        d = day["date"]
        out.append(f'<section class="day"><{heading}><span class="day-name">{d.strftime("%A")}</span> '
                   f'{d.strftime("%B %-d")}</{heading}><ul class="picks">{"".join(_pick_html(p) for p in picks)}</ul></section>')
    return "".join(out)


def _item_list(days, per_day, limit=30):
    items = []
    for day in days:
        for p in _trim(day["picks"], per_day):
            if p["url"] and len(items) < limit:
                items.append({"@type": "ListItem", "position": len(items) + 1, "name": p["title"], "url": p["url"]})
    return {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": items}


def _page(site_url, path, title, description, h1, lede, body, ld, depth=1):
    meta = build_seo_meta_tags(site_url=site_url, title=f"{title} · Wicked Boston Events", description=description,
                               path=path, image_url=f"{site_url}/og-image.jpg?v=2")
    up = "../" * depth
    nav = _main_hub_nav(SLUG)
    if depth != 1:
        nav = nav.replace('href="../', f'href="{up}')
    ld_json = json.dumps(ld).replace("</", "<\\/")
    built = datetime.now(EASTERN).strftime("%b %-d, %-I:%M %p")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{meta}
<script type="application/ld+json">{ld_json}</script>
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<script>try{{if(localStorage.getItem('boston_events_theme')==='light')document.documentElement.setAttribute('data-theme','light')}}catch(e){{}}</script>
<style>
{PAGE_CSS}{EXTRA_CSS}
</style>
</head>
<body>
<header>
  <a class="logo" href="{up}">Wicked <span>Boston</span> Events</a>
{nav}
</header>
<main>
  <h1>{escape(h1)}</h1>
  <p class="lede">{lede}</p>
  {body}
</main>
<footer>Updated {escape(built)} from 300+ local calendars. Spot something we missed? Tell us on Instagram at @wickedbostonevents.</footer>
</body>
</html>
"""


def _guide_html():
    parts = []
    def item(name, url, line):
        if not url:
            head = escape(name)
        elif url.startswith(".."):
            head = f'<a href="{escape(url)}">{escape(name)}</a>'
        else:
            head = f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(name)}</a>'
        return f'<li><strong>{head}</strong><div class="pick-meta">{escape(line)}</div></li>'

    for heading, intro, rows in GUIDE:
        lis = "".join(item(*r) for r in rows)
        parts.append(f'<h2>{escape(heading)}</h2><p>{escape(intro)}</p><ul class="guide-list">{lis}</ul>')
    return "".join(parts)


def _links_html(links, prefix=""):
    return '<ul class="link-grid">' + "".join(
        f'<li><a href="{escape(prefix + href)}">{escape(label)}</a></li>' for href, label in links) + "</ul>"


def render_main_page(site_url, today, week_days, runs, months):
    path = f"{SLUG}/"
    title = "Things to Do in Boston This Week"
    n = sum(len(_trim(d["picks"], WEEK_PER_DAY)) for d in week_days)
    first, last = week_days[0]["date"], week_days[-1]["date"]
    span = f"{first.strftime('%b %-d')}–{last.strftime('%-d') if last.month == first.month else last.strftime('%b %-d')}"
    description = (f"The best things to do in Boston, Cambridge & Somerville this week ({span}): {n} picks "
                   "for concerts, comedy, free events and more, plus a guide to the city's classics, museums and parks.")
    lede = (f"The best of this week ({escape(span)}) in Boston, Cambridge &amp; Somerville, picked from 300+ local calendars "
            "and updated every few hours. <strong>✨ Editor's picks</strong> are hand-chosen with a note on why. "
            "Below the picks is our year-round guide to the city.")
    month_links = [(f"{m.strftime('%B').lower()}/", f"{m.strftime('%B %Y')}") for m in months]
    runs_html = ""
    if runs:
        runs_html = f'<section class="runs"><h2>Running this week</h2><ul class="run-list">{"".join(_run_html(x) for x in runs)}</ul></section>'
    body = (
        f'<h2>This week\'s best picks</h2>{_day_sections(week_days, WEEK_PER_DAY)}'
        f'<p class="more">More each day on the <a href="../boston-event-highlights/">Highlights page</a>, '
        f'and everything on the <a href="../">full calendar</a>.</p>{runs_html}'
        f'<section class="guide"><h2>Plan further ahead</h2><p>The best picks month by month.</p>{_links_html(month_links)}'
        f'<h2 style="margin-top:22px">Browse by day, place or kind</h2>{_links_html(GUIDE_LINKS)}</section>'
        f'<section class="guide">{_guide_html()}</section>'
        '<section class="guide faq"><h2>Common questions</h2><dl>'
        '<dt>What is there to do in Boston this weekend?</dt><dd>See <a href="../boston-events-this-weekend/">things to do this weekend</a> '
        'for every listing, or the picks above for the short list.</dd>'
        '<dt>What free things are there to do in Boston?</dt><dd>Walking the Freedom Trail, the Public Garden, the Boston Public Library '
        'and the Arnold Arboretum are always free. Free concerts, museum nights and festivals are on our <a href="../free/">free events page</a>.</dd>'
        '<dt>What is there to do in Boston tonight?</dt><dd><a href="../boston-events-today/">Boston events today &amp; tonight</a> '
        'lists everything still to come today, with times and prices.</dd>'
        '</dl></section>')
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "CollectionPage", "name": title, "description": description, "url": f"{site_url}/{path}",
             "isPartOf": {"@type": "WebSite", "name": "Wicked Boston Events", "url": f"{site_url}/"},
             "mainEntity": _item_list(week_days, WEEK_PER_DAY)},
            {"@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": "What free things are there to do in Boston?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Walking the Freedom Trail, the Public Garden, the Boston Public Library and the Arnold Arboretum are always free. Free concerts, museum nights and festivals are listed on the Wicked Boston Events free events page."}},
                {"@type": "Question", "name": "What is there to do in Boston this weekend?",
                 "acceptedAnswer": {"@type": "Answer", "text": "Wicked Boston Events lists every concert, comedy show, market and free event in Boston, Cambridge and Somerville this weekend, with a short list of the best picks each day."}},
            ]},
        ],
    }
    return _page(site_url, path, title, description, title, lede, body, ld)


def render_month_page(site_url, first, days, runs, months):
    month = first.strftime("%B")
    path = f"{SLUG}/{month.lower()}/"
    title = f"Things to Do in Boston in {month} {first.year}"
    n = sum(len(_trim(d["picks"], MONTH_PER_DAY)) for d in days)
    description = (f"The best things to do in Boston, Cambridge & Somerville in {month} {first.year}: {n} picks for concerts, "
                   "comedy, theater, markets and free events, day by day.")
    lede = (f"The best of {escape(month)} {first.year} in Boston, Cambridge &amp; Somerville, day by day, picked from 300+ local calendars. "
            "Later dates fill in as venues announce shows. <strong>✨ Editor's picks</strong> are hand-chosen with a note on why.")
    other = [(f"../{m.strftime('%B').lower()}/", m.strftime("%B %Y")) for m in months if m != first]
    runs_html = ""
    if runs:
        runs_html = f'<section class="runs"><h2>Running in {escape(month)}</h2><ul class="run-list">{"".join(_run_html(x) for x in runs)}</ul></section>'
    sections = _day_sections(days, MONTH_PER_DAY, heading="h2") or "<p>Nothing announced yet. Check back soon.</p>"
    body = (f'{sections}{runs_html}'
            f'<section class="guide"><h2>Other months</h2>{_links_html(other)}'
            f'<h2 style="margin-top:22px">More ways to browse</h2>'
            f'{_links_html([("../", "Things to do in Boston this week")] + [("../" + h, l) for h, l in GUIDE_LINKS])}</section>')
    ld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "description": description,
          "url": f"{site_url}/{path}", "isPartOf": {"@type": "WebSite", "name": "Wicked Boston Events", "url": f"{site_url}/"},
          "mainEntity": _item_list(days, MONTH_PER_DAY)}
    return _page(site_url, path, title, description, title, lede, body, ld, depth=2)


def _runs_between(runs, a, b):
    return [x for x in runs if x["to"] >= a and x["from"] <= b]


def guide_paths(today=None):
    """Site paths these pages are written to (for the sitemap)."""
    today = today or datetime.now(EASTERN).date()
    return [f"{SLUG}/"] + [f"{SLUG}/{m.strftime('%B').lower()}/" for m in _month_starts(today)]


def write_guide_pages(base_dir, site_url=None, today=None):
    site_url = (site_url or get_site_url()).rstrip("/")
    today = today or datetime.now(EASTERN).date()
    months = _month_starts(today)
    all_days = [d for m in months for d in _month_days(m, today)]
    days, runs = build_highlight_days(today, days=all_days)
    by_date = {d["date"]: d for d in days}

    root = os.path.join(base_dir, SLUG)
    os.makedirs(root, exist_ok=True)
    week = [by_date[today + timedelta(days=i)] for i in range(7) if today + timedelta(days=i) in by_date]
    html = render_main_page(site_url, today, week, _runs_between(runs, today, today + timedelta(days=6)), months)
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {SLUG}/index.html: {len(html):,} bytes")

    keep = set()
    for m in months:
        mdays = [by_date[d] for d in _month_days(m, today) if d in by_date]
        last = mdays[-1]["date"] if mdays else m
        html = render_month_page(site_url, m, mdays, _runs_between(runs, mdays[0]["date"] if mdays else m, last), months)
        slug = m.strftime("%B").lower()
        keep.add(slug)
        os.makedirs(os.path.join(root, slug), exist_ok=True)
        with open(os.path.join(root, slug, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"wrote {SLUG}/{slug}/index.html: {len(html):,} bytes")
    for slug in MONTH_SLUGS:  # months that left the window
        if slug not in keep and os.path.isdir(os.path.join(root, slug)):
            shutil.rmtree(os.path.join(root, slug))
