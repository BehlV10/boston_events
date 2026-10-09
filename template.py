"""Boston Events — HTML rendering and template logic."""

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from scrapers import (
    EASTERN,
    CATEGORY_BUCKETS,
    CATEGORY_STYLES,
    DEAL_LINKS,
    STATIC_LINKS,
    category_bucket,
    fetch_boston_weather,
    fetch_luckyseat_boston,
)


CITY_RULES = [
    ("somerville", (
        "aeronaut", "crystal ballroom", "somerville theatre", "somerville theater",
        "somerville, ma", "(somerville)", ", somerville",
        "davis square", "assembly row", "union square, somerville",
        "the burren", "burren", "mccarthy's toad", "mccarthys toad", "remnant somerville",
        "comedy studio", "bow market", "union square",
    )),
    ("cambridge", (
        "mit ", "m.i.t", "harvard square", "harvard book", "porter square", "sinclair",
        "brattle", "cambridge, ma", "(cambridge)", ", cambridge",
        "kendall", "central square", "inman square", "cantab",
        "havetodance", "have to dance", "ywca cambridge",
        "middle east", "sonia", "regattabar", "arrow street",
        "harvard museum of natural history", "hmnh",
        "lovestruck", "lovestruck books",
        "havana club",
        "lamplighter", "roxy's arcade", "roxys arcade",
        "venture café", "venture cafe", "cic cambridge",
        "middle east", "phoenix landing", "manray", "man ray", "prospect st",
        "regattabar", "lilypad", "inman square",
    )),
    ("boston", (
        "city winery", "royale", "wilbur", "ica boston", "gardner", "boston public library",
        "laugh boston", "big night live", "house of blues", "paradise rock", "orpheum",
        "td garden", "mgm music hall", "citizens house of blues", "fenway", "back bay",
        "downtown crossing", "seaport", "boston, ma", "(boston)", ", boston",
        "boston common", "trident booksellers", "mfa", "museum of fine arts",
        "brookline booksmith",
        "loretta", "versus boston", "opera house", "symphony hall", "brighton music hall",
        "boch center", "wang theatre", "boston conservatory", "the beehive", "play boston",
        "petit robert", "the grand",
        "roxbury", "jamaica plain", "south end", "fort point", "south boston",
        "allston", "brighton", "dorchester", "mattapan", "roslindale", "west roxbury",
        "long live", "sam adams", "trillium", "castle island",
        "copley", "sowa", "newbury", "beehive", "wally",
        "the anchor", "anchor boston", "charlestown navy",
    )),
]

CITY_LABELS = {
    "boston": "Boston",
    "cambridge": "Cambridge",
    "somerville": "Somerville",
    "other": "Other",
}


def _event_city(venue, source):
    v = (venue or "").strip().lower()
    hay = v if v else (source or "").strip().lower()
    if hay == "boston":
        return "boston"
    for city, needles in CITY_RULES:
        for n in needles:
            if n in hay:
                return city
    return "other"


def _maps_link(venue, city):
    if not venue:
        return ""
    label = CITY_LABELS.get(city)
    query = venue if city == "other" or not label else f"{venue}, {label}, MA"
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


def _is_event_free(e):
    price = (e.get("price") or "").strip().lower()
    if any(k in price for k in ["free", "$0", "no cover"]):
        return True
    name = (e.get("name") or "").lower()
    desc = (e.get("description") or "").lower()
    source = (e.get("_source_venue") or e.get("venue") or "").lower()
    if any(k in source for k in ["library", "farmers market", "open market"]):
        return True
    if any(k in name for k in ["farmers market", "free outdoor", "open mic", "drop-in art", "board games", "fun run"]):
        return True
    if any(k in desc for k in ["free dance class", "free event", "free admission", "free and open to the public", "no cover"]):
        return True
    return False


def _build_gcal_link(e, title, venue, city):
    raw_date = e.get("date")
    if not raw_date:
        return None
    try:
        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        start_str = dt.strftime("%Y%m%dT%H%M%SZ")
        end_dt = dt + timedelta(hours=2)
        end_str = end_dt.strftime("%Y%m%dT%H%M%SZ")
    except (ValueError, TypeError, AttributeError):
        return None
    loc = f"{venue}, {city.capitalize() if city else 'Boston'}, MA" if venue else "Boston, MA"
    details = f"Details & Tickets: {e.get('url') or ''}\n\nDiscovered on Boston Events"
    return f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(title)}&dates={start_str}/{end_str}&details={quote(details)}&location={quote(loc)}"



BANNER_SVG = """
<svg viewBox="0 0 1200 240" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"   stop-color="#1b1348"/>
      <stop offset="30%"  stop-color="#5a1a6b"/>
      <stop offset="60%"  stop-color="#e8396a"/>
      <stop offset="85%"  stop-color="#ff9058"/>
      <stop offset="100%" stop-color="#ffd66b"/>
    </linearGradient>
    <radialGradient id="moon" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0%" stop-color="#fff4d6"/>
      <stop offset="100%" stop-color="#fff4d6" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1c3a6e"/>
      <stop offset="100%" stop-color="#0a1a35"/>
    </linearGradient>
    <linearGradient id="citgo" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#ff3b4a"/>
      <stop offset="50%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#1f6dff"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="240" fill="url(#sky)"/>
  <!-- stars -->
  <g fill="#ffffff" opacity="0.85">
    <circle cx="80" cy="28" r="1.2"/><circle cx="150" cy="52" r="1"/><circle cx="230" cy="22" r="1.3"/>
    <circle cx="310" cy="60" r="1"/><circle cx="420" cy="18" r="1.2"/><circle cx="540" cy="40" r="1"/>
    <circle cx="710" cy="25" r="1.3"/><circle cx="820" cy="55" r="1"/><circle cx="900" cy="18" r="1.2"/>
    <circle cx="1050" cy="48" r="1"/><circle cx="1130" cy="30" r="1.3"/>
  </g>
  <!-- moon -->
  <circle cx="1060" cy="78" r="46" fill="url(#moon)"/>
  <circle cx="1060" cy="78" r="24" fill="#fff4d6"/>

  <!-- Zakim Bridge (left) — pylons + cable stays -->
  <g stroke="#ffffff" stroke-width="1.2" opacity="0.9" fill="none">
    <!-- north pylon -->
    <line x1="60" y1="215" x2="60" y2="90"/>
    <line x1="50" y1="105" x2="70" y2="105"/>
    <line x1="45" y1="130" x2="75" y2="130"/>
    <!-- cables from pylon to deck -->
    <line x1="60" y1="95"  x2="10"  y2="200"/>
    <line x1="60" y1="95"  x2="35"  y2="200"/>
    <line x1="60" y1="95"  x2="95"  y2="200"/>
    <line x1="60" y1="95"  x2="130" y2="200"/>
    <line x1="60" y1="95"  x2="165" y2="200"/>
  </g>

  <!-- Swan Boat silhouette on the Charles (bottom left water) -->
  <g fill="#0b0d18" opacity="0.85">
    <path d="M 170 215 q 20 -12 50 0 q 0 8 -10 10 h -35 q -8 -2 -5 -10 z"/>
    <!-- swan neck -->
    <path d="M 200 205 q -4 -12 -12 -14 q 0 -6 6 -6 q 10 0 12 14 z" fill="#ffffff" opacity="0.9"/>
  </g>

  <!-- State House gold dome -->
  <g transform="translate(300,130)">
    <rect x="-30" y="45" width="60" height="40" fill="#c8bfa8"/>
    <path d="M -26 45 Q 0 -8 26 45 Z" fill="#f2c94c"/>
    <path d="M -26 45 Q 0 -8 26 45 Z" fill="none" stroke="#b4922e" stroke-width="1"/>
    <rect x="-2" y="-16" width="4" height="16" fill="#b4922e"/>
    <circle cx="0" cy="-18" r="3" fill="#f2c94c"/>
  </g>

  <!-- John Hancock tower (parallelogram) -->
  <polygon points="430,220 470,220 490,90 450,90" fill="#5d9bff"/>
  <polygon points="430,220 470,220 490,90 450,90" fill="#ffffff" opacity="0.08"/>
  <!-- Hancock window glints -->
  <g fill="#ffe8a3" opacity="0.6">
    <rect x="455" y="110" width="2" height="4"/><rect x="465" y="140" width="2" height="4"/>
    <rect x="475" y="170" width="2" height="4"/><rect x="450" y="190" width="2" height="4"/>
  </g>

  <!-- Prudential tower -->
  <g>
    <rect x="530" y="75" width="70" height="145" fill="#2f4f88"/>
    <rect x="548" y="60" width="34" height="20" fill="#2f4f88"/>
    <rect x="560" y="48" width="10" height="14" fill="#2f4f88"/>
    <rect x="563" y="36" width="4" height="14" fill="#2f4f88"/>
    <!-- window grid -->
    <g fill="#ffd866" opacity="0.55">
      <rect x="540" y="90"  width="3" height="4"/><rect x="552" y="90"  width="3" height="4"/><rect x="564" y="90"  width="3" height="4"/><rect x="576" y="90"  width="3" height="4"/><rect x="588" y="90"  width="3" height="4"/>
      <rect x="540" y="110" width="3" height="4"/><rect x="552" y="110" width="3" height="4"/><rect x="564" y="110" width="3" height="4"/><rect x="576" y="110" width="3" height="4"/><rect x="588" y="110" width="3" height="4"/>
      <rect x="540" y="130" width="3" height="4"/><rect x="552" y="130" width="3" height="4"/><rect x="564" y="130" width="3" height="4"/><rect x="576" y="130" width="3" height="4"/><rect x="588" y="130" width="3" height="4"/>
      <rect x="540" y="150" width="3" height="4"/><rect x="552" y="150" width="3" height="4"/><rect x="564" y="150" width="3" height="4"/><rect x="576" y="150" width="3" height="4"/><rect x="588" y="150" width="3" height="4"/>
      <rect x="540" y="170" width="3" height="4"/><rect x="552" y="170" width="3" height="4"/><rect x="564" y="170" width="3" height="4"/><rect x="576" y="170" width="3" height="4"/><rect x="588" y="170" width="3" height="4"/>
      <rect x="540" y="190" width="3" height="4"/><rect x="552" y="190" width="3" height="4"/><rect x="564" y="190" width="3" height="4"/><rect x="576" y="190" width="3" height="4"/><rect x="588" y="190" width="3" height="4"/>
    </g>
  </g>

  <!-- Citgo sign (iconic triangle over Fenway) -->
  <g transform="translate(700,70)">
    <rect x="-2" y="30" width="4" height="35" fill="#1a1a2e"/>
    <rect x="-36" y="-8" width="72" height="42" fill="#0b0d18"/>
    <polygon points="0,-4 34,30 -34,30" fill="url(#citgo)"/>
    <text x="0" y="20" text-anchor="middle" font-family="Impact, Arial Black, sans-serif" font-size="14" font-weight="900" fill="#0b0d18">CITGO</text>
  </g>

  <!-- Small mid-skyline buildings -->
  <g fill="#2a1e55">
    <rect x="760" y="155" width="25" height="65"/>
    <rect x="790" y="140" width="18" height="80"/>
    <rect x="815" y="165" width="22" height="55"/>
    <rect x="850" y="130" width="28" height="90"/>
    <rect x="885" y="150" width="20" height="70"/>
    <rect x="910" y="175" width="15" height="45"/>
  </g>

  <!-- Custom House Tower (clock tower) -->
  <g transform="translate(960,110)">
    <rect x="-12" y="30" width="24" height="80" fill="#3a2d6b"/>
    <rect x="-16" y="22" width="32" height="10" fill="#3a2d6b"/>
    <polygon points="-16,22 0,-4 16,22" fill="#3a2d6b"/>
    <circle cx="0" cy="48" r="7" fill="#ffd866"/>
    <line x1="0" y1="48" x2="0" y2="43" stroke="#0b0d18" stroke-width="1"/>
    <line x1="0" y1="48" x2="4" y2="48" stroke="#0b0d18" stroke-width="1"/>
  </g>

  <!-- T subway logo (round roundel, transit pin) -->
  <g transform="translate(1000,200)">
    <circle cx="0" cy="0" r="14" fill="#0b0d18"/>
    <circle cx="0" cy="0" r="12" fill="#ffffff"/>
    <text x="0" y="5" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-weight="900" font-size="17" fill="#0b0d18">T</text>
  </g>

  <!-- Ducklings row (Make Way for Ducklings) at bottom -->
  <g fill="#0b0d18">
    <g transform="translate(230,225)"><ellipse cx="0" cy="0" rx="6" ry="4"/><circle cx="-4" cy="-4" r="3"/></g>
    <g transform="translate(250,226)"><ellipse cx="0" cy="0" rx="5" ry="3.5"/><circle cx="-3" cy="-3" r="2.5"/></g>
    <g transform="translate(268,227)"><ellipse cx="0" cy="0" rx="4.5" ry="3"/><circle cx="-3" cy="-3" r="2.2"/></g>
    <g transform="translate(283,227)"><ellipse cx="0" cy="0" rx="4" ry="2.8"/><circle cx="-2.5" cy="-2.5" r="2"/></g>
  </g>

  <!-- foreground water strip -->
  <rect x="0" y="220" width="1200" height="20" fill="url(#water)"/>
  <g stroke="#6aa6ff" stroke-width="0.6" opacity="0.5" fill="none">
    <path d="M 0 228 q 30 -3 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0"/>
    <path d="M 0 234 q 30 -2 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0 t 60 0"/>
  </g>

  <!-- little confetti sparkles -->
  <g opacity="0.9">
    <circle cx="130" cy="110" r="2" fill="#7ae3ff"/>
    <circle cx="380" cy="70"  r="2" fill="#ffd866"/>
    <circle cx="660" cy="140" r="2" fill="#ff77aa"/>
    <circle cx="770" cy="80"  r="2" fill="#9cf0a0"/>
    <circle cx="850" cy="50"  r="2" fill="#ffd866"/>
    <circle cx="1010" cy="140" r="2" fill="#7ae3ff"/>
  </g>
</svg>
"""


def format_time(s):
    if not s:
        return "TBA"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return s
    return dt.astimezone(EASTERN).strftime("%-I:%M %p")


def format_when(e):
    if not e.get("date") and e.get("ends"):
        try:
            end = datetime.strptime(e["ends"], "%Y-%m-%d")
        except ValueError:
            return format_time(e.get("date"))
        return f"thru {end.month}/{end.day}"
    return format_time(e.get("date"))


def format_date_heading(date_obj):
    today = datetime.now(EASTERN).date()
    delta = (date_obj - today).days
    if delta == 0:
        prefix = "Today"
    elif delta == 1:
        prefix = "Tomorrow"
    else:
        prefix = date_obj.strftime("%A")
    return f"{prefix} · {date_obj.strftime('%b %-d')}"


def compute_recurring(dated):
    """Return set of (normalized_name, source_venue) keys for events that appear
    on the same weekday roughly a week apart — treated as weekly recurring."""
    groups = defaultdict(list)
    for _, events in dated:
        for e in events:
            t = e.get("_time")
            name = (e.get("name") or "").strip().lower()
            if not t or not name:
                continue
            key = (name, e.get("_source_venue") or "")
            groups[key].append(t)
    recurring = set()
    for key, times in groups.items():
        if len(times) < 2:
            continue
        times.sort()
        for i in range(len(times) - 1):
            delta = (times[i + 1].date() - times[i].date()).days
            if 5 <= delta <= 9:
                recurring.add(key)
                break
    return recurring


def _dedup_key(e):
    name = (e.get("name") or "").strip().lower()
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    if not name or len(name) < 4:
        return None
    return name


def _merge_duplicates(events):
    """Collapse events sharing a normalized name within the same day bucket.

    The first occurrence wins; later ones are attached as alt sources so render
    can link out to both. Events without a usable dedup key pass through as-is.
    """
    seen = {}
    out = []
    for e in events:
        key = _dedup_key(e)
        if key is None:
            out.append(e)
            continue
        if key in seen:
            primary = seen[key]
            primary.setdefault("_alt_sources", [])
            src_url = e.get("url")
            src_name = e.get("_source_venue") or e.get("venue") or "source"
            if src_url and not any(a.get("url") == src_url for a in primary["_alt_sources"]) and src_url != primary.get("url"):
                primary["_alt_sources"].append({"venue": src_name, "url": src_url})
            if not primary.get("price") and e.get("price"):
                primary["price"] = e["price"]
        else:
            seen[key] = e
            out.append(e)
    return out


def group_by_date(results):
    """Flatten venue results into events annotated with venue; group by Eastern calendar date.

    Returns (dated_from_today, tba, ongoing). `ongoing` is events whose date is before today
    (useful long-running or evergreen listings that sources flag as upcoming/pinned).
    """
    today = datetime.now(EASTERN).date()
    buckets = {}
    tba = []
    ongoing = []
    for r in results:
        for e in r["events"]:
            entry = {"venue_url": r["url"], **e, "_source_venue": r["venue"]}
            entry["venue"] = e.get("venue") or r["venue"]
            raw = e.get("date")
            key = None
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(EASTERN)
                    key = dt.date()
                    entry["_time"] = dt
                except (TypeError, ValueError):
                    pass
            if key is None:
                tba.append(entry)
            elif key < today:
                ongoing.append(entry)
            else:
                buckets.setdefault(key, []).append(entry)
    for date_key, events in list(buckets.items()):
        events.sort(key=lambda e: e["_time"])
        buckets[date_key] = _merge_duplicates(events)
    ongoing.sort(key=lambda e: e.get("_time") or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    return sorted(buckets.items()), tba, ongoing


def render_page(results):
    dated, tba, ongoing = group_by_date(results)
    recurring_keys = compute_recurring(dated)
    total = sum(len(v) for _, v in dated) + len(tba)
    failed = [r for r in results if r["error"]]
    all_venue_names = [r["venue"] for r in results]

    weather = fetch_boston_weather()
    weather_pill_html = ""
    if weather:
        weather_pill_html = f'<span class="pill-weather" title="{weather.get("label", "")} in Boston">{weather.get("icon", "🌤️")} {weather.get("temp", "--")}°F <span class="weather-label">{weather.get("label", "")}</span></span>'
        weather_html = f'{weather["icon"]} {weather["temp"]}°F {weather["label"]} · '
    else:
        weather_html = ""

    def is_recurring(e):
        return (
            (e.get("name") or "").strip().lower(),
            e.get("_source_venue") or "",
        ) in recurring_keys

    def render_event(e):
        raw_title = e.get("name") or "Untitled"
        title = escape(raw_title)
        link = (
            f'<a href="{escape(e["url"])}" target="_blank" rel="noopener">{title}</a>'
            if e.get("url") else title
        )
        is_free = _is_event_free(e)
        price_raw = escape(e["price"]) if e.get("price") else ""
        if price_raw:
            if "free" in price_raw.lower() or price_raw in ("$0", "0"):
                price_tag = f'<span class="price free">{price_raw}</span>'
            else:
                price_tag = f'<span class="price">{price_raw}</span>'
        elif is_free:
            price_tag = '<span class="price free">Free</span>'
        else:
            price_tag = ""

        cat = e.get("category") or "other"
        bucket = category_bucket(cat)
        color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
        cat_tag = f'<span class="cat-pill" style="--cat-c:{color}; background:{color}18; border-color:{color}33; color:{color}">{icon} {escape(cat)}</span>'
        venue = e.get("venue") or ""
        source = e.get("_source_venue") or ""
        city = _event_city(venue, source)
        recurring = is_recurring(e)
        recur_flag = "weekly" if recurring else "once"
        recur_badge = '<span class="recur">↻ weekly</span>' if recurring else ""
        alts = e.get("_alt_sources") or []
        alt_html = ""
        if alts:
            alt_links = " · ".join(
                f'<a href="{escape(a["url"])}" target="_blank" rel="noopener">{escape(a["venue"])}</a>'
                for a in alts if a.get("url")
            )
            if alt_links:
                alt_html = f'<span class="alt-sources">also on {alt_links}</span>'
        if venue:
            maps_url = _maps_link(venue, city)
            venue_html = f'<a class="venue-link" href="{escape(maps_url)}" target="_blank" rel="noopener">{escape(venue)}</a>'
        else:
            venue_html = ""

        gcal_url = _build_gcal_link(e, raw_title, venue, city)
        cal_actions = []
        if gcal_url:
            cal_actions.append(f'<a class="cal-btn" href="{escape(gcal_url)}" target="_blank" rel="noopener" title="Add to Google Calendar">+ GCal</a>')
        if e.get("date"):
            cal_actions.append(f'<button type="button" class="cal-btn ics-btn" data-title="{escape(raw_title)}" data-date="{escape(e["date"])}" data-venue="{escape(venue)}" data-url="{escape(e.get("url") or "")}" title="Download .ics for Apple/Outlook">+ .ics</button>')
        cal_html = f'<span class="cal-links">{" ".join(cal_actions)}</span>' if cal_actions else ""

        desc = (e.get("description") or "")[:150]
        desc_html = f'<div class="desc">{escape(desc)}</div>' if desc else ""
        free_flag = "true" if is_free else "false"
        return f'''<li class="event" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}" data-venue="{escape(source)}" data-city="{escape(city)}" data-recur="{recur_flag}" data-free="{free_flag}">
          <div class="when">{escape(format_when(e))}</div>
          <div class="what">{link}{price_tag}{recur_badge}
            <div class="venue-tag">{cat_tag} · {venue_html}{(" · " + alt_html) if alt_html else ""}{cal_html}</div>
            {desc_html}
          </div>
        </li>'''

    bucket_name_order = [b for b, _ in CATEGORY_BUCKETS]
    city_day_order = ["cambridge", "somerville", "boston", "other"]

    def _render_buckets(events):
        by_bucket = {b: [] for b in bucket_name_order}
        for e in events:
            by_bucket.setdefault(category_bucket(e.get("category")), []).append(e)
        bucket_blocks = []
        for bname in bucket_name_order:
            bucket_events = by_bucket.get(bname) or []
            if not bucket_events:
                continue
            cats = dict(CATEGORY_BUCKETS).get(bname, [])
            accent = CATEGORY_STYLES.get(cats[0], CATEGORY_STYLES["other"])[0] if cats else CATEGORY_STYLES["other"][0]
            items = "\n".join(render_event(e) for e in bucket_events)
            bucket_blocks.append(f'''
            <div class="bucket" data-bucket="{escape(bname)}">
              <div class="bucket-head" style="--accent:{accent}">
                <span class="bucket-name">{escape(bname)}</span>
                <span class="count">{len(bucket_events)}</span>
              </div>
              <ul>{items}</ul>
            </div>''')
        return "".join(bucket_blocks)

    def _render_day_section(heading_html, events, date_attr=""):
        by_city = {c: [] for c in city_day_order}
        for e in events:
            c = _event_city(e.get("venue"), e.get("_source_venue"))
            by_city.setdefault(c, []).append(e)
        city_blocks = []
        for cname in city_day_order:
            city_events = by_city.get(cname) or []
            if not city_events:
                continue
            city_blocks.append(f'''
          <div class="city-section" data-city="{escape(cname)}">
            <h3 class="city-head"><span>{escape(CITY_LABELS[cname])}</span><span class="count">{len(city_events)}</span></h3>
            <div class="buckets">{_render_buckets(city_events)}</div>
          </div>''')
        return f'''
        <section class="day" data-date="{date_attr}">
          <h2>{heading_html}<span class="count">{len(events)}</span></h2>
          <div class="cities">{"".join(city_blocks)}</div>
        </section>'''

    sections = []
    for date_obj, events in dated:
        sections.append(_render_day_section(escape(format_date_heading(date_obj)), events, date_obj.isoformat()))
    if tba:
        sections.append(_render_day_section("Date TBA", tba, "tba"))

    useful_sidebar = ""
    if STATIC_LINKS or DEAL_LINKS:
        deals_block = ""
        lucky_shows = fetch_luckyseat_boston()
        if DEAL_LINKS or lucky_shows:
            lucky_html = ""
            if lucky_shows:
                def _lucky_li(s):
                    price = s.get("price")
                    price_str = f" · ${price:.0f} all-in" if isinstance(price, (int, float)) else ""
                    return (
                        f'<li><a href="{escape(s["url"])}" target="_blank" rel="noopener">'
                        f'<span class="deal-name">{escape(s["name"] or "Show")}</span>'
                        f'<span class="deal-meta">{escape(s["venue"] or "")}{escape(price_str)}</span>'
                        f'</a></li>'
                    )
                lucky_items = "".join(_lucky_li(s) for s in lucky_shows)
                lucky_html = f'''
          <div class="deals-sub">
            <div class="deals-sub-head"><a href="https://www.luckyseat.com/" target="_blank" rel="noopener">LuckySeat — Boston</a></div>
            <ul class="deals-list">{lucky_items}</ul>
          </div>'''
            elif DEAL_LINKS:
                lucky_html = '''
          <div class="deals-sub">
            <div class="deals-sub-head">LuckySeat — Boston</div>
            <p class="hint">No active Boston lotteries right now.</p>
          </div>'''
            other_deals_html = ""
            others = [(n, u) for n, u in DEAL_LINKS if "luckyseat" not in u.lower()]
            if others:
                other_items = "".join(
                    f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(n)}</a></li>'
                    for n, u in others
                )
                other_deals_html = f'<ul class="deals-list">{other_items}</ul>'
            deals_block = f'''
        <div class="useful-inner">
          <h3>Deals &amp; lotteries</h3>
          {lucky_html}
          {other_deals_html}
        </div>'''

        useful_block = ""
        if STATIC_LINKS:
            by_cat = {}
            for cat, name, link in STATIC_LINKS:
                by_cat.setdefault(cat, []).append((name, link))
            parts = []
            for cat, pairs in by_cat.items():
                color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
                link_items = "".join(
                    f'<li><a href="{escape(u)}" target="_blank" rel="noopener">{escape(n)}</a></li>'
                    for n, u in pairs
                )
                parts.append(
                    f'<div class="useful-cat"><div class="useful-cat-head" style="color:{color}">{icon} {escape(cat)}</div><ul>{link_items}</ul></div>'
                )
            useful_block = f'''
        <div class="useful-inner">
          <h3>Useful links</h3>
          <p class="hint">Venues without a scrapable calendar.</p>
          {"".join(parts)}
        </div>'''

        useful_sidebar = f'''
      <aside class="useful">{deals_block}{useful_block}
      </aside>'''

    ongoing_section = ""
    if ongoing:
        items = "\n".join(render_event(e) for e in ongoing)
        ongoing_section = f'''
      <section class="ongoing">
        <h2>Ongoing &amp; evergreen<span class="count">{len(ongoing)}</span></h2>
        <p class="hint">Listings dated before today (long-running or pinned by the source).</p>
        <ul>{items}</ul>
      </section>'''

    bucket_order = [b for b, _ in CATEGORY_BUCKETS]
    bucket_counts = {b: 0 for b in bucket_order}
    other_count = 0
    recurring_count = 0
    once_count = 0
    all_events_flat = [e for _, es in dated for e in es] + list(tba)
    for e in all_events_flat:
        bucket_counts[category_bucket(e.get("category"))] = bucket_counts.get(category_bucket(e.get("category")), 0) + 1
        if (e.get("category") or "other") == "other":
            other_count += 1
        if is_recurring(e):
            recurring_count += 1
        else:
            once_count += 1

    def _bucket_icon_row(bucket_name):
        cats = dict(CATEGORY_BUCKETS).get(bucket_name, [])
        return " ".join(CATEGORY_STYLES.get(c, CATEGORY_STYLES["other"])[1] for c in cats)

    bucket_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="cat-chk" value="{escape(b)}" checked>
            <span>{_bucket_icon_row(b)} {escape(b)} <span class="count">{bucket_counts.get(b, 0)}</span></span>
          </label>'''
        for b in bucket_order
    )

    recur_boxes = f'''
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="once" checked>
          <span>One-time <span class="count">{once_count}</span></span>
        </label>
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="weekly" checked>
          <span>↻ Weekly recurring <span class="count">{recurring_count}</span></span>
        </label>'''

    venue_counts = {v: 0 for v in all_venue_names}
    for e in all_events_flat:
        venue_counts[e.get("_source_venue", "")] = venue_counts.get(e.get("_source_venue", ""), 0) + 1

    venue_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="venue-chk" value="{escape(v)}" checked>
            <span>{escape(v)} <span class="count">{venue_counts.get(v, 0)}</span></span>
          </label>'''
        for v in all_venue_names
    )

    city_order = ["boston", "cambridge", "somerville", "other"]
    city_counts = {c: 0 for c in city_order}
    for e in all_events_flat:
        c = _event_city(e.get("venue"), e.get("_source_venue"))
        city_counts[c] = city_counts.get(c, 0) + 1

    CITY_COLORS = {"boston": "#5d9bff", "cambridge": "#e05a6b", "somerville": "#f29e4c", "other": "#9aa3b2"}
    city_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="city-chk" value="{escape(c)}" checked>
            <span><span class="city-swatch" style="background:{CITY_COLORS[c]}"></span>{escape(CITY_LABELS[c])} <span class="count">{city_counts.get(c, 0)}</span></span>
          </label>'''
        for c in city_order
    )

    fail_banner = ""
    if failed:
        parts = " · ".join(
            f'<a href="{escape(r["url"])}" target="_blank" rel="noopener">{escape(r["venue"])}</a>'
            for r in failed
        )
        fail_banner = f'<div class="fail">Couldn\'t scrape: {parts}</div>'

    other_note = ""
    if other_count:
        other_note = f'<div class="other-note">{other_count} event{"" if other_count == 1 else "s"} fell through to <b>Community → other</b> — no keyword matched their title.</div>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Boston Events</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root {{
    --bg: #0c0e14;
    --card: #151822;
    --card-hover: #1c202e;
    --fg: #eef1f8;
    --muted: #8e96a8;
    --accent: #5d9bff;
    --accent-glow: rgba(93, 155, 255, 0.25);
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, 0.14);
    --green-border: rgba(74, 222, 128, 0.32);
    --warn: #f0a07a;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  /* Modern Hero Banner */
  .banner {{
    position: relative;
    min-height: 270px;
    display: flex;
    align-items: flex-end;
    background-color: #121020;
    background-image:
      linear-gradient(180deg, rgba(12, 14, 20, 0.18) 0%, rgba(12, 14, 20, 0.62) 58%, rgba(12, 14, 20, 0.98) 100%),
      url('banner.jpg');
    background-size: cover;
    background-position: center 60%;
    border-bottom: 1px solid var(--border);
    padding: 40px 24px 28px;
  }}
  .banner-inner {{
    max-width: 1320px;
    width: 100%;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .banner-top-tag {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #ffd866;
    text-shadow: 0 1px 8px rgba(0,0,0,0.6);
  }}
  .live-pulse {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7);
    animation: livepulse 2s infinite;
  }}
  @keyframes livepulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); }}
    70% {{ box-shadow: 0 0 0 8px rgba(74, 222, 128, 0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }}
  }}
  .banner-title {{
    margin: 0;
    font-size: 44px;
    font-weight: 850;
    letter-spacing: -0.035em;
    color: #ffffff;
    line-height: 1.05;
    text-shadow: 0 2px 20px rgba(0,0,0,0.6);
  }}
  .banner-meta-pill {{
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    align-self: flex-start;
    background: rgba(18, 21, 31, 0.72);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 13px;
    color: var(--fg);
    box-shadow: 0 4px 20px rgba(0,0,0,0.35);
  }}
  .pill-weather {{ display: inline-flex; align-items: center; gap: 4px; font-weight: 600; color: #fff; }}
  .weather-label {{ font-weight: 400; color: var(--muted); }}
  .pill-dot {{ color: var(--muted); opacity: 0.6; }}
  .pill-stat {{ color: var(--fg); }}
  .pill-refresh {{ color: #ffd866; text-decoration: none; font-weight: 600; font-size: 12px; }}
  .pill-refresh:hover {{ text-decoration: underline; }}

  /* Layout */
  .layout {{
    max-width: 1320px;
    margin: 0 auto;
    padding: 20px 24px 48px;
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr) 240px;
    gap: 18px;
    align-items: start;
  }}
  aside.filters {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-right: 4px;
  }}
  aside.filters::-webkit-scrollbar, aside.useful::-webkit-scrollbar {{ width: 6px; }}
  aside.filters::-webkit-scrollbar-thumb, aside.useful::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  aside.useful {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  aside.useful .useful-inner {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }}
  aside.useful .deals-list {{ list-style: none; margin: 0; padding: 0; }}
  aside.useful .deals-list li {{ margin: 6px 0; }}
  aside.useful .deals-list a {{ color: var(--accent); text-decoration: none; display: block; }}
  aside.useful .deals-list a:hover {{ text-decoration: underline; }}
  aside.useful .deal-name {{ display: block; font-weight: 500; }}
  aside.useful .deal-meta {{ display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }}
  aside.useful .deals-sub {{ margin-top: 8px; }}
  aside.useful .deals-sub:first-child {{ margin-top: 0; }}
  aside.useful .deals-sub-head {{ font-size: 11px; letter-spacing: 0.04em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }}
  aside.useful .deals-sub-head a {{ color: var(--muted); text-decoration: none; }}
  aside.useful .deals-sub-head a:hover {{ color: var(--accent); }}
  aside.useful h3 {{ margin: 0 0 4px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }}
  aside.useful p.hint {{ margin: 0 0 10px; color: var(--muted); font-size: 11px; }}
  .useful-cat {{ margin-top: 10px; }}
  .useful-cat:first-of-type {{ margin-top: 4px; }}
  .useful-cat-head {{ font-size: 11px; font-weight: 600; letter-spacing: 0.02em; margin-bottom: 4px; }}
  .useful-cat ul {{ list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 2px; }}
  .useful-cat li a {{ color: var(--accent); text-decoration: none; font-size: 12px; display: block; padding: 2px 0; }}
  .useful-cat li a:hover {{ text-decoration: underline; }}

  main {{ display: flex; flex-direction: column; gap: 16px; min-width: 0; }}

  /* Quick-Access Chips Bar */
  .quick-chips-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
  }}
  .chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: #fff;
  }}
  .chip.active {{
    background: var(--accent);
    color: #0c0e14;
    border-color: var(--accent);
    font-weight: 700;
    box-shadow: 0 2px 10px var(--accent-glow);
  }}
  .chip-free {{
    color: var(--green);
    border-color: var(--green-border);
    background: var(--green-bg);
    margin-left: auto;
  }}
  .chip-free.active {{
    background: var(--green);
    color: #08200f;
    border-color: var(--green);
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(74, 222, 128, 0.3);
  }}

  /* Day Section */
  .day {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 14px 18px 12px; }}
  .day h2 {{ margin: 0 0 12px; font-size: 17px; font-weight: 700; display:flex; align-items:center; gap:8px; color: var(--fg); position: sticky; top: 0; background: var(--card); padding: 4px 0 8px; z-index: 2; }}
  .count {{ background: rgba(255, 255, 255, 0.06); color: var(--muted); font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; }}
  .cities {{ display: flex; flex-direction: column; gap: 14px; }}
  .city-section {{ --city-color: var(--accent); border-top: 1px solid var(--border); padding-top: 12px; padding-left: 10px; border-left: 3px solid var(--city-color); }}
  .city-section:first-child {{ border-top: none; padding-top: 0; }}
  .city-section.empty {{ display: none; }}
  .city-section[data-city="boston"]    {{ --city-color: #5d9bff; }}
  .city-section[data-city="cambridge"] {{ --city-color: #e05a6b; }}
  .city-section[data-city="somerville"]{{ --city-color: #f29e4c; }}
  .city-section[data-city="other"]     {{ --city-color: #9aa3b2; }}
  .city-head {{ margin: 0 0 8px; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--city-color); display: flex; align-items: center; gap: 8px; }}
  .city-head .count {{ background: transparent; color: var(--muted); font-weight: 500; letter-spacing: 0; }}
  .buckets {{ display: flex; flex-direction: column; gap: 10px; }}
  .bucket {{ border-left: 3px solid var(--accent, #444); padding: 2px 0 2px 12px; border-left-color: var(--accent); }}
  .bucket-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-weight: 600; }}
  .bucket-head .count {{ background: transparent; color: var(--muted); }}
  .bucket ul {{ list-style: none; padding: 0; margin: 0; }}

  /* Event Cards */
  .event {{
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.04);
    margin-bottom: 6px;
    display: grid;
    grid-template-columns: 78px 1fr;
    gap: 12px;
    font-size: 14px;
    transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  }}
  .event:hover {{
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(93, 155, 255, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
  }}
  .when {{ color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 2px; font-weight: 500; }}
  .what a {{ color: #79aeff; text-decoration: none; font-weight: 500; }}
  .what a:hover {{ text-decoration: underline; color: #a5caff; }}
  .venue-tag {{ color: var(--muted); font-size: 11px; margin-top: 4px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }}
  .venue-link {{ color: var(--muted); text-decoration: none; border-bottom: 1px dotted rgba(154,163,178,0.4); }}
  .venue-link:hover {{ color: var(--fg); border-bottom-color: var(--fg); }}
  .cat-pill {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; line-height: 1.3; border: 1px solid; }}
  .price {{ display:inline-block; background: rgba(255,255,255,0.06); color: var(--muted); font-size: 11px; padding: 2px 7px; border-radius: 5px; font-weight: 500; }}
  .price.free {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); font-weight: 700; }}
  .cal-links {{ display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; }}
  .cal-btn {{ background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--muted); padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 500; text-decoration: none; cursor: pointer; line-height: 1.3; display: inline-flex; align-items: center; gap: 3px; font-family: inherit; transition: all 0.15s ease; }}
  .cal-btn:hover {{ color: #fff; border-color: var(--accent); background: rgba(93,155,255,0.15); }}
  .recur {{ display:inline-block; margin-left: 8px; background: rgba(255,122,178,0.14); color: #ff7ab2; font-size: 10px; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.02em; }}
  .alt-sources {{ color: var(--muted); font-size: 11px; }}
  .alt-sources a {{ color: var(--accent); text-decoration: none; }}
  .alt-sources a:hover {{ text-decoration: underline; }}
  .desc {{ color: var(--muted); font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }}
  .bucket.empty {{ display: none; }}

  /* Filter Groups */
  .filter-group {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
  .filter-group h3 {{ margin: 0 0 8px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); display: flex; align-items:center; gap:8px; flex-wrap:wrap; }}
  .filter-group h3 .spacer {{ flex:1; }}
  .filter-group h3 button {{ background: none; border: 1px solid var(--border); color: var(--muted); font-size: 10px; padding: 1px 8px; border-radius: 999px; cursor: pointer; font-family: inherit; letter-spacing: 0; text-transform: none; }}
  .filter-group h3 button:hover {{ color: var(--fg); border-color: var(--fg); }}
  .filter-group.venues .chk-grid {{ max-height: 280px; overflow-y: auto; }}
  .chk-grid {{ display:flex; flex-direction: column; gap:2px; }}
  .chk {{ display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; padding: 3px 4px; border-radius: 6px; }}
  .chk:hover {{ background: rgba(255,255,255,0.03); }}
  .chk input {{ accent-color: var(--accent); margin: 0; flex-shrink: 0; }}
  .chk > span {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }}
  .chk > span > .count {{ margin-left: auto; }}
  .city-swatch {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .free-toggle {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: var(--green); user-select: none; }}
  .free-toggle input {{ accent-color: var(--green); width: 14px; height: 14px; cursor: pointer; margin: 0; }}

  /* Search Box */
  .search-input-wrap {{ position: relative; display: flex; align-items: center; }}
  #search-input {{ width:100%; background:var(--bg); border:1px solid var(--border); color:var(--fg); padding:8px 36px 8px 10px; border-radius:var(--radius-sm); font-size:13px; font-family:inherit; transition: border-color 0.15s ease, box-shadow 0.15s ease; }}
  #search-input:focus {{ outline:none; border-color:var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
  #search-input::placeholder {{ color:var(--muted); }}
  .search-kbd {{ position: absolute; right: 10px; background: rgba(255, 255, 255, 0.08); color: var(--muted); font-size: 11px; padding: 1px 6px; border-radius: 4px; pointer-events: none; font-family: monospace; border: 1px solid rgba(255,255,255,0.06); }}
  .search-clear-btn {{ position: absolute; right: 8px; background: none; border: none; color: var(--muted); font-size: 16px; cursor: pointer; padding: 2px 6px; line-height: 1; }}
  .search-clear-btn:hover {{ color: var(--fg); }}
  .search-status {{ margin-top: 6px; font-size: 11px; color: var(--accent); font-weight: 500; }}

  /* Week navigation */
  .week-nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 8px 12px; }}
  .week-nav.bottom {{ justify-content: center; }}
  .week-nav button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; font-family: inherit; }}
  .week-nav button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .week-nav button[aria-pressed="true"], .week-nav button.active {{ background: var(--accent); color: #0c0e14; border-color: var(--accent); font-weight: 600; }}
  #week-label, #week-label-b {{ font-size: 13px; font-weight: 600; color: var(--fg); flex: 1; text-align: center; min-width: 160px; }}
  .week-nav.bottom #week-label-b {{ flex: 0; padding: 0 12px; }}
  .mini-cal {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
  .mini-cal-head {{ display:flex; align-items:center; gap:8px; margin-bottom: 6px; }}
  .mini-cal-head button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 6px; padding: 2px 10px; font-size: 14px; cursor: pointer; font-family: inherit; line-height: 1; }}
  .mini-cal-head button:hover {{ border-color: var(--accent); color: var(--accent); }}
  #cal-month-label {{ flex: 1; text-align: center; font-size: 13px; font-weight: 600; }}
  .mini-cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; font-size: 11px; }}
  .mini-cal-grid .dow {{ text-align: center; color: var(--muted); font-size: 10px; padding: 2px 0; letter-spacing: 0.04em; }}
  .mini-cal-grid .d {{ text-align: center; padding: 5px 0; border-radius: 6px; cursor: pointer; color: var(--muted); background: transparent; border: 1px solid transparent; position: relative; }}
  .mini-cal-grid .d.has-events {{ color: var(--fg); }}
  .mini-cal-grid .d.has-events::after {{ content:''; position:absolute; bottom: 2px; left: 50%; transform: translateX(-50%); width: 4px; height: 4px; border-radius: 50%; background: var(--accent); }}
  .mini-cal-grid .d.today {{ border-color: var(--border); }}
  .mini-cal-grid .d.in-week {{ background: rgba(93,155,255,0.12); color: var(--fg); }}
  .mini-cal-grid .d.anchor {{ background: var(--accent); color: #0c0e14; font-weight: 700; }}
  .mini-cal-grid .d.anchor::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.blank {{ cursor: default; }}
  .mini-cal-grid .d:not(.blank):hover {{ border-color: var(--accent); }}
  .event.hidden {{ display: none; }}
  .day.empty, .day.out-of-week {{ display: none; }}
  .ongoing {{ margin-top: 4px; }}
  .ongoing h2 {{ margin: 0 0 4px; font-size: 15px; font-weight: 600; display:flex; align-items:center; gap:8px; color: var(--fg); }}
  .ongoing .hint {{ margin: 0 0 10px; color: var(--muted); font-size: 12px; }}
  .ongoing ul {{ list-style: none; padding: 14px 18px; margin: 0; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); max-height: 420px; overflow-y: auto; }}
  .ongoing .event {{ padding: 8px 12px; }}
  .fail {{ max-width: 1320px; margin: 0 auto; padding: 8px 24px; color: var(--warn); font-size: 12px; }}
  .fail a {{ color: var(--warn); }}
  .other-note {{ max-width: 1320px; margin: 0 auto; padding: 4px 24px 0; color: var(--muted); font-size: 11px; }}
  footer {{ max-width: 1320px; margin: 0 auto; padding: 0 24px 32px; color: var(--muted); font-size: 12px; text-align: center; }}

  /* Mobile Responsive */
  .mobile-filter-bar {{ display: none; }}
  .mobile-filter-close {{ display: none; }}
  @media (max-width: 1100px) {{
    .layout {{ grid-template-columns: 240px minmax(0, 1fr); }}
    aside.useful {{ position: static; grid-column: 1 / -1; max-height: none; }}
  }}
  @media (max-width: 860px) {{
    .banner-title {{ font-size: 32px; }}
    .banner {{ min-height: 220px; padding: 30px 16px 20px; }}
    .layout {{ grid-template-columns: minmax(0, 1fr); padding: 16px; }}
    .mobile-filter-bar {{ display: block; margin-bottom: 12px; }}
    .mobile-filter-btn {{
      width: 100%;
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--fg);
      padding: 10px 14px;
      border-radius: var(--radius-md);
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font-family: inherit;
    }}
    aside.filters {{ display: none; }}
    aside.filters.mobile-open {{
      display: flex;
      position: fixed;
      inset: 0;
      z-index: 999;
      background: var(--bg);
      padding: 20px;
      max-height: 100vh;
      overflow-y: auto;
    }}
    .mobile-filter-close {{
      display: block;
      background: var(--accent);
      color: #0c0e14;
      border: none;
      padding: 10px;
      border-radius: var(--radius-sm);
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      font-family: inherit;
      margin-bottom: 12px;
    }}
    .chip-free {{ margin-left: 0; }}
  }}
</style>
</head>
<body>
  <div class="banner">
    <div class="banner-inner">
      <div class="banner-top-tag"><span class="live-pulse"></span> GREATER BOSTON LIVE EVENTS</div>
      <h1 class="banner-title">Boston Events</h1>
      <div class="banner-meta-pill">
        {weather_pill_html}
        <span class="pill-dot">·</span>
        <span class="pill-stat"><strong>{total:,}</strong> events · <strong>{len(results)}</strong> venues</span>
        <span class="pill-dot">·</span>
        <a href="?refresh=1" class="pill-refresh" title="Force refresh live feeds">↻ Refresh</a>
      </div>
    </div>
  </div>
  {fail_banner}
  {other_note}
  <div class="layout">
    <div class="mobile-filter-bar">
      <button type="button" id="mobile-filter-toggle" class="mobile-filter-btn">
        <span>⚙️ Filter Venues &amp; Categories</span>
        <span id="mobile-filter-badge" class="count">All</span>
      </button>
    </div>
    <aside class="filters" id="sidebar-filters">
      <button type="button" id="mobile-filter-close" class="mobile-filter-close">✕ Done Filtering</button>
      <div class="filter-group">
        <h3>Search</h3>
        <div class="search-input-wrap">
          <input type="text" id="search-input" placeholder="Search events, venues, bands…" autocomplete="off">
          <span class="search-kbd" id="search-kbd" title="Press / or Cmd+K to search">/</span>
          <button type="button" id="search-clear" class="search-clear-btn" aria-label="Clear search" hidden>×</button>
        </div>
        <div id="search-status" class="search-status" hidden>
          <span id="search-count">0</span> events found
        </div>
      </div>
      <div class="filter-group">
        <label class="free-toggle" for="free-only-chk">
          <input type="checkbox" id="free-only-chk">
          <span>✨ Free events only</span>
        </label>
      </div>
      <div class="filter-group">
        <h3>Category <span class="spacer"></span> <button type="button" id="cat-all">all</button> <button type="button" id="cat-none">none</button></h3>
        <div class="chk-grid">{bucket_boxes}</div>
      </div>
      <div class="filter-group">
        <h3>City <span class="spacer"></span> <button type="button" id="city-all">all</button> <button type="button" id="city-none">none</button></h3>
        <div class="chk-grid">{city_boxes}</div>
      </div>
      <div class="filter-group">
        <h3>Recurrence</h3>
        <div class="chk-grid">{recur_boxes}</div>
      </div>
      <div class="filter-group venues">
        <h3>Venue <span class="spacer"></span> <button type="button" id="venue-all">all</button> <button type="button" id="venue-none">none</button></h3>
        <div class="chk-grid">{venue_boxes}</div>
      </div>
    </aside>
    <main>
      <div class="quick-chips-bar" id="quick-chips">
        <button type="button" class="chip active" data-time="all">All Upcoming</button>
        <button type="button" class="chip" data-time="today">⚡ Today</button>
        <button type="button" class="chip" data-time="tomorrow">Tomorrow</button>
        <button type="button" class="chip" data-time="weekend">🎉 This Weekend</button>
        <button type="button" class="chip" data-time="week">📅 Next 7 Days</button>
        <button type="button" class="chip chip-free" id="quick-free-chip">✨ Free Only</button>
      </div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous week">← prev</button>
        <span id="week-label">Loading…</span>
        <button type="button" id="week-next" aria-label="Next week">next →</button>
        <button type="button" id="week-today">today</button>
        <button type="button" id="week-all" data-mode="week">show all</button>
        <button type="button" id="cal-toggle" aria-expanded="false">📅 pick date</button>
      </div>
      <div class="mini-cal" id="mini-cal" hidden>
        <div class="mini-cal-head">
          <button type="button" id="cal-prev-month" aria-label="Previous month">‹</button>
          <span id="cal-month-label"></span>
          <button type="button" id="cal-next-month" aria-label="Next month">›</button>
        </div>
        <div class="mini-cal-grid" id="mini-cal-grid"></div>
      </div>
      {"".join(sections)}
      <div class="week-nav bottom">
        <button type="button" id="week-prev-b" aria-label="Previous week">← prev</button>
        <span id="week-label-b"></span>
        <button type="button" id="week-next-b" aria-label="Next week">next →</button>
      </div>
      {ongoing_section}
    </main>
    {useful_sidebar}
  </div>
  <footer>Scraped live from each venue's site. Times shown in Eastern.</footer>
  <script>
    const catBoxes = document.querySelectorAll('.cat-chk');
    const venueBoxes = document.querySelectorAll('.venue-chk');
    const recurBoxes = document.querySelectorAll('.recur-chk');
    const cityBoxes = document.querySelectorAll('.city-chk');
    const searchInput = document.getElementById('search-input');
    const searchKbd = document.getElementById('search-kbd');
    const searchClear = document.getElementById('search-clear');
    const searchStatus = document.getElementById('search-status');
    const searchCount = document.getElementById('search-count');
    const freeOnlyChk = document.getElementById('free-only-chk');

    const quickChips = document.querySelectorAll('#quick-chips .chip[data-time]');
    const quickFreeChip = document.getElementById('quick-free-chip');
    let timeFilter = 'all';

    const mobileToggle = document.getElementById('mobile-filter-toggle');
    const mobileClose = document.getElementById('mobile-filter-close');
    const sidebarFilters = document.getElementById('sidebar-filters');
    const mobileBadge = document.getElementById('mobile-filter-badge');

    const daySections = Array.from(document.querySelectorAll('.day[data-date]'));
    const eventDates = new Set(
      daySections.map(d => d.dataset.date).filter(s => s && s !== 'tba')
    );
    function parseISO(s) {{ const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }}
    function fmtISO(d) {{
      const y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), da = String(d.getDate()).padStart(2, '0');
      return `${{y}}-${{m}}-${{da}}`;
    }}
    function addDays(d, n) {{ const c = new Date(d); c.setDate(c.getDate() + n); return c; }}
    const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    function fmtShort(d) {{ return MONTHS[d.getMonth()] + ' ' + d.getDate(); }}
    function fmtMonth(d) {{ return d.toLocaleString('en-US', {{ month: 'long', year: 'numeric' }}); }}

    const todayISO = fmtISO(new Date());
    let anchor = parseISO(todayISO);
    let showAll = true;
    let calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);

    function weekDates() {{
      const out = [];
      for (let i = 0; i < 7; i++) out.push(fmtISO(addDays(anchor, i)));
      return out;
    }}
    function updateWeekLabel() {{
      const end = addDays(anchor, 6);
      const label = (timeFilter === 'all' || showAll)
        ? 'Showing all upcoming'
        : `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      document.getElementById('week-label').textContent = label;
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const btn = document.getElementById('week-all');
      btn.textContent = (timeFilter === 'all' || showAll) ? 'week view' : 'show all';
      btn.setAttribute('aria-pressed', (timeFilter === 'all' || showAll) ? 'true' : 'false');
    }}

    function updateQuickChipsUI() {{
      quickChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.time === timeFilter);
      }});
      if (quickFreeChip) {{
        quickFreeChip.classList.toggle('active', freeOnlyChk ? freeOnlyChk.checked : false);
      }}
    }}

    function updateSearchUI() {{
      const val = searchInput.value.trim();
      if (searchClear) searchClear.hidden = !val;
      if (searchKbd) searchKbd.hidden = !!val;
      if (searchStatus && searchCount) {{
        if (val) {{
          const matched = document.querySelectorAll('.event:not(.hidden)').length;
          searchCount.textContent = matched;
          searchStatus.hidden = false;
        }} else {{
          searchStatus.hidden = true;
        }}
      }}
    }}

    function updateMobileBadge() {{
      if (!mobileBadge) return;
      const allCats = catBoxes.length;
      const chkCats = Array.from(catBoxes).filter(b => b.checked).length;
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isFiltered = (chkCats < allCats) || (chkVenues < allVenues) || isFree || searchInput.value.trim();
      mobileBadge.textContent = isFiltered ? 'Active' : 'All';
      mobileBadge.style.color = isFiltered ? 'var(--accent)' : '';
    }}

    function stateToHash() {{
      const params = new URLSearchParams();
      const q = searchInput.value.trim();
      if (q) params.set('q', q);

      const allCats = Array.from(catBoxes).map(b => b.value);
      const checkedCats = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCats.length > 0 && checkedCats.length < allCats.length) params.set('cat', checkedCats.join(','));

      const allCities = Array.from(cityBoxes).map(b => b.value);
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCities.length > 0 && checkedCities.length < allCities.length) params.set('city', checkedCities.join(','));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');

      if (timeFilter !== 'all') params.set('t', timeFilter);
      if (!showAll && fmtISO(anchor) !== todayISO) params.set('d', fmtISO(anchor));

      const hash = params.toString();
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    }}

    function hashToState() {{
      const hash = location.hash.slice(1);
      if (!hash) return;
      const params = new URLSearchParams(hash);

      if (params.has('q')) searchInput.value = params.get('q');
      if (params.get('free') === '1' && freeOnlyChk) freeOnlyChk.checked = true;

      if (params.has('t')) {{
        timeFilter = params.get('t');
        showAll = (timeFilter === 'all');
      }}

      if (params.has('cat')) {{
        const vals = new Set(params.get('cat').split(','));
        catBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
      }}

      if (params.has('city')) {{
        const vals = new Set(params.get('city').split(','));
        cityBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
      }}

      if (params.has('d')) {{
        const d = params.get('d');
        if (d === 'all') {{ showAll = true; timeFilter = 'all'; }}
        else {{ anchor = parseISO(d); calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1); }}
      }}
    }}

    function apply() {{
      const cats = new Set(Array.from(catBoxes).filter(b => b.checked).map(b => b.value));
      const venues = new Set(Array.from(venueBoxes).filter(b => b.checked).map(b => b.value));
      const recurs = new Set(Array.from(recurBoxes).filter(b => b.checked).map(b => b.value));
      const cities = new Set(Array.from(cityBoxes).filter(b => b.checked).map(b => b.value));
      const searchText = searchInput.value.trim().toLowerCase();
      const freeOnly = freeOnlyChk ? freeOnlyChk.checked : false;
      const week = new Set(weekDates());

      document.querySelectorAll('.event').forEach(li => {{
        const catOk = cats.has(li.dataset.bucket);
        const venueOk = venues.has(li.dataset.venue);
        const recurOk = recurs.has(li.dataset.recur);
        const cityOk = cities.has(li.dataset.city);
        const freeOk = !freeOnly || li.dataset.free === 'true';
        const searchOk = !searchText || li.textContent.toLowerCase().includes(searchText);
        li.classList.toggle('hidden', !(catOk && venueOk && recurOk && cityOk && searchOk && freeOk));
      }});

      document.querySelectorAll('.bucket').forEach(b => {{
        const visible = b.querySelectorAll('.event:not(.hidden)').length;
        b.classList.toggle('empty', visible === 0);
      }});
      document.querySelectorAll('.city-section').forEach(sec => {{
        const visible = sec.querySelectorAll('.event:not(.hidden)').length;
        sec.classList.toggle('empty', visible === 0);
      }});

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));

      daySections.forEach(day => {{
        const date = day.dataset.date;
        let inTime = true;
        if (timeFilter === 'today') {{
          inTime = (date === todayISO);
        }} else if (timeFilter === 'tomorrow') {{
          inTime = (date === tomorrowISO);
        }} else if (timeFilter === 'weekend') {{
          inTime = (date === satISO || date === sunISO);
        }} else if (timeFilter === 'week') {{
          inTime = (date === 'tba' || week.has(date));
        }} else {{
          // 'all'
          inTime = showAll || date === 'tba' || week.has(date);
        }}
        day.classList.toggle('out-of-week', !inTime);
        const visible = day.querySelectorAll('.event:not(.hidden)').length;
        day.classList.toggle('empty', visible === 0);
      }});

      renderCal();
      updateWeekLabel();
      updateQuickChipsUI();
      updateSearchUI();
      updateMobileBadge();
      stateToHash();
    }}

    function renderCal() {{
      const grid = document.getElementById('mini-cal-grid');
      if (!grid) return;
      const year = calMonth.getFullYear(), month = calMonth.getMonth();
      document.getElementById('cal-month-label').textContent = fmtMonth(calMonth);
      const first = new Date(year, month, 1);
      const startPad = first.getDay();
      const daysInMonth = new Date(year, month + 1, 0).getDate();
      const week = new Set(weekDates());
      let html = ['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => `<div class="dow">${{d}}</div>`).join('');
      for (let i = 0; i < startPad; i++) html += '<div class="d blank"></div>';
      for (let d = 1; d <= daysInMonth; d++) {{
        const iso = fmtISO(new Date(year, month, d));
        const classes = ['d'];
        if (eventDates.has(iso)) classes.push('has-events');
        if (iso === todayISO) classes.push('today');
        if (!showAll && week.has(iso)) classes.push('in-week');
        if (iso === fmtISO(anchor)) classes.push('anchor');
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;
    }}

    function shiftWeek(delta) {{
      timeFilter = 'week';
      showAll = false;
      anchor = addDays(anchor, delta);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}
    function setAnchor(iso) {{
      timeFilter = 'week';
      showAll = false;
      anchor = parseISO(iso);
      apply();
    }}

    quickChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        timeFilter = chip.dataset.time;
        const todayDate = parseISO(todayISO);
        const dayOfWeek = todayDate.getDay();
        let daysToSat = (6 - dayOfWeek + 7) % 7;
        if (dayOfWeek === 0) daysToSat = -1;

        if (timeFilter === 'all') {{
          showAll = true;
        }} else if (timeFilter === 'today') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'tomorrow') {{
          showAll = false;
          anchor = addDays(parseISO(todayISO), 1);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'weekend') {{
          showAll = false;
          anchor = addDays(todayDate, daysToSat);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'week') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }}
        apply();
      }});
    }});

    if (quickFreeChip && freeOnlyChk) {{
      quickFreeChip.addEventListener('click', () => {{
        freeOnlyChk.checked = !freeOnlyChk.checked;
        apply();
      }});
    }}

    document.addEventListener('keydown', (e) => {{
      if ((e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) &&
          document.activeElement !== searchInput &&
          !['input', 'textarea'].includes((document.activeElement.tagName || '').toLowerCase())) {{
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }} else if (e.key === 'Escape' && document.activeElement === searchInput) {{
        searchInput.value = '';
        searchInput.blur();
        apply();
      }}
    }});

    if (searchClear) {{
      searchClear.addEventListener('click', () => {{
        searchInput.value = '';
        apply();
        searchInput.focus();
      }});
    }}

    if (mobileToggle && sidebarFilters) {{
      mobileToggle.addEventListener('click', () => {{
        sidebarFilters.classList.add('mobile-open');
        document.body.style.overflow = 'hidden';
      }});
    }}
    if (mobileClose && sidebarFilters) {{
      mobileClose.addEventListener('click', () => {{
        sidebarFilters.classList.remove('mobile-open');
        document.body.style.overflow = '';
      }});
    }}

    document.getElementById('week-prev').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-prev-b').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next-b').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-today').addEventListener('click', () => {{ setAnchor(todayISO); calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1); apply(); }});
    document.getElementById('week-all').addEventListener('click', () => {{
      if (showAll || timeFilter === 'all') {{
        showAll = false;
        timeFilter = 'week';
        anchor = parseISO(todayISO);
      }} else {{
        showAll = true;
        timeFilter = 'all';
      }}
      apply();
    }});
    document.getElementById('cal-toggle').addEventListener('click', (e) => {{
      const cal = document.getElementById('mini-cal');
      const open = cal.hasAttribute('hidden');
      if (open) cal.removeAttribute('hidden'); else cal.setAttribute('hidden', '');
      e.currentTarget.setAttribute('aria-expanded', open ? 'true' : 'false');
    }});
    document.getElementById('cal-prev-month').addEventListener('click', () => {{
      calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() - 1, 1);
      renderCal();
    }});
    document.getElementById('cal-next-month').addEventListener('click', () => {{
      calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() + 1, 1);
      renderCal();
    }});
    document.getElementById('mini-cal-grid').addEventListener('click', (e) => {{
      const cell = e.target.closest('.d:not(.blank)');
      if (!cell || !cell.dataset.date) return;
      setAnchor(cell.dataset.date);
    }});

    if (freeOnlyChk) freeOnlyChk.addEventListener('change', apply);
    catBoxes.forEach(b => b.addEventListener('change', apply));
    venueBoxes.forEach(b => b.addEventListener('change', apply));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    searchInput.addEventListener('input', apply);
    document.getElementById('cat-all').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('cat-none').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('venue-all').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = false); apply(); }});

    function downloadICS(title, dateStr, venue, url) {{
      if (!dateStr) return;
      let dt;
      try {{ dt = new Date(dateStr); }} catch(e) {{ return; }}
      if (isNaN(dt.getTime())) return;
      function pad(n) {{ return n < 10 ? '0' + n : n; }}
      function toICS(d) {{
        return d.getUTCFullYear() + pad(d.getUTCMonth()+1) + pad(d.getUTCDate()) + 'T' +
               pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + 'Z';
      }}
      const start = toICS(dt);
      const end = toICS(new Date(dt.getTime() + 2 * 3600 * 1000));
      function cleanText(str) {{
        return (str || '').split(String.fromCharCode(10)).join(' ')
                          .split(String.fromCharCode(13)).join('')
                          .split(',').join('\\\\,');
      }}
      const cleanTitle = cleanText(title || 'Event');
      const cleanVenue = cleanText(venue || 'Boston, MA');
      const cleanUrl = (url || '').split(String.fromCharCode(10)).join('')
                                  .split(String.fromCharCode(13)).join('');
      const ics = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Boston Events//EN',
        'BEGIN:VEVENT',
        'SUMMARY:' + cleanTitle,
        'DTSTART:' + start,
        'DTEND:' + end,
        'LOCATION:' + cleanVenue,
        'DESCRIPTION:' + cleanUrl,
        'END:VEVENT',
        'END:VCALENDAR'
      ].join(String.fromCharCode(13, 10));
      const blob = new Blob([ics], {{ type: 'text/calendar;charset=utf-8' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = (title.replace(/[^a-zA-Z0-9]/g, '_') || 'event') + '.ics';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}

    document.addEventListener('click', (e) => {{
      const btn = e.target.closest('.ics-btn');
      if (!btn) return;
      e.preventDefault();
      downloadICS(btn.dataset.title, btn.dataset.date, btn.dataset.venue, btn.dataset.url);
    }});

    hashToState();
    apply();
  </script>
</body>
</html>"""
