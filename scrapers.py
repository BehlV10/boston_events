"""Boston Events — venue scrapers and data definitions."""

import html
import json
import os
import re
import ssl
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from dateutil.rrule import rrulestr
from dateutil import parser


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
            if not p:
                p = re.search(r'"minimum_ticket_price":\{[^}]*?"display":"([\d.]+)\s*USD"', chunk)
            if p:
                val = float(p.group(1))
                price = "Free" if val == 0 else f"${val:g}"
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
            geo = loc.get("geo") or {} if isinstance(loc, dict) else {}
            lat = geo.get("latitude")
            lng = geo.get("longitude")
            events.append({
                "name": ev.get("name"),
                "date": iso,
                "url": ev.get("url"),
                "venue": venue,
                "price": None,
                "description": (ev.get("description") or "")[:200],
                "lat": lat,
                "lng": lng,
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


def _parse_bc_admission(text):
    if not text:
        return None
    t = re.sub(r"^\s*admission\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    if not t:
        return None
    if re.search(r"\bfree\b", t, re.IGNORECASE) and "$" not in t:
        return "Free"
    m = re.search(r"\$\s*(\d+(?:\.\d{2})?)(?:\s*[-–]\s*\$?(\d+(?:\.\d{2})?))?", t)
    if m:
        p1 = m.group(1)
        p2 = m.group(2)
        if p2:
            return "Free" if p1 in ("0", "0.00") and p2 in ("0", "0.00") else f"${p1} - ${p2}"
        return "Free" if p1 in ("0", "0.00") else f"${p1}"
    if re.search(r"\bfree\b", t, re.IGNORECASE):
        return "Free"
    return None


def _bc_detail_info(bc_url, ua):
    """Fetch detail page for The Boston Calendar event and extract (external_url, admission_price)."""
    soup = None
    for attempt in range(2):
        try:
            soup = fetch_soup(bc_url, ua)
            break
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return None, None
    if soup is None:
        return None, None
    ext_url = None
    price = None
    for p in soup.find_all("p"):
        b = p.find("b") or p.find("strong")
        if not b:
            continue
        label = b.get_text(" ", strip=True).lower()
        if _BC_EXTERNAL_RE.search(label):
            a = p.find("a", href=True)
            if a and a.get("href"):
                ext_url = a["href"]
        elif "admission" in label:
            price = _parse_bc_admission(p.get_text(" ", strip=True))
    return ext_url, price


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
            time_el = li.select_one(".time")
            loc_el = li.select_one(".location")
            raw_time = time_el.get_text(" ", strip=True) if time_el else ""
            iso = _parse_boston_calendar_time(raw_time)
            seen_key = (href, iso[:10] if iso else str(d))
            if seen_key in seen_urls:
                continue
            seen_urls.add(seen_key)
            price = None
            if re.search(r"\b(?:free|no cover|complimentary)\b", name, re.IGNORECASE):
                price = "Free"
            entry = {
                "name": name,
                "date": iso,
                "url": href,
                "venue": loc_el.get_text(strip=True) if loc_el else None,
                "price": price,
            }
            until = _BC_GOES_UNTIL_RE.search(raw_time)
            if iso is None and until:
                end_month, end_day = int(until.group(1)), int(until.group(2))
                end_year = d.year + (1 if end_month < d.month else 0)
                entry["ends"] = f"{end_year:04d}-{end_month:02d}-{end_day:02d}"
            events.append(entry)
    if events:
        top = events[:60]
        with ThreadPoolExecutor(max_workers=12) as ex:
            details = list(ex.map(lambda e: _bc_detail_info(e["url"], ua), top))
        for e, (ext, p) in zip(top, details):
            if ext:
                e["url"] = ext
            if p and not e.get("price"):
                e["price"] = p
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
        href = a.get("href", "")

        # Extract time from .event-list__details--item or article text
        hour, minute = 19, 0
        time_text = None
        date_text = None
        for item in art.select(".event-list__details--item"):
            label = item.select_one(".event-list__details--label")
            if label and "time" in label.get_text().lower():
                time_text = item.get_text(" ", strip=True).replace(label.get_text(strip=True), "").strip()
            elif label and "date" in label.get_text().lower():
                date_text = item.get_text(" ", strip=True).replace(label.get_text(strip=True), "").strip()
            elif "time:" in item.get_text().lower():
                time_text = re.sub(r"(?i)^.*?time:\s*", "", item.get_text(" ", strip=True)).strip()
            elif "date:" in item.get_text().lower():
                date_text = re.sub(r"(?i)^.*?date:\s*", "", item.get_text(" ", strip=True)).strip()

        if not time_text:
            m_tm = re.search(r"(?:Time:\s*)(\d{1,2}(?::\d{2})?\s*(?:am|pm))", art.get_text(" ", strip=True), re.IGNORECASE)
            if m_tm:
                time_text = m_tm.group(1)

        if time_text:
            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_text, re.IGNORECASE)
            if m_time:
                h = int(m_time.group(1))
                mn = int(m_time.group(2) or 0)
                ampm = m_time.group(3).lower()
                if ampm == "pm" and h != 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour, minute = h, mn

        m = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", href)
        iso = None
        if m:
            y, mo, d = map(int, m.groups())
            try:
                dt = datetime(y, mo, d, hour, minute, tzinfo=EASTERN)
                iso = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        elif date_text:
            dm = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_text)
            if dm:
                mo, d, y = map(int, dm.groups())
                try:
                    dt = datetime(y, mo, d, hour, minute, tzinfo=EASTERN)
                    iso = dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass

        if not iso:
            mon = art.select_one(".event-list__date--month")
            day = art.select_one(".event-list__date--day")
            if mon and day:
                try:
                    year = datetime.now(EASTERN).year
                    dt = datetime.strptime(f"{mon.get_text(strip=True)} {day.get_text(strip=True)} {year} {hour:02d}:{minute:02d}", "%b %d %Y %H:%M").replace(tzinfo=EASTERN)
                    if dt < datetime.now(EASTERN):
                        dt = dt.replace(year=year + 1)
                    iso = dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass

        # Extract offsite venue location if present
        venue_name = None
        loc_item = art.select_one(".event-details__location--location")
        if not loc_item:
            for item in art.select(".event-list__details--item"):
                label = item.select_one(".event-list__details--label")
                if label and "place" in label.get_text().lower():
                    loc_item = item
                    break

        if loc_item:
            line1 = loc_item.select_one(".address-line1")
            if line1:
                text = line1.get_text(strip=True)
                if text and not re.match(r"^\d+\s+[A-Za-z]", text):
                    venue_name = text
            if not venue_name:
                addr = loc_item.select_one("address")
                if addr:
                    lines = [l.strip() for l in addr.get_text("\n").split("\n") if l.strip()]
                    if lines and not re.match(r"^\d+\s+[A-Za-z]", lines[0]):
                        venue_name = lines[0]
            if not venue_name:
                lbl = loc_item.select_one(".event-list__details--label")
                lbl_txt = lbl.get_text(strip=True) if lbl else ""
                txt = loc_item.get_text(" ", strip=True).replace(lbl_txt, "").strip()
                if txt and not re.match(r"^\d+\s+[A-Za-z]", txt) and txt.lower() not in ("place:", ""):
                    venue_name = txt

        if venue_name:
            v_low = venue_name.lower()
            u_low = url.lower()
            if "brookline" in u_low and "brookline booksmith" in v_low:
                venue_name = None
            elif "harvard" in u_low and "harvard book" in v_low:
                venue_name = None
            elif "trident" in u_low and "trident" in v_low:
                venue_name = None

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
            "venue": venue_name,
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
    events = []
    try:
        soup = fetch_soup(url, ua)
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
                "category": "art",
            })
    except Exception:
        pass

    if not events:
        today = datetime.now(EASTERN).date()
        for offset_mo in (0, 1):
            y = today.year + (today.month + offset_mo - 1) // 12
            m = (today.month + offset_mo - 1) % 12 + 1
            thurs_count = 0
            for d in range(1, 32):
                try:
                    cur = datetime(y, m, d, 17, 30, tzinfo=EASTERN)
                except ValueError:
                    break
                if cur.weekday() == 3:
                    thurs_count += 1
                    if thurs_count == 3 and cur.date() >= today:
                        events.append({
                            "name": "Gardner Museum Third Thursdays: Music, Drinks & Galleries",
                            "date": cur.astimezone(timezone.utc).isoformat(),
                            "url": "https://www.gardnermuseum.org/calendar/third-thursdays",
                            "venue": "Isabella Stewart Gardner Museum",
                            "price": "$20",
                            "category": "art",
                        })
                        break
        for i in range(1, 14):
            d = today + timedelta(days=i)
            if d.weekday() in (4, 5, 6):
                dt = datetime(d.year, d.month, d.day, 11, 0, tzinfo=EASTERN)
                events.append({
                    "name": "Isabella Stewart Gardner Museum: Courtyard & Historic Palace",
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": "https://www.gardnermuseum.org/visit",
                    "venue": "Isabella Stewart Gardner Museum",
                    "price": "$20",
                    "category": "art",
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
    """Venture Café Cambridge — community platform & Thursday Gatherings."""
    fetch_url = "https://community.venturecafecambridge.org/" if "venturecafecambridge.org" in url else url
    soup = fetch_soup(fetch_url, ua)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)

    # 1. Parse community site event cards
    for a in soup.find_all("a", href=re.compile(r"/events/[a-f0-9-]+")):
        title_el = a.select_one("div.font-headers")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue
        text = a.get_text()
        m = re.search(r"([A-Za-z]{3}\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}\s+[AP]M)", text)
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), "%b %d, %Y, %I:%M %p").replace(tzinfo=EASTERN)
            if dt.astimezone(timezone.utc) < now:
                continue
            iso = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
        href = a["href"]
        if href.startswith("/"):
            href = "https://community.venturecafecambridge.org" + href
        key = (title.lower(), iso)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": title,
            "date": iso,
            "url": href,
            "venue": "Venture Café Cambridge",
            "price": "Free",
            "category": "community",
        })

    if events:
        return events

    # 2. Fallback to WordPress/Tribe JSON-LD
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
                "price": "Free",
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
        if not event_url.startswith("http") or "google.com/calendar" in event_url or event_url.endswith(".ics"):
            if "theanchorboston" in url:
                event_url = "https://www.theanchorboston.com/calendar"
            else:
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
        desc_el = detail.find(class_="simcal-event-description")
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
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        cover_match = re.search(r"Cover\s*(\$[\d\.]+)", desc, re.IGNORECASE)
        price = cover_match.group(1) if cover_match else None
        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": link_el["href"] if link_el else url,
            "venue": "ManRay",
            "price": price,
            "category": "clubbing",
            "description": desc[:200],
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
    post_items = soup.select('.post-item')
    if post_items:
        for item in post_items:
            link = item.select_one('a[href*="/event/"]')
            if not link:
                continue
            href = link.get("href", "").split("?")[0]
            if not href or href in seen:
                continue
            seen.add(href)

            h2 = item.select_one("h2")
            img = item.select_one("img")
            name = (h2.get_text(strip=True) if h2 else "") or (img.get("alt") if img else "")
            if not name or name.lower() in ("buy tickets", "tickets", "info", "more"):
                slug = href.rstrip("/").split("/")[-1]
                name = slug.replace("-", " ").title()

            date_iso = None
            date_el = item.select_one(".date")
            if date_el:
                raw_date = date_el.get_text(strip=True)
                if raw_date:
                    try:
                        ym = re.search(r'\b(202\d)\b', raw_date)
                        year = ym.group(1) if ym else str(datetime.now().year)
                        start_part = raw_date.split(" - ")[0].strip()
                        if year not in start_part:
                            start_part = f"{start_part}, {year}"
                        dt = parser.parse(start_part)
                        date_iso = dt.replace(hour=19, minute=30).astimezone(EASTERN).isoformat()
                    except Exception:
                        pass

            events.append({
                "name": name[:160],
                "date": date_iso,
                "url": href,
                "venue": "Wilbur Theatre",
                "price": None,
                "category": "comedy",
            })
    else:
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
                "category": "comedy",
            })
    return events


_ST_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August","September","October","November","December"], start=1)}


def scrape_somerville_theatre(url, ua):
    """WP Theatre plugin: fetches both /events/ (live shows/concerts) and
    /calendar/ (repertory cinema screenings), deduplicating by title + showtime."""
    urls = [
        "https://www.somervilletheatre.com/events/",
        "https://www.somervilletheatre.com/calendar/",
    ]
    seen = set()
    events = []
    now = datetime.now(timezone.utc)
    for u in urls:
        try:
            soup = fetch_soup(u, ua)
        except Exception:
            continue
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
                dt_utc = dt.astimezone(timezone.utc)
            except ValueError:
                continue
            if dt_utc < now:
                continue
            dedup_key = (name.lower(), dt_utc.isoformat())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            link = block.select_one("a.wp_theatre_event_tickets_url") or block.select_one("a[href]")
            href = link.get("href") if link else u
            events.append({
                "name": name,
                "date": dt_utc.isoformat(),
                "url": href,
                "venue": "Somerville Theatre",
                "price": None,
                "category": "film",
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


def scrape_bowery_boston(url, ua):
    """Bowery Presents Boston (Roadrunner, The Sinclair, Royale, etc.) via public AEG events JSON feed."""
    feed_url = "https://aegwebprod.blob.core.windows.net/json/resources/8/events/7301mbln09/events.json"
    resp = _SESSION.get(feed_url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    now = datetime.now(timezone.utc)
    events = []
    seen = set()
    for e in data.get("events", []):
        venue = e.get("venue", {})
        state = (venue.get("state") or "").upper()
        city = (venue.get("city") or "").lower()
        if state not in ("MA", "MASS", "MASSACHUSETTS") and "boston" not in city and "cambridge" not in city and "somerville" not in city:
            continue
        iso = e.get("eventDateTimeISO")
        if not iso:
            continue
        try:
            dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=EASTERN)
            if dt.astimezone(timezone.utc) < now:
                continue
            iso_str = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
        title = (e.get("title", {}).get("headlinersText") or e.get("title", {}).get("eventTitleText") or "").strip()
        if not title:
            continue
        ticketing = e.get("ticketing", {})
        ticket_url = ticketing.get("ticketURL") or f"https://www.bowerypresents.com/events/detail/{e.get('eventId')}"
        vname = venue.get("title") or "Bowery Presents"
        key = (title.lower(), iso_str)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "name": title,
            "date": iso_str,
            "url": ticket_url,
            "venue": vname,
            "price": ticketing.get("priceRange"),
            "category": "music",
        })
    return events


def scrape_night_shift(url, ua):
    """Night Shift Brewing events in Everett Taproom."""
    soup = fetch_soup(url, ua)
    events = []
    now = datetime.now(EASTERN)
    weekdays = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3, 'friday': 4, 'saturday': 5, 'sunday': 6}

    cards = soup.select("article.card-new.type-event, article.event-article")
    for art in cards:
        title_a = art.select_one(".font-event-title a, .article-title a, h3 a, a.heading-link")
        if not title_a:
            continue
        name = re.sub(r"\s+", " ", title_a.get_text(" ", strip=True))
        href = title_a.get("href") or url
        date_el = art.select_one(".font-event-date-time, .font-event-date, .article-date")
        if not date_el:
            continue
        date_text = re.sub(r"\s+", " ", date_el.get_text(" ", strip=True))

        tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", date_text, re.IGNORECASE)
        hour, minute = 19, 0
        if tm:
            hour = int(tm.group(1))
            minute = int(tm.group(2)) if tm.group(2) else 0
            if tm.group(3).lower() == "pm" and hour != 12:
                hour += 12
            elif tm.group(3).lower() == "am" and hour == 12:
                hour = 0

        iso = None
        every_m = re.search(r"Every\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)", date_text, re.IGNORECASE)
        if every_m:
            target_wd = weekdays[every_m.group(1).lower()]
            days_ahead = (target_wd - now.weekday()) % 7
            event_date = now.date() + timedelta(days=days_ahead)
            dt = datetime(event_date.year, event_date.month, event_date.day, hour, minute, tzinfo=EASTERN)
            if dt < now:
                dt += timedelta(days=7)
            iso = dt.astimezone(timezone.utc).isoformat()
        else:
            slug = re.search(r"/(\d{4}-\d{2}-\d{2})/?$", href.rstrip("/") + "/")
            if slug:
                try:
                    d = datetime.strptime(slug.group(1), "%Y-%m-%d").date()
                    dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
                    if dt.astimezone(timezone.utc) >= now.astimezone(timezone.utc):
                        iso = dt.astimezone(timezone.utc).isoformat()
                except ValueError:
                    pass
            if not iso:
                m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(\d{4}))?", date_text)
                if m:
                    mname, day, yr = m.group(1).lower(), int(m.group(2)), int(m.group(3) or now.year)
                    month = _ST_MONTHS.get(mname)
                    if month:
                        try:
                            dt = datetime(yr, month, day, hour, minute, tzinfo=EASTERN)
                            if dt.astimezone(timezone.utc) >= now.astimezone(timezone.utc):
                                iso = dt.astimezone(timezone.utc).isoformat()
                        except ValueError:
                            pass

        if iso:
            events.append({
                "name": name,
                "date": iso,
                "url": href,
                "venue": "Night Shift Brewing",
                "price": None,
                "category": "food",
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
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        if resp.status_code == 200:
            html = resp.text
        else:
            raise ValueError(f"HTTP {resp.status_code}")
    except Exception:
        import subprocess
        try:
            html = subprocess.check_output(["curl", "-s", "-L", url], timeout=15).decode("utf-8", errors="ignore")
        except Exception:
            return []
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


def scrape_royale(_url, ua):
    """Royale Boston — Supabase REST API backend."""
    anon_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBnZ2RqbHd6cWNudmptbWFqanVqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE0MjgwMTQsImV4cCI6MjA4NzAwNDAxNH0.tlQoQ16pPO3JCDr4qZ7UgZGWSLSzbgkq0BkG2fa04oc"
    try:
        r_page = _SESSION.get("https://royaleboston.com/", headers={"User-Agent": ua}, timeout=8)
        js_src = re.search(r'src="(/assets/index-[^"]+\.js)"', r_page.text)
        if js_src:
            r_js = _SESSION.get(f"https://royaleboston.com{js_src.group(1)}", headers={"User-Agent": ua}, timeout=8)
            k_match = re.search(r'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9\._\-]+', r_js.text)
            if k_match:
                anon_key = k_match.group(0)
    except Exception:
        pass

    headers = {"apikey": anon_key, "Authorization": f"Bearer {anon_key}", "User-Agent": ua}
    resp = _SESSION.get("https://pggdjlwzqcnvjmmajjuj.supabase.co/rest/v1/events?select=*", headers=headers, timeout=12)
    resp.raise_for_status()
    data = resp.json()
    events = []
    for item in data:
        title = item.get("title")
        edate = item.get("event_date")
        etime = item.get("event_time") or "20:00:00"
        if not title or not edate:
            continue
        try:
            dt = datetime.fromisoformat(f"{edate}T{etime[:8]}").replace(tzinfo=EASTERN)
            iso = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            iso = None
        events.append({
            "name": title,
            "date": iso,
            "url": item.get("ticket_url") or "https://royaleboston.com/events/",
            "venue": "Royale",
            "price": None,
            "category": "clubbing",
        })
    return events


def scrape_tablelist(url, ua):
    """Tablelist Next.js ticketing embed for nightclubs (The Grand, Scorpion Bar, Mémoire)."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except Exception:
        return []
    props = data.get("props", {}).get("pageProps", {})
    venue_info = props.get("venue", {})
    default_venue = venue_info.get("name") or "Nightclub"
    raw_events = props.get("events", {}).get("data", [])
    events = []
    for item in raw_events:
        name = item.get("name")
        start = item.get("dateStart")
        if not name or not start:
            continue
        try:
            dt = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(timezone.utc)
            iso = dt.isoformat()
        except Exception:
            iso = None
        vname = item.get("venueName") or default_venue
        events.append({
            "name": name,
            "date": iso,
            "url": item.get("externalSellingLink") or url,
            "venue": vname,
            "price": None,
            "category": "clubbing",
        })
    return events


def scrape_ticketmaster_venue(url, ua):
    """Scrapes events from Ticketmaster venue page using __NEXT_DATA__ eventsJsonLD (e.g. Mémoire Boston)."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except Exception:
        return []
    props = data.get("props", {}).get("pageProps", {})
    events_ld = props.get("eventsJsonLD", [])
    flat_events = []
    if isinstance(events_ld, list):
        for sub in events_ld:
            if isinstance(sub, list):
                flat_events.extend(sub)
            elif isinstance(sub, dict):
                flat_events.append(sub)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    for item in flat_events:
        if not isinstance(item, dict):
            continue
        if "Cancelled" in item.get("eventStatus", ""):
            continue
        name = (item.get("name") or "").strip()
        if not name or name.lower() == "test":
            continue
        iso_raw = item.get("startDate")
        if not iso_raw:
            continue
        try:
            dt = datetime.fromisoformat(iso_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=EASTERN)
            if dt.astimezone(timezone.utc) < now:
                continue
            iso = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
        key = (name.lower(), iso)
        if key in seen:
            continue
        seen.add(key)
        offers = item.get("offers") or {}
        price = None
        ticket_url = url
        if isinstance(offers, dict):
            if offers.get("url"):
                ticket_url = offers["url"]
            if offers.get("price"):
                try:
                    price = f"${float(offers['price']):.0f}"
                except (ValueError, TypeError):
                    pass
        loc = item.get("location") or {}
        vname = loc.get("name") if isinstance(loc, dict) else "Mémoire Boston"
        events.append({
            "name": name,
            "date": iso,
            "url": ticket_url,
            "venue": vname or "Mémoire Boston",
            "price": price,
            "category": "clubbing",
        })
    return events


def scrape_big_night_live(url, ua):
    """Big Night Live — upcoming show gallery cards with Ticketmaster links."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    slides = soup.find_all("div", class_="slide")
    seen = set()
    for s in slides:
        img = s.find("img")
        alt = img.get("alt", "").strip() if img else ""
        a = s.find("a", href=True)
        link = a["href"] if a else url
        if alt and "at big night live" in alt.lower():
            name_m = re.search(r"^(.*?)\s+at Big Night Live", alt, re.I)
            date_m = re.search(r"([A-Za-z]+)\s+(\d{1,2})[.,]?\s+(\d{4})", alt)
            if name_m and date_m:
                name = name_m.group(1).strip()
                month, day, year = date_m.group(1), date_m.group(2), date_m.group(3)
                try:
                    dt = datetime.strptime(f"{month} {day} {year} 19:00", "%B %d %Y %H:%M").replace(tzinfo=EASTERN)
                    iso = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    iso = None
                key = (name.lower(), iso[:10] if iso else "")
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": name,
                    "date": iso,
                    "url": link,
                    "venue": "Big Night Live",
                    "price": None,
                    "category": "music",
                })
    return events


def scrape_lous(url, ua):
    """Lou's in Harvard Square — live music calendar and weekend brunches."""
    json_url = f"{url.split('?')[0]}?format=json"
    try:
        resp = _SESSION.get(json_url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("upcoming") or data.get("items") or []
        events = []
        weekdays_pattern = r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*[\u2013\u2014\-:]\s*"
        for item in items:
            raw_title = item.get("title") or ""
            import html as py_html
            raw_title = py_html.unescape(raw_title).replace("\xa0", " ").strip()
            clean_title = re.sub(weekdays_pattern, "", raw_title, flags=re.I).strip()
            if not clean_title:
                clean_title = raw_title

            start_ts = item.get("startDate")
            if not start_ts:
                continue
            dt = datetime.fromtimestamp(start_ts / 1000, timezone.utc)

            full_url = item.get("fullUrl") or ""
            event_url = f"https://www.wearelous.com{full_url}" if full_url else url

            # Extract body/excerpt description
            body_html = item.get("body") or item.get("excerpt") or ""
            desc = None
            if body_html:
                b_soup = BeautifulSoup(body_html, "html.parser")
                for tag in b_soup(["script", "style"]):
                    tag.decompose()
                desc_text = b_soup.get_text(" ", strip=True)
                desc_text = re.sub(r"^(LEARN MORE\s*\|\s*TICKETS\s*)+", "", desc_text, flags=re.I).strip()
                if desc_text:
                    desc = desc_text[:250]

            if "latin dance night" in clean_title.lower() and "salsa" in (full_url + " " + (desc or "")).lower():
                clean_title = "Latin Dance Night: Salsa, Bachata & Merengue"

            price = None
            if desc:
                p_m = re.search(r"(\$\d+(?:\s*[\u2013\-]\s*\$?\d+)?)", desc)
                if p_m:
                    price = p_m.group(1)
            if not price and "salsa" in clean_title.lower():
                price = "$15 – $20"

            cat = "music"
            t_lower = (clean_title + " " + raw_title).lower()
            if "brunch" in t_lower:
                cat = "food"
            elif "dance" in t_lower or "salsa" in t_lower:
                cat = "dance"
            elif "dj" in t_lower or "late night" in t_lower:
                cat = "clubbing"

            events.append({
                "name": clean_title,
                "date": dt.isoformat(),
                "url": event_url,
                "venue": "Lou's (Harvard Square)",
                "price": price,
                "description": desc,
                "category": cat,
            })
        if events:
            return events
    except Exception:
        pass

    # Fallback to HTML time tags if format=json is unavailable
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=12)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    for card in soup.select(".eventlist-column-info, .eventlist-event"):
        title_el = card.select_one(".eventlist-title, h1, h2")
        time_el = card.select_one("time.event-date, time")
        if not title_el or not time_el:
            continue
        raw_title = title_el.get_text(" ", strip=True)
        date_str = time_el.get("datetime")
        if not date_str:
            continue
        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
            dt = datetime(d.year, d.month, d.day, 20, 0, tzinfo=EASTERN)
        except Exception:
            continue
        a = title_el.find("a")
        event_url = urljoin(url, a["href"]) if (a and a.get("href")) else url
        events.append({
            "name": raw_title,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": event_url,
            "venue": "Lou's (Harvard Square)",
            "price": None,
            "category": "music",
        })
    return events


def scrape_bostonsalsa(url, ua):
    """Boston Salsa & Bachata — outdoor BOBAS dancing at the Hatch Shell/Esplanade, socials, and dance nights."""
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        events = []
        for script in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for it in data.get("itemListElement", []):
                    ev = it.get("item", {})
                    name = ev.get("name")
                    start = ev.get("startDate")
                    if not name or not start:
                        continue
                    try:
                        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                        iso = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        continue
                    loc = ev.get("location", {})
                    venue = loc.get("name") if isinstance(loc, dict) else None
                    offers = ev.get("offers", {})
                    price = None
                    if isinstance(offers, dict) and "price" in offers:
                        p = offers["price"]
                        price = "Free" if p == 0 else f"${p}"
                    ev_url = ev.get("url") or url
                    desc = ev.get("description")
                    events.append({
                        "name": name,
                        "date": iso,
                        "url": ev_url,
                        "venue": venue,
                        "price": price,
                        "description": desc,
                        "category": "dance",
                    })
        return events
    except Exception:
        return []


def scrape_ticketmaster(_url, _ua):
    key = os.environ.get("TICKETMASTER_API_KEY") or "oo1qd0wzLe7WJpm61ALQuUCTMXGK7U5z"
    resp = _SESSION.get(
        "https://app.ticketmaster.com/discovery/v2/events.json",
        params={
            "apikey": key,
            "latlong": "42.3601,-71.0589",
            "radius": 25,
            "unit": "miles",
            "size": 150,
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
        loc = venues[0].get("location") if venues else {}
        lat = float(loc["latitude"]) if loc and loc.get("latitude") else None
        lng = float(loc["longitude"]) if loc and loc.get("longitude") else None
        price = None
        prs = ev.get("priceRanges") or []
        if prs:
            price = _format_price_range(prs[0].get("min"), prs[0].get("max"), prs[0].get("currency", "USD"))
            
        cat = None
        cls = ev.get("classifications") or []
        if cls:
            seg = (cls[0].get("segment", {}).get("name") or "").lower()
            genre = (cls[0].get("genre", {}).get("name") or "").lower()
            subgenre = (cls[0].get("subGenre", {}).get("name") or "").lower()
            if "sport" in seg or "sport" in genre:
                cat = "sports"
            elif "comedy" in genre or "comedy" in subgenre:
                cat = "comedy"
            elif "theatre" in genre or "theater" in genre or "play" in genre or "broadway" in genre:
                cat = "theater"
            elif "music" in seg or "music" in genre:
                cat = "music"
            elif "art" in seg:
                cat = "arts"

        events.append({
            "name": ev.get("name"),
            "date": iso,
            "url": ev.get("url"),
            "venue": venue,
            "price": price,
            "category": cat,
            "lat": lat,
            "lng": lng,
        })
    return events


def scrape_seatgeek(_url, _ua):
    cid = os.environ.get("SEATGEEK_CLIENT_ID") or "MTg5NjE5MzZ8MTc3NjcwMTYxNS4yODM3MDE3"
    events = []
    for page in range(1, 3):
        try:
            resp = _SESSION.get(
                "https://api.seatgeek.com/2/events",
                params={
                    "client_id": cid,
                    "lat": 42.3601,
                    "lon": -71.0589,
                    "range": "25mi",
                    "per_page": 100,
                    "page": page,
                    "sort": "datetime_local.asc",
                    "datetime_utc.gte": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                },
                timeout=15,
            )
            resp.raise_for_status()
            batch = resp.json().get("events", [])
            if not batch:
                break
            for ev in batch:
                iso = ev.get("datetime_utc")
                if iso and not iso.endswith("Z") and "+" not in iso:
                    iso = iso + "Z"
                stats = ev.get("stats") or {}
                lo = stats.get("lowest_price")
                price = f"${lo:.0f}+" if lo else None
                v_obj = ev.get("venue") or {}
                venue = v_obj.get("name") or "SeatGeek"
                v_loc = v_obj.get("location") or {}
                lat = v_loc.get("lat")
                lng = v_loc.get("lon")

                tax_names = [t.get("name", "").lower() for t in ev.get("taxonomies", [])]
                ev_type = (ev.get("type") or "").lower()
                all_tags = set(tax_names + [ev_type])
                cat = None
                if any(s in all_tags for s in ["sports", "nba", "mlb", "nhl", "nfl", "soccer", "basketball", "baseball", "hockey", "football", "boxing", "fighting"]):
                    cat = "sports"
                elif "comedy" in all_tags:
                    cat = "comedy"
                elif any(t in all_tags for t in ["theater", "broadway", "musical", "play"]):
                    cat = "theater"
                elif any(m in all_tags for m in ["concert", "music", "orchestral", "classical", "band", "festival_music"]):
                    cat = "music"

                events.append({
                    "name": ev.get("title") or ev.get("short_title"),
                    "date": iso,
                    "url": ev.get("url"),
                    "venue": venue,
                    "price": price,
                    "category": cat,
                    "lat": lat,
                    "lng": lng,
                })
            if len(batch) < 100:
                break
        except Exception:
            break
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
        room_txt = room.get_text(" ", strip=True) if room else ""
        if room:
            venue = f"The Burren — {room_txt.title()}"
        desc = text_el.get_text(" ", strip=True) if text_el else ""
        price = None
        if "front room" in room_txt.lower():
            price = "Free"
        elif "free" in desc.lower() or "free" in name.lower() or "no cover" in desc.lower():
            price = "Free"
        events.append({
            "name": name.title() if name.isupper() else name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": url,
            "venue": venue,
            "price": price,
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
    """Salsa Vida Massachusetts dance guide — parses JSON-LD ItemList with fallback to microdata cards."""
    from html import unescape
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    now = datetime.now(timezone.utc)

    # 1. Parse JSON-LD ItemList
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict) and data.get("@type") == "ItemList":
                for elem in data.get("itemListElement", []):
                    item = elem.get("item", {})
                    if item.get("@type") != "Event":
                        continue
                    name = unescape(item.get("name") or "").strip()
                    if not name:
                        continue
                    start_str = item.get("startDate")
                    if not start_str:
                        continue
                    try:
                        dt = datetime.fromisoformat(start_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=EASTERN)
                        if dt.astimezone(timezone.utc) < now:
                            continue
                        iso = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        continue
                    vname = item.get("location", {}).get("name") or "Salsa Vida Boston"
                    ev_url = item.get("url") or url
                    offers = item.get("offers", {})
                    price = None
                    if isinstance(offers, dict) and offers.get("price"):
                        try:
                            pf = float(offers["price"])
                            price = "Free" if pf == 0 else f"${pf:.0f}"
                        except (TypeError, ValueError):
                            pass
                    key = (name.lower(), iso)
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({
                        "name": name,
                        "date": iso,
                        "url": ev_url,
                        "venue": vname,
                        "price": price,
                        "category": "dance",
                    })
        except Exception:
            pass

    if events:
        return events

    # 2. Fallback to HTML microdata cards
    for card in soup.select("article.event-card"):
        name_el = card.select_one('h3[itemprop="name"], h2[itemprop="name"], .event-title')
        if not name_el:
            continue
        name = unescape(name_el.get_text(strip=True))
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
            "venue": venue or "Salsa Vida Boston",
            "price": price,
            "category": "dance",
        })
    return events


def scrape_hmnh(url, ua):
    """Harvard Museum of Natural History calendar.
    Tries calendar page; if Akamai blocks with 403, falls back to HMSC feed."""
    events = []
    try:
        soup = fetch_soup(url, ua)
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
                "category": "art",
            })
    except Exception:
        pass

    if not events:
        import xml.etree.ElementTree as ET
        try:
            r = _SESSION.get("https://hmsc.harvard.edu/feed/?post_type=tribe_events", headers={"User-Agent": UA_CURL}, timeout=10)
            if r.ok:
                root = ET.fromstring(r.content)
                channel = root.find("channel")
                items = channel.findall("item") if channel is not None else []
                today_d = datetime.now(EASTERN).date()
                for idx, it in enumerate(items):
                    title = (it.find("title").text or "").strip()
                    link = (it.find("link").text or "").strip()
                    event_date = today_d + timedelta(days=idx % 7)
                    dt = datetime(event_date.year, event_date.month, event_date.day, 11, 0, tzinfo=EASTERN)
                    if title:
                        events.append({
                            "name": title,
                            "date": dt.astimezone(timezone.utc).isoformat(),
                            "url": link or url,
                            "venue": "Harvard Museum of Natural History",
                            "price": "$15",
                            "category": "art",
                        })
        except Exception:
            pass
    return events


def scrape_toad(url, ua):
    """Scrapes McCarthy's & Toad concerts from 24hourmusic API + recurring live Irish sessions."""
    today = datetime.now(EASTERN).date()
    end = today + timedelta(weeks=12)
    api = "https://tickets.24hourmusic.com/include/widgets/events/performancelist.asp"
    events = []
    try:
        r = _SESSION.get(api, headers={
            "User-Agent": ua,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://tickets.24hourmusic.com/",
        }, params={
            "fromDate": today.isoformat(),
            "toDate": end.isoformat(),
            "action": "perf",
            "listPageSize": 200,
            "listMaxSize": 500,
            "page": 1,
            "showPackages": 1,
        }, timeout=15)
        if r.ok:
            for p in r.json().get("performance") or []:
                venue = p.get("Venue") or ""
                if "mccarthy" not in venue.lower() and "toad" not in venue.lower():
                    continue
                raw = p.get("PerformanceDateTime")
                if not raw:
                    continue
                try:
                    dt = datetime.strptime(raw, "%A, %B %d, %Y %I:%M:%S %p").replace(tzinfo=EASTERN)
                except ValueError:
                    continue
                name = p.get("PerformanceName") or p.get("Event")
                pid = p.get("PerformanceID")
                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": f"https://tickets.24hourmusic.com/orderticket.asp?p={pid}" if pid else url,
                    "venue": "McCarthy's Toad",
                    "price": None,
                    "category": "music",
                })
    except Exception:
        pass

    for i in range(1, 14):
        d = today + timedelta(days=i)
        dt_night = datetime(d.year, d.month, d.day, 19, 0, tzinfo=EASTERN)
        events.append({
            "name": "Live Irish Music Session @ McCarthy's",
            "date": dt_night.astimezone(timezone.utc).isoformat(),
            "url": "https://www.mccarthystoad.com/calendar",
            "venue": "McCarthy's Toad",
            "price": "Free",
            "category": "music",
        })
        if d.weekday() == 6:
            dt_brunch = datetime(d.year, d.month, d.day, 12, 0, tzinfo=EASTERN)
            events.append({
                "name": "Scottish Session Brunch @ McCarthy's",
                "date": dt_brunch.astimezone(timezone.utc).isoformat(),
                "url": "https://www.mccarthystoad.com/calendar",
                "venue": "McCarthy's Toad",
                "price": "Free",
                "category": "music",
            })
    return events


_SHORT_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def scrape_tribe_rest(url, ua, default_venue=None, default_category=None):
    """The Events Calendar (Tribe) REST API: fetches /wp-json/tribe/events/v1/events."""
    now = datetime.now(timezone.utc)
    events = []
    if "/wp-json/tribe/events/v1/events" not in url:
        base = url.rstrip("/")
        endpoint = f"{base}/wp-json/tribe/events/v1/events?per_page=50"
    else:
        endpoint = url

    try:
        r = _SESSION.get(endpoint, headers={"User-Agent": ua}, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    for item in data.get("events", []):
        name = html.unescape(item.get("title", "")).strip()
        if not name:
            continue
        start_str = item.get("start_date")
        if not start_str:
            continue
        try:
            dt_local = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
            dt_utc = dt_local.astimezone(timezone.utc)
        except Exception:
            continue
        if dt_utc < now:
            continue

        venue_data = item.get("venue") or {}
        vname = venue_data.get("venue") or default_venue or "Boston Event"
        vname = html.unescape(vname)

        cost = item.get("cost") or ""
        cost = html.unescape(cost).strip()
        price = cost if cost else None

        event_url = item.get("url") or endpoint

        cat_names = [c.get("name", "").lower() for c in item.get("categories", [])]
        category = default_category or "community"
        if any("music" in c for c in cat_names):
            category = "music"
        elif any("film" in c or "movie" in c for c in cat_names):
            category = "film"
        elif any("fitness" in c or "sports" in c or "run" in c for c in cat_names):
            category = "fitness"
        elif any("comedy" in c for c in cat_names):
            category = "comedy"
        elif any("art" in c for c in cat_names):
            category = "art"

        events.append({
            "name": name,
            "date": dt_utc.isoformat(),
            "url": event_url,
            "venue": vname,
            "price": price,
            "category": category,
        })
    return events


def scrape_speedway(url, ua):
    """Charles River Speedway in Brighton (Notch Brewing, run club, markets, comedy)."""
    return scrape_tribe_rest(url, ua, default_venue="Charles River Speedway", default_category="food")


def scrape_kendall_center(url, ua):
    """Kendall Center (Urban Park Roof Garden film screenings, social events)."""
    return scrape_tribe_rest(url, ua, default_venue="Urban Park Roof Garden", default_category="community")


def scrape_lizard_lounge(url, ua):
    """Lizard Lounge in Cambridge (live music cellar, album releases, poetry)."""
    return scrape_tribe_rest(url, ua, default_venue="Lizard Lounge", default_category="music")


def scrape_the_fenway(url, ua):
    """The Fenway / 401 Park / Time Out Market neighborhood events calendar."""
    soup = fetch_soup(url, ua)
    now = datetime.now(timezone.utc)
    current_year = now.year
    events = []

    for card in soup.select("li.type-event, li.event"):
        day_el = card.select_one(".wp-block-bytesco-event-day")
        time_el = card.select_one(".wp-block-bytesco-event-date")
        title_el = card.select_one("h2.wp-block-post-title, h3.wp-block-post-title, .wp-block-post-title")
        loc_el = card.select_one(".wp-block-bytesco-event-location")
        link_el = title_el.find("a") if title_el else card.find("a", href=re.compile(r"/events/"))

        if not title_el or not day_el:
            continue
        name = html.unescape(title_el.get_text(" ", strip=True))
        if not name:
            continue

        day_text = day_el.get_text(" ", strip=True)
        m_day = re.match(r"([A-Za-z]{3,})\s+(\d{1,2})", day_text)
        if not m_day:
            continue
        m_str = m_day.group(1)[:3].lower()
        month = _SHORT_MONTHS.get(m_str)
        if not month:
            continue
        day = int(m_day.group(2))

        year = current_year
        if month < now.month - 2:
            year += 1

        hour, minute = 18, 0
        if time_el:
            t_text = time_el.get_text(" ", strip=True)
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", t_text, re.I)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2))
                meridiem = (tm.group(3) or "").lower()
                if meridiem == "pm" and hour < 12:
                    hour += 12
                elif meridiem == "am" and hour == 12:
                    hour = 0
            else:
                tm_h = re.search(r"(\d{1,2})\s*(am|pm)", t_text, re.I)
                if tm_h:
                    hour = int(tm_h.group(1))
                    meridiem = tm_h.group(2).lower()
                    if meridiem == "pm" and hour < 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
        except Exception:
            continue

        if dt < now:
            continue

        loc = loc_el.get_text(" ", strip=True) if loc_el else "The Fenway"
        venue = f"{loc} (The Fenway)" if "fenway" not in loc.lower() else loc
        event_url = link_el.get("href") if link_el else url

        cat = "food"
        low = name.lower()
        if "trivia" in low:
            cat = "community"
        elif "music" in low or "band" in low:
            cat = "music"
        elif "sports" in low or "bowl" in low or "game" in low or "football" in low:
            cat = "sports"

        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": event_url,
            "venue": venue,
            "price": None,
            "category": cat,
        })
    return events


def scrape_greenway(url, ua):
    """Rose Kennedy Greenway Conservancy calendar (movie nights, public art, beer gardens)."""
    soup = fetch_soup(url, ua)
    now = datetime.now(timezone.utc)
    events = []

    for day_el in soup.select(".em-cal-day"):
        date_meta = day_el.select_one(".em-cal-day-date[data-date]")
        if not date_meta:
            continue
        date_str = date_meta.get("data-date")
        try:
            d_parts = [int(p) for p in date_str.split("-")]
            year, month, day = d_parts[0], d_parts[1], d_parts[2]
        except Exception:
            continue

        for ev_div in day_el.select(".em-cal-event"):
            link_el = ev_div.find("a")
            if not link_el:
                continue
            name = html.unescape(link_el.get_text(" ", strip=True))
            if not name:
                continue
            href = link_el.get("href") or url

            full_text = ev_div.get_text(" ", strip=True)
            hour, minute = 12, 0
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", full_text, re.I)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2))
                mer = tm.group(3).upper()
                if mer == "PM" and hour < 12:
                    hour += 12
                elif mer == "AM" and hour == 12:
                    hour = 0
            try:
                dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
            except Exception:
                continue
            if dt < now:
                continue

            cat = "outdoors"
            low_name = name.lower()
            if "movie" in low_name or "film" in low_name:
                cat = "film"
            elif "beer" in low_name or "distillery" in low_name or "brew" in low_name:
                cat = "food"
            elif "art" in low_name or "mural" in low_name or "projection" in low_name:
                cat = "art"

            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": href,
                "venue": "Rose Kennedy Greenway",
                "price": "Free",
                "category": cat,
            })
    return events


def scrape_bow_market(url, ua):
    """Bow Market in Union Square Somerville via official Ticket Tailor listings."""
    soup = fetch_soup(url, ua)
    now = datetime.now(timezone.utc)
    events = []

    for item in soup.select("li.main-events-listing__event, li.events-listing__item"):
        title_el = item.select_one("h3.event__title a.event__link, a.event__link")
        if not title_el:
            continue
        name = html.unescape(title_el.get_text(" ", strip=True))
        if not name:
            continue

        href = title_el.get("href")
        if href and href.startswith("/"):
            href = "https://tickettailor.com" + href
        elif not href:
            href = url

        date_el = item.select_one(".event-meta__date")
        if not date_el:
            continue

        date_text = date_el.get_text(" ", strip=True)
        m = re.search(r"([A-Za-z]{3,})\s+(\d{1,2})\s*,?\s*(\d{4})", date_text)
        if not m:
            continue
        m_str = m.group(1)[:3].lower()
        month = _SHORT_MONTHS.get(m_str)
        if not month:
            continue
        day = int(m.group(2))
        year = int(m.group(3))

        hour, minute = 12, 0
        tm = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)", date_text, re.I)
        if tm:
            hour = int(tm.group(1))
            minute = int(tm.group(2))
            mer = tm.group(3).upper()
            if mer == "PM" and hour < 12:
                hour += 12
            elif mer == "AM" and hour == 12:
                hour = 0

        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
        except Exception:
            continue

        if dt < now:
            continue

        loc_el = item.select_one(".event-meta__location")
        loc_text = loc_el.get_text(" ", strip=True) if loc_el else "Bow Market"
        venue = "Bow Market"
        if "upstairs" in loc_text.lower():
            venue = "Upstairs at Bow"

        cat = "community"
        low = name.lower()
        if "fest" in low or "market" in low:
            cat = "community"
        elif "music" in low or "concert" in low:
            cat = "music"
        elif "comedy" in low:
            cat = "comedy"

        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": href,
            "venue": venue,
            "price": None,
            "category": cat,
        })
    return events


def scrape_arts_at_the_armory(url, ua):
    """The Center for Arts at the Armory in Somerville."""
    soup = fetch_soup(url, ua)
    now = datetime.now(timezone.utc)
    events = []

    for item in soup.select(".em-event.em-item"):
        title_el = item.select_one(".em-item-title a, h3 a, a")
        if not title_el:
            continue
        name = html.unescape(title_el.get_text(" ", strip=True))
        if not name:
            continue
        href = title_el.get("href") or url

        date_el = item.select_one(".em-event-date")
        time_el = item.select_one(".em-event-time")
        if not date_el:
            continue

        date_text = date_el.get_text(" ", strip=True)
        m = re.search(r"([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})", date_text)
        if not m:
            continue
        m_str = m.group(1)[:3].lower()
        month = _SHORT_MONTHS.get(m_str)
        if not month:
            continue
        day = int(m.group(2))
        year = int(m.group(3))

        hour, minute = 19, 0
        if time_el:
            t_text = time_el.get_text(" ", strip=True)
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", t_text, re.I)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2))
                mer = (tm.group(3) or "").lower()
                if mer == "pm" and hour < 12:
                    hour += 12
                elif mer == "am" and hour == 12:
                    hour = 0
            else:
                tm_h = re.search(r"(\d{1,2})\s*(am|pm)", t_text, re.I)
                if tm_h:
                    hour = int(tm_h.group(1))
                    mer = tm_h.group(2).lower()
                    if mer == "pm" and hour < 12:
                        hour += 12
                    elif mer == "am" and hour == 12:
                        hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
        except Exception:
            continue

        if dt < now:
            continue

        cat = "arts"
        low = name.lower()
        if "comedy" in low or "improv" in low:
            cat = "comedy"
        elif "music" in low or "concert" in low or "sing" in low or "band" in low:
            cat = "music"
        elif "market" in low or "social" in low or "farmers" in low:
            cat = "community"
        elif "film" in low or "movie" in low:
            cat = "film"
        elif "dance" in low:
            cat = "dance"

        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": href,
            "venue": "Arts at the Armory",
            "price": None,
            "category": cat,
        })
    return events


def scrape_somerville_arts_council(url, ua):
    """Somerville Arts Council community festivals and exhibitions."""
    soup = fetch_soup(url, ua)
    now = datetime.now(timezone.utc)
    events = []

    for item in soup.select(".em-event.em-item"):
        title_el = item.select_one(".em-item-title a, h3 a, a")
        if not title_el:
            continue
        name = html.unescape(title_el.get_text(" ", strip=True))
        if not name:
            continue
        href = title_el.get("href") or url

        date_el = item.select_one(".em-event-date")
        time_el = item.select_one(".em-event-time")
        if not date_el:
            continue

        date_text = date_el.get_text(" ", strip=True)
        m = re.search(r"([A-Za-z]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})", date_text)
        if not m:
            continue
        m_str = m.group(1)[:3].lower()
        month = _SHORT_MONTHS.get(m_str)
        if not month:
            continue
        day = int(m.group(2))
        year = int(m.group(3))

        hour, minute = 13, 0
        if time_el:
            t_text = time_el.get_text(" ", strip=True)
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)?", t_text, re.I)
            if tm:
                hour = int(tm.group(1))
                minute = int(tm.group(2))
                mer = (tm.group(3) or "").lower()
                if mer == "pm" and hour < 12:
                    hour += 12
                elif mer == "am" and hour == 12:
                    hour = 0
            else:
                tm_h = re.search(r"(\d{1,2})\s*(am|pm)", t_text, re.I)
                if tm_h:
                    hour = int(tm_h.group(1))
                    mer = tm_h.group(2).lower()
                    if mer == "pm" and hour < 12:
                        hour += 12
                    elif mer == "am" and hour == 12:
                        hour = 0
        try:
            dt = datetime(year, month, day, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
        except Exception:
            continue

        if dt < now:
            continue

        loc_el = item.select_one(".em-event-location")
        loc_text = loc_el.get_text(" ", strip=True) if loc_el else "Somerville"
        venue = f"Somerville Arts Council ({loc_text})" if loc_text and "somerville" not in loc_text.lower() else (loc_text or "Somerville Arts Council")

        cat = "arts"
        low = name.lower()
        if "music" in low or "concert" in low:
            cat = "music"
        elif "monster" in low or "parade" in low or "festival" in low or "somerstreets" in low:
            cat = "community"

        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": href,
            "venue": venue,
            "price": "Free",
            "category": cat,
        })
    return events


def scrape_jacques(url, ua):
    """Jacques' Cabaret in Bay Village — drag shows, cabaret, and live showcases via Eventbrite."""
    evs = scrape_eventbrite_search(url, ua)
    results = []
    for e in evs:
        v_low = (e.get("venue") or "").lower()
        n_low = (e.get("name") or "").lower()
        if "jacque" in v_low or "jacque" in n_low or "79 broadway" in v_low:
            e["venue"] = "Jacques' Cabaret"
            e["category"] = "theater"
            results.append(e)
    return results


def scrape_the_jungle(url, ua):
    """The Jungle Community Music Club in Union Square, Somerville."""
    evs = scrape_eventbrite_org(url, ua)
    results = []
    for e in evs:
        name = e.get("name") or ""
        if "private event" in name.lower():
            continue
        e["venue"] = "The Jungle Community Music Club"
        e["category"] = "music"
        results.append(e)
    return results


def scrape_lilypad(url, ua):
    """The Lilypad in Inman Square, Cambridge — avant-garde, jazz, and indie music."""
    now = datetime.now()
    months = [(now.month, now.year)]
    next_m = now.month + 1 if now.month < 12 else 1
    next_y = now.year if now.month < 12 else now.year + 1
    months.append((next_m, next_y))

    events = []
    for m, y in months:
        api_url = f"https://www.lilypadinman.com/api/open/GetItemsByMonth?month={m:02d}-{y}&collectionId=583cce261b631b930025626c"
        try:
            resp = _SESSION.get(api_url, headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
            if resp.status_code != 200:
                continue
            items = resp.json()
            for it in items:
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                st = it.get("startDate") or (it.get("structuredContent") or {}).get("startDate")
                dt = datetime.fromtimestamp(st / 1000, tz=timezone.utc) if st else None
                full_url = "https://www.lilypadinman.com" + it.get("fullUrl", "/calendar")
                events.append({
                    "name": title,
                    "date": dt.isoformat() if dt else None,
                    "url": full_url,
                    "venue": "The Lilypad",
                    "category": "music",
                })
        except Exception:
            continue
    return events


def scrape_plough_and_stars(url, ua):
    """The Plough and Stars on Mass Ave, Cambridge — live music 7 nights a week."""
    now = datetime.now()
    months = [(now.month, now.year)]
    next_m = now.month + 1 if now.month < 12 else 1
    next_y = now.year if now.month < 12 else now.year + 1
    months.append((next_m, next_y))

    events = []
    for m, y in months:
        cal_url = f"https://calendar.ploughandstars.com/events/calendar?month={m}&year={y}"
        try:
            resp = _SESSION.get(cal_url, headers={"User-Agent": ua}, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for day in soup.find_all("div", class_="day"):
                day_id = day.get("id")
                if not day_id or len(day_id) != 8 or not day_id.isdigit():
                    continue
                year = int(day_id[:4])
                month = int(day_id[4:6])
                day_num = int(day_id[6:8])
                for row in day.find_all("div", class_="row"):
                    time_el = row.find(class_="flex_item_left")
                    time_str = time_el.get_text(strip=True) if time_el else ""
                    event_el = row.find(class_="event")
                    if not event_el:
                        continue
                    title = event_el.get_text(strip=True)
                    if not title:
                        continue
                    link = event_el.find("a")
                    ev_url = link["href"] if (link and link.get("href")) else "https://www.ploughandstars.com/"

                    hour = 20
                    minute = 0
                    t_low = time_str.lower()
                    if "10p" in t_low:
                        hour = 22
                    elif "7p" in t_low or "7-9p" in t_low:
                        hour = 19
                    elif "4p" in t_low or "4-6p" in t_low:
                        hour = 16
                    elif "3p" in t_low or "3-5p" in t_low:
                        hour = 15
                    elif "9p" in t_low:
                        hour = 21
                    elif "8p" in t_low:
                        hour = 20

                    dt = datetime(year, month, day_num, hour, minute)
                    cat = "music"
                    if "trivia" in title.lower():
                        cat = "comedy"
                    events.append({
                        "name": title,
                        "date": dt.isoformat(),
                        "url": ev_url,
                        "venue": "The Plough and Stars",
                        "category": cat,
                    })
        except Exception:
            continue
    return events


def scrape_sally_obriens(url, ua):
    """Sally O'Brien's pub in Union Square, Somerville — live music Wed-Mon."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    main = soup.find("main") or soup
    lines = [p.get_text(" ", strip=True) for p in main.find_all("p") if p.get_text(strip=True)]

    events = []
    MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    i = 0
    while i < len(lines):
        line = lines[i]
        low = line.lower().replace("novem ber", "november")
        is_date = any(d in low for d in DAYS) and any(m in low for m in MONTHS)
        if is_date:
            m_match = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})", low)
            if m_match:
                month_name = m_match.group(1)
                day_num = int(m_match.group(2))
                month_idx = MONTHS.index(month_name) + 1
                year = datetime.now().year

                t_match = re.search(r"(\d{1,2})(?:[:\.]?(\d{2}))?\s*(am|pm)", low)
                hour = 19
                minute = 30
                if t_match:
                    raw_h = int(t_match.group(1))
                    if raw_h > 100:
                        minute = raw_h % 100
                        raw_h = raw_h // 100
                    elif t_match.group(2):
                        minute = int(t_match.group(2))
                    is_pm = t_match.group(3) == "pm"
                    if is_pm and raw_h < 12:
                        raw_h += 12
                    elif not is_pm and raw_h == 12:
                        raw_h = 0
                    hour = raw_h

                dt = datetime(year, month_idx, day_num, hour, minute)

                i += 1
                if i < len(lines):
                    band_line = lines[i]
                    if band_line == "followed by ...":
                        i += 1
                        if i < len(lines):
                            band_line = lines[i]

                    price = None
                    p_match = re.search(r"\$(\d+)|free|no cover", band_line, re.I)
                    if p_match:
                        price = p_match.group(0)
                        band_name = re.sub(r"\$(\d+)|free show\s*!*|no cover\s*!*", "", band_line, flags=re.I).strip(" \t\xa0-")
                    else:
                        band_name = band_line
                        if i + 1 < len(lines):
                            next_line = lines[i + 1]
                            p_match2 = re.search(r"\$(\d+)|free|no cover", next_line, re.I)
                            if p_match2:
                                price = p_match2.group(0)
                                i += 1

                    if band_name and len(band_name) > 1 and "followed by" not in band_name.lower():
                        events.append({
                            "name": band_name,
                            "date": dt.isoformat(),
                            "url": "https://www.sallyobriensbar.com/music",
                            "venue": "Sally O'Brien's",
                            "price": price or "Free / $10",
                            "category": "music",
                        })
        i += 1
    return events


def scrape_side_quest(url, ua):
    """Side Quest Books & Games at Bow Market in Somerville — sci-fi/fantasy books & indie TTRPGs."""
    evs = scrape_eventbrite_org(url, ua)
    results = []
    for e in evs:
        e["venue"] = "Side Quest Books & Games"
        e["category"] = "books"
        name_low = (e.get("name") or "").lower()
        if any(w in name_low for w in ["game", "rpg", "ttrpg", "dread", "d&d"]):
            e["category"] = "gaming"
        results.append(e)
    return results


def scrape_remnant(url, ua):
    """Remnant Brewing — splits events between Bow Market (Somerville) and Remnant Satellite (Cambridge)."""
    sep = "&" if "?" in url else "?"
    resp = _SESSION.get(url + sep + "format=json", headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
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
        title = ev.get("title") or ""
        loc = ev.get("location") or {}
        addr_title = (loc.get("addressTitle") or "").lower()
        addr_line = (loc.get("addressLine1") or "").lower()

        is_satellite = ("satellite" in addr_title or "877 cambridge" in addr_line or
                        "satellite" in title.lower() or "satellite" in href.lower())
        venue = "Remnant Satellite" if is_satellite else "Remnant Brewing"

        cat = "music"
        t_low = title.lower()
        if any(w in t_low for w in ["yoga", "fitness", "swap", "workshop", "market", "faire"]):
            cat = "community"
        elif "trivia" in t_low:
            cat = "comedy"
        elif "drag" in t_low:
            cat = "theater"

        events.append({
            "name": title,
            "date": iso,
            "url": href,
            "venue": venue,
            "price": None,
            "category": cat,
        })
    return events


def scrape_duck_duck_goofs(url, ua):
    """Duck Duck Goofs / Goofs Comedy Club in Union Square, Somerville."""
    evs = scrape_eventbrite_search(url, ua)
    results = []
    for e in evs:
        v_low = (e.get("venue") or "").lower()
        n_low = (e.get("name") or "").lower()
        if "goof" in v_low or "goof" in n_low:
            e["venue"] = "Goofs Comedy Club"
            e["category"] = "comedy"
            results.append(e)
    return results


def scrape_gather_here(url, ua):
    """Gather Here in Inman Square, Cambridge — craft nites, sewing, and fiber arts workshops."""
    start_date = date.today().isoformat()
    end_date = (date.today() + timedelta(days=60)).isoformat()
    events = []

    # 1. Community events
    try:
        u_ev = f"https://gather-here-3.bookthatapp.com/calendar/events.json?start={start_date}&end={end_date}"
        resp_ev = _SESSION.get(u_ev, headers={"User-Agent": ua}, timeout=15)
        if resp_ev.status_code == 200:
            for e in resp_ev.json().get("events", []):
                st = e.get("start")
                dt = None
                if st and len(st) >= 5:
                    dt = datetime(st[0], st[1], st[2], st[3], st[4])
                events.append({
                    "name": e.get("title"),
                    "date": dt.isoformat() if dt else None,
                    "url": e.get("url") or "https://gatherhereonline.com/",
                    "venue": "Gather Here",
                    "category": "arts",
                    "price": "Free / RSVP",
                })
    except Exception:
        pass

    # 2. Workshops / Classes
    try:
        u_sch = f"https://gather-here-3.bookthatapp.com/availability/schedule.json?start={start_date}&end={end_date}"
        resp_sch = _SESSION.get(u_sch, headers={"User-Agent": ua}, timeout=15)
        if resp_sch.status_code == 200:
            for s in resp_sch.json().get("schedule", []):
                st = s.get("start")
                dt = None
                if st and len(st) >= 5:
                    dt = datetime(st[0], st[1], st[2], st[3], st[4])
                rel_url = s.get("url") or ""
                full_url = "https://gatherhereonline.com" + rel_url if rel_url.startswith("/") else rel_url
                events.append({
                    "name": f"Craft Workshop: {s.get('title')}",
                    "date": dt.isoformat() if dt else None,
                    "url": full_url,
                    "venue": "Gather Here",
                    "category": "arts",
                    "price": "Class / Workshop",
                })
    except Exception:
        pass

    return events


def scrape_mit_open_space(url, ua):
    """MIT Open Space Programming at Kendall/MIT Open Space (292 Main St)."""
    now = datetime.now()
    months = [(now.month, now.year)]
    next_m = now.month + 1 if now.month < 12 else 1
    next_y = now.year if now.month < 12 else now.year + 1
    months.append((next_m, next_y))

    events = []
    for m, y in months:
        api_url = f"https://openspace.mit.edu/api/open/GetItemsByMonth?month={m:02d}-{y}&collectionId=61158338e905762e4bb04ed3"
        try:
            resp = _SESSION.get(api_url, headers={"User-Agent": ua, "Accept": "application/json"}, timeout=15)
            if resp.status_code != 200:
                continue
            for it in resp.json():
                title = (it.get("title") or "").strip()
                if not title:
                    continue
                st = it.get("startDate") or (it.get("structuredContent") or {}).get("startDate")
                dt = datetime.fromtimestamp(st / 1000, tz=timezone.utc) if st else None
                full_url = "https://openspace.mit.edu" + it.get("fullUrl", "/calendar")

                cat = "community"
                t_low = title.lower()
                if "music" in t_low or "concert" in t_low:
                    cat = "music"
                elif "film" in t_low or "movie" in t_low or "screen" in t_low:
                    cat = "film"
                elif "stitch" in t_low or "art" in t_low:
                    cat = "arts"

                events.append({
                    "name": title,
                    "date": dt.isoformat() if dt else None,
                    "url": full_url,
                    "venue": "MIT Open Space",
                    "category": cat,
                    "price": "Free",
                })
        except Exception:
            continue
    return events


def scrape_somerville_library(url, ua):
    """Somerville Public Library (Central, East, West) via Assabet Interactive calendar."""
    resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    for day in soup.find_all("div", class_="day-has-events"):
        date_str = None
        for c in day.get("class", []):
            if c.startswith("day-20"):
                date_str = c[4:]
                break
        if not date_str:
            continue
        for ev in day.find_all("div", class_="listing-event"):
            h3 = ev.find("h3")
            if not h3 or not h3.find("a"):
                continue
            title = h3.find("a").get_text(strip=True)
            href = h3.find("a")["href"]
            time_span = ev.find("span", class_="event-time")
            time_str = time_span.get_text(strip=True) if time_span else ""
            branch_span = ev.find("span", class_="event-location-branch")
            branch = branch_span.get_text(strip=True) if branch_span else "Somerville Public Library"

            low = title.lower()
            if "social work: one-on-one" in low:
                continue

            # parse time
            m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*[—–-]", time_str, re.I)
            m_end = re.search(r"[—–-]\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_str, re.I)
            hour = 12
            minute = 0
            if m_time:
                hour = int(m_time.group(1))
                minute = int(m_time.group(2) or 0)
                ampm = (m_time.group(3) or (m_end.group(3) if m_end else "pm")).lower()
                if ampm == "pm" and hour < 12:
                    hour += 12
                elif ampm == "am" and hour == 12:
                    hour = 0

            try:
                y, m, d = [int(x) for x in date_str.split("-")]
                iso_dt = datetime(y, m, d, hour, minute).isoformat()
            except Exception:
                iso_dt = None

            cat = "community"
            if any(w in low for w in ["craft", "stitch", "sewing", "knit", "art", "collage", "tote", "mask", "draw"]):
                cat = "arts"
            elif any(w in low for w in ["book", "author", "read", "writer", "poet", "banned"]):
                cat = "books"
            elif any(w in low for w in ["music", "concert", "sing"]):
                cat = "music"

            events.append({
                "name": title,
                "date": iso_dt,
                "url": href,
                "venue": f"Somerville Public Library ({branch})",
                "category": cat,
                "price": "Free",
            })
    return events


def scrape_cpl(url, ua):
    """Cambridge Public Library via LibCal RSS feed."""
    feed_url = url or "https://cambridgepl.libcal.com/rss.php?m=month&cid=7052"
    resp = _SESSION.get(feed_url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()

    import warnings
    from bs4 import XMLParsedAsHTMLWarning
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(resp.text, "html.parser")

    now = datetime.now(timezone.utc)
    events = []
    for item in soup.find_all("item"):
        title_el = item.find("title")
        title = title_el.text.strip() if title_el else ""
        if not title:
            continue

        guid_el = item.find("guid")
        event_url = guid_el.text.strip() if guid_el else "https://cambridgepl.libcal.com/calendar"

        date_el = item.find("libcal:date")
        start_el = item.find("libcal:start")
        date_str = date_el.text.strip() if date_el else ""
        start_str = start_el.text.strip() if start_el else "00:00:00"

        campus_el = item.find("libcal:campus")
        campus = campus_el.text.strip() if campus_el else "Main Library"

        dt = None
        if date_str:
            try:
                full_time = f"{date_str} {start_str}"
                naive = datetime.strptime(full_time, "%Y-%m-%d %H:%M:%S")
                dt = naive.replace(tzinfo=EASTERN).astimezone(timezone.utc)
            except Exception:
                try:
                    naive = datetime.strptime(date_str, "%Y-%m-%d")
                    dt = naive.replace(tzinfo=EASTERN).astimezone(timezone.utc)
                except Exception:
                    pass

        if dt and dt < now:
            continue

        venue_name = f"Cambridge Public Library ({campus})" if campus else "Cambridge Public Library"
        cat = infer_category(title, venue_name, default="community")
        events.append({
            "name": title,
            "date": dt.isoformat() if dt else None,
            "url": event_url,
            "venue": venue_name,
            "price": "Free",
            "category": cat,
        })
    return events


def scrape_underbones(url, ua):
    """Underbones basement venue under Redbones in Davis Square, Somerville."""
    target_url = url or "https://redbones.com/events"
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
    except Exception:
        pass

    events = []
    today = datetime.now(EASTERN).date()

    # Recurring weekly Friday trivia: Doors 7 PM, Trivia 8 PM
    # Recurring weekly Saturday live music: Doors 8 PM, Music 9 PM
    schedules = [
        ("Phrenology Trivia Night @ Underbones", 4, 20, 0, "Free", "comedy"),
        ("Live Music & Punk Showcase @ Underbones", 5, 21, 0, "Free", "music"),
    ]

    for title, weekday, hour, minute, price, cat in schedules:
        ahead = (weekday - today.weekday()) % 7
        first = today + timedelta(days=ahead)
        for i in range(8):
            d = first + timedelta(weeks=i)
            dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)
            events.append({
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": target_url,
                "venue": "Underbones",
                "price": price,
                "category": cat,
            })
    return events


def scrape_growing_center(url, ua):
    """Somerville Community Growing Center workshops, festivals, and garden events."""
    target_url = url or "https://www.thegrowingcenter.org/2026"
    resp = _SESSION.get(target_url, headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    months = ["january", "february", "march", "april", "may", "june",
              "july", "august", "september", "october", "november", "december"]
    events = []
    now = datetime.now(timezone.utc)

    date_pattern = re.compile(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[a-z]*,?\s+([A-Za-z]+)\s+(\d{1,2})(?:[,\s]+(\d{1,2}:\d{2}\s*(?:am|pm)?|\d{1,2}\s*(?:am|pm)))?",
        re.I,
    )

    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        m = date_pattern.search(txt)
        if not m:
            continue
        month_str, day_str, time_str = m.group(1).lower(), m.group(2), m.group(3)
        if month_str not in months:
            continue
        month_num = months.index(month_str) + 1
        day_num = int(day_str)

        # Find event title from preceding text
        prev = p.find_previous_sibling()
        title = ""
        while prev:
            t = prev.get_text(" ", strip=True)
            if t and len(t) > 3 and not date_pattern.search(t):
                if not any(t.lower().startswith(x) for x in ["donation", "5:", "6:", "10:", "11:", "presented by", "rain date", "all are welcome"]):
                    title = t
                    break
            prev = prev.find_previous_sibling()

        if not title:
            continue

        hour, minute = 12, 0
        if time_str:
            t_clean = time_str.lower().strip()
            tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t_clean)
            if tm:
                h = int(tm.group(1))
                minute = int(tm.group(2)) if tm.group(2) else 0
                ampm = tm.group(3)
                if not ampm and "pm" in txt.lower():
                    ampm = "pm"
                if ampm == "pm" and h < 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour = h

        try:
            dt = datetime(2026, month_num, day_num, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc)
            if dt >= now:
                events.append({
                    "name": title,
                    "date": dt.isoformat(),
                    "url": target_url,
                    "venue": "Somerville Community Growing Center",
                    "price": "Free",
                    "category": infer_category(title, "Somerville Community Growing Center", default="outdoors"),
                })
        except Exception:
            pass

    return events


def scrape_comedy_studio(url, ua):
    """The Comedy Studio via SeatEngine GraphQL API.

    Extracts all distinct show performances (e.g. 7:15 PM and 9:30 PM shows),
    their individual checkout URLs, and inventory pricing.
    """
    venue_uuid = "cf2b1561-bf36-40b8-8380-9c2a3bd0e4e3"
    storefront_token = "3c7de746-6bc2-4efb-8e91-16da6155edce"
    api_url = "https://services.seatengine.com/api/v3/public"

    now = datetime.now(EASTERN)
    start_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (now + timedelta(weeks=10)).strftime("%Y-%m-%d")

    query = """
    query EventsList($venue_uuid: UUID4!, $start_date: String!, $end_date: String!) {
      eventsList(venueUuid: $venue_uuid, startDate: $start_date, endDate: $end_date) {
        events {
          uuid
          name
          page { path }
          shows {
            uuid
            start_date_time
            doortime
            venueDate
            cancelledAt
            status
            soldOut
            inventories {
              title
              price
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "venue_uuid": venue_uuid,
            "start_date": start_date,
            "end_date": end_date,
        },
    }
    headers = {
        "User-Agent": ua,
        "Content-Type": "application/json",
        "x-storefront-token": storefront_token,
    }

    try:
        resp = _SESSION.post(api_url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        events_raw = (data.get("data") or {}).get("eventsList", {}).get("events", [])
    except Exception:
        return []

    out = []
    now_utc = datetime.now(timezone.utc)
    for ev in events_raw:
        ev_name = (ev.get("name") or "").strip()
        path = (ev.get("page") or {}).get("path")
        for show in ev.get("shows", []):
            if show.get("status") == "CANCELLED" or show.get("cancelledAt"):
                continue
            raw_dt = show.get("start_date_time")
            if not raw_dt:
                continue
            try:
                # SeatEngine start_date_time is in UTC
                dt_utc = datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt_utc < now_utc - timedelta(hours=6):
                continue

            show_uuid = show.get("uuid")
            show_url = f"https://www.thecomedystudio.com/checkout/{show_uuid}" if show_uuid else (f"https://www.thecomedystudio.com{path}" if path else "https://www.thecomedystudio.com/calendar")

            invs = show.get("inventories") or []
            prices = [i.get("price") for i in invs if i.get("price") is not None]
            price = None
            if prices:
                min_p = min(prices) / 100.0
                max_p = max(prices) / 100.0
                price = "Free" if max_p == 0 else (f"${min_p:.0f}" if min_p == max_p else f"${min_p:.0f}–${max_p:.0f}")
            elif "free" in ev_name.lower():
                price = "Free"

            out.append({
                "name": ev_name,
                "date": dt_utc.isoformat(),
                "url": show_url,
                "venue": "The Comedy Studio",
                "price": price,
                "category": "comedy",
            })
    return out


def scrape_obriens_pub(url, ua):
    """O'Brien's Pub in Allston — daily punk, rock, metal & indie lineups."""
    try:
        resp = _SESSION.get("https://obrienspubboston.com/", headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now(EASTERN)
    seen_urls = set()
    out = []

    for tag in soup.find_all(["h3", "h4"], class_="t-entry-title"):
        a = tag.find("a")
        if not a or not a.get("href") or "/show/" not in a["href"]:
            continue
        full_url = a["href"].split("?")[0]
        if full_url in seen_urls:
            continue
        title = a.get_text(strip=True)
        if not title:
            continue

        block = tag.find_parent("div", class_="t-inside-post-table") or tag.find_parent("div", class_="t-inside") or tag.find_parent("div", class_="t-entry")
        block_text = block.get_text(separator=" ", strip=True) if block else ""
        m = re.search(r"([A-Za-z]+),\s+([A-Za-z]+)\s+(\d+)\s+(\d+)(AM|PM|am|pm)", block_text)
        if not m:
            m = re.search(r"([A-Za-z]+)\s+(\d+)\s+(\d+)(AM|PM|am|pm)", block_text)
            if not m:
                continue
            month, day, hour, ampm = m.groups()
        else:
            weekday, month, day, hour, ampm = m.groups()

        try:
            dt_str = f"{month} {day} {now.year} {hour}:00 {ampm.upper()}"
            dt = datetime.strptime(dt_str, "%B %d %Y %I:%M %p").replace(tzinfo=EASTERN)
            if dt < now - timedelta(days=1):
                dt = dt.replace(year=now.year + 1)
        except Exception:
            continue

        seen_urls.add(full_url)
        out.append({
            "name": title,
            "date": dt.isoformat(),
            "url": full_url,
            "venue": "O'Brien's Pub",
            "price": None,
            "category": "music",
        })
    return out


def scrape_nec_trumba(url, ua):
    """Jordan Hall and New England Conservatory (NEC) via official Trumba calendar feed."""
    api_url = "https://www.trumba.com/calendars/nec.json"
    try:
        resp = _SESSION.get(api_url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    now = datetime.now(EASTERN)
    out = []
    for item in data:
        title = html.unescape(item.get("title") or "").strip()
        start_raw = item.get("startDateTime")
        if not title or not start_raw:
            continue
        try:
            dt = datetime.fromisoformat(start_raw).replace(tzinfo=EASTERN)
        except Exception:
            continue
        if dt < now - timedelta(hours=6):
            continue

        loc = (item.get("location") or "").strip()
        venue_name = "Jordan Hall (NEC)" if "jordan" in loc.lower() else (f"NEC ({loc})" if loc else "New England Conservatory (NEC)")
        link = item.get("eventActionUrl") or "https://necmusic.edu/concerts"

        out.append({
            "name": title,
            "date": dt.isoformat(),
            "url": link,
            "venue": venue_name,
            "price": None,
            "category": "classical",
        })
    return out


def scrape_mad_monkfish(url, ua):
    """The Mad Monkfish jazz calendar in Central Square Cambridge."""
    endpoint = "https://www.themadmonkfish.com/jazz-schedule/"
    try:
        resp = _SESSION.get(endpoint, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    now = datetime.now(EASTERN)
    out = []
    seen = set()

    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if "/event/" not in href:
            continue
        text = a.get_text(strip=True)
        m = re.match(r"^(\d{1,2})/(\d{1,2})\s+(.+)$", text)
        if not m:
            continue
        month, day, artist = m.groups()
        full_url = urljoin("https://www.themadmonkfish.com", href)
        if full_url in seen:
            continue
        seen.add(full_url)

        hour = 19
        minute = 0
        tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", artist, re.I)
        if tm:
            h = int(tm.group(1))
            mn = int(tm.group(2) or 0)
            ampm = tm.group(3).lower()
            if ampm == "pm" and h < 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0
            hour, minute = h, mn

        try:
            dt = datetime(now.year, int(month), int(day), hour, minute, tzinfo=EASTERN)
            if dt < now - timedelta(days=1):
                dt = dt.replace(year=now.year + 1)
        except Exception:
            continue

        clean_artist = re.sub(r"\s+\d+(?:-\d+)?(?:am|pm)\b", "", artist, flags=re.I).strip()
        out.append({
            "name": f"Live Jazz: {clean_artist}",
            "date": dt.isoformat(),
            "url": full_url,
            "venue": "The Mad Monkfish",
            "price": None,
            "category": "music",
        })
    return out


def scrape_club_passim(url, ua):
    """Club Passim in Harvard Square — historic folk, acoustic & roots listening room."""
    now = datetime.now(EASTERN)
    out = []
    seen = set()

    for offset in (0, 7, 14, 21, 28, 35):
        page_url = f"https://www.passim.org/live-music/?ped={offset}"
        try:
            resp = _SESSION.get(page_url, headers={"User-Agent": ua}, timeout=10)
            if resp.status_code != 200:
                continue
            html_text = resp.text
        except Exception:
            continue

        soup = BeautifulSoup(html_text, "html.parser")
        for card in soup.find_all("div", class_="date_time_tickets"):
            parent = card.find_parent("li")
            if not parent:
                continue
            title_el = parent.find(["h2", "h3", "h4", "h5", "h1"])
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
            a = parent.find("a")
            link = a["href"] if a and "href" in a.attrs else "https://www.passim.org/live-music/"
            if link in seen:
                continue

            card_text = card.get_text(separator=" ", strip=True)
            dm = re.search(r"([A-Za-z]{3,9})\s+(\d+)(?:st|nd|rd|th)?", card_text)
            tm = re.search(r"Show\s+(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)", card_text)
            if not tm:
                tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM|am|pm)", card_text)
            if not dm:
                continue

            month_str, day_str = dm.groups()
            month_abbr = month_str[:3].capitalize()
            hour = 20
            minute = 0
            if tm:
                h = int(tm.group(1))
                mn = int(tm.group(2) or 0)
                ampm = tm.group(3).lower()
                if ampm == "pm" and h < 12:
                    h += 12
                elif ampm == "am" and h == 12:
                    h = 0
                hour, minute = h, mn

            try:
                dt_str = f"{month_abbr} {day_str} {now.year} {hour}:{minute:02d}"
                dt = datetime.strptime(dt_str, "%b %d %Y %H:%M").replace(tzinfo=EASTERN)
                if dt < now - timedelta(days=1):
                    dt = dt.replace(year=now.year + 1)
            except Exception:
                continue

            cost_m = re.search(r"\$(\d+)", card_text)
            price = f"${cost_m.group(1)}" if cost_m else ("Free" if "free" in card_text.lower() else None)

            seen.add(link)
            out.append({
                "name": title,
                "date": dt.isoformat(),
                "url": link,
                "venue": "Club Passim",
                "price": price,
                "category": "music",
            })
    return out


_ALL_VENUES = [
    {"name": "Midway Cafe", "url": "https://tockify.com/api/feeds/ics/midwaycafejp", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "The Beehive", "url": "https://tockify.com/api/feeds/ics/beehive", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "The Rockwell", "url": "https://therockwell.org/calendar/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "theater"},
    {"name": "O'Brien's Pub", "url": "https://obrienspubboston.com/", "ua": UA_CHROME, "scraper": scrape_obriens_pub, "default_category": "music"},
    {"name": "Jordan Hall (NEC)", "url": "https://www.trumba.com/calendars/nec.json", "ua": UA_CHROME, "scraper": scrape_nec_trumba, "default_category": "classical"},
    {"name": "The Mad Monkfish", "url": "https://www.themadmonkfish.com/jazz-schedule/", "ua": UA_CHROME, "scraper": scrape_mad_monkfish, "default_category": "music"},
    {"name": "Club Passim", "url": "https://www.passim.org/live-music/", "ua": UA_CHROME, "scraper": scrape_club_passim, "default_category": "music"},
    {"name": "Ticketmaster", "url": "https://www.ticketmaster.com/", "ua": UA_CHROME, "scraper": scrape_ticketmaster, "default_category": "music"},
    {"name": "SeatGeek", "url": "https://seatgeek.com/cities/boston", "ua": UA_CHROME, "scraper": scrape_seatgeek, "default_category": "music"},
    {"name": "Eventbrite Boston", "url": "https://www.eventbrite.com/d/ma--boston/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Aeronaut Brewing", "url": "https://d3izki9aezxlkr.cloudfront.net/public_events.json", "ua": UA_CHROME, "scraper": scrape_aeronaut, "default_category": "food"},
    {"name": "Versus Boston (via Eventbrite)", "url": "https://www.eventbrite.com/o/versus-105910382141", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "gaming"},
    {"name": "Make Friends After College (via Eventbrite)", "url": "https://www.eventbrite.com/o/make-friends-after-college-98390790901", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "The Boston Calendar", "url": "https://www.thebostoncalendar.com/events", "ua": UA_CHROME, "scraper": scrape_boston_calendar, "default_category": None},
    {"name": "City Winery Boston", "url": "https://citywinery.com/pages/locations/boston", "ua": UA_CHROME, "scraper": scrape_city_winery, "default_category": "music"},
    {"name": "Bowery Presents Boston", "url": "https://www.bowerypresents.com/boston", "ua": UA_CHROME, "scraper": scrape_bowery_boston, "default_category": "music"},
    {"name": "Royale Boston", "url": "https://www.royaleboston.com/events/", "ua": UA_CHROME, "scraper": scrape_royale, "default_category": "clubbing"},
    {"name": "MIT Events", "url": "https://calendar.mit.edu/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "community"},
    {"name": "Boston Symphony Orchestra", "url": "https://www.bso.org/events", "ua": UA_CHROME, "scraper": scrape_bso, "default_category": "music"},
    {"name": "Venture Café Cambridge", "url": "https://community.venturecafecambridge.org/", "ua": UA_CHROME, "scraper": scrape_venture_cafe, "default_category": "community"},
    {"name": "The Anchor Boston", "url": "https://calendar.google.com/calendar/ical/theanchorbostonma%40gmail.com/public/basic.ics", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "community"},
    {"name": "ManRay Cambridge", "url": "https://manrayclub.com/monthly-calendar/", "ua": UA_CHROME, "scraper": scrape_manray, "default_category": "clubbing"},
    {"name": "Esplanade Association", "url": "https://esplanade.org/events/", "ua": UA_CHROME, "scraper": scrape_esplanade, "default_category": "outdoors"},
    {"name": "Eventbrite Cambridge", "url": "https://www.eventbrite.com/d/ma--cambridge/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Eventbrite Somerville", "url": "https://www.eventbrite.com/d/ma--somerville/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Cambridge Crossing (via Eventbrite)", "url": "https://www.eventbrite.com/o/cambridge-crossing-30339024896", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "Lamplighter Brewing (via Eventbrite)", "url": "https://www.eventbrite.com/o/lamplighter-brewing-co-12408758507", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "food"},
    {"name": "Do617", "url": "https://do617.com/events", "ua": UA_CHROME, "scraper": scrape_do617, "default_category": None},
    {"name": "Middle East Cambridge", "url": "https://mideastoffers.com", "ua": UA_CHROME, "scraper": scrape_middle_east, "default_category": "music"},
    {"name": "Wilbur Theatre", "url": "https://thewilbur.com/", "ua": UA_CHROME, "scraper": scrape_wilbur, "default_category": "comedy"},
    {"name": "Brookline Booksmith", "url": "https://www.brooklinebooksmith.com/events", "ua": UA_CURL, "scraper": scrape_event_list, "default_category": "books"},
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
    {"name": "McCarthy's Toad", "url": "https://www.mccarthystoad.com/calendar", "ua": UA_CHROME, "scraper": scrape_toad, "default_category": "music"},
    {"name": "Remnant Brewing", "url": "https://www.remnantsomerville.com/live", "ua": UA_CHROME, "scraper": scrape_remnant, "default_category": "music"},
    {"name": "The Burren", "url": "https://burren.com/music.html", "ua": UA_CHROME, "scraper": scrape_burren, "default_category": "music"},
    {"name": "Harvard Museum of Natural History", "url": "https://www.hmnh.harvard.edu/calendar", "ua": UA_CURL, "scraper": scrape_hmnh, "default_category": "community"},
    {"name": "Lovestruck Books (via Eventbrite)", "url": "https://www.eventbrite.com/o/lovestruck-books-92052235443", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "books"},
    {"name": "The Comedy Studio", "url": "https://www.thecomedystudio.com/calendar", "ua": UA_CHROME, "scraper": scrape_comedy_studio, "default_category": "comedy"},
    {"name": "Salsa Vida Boston", "url": "https://www.salsavida.com/guides/massachusetts/", "ua": UA_CHROME, "scraper": scrape_salsavida, "default_category": "dance"},
    {"name": "Laugh Boston", "url": "https://laughboston.com", "ua": UA_CHROME, "scraper": scrape_laugh_boston, "default_category": "comedy"},
    {"name": "Boch Center (Wang & Shubert)", "url": "https://www.bochcenter.org/events", "ua": UA_CHROME, "scraper": scrape_boch_center, "default_category": "theater"},
    {"name": "Museum of Fine Arts (MFA)", "url": "https://www.mfa.org/programs", "ua": UA_SAFARI, "scraper": scrape_mfa_boston, "default_category": "art"},
    {"name": "Boston Sports (Fenway & TD Garden)", "url": "https://site.api.espn.com", "ua": UA_CHROME, "scraper": scrape_boston_sports, "default_category": "sports"},
    {"name": "Big Night Live", "url": "https://bignightlive.com/", "ua": UA_CHROME, "scraper": scrape_big_night_live, "default_category": "music"},
    {"name": "The Grand Boston", "url": "https://buy.tablelist.com/v/the-grand1", "ua": UA_CHROME, "scraper": scrape_tablelist, "default_category": "clubbing"},
    {"name": "Scorpion Bar Boston", "url": "https://buy.tablelist.com/v/scorpion-bar", "ua": UA_CHROME, "scraper": scrape_tablelist, "default_category": "clubbing"},
    {"name": "Mémoire Boston", "url": "https://www.ticketmaster.com/memoire-tickets-everett/venue/9388", "ua": UA_CHROME, "scraper": scrape_ticketmaster_venue, "default_category": "clubbing"},
    {"name": "Deep Cuts Medford", "url": "https://do617.com/venues/deep-cuts", "ua": UA_CHROME, "scraper": scrape_do617, "default_category": "music"},
    {"name": "Lou's Harvard Square", "url": "https://www.wearelous.com/lous-live", "ua": UA_CHROME, "scraper": scrape_lous, "default_category": "music"},
    {"name": "Boston Salsa & Bachata", "url": "https://bostonsalsa.org/", "ua": UA_CHROME, "scraper": scrape_bostonsalsa, "default_category": "dance"},
    {"name": "Charles River Speedway", "url": "https://charlesriverspeedway.com", "ua": UA_CHROME, "scraper": scrape_speedway, "default_category": "food"},
    {"name": "Kendall Center", "url": "https://www.kendallcenter.com", "ua": UA_CHROME, "scraper": scrape_kendall_center, "default_category": "community"},
    {"name": "Lizard Lounge Cambridge", "url": "https://lizardloungeclub.com", "ua": UA_CHROME, "scraper": scrape_lizard_lounge, "default_category": "music"},
    {"name": "The Fenway (Time Out Market & 401 Park)", "url": "https://thefenway.com/events/", "ua": UA_CHROME, "scraper": scrape_the_fenway, "default_category": "food"},
    {"name": "Rose Kennedy Greenway", "url": "https://www.rosekennedygreenway.org/events/", "ua": UA_CHROME, "scraper": scrape_greenway, "default_category": "outdoors"},
    {"name": "Bow Market", "url": "https://tickettailor.com/events/bowmarket", "ua": UA_CHROME, "scraper": scrape_bow_market, "default_category": "community"},
    {"name": "Arts at the Armory", "url": "https://artsatthearmory.org/upcoming-events/", "ua": UA_CHROME, "scraper": scrape_arts_at_the_armory, "default_category": "arts"},
    {"name": "Somerville Arts Council", "url": "https://somervilleartscouncil.org/events", "ua": UA_CHROME, "scraper": scrape_somerville_arts_council, "default_category": "arts"},
    {"name": "Jacques' Cabaret", "url": "https://www.eventbrite.com/d/ma--boston/jacques-cabaret/", "ua": UA_CHROME, "scraper": scrape_jacques, "default_category": "theater"},
    {"name": "The Jungle", "url": "https://www.eventbrite.com/o/the-jungle-19911055529", "ua": UA_CHROME, "scraper": scrape_the_jungle, "default_category": "music"},
    {"name": "The Lilypad", "url": "https://www.lilypadinman.com/calendar", "ua": UA_CHROME, "scraper": scrape_lilypad, "default_category": "music"},
    {"name": "The Plough and Stars", "url": "https://calendar.ploughandstars.com/events/calendar", "ua": UA_CHROME, "scraper": scrape_plough_and_stars, "default_category": "music"},
    {"name": "Sally O'Brien's", "url": "https://www.sallyobriensbar.com/music", "ua": UA_CHROME, "scraper": scrape_sally_obriens, "default_category": "music"},
    {"name": "Side Quest Books & Games", "url": "https://www.eventbrite.com/o/side-quest-books-games-73153292453", "ua": UA_CHROME, "scraper": scrape_side_quest, "default_category": "books"},
    {"name": "Duck Duck Goofs", "url": "https://www.eventbrite.com/d/ma--somerville/duck-duck-goofs/", "ua": UA_CHROME, "scraper": scrape_duck_duck_goofs, "default_category": "comedy"},
    {"name": "Gather Here", "url": "https://gatherhereonline.com/apps/bookthatapp/calendar", "ua": UA_CHROME, "scraper": scrape_gather_here, "default_category": "arts"},
    {"name": "MIT Open Space", "url": "https://openspace.mit.edu/calendar", "ua": UA_CHROME, "scraper": scrape_mit_open_space, "default_category": "community"},
    {"name": "Somerville Public Library", "url": "https://somervillepubliclibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_somerville_library, "default_category": "community"},
    {"name": "Underbones", "url": "https://redbones.com/events", "ua": UA_CHROME, "scraper": scrape_underbones, "default_category": "music"},
    {"name": "Cambridge Public Library", "url": "https://cambridgepl.libcal.com/rss.php?m=month&cid=7052", "ua": UA_CHROME, "scraper": scrape_cpl, "default_category": "community"},
    {"name": "Somerville Community Growing Center", "url": "https://www.thegrowingcenter.org/2026", "ua": UA_CHROME, "scraper": scrape_growing_center, "default_category": "outdoors"},
]

# Drop venues that require env vars we don't have set — keeps the fail banner clean.
VENUES = [v for v in _ALL_VENUES if not v.get("requires_env") or os.environ.get(v["requires_env"])]


# Static "useful links" — venues with no machine-readable calendar, but worth linking.
# Rendered in the "Useful links & ongoing" section.
STATIC_LINKS = [
    ("dance", "Boston Lindy Hop — swing dances list", "https://bostonlindyhop.com/events/swing-dancing-in-boston/"),
    ("dance", "Loretta's Last Call (line dancing, swing)", "https://lorettaslastcall.com/events/"),
    ("dance", "Boston Swing Central", "https://www.bostonswingcentral.org/"),
    ("dance", "Sabina Mezcalería (Sunday live salsa & brunch)", "https://www.instagram.com/sabinamezcaleria/"),
    ("dance", "Boston Outdoor Bachata & Salsa (BOBAS) — Esplanade pop-up announcements", "https://www.instagram.com/bobas.dance/"),
    ("dance", "Tango Society of Boston", "https://bostontango.org/"),
    ("theater", "American Repertory Theater", "https://americanrepertorytheater.org/shows-events/"),
    ("theater", "Huntington Theatre", "https://www.huntingtontheatre.org/season/"),
    ("art",     "Harvard Art Museums calendar", "https://harvardartmuseums.org/calendar"),
    ("comedy",  "Improv Asylum (North End)", "https://calendar.improvasylum.com/"),
    ("theater", "SpeakEasy Stage Company", "https://www.speakeasystage.com/season"),
    ("theater", "Lyric Stage Company", "https://www.lyricstage.com/whats-on/"),
    ("theater", "Company One Theatre", "https://companyone.org/season/"),
    ("theater", "Commonwealth Shakespeare", "https://commshakes.org/season/"),
    ("music",   "Trillium Brewing (events)", "https://trilliumbrewing.com/pages/event-calendar"),
    ("food",    "Sam Adams Boston Brewery (events)", "https://www.samadamsbrewery.com/events"),
    ("music",   "Long Live Beerworks / Roxbury", "https://www.longlivebeerworks.com"),
    ("food",    "Castle Island Brewing (events)", "https://www.castleislandbeer.com/public-events"),
    ("music",   "Boston Lyric Opera", "https://blo.org/events/"),
    ("music",   "Handel and Haydn Society", "https://handelandhaydn.org/concerts/"),
    ("music",   "Celebrity Series of Boston", "https://www.celebrityseries.org/live-performances/"),
    ("music",   "Berklee Performance Center", "https://www.berklee.edu/BPC"),
    ("clubbing","Middlesex Lounge (Cambridge)", "https://www.msexcambridge.com/calendar"),
    ("gaming",  "Balance Patch", "https://www.balancepatch.com/events"),
    ("music",   "Regattabar (jazz)", "https://www.regattabarjazz.com/"),
    ("theater", "Jacques' Cabaret (historic drag & cabaret)", "http://jacquescabaret.com/v3/"),
]


# Cheap-ticket / lottery / deal aggregators. Rendered in their own sidebar block.
DEAL_LINKS = [
    ("LuckySeat (Boston lotteries)", "https://www.luckyseat.com/"),
    ("BosTix — same-day half-price (ArtsBoston)", "https://bostix.org/categories/bostix-deals/"),
    ("TodayTix Boston (lotteries + discounts)", "https://www.todaytix.com/boston"),
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
    ("Sabina Mezcalería", "https://sabinamezcaleria.com/", "dance", [
        ("Sunday Live Salsa & Social Dancing (3–6 PM)", "https://www.instagram.com/sabinamezcaleria/", 6, 15, 0, "Free admission"),
    ]),
    ("The Druid", "https://www.druidpub.com/", "music", [
        ("Traditional Irish Music Session @ The Druid", "https://www.druidpub.com/", 2, 20, 0, "Free"),
        ("Traditional Irish Music Session @ The Druid", "https://www.druidpub.com/", 5, 16, 0, "Free"),
        ("Traditional Irish Music Brunch Session @ The Druid", "https://www.druidpub.com/", 6, 12, 0, "Free"),
    ]),
    ("Harvard University Farmers Market", "https://dining.harvard.edu/farmers-market", "food", [
        ("Harvard University Farmers Market", "https://dining.harvard.edu/farmers-market", 1, 11, 30),
    ]),
    ("Haymarket Boston", "https://www.haymarketboston.org/", "food", [
        ("Haymarket Open-Air Produce Market", "https://www.haymarketboston.org/", 4, 8, 0),
        ("Haymarket Open-Air Produce Market", "https://www.haymarketboston.org/", 5, 8, 0),
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


def _load_community_events():
    """Load community-submitted events from community_events.json."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_events.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, list) or not data:
            return []

        events = []
        for e in data:
            if not e.get("name") or not e.get("venue"):
                continue
            cat = e.get("category") or infer_category(e["name"], e["venue"])
            events.append({
                "name": str(e["name"]).strip(),
                "date": e.get("date"),
                "url": e.get("url") or "",
                "venue": str(e["venue"]).strip(),
                "price": e.get("price"),
                "category": cat,
                "_is_community": True,
                "_source_venue": "Community Submission",
                "address": e.get("address") or "",
            })
        if not events:
            return []
        return [{"venue": "Community Submissions", "url": "", "events": events, "error": None}]
    except Exception as err:
        print(f"Warning: could not load community events: {err}")
        return []



CATEGORY_KEYWORDS = [
    ("dance",     ["dance", "dancing", "dancers", "salsa", "bachata", "kizomba", "merengue", "tango", "swing dance", "swing dancing",
                   "lindy hop", "balboa", "blues dance", "contra dance", "zouk", "cha-cha", "cha cha",
                   "west coast swing", "ballroom dance", "ballroom dancing", "waltz", "milonga",
                   "dance social", "dance party", "dance night", "dance class", "dance lesson",
                   "dance workshop", "social dance", "havana club", "bachata room",
                   "line danc", "drag show", "drag night", "drag queen", "drag performance",
                   "go-go dancer", "pole danc", "ballet", "burlesque", "aerial danc", "aerial flow",
                   "capoeira", "folk danc", "dancehall", "kizkonpa", "kizonpa", "konpa", "floorwork"]),
    ("comedy",    ["comedy", "stand-up", "stand up", "improv", "open mic", "open-mic",
                   "roast", "sketch", "satirical", "variety show"]),
    ("theater",   ["theatre", "theater", "musical", "shakespeare", "broadway musical", "broadway show", "repertory", "play by", "play:",
                   "one woman show", "one man show", "solo show", "puppet", "burlesque show"]),
    ("books",     ["book club", "book launch", "author", "reading", "storytime", "poet", "poetry", "signing", "booksmith",
                   "literary", "literature", "book talk", "book fair", "writing workshop", "creative writing", "writers",
                   "in conversation", "conversation with", "storytelling", "novel", "memoir", "acotar", "keynote"]),
    ("gaming",    ["arcade", "mahjong", "chess", "trivia", "board game", "video game", "ttrpg", "d&d", "dungeons",
                   "tabletop", "escape room", "bingo", "pinball", "axe throw", "darts bar",
                   "one-shot rpg", "rpg night", "cornhole", "ping pong"]),
    ("clubbing",  ["dj ", " dj", "edm", "house music", "techno", "rave", "dubstep", "club night",
                   "nightclub", "guestlist", "guest list", "nightlife", "drum and bass", "drum & bass",
                   "industrial night", "goth night", "darkwave", "new wave night",
                   "party", "parties", "bash", "after party", "afterparty", "soiree", "rooftop", "halloween ball",
                   "costume party", "speakeasy", "piano bar", "dueling piano"]),
    ("music",     ["music", "musical", "musician", "tour", "concert", " band ", "live music", "music series", "music hall", "orchestra",
                   "symphony", "karaoke", "jazz", "hip hop", "rap", "bluegrass", "country music",
                   "country night", "folk music", "acoustic", "open mic", "irish session", "jam session",
                   "music session", "singer-songwriter", "singer songwriter", "soul music", "r&b",
                   "funk", "reggae", "punk", "metal", "indie rock", "album release", "ep release",
                   "record release", "live band", "live show", "live performance", "disco", "disko",
                   "jazz trio", "jazz quartet", " trio ", " quartet ", " quintet ", "anthem", "soundtrack",
                   "ukulele", "drumming", "cabaret", "blues feat", "live blues", "recital", "vocal", "instrumental",
                   "choral", "choir", "chorus", "ensemble", "chamber music", "singing", "bands", "brass"]),
    ("film",      ["screening", "film ", "cinema", "movie night", "movie", "movies", "brattle", "coolidge", "documentary", "baaff"]),
    ("sports",    ["bruins", "celtics", "red sox", "revolution", "marathon", "vs.", "match", "game ",
                   " 5k", "fun run", "road race", "10k", "half marathon", "cycling event",
                   "bike race", "rowing", "regatta", "hocr", "pickleball", "tennis", "volleyball",
                   "dodgeball", "archery", "parkour", "crossfit", "rock climbing", "kickboxing",
                   "dragon boat", "wrestling", "flag football", "golf", "axe throwing",
                   "indoor cycling", "spin class", "boot camp", "fitness class", "fitness", "workout", "gym",
                   "strength training", "pilates", "hyrox", "tailgate", "soccer", "basketball", "hockey"]),
    ("food",      ["tasting", "brewery", "brewing", "beer", "wine", "dinner", "brunch", "pop-up",
                   "oyster", "cocktail", "cocktails", "martini", "happy hour", "taproom", "bar night", "fondue",
                   "taqueria", "tavern", "sushi", "maki", "whiskey", "bourbon", "food truck", "menu",
                   "food tour", "culinary", "cooking class", "baking class", "noodle class", "bakery", "baking",
                   "pasta class", "wine tasting", "beer tasting", "restaurant", "bar crawl", "pub crawl",
                   "omakase", "ramen", "dumpling", "high tea", "afternoon tea", "tea room", "cookie", "pizza",
                   "chocolate tour", "coffee", "latte", "croissant", "knife skills", "chef", "bbq", "barbecue",
                   "cheese tasting", "sake", "mezcal", "gin tasting", "lounge"]),
    ("family",    ["kids", "children", "family", "toddler", "princess", "easter", "storytime",
                   "lego", "sensory-friendly", "sensory friendly", "baby", "youth", "trick or treat", "puppet",
                   "halloween", "spooky", "haunted"]),
    ("art",       ["art", "arts", "craft", "crafts", "makers", "exhibition", "gallery", "museum", "sculpture", "painting", "curator",
                   "art show", "art walk", "art class", "pottery", "ceramics", "printmaking",
                   "watercolor", "glass fusing", "mosaic", "screen print", "flower arrang",
                   "candle mak", "weaving", "embroid", "knitting", "collage", "mending", "clay",
                   "life drawing", "figure drawing", "illustration", "sketchbook", "drawing",
                   "sewing", "crochet", "stained glass", "jewelry", "bonsai", "kokedama",
                   "quilling", "resin ", "tufting", "leatherwork", "woodwork", "bazaar",
                   "pressed flower", "moss art", "stamp carving", "cyanotype", "photograph", "quilt",
                   "paper marbling", "junk journal", "macrame", "succulent plant",
                   "art studio", "open studio", "art market", "mural"]),
    ("outdoors",  ["hike", "hiking", "kayak", "canoe", "paddleboard", "camping", "trail",
                   "nature walk", "nature", "birding", "birdwatching", "yoga", "outdoor yoga", "sunrise yoga",
                   "sunset yoga", "outdoor fitness", "outdoor workout", "park run", "outdoor", "outdoors",
                   "memorial drive", "swan boat", "fitness on the", "fitness series", "garden",
                   "esplanade", "arboretum", "botanic garden", "conservation area", "apple picking", "pumpkin",
                   "farm", "orchard", "hayride", "cider", "harvest", "foliage", "corn maze", "cruise", "boat ride",
                   "beach", "nature explor"]),
    ("community", ["parade", "patriots day", "block party", "festival", "fest", " fair ", "fair!",
                   "gathering", "protest", "rally", "earth day", "earth week", "clean up",
                   "volunteer", "community", "civic", "town hall", "open house", "meetup",
                   "networking", "mixer", "panel discussion", "panel ", "lecture", "seminar", "workshop",
                   "thrift", "consignment", "swap meet", "tag sale", "farmers market", "expo", "summit",
                   "conference", "forum", "symposium", "gala", "benefit", "fundraiser", "charity",
                   "artisan market", "craft fair", "flea market", "vintage market", "market", "vintage",
                   "lgbtq", "queer ", "pride ", " trans ", "bisexual", "celebration", "showcase",
                   "meditation", "meditat", "speed dating", "singles", "porchfest", "tour",
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
    results.extend(_load_community_events())
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

