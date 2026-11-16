#!/usr/bin/env python3
"""Copy the picks from a Reddit roundup post into highlights.json, so the site shows the same picks.

    python scripts/sync_post_highlights.py reddit/weekday_post_nov16-20.md [--year 2026] [--dry-run]

Each `* **[Title](url)** @ Venue · ...` line under a `## 📅 MONDAY, NOV 16` heading becomes a
one-day highlights.json entry (badge "Editor's Pick" unless the event already has one), with the
indented line under it as the note. Picks are matched to the scraped listing in events.json by URL,
then by title, so the entry uses the listing's own name. Picks that already have a highlight that day
are left alone; picks with no listing that day are reported and skipped.
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from template import EASTERN, _get_event_highlight  # noqa: E402

HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "highlights.json")
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
DAY_RE = re.compile(r"^##\s+\S*\s*[A-Z]+,\s+([A-Z]{3})[A-Z]*\s+(\d{1,2})\b")
PICK_RE = re.compile(r"^\*\s+\*\*\[(.+?)\]\((\S+?)\)\*\*\s+@\s+(.+?)\s+·")


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _url_key(u):
    u = (u or "").strip().lower().split("#")[0]
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.split("?")[0].rstrip("/")


def parse_post(text, year):
    """[(date, title, url, venue, note), ...] in post order."""
    picks, day, last = [], None, None
    for line in text.splitlines():
        m = DAY_RE.match(line)
        if m:
            day = date(year, MONTHS[m.group(1)], int(m.group(2)))
            continue
        m = PICK_RE.match(line)
        if m and day:
            title = re.sub(r"^[☆★✨*\s]+", "", m.group(1)).strip()
            last = [day, title, m.group(2), m.group(3).strip(), ""]
            picks.append(last)
            continue
        if last and line.startswith((" ", "\t")) and line.strip() and not last[4]:
            last[4] = line.strip()
        elif not line.strip() or line.startswith("#"):
            last = None
    return [tuple(p) for p in picks]


def _event_day(e):
    try:
        dt = datetime.fromisoformat(str(e.get("date") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt.astimezone(EASTERN) if dt.tzinfo else dt).date()


def load_events_by_day(path=EVENTS_FILE):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    by_day = {}
    for v in data.get("venues", []):
        for e in v.get("events", []):
            d = _event_day(e)
            if d:
                by_day.setdefault(d, []).append(dict(e, _source_venue=v.get("venue")))
    return by_day


def find_listing(day_events, title, url):
    """The day's listing for a post pick: same link and mostly the same title, else the title alone."""
    uk = _url_key(url)
    ft = _fold(title)
    words = set(ft.split()) - {"the", "a", "an", "of", "and", "at", "with", "w"}

    def overlap(e):
        return len(words & set(_fold(e.get("name")).split())) / max(len(words), 1)

    # A venue's calendar page can be the link for all its events, so the title must agree too.
    url_hits = [e for e in day_events if uk and _url_key(e.get("url")) == uk and overlap(e) >= 0.5]
    if url_hits:
        return max(url_hits, key=overlap)
    hits = [e for e in day_events if ft and ft in _fold(e.get("name"))]
    if not hits:  # post titles are often trimmed ("Celtics vs. Magic"): every title word in the name
        hits = [e for e in day_events if words and words <= set(_fold(e.get("name")).split())]
    return min(hits, key=lambda e: len(e.get("name") or "")) if hits else None


def _common_name(names):
    """The longest stretch of whole words every listing's name shares ("Pouya" for "Pouya" and
    "Pouya - The Foreverglades Tour"), lowercased. Falls back to the shortest name."""
    low = [re.sub(r"\s+", " ", n).strip().lower() for n in names]
    base = min(low, key=len)
    words = base.split(" ")
    for size in range(len(words), 0, -1):
        for i in range(len(words) - size + 1):
            cand = " ".join(words[i:i + size]).strip(" -–:,()")
            if len(re.sub(r"[^a-z0-9]", "", cand)) >= 4 and all(cand in n for n in low):
                return cand
    return base


GENERIC = {"the", "a", "an", "of", "and", "at", "with", "w", "vs", "live", "night", "show", "presents", "tour",
           "boston", "cambridge", "somerville", "comedy", "concert", "party", "music", "free", "in", "on", "for", "by"}


def _key_words(text):
    return set(_fold(text).split()) - GENERIC


VENUE_GENERIC = {"the", "a", "of", "at", "and", "boston", "cambridge", "somerville", "club", "bar", "hall", "theatre",
                 "theater", "cafe", "center", "music", "live", "room", "main", "stage", "pub", "brewing"}


def _venue_words(x):
    return set(_fold(f"{x.get('venue') or ''} {x.get('_source_venue') or ''}").split()) - VENUE_GENERIC


def listing_cluster(day_events, e, title, venue=""):
    """The day's listings of the same show as `e`: within 90 minutes, carrying half or more of the
    pick's key words (see below), and at the same venue (or listed with no venue at the same start time)."""
    t0 = _with_time(e).get("_time")
    words = _key_words(title) & _key_words(e.get("name")) or _key_words(e.get("name"))
    vwords = (set(_fold(venue).split()) - VENUE_GENERIC) | _venue_words(e)
    out = []
    for x in day_events:
        t = _with_time(x).get("_time")
        if not (t0 and t and abs((t - t0).total_seconds()) <= 90 * 60):
            continue
        xw = _key_words(x.get("name"))
        # one title's key words inside the other's ("Pouya" / "Pouya - The Foreverglades Tour"),
        # not just one shared word ("Fresh Goofs" / "Certified Fresh" at the same club)
        if not (words and xw and (words <= xw or xw <= words or len(words & xw) / len(words | xw) >= 0.6)):
            continue
        xv = _venue_words(x)
        if (xv & vwords) or (not (x.get("venue") or "").strip() and t == t0):
            out.append(x)
    return out if any(x is e for x in out) else out + [e]


def match_name(cluster, e, title):
    """What highlights.json should look for in the name: the words every listing shares, if they
    still say which show it is; else the listing's own name."""
    common = _common_name([x["name"] for x in cluster])
    if _key_words(common) & (_key_words(title) | _key_words(e.get("name"))):
        return common
    return re.sub(r"\s+", " ", e["name"]).strip().lower()


def _with_time(e):
    try:
        dt = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
        return dict(e, _time=dt if dt.tzinfo else dt.replace(tzinfo=EASTERN))
    except ValueError:
        return e


def _matches(m, x, d):
    h = {"match": m, "start_date": d.isoformat(), "expires": d.isoformat()}
    return bool(_get_event_highlight(_with_time(dict(x, venue=x.get("venue") or x.get("_source_venue"))), [h]))


def safe_match(day_events, cluster, e, name, venue, d):
    """A highlights.json match that hits this show's listings and nothing else that day. A short
    shared name ("magic" from "Orlando Magic at Boston Celtics") can also hit "Sweet Magic" at a
    library; then fall back to the listing's full name, then add the venue."""
    ids = {id(x) for x in cluster}
    full = re.sub(r"\s+", " ", e["name"]).strip().lower()
    tries = []
    for nm in (name, full):
        tries.append({"name_contains": nm})
        if venue:
            tries.append({"name_contains": nm, "venue_contains": venue})
    for m in tries:
        hits = [x for x in day_events if _matches(m, x, d)]
        if any(id(x) == id(e) for x in hits) and all(id(x) in ids for x in hits):
            return m
    return {"name_contains": full, "venue_contains": venue} if venue else {"name_contains": full}


def sync(post_text, year, highlights, by_day):
    """Returns (new_entries, already, missing)."""
    new, already, missing = [], [], []
    taken = {h.get("id") for h in highlights}
    for d, title, url, venue, note in parse_post(post_text, year):
        e = find_listing(by_day.get(d, []), title, url)
        if not e:
            missing.append((d, title, venue))
            continue
        ev = _with_time(dict(e, venue=e.get("venue") or e.get("_source_venue")))
        if _get_event_highlight(ev, highlights + new):
            already.append((d, title))
            continue
        cluster = listing_cluster(by_day.get(d, []), e, title, venue)
        name = match_name(cluster, e, title)
        v_low = venue.lower()
        slug = re.sub(r"[^a-z0-9]+", "-", _fold(title))[:40].strip("-")
        hid = f"{d.isoformat()}-{slug}"
        n = 2
        while hid in taken:
            hid, n = f"{d.isoformat()}-{slug}-{n}", n + 1
        taken.add(hid)
        same_venue = all(v_low in (x.get("venue") or x.get("_source_venue") or "").lower() for x in cluster)
        match = safe_match(by_day.get(d, []), cluster, e, name, venue if same_venue else None, d)
        entry = {"id": hid, "match": match, "badge": "Editor's Pick"}
        if note:
            entry["note"] = note
        entry.update(start_date=d.isoformat(), expires=d.isoformat(), from_post=True)
        new.append(entry)
    return new, already, missing


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("post")
    ap.add_argument("--year", type=int, default=datetime.now(EASTERN).year)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    with open(args.post, encoding="utf-8") as f:
        text = f.read()
    with open(HIGHLIGHTS_FILE, encoding="utf-8") as f:
        highlights = json.load(f)
    new, already, missing = sync(text, args.year, highlights, load_events_by_day())
    for h in new:
        print(f"add   {h['start_date']}  {h['match']['name_contains']}")
    print(f"{len(new)} added, {len(already)} already highlighted, {len(missing)} not found in events.json")
    for d, t, v in missing:
        print(f"  not found: {d}  {t} @ {v}")
    if new and not args.dry_run:
        with open(HIGHLIGHTS_FILE, "w", encoding="utf-8") as f:
            json.dump(highlights + new, f, indent=2)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
