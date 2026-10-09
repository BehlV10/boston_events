"""Boston Events — venue scrapers and data definitions."""

import json
import os
import re
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from dateutil.rrule import rrulestr


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
UA_CURL = "curl/8.4.0"

_HS_CERTIFI = "/opt/homebrew/var/hs-certifi/cacert.pem"


def _make_session():
    """Return a requests.Session with HubSpot's corporate CA bundle.

    Python 3.14 enforces stricter X.509 Basic Constraints checks than prior
    versions.  The HubSpot network proxy re-signs TLS with a corporate CA that
    pre-dates this requirement, so we must clear VERIFY_X509_STRICT to allow it.
    NODE_EXTRA_CA_CERTS already points at the same bundle for Node; we mirror it.
    """
    ca = _HS_CERTIFI if os.path.exists(_HS_CERTIFI) else True
    ctx = ssl.create_default_context(cafile=ca if isinstance(ca, str) else None)
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT

    class _Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = ctx
            super().init_poolmanager(*args, **kwargs)

    s = requests.Session()
    s.mount("https://", _Adapter())
    return s


_SESSION = _make_session()


def fetch_soup(url, ua):
    resp = _SESSION.get(
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


def _eventbrite_org_json_events(html, base_url):
    events = []
    seen = set()
    for chunk in html.split('"eventbrite_event_id":"')[1:]:
        def field(key):
            m = re.search(r'"%s":"((?:[^"\\]|\\.)*)"' % key, chunk)
            return json.loads(f'"{m.group(1)}"') if m else None
        name, href, start_date = field("name"), field("url"), field("start_date")
        if not name or not href or not start_date or href in seen:
            continue
        if re.search(r'"is_cancelled":true', chunk[:1500]):
            continue
        seen.add(href)
        try:
            start = datetime.strptime(f"{start_date} {field('start_time') or '19:00:00'}", "%Y-%m-%d %H:%M:%S")
            start = start.replace(tzinfo=ZoneInfo(field("timezone") or "America/New_York"))
            iso = start.astimezone(timezone.utc).isoformat()
        except (ValueError, KeyError):
            iso = None
        price = None
        if re.search(r'"is_free":true', chunk):
            price = "Free"
        else:
            p = re.search(r'"minimum_ticket_price":\{[^}]*?"major_value":"([\d.]+)"', chunk)
            if p:
                price = f"${float(p.group(1)):g}"
        venue = re.search(r'"primary_venue":\{[^{}]*?"name":"((?:[^"\\]|\\.)*)"', chunk)
        events.append({
            "name": name,
            "date": iso,
            "url": href,
            "venue": json.loads(f'"{venue.group(1)}"') if venue else None,
            "price": price,
        })
    return events


def scrape_eventbrite_org(url, ua):
    """Parse Eventbrite organizer page cards (used for Aeronaut, Versus)."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    json_events = _eventbrite_org_json_events(resp.text, url)
    if json_events:
        return json_events
    soup = BeautifulSoup(resp.text, "html.parser")
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
        resp = _SESSION.get(
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


_BC_GOES_UNTIL_RE = re.compile(r"goes until\s+(\d{1,2})/(\d{1,2})", re.IGNORECASE)
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


_BC_NOISE_PREFIXES = re.compile(
    r"^((?:the\s+)?\d+\s+(places|things|bars|beaches|best|hidden|independent|spots|ways|reasons|tips|ideas)\b"
    r"|top\s+\d+"
    r"|(?:boston\s+)?neighborhood guide:"
    r"|boston'?s\s+(best|only|top|most|oldest)"
    r"|how\s+to\s+(celebrate|spend|find|get|make|visit)"
    r"|join\s+our\s+team"
    r"|day\s+trips?\s+from\s+boston"
    r"|\d+\s+hidden\s+gems)",
    re.I,
)
_BC_NOISE_CONTAINS = re.compile(
    r"\|\s*(now\s+open|opening\s+soon|grand\s+opening)"
    r"|\bnow\s+open\b"
    r"|new\s+(location|opening)\s+(in|at)\b"
    r"|skip\s+the\s+(traffic|drive)\b",
    re.I,
)
# Standalone restaurant-type words that make it a listing, not an event
_BC_RESTAURANT_STANDALONE = re.compile(
    r"\b(steakhouse|chophouse|trattoria|brasserie|gastropub|rotisserie"
    r"|patisserie|boulangerie|enoteca|supper\s+club)\b"
    r"[^|]*\|",
    re.I,
)
# "Name: [nationality/descriptor cuisine/fare/plates] | Neighborhood" — colon required
_BC_RESTAURANT_DESCRIBED = re.compile(
    r":[^|]*\b(?:cuisine|fare|plates|kitchen|small\s+plates)"
    r"[^|]*\|",
    re.I,
)
# Nationality + cuisine type without a colon: "Capri Italian Steakhouse" style
_BC_NATIONALITY_CUISINE = re.compile(
    r"\b(?:american|italian|french|mediterranean|japanese|chinese|greek|thai"
    r"|indian|korean|vietnamese|peruvian|latin|portuguese|turkish|cambodian"
    r"|cajun|mexican|spanish|lebanese|moroccan|ethiopian|haitian|jamaican"
    r"|salvadoran|colombian|taiwanese|szechuan|cantonese)\s+"
    r"(?:steakhouse|chophouse|bistro|brasserie|trattoria|cuisine|kitchen|eatery|fare|seafood)\b"
    r"[^|]*\|",
    re.I,
)


def _bc_is_noise(name):
    if _BC_NOISE_PREFIXES.match(name) or _BC_NOISE_CONTAINS.search(name):
        return True
    if " | " in name and (
        _BC_RESTAURANT_STANDALONE.search(name)
        or _BC_RESTAURANT_DESCRIBED.search(name)
        or _BC_NATIONALITY_CUISINE.search(name)
    ):
        return True
    return False


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
            if not name or _bc_is_noise(name):
                continue
            href = urljoin(day_url, a.get("href", ""))
            if href in seen_urls:
                continue
            seen_urls.add(href)
            time_el = li.select_one(".time")
            loc_el = li.select_one(".location")
            raw_time = time_el.get_text(" ", strip=True) if time_el else ""
            iso = _parse_boston_calendar_time(raw_time)
            entry = {
                "name": name,
                "date": iso,
                "url": href,
                "venue": loc_el.get_text(strip=True) if loc_el else None,
                "price": None,
            }
            until = _BC_GOES_UNTIL_RE.search(raw_time)
            if iso is None and until:
                end_month, end_day = int(until.group(1)), int(until.group(2))
                end_year = d.year + (1 if end_month < d.month else 0)
                entry["ends"] = f"{end_year:04d}-{end_month:02d}-{end_day:02d}"
            events.append(entry)
    if events:
        top = events[:30]
        with ThreadPoolExecutor(max_workers=8) as ex:
            externals = list(ex.map(lambda e: _bc_external_url(e["url"], ua), top))
        for e, ext in zip(top, externals):
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
        r = _SESSION.get(f"https://tunehatch.com/api/v1/entities/venue/{slug}", timeout=15,
                         headers={"User-Agent": ua, "Accept": "application/json"})
        r.raise_for_status()
        venue_id = (r.json() or {}).get("id")
        if not venue_id:
            return []
    r = _SESSION.get("https://tunehatch.com/api/v1/shows", params={"venue_id": venue_id}, timeout=15,
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
        raw = block.get_text() or ""
        try:
            d = json.loads(raw.strip(), strict=False)
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


def _format_price_range(mn, mx, currency="USD"):
    if mn is None:
        return None
    sym = "$" if currency == "USD" else f"{currency} "
    if mx is None or mx == mn:
        return f"{sym}{mn:.0f}"
    return f"{sym}{mn:.0f}–{mx:.0f}"


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
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
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
    resp = _SESSION.get(
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


_BSO_TYPESENSE_KEY = "qoWHCTjesGfIaxdXbw9vOgod1VToEXNI"
_BSO_TYPESENSE_HOST = "https://go8f04wi19tuvlyrp-1.a1.typesense.net"


def scrape_bso(url, ua):
    """BSO/Boston Pops events via the public Typesense search API embedded in bso.org."""
    now_ts = int(time.time())
    cutoff = now_ts + 8 * 7 * 24 * 3600
    params = {
        "q": "*",
        "query_by": "title",
        "filter_by": f"show_in_cal:true && performance_date:>{now_ts} && performance_date:<{cutoff}",
        "sort_by": "performance_date:asc",
        "per_page": 250,
        "x-typesense-api-key": _BSO_TYPESENSE_KEY,
    }
    resp = _SESSION.get(
        f"{_BSO_TYPESENSE_HOST}/collections/performances/documents/search",
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for hit in resp.json().get("hits", []):
        doc = hit.get("document", {})
        if doc.get("event_brand") == "Tanglewood":
            continue
        venues = doc.get("performance_venue") or []
        venue_display = venues[0].get("display_name", "Symphony Hall") if venues else "Symphony Hall"
        link = doc.get("event_link") or ""
        events.append({
            "name": doc.get("title"),
            "date": datetime.fromtimestamp(doc["performance_date"], tz=timezone.utc).isoformat(),
            "url": f"https://www.bso.org{link}" if link else "https://www.bso.org/events",
            "venue": venue_display,
            "price": None,
            "category": "music",
        })
    return events


def scrape_venture_cafe(url, ua):
    """Venture Café Cambridge — WordPress/Tribe Events Calendar with JSON-LD."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(timezone.utc)
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
                dt = datetime.fromisoformat(iso).astimezone(timezone.utc)
            except (ValueError, TypeError, AttributeError):
                continue
            if dt < now:
                continue
            events.append({
                "name": ev.get("name"),
                "date": dt.isoformat(),
                "url": ev.get("url") or url,
                "venue": "Venture Café Cambridge",
                "price": None,
                "category": "community",
            })
    return events


def _ical_events(text):
    events = []
    current = None
    in_alarm = False
    lines = []
    for raw in text.splitlines():
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    for line in lines:
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif line == "BEGIN:VALARM":
            in_alarm = True
        elif line == "END:VALARM":
            in_alarm = False
        elif current is not None and not in_alarm and ":" in line:
            head, _, val = line.partition(":")
            current.setdefault(head.split(";")[0].upper(), []).append((head, val))
    return events


def _ical_parse_dt(head, value):
    params = head.split(";")[1:]
    value = value.strip()
    if len(value) == 8:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=EASTERN)
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    tz = EASTERN
    for p in params:
        if p.upper().startswith("TZID="):
            try:
                tz = ZoneInfo(p[5:])
            except Exception:
                tz = EASTERN
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=tz)


def _ical_text(event, key):
    vals = event.get(key)
    if not vals:
        return ""
    return vals[0][1].replace("\\n", " ").replace("\\,", ",").strip()


def scrape_ical(url, ua):
    """Fetch and parse a public iCal (.ics) feed — works for Google Calendar and others."""
    resp = _SESSION.get(url, headers={"User-Agent": ua, "Accept": "text/calendar,*/*"}, timeout=15)
    if resp.status_code in (429, 403):
        return []
    resp.raise_for_status()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(weeks=8)
    vevents = _ical_events(resp.text)
    overridden = {}
    for ev in vevents:
        if "RECURRENCE-ID" in ev:
            try:
                rid = _ical_parse_dt(*ev["RECURRENCE-ID"][0])
            except ValueError:
                continue
            overridden.setdefault(_ical_text(ev, "UID"), set()).add(rid.astimezone(timezone.utc))
    events = []
    for ev in vevents:
        summary = _ical_text(ev, "SUMMARY")
        if not summary or "DTSTART" not in ev or _ical_text(ev, "STATUS").upper() == "CANCELLED":
            continue
        try:
            start = _ical_parse_dt(*ev["DTSTART"][0])
        except ValueError:
            continue
        starts = [start]
        if "RRULE" in ev and "RECURRENCE-ID" not in ev:
            excluded = set(overridden.get(_ical_text(ev, "UID"), ()))
            for head, val in ev.get("EXDATE", []):
                for part in val.split(","):
                    try:
                        excluded.add(_ical_parse_dt(head, part).astimezone(timezone.utc))
                    except ValueError:
                        continue
            try:
                rule = rrulestr(ev["RRULE"][0][1], dtstart=start)
                starts = rule.between(now.astimezone(start.tzinfo), cutoff.astimezone(start.tzinfo), inc=True)
            except (ValueError, TypeError):
                pass
            starts = [d for d in starts if d.astimezone(timezone.utc) not in excluded]
        event_url = _ical_text(ev, "URL")
        if not event_url.startswith("http") or "google.com/calendar" in event_url:
            event_url = url
        desc = _ical_text(ev, "DESCRIPTION")
        price = None
        if re.search(r'\b(free\s+(?:admission|entry|event|dance|class)|no cover)\b', desc or "", re.I) or re.search(r'\bfree\b', summary or "", re.I):
            price = "Free"
        for dt in starts:
            dt_utc = dt.astimezone(timezone.utc)
            if dt_utc < now or dt_utc > cutoff:
                continue
            events.append({
                "name": summary,
                "date": dt_utc.isoformat(),
                "url": event_url,
                "venue": None,
                "location": _ical_text(ev, "LOCATION"),
                "price": price,
                "description": desc[:200] if desc else None,
            })
    return events


_ESPLANADE_CALENDAR_IDS = [
    "esplanadeinboston@gmail.com",
    "v6a9p6aden612efe4gu2tdjli8@group.calendar.google.com",
    "t4qs09kvust0gvnipv2v3k444g@group.calendar.google.com",
    "d1ft7lj5kroe2jcth37sfs2e84@group.calendar.google.com",
    "3gk26vmas99rmq6ilv4cgfdego@group.calendar.google.com",
    "l023g55dsugijg7puagrc6hpi8@group.calendar.google.com",
    "1uefeup9jrvvh1q7psrm7n3v3s@group.calendar.google.com",
]


def scrape_esplanade(url, ua):
    """Esplanade Association's public Google Calendars (embedded on esplanade.org/events)."""
    def fetch(cid):
        feed = f"https://calendar.google.com/calendar/ical/{quote(cid)}/public/basic.ics"
        return scrape_ical(feed, ua)
    with ThreadPoolExecutor(max_workers=len(_ESPLANADE_CALENDAR_IDS)) as ex:
        batches = list(ex.map(fetch, _ESPLANADE_CALENDAR_IDS))
    events = []
    for batch in batches:
        for e in batch:
            e["url"] = url
            location = e.pop("location", "")
            e["venue"] = location.split(",")[0].strip() or None
            events.append(e)
    return events


def scrape_manray(url, ua):
    """ManRay Cambridge — Simple Calendar plugin with itemprop startDate timestamps."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    for detail in soup.select(".simcal-event-details"):
        name_el = detail.find(class_="simcal-event-title")
        date_el = detail.find(class_="simcal-event-start-date")
        link_el = detail.find("a", href=lambda h: h and "google.com/calendar/event" in h)
        if not name_el or not date_el:
            continue
        name = name_el.get_text(strip=True)
        ts = date_el.get("data-event-start")
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (ValueError, TypeError):
            continue
        if dt < now:
            continue
        key = (name.lower(), dt.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": link_el["href"] if link_el else url,
            "venue": "ManRay",
            "price": None,
            "category": "clubbing",
        })
    return events


def scrape_do617(url, ua):
    """Do617 — Schema.org microdata embedded in server-rendered HTML."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(timezone.utc)
    seen = set()
    for card in soup.select('[itemprop="event"]'):
        name_el = card.find(itemprop="name")
        date_el = card.find(itemprop="startDate")
        loc_el = card.find(itemprop="location")
        if not name_el or not date_el:
            continue
        name = name_el.get_text(strip=True)
        iso = date_el.get("content", "")
        iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
        try:
            dt = datetime.fromisoformat(iso).astimezone(timezone.utc)
        except (ValueError, AttributeError):
            continue
        if dt < now:
            continue
        venue_name = None
        if loc_el:
            vn = loc_el.find(itemprop="name")
            venue_name = vn.get_text(strip=True) if vn else None
        permalink = card.get("data-permalink", "")
        event_url = f"https://do617.com{permalink}" if permalink else url
        key = (name.lower(), dt.date().isoformat())
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": event_url,
            "venue": venue_name,
            "price": None,
        })
    return events


def scrape_middle_east(url, ua):
    """Middle East Cambridge — TicketWeb plugin embeds event list as static HTML."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(EASTERN)
    year = now.year
    for section in soup.select(".tw-section"):
        link = section.find("a", href=lambda h: h and "ticketweb.com" in h)
        if not link:
            continue
        label = link.get("aria-label", "")
        m = re.match(r"Event Image Link-\s*(.*?)\s*\|", label)
        name = m.group(1).strip() if m else section.get_text(" ", strip=True)[:80]
        if not name:
            continue
        date_el = section.select_one(".tw-event-date")
        if not date_el:
            continue
        raw = date_el.get_text(strip=True)  # "5.19"
        try:
            month, day = (int(x) for x in raw.split("."))
            candidate = datetime(year, month, day, 19, 0, tzinfo=EASTERN)
            if candidate.date() < now.date():
                candidate = datetime(year + 1, month, day, 19, 0, tzinfo=EASTERN)
        except (ValueError, AttributeError):
            continue
        events.append({
            "name": name,
            "date": candidate.astimezone(timezone.utc).isoformat(),
            "url": link.get("href", url),
            "venue": "Middle East",
            "price": None,
            "category": "music",
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
    """Scrapes stand-up comedy shows from Laugh Boston (Seaport)."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(EASTERN)
    for col in soup.select(".col"):
        who = col.select_one(".who")
        when = col.select_one(".when")
        btn = col.select_one("a.btn")
        if not (who and when and btn):
            continue
        title = who.get_text(strip=True)
        raw_date = when.get_text(strip=True)
        ticket_url = btn.get("href")
        m = re.search(r"([A-Za-z]{3,9})\s+([A-Za-z]{3})\s+(\d{1,2})", raw_date)
        iso = None
        if m:
            _, mon, day = m.groups()
            try:
                dt = datetime.strptime(f"{mon} {day} {now.year}", "%b %d %Y").replace(
                    hour=20, minute=0, tzinfo=EASTERN
                )
                if dt.date() < now.date() - timedelta(days=2):
                    dt = dt.replace(year=now.year + 1)
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        events.append({
            "name": f"Laugh Boston: {title}",
            "date": iso,
            "url": ticket_url or url,
            "venue": "Laugh Boston",
            "price": None,
            "category": "comedy",
        })
    return events


def scrape_boch_center(url, ua):
    """Boch Center (Wang Theatre & Shubert Theatre) in Boston Theater District."""
    soup = fetch_soup(url, ua)
    events = []
    for s in soup.find_all("script", type="application/ld+json"):
        raw = s.get_text().strip()
        try:
            data = json.loads(raw, strict=False)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "Event":
                loc = item.get("location") or {}
                venue = loc.get("name") if isinstance(loc, dict) else "Boch Center"
                iso = item.get("startDate")
                if iso:
                    try:
                        iso = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
                    except ValueError:
                        pass
                events.append({
                    "name": item.get("name"),
                    "date": iso,
                    "url": item.get("url") or url,
                    "venue": venue or "Boch Center",
                    "price": None,
                    "category": "theater",
                })
    return events


def scrape_mfa_boston(url, ua):
    """Museum of Fine Arts (MFA Boston) upcoming programs, gallery tours, lectures, art classes."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for a in soup.find_all("a", href=lambda h: h and "/event/" in h):
        title = a.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        full_url = urljoin(url, a["href"])
        if full_url in seen:
            continue
        seen.add(full_url)
        row = a.find_parent("div", class_="row")
        raw_text = row.get_text(" ", strip=True) if row else ""
        m = re.search(r"(?:[A-Za-z]+,\s+)?([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", raw_text)
        tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", raw_text, re.IGNORECASE)
        iso = None
        if m:
            mon, day, yr = m.groups()
            hh = int(tm.group(1)) if tm else 11
            mm = int(tm.group(2)) if tm else 0
            ampm = tm.group(3).lower() if tm else "am"
            if ampm == "pm" and hh != 12:
                hh += 12
            if ampm == "am" and hh == 12:
                hh = 0
            try:
                dt = datetime.strptime(f"{mon} {day} {yr}", "%B %d %Y").replace(
                    hour=hh, minute=mm, tzinfo=EASTERN
                )
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        is_free = "free" in raw_text.lower()
        events.append({
            "name": f"MFA: {title}",
            "date": iso,
            "url": full_url,
            "venue": "Museum of Fine Arts (MFA)",
            "price": "Free with admission" if is_free else None,
            "category": "art",
        })
    return events


def scrape_boston_sports(_url, _ua):
    """Boston Red Sox, Celtics, Bruins home games at Fenway Park and TD Garden via ESPN APIs."""
    teams = [
        ("Boston Red Sox", "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/teams/bos/schedule", "Fenway Park"),
        ("Boston Celtics", "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/bos/schedule", "TD Garden"),
        ("Boston Bruins", "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams/bos/schedule", "TD Garden"),
    ]
    now = datetime.now(timezone.utc)
    max_date = now + timedelta(days=60)
    events = []
    for team, api_url, default_venue in teams:
        try:
            r = _SESSION.get(api_url, timeout=10)
            if r.status_code != 200:
                continue
            data = r.json()
            for ev in data.get("events", []):
                iso = ev.get("date")
                if not iso:
                    continue
                try:
                    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                if dt < now or dt > max_date:
                    continue
                comp = (ev.get("competitions") or [{}])[0]
                competitors = comp.get("competitors") or []
                is_home = False
                for c in competitors:
                    if team.lower() in (c.get("team", {}).get("displayName") or "").lower():
                        if c.get("homeAway") == "home":
                            is_home = True
                if not is_home:
                    continue
                v_name = comp.get("venue", {}).get("fullName") or default_venue
                link = (ev.get("links") or [{}])[0].get("href") or api_url
                events.append({
                    "name": ev.get("name"),
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": link,
                    "venue": v_name,
                    "price": None,
                    "category": "sports",
                })
        except Exception:
            continue
    return events


def scrape_city_winery(url, ua):
    """City Winery Boston — Vivenu-backed event API."""
    r = _SESSION.get("https://awsapi.citywinery.com/events", params={"location": "Boston", "top": 200},
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
    r = _SESSION.get(url, params={"format": "json-pretty"}, timeout=15,
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
    r = _SESSION.get(api, headers={
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
    ics = _SESSION.get(urljoin(url, "/events.ics"), headers={"User-Agent": ua}, timeout=15).text
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
    html = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15).text
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
    html = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15).text
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


def scrape_ticketmaster(_url, _ua):
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        raise RuntimeError("TICKETMASTER_API_KEY not set")
    resp = _SESSION.get(
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
    resp = _SESSION.get(
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
    resp = _SESSION.get(url + sep + "format=json", headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
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


def scrape_salsavida(url, ua):
    """Salsa Vida Massachusetts dance guide — schema.org microdata on article.event-card.
    The startDate datetime attr has the correct local time but wrong TZ offset (-07:00
    instead of Eastern), so we strip the offset and localize to EASTERN."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    for card in soup.select("article.event-card"):
        name_el = card.select_one('h2[itemprop="name"]')
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue
        start_el = card.find("time", itemprop="startDate")
        iso = None
        if start_el and start_el.get("datetime"):
            naive_m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", start_el["datetime"])
            if naive_m:
                try:
                    dt = datetime.fromisoformat(naive_m.group(1)).replace(tzinfo=EASTERN)
                    if dt.astimezone(timezone.utc) < now:
                        continue
                    iso = dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
        a = card.select_one('a[href*="salsavida.com/event/"]')
        href = a.get("href") if a else url
        loc_span = card.find("span", itemprop="location")
        venue = None
        if loc_span:
            loc_meta = loc_span.find("meta", attrs={"itemprop": "name"})
            venue = loc_meta.get("content") if loc_meta else loc_span.get_text(strip=True)
        price_meta = card.find("meta", attrs={"itemprop": "price"})
        price = None
        if price_meta:
            p = price_meta.get("content")
            try:
                p_f = float(p)
                price = "Free" if p_f == 0 else f"${p_f:.0f}"
            except (TypeError, ValueError):
                pass
        key = (name.lower(), iso or "")
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": name,
            "date": iso,
            "url": href,
            "venue": venue,
            "price": price,
            "category": "dance",
        })
    return events


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
    {"name": "Ticketmaster", "url": "https://www.ticketmaster.com/", "ua": UA_CHROME, "scraper": scrape_ticketmaster, "default_category": "music", "requires_env": "TICKETMASTER_API_KEY"},
    {"name": "SeatGeek", "url": "https://seatgeek.com/cities/boston", "ua": UA_CHROME, "scraper": scrape_seatgeek, "default_category": "music", "requires_env": "SEATGEEK_CLIENT_ID"},
    {"name": "Eventbrite Boston", "url": "https://www.eventbrite.com/d/ma--boston/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Aeronaut Brewing", "url": "https://d3izki9aezxlkr.cloudfront.net/public_events.json", "ua": UA_CHROME, "scraper": scrape_aeronaut, "default_category": "food"},
    {"name": "Versus Boston (via Eventbrite)", "url": "https://www.eventbrite.com/o/versus-105910382141", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "gaming"},
    {"name": "Make Friends After College (via Eventbrite)", "url": "https://www.eventbrite.com/o/make-friends-after-college-98390790901", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "The Boston Calendar", "url": "https://www.thebostoncalendar.com/events", "ua": UA_CHROME, "scraper": scrape_boston_calendar, "default_category": None},
    {"name": "City Winery Boston", "url": "https://citywinery.com/pages/locations/boston", "ua": UA_CHROME, "scraper": scrape_city_winery, "default_category": "music"},
    {"name": "Bowery Presents Boston", "url": "https://www.bowerypresents.com/boston", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "music"},
    {"name": "Royale Boston", "url": "https://www.royaleboston.com/events/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "clubbing"},
    {"name": "MIT Events", "url": "https://calendar.mit.edu/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "community"},
    {"name": "Boston Symphony Orchestra", "url": "https://www.bso.org/events", "ua": UA_CHROME, "scraper": scrape_bso, "default_category": "music"},
    {"name": "Venture Café Cambridge", "url": "https://venturecafecambridge.org/events/", "ua": UA_CHROME, "scraper": scrape_venture_cafe, "default_category": "community"},
    {"name": "The Anchor Boston", "url": "https://calendar.google.com/calendar/ical/theanchorbostonma%40gmail.com/public/basic.ics", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "community"},
    {"name": "ManRay Cambridge", "url": "https://manrayclub.com/event-calendar/", "ua": UA_CHROME, "scraper": scrape_manray, "default_category": "clubbing"},
    {"name": "Esplanade Association", "url": "https://esplanade.org/events/", "ua": UA_CHROME, "scraper": scrape_esplanade, "default_category": "outdoors"},
    {"name": "Eventbrite Cambridge", "url": "https://www.eventbrite.com/d/ma--cambridge/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Eventbrite Somerville", "url": "https://www.eventbrite.com/d/ma--somerville/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Cambridge Crossing (via Eventbrite)", "url": "https://www.eventbrite.com/o/cambridge-crossing-30339024896", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "Lamplighter Brewing (via Eventbrite)", "url": "https://www.eventbrite.com/o/lamplighter-brewing-co-12408758507", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "food"},
    {"name": "Do617", "url": "https://do617.com/events", "ua": UA_CHROME, "scraper": scrape_do617, "default_category": None},
    {"name": "Middle East Cambridge", "url": "https://mideastoffers.com", "ua": UA_CHROME, "scraper": scrape_middle_east, "default_category": "music"},
    {"name": "Wilbur Theatre", "url": "https://thewilbur.com/", "ua": UA_CHROME, "scraper": scrape_wilbur, "default_category": "comedy"},
    {"name": "Brookline Booksmith", "url": "https://www.brooklinebooksmith.com/events", "ua": UA_SAFARI, "scraper": scrape_event_list, "default_category": "books"},
    {"name": "Gardner Museum", "url": "https://www.gardnermuseum.org/calendar", "ua": UA_CHROME, "scraper": scrape_gardner, "default_category": "community"},
    {"name": "ICA Boston", "url": "https://www.icaboston.org/events", "ua": UA_CHROME, "scraper": scrape_ica, "default_category": "community"},
    {"name": "Brattle Theatre", "url": "https://www.brattlefilm.org/", "ua": UA_CHROME, "scraper": scrape_brattle, "default_category": "film"},
    {"name": "Meetup Boston", "url": "https://www.meetup.com/find/?location=us--ma--boston&source=EVENTS&eventType=inPerson&distance=tenMiles", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Somerville Board Games Meetup", "url": "https://www.meetup.com/somerville-board-games-meetup-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Beantown Gamers", "url": "https://www.meetup.com/boardgames-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Cambridge Game Night", "url": "https://www.meetup.com/CambridgeGameNight/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Unplugged Gaming Boston", "url": "https://www.meetup.com/unplugged-gaming-of-boston-surrounding-areas/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Hey Siri: Make Friends After College", "url": "https://www.meetup.com/Hey-Siri-How-Do-I-Make-New-Friends-After-College/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston Outdoor Adventures", "url": "https://www.meetup.com/boston-outdoor-adventures/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "outdoors"},
    {"name": "Boston Hiking Meetup", "url": "https://www.meetup.com/boston-hiking/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "outdoors"},
    {"name": "AMC Boston 20s & 30s", "url": "https://www.meetup.com/amc-boston-young-members/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "outdoors"},
    {"name": "Boston Photography Lovers", "url": "https://www.meetup.com/bostonphotolovers/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "art"},
    {"name": "Language Lovers Boston", "url": "https://www.meetup.com/language-lovers-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston New Technology", "url": "https://www.meetup.com/boston_new_technology/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston Generative AI Meetup", "url": "https://www.meetup.com/boston-generative-ai-meetup/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Amazing Social In Boston", "url": "https://www.meetup.com/amazing-social-in-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston Electronic Dance Music", "url": "https://www.meetup.com/bostonedm/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "clubbing"},
    {"name": "Second Sun Rising", "url": "https://secondsunrising.com/", "ua": UA_CHROME, "scraper": scrape_second_sun_rising, "default_category": "dance"},
    {"name": "BIDA Contra Dance", "url": "https://www.bidadance.org/", "ua": UA_CHROME, "scraper": scrape_bida, "default_category": "dance"},
    {"name": "24 Hour Music", "url": "https://tickets.24hourmusic.com/", "ua": UA_CHROME, "scraper": scrape_24hour_music, "default_category": "music"},
    {"name": "Boston Public Library", "url": "https://bpl.bibliocommons.com/events/search/index", "ua": UA_CHROME, "scraper": scrape_bpl, "default_category": "community"},
    {"name": "Crystal Ballroom", "url": "https://www.crystalballroomboston.com/events/", "ua": UA_CHROME, "scraper": scrape_crystal_ballroom, "default_category": "music"},
    {"name": "Coolidge Corner Theatre", "url": "https://coolidge.org/", "ua": UA_CHROME, "scraper": scrape_coolidge, "default_category": "film"},
    {"name": "Trident Booksellers & Cafe", "url": "https://tridentbookscafe.com/events", "ua": UA_CURL, "scraper": scrape_event_list, "default_category": "books"},
    {"name": "Harvard Book Store", "url": "https://www.harvard.com/events", "ua": UA_CURL, "scraper": scrape_event_list, "default_category": "books"},
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
    {"name": "Salsa Vida Boston", "url": "https://www.salsavida.com/guides/massachusetts/", "ua": UA_CHROME, "scraper": scrape_salsavida, "default_category": "dance"},
    {"name": "Laugh Boston", "url": "https://laughboston.com", "ua": UA_CHROME, "scraper": scrape_laugh_boston, "default_category": "comedy"},
    {"name": "Boch Center (Wang & Shubert)", "url": "https://www.bochcenter.org/events", "ua": UA_CHROME, "scraper": scrape_boch_center, "default_category": "theater"},
    {"name": "Museum of Fine Arts (MFA)", "url": "https://www.mfa.org/programs", "ua": UA_SAFARI, "scraper": scrape_mfa_boston, "default_category": "art"},
    {"name": "Boston Sports (Fenway & TD Garden)", "url": "https://site.api.espn.com", "ua": UA_CHROME, "scraper": scrape_boston_sports, "default_category": "sports"},
]

# Drop venues that require env vars we don't have set — keeps the fail banner clean.
VENUES = [v for v in _ALL_VENUES if not v.get("requires_env") or os.environ.get(v["requires_env"])]


# Static "useful links" — venues with no machine-readable calendar, but worth linking.
# Rendered in the "Useful links & ongoing" section.
STATIC_LINKS = [
    ("dance", "Boston Lindy Hop — swing dances list", "https://bostonlindyhop.com/events/swing-dancing-in-boston/"),
    ("dance", "Loretta's Last Call (line dancing, swing)", "https://lorettaslastcall.com/events/"),
    ("dance", "Boston Swing Central", "https://www.bostonswingcentral.org/"),
    ("dance", "Tango Society of Boston", "https://bostontango.org/"),
    ("theater", "American Repertory Theater", "https://americanrepertorytheater.org/shows-events/"),
    ("theater", "Huntington Theatre", "https://www.huntingtontheatre.org/season/"),
    ("art",     "Harvard Art Museums calendar", "https://harvardartmuseums.org/calendar"),
    ("comedy",  "Improv Asylum (North End)", "https://www.improvasylum.com/shows"),
    ("theater", "SpeakEasy Stage Company", "https://www.speakeasystage.com/season"),
    ("theater", "Lyric Stage Company", "https://www.lyricstage.com/productions/"),
    ("theater", "Company One Theatre", "https://companyone.org/onstage/"),
    ("theater", "Commonwealth Shakespeare", "https://commshakes.org/season/"),
    ("music",   "Trillium Brewing (events)", "https://trilliumbrewing.com/pages/event-calendar"),
    ("food",    "Sam Adams Boston Brewery (events)", "https://www.samadamsbrewery.com/events"),
    ("music",   "Long Live Beerworks / Roxbury", "https://www.longlivebeerworks.com"),
    ("food",    "Castle Island Brewing (events)", "https://www.castleislandbeer.com/public-events"),
    ("music",   "Boston Lyric Opera", "https://www.blo.org/performances/"),
    ("music",   "Handel and Haydn Society", "https://handelandhaydn.org/concerts/"),
    ("music",   "Celebrity Series of Boston", "https://www.celebrityseries.org/calendar/"),
    ("music",   "Berklee Performance Center", "https://www.berklee.edu/BPC"),
    ("clubbing","Middlesex Lounge (Cambridge)", "https://www.msexcambridge.com/calendar"),
    ("gaming",  "Balance Patch", "https://www.balancepatch.com/events"),
    ("gaming",  "MIT Strategic Games Society (Walker Memorial)", "https://calendar.mit.edu/group/mit_strategic_games_society"),
    ("music",   "Regattabar (jazz)", "https://www.regattabarjazz.com/"),
    ("music",   "Lilypad (Inman Square)", "https://www.lilypadinman.com/calendar"),
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
    ("The Beehive", "https://www.beehiveboston.com/calendar", "music", [
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/calendar", 0, 19, 30),
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/calendar", 1, 19, 30),
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/calendar", 2, 19, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/calendar", 3, 18, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/calendar", 4, 18, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/calendar", 5, 18, 30),
        ("Live Music Weekend Brunch", "https://www.beehiveboston.com/calendar", 5, 10, 0),
        ("Live Music Weekend Brunch", "https://www.beehiveboston.com/calendar", 6, 10, 0),
        ("Blues on Sunday with Bruce Bears & Friends", "https://www.beehiveboston.com/calendar", 6, 19, 30),
    ]),
    ("The Cantab Lounge", "https://thecantablounge.com/", "music", [
        ("Open Mic & Acoustic Showcase", "https://thecantablounge.com/", 0, 19, 30),
        ("Jazz Jam @ Cantab", "https://thecantablounge.com/", 0, 22, 0),
        ("Bluegrass Night @ Cantab", "https://thecantablounge.com/", 1, 20, 0),
        ("R&B & Soul Jam", "https://thecantablounge.com/", 2, 20, 30),
        ("Funk & Soul Party", "https://thecantablounge.com/", 4, 21, 30),
        ("Live Band Night @ Cantab", "https://thecantablounge.com/", 5, 21, 30),
        ("Sunday R&B Jam", "https://thecantablounge.com/", 6, 20, 30),
    ]),
    ("Loretta's Last Call", "https://www.lorettaslastcall.com/events/", "dance", [
        ("Partner Swing Dancing", "https://www.lorettaslastcall.com/event/partner-swing-dancing-on-mondays/", 0, 20, 0),
        ("Live Band Line Dancing", "https://www.lorettaslastcall.com/event/live-band-line-dancing/", 2, 20, 0),
        ("Sunday Line Dancing", "https://www.lorettaslastcall.com/event/sunday-line-dancing/", 6, 18, 0),
    ]),
    ("Central Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/central-square/", "food", [
        ("Central Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/central-square/", 0, 12, 0),
    ]),
    ("Copley Square Farmers Market", "https://www.bu.edu/treebos/copley-square-farmers-market/", "food", [
        ("Copley Square Farmers Market", "https://www.bu.edu/treebos/copley-square-farmers-market/", 1, 11, 0),
        ("Copley Square Farmers Market", "https://www.bu.edu/treebos/copley-square-farmers-market/", 4, 11, 0),
    ]),
    ("Davis Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/davis-square/", "food", [
        ("Davis Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/davis-square/", 2, 12, 0),
    ]),
    ("Kendall Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/kendall-square/", "food", [
        ("Kendall Square Farmers Market", "https://www.cambridgefarmersmarkets.org/markets/kendall-square/", 3, 12, 0),
    ]),
    ("Union Square Farmers Market", "https://www.unionsquaremain.org/farmers-market", "food", [
        ("Union Square Farmers Market", "https://www.unionsquaremain.org/farmers-market", 5, 9, 0),
    ]),
    ("SoWa Open Market", "https://sowaboston.com/open-market/", "community", [
        ("SoWa Open Market", "https://sowaboston.com/open-market/", 6, 10, 0),
    ]),
    ("Boston Fun Run", "https://www.meetup.com/boston-fun-run/", "sports", [
        ("Wednesday Run + Bar", "https://www.meetup.com/boston-fun-run/", 2, 19, 0),
    ]),
    ("MIT Strategic Games Society", "https://calendar.mit.edu/group/mit_strategic_games_society", "gaming", [
        ("Board Games @ Walker Memorial", "https://calendar.mit.edu/group/mit_strategic_games_society", 4, 18, 5),
        ("Board Games @ Walker Memorial", "https://calendar.mit.edu/group/mit_strategic_games_society", 6, 15, 5),
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
    ("Wally's Café", "https://www.wallyscafe.com/events", "music", [
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 0, 21, 0),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 1, 21, 0),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 2, 21, 0),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 3, 21, 0),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 4, 21, 0),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 5, 21, 30),
        ("Live Jazz @ Wally's", "https://www.wallyscafe.com/events", 6, 21, 0),
    ]),
    ("Greenway Artisan Market", "https://www.rosekennedygreenway.org/events/", "art", [
        ("Greenway Artisan Market", "https://www.rosekennedygreenway.org/events/", 5, 11, 0),
    ]),
    ("Memorial Drive Sundays", "https://www.cambridgema.gov/recreation/memorialdrive", "outdoors", [
        ("Memorial Drive Car-Free Sundays", "https://www.cambridgema.gov/recreation/memorialdrive", 6, 11, 0),
    ]),
    ("Swing in the Square", "https://www.rosi-boston.org/swing-in-the-square", "dance", [
        ("Swing in the Square — Free Outdoor Dancing", "https://www.rosi-boston.org/swing-in-the-square", 2, 18, 0),
    ]),
    ("Everybody Dance Now", "https://www.everybodydancenow.org", "dance", [
        ("Outdoor Drop-in Dance Classes @ The Grove", "https://www.everybodydancenow.org", 2, 18, 0),
    ]),
    ("Boston Outdoor Bachata & Salsa", "https://www.facebook.com/p/Boston-Outdoor-Bachata-And-Salsa-61551665503735/", "dance", [
        ("Outdoor Bachata & Salsa Social", "https://www.facebook.com/p/Boston-Outdoor-Bachata-And-Salsa-61551665503735/", 3, 18, 0, "Free"),
    ]),
]


def _expand_manual_recurring(weeks=8):
    """Expand MANUAL_RECURRING_EVENTS into synthetic venue results with concrete dates."""
    today = datetime.now(EASTERN).date()
    results = []
    for venue, venue_url, default_cat, items in MANUAL_RECURRING_EVENTS:
        events = []
        for item in items:
            name, url, weekday, hour, minute = item[:5]
            price = item[5] if len(item) > 5 else None
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
                    "price": price,
                    "category": default_cat,
                })
        results.append({"venue": venue, "url": venue_url, "events": events, "error": None})
    return results


CATEGORY_KEYWORDS = [
    ("dance",     ["salsa", "bachata", "kizomba", "merengue", "tango", "swing dance", "swing dancing",
                   "lindy hop", "balboa", "blues dance", "contra dance", "zouk", "cha-cha", "cha cha",
                   "west coast swing", "ballroom dance", "ballroom dancing", "waltz", "milonga",
                   "dance social", "dance party", "dance night", "dance class", "dance lesson",
                   "dance workshop", "social dance", "havana club", "bachata room",
                   "line danc", "drag show", "drag night", "drag queen", "drag performance",
                   "go-go dancer", "pole danc", "ballet", "burlesque", "aerial danc", "aerial flow",
                   "capoeira", "folk danc", "dancehall", "kizkonpa", "floorwork"]),
    ("comedy",    ["comedy", "stand-up", "stand up", "improv", "open mic", "open-mic",
                   "roast", "sketch", "satirical", "variety show"]),
    ("theater",   ["theatre", "theater", "musical", "shakespeare", "broadway musical", "broadway show", "repertory", "play by", "play:",
                   "one woman show", "one man show", "solo show", "puppet", "burlesque show"]),
    ("books",     ["book club", "book launch", "author", "reading", "storytime", "poet", "signing", "booksmith",
                   "literary", "book talk", "book fair", "writing workshop", "creative writing"]),
    ("gaming",    ["arcade", "mahjong", "chess", "trivia", "board game", "video game", "ttrpg", "d&d", "dungeons",
                   "tabletop", "escape room", "bingo", "pinball", "axe throw", "darts bar",
                   "one-shot rpg", "rpg night", "cornhole", "ping pong"]),
    ("clubbing",  ["dj ", " dj", "edm", "house music", "techno", "rave", "dubstep", "club night",
                   "nightclub", "guestlist", "guest list", "nightlife", "drum and bass", "drum & bass",
                   "industrial night", "goth night", "darkwave", "new wave night",
                   "speakeasy", "piano bar", "dueling piano"]),
    ("music",     ["tour", "concert", " band ", "live music", "music series", "music hall", "orchestra",
                   "symphony", "karaoke", "jazz", "hip hop", "rap", "bluegrass", "country music",
                   "country night", "folk music", "acoustic", "open mic", "irish session", "jam session",
                   "music session", "singer-songwriter", "singer songwriter", "soul music", "r&b",
                   "funk", "reggae", "punk", "metal", "indie rock", "album release", "ep release",
                   "record release", "live band", "live show", "live performance",
                   "jazz trio", "jazz quartet", " trio ", " quartet ", " quintet ",
                   "ukulele", "drumming", "cabaret", "blues feat", "live blues",
                   "choral", "choir", "ensemble", "chamber music"]),
    ("film",      ["screening", "film ", "cinema", "movie night", "brattle", "coolidge", "documentary"]),
    ("sports",    ["bruins", "celtics", "red sox", "revolution", "marathon", "vs.", "match", "game ",
                   " 5k", "fun run", "road race", "10k", "half marathon", "cycling event",
                   "bike race", "rowing", "regatta", "pickleball", "tennis", "volleyball",
                   "dodgeball", "archery", "parkour", "crossfit", "rock climbing", "kickboxing",
                   "dragon boat", "wrestling", "flag football", "golf", "axe throwing",
                   "indoor cycling", "spin class", "boot camp", "fitness class",
                   "strength training", "pilates", "hyrox"]),
    ("food",      ["tasting", "brewery", "brewing", "beer", "wine", "dinner", "brunch", "pop-up",
                   "oyster", "cocktail", "martini", "happy hour", "taproom", "bar night", "fondue",
                   "taqueria", "tavern", "sushi", "maki", "whiskey", "bourbon", "food truck", "menu",
                   "food tour", "culinary", "cooking class", "baking class", "noodle class",
                   "pasta class", "wine tasting", "beer tasting", "restaurant",
                   "omakase", "ramen", "dumpling", "high tea", "afternoon tea", "tea room",
                   "chocolate tour", "coffee", "latte", "croissant", "knife skills",
                   "cheese tasting", "sake", "mezcal", "gin tasting"]),
    ("family",    ["kids", "children", "family", "toddler", "princess", "easter", "storytime",
                   "lego", "sensory-friendly", "sensory friendly"]),
    ("art",       ["exhibition", "gallery", "museum", "sculpture", "painting", "curator",
                   "art show", "art walk", "art class", "pottery", "ceramics", "printmaking",
                   "watercolor", "glass fusing", "mosaic", "screen print", "flower arrang",
                   "candle mak", "weaving", "embroid", "knitting", "collage",
                   "life drawing", "figure drawing", "illustration", "sketchbook",
                   "sewing", "crochet", "stained glass", "jewelry", "bonsai", "kokedama",
                   "quilling", "resin ", "tufting", "leatherwork", "woodwork",
                   "pressed flower", "moss art", "stamp carving", "cyanotype",
                   "paper marbling", "junk journal", "macrame", "succulent plant",
                   "art studio", "open studio", "art market", "mural"]),
    ("outdoors",  ["hike", "hiking", "kayak", "canoe", "paddleboard", "camping", "trail",
                   "nature walk", "birding", "birdwatching", "yoga", "outdoor yoga", "sunrise yoga",
                   "sunset yoga", "outdoor fitness", "outdoor workout", "park run",
                   "memorial drive", "swan boat", "fitness on the", "fitness series",
                   "esplanade", "arboretum", "botanic garden", "conservation area",
                   "beach", "nature explor"]),
    ("community", ["parade", "patriots day", "block party", "festival", " fair ", "fair!",
                   "gathering", "protest", "rally", "earth day", "earth week", "clean up",
                   "volunteer", "community", "civic", "town hall", "open house", "meetup",
                   "networking", "panel discussion", "panel ", "lecture", "seminar",
                   "thrift", "consignment", "swap meet", "tag sale", "farmers market",
                   "artisan market", "craft fair", "flea market", "vintage market",
                   "lgbtq", "queer ", "pride ", " trans ", "bisexual",
                   "meditation", "meditat", "speed dating", "singles", "porchfest",
                   "open studios", "small business", "startup", "tarot"]),
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
        r = _SESSION.get(
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
        resp = _SESSION.get(
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


_last_known_good = {}
_cache = {"data": None, "ts": 0}
_cache_lock = threading.Lock()
_refresh_lock = threading.Lock()
_is_refreshing = False


def _init_warm_cache():
    """Warm in-memory cache and last-known-good map from events.json on disk if available."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
    if os.path.exists(json_path) and not _cache["data"]:
        try:
            with open(json_path) as f:
                payload = json.load(f)
            venues = payload.get("venues") if isinstance(payload, dict) else payload
            if venues and isinstance(venues, list):
                _cache["data"] = venues
                _cache["ts"] = time.time() - (CACHE_SECONDS / 2)  # half-fresh so it updates gracefully
                for v in venues:
                    if v.get("venue") and v.get("events"):
                        _last_known_good[v["venue"]] = v["events"]
        except Exception:
            pass


_init_warm_cache()


def _scrape_one(v):
    name = v["name"]
    try:
        events = dedupe(v["scraper"](v["url"], v["ua"]))
        for e in events:
            if not e.get("venue"):
                e["venue"] = name
            if not e.get("category"):
                e["category"] = infer_category(e.get("name"), e.get("venue"), v.get("default_category"))
        events.sort(key=_sort_key)
        
        # If scraper succeeded and returned events, update last known good
        if events:
            _last_known_good[name] = events
        elif name in _last_known_good and not events:
            # Scraper returned 0 events but previously had events: fall back to preserve data
            events = _last_known_good[name]
            
        return {"venue": name, "url": v["url"], "events": events, "error": None}
    except Exception as e:
        # Fall back to previous events if available on network error/timeout
        prev = _last_known_good.get(name, [])
        return {"venue": name, "url": v["url"], "events": prev, "error": str(e), "fallback": bool(prev)}


def _do_scrape_all():
    with ThreadPoolExecutor(max_workers=min(16, len(VENUES))) as ex:
        results = list(ex.map(_scrape_one, VENUES))
    order = {v["name"]: i for i, v in enumerate(VENUES)}
    results.sort(key=lambda r: order.get(r["venue"], 999))
    results.extend(_expand_manual_recurring())
    with _cache_lock:
        _cache["data"] = results
        _cache["ts"] = time.time()
    return results


def _background_refresh():
    global _is_refreshing
    with _refresh_lock:
        if _is_refreshing:
            return
        _is_refreshing = True
    try:
        _do_scrape_all()
    finally:
        with _refresh_lock:
            _is_refreshing = False


def get_all_events(force=False):
    """Return all scraped events.
    
    Uses Stale-While-Revalidate: If cached data exists, returns immediately (instant load)
    and asynchronously launches a background scraper update if the cache has expired.
    """
    now = time.time()
    with _cache_lock:
        cached = _cache["data"]
        is_stale = (now - _cache["ts"]) >= CACHE_SECONDS

    if force:
        return _do_scrape_all()

    if cached is not None:
        if is_stale and not _is_refreshing:
            threading.Thread(target=_background_refresh, daemon=True).start()
        return cached

    # Cold start with no events.json on disk: scrape synchronously
    return _do_scrape_all()

