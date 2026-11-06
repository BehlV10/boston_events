"""Boston Shows (bostonshows.org) as a last resort, after every other source has run.

Venues' own calendars come first. For the next two weeks this fills two gaps from Boston Shows'
hand-kept listings:
  * a show at a venue where we have nothing that day is added (credited to Boston Shows);
  * a show we already have but without a price gets Boston Shows' price, when the listing
    clearly matches (same day, same venue, similar title).
Venues we can't read at all (scrapers.BOSTON_SHOWS_GAP_VENUES) come in through their own source.
"""
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

SOURCE_NAME = "Boston Shows (shows we were missing)"
URL = "https://bostonshows.org/"
WINDOW_DAYS = 14
_PAGE = {"html": None, "at": 0.0}
_GENERIC = {"live", "music", "band", "jazz", "session", "sessions", "acoustic", "open", "mic", "night", "dj", "concert"}


def get_html(session, ua, max_age=1800):
    """The Boston Shows page (about 6 MB, the whole calendar), fetched once per crawl and shared by
    the unreadable-venues source and the fill-in step."""
    import time
    if _PAGE["html"] is None or time.time() - _PAGE["at"] > max_age:
        r = session.get(URL, headers={"User-Agent": ua}, timeout=30)
        r.raise_for_status()
        _PAGE["html"], _PAGE["at"] = r.text, time.time()
    return _PAGE["html"]

_STOP = set("the a an and at with w feat featuring ft of in on live music presents show night tour plus "
            "special guest guests s".split())


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"&", " and ", s).replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _toks(s):
    out = set()
    for t in _norm(s).split():
        if t in _STOP or len(t) < 2:
            continue
        out.add(t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t)
    return out


def _minutes(t):
    m = re.match(r"\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m", t or "", re.I)
    if not m:
        return None
    return (int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)) * 60 + int(m.group(2) or 0)


def _price(info):
    first = (info or "").split(" / ")[0].strip()
    if re.fullmatch(r"free", first, re.I):
        return "Free"
    return first if "$" in first else None


def parse(html):
    """bostonshows.org's home page -> one dict per listed show."""
    soup = BeautifulSoup(html, "html.parser")
    shows = []
    for day in soup.select("div.date-events[data-date]"):
        for tr in day.select("tr.event"):
            title = tr.select_one(".event-title")
            start = tr.select_one(".event-start")
            if not (title and start):
                continue
            a = title.find("a", href=True)
            info = tr.select_one(".event-info")
            info = info.get_text(" ", strip=True) if info else ""
            venue_div = tr.select_one(".event-venue")
            hood = re.search(r"\(([^)]*)\)\s*$", venue_div.get_text(" ", strip=True)) if venue_div else None
            shows.append({
                "date": day["data-date"], "start": _minutes(start.get_text(" ", strip=True)),
                "title": title.get_text(" ", strip=True), "url": a["href"] if a else URL,
                "venue": (tr.get("data-venue") or "").strip(), "hood": hood.group(1) if hood else "",
                "genre": tr.get("data-genre") or "", "info": info, "price": _price(info),
                "recurring": tr.get("data-recurring") == "True",
            })
    return shows


def _km(a, b):
    dlat = math.radians(b[0] - a[0])
    dlng = math.radians(b[1] - a[1]) * math.cos(math.radians(a[0]))
    return 6371 * math.hypot(dlat, dlng)


class _Ours:
    """Our events in the window, by local date, with what we need to match them."""

    def __init__(self, results, tz, geo):
        self.by_date = {}
        for r in results:
            src = r.get("venue") or ""
            for e in r.get("events") or []:
                try:
                    dt = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00")).astimezone(tz)
                except (TypeError, ValueError):
                    continue
                g = geo({**e, "_source_venue": src}) or {}
                self.by_date.setdefault(dt.date().isoformat(), []).append({
                    "ev": e, "min": dt.hour * 60 + dt.minute, "toks": _toks(e.get("name")),
                    "vtoks": _toks(e.get("venue") or "") | _toks(src),
                    "pt": (g["lat"], g["lng"]) if g.get("lat") is not None else None,
                })


def _first_tok(s):
    toks = [t for t in _norm(s).split() if t not in _STOP and len(t) > 1]
    return toks[0] if toks else None


def apply(results, html, tz, geo, skip_venues=(), now=None, days=WINDOW_DAYS):
    """Fill prices in `results` (in place) and return the source entry with shows we were missing.

    Matching is deliberately strict about titles: nearby venues share a map point (Davis Square,
    the Symphony Hall block), so place + time alone would hand one show's price to another.
      * same show = same day, same place (same building or venue name), and the titles share half
        their words or the headliner's name; or the same title and start time anywhere;
      * a generic listing of ours at the same venue name and time ("Live Music @ The Row Hotel")
        also counts as covered (no price copied), so it isn't added twice.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    first, last = now.date().isoformat(), (now + timedelta(days=days)).date().isoformat()
    ours = _Ours(results, tz, geo)
    skip = {v.lower() for v in skip_venues}
    added, seen, priced = [], set(), 0
    for s in parse(html):
        if not (first <= s["date"] <= last) or s["venue"].lower() in skip:
            continue
        key = (_norm(s["title"]), s["date"], s["start"])
        if key in seen:
            continue
        seen.add(key)
        g = geo({"venue": s["venue"]}) or {}
        pt = (g["lat"], g["lng"]) if g.get("lat") is not None else None
        vt, tt, head = _toks(s["venue"]), _toks(s["title"]), _first_tok(s["title"])
        day = ours.by_date.get(s["date"], [])

        def near_time(c):
            return s["start"] is not None and abs(c["min"] - s["start"]) <= 45

        def overlap(c):
            return len(tt & c["toks"]) / max(1, min(len(tt), len(c["toks"]) or 1)) if tt else 0

        def same_building(c):
            return bool(pt and c["pt"] and _km(pt, c["pt"]) <= 0.03)

        def same_name(c):
            return bool(vt) and len(vt & c["vtoks"]) / len(vt) >= 0.5

        def same_title(c):
            return overlap(c) >= 0.5 or (head is not None and (head in c["toks"] or _first_tok(c["ev"].get("name")) in tt))

        matches = [c for c in day if (same_building(c) or same_name(c)) and same_title(c)]
        matches += [c for c in day if c not in matches and overlap(c) >= 0.6 and near_time(c)]
        if matches:
            if s["price"]:
                for c in matches:
                    if not (c["ev"].get("price") or "").strip():
                        c["ev"]["price"] = s["price"]
                        priced += 1
            continue
        # A generic listing of ours in the same slot ("Live Music @ The Row Hotel") is the same
        # show; a different, specific title at a busy venue (MIT, the Armory) is not.
        def generic_or_related(c):
            return len(c["toks"] - c["vtoks"] - _GENERIC) <= 1 or overlap(c) >= 0.2
        if any(same_name(c) and near_time(c) and generic_or_related(c) for c in day):
            continue
        # The venue lists this one-off show on a nearby date (Passim: Power Outage Party on the 20th,
        # Boston Shows: the 17th): the venue's own date wins. Weekly sessions are left alone.
        y0, m0, d0 = map(int, s["date"].split("-"))
        around = [ours.by_date.get((datetime(y0, m0, d0) + timedelta(days=k)).date().isoformat(), [])
                  for k in range(-7, 8) if k]
        if not s["recurring"] and any((same_building(c) or same_name(c)) and same_title(c) for cs in around for c in cs):
            continue
        # Boston Shows sometimes lists one show twice under slightly different titles
        slot = (s["date"], s["start"], (g.get("venue") or s["venue"]).lower(), head)
        if slot in seen:
            continue
        seen.add(slot)
        h, mi = divmod(s["start"] if s["start"] is not None else 19 * 60, 60)
        y, mo, d = map(int, s["date"].split("-"))
        added.append({
            "name": s["title"],
            "date": datetime(y, mo, d, h, mi, tzinfo=tz).astimezone(timezone.utc).isoformat(),
            "url": s["url"],
            "venue": g.get("venue") or s["venue"],
            "price": s["price"],
            "category": "music",
            "description": f"Listing via Boston Shows (bostonshows.org). {s['info']}".strip(),
        })
    return {"venue": SOURCE_NAME, "url": URL, "events": added, "error": None, "cached": False,
            "duration": 0.0, "priced_from_boston_shows": priced}
