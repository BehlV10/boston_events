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
from urllib.parse import quote, urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup
from dateutil.rrule import rrulestr
from dateutil import parser


CACHE_SECONDS = 15 * 60
EASTERN = ZoneInfo("America/New_York")

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "venues")
os.makedirs(CACHE_DIR, exist_ok=True)

DEFAULT_VENUE_TTL = 3 * 3600    # 3 hours for standard venue feeds
FAST_VENUE_TTL = 1 * 3600       # 1 hour for high-turnover feeds (Ticketmaster, SeatGeek, Eventbrite, Do617, Boston Calendar, Boston Shows)
SLOW_VENUE_TTL = 12 * 3600      # 12 hours for evergreen/institutional feeds (Libraries, Museums, Bookstores, Parks)


def _get_venue_ttl(vname):
    low = (vname or "").lower()
    if any(k in low for k in ["ticketmaster", "seatgeek", "eventbrite", "do617", "boston calendar", "boston shows", "luma"]):
        return FAST_VENUE_TTL
    if any(k in low for k in ["library", "museum", "harvard", "mit", "books", "growing center", "esplanade", "arts council", "have to dance", "bida"]):
        return SLOW_VENUE_TTL
    return DEFAULT_VENUE_TTL


def _venue_cache_path(vname):
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", vname).strip("_").lower()
    return os.path.join(CACHE_DIR, f"{slug}.json")


def _load_venue_cache(vname, max_age=None):
    path = _venue_cache_path(vname)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if max_age is not None:
            age = time.time() - cached.get("ts", 0)
            if age > max_age:
                return None
        return cached
    except Exception:
        return None


def _save_venue_cache(vname, events, duration=0.0):
    path = _venue_cache_path(vname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "ts": time.time(),
                "venue": vname,
                "duration": duration,
                "events": events
            }, f, ensure_ascii=False)
    except Exception:
        pass


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


def is_placeholder_or_closed_event(title: str) -> bool:
    """Detect dummy calendar placeholders, cancellations, closures, and private events."""
    if not title:
        return True
    t = title.strip()

    # 1. Explicit cancellation or postponement at start of title
    if re.match(r"^\s*(\*{1,3}|\[|\()?\s*(canceled|cancelled|postponed)\b", t, re.I):
        return True

    # 2. "No event / no show / no music / no jam / no gypsy jazz"
    if re.search(r"\bno\s+([\w\s]+\s+)?(event|events|show|shows|live\s+music|music|performance|performances|band|bands|jam|jams|open\s+mic|dancing|dance|jazz)\b", t, re.I):
        # Guard against band/show names like "No Cover", "No Bad Chords", "No Static", "No Pressure", "No Friends"
        if not re.search(r"\bno\s+(cover|bad|pressure|static|relation|doubt|friends|more|guarantee|limit|worries|regrets|stopping)\b", t, re.I):
            return True

    # 3. Check calendar placeholder
    if re.search(r"\bcheck\s+(our\s+)?calendar\b", t, re.I):
        return True

    # 4. Standalone or holiday closures: "club closed", "closed for Thanksgiving", "closed for private event"
    if re.search(r"\b(closed|closing)\b.*(for\s+.*(holiday|thanksgiving|christmas|new\s+year|private)|private\s+(event|party))", t, re.I):
        return True
    if re.search(r"^\s*(club|venue|room|lounge|bar|taproom|brewery|kitchen)?\s*closed(\s+today|\s+tonight)?\s*$", t, re.I):
        return True
    if re.search(r"\bclosed\s+for\s+(the\s+)?holiday\b", t, re.I):
        return True

    # 5. Standalone Private event / Private party
    if re.search(r"^\s*(\*{1,3}|\[|\()?\s*private\s+(event|party|rental|function)\s*(\*{1,3}|\]|\))?\s*$", t, re.I):
        return True
    if re.search(r"\bclosed\s+for\s+(a\s+)?private\s+(event|party)\b", t, re.I):
        return True

    # 6. Generic single-word / short placeholder
    if t.lower() in ("tba", "tbd", "to be announced", "placeholder", "no title", "closed", "dark"):
        return True

    return False


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
    import subprocess
    try:
        soup = fetch_soup(url, ua)
    except Exception:
        res = subprocess.run(
            ["curl", "-sL", "-A", ua or UA_CHROME, "--max-time", "12", url],
            capture_output=True, text=True, check=False,
        )
        if not res.stdout or "application/ld+json" not in res.stdout:
            raise
        soup = BeautifulSoup(res.stdout, "html.parser")
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


def _bc_extract_url_from_p(p):
    a = p.find("a", href=True)
    if a and a.get("href"):
        href = a["href"].strip()
        if not href.startswith("#") and "thebostoncalendar.com" not in href:
            return href
    text = p.get_text(" ", strip=True)
    clean = re.sub(r"^(?:event\s*website|tickets?|registration|rsvp|more\s*info)\s*:?\s*", "", text, flags=re.I).strip()
    match = re.search(r"(https?://\S+|www\.\S+|[a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s<>\"']*)?)", clean)
    if match:
        url = match.group(1).rstrip(".,;)")
        if not url.startswith("http"):
            url = "https://" + url
        return url
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
        if _BC_EXTERNAL_RE.search(label) or any(k in label for k in ["ticket", "registration", "rsvp", "more info", "website"]):
            u = _bc_extract_url_from_p(p)
            if u and not ext_url:
                ext_url = u
        elif "admission" in label or "price" in label:
            price = _parse_bc_admission(p.get_text(" ", strip=True))

    if not ext_url:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http"):
                continue
            if any(k in href for k in ["thebostoncalendar.com", "facebook.com/sharer", "twitter.com", "instagram.com"]):
                continue
            text = a.get_text(" ", strip=True).lower()
            if any(k in text for k in ["buy ticket", "get ticket", "ticket", "event website", "official website", "more info", "register"]):
                ext_url = href
                break

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
        # Prioritize upcoming events in the immediate future for detail fetching
        # so users get direct primary source links for all near-term happenings
        def _bc_sort_key(e):
            d = e.get("date")
            return d if d else "9999"

        sorted_events = sorted(events, key=_bc_sort_key)
        top = sorted_events[:180]
        with ThreadPoolExecutor(max_workers=20) as ex:
            details = list(ex.map(lambda e: _bc_detail_info(e["url"], ua), top))
        for e, (ext, p) in zip(top, details):
            if ext:
                e["url"] = ext
            if p and not e.get("price"):
                e["price"] = p
    return events


_TUNEHATCH_VENUE_IDS = {
    "cantab": "968ae511-dae2-43a9-a916-15ae44ef47b8",
    "cantab_underground": "6126dd7d-0e07-4aad-92ef-3b52c0955bd4",
}


def scrape_tunehatch(url, ua):
    """TuneHatch venue shows API. Supports ?venue=slug or detects underground from URL."""
    m = re.search(r"[?&]venue=([^&]+)", url)
    if m:
        slug = m.group(1)
    elif "underground" in url.lower():
        slug = "cantab_underground"
    else:
        slug = "cantab"

    venue_id = _TUNEHATCH_VENUE_IDS.get(slug)
    if not venue_id:
        r = _SESSION.get(f"https://tunehatch.com/api/v1/entities/venue/{slug}", timeout=15,
                         headers={"User-Agent": ua, "Accept": "application/json"})
        r.raise_for_status()
        venue_id = (r.json() or {}).get("id")
        if not venue_id:
            return []

    now = datetime.now(timezone.utc)
    params = {
        "venue_id": venue_id,
        "limit": 300,
        "offset": 0,
        "published": "true",
        "starts_after": now.isoformat(),
    }
    r = _SESSION.get("https://tunehatch.com/api/v1/shows", params=params, timeout=15,
                     headers={"User-Agent": ua, "Accept": "application/json"})
    r.raise_for_status()
    payload = r.json() or {}
    shows = payload.get("data") or payload.get("shows") if isinstance(payload, dict) else payload
    shows = shows or []
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

        desc = ""
        about_html = s.get("about") or ""
        if about_html:
            desc = re.sub(r"<[^>]+>", " ", about_html).strip()
            desc = re.sub(r"\s+", " ", desc)

        v_name = s.get("venueName") or ("Cantab Underground" if slug == "cantab_underground" else "The Cantab Lounge")

        events.append({
            "name": name,
            "date": when.astimezone(timezone.utc).isoformat(),
            "url": f"https://tunehatch.com/e/shows/{slug_s}" if slug_s else None,
            "venue": v_name,
            "price": None,
            "description": desc or None,
            "category": "music",
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
    (Brookline Booksmith, Harvard Book Store, Trident Booksellers).
    Fetches current month and upcoming 2 months, filters past events, and for
    Harvard Book Store merges its Eventbrite organizer feed for prices & resilience.
    """
    import subprocess
    now_est = datetime.now(EASTERN)
    today_start = datetime(now_est.year, now_est.month, now_est.day, 0, 0, tzinfo=EASTERN)

    base_url = url.split("?")[0].rstrip("/")
    base_url = re.sub(r"/\d{4}/\d{1,2}$", "", base_url)
    page_urls = [base_url]
    y_cur, m_cur = now_est.year, now_est.month
    for _ in range(2):
        m_cur += 1
        if m_cur > 12:
            m_cur = 1
            y_cur += 1
        page_urls.append(f"{base_url}/{y_cur}/{m_cur:02d}")

    events = []
    seen = set()

    for page_url in page_urls:
        soup = None
        try:
            soup = fetch_soup(page_url, ua)
        except Exception:
            try:
                res = subprocess.run(
                    ["curl", "-sL", "-A", ua or UA_CURL, "--max-time", "12", page_url],
                    capture_output=True, text=True, check=False,
                )
                if res.stdout and "article" in res.stdout:
                    soup = BeautifulSoup(res.stdout, "html.parser")
            except Exception:
                soup = None
        if not soup:
            continue

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
            dt = None
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
                        year = now_est.year
                        dt = datetime.strptime(f"{mon.get_text(strip=True)} {day.get_text(strip=True)} {year} {hour:02d}:{minute:02d}", "%b %d %Y %H:%M").replace(tzinfo=EASTERN)
                        if dt < today_start:
                            dt = dt.replace(year=year + 1)
                        iso = dt.astimezone(timezone.utc).isoformat()
                    except ValueError:
                        pass

            if dt and dt < today_start:
                continue

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

            title_str = a.get_text(strip=True)
            if not venue_name and " at " in title_str:
                m_at = re.search(r"\bat\s+(?:the\s+)?(First Parish Church|Brattle Theatre|Cambridge Public Library|Harvard Science Center|Harvard Book Store)\b", title_str, re.I)
                if m_at and "harvard book" not in m_at.group(1).lower():
                    venue_name = m_at.group(1)

            if venue_name:
                v_low = venue_name.lower()
                u_low = url.lower()
                if "brookline" in u_low and "brookline booksmith" in v_low:
                    venue_name = None
                elif "harvard" in u_low and v_low in ("harvard book store", "harvard bookstore"):
                    venue_name = None
                elif "trident" in u_low and "trident" in v_low:
                    venue_name = None

            price = None
            body = art.select_one(".event-list__body")
            body_text = body.get_text(" ", strip=True) if body else ""
            art_text = art.get_text(" ", strip=True)
            p = re.search(r"(Free|FREE|\$\d+(?:\.\d{2})?(?:\s*[–-]\s*\$?\d+(?:\.\d{2})?)?)", body_text or art_text)
            if p:
                price = "Free" if p.group(1).lower() == "free" else p.group(1)

            key = (title_str.lower(), (iso or "")[:10])
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "name": title_str,
                "date": iso,
                "url": urljoin(url, href),
                "venue": venue_name,
                "price": price,
            })

    # For Harvard Book Store, also merge their official Eventbrite organizer feed
    if "harvard.com" in url.lower():
        try:
            eb_evs = scrape_eventbrite_org("https://www.eventbrite.com/o/harvard-book-store-74507930", UA_CHROME)
            by_date = {}
            for ev in events:
                if ev.get("date"):
                    by_date.setdefault(ev["date"][:10], []).append(ev)
            for eb in eb_evs:
                eb_date = (eb.get("date") or "")[:10]
                eb_name = (eb.get("name") or "").strip()
                if not eb_date or not eb_name:
                    continue
                matched = False
                for existing in by_date.get(eb_date, []):
                    if existing["name"].lower()[:18] in eb_name.lower() or eb_name.lower()[:18] in existing["name"].lower():
                        if not existing.get("price") and eb.get("price"):
                            existing["price"] = eb["price"]
                        matched = True
                        break
                if not matched:
                    v_eb = eb.get("venue")
                    if v_eb and "harvard book" not in v_eb.lower():
                        v_eb = f"Harvard Book Store ({v_eb})"
                    else:
                        v_eb = "Harvard Book Store"
                    events.append({
                        "name": eb_name,
                        "date": eb.get("date"),
                        "url": eb.get("url"),
                        "venue": v_eb,
                        "price": eb.get("price"),
                        "category": "books",
                    })
        except Exception:
            pass

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
        brand = (doc.get("event_brand") or "").lower()
        if "tanglewood" in brand:
            continue
        venues = doc.get("performance_venue") or []
        venue_display = venues[0].get("display_name", "Symphony Hall") if venues else "Symphony Hall"
        if any(w in venue_display.lower() for w in ["linde center", "tanglewood", "ozawa", "koussevitzky", "lenox"]):
            continue
        link = doc.get("event_link") or ""
        events.append({
            "name": doc.get("title"),
            "date": datetime.fromtimestamp(doc["performance_date"], tz=timezone.utc).isoformat(),
            "url": f"https://www.bso.org{link}" if link else "https://www.bso.org/events",
            "venue": venue_display,
            "price": None,
            "category": "music",
            "genre": "classical",
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
    """Middle East Cambridge — TicketWeb plugin embeds event list as static HTML.
    
    Scrapes upcoming shows across all Middle East rooms (Downstairs, Upstairs,
    Corner/Bakery, ZuZu, Sonia) across up to 5 pages with precise showtimes and pricing.
    """
    events = []
    seen_keys = set()
    now = datetime.now(EASTERN)
    year = now.year
    base_url = url.rstrip("/")

    for page in range(1, 6):
        purl = f"{base_url}/page/{page}/" if page > 1 else url
        try:
            soup = fetch_soup(purl, ua)
        except Exception:
            break
        sections = soup.select(".tw-section")
        if not sections:
            break

        for section in sections:
            link = section.find("a", href=lambda h: h and "ticketweb.com" in h)
            if not link:
                link = section.select_one("a.tw-buy-tix-btn")
            event_url = link.get("href", url) if link else url
            label = link.get("aria-label", "") if link else ""

            name_el = section.select_one(".tw-name")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name and label:
                m = re.match(r"Event Image Link-\s*(.*?)\s*\|", label)
                name = m.group(1).strip() if m else ""
            if not name:
                name = section.get_text(" ", strip=True)[:80]
            if not name:
                continue

            date_el = section.select_one(".tw-event-date")
            if not date_el:
                continue
            raw_date = date_el.get_text(strip=True)
            try:
                month, day = (int(x) for x in raw_date.split("."))
            except (ValueError, AttributeError):
                continue

            # Parse exact showtime
            time_el = section.select_one(".tw-event-time")
            raw_time = time_el.get_text(" ", strip=True) if time_el else ""
            if not raw_time:
                raw_time = label

            hour, minute = 19, 0
            tm = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)", raw_time, re.I)
            if tm:
                h = int(tm.group(1))
                m_min = int(tm.group(2))
                mer = tm.group(3).lower()
                if mer == "pm" and h != 12:
                    h += 12
                elif mer == "am" and h == 12:
                    h = 0
                hour, minute = h, m_min
            else:
                tm_hr = re.search(r"(\d{1,2})\s*(am|pm)", raw_time, re.I)
                if tm_hr:
                    h = int(tm_hr.group(1))
                    mer = tm_hr.group(2).lower()
                    if mer == "pm" and h != 12:
                        h += 12
                    elif mer == "am" and h == 12:
                        h = 0
                    hour, minute = h, 0

            try:
                candidate = datetime(year, month, day, hour, minute, tzinfo=EASTERN)
                if candidate.date() < now.date() - timedelta(days=2):
                    candidate = datetime(year + 1, month, day, hour, minute, tzinfo=EASTERN)
            except (ValueError, OverflowError):
                continue

            venue_el = section.select_one(".tw-venue-name")
            v_name = "Middle East"
            if venue_el:
                clean_v = re.sub(r"^@\s*", "", venue_el.get_text(strip=True)).strip()
                if clean_v:
                    v_name = clean_v

            price = None
            price_el = section.select_one(".tw-price")
            if price_el:
                p_text = price_el.get_text(strip=True)
                if p_text:
                    price = p_text

            dedup_key = (name.lower(), candidate.isoformat(), v_name.lower())
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            events.append({
                "name": name,
                "date": candidate.astimezone(timezone.utc).isoformat(),
                "url": event_url,
                "venue": v_name,
                "price": price,
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
        bio_raw = e.get("bio") or e.get("description") or ""
        bio_clean = re.sub(r"<[^>]+>", " ", bio_raw)
        bio_clean = re.sub(r"\s+", " ", bio_clean).strip()
        desc = bio_clean[:300] if bio_clean else None
        genre = infer_music_genre(title, vname, description=bio_clean)

        events.append({
            "name": title,
            "date": iso_str,
            "url": ticket_url,
            "venue": vname,
            "price": ticketing.get("priceRange"),
            "category": "music",
            "genre": genre,
            "description": desc,
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
    tm_url = "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZAJd6FA,KovZpZA1EEJA&size=100&sort=date,asc"
    tm_events = scrape_ticketmaster_discovery(tm_url, ua)
    if tm_events:
        for e in tm_events:
            if not e.get("category"):
                e["category"] = infer_category(e.get("name"), e.get("venue"), default="theater")
        return tm_events

    try:
        soup = fetch_soup(url, ua)
    except Exception:
        return []
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


def scrape_luma(url, ua):
    """Scrape curated Boston tech, AI, startup, and community events from Luma."""
    api_url = "https://api.lu.ma/discover/get-paginated-events?discover_place_api_id=discplace-VWeZ1zUvnawYHMj"
    headers = {
        "User-Agent": ua,
        "Accept": "application/json",
    }
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    cursor = None

    for _ in range(5):
        req_url = api_url
        if cursor:
            req_url += f"&pagination_cursor={cursor}"
        try:
            resp = _SESSION.get(req_url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break

        entries = data.get("entries") or []
        for entry in entries:
            ev = entry.get("event") or {}
            name = (ev.get("name") or "").strip()
            if not name or is_placeholder_or_closed_event(name):
                continue

            start_at = ev.get("start_at")
            if not start_at:
                continue
            try:
                dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
                if dt.astimezone(timezone.utc) < now:
                    continue
                iso_date = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                continue

            slug = ev.get("url") or ""
            link = slug if slug.startswith("http") else f"https://lu.ma/{slug}"

            key = (name.lower(), iso_date[:10])
            if key in seen:
                continue
            seen.add(key)

            geo = ev.get("geo_address_info") or {}
            cal = entry.get("calendar") or {}

            if geo.get("mode") == "shown" and (geo.get("address") or geo.get("short_address")):
                addr = geo.get("address") or geo.get("short_address")
                city = geo.get("city") or "Boston"
                venue = addr if city.lower() in addr.lower() else f"{addr}, {city}"
            elif geo.get("sublocality") or geo.get("city"):
                subloc = geo.get("sublocality") or geo.get("city")
                venue = f"{subloc} (RSVP for address)"
            elif cal.get("name") and cal.get("name").lower() != "personal":
                venue = cal.get("name")
            else:
                venue = "Boston"

            coord = ev.get("coordinate") or geo.get("place_coordinate") or {}
            lat = coord.get("latitude")
            lng = coord.get("longitude")
            address = geo.get("full_address") or geo.get("address") or ""
            neighborhood = geo.get("sublocality") or ""

            t_info = entry.get("ticket_info") or {}
            price = None
            if t_info.get("is_free"):
                price = "Free"
            elif t_info.get("price"):
                cents = t_info["price"].get("cents")
                if cents == 0:
                    price = "Free"
                elif cents is not None:
                    price = f"${cents / 100:.2f}".rstrip("0").rstrip(".")

            hosts = [h.get("name") for h in (entry.get("hosts") or []) if h.get("name")]
            cal_desc = cal.get("description_short")
            desc_parts = []
            if hosts:
                h_str = ", ".join(hosts[:3])
                desc_parts.append(f"Hosted by {h_str}")
            if cal_desc:
                desc_parts.append(cal_desc)
            desc = " • ".join(desc_parts)[:250] if desc_parts else None

            cat = infer_category(name, venue, default="community")

            ev_dict = {
                "name": name,
                "date": iso_date,
                "url": link,
                "venue": venue,
                "price": price,
                "category": cat,
                "description": desc,
            }
            if lat is not None and lng is not None:
                ev_dict["lat"] = lat
                ev_dict["lng"] = lng
            if address:
                ev_dict["address"] = address
            if neighborhood:
                ev_dict["neighborhood"] = neighborhood

            events.append(ev_dict)

        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

    return events


def scrape_porter_square_books(url, ua):
    """Porter Square Books embeds its full FullCalendar event list in the
    Drupal `drupalSettings` JSON blob on the calendar page. We fetch both
    the current month and the upcoming months so events do not truncate at month-end."""
    import subprocess
    now = datetime.now(timezone.utc)
    base_url = url.split("?")[0].rstrip("/")
    base_url = re.sub(r"/\d{4}/\d{1,2}$", "", base_url)

    urls = [base_url]
    y, m = now.year, now.month
    for _ in range(2):
        m += 1
        if m > 12:
            m = 1
            y += 1
        urls.append(f"{base_url}/{y}/{m:02d}")

    events = []
    seen = set()
    for target_url in urls:
        html = None
        try:
            resp = _SESSION.get(target_url, headers={"User-Agent": ua}, timeout=15)
            if resp.status_code == 200:
                html = resp.text
        except Exception:
            pass

        if not html:
            try:
                html = subprocess.check_output(
                    ["curl", "-s", "-L", target_url], timeout=15
                ).decode("utf-8", errors="ignore")
            except Exception:
                continue

        m_tag = re.search(
            r'data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>',
            html, re.S,
        )
        if not m_tag:
            continue
        try:
            settings = json.loads(m_tag.group(1))
        except Exception:
            continue
        fcv = (settings.get("fullCalendarView") or [{}])[0]
        calendar_opts = fcv.get("calendar_options") or {}
        if isinstance(calendar_opts, str):
            try:
                calendar_opts = json.loads(calendar_opts)
            except Exception:
                calendar_opts = {}
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
            ev_url = urljoin(target_url, href) if href else target_url
            key = (name.lower(), when.isoformat())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": name,
                "date": when.astimezone(timezone.utc).isoformat(),
                "url": ev_url,
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
    """Scrapes events from Ticketmaster venue page using Discovery API or __NEXT_DATA__ eventsJsonLD (e.g. Mémoire Boston)."""
    if "memoire" in (url or "").lower() or "9388" in (url or ""):
        tm_evs = scrape_ticketmaster_discovery(
            "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZ917AJPk&size=100&sort=date,asc",
            ua,
        )
        if tm_evs:
            for e in tm_evs:
                e["venue"] = "Mémoire Boston"
                e["category"] = "clubbing"
            return tm_evs

    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15)
        resp.raise_for_status()
    except Exception:
        return []
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

                genre = None
                if cat == "music":
                    native_g = None
                    for p in ev.get("performers", []):
                        for g_obj in p.get("genres", []):
                            g_str = g_obj.get("name") if isinstance(g_obj, dict) else str(g_obj)
                            native_g = map_native_genre(g_str)
                            if native_g:
                                break
                        if native_g:
                            break
                    genre = infer_music_genre(ev.get("title") or ev.get("short_title"), venue, native_genre=native_g)

                events.append({
                    "name": ev.get("title") or ev.get("short_title"),
                    "date": iso,
                    "url": ev.get("url"),
                    "venue": venue,
                    "price": price,
                    "category": cat,
                    "genre": genre,
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
        if not name or is_placeholder_or_closed_event(name):
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
    evs = []
    try:
        evs.extend(scrape_eventbrite_search(url, ua))
    except Exception:
        pass
    for org_url in [
        "https://www.eventbrite.com/o/the-vampire-leslut-65543514293",
        "https://www.eventbrite.com/o/patty-bourree-53423796003",
        "https://www.eventbrite.com/o/graveyard-brat-121779050661",
    ]:
        try:
            evs.extend(scrape_eventbrite_org(org_url, ua))
        except Exception:
            pass
    results = []
    seen = set()
    for e in evs:
        v_low = (e.get("venue") or "").lower()
        n_low = (e.get("name") or "").lower()
        if "jacque" in v_low or "jacque" in n_low or "79 broadway" in v_low:
            key = (n_low, (e.get("date") or "")[:10])
            if key in seen:
                continue
            seen.add(key)
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

                dt = datetime(year, month_idx, day_num, hour, minute, tzinfo=EASTERN)

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
                            "date": dt.astimezone(timezone.utc).isoformat(),
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
    evs = []
    try:
        evs.extend(scrape_eventbrite_org("https://www.eventbrite.com/o/duck-duck-goofs-39699614543", ua))
    except Exception:
        pass
    try:
        evs.extend(scrape_eventbrite_search(url, ua))
    except Exception:
        pass
    results = []
    seen = set()
    for e in evs:
        v_low = (e.get("venue") or "").lower()
        n_low = (e.get("name") or "").lower()
        if "goof" in v_low or "goof" in n_low or "duck-duck-goofs" in (e.get("url") or ""):
            key = (n_low, (e.get("date") or "")[:10])
            if key in seen:
                continue
            seen.add(key)
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
                iso_dt = datetime(y, m, d, hour, minute, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
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
            if not title_el:
                continue
            a = title_el.find("a") or parent.find("a")
            if a and a.find("em"):
                em_text = a.find("em").get_text(strip=True)
                main_text = "".join(c for c in a.contents if isinstance(c, str)).strip()
                title = f"{main_text} ({em_text})" if main_text and em_text else a.get_text(" ", strip=True)
            else:
                title = title_el.get_text(" ", strip=True)
            if not title:
                continue
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
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": link,
                "venue": "Club Passim",
                "price": price,
                "category": "music",
            })
    return out


def scrape_danis_queer_bar(url, ua):
    """Dani's Queer Bar in Back Bay — Boston's premier lesbian & queer bar.

    Combines ticketed special events via Eventbrite with their regular weekly programming:
    Drag Bingo (Tuesdays), Front2Back (Wednesdays), No Cover Karaoke (Thursdays),
    Friday Queer Dance Party, Saturday & Sunday Drag Brunches, and Weekend Dance Parties.
    """
    results = []
    seen = set()

    # 1. Ticketed special events from Eventbrite
    try:
        eb_evs = scrape_eventbrite_search(url, ua)
        for e in eb_evs:
            v_low = (e.get("venue") or "").lower()
            n_low = (e.get("name") or "").lower()
            if "dani" in v_low or "dani" in n_low or "909 boylston" in v_low:
                e["venue"] = "Dani's Queer Bar"
                if any(w in n_low for w in ["comedy", "quiz", "trivia"]):
                    e["category"] = "comedy"
                elif any(w in n_low for w in ["drag", "brunch", "cabaret"]):
                    e["category"] = "theater"
                else:
                    e["category"] = "clubbing"
                results.append(e)
                if e.get("date"):
                    seen.add((e.get("date")[:10], e["name"].lower()))
    except Exception:
        pass

    # 2. Weekly recurring programming for the next 4 weeks
    today = datetime.now(EASTERN).date()
    recurring_specs = [
        (1, 20, 0, "No Cover Drag Bingo with Wilhelmina", "Free", "comedy", "https://danisqueerbar.com/"),
        (2, 19, 0, "Front2Back Listening Party", "Free", "music", "https://danisqueerbar.com/"),
        (3, 22, 0, "No Cover Karaoke w/ Miss Jade Rock", "Free", "music", "https://danisqueerbar.com/"),
        (4, 22, 0, "Friday Night Queer Dance Party", "Free", "clubbing", "https://danisqueerbar.com/"),
        (5, 11, 30, "Dani's Drag Brunch w/ Shakaren", "Free", "theater", "https://danisqueerbar.com/"),
        (5, 22, 0, "Weekend Queer Dance Party", "Free", "clubbing", "https://danisqueerbar.com/"),
        (6, 11, 30, "Sunday Drag Brunch", "Free", "theater", "https://danisqueerbar.com/"),
    ]

    for day_offset in range(28):
        cur_day = today + timedelta(days=day_offset)
        dow = cur_day.weekday()
        for r_dow, r_hr, r_min, r_name, r_price, r_cat, r_url in recurring_specs:
            if dow == r_dow:
                dt_obj = datetime(cur_day.year, cur_day.month, cur_day.day, r_hr, r_min, tzinfo=EASTERN)
                results.append({
                    "name": r_name,
                    "date": dt_obj.astimezone(timezone.utc).isoformat(),
                    "url": r_url,
                    "venue": "Dani's Queer Bar",
                    "price": r_price,
                    "category": r_cat,
                })

    return results


def scrape_club_cafe(url, ua):
    """Club Café in South End — historic LGBT nightlife, cabaret, piano bar & dance club."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    for a in soup.find_all("article", class_=lambda c: c and "mec-event-article" in c):
        title_el = a.find(class_="mec-event-title")
        if not title_el:
            continue
        a_link = title_el.find("a")
        name = html.unescape(a_link.get_text(strip=True) if a_link else title_el.get_text(strip=True))
        href = a_link["href"] if a_link and a_link.has_attr("href") else ""

        m_occ = re.search(r"occurrence=(\d{4}-\d{2}-\d{2})", href)
        date_str = m_occ.group(1) if m_occ else None
        if not date_str:
            continue

        time_el = a.find(class_="mec-event-time")
        time_str = time_el.get_text(" ", strip=True) if time_el else ""
        m_time = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))", time_str, re.I)
        t_part = m_time.group(1).lower().replace(" ", "") if m_time else None

        if t_part:
            try:
                parsed_dt = datetime.strptime(f"{date_str} {t_part}", "%Y-%m-%d %I:%M%p")
                dt = parsed_dt.replace(tzinfo=EASTERN).astimezone(timezone.utc)
                dt_iso = dt.isoformat()
            except Exception:
                dt_iso = f"{date_str}T20:00:00-04:00"
        else:
            dt_iso = f"{date_str}T20:00:00-04:00"

        loc_el = a.find(class_="mec-event-loc-place")
        loc = loc_el.get_text(strip=True) if loc_el else "Club Café"
        venue_name = f"Club Café ({loc})" if loc and loc != "Club Café Boston" else "Club Café"

        low = name.lower()
        if any(w in low for w in ["drag", "bingo"]):
            cat = "comedy" if "bingo" in low else "theater"
        elif any(w in low for w in ["tea dance", "dance", "dj", "party", "fridays", "maxxing", "house party"]):
            cat = "clubbing"
        elif any(w in low for w in ["cabaret", "broadway", "tribute", "burlesque"]):
            cat = "theater"
        else:
            cat = "music"

        price = "Free" if any(w in low for w in ["free", "no cover", "tea dance", "karaoke", "trivia", "drag bingo"]) else None

        key = (name, dt_iso)
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": name,
            "date": dt_iso,
            "url": href,
            "venue": venue_name,
            "price": price,
            "category": cat,
        })
    return events


def scrape_boston_queer_nightlife(url, ua):
    """Boston LGBTQ+ Nightlife & Parties — pop-up queer dance parties, tea dances, drag and circuit events."""
    evs = scrape_eventbrite_search(url, ua)
    results = []
    seen = set()
    for e in evs:
        name = e.get("name") or ""
        low = name.lower()
        v_low = (e.get("venue") or "").lower()
        if not e.get("date") or not name:
            continue
        # Avoid duplicating dedicated venues
        if "dani" in v_low or "club caf" in v_low or "jacque" in v_low:
            continue
        if any(w in low or w in v_low for w in ["queer", "lgbt", "gay", "trans ", "sapphic", "lesbian", "drag", "pride", "tea dance", "sinthetic"]):
            if any(w in low for w in ["drag", "cabaret", "burlesque"]):
                e["category"] = "theater"
            elif any(w in low for w in ["comedy", "quiz", "trivia"]):
                e["category"] = "comedy"
            else:
                e["category"] = "clubbing"
            key = (name, e["date"][:10])
            if key not in seen:
                seen.add(key)
                results.append(e)
    return results


def scrape_feral(url, ua):
    """FERAL (@feral.party) — Boston's iconic queer & trans dance party and rager series."""
    results = []
    seen = set()

    # 1. Official Eventbrite organizer profile (__NEXT_DATA__)
    try:
        soup = fetch_soup("https://www.eventbrite.com/o/feral-events-71015854393", ua)
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag:
            data = json.loads(tag.string)
            evs = data.get("props", {}).get("pageProps", {}).get("upcomingEvents", [])
            for e in evs:
                name = (e.get("name") or "").strip()
                if not name or e.get("is_cancelled"):
                    continue
                display_name = name if "feral" in name.lower() else f"FERAL: {name}"
                s_date = e.get("start_date")
                s_time = e.get("start_time") or "22:00:00"
                if not s_date:
                    continue
                try:
                    dt = datetime.strptime(f"{s_date} {s_time}", "%Y-%m-%d %H:%M:%S")
                    dt_iso = dt.replace(tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
                except Exception:
                    dt_iso = f"{s_date}T22:00:00-04:00"
                pv = e.get("primary_venue") or {}
                vname = pv.get("name") or "Legacy Boston"
                if "legacy" in vname.lower():
                    vname = "Legacy Boston"
                tix = e.get("ticket_availability") or {}
                if tix.get("is_free"):
                    price = "Free"
                else:
                    min_tix = tix.get("minimum_ticket_price") or {}
                    val = min_tix.get("major_value")
                    price = f"${int(float(val))}" if val else "$25"
                key = (name.lower(), s_date)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "name": display_name,
                        "date": dt_iso,
                        "url": e.get("url") or url,
                        "venue": vname,
                        "price": price,
                        "category": "clubbing",
                    })
    except Exception:
        pass

    # 2. Eventbrite discovery search for any other FERAL events
    try:
        search_evs = scrape_eventbrite_search("https://www.eventbrite.com/d/ma--boston/feral/", ua)
        for e in search_evs:
            n_low = (e.get("name") or "").lower()
            if "feral" in n_low or "tara dikhof" in n_low or "sinthetic" in n_low:
                if any(w in n_low for w in ["5k", "10k", "marathon", "running", "race"]):
                    continue
                key = (e["name"].lower(), (e.get("date") or "")[:10])
                if key not in seen and e.get("date"):
                    seen.add(key)
                    e["category"] = "clubbing"
                    if "legacy" in (e.get("venue") or "").lower():
                        e["venue"] = "Legacy Boston"
                    results.append(e)
    except Exception:
        pass

    return results


def scrape_warehouse_xi(url, ua):
    """Warehouse XI (11 Sanborn Ct, Union Square, Somerville).

    Direct primary scraper: pulls upcoming concerts & live shows straight from
    in-house promoter Get To The Gig Boston (with Eventim checkout links) and
    community forums / arts gatherings from Eventbrite.
    """
    events = []
    now = datetime.now(timezone.utc)

    # 1. Shows directly from in-house promoter Get To The Gig Boston
    try:
        g2g_url = "https://core.service.elfsight.com/p/boot/?page=https%3A%2F%2Fget2thegigbos.com%2Fhome&w=4e09de31-e966-4802-8dbe-53cecc8533ca"
        resp = _SESSION.get(g2g_url, headers={"User-Agent": ua}, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        widgets = data.get("data", {}).get("widgets", {})
        if widgets:
            w = list(widgets.values())[0]
            for ev in w.get("data", {}).get("settings", {}).get("events", []):
                # 'loew1wfv' is Get To The Gig's venue ID for Warehouse XI
                if "loew1wfv" in ev.get("location", []):
                    name = ev.get("name")
                    start = ev.get("start", {})
                    s_date = start.get("date")
                    s_time = start.get("time") or "20:00"
                    if not name or not s_date:
                        continue
                    try:
                        dt = datetime.strptime(f"{s_date} {s_time}", "%Y-%m-%d %H:%M").replace(tzinfo=EASTERN)
                        if dt.astimezone(timezone.utc) < now - timedelta(days=1):
                            continue
                        iso = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        continue

                    actions = ev.get("actions", [])
                    ticket_url = actions[0].get("link", {}).get("value") if actions else "https://www.wxi.space"

                    events.append({
                        "name": name,
                        "date": iso,
                        "url": ticket_url,
                        "venue": "Warehouse XI",
                        "price": None,
                        "category": "music",
                    })
    except Exception:
        pass

    # 2. Eventbrite for community / forum events
    try:
        eb_url = "https://www.eventbrite.com/d/ma--somerville/warehouse-xi/"
        eb_soup = fetch_soup(eb_url, ua)
        for s in eb_soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(s.string)
                if isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        it = item.get("item", {})
                        loc = it.get("location", {})
                        loc_name = loc.get("name", "").lower()
                        addr = str(loc.get("address", "")).lower()
                        if "warehouse xi" in loc_name or "sanborn" in addr:
                            ev_name = it.get("name")
                            ev_start = it.get("startDate")
                            ev_url = it.get("url")
                            if ev_name and ev_start:
                                events.append({
                                    "name": ev_name,
                                    "date": ev_start if "T" in ev_start else f"{ev_start}T19:00:00-04:00",
                                    "url": ev_url or "https://www.wxi.space",
                                    "venue": "Warehouse XI",
                                    "price": None,
                                    "category": "community",
                                })
            except Exception:
                pass
    except Exception:
        pass

    return events


def scrape_downtown_boston(url, ua):
    """Downtown Boston BID (downtownboston.org).

    Fetches public calendar via WordPress Tribe Events REST API for Downtown Crossing,
    Financial District, and Theater District happenings.
    """
    events = []
    today = datetime.now(EASTERN).date().isoformat()
    api_url = f"https://www.downtownboston.org/wp-json/tribe/events/v1/events?start_date={today}&per_page=50"
    headers = {"User-Agent": ua}

    try:
        resp = _SESSION.get(api_url, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        for ev in data.get("events", []):
            raw_title = ev.get("title", "")
            title = BeautifulSoup(raw_title, "html.parser").get_text(strip=True)
            if not title:
                continue

            start_str = ev.get("start_date")
            if not start_str:
                continue
            try:
                dt = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
                iso = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                continue

            event_url = ev.get("website") or ev.get("url") or url
            venue_obj = ev.get("venue") or {}
            venue_name = venue_obj.get("venue") or "Downtown Boston"

            cost = ev.get("cost")
            price = cost.strip() if cost else None

            events.append({
                "name": title,
                "date": iso,
                "url": event_url,
                "venue": f"Downtown Boston - {venue_name}" if "downtown" not in venue_name.lower() else venue_name,
                "price": price,
                "category": infer_category(title, venue_name, default="community"),
            })
    except Exception:
        pass

    return events


def scrape_symphony_hall(url, ua):
    """Boston Symphony Orchestra, Boston Pops, and Symphony Hall concerts via official Typesense API."""
    now = int(time.time())
    api_url = "https://go8f04wi19tuvlyrp-1.a1.typesense.net/collections/performances/documents/search"
    params = {
        "q": "*",
        "query_by": "title",
        "sort_by": "performance_date:asc",
        "filter_by": f"show_in_cal:true && performance_date:>={now}",
        "per_page": 250,
    }
    headers = {
        "X-TYPESENSE-API-KEY": "qoWHCTjesGfIaxdXbw9vOgod1VToEXNI",
        "User-Agent": ua or UA_CHROME,
    }
    try:
        resp = _SESSION.get(api_url, params=params, headers=headers, timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    events = []
    seen = set()
    for hit in data.get("hits", []):
        doc = hit.get("document", {})
        brand = (doc.get("event_brand") or "").lower()
        if "tanglewood" in brand:
            continue
        title = (doc.get("title") or "").strip()
        ts = doc.get("performance_date")
        if not title or not ts:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        link = doc.get("performance_link") or doc.get("event_link") or doc.get("ticket_link") or url
        if link and link.startswith("/"):
            link = f"https://www.bso.org{link}"
        key = (title.lower(), dt.isoformat())
        if key in seen:
            continue
        seen.add(key)
        venues = doc.get("performance_venue", [])
        vname = venues[0].get("name", "Symphony Hall") if venues else "Symphony Hall"
        if any(w in vname.lower() for w in ["linde center", "tanglewood", "ozawa", "koussevitzky", "lenox"]):
            continue
        desc = doc.get("subhead") or re.sub(r"<[^>]+>", " ", doc.get("excerpt") or "").strip()
        events.append({
            "name": title,
            "date": dt.isoformat(),
            "url": link,
            "venue": vname,
            "price": None,
            "description": desc[:300] if desc else None,
            "category": "music",
            "genre": "classical",
        })
    return events


def scrape_berklee(url, ua):
    """Berklee College of Music and Boston Conservatory concerts, recitals, and masterclasses."""
    base_url = "https://www.berklee.edu"
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    for page in range(4):
        page_url = f"{url}?page={page}" if page > 0 else url
        soup = fetch_soup(page_url, ua)
        if not soup:
            break

        cards = soup.select(".event.teaser")
        if not cards:
            break

        for card in cards:
            title_el = card.select_one(".title") or card.find(["h3", "h2"])
            if not title_el:
                continue
            name = re.sub(r"\s+", " ", title_el.get_text(strip=True))
            if not name:
                continue

            a = card.find("a", href=True)
            link = urljoin(base_url, a["href"]) if a else page_url
            if link in seen:
                continue

            date_el = card.select_one(".field--name-field-event-instance-date") or card.select_one(".daterange") or card.select_one(".date")
            if not date_el:
                continue
            date_raw = date_el.get_text(strip=True)

            dm = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\s*/\s*(\d{1,2}):(\d{2})\s*(a\.m\.|p\.m\.|am|pm)", date_raw, re.I)
            if not dm:
                continue

            m_str, d_str, y_str, h_str, mn_str, ampm = dm.groups()
            try:
                month_num = datetime.strptime(m_str[:3], "%b").month
                h = int(h_str)
                mn = int(mn_str)
                if "p" in ampm.lower() and h < 12:
                    h += 12
                elif "a" in ampm.lower() and h == 12:
                    h = 0
                dt = datetime(int(y_str), month_num, int(d_str), h, mn, tzinfo=EASTERN)
                if (now - dt).total_seconds() > 24 * 3600:
                    continue
            except Exception:
                continue

            v_el = card.select_one(".field--name-field-event-venue-title")
            vname = v_el.get_text(strip=True) if v_el else "Berklee Performance Center"

            seen.add(link)
            events.append({
                "name": name,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": link,
                "venue": vname,
                "price": "Free" if "free" in card.get_text().lower() else None,
                "category": "music",
            })

    return events


def scrape_the_bebop(url, ua):
    """The Bebop — live music bar next to Berklee on Boylston St (jazz, blues, folk, funk)."""
    target_url = "https://www.thebebopboston.com/new-events?format=json"
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    events = []
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=90)
    seen = set()
    for item in data.get("items", []):
        title = re.sub(r"\s+", " ", (item.get("title") or "").strip())
        if not title:
            continue
        ms = item.get("startDate")
        if not ms:
            continue
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        if dt < now - timedelta(days=1) or dt > cutoff:
            continue
        full_url = item.get("fullUrl")
        ev_url = f"https://thebebopboston.com{full_url}" if full_url else "https://thebebopboston.com/new-events"
        key = (title.lower(), dt.isoformat())
        if key in seen:
            continue
        seen.add(key)
        desc = re.sub(r"<[^>]+>", " ", item.get("excerpt") or item.get("body") or "").strip()
        events.append({
            "name": title,
            "date": dt.isoformat(),
            "url": ev_url,
            "venue": "The Bebop",
            "price": "Free",
            "description": desc[:300] if desc else None,
            "category": "music",
        })
    return events


def scrape_ticketmaster_discovery(url, ua):
    """Scrape official events from Ticketmaster Discovery API.

    Supports venueId queries for major Boston music halls and venues
    (Paradise Rock Club, Brighton Music Hall, MGM Music Hall, House of Blues,
    Orpheum Theatre, Leader Bank Pavilion, Chevalier Theatre).
    """
    api_url = url
    if "apikey=" not in api_url:
        sep = "&" if "?" in api_url else "?"
        api_url = f"{api_url}{sep}apikey=oo1qd0wzLe7WJpm61ALQuUCTMXGK7U5z"

    try:
        resp = _SESSION.get(
            api_url,
            headers={"User-Agent": ua or UA_CHROME, "Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    raw_events = data.get("_embedded", {}).get("events", [])
    now = datetime.now(EASTERN)
    events = []
    seen = set()

    for ev in raw_events:
        name = (ev.get("name") or "").strip()
        if not name or is_placeholder_or_closed_event(name):
            continue

        start_date = ev.get("dates", {}).get("start", {}).get("localDate")
        start_time = ev.get("dates", {}).get("start", {}).get("localTime") or "19:00:00"
        if not start_date:
            continue
        try:
            dt = datetime.fromisoformat(f"{start_date}T{start_time}").replace(tzinfo=EASTERN)
        except Exception:
            continue

        if (now - dt).total_seconds() > 24 * 3600:
            continue

        link = ev.get("url") or ""
        v_embedded = (ev.get("_embedded", {}).get("venues") or [{}])[0]
        vname = v_embedded.get("name")

        price = None
        price_ranges = ev.get("priceRanges", [])
        if price_ranges:
            p_min = price_ranges[0].get("min")
            p_max = price_ranges[0].get("max")
            if p_min is not None and p_max is not None:
                if p_min == p_max:
                    price = f"${int(p_min)}" if p_min == int(p_min) else f"${p_min:.2f}"
                else:
                    price = f"${int(p_min)}-${int(p_max)}"
            elif p_min is not None:
                price = f"From ${int(p_min)}"

        classifications = ev.get("classifications") or []
        g_name = ""
        sg_name = ""
        if classifications:
            g_name = classifications[0].get("genre", {}).get("name") or ""
            sg_name = classifications[0].get("subGenre", {}).get("name") or ""
        native_g = map_native_genre(g_name) or map_native_genre(sg_name)
        genre = infer_music_genre(name, vname, native_genre=native_g)

        key = (name.lower(), dt.strftime("%Y-%m-%d"))
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": link,
            "venue": vname,
            "price": price,
            "category": "music",
            "genre": genre,
        })

    return events


def scrape_ticketweb(url, ua):
    """Scrape upcoming live shows from TicketWeb venue pages using schema.org MusicEvent LD+JSON."""
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return []

    scripts = soup.find_all("script", type="application/ld+json")
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    for s in scripts:
        try:
            items = json.loads(s.string)
            if not isinstance(items, list):
                items = [items]
            for it in items:
                if not isinstance(it, dict) or it.get("@type") != "MusicEvent":
                    continue
                name = (it.get("name") or "").strip()
                if not name or is_placeholder_or_closed_event(name):
                    continue
                start_str = it.get("startDate")
                if not start_str:
                    continue
                try:
                    dt = datetime.fromisoformat(start_str).replace(tzinfo=EASTERN)
                except Exception:
                    continue
                if (now - dt).total_seconds() > 24 * 3600:
                    continue

                link = it.get("url") or url
                loc = it.get("location", {})
                vname = loc.get("name") if isinstance(loc, dict) else None

                key = (name.lower(), dt.strftime("%Y-%m-%d"))
                if key in seen:
                    continue
                seen.add(key)

                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": link,
                    "venue": vname,
                    "price": None,
                    "category": "music",
                })
        except Exception:
            continue

    return events


def scrape_trumba(url, ua):
    """Fetch and parse events from official Trumba JSON feeds (NEC, Tufts Music, etc.)."""
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    now = datetime.now(EASTERN)
    out = []
    seen = set()

    for item in data:
        title = html.unescape(item.get("title") or "").strip()
        start_raw = item.get("startDateTime")
        if not title or not start_raw or is_placeholder_or_closed_event(title):
            continue
        try:
            dt = datetime.fromisoformat(start_raw).replace(tzinfo=EASTERN)
        except Exception:
            continue
        if dt < now - timedelta(hours=6):
            continue

        link = item.get("permaLinkUrl") or url
        loc = (item.get("location") or "").strip()

        key = (title.lower(), dt.strftime("%Y-%m-%d"))
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "name": title,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": link,
            "venue": loc if loc else None,
            "price": None,
            "category": "classical",
        })

    return out


def scrape_squarespace(url, ua):
    """Generic Squarespace calendar scraper (e.g. The Bebop, Remnant Satellite, Portico Brewing)."""
    target_url = url if "format=json" in url else (f"{url}?format=json" if "?" not in url else f"{url}&format=json")
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    parsed = urlparse(url)
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"

    events = []
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=90)
    seen = set()
    items = data.get("upcoming", []) or data.get("items", [])
    for item in items:
        title = re.sub(r"\s+", " ", (item.get("title") or "").strip())
        if not title or is_placeholder_or_closed_event(title):
            continue
        ms = item.get("startDate")
        if not ms:
            continue
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        if dt < now - timedelta(days=1) or dt > cutoff:
            continue
        full_url = item.get("fullUrl")
        ev_url = f"{base}{full_url}" if full_url else url

        key = (title.lower(), dt.strftime("%Y-%m-%d"))
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt.isoformat(),
            "url": ev_url,
            "venue": None,
            "price": None,
            "description": None,
            "category": "music",
        })
    return events


_ALL_VENUES = [
    {"name": "Paradise Rock Club", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZA11JtA&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Brighton Music Hall", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpapwne&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "MGM Music Hall at Fenway", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZ917AEJz&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Citizens House of Blues Boston", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZAEA7eA&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Orpheum Theatre", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZA1J7JA&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Leader Bank Pavilion", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZ917AxdQ&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Chevalier Theatre", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZAJd6aA&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "music"},
    {"name": "Sonia", "url": "https://www.ticketweb.com/venue/sonia-cambridge-ma/435615", "ua": UA_CHROME, "scraper": scrape_ticketweb, "default_category": "music"},
    {"name": "Scullers Jazz Club", "url": "https://www.ticketweb.com/venue/scullers-jazz-club-boston-ma/18647", "ua": UA_CHROME, "scraper": scrape_ticketweb, "default_category": "music"},
    {"name": "Regattabar", "url": "https://www.ticketweb.com/venue/regattabar-cambridge-ma/748814", "ua": UA_CHROME, "scraper": scrape_ticketweb, "default_category": "music"},
    {"name": "Off the Rails Boston", "url": "https://www.ticketweb.com/venue/off-the-rails-boston-boston-ma/797374", "ua": UA_CHROME, "scraper": scrape_ticketweb, "default_category": "music"},
    {"name": "Mr. Dooley's", "url": "https://www.mrdooleys.com/events/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "The Green Dragon Tavern", "url": "https://www.greendragonboston.com/events/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "Hennessy's Bar", "url": "https://hennessysboston.com/events/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "UnCommon Corner", "url": "https://uncommoncorner.org/events/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "Roundhead Brewing", "url": "https://roundheadbrewing.com/events/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "Tufts Music (Granoff Music Center)", "url": "https://www.trumba.com/calendars/tts-wms-managed-music.json", "ua": UA_CHROME, "scraper": scrape_trumba, "default_category": "classical"},
    {"name": "Remnant Satellite", "url": "https://www.remnantsomerville.com/live", "ua": UA_CHROME, "scraper": scrape_squarespace, "default_category": "music"},
    {"name": "Portico Brewing", "url": "https://porticobrewing.com/upcoming-events", "ua": UA_CHROME, "scraper": scrape_squarespace, "default_category": "music"},
    {"name": "Symphony Hall", "url": "https://www.bso.org/events", "ua": UA_CHROME, "scraper": scrape_symphony_hall, "default_category": "classical"},
    {"name": "Berklee College of Music", "url": "https://www.berklee.edu/events", "ua": UA_CHROME, "scraper": scrape_berklee, "default_category": "music"},
    {"name": "The Bebop", "url": "https://thebebopboston.com/new-events", "ua": UA_CHROME, "scraper": scrape_the_bebop, "default_category": "music"},
    {"name": "Longy School of Music", "url": "https://longy.edu/calendar/list/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "classical"},
    {"name": "Warehouse XI", "url": "https://www.wxi.space", "ua": UA_CHROME, "scraper": scrape_warehouse_xi, "default_category": "music"},
    {"name": "Downtown Boston BID", "url": "https://www.downtownboston.org/events/", "ua": UA_CHROME, "scraper": scrape_downtown_boston, "default_category": "community"},
    {"name": "Dani's Queer Bar", "url": "https://www.eventbrite.com/d/ma--boston/danis-queer-bar/", "ua": UA_CHROME, "scraper": scrape_danis_queer_bar, "default_category": "clubbing"},
    {"name": "Club Café", "url": "https://www.clubcafe.com/full-calendar/", "ua": UA_CHROME, "scraper": scrape_club_cafe, "default_category": "clubbing"},
    {"name": "FERAL", "url": "https://www.eventbrite.com/o/feral-events-71015854393", "ua": UA_CHROME, "scraper": scrape_feral, "default_category": "clubbing"},
    {"name": "Boston LGBTQ+ Nightlife", "url": "https://www.eventbrite.com/d/ma--boston/lgbtq-nightlife/", "ua": UA_CHROME, "scraper": scrape_boston_queer_nightlife, "default_category": "clubbing"},
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
    {"name": "Luma Boston", "url": "https://lu.ma/boston", "ua": UA_CHROME, "scraper": scrape_luma, "default_category": "community"},
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
    {"name": "The Cantab Lounge", "url": "https://thecantablounge.com/", "ua": UA_CHROME, "scraper": scrape_tunehatch, "default_category": "music"},
    {"name": "Cantab Underground", "url": "https://thecantablounge.com/cantab/underground", "ua": UA_CHROME, "scraper": scrape_tunehatch, "default_category": "music"},
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
    ("clubbing","Dani's Queer Bar (Back Bay lesbian/queer bar)", "https://danisqueerbar.com/"),
    ("clubbing","Club Café (historic South End LGBT nightclub & cabaret)", "https://www.clubcafe.com/"),
    ("clubbing","The Alley Bar (Downtown bear & leather bar)", "http://www.thealleybar.com/"),
    ("clubbing","Gay Mafia Boston (Legacy & Candystrip parties)", "https://www.gaymafiaboston.com"),
    ("clubbing","LesbianNightLife (tea dances & queer parties)", "https://www.lesbiannightlife.com"),
    ("clubbing","FERAL (@feral.party · queer/trans rager)", "https://www.instagram.com/feral.party"),
    ("music",   "Boston Symphony Orchestra / Symphony Hall", "https://www.bso.org/events"),
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
    ("The Black Rose", "https://www.blackroseboston.com/live-music1/", "music", [
        ("Live Irish & Acoustic Music", "https://www.blackroseboston.com/live-music1/", 0, 20, 0, "Free"),
        ("Live Irish & Acoustic Music", "https://www.blackroseboston.com/live-music1/", 1, 20, 0, "Free"),
        ("Live Irish & Acoustic Music", "https://www.blackroseboston.com/live-music1/", 2, 20, 0, "Free"),
        ("Live Irish & Acoustic Music", "https://www.blackroseboston.com/live-music1/", 3, 20, 0, "Free"),
        ("Afternoon Acoustic Session", "https://www.blackroseboston.com/live-music1/", 4, 16, 0, "Free"),
        ("Friday Night Live Band", "https://www.blackroseboston.com/live-music1/", 4, 21, 0, "Free"),
        ("Saturday Afternoon Acoustic", "https://www.blackroseboston.com/live-music1/", 5, 16, 0, "Free"),
        ("Saturday Night Live Band", "https://www.blackroseboston.com/live-music1/", 5, 21, 0, "Free"),
        ("Sunday Traditional Irish Session", "https://www.blackroseboston.com/live-music1/", 6, 17, 0, "Free"),
        ("Sunday Night Live Band", "https://www.blackroseboston.com/live-music1/", 6, 20, 0, "Free"),
    ]),
    ("Emmets Irish Pub", "https://www.emmetsirishpubandrestaurant.com", "music", [
        ("Saturday Afternoon Irish Session", "https://www.emmetsirishpubandrestaurant.com", 5, 15, 0, "Free"),
        ("Saturday Night Live Music", "https://www.emmetsirishpubandrestaurant.com", 5, 21, 0, "Free"),
        ("Sunday Afternoon Irish Session", "https://www.emmetsirishpubandrestaurant.com", 6, 15, 0, "Free"),
    ]),
    ("The Brendan Behan Pub", "https://brendanbehanjp.com", "music", [
        ("Live Traditional Irish Session", "https://brendanbehanjp.com", 5, 17, 0, "Free"),
    ]),
    ("Emmanuel Church", "https://www.emmanuelmusic.org/performance-info/2026-2027-cantata-schedule", "classical", [
        ("Emmanuel Music Weekly Bach Cantata Series", "https://www.emmanuelmusic.org/performance-info/2026-2027-cantata-schedule", 6, 11, 0, "Free"),
    ]),
    ("Redbones", "https://redbones.com/events", "music", [
        ("Phrenology Trivia Night @ Underbones", "https://redbones.com/events", 4, 20, 0, "Free"),
        ("Live Music & Showcase @ Underbones", "https://redbones.com/events", 5, 21, 0, "Free"),
        ("ONCE Upon A Time: Indie Music Series @ Underbones", "https://redbones.com/events", 6, 16, 0, "$15"),
        ("Bluegrass & Roots Night @ Underbones", "https://redbones.com/events", 3, 20, 0, "Free"),
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
                genre = infer_music_genre(name, venue, category=default_cat) if default_cat in ("music", "clubbing") else None
                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": url,
                    "venue": venue,
                    "price": price,
                    "category": default_cat,
                    "genre": genre,
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
            genre = e.get("genre")
            if not genre and cat in ("music", "clubbing"):
                genre = infer_music_genre(e["name"], e["venue"], description=e.get("description"), category=cat)
            events.append({
                "name": str(e["name"]).strip(),
                "date": e.get("date"),
                "url": e.get("url") or "",
                "venue": str(e["venue"]).strip(),
                "price": e.get("price"),
                "category": cat,
                "genre": genre,
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
    ("music",     ["music", "musical", "musician", "concert", " band ", "live music", "music series", "music hall", "orchestra",
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

_WORD_BOUNDARY_KEYWORDS = {
    "art", "arts", "rap", "disco", "disko", "pop", "funk", "punk", "metal",
    "bash", "rave", "edm", "jam", "fest", "tour", "expo", "gala", "poet",
    "clay", "sake", "maki", "menu", "chef", "bbq", "gym", "golf", "kids",
    "baby", "lego", "hike", "yoga", "farm", "beer", "wine", "film", "match",
}
_WORD_BOUNDARY_PATTERNS = {
    k: re.compile(rf"\b{re.escape(k)}\b", re.I) for k in _WORD_BOUNDARY_KEYWORDS
}


def infer_category(name, venue, default=None):
    text = f"{name or ''} {venue or ''}".lower()
    for cat, kws in CATEGORY_KEYWORDS:
        for k in kws:
            pat = _WORD_BOUNDARY_PATTERNS.get(k)
            if pat is not None:
                if pat.search(text):
                    return cat
            elif k in text:
                return cat
    if default == "classical":
        return "music"
    if default == "arts":
        return "art"
    if default == "fitness":
        return "sports"
    return default or "other"


CATEGORY_STYLES = {
    "music":     ("#7aa2f7", "♪"),
    "classical": ("#7aa2f7", "♪"),
    "dance":     ("#ff7ab2", "💃"),
    "comedy":    ("#f0a07a", "☺"),
    "theater":   ("#f7768e", "🎭"),
    "stage":     ("#f7768e", "🎭"),
    "books":     ("#9ece6a", "📖"),
    "gaming":    ("#bb9af7", "◆"),
    "clubbing":  ("#e06c75", "◉"),
    "film":      ("#e0af68", "▶"),
    "sports":    ("#73daca", "⚑"),
    "fitness":   ("#73daca", "⚑"),
    "outdoors":  ("#4fbf8f", "⛰"),
    "food":      ("#c678dd", "🍺"),
    "family":    ("#ffb8d1", "✦"),
    "art":       ("#ffd866", "✦"),
    "arts":      ("#ffd866", "✦"),
    "community": ("#8fa1b3", "◯"),
    "other":     ("#6b7280", "·"),
}


CATEGORY_BUCKETS = [
    ("Music & nightlife", ["music", "clubbing", "classical"]),
    ("Dance",             ["dance"]),
    ("Stage",             ["comedy", "theater", "stage"]),
    ("Arts & culture",    ["books", "film", "art", "arts"]),
    ("Play",              ["gaming", "sports", "fitness", "outdoors", "family"]),
    ("Food & drink",      ["food"]),
    ("Community",         ["community", "other"]),
]
_CAT_TO_BUCKET = {cat: name for name, cats in CATEGORY_BUCKETS for cat in cats}


def category_bucket(cat):
    return _CAT_TO_BUCKET.get(cat or "other", "Community")


MUSIC_GENRES = {
    "rock_indie": {
        "id": "rock_indie",
        "label": "Rock & Indie",
        "icon": "🎸",
        "color": "#ff708d",
    },
    "folk_trad": {
        "id": "folk_trad",
        "label": "Folk & Trad",
        "icon": "🪕",
        "color": "#9ece6a",
    },
    "jazz_blues": {
        "id": "jazz_blues",
        "label": "Jazz & Blues",
        "icon": "🎷",
        "color": "#f29e4c",
    },
    "electronic": {
        "id": "electronic",
        "label": "Electronic & Club",
        "icon": "🎛",
        "color": "#bb9af7",
    },
    "classical": {
        "id": "classical",
        "label": "Classical",
        "icon": "🎻",
        "color": "#7aa2f7",
    },
    "hiphop_rnb": {
        "id": "hiphop_rnb",
        "label": "Hip-Hop & R&B",
        "icon": "🎤",
        "color": "#f0a07a",
    },
    "latin_global": {
        "id": "latin_global",
        "label": "Latin & Global",
        "icon": "🪇",
        "color": "#ffb8d1",
    },
    "pop": {
        "id": "pop",
        "label": "Pop",
        "icon": "✨",
        "color": "#ffd866",
    },
}

def map_native_genre(name):
    """Maps raw external genre strings (e.g. from Ticketmaster or SeatGeek) into our standard MUSIC_GENRES."""
    if not name or not isinstance(name, str):
        return None
    s = name.strip().lower()
    if s in ("undefined", "other", "music", "concert"):
        return None
    if any(k in s for k in ["classical", "orchestr", "symphon", "opera", "chamber"]):
        return "classical"
    if any(k in s for k in ["jazz", "blues"]):
        return "jazz_blues"
    if any(k in s for k in ["folk", "country", "americana", "bluegrass", "celtic", "irish", "traditional", "acoustic"]):
        return "folk_trad"
    if any(k in s for k in ["dance", "electronic", "edm", "house", "techno", "club", "trance", "drum & bass", "dubstep", "synth"]):
        return "electronic"
    if any(k in s for k in ["hip-hop", "hip hop", "rap", "r&b", "rhythm and blues", "urban", "soul", "trap"]):
        return "hiphop_rnb"
    if any(k in s for k in ["latin", "salsa", "reggaeton", "bachata", "cumbia", "world", "reggae", "afrobeat", "dancehall", "ska"]):
        return "latin_global"
    if any(k in s for k in ["rock", "alternative", "punk", "metal", "indie", "grunge", "emo", "hardcore"]):
        return "rock_indie"
    if any(k in s for k in ["pop", "k-pop", "j-pop"]):
        return "pop"
    return None

MUSIC_VENUE_ANCHORS = {
    # Classical institutions
    "boston symphony orchestra": "classical",
    "symphony hall": "classical",
    "new england conservatory": "classical",
    "jordan hall": "classical",
    "longy school of music": "classical",
    "tufts music": "classical",
    "boston lyric opera": "classical",
    "boston baroque": "classical",
    "handel and haydn society": "classical",
    "emmanuel music": "classical",
    "cantata singers": "classical",
    "a far cry": "classical",

    # Jazz & Blues anchors
    "wally": "jazz_blues",
    "scullers jazz club": "jazz_blues",
    "regattabar": "jazz_blues",
    "the bebop": "jazz_blues",
    "mad monkfish": "jazz_blues",
    "the beehive": "jazz_blues",
    "the lilypad": "jazz_blues",
    "lilypad": "jazz_blues",

    # Folk & Trad anchors
    "club passim": "folk_trad",
    "passim": "folk_trad",
    "the burren": "folk_trad",
    "the druid": "folk_trad",
    "druid": "folk_trad",
    "the black rose": "folk_trad",
    "black rose": "folk_trad",
    "mr. dooley": "folk_trad",
    "sally o": "folk_trad",
    "mccarthy": "folk_trad",
    "banter bar": "folk_trad",
    "emmet": "folk_trad",
    "brendan behan": "folk_trad",
    "canadian american club": "folk_trad",
    "the plough and stars": "folk_trad",
    "plough and stars": "folk_trad",

    # Electronic / Nightlife anchors
    "manray": "electronic",
    "mémoire": "electronic",
    "memoire": "electronic",
    "phoenix landing": "electronic",
    "middlesex lounge": "electronic",
    "zuzu": "electronic",
}

MUSIC_VENUE_DEFAULTS = {
    "o'brien": "rock_indie",
    "sinclair": "rock_indie",
    "roadrunner": "rock_indie",
    "paradise rock": "rock_indie",
    "brighton music": "rock_indie",
    "middle east": "rock_indie",
    "sonia": "rock_indie",
    "deep cuts": "rock_indie",
    "faces brewing": "rock_indie",
    "silhouette": "rock_indie",
    "square root": "rock_indie",
    "midway cafe": "rock_indie",
    "big night live": "electronic",
    "royale": "electronic",
    "redbones": "rock_indie",
    "lizard lounge": "rock_indie",
}

MUSIC_GENRE_RULES = [
    ("classical", [
        r"\b(symphony(\s+no\b|\s+orchestra|\s+hall)?|philharmonic|concerto|sonata|chamber\s+(orchestra|music|ensemble)|opera\b(?!(\s+(house|theatre|theater|pop|rock)))|soprano|tenor\s+solo|mezzo-soprano|baritone\s+solo|choral\s+(society|concert|works)|requiem|cantata|oratorio|sinfonia|allegro|adagio|beethoven|mozart|\bbach\b(?!ata)|chopin|brahms|tchaikovsky|vivaldi|mahler|handel(\s+and\s+haydn)?|haydn\b|debussy|ravel\b|rachmaninoff|shostakovich|stravinsky|dvorak|mendelssohn|schubert|schumann|puccini|verdi\b|string\s+quartet|piano\s+trio|brass\s+quintet|wind\s+quintet|organ\s+recital|flute\s+recital|cello\s+recital|violin\s+recital|harpsichord)\b"
    ]),
    ("jazz_blues", [
        r"\b(jazz|blues\b(?!(\s+screens|ky))|bebop|post-bop|hard\s+bop|dixieland|big\s+band|trad\s+jazz|jazz\s+fusion|delta\s+blues|chicago\s+blues|rhythm\s+and\s+blues|boogie\s+woogie|stride\s+piano|saxophone\s+(quartet|solo)|coltrane|thelonious|miles\s+davis|charlie\s+parker|bill\s+evans|ella\s+fitzgerald|billie\s+holiday|muddy\s+waters|b\.b\.\s+king|buddy\s+guy|howlin['\''’]?\s*wolf|straight-ahead\s+jazz|jazz\s+(trio|quartet|quintet|ensemble|orchestra|jam|collective|brunch|lounge))\b"
    ]),
    ("folk_trad", [
        r"\b(folk\b(?!(\s+art))|bluegrass|americana|celtic|irish\s+(session|trad|traditional|music|tunes)|seisi[uú]n|fiddle|banjo|mandolin|singer-songwriter|old-time|flatpicking|sea\s+shant(y|ies)|appalachian|honky\s*tonk|outlaw\s+country|country\s+music|acoustic\s+(folk|guitar|showcase|open\s+mic)|woody\s+guthrie|john\s+prine|townes\s+van\s+zandt|doc\s+watson|cape\s+breton)\b"
    ]),
    ("electronic", [
        r"\b(electronic(a)?|edm\b|techno\b|house\s+music|deep\s+house|tech\s+house|drum\s*&\s*bass|drum\s+and\s+bass|\bdnb\b|\bd&b\b|dubstep|synthwave|darkwave|ebm\b|industrial\s+(dance|music)|trance\b|psytrance|ambient\s+music|dj\s+(set|night|party)|all-night\s+dance|dance\s+party|rave\b|turntabli(sm|st)|boiler\s+room|club\s+night|modular\s+synth|synthesizer\s+music|nightclub|electro-pop|electronic\s+dance)\b"
    ]),
    ("hiphop_rnb", [
        r"\b(hip[- ]?hop|rap\b(?!ture|id)|rapper|emcee|\bmc\s+[a-z]+|trap\s+music|boom\s+bap|r&b\b|rhythm\s+&\s+blues|neo-soul|soul\s+music|motown|afrobeat|freestyle\s+(rap|session)|cypher|drill\s+music|grime\b)\b"
    ]),
    ("latin_global", [
        r"\b(latin\b(?!o?\s+(america|studies))|salsa\b|bachata|cumbia|merengue|reggaeton|tango\b|flamenco|bossa\s+nova|samba\b|mariachi|ranchera|corrido|latin\s+jazz|afro-cuban|calypso|reggae|dancehall|rocksteady|afrobeats|klezmer|balkan|flamenco\s+guitar|middle\s+eastern\s+music|oud\s+recital|\bsitar\b|\btabla\b|bollywood)\b"
    ]),
    ("rock_indie", [
        r"\b(rock(\s+and\s+roll|\s*'\''n'\''\s*roll)?|indie\s+rock|indie\s+pop|alternative(\s+rock)?|punk(\s+rock)?|hardcore(\s+punk)?|post-punk|post-hardcore|emo\b|metal(\s+band)?|heavy\s+metal|death\s+metal|black\s+metal|thrash(\s+metal)?|doom\s+metal|sludge(\s+metal)?|stoner\s+rock|grunge|shoegaze|dream\s+pop|math\s+rock|psychedelic(\s+rock)?|garage\s+rock|noise\s+rock|art\s+rock|prog\s+rock|progressive\s+rock|glam\s+rock|classic\s+rock|hard\s+rock|tribute\s+band|cover\s+band|screamo|pop-punk|riot\s+grrrl|surf\s+rock|dark\s+star\s+orchestra)\b"
    ]),
    ("pop", [
        r"\b(pop\s+music|electropop|synth-pop|synthpop|k-pop|kpop|j-pop|jpop|boy\s+band|girl\s+group|dance\s+pop|teen\s+pop|hyperpop|taylor\s+swift|swiftie|beatles\s+tribute|disco(\s+night|\s+party)?|abba\s+night|britpop)\b"
    ]),
]

def infer_music_genre(name, venue=None, description=None, native_genre=None, category=None):
    """Infers music subgenre from native tags, venue signature, event title, and description."""
    if native_genre:
        mapped = map_native_genre(native_genre)
        if mapped:
            return mapped

    v_str = (venue or "").lower()
    t_str = f"{name or ''} {description or ''}".lower()

    # Negative exclusions
    if "dark star orchestra" in t_str or "night at the opera" in t_str:
        return "rock_indie"

    # Institutional anchor venues (BSO, Wally's, Passim, ManRay, etc.)
    for anchor, g in MUSIC_VENUE_ANCHORS.items():
        if anchor in v_str:
            return g

    # Pattern matching on title & description
    for genre, patterns in MUSIC_GENRE_RULES:
        for p in patterns:
            if re.search(p, t_str, re.IGNORECASE):
                return genre

    # Clubbing fallback
    if category == "clubbing" or "clubbing" in v_str:
        return "electronic"

    # Signature venue defaults
    for v_prefix, g in MUSIC_VENUE_DEFAULTS.items():
        if v_prefix in v_str:
            return g

    return "rock_indie"


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


LUCKYSEAT_CACHE_FILE = os.path.join(CACHE_DIR, "luckyseat_shows.json")


def fetch_luckyseat_boston():
    """Fetch LuckySeat's show list and filter to Greater Boston (Boston, Cambridge, Somerville).
    Cached for 15 min with persistent disk backup so transient WAF blocks never wipe listings."""
    if _luckyseat_cache["data"] is not None and time.time() - _luckyseat_cache["ts"] < CACHE_SECONDS:
        return _luckyseat_cache["data"]

    disk_data = None
    if os.path.exists(LUCKYSEAT_CACHE_FILE):
        try:
            with open(LUCKYSEAT_CACHE_FILE, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
        except Exception:
            disk_data = None

    shows = []
    try:
        headers = {
            "User-Agent": UA_CHROME,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.luckyseat.com/",
            "Origin": "https://www.luckyseat.com",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = _SESSION.get(
            "https://www.luckyseat.com/api/showmanagement/getshowlist",
            headers=headers,
            timeout=10,
        )
        resp.raise_for_status()
        raw_shows = resp.json()
        if isinstance(raw_shows, list) and len(raw_shows) > 0:
            for s in raw_shows:
                city = (s.get("city") or "").strip().lower()
                if city not in ("boston", "cambridge", "somerville"):
                    continue
                if not s.get("isActive") or s.get("isTempClosed"):
                    continue
                shows.append({
                    "name": s.get("showName"),
                    "venue": s.get("eventLocation"),
                    "price": s.get("priceAndFeesTotal"),
                    "url": f"https://www.luckyseat.com/shows/{s.get('showAlias')}" if s.get("showAlias") else "https://www.luckyseat.com/",
                })
            if shows:
                try:
                    with open(LUCKYSEAT_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(shows, f)
                except Exception:
                    pass
    except Exception as e:
        if disk_data:
            shows = disk_data
        else:
            try:
                events_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
                if os.path.exists(events_json_path):
                    with open(events_json_path, "r", encoding="utf-8") as f:
                        shows = json.load(f).get("luckyseat") or []
            except Exception:
                shows = []

    if not shows and disk_data:
        shows = disk_data

    _luckyseat_cache["data"] = shows
    _luckyseat_cache["ts"] = time.time()
    return shows


def dedupe(events):
    seen = set()
    out = []
    for e in events:
        name = e.get("name") or ""
        if is_placeholder_or_closed_event(name):
            continue
        key = ((name).lower(), e.get("date") or "")
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
    """Warm in-memory cache, last-known-good map, and disk venue cache from events.json on disk if available."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
    if not os.path.exists(json_path):
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        venues = payload.get("venues") if isinstance(payload, dict) else payload
        generated_at = payload.get("generated_at") if isinstance(payload, dict) else None

        file_ts = os.path.getmtime(json_path)
        if generated_at:
            try:
                dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                file_ts = dt.timestamp()
            except Exception:
                pass

        if venues and isinstance(venues, list):
            for v in venues:
                if v.get("events"):
                    v["events"] = [e for e in v["events"] if not is_placeholder_or_closed_event(e.get("name"))]
            if not _cache["data"]:
                _cache["data"] = venues
                _cache["ts"] = file_ts
            for v in venues:
                vname = v.get("venue")
                evs = v.get("events")
                if vname and evs is not None:
                    evs = [e for e in evs if not is_placeholder_or_closed_event(e.get("name"))]
                    _last_known_good[vname] = evs
                    # If venue cache does not exist on disk, seed it with events and timestamp from events.json
                    cpath = _venue_cache_path(vname)
                    if not os.path.exists(cpath):
                        try:
                            with open(cpath, "w", encoding="utf-8") as cf:
                                json.dump({
                                    "ts": file_ts,
                                    "venue": vname,
                                    "duration": v.get("duration", 0.0),
                                    "events": evs
                                }, cf, ensure_ascii=False)
                        except Exception:
                            pass
    except Exception:
        pass


_init_warm_cache()


_AGGREGATOR_VENUES = {
    "The Boston Calendar", "Eventbrite Boston", "Eventbrite Cambridge",
    "Eventbrite Somerville", "Do617", "Meetup Boston", "Luma Boston",
}


def _normalize_and_filter_events(raw_events, v):
    """Filter out placeholders, past events (>18h ago), virtual events, and far-away venues,
    and normalize category & music genre."""
    name = v["name"]
    default_cat = v.get("default_category")
    is_agg = (default_cat is None) or (name in _AGGREGATOR_VENUES)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=18)
    out = []

    for e in (raw_events or []):
        title = (e.get("name") or "").strip()
        if not title or is_placeholder_or_closed_event(title):
            continue

        v_raw = (e.get("venue") or "").strip()
        v_low = v_raw.lower()
        t_low = title.lower()

        # Filter virtual/online events
        if v_low in ("online", "online event", "virtual", "zoom") or "(virtual)" in v_low or t_low.startswith(("virtual -", "virtual:", "online -", "online:")):
            continue

        # Filter far out-of-region venues (Western Mass, Cape Ann, Fall River, NH)
        if any(far in v_low for far in ("linde center", "tanglewood", "ozawa hall", "hammond castle", "lizzie borden house", "exeter nh", "scenic railriders")):
            continue

        # Filter past events (>18h ago)
        d_str = e.get("date")
        if d_str and d_str != "tba":
            try:
                dt = datetime.fromisoformat(d_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=EASTERN)
                if dt.astimezone(timezone.utc) < cutoff:
                    continue
            except Exception:
                pass

        if not v_raw:
            e["venue"] = name

        cat = e.get("category")
        if cat == "classical" or (not cat and default_cat == "classical"):
            e["category"] = "music"
            if not e.get("genre"):
                e["genre"] = "classical"
        elif cat == "arts" or (not cat and default_cat == "arts"):
            e["category"] = "art"
        elif cat == "fitness":
            e["category"] = "sports"
        elif cat == "stage":
            e["category"] = "theater"
        elif is_agg or not cat:
            e["category"] = infer_category(e.get("name"), e.get("venue"), default_cat)

        if e.get("category") in ("music", "clubbing"):
            if not e.get("genre"):
                e["genre"] = infer_music_genre(
                    e.get("name"), e.get("venue"),
                    description=e.get("description"),
                    native_genre=e.get("genre"),
                    category=e.get("category"),
                )
        else:
            e.pop("genre", None)

        out.append(e)

    out.sort(key=_sort_key)
    return out


def _scrape_one(v, force=False):
    name = v["name"]
    ttl = _get_venue_ttl(name)
    t0 = time.time()

    # 1. Check if cached data exists and is within TTL
    if not force:
        cached = _load_venue_cache(name, max_age=ttl)
        if cached and cached.get("events") is not None:
            events = _normalize_and_filter_events(cached["events"], v)
            return {
                "venue": name,
                "url": v["url"],
                "events": events,
                "error": None,
                "duration": cached.get("duration", 0.0),
                "cached": True,
            }

    # 2. Live scrape from external website
    try:
        events = dedupe(v["scraper"](v["url"], v["ua"]))
        events = _normalize_and_filter_events(events, v)
        dur = round(time.time() - t0, 2)

        # Update last known good and save to disk cache
        if events:
            _last_known_good[name] = events
            _save_venue_cache(name, events, duration=dur)
        elif name in _last_known_good and not events:
            # Scraper returned 0 events but previously had events: fall back to preserve data
            events = _normalize_and_filter_events(_last_known_good[name], v)
        else:
            _save_venue_cache(name, events, duration=dur)

        return {
            "venue": name,
            "url": v["url"],
            "events": events,
            "error": None,
            "duration": dur,
            "cached": False,
        }
    except Exception as e:
        # Fall back to stale cache or previous events if available on network error/timeout
        stale = _load_venue_cache(name, max_age=None)
        prev = (stale.get("events") if stale else None) or _last_known_good.get(name, [])
        prev = _normalize_and_filter_events(prev, v)
        return {
            "venue": name,
            "url": v["url"],
            "events": prev,
            "error": str(e),
            "fallback": bool(prev),
            "duration": round(time.time() - t0, 2),
            "cached": bool(prev),
        }


def _do_scrape_all(force=False):
    def _worker(v):
        return _scrape_one(v, force=force)

    with ThreadPoolExecutor(max_workers=min(16, len(VENUES))) as ex:
        results = list(ex.map(_worker, VENUES))
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
        _do_scrape_all(force=False)
    finally:
        with _refresh_lock:
            _is_refreshing = False


def get_all_events(force=False):
    """Return all scraped events.

    Uses per-venue TTL caching (1h for fast-turnover, 3h standard, 12h evergreen)
    backed by persistent disk cache and fallback error resilience.
    """
    now = time.time()
    with _cache_lock:
        cached = _cache["data"]
        is_stale = (now - _cache["ts"]) >= CACHE_SECONDS

    if force:
        return _do_scrape_all(force=True)

    if cached is not None and not is_stale:
        return cached

    return _do_scrape_all(force=False)

