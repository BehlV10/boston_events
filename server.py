#!/usr/bin/env python3
"""Boston Events — scrape a handful of venue sites and serve a simple list at localhost:3000."""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()


PORT = int(os.environ.get("PORT", 3000))
CACHE_SECONDS = 15 * 60
EASTERN = ZoneInfo("America/New_York")

UA_SAFARI = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
UA_CHROME = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_soup(url, ua):
    resp = requests.get(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def parse_crystal_ballroom_date(text):
    """Parse 'Tue, Apr 21, 2026 Show 7:00 pm Doors 6:30 pm All Ages'."""
    if not text:
        return None
    m = re.search(
        r"([A-Za-z]{3}),?\s+([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})"
        r"(?:.*?Show\s+(\d{1,2}):(\d{2})\s*(am|pm))?",
        text, re.IGNORECASE,
    )
    if not m:
        return None
    _, mon, day, year, hh, mm, ampm = m.groups()
    hour = int(hh) if hh else 19
    if ampm and ampm.lower() == "pm" and hour != 12:
        hour += 12
    if ampm and ampm.lower() == "am" and hour == 12:
        hour = 0
    try:
        dt = datetime.strptime(f"{mon} {day} {year}", "%b %d %Y").replace(
            hour=hour, minute=int(mm) if mm else 0, tzinfo=EASTERN,
        )
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def scrape_crystal_ballroom(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    for article in soup.select("article.event-grid-item, article.event"):
        a = article.select_one(".entry-title a") or article.select_one("h2 a")
        if not a:
            continue
        name = a.get_text(strip=True)
        href = a.get("href", "")
        meta = article.select_one(".event-meta")
        meta_text = re.sub(r"\s+", " ", meta.get_text(" ", strip=True)) if meta else ""
        events.append({
            "name": name,
            "date": parse_crystal_ballroom_date(meta_text) or meta_text or None,
            "url": urljoin(url, href) if href else url,
        })
    return events


def parse_coolidge_date(text):
    """Parse 'Mon 4/20'-style dates; guess year based on current date."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    now = datetime.now(EASTERN)
    try:
        candidate = datetime(now.year, month, day, 19, 0, tzinfo=EASTERN)
    except ValueError:
        return None
    if (candidate - now).days < -1:
        candidate = candidate.replace(year=now.year + 1)
    return candidate.astimezone(timezone.utc).isoformat()


def scrape_coolidge(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    for card in soup.select(".film-card.film-card__narrow"):
        a = card.select_one(".film-card__title a") or card.select_one("h2 a, h3 a")
        if not a:
            continue
        name = a.get_text(strip=True) or a.get("title", "")
        if not name:
            continue
        href = a.get("href") or ""
        date_el = card.select_one(".datepicker__date")
        date_text = date_el.get_text(strip=True) if date_el else ""
        events.append({
            "name": name,
            "date": parse_coolidge_date(date_text) or date_text or None,
            "url": urljoin(url, href) if href else url,
        })
    return events


def _parse_eventbrite_card_date(text):
    """'Sat, Jul 12 •  1:30 PM' → UTC ISO (year inferred)."""
    if not text:
        return None
    m = re.search(
        r"(?:[A-Za-z]{3},?\s+)?([A-Za-z]{3})\s+(\d{1,2})(?:,?\s+(\d{4}))?"
        r"(?:.*?(\d{1,2}):(\d{2})\s*(AM|PM))?",
        text,
    )
    if not m:
        return None
    mon, day, year, hh, mm, ampm = m.groups()
    now = datetime.now(EASTERN)
    year = int(year) if year else now.year
    try:
        dt = datetime.strptime(f"{mon} {day} {year}", "%b %d %Y")
    except ValueError:
        return None
    hour = 19
    if hh:
        hour = int(hh)
        if ampm and ampm.upper() == "PM" and hour != 12:
            hour += 12
        if ampm and ampm.upper() == "AM" and hour == 12:
            hour = 0
    dt = dt.replace(hour=hour, minute=int(mm) if mm else 0, tzinfo=EASTERN)
    if not year or (dt - now).days < -1:
        dt = dt.replace(year=now.year + 1)
    return dt.astimezone(timezone.utc).isoformat()


def scrape_eventbrite_org(url, ua):
    """Parse Eventbrite organizer page cards (used for Aeronaut, Versus)."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for a in soup.select('a[href*="/e/"]'):
        href = a.get("href", "").split("?")[0]
        if not href:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue
        if href in seen:
            continue
        card = a
        for _ in range(5):
            card = card.parent
            if card is None:
                break
            classes = " ".join(card.get("class", []))
            if "event-card" in classes or "eds-event-card" in classes or card.name == "section":
                break
        text = (card or a).get_text(" • ", strip=True) if card else a.get_text(" ", strip=True)
        date_iso = _parse_eventbrite_card_date(text)
        price = None
        p = re.search(r"(Free|From\s*\$[\d.]+|\$[\d.]+(?:\s*[–-]\s*\$?[\d.]+)?)", text)
        if p:
            price = p.group(1).replace("From ", "").strip()
        venue = None
        v = re.search(r"•\s*([A-Z][^•]*?(?:Brewing|Hall|Theater|Theatre|Club|House|Pub|Cafe|Bar|Center|Room|Lounge|Studio|Space|Library|Park)[^•]*?)\s*(?:•|$)", text)
        if v:
            venue = v.group(1).strip()
        seen.add(href)
        events.append({
            "name": title,
            "date": date_iso,
            "url": urljoin(url, href),
            "venue": venue,
            "price": price,
        })
    return events


def scrape_eventbrite_search(url, ua):
    """Parse Eventbrite Boston discovery page via ItemList JSON-LD."""
    soup = fetch_soup(url, ua)
    events = []
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(block.string or "")
        except Exception:
            continue
        if not isinstance(d, dict) or d.get("@type") != "ItemList":
            continue
        for item in d.get("itemListElement") or []:
            ev = item.get("item") or {}
            if ev.get("@type") != "Event":
                continue
            iso = ev.get("startDate")
            if iso and "T" not in iso:
                iso = f"{iso}T19:00:00-04:00"
            try:
                iso = datetime.fromisoformat(iso).astimezone(timezone.utc).isoformat() if iso else None
            except ValueError:
                iso = None
            loc = ev.get("location") or {}
            venue = loc.get("name") if isinstance(loc, dict) else None
            events.append({
                "name": ev.get("name"),
                "date": iso,
                "url": ev.get("url"),
                "venue": venue,
                "price": None,
                "description": (ev.get("description") or "")[:200],
            })
    return events


def scrape_bpl(url, ua):
    """Boston Public Library via BiblioCommons gateway — paginate 5 pages (~50 events)."""
    events = []
    for page in range(1, 6):
        resp = requests.get(
            "https://gateway.bibliocommons.com/v2/libraries/bpl/events",
            params={"page": page},
            headers={"User-Agent": ua, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        ids = (data.get("events") or {}).get("items") or []
        ev_entities = (data.get("entities") or {}).get("events") or {}
        if not ids:
            break
        for eid in ids:
            ev = ev_entities.get(eid) or {}
            d = ev.get("definition") or {}
            start = d.get("start")
            if start:
                try:
                    start = datetime.fromisoformat(start).replace(tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
                except ValueError:
                    start = None
            events.append({
                "name": d.get("title"),
                "date": start,
                "url": f"https://bpl.bibliocommons.com/events/{eid}",
                "venue": "Boston Public Library",
                "price": "Free",
            })
    return events


_BC_TIME_RE = re.compile(
    r"(Sun|Mon|Tue|Wed|Thu|Fri|Sat)[a-z]*,\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(\d{1,2}),\s+(\d{4})\s+(\d{1,2})(?::(\d{2}))?([ap])",
    re.IGNORECASE,
)
_BC_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1
)}


def _parse_boston_calendar_time(text):
    m = _BC_TIME_RE.search(text or "")
    if not m:
        return None
    _, mon, day, year, hour, minute, ampm = m.groups()
    hour = int(hour)
    minute = int(minute or 0)
    if ampm.lower() == "p" and hour != 12:
        hour += 12
    if ampm.lower() == "a" and hour == 12:
        hour = 0
    try:
        dt = datetime(int(year), _BC_MONTHS[mon.title()[:3]], int(day), hour, minute, tzinfo=EASTERN)
    except (ValueError, KeyError):
        return None
    return dt.astimezone(timezone.utc).isoformat()


_BC_EXTERNAL_RE = re.compile(r"event\s*website", re.IGNORECASE)


def _bc_external_url(bc_url, ua):
    """Fetch a Boston Calendar event detail page and extract the external 'Event website' link.
    Retries once on transient failure since the parallel rewrite hammers BC; returns None
    only after both attempts fail."""
    soup = None
    for attempt in range(2):
        try:
            soup = fetch_soup(bc_url, ua)
            break
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None
    if soup is None:
        return None
    for p in soup.find_all("p"):
        b = p.find("b") or p.find("strong")
        if not b or not _BC_EXTERNAL_RE.search(b.get_text(" ", strip=True)):
            continue
        a = p.find("a", href=True)
        if a and a.get("href"):
            return a["href"]
    return None


def scrape_boston_calendar(url, ua):
    """TheBostonCalendar.com — events aggregator. The `/events` page is scoped to a single day,
    so we iterate the next 14 days and dedupe. For each event, we fetch the detail page in
    parallel and replace the URL with the external 'Event website' link when present."""
    base = url.split("?")[0]
    start = datetime.now(EASTERN).date()
    events = []
    seen_urls = set()
    for i in range(14):
        d = start + timedelta(days=i)
        day_url = f"{base}?day={d.day}&month={d.month}&year={d.year}"
        try:
            soup = fetch_soup(day_url, ua)
        except Exception:
            continue
        for li in soup.select("li.event"):
            a = li.select_one("h3 a") or li.select_one("a")
            if not a:
                continue
            name = a.get_text(strip=True)
            if not name:
                continue
            href = urljoin(day_url, a.get("href", ""))
            if href in seen_urls:
                continue
            seen_urls.add(href)
            time_el = li.select_one(".time")
            loc_el = li.select_one(".location")
            raw_time = time_el.get_text(" ", strip=True) if time_el else ""
            iso = _parse_boston_calendar_time(raw_time)
            events.append({
                "name": name,
                "date": iso,
                "url": href,
                "venue": loc_el.get_text(strip=True) if loc_el else None,
                "price": None,
            })
    if events:
        with ThreadPoolExecutor(max_workers=16) as ex:
            externals = list(ex.map(lambda e: _bc_external_url(e["url"], ua), events))
        for e, ext in zip(events, externals):
            if ext:
                e["url"] = ext
    return events


_TUNEHATCH_VENUE_IDS = {
    "cantab": "968ae511-dae2-43a9-a916-15ae44ef47b8",
}


def scrape_tunehatch(url, ua):
    """TuneHatch venue shows API. `url` encodes the venue slug in the query string, e.g. ?venue=cantab."""
    m = re.search(r"[?&]venue=([^&]+)", url)
    slug = m.group(1) if m else "cantab"
    venue_id = _TUNEHATCH_VENUE_IDS.get(slug)
    if not venue_id:
        r = requests.get(f"https://tunehatch.com/api/v1/entities/venue/{slug}", timeout=15,
                         headers={"User-Agent": ua, "Accept": "application/json"})
        r.raise_for_status()
        venue_id = (r.json() or {}).get("id")
        if not venue_id:
            return []
    r = requests.get("https://tunehatch.com/api/v1/shows", params={"venue_id": venue_id}, timeout=15,
                     headers={"User-Agent": ua, "Accept": "application/json"})
    r.raise_for_status()
    payload = r.json() or {}
    shows = payload.get("data") or payload.get("shows") if isinstance(payload, dict) else payload
    shows = shows or []
    now = datetime.now(timezone.utc)
    events = []
    for s in shows:
        iso = s.get("startsAt")
        if not iso:
            continue
        try:
            when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < now:
            continue
        slug_s = s.get("slug") or s.get("id")
        perf = [p.get("name") for p in (s.get("performers") or []) if isinstance(p, dict) and p.get("name")]
        lineup = ", ".join(perf) if perf else ""
        name = s.get("name") or lineup or "TuneHatch show"
        if lineup and lineup not in name:
            name = f"{name} — {lineup}"
        events.append({
            "name": name,
            "date": when.astimezone(timezone.utc).isoformat(),
            "url": f"https://tunehatch.com/e/shows/{slug_s}" if slug_s else None,
            "venue": s.get("venueName"),
            "price": None,
        })
    return events


def _extract_jsonld_events(soup, base_url):
    """Walk JSON-LD blocks and yield schema.org Event dicts (handles ItemList wrappers)."""
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(block.string or "")
        except Exception:
            continue
        stack = [d]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                t = node.get("@type")
                if t == "Event" or (isinstance(t, list) and "Event" in t):
                    yield node
                for v in node.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)


def _jsonld_event_to_entry(ev, base_url):
    iso = ev.get("startDate")
    try:
        iso = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat() if iso else None
    except (ValueError, AttributeError):
        iso = None
    loc = ev.get("location") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    venue = (loc.get("name") if isinstance(loc, dict) else None)
    offers = ev.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    url = ev.get("url") or (offers.get("url") if isinstance(offers, dict) else None)
    if url and base_url:
        url = urljoin(base_url, url)
    price = None
    if isinstance(offers, dict):
        lo = offers.get("lowPrice") or offers.get("price")
        hi = offers.get("highPrice")
        def _num(x):
            if x in (None, "", "0", 0):
                return None
            try:
                return float(x)
            except (TypeError, ValueError):
                return None
        lo_n = _num(lo)
        hi_n = _num(hi)
        if lo_n is not None or hi_n is not None:
            price = _format_price_range(lo_n, hi_n, offers.get("priceCurrency") or "USD")
        elif isinstance(lo, str) and lo.strip():
            price = lo.strip()
    return {
        "name": ev.get("name"),
        "date": iso,
        "url": url,
        "venue": venue,
        "price": price,
    }


def scrape_jsonld(url, ua):
    """Generic schema.org JSON-LD Event scraper. Works for any page that embeds Events in JSON-LD."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for ev in _extract_jsonld_events(soup, url):
        entry = _jsonld_event_to_entry(ev, url)
        if not entry.get("name"):
            continue
        key = (entry["name"].lower(), entry.get("date") or "")
        if key in seen:
            continue
        seen.add(key)
        events.append(entry)
    return events


def scrape_event_list(url, ua):
    """Shared scraper for Drupal sites that use `article.event-list` markup
    (Brookline Booksmith, Trident Booksellers, etc.). Venue name is filled
    in by group_by_date from the registering source name."""
    soup = fetch_soup(url, ua)
    events = []
    for art in soup.select("article.event-list"):
        a = art.select_one(".event-list__title a") or art.select_one("a[href*='/event/']")
        if not a:
            continue
        mon = art.select_one(".event-list__date--month")
        day = art.select_one(".event-list__date--day")
        href = a.get("href", "")
        m = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", href)
        iso = None
        if m:
            y, mo, d = map(int, m.groups())
            try:
                dt = datetime(y, mo, d, 19, 0, tzinfo=EASTERN)
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        elif mon and day:
            try:
                year = datetime.now(EASTERN).year
                dt = datetime.strptime(f"{mon.get_text(strip=True)} {day.get_text(strip=True)} {year} 19:00", "%b %d %Y %H:%M").replace(tzinfo=EASTERN)
                if dt < datetime.now(EASTERN):
                    dt = dt.replace(year=year + 1)
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        price = None
        body = art.select_one(".event-list__body")
        body_text = body.get_text(" ", strip=True) if body else ""
        p = re.search(r"(Free|FREE|\$\d+(?:\.\d{2})?(?:\s*[–-]\s*\$?\d+(?:\.\d{2})?)?)", body_text)
        if p:
            price = "Free" if p.group(1).lower() == "free" else p.group(1)
        events.append({
            "name": a.get_text(strip=True),
            "date": iso,
            "url": urljoin(url, href),
            "venue": None,
            "price": price,
        })
    return events


_HTD_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _htd_parse_time(text):
    """Parse time from havetodance third-td text like '8:30pm' or '9:00pm-midnight (lesson: 8:00)'."""
    if not text:
        return 19, 0
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text, re.IGNORECASE)
    if not m:
        return 19, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def scrape_havetodance(url, ua):
    """Parse havetodance.com's month-table calendar. Each <table> is one month,
    with <th> containing 'Month, YYYY' and subsequent <tr> rows holding
    (day, name+venue, time) across three <td>s."""
    soup = fetch_soup(url, ua)
    events = []
    for table in soup.find_all("table"):
        th = table.find("th")
        if not th:
            continue
        th_text = th.get_text(" ", strip=True)
        m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(\d{4})", th_text, re.IGNORECASE)
        if not m:
            continue
        month = _HTD_MONTHS[m.group(1).lower()]
        year = int(m.group(2))
        for tr in table.find_all("tr"):
            if tr.find("th"):
                continue
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 2:
                continue
            day_td = tds[0]
            day_b = day_td.find("b")
            day_text = (day_b.get_text(" ", strip=True) if day_b else day_td.get_text(" ", strip=True))
            dm = re.match(r"^\s*(\d{1,2})\s*$", day_text)
            if not dm:
                continue
            day = int(dm.group(1))
            info_td = tds[1]
            a = info_td.find("a")
            if not a:
                continue
            name = a.get_text(" ", strip=True)
            if not name:
                continue
            href = a.get("href", "")
            featured_band = None
            for b in info_td.find_all("b"):
                band_a = b.find("a")
                if band_a:
                    featured_band = band_a.get_text(" ", strip=True)
                    break
            time_text = tds[2].get_text(" ", strip=True) if len(tds) >= 3 else ""
            hour, minute = _htd_parse_time(time_text)
            try:
                dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN)
            except ValueError:
                continue
            display_name = f"{name} — {featured_band}" if featured_band else name
            events.append({
                "name": display_name,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": urljoin(url, href) if href else url,
                "venue": name,
                "price": None,
            })
    return events


_AERONAUT_CATEGORY_MAP = {
    "music": "music",
    "community": "community",
    "trivia": "gaming",
    "meetup": "community",
    "bike": "sports",
    "art": "art",
    "party": "clubbing",
    "performance": "theater",
}


def scrape_aeronaut(url, ua):
    """Aeronaut Brewing Somerville publishes events as a public JSON feed
    on CloudFront. The main page is Cloudflare-gated but the JSON isn't."""
    resp = requests.get(url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    today = datetime.now(EASTERN).date()
    events = []
    for row in resp.json():
        if row.get("venue_slug") != "somerville":
            continue
        date_str = row.get("date")
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < today:
            continue
        hour, minute = 19, 0
        start = row.get("start") or ""
        m = re.match(r"(\d{1,2}):(\d{2})", start)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
        try:
            dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
        except ValueError:
            continue
        link = row.get("tickets") or row.get("extlink") or "https://www.aeronautbrewing.com/visit/somerville/#events"
        events.append({
            "name": row.get("name") or "Event",
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": link,
            "venue": "Aeronaut Brewing (Somerville)",
            "price": None,
            "category": _AERONAUT_CATEGORY_MAP.get(row.get("category")),
        })
    return events


_BAC_SUPABASE = "https://xmvgtpwxmlsmkopfdifw.supabase.co"
_BAC_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inhtdmd0cHd4bWxzbWtvcGZkaWZ3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzIyMTQ4MDUsImV4cCI6MjA4Nzc5MDgwNX0.AxCKUYjY9mNvzhNtRPMmY7XBMK2qS__tRD3KudcDzqg"


def scrape_boston_adventure_club(url, ua):
    """Boston Adventure Club is a Lovable SPA backed by a public Supabase
    `events` table. We query upcoming events directly via PostgREST."""
    today = datetime.now(EASTERN).date().isoformat()
    resp = requests.get(
        f"{_BAC_SUPABASE}/rest/v1/events",
        params={
            "select": "id,title,location,event_date",
            "event_date": f"gte.{today}",
            "order": "event_date.asc",
            "limit": "100",
        },
        headers={
            "apikey": _BAC_ANON_KEY,
            "Authorization": f"Bearer {_BAC_ANON_KEY}",
            "User-Agent": ua,
        },
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for row in resp.json():
        dt_iso = row.get("event_date")
        if not dt_iso:
            continue
        events.append({
            "name": row.get("title") or "Adventure",
            "date": dt_iso,
            "url": f"https://bostonadventureclub.com/events/{row['id']}",
            "venue": row.get("location") or "Boston Adventure Club",
            "price": None,
        })
    return events


def scrape_gardner(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    for art in soup.select("article.views-rendered-node, .isg-events-list__item-wrapper"):
        aside = art.select_one(".isg-events-list__date")
        h = art.select_one(".isg-card__title, h2, h3, .isg-card--text-left")
        link = art.select_one("a[href*='/calendar/'], a[href*='/events']") or art.select_one("a")
        name = None
        if h:
            name = h.get_text(" ", strip=True)[:160]
        if not name and link:
            name = link.get_text(" ", strip=True)[:160]
        if not name:
            continue
        iso = None
        if aside:
            txt = aside.get_text(" ", strip=True)
            m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4}).*?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", txt, re.IGNORECASE)
            if m:
                mon_name, day, year, hour, minute, ampm = m.groups()
                try:
                    mo = datetime.strptime(mon_name[:3], "%b").month
                    h = int(hour)
                    if ampm and ampm.lower() == "pm" and h != 12:
                        h += 12
                    dt = datetime(int(year), mo, int(day), h, int(minute or 0), tzinfo=EASTERN)
                    iso = dt.astimezone(timezone.utc).isoformat()
                except (ValueError, KeyError):
                    pass
        events.append({
            "name": name,
            "date": iso,
            "url": urljoin(url, link.get("href", "")) if link else None,
            "venue": "Isabella Stewart Gardner Museum",
            "price": None,
        })
    return events


def scrape_brattle(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    for show in soup.select(".show"):
        a = show.select_one("a[href*='brattlefilm.org']") or show.select_one("a")
        h = show.select_one("h2, h3")
        if not a or not h:
            continue
        events.append({
            "name": h.get_text(strip=True),
            "date": None,
            "url": urljoin(url, a.get("href", "")),
            "venue": "Brattle Theatre",
            "price": None,
        })
    return events


def scrape_ica(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for art in soup.select("article"):
        a = art.select_one("a[href*='/events/']")
        if not a:
            continue
        href = a.get("href", "")
        if href in seen or not href.rstrip("/").endswith(tuple(href.rstrip("/").split("/")[-1:])):
            pass
        img = a.select_one("img")
        name = None
        if a.get_text(strip=True):
            name = a.get_text(strip=True)
        elif img and img.get("alt"):
            name = img.get("alt")
        else:
            slug = href.rstrip("/").split("/")[-1]
            name = slug.replace("-", " ").title()
        if not name or href in seen:
            continue
        seen.add(href)
        events.append({
            "name": name[:160],
            "date": None,
            "url": urljoin(url, href),
            "venue": "ICA Boston",
            "price": None,
        })
    return events


def scrape_wilbur(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for a in soup.select('a[href*="/event/"]'):
        href = a.get("href", "").split("?")[0]
        if not href or href in seen:
            continue
        seen.add(href)
        img = a.select_one("img")
        name = a.get_text(strip=True) or (img.get("alt") if img else "")
        if not name or name.lower() in ("buy tickets", "tickets", "info", "more"):
            slug = href.rstrip("/").split("/")[-1]
            name = slug.replace("-", " ").title()
        events.append({
            "name": name[:160],
            "date": None,
            "url": href,
            "venue": "Wilbur Theatre",
            "price": None,
        })
    return events


_ST_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}


def scrape_somerville_theatre(url, ua):
    """WP Theatre plugin: one `.wp_theatre_event` per show with title, date,
    time, and ticket link rendered inline."""
    soup = fetch_soup(url, ua)
    events = []
    for block in soup.select(".wp_theatre_event"):
        title_el = block.select_one(".wp_theatre_event_title")
        if not title_el:
            continue
        name = re.sub(r"\s+", " ", title_el.get_text(" ", strip=True))
        date_el = block.select_one(".wp_theatre_event_startdate")
        time_el = block.select_one(".wp_theatre_event_starttime")
        if not date_el:
            continue
        m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})", date_el.get_text(strip=True))
        if not m:
            continue
        month = _ST_MONTHS.get(m.group(1).lower())
        if not month:
            continue
        day, year = int(m.group(2)), int(m.group(3))
        hour, minute = 19, 30
        if time_el:
            tm = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)?", time_el.get_text(strip=True), re.IGNORECASE)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))
                if tm.group(3) and tm.group(3).lower() == "pm" and hour != 12:
                    hour += 12
                elif tm.group(3) and tm.group(3).lower() == "am" and hour == 12:
                    hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN)
        except ValueError:
            continue
        link = block.select_one("a.wp_theatre_event_tickets_url") or block.select_one("a[href]")
        href = link.get("href") if link else url
        events.append({
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": href,
            "venue": "Somerville Theatre",
            "price": None,
        })
    return events


_SINCLAIR_DAY_MONTHS = {m: i for i, m in enumerate(
    ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"], start=1)}


def scrape_sinclair(url, ua):
    """Sinclair's events page renders AXS event cards server-side as
    `.entry.sinclair` blocks. Date text like 'Mon, Apr 20, 2026' + 'Doors 7:00 PM'."""
    soup = fetch_soup(url, ua)
    events = []
    for entry in soup.select(".event_list > .entry"):
        h = entry.select_one(".title h3 a, h3.carousel_item_title_small a")
        if not h:
            continue
        name = re.sub(r"\s+", " ", h.get_text(" ", strip=True))
        href = h.get("href") or url
        date_el = entry.select_one(".date")
        time_el = entry.select_one(".time")
        if not date_el:
            continue
        date_text = re.sub(r"\s+", " ", date_el.get_text(" ", strip=True))
        dm = re.search(r"([A-Za-z]{3}),\s+([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", date_text)
        if not dm:
            continue
        month = _SINCLAIR_DAY_MONTHS.get(dm.group(2))
        if not month:
            continue
        day, year = int(dm.group(3)), int(dm.group(4))
        hour, minute = 19, 0
        if time_el:
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", time_el.get_text(" ", strip=True), re.IGNORECASE)
            if tm:
                hour, minute = int(tm.group(1)), int(tm.group(2))
                if tm.group(3).upper() == "PM" and hour != 12:
                    hour += 12
                elif tm.group(3).upper() == "AM" and hour == 12:
                    hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN)
        except ValueError:
            continue
        tickets = entry.select_one("a.btn-tickets")
        ticket_href = tickets.get("href") if tickets else href
        events.append({
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": ticket_href,
            "venue": "The Sinclair",
            "price": None,
        })
    return events


def scrape_night_shift(url, ua):
    """Night Shift uses the Tribe Events calendar; each upcoming event renders
    as `article.event-article` with a .article-date text line and .article-title
    link to the event detail page."""
    soup = fetch_soup(url, ua)
    events = []
    current_year = datetime.now(EASTERN).year
    for art in soup.select("article.event-article"):
        title_a = art.select_one(".article-title a")
        if not title_a:
            continue
        name = re.sub(r"\s+", " ", title_a.get_text(" ", strip=True))
        href = title_a.get("href") or url
        date_el = art.select_one(".article-date")
        if not date_el:
            continue
        date_text = re.sub(r"\s+", " ", date_el.get_text(" ", strip=True))
        iso = None
        slug = re.search(r"/(\d{4}-\d{2}-\d{2})/?$", href.rstrip("/") + "/")
        if slug:
            try:
                d = datetime.strptime(slug.group(1), "%Y-%m-%d").date()
                tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", date_text, re.IGNORECASE)
                hour, minute = 19, 0
                if tm:
                    hour, minute = int(tm.group(1)), int(tm.group(2))
                    if tm.group(3).lower() == "pm" and hour != 12:
                        hour += 12
                    elif tm.group(3).lower() == "am" and hour == 12:
                        hour = 0
                dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        if not iso:
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(\d{4}))?", date_text)
            if m:
                mname, day, yr = m.group(1), int(m.group(2)), int(m.group(3) or current_year)
                month = _ST_MONTHS.get(mname.lower())
                if month:
                    tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", date_text, re.IGNORECASE)
                    hour, minute = 19, 0
                    if tm:
                        hour, minute = int(tm.group(1)), int(tm.group(2))
                        if tm.group(3).lower() == "pm" and hour != 12:
                            hour += 12
                        elif tm.group(3).lower() == "am" and hour == 12:
                            hour = 0
                    try:
                        dt = datetime(yr, month, day, hour, minute, tzinfo=EASTERN)
                        iso = dt.astimezone(timezone.utc).isoformat()
                    except ValueError:
                        pass
        events.append({
            "name": name,
            "date": iso,
            "url": href,
            "venue": "Night Shift Brewing",
            "price": None,
        })
    return events


def scrape_laugh_boston(url, ua):
    """Laugh Boston uses Ticketmaster for their lineup; fall back to JSON-LD on their site."""
    events = scrape_jsonld(url, ua)
    if events:
        for e in events:
            e.setdefault("venue", "Laugh Boston")
        return events
    return []


def scrape_city_winery(url, ua):
    """City Winery Boston — Vivenu-backed event API."""
    r = requests.get("https://awsapi.citywinery.com/events", params={"location": "Boston", "top": 200},
                     timeout=20, headers={"User-Agent": ua, "Accept": "application/json"})
    r.raise_for_status()
    payload = (r.json() or {}).get("data", {})
    events = []
    now = datetime.now(timezone.utc)
    for ev in payload.get("event_data", []) or []:
        iso = ev.get("start")
        if not iso:
            continue
        try:
            when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < now:
            continue
        slug = ev.get("url") or ev.get("_id")
        price = ev.get("startingPrice")
        price_str = f"From ${int(price) if price == int(price) else price}" if isinstance(price, (int, float)) and price > 0 else None
        events.append({
            "name": ev.get("name"),
            "date": when.astimezone(timezone.utc).isoformat(),
            "url": f"https://tickets.citywinery.com/events/{slug}" if slug else None,
            "venue": ev.get("locationName") or "City Winery Boston",
            "price": price_str,
        })
    return events


def scrape_balance_patch(url, ua):
    """Squarespace events collection JSON (?format=json-pretty). Currently empty — keeps hook in place."""
    r = requests.get(url, params={"format": "json-pretty"}, timeout=15,
                     headers={"User-Agent": ua, "Accept": "application/json"})
    r.raise_for_status()
    data = r.json() or {}
    events = []
    for item in data.get("items", []) or []:
        start_ms = item.get("startDate")
        if not start_ms:
            continue
        iso = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc).isoformat()
        events.append({
            "name": item.get("title"),
            "date": iso,
            "url": urljoin(url, "/" + item.get("fullUrl", "").lstrip("/")) if item.get("fullUrl") else None,
            "venue": "Balance Patch",
            "price": None,
        })
    return events


def scrape_24hour_music(url, ua):
    """24 Hour Music — accesso ShoWare ticketing platform.
    Hits internal JSON endpoint that powers the homepage performance list."""
    today = datetime.now(EASTERN).date()
    end = today + timedelta(weeks=12)
    api = urljoin(url, "/include/widgets/events/performancelist.asp")
    r = requests.get(api, headers={
        "User-Agent": ua,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": url,
    }, params={
        "fromDate": today.isoformat(),
        "toDate": end.isoformat(),
        "action": "perf",
        "listPageSize": 200,
        "listMaxSize": 500,
        "page": 1,
        "showPackages": 1,
    }, timeout=15)
    r.raise_for_status()
    events = []
    for p in r.json().get("performance") or []:
        raw = p.get("PerformanceDateTime")
        if not raw:
            continue
        try:
            dt = datetime.strptime(raw, "%A, %B %d, %Y %I:%M:%S %p").replace(tzinfo=EASTERN)
        except ValueError:
            continue
        name = p.get("PerformanceName") or p.get("Event")
        venue = p.get("Venue")
        city = p.get("VenueCity")
        if venue and city:
            venue = f"{venue} ({city})"
        pid = p.get("PerformanceID")
        events.append({
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": urljoin(url, f"/orderticket.asp?p={pid}") if pid else url,
            "venue": venue,
            "price": None,
        })
    return events


def scrape_bida(url, ua):
    """BIDA contra dance — public ICS feed at /events.ics."""
    ics = requests.get(urljoin(url, "/events.ics"), headers={"User-Agent": ua}, timeout=15).text
    # unfold continuation lines (RFC 5545: leading space/tab = continuation)
    ics = re.sub(r"\r?\n[ \t]", "", ics)
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(weeks=12)
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics, re.S):
        summary = re.search(r"^SUMMARY:(.+)$", block, re.M)
        dtstart = re.search(r"^DTSTART(?:;TZID=([^:]+))?:(\d{8}T\d{6})", block, re.M)
        ev_url = re.search(r"^URL:(.+)$", block, re.M)
        if not summary or not dtstart:
            continue
        title = summary.group(1).strip()
        title_lower = title.lower()
        if "cancelled" in title_lower or "no dance" in title_lower:
            continue
        tzid, raw = dtstart.group(1), dtstart.group(2)
        try:
            naive = datetime.strptime(raw, "%Y%m%dT%H%M%S")
        except ValueError:
            continue
        if tzid:
            try:
                local = naive.replace(tzinfo=ZoneInfo(tzid))
            except Exception:
                local = naive.replace(tzinfo=EASTERN)
        else:
            local = naive.replace(tzinfo=timezone.utc)
        when = local.astimezone(timezone.utc)
        if when < now or when > cutoff:
            continue
        events.append({
            "name": title,
            "date": when.isoformat(),
            "url": (ev_url.group(1).strip() if ev_url else url),
            "venue": "Masonic Hall (Cambridge)",
            "price": "$5–$20 sliding scale",
        })
    return events


_SSR_DATE_RE = re.compile(
    r'(Sunday|Saturday|Friday|Monday|Tuesday|Wednesday|Thursday),\s+'
    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?',
    re.I,
)


def scrape_second_sun_rising(url, ua):
    """Second Sun Rising — monthly Sunday fusion dance at Cambridge Masonic Hall.
    Page describes one upcoming dance in prose; parse the date out."""
    soup = fetch_soup(url + "index.php/this-months-dance/", ua)
    text = soup.get_text(" ", strip=True)
    m = _SSR_DATE_RE.search(text)
    if not m:
        return []
    month_name, day = m.group(2), int(m.group(3))
    now = datetime.now(EASTERN)
    try:
        dt = datetime.strptime(f"{month_name} {day} {now.year}", "%B %d %Y").replace(
            hour=19, tzinfo=EASTERN,
        )
    except ValueError:
        return []
    if dt < now - timedelta(hours=4):
        return []
    return [{
        "name": "Second Sun Rising — Fusion Dance",
        "date": dt.astimezone(timezone.utc).isoformat(),
        "url": url,
        "venue": "Cambridge Masonic Hall (Cambridge)",
        "price": "pay-what-you-can $10–$30",
    }]


def scrape_meetup_group(url, ua):
    """Meetup group page — events live in Next.js __NEXT_DATA__ Apollo state.
    Caps to events within the next 6 weeks to avoid weekly recurrences flooding."""
    html = requests.get(url, headers={"User-Agent": ua}, timeout=15).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    data = json.loads(m.group(1))
    state = (data.get("props") or {}).get("pageProps", {}).get("__APOLLO_STATE__") or {}
    cutoff = datetime.now(timezone.utc) + timedelta(weeks=6)
    events = []
    for k, v in state.items():
        if not k.startswith("Event:") or not isinstance(v, dict):
            continue
        if v.get("status") != "ACTIVE" or not v.get("eventUrl"):
            continue
        iso_raw = v.get("dateTime")
        if not iso_raw:
            continue
        try:
            when = datetime.fromisoformat(iso_raw).astimezone(timezone.utc)
        except ValueError:
            continue
        if when > cutoff:
            continue
        venue_ref = (v.get("venue") or {}).get("__ref")
        venue_obj = state.get(venue_ref, {}) if venue_ref else {}
        venue_name = venue_obj.get("name")
        if venue_obj.get("city"):
            venue_name = f"{venue_name} ({venue_obj['city']})" if venue_name else venue_obj["city"]
        events.append({
            "name": v.get("title"),
            "date": when.isoformat(),
            "url": v.get("eventUrl"),
            "venue": venue_name,
            "price": None,
            "description": (v.get("description") or "")[:200],
        })
    return events


def scrape_meetup(url, ua):
    """Meetup in-person Boston events via JSON-LD Event array."""
    soup = fetch_soup(url, ua)
    events = []
    for block in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(block.string or "")
        except Exception:
            continue
        arr = d if isinstance(d, list) else [d]
        for ev in arr:
            if not isinstance(ev, dict) or ev.get("@type") != "Event":
                continue
            iso = ev.get("startDate")
            try:
                iso = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat() if iso else None
            except (ValueError, AttributeError):
                iso = None
            loc = ev.get("location") or {}
            if isinstance(loc, dict):
                venue = loc.get("name") or (loc.get("address") or {}).get("streetAddress")
            else:
                venue = None
            events.append({
                "name": ev.get("name"),
                "date": iso,
                "url": ev.get("url"),
                "venue": venue,
                "price": None,
                "description": (ev.get("description") or "")[:200],
            })
    return events


def scrape_porter_square_books(url, ua):
    """Porter Square Books embeds its full FullCalendar event list in the
    Drupal `drupalSettings` JSON blob on the calendar page. The rendered
    HTML only shows a handful of cards, but the JSON has the whole month."""
    html = requests.get(url, headers={"User-Agent": ua}, timeout=15).text
    m = re.search(
        r'data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>',
        html, re.S,
    )
    if not m:
        return []
    settings = json.loads(m.group(1))
    fcv = (settings.get("fullCalendarView") or [{}])[0]
    calendar_opts = fcv.get("calendar_options") or {}
    if isinstance(calendar_opts, str):
        calendar_opts = json.loads(calendar_opts)
    events = []
    now = datetime.now(timezone.utc)
    for ev in calendar_opts.get("events") or []:
        start = ev.get("start")
        if not start:
            continue
        try:
            when = datetime.fromisoformat(start)
        except ValueError:
            continue
        if when.astimezone(timezone.utc) < now:
            continue
        title_html = ev.get("title") or ""
        title_soup = BeautifulSoup(title_html, "html.parser")
        span = title_soup.find("span")
        name = re.sub(r"\s+", " ", (span or title_soup).get_text(" ", strip=True))
        href = ev.get("url") or ""
        events.append({
            "name": name,
            "date": when.astimezone(timezone.utc).isoformat(),
            "url": urljoin(url, href) if href else url,
            "venue": "Porter Square Books",
            "price": None,
        })
    return events


def scrape_event_blocks(url, ua):
    """Shared IndieCommerce/Drupal scraper used by Trident and Porter Square Books."""
    soup = fetch_soup(url, ua)
    events = []
    for block in soup.select("article.event-block"):
        title = block.select_one(".event-block__title")
        if not title:
            continue
        name = re.sub(r"\s+", " ", title.get_text(" ", strip=True))
        a = block.select_one(".event-block__cta a") or block.select_one("a")
        href = a.get("href", "") if a else ""
        iso = None
        href_match = re.search(r"/event/(\d{4}-\d{2}-\d{2})", href)
        if href_match:
            iso = datetime.fromisoformat(href_match.group(1)).replace(
                hour=19, tzinfo=EASTERN,
            ).astimezone(timezone.utc).isoformat()
        else:
            mon = block.select_one(".event__month--start")
            day = block.select_one(".event__day--start")
            if mon and day:
                try:
                    dt = datetime.strptime(
                        f"{mon.get_text(strip=True)} {day.get_text(strip=True)} {datetime.now().year}",
                        "%b %d %Y",
                    ).replace(hour=19, tzinfo=EASTERN)
                    iso = dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
        events.append({
            "name": name,
            "date": iso,
            "url": urljoin(url, href) if href else url,
        })
    return events


def parse_harvard_date(text):
    """Parse 'Tuesday, April 21, 2026 - 7:00pm'."""
    if not text:
        return None
    m = re.match(
        r"[A-Za-z]+,\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\s*-\s*(\d{1,2}):(\d{2})(am|pm)",
        text, re.IGNORECASE,
    )
    if not m:
        return None
    mon, day, year, hh, mm, ampm = m.groups()
    hour = int(hh)
    if ampm.lower() == "pm" and hour != 12:
        hour += 12
    if ampm.lower() == "am" and hour == 12:
        hour = 0
    try:
        dt = datetime.strptime(f"{mon} {day} {year}", "%B %d %Y").replace(
            hour=hour, minute=int(mm), tzinfo=EASTERN,
        )
        return dt.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def scrape_harvard(url, ua):
    soup = fetch_soup(url, ua)
    events = []
    for row in soup.select(".event-row"):
        info = row.select_one(".event-info")
        if not info:
            continue
        a = info.select_one("h2 a")
        h2 = info.select_one("h2")
        name = a.get_text(strip=True) if a else (h2.get_text(strip=True) if h2 else "")
        if not name:
            continue
        date_el = info.select_one(".date-display-single")
        date_text = date_el.get_text(strip=True) if date_el else ""
        btn = info.select_one("a.event-btn")
        href = (a.get("href") if a else None) or (btn.get("href", "") if btn else "")
        events.append({
            "name": name,
            "date": parse_harvard_date(date_text) or date_text or None,
            "url": urljoin(url, href) if href else url,
        })
    return events


def _format_price_range(mn, mx, currency="USD"):
    if mn is None:
        return None
    sym = "$" if currency == "USD" else f"{currency} "
    if mx is None or mx == mn:
        return f"{sym}{mn:.0f}"
    return f"{sym}{mn:.0f}–{mx:.0f}"


def scrape_ticketmaster(_url, _ua):
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        raise RuntimeError("TICKETMASTER_API_KEY not set")
    resp = requests.get(
        "https://app.ticketmaster.com/discovery/v2/events.json",
        params={
            "apikey": key,
            "latlong": "42.3601,-71.0589",
            "radius": 25,
            "unit": "miles",
            "size": 100,
            "sort": "date,asc",
            "startDateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for ev in resp.json().get("_embedded", {}).get("events", []):
        start = ev.get("dates", {}).get("start", {})
        iso = start.get("dateTime")
        if not iso and start.get("localDate"):
            try:
                iso = datetime.fromisoformat(f"{start['localDate']}T19:00:00").replace(
                    tzinfo=EASTERN,
                ).astimezone(timezone.utc).isoformat()
            except ValueError:
                iso = None
        venues = ev.get("_embedded", {}).get("venues") or []
        venue = venues[0]["name"] if venues and venues[0].get("name") else "Ticketmaster"
        price = None
        prs = ev.get("priceRanges") or []
        if prs:
            price = _format_price_range(prs[0].get("min"), prs[0].get("max"), prs[0].get("currency", "USD"))
        events.append({
            "name": ev.get("name"),
            "date": iso,
            "url": ev.get("url"),
            "venue": venue,
            "price": price,
        })
    return events


def scrape_seatgeek(_url, _ua):
    cid = os.environ.get("SEATGEEK_CLIENT_ID")
    if not cid:
        raise RuntimeError("SEATGEEK_CLIENT_ID not set")
    resp = requests.get(
        "https://api.seatgeek.com/2/events",
        params={
            "client_id": cid,
            "lat": 42.3601,
            "lon": -71.0589,
            "range": "25mi",
            "per_page": 100,
            "sort": "datetime_local.asc",
            "datetime_utc.gte": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        },
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for ev in resp.json().get("events", []):
        iso = ev.get("datetime_utc")
        if iso and not iso.endswith("Z") and "+" not in iso:
            iso = iso + "Z"
        stats = ev.get("stats") or {}
        lo = stats.get("lowest_price")
        price = f"${lo:.0f}+" if lo else None
        venue = ((ev.get("venue") or {}).get("name")) or "SeatGeek"
        events.append({
            "name": ev.get("title") or ev.get("short_title"),
            "date": iso,
            "url": ev.get("url"),
            "venue": venue,
            "price": price,
        })
    return events


def scrape_squarespace_events(url, ua):
    """Squarespace events collections expose ?format=json with an `upcoming` array.
    startDate is a ms-since-epoch integer."""
    sep = "&" if "?" in url else "?"
    resp = requests.get(url + sep + "format=json", headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    root = url.split("?")[0].rsplit("/", 1)[0]
    events = []
    for ev in data.get("upcoming", []) or []:
        ts = ev.get("startDate")
        iso = None
        if isinstance(ts, (int, float)):
            try:
                iso = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
            except (OverflowError, OSError, ValueError):
                iso = None
        full = ev.get("fullUrl") or ""
        href = urljoin(url, full) if full else url
        events.append({
            "name": ev.get("title"),
            "date": iso,
            "url": href,
            "venue": None,
            "price": None,
        })
    return events


_BURREN_MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "MAY": 5, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def _burren_parse_date(header_text):
    m = re.search(r"([A-Z]+)\s+([A-Z]+)\s+(\d{1,2})", (header_text or "").upper())
    if not m:
        return None
    month = _BURREN_MONTHS.get(m.group(2))
    if not month:
        return None
    day = int(m.group(3))
    today = datetime.now(EASTERN).date()
    year = today.year
    try:
        d = datetime(year, month, day).date()
    except ValueError:
        return None
    if (d - today).days < -60:
        d = datetime(year + 1, month, day).date()
    return d


def _burren_parse_time(text):
    if not text:
        return 20, 0
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text, re.IGNORECASE)
    if not m:
        return 20, 0
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    return hour, minute


def scrape_burren(url, ua):
    """The Burren publishes calendars as a sequence of tables: a HEADER table for each day,
    followed by one-row tables with .Room / .Time / .BAND / .Text spans."""
    soup = fetch_soup(url, ua)
    today = datetime.now(EASTERN).date()
    current_date = None
    events = []
    for t in soup.find_all("table"):
        hd = t.select_one(".HEADER")
        if hd:
            current_date = _burren_parse_date(hd.get_text(strip=True))
            continue
        if not current_date or current_date < today:
            continue
        band = t.select_one(".BAND")
        if not band:
            continue
        name = band.get_text(" ", strip=True)
        if not name:
            continue
        room = t.select_one(".Room")
        time_el = t.select_one(".Time")
        text_el = t.select_one(".Text")
        hour, minute = _burren_parse_time(time_el.get_text(" ", strip=True) if time_el else "")
        dt = datetime(current_date.year, current_date.month, current_date.day, hour, minute, tzinfo=EASTERN)
        venue = "The Burren"
        if room:
            venue = f"The Burren — {room.get_text(' ', strip=True).title()}"
        desc = text_el.get_text(" ", strip=True) if text_el else ""
        events.append({
            "name": name.title() if name.isupper() else name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": url,
            "venue": venue,
            "price": None,
            "description": desc or None,
        })
    return events


_HMNH_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _hmnh_parse_date(date_str, time_str):
    if not date_str:
        return None
    m = re.search(r"([A-Za-z]{3})\s+(\d{1,2}),?\s+(\d{4})", date_str)
    if not m:
        return None
    mon = _HMNH_MONTHS.get(m.group(1).title())
    if not mon:
        return None
    day, year = int(m.group(2)), int(m.group(3))
    hour, minute = 10, 0
    if time_str:
        mt = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", time_str, re.IGNORECASE)
        if mt:
            hour = int(mt.group(1))
            minute = int(mt.group(2) or 0)
            if mt.group(3).upper() == "PM" and hour != 12:
                hour += 12
            if mt.group(3).upper() == "AM" and hour == 12:
                hour = 0
    try:
        dt = datetime(year, mon, day, hour, minute, tzinfo=EASTERN)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def scrape_hmnh(url, ua):
    """Harvard Museum of Natural History calendar uses `article.event-card` blocks."""
    soup = fetch_soup(url, ua)
    events = []
    for card in soup.select("article.event-card"):
        h = card.select_one(".event-card__heading") or card.select_one("h2, h3")
        a = card.select_one(".event-card__link") or card.select_one("a[href]")
        if not h or not a:
            continue
        name = h.get_text(" ", strip=True)
        d_el = card.select_one(".event-card__date")
        t_el = card.select_one(".event-card__time")
        iso = _hmnh_parse_date(
            d_el.get_text(" ", strip=True) if d_el else "",
            t_el.get_text(" ", strip=True) if t_el else "",
        )
        events.append({
            "name": name,
            "date": iso,
            "url": urljoin(url, a.get("href", "")),
            "venue": "Harvard Museum of Natural History",
            "price": None,
        })
    return events


_ALL_VENUES = [
    # API-keyed — only enabled when creds present
    {"name": "Ticketmaster", "url": "https://www.ticketmaster.com/", "ua": UA_CHROME, "scraper": scrape_ticketmaster, "default_category": None, "requires_env": "TICKETMASTER_API_KEY"},
    {"name": "SeatGeek", "url": "https://seatgeek.com/cities/boston", "ua": UA_CHROME, "scraper": scrape_seatgeek, "default_category": None, "requires_env": "SEATGEEK_CLIENT_ID"},
    {"name": "Eventbrite Boston", "url": "https://www.eventbrite.com/d/ma--boston/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Aeronaut Brewing", "url": "https://d3izki9aezxlkr.cloudfront.net/public_events.json", "ua": UA_CHROME, "scraper": scrape_aeronaut, "default_category": "food"},
    {"name": "Versus Boston (via Eventbrite)", "url": "https://www.eventbrite.com/o/versus-105910382141", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "gaming"},
    {"name": "Make Friends After College (via Eventbrite)", "url": "https://www.eventbrite.com/o/make-friends-after-college-98390790901", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "The Boston Calendar", "url": "https://www.thebostoncalendar.com/events", "ua": UA_CHROME, "scraper": scrape_boston_calendar, "default_category": None},
    {"name": "City Winery Boston", "url": "https://citywinery.com/pages/locations/boston", "ua": UA_CHROME, "scraper": scrape_city_winery, "default_category": "music"},
    {"name": "Bowery Presents Boston", "url": "https://www.bowerypresents.com/boston", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "music"},
    {"name": "Royale Boston", "url": "https://www.royaleboston.com/events/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "clubbing"},
    {"name": "MIT Events", "url": "https://calendar.mit.edu/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "community"},
    {"name": "Wilbur Theatre", "url": "https://thewilbur.com/", "ua": UA_CHROME, "scraper": scrape_wilbur, "default_category": "comedy"},
    {"name": "Brookline Booksmith", "url": "https://www.brooklinebooksmith.com/events", "ua": UA_SAFARI, "scraper": scrape_event_list, "default_category": "books"},
    {"name": "Gardner Museum", "url": "https://www.gardnermuseum.org/calendar", "ua": UA_CHROME, "scraper": scrape_gardner, "default_category": "community"},
    {"name": "ICA Boston", "url": "https://www.icaboston.org/events", "ua": UA_CHROME, "scraper": scrape_ica, "default_category": "community"},
    {"name": "Brattle Theatre", "url": "https://www.brattlefilm.org/", "ua": UA_CHROME, "scraper": scrape_brattle, "default_category": "film"},
    {"name": "Meetup Boston", "url": "https://www.meetup.com/find/?location=us--ma--boston&source=EVENTS&eventType=inPerson&distance=tenMiles", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Somerville Board Games Meetup", "url": "https://www.meetup.com/somerville-board-games-meetup-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Second Sun Rising", "url": "https://secondsunrising.com/", "ua": UA_CHROME, "scraper": scrape_second_sun_rising, "default_category": "dance"},
    {"name": "BIDA Contra Dance", "url": "https://www.bidadance.org/", "ua": UA_CHROME, "scraper": scrape_bida, "default_category": "dance"},
    {"name": "24 Hour Music", "url": "https://tickets.24hourmusic.com/", "ua": UA_CHROME, "scraper": scrape_24hour_music, "default_category": "music"},
    {"name": "Boston Public Library", "url": "https://bpl.bibliocommons.com/events/search/index", "ua": UA_CHROME, "scraper": scrape_bpl, "default_category": "community"},
    {"name": "Crystal Ballroom", "url": "https://www.crystalballroomboston.com/events/", "ua": UA_CHROME, "scraper": scrape_crystal_ballroom, "default_category": "music"},
    {"name": "Coolidge Corner Theatre", "url": "https://coolidge.org/", "ua": UA_CHROME, "scraper": scrape_coolidge, "default_category": "film"},
    {"name": "Trident Booksellers & Cafe", "url": "https://tridentbookscafe.com/events", "ua": UA_SAFARI, "scraper": scrape_event_list, "default_category": "books"},
    {"name": "Harvard Book Store", "url": "https://www.harvard.com/events", "ua": UA_SAFARI, "scraper": scrape_harvard, "default_category": "books"},
    {"name": "Porter Square Books", "url": "https://portersquarebooks.com/events/calendar", "ua": UA_SAFARI, "scraper": scrape_porter_square_books, "default_category": "books"},
    {"name": "Have To Dance", "url": "http://www.havetodance.com/calendar.html", "ua": UA_CHROME, "scraper": scrape_havetodance, "default_category": "dance"},
    {"name": "Boston Adventure Club", "url": "https://bostonadventureclub.com/events", "ua": UA_CHROME, "scraper": scrape_boston_adventure_club, "default_category": "outdoors"},
    {"name": "Somerville Theatre", "url": "https://www.somervilletheatre.com/events/", "ua": UA_CHROME, "scraper": scrape_somerville_theatre, "default_category": "film"},
    {"name": "The Sinclair", "url": "https://www.sinclaircambridge.com/events", "ua": UA_CHROME, "scraper": scrape_sinclair, "default_category": "music"},
    {"name": "Night Shift Brewing", "url": "https://nightshiftbrewing.com/events/", "ua": UA_CHROME, "scraper": scrape_night_shift, "default_category": "food"},
    {"name": "McCarthy's Toad", "url": "https://www.mccarthystoad.com/music", "ua": UA_CHROME, "scraper": scrape_squarespace_events, "default_category": "music"},
    {"name": "Remnant Somerville", "url": "https://www.remnantsomerville.com/live", "ua": UA_CHROME, "scraper": scrape_squarespace_events, "default_category": "music"},
    {"name": "The Burren", "url": "https://burren.com/music.html", "ua": UA_CHROME, "scraper": scrape_burren, "default_category": "music"},
    {"name": "Harvard Museum of Natural History", "url": "https://www.hmnh.harvard.edu/calendar", "ua": UA_CHROME, "scraper": scrape_hmnh, "default_category": "community"},
    {"name": "Lovestruck Books (via Eventbrite)", "url": "https://www.eventbrite.com/o/lovestruck-books-92052235443", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "books"},
    {"name": "The Comedy Studio", "url": "https://thecomedystudio.com/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "comedy"},
]

# Drop venues that require env vars we don't have set — keeps the fail banner clean.
VENUES = [v for v in _ALL_VENUES if not v.get("requires_env") or os.environ.get(v["requires_env"])]


# Static "useful links" — venues with no machine-readable calendar, but worth linking.
# Rendered in the "Useful links & ongoing" section.
STATIC_LINKS = [
    ("music", "Cantab Lounge", "https://thecantablounge.com/"),
    ("dance", "Boston Lindy Hop — swing dances list", "https://bostonlindyhop.com/events/swing-dancing-in-boston/"),
    ("dance", "Loretta's Last Call (line dancing, swing)", "https://lorettaslastcall.com/events/"),
    ("dance", "Boston Swing Central", "https://www.bostonswingcentral.org/"),
    ("dance", "Tango Society of Boston", "https://bostontango.org/"),
    ("theater", "American Repertory Theater", "https://americanrepertorytheater.org/shows-events/"),
    ("theater", "Huntington Theatre", "https://www.huntingtontheatre.org/season/"),
    ("art",     "MFA Boston programs", "https://www.mfa.org/programs"),
    ("art",     "Harvard Art Museums calendar", "https://harvardartmuseums.org/calendar"),
    ("comedy",  "Laugh Boston", "https://laughboston.com/"),
    ("comedy",  "Improv Asylum (North End)", "https://www.improvasylum.com/shows"),
    ("theater", "SpeakEasy Stage Company", "https://www.speakeasystage.com/season"),
    ("theater", "Lyric Stage Company", "https://www.lyricstage.com/productions/"),
    ("theater", "Company One Theatre", "https://companyone.org/onstage/"),
    ("theater", "Commonwealth Shakespeare", "https://commshakes.org/season/"),
    ("music",   "Boston Symphony Orchestra", "https://www.bso.org/performances"),
    ("music",   "Boston Lyric Opera", "https://www.blo.org/performances/"),
    ("music",   "Handel and Haydn Society", "https://handelandhaydn.org/concerts/"),
    ("music",   "Celebrity Series of Boston", "https://www.celebrityseries.org/calendar/"),
    ("music",   "Berklee Performance Center", "https://www.berklee.edu/BPC"),
    ("gaming",  "Balance Patch", "https://www.balancepatch.com/events"),
]


# Cheap-ticket / lottery / deal aggregators. Rendered in their own sidebar block.
DEAL_LINKS = [
    ("LuckySeat (Boston lotteries)", "https://www.luckyseat.com/"),
    ("BosTix — same-day half-price (ArtsBoston)", "https://artsboston.org/bostix/"),
    ("TodayTix Boston (lotteries + discounts)", "https://www.todaytix.com/boston-ma"),
    ("Goldstar Boston discounts", "https://www.goldstar.com/cities/boston-ma"),
]


# Hand-curated weekly recurring events for venues that don't publish a
# structured calendar. Expanded into concrete dated entries at request time.
# Tuple: (venue_name, venue_url, default_category, [(title, event_url, weekday 0=Mon..6=Sun, hour, minute), ...])
MANUAL_RECURRING_EVENTS = [
    ("Loretta's Last Call", "https://www.lorettaslastcall.com/events/", "dance", [
        ("Partner Swing Dancing", "https://www.lorettaslastcall.com/event/partner-swing-dancing-on-mondays/", 0, 20, 0),
        ("Live Band Line Dancing", "https://www.lorettaslastcall.com/event/live-band-line-dancing/", 2, 20, 0),
        ("Sunday Line Dancing", "https://www.lorettaslastcall.com/event/sunday-line-dancing/", 6, 18, 0),
    ]),
    ("Versus Boston", "https://www.versusboston.com/", "gaming", [
        ("Madden Madness Mondays", "https://www.versusboston.com/", 0, 19, 0),
        ("Tekken Thursdays", "https://www.versusboston.com/", 3, 19, 0),
        ("Super Smash Bros Tournament", "https://www.versusboston.com/", 6, 19, 0),
    ]),
    ("Havana Club", "https://havanaclubsalsa.com/", "dance", [
        ("Bachata Mondays", "https://havanaclubsalsa.com/mondays", 0, 20, 15),
        ("Salsa/Bachata Tuesdays", "https://havanaclubsalsa.com/tuesdays", 1, 20, 15),
        ("Bachata Thursdays", "https://havanaclubsalsa.com/thursdays", 3, 20, 45),
        ("Friday Night Bachata/Salsa", "https://havanaclubsalsa.com/fridays", 4, 21, 15),
        ("Bachata/Salsa Saturdays", "https://havanaclubsalsa.com/saturdays", 5, 21, 15),
        ("Bachata Sundays", "https://havanaclubsalsa.com/sundays", 6, 19, 15),
    ]),
]


def _expand_manual_recurring(weeks=8):
    """Expand MANUAL_RECURRING_EVENTS into synthetic venue results with concrete dates."""
    today = datetime.now(EASTERN).date()
    results = []
    for venue, venue_url, default_cat, items in MANUAL_RECURRING_EVENTS:
        events = []
        for name, url, weekday, hour, minute in items:
            ahead = (weekday - today.weekday()) % 7
            first = today + timedelta(days=ahead)
            for i in range(weeks):
                d = first + timedelta(weeks=i)
                dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": url,
                    "venue": venue,
                    "price": None,
                    "category": default_cat,
                })
        results.append({"venue": venue, "url": venue_url, "events": events, "error": None})
    return results


CATEGORY_KEYWORDS = [
    ("dance",     ["salsa", "bachata", "kizomba", "merengue", "tango", "swing dance", "swing dancing",
                   "lindy hop", "balboa", "blues dance", "contra dance", "zouk", "cha-cha", "cha cha",
                   "west coast swing", "ballroom dance", "ballroom dancing", "waltz", "milonga",
                   "dance social", "dance party", "dance night", "dance class", "dance lesson",
                   "dance workshop", "social dance", "havana club", "bachata room"]),
    ("comedy",    ["comedy", "stand-up", "stand up", "improv", "open mic"]),
    ("theater",   ["theatre", "theater", "musical", "shakespeare", "broadway", "repertory", "play by", "play:"]),
    ("books",     ["book club", "book launch", "author", "reading", "storytime", "poet", "signing", "booksmith"]),
    ("gaming",    ["arcade", "mahjong", "chess", "trivia", "board game", "video game", "ttrpg", "d&d", "dungeons"]),
    ("clubbing",  ["dj ", " dj", "edm", "house music", "techno", "rave", "dubstep", "club night"]),
    ("music",     ["tour", "concert", " band ", "live music", "music series", "music hall", "orchestra", "symphony", "karaoke", "jazz", "hip hop", "rap"]),
    ("film",      ["screening", "film ", "cinema", "movie night", "brattle", "coolidge"]),
    ("sports",    ["bruins", "celtics", "red sox", "revolution", "marathon", "vs.", "match", "game "]),
    ("food",      ["tasting", "brewery", "brewing", "beer", "wine", "dinner", "brunch", "pop-up",
                   "oyster", "cocktail", "martini", "happy hour", "taproom", "bar night", "fondue",
                   "taqueria", "tavern", "sushi", "maki", "whiskey", "bourbon", "food truck", "menu"]),
    ("family",    ["kids", "children", "family", "toddler", "princess", "easter", "storytime"]),
    ("art",       ["exhibition", "gallery", "museum", "sculpture", "painting", "curator",
                   "art show", "art walk", "art class", "pottery", "ceramics", "printmaking"]),
    ("community", ["parade", "patriots day", "block party", "festival", " fair ", "fair!",
                   "gathering", "protest", "rally", "earth day", "earth week", "clean up",
                   "volunteer", "community", "civic", "town hall", "open house", "meetup"]),
]


def infer_category(name, venue, default=None):
    text = f"{name or ''} {venue or ''}".lower()
    for cat, kws in CATEGORY_KEYWORDS:
        if any(k in text for k in kws):
            return cat
    return default or "other"


CATEGORY_STYLES = {
    "music":    ("#7aa2f7", "♪"),
    "dance":    ("#ff7ab2", "💃"),
    "comedy":   ("#f0a07a", "☺"),
    "theater":  ("#f7768e", "🎭"),
    "books":    ("#9ece6a", "📖"),
    "gaming":   ("#bb9af7", "◆"),
    "clubbing": ("#e06c75", "◉"),
    "film":     ("#e0af68", "▶"),
    "sports":   ("#73daca", "⚑"),
    "outdoors": ("#4fbf8f", "⛰"),
    "food":     ("#c678dd", "🍺"),
    "family":   ("#ffb8d1", "✦"),
    "art":      ("#ffd866", "✦"),
    "community":("#8fa1b3", "◯"),
    "other":    ("#6b7280", "·"),
}


CATEGORY_BUCKETS = [
    ("Music & nightlife", ["music", "clubbing"]),
    ("Dance",             ["dance"]),
    ("Stage",             ["comedy", "theater"]),
    ("Arts & culture",    ["books", "film", "art"]),
    ("Play",              ["gaming", "sports", "outdoors", "family"]),
    ("Food & drink",      ["food"]),
    ("Community",         ["community", "other"]),
]
_CAT_TO_BUCKET = {cat: name for name, cats in CATEGORY_BUCKETS for cat in cats}


def category_bucket(cat):
    return _CAT_TO_BUCKET.get(cat or "other", "Community")


_cache = {"data": None, "ts": 0.0}
_luckyseat_cache = {"data": None, "ts": 0.0}
_weather_cache = {"data": None, "ts": 0.0}


# WMO weather code → (emoji, short label). https://open-meteo.com/en/docs#weathervariables
_WMO_ICON = {
    0: ("☀️", "Clear"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Cloudy"),
    45: ("🌫️", "Foggy"), 48: ("🌫️", "Foggy"),
    51: ("🌦️", "Drizzle"), 53: ("🌦️", "Drizzle"), 55: ("🌦️", "Drizzle"),
    61: ("🌧️", "Rain"), 63: ("🌧️", "Rain"), 65: ("🌧️", "Heavy rain"),
    66: ("🌧️", "Freezing rain"), 67: ("🌧️", "Freezing rain"),
    71: ("🌨️", "Snow"), 73: ("🌨️", "Snow"), 75: ("❄️", "Heavy snow"),
    77: ("🌨️", "Snow grains"),
    80: ("🌦️", "Showers"), 81: ("🌧️", "Showers"), 82: ("⛈️", "Heavy showers"),
    85: ("🌨️", "Snow showers"), 86: ("❄️", "Snow showers"),
    95: ("⛈️", "Thunderstorm"), 96: ("⛈️", "T-storm w/ hail"), 99: ("⛈️", "T-storm w/ hail"),
}


def fetch_boston_weather():
    """Current Boston temp + condition. Cached for 30 min."""
    if _weather_cache["data"] is not None and time.time() - _weather_cache["ts"] < 30 * 60:
        return _weather_cache["data"]
    out = None
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 42.36, "longitude": -71.06,
                "current": "temperature_2m,weather_code",
                "temperature_unit": "fahrenheit",
                "timezone": "America/New_York",
            },
            timeout=8,
        )
        r.raise_for_status()
        cur = r.json().get("current") or {}
        temp = cur.get("temperature_2m")
        code = cur.get("weather_code")
        icon, label = _WMO_ICON.get(code, ("🌡️", "—"))
        if temp is not None:
            out = {"temp": round(temp), "icon": icon, "label": label}
    except Exception:
        out = None
    _weather_cache["data"] = out
    _weather_cache["ts"] = time.time()
    return out


def fetch_luckyseat_boston():
    """Fetch LuckySeat's show list and filter to Boston. Cached for 15 min."""
    if _luckyseat_cache["data"] is not None and time.time() - _luckyseat_cache["ts"] < CACHE_SECONDS:
        return _luckyseat_cache["data"]
    shows = []
    try:
        resp = requests.get(
            "https://www.luckyseat.com/api/showmanagement/getshowlist",
            headers={"User-Agent": UA_SAFARI, "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        for s in resp.json():
            if (s.get("city") or "").lower() != "boston":
                continue
            if not s.get("isActive") or s.get("isTempClosed"):
                continue
            shows.append({
                "name": s.get("showName"),
                "venue": s.get("eventLocation"),
                "price": s.get("priceAndFeesTotal"),
                "url": f"https://www.luckyseat.com/shows/{s.get('showAlias')}" if s.get("showAlias") else "https://www.luckyseat.com/",
            })
    except Exception:
        shows = []
    _luckyseat_cache["data"] = shows
    _luckyseat_cache["ts"] = time.time()
    return shows


def dedupe(events):
    seen = set()
    out = []
    for e in events:
        key = ((e.get("name") or "").lower(), e.get("date") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _sort_key(e):
    try:
        return datetime.fromisoformat(e["date"].replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, AttributeError):
        return float("inf")


def _scrape_one(v):
    try:
        events = dedupe(v["scraper"](v["url"], v["ua"]))
        for e in events:
            if not e.get("category"):
                e["category"] = infer_category(e.get("name"), e.get("venue"), v.get("default_category"))
        events.sort(key=_sort_key)
        return {"venue": v["name"], "url": v["url"], "events": events, "error": None}
    except Exception as e:
        return {"venue": v["name"], "url": v["url"], "events": [], "error": str(e)}


def get_all_events(force=False):
    if not force and _cache["data"] and time.time() - _cache["ts"] < CACHE_SECONDS:
        return _cache["data"]
    with ThreadPoolExecutor(max_workers=min(16, len(VENUES))) as ex:
        results = list(ex.map(_scrape_one, VENUES))
    order = {v["name"]: i for i, v in enumerate(VENUES)}
    results.sort(key=lambda r: order.get(r["venue"], 999))
    results.extend(_expand_manual_recurring())
    _cache["data"] = results
    _cache["ts"] = time.time()
    return results


def format_time(s):
    if not s:
        return "TBA"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return s
    return dt.astimezone(EASTERN).strftime("%-I:%M %p")


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
    from collections import defaultdict
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


CITY_RULES = [
    ("somerville", (
        "aeronaut", "crystal ballroom", "somerville theatre", "somerville theater",
        "somerville, ma", "davis square", "assembly row", "union square, somerville",
        "the burren", "burren", "mccarthy's toad", "mccarthys toad", "remnant somerville",
        "comedy studio", "bow market",
    )),
    ("cambridge", (
        "mit ", "m.i.t", "harvard square", "harvard book", "porter square", "sinclair",
        "brattle", "cambridge, ma", "kendall", "central square", "inman square",
        "havetodance", "have to dance", "ywca cambridge",
        "middle east", "sonia", "regattabar", "arrow street",
        "harvard museum of natural history", "hmnh",
        "lovestruck", "lovestruck books",
    )),
    ("boston", (
        "city winery", "royale", "wilbur", "ica boston", "gardner", "boston public library",
        "laugh boston", "big night live", "house of blues", "paradise rock", "orpheum",
        "td garden", "mgm music hall", "citizens house of blues", "fenway", "back bay",
        "downtown crossing", "seaport", "boston, ma", "boston common", "trident booksellers",
        "havana club",
        "loretta", "versus boston", "opera house", "symphony hall", "brighton music hall",
        "boch center", "wang theatre", "boston conservatory", "the beehive", "play boston",
        "petit robert", "the grand",
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


def render_page(results):
    dated, tba, ongoing = group_by_date(results)
    recurring_keys = compute_recurring(dated)
    total = sum(len(v) for _, v in dated) + len(tba)
    failed = [r for r in results if r["error"]]
    all_venue_names = [r["venue"] for r in results]

    def is_recurring(e):
        return (
            (e.get("name") or "").strip().lower(),
            e.get("_source_venue") or "",
        ) in recurring_keys

    def render_event(e):
        title = escape(e.get("name") or "Untitled")
        link = (
            f'<a href="{escape(e["url"])}" target="_blank" rel="noopener">{title}</a>'
            if e.get("url") else title
        )
        price = escape(e["price"]) if e.get("price") else ""
        price_tag = f'<span class="price">{price}</span>' if price else ""
        cat = e.get("category") or "other"
        bucket = category_bucket(cat)
        color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
        cat_tag = f'<span class="cat" style="color:{color}">{icon} {escape(cat)}</span>'
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
        return f'''<li class="event" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}" data-venue="{escape(source)}" data-city="{escape(city)}" data-recur="{recur_flag}">
          <div class="when">{escape(format_time(e.get("date")))}</div>
          <div class="what">{link}{price_tag}{recur_badge}
            <div class="venue-tag">{cat_tag} · {venue_html}{(" · " + alt_html) if alt_html else ""}</div>
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
  :root {{ --bg:#0f1115; --card:#171923; --fg:#e6e8ef; --muted:#9aa3b2; --accent:#7aa2f7; --warn:#f0a07a; --border:#222634; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; background:var(--bg); color:var(--fg); line-height:1.5; }}
  .banner {{ position:relative; height: 240px; overflow:hidden; }}
  .banner svg {{ width: 100%; height: 100%; display: block; }}
  .banner .title {{ position:absolute; inset:0; display:flex; flex-direction:column; justify-content:flex-end; padding: 0 24px 20px; max-width: 1200px; margin: 0 auto; }}
  .banner h1 {{ margin: 0; font-size: 40px; letter-spacing: -0.02em; color: #fff; text-shadow: 0 2px 14px rgba(0,0,0,0.55); font-weight: 800; }}
  .banner p {{ margin: 4px 0 0; color: #fff4d6; font-size: 13px; text-shadow: 0 1px 6px rgba(0,0,0,0.55); }}
  .banner a {{ color: #ffd866; text-decoration: none; }}
  .layout {{ max-width: 1320px; margin: 0 auto; padding: 20px 24px 48px; display: grid; grid-template-columns: 240px minmax(0, 1fr) 240px; gap: 18px; align-items: start; }}
  aside.filters {{ position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; display: flex; flex-direction: column; gap: 12px; padding-right: 4px; }}
  aside.filters::-webkit-scrollbar, aside.useful::-webkit-scrollbar {{ width: 6px; }}
  aside.filters::-webkit-scrollbar-thumb, aside.useful::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  aside.useful {{ position: sticky; top: 12px; max-height: calc(100vh - 24px); overflow-y: auto; }}
  aside.useful {{ display: flex; flex-direction: column; gap: 12px; }}
  aside.useful .useful-inner {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px 14px; }}
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
  main {{ display: flex; flex-direction: column; gap: 18px; min-width: 0; }}
  .day {{ background: var(--card); border:1px solid var(--border); border-radius: 14px; padding: 14px 18px 10px; }}
  .day h2 {{ margin: 0 0 10px; font-size: 17px; font-weight: 700; display:flex; align-items:center; gap:8px; color: var(--fg); position: sticky; top: 0; background: var(--card); padding: 4px 0 8px; z-index: 2; }}
  .count {{ background: var(--border); color: var(--muted); font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; }}
  .cities {{ display: flex; flex-direction: column; gap: 14px; }}
  .city-section {{ --city-color: var(--accent); border-top: 1px solid var(--border); padding-top: 10px; padding-left: 10px; border-left: 3px solid var(--city-color); }}
  .city-section:first-child {{ border-top: none; padding-top: 0; }}
  .city-section.empty {{ display: none; }}
  .city-section[data-city="boston"]    {{ --city-color: #5d9bff; }}
  .city-section[data-city="cambridge"] {{ --city-color: #e05a6b; }}
  .city-section[data-city="somerville"]{{ --city-color: #f29e4c; }}
  .city-section[data-city="other"]     {{ --city-color: #9aa3b2; }}
  .city-head {{ margin: 0 0 6px; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--city-color); display: flex; align-items: center; gap: 8px; }}
  .city-head .count {{ background: transparent; color: var(--muted); font-weight: 500; letter-spacing: 0; }}
  .buckets {{ display: flex; flex-direction: column; gap: 10px; }}
  .bucket {{ border-left: 3px solid var(--accent, #444); padding: 2px 0 2px 12px; border-left-color: var(--accent); }}
  .bucket-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-weight: 600; }}
  .bucket-head .count {{ background: transparent; color: var(--muted); }}
  .bucket ul {{ list-style: none; padding: 0; margin: 0; }}
  .event {{ padding: 6px 0; border-top: 1px dashed rgba(255,255,255,0.06); display:grid; grid-template-columns: 70px 1fr; gap: 10px; font-size: 14px; }}
  .event:first-child {{ border-top: none; }}
  .when {{ color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 2px; }}
  .what a {{ color: var(--accent); text-decoration: none; }}
  .what a:hover {{ text-decoration: underline; }}
  .venue-tag {{ color: var(--muted); font-size: 11px; margin-top: 2px; }}
  .venue-link {{ color: var(--muted); text-decoration: none; border-bottom: 1px dotted rgba(154,163,178,0.4); }}
  .venue-link:hover {{ color: var(--fg); border-bottom-color: var(--fg); }}
  .price {{ display:inline-block; margin-left: 8px; background: var(--border); color: var(--muted); font-size: 11px; padding: 1px 6px; border-radius: 4px; }}
  .cat {{ font-size: 11px; font-weight: 500; margin-right: 4px; }}
  .recur {{ display:inline-block; margin-left: 8px; background: rgba(255,122,178,0.14); color: #ff7ab2; font-size: 10px; padding: 1px 6px; border-radius: 4px; letter-spacing: 0.02em; }}
  .alt-sources {{ color: var(--muted); font-size: 11px; }}
  .alt-sources a {{ color: var(--accent); text-decoration: none; }}
  .alt-sources a:hover {{ text-decoration: underline; }}
  .bucket.empty {{ display: none; }}
  .filter-group {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; }}
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
  .event.hidden {{ display: none; }}
  .day.empty, .day.out-of-week {{ display: none; }}
  .week-nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 8px 12px; }}
  .week-nav.bottom {{ justify-content: center; }}
  .week-nav button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; font-family: inherit; }}
  .week-nav button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .week-nav button[aria-pressed="true"], .week-nav button.active {{ background: var(--accent); color: #0f1115; border-color: var(--accent); }}
  #week-label, #week-label-b {{ font-size: 13px; font-weight: 600; color: var(--fg); flex: 1; text-align: center; min-width: 160px; }}
  .week-nav.bottom #week-label-b {{ flex: 0; padding: 0 12px; }}
  .mini-cal {{ background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; }}
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
  .mini-cal-grid .d.in-week {{ background: rgba(122,162,247,0.12); color: var(--fg); }}
  .mini-cal-grid .d.anchor {{ background: var(--accent); color: #0f1115; font-weight: 700; }}
  .mini-cal-grid .d.anchor::after {{ background: #0f1115; }}
  .mini-cal-grid .d.blank {{ cursor: default; }}
  .mini-cal-grid .d:not(.blank):hover {{ border-color: var(--accent); }}
  .ongoing {{ margin-top: 4px; }}
  .ongoing h2 {{ margin: 0 0 4px; font-size: 15px; font-weight: 600; display:flex; align-items:center; gap:8px; color: var(--fg); }}
  .ongoing .hint {{ margin: 0 0 10px; color: var(--muted); font-size: 12px; }}
  .ongoing ul {{ list-style: none; padding: 14px 18px; margin: 0; background: var(--card); border: 1px solid var(--border); border-radius: 12px; max-height: 420px; overflow-y: auto; }}
  .ongoing .event {{ padding: 8px 0; border-top: 1px solid var(--border); display:grid; grid-template-columns: 1fr; gap: 4px; font-size: 14px; }}
  .ongoing .event:first-child {{ border-top: none; }}
  .ongoing .when {{ display: none; }}
  .fail {{ max-width: 1200px; margin: 0 auto; padding: 8px 24px; color: var(--warn); font-size: 12px; }}
  .fail a {{ color: var(--warn); }}
  .other-note {{ max-width: 1200px; margin: 0 auto; padding: 4px 24px 0; color: var(--muted); font-size: 11px; }}
  footer {{ max-width: 1200px; margin: 0 auto; padding: 0 24px 32px; color: var(--muted); font-size: 12px; }}
  @media (max-width: 1100px) {{
    .layout {{ grid-template-columns: 240px minmax(0, 1fr); }}
    aside.useful {{ position: static; grid-column: 1 / -1; max-height: none; }}
  }}
  @media (max-width: 860px) {{
    .layout {{ grid-template-columns: minmax(0, 1fr); }}
    aside.filters {{ position: static; max-height: none; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    aside.filters > * {{ grid-column: auto; }}
    .filter-group.venues {{ grid-column: 1 / -1; }}
  }}
</style>
</head>
<body>
  <div class="banner">
    {BANNER_SVG}
    <div class="title">
      <h1>Boston Events</h1>
      <p>{total} events across {len(results)} venues · cached 15 min · <a href="/?refresh=1">refresh</a></p>
    </div>
  </div>
  {fail_banner}
  {other_note}
  <div class="layout">
    <aside class="filters">
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
    let showAll = false;
    let calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);

    function weekDates() {{
      const out = [];
      for (let i = 0; i < 7; i++) out.push(fmtISO(addDays(anchor, i)));
      return out;
    }}
    function updateWeekLabel() {{
      const end = addDays(anchor, 6);
      const label = showAll
        ? 'Showing all upcoming'
        : `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      document.getElementById('week-label').textContent = label;
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const btn = document.getElementById('week-all');
      btn.textContent = showAll ? 'week view' : 'show all';
      btn.setAttribute('aria-pressed', showAll ? 'true' : 'false');
    }}

    function apply() {{
      const cats = new Set(Array.from(catBoxes).filter(b => b.checked).map(b => b.value));
      const venues = new Set(Array.from(venueBoxes).filter(b => b.checked).map(b => b.value));
      const recurs = new Set(Array.from(recurBoxes).filter(b => b.checked).map(b => b.value));
      const cities = new Set(Array.from(cityBoxes).filter(b => b.checked).map(b => b.value));
      const week = new Set(weekDates());
      document.querySelectorAll('.event').forEach(li => {{
        const catOk = cats.has(li.dataset.bucket);
        const venueOk = venues.has(li.dataset.venue);
        const recurOk = recurs.has(li.dataset.recur);
        const cityOk = cities.has(li.dataset.city);
        li.classList.toggle('hidden', !(catOk && venueOk && recurOk && cityOk));
      }});
      document.querySelectorAll('.bucket').forEach(b => {{
        const visible = b.querySelectorAll('.event:not(.hidden)').length;
        b.classList.toggle('empty', visible === 0);
      }});
      document.querySelectorAll('.city-section').forEach(sec => {{
        const visible = sec.querySelectorAll('.event:not(.hidden)').length;
        sec.classList.toggle('empty', visible === 0);
      }});
      daySections.forEach(day => {{
        const date = day.dataset.date;
        const inWeek = showAll || date === 'tba' || week.has(date);
        day.classList.toggle('out-of-week', !inWeek);
        const visible = day.querySelectorAll('.event:not(.hidden)').length;
        day.classList.toggle('empty', visible === 0);
      }});
      renderCal();
      updateWeekLabel();
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
      showAll = false;
      anchor = addDays(anchor, delta);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}
    function setAnchor(iso) {{
      showAll = false;
      anchor = parseISO(iso);
      apply();
    }}

    document.getElementById('week-prev').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-prev-b').addEventListener('click', () => shiftWeek(-7));
    document.getElementById('week-next-b').addEventListener('click', () => shiftWeek(7));
    document.getElementById('week-today').addEventListener('click', () => {{ setAnchor(todayISO); calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1); apply(); }});
    document.getElementById('week-all').addEventListener('click', () => {{ showAll = !showAll; apply(); }});
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

    catBoxes.forEach(b => b.addEventListener('change', apply));
    venueBoxes.forEach(b => b.addEventListener('change', apply));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    document.getElementById('cat-all').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('cat-none').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('venue-all').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ cityBoxes.forEach(b => b.checked = false); apply(); }});

    apply();
  </script>
</body>
</html>"""


app = Flask(__name__)


@app.get("/")
def index():
    return render_page(get_all_events(force="refresh" in request.args))


@app.get("/api/events")
def api_events():
    return jsonify(get_all_events(force="refresh" in request.args))


if __name__ == "__main__":
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"Boston Events → http://{host}:{PORT}")
    app.run(host=host, port=PORT, debug=False)
