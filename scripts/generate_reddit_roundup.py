#!/usr/bin/env python3
"""Draft the weekly r/boston post: things to do Monday–Sunday in Boston, Cambridge & Somerville.

Modeled on the popular r/boston weekend list (big-name concerts, comedy headliners, museum
nights, sports, festivals and theater runs as "Title @ Venue @ Time", a one-line blurb on the
notable ones, an "all week" section for runs), plus what that list doesn't have: a full
Monday–Sunday week, free picks, kids & family, ways to meet people, prices and neighborhoods.

Built from the site's merged, deduplicated events, so times and prices match the site.

    python3 scripts/generate_reddit_roundup.py              # next Monday–Sunday
    python3 scripts/generate_reddit_roundup.py 2026-11-09   # the week starting that Monday

Writes reddit/week-of-YYYY-MM-DD.md (title in the first line) and lists the headliners that
have no blurb yet; add those to highlights.json (or ask Claude to draft them), rerun, then
read the post through before posting. Picks are automatic.
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
    _is_event_free, _load_highlights, compute_recurring, group_by_date,
)
from scrapers import TECH_EVENT_RE, category_bucket, is_kid_family_event  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

SITE = "https://www.wickedbostonevents.com"
PER_DAY = 12
RUN_PICKS = 10
FREE_PICKS = 12
KIDS_PICKS = 10
SOCIAL_PICKS = 8
PER_VENUE_WEEK = 2
SKIP_BUCKETS = {"Classes & Services", "Deals & Specials", "Tech & Startups"}

# The places that weekly list leans on: arenas, theaters, the big rock clubs, comedy clubs,
# museums. Their shows are what most readers are scanning for.
MAJOR_VENUES = (
    "td garden", "mgm music hall", "house of blues", "big night live", "roadrunner", "royale",
    "paradise rock", "the sinclair", "brighton music hall", "the wilbur", "orpheum", "agganis",
    "leader bank pavilion", "fenway park", "gillette", "chevalier", "shubert", "wang theatre",
    "boch center", "emerson colonial", "cutler majestic", "emerson paramount", "huntington",
    "symphony hall", "jordan hall", "berklee performance", "sanders theatre", "laugh boston",
    "nick's comedy", "comedy studio", "improv asylum", "city winery", "crystal ballroom",
    "somerville theatre", "arts at the armory", "the middle east", "club passim",
    "museum of fine arts", "isabella stewart gardner", "ica boston", "institute of contemporary art",
    "museum of science", "harvard art museums", "wbur cityspace", "coolidge corner", "brattle",
)
# Big-name signal for the list's top slots
MUSEUM_NIGHT_RE = re.compile(r"(?i)\b(?:after dark|late nites?|at night|third thursday|first friday|night at the)\b")

SOCIAL_SOURCES = ("luma", "partiful", "meetup", "heylo", "skip the small talk", "make friends")
SKIP_TITLE_RE = re.compile(
    r"(?i)\b(?:class|classes|course|workshop|intro to|bootcamp|training|certification|summit|"
    r"conference|strategy|leadership|founders?|investors?|webinar|yoga|early bird|field trips?|"
    r"pre-?show|q&a ticket|vip|parking|upgrade|recital|seminar|prep|students?|member morning|"
    r"members? only|camp|courtyard & historic|general admission|vision board(?:ing)?|"
    r"preliminary round|contest round|semifinal|figure drawing)\b")
# NEC's small halls host student recitals and studio classes, not public headliners
MINOR_ROOMS_RE = re.compile(r"(?i)\bNEC \((?:Williams|Burnes|Keller|Brown|Pierce|Plimpton)|\bCCAE\b|Cambridge Center for Adult Education")
NEARBY_TOWNS = {"brookline", "newton", "watertown", "medford", "arlington", "belmont", "malden",
                "everett", "chelsea", "quincy", "milton", "waltham", "winchester", "lexington"}
# Sources whose whole calendar is for kids (Audubon and the Aquarium also run adult programs)
FAMILY_SOURCES = ("children's museum", "puppet showplace", "little muse", "library (kids)", "eventbrite (kids")


def _week_start(arg):
    if arg:
        d = date.fromisoformat(arg)
        return d - timedelta(days=d.weekday())
    today = datetime.now(EASTERN).date()
    return today + timedelta(days=(7 - today.weekday()) or 7)  # next Monday


def _clean_title(name):
    t = re.sub(r"\s+", " ", unescape(name or "")).strip()
    t = re.sub(r"^(?:The )?Bowery Presents:?\s+", "", t)
    return t if len(t) <= 80 else t[:77].rstrip() + "…"


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
        return ""  # "Check link", "Tickets", "TBA"
    return re.sub(r"\.00\b", "", p)


def _time(e):
    t = e["_time"]
    return "" if (t.hour, t.minute) == (0, 0) else t.strftime("%-I:%M%p").replace(":00", "")


def _venue(e):
    v = re.sub(r"\s+", " ", e.get("venue") or e.get("_source_venue") or "").strip()
    v = re.sub(r"\s+presented by .*$", "", v, flags=re.I)
    v = re.sub(r"\s*\((?:Boston|Cambridge|Somerville)\)$", "", v)
    v = re.sub(r"^Downtown Boston - ", "", v)
    v = re.sub(r"^Main Stage, ", "", v)
    return v


def _area(e):
    venue, source = _venue(e), e.get("_source_venue") or ""
    words = lambda v: {w for w in re.findall(r"[a-z]{3,}", v.lower())} - {
        "the", "boston", "hall", "center", "theatre", "theater", "room", "presented", "citizens"}
    g = resolve_event_geo(e)
    if g and g.get("neighborhood") and words(venue) & words(g.get("venue") or ""):
        area = g["neighborhood"]          # this venue's own pin: "Boston Athenaeum" -> Beacon Hill
    elif words(venue) & words(source):
        city = _event_city(e.get("venue"), source, e)
        area = _hub_place_label(city, e).split(",")[0]
    else:
        return ""                         # somewhere other than the source's home venue; don't guess
    area = area.replace(" Square", " Sq")
    return "" if area in ("Greater Boston",) or area.lower() in venue.lower() else area


def _line(e, day_prefix=False, when=None):
    """* **[Title](url)** @ Venue @ 7PM · $25 · Harvard Sq
         Blurb."""
    head = f"{e['_time'].strftime('%a')} · " if day_prefix else ""
    parts = [f"{head}{_link(_clean_title(e['name']), e.get('url'))} @ {_venue(e)}"]
    t = when if when is not None else _time(e)
    if t:
        parts[0] += f" @ {t}"
    extra = [x for x in (_price(e), _area(e)) if x]
    s = "* " + parts[0] + (" · " + " · ".join(extra) if extra else "")
    note = (e.get("_highlight") or {}).get("note")
    if note:
        s += f"  \n  {note}"
    return s


def _in_area(e, family=False):
    city = _event_city(e.get("venue"), e.get("_source_venue"), e)
    if city in ("boston", "cambridge", "somerville"):
        return True
    loc = (e.get("locality") or "").strip().lower()
    if loc in ("boston", "cambridge", "somerville") or re.search(
            r"(?i)\b(?:boston|cambridge|somerville),? ma\b", e.get("address") or ""):
        return True
    if family and re.match(r"(?i)boston\b", e.get("venue") or e.get("_source_venue") or ""):
        return True   # "Boston Children's Museum", "Boston Nature Center"
    return family and loc in NEARBY_TOWNS


def _is_kids(e):
    name = e.get("name") or ""
    if re.search(r"(?i)\badults?\b", name):
        return False
    src = (e.get("_source_venue") or "").lower()
    return is_kid_family_event(name, e.get("venue")) or any(k in src for k in FAMILY_SOURCES)


def _is_library(e):
    return "library" in f"{e.get('venue')} {e.get('_source_venue')}".lower()


def _is_social(e):
    src = (e.get("_source_venue") or "").lower()
    return any(k in src for k in SOCIAL_SOURCES)


def _is_major(e):
    blob = f"{e.get('venue')} {e.get('_source_venue')}".lower()
    return any(v in blob for v in MAJOR_VENUES)


def build(week_start):
    with open(os.path.join(ROOT, "events.json"), encoding="utf-8") as f:
        venues = json.load(f)["venues"]
    dated, _, _ = group_by_date(copy.deepcopy(venues))
    recurring = compute_recurring(dated)
    highlights = _load_highlights()
    week = [week_start + timedelta(days=i) for i in range(7)]
    by_day = {d: evs for d, evs in dated if d in week}
    total = sum(len(v) for v in by_day.values())

    def is_recurring(e):
        return ((e.get("name") or "").strip().lower(), e.get("_source_venue") or "",
                (e.get("venue") or "").strip().lower()) in recurring

    # Group each show's nights: 3+ nights is a run ("All week"), otherwise list it on its first night
    runs = defaultdict(list)
    for d in week:
        for e in by_day.get(d, []):
            key = re.sub(r"\s+[-–]\s+boston\b.*$", "", e["name"].lower())   # "Hadestown - Boston"
            runs[(re.sub(r"\W+", " ", key).strip(), _venue(e).lower())].append(e)

    pool, run_pool = [], []
    for evs in runs.values():
        e = evs[0]
        nights = sorted({x["_time"].date() for x in evs})
        e["_nights"] = nights
        bucket = category_bucket(_effective_category(e))
        if bucket in SKIP_BUCKETS:
            continue
        e["_bucket"] = bucket
        e["_highlight"] = _get_event_highlight(e, highlights)
        t = e["_time"]
        if not e["_highlight"]:
            if SKIP_TITLE_RE.search(e["name"]) or TECH_EVENT_RE.search(e["name"]) or MINOR_ROOMS_RE.search(
                    f"{e.get('venue')} {e.get('_source_venue')}"):
                continue
            if "rsvp for address" in (e.get("venue") or "").lower() or e.get("_venue_unknown"):
                continue
            if (t.hour, t.minute) != (0, 0) and t.hour < 7:
                continue
            m = re.search(r"\$(\d+)", str(e.get("price") or ""))
            if m and int(m.group(1)) > 100 and bucket not in ("Music & nightlife", "Stage"):
                continue
        e["_kids"] = _is_kids(e)
        if not _in_area(e, family=e["_kids"]):
            continue
        if len(nights) >= 3 and bucket in ("Stage", "Arts & culture") and not is_recurring(e):
            run_pool.append(e)
        else:
            pool.append(e)

    def score(e):
        s = 0
        if e.get("_highlight"):
            s += 60
        if _is_major(e):
            s += 40
        if MUSEUM_NIGHT_RE.search(e["name"]):
            s += 25
        if not is_recurring(e):
            s += 20
        if _is_social(e):
            s -= 30          # meetups get their own section
        src = (e.get("_source_venue") or "").lower()
        if src not in ("ticketmaster", "seatgeek", "the boston calendar", "do617") and not src.startswith("eventbrite"):
            s += 5
        s += 2 * min(len(e.get("_alt_sources") or []), 3)   # listed by several sources: more notable
        if not _time(e):
            s -= 15
        return s

    pool.sort(key=lambda e: (-score(e), e["_time"]))
    run_pool.sort(key=lambda e: (-score(e), e["_time"]))
    used, venue_count = set(), Counter()

    def take(e):
        used.add(id(e))
        venue_count[_venue(e).lower()] += 1

    def ok_venue(e, cap=PER_VENUE_WEEK):
        return venue_count[_venue(e).lower()] < cap

    runs_pick = []
    for e in run_pool:
        if len(runs_pick) < RUN_PICKS and ok_venue(e):
            runs_pick.append(e); take(e)

    kids = sorted((e for e in pool if e["_kids"]), key=lambda e: (_is_library(e), -score(e), e["_time"]))
    kids_pick, n_lib = [], 0
    for e in kids:
        if len(kids_pick) < KIDS_PICKS and ok_venue(e) and not (_is_library(e) and n_lib >= 3):
            kids_pick.append(e); take(e); n_lib += _is_library(e)

    social_pick = []
    for e in pool:
        if len(social_pick) >= SOCIAL_PICKS:
            break
        if id(e) not in used and _is_social(e) and not e["_kids"] and ok_venue(e, 1):
            social_pick.append(e); take(e)

    days = {}
    for d in week:
        picks, per_bucket = [], Counter()
        for e in pool:
            if len(picks) >= PER_DAY:
                break
            if e["_time"].date() != d or id(e) in used or _is_library(e) or e["_kids"] or _is_social(e):
                continue
            cap = 5 if e["_bucket"] == "Music & nightlife" else 3
            if per_bucket[e["_bucket"]] >= cap or not ok_venue(e):
                continue
            picks.append(e); take(e); per_bucket[e["_bucket"]] += 1
        days[d] = sorted(picks, key=lambda e: e["_time"])

    free_pick, free_kind = [], Counter()
    for e in pool:
        if len(free_pick) >= FREE_PICKS:
            break
        if id(e) in used or not _is_event_free(e) or _is_library(e) or e["_kids"] or is_recurring(e):
            continue
        kind = "trivia" if re.search(r"(?i)trivia|bingo", e["name"]) else e["_bucket"]
        if ok_venue(e) and free_kind[kind] < (1 if kind == "trivia" else 4):
            free_pick.append(e); take(e); free_kind[kind] += 1

    end = week[-1]
    span = f"{week_start.strftime('%b %-d')}–{end.strftime('%-d') if end.month == week_start.month else end.strftime('%b %-d')}"
    title = f"Things to do in Boston this week ({span}): concerts, comedy, free stuff, kids & more"

    def nights_label(e):
        ds = e["_nights"]
        return f"{ds[0].strftime('%a')}–{ds[-1].strftime('%a')}" if len(ds) > 1 else ds[0].strftime("%a")

    out = [
        f"Hi Boston! Here's what's on **Monday {week_start.strftime('%b %-d')} through Sunday "
        f"{end.strftime('%b %-d')}** around Boston, Cambridge & Somerville: the big shows, plus free "
        f"stuff, kids' events and ways to meet people. Please add anything I missed below!",
        "",
    ]
    for d in week:
        if days[d]:
            out += [f"**{d.strftime('%A').upper()}, {d.strftime('%b %-d').upper()}**", ""]
            out += [_line(e) for e in days[d]]
            out.append("")
    if runs_pick:
        out += ["**🎭 RUNNING ALL WEEK**", ""]
        out += [_line(e, when=nights_label(e)) for e in sorted(runs_pick, key=lambda e: e["_time"])]
        out.append("")
    if free_pick:
        out += ["**🆓 FREE THIS WEEK**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(free_pick, key=lambda e: e["_time"])]
        out.append("")
    if kids_pick:
        out += ["**👶 KIDS & FAMILIES**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(kids_pick, key=lambda e: e["_time"])]
        out += ["", f"Story times, playgroups & more: [kids & family calendar]({SITE}/kids-family-events-boston/)", ""]
    if social_pick:
        out += ["**🤝 MEET PEOPLE**", ""]
        out += [_line(e, day_prefix=True) for e in sorted(social_pick, key=lambda e: e["_time"])]
        out.append("")
    shown = len(used)
    out += [
        "---",
        "",
        f"That's {shown} of the {total:,} events on this week. Everything else is searchable by "
        f"neighborhood, T line, free or kids at **[wickedbostonevents.com]({SITE})** "
        f"(independent and ad-free; it pulls from 200+ venue, library, museum and community calendars daily).",
    ]
    body = "\n".join(out) + "\n"
    needs_blurb = [e for d in week for e in days[d] if _is_major(e) and not e.get("_highlight")]
    return title, body, needs_blurb


def main():
    week_start = _week_start(sys.argv[1] if len(sys.argv) > 1 else None)
    title, body, needs_blurb = build(week_start)
    out_dir = os.path.join(ROOT, "reddit")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"week-of-{week_start.isoformat()}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"<!-- Title: {title} -->\n\n{body}")
    print(f"Title: {title}")
    print(f"Body:  {path} ({len(body):,} characters; Reddit allows 40,000)")
    if needs_blurb:
        print(f"\n{len(needs_blurb)} headliners have no blurb yet (add to highlights.json and rerun):")
        for e in needs_blurb:
            print(f"  {e['_time'].strftime('%a %m-%d')}  {_clean_title(e['name'])} @ {_venue(e)}")


if __name__ == "__main__":
    main()
