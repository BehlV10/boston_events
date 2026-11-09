#!/usr/bin/env python3
"""Generate the weekday (Mon–Fri) or weekend (Fri–Sun) Reddit roundup.

Curates ~5 top events per day for Boston, Cambridge, and Somerville, formatted in Reddit
Markdown with venue, time, price, neighborhood, and 1-line descriptions (highlights.json notes).
The daily build also publishes both as hidden pages (roundup/weekday/, roundup/weekend/) with
copy buttons; see render_roundup_page.

Usage:
    python3 scripts/generate_weekday_reddit_roundup.py                      # this/next Monday–Friday
    python3 scripts/generate_weekday_reddit_roundup.py 2026-11-09           # week starting that Monday
    python3 scripts/generate_weekday_reddit_roundup.py --weekend            # this/next Friday–Sunday
    python3 scripts/generate_weekday_reddit_roundup.py --weekend 2026-11-13
"""

import copy
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from template import (  # noqa: E402
    EASTERN, _effective_category, _event_city, _get_event_highlight, _hub_place_label,
    _is_event_free, _load_highlights, _merge_duplicates, title_word_freq,
)
from scrapers import category_bucket  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

SITE = "https://www.wickedbostonevents.com"

MAJOR_VENUES = (
    "td garden", "mgm music hall", "house of blues", "big night live", "roadrunner", "royale",
    "paradise rock", "the sinclair", "brighton music hall", "the wilbur", "orpheum", "agganis",
    "leader bank pavilion", "fenway park", "chevalier", "shubert", "wang theatre",
    "boch center", "emerson colonial", "cutler majestic", "emerson paramount", "huntington",
    "symphony hall", "jordan hall", "berklee performance", "sanders theatre", "laugh boston",
    "nick's comedy", "comedy studio", "improv asylum", "city winery", "crystal ballroom",
    "somerville theatre", "arts at the armory", "the middle east", "club passim",
    "museum of fine arts", "isabella stewart gardner", "ica boston", "institute of contemporary art",
    "museum of science", "harvard art museums", "wbur cityspace", "coolidge corner", "brattle",
    "the burren", "aeronaut", "remnant", "portico", "castle island"
)

# Arenas and big theaters: a highlighted show here outranks one at a club the same night
BIG_VENUES = (
    "td garden", "mgm music hall", "roadrunner", "agganis", "leader bank pavilion", "fenway park",
    "orpheum", "wang theatre", "shubert", "emerson colonial", "symphony hall", "house of blues",
)

AGGREGATOR_SOURCES = ("seatgeek", "ticketmaster", "boston shows", "boston calendar", "do617",
                      "eventschaser", "eventbrite")

# Picks per city per day. The first BASE_PICKS fill on score; anything past that must carry a
# highlights.json blurb, so the extra slots go to curated events, never filler.
BASE_PICKS = 5
CITY_CAPS = {"boston": 10, "cambridge": 9, "somerville": 7}
REDDIT_LIMIT = 40000      # Reddit self-post body limit (characters)
SIZE_TARGET = 38500       # leave headroom for hand edits before posting

# Reddit's spam filters (and r/boston mods) block or bury posts linking social networks, so
# those links are swapped for another listing's direct link, the venue's own events page,
# or dropped (title shown in bold, unlinked).
SOCIAL_URL_RE = re.compile(
    r"(?i)^https?://(?:[\w-]+\.)*(?:facebook\.com|fb\.(?:com|me|watch)|instagram\.com|instagr\.am|"
    r"twitter\.com|x\.com|t\.co|threads\.(?:net|com)|tiktok\.com)(?:/|$)"
)
# Ticket-platform links we'd rather not lead with: swapped for another listing's direct link
# (venue, library, university page) when one exists, kept otherwise.
SECONDARY_URL_RE = re.compile(r"(?i)^https?://(?:[\w-]+\.)*(?:eventbrite\.[a-z.]+|evbuc\.com)(?:/|$)")
VENUE_EVENT_PAGES = {
    "aeronaut": "https://www.aeronautbrewing.com/visit/somerville/#events",
}

SKIP_TITLE_RE = re.compile(
    r"(?i)\b(?:class|classes|course|workshop|training|certification|summit|"
    r"conference|webinar|yoga|zoom|exam|prep|figure drawing|infant|toddler|"
    r"storytime|story time|committee|meeting|retirement board|clubhouse|board of health|"
    r"luthier collective|preview session|open house|pose|poses|drawing club|runners|group run|"
    r"stair climb|happy hour deals|virtual|council on aging|pre-show)\b"
)


def _week_start(arg=None):
    if arg:
        d = date.fromisoformat(arg)
        return d - timedelta(days=d.weekday())
    today = datetime.now(EASTERN).date()
    # If today is Monday-Friday, use this week's Monday; if weekend (Sat/Sun), use upcoming Monday
    if today.weekday() < 5:
        return today - timedelta(days=today.weekday())
    return today + timedelta(days=(7 - today.weekday()))


def _weekend_start(arg=None):
    """Friday of the weekend to cover: this weekend through Saturday, next weekend from Sunday."""
    d = date.fromisoformat(arg) if arg else datetime.now(EASTERN).date()
    if arg:
        return d + timedelta(days=(4 - d.weekday()) % 7) if d.weekday() < 4 else d - timedelta(days=d.weekday() - 4)
    if d.weekday() == 6:
        return d + timedelta(days=5)
    return d + timedelta(days=4 - d.weekday())


def _clean_title(name):
    t = re.sub(r"\s+", " ", unescape(name or "")).strip()
    t = re.sub(r"^(?:The )?Bowery Presents:?\s*", "", t, flags=re.I)
    t = re.sub(r"\s+presented by .*$", "", t, flags=re.I)
    t = re.sub(r"\s+[-–]\s+(?:Ages 18\+|21\+|Boston|MA).*$", "", t, flags=re.I)
    return t if len(t) <= 75 else t[:72].rstrip() + "…"


def _link(text, url):
    text = text.replace("[", "(").replace("]", ")")
    if not url or not url.startswith("http"):
        return f"**{text}**"
    return f"**[{text}]({url.replace(')', '%29').replace(' ', '%20')})**"


def _price(e):
    if _is_event_free(e):
        return "Free"
    p = str(e.get("price") or "").strip()
    if not p or re.fullmatch(r"\$?0(?:\.00)?", p) or len(p) > 20 or not re.search(r"\d", p):
        return ""
    return re.sub(r"\.00\b", "", p)


def _time(e):
    t = e.get("_time")
    if not isinstance(t, datetime):
        return e.get("time") or ""
    return "" if (t.hour, t.minute) == (0, 0) else t.strftime("%-I:%M%p").replace(":00", "")


def _venue(e):
    v = re.sub(r"\s+", " ", e.get("venue") or e.get("_source_venue") or "").strip()
    v = re.sub(r"\s+presented by .*$", "", v, flags=re.I)
    v = re.sub(r"\s*\((?:Boston|Cambridge|Somerville)\)$", "", v)
    v = re.sub(r"^Downtown Boston - ", "", v)
    v = re.sub(r"^Main Stage,\s*", "", v)
    return v


def _area(e):
    g = resolve_event_geo(e)
    if g and g.get("neighborhood"):
        return g["neighborhood"].replace(" Square", " Sq")
    city = _event_city(e.get("venue"), e.get("_source_venue"), e)
    lbl = _hub_place_label(city, e).split(",")[0].replace(" Square", " Sq")
    return "" if lbl in ("Greater Boston",) else lbl


def _line(e):
    parts = [_link(_clean_title(e["name"]), e.get("url")) + f" @ {_venue(e)}"]
    t = _time(e)
    if t:
        parts[0] += f" @ {t}"
    extra = [x for x in (_price(e), _area(e)) if x]
    s = "* " + parts[0] + (" · " + " · ".join(extra) if extra else "")
    note = (e.get("_highlight") or {}).get("note")
    if note:
        s += f"  \n  {note}"
    return s


def _norm_key(title):
    t = re.sub(r"[^a-z0-9]+", "", (title or "").lower())
    return t[:20]


def build_weekday_roundup(start_monday=None):
    return build_roundup("weekday", start_monday)


def roundup_days(mode, start=None):
    if mode == "weekend":
        fri = _weekend_start(start)
        return [fri + timedelta(days=i) for i in range(3)]  # Fri, Sat, Sun
    mon = _week_start(start)
    return [mon + timedelta(days=i) for i in range(5)]  # Mon, Tue, Wed, Thu, Fri


def build_roundup(mode="weekday", start=None):
    """(title, markdown body) for the weekday (Mon–Fri) or weekend (Fri–Sun) post."""
    weekend = mode == "weekend"
    weekdays = roundup_days(mode, start)
    mon = weekdays[0]
    highlights = _load_highlights()

    with open(os.path.join(ROOT, "events.json"), encoding="utf-8") as f:
        data = json.load(f)
        venues = data["venues"] if isinstance(data, dict) and "venues" in data else data

    # Filter events to Mon-Fri and target cities
    city_keys = ("boston", "cambridge", "somerville")
    raw_events_by_day = {d: [] for d in weekdays}
    runs = defaultdict(list)  # highlight id -> listings of a multi-night theater run
    sold_out = set()  # (start time, venue) of sold-out listings; other listings of that show go too

    def _room_key(v):
        v = re.sub(r"^the\s+", "", (v or "").lower())
        return re.sub(r"[^a-z]", "", v)[:12]

    def _head_slug(name):
        n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().strip()
        n = re.sub(r"^(?:the\s+bowery\s+presents:?\s*|an\s+evening\s+with\s+|a\s+conversation\s+with\s+|sold\s+out:?\s*|!\s*)", "", n)
        n = re.sub(r"\s+(?:with|w/|ft\.|feat\.|presents|opened by)\s+.*$", "", n)
        n = re.sub(r"\s+[-–—:]\s+.*$", "", n)
        n = re.sub(r"\s*\((?:18\+|21\+|ages?\s+\d+\+?|boston|cambridge|somerville)\)$", "", n)
        n = re.sub(r"[^a-z0-9]+", "", n)
        return n[:16]

    for v in venues:
        vname = v["venue"]
        vurl = v.get("url", "")
        for e in v.get("events", []):
            d_str = e.get("date")
            if not d_str or d_str == "tba":
                continue
            try:
                ev_time = datetime.fromisoformat(d_str.replace("Z", "+00:00")).astimezone(EASTERN)
                ev_date = ev_time.date()
            except Exception:
                continue

            if ev_date not in raw_events_by_day:
                continue

            city = _event_city(e.get("venue"), vname, e)
            if city not in city_keys:
                continue

            name = e.get("name") or e.get("title") or ""
            if SKIP_TITLE_RE.search(name) or re.search(r"(?i)\b(?:closed|closure|canceled|cancelled|postponed)\b", name):
                continue
            if re.search(r"(?i)\bsold[ -]?out\b", f"{name} {e.get('price') or ''}"):
                sold_out.add((ev_time.replace(second=0, microsecond=0), _room_key(e.get("venue") or vname)))
                continue

            ev = dict(e)
            ev["_time"] = ev_time
            ev["_source_venue"] = vname
            ev["venue"] = e.get("venue") or vname
            ev["_city"] = city
            ev["_highlight"] = _get_event_highlight(ev, highlights)
            if ev["_highlight"] and ev["_highlight"].get("run"):
                runs[ev["_highlight"]["id"]].append(ev)  # listed once under "Running all week"
                continue
            raw_events_by_day[ev_date].append(ev)

    def score(e):
        s = 0
        if e.get("_highlight"):
            s += 120
        v_low = f"{e.get('venue')} {e.get('_source_venue')}".lower()
        if any(mv in v_low for mv in MAJOR_VENUES):
            s += 40
        if e.get("_highlight") and any(bv in v_low for bv in BIG_VENUES):
            s += 25
        if _is_event_free(e):
            s += 15
        # Library book groups / craft hours are free but rarely Reddit-worthy unless curated
        if ("public library" in v_low or "city hall" in v_low) and not e.get("_highlight"):
            s -= 40
        if e.get("price"):
            s += 10
        if _time(e):
            s += 10
        # Deprioritize aggregator duplicates or missing times
        if not _time(e):
            s -= 15
        # Weekday post is for after work: daytime talks/matinees only fill gaps.
        # On weekends daytime is prime time; only very early listings sink.
        elif not weekend and e["_time"].hour < 17:
            s -= 60
        elif weekend and e["_time"].hour < 9:
            s -= 30
        src = (e.get("_source_venue") or "").lower()
        if src in ("ticketmaster", "seatgeek", "eventschaser"):
            s -= 5
        return s

    def _venue_key(e):
        v = _venue(e).lower()
        v = re.split(r"\s+[—–-]\s+", v)[0]
        v = re.sub(r"^the\s+|\s+(?:company|co\.?)$", "", v)
        return v.strip()

    def _same_listing(a, b):
        if a["_time"].replace(second=0, microsecond=0) != b["_time"].replace(second=0, microsecond=0):
            return False
        an, bn = a["name"].lower(), b["name"].lower()
        return _venue_key(b) in an or _venue_key(a) in bn

    def _is_trivia(e):
        return bool(re.search(r"(?i)\btrivia\b", e.get("name") or ""))

    # Other listings of the same event: same start minute and same room, or same start minute
    # and same title opening (venue names vary across calendars).
    def _alt_keys(e):
        t = e["_time"].replace(second=0, microsecond=0)
        title = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", e["name"]).encode("ascii", "ignore").decode().lower())
        return [(t, "room", _room_key(e["venue"])), (t, "title", title[:12])]

    direct_urls = defaultdict(list)  # alt key -> direct (non-social, non-ticket-platform) links
    all_raw = [e for evs in raw_events_by_day.values() for e in evs] + [e for evs in runs.values() for e in evs]
    for e in all_raw:
        u = e.get("url") or ""
        if u.startswith("http") and not SOCIAL_URL_RE.match(u) and not SECONDARY_URL_RE.match(u):
            # the venue's own calendar first (source "Cambridge Public Library" for a CPL talk)
            own = _room_key(e.get("_source_venue"))[:8] == _room_key(e["venue"])[:8]
            for k in _alt_keys(e):
                direct_urls[k].append((0 if own else 1, u))
    for e in all_raw:
        u = e.get("url") or ""
        social, secondary = SOCIAL_URL_RE.match(u), SECONDARY_URL_RE.match(u)
        if not (social or secondary):
            continue
        alt = min((x for k in _alt_keys(e) for x in direct_urls.get(k, [])), default=(None, None))[1]
        if alt:
            e["url"] = alt
        elif social:
            v_low = f"{e.get('venue')} {e.get('_source_venue')}".lower()
            # venue's events page, else None -> rendered as bold text without a link
            e["url"] = next((pg for k, pg in VENUE_EVENT_PAGES.items() if k in v_low), None)

    picked_by_day_city = {d: {c: [] for c in city_keys} for d in weekdays}

    for d in weekdays:
        day_events = [e for e in raw_events_by_day[d]
                      if (e["_time"].replace(second=0, microsecond=0), _room_key(e["venue"])) not in sold_out]
        if not day_events:
            continue
        # One act can't play two cities the same night: when aggregators put a show somewhere
        # the venue's own calendar doesn't, drop the aggregator-only city.
        head_cities = defaultdict(lambda: defaultdict(bool))
        for e in day_events:
            src = (e.get("_source_venue") or "").lower()
            first_party = not any(a in src for a in AGGREGATOR_SOURCES)
            head_cities[_head_slug(e["name"])][e["_city"]] |= first_party
        def _wrong_city(e):
            cities = head_cities[_head_slug(e["name"])]
            return len(cities) > 1 and not cities[e["_city"]] and any(cities.values())
        day_events = [e for e in day_events if not _wrong_city(e)]
        day_heads = set()
        w_freq = title_word_freq(day_events)
        merged_day = _merge_duplicates(day_events, w_freq)

        # Group by city
        city_pools = {c: [] for c in city_keys}
        for e in merged_day:
            c = e.get("_city") or _event_city(e.get("venue"), e.get("_source_venue"), e)
            if c in city_pools:
                city_pools[c].append(e)

        for c in city_keys:
            evs = city_pools[c]
            evs.sort(key=lambda e: (-score(e), e["_time"]))
            day_picked = []
            seen_heads = day_heads
            seen_venue = Counter()

            cap = CITY_CAPS[c]

            def _room_for(e):
                return len(day_picked) < BASE_PICKS or (len(day_picked) < cap and e.get("_highlight"))

            # First pass: try strictly 1 event per venue and unique headliner
            for e in evs:
                if len(day_picked) >= cap:
                    break
                if not _room_for(e):
                    continue
                slug = _head_slug(e["name"])
                v_clean = _venue_key(e)
                if slug and slug in seen_heads:
                    continue
                if seen_venue[v_clean] >= 1:
                    continue
                if _is_trivia(e) and any(_is_trivia(p) for p in day_picked):
                    continue
                if any(_same_listing(e, p) for p in day_picked):
                    continue

                if slug:
                    seen_heads.add(slug)
                seen_venue[v_clean] += 1
                day_picked.append(e)

            # Second pass: if slots remain, allow up to 2 per venue if different headliner
            if len(day_picked) < cap:
                for e in evs:
                    if len(day_picked) >= cap:
                        break
                    if not _room_for(e):
                        continue
                    slug = _head_slug(e["name"])
                    v_clean = _venue_key(e)
                    if e in day_picked:
                        continue
                    if _is_trivia(e) and any(_is_trivia(p) for p in day_picked):
                        continue
                    if any(_same_listing(e, p) for p in day_picked):
                        continue
                    if slug and slug in seen_heads:
                        continue
                    if seen_venue[v_clean] >= 2:
                        continue
                    if slug:
                        seen_heads.add(slug)
                    seen_venue[v_clean] += 1
                    day_picked.append(e)

            picked_by_day_city[d][c] = day_picked  # pick order ~ rank; trimmed to fit, then time-sorted

    def _render(caps):
        # Format Markdown
        fri = weekdays[-1]
        span = f"{mon.strftime('%b %-d')}–{fri.strftime('%-d') if fri.month == mon.month else fri.strftime('%b %-d')}"
        if weekend:
            title = f"Things to do in Boston, Cambridge & Somerville this weekend ({span}) · Weekend Guide"
        else:
            title = f"Things to do in Boston, Cambridge & Somerville this week ({span}) · Weekday Guide"

        city_display = {
            "boston": "🏙️ BOSTON",
            "cambridge": "🎓 CAMBRIDGE",
            "somerville": "🎨 SOMERVILLE",
        }

        if weekend:
            out = [
                f"Hi Boston! Here are 5–9 curated things to do each day for **Friday {mon.strftime('%b %-d')} through "
                f"Sunday {fri.strftime('%b %-d')}**, broken down by city (**Boston**, **Cambridge**, and **Somerville**).",
                "",
                "Concerts, comedy, markets, museum days, 35mm films and more for the weekend. "
                "Add anything else happening below!",
                "",
            ]
        else:
            out = [
                f"Hi Boston! Here are 5–9 curated things to do each day for **Monday {mon.strftime('%b %-d')} through "
                f"Friday {fri.strftime('%b %-d')}**, broken down by city (**Boston**, **Cambridge**, and **Somerville**).",
                "",
                "Whether you're looking for live music, comedy, 35mm films, pub trivia, or free museum nights after work, "
                "here are the top picks for the week! Add anything else happening below.",
                "",
            ]

        if runs:
            out += ["## 🎭 RUNNING ALL WEEKEND" if weekend else "## 🎭 RUNNING ALL WEEK", ""]
            for evs in sorted(runs.values(), key=lambda v: min(e["_time"] for e in v)):
                evs = sorted(evs, key=lambda e: e["_time"])
                days = sorted({e["_time"].date() for e in evs})
                day_lbl = (days[0].strftime("%a") if len(days) == 1 else
                           f"{days[0].strftime('%a')}–{days[-1].strftime('%a')}")
                e = evs[0]
                price = next((_price(x) for x in evs if _price(x)), "")
                line = "* " + _link(_clean_title(e["name"]), e.get("url")) + f" @ {_venue(e)} · {day_lbl}"
                line += "".join(f" · {x}" for x in (price, _area(e)) if x)
                note = e["_highlight"].get("note")
                out.append(line + (f"  \n  {note}" if note else ""))
            out.append("")

        for d in weekdays:
            day_heading = f"## 📅 {d.strftime('%A, %b %-d').upper()}"
            out.append(day_heading)
            out.append("")

            for c in city_keys:
                picks = sorted(picked_by_day_city[d][c][:caps[c]], key=lambda e: e["_time"])
                out.append(f"### {city_display[c]}")
                if picks:
                    for e in picks:
                        out.append(_line(e))
                else:
                    out.append("* *Check the calendar for local shows tonight.*")
                out.append("")

        out += [
            "---",
            "",
            "### 🔗 More on Wicked Boston Events",
            f"- **Full calendar** (filter by neighborhood & T line): [{SITE}]({SITE})",
            f"- **For parents** (kids & family events): [{SITE}/kids-family-events-boston/]({SITE}/kids-family-events-boston/)",
            "",
            f"*Curated from 200+ local venue, theatre, museum, and community calendars at **[wickedbostonevents.com]({SITE})** (ad-free & independent).*",
        ]
        return title, "\n".join(out) + "\n"

    # Use the extra slots only as far as Reddit's limit allows: trim the lowest-ranked
    # curated extras (largest city first) until the body fits.
    caps = dict(CITY_CAPS)
    title, body = _render(caps)
    while len(body) > SIZE_TARGET and any(v > BASE_PICKS for v in caps.values()):
        c = max(caps, key=lambda k: caps[k])
        caps[c] -= 1
        title, body = _render(caps)
    social = re.findall(r"\]\((https?://[^)\s]+)\)", body)
    assert not any(SOCIAL_URL_RE.match(u) for u in social), "social-network link left in post"
    assert len(body) <= REDDIT_LIMIT, f"post is {len(body):,} chars, over Reddit's {REDDIT_LIMIT:,}"
    return title, body


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "weekend" if "--weekend" in sys.argv else "weekday"
    start_arg = args[0] if args else None
    title, body = build_roundup(mode, start_arg)
    first = roundup_days(mode, start_arg)[0]
    out_dir = os.path.join(ROOT, "reddit")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{mode}-roundup-{first.isoformat()}.md")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"<!-- Title: {title} -->\n\n{body}")

    print(f"Title: {title}")
    print(f"Saved: {out_file} ({len(body):,} characters)")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------------------------
# Hidden posting pages (roundup/weekday/, roundup/weekend/), rebuilt by every daily build.
# noindex + robots.txt Disallow + not in the sitemap: they're tools for posting, not site pages.

SUBREDDITS = (  # (name, who it's for)
    ("boston", "the main city sub"),
    ("CambridgeMA", "Cambridge"),
    ("Somerville", "Somerville"),
    ("BostonSocialClub", "people looking for things to do and company"),
)


def _md_inline(text):
    from html import escape as esc
    t = esc(text, quote=False)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: f'<a href="{esc(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", t)
    return t


def markdown_to_html(md):
    """The small Markdown subset the roundup uses: ##/### headings, * and - bullets with an
    indented second line, ---, paragraphs, links, bold and italics."""
    out, in_list = [], False
    for line in md.split("\n"):
        if line.startswith("  ") and in_list and line.strip():
            out[-1] = out[-1][:-5] + "<br>" + _md_inline(line.strip()) + "</li>"
            continue
        is_item = line.startswith(("* ", "- "))
        if in_list and not is_item:
            out.append("</ul>")
            in_list = False
        if is_item:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_md_inline(line[2:].rstrip())}</li>")
        elif line.startswith("### "):
            out.append(f"<h3>{_md_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_md_inline(line[3:])}</h2>")
        elif line.strip() == "---":
            out.append("<hr>")
        elif line.strip():
            out.append(f"<p>{_md_inline(line.strip())}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def render_roundup_page(mode, title, body, built_at=None):
    from html import escape as esc
    from urllib.parse import quote
    other = "weekend" if mode == "weekday" else "weekday"
    days = roundup_days(mode)
    span = f"{days[0].strftime('%a %b %-d')} – {days[-1].strftime('%a %b %-d')}"
    built = (built_at or datetime.now(EASTERN)).strftime("%a %b %-d, %-I:%M %p")
    subs = "\n".join(
        f'      <li><a class="sub" href="https://old.reddit.com/r/{n}/submit?selftext=true&amp;title={esc(quote(title))}" '
        f'target="_blank" rel="noopener">Post to r/{n}</a> <span class="muted">{esc(why)} · '
        f'<a href="https://www.reddit.com/r/{n}/about/rules" target="_blank" rel="noopener">rules</a></span></li>'
        for n, why in SUBREDDITS)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow,noarchive">
<title>{"Weekend" if mode == "weekend" else "Weekday"} Reddit Roundup</title>
<style>
:root{{--bg:#f6f7f9;--panel:#fff;--fg:#1c2230;--muted:#5d6676;--line:#dde1e8;--accent:#c2410c;--accent-fg:#fff;--code:#f0f2f5;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151b;--panel:#1a1e26;--fg:#e6e9ef;--muted:#9aa3b2;--line:#2c323d;--accent:#fb923c;--accent-fg:#1a1006;--code:#151920;color-scheme:dark}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,sans-serif}}
.wrap{{max-width:820px;margin:0 auto;padding:28px 16px 64px;display:grid;gap:18px}}
.eyebrow{{font-size:12px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
h1{{font:600 clamp(22px,4vw,30px)/1.2 Georgia,serif;margin:6px 0 0}}
.row{{display:flex;flex-wrap:wrap;gap:10px;align-items:center}}
.field{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 14px;display:grid;gap:8px;min-width:0}}
.label{{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.titletext{{font-weight:600;overflow-wrap:anywhere}}
button{{font:600 14px/1 inherit;font-family:inherit;border-radius:6px;padding:10px 14px;cursor:pointer;border:1px solid var(--line);background:var(--panel);color:var(--fg)}}
button.primary{{background:var(--accent);border-color:var(--accent);color:var(--accent-fg)}}
.muted,.status{{color:var(--muted);font-size:13px}}
.subs{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}
a{{color:var(--accent)}}
a.sub{{font-weight:600}}
.tabs{{display:flex;gap:4px;border-bottom:1px solid var(--line)}}
.tab{{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;color:var(--muted)}}
.tab[aria-selected="true"]{{color:var(--fg);border-bottom-color:var(--accent)}}
textarea{{width:100%;min-height:60vh;font:13px/1.5 ui-monospace,Menlo,monospace;background:var(--code);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:12px}}
.preview{{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:4px 18px 18px;overflow-wrap:anywhere}}
.preview h2{{font:600 18px/1.3 Georgia,serif;margin:24px 0 6px}}
.preview h3{{font-size:13px;letter-spacing:.06em;color:var(--muted);margin:14px 0 4px}}
.preview ul{{padding-left:20px;margin:4px 0}} .preview li{{margin:5px 0}}
[hidden]{{display:none!important}}
</style>
</head><body>
<div class="wrap">
  <header>
    <div class="eyebrow">{esc(span)} · rebuilt {esc(built)} · <a href="../{other}/">{other} version →</a></div>
    <h1>{"Weekend" if mode == "weekend" else "Weekday"} Reddit roundup</h1>
  </header>
  <div class="field">
    <div class="label">Post title</div>
    <div class="titletext" id="t">{esc(title)}</div>
    <div class="row"><button id="copyTitle">Copy title</button></div>
  </div>
  <div class="row">
    <button class="primary" id="copyBody">Copy post body (Markdown)</button>
    <span class="status" id="status" role="status"></span>
    <span class="status">{len(body):,} of 40,000 characters</span>
  </div>
  <div class="field">
    <div class="label">Where to post</div>
    <ul class="subs">
{subs}
    </ul>
    <p class="muted" style="margin:0">Each link opens old Reddit's text-post form with the title filled in; paste the body (old Reddit takes Markdown as is). On new Reddit, switch the editor to Markdown mode first. Check each sub's rules on self-promotion, and space posts out rather than cross-posting all at once.</p>
  </div>
  <div class="tabs" role="tablist">
    <button class="tab" role="tab" id="tabPrev" aria-selected="true">Preview</button>
    <button class="tab" role="tab" id="tabMd" aria-selected="false">Markdown</button>
  </div>
  <div class="preview" id="preview">
{markdown_to_html(body)}
  </div>
  <textarea id="md" spellcheck="false" hidden>{esc(body)}</textarea>
</div>
<script>
const ta = document.getElementById('md'), pv = document.getElementById('preview'), status = document.getElementById('status');
async function copy(text, label, fallback) {{
  try {{ await navigator.clipboard.writeText(text); status.textContent = label + ' copied'; }}
  catch (e) {{ if (fallback) {{ showMd(); ta.focus(); ta.select(); }} status.textContent = 'Copy was blocked: select the text and press Ctrl/Cmd+C.'; }}
}}
document.getElementById('copyBody').onclick = () => copy(ta.value, 'Post body', true);
document.getElementById('copyTitle').onclick = () => copy(document.getElementById('t').textContent, 'Title', false);
const tp = document.getElementById('tabPrev'), tm = document.getElementById('tabMd');
function showMd() {{ ta.hidden = false; pv.hidden = true; tm.setAttribute('aria-selected', 'true'); tp.setAttribute('aria-selected', 'false'); }}
function showPv() {{ ta.hidden = true; pv.hidden = false; tp.setAttribute('aria-selected', 'true'); tm.setAttribute('aria-selected', 'false'); }}
tm.onclick = showMd; tp.onclick = showPv;
</script>
</body></html>
"""


def write_roundup_pages(base_dir):
    """Write roundup/weekday/index.html and roundup/weekend/index.html under base_dir."""
    for mode in ("weekday", "weekend"):
        title, body = build_roundup(mode)
        d = os.path.join(base_dir, "roundup", mode)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(render_roundup_page(mode, title, body))
        print(f"wrote roundup/{mode}/: {title} ({len(body):,} chars)")
