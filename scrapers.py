"""Boston Events — venue scrapers and data definitions."""

import hashlib
import html
import json
import os
import random
import re
import ssl
import string
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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


def _scraper_fingerprint(v):
    """Hash of a source's scraper code + URL. A cache entry from different code is discarded,
    so scraper fixes show up on the next deploy instead of after the TTL (up to 12h)."""
    import hashlib
    import inspect
    try:
        src = inspect.getsource(v["scraper"])
    except (OSError, TypeError):
        src = getattr(v["scraper"], "__name__", "")
    return hashlib.sha1(f"{src}\n{v.get('url')}".encode("utf-8")).hexdigest()[:12]


def _load_venue_cache(vname, max_age=None, fingerprint=None):
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
        if fingerprint is not None and cached.get("fp") != fingerprint:
            return None  # written by older scraper code
        return cached
    except Exception:
        return None


def _save_venue_cache(vname, events, duration=0.0, fingerprint=None):
    path = _venue_cache_path(vname)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "ts": time.time(),
                "venue": vname,
                "duration": duration,
                "fp": fingerprint,
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

    s = _PoliteSession()
    s.mount("https://", _Adapter())
    return s


# --- Polite crawling ------------------------------------------------------------------------
# A daily build sends ~1,500 requests to ~130 sites. Every request goes through _SESSION and this
# gate, so no site sees a burst: at most two requests in flight per site with a pause between
# them (one at a time for sites with bot protection). A 429 ("slow down") or 5xx gets one retry
# after a pause; a site that refuses us (403, or 429 again) isn't asked again for the rest of
# the run, and its source keeps its last good data.
HOST_POLICY_DEFAULT = (2, 0.5)  # (max requests in flight, min seconds between request starts)
HOST_POLICY = {
    "eventbrite.com": (1, 1.0),
    "meetup.com": (1, 1.0),
    "partiful.com": (1, 1.0),
    "do617.com": (1, 0.5),
    "bostonchildrensmuseum.org": (1, 1.0),  # answered 504 at four at a time
}
RETRY_STATUSES = {429, 502, 503, 504}
MAX_RETRY_WAIT = 30
OVERLOADED_AFTER = 3  # 5xx answers (after retrying) before we leave a site alone for the run


class SiteRefused(requests.RequestException):
    """A site refused us earlier this run (403/429), so we don't ask it again."""


def _host_of(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def _host_policy(host):
    for domain, policy in HOST_POLICY.items():
        if host == domain or host.endswith("." + domain):
            return policy
    return HOST_POLICY_DEFAULT


class _HostGate:
    """Per-site concurrency and spacing, plus the list of sites that refused us this run."""

    def __init__(self):
        self._lock = threading.Lock()
        self._slots = {}
        self._next_start = {}
        self._overloads = {}
        self.refused = {}

    def reset(self):
        with self._lock:
            self.refused.clear()
            self._overloads.clear()

    def acquire(self, host):
        in_flight, gap = _host_policy(host)
        with self._lock:
            slot = self._slots.setdefault(host, threading.BoundedSemaphore(in_flight))
        slot.acquire()
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start.get(host, 0.0))
            self._next_start[host] = start + gap
        if start > now:
            time.sleep(start - now)

    def release(self, host):
        self._slots[host].release()

    def refuse(self, host, reason):
        with self._lock:
            self.refused.setdefault(host, reason)

    def overloaded(self, host):
        with self._lock:
            self._overloads[host] = self._overloads.get(host, 0) + 1
            if self._overloads[host] >= OVERLOADED_AFTER:
                self.refused.setdefault(host, "overloaded")


HOST_GATE = _HostGate()


def _retry_after_secs(resp):
    raw = (resp.headers or {}).get("Retry-After", "")
    if raw.strip().isdigit():
        return min(int(raw), MAX_RETRY_WAIT)
    try:
        when = parsedate_to_datetime(raw)
        return max(0, min((when - datetime.now(timezone.utc)).total_seconds(), MAX_RETRY_WAIT))
    except (TypeError, ValueError):
        return 5


class _PoliteSession(requests.Session):
    def request(self, method, url, *args, **kwargs):
        host = _host_of(url)
        if host in HOST_GATE.refused:
            raise SiteRefused(f"{host} refused us earlier this run ({HOST_GATE.refused[host]})")
        for attempt in (1, 2):
            HOST_GATE.acquire(host)
            try:
                resp = super().request(method, url, *args, **kwargs)
            finally:
                HOST_GATE.release(host)
            status = resp.status_code
            if status in RETRY_STATUSES and attempt == 1:
                time.sleep(_retry_after_secs(resp))
                continue
            if status in (403, 429):
                HOST_GATE.refuse(host, str(status))
            elif status in RETRY_STATUSES:
                HOST_GATE.overloaded(host)
            return resp
        return resp


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
    # Pass raw bytes so BeautifulSoup honors the page's own charset declaration; resp.text
    # falls back to Latin-1 when the server omits a charset, producing mojibake (e.g. "Whereâs").
    return BeautifulSoup(resp.content, "html.parser")


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

    # 2b. Relocated shows: "[moved to Roadrunner!] Michelle Branch" — the new venue lists it too
    if re.match(r"^\s*[\[\(]?\s*(moved|relocated)\s+to\b", t, re.I):
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

    # 7. Misleading commercial promo / fake free gym passes
    if re.search(r"\bfree\s+rock\s+climbing\b", t, re.I):
        return True

    # 8. Ongoing museum exhibits / static attraction listings spamming daily calendars
    if re.search(r"\b(rubies|pop\s+quiz:\s*1776|collecting\s+wonders|from\s+iran:\s*a\s+visual\s+testimony)\b", t, re.I):
        return True
    if re.search(r"^\s*(the\s+)?(peabody\s+museum|harvard\s+museum\s+of\s+(natural\s+history|the\s+ancient\s+near\s+east))\b", t, re.I) and not re.search(r"\btours?\b", t, re.I):
        return True
    if re.search(r"\bvolunteer\s+opportunities\s+everyday\b", t, re.I):
        return True

    return False


_DOUBLED_URL_SPLIT_RE = re.compile(r"(?<=[A-Za-z0-9/])(?=https?://)")


def fix_doubled_url(url):
    """Repair URLs where two absolute URLs got glued together
    (e.g. 'https://www.bso.orghttps://www.bso.org/events/x'). Keeps the last full URL.

    Only splits where the second scheme directly follows an alphanumeric or '/', so
    legitimate redirect/share links ('?u=https://...') are left untouched.
    """
    if not url or url.count("://") < 2:
        return url
    parts = [p for p in _DOUBLED_URL_SPLIT_RE.split(url) if p]
    return parts[-1] if len(parts) > 1 else url


# Domains that have lapsed or been taken over by unrelated sites (verified redirect targets).
DEAD_EVENT_DOMAINS = {
    "themillennialcrisis.com",  # Boston Social Conversations' old site; 404s since Nov 2026
    "thebiltmoregrill.com",  # now redirects to a brewery in Cortez, CO
}


# Paid spa/massage services posted as events: promos from massage businesses, hotel spa
# packages ("Spa After Dark", $145), members-club spa nights. Massage *classes* (CCAE,
# partner Thai massage workshops) and free wellness walks are real events and stay.
_SERVICE_AD_VENUE_RE = re.compile(r"\bmassage\b(?!.*\bschool\b)|\bmed\s*spa\b|\bremedy place\b", re.I)
_SERVICE_AD_TITLE_RE = re.compile(
    r"\bspa (?:night|after dark|day|package|weekend)\b|\breflexology experience\b|\bstress[- ]free week\b|"
    r"\b(?:botox|filler|iv (?:drip|therapy))\b",
    re.I,
)


def is_service_ad(name, venue=None):
    if _SERVICE_AD_TITLE_RE.search(name or ""):
        return True
    return bool(venue and _SERVICE_AD_VENUE_RE.search(venue))


def sanitize_event_url(url, fallback=None):
    """Return a usable absolute event URL, or `fallback` when the scraped link is broken:
    Cloudflare email-obfuscation paths, relative paths, or known-dead domains."""
    if not url:
        return fallback
    u = url.strip()
    if not re.match(r"^https?://", u, re.I) or "/cdn-cgi/l/email-protection" in u:
        return fallback
    host = re.sub(r"^https?://(?:www\.)?", "", u, flags=re.I).split("/")[0].split("?")[0].lower()
    if host in DEAD_EVENT_DOMAINS:
        return fallback
    return u


_EXHIBIT_URL_RE = re.compile(r"revolutionaryspaces\.org/explore/exhibits/", re.I)
_MUSEUMISH_VENUE_RE = re.compile(r"museum|athen|meeting\s+house|hall\s+of\s+fame|gallery|historical\s+society", re.I)
_GENERIC_CAMPAIGN_RE = re.compile(r"^\s*(?:winter\s+)?coat\s+drive\s*!?\s*$", re.I)


def is_standing_exhibit(e: dict) -> bool:
    """Detect permanent/long-running exhibits and campaigns that sources list as if they were
    daily events (an exhibit page is not something you attend at a specific time).

    Signals (any one):
      1. URL is an exhibit page on a known exhibit-hosting site (Revolutionary Spaces).
      2. Do617 listing whose URL start-date is >21 days before this occurrence, at a
         museum-type venue (a months-long run, e.g. a photography exhibition).
      3. Generic donation-campaign title with no specific time/place (e.g. "Winter Coat Drive").
    """
    url = e.get("url") or ""
    name = (e.get("name") or "").strip()
    if _EXHIBIT_URL_RE.search(url):
        return True
    if _GENERIC_CAMPAIGN_RE.match(name):
        return True
    m = re.search(r"do617\.com/events/(\d{4})/(\d{1,2})/(\d{1,2})/", url)
    raw = e.get("date")
    if m and raw and _MUSEUMISH_VENUE_RE.search(e.get("venue") or ""):
        try:
            start = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
            occ = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).date()
        except ValueError:
            return False
        if (occ - start).days > 21:
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


def _parse_eventbrite_server_data(html):
    """Extract high-fidelity events with exact start_time, end_time, and venue from window.__SERVER_DATA__."""
    m = re.search(r'window\.__SERVER_DATA__\s*=\s*(\{.*?\});\s*(?:window\.|</script>)', html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []

    def find_events(obj):
        found = []
        if isinstance(obj, dict):
            if 'eventbrite_event_id' in obj or ('start_date' in obj and 'start_time' in obj):
                found.append(obj)
            for v in obj.values():
                found.extend(find_events(v))
        elif isinstance(obj, list):
            for item in obj:
                found.extend(find_events(item))
        return found

    raw_events = find_events(data)
    events = []
    seen = set()

    for ev in raw_events:
        name = ev.get("name")
        u = ev.get("url")
        start_date = ev.get("start_date")
        start_time = ev.get("start_time") or "19:00"
        tz_str = ev.get("timezone") or "America/New_York"

        if not name or not u or not start_date:
            continue
        if u in seen:
            continue
        seen.add(u)

        try:
            dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
            try:
                dt = dt.replace(tzinfo=ZoneInfo(tz_str))
            except Exception:
                dt = dt.replace(tzinfo=EASTERN)
            iso = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            iso = None

        pv = ev.get("primary_venue") or {}
        venue_name = pv.get("name") if isinstance(pv, dict) else None
        addr = pv.get("address") or {} if isinstance(pv, dict) else {}
        lat = addr.get("latitude")
        lng = addr.get("longitude")

        price = None
        if ev.get("is_free"):
            price = "Free"
        else:
            ticket_avail = ev.get("ticket_availability") or {}
            min_price = ticket_avail.get("minimum_ticket_price") or {}
            if min_price.get("major_value"):
                try:
                    val = float(min_price["major_value"])
                    price = "Free" if val == 0 else f"${val:g}"
                except Exception:
                    pass

        events.append({
            "name": name,
            "date": iso,
            "url": u,
            "venue": venue_name,
            "price": price,
            "description": (ev.get("summary") or "")[:200],
            "lat": lat,
            "lng": lng,
        })
    return events


def _parse_eventbrite_json_ld(soup):
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
                # When date has no time, default to 19:00 (7 PM) Eastern rather than midnight,
                # and use dynamic EASTERN timezone so it never shifts days between EST/EDT
                try:
                    dt_naive = datetime.strptime(iso, "%Y-%m-%d").replace(hour=19, minute=0, tzinfo=EASTERN)
                    iso = dt_naive.astimezone(timezone.utc).isoformat()
                except ValueError:
                    iso = None
            elif iso:
                try:
                    iso = datetime.fromisoformat(iso).astimezone(timezone.utc).isoformat()
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


def scrape_eventbrite_search(url, ua):
    """Parse Eventbrite discovery page via embedded __SERVER_DATA__ and ItemList JSON-LD."""

    def fetch_eb_html(target_url):
        # No retry through another client when Eventbrite says no: that's dodging its bot check.
        try:
            resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
            if resp.status_code == 200 and len(resp.text) > 10000:
                return resp.text
        except Exception:
            pass
        return ""

    urls_to_scrape = [url]
    if "ma--boston/events" in url:
        subcategories = [
            "music--events/",
            "nightlife--events/",
            "arts--events/",
            "community--events/",
            "free--events/",
            "food-and-drink--events/",
        ]
        base_prefix = url.rstrip("/")
        if base_prefix.endswith("/events"):
            base_prefix = base_prefix[:-7]
        for sub in subcategories:
            urls_to_scrape.append(f"{base_prefix}/{sub}")

    all_events = []
    seen_urls = set()

    for target in urls_to_scrape:
        try:
            html = fetch_eb_html(target)
            if not html:
                continue

            # 1. Prefer high-fidelity __SERVER_DATA__ with exact start_time & end_time
            batch = _parse_eventbrite_server_data(html)

            # 2. Fall back to ItemList JSON-LD if __SERVER_DATA__ wasn't found
            if not batch:
                soup = BeautifulSoup(html, "html.parser")
                batch = _parse_eventbrite_json_ld(soup)

            for e in batch:
                u = e.get("url")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_events.append(e)
        except Exception:
            continue

    return all_events


_KIDS_AUDIENCE_RE = re.compile(r"\b(?:bab(?:y|ies)|toddlers?|pre-?school|kids?|child(?:ren)?|famil(?:y|ies)|"
                               r"early literacy|ages?\s*0|birth|grades?\s*k|elementary)\b", re.I)
_ADULT_AUDIENCE_RE = re.compile(r"\b(?:adults?|seniors?|older adults|teens?|young adults|tweens?)\b", re.I)


def scrape_bibliocommons(library, ua, weeks=4, max_pages=25):
    """Events for a BiblioCommons library (gateway API). The API ignores date/audience filters
    and returns events unordered, so read every page (200/page) and keep the next `weeks`.
    Adds the branch to the venue and marks baby/toddler/kids/family programs as "family"."""
    base = f"https://gateway.bibliocommons.com/v2/libraries/{library}/events"
    headers = {"User-Agent": ua, "Accept": "application/json"}
    now = datetime.now(EASTERN)
    horizon = now + timedelta(weeks=weeks)
    defs, locations, audiences = {}, {}, {}
    for page in range(1, max_pages + 1):
        resp = _SESSION.get(base, params={"page": page, "limit": 200}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        ents = data.get("entities") or {}
        for eid, ev in (ents.get("events") or {}).items():
            defs[eid] = ev.get("definition") or {}
        locations.update(ents.get("locations") or {})
        audiences.update(ents.get("eventAudiences") or {})
        pag = (data.get("events") or {}).get("pagination") or {}
        if page >= (pag.get("pages") or 0):
            break
    events = []
    for eid, d in defs.items():
        if d.get("isCancelled") or not d.get("start") or not d.get("title"):
            continue
        try:
            start = datetime.fromisoformat(d["start"]).replace(tzinfo=EASTERN)
        except ValueError:
            continue
        if not (now - timedelta(hours=2) <= start <= horizon):
            continue
        branch = (locations.get(str(d.get("branchLocationId"))) or {}).get("name")
        aud_names = [(audiences.get(a) or {}).get("name") or "" for a in d.get("audienceIds") or []]
        aud = " ".join(aud_names)
        kids = bool(_KIDS_AUDIENCE_RE.search(aud)) and not (
            _ADULT_AUDIENCE_RE.search(aud) and not re.search(r"(?i)famil", aud))
        ev = {
            "name": d["title"].strip(),
            "date": start.astimezone(timezone.utc).isoformat(),
            "url": f"https://{library}.bibliocommons.com/events/{eid}",
            "branch": branch,
            "price": "Free",
            "audience": aud_names or None,
        }
        if kids:
            ev["category"] = "family"
        events.append(ev)
    return events


# BPL branches: (match key in the BiblioCommons branch name, lat, lng, neighborhood, address).
# Coordinates are approximate (building-level).
_BPL_BRANCHES = [
    ("central", 42.3496, -71.0779, "Back Bay", "700 Boylston St, Boston"),
    ("copley", 42.3496, -71.0779, "Back Bay", "700 Boylston St, Boston"),
    ("adams street", 42.2856, -71.0573, "Dorchester", "690 Adams St, Dorchester"),
    ("faneuil", 42.3497, -71.1658, "Brighton", "419 Faneuil St, Brighton"),
    ("brighton", 42.3497, -71.1567, "Brighton", "40 Academy Hill Rd, Brighton"),
    ("charlestown", 42.3757, -71.0640, "Charlestown", "179 Main St, Charlestown"),
    ("chinatown", 42.3523, -71.0626, "Chinatown", "2 Boylston St, Boston"),
    ("codman", 42.2876, -71.0716, "Dorchester", "690 Washington St, Dorchester"),
    ("connolly", 42.3209, -71.1110, "Jamaica Plain", "433 Centre St, Jamaica Plain"),
    ("east boston", 42.3745, -71.0350, "East Boston", "365 Bremen St, East Boston"),
    ("egleston", 42.3133, -71.0989, "Roxbury", "2044 Columbus Ave, Roxbury"),
    ("fields corner", 42.3000, -71.0613, "Dorchester", "1520 Dorchester Ave, Dorchester"),
    ("grove hall", 42.3087, -71.0807, "Dorchester", "41 Geneva Ave, Dorchester"),
    ("honan", 42.3613, -71.1300, "Allston", "300 N Harvard St, Allston"),
    ("allston", 42.3613, -71.1300, "Allston", "300 N Harvard St, Allston"),
    ("hyde park", 42.2556, -71.1240, "Hyde Park", "35 Harvard Ave, Hyde Park"),
    ("jamaica plain", 42.3092, -71.1153, "Jamaica Plain", "30 South St, Jamaica Plain"),
    ("lower mills", 42.2722, -71.0679, "Dorchester", "27 Richmond St, Dorchester"),
    ("mattapan", 42.2706, -71.0931, "Mattapan", "1350 Blue Hill Ave, Mattapan"),
    ("north end", 42.3640, -71.0547, "North End", "25 Parmenter St, Boston"),
    ("orient heights", 42.3874, -71.0045, "East Boston", "18 Barnes Ave, East Boston"),
    ("parker hill", 42.3311, -71.1007, "Mission Hill", "1497 Tremont St, Roxbury"),
    ("roslindale", 42.2870, -71.1270, "Roslindale", "4246 Washington St, Roslindale"),
    ("dudley", 42.3289, -71.0837, "Roxbury", "149 Dudley St, Roxbury"),
    ("roxbury", 42.3289, -71.0837, "Roxbury", "149 Dudley St, Roxbury"),
    ("south boston", 42.3355, -71.0383, "South Boston", "646 E Broadway, South Boston"),
    ("south end", 42.3416, -71.0763, "South End", "685 Tremont St, Boston"),
    ("uphams", 42.3172, -71.0656, "Dorchester", "500 Columbia Rd, Dorchester"),
    ("west end", 42.3611, -71.0655, "West End", "151 Cambridge St, Boston"),
    ("west roxbury", 42.2843, -71.1599, "West Roxbury", "1961 Centre St, West Roxbury"),
]


def _bpl_branch_geo(branch):
    low = (branch or "").lower()
    # longest key first so "west roxbury" beats "roxbury", "faneuil" beats "brighton"
    for key, lat, lng, neigh, addr in sorted(_BPL_BRANCHES, key=lambda b: -len(b[0])):
        if key in low:
            return {"lat": lat, "lng": lng, "neighborhood": neigh, "address": addr}
    return None


def scrape_bpl(url, ua):
    """Boston Public Library (Central + 25 branches) via BiblioCommons, with each branch's
    own pin and neighborhood instead of everything at Copley."""
    events = scrape_bibliocommons("bpl", ua, weeks=3)
    for e in events:
        br = e.pop("branch", None)
        e["venue"] = f"Boston Public Library ({br})" if br else "Boston Public Library"
        geo = _bpl_branch_geo(br)
        if geo:
            e.update(geo)
    return events


def scrape_brookline_library(url, ua):
    """Public Library of Brookline (Main, Coolidge Corner, Putterham): LibCal RSS, same feed
    format as Cambridge's. Drops room-booking placeholders ("space unavailable")."""
    out = []
    for e in scrape_cpl(url, ua):
        if re.match(r"(?i)\s*(space unavailable|closed|room reserved)\b", e.get("name") or ""):
            continue
        e["venue"] = re.sub(r"^Cambridge Public Library", "Brookline Public Library", e.get("venue") or "Brookline Public Library")
        out.append(e)
    return out


def scrape_boston_childrens_museum(url, ua):
    """Boston Children's Museum: event posts (EventON) from the WordPress API; start time from
    each page's JSON-LD (offsets written "-5:00", which fromisoformat rejects)."""
    from concurrent.futures import ThreadPoolExecutor
    posts = _SESSION.get(url, params={"per_page": 60}, headers={"User-Agent": ua}, timeout=20).json()
    now = datetime.now(timezone.utc)

    def one(post):
        link = post.get("link")
        try:
            html = _SESSION.get(link, headers={"User-Agent": ua}, timeout=20).text
        except Exception:
            return []
        out = []
        for m in re.finditer(r'"startDate"\s*:\s*"(\d{4}-\d{2}-\d{2})T(\d{1,2}):(\d{2})([+-])(\d{1,2}):?(\d{2})"', html):
            d, hh, mm, sign, oh, om = m.groups()
            iso = f"{d}T{int(hh):02d}:{mm}:00{sign}{int(oh):02d}:{om}"
            try:
                dt = datetime.fromisoformat(iso)
            except ValueError:
                continue
            if dt < now - timedelta(hours=2):
                continue
            out.append({
                "name": _html_unescape(_html_unescape((post.get("title") or {}).get("rendered") or "")).strip(),
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": link,
                "venue": "Boston Children's Museum",
                "price": None,
                "category": "family",
            })
        return out

    with ThreadPoolExecutor(max_workers=4) as ex:
        events = [e for evs in ex.map(one, posts if isinstance(posts, list) else []) for e in evs if e["name"]]
    seen, uniq = set(), []
    for e in events:
        k = (e["name"], e["date"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    return uniq


def scrape_puppet_showplace(url, ua):
    """Puppet Showplace Theater (Brookline Village): Squarespace calendar of family shows."""
    out = []
    for e in scrape_squarespace(url, ua):
        e["venue"] = "Puppet Showplace Theater"
        # adult "Puppet Slams" and workshops aren't kids' shows
        try:
            evening = datetime.fromisoformat(e["date"]).astimezone(EASTERN).hour >= 19
        except (KeyError, TypeError, ValueError):
            evening = False
        name = e.get("name") or ""
        if re.search(r"(?i)\binfo session\b|\bvolunteer\b", name):
            e["category"] = "community"
        elif evening or re.search(r"(?i)\bslam\b|\b(?:18|21)\+|adults?\b|workshop", name):
            e["category"] = "theater"  # evening shows and slams are for grown-ups
        else:
            e["category"] = "family"
        out.append(e)
    return out


_LM_DAY_RE = re.compile(r"^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY),?\s+([A-Za-z]+)\s+(\d{1,2})", re.I)
_LM_TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(AM|PM)", re.I)


def _little_muse_posts(base, ua, posts):
    """Latest posts as {post_date, body_html, canonical_url}. The RSS feed carries each post's
    full HTML and is served to GitHub's runners, which Substack's JSON API refuses (it answers
    them with a non-JSON page); the API is the fallback."""
    out = []
    try:
        r = _SESSION.get(f"{base}/feed", headers={"User-Agent": ua, "Accept": "application/rss+xml, application/xml"}, timeout=20)
        r.raise_for_status()
        for item in re.findall(r"<item>(.*?)</item>", r.text, re.S)[:posts]:
            body = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", item, re.S)
            link = re.search(r"<link>(.*?)</link>", item)
            when = re.search(r"<pubDate>(.*?)</pubDate>", item)
            if not (body and when):
                continue
            out.append({
                "post_date": parsedate_to_datetime(when.group(1).strip()).astimezone(EASTERN).date(),
                "body_html": body.group(1),
                "canonical_url": link.group(1).strip() if link else base,
            })
    except Exception:
        out = []
    if out:
        return out
    headers = {"User-Agent": ua, "Accept": "application/json"}
    archive = _SESSION.get(f"{base}/api/v1/archive", params={"sort": "new", "limit": posts},
                           headers=headers, timeout=20).json()
    for meta in archive[:posts]:
        if meta.get("audience") not in (None, "everyone"):
            continue
        post = _SESSION.get(f"{base}/api/v1/posts/{meta['slug']}", headers=headers, timeout=20).json()
        out.append({
            "post_date": datetime.fromisoformat(post["post_date"].replace("Z", "+00:00")).astimezone(EASTERN).date(),
            "body_html": post.get("body_html"),
            "canonical_url": post.get("canonical_url"),
        })
    return out


def scrape_little_muse(url, ua, posts=3):
    """Little Muse (littlemuse.substack.com): a free weekly newsletter of kids' events around
    Cambridge/Somerville/Boston. Each listing is three <br>-separated lines:
      "🎃 10:00-11:00 AM - <a>Title</a> (ages 0-5) ~22 min 💲✱"
      "Venue, Street Address, Town"
      "Description."
    Listings link to the original event page, so copies of events we already scrape (libraries)
    merge with ours by URL; Little Muse shows as a source on the card."""
    now = datetime.now(EASTERN)
    events = []
    for post in _little_muse_posts(url.rstrip("/"), ua, posts):
        post_date = post["post_date"]
        soup = BeautifulSoup(post.get("body_html") or "", "html.parser")
        day = None
        for el in soup.find_all(["h2", "h3", "p"]):
            text = el.get_text(" ", strip=True)
            if el.name == "h2":
                day = None  # e.g. "All Week / Multi-Day": ongoing things, no single date
                m = _LM_DAY_RE.match(text)
                if m:
                    mon = next((v for k, v in _MONTHS.items() if k.startswith(m.group(2).lower()[:3])), None)
                    if mon:
                        year = post_date.year + (1 if mon < post_date.month - 6 else 0)  # Dec post, Jan days
                        try:
                            day = date(year, mon, int(m.group(3)))
                        except ValueError:
                            day = None
                continue
            if el.name != "p" or day is None:
                continue
            link = el.find("a")
            parts = [p.strip() for p in re.split(r"<br\s*/?>", el.decode_contents())]
            if not link or len(parts) < 2:
                continue
            first = BeautifulSoup(parts[0], "html.parser").get_text(" ", strip=True)
            tm = _LM_TIME_RE.search(first)
            if not tm:
                continue
            h, mnt = int(tm.group(1)), int(tm.group(2) or 0)
            ampm = (tm.group(3) or tm.group(4)).upper()
            h = h % 12 + (12 if ampm == "PM" else 0)
            start = datetime(day.year, day.month, day.day, h, mnt, tzinfo=EASTERN)
            if not (now - timedelta(hours=3) <= start <= now + timedelta(days=10)):
                continue
            title = link.get_text(" ", strip=True)
            ages = re.search(r"\((ages?[^)]*|all ages)\)", first, re.I)
            where = BeautifulSoup(parts[1], "html.parser").get_text(" ", strip=True)
            desc = BeautifulSoup(parts[2], "html.parser").get_text(" ", strip=True) if len(parts) > 2 else ""
            bits = [b.strip() for b in where.split(",")]
            # venue = leading parts until one starts with a street number ("123 Main St")
            i = next((k for k, b in enumerate(bits) if re.match(r"\d", b)), len(bits))
            venue = ", ".join(bits[:i]) or where
            address = ", ".join(bits[i:]) if i < len(bits) else None
            town = re.sub(r"\s*\(.*?\)\s*$", "", bits[-1]) if len(bits) > 1 else None
            price = None
            if "💲" in first:
                pm = re.search(r"\$\d+(?:\.\d{2})?", desc)
                price = f"{pm.group(0)}+" if pm else "Paid"
            elif re.search(r"(?i)\bfree\b", desc):
                price = "Free"
            ev = {
                "name": title,
                "date": start.astimezone(timezone.utc).isoformat(),
                "url": link.get("href"),
                "venue": venue,
                "price": price,
                "category": "family",
                "description": (f"({ages.group(1)}) " if ages else "") + desc[:220],
                "via_url": post.get("canonical_url"),
            }
            if address:
                ev["address"] = address
            if town and not re.match(r"\d", town):
                ev["locality"] = town
            events.append(ev)
    return events


def scrape_town_library_kids(url, ua, library, town):
    """Kids/family programs only from a nearby town's Assabet library calendar (same platform
    as Somerville's). Their adult programs would flood the Outer Suburbs group."""
    out = []
    for e in scrape_somerville_library(url, ua):
        if e.get("category") != "family" and not is_kid_family_event(e.get("name"), None):
            continue
        if _teen_only(e.get("name")):
            continue
        branch = re.sub(r"^Somerville Public Library\s*\(?|\)$", "", e.get("venue") or "").strip()
        # single-branch libraries report their own name as the branch
        same = (not branch or town.lower() in branch.lower() or branch.lower() == "somerville public library"
                or library.lower() in branch.lower() or branch.lower() in library.lower())
        e["venue"] = library if same else f"{library} ({branch})"
        e["locality"] = town  # card shows "Watertown", not "Outer Suburbs"
        e["category"] = "family"
        out.append(e)
    return out


def scrape_watertown_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Watertown Free Public Library", "Watertown")


def scrape_medford_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Medford Public Library", "Medford")


def scrape_belmont_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Belmont Public Library", "Belmont")


def scrape_malden_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Malden Public Library", "Malden")


def scrape_waltham_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Waltham Public Library", "Waltham")


def scrape_quincy_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Thomas Crane Public Library", "Quincy")


def scrape_lexington_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Cary Memorial Library", "Lexington")


def scrape_melrose_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Melrose Public Library", "Melrose")


def scrape_revere_library_kids(url, ua):
    return scrape_town_library_kids(url, ua, "Revere Public Library", "Revere")


def scrape_libcal_town_kids(url, ua, library, town):
    """Kids/family programs only from a nearby town's LibCal calendar (the RSS format Cambridge's
    scraper reads). Adult programs would flood the Outer Suburbs group."""
    out = []
    for e in scrape_cpl(url, ua):
        if e.get("category") != "family" and not is_kid_family_event(e.get("name"), None):
            continue
        if _teen_only(e.get("name")):
            continue
        m = re.match(r"Cambridge Public Library \((.*)\)$", e.get("venue") or "")
        campus = (m.group(1) if m else "").strip()
        if "virtual" in campus.lower() or "online" in campus.lower():
            continue
        main = not campus or campus.lower() in ("main library", library.lower()) or library.lower() in campus.lower()
        e["venue"] = library if main else f"{library} ({campus})"
        e["locality"] = town
        e["category"] = "family"
        out.append(e)
    return out


def scrape_newton_library_kids(url, ua):
    return scrape_libcal_town_kids(url, ua, "Newton Free Library", "Newton")


def scrape_milton_library_kids(url, ua):
    return scrape_libcal_town_kids(url, ua, "Milton Public Library", "Milton")



def scrape_mass_audubon(url, ua, venue, address):
    """Mass Audubon center program list -> each program page's JSON-LD. Family/kids programs
    (by title or description) go to Kids & Family, the rest to outdoors."""
    from concurrent.futures import ThreadPoolExecutor
    html = _SESSION.get(url, headers={"User-Agent": ua}, timeout=20).text
    path = urlparse(url).path.rstrip("/")
    links = sorted({urljoin(url, h) for h in re.findall(r'href="(%s/\d+[^"#?]*)"' % re.escape(path), html)})

    def one(link):
        try:
            evs = scrape_jsonld(link, ua)
        except Exception:
            return []
        try:
            page = _SESSION.get(link, headers={"User-Agent": ua}, timeout=20).text
            m = re.search(r'"description"\s*:\s*"([^"]{0,600})', page)
            desc = _html_unescape(m.group(1)) if m else ""
        except Exception:
            desc = ""
        out = []
        for e in evs:
            if not e.get("date"):
                continue
            blob = f"{e.get('name')} {desc}"
            e["url"] = link  # the JSON-LD has no url; each program page is its own event
            e["venue"] = venue
            e["address"] = address
            e["category"] = "family" if re.search(r"(?i)\b(?:famil(?:y|ies)|kids?|children|toddlers?|preschool|ages? \d)", blob) else "outdoors"
            out.append(e)
        return out

    with ThreadPoolExecutor(max_workers=3) as ex:
        return [e for evs in ex.map(one, links[:20]) for e in evs]


def scrape_mass_audubon_magazine_beach(url, ua):
    return scrape_mass_audubon(url, ua, "Mass Audubon Nature Center at Magazine Beach", "668 Memorial Dr, Cambridge")


def scrape_mass_audubon_boston_nature_center(url, ua):
    return scrape_mass_audubon(url, ua, "Mass Audubon Boston Nature Center", "500 Walk Hill St, Mattapan")


def scrape_mass_audubon_habitat(url, ua):
    evs = scrape_mass_audubon(url, ua, "Mass Audubon Habitat Education Center", "10 Juniper Rd, Belmont")
    for e in evs:
        e["locality"] = "Belmont"
    return evs


def scrape_mass_audubon_drumlin_farm(url, ua):
    """Drumlin Farm in Lincoln: the working farm families drive out to (barnyard programs,
    hayrides, farm walks)."""
    evs = scrape_mass_audubon(url, ua, "Mass Audubon Drumlin Farm", "208 S Great Rd, Lincoln")
    for e in evs:
        e["locality"] = "Lincoln"
    return evs


_EB_FAMILY_RE = re.compile(
    r"(?i)\b(?:tots?|toddlers?|bab(?:y|ies)|babywearing|littles|kids?|children|famil(?:y|ies)|"
    r"daddy|mommy|father|mother|parents? (?:&|and) (?:child|kid|caregiver)|youth|girls|boys)\b")
_EB_FAMILY_SKIP_RE = re.compile(
    r"(?i)\b(?:cpr|aed|first aid|certification|webinar|online|virtual|coaching|breakthrough|"
    r"retreat|adult child|pregnan)")


def scrape_cafe_zing(url, ua):
    """Cafe Zing (inside Porter Square Books): live music, songwriter rounds, craft and chess nights."""
    events = scrape_squarespace_events(url, ua)
    for e in events:
        e["venue"] = "Cafe Zing"
        e["address"] = "25 White St, Cambridge"
        e["locality"] = "Cambridge"
    return events


def scrape_ikeda_center(url, ua):
    """Ikeda Center's Eventbrite (its own event pages block scripts); Eventbrite omits the address."""
    events = scrape_eventbrite_org(url, ua)
    for e in events:
        e["venue"] = "Ikeda Center"
        e["address"] = "396 Harvard St, Cambridge"
        e["locality"] = "Cambridge"
    return events


def scrape_eventbrite_family(url, ua):
    """Eventbrite's "parent" search: keep in-person outings for kids and families; drop
    the plant classes, parenting webinars, coaching pitches and certification courses it mixes in."""
    out = []
    for e in scrape_eventbrite_search(url, ua):
        name = e.get("name") or ""
        if not e.get("venue") or not _EB_FAMILY_RE.search(name) or _EB_FAMILY_SKIP_RE.search(name):
            continue
        e["category"] = "family"
        out.append(e)
    return out


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


TBC_DETAILS_CACHE_PATH = os.path.join(CACHE_DIR, "tbc_details_cache.json")
# Detail pages read per run, soonest events first. A cold cache fills in over a few days instead
# of 1,000 requests at once.
TBC_DETAILS_PER_RUN = 150


def _load_tbc_details_cache():
    if not os.path.exists(TBC_DETAILS_CACHE_PATH):
        return {}
    try:
        with open(TBC_DETAILS_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_tbc_details_cache(cache_dict):
    try:
        with open(TBC_DETAILS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_dict, f)
    except Exception:
        pass


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
            return None, None, None
    if soup is None:
        return None, None, None
    ext_url = None
    price = None
    where_url = None
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
        elif "where" in label and not where_url:
            u = _bc_extract_url_from_p(p)
            if u and not any(m in u for m in ["google.com/maps", "maps.google.com", "openstreetmap"]):
                where_url = u

    if not ext_url and where_url:
        ext_url = where_url

    addr = None
    street = soup.find(attrs={"itemprop": "streetAddress"})
    locality = soup.find(attrs={"itemprop": "addressLocality"})
    postal = soup.find(attrs={"itemprop": "postalCode"})
    if street or locality:
        addr = {
            "street": street.get_text(" ", strip=True) if street else "",
            "locality": locality.get_text(" ", strip=True).title() if locality else "",
            "postal": postal.get_text(" ", strip=True) if postal else "",
        }
        if not addr["postal"]:
            m = re.search(r"\b(0\d{4})\b", (soup.find(attrs={"itemprop": "address"}) or soup).get_text(" ", strip=True)[:4000])
            addr["postal"] = m.group(1) if m else ""

    if not ext_url:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith("http"):
                continue
            if any(k in href for k in ["thebostoncalendar.com", "facebook.com/sharer", "twitter.com", "instagram.com"]):
                continue
            text = a.get_text(" ", strip=True).lower()
            if any(k in text for k in [
                "buy ticket", "get ticket", "ticket", "event website", "official website",
                "more info", "register", "sign up", "reserve", "details", "learn more", "enroll"
            ]):
                ext_url = href
                break

    return fix_doubled_url(ext_url), price, addr


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
    r"|skip\s+the\s+(traffic|drive)\b"
    r"|\bfree\s+rock\s+climbing\b"
    r"|\b(rubies|pop\s+quiz:\s*1776|collecting\s+wonders)\b"
    r"|volunteer\s+opportunities\s+everyday",
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
            venue_txt = loc_el.get_text(strip=True) if loc_el else None
            if is_service_ad(name, venue_txt):
                continue
            price = None
            if _BC_FREE_RE.search(name):
                price = "Free"
            entry = {
                "name": name,
                "date": iso,
                "url": href,
                "venue": venue_txt,
                "price": price,
                "_bc_url": href,
                "_price_from_title": bool(price),
            }
            until = _BC_GOES_UNTIL_RE.search(raw_time)
            if iso is None and until:
                end_month, end_day = int(until.group(1)), int(until.group(2))
                end_year = d.year + (1 if end_month < d.month else 0)
                entry["ends"] = f"{end_year:04d}-{end_month:02d}-{end_day:02d}"
            events.append(entry)
    if events:
        cache = _load_tbc_details_cache()

        # 1. Apply existing cached details immediately
        for e in events:
            u = e.get("_bc_url")
            if u and u in cache:
                _bc_apply_details(e, cache[u])

        # 2. Identify uncached events still pointing to thebostoncalendar.com
        def _bc_sort_key(e):
            d = e.get("date")
            v = (e.get("venue") or "").lower()
            # Prioritize specific venues (like CCAE) and near-term dates
            is_pri = 0 if any(k in v for k in ["ccae", "cambridge center", "museum", "theater", "theatre"]) else 1
            return (is_pri, d if d else "9999")

        # Uncached, or cached before addresses were captured (no "addr_v")
        uncached = [e for e in events if e.get("_bc_url") and (e["_bc_url"] not in cache or "addr_v" not in cache[e["_bc_url"]])]
        sorted_uncached = sorted(uncached, key=_bc_sort_key)
        batch = sorted_uncached[:TBC_DETAILS_PER_RUN]  # the rest fill in on later runs

        if batch:
            with ThreadPoolExecutor(max_workers=2) as ex:
                urls_to_fetch = [e["_bc_url"] for e in batch]
                details = list(ex.map(lambda u: _bc_detail_info(u, ua), urls_to_fetch))

            for e, res in zip(batch, details):
                ext, p, addr = res if res else (None, None, None)
                if ext is None and p is None and addr is None and e["_bc_url"] in cache:
                    continue  # fetch failed; keep the older cache entry
                cache[e["_bc_url"]] = {
                    "url": ext,
                    "price": p,
                    "addr": addr,
                    "addr_v": 1,
                    "ts": time.time(),
                }
                _bc_apply_details(e, cache[e["_bc_url"]])

            _save_tbc_details_cache(cache)
    for e in events:
        e.pop("_bc_url", None)
        e.pop("_price_from_title", None)
    return events


# Titles that say nothing about the event ("Book Event"); use the ticket page's slug instead.
_BC_GENERIC_TITLE_RE = re.compile(
    r"^\s*(?:(?:book|author|music|art|film|community|special|private|live)\s+)?(?:event|talk|show|night|reading)s?\s*$",
    re.I,
)
# "Free" in a title means admission, not "stress-free", "gluten-free", "feel free" or a band
# called "Dogs Run Free".
_BC_FREE_RE = re.compile(
    r"(?<![\w-])(?<!stress )(?<!gluten )(?<!sugar )(?<!dairy )(?<!alcohol )(?<!care )(?<!cruelty )(?<!fragrance )"
    r"(?<!feel )(?<!run )(?<!runs )(?<!born )"
    r"(?:free|no cover|complimentary)\b(?!\s*(?:week|zone|spirit|style|flow|form|hold))",
    re.I,
)


def mentions_free(text):
    """True when text says getting in is free ("Free show", "no cover"), not "Freebo" or "gluten-free"."""
    return bool(_BC_FREE_RE.search(text or ""))


# A dollar amount that is the price of getting in ("$10 cover", "Tickets: $15", "$5 Tickets",
# "$10 CASH OR VENMO", "$15.00 + fee"), not a prize, a menu price or a fundraising total.
# One amount or a run of them: "$15", "$40 & $30", "$20 - $30", "$10/$15".
_PRICE_GROUP = r"\$\s?\d{1,3}(?:\.\d{2})?(?![\d,])(?:\s*(?:&|/|-|–|or|and)\s*\$?\s?\d{1,3}(?:\.\d{2})?(?![\d,]))*"
_ADMISSION_PRICE_RE = re.compile(
    r"(" + _PRICE_GROUP + r")(?=\s+to (?:enter|attend|play|join|register)\b|[^.!?\n$]{0,20}?(?<!\w)(?:cover|tickets?|"
    r"admission|entry|entrance|at the door|doors?|cash|venmo|\+\s*fees?|fees?|in advance|advance|adv|per person)\b)"
    r"|(?<!\w)(?:cover(?: charge)?|tickets?|admission|entry|entrance|cost|price)\b[^.!?\n$\d]{0,15}(" + _PRICE_GROUP + r")",
    re.I,
)


def admission_price(text):
    """'$10 CASH ONLY cover' -> '$10'; 'Tickets $15 adv / $20 door' -> '$15–$20'; None if no admission price."""
    amounts = sorted({float(a) for m in _ADMISSION_PRICE_RE.finditer(text or "")
                      for a in re.findall(r"\d{1,3}(?:\.\d{2})?", m.group(1) or m.group(2))} - {0.0})
    if not amounts:
        return None
    fmt = lambda v: f"${v:g}" if v == int(v) else f"${v:.2f}"
    return fmt(amounts[0]) if len(amounts) == 1 else f"{fmt(amounts[0])}–{fmt(amounts[-1])}"


def _title_from_ticket_slug(url):
    """'.../e/author-talk-with-seamus-boshell-tickets-2003750302093' -> 'Author Talk With Seamus Boshell'."""
    m = re.search(r"eventbrite\.[a-z.]+/e/([a-z0-9-]+?)-tickets-\d+", url or "", re.I)
    if not m:
        return None
    words = m.group(1).split("-")
    small = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
    return " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(words))


def _bc_apply_details(e, info):
    """Merge a Boston Calendar detail-page record (external URL, admission, address) into e."""
    if info.get("url"):
        e["url"] = info["url"]
    p = info.get("price")
    if p and (not e.get("price") or e.get("_price_from_title")):
        e["price"] = p  # the listed admission beats a "free" guessed from the title
    addr = info.get("addr") or {}
    if addr.get("street") or addr.get("locality"):
        e["address"] = ", ".join(x for x in (addr.get("street"), addr.get("locality")) if x)
        if addr.get("locality"):
            e["locality"] = addr["locality"]
        if addr.get("postal"):
            e["postal_code"] = addr["postal"]
    if _BC_GENERIC_TITLE_RE.match(e.get("name") or ""):
        better = _title_from_ticket_slug(e.get("url"))
        if better:
            e["name"] = better


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

        show_url = s.get("externalTicketURL") or (f"https://tunehatch.com/shows/{slug_s}" if slug_s else "https://thecantablounge.com/")
        events.append({
            "name": name,
            "date": when.astimezone(timezone.utc).isoformat(),
            "url": show_url,
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
    Fetches official RSS/XML feed (/events/feed.xml) first for speed and resilience,
    falls back to multi-month HTML article markup, and for Harvard Book Store merges
    its Eventbrite organizer feed for ticket prices and offsite locations.
    """
    import html as html_lib
    now_est = datetime.now(EASTERN)
    today_start = datetime(now_est.year, now_est.month, now_est.day, 0, 0, tzinfo=EASTERN)

    base_url = url.split("?")[0].rstrip("/")
    base_url = re.sub(r"/\d{4}/\d{1,2}$", "", base_url)
    feed_url = f"{base_url}/feed.xml"

    events = []
    seen = set()

    # 1. Multi-month HTML article.event-list markup
    page_urls = [base_url]
    y_cur, m_cur = now_est.year, now_est.month
    for _ in range(2):
        m_cur += 1
        if m_cur > 12:
            m_cur = 1
            y_cur += 1
        page_urls.append(f"{base_url}/{y_cur}/{m_cur:02d}")

    for page_url in page_urls:
        try:
            soup = fetch_soup(page_url, ua)
        except Exception:
            continue  # refused (Porter Square Books answers 403) or down: no retry through curl

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

            title_str = html_lib.unescape(a.get_text(strip=True))
            title_str = re.sub(r"^\*{1,3}SOLD OUT\*{1,3}\s*", "", title_str, flags=re.I).strip()
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

            tags = [t.get_text(strip=True).lower() for t in art.select(".event-tag__term, .event-list__tags a")]
            price = None
            if "free" in tags:
                price = "Free"
            body = art.select_one(".event-list__body")
            body_text = body.get_text(" ", strip=True) if body else ""
            art_text = art.get_text(" ", strip=True)
            if not price:
                p = re.search(r"(\$\d+(?:\.\d{2})?(?:\s*[–-]\s*\$?\d+(?:\.\d{2})?)?|\bFree\b)", body_text + " " + art_text)
                if p:
                    price = "Free" if p.group(1).lower() == "free" else p.group(1)
            if not price and "harvard" in url.lower() and venue_name is None:
                price = "Free"

            key = (title_str.lower()[:30], (iso or "")[:10])
            if key in seen:
                for ev in events:
                    if (ev["name"].lower()[:30], (ev["date"] or "")[:10]) == key:
                        if not ev.get("price") and price:
                            ev["price"] = price
                        break
                continue
            seen.add(key)

            events.append({
                "name": title_str,
                "date": iso,
                "url": urljoin(url, href),
                "venue": venue_name,
                "price": price,
            })

    # 2. Resilient fallback: Try official Drupal XML feed (/events/feed.xml) if HTML yielded no events
    if not events:
        feed_text = None
        try:
            r = _SESSION.get(
                feed_url,
                headers={
                    "User-Agent": ua or UA_CURL,
                    "Accept": "application/xml,text/xml,*/*;q=0.9",
                },
                timeout=10,
            )
            if r.status_code == 200 and "<item>" in r.text:
                feed_text = r.text
        except Exception:
            pass


        if feed_text:
            items = re.findall(r"<item>(.*?)</item>", feed_text, re.DOTALL)
            for it in items:
                m_title = re.search(r"<title>(.*?)</title>", it)
                if not m_title:
                    continue
                title = html_lib.unescape(m_title.group(1).strip())
                title = re.sub(r"^\*{1,3}SOLD OUT\*{1,3}\s*", "", title, flags=re.I).strip()

                m_date = re.search(r"<eventdate>(.*?)</eventdate>", it, re.I)
                date_str = m_date.group(1).strip() if m_date else ""

                m_link = re.search(r"<link>(.*?)</link>", it, re.I)
                link = m_link.group(1).strip() if m_link else ""

                m_loc = re.search(r"<location>(.*?)</location>", it, re.I | re.DOTALL)
                loc_str = " ".join(m_loc.group(1).split()) if m_loc else ""

                m_desc = re.search(r"<description>(.*?)</description>", it, re.I | re.DOTALL)
                desc_str = html_lib.unescape(m_desc.group(1).strip()) if m_desc else ""

                iso = None
                if date_str:
                    cleaned_d = re.sub(r"^[A-Za-z]+,\s*", "", date_str)
                    for fmt in ("%B %d, %Y - %I:%M%p", "%b %d, %Y - %I:%M%p", "%B %d, %Y - %I:%M %p"):
                        try:
                            dt = datetime.strptime(cleaned_d, fmt).replace(tzinfo=EASTERN)
                            if dt < today_start:
                                break
                            iso = dt.astimezone(timezone.utc).isoformat()
                            break
                        except ValueError:
                            pass
                if not iso:
                    continue

                venue_name = None
                if loc_str:
                    loc_l = loc_str.lower()
                    u_l = url.lower()
                    if "harvard" in u_l:
                        if "brattle" in loc_l:
                            venue_name = "The Brattle Theatre"
                        elif "cambridge public library" in loc_l:
                            venue_name = "Cambridge Public Library"
                        elif "science center" in loc_l:
                            m_hall = re.search(r"(Harvard Science Center[^,]*|Science Center[^,]*)", loc_str)
                            venue_name = m_hall.group(1).strip() if m_hall else "Harvard Science Center"
                        elif "first parish" in loc_l:
                            venue_name = "First Parish Church"
                        elif "harvard book store" in loc_l or "1256 massachusetts" in loc_l:
                            venue_name = None
                        else:
                            venue_name = loc_str.split("1256")[0].strip() or None
                    elif "brookline" in u_l:
                        if "brookline booksmith" in loc_l or "279 harvard" in loc_l:
                            venue_name = None
                        else:
                            first_part = re.split(r"\d+\s+[A-Za-z]", loc_str)[0].strip()
                            venue_name = first_part or None
                    elif "trident" in u_l:
                        if "trident" in loc_l or "338 newbury" in loc_l:
                            venue_name = None
                        else:
                            first_part = re.split(r"\d+\s+[A-Za-z]", loc_str)[0].strip()
                            venue_name = first_part or None

                price = None
                p = re.search(r"(\$\d+(?:\.\d{2})?(?:\s*[–-]\s*\$?\d+(?:\.\d{2})?)?|\bFree\b)", desc_str)
                if p:
                    price = "Free" if p.group(1).lower() == "free" else p.group(1)
                elif "harvard" in url.lower() and venue_name is None:
                    price = "Free"

                key = (title.lower()[:30], iso[:10])
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title,
                    "date": iso,
                    "url": link or url,
                    "venue": venue_name,
                    "price": price,
                })

    # 3. For Harvard Book Store, also merge their official Eventbrite organizer feed for ticket prices
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
        link = sanitize_event_url((row.get("tickets") or row.get("extlink") or "").strip(),
                                  fallback="https://www.aeronautbrewing.com/visit/somerville/#events")
        events.append({
            # "Boston Social Conversations | Millennial Crisis": organizer suffix, not part of the name
            "name": re.sub(r"\s*\|\s*millennial crisis\s*$", "", row.get("name") or "Event", flags=re.I),
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
    """Brattle Theatre screenings. /coming-soon/ lists each film (.show-details) with its showtimes,
    grouped by day (li[data-date] = that day's UTC-midnight timestamp, link text '7:00 pm')."""
    soup = fetch_soup("https://brattlefilm.org/coming-soon/", ua)
    events, seen = [], set()
    now = datetime.now(EASTERN)
    for film in soup.select(".show-details"):
        h = film.find(["h2", "h3"])
        if not h:
            continue
        title = h.get_text(" ", strip=True)
        page = film.select_one("a[href*='/movies/']")
        for li in film.select("li[data-date]"):
            try:
                day = datetime.fromtimestamp(int(li["data-date"]), tz=timezone.utc).date()
            except (TypeError, ValueError):
                continue
            for a in li.select("a[data-showtime_id]"):
                if a["data-showtime_id"] in seen:
                    continue
                hm = _clock(a.get_text(" ", strip=True))
                if not hm:
                    continue
                dt = datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=EASTERN)
                if dt < now - timedelta(hours=3):
                    continue
                seen.add(a["data-showtime_id"])
                events.append({
                    "name": title,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": page["href"] if page else urljoin(url, a.get("href", "")),
                    "venue": "Brattle Theatre",
                    "price": None,
                    "category": "film",
                })
    return events


def scrape_ica(url, ua):
    """Scrape events from ICA Boston (including ICA Free Thursday Night, First Fridays, Tours, and Talks)."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    for node in soup.select(".node-event"):
        a = node.select_one("h3 a") or node.select_one("a[href*='/events/']")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        href = a.get("href", "")
        ev_url = urljoin(url, href)

        text = node.get_text(separator=" | ", strip=True)
        is_free = "Free" in text

        # Find dates like 'Thu, Oct 29, 5–9 PM' or 'Sat, Oct 31, 11 AM–3 PM' or 'Sun, Nov 1, 10 AM'
        date_matches = re.findall(
            r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Za-z]+)\s+(\d{1,2})(?:,\s+(\d{4}))?(?:,\s+(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?(?:[–-]\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))?))?',
            text
        )

        for m in date_matches:
            month_s, day_s, year_s, time_s = m
            yr = int(year_s) if year_s else now.year
            start_t = "12:00 PM"
            if time_s:
                ampm_m = re.search(r'(AM|PM|am|pm)', time_s, re.IGNORECASE)
                default_ampm = ampm_m.group(1).upper() if ampm_m else "PM"
                parts = re.split(r'[–-]', time_s)
                start_raw = parts[0].strip()
                if not re.search(r'[a-zA-Z]', start_raw):
                    start_raw = f"{start_raw} {default_ampm}"
                start_t = start_raw

            dt = None
            for fmt in ("%b %d %Y %I %p", "%b %d %Y %I:%M %p", "%B %d %Y %I %p", "%B %d %Y %I:%M %p"):
                try:
                    dt = datetime.strptime(f"{month_s} {day_s} {yr} {start_t}", fmt).replace(tzinfo=EASTERN)
                    break
                except Exception:
                    pass

            if not dt:
                continue

            iso_date = dt.astimezone(timezone.utc).isoformat()
            key = (title.lower(), iso_date[:10])
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "name": html.unescape(title).strip()[:160],
                "date": iso_date,
                "url": ev_url,
                "venue": "ICA Boston",
                "price": "Free" if is_free else None,
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
            "url": urljoin("https://www.bso.org", link) if link else "https://www.bso.org/events",
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


def _clean_ical_description(desc):
    if not desc:
        return None
    # Strip WordPress / WPBakery / Visual Composer shortcodes like [vc_row ...], [/vc_row]
    text = re.sub(r'\[/?[a-zA-Z0-9_-]+[^\]]*\]', ' ', desc)
    # Strip any remaining unclosed or broken brackets
    text = re.sub(r'\[[^\]]*\]?', ' ', text)
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Clean unescaped iCal backslashes
    text = text.replace(r'\,', ',').replace(r'\;', ';').replace(r'\n', ' ')
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:250] if text else None


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
        clean_desc = _clean_ical_description(desc)
        price = None
        if re.search(r'\b(free\s+(?:admission|entry|event|dance|class)|no cover)\b', desc or "", re.I) or re.search(r'\bfree\b', summary or "", re.I):
            price = "Free"
        else:
            m_cost = re.search(r'(?:Cost|Fee|Price|Tickets?|Admission|Cover)[\s:\-–—\xa0]+(?:[A-Za-z\s]+:\s*)?(\$[0-9]+(?:\.[0-9]{2})?(?:\s*[-–—]\s*\$[0-9]+(?:\.[0-9]{2})?)?|\bFree\b|\$0\b)', desc or "", re.I)
            if m_cost:
                val = m_cost.group(1).strip()
                price = "Free" if val.lower() in ("free", "$0", "$0.00") else val
            else:
                m_sum = re.search(r'\(\s*(\$[0-9]+(?:\.[0-9]{2})?(?:\s*[-–—]\s*\$?[0-9]+)?)\s*\)', summary or "")
                if m_sum:
                    price = m_sum.group(1).strip()
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
                "description": clean_desc,
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
        # Fix venue typo "Karakoe" -> "Karaoke"
        name = re.sub(r"\bKarakoe\b", "Karaoke", name, flags=re.IGNORECASE)
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
        # Use official ManRay monthly calendar page rather than private/broken Google Calendar eid link
        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": url,
            "venue": "ManRay",
            "price": price,
            "category": "clubbing",
            "description": desc[:200],
        })
    return events


def scrape_middlesex(url, ua):
    """Middlesex Lounge (Central Square, Cambridge) — parses weekly party announcements, guest DJs, and throwback parties."""
    target_url = "https://www.msexcambridge.com"
    events = []
    seen_dates = set()
    now = datetime.now(EASTERN)

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        if resp.status_code != 200:
            return events
        html = resp.text
    except Exception as exc:
        print(f"Error scraping Middlesex Lounge: {exc}")
        return events

    soup = BeautifulSoup(html, "html.parser")

    # 1. Primary: Parse Wix repeater items
    items = soup.find_all(class_="wixui-repeater__item")
    for item in items:
        p_tags = [p.get_text(strip=True) for p in item.find_all(["p", "span"]) if p.get_text(strip=True)]
        cleaned = []
        for s in p_tags:
            if not cleaned or cleaned[-1] != s:
                cleaned.append(s)

        date_obj = None
        title_parts = []
        date_found = False

        for text in cleaned:
            m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", text, re.I)
            if m and not date_found:
                month_str, day_str = m.group(1).lower(), m.group(2)
                month = month_map.get(month_str)
                if not month:
                    continue
                day = int(day_str)
                ev_year = now.year + 1 if month < now.month - 2 else now.year
                try:
                    date_obj = datetime(ev_year, month, day, 21, 0, tzinfo=EASTERN)
                except ValueError:
                    continue
                date_found = True
            elif not date_found:
                continue
            else:
                if text.lower() not in [t.lower() for t in title_parts]:
                    title_parts.append(text)

        if not date_obj:
            continue

        title = " ".join(title_parts).strip()
        title = re.sub(r"\s+", " ", title)
        if not title or title.upper() == "TBD":
            title = "Middlesex Club Night"

        date_key = date_obj.strftime("%Y-%m-%d")
        if date_key in seen_dates:
            for ev in events:
                if ev["date"].startswith(date_key) and len(title) > len(ev["name"]):
                    ev["name"] = title
            continue

        seen_dates.add(date_key)
        events.append({
            "name": title,
            "date": date_obj.isoformat(),
            "venue": "Middlesex Lounge",
            "category": "clubbing",
            "url": "https://www.msexcambridge.com",
            "description": "Party and underground DJ set at Middlesex Lounge in Central Square. Lounge opens at 5 PM, party starts at 9 PM.",
        })

    # 2. Fallback: Parse plain text if repeater items empty
    if not events:
        lines = [line.strip() for line in soup.stripped_strings if line.strip()]
        i = 0
        while i < len(lines):
            line = lines[i]
            m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b", line, re.I)
            if m:
                month_str, day_str = m.group(1).lower(), m.group(2)
                month = month_map.get(month_str)
                if month:
                    day = int(day_str)
                    ev_year = now.year + 1 if month < now.month - 2 else now.year
                    title_lines = []
                    j = i + 1
                    while j < len(lines) and j <= i + 3:
                        nxt = lines[j]
                        if any(kw in nxt.upper() for kw in ["PARTY IN", "CENTRAL SQ", "THIS WEEK", "THURSDAY", "FRIDAY", "SATURDAY", "UPCOMING GUESTS", "CALENDAR", "MASSACHUSETTS AVENUE"]):
                            break
                        if not re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b", nxt, re.I):
                            title_lines.append(nxt)
                        j += 1
                    title = " ".join(title_lines).strip() or "Middlesex Club Night"
                    try:
                        dt = datetime(ev_year, month, day, 21, 0, tzinfo=EASTERN)
                        date_key = dt.strftime("%Y-%m-%d")
                        if date_key not in seen_dates:
                            seen_dates.add(date_key)
                            events.append({
                                "name": title,
                                "date": dt.isoformat(),
                                "venue": "Middlesex Lounge",
                                "category": "clubbing",
                                "url": "https://www.msexcambridge.com",
                                "description": "Party and underground DJ set at Middlesex Lounge in Central Square. Lounge opens at 5 PM, party starts at 9 PM.",
                            })
                    except ValueError:
                        pass
            i += 1

    events.sort(key=lambda x: x["date"])
    return events


def scrape_roxys_arcade(url, ua):
    """Roxy's Arcade / A4cade (Central Square) — speakeasy arcade bar, drag trivia, karaoke, Smash tournaments, DJs."""
    events = []
    now = datetime.now(EASTERN)
    # Recurring schedule verified from https://www.roxysarcade.com/event-schedule
    for i in range(45):
        cur = now.date() + timedelta(days=i)
        weekday = cur.weekday()
        if weekday == 0:
            events.append({
                "name": "Drag Trivia Hosted by Missy Steak",
                "date": datetime(cur.year, cur.month, cur.day, 19, 30, tzinfo=EASTERN).isoformat(),
                "venue": "Roxy's Arcade",
                "category": "gaming",
                "price": "Free",
                "url": "https://www.roxysarcade.com/event-schedule",
                "description": "Weekly Drag Trivia hosted by Missy Steak at Roxy's Arcade in Central Square. Free to play, arcade games & grilled cheese.",
            })
        elif weekday == 2:
            events.append({
                "name": "Karaoke Night at Roxy's Arcade",
                "date": datetime(cur.year, cur.month, cur.day, 19, 0, tzinfo=EASTERN).isoformat(),
                "venue": "Roxy's Arcade",
                "category": "music",
                "price": "Free",
                "url": "https://www.roxysarcade.com/event-schedule",
                "description": "Weekly Wednesday karaoke night in the hidden speakeasy arcade at Roxy's Arcade in Central Square.",
            })
        elif weekday == 4:
            events.append({
                "name": "Live DJs at Roxy's Arcade",
                "date": datetime(cur.year, cur.month, cur.day, 21, 0, tzinfo=EASTERN).isoformat(),
                "venue": "Roxy's Arcade",
                "category": "clubbing",
                "price": "Free",
                "url": "https://www.roxysarcade.com/event-schedule",
                "description": "Friday night live DJ sets and retro arcade games at Roxy's Arcade in Central Square.",
            })
        elif weekday == 5:
            is_last_sat = (cur + timedelta(days=7)).month != cur.month
            if is_last_sat:
                events.append({
                    "name": "Super Smash Bros. Tournament with The Boston Gaymers",
                    "date": datetime(cur.year, cur.month, cur.day, 13, 0, tzinfo=EASTERN).isoformat(),
                    "venue": "Roxy's Arcade",
                    "category": "gaming",
                    "price": "Free",
                    "url": "https://www.roxysarcade.com/event-schedule",
                    "description": "Monthly Super Smash Bros tournament with The Boston Gaymers at Roxy's Arcade in Central Square.",
                })
            events.append({
                "name": "Saturday Night DJs at Roxy's Arcade",
                "date": datetime(cur.year, cur.month, cur.day, 21, 0, tzinfo=EASTERN).isoformat(),
                "venue": "Roxy's Arcade",
                "category": "clubbing",
                "price": "Free",
                "url": "https://www.roxysarcade.com/event-schedule",
                "description": "Saturday night DJ dance party and retro arcade games at Roxy's Arcade in Central Square.",
            })
    return events


def scrape_phoenix_landing(url, ua):
    """The Phoenix Landing (Central Square) — premier electronic music, drum & bass, house/techno, and soccer pub."""
    events = []
    now = datetime.now(EASTERN)
    # Residencies verified from https://www.thephoenixlanding.com/events
    for i in range(45):
        cur = now.date() + timedelta(days=i)
        weekday = cur.weekday()
        if weekday == 1:
            events.append({
                "name": "Infra: Underground Dance & Techno",
                "date": datetime(cur.year, cur.month, cur.day, 22, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "clubbing",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "Weekly underground dance and techno night hosted by Infra at The Phoenix Landing in Central Square.",
            })
        elif weekday == 2:
            events.append({
                "name": "Geeks Who Drink Trivia Night",
                "date": datetime(cur.year, cur.month, cur.day, 19, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "gaming",
                "price": "Free",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "Weekly Wednesday pub trivia with Geeks Who Drink at The Phoenix Landing. Free to play, prizes for top teams.",
            })
            events.append({
                "name": "Re:Set — House & Techno",
                "date": datetime(cur.year, cur.month, cur.day, 22, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "clubbing",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "Weekly Wednesday house and techno residency with rotating guest and resident DJs at The Phoenix Landing.",
            })
        elif weekday == 3:
            events.append({
                "name": "elements: Boston Drum & Bass",
                "date": datetime(cur.year, cur.month, cur.day, 22, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "clubbing",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "elements: Boston's legendary and longest-running weekly Drum & Bass party (since 1999) at The Phoenix Landing.",
            })
        elif weekday == 4:
            if cur.day <= 7 or (14 < cur.day <= 21):
                events.append({
                    "name": "Jazz Night & Open Jam",
                    "date": datetime(cur.year, cur.month, cur.day, 17, 0, tzinfo=EASTERN).isoformat(),
                    "venue": "The Phoenix Landing",
                    "category": "music",
                    "price": "Free",
                    "url": "https://www.thephoenixlanding.com/events",
                    "description": "First and third Friday open jazz jam session. All-ages, free, and open to the public at The Phoenix Landing.",
                })
            events.append({
                "name": "Friday Night Vibes with DJ Special K",
                "date": datetime(cur.year, cur.month, cur.day, 22, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "clubbing",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "Friday night dance party featuring hip hop, reggaeton, and Top 40 with resident DJ Special K at The Phoenix Landing.",
            })
        elif weekday == 5:
            events.append({
                "name": "The Boom Boom Room with DJ Vinny",
                "date": datetime(cur.year, cur.month, cur.day, 22, 0, tzinfo=EASTERN).isoformat(),
                "venue": "The Phoenix Landing",
                "category": "clubbing",
                "url": "https://www.thephoenixlanding.com/events",
                "description": "Saturday night dance hits, classic throwbacks, and party anthems with DJ Vinny at The Phoenix Landing.",
            })
    return events


def scrape_harvard_art_museums(url, ua):
    """Harvard Art Museums (Cambridge) — gallery talks, lectures, recitals, and exhibitions."""
    events = []
    now = datetime.now(timezone.utc)
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        if resp.status_code != 200:
            return events
        html_text = resp.text
    except Exception:
        return events

    m = re.search(r"var\s+initialEvents\s*=\s*\[\]\.concat\((\[.*?\])\);", html_text, re.DOTALL)
    if not m:
        return events

    try:
        raw_events = json.loads(m.group(1))
    except Exception:
        return events

    seen = set()
    for item in raw_events:
        title = item.get("title")
        date_str = item.get("date")
        slug = item.get("slug") or ""
        link = item.get("event_link") or (f"https://harvardartmuseums.org/calendar/{slug}" if slug else url)
        if not title or not date_str:
            continue
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            dt_utc = dt.astimezone(timezone.utc)
        except Exception:
            continue
        if dt_utc < now:
            continue

        price = "Free"
        for info in (item.get("info") or []):
            label = (info.get("label") or "").lower()
            val = (info.get("value") or "").strip()
            if "fee" in label and "free" not in val.lower():
                price = val

        key = (title, dt_utc.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt_utc.isoformat(),
            "url": link,
            "venue": "Harvard Art Museums",
            "price": price,
            "category": "art",
        })
    return events


def scrape_lyric_stage(url, ua):
    """Lyric Stage Company of Boston (Copley / Back Bay) — theater productions & performances."""
    now = datetime.now(timezone.utc)
    soup = fetch_soup(url, ua)
    events = []
    current_year = datetime.now(EASTERN).year

    seen = set()
    for p in soup.find_all("p", class_="date-range"):
        text = p.get_text().strip()
        m = re.match(r"([A-Za-z]+)\s+(\d{1,2})\s*-\s*(\d{1,2}):(\d{2})\s*(am|pm)", text, re.I)
        if not m:
            continue
        mon_str, day_str, hour_str, min_str, ampm = m.groups()
        hour = int(hour_str)
        minute = int(min_str)
        if ampm.lower() == "pm" and hour != 12:
            hour += 12
        elif ampm.lower() == "am" and hour == 12:
            hour = 0

        curr = p.parent
        title = None
        for _ in range(5):
            curr = curr.parent
            if not curr:
                break
            h = curr.find(["h2", "h3"])
            if h and h.get_text().strip() not in ["What's On", "Subscriptions"]:
                title = h.get_text().strip()
                break
        if not title:
            continue

        try:
            dt_mon = datetime.strptime(mon_str[:3], "%b").month
            year = current_year
            if dt_mon < datetime.now(EASTERN).month:
                year += 1
            dt_local = datetime(year, dt_mon, int(day_str), hour, minute, tzinfo=EASTERN)
            dt_utc = dt_local.astimezone(timezone.utc)
        except Exception:
            continue

        if dt_utc < now:
            continue

        link_tag = p.parent.find("a", href=True)
        ev_url = link_tag["href"] if link_tag else url
        if ev_url.startswith("/"):
            ev_url = f"https://lyricstage.com{ev_url}"

        key = (title, dt_utc.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt_utc.isoformat(),
            "url": ev_url,
            "venue": "Lyric Stage Company",
            "price": None,
            "category": "theater",
        })
    return events


def scrape_celebrity_series(url, ua):
    """Celebrity Series of Boston — world-class recitals, concerts, dance, and jazz."""
    now = datetime.now(timezone.utc)
    soup = fetch_soup(url, ua)
    events = []
    current_year = datetime.now(EASTERN).year

    seen = set()
    for art in soup.find_all("article", class_="event_item"):
        a_title = art.find("a", class_="event_item_title_link")
        if not a_title:
            continue
        title = a_title.get_text().strip()
        ev_url = a_title.get("href") or url

        date_label = a_title.get("aria-label") or ""
        m_date = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", date_label)
        if not m_date:
            continue
        mon_str, day_str = m_date.groups()

        times = re.findall(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", art.get_text(), re.I)
        if times:
            h_str, m_str, ampm = times[0]
            hour = int(h_str)
            minute = int(m_str or 0)
            if ampm.lower() == "pm" and hour != 12:
                hour += 12
            elif ampm.lower() == "am" and hour == 12:
                hour = 0
        else:
            hour = 20
            minute = 0

        try:
            dt_mon = datetime.strptime(mon_str[:3], "%b").month
            year = current_year
            if dt_mon < datetime.now(EASTERN).month:
                year += 1
            dt_local = datetime(year, dt_mon, int(day_str), hour, minute, tzinfo=EASTERN)
            dt_utc = dt_local.astimezone(timezone.utc)
        except Exception:
            continue

        if dt_utc < now:
            continue

        footer = art.find("footer", class_="event_item_footer")
        venue = "Celebrity Series of Boston"
        if footer:
            foot_text = footer.get_text()
            for v in ["Symphony Hall", "Jordan Hall", "Sanders Theatre", "Berklee Performance Center"]:
                if v in foot_text:
                    venue = f"Celebrity Series @ {v}"
                    break

        key = (title, dt_utc.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt_utc.isoformat(),
            "url": ev_url,
            "venue": venue,
            "price": None,
            "category": "music",
        })
    return events


def scrape_wix_events(url, ua, default_venue=None, default_category="clubbing"):
    """Generic scraper for Wix sites embedding events in <script id='wix-warmup-data'>."""
    now = datetime.now(timezone.utc)
    events = []
    try:
        resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        if resp.status_code != 200:
            return events
        html_text = resp.text
    except Exception:
        return events

    m = re.search(r"<script[^>]+id=[\"\']wix-warmup-data[\"\'][^>]*>(.*?)</script>", html_text, re.DOTALL)
    if not m:
        return events

    try:
        data = json.loads(m.group(1))
    except Exception:
        return events

    parts = urlparse(url)
    origin = f"{parts.scheme}://{parts.netloc}"

    seen = set()
    apps = data.get("appsWarmupData", {})
    for _, comp_map in apps.items():
        if not isinstance(comp_map, dict):
            continue
        for _, comp_data in comp_map.items():
            if not isinstance(comp_data, dict):
                continue
            ev_container = comp_data.get("events")
            if isinstance(ev_container, dict):
                ev_list = ev_container.get("events", [])
            elif isinstance(ev_container, list):
                ev_list = ev_container
            else:
                ev_list = []

            for item in ev_list:
                title = item.get("title")
                sched = item.get("scheduling", {}).get("config", {})
                start_str = sched.get("startDate")
                slug = item.get("slug")
                if not title or not start_str:
                    continue
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    dt_utc = dt.astimezone(timezone.utc)
                except Exception:
                    continue
                if dt_utc < now:
                    continue

                ev_url = f"{origin}/event-details/{slug}" if slug else url
                key = (title, dt_utc.isoformat())
                if key in seen:
                    continue
                seen.add(key)

                events.append({
                    "name": title,
                    "date": dt_utc.isoformat(),
                    "url": ev_url,
                    "venue": default_venue or "Boston Venue",
                    "price": None,
                    "category": default_category or "clubbing",
                })
    return events


def _do617_ticket_price(event_url, ua):
    """The ticket line on a Do617 event page: "Tickets: $5 + fee" -> "$5 + fee",
    "Tickets: $46-$138+" -> "$46-$138+", "Tickets: Free, 21+" -> "Free"; None when the page
    gives no price ("Tickets", "Tickets: Dates and times vary")."""
    try:
        resp = _SESSION.get(event_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
    except Exception:
        return None
    sec = soup.select_one("section.ticket-section")
    head = sec.find(["h2", "h3"]) if sec else None
    line = re.sub(r"(?i)^\s*tickets?\s*:?\s*", "", head.get_text(" ", strip=True)) if head else ""
    amt = r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?"
    m = re.search(amt + r"(?:\s*[-–]\s*" + amt.replace("\\$", "\\$?", 1) + r")?\+?(?:\s*\+\s*fees?)?", line)
    if m:
        return re.sub(r"\$(\d+)\.00\b", r"$\1", m.group(0)).strip()
    if mentions_free(line):
        return "Free"
    for ld in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(ld.string or "")
        except ValueError:
            continue
        for node in (data.get("@graph") or [data]) if isinstance(data, dict) else []:
            if isinstance(node, dict) and node.get("@type") == "Event" and node.get("isAccessibleForFree") is True:
                return "Free"
    return None


def _do617_fill_prices(events, ua):
    """Do617's day lists carry no prices; each event's own page does."""
    todo = [e for e in events if not e.get("price") and "do617.com/events/" in (e.get("url") or "")]
    if todo:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for e, price in zip(todo, ex.map(lambda e: _do617_ticket_price(e["url"], ua), todo)):
                if price:
                    e["price"] = price
    return events


def scrape_do617(url, ua):
    """Do617 — Scrapes upcoming Boston events via modern Svelte event cards or legacy Schema.org microdata."""
    events = []
    now = datetime.now(timezone.utc)
    seen = set()
    start_date = datetime.now(EASTERN).date()

    # 0. Single venue page support (e.g. /venues/deep-cuts)
    if "/venues/" in (url or ""):
        try:
            resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.content, "html.parser")
                cards = soup.find_all("div", attrs={"data-card-kind": "event"})
                for card in cards:
                    a_link = card.find("a", href=True)
                    if not a_link:
                        continue
                    rel_href = a_link.get("href", "")
                    full_url = urljoin("https://do617.com", rel_href.lstrip("./"))
                    h3 = card.find("h3")
                    name = h3.get_text(strip=True) if h3 else ""
                    if not name:
                        continue
                    m_date = re.search(r"/events/(\d{4})/(\d{1,2})/(\d{1,2})/", rel_href)
                    if not m_date:
                        continue
                    y, m_val, day_val = m_date.groups()
                    date_part = f"{int(y):04d}-{int(m_val):02d}-{int(day_val):02d}"
                    date_el = card.find(class_=lambda c: c and "date" in c)
                    raw_date_text = date_el.get_text(" ", strip=True) if date_el else ""
                    time_str = "20:00:00"
                    m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", raw_date_text, re.I)
                    if m_time:
                        hr = int(m_time.group(1))
                        mn = int(m_time.group(2) or 0)
                        merid = m_time.group(3).lower()
                        if merid == "pm" and hr < 12:
                            hr += 12
                        elif merid == "am" and hr == 12:
                            hr = 0
                        time_str = f"{hr:02d}:{mn:02d}:00"
                    try:
                        iso_str = f"{date_part}T{time_str}-04:00"
                        iso = datetime.fromisoformat(iso_str).astimezone(timezone.utc).isoformat()
                    except Exception:
                        iso = None
                    events.append({
                        "name": name,
                        "date": iso,
                        "url": full_url,
                        "venue": "Deep Cuts",
                        "price": None,
                    })
        except Exception:
            pass
        return _do617_fill_prices(events, ua)

    # 1. Scrape today + next 4 days from Do617 date feeds
    for i in range(5):
        d = start_date + timedelta(days=i)
        day_url = f"https://do617.com/events/{d.year}/{d.month:02d}/{d.day:02d}"
        try:
            resp = _SESSION.get(day_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.content, "html.parser")
            cards = soup.find_all("div", attrs={"data-card-kind": "event"})
            for card in cards:
                a_link = card.find("a", href=True)
                if not a_link:
                    continue
                rel_href = a_link.get("href", "")
                full_url = urljoin("https://do617.com", rel_href.lstrip("./"))

                h3 = card.find("h3")
                name = h3.get_text(strip=True) if h3 else ""
                if not name:
                    continue

                m_date = re.search(r"/events/(\d{4})/(\d{2})/(\d{2})/", rel_href)
                date_part = f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
                if m_date:
                    y, m_val, day_val = m_date.groups()
                    date_part = f"{y}-{m_val}-{day_val}"

                date_el = card.find(class_=lambda c: c and "date" in c)
                raw_date_text = date_el.get_text(" ", strip=True) if date_el else ""

                time_str = "20:00:00"
                m_time = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", raw_date_text, re.I)
                if m_time:
                    hr = int(m_time.group(1))
                    mn = int(m_time.group(2) or 0)
                    merid = m_time.group(3).lower()
                    if merid == "pm" and hr < 12:
                        hr += 12
                    elif merid == "am" and hr == 12:
                        hr = 0
                    time_str = f"{hr:02d}:{mn:02d}:00"

                iso = None
                try:
                    iso_str = f"{date_part}T{time_str}-04:00"
                    iso = datetime.fromisoformat(iso_str).astimezone(timezone.utc).isoformat()
                except Exception:
                    iso = None

                p_tags = [
                    p.get_text(strip=True)
                    for p in card.find_all("p")
                    if "enrichment" not in (p.get("class") or []) and "date" not in (p.get("class") or [])
                ]
                venue_name = p_tags[0] if p_tags else None
                if "88 club" in name.lower():
                    venue_name = "The 88 Club"
                elif venue_name and venue_name.startswith("@"):
                    m_at = re.search(r"\bat\s+(?:the\s+)?([A-Za-z0-9\s'&]+?)(?:\s*-\s*Boston|\s*,\s*MA|\s*$)", name, re.I)
                    if m_at:
                        venue_name = m_at.group(1).strip()

                key = (name.lower(), date_part)
                if key in seen:
                    continue
                seen.add(key)

                events.append({
                    "name": name,
                    "date": iso,
                    "url": full_url,
                    "venue": venue_name,
                    "price": None,
                })
        except Exception:
            continue

    # 2. Fallback to legacy Schema.org microdata if modern feed returned nothing
    if not events:
        try:
            soup = fetch_soup(url, ua)
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
        except Exception:
            pass

    return _do617_fill_prices(events, ua)


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
    """Scrapes stand-up comedy shows from Laugh Boston (Seaport) via calendar and Tixr."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    cal_url = "https://calendar.laughboston.com/"

    try:
        soup = fetch_soup(cal_url, ua)
        for s in soup.find_all("script"):
            text = s.string or ""
            for push in re.finditer(r"self\.__next_f\.push\(\[\d+,\"(.*)\"\]\)", text):
                chunk = push.group(1).encode("utf-8").decode("unicode_escape")
                if '"@graph":' in chunk:
                    try:
                        data = json.loads(chunk)
                        for item in data.get("@graph", []):
                            if item.get("@type") == "Event":
                                name = item.get("name") or ""
                                start_raw = item.get("startDate")
                                ticket_url = item.get("url") or "https://laughboston.com"
                                desc = item.get("description") or ""

                                iso = None
                                if start_raw:
                                    try:
                                        dt = datetime.fromisoformat(start_raw)
                                        iso = dt.astimezone(timezone.utc).isoformat()
                                    except Exception:
                                        pass

                                key = (name.lower(), (iso or "")[:10])
                                if key not in seen and name:
                                    seen.add(key)
                                    events.append({
                                        "name": f"Laugh Boston: {name}",
                                        "date": iso,
                                        "url": ticket_url,
                                        "venue": "Laugh Boston",
                                        "price": "$25 - $45",
                                        "category": "comedy",
                                        "description": desc[:250] if desc else None,
                                    })
                    except Exception:
                        pass
    except Exception:
        pass

    if not events:
        try:
            hp_soup = fetch_soup(url, ua)
            for col in hp_soup.select(".col"):
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
                    "price": "$25 - $45",
                    "category": "comedy",
                })
        except Exception:
            pass

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
        # Daily drop-in gallery tours (Gallery Highlights, Boston Stories, America at 250, ...)
        # run once or twice every day with admission; they'd fill every day of the calendar.
        if re.match(r"guided tour\b", raw_text, re.I) or re.search(r"\bcancell?ed\b", raw_text, re.I):
            continue
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
        is_free = mentions_free(raw_text)
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
    r = _SESSION.get("https://awsapi.citywinery.com/events", params={"location": "Boston", "top": 500},
                     timeout=20, headers={"User-Agent": ua, "Accept": "application/json"})
    r.raise_for_status()
    payload = (r.json() or {}).get("data", {})
    events = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)
    for ev in payload.get("event_data", []) or []:
        iso = ev.get("start")
        if not iso:
            continue
        try:
            when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
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
            "category": "music",
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
        # "Event" is the show title; "PerformanceName" is a marketing tagline
        # (e.g. "World Class traditional and contemporary music from ... -Dervish!").
        name = p.get("Event") or p.get("PerformanceName")
        venue = p.get("Venue")
        city = p.get("VenueCity")
        if venue and city:
            venue = f"{venue} ({city})"
        eid = p.get("EventID")
        ev = {
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            # orderticket.asp?p=<PerformanceID> 404s; the event page lists all performances.
            "url": urljoin(url, f"/eventperformances.asp?evt={eid}") if eid else url,
            "venue": venue,
            "price": None,
        }
        tagline = (p.get("PerformanceName") or "").strip()
        if tagline and tagline != name:
            ev["description"] = tagline
        events.append(ev)
    return events


def scrape_tnew(url, ua, venue, venue_overrides=(), months=4):
    """Tessitura TNEW storefronts (Boston Ballet, Handel and Haydn, A.R.T.).

    POST /api/products/productionseasons returns every production with its individual
    performances. TNEW doesn't expose the venue, so `venue` is the default and
    `venue_overrides` maps a phrase in the production description (e.g. "Jordan Hall")
    to the venue to use instead.
    """
    base = url.rstrip("/")
    now = datetime.now(EASTERN)
    body = {
        "startDate": now.strftime("%Y-%m-%dT00:00:00"),
        "endDate": (now + timedelta(days=30 * months)).strftime("%Y-%m-%dT23:59:59"),
        "keywordIds": [],
    }
    r = _SESSION.post(f"{base}/api/products/productionseasons", json=body, headers={
        "User-Agent": ua, "Accept": "application/json", "Referer": f"{base}/events",
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    productions = data.get("productions", []) if isinstance(data, dict) else data
    skip = re.compile(r"concession|parking|gift|membership|donat|voucher|merch", re.I)
    events = []
    for prod in productions or []:
        title = html.unescape(re.sub(r"<[^>]+>", "", prod.get("productionTitle") or "")).strip()
        if not title or skip.search(title):
            continue
        desc_html = prod.get("description") or ""
        desc = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", "", desc_html, flags=re.S)))
        desc = re.sub(r"\s+", " ", desc).strip()
        ev_venue = venue
        for phrase, v in venue_overrides:
            if phrase.lower() in desc.lower():
                ev_venue = v
                break
        for perf in prod.get("performances") or []:
            if perf.get("isPerformanceVisible") is False:
                continue
            iso = perf.get("iso8601DateString") or perf.get("performanceDate")
            if not iso:
                continue
            try:
                dt = datetime.fromisoformat(re.sub(r"\.\d+", "", iso))
            except ValueError:
                continue
            status = (perf.get("performanceStatusMessage") or "").strip()
            ev = {
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": perf.get("actionUrl") or prod.get("productionSeasonActionUrl") or base,
                "venue": ev_venue,
                "price": "Sold out" if re.search(r"sold\s*out", status, re.I) else None,
            }
            if desc:
                ev["description"] = desc[:400]
            events.append(ev)
    return events


def scrape_boston_ballet(url, ua):
    return scrape_tnew(url, ua, venue="Citizens Opera House")


def scrape_handel_haydn(url, ua):
    return scrape_tnew(url, ua, venue="Symphony Hall", venue_overrides=(
        ("Jordan Hall", "Jordan Hall (NEC)"),
        ("Sanders Theatre", "Sanders Theatre"),
        ("Emmanuel Church", "Emmanuel Church"),
    ))


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}


def _roll_year(month, day, today):
    """Pick the year for a yearless 'December 4' so it lands on/after ~a month ago."""
    for y in (today.year, today.year + 1):
        try:
            d = date(y, month, day)
        except ValueError:
            return None
        if d >= today - timedelta(days=31):
            return d
    return None


def scrape_art(url, ua):
    """American Repertory Theater (Loeb, Farkas Hall, Oberon). The listing page gives one
    card per show; each show page lists its performances as .c-booking-instance rows
    (weekday, 'December 4', '7:30PM ET', price, ticket link)."""
    today = datetime.now(EASTERN).date()
    soup = fetch_soup(url, ua)
    events = []
    for card in soup.select(".c-event-card"):
        t = card.select_one(".c-col-title")
        link = card.select_one(".c-event-card__titles a[href]") or card.select_one("a[href]")
        if not t or not link:
            continue
        title = t.get_text(" ", strip=True)
        sub = card.select_one(".c-col-subtitle")
        if sub and sub.get_text(strip=True).lower() not in title.lower():
            subtitle = sub.get_text(" ", strip=True)
        else:
            subtitle = ""
        venue_el = card.select_one(".c-masthead__venue")
        venue = venue_el.get_text(" ", strip=True) if venue_el else "American Repertory Theater"
        show_url = link["href"]
        meta = [li.get_text(" ", strip=True) for li in card.select(".c-masthead__event-meta li")]
        date_txt = meta[0] if meta else ""

        perfs = []
        try:
            show = fetch_soup(show_url, ua)
            for inst in show.select(".c-booking-instance"):
                m_el = inst.select_one(".c-booking-instance__month")
                tm_el = inst.select_one(".c-booking-instance__times")
                if not m_el:
                    continue
                m = re.match(r"([A-Za-z]+)\s+(\d{1,2})", m_el.get_text(" ", strip=True))
                if not m or m.group(1).lower() not in _MONTHS:
                    continue
                d = _roll_year(_MONTHS[m.group(1).lower()], int(m.group(2)), today)
                tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([AP]M)", tm_el.get_text(" ", strip=True) if tm_el else "", re.I)
                if not d or not tm:
                    continue
                hh = int(tm.group(1)) % 12 + (12 if tm.group(3).upper() == "PM" else 0)
                dt = datetime(d.year, d.month, d.day, hh, int(tm.group(2) or 0), tzinfo=EASTERN)
                btn = inst.select_one("a.c-booking-btn[href]")
                price_el = inst.select_one(".c-booking-instance__price")
                price = re.sub(r"^From:\s*", "From ", price_el.get_text(" ", strip=True)) if price_el else None
                if btn and "sold" in " ".join(btn.get("class", [])).lower():
                    price = "Sold out"
                perfs.append((dt, btn["href"] if btn else show_url, price))
        except Exception:
            pass

        if not perfs:
            # One-off events show a full date+time on the card: "Nov 9 7:30PM ET"
            m = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s+(\d{1,2})(?::(\d{2}))?\s*([AP]M)", date_txt, re.I)
            mon = m and next((v for k, v in _MONTHS.items() if k.startswith(m.group(1).lower()[:3])), None)
            if m and mon:
                d = _roll_year(mon, int(m.group(2)), today)
                if d:
                    hh = int(m.group(3)) % 12 + (12 if m.group(5).upper() == "PM" else 0)
                    btn = card.select_one("a.c-booking-btn[href]")
                    perfs.append((datetime(d.year, d.month, d.day, hh, int(m.group(4) or 0), tzinfo=EASTERN),
                                  btn["href"] if btn else show_url, None))

        name = f"{title}: {subtitle}" if subtitle and subtitle.lower() not in ("behind the scenes",) else title
        for dt, href, price in perfs:
            if dt.date() < today:
                continue
            events.append({
                "name": name,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": href,
                "venue": f"{venue} (A.R.T.)" if "a.r.t" not in venue.lower() else venue,
                "price": price,
            })
    return events


def scrape_harvard_film_archive(url, ua):
    """Harvard Film Archive calendar: .m-calendar__spot--event cards with <time datetime>.
    Fetches the current page plus next month via ?date_from=MM/01/YYYY."""
    today = datetime.now(EASTERN).date()
    nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    pages = [url, f"{url.split('?')[0]}?date_from={nxt.strftime('%m/%d/%Y')}"]
    seen, events = set(), []
    for page in pages:
        try:
            soup = fetch_soup(page, ua)
        except Exception:
            continue
        for card in soup.select(".m-calendar__spot--event"):
            t_el = card.select_one(".event__time time[datetime]")
            title_el = card.select_one(".event__title")
            a = card.select_one("a.event__link[href]")
            if not t_el or not title_el:
                continue
            try:
                dt = datetime.strptime(t_el["datetime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
            except ValueError:
                continue
            href = urljoin("https://harvardfilmarchive.org", a["href"]) if a else url
            key = (href, dt)
            if key in seen or dt.date() < today:
                continue
            seen.add(key)
            info = card.select_one(".event__info")
            labels = [x.get_text(" ", strip=True) for x in card.select(".event__labels .tooltip")]
            desc = " · ".join(filter(None, [re.sub(r"\s+", " ", info.get_text(" ", strip=True)) if info else "", *labels]))
            events.append({
                "name": title_el.get_text(" ", strip=True),
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": href,
                "venue": "Harvard Film Archive",
                "price": "$5 or free with CPL card" if any("CPL" in l for l in labels) else None,
                "category": "film",
                **({"description": desc} if desc else {}),
            })
    return events


def scrape_november_project(url, ua):
    """November Project Boston: free Wednesday stadium-stairs workout at Harvard Stadium
    (5:55 and 6:30am). Monday/Friday locations rotate and are only posted on Instagram,
    so only the fixed Wednesday session is listed."""
    today = datetime.now(EASTERN).date()
    events = []
    for i in range(0, 21):
        d = today + timedelta(days=i)
        if d.weekday() != 2:
            continue
        dt = datetime(d.year, d.month, d.day, 6, 30, tzinfo=EASTERN)
        if dt < datetime.now(EASTERN):
            continue
        events.append({
            "name": "November Project: Harvard Stadium Stairs (free workout)",
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": url,
            "venue": "Harvard Stadium",
            "price": "Free",
            "category": "sports",
            "description": "Free community workout running the Harvard Stadium stairs. Two start times: 5:55am and 6:30am. One-time waiver required.",
        })
    return events


def scrape_midnight_runners(url, ua):
    """Midnight Runners Boston: every Tuesday 7-9pm from Carrie Nation Cocktail Club.
    The first Tuesday of the month is a Bring a Friend 5K; the others are the 5-mile
    Bootcamp Run. Events live on Heylo (members-only), so the fixed schedule is generated.
    (Sunday Long Run & Brunch starts from rotating spots and is omitted.)"""
    now = datetime.now(EASTERN)
    events = []
    for i in range(0, 28):
        d = now.date() + timedelta(days=i)
        if d.weekday() != 1:
            continue
        dt = datetime(d.year, d.month, d.day, 19, 0, tzinfo=EASTERN)
        if dt < now:
            continue
        first_tuesday = d.day <= 7
        if first_tuesday:
            name = "Midnight Runners: Bring a Friend 5K"
            desc = "Free social 5K run, 7-9pm. First Tuesday of the month: bring a friend. Drinks after at Carrie Nation."
        else:
            name = "Midnight Runners: 5 Mile Bootcamp Run"
            desc = ("Free 5-mile run with music and bootcamp-style exercise stops, 7-9pm. "
                    "All paces welcome; warm-up, yoga cool-down, and drinks after at Carrie Nation.")
        events.append({
            "name": name,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": url,
            "venue": "Carrie Nation Cocktail Club",
            "price": "Free",
            "category": "sports",
            "description": desc,
        })
    return events


# Somerville Road Runners free weekly runs with a fixed time and meeting spot (srr.org/run-with-us
# pages). Runs that alternate locations (Sunday No Expectations) or lack a posted start
# (Wednesday morning) are left out. (weekday, hour, minute, name, venue, page, months or None)
SRR_WEEKLY_RUNS = [
    (0, 18, 45, "SRR Bur-Run: free 3-mile group run", "Kenney Park, Davis Square (Somerville)",
     "https://srr.org/monday-night-burrun", None),
    (1, 7, 30, "SRR Union Square Breakfast Club: 3-mile run", "Life Alive, Union Square (Somerville)",
     "https://srr.org/usbc", None),
    (1, 21, 0, "SRR Night Noodle: easy 3-4 mile night run", "Davis Square T Station (Somerville)",
     "https://srr.org/tuesday-night-noodle", range(4, 10)),
    (3, 19, 15, "SRR Thursday Night Casey's Run: 4 miles", "Casey's, 173 Broadway (Somerville)",
     "https://srr.org/thursday-night-caseys", None),
]


def scrape_somerville_road_runners(url, ua):
    """Somerville Road Runners' free, all-paces weekly runs (no membership needed)."""
    now = datetime.now(EASTERN)
    events = []
    for i in range(0, 21):
        d = now.date() + timedelta(days=i)
        for wd, hh, mm, name, venue, page, months in SRR_WEEKLY_RUNS:
            if d.weekday() != wd or (months and d.month not in months):
                continue
            dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=EASTERN)
            if dt < now:
                continue
            events.append({
                "name": name,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": page,
                "venue": venue,
                "price": "Free",
                "category": "sports",
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


_SSR_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_SSR_DATE_RE = re.compile(
    r'(?:(Sunday|Saturday|Friday|Monday|Tuesday|Wednesday|Thursday)[,\s]+)?'
    r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+'
    r'(\d{1,2})(?:st|nd|rd|th)?',
    re.I,
)


def scrape_second_sun_rising(url, ua):
    """Second Sun Rising: monthly fusion dance (second Sundays). The "This Month's Dance" page
    gives each date in prose with its venue in the same sentence ("Sunday Nov 8th we'll be at
    Cambridge Masonic Hall at 1950 Mass Ave", "December 13th ... at First Street Market, 59
    First Street in Cambridge"). Date ranges ("November 5-8th is Little Dipper weekend") are
    other events, not a Second Sun Rising dance, and are skipped."""
    soup = fetch_soup(url + "index.php/this-months-dance/", ua)
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    now = datetime.now(EASTERN)
    events, seen = [], set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        for m in _SSR_DATE_RE.finditer(sentence):
            if re.match(r"\s*(?:-|–|to\b)", sentence[m.end():]):
                continue  # a date range: a multi-day event, not the monthly dance
            if re.search(r"(?i)\b(?:return|expect)", sentence[:m.start()]):
                continue  # "We expect to return to the Masonic Hall for our January 10 dance": tentative
            m_num = _SSR_MONTHS.get(m.group(2)[:3].lower())
            if not m_num:
                continue
            year = now.year + (1 if m_num < now.month - 1 else 0)
            try:
                dt = datetime(year, m_num, int(m.group(3)), 19, 0, tzinfo=EASTERN)
            except ValueError:
                continue
            if dt < now - timedelta(hours=4) or dt.date() in seen:
                continue
            venue, address = "Cambridge Masonic Hall", "1950 Mass Ave, Cambridge"
            vm = re.search(r"(?i)\bbe at (?:the )?([A-Z][\w'&. ]+?)(?:,| at) (\d+ [^,.!]+?)(?: in ([A-Z][a-z]+))?(?=[,.!]|$)", sentence)
            if vm:
                venue = vm.group(1).strip()
                address = vm.group(2).strip().replace(" Street", " St").replace(" Avenue", " Ave")
                address += f", {vm.group(3) or 'Cambridge'}"
            seen.add(dt.date())
            events.append({
                "name": "Second Sun Rising — Fusion Dance",
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": url,
                "venue": venue,
                "address": address,
                "locality": address.rsplit(", ", 1)[-1],
                "price": "pay-what-you-can $10–$30",
            })
    events.sort(key=lambda e: e["date"])
    return events[:2]


def scrape_dorchester_brewing(url, ua):
    """Dorchester Brewing Company — live music, trivia, and community events."""
    resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    seen = set()
    now = datetime.now(timezone.utc)

    for a in soup.find_all("a", href=lambda h: h and "/events/event/" in h):
        href = a["href"]
        parent = a.find_parent("article") or a.find_parent("div", class_=lambda c: c and ("tribe" in " ".join(c) or "event" in " ".join(c)))
        if not parent:
            continue

        title_el = parent.find(["h2", "h3", "h4"])
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            t = a.get_text(strip=True)
            if t and "view event" not in t.lower() and not re.search(r"\d{1,2}:\d{2}", t):
                title = t
        if not title or title.lower() in ("view event",):
            continue

        full_text = parent.get_text(" ", strip=True)
        m_dt = re.search(r"([A-Za-z]+ \d{1,2}, \d{4})\s+(\d{1,2}:\d{2}\s*(?:am|pm))", full_text, re.I)
        iso = None
        if m_dt:
            d_str = f"{m_dt.group(1)} {m_dt.group(2)}"
            try:
                dt = datetime.strptime(d_str, "%B %d, %Y %I:%M %p").replace(tzinfo=EASTERN)
                if dt < now:
                    continue
                iso = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass

        key = (title.lower(), href)
        if key in seen:
            continue
        seen.add(key)

        is_trivia = "trivia" in title.lower()
        events.append({
            "name": title,
            "date": iso,
            "url": href,
            "venue": "Dorchester Brewing Company",
            "category": "trivia" if is_trivia else ("music" if any(k in title.lower() for k in ["dance", "music", "songwriting"]) else "food"),
            "price": "Free" if is_trivia else None,
        })
    return events


def scrape_huntington_theatre(url, ua):
    """The Huntington Theatre — Tony Award-winning regional theatre productions on Huntington Ave."""
    resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    for card in soup.find_all(class_=lambda c: c and "c-event-card" in c):
        title_el = card.find("h3") or card.find("h2")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue

        a = card.find("a", href=True)
        link = a["href"] if a else url
        if not link.startswith("http"):
            link = f"https://www.huntingtontheatre.org{link}"

        key = title.lower()
        if key in seen:
            continue
        seen.add(key)

        full_text = card.get_text(" ", strip=True)
        m_dates = re.search(r"([A-Za-z]+ \d{1,2})\s*[-–—]\s*([A-Za-z]+ \d{1,2}),?\s*(\d{4})", full_text)
        if m_dates:
            start_m_d = m_dates.group(1)
            end_m_d = m_dates.group(2)
            year = m_dates.group(3)
            start_dt = None
            end_dt = None
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    start_dt = datetime.strptime(f"{start_m_d} {year}", fmt).replace(hour=19, minute=30, tzinfo=EASTERN)
                    end_dt = datetime.strptime(f"{end_m_d} {year}", fmt).replace(hour=19, minute=30, tzinfo=EASTERN)
                    break
                except ValueError:
                    continue
            if not end_dt or end_dt < now:
                continue

            iso = end_dt.astimezone(timezone.utc).isoformat()
            events.append({
                "name": title,
                "date": iso,
                "url": link,
                "venue": "The Huntington Theatre",
                "category": "theater",
                "price": "$25 with HYPE Pass ($25+)",
                "description": f"Playing through {end_m_d}, {year} at The Huntington Theatre. Deal: $25 tickets for patrons under 40 via Huntington HYPE Pass (huntingtontheatre.org/flex-pass).",
            })
    return events


def scrape_calderwood_pavilion(url, ua):
    """Calderwood Pavilion at Boston Center for the Arts (BCA) / Boston Theatre Scene in South End."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    pages = [url, f"{url.rstrip('/')}/page/2/"]

    for p_url in pages:
        try:
            resp = _SESSION.get(p_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            continue

        for card in soup.select(".c-event-card"):
            title_el = card.select_one(".c-event-card__title")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            link_el = card.select_one(".c-event-card__permalink")
            href = link_el.get("href") if link_el else p_url

            card_text = card.get_text(" ", strip=True)
            is_calderwood = any(k in card_text.lower() for k in ["calderwood", "wimberly", "527 tremont", "539 tremont", "bca", "plaza theatre", "black box"])
            is_huntington = any(k in card_text.lower() for k in ["huntington ave", "huntington theatre", "264 huntington"])

            venue_name = "Calderwood Pavilion"
            if is_huntington and not is_calderwood:
                venue_name = "The Huntington Theatre"

            time_el = card.select_one(".c-event-card__daterange")
            date_raw = time_el.get_text(strip=True) if time_el else ""

            m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[-–—]\s*(?:([A-Za-z]+)\s+)?(\d{1,2}),?\s*(\d{4})", date_raw)
            single_m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s*(\d{4})", date_raw)

            dates_to_add = []
            if m:
                m1, d1, m2, d2, yr = m.groups()
                m2 = m2 or m1
                try:
                    start_dt = datetime.strptime(f"{m1} {d1} {yr}", "%B %d %Y").replace(hour=19, minute=30, tzinfo=EASTERN)
                    end_dt = datetime.strptime(f"{m2} {d2} {yr}", "%B %d %Y").replace(hour=19, minute=30, tzinfo=EASTERN)
                    if end_dt >= now:
                        if start_dt >= now - timedelta(days=1):
                            dates_to_add.append(start_dt)
                        cur = max(start_dt, now.replace(hour=19, minute=30, second=0, microsecond=0))
                        days_emitted = 0
                        while cur <= end_dt and days_emitted < 7:
                            if cur not in dates_to_add and cur >= now - timedelta(hours=3):
                                dates_to_add.append(cur)
                                days_emitted += 1
                            cur += timedelta(days=1)
                except Exception:
                    pass
            elif single_m:
                m1, d1, yr = single_m.groups()
                try:
                    dt = datetime.strptime(f"{m1} {d1} {yr}", "%B %d %Y").replace(hour=19, minute=30, tzinfo=EASTERN)
                    if dt >= now - timedelta(days=1):
                        dates_to_add.append(dt)
                except Exception:
                    pass

            if not dates_to_add and not (m and end_dt < now):
                dates_to_add.append(now)

            for dt in dates_to_add:
                iso = dt.astimezone(timezone.utc).isoformat()
                key = (title.lower(), iso[:10], venue_name)
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title,
                    "date": iso,
                    "url": href,
                    "venue": venue_name,
                    "category": "theater",
                    "price": "$25+",
                    "description": f"{title} presented at {venue_name}. {date_raw}",
                })

    return events


def scrape_central_square_theater(url, ua):
    """Central Square Theater — award-winning intimate theater in Cambridge (Catalyst Collaborative@MIT, Front Porch)."""
    events = []
    seen = set()
    now = datetime.now(EASTERN)
    pages = [url, f"{url.rstrip('/')}/page/2/"]

    for p_url in pages:
        try:
            resp = _SESSION.get(p_url, headers={"User-Agent": ua or UA_CHROME}, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception:
            continue

        for art in soup.find_all("article"):
            h_el = art.find(["h1", "h2", "h3"])
            title = h_el.get_text(strip=True) if h_el else ""
            if not title or any(skip in title.lower() for skip in ["soiree", "benefit", "gala"]):
                continue

            link_el = art.find("a", href=True)
            href = link_el["href"] if link_el else p_url

            text = art.get_text(" ", strip=True)
            m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[-–—]\s*(?:([A-Za-z]+)\s+)?(\d{1,2}),?\s*(\d{4})", text)
            if not m:
                continue

            m1, d1, m2, d2, yr = m.groups()
            m2 = m2 or m1
            try:
                start_dt = datetime.strptime(f"{m1} {d1} {yr}", "%B %d %Y").replace(hour=19, minute=30, tzinfo=EASTERN)
                end_dt = datetime.strptime(f"{m2} {d2} {yr}", "%B %d %Y").replace(hour=19, minute=30, tzinfo=EASTERN)
            except Exception:
                continue

            if end_dt < now:
                continue

            dates_to_add = []
            if start_dt >= now - timedelta(days=1):
                dates_to_add.append(start_dt)

            cur = max(start_dt, now.replace(hour=19, minute=30, second=0, microsecond=0))
            days_emitted = 0
            while cur <= end_dt and days_emitted < 7:
                if cur not in dates_to_add and cur >= now - timedelta(hours=3):
                    dates_to_add.append(cur)
                    days_emitted += 1
                cur += timedelta(days=1)

            for dt in dates_to_add:
                iso = dt.astimezone(timezone.utc).isoformat()
                key = (title.lower(), iso[:10])
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": f"Central Square Theater: {title}",
                    "date": iso,
                    "url": href,
                    "venue": "Central Square Theater",
                    "category": "theater",
                    "price": "$25 - $75",
                    "description": f"{title} at Central Square Theater in Cambridge. Running {m1} {d1} - {m2} {d2}, {yr}.",
                })

    return events


def scrape_harvard_pogo_meetups(url, ua):
    """Parse real in-person Pokémon GO community meetups (Raid Days, Community Days, Global Wild Area)
    held at Harvard Square & Harvard Yard by the Harvard/Central PoGO Campfire community."""
    events = []
    seen = set()
    try:
        resp = _SESSION.get("https://leekduck.com/events/", headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        events_map = {}

        for a in soup.find_all("a", class_=lambda c: c and "event-item-link" in c):
            h = a.find("h2") or a.find("h3")
            title = h.get_text(strip=True) if h else ""
            tag = a.find(class_="event-tag-badge")
            tag_str = tag.get_text(strip=True) if tag else ""
            cd = a.find(class_="event-countdown")
            if not cd or not title:
                continue
            to_type = cd.get("data-countdown-to")
            ts = cd.get("data-countdown")
            link = "https://leekduck.com" + a.get("href", "")
            if title not in events_map:
                events_map[title] = {"tag": tag_str, "link": link}
            events_map[title][to_type] = ts

        MEETUP_TAGS = {"raid day", "community day", "wild area", "research day", "max battle"}

        for title, d in events_map.items():
            tag = d.get("tag", "").lower()
            if "sendai" in title.lower() or "mexico" in title.lower():
                continue
            if not any(k in tag or k in title.lower() for k in MEETUP_TAGS):
                continue

            start_str = d.get("start")
            end_str = d.get("end")
            dt = None
            if start_str:
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=EASTERN)
                except Exception:
                    dt = None
            elif end_str:
                try:
                    end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                    if end_dt.tzinfo is None:
                        end_dt = end_dt.replace(tzinfo=EASTERN)
                    dt = end_dt - timedelta(hours=3)
                except Exception:
                    dt = None

            if not dt:
                continue

            iso = dt.astimezone(timezone.utc).isoformat()
            key = (title.lower(), iso[:10])
            if key in seen:
                continue
            seen.add(key)

            clean_title = f"{title} (Harvard/Central PoGO Campfire Meetup)"
            events.append({
                "name": clean_title,
                "date": iso,
                "url": "https://apps.apple.com/us/app/niantic-campfire/id1608154490",
                "venue": "Harvard Square",
                "category": "gaming",
                "price": "Free",
                "description": "In-person Pokémon GO meetup hosted by the Harvard/Central PoGO community at Harvard Square & Harvard Yard. Check in on the Niantic Campfire app for raid coordinates, flares, and lures.",
            })
    except Exception:
        pass

    return events


def scrape_ccae(url, ua):
    """Cambridge Center for Adult Education (CCAE) — community talks, workshops, and arts series in Harvard Sq."""
    resp = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    seen = set()
    now = datetime.now(EASTERN)

    for a in soup.find_all("a", class_=lambda c: c and "card-image" in c):
        href = a.get("href", "")
        if "/happenings/events/" not in href:
            continue
        h3 = a.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        if not title:
            continue

        full_text = a.get_text(" ", strip=True)
        m_dt = re.search(r"([A-Za-z]+ \d{1,2})\s*\|\s*(\d{1,2}:\d{2}\s*(?:am|pm))", full_text, re.I)
        iso = None
        if m_dt:
            m_d_str = m_dt.group(1)
            time_str = m_dt.group(2).replace(" ", "")
            year = now.year
            for fmt in ("%B %d %Y %I:%M%p", "%b %d %Y %I:%M%p"):
                try:
                    dt = datetime.strptime(f"{m_d_str} {year} {time_str}", fmt).replace(tzinfo=EASTERN)
                    if dt >= now:
                        iso = dt.astimezone(timezone.utc).isoformat()
                    break
                except ValueError:
                    continue

        key = (title.lower(), href)
        if key in seen:
            continue
        seen.add(key)

        is_art = any(k in title.lower() for k in ["drawing", "craft", "art", "paint", "watercolor", "ceramic", "photo"])
        events.append({
            "name": f"CCAE: {title}",
            "date": iso,
            "url": href,
            "venue": "Cambridge Center for Adult Education (CCAE)",
            "category": "art" if is_art else "community",
            "price": None,
        })
    return events


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
        ev = {
            "name": v.get("title"),
            "date": when.isoformat(),
            "url": v.get("eventUrl"),
            "venue": venue_name,
            "price": None,
            "description": (v.get("description") or "")[:200],
        }
        events.append(ev)
    return events


# Meetup's Boston search one topic at a time: each view server-renders only 12 events, so a sweep
# of topics x date windows reaches a few hundred. (topic id, category, trust the topic?):
# a narrow topic's events take its category ("Game Night", "BOINGA Game Festival" are board games,
# a dog-park "playgroup" isn't for kids); a broad one's are read from the title. Narrow topics come
# first so an event listed under both keeps the narrow category.
MEETUP_FIND_TOPICS = [
    (535, "gaming", True),       # Games
    (612, "dance", True),        # Dancing
    (482, "sports", True),       # Sports & Fitness
    (684, "outdoors", True),     # Travel & Outdoor
    (467, "books", True),        # Writing
    (701, "community", True),    # Pets & Animals
    (395, "music", False),       # Music (karaoke, jams, tribute shows, choirs)
    (521, "art", False),         # Art & Culture (also improv, opera, film outings)
    (652, "community", False),   # Social Activities
    (571, "community", False),   # Hobbies & Passions
    (511, "community", False),   # Health & Wellbeing
    (622, "community", False),   # Identity & Language
]
MEETUP_FIND_WINDOWS = ("", "this-weekend", "next-week")
_MEETUP_FIND_URL = ("https://www.meetup.com/find/?location=us--ma--boston&source=EVENTS"
                    "&eventType=inPerson&distance=tenMiles&categoryId={topic}{window}")


def _meetup_find_events(page_html):
    """Events in a Meetup search page's Apollo state: [(event, group_name)]."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html or "", re.S)
    if not m:
        return []
    try:
        state = json.loads(m.group(1))["props"]["pageProps"]["__APOLLO_STATE__"]
    except (ValueError, KeyError, TypeError):
        return []
    out = []
    for k, v in state.items():
        if k.startswith("Event:") and isinstance(v, dict) and v.get("title") and v.get("eventUrl"):
            group = state.get((v.get("group") or {}).get("__ref") or "") or {}
            out.append((v, (group.get("name") or "").strip()))
    return out


def scrape_meetup_topics(url, ua):
    """In-person Meetup events within 10 miles of Boston across the fun topics (social, games,
    arts, music, dance, sports, outdoors, hobbies, language, writing, pets), for the next days,
    this weekend and next week. Tech and career networking titles go to the Tech bucket."""
    from concurrent.futures import ThreadPoolExecutor
    pages = [(topic, _MEETUP_FIND_URL.format(topic=topic[0], window=f"&dateRange={w}" if w else ""))
             for topic in MEETUP_FIND_TOPICS for w in MEETUP_FIND_WINDOWS]

    def fetch(job):
        topic, page_url = job
        try:
            r = _SESSION.get(page_url, headers={"User-Agent": ua}, timeout=20)
            return topic, (r.text if r.status_code == 200 else "")
        except Exception:
            return topic, ""

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(weeks=6)
    events, seen = [], set()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for topic, page_html in ex.map(fetch, pages):
            for v, group_name in _meetup_find_events(page_html):
                if v.get("eventType") not in (None, "PHYSICAL") or v["eventUrl"] in seen:
                    continue
                try:
                    when = datetime.fromisoformat(v.get("dateTime") or "").astimezone(timezone.utc)
                except ValueError:
                    continue
                if not (now <= when <= cutoff):
                    continue
                seen.add(v["eventUrl"])
                venue = v.get("venue") or {}
                vname = (venue.get("name") or "").strip()
                if vname.lower() in ("online event", "online", "tbd", "to be determined"):
                    vname = ""
                if venue.get("city") and vname and venue["city"].lower() not in vname.lower():
                    vname = f"{vname} ({venue['city']})"
                elif not vname:
                    vname = group_name or "Meetup"
                title = v["title"].strip()
                _, topic_cat, narrow = topic
                # Title only: venue names mislead ("Open Studios" at a coffee bar isn't food)
                category = topic_cat if narrow else infer_category(title, None, topic_cat)
                # A tech talk that slipped into a social topic; not a tango "code" or improv "incubator"
                if category in ("community", "other") and TECH_EVENT_RE.search(title):
                    category = "tech"
                fee = v.get("feeSettings") or {}
                price = None
                if isinstance(fee.get("amount"), (int, float)) and fee["amount"] > 0:
                    price = f"${fee['amount']:g}"
                ev = {
                    "name": title,
                    "date": when.isoformat(),
                    "url": v["eventUrl"],
                    "venue": vname,
                    "price": price,
                    "category": category,
                    "description": re.sub(r"[*_#]+", "", v.get("description") or "")[:200],
                }
                if venue.get("address"):
                    ev["address"] = ", ".join(x for x in (venue.get("address"), venue.get("city")) if x)
                events.append(ev)
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


# Startup/tech events (mostly Luma): founders, VCs, AI, hackathons, demo/pitch nights.
TECH_EVENT_RE = re.compile(
    r"\b(?:startups?|founders?|co-?founder|vcs?|venture|investors?|fundrais\w*|pitch(?:es| night| showcase)?|"
    r"demo (?:day|night)|hackathon|hack night|ai|llms?|agents?|genai|gen ai|machine learning|ml|deep ?tech|"
    r"saas|devs?|developers?|engineers?|engineering|coding|code|software|product (?:managers?|teams?)|"
    r"robotics?|crypto|blockchain|web3|biotech|climate ?tech|accelerator|incubator|co-?working|"
    r"masschallenge|langchain|y ?combinator|cloud|agile|scrum|claude|chatgpt|openai|kubernetes|"
    r"data science|cybersecurity|infra|devops|b2b|gtm|life sciences|demo day|ecosystem)\b|"
    r"tech|robot",  # substrings: AgeTech, Health2Tech, TechWalk, TechCrunch, RoboBoston
    re.I,
)


def _luma_entry_to_event(entry, now, default_category="community"):
    """One Luma API entry ({event, calendar, hosts, ticket_info}) -> our event dict, or None."""
    ev = entry.get("event") or {}
    name = (ev.get("name") or "").strip()
    if not name or is_placeholder_or_closed_event(name):
        return None

    start_at = ev.get("start_at")
    if not start_at:
        return None
    try:
        dt = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
        if dt.astimezone(timezone.utc) < now:
            return None
        iso_date = dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None

    slug = ev.get("url") or ""
    link = slug if slug.startswith("http") else f"https://lu.ma/{slug}"

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

    cat = infer_category(name, venue, default=default_category)
    cal_name = ((entry.get("calendar") or {}).get("name") or "")
    if cat in ("community", "other") and (TECH_EVENT_RE.search(name) or TECH_EVENT_RE.search(cal_name)):
        cat = "tech"

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

    return ev_dict


# Luma calendars to follow. Seeded by hand; scrape_luma and other sources' lu.ma links add more
# (cached), so new Boston organizers on Luma get picked up without code changes.
LUMA_CALENDAR_SEEDS = {
    "cal-Fo5DfeIk8ur7FPY": "Millennial Crisis",  # Boston Social Conversations (Aeronaut)
    "cal-WqHXCe1kCl1MWaL": "Human Week",          # luma.com/humanweek
    "cal-21bcAtxY2x6CA7d": "The Story Circus",    # luma.com/thestorycircus
}
LUMA_CALENDARS_CACHE_PATH = os.path.join(CACHE_DIR, "luma_calendars.json")
LUMA_CALENDAR_CAP = 200  # calendars fetched per run
LUMA_LOCAL_CATEGORIES = {
    "cat-family": "Family", "cat-books": "Books", "cat-games": "Games", "cat-fooddrink": "Food & Drink",
    "cat-running": "Running", "cat-AzVAf6VmE9JEre4": "Arts & Culture", "cat-climate": "Climate",
    "cat-0Km9ZnuBjFAjwFl": "Fitness", "cat-C1VaNLnt25w9t6c": "Wellness",
    "cat-tech": "Tech", "cat-ai": "AI", "cat-crypto": "Crypto",
}
_LUMA_CATEGORY_DEFAULTS = {
    "cat-tech": "tech", "cat-ai": "tech", "cat-crypto": "tech",
    "cat-family": "family", "cat-books": "books", "cat-games": "gaming", "cat-fooddrink": "food",
    "cat-running": "fitness", "cat-AzVAf6VmE9JEre4": "art", "cat-0Km9ZnuBjFAjwFl": "fitness",
}
_BOSTON_CENTER = (42.3601, -71.0589)


def _load_luma_calendars():
    cals = dict(LUMA_CALENDAR_SEEDS)
    try:
        with open(LUMA_CALENDARS_CACHE_PATH) as f:
            cals.update(json.load(f).get("calendars") or {})
    except (OSError, ValueError):
        pass
    return cals


def _save_luma_calendars(cals, resolved_urls):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(LUMA_CALENDARS_CACHE_PATH, "w") as f:
            json.dump({"calendars": cals, "resolved_urls": sorted(resolved_urls)}, f)
    except OSError:
        pass


_LUMA_DISCOVERED = {}
_luma_tech_urls = set()


def _remember_luma_calendar(cal):
    cal = cal or {}
    api_id, name = cal.get("api_id"), (cal.get("name") or "").strip()
    if api_id and api_id.startswith("cal-") and name and name.lower() != "personal":
        _LUMA_DISCOVERED[api_id] = name


def _near_boston(ev, km=25):
    import math
    lat, lng = ev.get("lat"), ev.get("lng")
    if lat is None or lng is None:
        return False  # online or hidden-location: can't tell it's local
    dy = (float(lat) - _BOSTON_CENTER[0]) * 111.0
    dx = (float(lng) - _BOSTON_CENTER[1]) * 111.0 * math.cos(math.radians(_BOSTON_CENTER[0]))
    return math.hypot(dx, dy) <= km


def _luma_links_from_last_run():
    """lu.ma / luma.com event links any source published last run (e.g. Partiful, Do617, venues)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    out = set()
    for v in data.get("venues") or []:
        for e in v.get("events") or []:
            for u in [e.get("url")] + [a.get("url") for a in e.get("_alt_sources") or []]:
                m = re.match(r"https?://(?:www\.)?(?:lu\.ma|luma\.com)/([A-Za-z0-9_-]+)/?$", (u or "").strip())
                if m and m.group(1) not in ("boston", "discover", "home", "explore"):
                    out.add(m.group(1))
    return out


def scrape_luma_calendars(url, ua):
    """Upcoming Boston-area events from every Luma calendar we follow (seeds + discovered)."""
    from concurrent.futures import ThreadPoolExecutor
    headers = {"User-Agent": ua, "Accept": "application/json"}
    cals = _load_luma_calendars()
    cals.update(_LUMA_DISCOVERED)
    try:
        with open(LUMA_CALENDARS_CACHE_PATH) as f:
            resolved = set(json.load(f).get("resolved_urls") or [])
    except (OSError, ValueError):
        resolved = set()

    # Learn the calendar behind event links other sources published (capped per run)
    for slug in sorted(_luma_links_from_last_run() - resolved)[:25]:
        resolved.add(slug)
        try:
            d = _SESSION.get(f"https://api.lu.ma/url?url={slug}", headers=headers, timeout=10).json().get("data") or {}
        except Exception:
            continue
        cal = d.get("calendar") or {}
        if cal.get("api_id") and cal.get("name") and cal["name"].lower() != "personal":
            cals[cal["api_id"]] = cal["name"]

    now = datetime.now(timezone.utc)

    def fetch(cal_id):
        try:
            r = _SESSION.get("https://api.lu.ma/calendar/get-items",
                             params={"calendar_api_id": cal_id, "period": "future", "pagination_limit": 50},
                             headers=headers, timeout=15)
            r.raise_for_status()
            return r.json().get("entries") or []
        except Exception:
            return []

    # Fun organizers first (most discovered calendars are startup ones, from Luma's tech feeds),
    # then the cap: about 0.3s a calendar across 8 workers.
    order = sorted(cals, key=lambda cid: (cid not in LUMA_CALENDAR_SEEDS, bool(TECH_EVENT_RE.search(cals[cid] or ""))))
    events, seen = [], set()
    with ThreadPoolExecutor(max_workers=8) as ex:
        for entries in ex.map(fetch, order[:LUMA_CALENDAR_CAP]):
            cal_events = []
            for entry in entries:
                ev = _luma_entry_to_event(entry, now)
                if not ev or not _near_boston(ev):
                    continue
                key = (ev["name"].lower(), ev["date"][:16])
                if key not in seen:
                    seen.add(key)
                    cal_events.append(ev)
            # A mostly-tech organizer's other events (mixers, lunches, info sessions) are tech too
            if cal_events and sum(e["category"] == "tech" for e in cal_events) * 2 >= len(cal_events):
                for e in cal_events:
                    if e["category"] in ("community", "other"):
                        e["category"] = "tech"
            events.extend(cal_events)
    _save_luma_calendars(cals, resolved)
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
            ev_dict = _luma_entry_to_event(entry, now)
            if not ev_dict:
                continue
            key = (ev_dict["name"].lower(), ev_dict["date"][:10])
            if key in seen:
                continue
            seen.add(key)
            _remember_luma_calendar(entry.get("calendar"))
            events.append(ev_dict)

        if not data.get("has_more") or not data.get("next_cursor"):
            break
        cursor = data.get("next_cursor")

    # Category feeds by coordinates reach well past the ~22 curated "Boston" picks. Tech/AI/crypto
    # (~150 startup events a fortnight) go to the default-off "Tech & Startups" bucket.
    for cat_id in LUMA_LOCAL_CATEGORIES:
        cursor = None
        for _ in range(6):
            q = (f"https://api.lu.ma/discover/get-paginated-events?latitude={_BOSTON_CENTER[0]}"
                 f"&longitude={_BOSTON_CENTER[1]}&pagination_limit=50&discover_category_api_id={cat_id}")
            if cursor:
                q += f"&pagination_cursor={cursor}"
            try:
                data = _SESSION.get(q, headers=headers, timeout=15).json()
            except Exception:
                break
            for entry in data.get("entries") or []:
                ev_dict = _luma_entry_to_event(entry, now, _LUMA_CATEGORY_DEFAULTS.get(cat_id, "community"))
                if ev_dict and cat_id in ("cat-tech", "cat-ai", "cat-crypto"):
                    _luma_tech_urls.add(ev_dict["url"])  # tech even if first seen in another feed
                if not ev_dict or not _near_boston(ev_dict) or re.match(r"\s*private event\b", ev_dict["name"], re.I):
                    continue
                key = (ev_dict["name"].lower(), ev_dict["date"][:10])
                if key in seen:
                    continue
                seen.add(key)
                _remember_luma_calendar(entry.get("calendar"))
                events.append(ev_dict)
            if not data.get("has_more") or not data.get("next_cursor"):
                break
            cursor = data["next_cursor"]

    for ev_dict in events:
        if ev_dict.get("category") in ("community", "other") and ev_dict["url"] in _luma_tech_urls:
            ev_dict["category"] = "tech"
    _luma_tech_urls.clear()

    if _LUMA_DISCOVERED:  # persist so scrape_luma_calendars follows them (it may run concurrently)
        try:
            with open(LUMA_CALENDARS_CACHE_PATH) as f:
                cached = json.load(f)
        except (OSError, ValueError):
            cached = {}
        cals = {**(cached.get("calendars") or {}), **_LUMA_DISCOVERED}
        _save_luma_calendars(cals, set(cached.get("resolved_urls") or []))
    return events


from html import unescape as _html_unescape


def _clock_to_hm(txt):
    """'7:00 pm' / '6pm' -> (19, 0), or None."""
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", txt or "", re.I)
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)
    return h, int(m.group(2) or 0)


def scrape_wbur_cityspace(url, ua):
    """WBUR CitySpace: events embedded in the Next.js data of wbur.org/events."""
    html = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15).text
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return []
    found = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("source") == "events" and o.get("start") and o.get("headline") and o.get("id"):
                found[o["id"]] = o
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.loads(m.group(1)))
    now = datetime.now(EASTERN)
    events = []
    for o in found.values():
        try:
            dt = datetime.strptime(o["start"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=EASTERN)
        except ValueError:
            continue
        if dt < now - timedelta(hours=3):
            continue
        venue_parts = o.get("venue") or []
        venue = venue_parts[0] if venue_parts else "WBUR CitySpace"
        price = None
        p = (o.get("price") or "").strip()
        if p and re.match(r"^[\d.]+(?:-[\d.]+)?$", p):
            lo = float(p.split("-")[0])
            price = "Free" if lo == 0 else f"${lo:g}+" if "-" in p else f"${lo:g}"
        events.append({
            "name": _html_unescape(o["headline"]),
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": urljoin("https://www.wbur.org", o.get("relativeURL") or "/events"),
            "venue": venue,
            "price": price,
            "description": (o.get("excerpt") or "")[:250] or None,
        })
    return events


def scrape_hmsc(url, ua):
    """Harvard Museums of Science & Culture (Peabody, Natural History, Ancient Near East, ...):
    event links from the Upcoming Programs page; date/time/location from each event page.
    Two workers: the site rate-limits (429) at higher concurrency."""
    from concurrent.futures import ThreadPoolExecutor
    html = _SESSION.get(url, headers={"User-Agent": ua}, timeout=15).text
    links = sorted(set(re.findall(r"https://hmsc\.harvard\.edu/calendar_event/[a-z0-9-]+/", html)))
    today = datetime.now(EASTERN).date()

    def one(link):
        try:
            soup = fetch_soup(link, ua)
        except Exception:
            return []
        d_el = soup.select_one("li.post-date .meta-text")
        if not d_el:
            return []
        t_el = soup.select_one("li.event-time .meta-text")
        hm = _clock_to_hm(t_el.get_text(" ", strip=True) if t_el else "") or (18, 0)
        main = soup.find("main") or soup
        txt = main.get_text("\n", strip=True)
        loc = re.search(r"Location:\s*\n?(.+)", txt)
        venue = (loc.group(1).split(",")[0].strip() if loc else None) or "Harvard Museums of Science & Culture"
        if re.search(r"(?i)\bonline\b|\bzoom\b", venue):
            return []
        og = soup.find("meta", property="og:title")
        title = _html_unescape((og.get("content") if og else "") or (soup.title.string if soup.title else ""))
        title = re.sub(r"\s+[–-]\s+Harvard Museums of Science & Culture\s*$", "", title).strip()
        out = []
        for ds in re.findall(r"[A-Z][a-z]+ \d{1,2}, \d{4}", d_el.get_text(" ", strip=True)):
            try:
                d = datetime.strptime(ds, "%B %d, %Y").date()
            except ValueError:
                continue
            if d < today:
                continue
            dt = datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=EASTERN)
            out.append({
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": link,
                "venue": venue,
                "address": loc.group(1).strip() if loc else None,
                "price": "Free" if re.search(r"(?i)\bfree\b", txt[:200]) else None,
            })
        return out

    with ThreadPoolExecutor(max_workers=2) as ex:
        return [e for evs in ex.map(one, links) for e in evs if e["name"]]


def scrape_long_live_roxbury(url, ua):
    """Long Live Beerworks' Roxbury taproom: Thursday Jazz Night lineup, posted as text
    ("Nov 5 / The Filipe Salles Quartet"), 6-9pm."""
    soup = fetch_soup(url, ua)
    lines = [l for l in soup.get_text("\n", strip=True).split("\n") if l]
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"(?i)thursdays? at \d", l))
    except StopIteration:
        return []
    hm = _clock_to_hm(lines[start]) or (18, 0)
    today = datetime.now(EASTERN).date()
    events = []
    i = start + 1
    while i + 1 < len(lines):
        m = re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})$", lines[i], re.I)
        if not m:
            if events:
                break  # end of the lineup
            i += 1
            continue
        d = _roll_year(next(v for k, v in _MONTHS.items() if k.startswith(m.group(1).lower()[:3])), int(m.group(2)), today)
        act = lines[i + 1]
        if d and d >= today:
            dt = datetime(d.year, d.month, d.day, hm[0], hm[1], tzinfo=EASTERN)
            events.append({
                "name": f"Jazz Night: {act}",
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": url,
                "venue": "Long Live Roxbury",
                "price": "Free",
                "category": "music",
            })
        i += 2
    return events


def scrape_porter_square_books(url, ua):
    """Porter Square Books embeds its full FullCalendar event list in the
    Drupal `drupalSettings` JSON blob on the calendar page. We fetch both
    the current month and the upcoming months so events do not truncate at month-end."""
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
            continue  # the site answers 403 to us; asking again through curl would dodge that

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
        elif mentions_free(desc) or mentions_free(name):  # whole words: "Alice Howe & Freebo" is ticketed
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


_SHORT_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


_TRIBE_FAMILY_CATEGORIES = {"family", "families", "kids", "children", "family programs", "family events",
                             "kids & family", "kids & families", "kids and families", "family fun"}


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

        cat_names = [html.unescape(c.get("name", "")).lower().strip() for c in item.get("categories", [])]
        category = default_category or "community"
        if any(c in _TRIBE_FAMILY_CATEGORIES for c in cat_names):
            category = "family"
        elif any("music" in c for c in cat_names):
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


def scrape_arnold_arboretum(url, ua):
    """Arnold Arboretum (Jamaica Plain): family walks, birding, owl prowls, mushroom hunts, drop-in
    art and lectures (The Events Calendar API). Skips the twice-daily Highlights Tours, which run
    every day and would bury the real programs (like the MFA's daily tours)."""
    out = []
    for e in scrape_tribe_rest(url, ua, default_venue="Arnold Arboretum", default_category="outdoors"):
        if re.match(r"(?i)\s*arboretum highlights tour\b", e.get("name") or ""):
            continue
        spot = (e.get("venue") or "").strip()
        e["venue"] = "Arnold Arboretum"
        e["address"] = "125 Arborway, Jamaica Plain, Boston"
        if spot and spot.lower() != "arnold arboretum":
            e["description"] = f"Meet {spot[0].lower() + spot[1:] if spot.lower().startswith('in front') else 'at ' + spot}."
        if e.get("category") != "family" and is_kid_family_event(e.get("name"), None):
            e["category"] = "family"
        out.append(e)
    return out


_MONTHS_RE = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


_CLOCK_TIME_RE = re.compile(r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?(?![\d:])")


def _first_time_in(text):
    """(hour, minute) of the first clock time in text like "4:30 – 6:30 pm" or "12:00 pm; 7:30 pm";
    an am/pm-less first time takes the next am/pm marker. None if there's no time."""
    for m in _CLOCK_TIME_RE.finditer(text or ""):
        if not (m.group(2) or m.group(3)):
            continue  # a bare number ("27," or "2 shows") isn't a time
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if not ampm:
            nxt = re.search(r"(?i)\b([ap])\.?m\b", text[m.end():])
            ampm = nxt.group(1) if nxt else ("p" if 1 <= hour <= 7 else "a")
        if ampm.lower().startswith("p") and hour != 12:
            hour += 12
        elif ampm.lower().startswith("a") and hour == 12:
            hour = 0
        if hour < 24 and minute < 60:
            return hour, minute
    return None


def scrape_museum_of_science(url, ua):
    """Museum of Science special events (talks, planetarium nights, community days, family
    programs) from the site's event-listing API; each result is an HTML card with a date/time
    line, title and summary. Family programs go to Kids & Family."""
    out, now = [], datetime.now(timezone.utc)
    months = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July",
                                          "August", "September", "October", "November", "December"), 1)}
    for page in range(4):
        resp = _SESSION.get(url, params={"items_per_page": 18, "sort_by": "date_asc", "page": page},
                            headers={"User-Agent": ua, "Accept": "application/json"}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        for row in data.get("results") or []:
            card = row.get("event_listing") or ""
            tm = re.search(r'<h3[^>]*>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', card, re.S)
            info = re.search(r'field--name-field-date-time-info[^>]*>(.*?)</div>', card, re.S)
            if not tm or not info:
                continue
            title = html.unescape(re.sub(r"<[^>]+>", "", tm.group(2))).strip()
            info_txt = html.unescape(re.sub(r"<[^>]+>", " ", info.group(1)))
            info_txt = re.sub(r"\s+", " ", info_txt).strip()
            summ = re.search(r'listing-item__summary">(.*?)</div>', card, re.S)
            summary = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", summ.group(1)))).strip() if summ else ""
            dm = re.search(_MONTHS_RE + r"\s+(\d{1,2})(?:\s*[–-]\s*\d{1,2})?,\s*(\d{4})", info_txt)
            if not title or not dm:
                continue
            hm = None if re.search(r"(?i)\ball day\b", info_txt) else _first_time_in(info_txt[dm.end():])
            hour, minute = hm or (10, 0)
            try:
                dt = datetime(int(dm.group(3)), months[dm.group(1)], int(dm.group(2)), hour, minute, tzinfo=EASTERN)
            except ValueError:
                continue
            if dt.astimezone(timezone.utc) < now - timedelta(hours=6):
                continue
            blob = f"{title} {info_txt} {summary}"
            if re.search(r"(?i)\b(?:famil(?:y|ies)|kids?|children|toddlers?|ages? \d)", blob):
                cat = "family"
            else:
                cat = infer_category(title, None, default="community")  # "Museum" in the venue would say art
            out.append({
                "name": title,
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": urljoin("https://www.mos.org", tm.group(1)),
                "venue": "Museum of Science",
                "address": "1 Science Park, Boston",
                "price": None,
                "category": cat,
                "description": summary[:240] or None,
            })
        pager = data.get("pager") or {}
        if page + 1 >= int(pager.get("total_pages") or 1):
            break
    return out


def scrape_mount_auburn(url, ua):
    """Mount Auburn Cemetery (Cambridge/Watertown line): walking tours, birding, mindfulness walks,
    wreath and centerpiece workshops (The Events Calendar iCal feed)."""
    out = []
    for e in scrape_ical(url, ua):
        e["venue"] = "Mount Auburn Cemetery"
        e["address"] = "580 Mount Auburn St, Cambridge"
        cat = infer_category(e.get("name"), None, default="outdoors")
        e["category"] = "outdoors" if cat == "community" else cat  # walking tours read as community
        out.append(e)
    return out


def scrape_franklin_park_coalition(url, ua):
    """Franklin Park Coalition: Turkey Trot, park cleanups, Franklin Park Day (Events Calendar API)."""
    return scrape_tribe_rest(url, ua, default_venue="Franklin Park", default_category="outdoors")


def scrape_speedway(url, ua):
    """Charles River Speedway in Brighton (Notch Brewing, run club, markets, comedy)."""
    return scrape_tribe_rest(url, ua, default_venue="Charles River Speedway", default_category="food")


def scrape_kendall_center(url, ua):
    """Kendall Center (Urban Park Roof Garden film screenings, social events)."""
    return scrape_tribe_rest(url, ua, default_venue="Urban Park Roof Garden", default_category="community")


def scrape_lizard_lounge(url, ua):
    """Lizard Lounge in Cambridge (live music cellar, album releases, poetry).

    Parses the current month calendar HTML (with showtimes and ticket prices)
    and combines with the iCal feed for subsequent months.
    """
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)

    # 1. Scrape current month from calendar HTML
    try:
        headers = {
            "User-Agent": ua or UA_CHROME,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = _SESSION.get("https://lizardloungeclub.com/calendar/", headers=headers, timeout=15)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            for art in soup.find_all("article"):
                title_el = art.find(["h3", "h4", "h2", "a"])
                if not title_el:
                    continue
                a = art.find("a", href=True)
                link = a["href"] if a else "https://lizardloungeclub.com/calendar/"
                name = a.get_text(" ", strip=True) if a else title_el.get_text(" ", strip=True)
                if not name or "No Event Tonight" in name:
                    continue

                times = art.find_all("time")
                date_str = None
                time_str = "20:00"
                for t in times:
                    dt_val = t.get("datetime") or t.get_text(strip=True)
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", dt_val):
                        date_str = dt_val
                    elif re.match(r"^\d{1,2}:\d{2}$", dt_val) and time_str == "20:00":
                        time_str = dt_val

                if not date_str:
                    continue

                hour, minute = [int(x) for x in time_str.split(":")]
                y, m, d = [int(x) for x in date_str.split("-")]
                dt = datetime(y, m, d, hour, minute, tzinfo=EASTERN)
                dt_utc = dt.astimezone(timezone.utc)
                if dt_utc < cutoff:
                    continue

                pm = re.search(r"\$\d+(?:\.\d{2})?", art.get_text())
                price = pm.group(0) if pm else None

                key = (name.lower(), date_str)
                if key not in seen:
                    seen.add(key)
                    events.append({
                        "name": name,
                        "date": dt_utc.isoformat(),
                        "url": link,
                        "venue": "Lizard Lounge",
                        "price": price,
                        "category": "music",
                    })
    except Exception:
        pass

    # 2. Scrape iCal feed for future months
    try:
        ical_events = scrape_ical("https://lizardloungeclub.com/?post_type=tribe_events&ical=1&eventDisplay=list", ua)
        for ev in ical_events:
            ev_name = ev.get("name") or ""
            if not ev_name or "No Event Tonight" in ev_name:
                continue
            ev_date = (ev.get("date") or "")[:10]
            key = (ev_name.lower(), ev_date)
            if key not in seen:
                seen.add(key)
                ev["venue"] = "Lizard Lounge"
                ev["category"] = "music"
                events.append(ev)
    except Exception:
        pass

    return events


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


def scrape_tribe_rest_paged(url, ua, default_venue=None, default_category=None, days=21, max_pages=6,
                            skip_re=None):
    """The Events Calendar API, several pages of the next `days` days (busy calendars like
    Harvard Square's list 200+ events in three weeks; one page holds 50)."""
    base = url.split("?")[0]
    today = datetime.now(EASTERN)
    start, end = today.strftime("%Y-%m-%d"), (today + timedelta(days=days)).strftime("%Y-%m-%d")
    fallback = default_category or "community"
    out, seen = [], set()
    for page in range(1, max_pages + 1):
        evs = scrape_tribe_rest(f"{base}?per_page=50&page={page}&start_date={start}&end_date={end}", ua,
                                default_venue=default_venue, default_category=default_category)
        if not evs:
            if page > 1:  # past the last page the API answers 400; page 1 may be all earlier-today events
                break
            continue
        for e in evs:
            key = (e["name"], e["date"], e.get("venue"))
            if key in seen or (skip_re and skip_re.search(e["name"])):
                continue
            seen.add(key)
            # No telling calendar category (Live Music, Comedy, Art...): read the title and venue
            if e["category"] == fallback:
                e["category"] = infer_category(e["name"], e["venue"], fallback)
            out.append(e)
    return out


def _sugar_calendar_cells(page_html):
    """(start 'YYYY-MM-DDTHH:MM:SS' local, title, url) for each event in a Sugar Calendar month grid."""
    out = []
    for m in re.finditer(r'data-eventurl="([^"]+)".*?data-daydate="([^"]+)".*?'
                         r'sugar-calendar-block__event-cell__title">\s*(.*?)\s*</div>', page_html or "", re.S):
        try:
            start = json.loads(html.unescape(m.group(2)))["start_date"]["datetime"]
        except (ValueError, KeyError, TypeError):
            continue
        out.append((start, html.unescape(m.group(3)).strip(), html.unescape(m.group(1))))
    return out


def _flatten_form(prefix, obj, out):
    """jQuery-style form encoding of a nested object (a[b][0]=...), as $.post sends it."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten_form(f"{prefix}[{k}]", v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten_form(f"{prefix}[{i}]", v, out)
    else:
        out.append((prefix, "true" if obj is True else "false" if obj is False else str(obj)))
    return out


_BPM_SKIP_RE = re.compile(r"(?i)market closed|blood (?:donor|drive)|\bclosed\b|private event")
# The market's weekend kids' programming (face painting, the magician, puppets, story & craft hour)
_BPM_KIDS_RE = re.compile(r"(?i)face ?paint|magician|puppet|story ?(?:time|& craft|and craft)|sing-?along|\bkids?\b|famil")
_BPM_FOOD_RE = re.compile(r"(?i)tasting|pairing|blending|spice|coffee|latt[eé]|tea\b|wine|beer|cider|supper|brunch|"
                          r"munchies|nouveau|cheese|chocolate|cook|bak(?:e|ing)|dinner")


def scrape_boston_public_market(url, ua):
    """Boston Public Market's events calendar (Sugar Calendar): trivia nights, tastings, craft
    club, live music, kids' activity hours and story times, pop-up and holiday markets. The page
    shows this month; next month comes from the calendar's own month-change request."""
    headers = {"User-Agent": ua}
    try:
        page = _SESSION.get(url, headers=headers, timeout=20).text
    except Exception:
        return []
    cells = _sugar_calendar_cells(page)
    now = datetime.now(EASTERN)
    try:
        nonce = re.search(r'var sugar_calendar_obj = \{[^}]*"nonce":"(\w+)"', page).group(1)
        attrs = json.loads(html.unescape(re.search(r'data-attributes="([^"]+)"', page).group(1)))
        block_id = re.search(r'name="sc_calendar_id" value="([^"]+)"', page).group(1)
        nxt = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        block = {"id": block_id, "attributes": attrs, "day": 1, "month": nxt.month, "year": nxt.year,
                 "search": "", "display": "month", "visitor_tz_convert": 0,
                 "visitor_tz": "America/New_York", "updateDisplay": False, "action": ""}
        data = _flatten_form("calendar_block", block, [("action", "sugar_calendar_block_update"), ("nonce", nonce)])
        ajax = url.split("/events")[0] + "/wp-admin/admin-ajax.php"
        r = _SESSION.post(ajax, data=data, timeout=20,
                          headers={**headers, "X-Requested-With": "XMLHttpRequest", "Referer": url})
        cells += _sugar_calendar_cells(((r.json() or {}).get("data") or {}).get("body") or "")
    except Exception:
        pass  # this month only

    events, seen = [], set()
    for start, title, link in cells:
        if (start, title) in seen or not title or _BPM_SKIP_RE.search(title):
            continue
        seen.add((start, title))
        try:
            dt = datetime.fromisoformat(start).replace(tzinfo=EASTERN)
        except ValueError:
            continue
        if dt < now - timedelta(hours=2):
            continue
        events.append({
            "name": title,
            "date": dt.astimezone(timezone.utc).isoformat(),
            "url": link,
            "venue": "Boston Public Market",
            "address": "100 Hanover St, Boston, MA",
            "price": None,
            "category": ("family" if _BPM_KIDS_RE.search(title) else
                         "food" if _BPM_FOOD_RE.search(title) else infer_category(title, None, "community")),
        })
    return events


_HSHF_DAY_HOURS_RE = re.compile(r"(?i)(Fri|Satur|Sun)days?\s*:\s*(\d{1,2})(?::(\d\d))?\s*-\s*(\d{1,2})")


def scrape_harvard_square_holiday_fair(url, ua):
    """Harvard Square Holiday Fair (Christmas Crafts Co-op, since 1986): two December weekends
    of craft vendors at JFK & Winthrop St. Its one-page site lists the year's dates and hours:
    'HARVARD SQUARE HOLIDAY FAIR 2026 ... Dec 11th - 13th ... Dec 18th - 20th ... Fridays: 12-7
    Saturdays: 11-7 Sundays: 12-6'. One event per fair day."""
    try:
        soup = fetch_soup(url, ua)
    except Exception:
        return []
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    year_m = re.search(r"(?i)holiday fair\s+(20\d\d)", text)
    if not year_m:
        return []
    year = int(year_m.group(1))
    opens = {}  # weekday -> (open hour 24h, close hour 24h)
    for day, h1, m1, h2 in _HSHF_DAY_HOURS_RE.findall(text):
        wd = {"fri": 4, "satur": 5, "sun": 6}[day.lower()]
        start = int(h1) + (12 if int(h1) < 9 else 0)  # "12-7", "11-7": daytime hours
        opens[wd] = (start, int(m1 or 0))
    events = []
    now = datetime.now(EASTERN)
    for mon, d1, d2 in re.findall(r"(?i)\b(Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–]\s*(?:(?:Nov|Dec)[a-z]*\.?\s+)?(\d{1,2})", text):
        month = 11 if mon.lower().startswith("nov") else 12
        for day in range(int(d1), int(d2) + 1):
            try:
                d = datetime(year, month, day, tzinfo=EASTERN)
            except ValueError:
                continue
            hour, minute = opens.get(d.weekday(), (11, 0))
            dt = d.replace(hour=hour, minute=minute)
            if dt < now - timedelta(hours=6):
                continue
            events.append({
                "name": "Harvard Square Holiday Fair",
                "date": dt.astimezone(timezone.utc).isoformat(),
                "url": url,
                "venue": "Harvard Square Holiday Fair (JFK & Winthrop St)",
                "address": "JFK St & Winthrop St, Cambridge, MA",
                "price": "Free",
                "category": "markets",
                "description": "Handmade gifts from local craft vendors, two weekends every December since 1986.",
            })
    return events


# Weekly worship, office hours and permitting clinics in neighborhood business-district calendars
_DISTRICT_NOISE_RE = re.compile(
    r"(?i)\b(?:prayer|bible study|worship|sunday service|eucharist|mass\b|vespers|compline|meditation hour|"
    r"office hours|permitting|clinic\b|shuttle|members? only|board meeting|staff meeting|closed\b)")


def scrape_harvard_square(url, ua):
    """Harvard Square Business Association calendar: the square's festivals and fairs (Thai Night
    Market, Oktoberfest, the Holiday Fair), food and chocolate tours, shop events, plus listings
    from venues we also scrape (dedup merges those). Skips church services and office hours."""
    return scrape_tribe_rest_paged(url, ua, default_venue="Harvard Square", skip_re=_DISTRICT_NOISE_RE)


def scrape_kendall_square(url, ua):
    """Kendall Square Association calendar: trivia and music bingo at CambridgeSide, rooftop
    meetups, member socials, talks and plaza events."""
    return scrape_tribe_rest_paged(url, ua, default_venue="Kendall Square", skip_re=_DISTRICT_NOISE_RE)


# Brighton Main Streets also lists recovery meetings, small-business webinars, benefits clinics
# and youth sports leagues; none of them is a night out.
_BRIGHTON_SKIP_RE = re.compile(
    r"(?i)\bAA\b|\bNA meeting|alcoholics|al-anon|recovery meeting|medicare|screening|scholarship|deadline|"
    r"business|quickbooks|linkedin|marketing|networking|planning academy|advocate hours|age strong|"
    r"enrollment|webinar|seminar|certificat|\bleague\b|price it right|ai at work|cyber ?security")
# Family Nurturing Center playgroups ("Terrific Twos", "Wonderful Ones"), learn-to-skate, story times
_BRIGHTON_KIDS_RE = re.compile(r"(?i)\b(?:ones|twos|threes|toddlers?|pre-?school|story ?time|"
                               r"learn to (?:skate|play)|youth|kids?|children|playgroup|come & play)\b")


def scrape_brighton_main_streets(url, ua):
    """Brighton Main Streets community calendar: Irish Village and Porter Belly's live music and
    open mics, Cafenation paint and writing nights, Irish dance classes, the Brighton Bazaar,
    harvest fests, library story times. Events without a venue (online webinars) are skipped."""
    events = scrape_tribe_rest_paged(url, ua, default_venue="", skip_re=_DISTRICT_NOISE_RE)
    out = []
    for e in events:
        if e["venue"] in ("", "Boston Event") or _BRIGHTON_SKIP_RE.search(e["name"]):
            continue
        if _BRIGHTON_KIDS_RE.search(e["name"]):
            e["category"] = "family"
        elif e["category"] == "community" and re.search(r"(?i)live (?:entertainment|music|band)", e["name"]):
            e["category"] = "music"
        out.append(e)
    return out


def scrape_assembly_row(url, ua):
    """Assembly Row (Somerville): live music at The Row Hotel, Baxter Park events, LEGO Discovery
    Center adult nights, pop-ups."""
    return scrape_tribe_rest_paged(url, ua, default_venue="Assembly Row", skip_re=_DISTRICT_NOISE_RE)


def scrape_bow_market(url, ua):
    """Bow Market in Union Square Somerville via official Upstairs at Bow listings and Ticket Tailor."""
    now = datetime.now(timezone.utc)
    events = []
    seen = set()

    # 1. Primary: Upstairs at Bow official Squarespace public events
    upstairs_url = "https://www.upstairsatbow.com/public-events?format=json"
    try:
        resp = _SESSION.get(upstairs_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            items = d.get("upcoming", []) or d.get("items", []) or []
            for item in items:
                title = item.get("title")
                start_ms = item.get("startDate")
                if not title or not start_ms:
                    continue
                dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc).astimezone(EASTERN)
                if dt < now:
                    continue
                cat = "community"
                low = title.lower()
                if "tango" in low or "dance" in low or "milonga" in low:
                    cat = "dance"
                elif "comedy" in low or "improv" in low:
                    cat = "comedy"
                elif "art" in low or "auction" in low:
                    cat = "art"
                elif "music" in low or "concert" in low:
                    cat = "music"

                ev_url = "https://www.upstairsatbow.com" + (item.get("fullUrl") or "/public-events")
                key = (dt.date().isoformat(), title.strip().lower())
                if key in seen:
                    continue
                seen.add(key)
                events.append({
                    "name": title.strip(),
                    "date": dt.isoformat(),
                    "url": ev_url,
                    "venue": "Upstairs at Bow",
                    "price": None,
                    "category": cat,
                    "description": f"{title} at Upstairs at Bow (Bow Market, Union Square Somerville).",
                })
    except Exception as exc:
        print(f"Error fetching Upstairs at Bow: {exc}")

    # 2. Ticket Tailor listings for courtyard / general Bow Market
    try:
        soup = fetch_soup(url, ua)
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

            key = (dt.date().isoformat(), name.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "name": name,
                "date": dt.isoformat(),
                "url": href,
                "venue": venue,
                "price": None,
                "category": cat,
            })
    except Exception as exc:
        print(f"Error fetching Ticket Tailor: {exc}")

    events.sort(key=lambda x: x["date"])
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

                    dt = datetime(year, month, day_num, hour, minute, tzinfo=EASTERN)
                    cat = "music"
                    if "trivia" in title.lower():
                        cat = "comedy"
                    events.append({
                        "name": title,
                        "date": dt.astimezone(timezone.utc).isoformat(),
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
                    dt = datetime(st[0], st[1], st[2], st[3], st[4], tzinfo=EASTERN)
                events.append({
                    "name": e.get("title"),
                    "date": dt.astimezone(timezone.utc).isoformat() if dt else None,
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
                    dt = datetime(st[0], st[1], st[2], st[3], st[4], tzinfo=EASTERN)
                rel_url = s.get("url") or ""
                full_url = "https://gatherhereonline.com" + rel_url if rel_url.startswith("/") else rel_url
                events.append({
                    "name": f"Craft Workshop: {s.get('title')}",
                    "date": dt.astimezone(timezone.utc).isoformat() if dt else None,
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


# Teen-only library programs (Teen D&D, Teen Movie Fridays) aren't for parents with kids.
_TEEN_ONLY_RE = re.compile(r"(?i)\bteens?\b")
_NOT_TEEN_ONLY_RE = re.compile(r"(?i)\b(?:kids?|children|famil(?:y|ies)|tweens?|grades? (?:k|[1-5])\b|ages? [1-9]\b)")


def _teen_only(name):
    return bool(_TEEN_ONLY_RE.search(name or "")) and not _NOT_TEEN_ONLY_RE.search(name or "")


_LIBCAL_KIDS_RE = re.compile(
    r"(?i)\b(?:recommended for|for|ages?|designed for|perfect for)\b[^.]{0,40}\b(?:children|kids|toddlers?|babies|"
    r"infants|preschoolers?|families|caregivers|grades? (?:k|pre-?k|\d))\b|\bages? \d{1,2}\s*(?:-|–|to)\s*\d{1,2}\b|\b(?:babies|toddlers)\b")
_LIBCAL_ADULTS_RE = re.compile(r"(?i)\b(?:adults? only|for adults|teens? only|ages? 1[3-9]|ages? 2\d|18\+|21\+)\b")


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
        desc_el = item.find("libcal:description") or item.find("description")
        desc = BeautifulSoup(html.unescape(desc_el.text), "html.parser").get_text(" ", strip=True) if desc_el else ""
        desc = re.sub(r"\s+", " ", desc.replace("\xa0", " ")).strip()
        cat = infer_category(title, venue_name, default="community")
        if _LIBCAL_KIDS_RE.search(desc) and not _LIBCAL_ADULTS_RE.search(f"{title} {desc}"):
            cat = "family"  # e.g. "Recommended for children of all ages and their caregivers"
        events.append({
            "name": title,
            "date": dt.isoformat() if dt else None,
            "url": event_url,
            "venue": venue_name,
            "price": "Free",
            "category": cat,
            "description": desc[:300] or None,
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
            elif mentions_free(ev_name):
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
    """O'Brien's Pub in Allston — daily punk, rock, metal & indie lineups. Each show is a ticket in
    their WooCommerce shop; its public product API gives every show with its ticket price, and the
    SKU holds the date (20261114-2). Falls back to the home page listing if the API fails."""
    try:
        return _obriens_store_api(ua)
    except Exception:
        return _obriens_home_page(url, ua)


def _obriens_store_api(ua):
    resp = _SESSION.get("https://obrienspubboston.com/wp-json/wc/store/v1/products", params={"per_page": 100},
                        headers={"User-Agent": ua or UA_CHROME}, timeout=15)
    resp.raise_for_status()
    products = resp.json()
    if not isinstance(products, list) or not products:
        raise ValueError("no products")
    now = datetime.now(EASTERN)
    out = []
    for p in products:
        m = re.match(r"(\d{4})(\d{2})(\d{2})", p.get("sku") or "")
        if not m:
            continue
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        desc = BeautifulSoup(p.get("short_description") or p.get("description") or "", "html.parser").get_text(" ", strip=True)
        hm = _clock(re.sub(r"\b20\d\d\b|\d{1,2}(?:st|nd|rd|th)\b|,\s*\w+\s+\d{1,2}\b", " ", desc)) or (19, 0)
        dt = datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=EASTERN)
        if dt < now - timedelta(hours=6):
            continue
        price = None
        pr = p.get("prices") or {}
        try:
            cents = int(pr.get("price") or 0)
            if cents > 0:
                v = cents / (10 ** int(pr.get("currency_minor_unit", 2)))
                price = f"${v:g}" if v == int(v) else f"${v:.2f}"
        except (TypeError, ValueError):
            pass
        if price and not p.get("is_in_stock", True):
            price = f"{price} (sold out)"
        out.append({
            "name": html.unescape(p.get("name") or "").strip(),
            "date": dt.isoformat(),
            "url": p.get("permalink") or "https://obrienspubboston.com/",
            "venue": "O'Brien's Pub",
            "price": price,
            "category": "music",
        })
    return out


def _obriens_home_page(url, ua):
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
    now = datetime.now(EASTERN)
    out = []
    seen = set()
    # 10 shows a page; "Load More" fetches ?p=2, ?p=3 ... Follow it until two weeks out.
    page_url = endpoint
    for _ in range(6):
        try:
            resp = _SESSION.get(page_url, headers={"User-Agent": ua}, timeout=15)
            resp.raise_for_status()
        except Exception:
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        before = len(out)
        _mad_monkfish_page(soup, now, out, seen)
        nxt = soup.find(attrs={"data-paginator-next-url": True})
        if len(out) == before or not nxt or not out or max(e["date"] for e in out) > (now + timedelta(days=16)).isoformat():
            break
        page_url = urljoin(endpoint, nxt["data-paginator-next-url"])
    return out


def _mad_monkfish_page(soup, now, out, seen):
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


def scrape_club_passim(url, ua):
    """Club Passim in Harvard Square — historic folk, acoustic & roots listening room."""
    now = datetime.now(EASTERN)
    out = []
    seen = set()
    consecutive_empty = 0

    for offset in range(-7, 126, 7):
        page_url = f"https://www.passim.org/live-music/?ped={offset}"
        try:
            resp = _SESSION.get(page_url, headers={"User-Agent": ua}, timeout=10)
            if resp.status_code != 200:
                continue
            html_text = resp.text
        except Exception:
            continue

        soup = BeautifulSoup(html_text, "html.parser")
        cards = soup.find_all("div", class_="date_time_tickets")
        if not cards and offset > 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                break
            continue
        else:
            consecutive_empty = 0

        for card in cards:
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
                if dt < now - timedelta(days=60):
                    dt = dt.replace(year=now.year + 1)
                if dt < now - timedelta(hours=6):
                    continue
            except Exception:
                continue

            cost_m = re.search(r"\$(\d+)", card_text)
            price = f"${cost_m.group(1)}" if cost_m else ("Free" if mentions_free(card_text) else None)

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

    # 1. Live scheduled events from Dani's website (Wix Events)
    try:
        wix_evs = scrape_wix_events("https://www.danisqueerbar.com/copy-of-events", ua, default_venue="Dani's Queer Bar", default_category="clubbing")
        for e in wix_evs:
            results.append(e)
            if e.get("date"):
                seen.add((e.get("date")[:10], e["name"].lower()))
    except Exception:
        pass

    # 2. Ticketed special events from Eventbrite
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
                key = (e.get("date", "")[:10], e["name"].lower())
                if key not in seen:
                    results.append(e)
                    seen.add(key)
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


def _club_cafe_offers(soup):
    """Event URL -> (offers.price, description) from the calendar's JSON-LD blocks.

    The price is the digits of the event's "Cost" line: "5.00" for "$5.00 + fee", "0" when there's
    no charge, "" for "No Cover"/"FREE", and run together when there are two figures ("1510" for
    "$15 after 10 pm", "4030" for "$40 & $30 + fee").
    """
    out = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(s.string or "", strict=False)
        except ValueError:
            continue
        if not isinstance(j, dict) or not j.get("url"):
            continue
        offers = j.get("offers") if isinstance(j.get("offers"), dict) else {}
        desc = re.sub(r"<[^>]+>", " ", html.unescape(html.unescape(j.get("description") or "")))
        info = (str(offers.get("price") if offers.get("price") is not None else "").strip(), desc)
        out.setdefault(j["url"], info)
        out.setdefault(j["url"].split("?")[0].rstrip("/"), info)
    return out


def _club_cafe_cost_line(event_url, ua):
    """The "Cost" line on a Club Café event page: "$15 after 10 pm", "$40 & $30 + fee", "No Cover"."""
    try:
        resp = _SESSION.get(event_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        resp.raise_for_status()
        el = BeautifulSoup(resp.text, "html.parser").select_one(".mec-events-event-cost")
    except Exception:
        return None
    return el.get_text(" ", strip=True) if el else None


# Club Café's weekly no-cover nights, for listings that don't carry their own price.
_CLUB_CAFE_NO_COVER = ("free", "no cover", "tea dance", "karaoke", "trivia", "drag bingo")


def _club_cafe_price(name, ld_price, desc, cost_line=None):
    """A price from the venue's own Cost data; never "Free" for a ticketed night (Queer Board
    Game Night is $5 + fee even though board game nights elsewhere are usually free)."""
    if cost_line and re.search(r"\$\s?[1-9]", cost_line):
        return re.sub(r"\s+", " ", re.sub(r"\$(\d+)\.00\b", r"$\1", cost_line)).strip()[:32]
    if ld_price in ("0", "0.0", "0.00"):
        return "Free"
    if ld_price:
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", ld_price):
            amount = float(ld_price)
            return f"${amount:g}" if amount == int(amount) else f"${amount:.2f}"
        return admission_price(desc) or "Ticketed"  # two figures run together; it isn't free
    low = (name or "").lower()
    if any(w in low for w in _CLUB_CAFE_NO_COVER) or mentions_free(desc):
        return "Free"
    return None


def scrape_club_cafe(url, ua):
    """Club Café in South End — historic LGBT nightlife, cabaret, piano bar & dance club."""
    soup = fetch_soup(url, ua)
    offers = _club_cafe_offers(soup)
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

        ld_price, desc = offers.get(href) or offers.get(href.split("?")[0].rstrip("/")) or ("", "")

        key = (name, dt_iso)
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": name,
            "date": dt_iso,
            "url": href,
            "venue": venue_name,
            "category": cat,
            "_ld_price": ld_price,
            "_desc": desc,
        })

    # Two prices squeezed into one number ("1510") can only be read off the event's own page;
    # fetch each such event once.
    unclear = {}
    for e in events:
        if e["_ld_price"] and not re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", e["_ld_price"]):
            unclear.setdefault(e["url"].split("?")[0].rstrip("/"), e["url"])
    cost_lines = {}
    if unclear:
        with ThreadPoolExecutor(max_workers=4) as ex:
            cost_lines = dict(zip(unclear, ex.map(lambda u: _club_cafe_cost_line(u, ua), list(unclear.values())[:20])))
    for e in events:
        cost = cost_lines.get(e["url"].split("?")[0].rstrip("/"))
        e["price"] = _club_cafe_price(e["name"], e.pop("_ld_price"), e.pop("_desc"), cost)
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
    horizon = now + timedelta(days=16)

    # 10 concerts a page, in date order: page on until the list passes two weeks out (a busy
    # Berklee fortnight is 12+ pages), with a hard stop so a site change can't page forever.
    for page in range(20):
        page_url = f"{url}?page={page}" if page > 0 else url
        soup = fetch_soup(page_url, ua)
        if not soup:
            break

        cards = soup.select(".event.teaser")
        if not cards:
            break
        latest = None

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
                latest = max(latest, dt) if latest else dt
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
                "price": "Free" if mentions_free(card.get_text(" ")) else None,
                "category": "music",
            })
        if latest and latest > horizon:
            break

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


def scrape_improv_asylum(url, ua):
    """Improv Asylum in North End — live comedy, mainstage revue & improv shows via Tixr / Schema.org."""
    resp = _SESSION.get("https://calendar.improvasylum.com", headers={"User-Agent": ua}, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    events = []
    seen = set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=6)

    for s in soup.find_all("script"):
        if s.string and "schema.org" in s.string and '"Event"' in s.string:
            try:
                data = json.loads(s.string)
            except Exception:
                continue
            graph = data.get("@graph", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for item in graph:
                if item.get("@type") != "Event":
                    continue
                name = item.get("name")
                start_iso = item.get("startDate")
                if not name or not start_iso:
                    continue
                try:
                    dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                except ValueError:
                    continue

                ev_url = item.get("url") or item.get("@id") or "https://calendar.improvasylum.com"
                key = (name.lower(), dt.isoformat())
                if key in seen:
                    continue
                seen.add(key)

                offers = item.get("offers", {})
                price = None
                if isinstance(offers, dict):
                    low = offers.get("lowPrice") or offers.get("price")
                    if low:
                        price = f"${low}"

                events.append({
                    "name": name,
                    "date": dt.astimezone(timezone.utc).isoformat(),
                    "url": ev_url,
                    "venue": "Improv Asylum",
                    "price": price,
                    "category": "comedy",
                })
    return events


def scrape_squarespace_calendar_block(url, ua):
    """Scrape events from Squarespace pages using calendar blocks (e.g. Cisco Brewers Fenway, Castle Island Brewing)."""
    soup = fetch_soup(url, ua)
    cal_block = soup.select_one(".sqs-block-calendar[data-block-json]")
    if not cal_block:
        return []
    try:
        b_json = json.loads(cal_block["data-block-json"])
        collection_id = b_json.get("collectionId")
    except Exception:
        return []
    if not collection_id:
        return []

    now = datetime.now(EASTERN)
    months = [now.strftime("%m-%Y"), (now.replace(day=28) + timedelta(days=5)).strftime("%m-%Y")]

    events = []
    seen = set()
    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    for m in months:
        api_url = f"{base_url}/api/open/GetItemsByMonth?collectionId={collection_id}&month={m}"
        try:
            r = _SESSION.get(api_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
            if r.status_code != 200:
                continue
            items = r.json()
        except Exception:
            continue

        for it in items:
            title = it.get("title")
            if not title or is_placeholder_or_closed_event(title):
                continue
            sc = it.get("structuredContent") or {}
            start_ts = sc.get("startDate")
            iso_date = None
            if start_ts:
                dt = datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc).astimezone(EASTERN)
                iso_date = dt.isoformat()

            full_url = it.get("fullUrl")
            ev_url = urljoin(base_url, full_url) if full_url else url
            key = (title.lower(), iso_date[:10] if iso_date else None)
            if key in seen:
                continue
            seen.add(key)

            events.append({
                "name": html.unescape(title).strip()[:160],
                "date": iso_date,
                "url": ev_url,
                "price": None,
            })
    return events


def scrape_somerville_city(url, ua):
    """Scrape municipal community events from City of Somerville calendar (Truck O' Treat, etc.)."""
    soup = fetch_soup(url, ua)
    events = []
    seen = set()

    for row in soup.select(".views-row"):
        a = row.select_one("a")
        if not a:
            continue
        title = a.get_text(" ", strip=True)
        if not title or is_placeholder_or_closed_event(title):
            continue
        href = a.get("href", "")
        ev_url = urljoin(url, href)
        text = row.get_text(separator=" | ", strip=True)

        m = re.search(
            r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})(?:\s*-\s*(\d{1,2}:\d{2}\s*(?:am|pm)))?',
            text,
            re.IGNORECASE,
        )
        iso_date = None
        if m:
            month_s, day_s, year_s, time_s = m.groups()
            time_part = time_s.strip() if time_s else "12:00pm"
            try:
                dt = datetime.strptime(f"{month_s} {day_s} {year_s} {time_part}", "%B %d %Y %I:%M%p").replace(tzinfo=EASTERN)
                iso_date = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                try:
                    dt = datetime.strptime(f"{month_s} {day_s} {year_s}", "%B %d %Y").replace(tzinfo=EASTERN)
                    iso_date = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

        if not iso_date:
            continue

        key = (title.lower(), iso_date[:10])
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": html.unescape(title).strip()[:160],
            "date": iso_date,
            "url": ev_url,
            "venue": "Somerville City Hall",
            "price": "Free",
        })
    return events


def scrape_northeastern(url, ua):
    """Scrape campus lectures and public performances from Northeastern University Localist API."""
    try:
        r = _SESSION.get(url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    events = []
    seen = set()
    for it in data.get("events", []):
        ev = it.get("event", {})
        title = ev.get("title")
        if not title or is_placeholder_or_closed_event(title):
            continue
        instances = ev.get("event_instances", [])
        if not instances:
            continue
        inst = instances[0].get("event_instance", {})
        start_str = inst.get("start")
        if not start_str:
            continue

        try:
            dt = datetime.fromisoformat(start_str).astimezone(timezone.utc)
            iso_date = dt.isoformat()
        except Exception:
            continue

        loc = ev.get("location_name") or "Northeastern University"
        ev_url = ev.get("localist_url") or url
        key = (title.lower(), iso_date[:10])
        if key in seen:
            continue
        seen.add(key)

        entry = {
            "name": html.unescape(title).strip()[:160],
            "date": iso_date,
            "url": ev_url,
            "venue": loc[:80],
            "price": "Free" if ev.get("free") else None,
        }
        # Engineering/CS/AI departments and tech-titled talks -> default-off Tech & Startups
        depts = " ".join(t.get("name") or "" for t in (ev.get("filters") or {}).get("departments") or [])
        if _NEU_TECH_DEPT_RE.search(depts) or TECH_EVENT_RE.search(entry["name"]) or re.search(r"(?i)\bstem\b|\bdata\b", entry["name"]):
            entry["category"] = "tech"
        events.append(entry)
    return events


_NEU_TECH_DEPT_RE = re.compile(
    r"\b(?:COE|College of Engineering|Khoury|Computer Science|Experiential AI|NUlab|Roux Institute|"
    r"Network Science|Data Science|Bioengineering|Mechanical|Electrical)\b", re.I)


PARTIFUL_SOURCES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "partiful_sources.json")


def _get_partiful_targets(primary_url):
    targets = []
    if primary_url:
        targets.append(primary_url)
    if os.path.exists(PARTIFUL_SOURCES_FILE):
        try:
            with open(PARTIFUL_SOURCES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for u in data:
                        if isinstance(u, str) and u.startswith("http") and u not in targets:
                            targets.append(u)
        except Exception:
            pass
    # Guaranteed defaults for community favorites
    for default_u in (
        "https://partiful.com/explore/l/bos/events",
        "https://partiful.com/u/qu6OZYvBzHdRAzlwQBXK",  # Touch Grass + Meet irl organizer
        "https://partiful.com/e/oKWiAZcxbw1kWLgb5CRR",  # Cuffing Season Finale
        "https://partiful.com/e/nMhM5jZffB2zl2NMgQtO",  # Duck Duck Goose in Boston Public Garden
    ):
        if default_u not in targets:
            targets.append(default_u)
    return targets


def _partiful_price(ev):
    """Partiful RSVPs are free unless the host names a cover in the description ("21+, $10 CASH ONLY
    cover", "🎟️: $10 CASH OR VENMO"); being public doesn't make an event free."""
    text = f"{ev.get('title') or ''}\n{ev.get('description') or ''}"
    paid = admission_price(text)
    if paid:
        return paid
    if mentions_free(text):
        return "Free"
    if re.search(r"(?i)\b(?:tickets?|cover charge|admission|venmo|cash only)\b", text):
        return None  # a charge is mentioned without an amount
    return "Free" if ev.get("isPublic") else None


def scrape_partiful(url, ua):
    """Scrape community events, parties, and Touch Grass mixers from Partiful Boston."""
    headers = {
        "User-Agent": ua or UA_CHROME,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    targets = _get_partiful_targets(url)
    events = []
    seen = set()

    for target_url in targets:
        try:
            r = _SESSION.get(target_url, headers=headers, timeout=12)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception:
            continue

        next_data_el = soup.select_one("script#__NEXT_DATA__")
        if next_data_el:
            try:
                nd = json.loads(next_data_el.string)
                props = nd.get("props", {}).get("pageProps", {})

                # Case A: Explore directory (props['items'])
                items = props.get("items", [])
                for it in items:
                    ev = it.get("item", {}).get("event", {})
                    title = ev.get("title")
                    start_iso = ev.get("startDate")
                    if not title or not start_iso or is_placeholder_or_closed_event(title):
                        continue
                    loc = ev.get("locationInfo", {}) or {}
                    vname = loc.get("displayName") or loc.get("mapsInfo", {}).get("name") or loc.get("approximateLocation") or "Boston"
                    ev_url = f"https://partiful.com/e/{ev.get('id')}"
                    key = (title.lower().strip(), start_iso[:10])
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({
                        "name": html.unescape(title).strip()[:160],
                        "date": start_iso,
                        "url": ev_url,
                        "venue": vname,
                        "price": _partiful_price(ev),
                        "category": "community",
                    })

                # Case B: Single event page (props['event'])
                ev = props.get("event", {})
                if ev and ev.get("title") and ev.get("startDate"):
                    title = ev.get("title")
                    start_iso = ev.get("startDate")
                    if not is_placeholder_or_closed_event(title):
                        loc = ev.get("locationInfo", {}) or {}
                        vname = loc.get("displayName") or loc.get("mapsInfo", {}).get("name") or ev.get("location") or loc.get("approximateLocation") or "Boston"
                        key = (title.lower().strip(), start_iso[:10])
                        if key in seen:
                            if vname and vname.lower() != "boston":
                                for ex in events:
                                    if (ex["name"].lower().strip(), ex["date"][:10]) == key:
                                        if ex["venue"].lower() == "boston":
                                            ex["venue"] = vname
                                        break
                        else:
                            seen.add(key)
                            events.append({
                                "name": html.unescape(title).strip()[:160],
                                "date": start_iso,
                                "url": target_url,
                                "venue": vname,
                                "price": _partiful_price(ev),
                                "category": "community",
                            })

                # Case C: Organizer profile page (props['initialPublishedEvents'], e.g. Touch Grass)
                for ev in props.get("initialPublishedEvents", []):
                    title = ev.get("title")
                    start_iso = ev.get("startDate")
                    if not title or not start_iso or is_placeholder_or_closed_event(title):
                        continue
                    loc = ev.get("locationInfo", {}) or {}
                    vname = loc.get("displayName") or loc.get("mapsInfo", {}).get("name") or loc.get("approximateLocation") or "Boston"
                    ev_url = f"https://partiful.com/e/{ev.get('id')}" if ev.get("id") else target_url
                    key = (title.lower().strip(), start_iso[:10])
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({
                        "name": html.unescape(title).strip()[:160],
                        "date": start_iso,
                        "url": ev_url,
                        "venue": vname,
                        "price": _partiful_price(ev),
                        "category": "community",
                    })
            except Exception:
                pass

        # Case D: Fallback schema.org Event LD+JSON
        for s in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(s.string)
                if isinstance(data, dict) and data.get("@type") == "Event":
                    title = data.get("name")
                    start_iso = data.get("startDate")
                    if not title or not start_iso or is_placeholder_or_closed_event(title):
                        continue
                    loc = data.get("location", {})
                    vname = loc.get("name") if isinstance(loc, dict) else "Boston"
                    key = (title.lower().strip(), start_iso[:10])
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append({
                        "name": html.unescape(title).strip()[:160],
                        "date": start_iso,
                        "url": target_url,
                        "venue": vname,
                        "price": "Free" if data.get("offers", {}).get("price") == 0 else None,
                        "category": "community",
                    })
            except Exception:
                pass

    return events


def scrape_the_platform_kendall(url=None, ua=None):
    """Scrape upcoming performances and productions at The Platform Kendall from Algolia API."""
    algolia_url = "https://Y1VSI41HOC-dsn.algolia.net/1/indexes/wp_platform_searchable_posts/query"
    headers = {
        "X-Algolia-Application-Id": "Y1VSI41HOC",
        "X-Algolia-API-Key": "906fcb304f59c27fc5e38065cffa2da4",
        "Content-Type": "application/json",
        "User-Agent": ua or UA_CHROME,
    }

    prods = []
    try:
        p_body = json.dumps({"params": "hitsPerPage=1000&filters=post_type:production AND language:en"}).encode("utf-8")
        resp = _SESSION.post(algolia_url, data=p_body, headers=headers, timeout=15)
        if resp.status_code == 200:
            prods = resp.json().get("hits", [])
    except Exception as e:
        log_warning(f"The Platform Kendall: productions query failed: {e}")

    perfs = []
    try:
        f_body = json.dumps({"params": "hitsPerPage=1000&filters=post_type:performance"}).encode("utf-8")
        resp = _SESSION.post(algolia_url, data=f_body, headers=headers, timeout=15)
        if resp.status_code == 200:
            perfs = resp.json().get("hits", [])
    except Exception as e:
        log_warning(f"The Platform Kendall: performances query failed: {e}")

    def _norm(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("utf-8")
        return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()

    prod_by_norm = {}
    for p in prods:
        t = p.get("production_title") or p.get("post_title") or ""
        n = _norm(t)
        if n:
            prod_by_norm[n] = p

    now = datetime.now(timezone.utc)
    pattern = re.compile(r"^(.*?)\s*[-–—]\s*(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})$")

    events = []
    seen = set()

    def find_prod(name_str):
        n = _norm(name_str)
        if n in prod_by_norm:
            return prod_by_norm[n]
        for pn, p in prod_by_norm.items():
            if pn.startswith(n) or n.startswith(pn):
                return p
        return None

    def decide_category(cname, genres):
        g_str = " ".join(genres).lower()
        if any(k in g_str for k in ["acrobatic", "circus", "theater", "theatre"]):
            return "stage"
        if any(k in g_str for k in ["dance", "ballet", "danza", "flamenco", "tap"]):
            return "dance"
        if any(k in g_str for k in ["jazz", "folk", "orchestra", "brass", "acoustic", "music", "classical", "soul", "blues", "hip hop", "rock"]):
            return "music"
        return infer_category(cname, "The Platform Kendall", default="stage")

    for h in perfs:
        link = h.get("permalink", "")
        if "wpenginepowered" in link:
            continue
        title_raw = h.get("post_title", "").strip()
        if not title_raw or ("scan" in title_raw.lower() and "test" in title_raw.lower()):
            continue

        perf_date = h.get("performance_date")
        name = h.get("performance_title") or title_raw
        dt = None
        if perf_date:
            try:
                raw_iso = perf_date.replace("Z", "+00:00")
                dt = datetime.fromisoformat(raw_iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=EASTERN)
            except Exception:
                pass
        if not dt:
            m = pattern.search(title_raw)
            if m:
                name = m.group(1).strip()
                date_str = m.group(2)
                time_str = m.group(3)
                dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=EASTERN)

        if not dt:
            continue

        dt_utc = dt.astimezone(timezone.utc)
        if dt_utc < now:
            continue

        prod = find_prod(name)
        clean_name = (prod.get("production_title") or prod.get("post_title")) if prod else name
        if is_placeholder_or_closed_event(clean_name):
            continue

        event_url = (prod.get("permalink") if prod else None) or link
        if "opening-day" in event_url or "opening day" in clean_name.lower():
            event_url = "https://www.theplatformkendall.org/the-platform-opening-day/"

        alert = (prod.get("alert_text") if prod else "") or ""
        price = "Free" if "opening day" in clean_name.lower() or mentions_free(alert) else None

        prod_genres = (prod.get("genre") if prod else None) or []
        cat = decide_category(clean_name, prod_genres)
        genre = infer_music_genre(clean_name, "The Platform Kendall", description=" ".join(prod_genres), category=cat) if cat in ("music", "clubbing") else None

        key = (_norm(clean_name), dt.isoformat()[:16])
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": clean_name,
            "date": dt.isoformat(),
            "url": event_url,
            "venue": "The Platform Kendall",
            "price": price or "Check link",
            "category": cat,
            "genre": genre,
        })

    for p in prods:
        name = (p.get("production_title") or p.get("post_title") or "").strip()
        fdate = p.get("first_performance_date")
        if not fdate or is_placeholder_or_closed_event(name):
            continue
        try:
            raw_iso = fdate.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=EASTERN)
        except Exception:
            continue

        dt_utc = dt.astimezone(timezone.utc)
        if dt_utc < now:
            continue

        key = (_norm(name), dt.isoformat()[:16])
        if key in seen:
            continue
        seen.add(key)

        event_url = p.get("permalink") or "https://www.theplatformkendall.org/event-listing/"
        if "opening-day" in event_url or "opening day" in name.lower():
            event_url = "https://www.theplatformkendall.org/the-platform-opening-day/"

        alert = p.get("alert_text") or ""
        price = "Free" if "opening day" in name.lower() or mentions_free(alert) else None
        prod_genres = p.get("genre") or []
        cat = decide_category(name, prod_genres)
        genre = infer_music_genre(name, "The Platform Kendall", description=" ".join(prod_genres), category=cat) if cat in ("music", "clubbing") else None

        events.append({
            "name": name,
            "date": dt.isoformat(),
            "url": event_url,
            "venue": "The Platform Kendall",
            "price": price or "Check link",
            "category": cat,
            "genre": genre,
        })

    events.sort(key=lambda x: x["date"])
    return events


def scrape_life_drawing_boston(url, ua):
    """Life Drawing Boston at The Loov (Somerville) — figure drawing & portrait club."""
    events = []
    now = datetime.now(timezone.utc)
    target_url = url if "format=json" in url else url.rstrip("/") + "/?format=json"
    try:
        resp = _SESSION.get(target_url, headers={"User-Agent": ua or UA_CHROME}, timeout=15)
        if resp.status_code != 200:
            return events
        data = resp.json()
    except Exception:
        return events

    items = data.get("upcoming", []) or data.get("items", [])
    seen = set()
    for item in items:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        start_ms = item.get("startDate")
        if not start_ms:
            continue
        try:
            dt = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc)
        except Exception:
            continue
        if dt < now:
            continue

        full_url = item.get("fullUrl") or ""
        if full_url and not full_url.startswith("http"):
            link = "https://www.lifedrawingboston.com" + full_url
        else:
            link = full_url or url

        # Check if description or excerpt mentions a specific price
        body_html = item.get("body") or ""
        excerpt_html = item.get("excerpt") or ""
        combined_text = f"{title} {body_html} {excerpt_html}"
        m_cost = re.search(r'(?:Cost|Fee|Price|Admission|Door)[\s:\-–—\xa0]+(\$[0-9]+(?:\.[0-9]{2})?|\bFree\b)', combined_text, re.I)
        if m_cost:
            val = m_cost.group(1).strip()
            price = "Free" if val.lower() == "free" else val
        else:
            m_dollar = re.search(r'(\$[0-9]{1,3}(?:\.[0-9]{2})?)', combined_text)
            price = m_dollar.group(1).strip() if m_dollar else "$20"

        key = (title, dt.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt.isoformat(),
            "url": link,
            "venue": "Life Drawing Boston",
            "price": price,
            "category": "art",
        })
    events.sort(key=lambda x: x["date"])
    return events


def scrape_bostonfac(url, ua):
    """Boston Figure Art Center (BFAC, Somerville) — figure sessions, drawing clubs, & workshops."""
    events = []
    now = datetime.now(timezone.utc)

    try:
        session_id = "".join(random.choices(string.ascii_letters + string.digits, k=40))
        csrf_url = f"https://widgets-api.www.wellnessliving.com/api/csrf?sessionId={session_id}"
        csrf_resp = _SESSION.get(csrf_url, headers={"User-Agent": ua or UA_CHROME}, timeout=10)
        if csrf_resp.status_code != 200:
            return events
        csrf = csrf_resp.json().get("csrf")
        if not csrf:
            return events

        auth_id = "raa-UXnOYOs5JPTnSb3l"
        dt_request = now.strftime("%Y-%m-%d %H:%M:%S")
        http_date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
        csrf_parts = csrf.split(".")
        csrf_check = f"{session_id}.{csrf_parts[0][:5]}.{csrf_parts[1]}"

        # 1. Fetch class pricing map via ClassView/Element.json
        class_prices = {}
        try:
            params_cv = {"k_business": "693029", "k_class": ""}
            sig_lines_cv = ["Core\\Request\\Api::20210304-cors", dt_request, "www.wellnessliving.com", auth_id, "GET", "Wl/Classes/ClassView/Element.json", csrf]
            for k in sorted(params_cv.keys()):
                sig_lines_cv.append(f"{k.lower()}={params_cv[k]}")
            sig_check_cv = "".join([hashlib.sha256(line.encode("utf-8")).hexdigest()[:1] for line in sig_lines_cv])
            sig_hash_cv = hashlib.sha256("\n".join(sig_lines_cv).encode("utf-8")).hexdigest()
            auth_header_cv = f"20210304-cors,{auth_id},,{csrf_check},{sig_hash_cv}.2.{sig_check_cv}.."

            url_cv = "https://www.wellnessliving.com/Wl/Classes/ClassView/Element.json?" + urllib.parse.urlencode(params_cv)
            resp_cv = _SESSION.get(url_cv, headers={
                "User-Agent": ua or UA_CHROME,
                "Authorization": auth_header_cv,
                "X-Signature-Date": http_date,
                "X-Signature-Timezone": "300"
            }, timeout=10)
            if resp_cv.status_code == 200:
                cv_data = resp_cv.json().get("a_class_list", {})
                for cid, cinfo in cv_data.items():
                    sched = cinfo.get("a_schedule", [])
                    for sc in sched:
                        mp = sc.get("m_price")
                        if mp:
                            try:
                                class_prices[cid] = float(mp)
                            except Exception:
                                pass
                            break
        except Exception:
            pass

        # 2. Fetch session schedule
        start_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        end_str = (now + timedelta(days=35)).strftime("%Y-%m-%d")

        params = {
            "dt_date": start_str,
            "dt_end": end_str,
            "is_response_short": "0",
            "is_tab_all": "1",
            "k_business": "693029",
            "k_class_tab": "",
            "s_staff": "",
            "s_staff_uid": "",
            "show_book_status": "0",
            "show_cancel": "0",
            "show_class": "1",
            "show_event": "1",
            "show_quick_filter": "0",
            "show_ticket": "0",
            "uid": "",
        }

        sig_lines = [
            "Core\\Request\\Api::20210304-cors",
            dt_request,
            "www.wellnessliving.com",
            auth_id,
            "POST",
            "Wl/Schedule/ClassList/ClassList68.json",
            csrf,
        ]
        for k in sorted(params.keys()):
            sig_lines.append(f"{k.lower()}={params[k]}")

        sig_check = "".join([hashlib.sha256(line.encode("utf-8")).hexdigest()[:1] for line in sig_lines])
        full_str = "\n".join(sig_lines)
        sig_hash = hashlib.sha256(full_str.encode("utf-8")).hexdigest()
        final_sig = f"{sig_hash}.2.{sig_check}.."
        auth_header = f"20210304-cors,{auth_id},,{csrf_check},{final_sig}"

        post_url = "https://www.wellnessliving.com/Wl/Schedule/ClassList/ClassList68.json"
        headers = {
            "User-Agent": ua or UA_CHROME,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Authorization": auth_header,
            "X-Signature-Date": http_date,
            "X-Signature-Timezone": "300",
        }

        resp = _SESSION.post(post_url, data=params, headers=headers, timeout=15)
        if resp.status_code != 200:
            return events
        data = resp.json()
        sessions = data.get("a_session", [])
    except Exception:
        return events

    seen = set()
    for s in sessions:
        title = (s.get("s_title") or "").strip()
        if not title:
            continue
        raw_dt = s.get("dt_date")
        if not raw_dt:
            continue
        try:
            dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if dt < now:
            continue

        cid = str(s.get("k_class") or "")
        link = (s.get("url_book") or "https://www.bostonfac.com/figuresessions").strip()
        desc_lower = (s.get("html_description") or "").lower()
        t_lower = title.lower()

        f_price = class_prices.get(cid)
        if f_price is not None and f_price > 0:
            price = f"${f_price:.0f}"
        elif "free" in t_lower or "*free" in desc_lower or "free for members" in desc_lower or "free, members-only" in desc_lower or "opening reception" in t_lower:
            price = "Free"
        elif f_price == 0.0 and ("class" in t_lower or "workshop" in t_lower):
            price = "Check link"
        else:
            price = "$30"

        key = (title, dt.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "name": title,
            "date": dt.isoformat(),
            "url": link,
            "venue": "Boston Figure Art Center",
            "price": price,
            "category": "art",
        })
    events.sort(key=lambda x: x["date"])
    return events


# ---------------------------------------------------------------------------
# Music venues found missing in a comparison with bostonshows.org (Nov 2026).
# Each reads the venue's own calendar; shared date/time/price helpers first.
# ---------------------------------------------------------------------------

_MONTH_NUM = {name: i for i, names in enumerate(
    [(), ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",), ("june", "jun"),
     ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"),
     ("december", "dec")]) for name in names}
_WEEKDAY_NUM = {d: i for i, d in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])}
_CLOCK_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?(?![\w:])", re.I)


def _clock(text, assume_pm=True):
    """'7:30', '7 PM', '12:15 p.m.' -> (hour, minute). A bare 1-11 is an evening show time."""
    m = _CLOCK_RE.search(text or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    ap = (m.group(3) or "").lower()
    if h > 23 or mi > 59:
        return None
    if ap.startswith("p") and h < 12:
        h += 12
    elif ap.startswith("a") and h == 12:
        h = 0
    elif not ap and assume_pm and 1 <= h < 12:
        h += 12
    return h, mi


def _month_day(month_name, day, today=None):
    """A month/day without a year -> the nearest such date (a December list read in January stays December)."""
    today = today or datetime.now(EASTERN).date()
    month = _MONTH_NUM.get((month_name or "").strip(". ").lower())
    if not month:
        return None
    try:
        d = date(today.year, month, int(day))
    except ValueError:
        return None
    if (d - today).days < -183:
        d = d.replace(year=d.year + 1)
    elif (d - today).days > 183:
        d = d.replace(year=d.year - 1)
    return d


def _et_iso(d, hm):
    h, mi = hm or (19, 0)
    return datetime(d.year, d.month, d.day, h, mi, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()


def _price_from_text(text):
    """'$15 (cash or Venmo at the door)' -> '$15'; 'Free; tips appreciated' -> 'Free'; else None."""
    p = admission_price(text or "")
    if p:
        return p
    return "Free" if mentions_free(text or "") else None


def _text_lines(soup):
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return [re.sub(r"\s+", " ", l).strip() for l in soup.get_text("\n").split("\n") if l.strip()]


# --- Elfsight Event Calendar widget (McCarthy's & Toad) ---------------------------------------

_ELF_DAYS = {"mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6}


def _elfsight_settings(page_url, widget_id, ua):
    """The widget's settings (events, locations), from the same public endpoint the widget itself loads."""
    r = _SESSION.get("https://core.service.elfsight.com/p/boot/", params={"page": page_url, "w": widget_id},
                     headers={"User-Agent": ua or UA_CHROME}, timeout=20)
    r.raise_for_status()
    widgets = (r.json().get("data") or {}).get("widgets") or {}
    w = widgets.get(widget_id) or next(iter(widgets.values()), {})
    return (w.get("data") or {}).get("settings") or {}


def _elf_date(v):
    if isinstance(v, dict):
        v = v.get("date")
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date()
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _elfsight_occurrences(ev, start_day, end_day):
    """(date, 'HH:MM') for each time an Elfsight event happens between start_day and end_day."""
    st = ev.get("start") or {}
    first = _elf_date(st)
    if not first:
        return []
    t = st.get("time") or "19:00"
    period = ev.get("repeatPeriod") or "noRepeat"
    interval = max(1, int(ev.get("repeatInterval") or 1))
    ends = ev.get("repeatEnds") or "never"
    until = _elf_date(ev.get("repeatEndsDate")) if ends == "onDate" else None
    max_count = int(ev.get("repeatEndsOccurrences") or 1) if ends == "afterOccurrences" else None
    last = min(end_day, until) if until else end_day

    days = []
    if period == "noRepeat":
        days = [first]
    elif period in ("weeklyOn", "weekly"):
        wanted = {_ELF_DAYS[d] for d in (ev.get("repeatWeeklyOnDays") or []) if d in _ELF_DAYS} or {first.weekday()}
        week0 = first - timedelta(days=first.weekday())
        d = first
        while d <= last:
            if d.weekday() in wanted and ((d - week0).days // 7) % interval == 0:
                days.append(d)
            d += timedelta(days=1)
    elif period == "daily":
        d = first
        while d <= last:
            days.append(d)
            d += timedelta(days=interval)
    elif period in ("nthDayInMonth", "monthly", "monthlyOn"):
        nth = (first.day - 1) // 7
        y, m = first.year, first.month
        while date(y, m, 1) <= last:
            if period == "nthDayInMonth":
                d1 = date(y, m, 1)
                d = d1 + timedelta(days=(first.weekday() - d1.weekday()) % 7 + 7 * nth)
            else:
                try:
                    d = date(y, m, first.day)
                except ValueError:
                    d = None
            if d and d.month == m and first <= d <= last:
                days.append(d)
            m += interval
            while m > 12:
                y, m = y + 1, m - 12
    else:
        days = [first]
    if max_count:
        days = days[:max_count]

    skip, moved = set(), []
    for x in ev.get("exceptions") or []:
        orig = _elf_date(x.get("originalDate"))
        if not orig:
            continue
        skip.add(orig)
        if x.get("type") == "reschedule":
            nd = _elf_date(x.get("rescheduledStart"))
            if nd:
                moved.append((nd, (x.get("rescheduledStart") or {}).get("time") or t))
    out = [(d, t) for d in days if d not in skip] + moved
    return [(d, tt) for d, tt in out if start_day <= d <= end_day]


def scrape_elfsight_calendar(url, ua, widget_id, venue_for_location=None, default_venue=None, days=21):
    s = _elfsight_settings(url, widget_id, ua)
    locs = {l.get("id"): (l.get("name") or "").strip() for l in s.get("locations") or []}
    today = datetime.now(EASTERN).date()
    end = today + timedelta(days=days)
    events = []
    for ev in s.get("events") or []:
        name = html.unescape(re.sub(r"\s+", " ", ev.get("name") or "")).strip()
        if not name or is_placeholder_or_closed_event(name):
            continue
        desc = BeautifulSoup(ev.get("description") or "", "html.parser").get_text(" ", strip=True)
        loc_ids = ev.get("location") or []
        loc = locs.get(loc_ids[0], "") if loc_ids else ""
        venue = (venue_for_location(loc) if venue_for_location else loc) or default_venue
        for d, hhmm in _elfsight_occurrences(ev, today, end):
            try:
                hm = tuple(int(x) for x in hhmm.split(":")[:2])
            except ValueError:
                hm = (19, 0)
            events.append({
                "name": name,
                "date": _et_iso(d, hm),
                "url": url,
                "venue": venue,
                "price": _price_from_text(desc),
                "description": desc[:500],
            })
    return events


def scrape_toad(url, ua):
    """McCarthy's and Toad (Porter Square): one Elfsight calendar covers Toad's stage, upstairs at
    McCarthy's and the session table, recurring sessions included."""
    def venue(loc):
        return "Toad" if "toad" in (loc or "").lower() else "McCarthy's"
    return scrape_elfsight_calendar(url, ua, "3fdd143a-e20d-4e92-9fcb-84d101240a59",
                                    venue_for_location=venue, default_venue="McCarthy's")


# --- Redbones / Underbones -----------------------------------------------------------------------

_EVERY_UNTIL_RE = re.compile(r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
                             r"(?:\s+until\s+(\d{1,2})\s+([a-z]+))?", re.I)


def scrape_underbones(url, ua):
    """Redbones (Davis Square) and Underbones, its basement venue: redbones.com/happenings lists the
    next date of each event; 'Every Friday until 18 Dec' repeats it."""
    soup = fetch_soup(url, ua)
    today = datetime.now(EASTERN).date()
    horizon = today + timedelta(days=21)
    events = []
    for li in soup.select("li.rb-event"):
        day, mon, title = (li.select_one(".rb-event__day"), li.select_one(".rb-event__month"),
                           li.select_one(".rb-event__title"))
        if not (day and mon and title):
            continue
        d = _month_day(mon.get_text(strip=True), day.get_text(strip=True), today)
        if not d:
            continue
        name = title.get_text(" ", strip=True)
        room = li.select_one(".rb-event__venue")
        venue = "Underbones" if room and "underbones" in room.get_text().lower() else "Redbones"
        tm = li.select_one(".rb-event__time")
        hm = _clock(tm.get_text(" ", strip=True)) if tm else None
        body = li.get_text(" ", strip=True)
        a = li.find("a", href=True)
        cat = (li.get("data-category") or "").lower()
        base = {"name": name, "url": urljoin(url, a["href"]) if a else url, "venue": venue,
                "price": _price_from_text(body), "category": "gaming" if cat == "trivia" else "music",
                "description": body[:400]}
        dates = [d]
        rep = _EVERY_UNTIL_RE.search(body)
        if rep and _WEEKDAY_NUM[rep.group(1).lower()] == d.weekday():
            stop = _month_day(rep.group(3), rep.group(2), today) if rep.group(2) else horizon
            nxt = d + timedelta(weeks=1)
            while nxt <= min(stop or horizon, horizon):
                dates.append(nxt)
                nxt += timedelta(weeks=1)
        for x in dates:
            events.append({**base, "date": _et_iso(x, hm)})
    return events


# --- POSTunderground (Brookline) -------------------------------------------------------------------

_DAY_HEADER_RE = re.compile(r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+([a-z]+)\.?\s+"
                            r"(\d{1,2})(?:st|nd|rd|th)?\b\s*(.*)$", re.I)


def _act_name(text):
    """'(bands performing here for the first time) Nathaniel Plocinski Group (all the way from Maine)! ...'
    -> 'Nathaniel Plocinski Group'."""
    t = re.sub(r"^\([^)]*\)\s*", "", text.replace("\xa0", " ")).strip()
    t = re.split(r"\s+(?:performs|presents|plays|featuring)\b|[(!.,;]", t, maxsplit=1)[0]
    return t.strip(" :-")[:90]


def scrape_postunderground(url, ua):
    """POSTunderground jazz nights: the home page lists each date ('Friday, November 6th') followed by
    set times ('7:30' then 'Band:' and its lineup, or '7 PM: Orchestra performs ...'). Free admission."""
    lines = _text_lines(fetch_soup(url, ua))
    events, cur, i = [], None, 0
    is_time = lambda s: re.fullmatch(r"\d{1,2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?", s, re.I)
    while i < len(lines):
        line = lines[i]
        m = _DAY_HEADER_RE.match(line)
        if m:
            cur = _month_day(m.group(2), m.group(3))
            i += 1
            continue
        if cur and is_time(line) and i + 1 < len(lines):
            title = lines[i + 1].rstrip(":").strip()
            details = ""
            if i + 2 < len(lines) and not is_time(lines[i + 2]) and not _DAY_HEADER_RE.match(lines[i + 2]):
                details = lines[i + 2]
            if "feature" in title.lower() and details:
                title = _act_name(details) or title
            events.append({"name": title, "date": _et_iso(cur, _clock(line)), "url": url,
                           "venue": "POSTunderground", "price": "Free", "description": details[:400]})
            i += 3 if details else 2
            continue
        inline = re.match(r"^(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\s*:\s*(.+)$", line, re.I)
        if cur and inline:
            events.append({"name": _act_name(inline.group(2)), "date": _et_iso(cur, _clock(inline.group(1))),
                           "url": url, "venue": "POSTunderground", "price": "Free",
                           "description": inline.group(2)[:400]})
        i += 1
    return events


# --- Lower Mills Tavern (Dorchester) -----------------------------------------------------------------

def scrape_lower_mills_tavern(url, ua):
    """Lower Mills Tavern lists 'November 10th - Joe Sabourin'; music is Tuesdays 7 pm and Thursdays
    7:30 pm, no cover (both from the same page)."""
    events = []
    for line in _text_lines(fetch_soup(url, ua)):
        m = re.match(r"^([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*[-–—]\s*(.+)$", line)
        if not m or m.group(1).lower() not in _MONTH_NUM:
            continue
        act = m.group(3).strip()
        if re.search(r"\bclosed\b|happy thanksgiving|no music", act, re.I):
            continue
        d = _month_day(m.group(1), m.group(2))
        if not d:
            continue
        hm = (19, 30) if d.weekday() == 3 else (19, 0)
        events.append({"name": act, "date": _et_iso(d, hm), "url": url, "venue": "Lower Mills Tavern",
                       "price": "Free"})
    return events


# --- King's Chapel Tuesday recitals --------------------------------------------------------------------

def scrape_kings_chapel(url, ua):
    """King's Chapel's Tuesday 12:15 recitals: 'Upcoming Performances' pairs a performer line with
    'Tuesday, November 10, 12:15 p.m.'; later months are 'Recitals - December' then day / performer.
    $5 suggested donation (stated on the page)."""
    soup = fetch_soup(url, ua)
    lines = _text_lines(soup)
    donation = re.search(r"suggested donation[^$.]*\$(\d+)|\$(\d+)\s*suggested donation", " ".join(lines), re.I)
    price = f"${donation.group(1) or donation.group(2)} suggested" if donation else None
    events, month = [], None
    for i, line in enumerate(lines):
        m = re.match(r"^(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),\s+([a-z]+)\s+(\d{1,2}),?\s*(.*)$",
                     line, re.I)
        if m and i > 0:
            d = _month_day(m.group(1), m.group(2))
            if d:
                events.append({"name": lines[i - 1], "date": _et_iso(d, _clock(m.group(3), assume_pm=False) or (12, 15)),
                               "url": url, "venue": "King's Chapel", "price": price})
            continue
        hdr = re.match(r"^recitals\s*[-–]\s*([a-z]+)$", line, re.I)
        if hdr:
            month = hdr.group(1)
            continue
        if month and re.fullmatch(r"\d{1,2}", line) and i + 1 < len(lines) and not re.fullmatch(r"\d{1,2}", lines[i + 1]):
            d = _month_day(month, line)
            if d:
                events.append({"name": lines[i + 1], "date": _et_iso(d, (12, 15)), "url": url,
                               "venue": "King's Chapel", "price": price})
    return events


# --- Faces Brewing (Malden) ---------------------------------------------------------------------------

def scrape_faces_brewing(url, ua):
    """Faces Brewing sells show tickets as Squarespace products: the events page embeds each one's
    title, ticket price and a description starting '7 pm - November 11th, 2026'."""
    soup = fetch_soup(url, ua)
    pl = soup.select_one(".product-list[data-context]")
    if not pl:
        return []
    try:
        items = json.loads(pl["data-context"]).get("items") or []
    except ValueError:
        return []
    events = []
    for it in items:
        desc = BeautifulSoup(it.get("description") or "", "html.parser").get_text(" ", strip=True)
        m = re.search(r"(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\s*[-–]\s*([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?", desc, re.I)
        if not m:
            continue
        d = _month_day(m.group(2), m.group(3))
        if not d:
            continue
        price = None
        try:
            v = float((it.get("price") or {}).get("value"))
            price = "Free" if v == 0 else (f"${v:g}" if v == int(v) else f"${v:.2f}")
        except (TypeError, ValueError):
            pass
        if it.get("soldOut"):
            price = f"{price} (sold out)" if price else "Sold out"
        events.append({"name": html.unescape(it.get("title") or "").strip(), "date": _et_iso(d, _clock(m.group(1))),
                       "url": urljoin(url, it.get("fullUrl") or ""), "venue": "Faces Brewing", "price": price,
                       "description": desc[:400]})
    return events


# --- GBH (Brighton studios and the BPL studio) ------------------------------------------------------------

def scrape_gbh_events(url, ua):
    """GBH's events page: 'title / 7:15pm / Thu, Nov 5, 2026 / description' blocks. Concerts and talks
    at the Fraser Performance Studio (Brighton), the GBH studio in the Copley library, and elsewhere."""
    soup = fetch_soup(url, ua)
    links = {}
    for a in soup.find_all("a", href=True):
        txt = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if "/events/" in a["href"] and txt:
            links.setdefault(txt.lower(), urljoin(url, a["href"]))
    lines = _text_lines(soup)
    events = []
    for i in range(1, len(lines) - 1):
        tm = re.fullmatch(r"\d{1,2}(?::\d{2})?\s*[ap]m", lines[i], re.I)
        dm = re.fullmatch(r"[A-Za-z]{3},\s+([A-Za-z]{3})\s+(\d{1,2}),\s*(\d{4})", lines[i + 1])
        if not (tm and dm):
            continue
        title = lines[i - 1]
        d = _month_day(dm.group(1), dm.group(2))
        desc = " ".join(lines[i + 2:i + 4])
        low = desc.lower()
        if "fraser" in low:
            venue = "GBH Fraser Performance Studio"
        elif "copley" in low or "bpl studio" in low:
            venue = "GBH Studio at the Boston Public Library"
        elif "shaw roxbury" in low:
            venue = "Boston Public Library (Shaw-Roxbury)"
        else:
            venue = "GBH Studios"
        music = re.search(r"\b(music|jazz|concert|recital|pianist|quartet|orchestra|band)\b", f"{title} {desc}", re.I)
        events.append({"name": title, "date": _et_iso(d, _clock(lines[i])), "url": links.get(title.lower(), url),
                       "venue": venue, "price": _price_from_text(desc), "category": "music" if music else "community",
                       "description": desc[:400]})
    return events


# --- Off the Rails (Downtown) -------------------------------------------------------------------------------

def scrape_off_the_rails(url, ua):
    """Off the Rails' own events list: free nights (open mic, karaoke, acoustics, DJs) as well as the
    ticketed shows Ticketweb has. Cards read 'Fri | Nov | 6 | Anthony Calla | Doors 7:00 PM · Show 8:00 PM
    | $17.20 | with fees'."""
    soup = fetch_soup(url, ua)
    events = []
    for card in soup.select("li.otr-rise"):
        parts = [p.strip() for p in card.get_text("|", strip=True).split("|") if p.strip()]
        mon = next((p for p in parts if p.lower()[:3] in _MONTH_NUM and len(p) <= 4), None)
        day = next((p for p in parts if re.fullmatch(r"\d{1,2}", p)), None)
        timeline = next((p for p in parts if re.search(r"\b(show|doors)\b.*\d", p, re.I)), "")
        if not (mon and day and timeline):
            continue
        title = parts[parts.index(timeline) - 1]
        show = re.search(r"show\s+(\d{1,2}(?::\d{2})?\s*[ap]m)", timeline, re.I)
        hm = _clock(show.group(1) if show else timeline)
        d = _month_day(mon, day)
        after = " ".join(parts[parts.index(timeline) + 1:])
        price = "Free" if re.search(r"free entry", after, re.I) else _price_from_text(after) or (
            re.search(r"\$\d+(?:\.\d{2})?", after).group(0) if re.search(r"\$\d+(?:\.\d{2})?", after) else None)
        a = card.find("a", href=True)
        events.append({"name": title, "date": _et_iso(d, hm), "url": urljoin(url, a["href"]) if a else url,
                       "venue": "Off the Rails Boston", "price": price})
    return events


def scrape_jazz_urbane(url, ua):
    return scrape_wix_events(url, ua, default_venue="Jazz Urbane Cafe", default_category="music")


def scrape_medford_brewing(url, ua):
    return scrape_tribe_rest_paged(url, ua, default_venue="Medford Brewing Company", default_category="music")




# --- Boston Shows, only for venues we can't read ---------------------------------------------------
# These venues block automated access or don't publish lineups as text (see source_health.py).
# bostonshows.org lists their shows by hand, so for these venues only we take its listings, credited.
# Everywhere else the venue's own calendar is the source. Boston Shows' name -> ours:
BOSTON_SHOWS_GAP_VENUES = {
    "wally's cafe": "Wally's Café",
    "the black rose": "The Black Rose",
    "kestra": "Kestra (Omni Boston Seaport)",
    "harvard university": "Harvard University (Harvard Square)",
    "memorial church": "Memorial Church (Harvard)",
    "silhouette lounge": "Silhouette Lounge",
    "lithuanian club": "Lithuanian Club",
    "an sibin": "An Síbín",
    "rosa y marigold": "Rosa y Marigold",
}


def scrape_boston_shows_gaps(url, ua, days=21):
    """bostonshows.org's listings at BOSTON_SHOWS_GAP_VENUES only (one page holds the whole calendar)."""
    soup = fetch_soup(url, ua)
    today = datetime.now(EASTERN).date()
    end = today + timedelta(days=days)
    events = []
    for day in soup.select("div.date-events[data-date]"):
        try:
            d = datetime.strptime(day["data-date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not today <= d <= end:
            continue
        for tr in day.select("tr.event"):
            ours = BOSTON_SHOWS_GAP_VENUES.get((tr.get("data-venue") or "").strip().lower())
            if not ours:
                continue
            title = tr.select_one(".event-title")
            start = tr.select_one(".event-start")
            if not (title and start):
                continue
            a = title.find("a", href=True)
            info = tr.select_one(".event-info")
            info = info.get_text(" ", strip=True) if info else ""
            first = info.split(" / ")[0].strip()
            price = first if re.search(r"\$|\bfree\b", first, re.I) else None
            if price and price.lower() == "free":
                price = "Free"
            events.append({
                "name": title.get_text(" ", strip=True),
                "date": _et_iso(d, _clock(start.get_text(" ", strip=True))),
                "url": a["href"] if a else url,
                "venue": ours,
                "price": price,
                "description": f"Listing via Boston Shows (bostonshows.org). {info}".strip(),
            })
    return events

_ALL_VENUES = [
    # Added from the Boston Shows coverage check: venues' own calendars
    {"name": "Square Root", "url": "https://tockify.com/api/feeds/ics/sqrozzietester", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "POSTunderground", "url": "https://postunderground.com/", "ua": UA_CHROME, "scraper": scrape_postunderground, "default_category": "music"},
    {"name": "Lower Mills Tavern", "url": "https://www.lowermillstavern.com/livemusicschedule/", "ua": UA_CHROME, "scraper": scrape_lower_mills_tavern, "default_category": "music"},
    {"name": "King's Chapel", "url": "https://www.kings-chapel.org/music/tuesday-recitals", "ua": UA_CHROME, "scraper": scrape_kings_chapel, "default_category": "music"},
    {"name": "Faces Brewing", "url": "https://www.facesbrewing.com/events", "ua": UA_CHROME, "scraper": scrape_faces_brewing, "default_category": "music"},
    {"name": "GBH Events", "url": "https://www.wgbh.org/events", "ua": UA_CHROME, "scraper": scrape_gbh_events, "default_category": "music"},
    {"name": "Jazz Urbane Cafe", "url": "https://www.jazzurbanecafe.com/events", "ua": UA_CHROME, "scraper": scrape_jazz_urbane, "default_category": "music"},
    {"name": "Medford Brewing Company", "url": "https://medfordbrew.com/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_medford_brewing, "default_category": "music"},
    {"name": "Village Social Club", "url": "https://calendar.google.com/calendar/ical/va8lree72bp7a14v0ftkfic0os%40group.calendar.google.com/public/basic.ics", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "music"},
    {"name": "Boston Shows (venues we can't read)", "url": "https://bostonshows.org/", "ua": UA_CHROME, "scraper": scrape_boston_shows_gaps, "default_category": "music"},
    {"name": "Luthier Collective", "url": "https://www.evabroadwaystrings.com/events", "ua": UA_CHROME, "scraper": scrape_squarespace_events, "default_category": "music"},
    {"name": "Life Drawing Boston", "url": "https://www.lifedrawingboston.com/calendar?format=json", "ua": UA_CHROME, "scraper": scrape_life_drawing_boston, "default_category": "art"},
    {"name": "Boston Figure Art Center", "url": "https://www.bostonfac.com/figuresessions", "ua": UA_CHROME, "scraper": scrape_bostonfac, "default_category": "art"},
    {"name": "The Platform Kendall", "url": "https://www.theplatformkendall.org/event-listing/", "ua": UA_CHROME, "scraper": scrape_the_platform_kendall, "default_category": "stage"},
    {"name": "Partiful Boston", "url": "https://partiful.com/explore/l/bos/events", "ua": UA_CHROME, "scraper": scrape_partiful, "default_category": "community"},
    {"name": "Luma Boston", "url": "https://lu.ma/boston", "ua": UA_CHROME, "scraper": scrape_luma, "default_category": "community"},
    {"name": "Luma Calendars", "url": "https://lu.ma/discover", "ua": UA_CHROME, "scraper": scrape_luma_calendars, "default_category": "community"},
    {"name": "ICA Boston", "url": "https://www.icaboston.org/events/", "ua": UA_CHROME, "scraper": scrape_ica, "default_category": "art"},
    {"name": "Cisco Brewers Fenway", "url": "https://ciscobrewersfenway.com/eventschedule", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar_block, "default_category": "music"},
    {"name": "Castle Island Brewing", "url": "https://castleislandbeer.com/public-events", "ua": UA_CHROME, "scraper": scrape_squarespace_calendar_block, "default_category": "food"},
    {"name": "City of Somerville", "url": "https://www.somervillema.gov/events", "ua": UA_CHROME, "scraper": scrape_somerville_city, "default_category": "community"},
    {"name": "Northeastern University", "url": "https://calendar.northeastern.edu/api/2/events?days=45", "ua": UA_CHROME, "scraper": scrape_northeastern, "default_category": "community"},
    {"name": "Improv Asylum", "url": "https://calendar.improvasylum.com", "ua": UA_CHROME, "scraper": scrape_improv_asylum, "default_category": "comedy"},
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
    {"name": "Off the Rails Boston", "url": "https://www.offtherailsboston.com/events", "ua": UA_CHROME, "scraper": scrape_off_the_rails, "default_category": "music"},
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
    {"name": "Harvard/Central PoGO", "url": "https://apps.apple.com/us/app/niantic-campfire/id1608154490", "ua": UA_CHROME, "scraper": scrape_harvard_pogo_meetups, "default_category": "gaming"},
    {"name": "Make Friends After College (via Eventbrite)", "url": "https://www.eventbrite.com/o/make-friends-after-college-98390790901", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "The Boston Calendar", "url": "https://www.thebostoncalendar.com/events", "ua": UA_CHROME, "scraper": scrape_boston_calendar, "default_category": None},
    {"name": "City Winery Boston", "url": "https://citywinery.com/pages/locations/boston", "ua": UA_CHROME, "scraper": scrape_city_winery, "default_category": "music"},
    {"name": "Bowery Presents Boston", "url": "https://www.bowerypresents.com/boston", "ua": UA_CHROME, "scraper": scrape_bowery_boston, "default_category": "music"},
    {"name": "Royale Boston", "url": "https://www.royaleboston.com/events/", "ua": UA_CHROME, "scraper": scrape_royale, "default_category": "clubbing"},
    {"name": "MIT Events", "url": "https://calendar.mit.edu/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "community"},
    {"name": "Boston Symphony Orchestra", "url": "https://www.bso.org/events", "ua": UA_CHROME, "scraper": scrape_bso, "default_category": "music"},
    {"name": "Venture Café Cambridge", "url": "https://community.venturecafecambridge.org/", "ua": UA_CHROME, "scraper": scrape_venture_cafe, "default_category": "community"},
    {"name": "The Anchor Boston", "url": "https://calendar.google.com/calendar/ical/theanchorbostonma%40gmail.com/public/basic.ics", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "community"},
    {"name": "Artisans Asylum", "url": "https://www.eventbrite.com/o/artisans-asylum-inc-18841526871", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "ManRay Cambridge", "url": "https://manrayclub.com/monthly-calendar/", "ua": UA_CHROME, "scraper": scrape_manray, "default_category": "clubbing"},
    {"name": "Middlesex Lounge", "url": "https://www.msexcambridge.com", "ua": UA_CHROME, "scraper": scrape_middlesex, "default_category": "clubbing"},
    {"name": "Roxy's Arcade", "url": "https://www.roxysarcade.com/event-schedule", "ua": UA_CHROME, "scraper": scrape_roxys_arcade, "default_category": "gaming"},
    {"name": "The Phoenix Landing", "url": "https://www.thephoenixlanding.com/events", "ua": UA_CHROME, "scraper": scrape_phoenix_landing, "default_category": "clubbing"},
    {"name": "Esplanade Association", "url": "https://esplanade.org/events/", "ua": UA_CHROME, "scraper": scrape_esplanade, "default_category": "outdoors"},
    {"name": "Eventbrite Cambridge", "url": "https://www.eventbrite.com/d/ma--cambridge/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Eventbrite Somerville", "url": "https://www.eventbrite.com/d/ma--somerville/events/", "ua": UA_CHROME, "scraper": scrape_eventbrite_search, "default_category": None},
    {"name": "Cambridge Crossing (via Eventbrite)", "url": "https://www.eventbrite.com/o/cambridge-crossing-30339024896", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "community"},
    {"name": "Lamplighter Brewing (via Eventbrite)", "url": "https://www.eventbrite.com/o/lamplighter-brewing-co-12408758507", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "food"},
    {"name": "Do617", "url": "https://do617.com/events", "ua": UA_CHROME, "scraper": scrape_do617, "default_category": None},
    {"name": "Middle East Cambridge", "url": "https://mideastoffers.com", "ua": UA_CHROME, "scraper": scrape_middle_east, "default_category": "music"},
    {"name": "The Wilbur", "url": "https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZAEAIvA&size=100&sort=date,asc", "ua": UA_CHROME, "scraper": scrape_ticketmaster_discovery, "default_category": "comedy"},
    {"name": "The Dance Complex", "url": "https://www.dancecomplex.org/events/?ical=1", "ua": UA_CHROME, "scraper": scrape_ical, "default_category": "dance"},
    {"name": "Dorchester Brewing Company", "url": "https://www.dorchesterbrewing.com/events/", "ua": UA_CHROME, "scraper": scrape_dorchester_brewing, "default_category": "food"},
    {"name": "The Huntington Theatre", "url": "https://www.huntingtontheatre.org/season/", "ua": UA_CHROME, "scraper": scrape_huntington_theatre, "default_category": "theater"},
    {"name": "CCAE (Cambridge Center for Adult Education)", "url": "https://ccae.org/events", "ua": UA_CHROME, "scraper": scrape_ccae, "default_category": "community"},
    {"name": "Brookline Booksmith", "url": "https://www.brooklinebooksmith.com/events", "ua": UA_CURL, "scraper": scrape_event_list, "default_category": "books"},
    {"name": "Gardner Museum", "url": "https://www.gardnermuseum.org/calendar", "ua": UA_CHROME, "scraper": scrape_gardner, "default_category": "community"},
    {"name": "Brattle Theatre", "url": "https://www.brattlefilm.org/", "ua": UA_CHROME, "scraper": scrape_brattle, "default_category": "film"},
    {"name": "Meetup Boston", "url": "https://www.meetup.com/find/?location=us--ma--boston&source=EVENTS&eventType=inPerson&distance=tenMiles", "ua": UA_CHROME, "scraper": scrape_meetup, "default_category": "community"},
    {"name": "Meetup Boston (by topic)", "url": "https://www.meetup.com/find/?location=us--ma--boston&source=EVENTS&eventType=inPerson", "ua": UA_CHROME, "scraper": scrape_meetup_topics, "default_category": "community"},
    {"name": "Somerville Board Games Meetup", "url": "https://www.meetup.com/somerville-board-games-meetup-group/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Beantown Gamers", "url": "https://www.meetup.com/boardgames-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Cambridge Game Night", "url": "https://www.meetup.com/CambridgeGameNight/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Unplugged Gaming Boston", "url": "https://www.meetup.com/unplugged-gaming-of-boston-surrounding-areas/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Boston Python", "url": "https://www.meetup.com/bostonpython/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Skip the Small Talk Boston", "url": "https://www.meetup.com/skip-the-small-talk-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston Japanese Language Exchange", "url": "https://www.meetup.com/bostonjapanese/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "community"},
    {"name": "Boston Indie Game Devs", "url": "https://www.meetup.com/bostongamedev/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Unplugged Boston", "url": "https://www.meetup.com/unplugged-boston/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "gaming"},
    {"name": "Revolutionary Spaces", "url": "https://revolutionaryspaces.org/explore/program-calendar/", "ua": UA_CHROME, "scraper": scrape_jsonld, "default_category": "community"},
    {"name": "WBUR CitySpace", "url": "https://www.wbur.org/events", "ua": UA_CHROME, "scraper": scrape_wbur_cityspace, "default_category": "books"},
    {"name": "Harvard Museums of Science & Culture", "url": "https://hmsc.harvard.edu/upcoming-programs/", "ua": UA_CHROME, "scraper": scrape_hmsc, "default_category": "community"},
    {"name": "Long Live Roxbury", "url": "https://www.longlivebeerworks.com/boston", "ua": UA_CHROME, "scraper": scrape_long_live_roxbury, "default_category": "music"},
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
    {"name": "Brookline Public Library", "url": "https://brooklinelibrary.libcal.com/rss.php?m=month&cid=20102", "ua": UA_CHROME, "scraper": scrape_brookline_library, "default_category": "community"},
    {"name": "Boston Children's Museum", "url": "https://bostonchildrensmuseum.org/wp-json/wp/v2/ajde_events", "ua": UA_CHROME, "scraper": scrape_boston_childrens_museum, "default_category": "family"},
    {"name": "New England Aquarium", "url": "https://www.neaq.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_tribe_rest, "default_category": "family"},
    {"name": "Watertown Library (kids)", "url": "https://watertownlib.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_watertown_library_kids, "default_category": "family"},
    {"name": "Medford Library (kids)", "url": "https://medfordlibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_medford_library_kids, "default_category": "family"},
    {"name": "Belmont Library (kids)", "url": "https://belmontpubliclibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_belmont_library_kids, "default_category": "family"},
    {"name": "Malden Library (kids)", "url": "https://maldenpubliclibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_malden_library_kids, "default_category": "family"},
    {"name": "Waltham Library (kids)", "url": "https://waltham.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_waltham_library_kids, "default_category": "family"},
    {"name": "Quincy Library (kids)", "url": "https://thomascranelibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_quincy_library_kids, "default_category": "family"},
    {"name": "Lexington Library (kids)", "url": "https://carylibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_lexington_library_kids, "default_category": "family"},
    {"name": "Melrose Library (kids)", "url": "https://melrosepubliclibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_melrose_library_kids, "default_category": "family"},
    {"name": "Revere Library (kids)", "url": "https://reverepubliclibrary.assabetinteractive.com/calendar/", "ua": UA_CHROME, "scraper": scrape_revere_library_kids, "default_category": "family"},
    {"name": "Newton Library (kids)", "url": "https://newtonfreelibrary.libcal.com/rss.php?m=month&cid=3836", "ua": UA_CHROME, "scraper": scrape_newton_library_kids, "default_category": "family"},
    {"name": "Milton Library (kids)", "url": "https://miltonlibrary.libcal.com/rss.php?m=month&cid=20657", "ua": UA_CHROME, "scraper": scrape_milton_library_kids, "default_category": "family"},
    {"name": "Arnold Arboretum", "url": "https://arboretum.harvard.edu/wp-json/tribe/events/v1/events?per_page=50", "ua": UA_CHROME, "scraper": scrape_arnold_arboretum, "default_category": "outdoors"},
    {"name": "Museum of Science", "url": "https://www.mos.org/api/v1/event-listing/event_detail/96+101/all/all/all/all", "ua": UA_CHROME, "scraper": scrape_museum_of_science, "default_category": "community"},
    {"name": "Mount Auburn Cemetery", "url": "https://mountauburn.org/events/?ical=1", "ua": UA_CHROME, "scraper": scrape_mount_auburn, "default_category": "outdoors"},
    {"name": "Franklin Park Coalition", "url": "https://www.franklinparkcoalition.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_franklin_park_coalition, "default_category": "outdoors"},
    {"name": "Mass Audubon Habitat (Belmont)", "url": "https://www.massaudubon.org/programs/habitat", "ua": UA_CHROME, "scraper": scrape_mass_audubon_habitat, "default_category": "outdoors"},
    {"name": "Mass Audubon Drumlin Farm", "url": "https://www.massaudubon.org/programs/drumlin-farm", "ua": UA_CHROME, "scraper": scrape_mass_audubon_drumlin_farm, "default_category": "outdoors"},
    {"name": "Mass Audubon Magazine Beach", "url": "https://www.massaudubon.org/programs/magazine-beach", "ua": UA_CHROME, "scraper": scrape_mass_audubon_magazine_beach, "default_category": "outdoors"},
    {"name": "Mass Audubon Boston Nature Center", "url": "https://www.massaudubon.org/programs/boston-nature-center", "ua": UA_CHROME, "scraper": scrape_mass_audubon_boston_nature_center, "default_category": "outdoors"},
    {"name": "Somerville Museum", "url": "https://www.somervillemuseum.org/calendar-events", "ua": UA_CHROME, "scraper": scrape_squarespace_events, "default_category": "community"},
    {"name": "Eventbrite (kids & parents)", "url": "https://www.eventbrite.com/d/ma--boston/parent/", "ua": UA_CHROME, "scraper": scrape_eventbrite_family, "default_category": "family"},
    {"name": "Cafe Zing", "url": "https://www.cafezingcambridge.com/events", "ua": UA_CHROME, "scraper": scrape_cafe_zing, "default_category": "community"},
    {"name": "Ikeda Center (via Eventbrite)", "url": "https://www.eventbrite.com/o/18029151775", "ua": UA_CHROME, "scraper": scrape_ikeda_center, "default_category": "community"},
    {"name": "Little Muse", "url": "https://littlemuse.substack.com", "ua": UA_CHROME, "scraper": scrape_little_muse, "default_category": "family"},
    {"name": "Puppet Showplace Theater", "url": "https://www.puppetshowplace.org/calendar", "ua": UA_CHROME, "scraper": scrape_puppet_showplace, "default_category": "family"},
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
    {"name": "Lovestruck Books (via Eventbrite)", "url": "https://www.eventbrite.com/o/lovestruck-books-92052235443", "ua": UA_CHROME, "scraper": scrape_eventbrite_org, "default_category": "books"},
    {"name": "The Comedy Studio", "url": "https://www.thecomedystudio.com/calendar", "ua": UA_CHROME, "scraper": scrape_comedy_studio, "default_category": "comedy"},
    {"name": "Salsa Vida Boston", "url": "https://www.salsavida.com/guides/massachusetts/", "ua": UA_CHROME, "scraper": scrape_salsavida, "default_category": "dance"},
    {"name": "Laugh Boston", "url": "https://laughboston.com", "ua": UA_CHROME, "scraper": scrape_laugh_boston, "default_category": "comedy"},
    {"name": "Calderwood Pavilion", "url": "https://www.bostontheatrescene.com/shows-and-events/", "ua": UA_CHROME, "scraper": scrape_calderwood_pavilion, "default_category": "theater"},
    {"name": "Central Square Theater", "url": "https://www.centralsquaretheater.org/shows/", "ua": UA_CHROME, "scraper": scrape_central_square_theater, "default_category": "theater"},
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
    {"name": "Boston Public Market", "url": "https://bostonpublicmarket.org/events/", "ua": UA_CHROME, "scraper": scrape_boston_public_market, "default_category": "food"},
    {"name": "Harvard Square Holiday Fair", "url": "https://www.harvardsquareholidayfair.com/", "ua": UA_CHROME, "scraper": scrape_harvard_square_holiday_fair, "default_category": "markets"},
    {"name": "Harvard Square (HSBA)", "url": "https://www.harvardsquare.com/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_harvard_square, "default_category": "community"},
    {"name": "Kendall Square Association", "url": "https://www.kendallsquare.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_kendall_square, "default_category": "community"},
    {"name": "Brighton Main Streets", "url": "https://www.brightonmainstreets.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_brighton_main_streets, "default_category": "community"},
    {"name": "Assembly Row", "url": "https://www.assemblyrow.com/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_assembly_row, "default_category": "community"},
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
    {"name": "Underbones", "url": "https://redbones.com/happenings/", "ua": UA_CHROME, "scraper": scrape_underbones, "default_category": "music"},
    {"name": "Cambridge Public Library", "url": "https://cambridgepl.libcal.com/rss.php?m=month&cid=7052", "ua": UA_CHROME, "scraper": scrape_cpl, "default_category": "community"},
    {"name": "Somerville Community Growing Center", "url": "https://www.thegrowingcenter.org/2026", "ua": UA_CHROME, "scraper": scrape_growing_center, "default_category": "outdoors"},
    {"name": "The Cantab Lounge", "url": "https://thecantablounge.com/", "ua": UA_CHROME, "scraper": scrape_tunehatch, "default_category": "music"},
    {"name": "Cantab Underground", "url": "https://thecantablounge.com/cantab/underground", "ua": UA_CHROME, "scraper": scrape_tunehatch, "default_category": "music"},
    {"name": "Harvard Art Museums", "url": "https://harvardartmuseums.org/calendar", "ua": UA_CHROME, "scraper": scrape_harvard_art_museums, "default_category": "art"},
    {"name": "Boston Lyric Opera", "url": "https://blo.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_tribe_rest, "default_category": "music"},
    {"name": "SpeakEasy Stage", "url": "https://speakeasystage.com/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_tribe_rest, "default_category": "theater"},
    {"name": "American Repertory Theater", "url": "https://americanrepertorytheater.org/shows-events/", "ua": UA_CHROME, "scraper": scrape_art, "default_category": "theater"},
    {"name": "Boston Ballet", "url": "https://cart.bostonballet.org", "ua": UA_CHROME, "scraper": scrape_boston_ballet, "default_category": "dance"},
    {"name": "Handel and Haydn Society", "url": "https://cart.handelandhaydn.org", "ua": UA_CHROME, "scraper": scrape_handel_haydn, "default_category": "classical"},
    {"name": "Harvard Film Archive", "url": "https://harvardfilmarchive.org/calendar", "ua": UA_CHROME, "scraper": scrape_harvard_film_archive, "default_category": "film"},
    {"name": "Midnight Runners Boston", "url": "https://www.heylo.com/events/26e9657b-085f-468f-bd45-304b48d68bdb/", "ua": UA_CHROME, "scraper": scrape_midnight_runners, "default_category": "sports"},
    {"name": "Somerville Road Runners", "url": "https://srr.org/", "ua": UA_CHROME, "scraper": scrape_somerville_road_runners, "default_category": "sports"},
    {"name": "Davis Square Runners", "url": "https://www.meetup.com/davissquarerunners/events/", "ua": UA_CHROME, "scraper": scrape_meetup_group, "default_category": "sports"},
    {"name": "November Project Boston", "url": "https://november-project.com/boston/", "ua": UA_CHROME, "scraper": scrape_november_project, "default_category": "sports"},
    {"name": "ArtsEmerson", "url": "https://artsemerson.org/wp-json/tribe/events/v1/events", "ua": UA_CHROME, "scraper": scrape_tribe_rest, "default_category": "theater"},
    {"name": "Lyric Stage Company", "url": "https://lyricstage.com/whats-on/", "ua": UA_CHROME, "scraper": scrape_lyric_stage, "default_category": "theater"},
    {"name": "Celebrity Series of Boston", "url": "https://www.celebrityseries.org/live-performances/performance-event-calendar/", "ua": UA_CHROME, "scraper": scrape_celebrity_series, "default_category": "music"},
    {"name": "LesbianNightLife", "url": "https://www.lesbiannightlife.com", "ua": UA_CHROME, "scraper": scrape_wix_events, "default_category": "clubbing"},
]

# Drop venues that require env vars we don't have set — keeps the fail banner clean.
VENUES = [v for v in _ALL_VENUES if not v.get("requires_env") or os.environ.get(v["requires_env"])]


# Static "useful links" — venues with no machine-readable calendar, but worth linking.
# Rendered in the "Useful links & ongoing" section.
STATIC_LINKS = [
    ("dance",   "Boston Lindy Hop — swing dances list", "https://bostonlindyhop.com/events/swing-dancing-in-boston/"),
    ("dance",   "Boston Swing Central", "https://www.bostonswingcentral.org/"),
    ("dance",   "Boston Outdoor Bachata & Salsa (BOBAS) — Esplanade pop-up announcements", "https://www.instagram.com/bobas.dance/"),
    ("dance",   "Tango Society of Boston", "https://bostontango.org/"),
    ("theater", "American Repertory Theater", "https://americanrepertorytheater.org/shows-events/"),
    ("theater", "Huntington Theatre Current Shows", "https://www.huntingtontheatre.org/season/"),
    ("theater", "Company One Theatre", "https://companyone.org/season/"),
    ("theater", "Commonwealth Shakespeare", "https://commshakes.org/season/"),
    ("music",   "Trillium Brewing (events)", "https://trilliumbrewing.com/pages/event-calendar"),
    ("food",    "Sam Adams Boston Brewery (events)", "https://www.samadamsbrewery.com/events"),
    ("music",   "Long Live Beerworks / Roxbury", "https://www.longlivebeerworks.com"),
    ("food",    "Castle Island Brewing (events)", "https://www.castleislandbeer.com/public-events"),
    ("music",   "Handel and Haydn Society", "https://handelandhaydn.org/concerts/"),
    ("music",   "Berklee Performance Center", "https://www.berklee.edu/BPC"),
    ("gaming",  "Harvard/Central PoGO (Campfire App on iOS)", "https://apps.apple.com/us/app/niantic-campfire/id1608154490"),
    ("theater", "Jacques' Cabaret (historic drag & cabaret)", "http://jacquescabaret.com/v3/"),
    ("clubbing","The Alley Bar (Downtown bear & leather bar)", "http://www.thealleybar.com/"),
    ("clubbing","Gay Mafia Boston (Legacy & Candystrip parties)", "https://www.gaymafiaboston.com"),
    ("clubbing","FERAL (@feral.party · queer/trans rager)", "https://www.instagram.com/feral.party"),
]


# Cheap-ticket / lottery / deal aggregators. Rendered in their own sidebar block.
DEAL_LINKS = [
    ("Huntington Theatre HYPE Pass ($25 Under 40)", "https://www.huntingtontheatre.org/flex-pass/"),
    ("LuckySeat (Boston lotteries)", "https://www.luckyseat.com/"),
    ("BosTix — same-day half-price (ArtsBoston)", "https://bostix.org/categories/bostix-deals/"),
    ("TodayTix Boston (lotteries + discounts)", "https://www.todaytix.com/boston"),
    ("Goldstar Boston discounts", "https://www.goldstar.com/cities/boston-ma"),
]


# Hand-curated weekly recurring events for venues that don't publish a
# structured calendar. Expanded into concrete dated entries at request time.
# Tuple: (venue_name, venue_url, default_category, [(title, event_url, weekday 0=Mon..6=Sun, hour, minute), ...])
MANUAL_RECURRING_EVENTS = [
    ("The Beehive", "https://www.beehiveboston.com/musiccalendar", "music", [
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 0, 19, 30),
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 1, 19, 30),
        ("Live Jazz & Soul @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 2, 19, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 3, 18, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 4, 18, 30),
        ("Live Music Night @ The Beehive", "https://www.beehiveboston.com/musiccalendar", 5, 18, 30),
        ("Live Music Weekend Brunch", "https://www.beehiveboston.com/musiccalendar", 5, 10, 0),
        ("Live Music Weekend Brunch", "https://www.beehiveboston.com/musiccalendar", 6, 10, 0),
        ("Blues on Sunday with Bruce Bears & Friends", "https://www.beehiveboston.com/musiccalendar", 6, 19, 30),
    ]),
    ("Loretta's Last Call", "https://www.lorettaslastcall.com/events/", "dance", [
        ("Partner Swing Dancing", "https://www.lorettaslastcall.com/events/", 0, 20, 0),
        ("Live Band Line Dancing", "https://www.lorettaslastcall.com/events/", 2, 20, 0),
        ("Sunday Line Dancing", "https://www.lorettaslastcall.com/events/", 6, 20, 0),
    ]),
    ("Sabina Mezcalería", "https://www.instagram.com/sabinamezcaleria/", "dance", [
        ("Sunday Live Salsa & Latin Jazz Brunch", "https://www.instagram.com/sabinamezcaleria/", 6, 13, 0),
    ]),
    ("Balance Patch", "https://www.balancepatch.com/events", "gaming", [
        ("Smash Bros Melee Weekly (Allston Melee)", "https://www.balancepatch.com/events", 1, 18, 30),
        ("Baystate Beatdown: Smash Ultimate Weekly", "https://smash.gg/baystate", 3, 18, 30),
        ("Fighting Game Community (FGC) Weekly: Street Fighter & Tekken", "https://www.balancepatch.com/events", 4, 19, 0),
        ("Balance Patch Weekend Community LAN & Casuals", "https://www.balancepatch.com/events", 5, 13, 0),
    ]),
    ("Central Square Farmers Market", "https://www.massfarmersmarkets.org/central", "food", [
        ("Central Square Farmers Market", "https://www.massfarmersmarkets.org/central", 0, 12, 0),
    ]),
    ("Copley Square Farmers Market", "https://www.massfarmersmarkets.org/copley", "food", [
        ("Copley Square Farmers Market", "https://www.massfarmersmarkets.org/copley", 1, 11, 0),
        ("Copley Square Farmers Market", "https://www.massfarmersmarkets.org/copley", 4, 11, 0),
    ]),
    ("Davis Square Farmers Market", "https://www.massfarmersmarkets.org/davis", "food", [
        ("Davis Square Farmers Market", "https://www.massfarmersmarkets.org/davis", 2, 12, 0),
    ]),
    ("Kendall Square Farmers Market", "https://www.massfarmersmarkets.org/kendall", "food", [
        ("Kendall Square Farmers Market", "https://www.massfarmersmarkets.org/kendall", 3, 12, 0),
    ]),
    ("Union Square Farmers Market", "https://www.unionsquaremain.org/union-square-farmers-market", "food", [
        ("Union Square Farmers Market", "https://www.unionsquaremain.org/union-square-farmers-market", 5, 9, 0),
    ]),
    ("SoWa Open Market", "https://sowaboston.com/open-market/", "community", [
        ("SoWa Open Market", "https://sowaboston.com/open-market/", 6, 10, 0),
    ]),
    ("SoWa Vintage Market", "https://sowavintagemkt.com/", "community", [
        ("SoWa Vintage Market", "https://sowavintagemkt.com/", 6, 11, 0, "Free"),
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
    ("Greenway Artisan Market", "https://www.rosekennedygreenway.org/events/", "art", [
        ("Greenway Artisan Market", "https://www.rosekennedygreenway.org/events/", 5, 11, 0),
    ]),
    ("Memorial Drive Sundays", "https://www.memorialdrivealliance.org", "outdoors", [
        ("Memorial Drive Car-Free Sundays", "https://www.memorialdrivealliance.org", 6, 11, 0),
    ]),
    ("Everybody Dance Now", "https://www.instagram.com/everybodydancenowboston/", "dance", [
        ("Outdoor Drop-in Dance Classes @ The Grove", "https://www.instagram.com/everybodydancenowboston/", 2, 18, 0),
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
    ("Redbones", "https://redbones.com/", "music", [
        ("Phrenology Trivia Night @ Underbones", "https://redbones.com/", 4, 20, 0, "Free"),
        ("Live Music & Showcase @ Underbones", "https://redbones.com/", 5, 21, 0, "Free"),
        ("ONCE Upon A Time: Indie Music Series @ Underbones", "https://redbones.com/", 6, 16, 0, "$15"),
        ("Bluegrass & Roots Night @ Underbones", "https://redbones.com/", 3, 20, 0, "Free"),
    ]),
]


# Outdoor and seasonal series: (first, last) (month, day) each year, inclusive. Dates drift a
# little year to year, so the ends are the usual last week (farmers markets close the week of
# Thanksgiving; SoWa Open Market runs the first Sunday of May to mid-November, the Greenway
# Artisan Market May through October).
MANUAL_RECURRING_SEASONS = {
    "SoWa Open Market": ((5, 1), (11, 15)),
    "Greenway Artisan Market": ((5, 1), (10, 31)),
    "Central Square Farmers Market": ((5, 25), (11, 24)),
    "Copley Square Farmers Market": ((5, 10), (11, 25)),
    "Davis Square Farmers Market": ((5, 15), (11, 25)),
    "Kendall Square Farmers Market": ((5, 15), (11, 25)),
    "Union Square Farmers Market": ((5, 10), (11, 25)),
    "Harvard University Farmers Market": ((6, 1), (11, 25)),
    "Memorial Drive Sundays": ((4, 25), (11, 15)),
    "Everybody Dance Now": ((5, 15), (9, 30)),
}


def _in_season(venue, d):
    season = MANUAL_RECURRING_SEASONS.get(venue)
    if not season:
        return True
    (m1, d1), (m2, d2) = season
    return (m1, d1) <= (d.month, d.day) <= (m2, d2)


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
                if not _in_season(venue, d):
                    continue
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
                   "one-shot rpg", "rpg night", "cornhole", "ping pong", "puzzle party", "puzzle night", "puzzle hunt", "puzzle swap", "jigsaw", "mah jongg", "mahjongg", "trading card", "pack wars", "pokemon"]),
    ("clubbing",  ["dj", "djs", "djz", "edm", "house music", "techno", "rave", "dubstep", "club night",
                   "nightclub", "guestlist", "guest list", "nightlife", "drum and bass", "drum & bass",
                   "industrial night", "goth night", "darkwave", "new wave night",
                   "party", "parties", "bash", "after party", "afterparty", "soiree", "rooftop", "halloween ball",
                   "costume party", "speakeasy", "piano bar", "dueling piano", "bsmnt"]),
    ("music",     ["music", "musical", "musician", "concert", " band ", "live music", "music series", "music hall", "orchestra",
                   "symphony", "karaoke", "jazz", "hip hop", "rap", "bluegrass", "country music",
                   "country night", "folk music", "acoustic", "open mic", "irish session", "jam session",
                   "music session", "singer-songwriter", "singer songwriter", "soul music", "r&b",
                   "funk", "reggae", "punk", "metal", "indie rock", "album release", "ep release",
                   "record release", "live band", "live show", "live performance", "disco", "disko",
                   "jazz trio", "jazz quartet", " trio ", " quartet ", " quintet ", "anthem", "soundtrack",
                   "ukulele", "drumming", "cabaret", "blues feat", "live blues", "recital", "vocal", "instrumental",
                   "choral", "choir", "chorus", "ensemble", "chamber music", "singing", "bands", "brass", "a cappella", "countertenor", "a far cry"]),
    ("film",      ["screening", "film ", "cinema", "movie night", "movie", "movies", "brattle", "coolidge", "documentary", "baaff", "reel rock", "warren miller", "film fest", "in 35mm", "in 70mm"]),
    ("sports",    ["bruins", "celtics", "red sox", "revolution", "patriots watch", "marathon", "vs.", "match", "game ",
                   " 5k", "fun run", "road race", "10k", "half marathon", "cycling event",
                   "bike race", "rowing", "regatta", "hocr", "pickleball", "tennis", "volleyball",
                   "dodgeball", "archery", "parkour", "crossfit", "rock climbing", "kickboxing",
                   "dragon boat", "wrestling", "flag football", "golf", "axe throwing",
                   "indoor cycling", "spin class", "boot camp", "fitness class", "fitness", "workout", "gym",
                   "strength training", "pilates", "hyrox", "tailgate", "soccer", "basketball", "hockey", "curling", "climb night", "rec league", "river run", "tai chi"]),
    ("food",      ["tasting", "brewery", "brewing", "beer", "wine", "dinner", "brunch", "pop-up",
                   "oyster", "cocktail", "cocktails", "martini", "happy hour", "taproom", "bar night", "fondue",
                   "taqueria", "tavern", "sushi", "maki", "whiskey", "bourbon", "food truck", "menu",
                   "food tour", "culinary", "cooking class", "baking class", "noodle class", "bakery", "baking",
                   "pasta class", "wine tasting", "beer tasting", "restaurant", "bar crawl", "pub crawl",
                   "omakase", "ramen", "dumpling", "high tea", "afternoon tea", "tea room", "cookie", "pizza",
                   "chocolate tour", "coffee", "latte", "croissant", "knife skills", "chef", "bbq", "barbecue",
                   "cheese tasting", "sake", "mezcal", "gin tasting", "lounge", "cognac", "armagnac", "wines of", "pasta", "cast iron", "hot dog", "biscuit", "bread"]),
    ("family",    ["kids", "children", "family", "toddler", "princess", "easter", "storytime",
                   "lego", "sensory-friendly", "sensory friendly", "baby", "youth", "trick or treat", "puppet",
                   "halloween", "spooky", "haunted", "playgroup", "rhythm time", "bookworms"]),
    ("art",       ["art", "arts", "craft", "crafts", "makers", "exhibition", "gallery", "museum", "sculpture", "painting", "curator",
                   "art show", "art walk", "art class", "pottery", "ceramics", "printmaking",
                   "watercolor", "glass fusing", "mosaic", "screen print", "flower arrang",
                   "candle mak", "weaving", "embroid", "knitting", "collage", "mending", "clay",
                   "life drawing", "figure drawing", "illustration", "sketchbook", "drawing",
                   "sewing", "crochet", "stained glass", "jewelry", "bonsai", "kokedama",
                   "quilling", "resin ", "tufting", "leatherwork", "woodwork", "bazaar",
                   "pressed flower", "moss art", "stamp carving", "cyanotype", "photograph", "quilt",
                   "paper marbling", "junk journal", "macrame", "succulent plant",
                   "art studio", "open studio", "art market", "mural", "paint party", "paint night", "sip and paint", "sip & paint", "candlemaking", "needlepoint", "knit circle", "hand lettering", "enamel", "silver ring", "bracelet", "artist talk", "artist walk", "lantern", "fleurs de villes", "orchid"]),
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
                   "open studios", "small business", "startup", "tarot", "worship", "veterans day", "remembrance", "grand opening", "style exchange", "trunk show", "debat", "human library", "blood donor", "fireside chat"]),
]

_WORD_BOUNDARY_KEYWORDS = {
    "art", "arts", "rap", "disco", "disko", "pop", "funk", "punk", "metal",
    "bash", "rave", "edm", "jam", "fest", "tour", "expo", "gala", "poet",
    "clay", "sake", "maki", "menu", "chef", "bbq", "gym", "golf", "kids",
    "baby", "lego", "hike", "yoga", "farm", "beer", "wine", "film", "match",
    "easter",  # not "Northeastern"
    "dj", "djs", "djz",  # not "The Django Cadre"
}

# A music venue's own listing whose title happens to contain another category's keyword:
# "Book Club" is a band ("COLLEGE BAND THURSDAYS!"), "Hollow Harvest" a live-music benefit.
# If the description says it's music, keep the venue's music category. Categories that a
# music venue really does host (trivia, comedy, kids' open mics, dance nights) are left alone.
_MUSIC_EVIDENCE_RE = re.compile(
    r"\b(bands?|live music|concert|gig|singer|songwriter|album|ep release|record release|"
    r"jazz|folk|blues|bluegrass|americana|rock|punk|indie|soul|funk|reggae|hip[- ]hop|"
    r"acoustic|quartet|trio|quintet|ensemble|lineup|headlin\w*|opener|tour)\b",
    re.IGNORECASE,
)
_MUSIC_VENUE_OVERRIDABLE = {"books", "outdoors", "food", "community", "art", "other", "wellness"}


def _keep_music_venue_category(cat, default_cat, description):
    if default_cat == "music" and cat in _MUSIC_VENUE_OVERRIDABLE and _MUSIC_EVIDENCE_RE.search(description or ""):
        return "music"
    return cat
_WORD_BOUNDARY_PATTERNS = {
    k: re.compile(rf"\b{re.escape(k)}\b", re.I) for k in _WORD_BOUNDARY_KEYWORDS
}

EXCLUDE_UTILITY_RE = re.compile(
    r"\b(world class|jam session|music sessions?|sunday sessions?)\b",
    re.IGNORECASE,
)

UTILITY_EVENT_RE = re.compile(
    r"\b("
    r"esol|esl|ell\b|ell class(?:es)?|ell conversation|english class(?:es)?|beginning english|language class(?:es)?|"
    r"language courses?|spanish class(?:es)?|portuguese class(?:es)?|french class(?:es)?|italian class(?:es)?|german class(?:es)?|"
    r"citizenship class(?:es)?|citizenship preparation|citizenship prep|"
    r"homework help|drop-in tutoring|tutoring for teens|tutoring|"
    r"tech help|device clinic|computer basics|digital literacy|meet your device|one-on-one tech help|"
    r"safety training|hive safety training|serger training|3d printing 101|vinyl cutting 101|laser cutting 101|xr lab 101|studio recording 101|sewing 101|"
    r"job seekers?|job application|career exploration|career coaching|resume and job|resume help|linkedin profile\+|job fairs?|career fairs?|"
    r"teacher training|coach certification|food safety|first aid|cpr course|cpr class|cpr certification|overdose prevention|"
    r"machine maintenance|machine clinic|sew by the hour|studio time - sew by the hour|longarm studio time|"
    r"\d+[- ]sessions|\d+-(?:week|month)|"
    r"library social work|social work|city council meeting|school committee|school building committee|zoning board|"
    r"council on aging|virtual nutrition class|virtual general exercise|general exercise - holland|general exercise - ralph"
    r")\b|"
    r"english for speakers of[\s\xa0]+other[\s\xa0]+languages|english for u\.s\. citizenship|"
    r"english conversation|conversation practice|conversation group|conversational group|english grammar|accent improvement",
    re.IGNORECASE,
)


# Recurring bar/restaurant specials that sources list as daily "events" ("Happy Hour Deals!",
# "$1 Oysters at X", "1/2 OFF APPS"). They go in their own default-off "Deals & Specials" bucket.
DEAL_EVENT_RE = re.compile(
    r"happy\s+hour\s+deals?|half[-\s]?price[ds]?\b|half\s+off|1/2\s+off|"
    r"\bbogo\s+(?!-)\w|\$\d+\s+(?:oysters|martinis|cocktails|margaritas|wings|tacos|burgers|pizza|apps|appetizers)\b|"
    r"\boysters\b.*\$\d|bottomless\s+(?:pasta|maki|steak|mimosas)|\bbottomless\s+brunch!|"
    r"taco\s+tuesday|\bdiscount\b|free\s+biscuit|no\s+weigh\s+wednesday|\$\d+\s+girl\s+dinner",
    re.IGNORECASE,
)
# A price mention inside a real ticketed show or activity ("Standup Comedy Show and $4 Drinks").
EXCLUDE_DEAL_RE = re.compile(
    r"comedy|stand-?up|stroll|\btour\b|trivia|bingo|\bdj\b|live\s+music|\bshow\b|class|tasting|"
    r"commuter\s+rail|day\s+trip|developers|food\s+drive",
    re.IGNORECASE,
)


def is_deal_event(name):
    """True for a recurring food/drink special rather than an event you attend."""
    if not name or not DEAL_EVENT_RE.search(name):
        return False
    return not EXCLUDE_DEAL_RE.search(name)


def is_utility_event(name):
    """Return True if an event is an instructional, vocational, or civic service event."""
    if not name:
        return False
    if EXCLUDE_UTILITY_RE.search(name):
        return False
    return bool(UTILITY_EVENT_RE.search(name))


EXCLUDE_KID_FAMILY_RE = re.compile(
    r"\b("
    r"dababy|frost children|dinty child|wild child|childish gambino|fat baby|"
    r"destiny's child|child's play|children of bodom|indiana jones|"
    r"sip & support|r&b sing-?along|beatles singalong|"
    r"adults?[- ]only|adults? nights?|grown[- ]ups? only"
    r")\b",
    re.IGNORECASE,
)

KID_FAMILY_EVENT_RE = re.compile(
    r"\b("
    r"baby|babies|lapsit|storytime|story time|singalong|sing-along|toddler|toddlers|"
    r"preschool|preschooler|preschoolers|infant|infants|"
    r"children|child(?:ren)?'s|for kids|for children|kid's|kids\b|"
    r"library card design contest|pajama story|baby rave|mindful movement: kids yoga|"
    r"family days?|family fun|family festival|family-friendly|families"
    r")\b",
    re.IGNORECASE,
)


def is_kid_family_event(name, venue=None):
    """Return True if an event is meant for infants, toddlers, kids, or family storytimes."""
    if not name:
        return False
    if EXCLUDE_KID_FAMILY_RE.search(name):
        return False
    return bool(KID_FAMILY_EVENT_RE.search(name))


_WEAK_CLUBBING_KEYWORDS = {"party", "parties", "bash"}
_EXTRA_MUSIC_VENUES = ("shalin liu", "performance center", "jordan hall", "symphony hall", "scullers", "regattabar")


def infer_category(name, venue, default=None):
    if is_utility_event(name):
        return "services"
    if is_kid_family_event(name, venue):
        return "family"
    text = f"{name or ''} {venue or ''}".lower()
    name_text = (name or "").lower()

    def _match(k, t):
        pat = _WORD_BOUNDARY_PATTERNS.get(k)
        return bool(pat.search(t)) if pat is not None else k in t

    # Generic "party" words alone are weak evidence for nightlife ("Puzzle Party",
    # "Watch Party: Celtics vs. ...", "Dumpling Making Party"). If one is the only
    # clubbing hit, keep looking for a more specific match in the event's own title.
    weak_hit = None
    not_for_kids = bool(EXCLUDE_KID_FAMILY_RE.search(name or ""))  # "Adult Night @ LEGO"
    for cat, kws in CATEGORY_KEYWORDS:
        if cat == "family" and not_for_kids:
            continue
        for k in kws:
            if weak_hit is not None:
                if _match(k, name_text):
                    return cat
                continue
            if _match(k, text):
                if cat == "clubbing" and k in _WEAK_CLUBBING_KEYWORDS:
                    if any(_match(k2, text) for k2 in kws if k2 not in _WEAK_CLUBBING_KEYWORDS):
                        return cat
                    weak_hit = cat
                    break
                return cat
    if weak_hit is not None:
        return weak_hit
    # Aggregator listings (Do617, The Boston Calendar) at a known music venue with no keyword hit
    if default in (None, "other", "community"):
        v_low = (venue or "").lower()
        if any(k in v_low for k in MUSIC_VENUE_DEFAULTS) or any(k in v_low for k in _EXTRA_MUSIC_VENUES):
            return "music"
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
    "services":  ("#8fa1b3", "🛠"),
    "deals":     ("#c678dd", "🏷"),
    "tech":      ("#7aa2f7", "⌘"),
    "markets":   ("#f4a261", "🎪"),
    "other":     ("#6b7280", "·"),
}


CATEGORY_BUCKETS = [
    ("Music & nightlife",  ["music", "clubbing", "classical"]),
    ("Dance",              ["dance"]),
    ("Stage",              ["comedy", "theater", "stage"]),
    ("Arts & culture",     ["books", "film", "art", "arts"]),
    ("Play",               ["gaming", "sports", "fitness", "outdoors"]),
    ("Food & drink",       ["food"]),
    ("Markets & Festivals", ["markets"]),
    ("Community",          ["community", "other"]),
    ("Classes & Services", ["services"]),
    ("Kids & Family",      ["family", "kids"]),
    ("Deals & Specials",   ["deals"]),
    ("Tech & Startups",    ["tech"]),
]
_CAT_TO_BUCKET = {cat: name for name, cats in CATEGORY_BUCKETS for cat in cats}

# Markets, fairs & festivals: flea and night markets, farmers markets, holiday markets and
# bazaars, craft/vintage/artisan fairs, street festivals and food fests. Matched on the title.
MARKET_FESTIVAL_RE = re.compile(
    r"(?i)\b(?:flea(?:\s+market)?|night\s+market|farmers'?\s*market|open[- ]air\s+(?:produce\s+)?market|produce\s+market|"
    r"(?:holiday|christmas|winter|spring|summer|fall|autumn|harvest|artisan|craft|crafts|makers?|maker's|vintage|antiques?|"
    r"pop[- ]?up|open|art|artists'?|record|book|zine|plant|night|street|asian|thai|vietnamese|latin|caribbean|"
    r"local|indie|handmade|community|sunday|saturday)\s+(?:market|bazaar|fair|faire|village|festival|fest)s?|"
    r"(?:craft|antiques?|vintage|record|plant|flower)\s+shows?|"  # not "art show": that's a gallery show
    r"bazaar|street\s+(?:fair|festival|party)|block\s+party|renaissance\s+faire?|"
    r"(?:food|beer|wine|cider|taco|dumpling|chili|oyster|lobster|pie|cheese|chocolate|halal|vegan|ramen|bbq|"
    r"lantern|lights?|moon|dragon\s+boat|harvest|heritage|cultural|music|arts?|folk|fall|autumn|winter|spring|summer|"
    r"holiday|oktober|octoberfest|sukkot|diwali|lunar\s+new\s+year|loy\s+krathong)\s*(?:fest(?:ival)?)|"
    r"festival|oktoberfest|snowport|swap\s+meet|yard\s+sale|craft\s+show|makers?\s+mart|"
    r"winter\s+village|holiday\s+(?:stroll|pop[- ]?up(?!\s*bar))|tree\s+lighting)\b")
# Fairs that aren't a day out: job fairs, college fairs, resource fairs.
NOT_MARKET_FESTIVAL_RE = re.compile(
    r"(?i)\b(?:job|career|college|resource|health|hiring|grad(?:uate)?|graduate school|internship|volunteer|stem|steam|"
    r"benefits?|employment|recruit(?:ing|ment)|housing|financial aid|study abroad|science|vendor application|"
    r"call for (?:vendors|artists)|vendor sign[- ]?up)\s+(?:fairs?|expos?|markets?|festivals?)\b|"
    r"\bfilm\s+fest|\bfestival\s+(?:of\s+)?(?:films?|shorts)\b|"
    r"\bcall for (?:vendors|artists|makers|artisans)\b|\bvendor (?:applications?|registration|sign[- ]?ups?)\b")
# Categories a market/festival title may replace (a jazz or film festival stays music/film).
_MARKET_OVERRIDABLE = {"community", "other", "food", "art", "arts", "outdoors"}


def is_market_or_festival(name):
    name = name or ""
    return bool(MARKET_FESTIVAL_RE.search(name)) and not NOT_MARKET_FESTIVAL_RE.search(name)


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


LUCKYSEAT_FALLBACK_SHOWS = [
    {
        "name": "Hadestown",
        "venue": "Emerson Colonial Theatre",
        "price": 45.0,
        "url": "https://www.luckyseat.com/shows/hadestown-boston-2026Oct",
    },
    {
        "name": "Late Nite Catechism: Til Death Do Us Part",
        "venue": "Charles Playhouse",
        "price": 35.0,
        "url": "https://www.luckyseat.com/shows/latenitecatechism-boston-2026Oct",
    },
    {
        "name": "Rocky™ in Concert",
        "venue": "Emerson Colonial Theatre",
        "price": 30.0,
        "url": "https://www.luckyseat.com/shows/rockyinconcert-boston-2026Oct",
    },
    {
        "name": "Wicked",
        "venue": "Citizens Opera House",
        "price": 40.0,
        "url": "https://www.luckyseat.com/shows/wicked-boston-2026Sep",
    },
    {
        "name": "The Getaway Driver",
        "venue": "Central Square Theater",
        "price": 49.0,
        "url": "https://www.luckyseat.com/shows/thegetawaydriver-cambridge-2026Sep",
    },
]

LUCKYSEAT_CACHE_FILE = os.path.join(CACHE_DIR, "luckyseat_shows.json")
LUCKYSEAT_COMMITTED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "luckyseat_shows.json")


def fetch_luckyseat_boston():
    """Fetch LuckySeat's show list and filter to Greater Boston (Boston, Cambridge, Somerville).
    Cached for 15 min with multi-tier disk and hardcoded fallbacks so Cloudflare blocks never wipe listings."""
    if _luckyseat_cache["data"] is not None and time.time() - _luckyseat_cache["ts"] < CACHE_SECONDS:
        return _luckyseat_cache["data"]

    disk_data = None
    for candidate_path in (LUCKYSEAT_CACHE_FILE, LUCKYSEAT_COMMITTED_FILE):
        if os.path.exists(candidate_path):
            try:
                with open(candidate_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) > 0:
                        disk_data = data
                        break
            except Exception:
                pass

    shows = []
    try:
        headers = {
            "User-Agent": UA_CHROME,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        raw_shows = None
        try:
            resp = _SESSION.get(
                "https://www.luckyseat.com/api/showmanagement/getshowlist",
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 200:
                raw_shows = resp.json()
        except Exception:
            raw_shows = None


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
                for save_path in (LUCKYSEAT_CACHE_FILE, LUCKYSEAT_COMMITTED_FILE):
                    try:
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(shows, f, indent=2)
                    except Exception:
                        pass
    except Exception:
        pass

    if not shows and disk_data:
        shows = disk_data

    if not shows:
        try:
            events_json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "events.json")
            if os.path.exists(events_json_path):
                with open(events_json_path, "r", encoding="utf-8") as f:
                    candidate = json.load(f).get("luckyseat")
                    if isinstance(candidate, list) and len(candidate) > 0:
                        shows = candidate
        except Exception:
            pass

    if not shows:
        shows = list(LUCKYSEAT_FALLBACK_SHOWS)

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

        # Ticketing feeds report $0 when they have no price (e.g. Sonia shows on Ticketmaster
        # at $29.85 elsewhere); drop it so a real price from another listing can show.
        if name in ("Ticketmaster", "SeatGeek") and re.fullmatch(r"\$?0(?:\.00)?", str(e.get("price") or "").strip()):
            e["price"] = None

        # Sanitize Loretta's Last Call URLs and correct Sunday Line Dancing to 8 PM
        url_raw = e.get("url") or ""
        if "lorettaslastcall.com/event/" in url_raw:
            e["url"] = "https://www.lorettaslastcall.com/events/"

        if "loretta" in v_low or "loretta" in t_low:
            if "line dancing" in t_low and "sunday" in t_low:
                if d_str and d_str != "tba":
                    try:
                        dt_lor = datetime.fromisoformat(d_str.replace("Z", "+00:00"))
                        if dt_lor.tzinfo is None:
                            dt_lor = dt_lor.replace(tzinfo=EASTERN)
                        dt_lor_eastern = dt_lor.astimezone(EASTERN)
                        if dt_lor_eastern.hour in (18, 19):
                            dt_lor_eastern = dt_lor_eastern.replace(hour=20, minute=0)
                            e["date"] = dt_lor_eastern.astimezone(timezone.utc).isoformat()
                    except Exception:
                        pass

        if not v_raw:
            e["venue"] = name
            e["venue_unknown"] = True  # placeholder = source name; dedup may find the real venue

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
            if not is_agg:
                e["category"] = _keep_music_venue_category(e["category"], default_cat, e.get("description"))

        if e.get("category") in _MARKET_OVERRIDABLE and is_market_or_festival(title):
            e["category"] = "markets"

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
    fp = _scraper_fingerprint(v)
    if not force:
        cached = _load_venue_cache(name, max_age=ttl, fingerprint=fp)
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

        # The site refused us partway (403/429): keep what we had rather than saving a short list.
        refused = HOST_GATE.refused.get(_host_of(v["url"]))
        if refused:
            stale = _load_venue_cache(name, max_age=None)
            old = _normalize_and_filter_events((stale or {}).get("events") or [], v)
            if old:
                return {
                    "venue": name,
                    "url": v["url"],
                    "events": dedupe(events + old),
                    "error": None,
                    "fallback": True,
                    "duration": dur,
                    "cached": True,
                }

        # Update last known good and save to disk cache
        if events:
            _last_known_good[name] = events
            _save_venue_cache(name, events, duration=dur, fingerprint=fp)
        elif name in _last_known_good and not events:
            # Scraper returned 0 events but previously had events: fall back to preserve data
            events = _normalize_and_filter_events(_last_known_good[name], v)
        else:
            _save_venue_cache(name, events, duration=dur, fingerprint=fp)

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
            "error": str(e) if not prev else None,
            "fallback": bool(prev),
            "duration": round(time.time() - t0, 2),
            "cached": bool(prev),
        }


def _do_scrape_all(force=False):
    HOST_GATE.reset()  # a site that refused us yesterday gets asked again, once

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

