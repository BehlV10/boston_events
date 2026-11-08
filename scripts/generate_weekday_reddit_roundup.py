#!/usr/bin/env python3
"""Generate a weekday Reddit roundup for r/boston, r/cambridgema, and r/somerville.

Curates ~5 top events per day for Boston, Cambridge, and Somerville from Monday to Friday
(15 events per day, 75 events total), formatted in Reddit Markdown with venue, time,
price, neighborhood, and 1-line descriptions.

Usage:
    python3 scripts/generate_weekday_reddit_roundup.py              # this/next Monday–Friday
    python3 scripts/generate_weekday_reddit_roundup.py 2026-11-09   # specific week starting Monday
"""

import copy
import json
import os
import re
import sys
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
CITY_CAPS = {"boston": 9, "cambridge": 8, "somerville": 6}
REDDIT_LIMIT = 40000      # Reddit self-post body limit (characters)
SIZE_TARGET = 38500       # leave headroom for hand edits before posting

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
    mon = _week_start(start_monday)
    weekdays = [mon + timedelta(days=i) for i in range(5)]  # Mon, Tue, Wed, Thu, Fri
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
        n = (name or "").lower().strip()
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
        # Weekday post is for after work: daytime talks/matinees only fill gaps
        elif e["_time"].hour < 17:
            s -= 60
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
        title = f"Things to do in Boston, Cambridge & Somerville this week ({span}) · Weekday Guide"

        city_display = {
            "boston": "🏙️ BOSTON",
            "cambridge": "🎓 CAMBRIDGE",
            "somerville": "🎨 SOMERVILLE",
        }

        out = [
            f"Hi Boston! Here are 5–9 curated things to do each day for **Monday {mon.strftime('%b %-d')} through "
            f"Friday {fri.strftime('%b %-d')}**, broken down by city (**Boston**, **Cambridge**, and **Somerville**).",
            "",
            "Whether you're looking for live music, comedy, 35mm films, pub trivia, or free museum nights after work, "
            "here are the top picks for the week! Add anything else happening below.",
            "",
        ]

        if runs:
            out += ["## 🎭 RUNNING ALL WEEK", ""]
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
            f"- **Today in Boston**: [{SITE}/boston-events-today/]({SITE}/boston-events-today/)",
            f"- **This weekend**: [{SITE}/boston-events-this-weekend/]({SITE}/boston-events-this-weekend/) · "
            f"**Free this weekend**: [{SITE}/free-events-boston-this-weekend/]({SITE}/free-events-boston-this-weekend/)",
            f"- **By city**: [Boston]({SITE}/boston/) · [Cambridge]({SITE}/cambridge/) · "
            f"[Cambridge tonight]({SITE}/cambridge-events-tonight/) · [Somerville]({SITE}/somerville/) · "
            f"[Somerville live music]({SITE}/live-music-somerville/)",
            f"- **By interest**: [Music]({SITE}/music/) · [Comedy]({SITE}/comedy/) · [Free]({SITE}/free/) · "
            f"[EDM & nightlife]({SITE}/boston-edm/) · [Board game nights]({SITE}/board-game-nights-boston/) · "
            f"[Markets & festivals]({SITE}/markets-festivals-boston/) · [Kids & family]({SITE}/kids-family-events-boston/)",
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
    assert len(body) <= REDDIT_LIMIT, f"post is {len(body):,} chars, over Reddit's {REDDIT_LIMIT:,}"
    return title, body


def main():
    start_arg = sys.argv[1] if len(sys.argv) > 1 else None
    title, body = build_weekday_roundup(start_arg)
    mon = _week_start(start_arg)
    out_dir = os.path.join(ROOT, "reddit")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"weekday-roundup-{mon.isoformat()}.md")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(f"<!-- Title: {title} -->\n\n{body}")

    print(f"Title: {title}")
    print(f"Saved: {out_file} ({len(body):,} characters)")


if __name__ == "__main__":
    main()
