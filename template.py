"""Boston Events — HTML rendering and template logic."""

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import quote, quote_plus

from scrapers import (
    EASTERN,
    CATEGORY_BUCKETS,
    CATEGORY_STYLES,
    MUSIC_GENRES,
    DEAL_LINKS,
    STATIC_LINKS,
    category_bucket,
    infer_music_genre,
    fetch_boston_weather,
    fetch_luckyseat_boston,
    _load_community_events,
    is_placeholder_or_closed_event,
)
from venues_geo import resolve_event_geo


CITY_RULES = [
    ("somerville", (
        "somerville", "aeronaut", "crystal ballroom", "somerville theatre", "somerville theater",
        "somerville, ma", "(somerville)", ", somerville",
        "davis square", "assembly row", "union square",
        "the burren", "burren", "mccarthy's toad", "mccarthys toad", "remnant somerville",
        "comedy studio", "bow market", "upstairs at bow",
        "armory", "arts at the armory", "somerville arts council",
        "the jungle", "jungle", "sally o'brien", "sally obrien", "side quest",
        "duck duck goof", "goofs comedy", "somerville library", "growing center",
        "underbones", "remnant brewing", "the rockwell", "rockwell",
        "vera's", "veras", "craft loft", "the chester tavern", "chester tavern",
        "all she wrote books", "portico brewing", "portico", "dance union",
        "warehouse xi", "warehouse 11", "warehouse-xi",
        "winter hill brewing", "the independent", "olde magoun", "magoun's saloon",
        "somart", "wyllo", "jean appolon", "the biltmore", "diversity consignment",
        "boston figurative art center", "perry park", "nathan tufts park", "ward 4",
        "the painted burro", "orlean's restaurant", "orleans restaurant",
    )),
    ("cambridge", (
        "cambridge", "batifol", "passim", "club passim", "monkfish", "mad monkfish",
        "mit ", "m.i.t", "harvard square", "harvard book", "porter square", "sinclair",
        "brattle", "cambridge, ma", "(cambridge)", ", cambridge",
        "kendall", "kendall center", "urban park", "central square", "inman square", "cantab",
        "havetodance", "have to dance", "ywca cambridge",
        "middle east", "sonia", "regattabar", "arrow street",
        "harvard museum", "hmnh",
        "lovestruck", "lovestruck books",
        "havana club", "lou's", "wearelous", "lizard lounge",
        "lamplighter", "roxy's arcade", "roxys arcade",
        "venture café", "venture cafe", "cic cambridge",
        "phoenix landing", "manray", "man ray", "prospect st",
        "lilypad", "inman square", "the druid", "druid",
        "plough and stars", "plough & stars", "gather here", "mit open space",
        "remnant satellite", "satellite", "cambridge public library", "cambridge library",
        "harvard university farmers market", "harvard farmers market",
        "q ballroom", "ccae", "cambridge center for adult education",
        "harvard art museum", "peabody museum", "the foundry", "memorial drive",
        "swing in the square", "bluesy tuesy", "blues union", "41 hampshire", "dante alighieri",
        "everybody dance now", "multicultural arts center", "the dance complex", "dance complex",
        "first street market", "la fábrica", "la fabrica", "kathryn schultz",
        "an sibin", "an sibín", "the coop", "forage", "52 church", "farkas hall",
        "loeb ex", "pemberton farms", "fusey bluesy", "graymist", "the grove",
        "cambridge art association",
    )),
    ("boston", (
        "bsmnt", "kings seaport", "kings - seaport", "kings dining",
        "midway cafe", "o'brien's pub", "obriens pub", "o'brien's", "obriens",
        "jordan hall", "new england conservatory", "nec (", "nec:", "nec ", "nec hall",
        "city winery", "royale", "wilbur", "ica boston", "gardner", "boston public library",
        "laugh boston", "big night live", "house of blues", "paradise rock", "orpheum",
        "td garden", "mgm music hall", "citizens house of blues", "fenway", "back bay",
        "the fenway", "401 park", "time out market",
        "speedway", "charles river speedway", "notch brewing",
        "greenway", "rose kennedy greenway",
        "downtown crossing", "seaport", "boston, ma", "(boston)", ", boston",
        "boston common", "trident booksellers", "mfa", "museum of fine arts",
        "brookline", "coolidge corner", "puppet showplace", "esplanade", "hatch shell", "sabina",
        "loretta", "versus boston", "versus", "opera house", "symphony hall", "brighton music hall",
        "boch center", "wang theatre", "boston conservatory", "the beehive", "play boston",
        "petit robert", "the grand", "scorpion bar", "scorpion", "memoire", "mémoire",
        "roxbury", "jamaica plain", "south end", "fort point", "south boston",
        "allston", "brighton", "dorchester", "mattapan", "roslindale", "west roxbury",
        "long live", "sam adams", "trillium", "castle island",
        "copley", "sowa", "newbury", "beehive", "wally",
        "the anchor", "anchor boston", "charlestown",
        "jacque", "jacques", "haymarket", "copley square farmers market",
        "head of the charles", "charles river", "bu sailing", "sailing pavilion",
        "roadrunner", "colonial theatre", "colonial theater", "emerson colonial",
        "paramount center", "emerson paramount", "shubert theatre", "sports museum",
        "the sports museum", "huntington theatre", "huntington theater", "huntington ave",
        "calderwood", "club cafe", "club café", "dani's", "danis", "dani's queer bar", "danis queer bar", "legacy", "feral", "sunset cantina", "reunion bbq", "439 tremont", "urbanity dance",
        "berklee", "cafe 939", "wbur cityspace", "cityspace", "beacon hill",
        "the phoenix boston", "fourth presbyterian", "boston fun run", "arlington street church",
        "tony demarco", "kadampa", "ula cafe", "artisans asylum", "walter brown arena",
        "agganis arena", "scullers", "eliot hall", "bill's bar", "bills bar",
        "charles playhouse", "charlesgate", "fiedler field", "museum of science",
        "bloomberg public science", "east boston", "trinity church", "park street church",
        "boston nature center", "carrie nation", "blondie's", "alexander hamilton",
        "the greatest bar", "the bebop", "shore leave", "sidebar boston", "roundhead brewery",
        "petula's", "old south", "oak long bar", "massachusetts historical society",
        "loco taqueria", "high street place", "gray's hall", "flight club", "empire",
        "arnold arboretum", "224 boston", "yellow door taqueria", "wyndham boston beacon hill",
        "white bull tavern", "west end johnnie", "view boston", "the superette",
        "the substation", "the rocks at harbor way", "the harp", "the alley bar",
        "telegraph hill", "simmons university", "rocco's cucina", "reggie lewis",
        "red cross of greater boston", "rebel's guild", "raffles boston", "pkl boston",
        "old state house", "offsuit", "new england aquarium", "luckys lounge", "lucky's lounge",
        "lower mills tavern", "lincoln tavern", "lansdowne pub", "grubstreet",
        "freedom trail", "franklin park zoo", "fat baby", "emmanuel church", "dudley town",
        "democracy brewing", "deluca", "community boating", "city tap house",
        "church of the covenant", "capo restaurant", "bell in hand", "ashmont farmers market",
        "alumni stadium", "adams park", "adam park", "nathálie", "nathalie",
        "goethe-institut", "goethe institut", "broken records", "lifebloom",
        "winthrop center", "overlook st gabriel", "harvard stadium", "bright-landry",
    )),
]

CITY_LABELS = {
    "boston": "Boston",
    "cambridge": "Cambridge",
    "somerville": "Somerville",
    "other": "Other",
}


def _event_city(venue, source, event=None):
    targets = []
    if isinstance(venue, dict):
        event = venue
        v_str = (event.get("venue") or "").strip().lower()
        s_str = (event.get("_source_venue") or "").strip().lower()
        t_str = (event.get("title") or event.get("name") or "").strip().lower()
        targets = [v_str, s_str, t_str]
    else:
        v_str = (venue or "").strip().lower()
        s_str = (source or "").strip().lower()
        targets = [v_str, s_str]
        if isinstance(event, dict):
            t_str = (event.get("title") or event.get("name") or "").strip().lower()
            if t_str:
                targets.append(t_str)

    combined = " ".join(t for t in targets if t)
    is_waltham_museum = "charles river museum" in combined or "waltham" in combined

    for target in targets:
        if not target:
            continue
        if target == "boston":
            return "boston"
        for city, needles in CITY_RULES:
            if city == "boston" and is_waltham_museum and not any(k in target for k in ["charles river speedway", "esplanade"]):
                continue
            for n in needles:
                if n in target:
                    return city

    ev_dict = event if isinstance(event, dict) else {"venue": venue, "_source_venue": source}
    geo = resolve_event_geo(ev_dict)
    if geo and geo.get("address"):
        addr = geo["address"].lower()
        if ", cambridge" in addr:
            return "cambridge"
        if ", somerville" in addr:
            return "somerville"
        if any(b in addr for b in [", boston", ", allston", ", brighton", ", charlestown", ", jamaica plain", ", dorchester", ", roxbury", ", south boston", ", mattapan", ", roslindale", ", hyde park", ", brookline"]):
            return "boston"

    return "other"


SUBAREAS_BY_CITY = {
    "cambridge": [
        ("central_sq", "Central Square", "🏛️"),
        ("harvard_sq", "Harvard Square", "🎓"),
        ("kendall_mit", "Kendall / MIT", "🚀"),
        ("inman_sq", "Inman Square", "🎷"),
        ("porter_sq", "Porter Square", "📚"),
        ("east_cambridge", "East Cambridge", "⛵"),
        ("cambridge_other", "Other Cambridge", "📍"),
    ],
    "somerville": [
        ("davis_sq", "Davis Square", "🎭"),
        ("union_sq", "Union Square", "🎨"),
        ("spring_winter_hill", "Spring & Winter Hill", "🌿"),
        ("assembly_east", "Assembly & East Somerville", "🛍️"),
        ("somerville_other", "Other Somerville", "📍"),
    ],
    "boston": [
        ("theater_downtown", "Downtown & Theater Dist.", "🎭"),
        ("fenway_kenmore", "Fenway & Kenmore", "⚾"),
        ("south_end", "South End", "🎺"),
        ("back_bay", "Back Bay & Copley", "🏛️"),
        ("seaport_waterfront", "Seaport & Waterfront", "🌊"),
        ("allston_brighton", "Allston & Brighton", "🎸"),
        ("brookline", "Brookline / Coolidge", "🎬"),
        ("jp_dorchester", "JP & Dorchester", "🌳"),
        ("charlestown_eastie", "Charlestown & Eastie", "⚓"),
        ("boston_other", "Other Boston", "📍"),
    ],
    "other": [
        ("everett_north", "Everett & North Shore", "🌃"),
        ("medford_malden", "Medford & Malden", "🎪"),
        ("metrowest", "Metrowest & South", "🌲"),
        ("suburbs_other", "Outer Suburbs", "📍"),
    ]
}


def resolve_subarea(city, event, geo=None):
    if not geo:
        geo = resolve_event_geo(event)
    vn = (event.get("venue") or "").lower()
    src = (event.get("_source_venue") or "").lower()
    title = (event.get("title") or event.get("name") or "").lower()
    loc = (event.get("location") or event.get("address") or "").lower()
    neigh = (geo.get("neighborhood") or "").lower() if geo else ""
    blob = f"{vn} {src} {title} {loc} {neigh}"

    if city == "cambridge":
        if any(k in blob for k in ["central square", "cantab", "middle east", "sonia", "manray", "man ray", "middlesex", "phoenix landing", "plough and stars", "plough & stars", "dance complex", "mad monkfish", "la fabrica", "havana club"]):
            return ("Central Square", "central_sq")
        if any(k in blob for k in ["harvard square", "sinclair", "brattle", "passim", "harvard book", "harvard museum", "peabody museum", "lou's", "wearelous", "sanders", "farkas", "harvard university", "ccae", "harvard art museum", "main library", "449 broadway"]):
            return ("Harvard Square", "harvard_sq")
        if any(k in blob for k in ["kendall", "mit ", "m.i.t", "venture café", "venture cafe", "cambridge crossing", "starlight", "broadway", "urban park"]):
            return ("Kendall / MIT", "kendall_mit")
        if any(k in blob for k in ["inman", "lilypad", "lily pad", "druid", "gather here"]):
            return ("Inman Square", "inman_sq")
        if any(k in blob for k in ["porter", "toad", "pemberton", "cambridge common", "lizard lounge", "mccarthys"]):
            return ("Porter Square", "porter_sq")
        if any(k in blob for k in ["east cambridge", "remnant satellite", "valente"]):
            return ("East Cambridge", "east_cambridge")
        return ("Other Cambridge", "cambridge_other")

    elif city == "somerville":
        if any(k in blob for k in ["davis", "somerville theatre", "crystal ballroom", "burren", "rockwell", "comedy studio", "underbones", "painted burro", "west branch"]):
            return ("Davis Square", "davis_sq")
        if any(k in blob for k in ["union square", "bow market", "armory", "arts at the armory", "jungle", "remnant", "sally o'brien", "sally obrien", "side quest", "duck duck goof", "dance union", "goofs comedy", "vera's", "warehouse xi", "warehouse 11", "warehouse-xi"]):
            return ("Union Square", "union_sq")
        if any(k in blob for k in ["growing center", "spring hill", "winter hill", "magoun", "highland", "central library", "79 highland", "chester tavern"]):
            return ("Spring & Winter Hill", "spring_winter_hill")
        if any(k in blob for k in ["assembly", "portico", "aeronaut", "east somerville", "boynton", "east branch", "craft loft", "all she wrote"]):
            return ("Assembly & East Somerville", "assembly_east")
        return ("Other Somerville", "somerville_other")

    elif city == "boston":
        if any(k in blob for k in ["fenway", "symphony", "house of blues", "mgm music", "mfa", "museum of fine arts", "jordan hall", "nec ", "nec:", "nec (", "new england conservatory", "berklee", "cafe 939", "time out", "401 park", "bill's bar", "bills bar", "loretta"]):
            return ("Fenway & Kenmore", "fenway_kenmore")
        if any(k in blob for k in ["theater district", "theatre district", "boch", "wang", "shubert", "paramount", "colonial", "royale", "charles playhouse", "downtown", "common", "orpheum", "bsmnt", "city winery", "big night live", "td garden", "wilbur", "sports museum", "versus", "west end", "legacy", "feral"]):
            return ("Downtown & Theater Dist.", "theater_downtown")
        if any(k in blob for k in ["south end", "beehive", "wally", "club cafe", "club café", "sowa", "reunion bbq", "calderwood"]):
            return ("South End", "south_end")
        if any(k in blob for k in ["back bay", "copley", "boston public library", "bpl", "trident", "newbury", "prudential", "dani", "danis"]):
            return ("Back Bay & Copley", "back_bay")
        if any(k in blob for k in ["seaport", "leader bank", "ica boston", "kings seaport", "kings dining", "greenway", "harbor", "scorpion", "laugh boston"]):
            return ("Seaport & Waterfront", "seaport_waterfront")
        if any(k in blob for k in ["allston", "brighton", "o'brien", "obrien", "brighton music", "speedway", "roadrunner", "lavietes", "notch brewing", "harvard stadium", "sunset cantina"]):
            return ("Allston & Brighton", "allston_brighton")
        if any(k in blob for k in ["jamaica plain", "jp", "midway cafe", "arboretum", "dorchester", "roxbury"]):
            return ("JP & Dorchester", "jp_dorchester")
        if any(k in blob for k in ["charlestown", "anchor", "navy yard", "east boston", "eastie"]):
            return ("Charlestown & Eastie", "charlestown_eastie")
        if any(k in blob for k in ["brookline", "coolidge", "puppet showplace", "booksmith"]):
            return ("Brookline / Coolidge", "brookline")
        return ("Other Boston", "boston_other")

    else:
        if any(k in blob for k in ["everett", "mémoire", "memoire", "encore", "night shift"]):
            return ("Everett & North Shore", "everett_north")
        if any(k in blob for k in ["medford", "malden", "deep cuts", "chevalier"]):
            return ("Medford & Malden", "medford_malden")
        if any(k in blob for k in ["waltham", "gore place", "foxborough", "gillette", "natick"]):
            return ("Metrowest & South", "metrowest")
        return ("Outer Suburbs", "suburbs_other")


def resolve_transit_lines(city, sub_slug, event, geo=None):
    """Return comma-separated MBTA Rapid Transit lines ('red', 'green', 'orange', 'blue') serving the event."""
    lines = []
    vn = (event.get("venue") or "").lower()
    src = (event.get("_source_venue") or "").lower()
    neigh = (geo.get("neighborhood") or "").lower() if geo else ""
    blob = f"{vn} {src} {neigh}"

    if sub_slug in ("harvard_sq", "central_sq", "kendall_mit", "porter_sq", "davis_sq"):
        lines.append("red")
    elif sub_slug in ("union_sq", "inman_sq", "east_cambridge", "spring_winter_hill", "fenway_kenmore", "allston_brighton", "brookline"):
        lines.append("green")
    elif sub_slug in ("assembly_east", "south_end"):
        lines.append("orange")
    elif sub_slug == "back_bay":
        lines.extend(["green", "orange"])
    elif sub_slug == "theater_downtown":
        if any(k in blob for k in ["td garden", "big night live", "west end", "sports museum", "city winery"]):
            lines.extend(["green", "orange"])
        else:
            lines.extend(["red", "green", "orange"])
    elif sub_slug == "seaport_waterfront":
        if any(k in blob for k in ["aquarium", "harbor", "greenway", "faneuil", "comedy", "improvasylum"]):
            lines.extend(["blue", "red"])
        else:
            lines.append("red")
    elif sub_slug == "jp_dorchester":
        if "dorchester" in blob or "ashmont" in blob or "jfk" in blob or "savin" in blob:
            lines.append("red")
        else:
            lines.append("orange")
    elif sub_slug == "charlestown_eastie":
        if "east boston" in blob or "eastie" in blob or "maverick" in blob or "tall ship" in blob or "zumix" in blob:
            lines.append("blue")
        else:
            lines.append("orange")
    elif sub_slug == "medford_malden":
        if "malden" in blob:
            lines.append("orange")
        else:
            lines.append("green")
    elif city == "cambridge":
        lines.append("red")
    elif city == "somerville":
        lines.append("green")
    elif city == "boston":
        if "beacon hill" in blob or "mgh" in blob or "south boston" in blob or "broadway" in blob:
            lines.append("red")
        else:
            lines.append("green")
    return ",".join(dict.fromkeys(lines))


def _maps_link(venue, city):
    if not venue or venue.strip().lower() in ("zoom", "online", "virtual"):
        return ""
    label = CITY_LABELS.get(city)
    query = venue if city == "other" or not label else f"{venue}, {label}, MA"
    return f"https://www.google.com/maps/search/?api=1&query={quote(query)}"


_FREE_TITLE_RE = re.compile(
    r"\b("
    r"free|"
    r"honk(!|\b)|"
    r"porchfest|"
    r"parade|"
    r"car-free|"
    r"open streets?|"
    r"open studios?|"
    r"farmers? markets?|"
    r"artisan markets?|"
    r"flea markets?|"
    r"craft markets?|"
    r"vintage markets?|"
    r"open markets?|"
    r"clothing swaps?|"
    r"book swaps?|"
    r"seed swaps?|"
    r"clean-?ups?|"
    r"blood drive|"
    r"book clubs?|"
    r"open mics?|"
    r"board games?|"
    r"storytimes?|"
    r"fun runs?|"
    r"run clubs?|"
    r"no cover"
    r")\b",
    re.IGNORECASE,
)

_FREE_DESC_PHRASES = [
    "admission: free",
    "admission is free",
    "free admission",
    "free event",
    "free and open",
    "free to attend",
    "free to the public",
    "all events are free",
    "no cover",
    "free entry",
    "complimentary admission",
    "complimentary entry",
    "free outdoor",
    "no tickets required",
    "free dance class",
]


def _is_event_free(e):
    price = (e.get("price") or "").strip().lower()
    if price:
        if any(k in price for k in ["free", "no cover", "complimentary", "pay what you can"]):
            return True
        if price in ("0", "$0", "$0.00", "0.00"):
            return True
        if re.search(r"\$[1-9]", price):
            return False

    name = (e.get("name") or "").lower()
    desc = (e.get("description") or "").lower()
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()

    if any(k in source or k in venue for k in [
        "library", "bpl", "farmers market", "open market",
        "esplanade association", "greenway", "rose kennedy greenway", "arnold arboretum"
    ]):
        return True

    if _FREE_TITLE_RE.search(name):
        return True

    if any(p in desc for p in _FREE_DESC_PHRASES):
        return True

    return False


def _event_stable_id(e):
    title = (e.get("name") or "").strip().lower()
    venue = (e.get("venue") or e.get("_source_venue") or "").strip().lower()
    date_str = (e.get("date") or "")[:10]
    raw = f"{venue}|{title}|{date_str}"
    return "ev_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _load_upvotes_map():
    upvotes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upvotes.json")
    if os.path.exists(upvotes_file):
        try:
            with open(upvotes_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _build_gcal_link(e, title, venue, city):
    raw_date = e.get("date")
    if not raw_date:
        return None
    try:
        dt = datetime.fromisoformat(raw_date.replace("Z", "+00:00")).astimezone(timezone.utc)
        start_str = dt.strftime("%Y%m%dT%H%M%SZ")
        end_dt = dt + timedelta(hours=2)
        end_str = end_dt.strftime("%Y%m%dT%H%M%SZ")
    except (ValueError, TypeError, AttributeError):
        return None
    if venue and venue.lower() in ("zoom", "online", "virtual"):
        loc = venue.capitalize()
    elif venue:
        loc = f"{venue}, {city.capitalize() if city else 'Boston'}, MA"
    else:
        loc = "Boston, MA"
    details = f"Details & Tickets: {e.get('url') or ''}\n\nDiscovered on Wicked Boston Events"
    return f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(title)}&dates={start_str}/{end_str}&details={quote(details)}&location={quote(loc)}"



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


def format_time(s):
    if not s:
        return "TBA"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return s
    return dt.astimezone(EASTERN).strftime("%-I:%M %p")


def format_when(e):
    if not e.get("date") and e.get("ends"):
        try:
            end = datetime.strptime(e["ends"], "%Y-%m-%d")
        except ValueError:
            return format_time(e.get("date"))
        return f"thru {end.month}/{end.day}"
    return format_time(e.get("date"))


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


GENERIC_HEADS = {
    "trivia", "story hour", "open mic", "board games", "run club", "farmers market",
    "salsa", "bachata", "yoga", "live music", "comedy night", "book club",
    "happy hour", "karaoke", "jazz night", "reunion", "tour", "tours", "market"
}

COMMERCIAL_VENUES = {
    "td garden", "fenway park", "fenway", "gillette stadium", "mgm music hall",
    "house of blues", "roadrunner", "royale", "the wilbur", "wilbur theatre",
    "chevalier theatre", "citizens bank opera house", "citizens opera house",
    "boch center", "wang theatre", "shubert theatre", "paradise rock club",
    "brighton music hall", "leader bank pavilion", "big night live", "the sinclair",
    "crystal ballroom", "middle east", "city winery", "laugh boston",
    "boston symphony orchestra", "symphony hall", "huntington theatre",
    "emerson colonial theatre", "agganis arena"
}

EXCLUDE_VENUES_OR_SOURCES = {
    "museum", "library", "bookstore", "booksmith", "farmers market",
    "park run", "board games", "trivia", "contra dance", "language lovers",
    "hiking", "photography", "volunteer", "mit events", "botanic", "church", "cathedral"
}


GENERIC_DESCRIPTOR_PREFIXES = {
    "recital", "concert", "workshop", "screening", "lecture", "class",
    "showcase", "exhibition", "panel", "presentation", "meeting",
    "discussion", "reception", "webinar", "seminar", "film", "movie",
    "book launch", "reading"
}


def _normalize_title_head(title, venue=None):
    t = (title or "").lower().strip()

    # 1. Strip venue name from title if title starts with venue (e.g. "McCarthys Cambridge Irish Session")
    if venue:
        v_clean = re.sub(r"[^a-z0-9]+", " ", venue.lower()).strip()
        v_core = re.sub(r"^the\s+", "", v_clean).strip()
        t_clean = re.sub(r"[^a-z0-9]+", " ", t).strip()
        for v_cand in [v_clean, v_core]:
            if v_cand and len(v_cand) >= 4 and t_clean.startswith(v_cand):
                t = t_clean[len(v_cand):].strip()
                break

    # 2. Strip leading generic words: "live ", "traditional ", "weekly ", "annual "
    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)

    # 3. Strip parentheses / brackets with openers, support, guest, tour, etc.
    t = re.sub(r"\s*[\(\[][^\)\]]*(?:touring|18\+|21\+|sold out|ages|rescheduled|presale|preseason|preview|week\s*\d+|opens|opener|support|guest|special guest|featuring)[^\)\]]*[\)\]]", "", t, flags=re.I)

    # 4. Standard prefixes & suffixes
    t = re.sub(r"^(?:broadway in boston|presents|live nation presents|bowery presents|bowery boston presents):\s*", "", t)
    t = re.sub(r"^(?:nba\s+|mlb\s+|nhl\s+|nfl\s+)?(?:preseason|rescheduled|postponed):\s*", "", t)
    t = re.sub(r"\s+at\s+(?:the\s+)?[a-z0-9\x27\s\.\&\-]+$", "", t)
    t = re.sub(r"\s*-\s*202\d\s+tour.*$", "", t)
    t = re.sub(r"\s*-\s*tour.*$", "", t)
    t = re.sub(r"\s*-\s*boston(\b.*)?$", "", t)

    # If title starts with a generic descriptor prefix like "Recital:", strip it so the performer is the head
    for p in GENERIC_DESCRIPTOR_PREFIXES:
        if t.startswith(p + ":") or t.startswith(p + " -"):
            t = t[len(p) + 1:].strip()
            break

    GENERIC_CATEGORY_SUFFIXES = (
        "workshop", "class", "clinic", "tour", "screening", "recital",
        "lecture", "discussion", "series", "market", "night", "trivia", "brunch", "show"
    )

    for sep in [":", " @ ", " @", " with ", " feat. ", " feat ", " ft. ", " ft ", " - ", " – ", " — ", " “", " \"", "”", "“", "\""]:
        if sep in t:
            parts = t.split(sep, 1)
            left = parts[0].strip()
            if any(left.endswith(suff) for suff in GENERIC_CATEGORY_SUFFIXES):
                if len(parts[1].strip()) >= 3:
                    t = parts[1].strip()
                    continue
            if len(left) >= 3 and left not in GENERIC_DESCRIPTOR_PREFIXES and not any(gen in left for gen in ["an evening", "a night", "special"]):
                t = left
                break
    if "," in t:
        parts = t.split(",", 1)
        if len(parts[0].strip()) >= 3:
            t = parts[0].strip()

    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)
    t = re.sub(r"\bmusic\s+", "", t, flags=re.I)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return t


def _clean_ticket_query(title):
    if not title:
        return ""
    q = title
    q = re.sub(r"^(?:broadway in boston|presents|live nation presents|bowery presents):\s*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"^(?:nba\s+|mlb\s+|nhl\s+|nfl\s+)?(?:preseason|rescheduled|postponed):\s*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s*[\(\[](?:18\+|21\+|all ages|sold out|matinee|late show|early show|touring|preseason)[^\)\]]*[\)\]]", "", q, flags=re.IGNORECASE)
    if ":" in q:
        head, _ = q.split(":", 1)
        if len(head.strip()) >= 3 and not any(gen in head.lower() for gen in ["tour", "special", "an evening", "night", "live"]):
            q = head.strip()
    for q_sep in [" “", " \"", " - ", " – ", " — "]:
        if q_sep in q:
            head, _ = q.split(q_sep, 1)
            if len(head.strip()) >= 4:
                q = head.strip()
                break
    q = re.sub(r"\s*-\s*Boston\b.*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"[\"“”]", "", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


def _is_commercial_ticketed(e):
    p = (e.get("price") or "").lower()
    if "free" in p or p in ("$0", "0"):
        return False
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()
    name = (e.get("name") or "").lower()
    cat = (e.get("category") or "").lower()
    if any(ex in source or ex in venue for ex in EXCLUDE_VENUES_OR_SOURCES):
        return False
    if "museum tour" in name or "walking tour" in name or "historical tour" in name:
        return False
    if any(s in source for s in ["ticketmaster", "seatgeek", "boston sports", "bowery presents"]):
        return True
    if any(cv in venue or cv in source for cv in COMMERCIAL_VENUES):
        return True
    if cat in ("music", "sports", "comedy", "theater") and e.get("price"):
        return True
    return False


def _build_compare_links(e, raw_title):
    if not _is_commercial_ticketed(e):
        return ""
    q = _clean_ticket_query(raw_title)
    if not q or len(q) < 3:
        return ""
    encoded_q = quote_plus(q)
    gt_url = f"https://gametime.co/search?q={encoded_q}"
    sh_url = f"https://www.stubhub.com/search?q={encoded_q}"
    label = "compare prices" if e.get("price") else "tickets"
    return f'<span class="compare-tickets">{label}: <a href="{escape(gt_url)}" target="_blank" rel="noopener">Gametime</a> · <a href="{escape(sh_url)}" target="_blank" rel="noopener">StubHub</a></span>'


def _source_priority(s):
    s = (s or "").lower()
    if s in ("ticketmaster", "seatgeek", "eventbrite", "eventbrite boston", "eventbrite cambridge", "eventbrite somerville"):
        return 1
    if s in ("the boston calendar", "do617", "boston shows"):
        return 5
    return 10


def _clean_event_url(u):
    if not u or not isinstance(u, str):
        return ""
    u = re.sub(r"[?#].*$", "", u).strip().rstrip("/")
    generic = {
        "https://www.passim.org/live-music",
        "https://burren.com/music.html",
        "https://www.sallyobriensbar.com/music",
        "https://www.mccarthystoad.com/calendar",
        "https://www.thebostoncalendar.com",
        "https://bostonshows.org",
        "https://facebook.com",
        "https://instagram.com",
    }
    if u in generic or len(u.split("/")) <= 3:
        return ""
    return u


def _merge_duplicates(events):
    """Collapse events sharing a normalized name or head title within the same day bucket.

    Preserves the best physical venue, merges prices across primary and alt sources,
    and attaches alt sources so users can compare providers. Preserves distinct
    showtimes from the same primary source (e.g. 7:00 PM and 9:30 PM performances),
    while merging cross-source postings of the same show.
    """
    seen_exact = {}
    seen_head = {}
    seen_url = {}
    out = []
    generic_sources = {"ticketmaster", "seatgeek", "the boston calendar", "eventbrite boston", "eventbrite cambridge", "eventbrite somerville", "do617", "boston shows"}

    def _is_different_show(e1, e2):
        t1 = e1.get("_time")
        t2 = e2.get("_time")
        if not t1 and e1.get("date"):
            try:
                t1 = datetime.fromisoformat(str(e1["date"]).replace("Z", "+00:00"))
            except Exception:
                pass
        if not t2 and e2.get("date"):
            try:
                t2 = datetime.fromisoformat(str(e2["date"]).replace("Z", "+00:00"))
            except Exception:
                pass
        if not t1 or not t2:
            return False
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=EASTERN)
        else:
            t1 = t1.astimezone(EASTERN)
        if t2.tzinfo is None:
            t2 = t2.replace(tzinfo=EASTERN)
        else:
            t2 = t2.astimezone(EASTERN)
        # If either time is EDT midnight (00:00), it is likely an untimed/all-day placeholder
        if (t1.hour == 0 and t1.minute == 0) or (t2.hour == 0 and t2.minute == 0):
            return False
        diff_mins = abs((t1 - t2).total_seconds()) / 60.0
        s1 = (e1.get("_source_venue") or e1.get("source") or "").lower()
        s2 = (e2.get("_source_venue") or e2.get("source") or "").lower()
        # Same source with >= 45m diff: distinct show sets (e.g. 7:00 PM and 9:30 PM)
        if s1 and s1 == s2 and diff_mins >= 45:
            return True
        # Different sources within 90m (doors vs show time): same show
        if s1 != s2 and diff_mins <= 90:
            return False
        # If diff > 90m: separate shows
        if diff_mins > 90:
            return True
        return False

    def _venue_match(v1, v2, e1, e2):
        if not v1 or not v2:
            return True
        v1_low = v1.lower()
        v2_low = v2.lower()
        if v1_low in generic_sources or v2_low in generic_sources:
            return True
        if v1_low == v2_low:
            return True
        generic_vwords = {
            "the", "at", "in", "of", "and", "boston", "cambridge", "somerville",
            "theatre", "theater", "tavern", "pub", "bar", "lounge", "brewery",
            "brewing", "cafe", "café", "center", "hall", "club", "studio", "house", "room"
        }
        w1 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v1_low)} - generic_vwords
        w2 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v2_low)} - generic_vwords
        if w1 and w2 and (w1 & w2):
            return True
        if e1 and e2:
            g1 = resolve_event_geo(e1)
            g2 = resolve_event_geo(e2)
            if g1 and g2 and g1.get("venue") and g1.get("venue") == g2.get("venue"):
                return True
        return False

    for e in events:
        raw_name = e.get("name") or ""
        full = re.sub(r"[^a-z0-9]+", " ", raw_name.lower()).strip()
        venue_str = e.get("venue") or ""
        head = _normalize_title_head(raw_name, venue=venue_str)
        venue = venue_str.lower()
        curl = _clean_event_url(e.get("url"))

        match = None
        # 0. Canonical specific URL match check
        if curl and curl in seen_url:
            for cand in seen_url[curl]:
                if not _is_different_show(e, cand):
                    match = cand
                    break

        # 1. Exact match check
        if not match and full and len(full) >= 4 and full in seen_exact:
            for cand in seen_exact[full]:
                if not _is_different_show(e, cand):
                    match = cand
                    break

        # 2. Normalized head match check
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS and head in seen_head:
            for cand in seen_head[head]:
                c_venue = (cand.get("venue") or "").lower()
                if _venue_match(venue, c_venue, e, cand):
                    if not _is_different_show(e, cand):
                        match = cand
                        break

        # 3. Same physical venue title prefix/containment match
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS:
            for cand in out:
                c_venue = (cand.get("venue") or "").lower()
                if _venue_match(venue, c_venue, e, cand) and not _is_different_show(e, cand):
                    cand_head = _normalize_title_head(cand.get("name") or "", venue=cand.get("venue"))
                    if cand_head and cand_head not in GENERIC_HEADS:
                        if (cand_head.startswith(head) or head.startswith(cand_head)) and min(len(head), len(cand_head)) >= 6:
                            match = cand
                            break

        if match:
            match.setdefault("_alt_sources", [])
            src_url = e.get("url")
            src_name = e.get("_source_venue") or e.get("venue") or "source"
            if src_url and not any(a.get("url") == src_url for a in match["_alt_sources"]) and src_url != match.get("url"):
                match["_alt_sources"].append({"venue": src_name, "url": src_url, "price": e.get("price")})

            # If the newly arrived event has higher priority (e.g. direct venue vs aggregator), upgrade primary info
            cur_prio = _source_priority(match.get("_source_venue"))
            new_prio = _source_priority(e.get("_source_venue"))
            if new_prio > cur_prio:
                old_url = match.get("url")
                old_src = match.get("_source_venue")
                if old_url and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": old_src, "url": old_url, "price": match.get("price")})
                match["url"] = e.get("url")
                match["name"] = e.get("name")
                match["venue"] = e.get("venue")
                match["_source_venue"] = e.get("_source_venue")
                if e.get("_time") and (e["_time"].hour != 0 or e["_time"].minute != 0):
                    match["_time"] = e["_time"]

            if not match.get("price") and e.get("price"):
                match["price"] = e["price"]

            p_venue = (match.get("venue") or "").lower()
            if p_venue in generic_sources and venue and venue not in generic_sources:
                match["venue"] = e.get("venue")

            if (not match.get("category") or match.get("category") in ("other", "community")) and e.get("category") and e.get("category") not in ("other", "community"):
                match["category"] = e["category"]

            if not match.get("genre") and e.get("genre"):
                match["genre"] = e["genre"]

            if not match.get("description") and e.get("description"):
                match["description"] = e["description"]
        else:
            if curl:
                seen_url.setdefault(curl, []).append(e)
            if full and len(full) >= 4:
                seen_exact.setdefault(full, []).append(e)
            if head and len(head) >= 4 and head not in GENERIC_HEADS:
                seen_head.setdefault(head, []).append(e)
            out.append(e)

    return out


def group_by_date(results):
    """Flatten venue results into events annotated with venue; group by Eastern calendar date.

    Returns (dated_from_today, tba, ongoing). `ongoing` is events whose date is before today
    (useful long-running or evergreen listings that sources flag as upcoming/pinned).
    """
    today = datetime.now(EASTERN).date()
    horizon = today + timedelta(days=120)
    buckets = {}
    tba = []
    ongoing = []
    for r in results:
        for e in r["events"]:
            name = e.get("name") or ""
            if is_placeholder_or_closed_event(name):
                continue
            entry = {"venue_url": r["url"], **e, "_source_venue": r["venue"]}
            entry["venue"] = e.get("venue") or r["venue"]
            raw = e.get("date")
            key = None
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=EASTERN)
                    else:
                        dt = dt.astimezone(EASTERN)
                    key = dt.date()
                    entry["_time"] = dt
                except (TypeError, ValueError):
                    pass
            if key is None:
                tba.append(entry)
            elif key < today:
                ongoing.append(entry)
            elif key <= horizon:
                buckets.setdefault(key, []).append(entry)
    for date_key, events in list(buckets.items()):
        events.sort(key=lambda e: e["_time"])
        buckets[date_key] = _merge_duplicates(events)
    ongoing.sort(key=lambda e: e.get("_time") or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    return sorted(buckets.items()), tba, ongoing


def render_page(results, weather=None, luckyseat_shows=None):
    if not any(r.get("venue") == "Community Submissions" for r in results):
        comm = _load_community_events()
        if comm:
            results = list(results) + comm

    today = datetime.now(EASTERN).date()
    today_iso = today.isoformat()
    dated, tba, ongoing = group_by_date(results)
    recurring_keys = compute_recurring(dated)
    total = sum(len(v) for _, v in dated) + len(tba)
    failed = [r for r in results if r.get("error")]
    all_venue_names = [r["venue"] for r in results]

    upvotes_map = _load_upvotes_map()

    if weather is None:
        weather = fetch_boston_weather()
    weather_pill_html = ""
    if weather:
        w_label = weather.get("label", "")
        w_icon = weather.get("icon", "🌤️")
        w_temp = weather.get("temp", "--")
        weather_pill_html = f'<span class="pill-weather" title="{w_label} in Boston"><span class="chip-icon">{w_icon} </span>{w_temp}°F <span class="weather-label">{w_label}</span></span><span class="pill-dot">·</span>'
        weather_html = f'{w_icon} {w_temp}°F {w_label} · '
    else:
        weather_html = ""

    def is_recurring(e):
        return (
            (e.get("name") or "").strip().lower(),
            e.get("_source_venue") or "",
        ) in recurring_keys

    def render_event(e):
        raw_title = e.get("name") or "Untitled"
        title = escape(raw_title)
        ev_id = _event_stable_id(e)
        link = (
            f'<a href="{escape(e["url"])}" target="_blank" rel="noopener">{title}</a>'
            if e.get("url") else title
        )
        is_free = _is_event_free(e)
        price_raw = escape(e["price"]) if e.get("price") else ""
        if price_raw:
            if "free" in price_raw.lower() or price_raw in ("$0", "0"):
                price_tag = f'<span class="price free">{price_raw}</span>'
            else:
                price_tag = f'<span class="price">{price_raw}</span>'
        elif is_free:
            price_tag = '<span class="price free">Free</span>'
        else:
            price_tag = ""

        cat = e.get("category") or "other"
        genre = e.get("genre")
        if not genre and cat in ("music", "clubbing"):
            genre = infer_music_genre(e.get("name"), e.get("venue"), description=e.get("description"), category=cat)
            e["genre"] = genre

        bucket = category_bucket(cat)
        if genre and genre in MUSIC_GENRES:
            ginfo = MUSIC_GENRES[genre]
            gcolor = ginfo["color"]
            gicon = ginfo["icon"]
            glabel = ginfo["label"]
            cat_tag = f'<span class="cat-pill genre-pill" data-genre="{escape(genre)}" title="Music Genre: {escape(glabel)}" style="--cat-c:{gcolor}; background:{gcolor}18; border-color:{gcolor}33; color:{gcolor}"><span class="chip-icon">{gicon} </span>{escape(glabel)}</span>'
        else:
            color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
            cat_tag = f'<span class="cat-pill" style="--cat-c:{color}; background:{color}18; border-color:{color}33; color:{color}"><span class="chip-icon">{icon} </span>{escape(cat)}</span>'
        venue = e.get("venue") or ""
        source = e.get("_source_venue") or ""
        city = _event_city(venue, source, e)
        recurring = is_recurring(e)
        recur_flag = "weekly" if recurring else "once"
        recur_badge = '<span class="recur">↻ weekly</span>' if recurring else ""
        alts = e.get("_alt_sources") or []
        alt_html = ""
        if alts:
            alt_parts = []
            for a in alts:
                if not a.get("url"):
                    continue
                v_name = escape(a.get("venue") or "source")
                a_price = f" ({escape(a['price'])})" if a.get("price") and a["price"] != e.get("price") else ""
                alt_parts.append(f'<a href="{escape(a["url"])}" target="_blank" rel="noopener">{v_name}{a_price}</a>')
            if alt_parts:
                alt_joined = " · ".join(alt_parts)
                alt_html = f'<span class="alt-sources">also on {alt_joined}</span>'

        compare_html = _build_compare_links(e, raw_title)

        geo = resolve_event_geo(e)
        geo_attrs = ""
        geo_btn = ""
        if geo:
            geo_attrs = f' data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-venue-name="{escape(geo["venue"])}" data-neighborhood="{escape(geo["neighborhood"])}"'
            geo_btn = ' <button type="button" class="venue-map-jump" title="View on Map"><span class="chip-icon">📍</span><span class="indie-jump-label">map</span></button>'

        sub_name, sub_slug = resolve_subarea(city, e, geo)
        sub_attrs = f' data-subarea="{escape(sub_slug)}"'
        sub_tag = f' <span class="subarea-tag">· {escape(sub_name)}</span>'

        transit_str = resolve_transit_lines(city, sub_slug, e, geo)
        transit_attr = f' data-transit="{escape(transit_str)}"' if transit_str else ""

        t_obj = e.get("_time")
        if t_obj:
            tod_val = "day" if t_obj.hour < 17 else "night"
        else:
            tod_val = "all"
        tod_attr = f' data-tod="{tod_val}"'

        if venue:
            if venue.lower() in ("zoom", "online", "virtual"):
                venue_link = f'<span class="venue-online">💻 {escape(venue)}</span>'
            else:
                maps_url = _maps_link(venue, city)
                venue_link = f'<a class="venue-link" href="{escape(maps_url)}" target="_blank" rel="noopener">{escape(venue)}</a>'

            if e.get("_is_community"):
                venue_html = f'{venue_link}{geo_btn} <span class="badge-community" title="Community submitted event"><span class="chip-icon">👤 </span>Community</span>'
            elif source and source.lower() != venue.lower() and not any(agg in source.lower() for agg in ["ticketmaster", "eventbrite", "do617", "boston calendar", "boston shows"]):
                venue_html = f'{venue_link}{geo_btn} <span class="venue-via">(via {escape(source)})</span>'
            else:
                venue_html = f'{venue_link}{geo_btn}'
        else:
            venue_html = ""

        extra_tags = []
        if alt_html:
            extra_tags.append(alt_html)
        if compare_html:
            extra_tags.append(compare_html)
        extra_html = (" · " + " · ".join(extra_tags)) if extra_tags else ""

        cal_html = '<span class="cal-links"><button type="button" class="cal-btn gcal-btn" title="Add to Google Calendar">+ GCal</button> <button type="button" class="cal-btn ics-btn" title="Download .ics">+ .ics</button></span>' if e.get("date") else ""
        star_btn = '<button type="button" class="star-btn" title="Save to My Shortlist" aria-label="Save event">☆</button>'

        raw_desc = (e.get("description") or "").replace("***", "").replace("**", "").replace("__", "").replace("`", "").strip()
        desc = raw_desc[:180]
        desc_html = f'<div class="desc">{escape(desc)}</div>' if desc else ""
        free_flag = "true" if is_free else "false"
        epoch_attr = f' data-epoch="{int(t_obj.timestamp())}"' if t_obj else ''
        genre_attr = f' data-genre="{escape(genre)}"' if genre else ''
        v_prefix = f" · {venue_html}" if venue_html else ""
        return (
            f'<li class="event" data-id="{ev_id}" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}"{genre_attr} '
            f'data-venue="{escape(source)}" data-city="{escape(city)}"{sub_attrs}{transit_attr}{tod_attr} '
            f'data-recur="{recur_flag}" data-free="{free_flag}"{epoch_attr}{geo_attrs}>'
            f'<div class="when">{escape(format_when(e))}</div>'
            f'<div class="what">{star_btn}{link}{price_tag}{recur_badge}'
            f'<div class="venue-tag">{cat_tag}{v_prefix}{sub_tag}{extra_html}{cal_html}</div>'
            f'{desc_html}</div></li>'
        )

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
            c = _event_city(e.get("venue"), e.get("_source_venue"), e)
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
        is_today = (date_attr == today_iso)
        day_class = "day" if is_today else "day out-of-week"
        past_banner_html = '''
          <div class="past-events-banner" id="past-events-banner" style="display: none;">
            <div class="past-banner-info">
              <span class="past-banner-badge" id="past-banner-badge"><span class="chip-icon">⏱️ </span>Live Tonight</span>
              <span class="past-banner-text" id="past-banner-text"></span>
            </div>
            <div class="past-banner-actions">
              <button type="button" class="past-banner-btn" id="btn-toggle-past">Show earlier today</button>
              <button type="button" class="past-banner-btn btn-tomorrow" id="btn-banner-tomorrow" style="display: none;">See Tomorrow →</button>
            </div>
          </div>''' if is_today else ""
        return f'''
        <section class="{day_class}" data-date="{date_attr}">
          <h2>{heading_html}<span class="count">{len(events)}</span></h2>
          {past_banner_html}
          <div class="cities">{"".join(city_blocks)}</div>
        </section>'''

    initial_sections = []
    deferred_sections = []
    for idx, (date_obj, events) in enumerate(dated):
        sec_html = _render_day_section(escape(format_date_heading(date_obj)), events, date_obj.isoformat())
        if idx < 7:
            initial_sections.append(sec_html)
        else:
            deferred_sections.append(sec_html)
    if tba:
        deferred_sections.append(_render_day_section("Date TBA", tba, "tba"))

    all_event_dates = [d.isoformat() for d, _ in dated]

    useful_sidebar = ""
    if STATIC_LINKS or DEAL_LINKS:
        deals_block = ""
        lucky_shows = luckyseat_shows if luckyseat_shows is not None else fetch_luckyseat_boston()
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
                    f'<div class="useful-cat"><div class="useful-cat-head" style="color:{color}"><span class="chip-icon">{icon} </span>{escape(cat)}</div><ul>{link_items}</ul></div>'
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
      <section class="ongoing" style="display: none;">
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
            <span><span class="chip-icon">{_bucket_icon_row(b)} </span>{escape(b)} <span class="count">{bucket_counts.get(b, 0)}</span></span>
          </label>'''
        for b in bucket_order
    )

    genre_order = list(MUSIC_GENRES.keys())
    genre_counts = {g: 0 for g in genre_order}
    for e in all_events_flat:
        g = e.get("genre")
        if not g and (e.get("category") or "") in ("music", "clubbing"):
            g = infer_music_genre(e.get("name"), e.get("venue"), description=e.get("description"), category=e.get("category"))
            e["genre"] = g
        if g in genre_counts:
            genre_counts[g] += 1

    genre_boxes = "\n".join(
        f'''<label class="chk">
            <input type="checkbox" class="genre-chk" value="{escape(gid)}" checked>
            <span><span class="genre-swatch" style="background:{ginfo['color']}"></span><span class="chip-icon">{ginfo['icon']} </span>{escape(ginfo['label'])} <span class="count">{genre_counts.get(gid, 0)}</span></span>
          </label>'''
        for gid, ginfo in MUSIC_GENRES.items()
    )

    recur_boxes = f'''
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="once" checked>
          <span>One-time <span class="count">{once_count}</span></span>
        </label>
        <label class="chk">
          <input type="checkbox" class="recur-chk" value="weekly" checked>
          <span><span class="chip-icon">↻ </span>Weekly recurring <span class="count">{recurring_count}</span></span>
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
        c = _event_city(e.get("venue"), e.get("_source_venue"), e)
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
    # In live mode, we keep fail_banner and internal notes silent for visitors
    other_note = ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Wicked Boston Events</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<script>
  try {{
    var t = localStorage.getItem('boston_events_theme') || 'indie';
    document.documentElement.setAttribute('data-theme', t);
  }} catch(e) {{}}
</script>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='16' fill='%230c0e14'/%3E%3Crect x='3' y='3' width='58' height='58' rx='13' fill='none' stroke='%23ffd866' stroke-width='3'/%3E%3Ctext x='32' y='48' font-family='Impact, Arial Black, sans-serif' font-weight='900' font-size='44' fill='%235d9bff' text-anchor='middle'%3EB%3C/text%3E%3C/svg%3E">
<style>
  :root, [data-theme="classic"] {{
    --bg: #0c0e14;
    --card: #151822;
    --card-hover: #1c202e;
    --fg: #eef1f8;
    --muted: #8e96a8;
    --accent: #5d9bff;
    --accent-glow: rgba(93, 155, 255, 0.25);
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --green: #4ade80;
    --green-bg: rgba(74, 222, 128, 0.14);
    --green-border: rgba(74, 222, 128, 0.32);
    --warn: #f0a07a;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  [data-theme="indie"] {{
    --bg: #0e1014;
    --card: #15181e;
    --card-hover: #1c2028;
    --fg: #f4f5f8;
    --muted: #8c93a4;
    --accent: #e2a85a;
    --accent-glow: transparent;
    --border: rgba(255, 255, 255, 0.08);
    --border-hover: rgba(255, 255, 255, 0.16);
    --green: #48bb78;
    --green-bg: rgba(72, 187, 120, 0.12);
    --green-border: rgba(72, 187, 120, 0.25);
    --warn: #e07a5f;
    --radius-lg: 10px;
    --radius-md: 6px;
    --radius-sm: 4px;
  }}
  [data-theme="anime"] {{
    --bg: #0d0a1c;
    --card: #17122e;
    --card-hover: #211a42;
    --fg: #f5f0ff;
    --muted: #a49abf;
    --accent: #ff4b93;
    --accent-glow: rgba(255, 75, 147, 0.4);
    --border: rgba(255, 107, 181, 0.22);
    --border-hover: rgba(0, 240, 255, 0.45);
    --green: #00f0ff;
    --green-bg: rgba(0, 240, 255, 0.14);
    --green-border: rgba(0, 240, 255, 0.38);
    --warn: #ff758f;
    --radius-lg: 18px;
    --radius-md: 12px;
    --radius-sm: 8px;
  }}
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    width: 100%;
    max-width: 100vw;
    overflow-x: hidden;
    -webkit-text-size-adjust: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: var(--bg);
    color: var(--fg);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  /* Modern Hero Banner */
  .banner {{
    position: relative;
    min-height: 270px;
    display: flex;
    align-items: flex-end;
    background-color: #121020;
    background-image:
      linear-gradient(180deg, rgba(12, 14, 20, 0.18) 0%, rgba(12, 14, 20, 0.62) 58%, rgba(12, 14, 20, 0.98) 100%),
      url('banner.jpg');
    background-size: cover;
    background-position: center 60%;
    border-bottom: 1px solid var(--border);
    padding: 40px 24px 28px;
  }}
  .banner-inner {{
    max-width: 1320px;
    width: 100%;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .banner-top-tag {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #ffd866;
    text-shadow: 0 1px 8px rgba(0,0,0,0.6);
  }}
  .live-pulse {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7);
    animation: livepulse 2s infinite;
  }}
  @keyframes livepulse {{
    0% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); }}
    70% {{ box-shadow: 0 0 0 8px rgba(74, 222, 128, 0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }}
  }}
  .banner-title {{
    margin: 0;
    font-size: 44px;
    font-weight: 850;
    letter-spacing: -0.035em;
    color: #ffffff;
    line-height: 1.05;
    text-shadow: 0 2px 20px rgba(0,0,0,0.6);
  }}
  .banner-meta-pill {{
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    align-self: flex-start;
    background: rgba(18, 21, 31, 0.72);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 6px 16px;
    font-size: 13px;
    color: var(--fg);
    box-shadow: 0 4px 20px rgba(0,0,0,0.35);
  }}
  .pill-weather {{ display: inline-flex; align-items: center; gap: 4px; font-weight: 600; color: #fff; }}
  .weather-label {{ font-weight: 400; color: var(--muted); }}
  .pill-dot {{ color: var(--muted); opacity: 0.6; }}
  .pill-submit-btn {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: linear-gradient(135deg, #ffd866 0%, #f29e4c 100%);
    color: #0c0e14;
    font-weight: 750;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 999px;
    border: none;
    cursor: pointer;
    font-family: inherit;
    box-shadow: 0 2px 8px rgba(255, 216, 102, 0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease, filter 0.15s ease;
    line-height: 1.3;
    vertical-align: middle;
  }}
  .pill-submit-btn:hover {{
    transform: translateY(-1px) scale(1.02);
    box-shadow: 0 4px 12px rgba(255, 216, 102, 0.45);
    filter: brightness(1.06);
  }}
  .pill-submit-btn:active {{
    transform: translateY(1px);
  }}

  /* Layout */
  .layout {{
    max-width: 1320px;
    margin: 0 auto;
    padding: 20px 24px 48px;
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr) 240px;
    gap: 18px;
    align-items: start;
  }}
  aside.filters {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-right: 4px;
  }}
  aside.filters::-webkit-scrollbar, aside.useful::-webkit-scrollbar {{ width: 6px; }}
  aside.filters::-webkit-scrollbar-thumb, aside.useful::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
  aside.useful {{
    position: sticky;
    top: 12px;
    max-height: calc(100vh - 24px);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  aside.useful .useful-inner {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }}
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

  main {{ display: flex; flex-direction: column; gap: 14px; min-width: 0; }}

  /* Top-Level Location Bar */
  .location-chips-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    max-width: 100%;
  }}
  .location-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .loc-chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .loc-chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: #fff;
  }}
  .loc-chip.active {{
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.35);
    color: #fff;
    font-weight: 700;
  }}
  .loc-chip.active[data-city="boston"] {{
    border-color: #5d9bff;
    background: rgba(93, 155, 255, 0.18);
    color: #79aeff;
  }}
  .loc-chip.active[data-city="cambridge"] {{
    border-color: #e05a6b;
    background: rgba(224, 90, 107, 0.18);
    color: #ff7a8a;
  }}
  .loc-chip.active[data-city="somerville"] {{
    border-color: #f29e4c;
    background: rgba(242, 158, 76, 0.18);
    color: #ffb169;
  }}
  .loc-chip.active[data-city="other"] {{
    border-color: #9aa3b2;
    background: rgba(154, 163, 178, 0.18);
    color: #d1d5db;
  }}
  .city-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }}

  /* Secondary Subarea Chips Bar */
  .subarea-chips-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px dashed var(--border);
    border-radius: var(--radius-md);
    padding: 6px 10px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    max-width: 100%;
  }}
  .subarea-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .sub-chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 11px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .sub-chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.3);
    color: #fff;
  }}
  .sub-chip.active {{
    background: rgba(93, 155, 255, 0.16);
    border-color: var(--accent);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
  }}
  .subarea-tag {{
    color: var(--muted);
    font-size: 11px;
    font-weight: 500;
  }}

  /* Music Genre Chips Bar */
  .genre-chips-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 6px 10px;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    max-width: 100%;
  }}
  .genre-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .genre-chip {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
    white-space: nowrap;
    transition: all 0.15s ease;
    user-select: none;
  }}
  .genre-chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.3);
    color: #fff;
  }}
  .genre-chip.active {{
    background: rgba(122, 162, 247, 0.18);
    border-color: rgba(122, 162, 247, 0.5);
    color: #fff;
    font-weight: 700;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.3);
  }}
  .genre-chip.active[data-genre="rock_indie"] {{ border-color: #ff708d; background: rgba(255, 112, 141, 0.2); color: #ff94ab; }}
  .genre-chip.active[data-genre="jazz_blues"] {{ border-color: #f29e4c; background: rgba(242, 158, 76, 0.2); color: #ffb169; }}
  .genre-chip.active[data-genre="folk_trad"] {{ border-color: #9ece6a; background: rgba(158, 206, 106, 0.2); color: #b4e67d; }}
  .genre-chip.active[data-genre="electronic"] {{ border-color: #bb9af7; background: rgba(187, 154, 247, 0.2); color: #cfb7ff; }}
  .genre-chip.active[data-genre="classical"] {{ border-color: #7aa2f7; background: rgba(122, 162, 247, 0.2); color: #9abaff; }}
  .genre-chip.active[data-genre="hiphop_rnb"] {{ border-color: #f0a07a; background: rgba(240, 160, 122, 0.2); color: #ffb799; }}
  .genre-chip.active[data-genre="latin_global"] {{ border-color: #ffb8d1; background: rgba(255, 184, 209, 0.2); color: #ffd1e3; }}
  .genre-chip.active[data-genre="pop"] {{ border-color: #ffd866; background: rgba(255, 216, 102, 0.2); color: #ffe68f; }}

  .genre-pill {{
    cursor: pointer;
    transition: transform 0.12s ease, filter 0.12s ease;
  }}
  .genre-pill:hover {{
    transform: translateY(-1px);
    filter: brightness(1.25);
  }}
  .genre-swatch {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
    vertical-align: middle;
  }}

  /* Quick-Access Chips Bar */
  .quick-chips-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: nowrap;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    -ms-overflow-style: none;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    max-width: 100%;
  }}
  .quick-chips-bar::-webkit-scrollbar {{
    display: none;
  }}
  .chip {{
    flex-shrink: 0;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .chip:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: #fff;
  }}
  .chip.active {{
    background: var(--accent);
    color: #0c0e14;
    border-color: var(--accent);
    font-weight: 700;
    box-shadow: 0 2px 10px var(--accent-glow);
  }}
  .chip-popular {{
    color: #f29e4c;
    border-color: rgba(242, 158, 76, 0.4);
    background: rgba(242, 158, 76, 0.08);
    margin-left: auto;
  }}
  .chip-popular:hover {{
    background: rgba(242, 158, 76, 0.16);
    border-color: #f29e4c;
    color: #ffd866;
  }}
  .chip-popular.active {{
    background: linear-gradient(135deg, #f29e4c 0%, #ffd866 100%);
    color: #0c0e14;
    border-color: #ffd866;
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(242, 158, 76, 0.35);
  }}
  .chip-free {{
    color: var(--green);
    border-color: var(--green-border);
    background: var(--green-bg);
  }}
  .chip-free.active {{
    background: var(--green);
    color: #08200f;
    border-color: var(--green);
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(74, 222, 128, 0.3);
  }}
  .chip-starred {{
    color: #ffd866;
    border-color: rgba(255, 216, 102, 0.35);
    background: rgba(255, 216, 102, 0.08);
  }}
  .chip-starred:hover {{
    background: rgba(255, 216, 102, 0.16);
    border-color: #ffd866;
    color: #fff;
  }}
  .chip-starred.active {{
    background: #ffd866;
    color: #0c0e14;
    border-color: #ffd866;
    font-weight: 700;
    box-shadow: 0 2px 10px rgba(255, 216, 102, 0.35);
  }}
  .chip-copy-plan {{
    color: #79aeff;
    border-color: rgba(121, 174, 255, 0.35);
    background: rgba(121, 174, 255, 0.1);
    font-weight: 600;
  }}
  .chip-copy-plan:hover {{
    background: rgba(121, 174, 255, 0.22);
    border-color: #79aeff;
    color: #fff;
  }}
  .star-btn {{
    background: none;
    border: none;
    color: var(--muted);
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    padding: 0 5px 0 0;
    vertical-align: baseline;
    opacity: 0.55;
    transition: transform 0.12s ease, color 0.12s ease, opacity 0.12s ease;
  }}
  .star-btn:hover {{
    opacity: 1;
    color: #ffd866;
    transform: scale(1.2);
  }}
  .star-btn.starred {{
    opacity: 1;
    color: #ffd866;
    text-shadow: 0 0 8px rgba(255, 216, 102, 0.45);
  }}
  .transit-sep {{
    width: 1px;
    height: 18px;
    background: var(--border);
    margin: 0 2px;
  }}
  .transit-chip {{
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.15s ease;
  }}
  .transit-chip:hover {{
    color: #fff;
    border-color: rgba(255, 255, 255, 0.28);
    background: rgba(255, 255, 255, 0.08);
  }}
  .transit-chip.active[data-transit="red"]    {{ background: rgba(218, 41, 28, 0.22); border-color: #da291c; color: #ff7b72; }}
  .transit-chip.active[data-transit="green"]  {{ background: rgba(0, 132, 61, 0.24); border-color: #00843d; color: #4ade80; }}
  .transit-chip.active[data-transit="orange"] {{ background: rgba(237, 139, 0, 0.22); border-color: #ed8b00; color: #ffb169; }}
  .transit-chip.active[data-transit="blue"]   {{ background: rgba(0, 61, 165, 0.28); border-color: #3b82f6; color: #93c5fd; }}
  .t-dot {{
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }}

  /* Day Section */
  .day {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 14px 18px 12px;
    content-visibility: auto;
    contain-intrinsic-size: auto 600px;
  }}
  .day h2 {{ margin: 0 0 12px; font-size: 17px; font-weight: 700; display:flex; align-items:center; gap:8px; color: var(--fg); position: sticky; top: 0; background: var(--card); padding: 4px 0 8px; z-index: 2; }}
  .count {{ background: rgba(255, 255, 255, 0.06); color: var(--muted); font-size: 11px; padding: 2px 8px; border-radius: 999px; font-weight: 500; }}
  .cities {{ display: flex; flex-direction: column; gap: 14px; }}
  .city-section {{ --city-color: var(--accent); border-top: 1px solid var(--border); padding-top: 12px; padding-left: 10px; border-left: 3px solid var(--city-color); }}
  .city-section:first-child {{ border-top: none; padding-top: 0; }}
  .city-section.empty {{ display: none; }}
  .city-section[data-city="boston"]    {{ --city-color: #5d9bff; }}
  .city-section[data-city="cambridge"] {{ --city-color: #e05a6b; }}
  .city-section[data-city="somerville"]{{ --city-color: #f29e4c; }}
  .city-section[data-city="other"]     {{ --city-color: #9aa3b2; }}
  .city-head {{ margin: 0 0 8px; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--city-color); display: flex; align-items: center; gap: 8px; }}
  .city-head .count {{ background: transparent; color: var(--muted); font-weight: 500; letter-spacing: 0; }}
  .buckets {{ display: flex; flex-direction: column; gap: 10px; }}
  .bucket {{ border-left: 3px solid var(--accent, #444); padding: 2px 0 2px 12px; border-left-color: var(--accent); }}
  .bucket-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); font-weight: 600; }}
  .bucket-head .count {{ background: transparent; color: var(--muted); }}
  .bucket ul {{ list-style: none; padding: 0; margin: 0; }}

  /* Event Cards */
  .event {{
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid rgba(255, 255, 255, 0.04);
    margin-bottom: 6px;
    display: grid;
    grid-template-columns: 78px minmax(0, 1fr);
    align-items: start;
    gap: 12px;
    font-size: 14px;
    min-width: 0;
    transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
  }}
  .event:hover {{
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(93, 155, 255, 0.3);
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.22);
  }}

  /* Upvote Button & Vote Wrap */
  .vote-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-start;
    padding-top: 1px;
    min-width: 40px;
  }}
  .btn-upvote {{
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 38px;
    padding: 4px 6px;
    border-radius: var(--radius-sm);
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border);
    color: var(--muted);
    font-family: inherit;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    line-height: 1.15;
    transition: all 0.15s ease;
    user-select: none;
    -webkit-user-select: none;
  }}
  .btn-upvote:hover {{
    background: rgba(255, 255, 255, 0.08);
    border-color: var(--accent);
    color: var(--fg);
    transform: translateY(-1px);
  }}
  .btn-upvote .upvote-arrow {{
    font-size: 10px;
    line-height: 1;
    margin-bottom: 2px;
    transition: transform 0.15s ease;
  }}
  .btn-upvote:hover .upvote-arrow {{
    transform: translateY(-1px);
    color: var(--accent);
  }}
  .btn-upvote.voted {{
    background: rgba(255, 216, 102, 0.14);
    border-color: #ffd866;
    color: #ffd866;
    box-shadow: 0 0 10px rgba(255, 216, 102, 0.25);
  }}
  .btn-upvote.voted .upvote-arrow {{
    color: #ffd866;
  }}
  .btn-upvote.anim-bounce {{
    animation: upvote-pop 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  }}
  @keyframes upvote-pop {{
    0% {{ transform: scale(1); }}
    50% {{ transform: scale(1.22); }}
    100% {{ transform: scale(1); }}
  }}

  /* Popular State (3 to 4 votes) */
  .event.popular {{
    border-color: rgba(242, 158, 76, 0.38);
    background: rgba(242, 158, 76, 0.025);
  }}
  .event.popular .btn-upvote {{
    border-color: rgba(242, 158, 76, 0.45);
    color: #f29e4c;
  }}
  .badge-popular {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    background: rgba(242, 158, 76, 0.15);
    border: 1px solid rgba(242, 158, 76, 0.4);
    color: #f29e4c;
    vertical-align: middle;
  }}

  /* Glowing State (5+ votes) */
  .event.glowing {{
    border-color: rgba(255, 216, 102, 0.65);
    background: linear-gradient(135deg, rgba(255, 216, 102, 0.06) 0%, rgba(255, 255, 255, 0.02) 100%);
    box-shadow: 0 0 18px rgba(255, 216, 102, 0.2), 0 2px 10px rgba(0, 0, 0, 0.3);
    position: relative;
  }}
  .event.glowing:hover {{
    border-color: rgba(255, 216, 102, 0.9);
    box-shadow: 0 0 26px rgba(255, 216, 102, 0.35), 0 4px 16px rgba(0, 0, 0, 0.4);
  }}
  .event.glowing .btn-upvote {{
    background: linear-gradient(135deg, rgba(255, 216, 102, 0.22) 0%, rgba(242, 158, 76, 0.22) 100%);
    border-color: #ffd866;
    color: #ffd866;
    box-shadow: 0 0 12px rgba(255, 216, 102, 0.45);
  }}
  .badge-glowing {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: linear-gradient(135deg, #ffd866 0%, #f29e4c 100%);
    color: #0c0e14;
    border: none;
    box-shadow: 0 0 10px rgba(255, 216, 102, 0.5);
    vertical-align: middle;
    animation: badge-pulse-glow 2.5s infinite;
  }}
  @keyframes badge-pulse-glow {{
    0%, 100% {{ box-shadow: 0 0 8px rgba(255, 216, 102, 0.4); transform: scale(1); }}
    50% {{ box-shadow: 0 0 16px rgba(255, 216, 102, 0.7); transform: scale(1.03); }}
  }}
  .when {{ color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; padding-top: 2px; font-weight: 500; }}
  .what {{ min-width: 0; overflow-wrap: break-word; word-break: break-word; }}
  .what a {{ color: #79aeff; text-decoration: none; font-weight: 500; }}
  .what a:hover {{ text-decoration: underline; color: #a5caff; }}
  .venue-tag {{ color: var(--muted); font-size: 11px; margin-top: 4px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }}
  .venue-link {{ color: var(--muted); text-decoration: none; border-bottom: 1px dotted rgba(154,163,178,0.4); }}
  .venue-link:hover {{ color: var(--fg); border-bottom-color: var(--fg); }}
  .venue-via {{ color: var(--muted); font-size: 11px; opacity: 0.85; font-style: italic; }}
  .venue-online {{ color: var(--muted); font-size: 11px; }}
  .cat-pill {{ display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 600; line-height: 1.3; border: 1px solid; }}
  .price {{ display:inline-block; margin-left: 8px; background: rgba(255,255,255,0.06); color: var(--muted); font-size: 11px; padding: 2px 7px; border-radius: 5px; font-weight: 500; vertical-align: middle; }}
  .price.free {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green-border); font-weight: 700; }}
  .price.ticketed {{ background: rgba(139, 178, 255, 0.12); color: #8bb2ff; border: 1px solid rgba(139, 178, 255, 0.3); font-weight: 600; font-size: 10px; }}
  .cal-links {{ display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; }}
  .cal-btn {{ background: rgba(255,255,255,0.04); border: 1px solid var(--border); color: var(--muted); padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 500; text-decoration: none; cursor: pointer; line-height: 1.3; display: inline-flex; align-items: center; gap: 3px; font-family: inherit; transition: all 0.15s ease; }}
  .cal-btn:hover {{ color: #fff; border-color: var(--accent); background: rgba(93,155,255,0.15); }}
  .recur {{ display:inline-block; margin-left: 8px; background: rgba(255,122,178,0.14); color: #ff7ab2; font-size: 10px; padding: 2px 6px; border-radius: 4px; letter-spacing: 0.02em; }}
  .alt-sources {{ color: var(--muted); font-size: 11px; }}
  .alt-sources a {{ color: var(--accent); text-decoration: none; }}
  .alt-sources a:hover {{ text-decoration: underline; }}
  .compare-tickets {{ color: var(--muted); font-size: 11px; }}
  .compare-tickets a {{ color: #8bb2ff; text-decoration: none; border-bottom: 1px dotted rgba(139,178,255,0.4); }}
  .compare-tickets a:hover {{ color: #fff; border-bottom-color: #fff; }}
  .desc {{
    color: var(--muted);
    font-size: 12px;
    margin-top: 5px;
    line-height: 1.45;
    word-break: break-word;
    overflow-wrap: break-word;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    max-width: 100%;
  }}
  .bucket.empty {{ display: none; }}

  /* Filter Groups */
  .filter-group {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
  .filter-group h3 {{ margin: 0 0 8px; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); display: flex; align-items:center; gap:8px; flex-wrap:wrap; }}
  .filter-group h3 .spacer {{ flex:1; }}
  .filter-group h3 button {{ background: none; border: 1px solid var(--border); color: var(--muted); font-size: 10px; padding: 1px 8px; border-radius: 999px; cursor: pointer; font-family: inherit; letter-spacing: 0; text-transform: none; }}
  .filter-group h3 button:hover {{ color: var(--fg); border-color: var(--fg); }}
  .filter-badge {{ background: var(--accent); color: #0d1117; font-size: 10px; font-weight: 700; padding: 1px 7px; border-radius: 999px; text-transform: none; letter-spacing: 0; }}
  .reset-filters-bar {{ margin-bottom: 8px; }}
  .btn-reset-filters {{
    width: 100%;
    background: rgba(224, 90, 107, 0.12);
    border: 1px solid rgba(224, 90, 107, 0.35);
    color: #ff7b72;
    font-size: 11px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: var(--radius-md);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}
  .btn-reset-filters:hover {{
    background: rgba(224, 90, 107, 0.22);
    border-color: #ff7b72;
    color: #ffffff;
  }}
  .filter-group.venues .chk-grid {{ max-height: 280px; overflow-y: auto; }}
  .chk-grid {{ display:flex; flex-direction: column; gap:2px; }}
  .chk {{ display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; padding: 3px 4px; border-radius: 6px; }}
  .chk:hover {{ background: rgba(255,255,255,0.03); }}
  .chk input {{ accent-color: var(--accent); margin: 0; flex-shrink: 0; }}
  .chk > span {{ display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }}
  .chk > span > .count {{ margin-left: auto; }}
  .city-swatch {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .free-toggle {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: var(--green); user-select: none; }}
  .free-toggle input {{ accent-color: var(--green); width: 14px; height: 14px; cursor: pointer; margin: 0; }}

  /* Search Box */
  .search-input-wrap {{ position: relative; display: flex; align-items: center; }}
  #search-input {{ width:100%; background:var(--bg); border:1px solid var(--border); color:var(--fg); padding:8px 36px 8px 10px; border-radius:var(--radius-sm); font-size:13px; font-family:inherit; transition: border-color 0.15s ease, box-shadow 0.15s ease; }}
  #search-input:focus {{ outline:none; border-color:var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }}
  #search-input::placeholder {{ color:var(--muted); }}
  .search-kbd {{ position: absolute; right: 10px; background: rgba(255, 255, 255, 0.08); color: var(--muted); font-size: 11px; padding: 1px 6px; border-radius: 4px; pointer-events: none; font-family: monospace; border: 1px solid rgba(255,255,255,0.06); }}
  .search-clear-btn {{ position: absolute; right: 8px; background: none; border: none; color: var(--muted); font-size: 16px; cursor: pointer; padding: 2px 6px; line-height: 1; }}
  .search-clear-btn:hover {{ color: var(--fg); }}
  .search-status {{ margin-top: 6px; font-size: 11px; color: var(--accent); font-weight: 500; }}

  /* Week navigation */
  .week-nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 8px 12px; }}
  .week-nav.bottom {{ justify-content: center; }}
  .week-nav button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; font-family: inherit; }}
  .week-nav button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .week-nav button[aria-pressed="true"], .week-nav button.active {{ background: var(--accent); color: #0c0e14; border-color: var(--accent); font-weight: 600; }}
  #week-label, #week-label-b {{ font-size: 13px; font-weight: 600; color: var(--fg); flex: 1; text-align: center; min-width: 160px; }}
  .week-nav.bottom #week-label-b {{ flex: 0; padding: 0 12px; }}
  .mini-cal {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; }}
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
  .mini-cal-grid .d.in-week {{ background: rgba(93,155,255,0.12); color: var(--fg); }}
  .mini-cal-grid .d.anchor {{ background: var(--accent); color: #0c0e14; font-weight: 700; }}
  .mini-cal-grid .d.anchor::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.blank {{ cursor: default; }}
  .mini-cal-grid .d:not(.blank):hover {{ border-color: var(--accent); }}
  .event.hidden {{ display: none; }}
  .day.empty, .day.out-of-week {{ display: none; }}
  .no-events-msg {{
    background: var(--card);
    border: 1px dashed var(--border);
    border-radius: var(--radius-md);
    padding: 36px 20px;
    text-align: center;
    color: var(--muted);
    margin: 8px 0 16px;
  }}
  .no-events-msg p {{
    margin: 0 0 14px;
    font-size: 14px;
    color: var(--fg);
  }}

  /* Past Events Filter Banner */
  .past-events-banner {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 8px 12px;
    margin: 8px 0 16px;
    font-size: 12px;
  }}
  .past-banner-info {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--fg);
    flex-wrap: wrap;
  }}
  .past-banner-badge {{
    background: rgba(93, 155, 255, 0.15);
    border: 1px solid rgba(93, 155, 255, 0.3);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
  }}
  .past-banner-badge.badge-all {{
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.2);
    color: var(--fg);
  }}
  .past-banner-badge.badge-done {{
    background: rgba(242, 158, 76, 0.15);
    border-color: rgba(242, 158, 76, 0.35);
    color: #f29e4c;
  }}
  .past-banner-actions {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .past-banner-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: var(--radius-sm);
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .past-banner-btn:hover {{
    background: rgba(255, 255, 255, 0.12);
    border-color: var(--accent);
    color: #fff;
  }}
  .past-banner-btn.btn-tomorrow {{
    background: var(--accent);
    color: #0c0e14;
    border-color: var(--accent);
    font-weight: 700;
  }}
  .past-banner-btn.btn-tomorrow:hover {{
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .event.past-time {{
    opacity: 0.55;
    transition: opacity 0.15s ease;
  }}
  .event.past-time:hover {{
    opacity: 0.95;
  }}
  .event.past-time .when::after {{
    content: " (earlier)";
    font-size: 10px;
    opacity: 0.7;
    font-weight: 400;
  }}

  /* View Switcher */
  .view-switch-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 6px 12px;
  }}
  .view-toggle {{
    display: inline-flex;
    align-items: center;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 2px;
    gap: 2px;
  }}
  .view-btn {{
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    padding: 5px 14px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;
  }}
  .view-btn:hover {{
    color: var(--fg);
  }}
  .view-btn.active {{
    background: var(--accent);
    color: #0c0e14;
    font-weight: 700;
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .share-filter-btn {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    transition: all 0.15s ease;
  }}
  .share-filter-btn:hover {{
    color: var(--fg);
    border-color: var(--accent);
  }}
  .share-filter-btn.copied {{
    background: rgba(35, 134, 54, 0.2);
    border-color: #238636;
    color: #3fb950;
  }}
  .map-venue-stat {{
    font-size: 12px;
    color: var(--muted);
  }}
  .map-venue-stat strong {{
    color: var(--accent);
  }}

  /* Map View Wrapper */
  .map-view-wrapper {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    position: relative;
  }}
  .map-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 4px;
  }}
  .map-header-title {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--fg);
  }}
  .map-hint {{
    color: var(--muted);
    font-size: 11px;
  }}
  .map-tool-btn {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: var(--radius-sm);
    padding: 3px 10px;
    font-size: 11px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
  }}
  .map-tool-btn:hover {{
    border-color: var(--accent);
    color: var(--accent);
  }}
  .leaflet-map {{
    width: 100%;
    height: 520px;
    border-radius: var(--radius-md);
    border: 1px solid var(--border);
    background: #0c0e14;
    z-index: 1;
  }}
  .leaflet-container.osm-dark-tiles,
  .leaflet-container.osm-dark-tiles .leaflet-tile-container {{
    background: #0c0e14 !important;
  }}
  .leaflet-container.osm-dark-tiles .leaflet-tile-pane {{
    filter: invert(100%) hue-rotate(180deg) brightness(88%) contrast(95%);
  }}
  .leaflet-control-attribution {{
    background: rgba(12, 14, 20, 0.85) !important;
    color: var(--muted) !important;
    border-radius: var(--radius-sm);
    font-size: 10px !important;
    padding: 2px 6px !important;
  }}
  .leaflet-control-attribution a {{
    color: var(--accent) !important;
    text-decoration: none !important;
  }}
  .leaflet-control-attribution a:hover {{
    text-decoration: underline !important;
  }}
  .leaflet-bar a {{
    background-color: #141824 !important;
    color: #eef1f8 !important;
    border: 1px solid var(--border) !important;
    border-bottom: 1px solid var(--border) !important;
  }}
  .leaflet-bar a:hover {{
    background-color: #1e2436 !important;
    color: var(--accent) !important;
  }}

  /* Venue Map Pin in Leaflet */
  .custom-venue-icon {{
    background: transparent !important;
    border: none !important;
  }}
  .venue-marker {{
    background: #141824;
    border: 1.5px solid var(--accent);
    color: #eef1f8;
    border-radius: 999px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.7), 0 0 10px rgba(93, 155, 255, 0.35);
    cursor: pointer;
    white-space: nowrap;
    transition: transform 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
    transform: translate(-50%, -50%);
    user-select: none;
  }}
  .venue-marker:hover, .venue-marker.highlighted {{
    transform: translate(-50%, -50%) scale(1.12);
    background: var(--accent);
    color: #0c0e14;
    border-color: #fff;
    box-shadow: 0 6px 20px rgba(93, 155, 255, 0.6);
    z-index: 9999 !important;
  }}
  .venue-marker .pin-count {{
    background: var(--accent);
    color: #0c0e14;
    border-radius: 999px;
    font-size: 10px;
    padding: 1px 6px;
    font-weight: 800;
    line-height: 1.2;
  }}
  .venue-marker:hover .pin-count, .venue-marker.highlighted .pin-count {{
    background: #0c0e14;
    color: #fff;
  }}
  /* Compact numbers-only mode */
  .leaflet-map.hide-pin-names .venue-marker {{
    min-width: 24px;
    height: 24px;
    padding: 0 4px;
    border-radius: 999px;
    justify-content: center;
    gap: 0;
  }}
  .leaflet-map.hide-pin-names .venue-marker .pin-name {{
    display: none !important;
  }}
  .leaflet-map.hide-pin-names .venue-marker .pin-count {{
    background: transparent;
    color: var(--accent);
    padding: 0;
    font-size: 11px;
    font-weight: 800;
  }}
  .leaflet-map.hide-pin-names .venue-marker:hover .pin-count,
  .leaflet-map.hide-pin-names .venue-marker.highlighted .pin-count {{
    color: #0c0e14;
  }}
  .venue-map-jump {{
    background: none;
    border: none;
    cursor: pointer;
    font-size: 12px;
    padding: 0 2px;
    line-height: 1;
    opacity: 0.75;
    transition: transform 0.12s ease, opacity 0.12s ease;
    display: inline-block;
    vertical-align: middle;
  }}
  .venue-map-jump:hover {{
    opacity: 1;
    transform: scale(1.3);
  }}

  /* Dark theme Leaflet Popups */
  .leaflet-popup-content-wrapper, .leaflet-popup-tip {{
    background: #151822 !important;
    color: #eef1f8 !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    box-shadow: 0 16px 36px rgba(0, 0, 0, 0.85) !important;
    border-radius: 12px !important;
  }}
  .leaflet-popup-content {{
    margin: 12px 14px !important;
    line-height: 1.4 !important;
    font-family: inherit !important;
  }}
  .leaflet-container a.leaflet-popup-close-button {{
    color: var(--muted) !important;
    padding: 8px 10px !important;
  }}
  .leaflet-container a.leaflet-popup-close-button:hover {{
    color: #fff !important;
  }}
  .map-popup {{
    min-width: 220px;
    max-width: 280px;
  }}
  .popup-head {{
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
  }}
  .popup-head strong {{
    font-size: 13px;
    color: #fff;
  }}
  .popup-neighborhood {{
    font-size: 11px;
    color: var(--accent);
    font-weight: 500;
  }}
  .popup-events {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 220px;
    overflow-y: auto;
  }}
  .popup-event-item {{
    font-size: 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.03);
  }}
  .popup-time {{
    font-size: 10px;
    color: var(--muted);
  }}
  .popup-title {{
    color: var(--fg);
    text-decoration: none;
    font-weight: 500;
  }}
  .popup-title:hover {{
    color: var(--accent);
    text-decoration: underline;
  }}
  .popup-price {{
    font-size: 10px;
    color: var(--muted);
    margin-left: 6px;
  }}
  .popup-price.free {{
    color: var(--green);
    font-weight: 600;
  }}
  .popup-more {{
    font-size: 11px;
    color: var(--muted);
    text-align: center;
    padding: 4px 0 2px;
  }}
  .popup-foot {{
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: flex-end;
  }}
  .popup-dir-link {{
    font-size: 11px;
    color: var(--accent);
    text-decoration: none;
  }}
  .popup-dir-link:hover {{
    text-decoration: underline;
  }}

  /* Venue Card below map */
  .map-venue-card {{
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 12px 14px;
  }}
  .map-venue-card-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }}
  .map-venue-card-head h3 {{
    margin: 0;
    font-size: 15px;
    color: #fff;
  }}
  .panel-sub {{
    margin: 2px 0 0;
    font-size: 12px;
    color: var(--accent);
  }}
  .panel-close {{
    background: none;
    border: 1px solid var(--border);
    color: var(--muted);
    border-radius: 6px;
    padding: 2px 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 12px;
  }}
  .panel-close:hover {{
    color: var(--fg);
    border-color: var(--fg);
  }}
  .panel-events {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 260px;
    overflow-y: auto;
  }}
  .ongoing {{ margin-top: 4px; }}
  .ongoing h2 {{ margin: 0 0 4px; font-size: 15px; font-weight: 600; display:flex; align-items:center; gap:8px; color: var(--fg); }}
  .ongoing .hint {{ margin: 0 0 10px; color: var(--muted); font-size: 12px; }}
  .ongoing ul {{ list-style: none; padding: 14px 18px; margin: 0; background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); max-height: 420px; overflow-y: auto; }}
  .ongoing .event {{ padding: 8px 12px; }}
  .fail {{ max-width: 1320px; margin: 0 auto; padding: 8px 24px; color: var(--warn); font-size: 12px; }}
  .fail a {{ color: var(--warn); }}
  .other-note {{ max-width: 1320px; margin: 0 auto; padding: 4px 24px 0; color: var(--muted); font-size: 11px; }}
  footer {{ max-width: 1320px; margin: 0 auto; padding: 0 24px 32px; color: var(--muted); font-size: 12px; text-align: center; }}

  /* Mobile Responsive */
  .mobile-filter-bar {{ display: none; }}
  .mobile-filter-close {{ display: none; }}
  @media (max-width: 1100px) {{
    .layout {{ grid-template-columns: 240px minmax(0, 1fr); }}
    aside.useful {{ position: static; grid-column: 1 / -1; max-height: none; }}
  }}
  @media (max-width: 860px) {{
    .banner-title {{ font-size: 28px; }}
    .banner {{ min-height: 190px; padding: 24px 16px 16px; width: 100%; max-width: 100vw; }}
    .banner-meta-pill {{
      border-radius: var(--radius-md);
      font-size: 12px;
      padding: 6px 12px;
      gap: 6px 10px;
      max-width: 100%;
    }}
    .layout {{
      grid-template-columns: minmax(0, 1fr);
      padding: 12px;
      gap: 12px;
      width: 100%;
      max-width: 100vw;
      box-sizing: border-box;
      overflow-x: hidden;
    }}
    .mobile-filter-bar {{ display: block; margin-bottom: 8px; }}
    .mobile-filter-btn {{
      width: 100%;
      background: var(--card);
      border: 1px solid var(--border);
      color: var(--fg);
      padding: 10px 14px;
      border-radius: var(--radius-md);
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      font-family: inherit;
    }}
    aside.filters {{ display: none; }}
    aside.filters.mobile-open {{
      display: flex;
      position: fixed;
      inset: 0;
      z-index: 999;
      background: var(--bg);
      padding: 20px;
      max-height: 100vh;
      overflow-y: auto;
    }}
    .mobile-filter-close {{
      display: block;
      background: var(--accent);
      color: #0c0e14;
      border: none;
      padding: 10px;
      border-radius: var(--radius-sm);
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      font-family: inherit;
      margin-bottom: 12px;
    }}
    .location-chips-bar {{
      padding: 6px 10px;
      gap: 6px;
    }}
    .loc-chip {{
      padding: 5px 12px;
      font-size: 12px;
    }}
    .subarea-chips-bar {{
      padding: 5px 8px;
      gap: 5px;
    }}
    .sub-chip {{
      padding: 3px 9px;
      font-size: 11px;
    }}
    .genre-chips-bar {{
      padding: 5px 8px;
      gap: 5px;
    }}
    .genre-chip {{
      padding: 3px 10px;
      font-size: 11px;
    }}
    .quick-chips-bar {{
      flex-wrap: nowrap;
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      scrollbar-width: none;
      -ms-overflow-style: none;
      padding: 8px 10px;
      gap: 6px;
    }}
    .quick-chips-bar::-webkit-scrollbar {{
      display: none;
    }}
    .chip {{
      flex-shrink: 0;
      padding: 5px 12px;
      font-size: 12px;
    }}
    .chip-free, .chip-popular {{ margin-left: 0; }}

    .week-nav {{
      justify-content: space-between;
      gap: 6px;
      padding: 8px 10px;
      flex-wrap: wrap;
    }}
    #week-label, #week-label-b {{
      min-width: 0;
      width: 100%;
      flex-basis: 100%;
      order: -1;
      margin-bottom: 4px;
      font-size: 12px;
      text-align: center;
    }}

    .event {{
      grid-template-columns: 66px minmax(0, 1fr);
      gap: 8px;
      padding: 8px 10px;
    }}
    .what {{
      min-width: 0;
      overflow-wrap: break-word;
      word-break: break-word;
    }}
    .venue-tag {{
      font-size: 11px;
      gap: 4px;
    }}
    .cal-links {{
      margin-left: 0;
      margin-top: 2px;
    }}
    .day {{
      padding: 12px 14px 10px;
    }}
    .day h2 {{
      font-size: 15px;
    }}
    aside.useful {{
      grid-column: 1 / -1;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
    }}
    .leaflet-map {{
      height: 380px;
    }}
    .map-header {{
      flex-direction: column;
      align-items: flex-start;
      gap: 6px;
    }}
    /* Mobile: Default to compact numbers-only pins to prevent clutter */
    .venue-marker {{
      min-width: 24px;
      height: 24px;
      padding: 0 4px;
      border-radius: 999px;
      justify-content: center;
      gap: 0;
    }}
    .venue-marker .pin-name {{
      display: none;
    }}
    .venue-marker .pin-count {{
      background: transparent;
      color: var(--accent);
      padding: 0;
      font-size: 11px;
      font-weight: 800;
    }}
    .venue-marker:hover .pin-count,
    .venue-marker.highlighted .pin-count {{
      color: #0c0e14;
    }}
    /* Mobile: If user toggles names on */
    .leaflet-map.show-pin-names-mobile .venue-marker {{
      min-width: auto;
      height: auto;
      padding: 3px 8px;
      border-radius: 999px;
      gap: 5px;
    }}
    .leaflet-map.show-pin-names-mobile .venue-marker .pin-name {{
      display: inline !important;
    }}
    .leaflet-map.show-pin-names-mobile .venue-marker .pin-count {{
      background: var(--accent);
      color: #0c0e14;
      padding: 1px 6px;
    }}
  }}
  /* Banner Header Row */
  .banner-title-row {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}

  /* Community Badge */
  .badge-community {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: rgba(93, 155, 255, 0.15);
    border: 1px solid rgba(93, 155, 255, 0.3);
    color: #5d9bff;
    vertical-align: middle;
  }}

  /* Submission Modal Overlay */
  .modal-overlay {{
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(6, 8, 12, 0.78);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 99999;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    overflow-y: auto;
    animation: modalFadeIn 0.2s ease-out;
  }}
  @keyframes modalFadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
  }}
  .modal-card {{
    background: #141722;
    border: 1px solid var(--border-hover);
    border-radius: var(--radius-lg);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.05);
    width: 100%;
    max-width: 580px;
    max-height: 90vh;
    overflow-y: auto;
    padding: 28px 24px;
    position: relative;
    animation: modalCardPop 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  @keyframes modalCardPop {{
    from {{ transform: scale(0.95) translateY(12px); opacity: 0; }}
    to {{ transform: scale(1) translateY(0); opacity: 1; }}
  }}
  .modal-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 16px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
  }}
  .modal-tabs {{
    display: flex;
    gap: 6px;
    margin-bottom: 18px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 4px;
  }}
  .modal-tab {{
    flex: 1;
    background: transparent;
    border: none;
    color: var(--muted);
    font-size: 13px;
    font-weight: 700;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}
  .modal-tab:hover {{
    color: #ffffff;
  }}
  .modal-tab.active {{
    background: var(--accent);
    color: #0c0e14;
    box-shadow: 0 2px 8px var(--accent-glow);
  }}
  .modal-title {{
    margin: 0;
    font-size: 20px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
  }}
  .modal-sub {{
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.4;
  }}
  .modal-close-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 16px;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.15s ease;
    flex-shrink: 0;
  }}
  .modal-close-btn:hover {{
    background: rgba(255, 255, 255, 0.15);
    color: #ffffff;
  }}
  .modal-form {{
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}
  .form-row {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .form-grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  @media (max-width: 520px) {{
    .form-grid-2 {{
      grid-template-columns: 1fr;
    }}
  }}
  .form-label {{
    font-size: 12px;
    font-weight: 700;
    color: #c9d1d9;
    letter-spacing: 0.02em;
  }}
  .form-label .req {{
    color: #e05a6b;
  }}
  .form-label .hint {{
    font-weight: 400;
    color: var(--muted);
  }}
  .form-input, .form-select, .form-textarea {{
    width: 100%;
    box-sizing: border-box;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 9px 12px;
    color: #ffffff;
    font-size: 13px;
    font-family: inherit;
    transition: border-color 0.15s ease, background 0.15s ease;
  }}
  .form-input:focus, .form-select:focus, .form-textarea:focus {{
    outline: none;
    border-color: var(--accent);
    background: rgba(93, 155, 255, 0.08);
  }}
  .form-select option {{
    background: #151822;
    color: #ffffff;
  }}
  .price-input-row {{
    display: flex;
    gap: 8px;
    align-items: center;
  }}
  .btn-pill-free {{
    background: rgba(74, 222, 128, 0.14);
    border: 1px solid rgba(74, 222, 128, 0.35);
    color: #4ade80;
    font-weight: 700;
    font-size: 12px;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s ease;
  }}
  .btn-pill-free:hover {{
    background: rgba(74, 222, 128, 0.25);
  }}
  .form-status {{
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
  }}
  .form-status.success {{
    background: rgba(74, 222, 128, 0.15);
    border: 1px solid rgba(74, 222, 128, 0.4);
    color: #4ade80;
  }}
  .form-status.error {{
    background: rgba(224, 90, 107, 0.15);
    border: 1px solid rgba(224, 90, 107, 0.4);
    color: #ff7b8b;
  }}
  .form-actions {{
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 8px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
  }}
  .btn-cancel {{
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    font-weight: 600;
    font-size: 13px;
    padding: 9px 16px;
    border-radius: var(--radius-sm);
    cursor: pointer;
  }}
  .btn-cancel:hover {{
    color: #ffffff;
    border-color: var(--border-hover);
  }}
  .btn-primary-submit {{
    background: linear-gradient(135deg, #5d9bff 0%, #3b82f6 100%);
    border: none;
    color: #ffffff;
    font-weight: 700;
    font-size: 13px;
    padding: 10px 20px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
    transition: all 0.15s ease;
  }}
  .btn-primary-submit:hover {{
    box-shadow: 0 6px 20px rgba(59, 130, 246, 0.5);
    filter: brightness(1.08);
  }}
  .form-footer-note {{
    font-size: 11px;
    color: var(--muted);
    text-align: center;
    margin-top: 4px;
  }}
  /* ========================================================
     THEME SWITCHER & INDIE GUIDE THEME
     ======================================================== */
  .banner-top-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .theme-toggle-wrap {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(15, 18, 25, 0.75);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 3px 4px 3px 10px;
    margin-left: auto;
  }}
  .theme-toggle-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
  }}
  .theme-toggle-pills {{
    display: inline-flex;
    gap: 2px;
    background: rgba(0, 0, 0, 0.35);
    border-radius: 999px;
    padding: 2px;
  }}
  .theme-pill-btn {{
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
  }}
  .theme-pill-btn:hover {{
    color: #fff;
  }}
  .theme-pill-btn.active {{
    background: #f4f5f8;
    color: #0c0e14;
    font-weight: 700;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3);
  }}
  [data-theme="classic"] .theme-pill-btn.active {{
    background: var(--accent);
    color: #0c0e14;
  }}
  [data-theme="anime"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ff4b93 0%, #a855f7 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(255, 75, 147, 0.5);
  }}

  /* Indie Guide Aesthetic */
  [data-theme="indie"] .chip-icon,
  [data-theme="indie"] .live-pulse {{
    display: none !important;
  }}
  [data-theme="indie"] .banner {{
    background-color: #0b0d11;
    background-image:
      linear-gradient(180deg, rgba(11, 13, 17, 0.35) 0%, rgba(11, 13, 17, 0.82) 60%, rgba(11, 13, 17, 0.98) 100%),
      url('banner.jpg');
    min-height: 250px;
    padding: 34px 24px 26px;
  }}
  [data-theme="indie"] .banner-top-tag {{
    color: #cbd5e1;
    font-size: 11px;
    letter-spacing: 0.16em;
    font-weight: 650;
    text-shadow: none;
  }}
  [data-theme="indie"] .banner-title {{
    font-size: 42px;
    letter-spacing: -0.04em;
    font-weight: 850;
  }}
  [data-theme="indie"] .banner-meta-pill {{
    background: rgba(18, 21, 28, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 6px 14px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
  }}
  [data-theme="indie"] .pill-submit-btn {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #f4f5f8;
    box-shadow: none;
    border-radius: 6px;
    font-weight: 600;
    padding: 4px 11px;
  }}
  [data-theme="indie"] .pill-submit-btn:hover {{
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.35);
    transform: none;
    filter: none;
    box-shadow: none;
  }}
  [data-theme="indie"] .chip,
  [data-theme="indie"] .loc-chip,
  [data-theme="indie"] .genre-chip,
  [data-theme="indie"] .transit-chip,
  [data-theme="indie"] .sub-chip {{
    border-radius: 6px;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.01em;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    padding: 6px 13px;
  }}
  [data-theme="indie"] .chip.active,
  [data-theme="indie"] .loc-chip.active,
  [data-theme="indie"] .genre-chip.active,
  [data-theme="indie"] .sub-chip.active {{
    background: rgba(226, 168, 90, 0.14);
    border-color: #e2a85a;
    color: #f6c888;
    font-weight: 600;
  }}
  [data-theme="indie"] .chip:hover,
  [data-theme="indie"] .loc-chip:hover,
  [data-theme="indie"] .genre-chip:hover,
  [data-theme="indie"] .transit-chip:hover,
  [data-theme="indie"] .sub-chip:hover {{
    background: rgba(255, 255, 255, 0.07);
    border-color: rgba(255, 255, 255, 0.18);
    color: #fff;
  }}
  [data-theme="indie"] .day {{
    border-radius: 8px;
    padding: 16px 18px 14px;
    background: var(--card);
  }}
  [data-theme="indie"] .day h2 {{
    font-size: 16px;
    font-weight: 700;
    letter-spacing: -0.01em;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}
  [data-theme="indie"] .event {{
    padding: 9px 12px;
    border-radius: 4px;
    background: transparent;
    border: 1px solid transparent;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    margin-bottom: 2px;
  }}
  [data-theme="indie"] .event:hover {{
    background: rgba(255, 255, 255, 0.035);
    border-color: rgba(255, 255, 255, 0.08);
    transform: none;
    box-shadow: none;
  }}
  [data-theme="indie"] .event .when {{
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    color: #9aa1b2;
    font-weight: 500;
  }}
  [data-theme="indie"] .event .what a {{
    color: #f4f5f8;
    font-weight: 600;
  }}
  [data-theme="indie"] .event .what a:hover {{
    color: #e2a85a;
    text-decoration: underline;
  }}
  [data-theme="indie"] .cat-pill {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border-radius: 3px;
    padding: 2px 6px;
    background: rgba(255, 255, 255, 0.05) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    color: #b5bcc9 !important;
  }}
  [data-theme="indie"] .cal-btn {{
    border-radius: 4px;
    font-size: 11px;
    padding: 1px 7px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: transparent;
    color: var(--muted);
  }}
  [data-theme="indie"] .cal-btn:hover {{
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    border-color: rgba(255, 255, 255, 0.25);
  }}
  [data-theme="indie"] .view-toggle {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    padding: 2px;
  }}
  [data-theme="indie"] .view-btn {{
    border-radius: 4px;
    font-size: 12px;
    font-weight: 500;
    padding: 5px 12px;
  }}
  [data-theme="indie"] .view-btn.active {{
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
    box-shadow: none;
  }}
  [data-theme="indie"] .share-filter-btn {{
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    font-size: 12px;
  }}
  [data-theme="indie"] .past-events-banner {{
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    box-shadow: none;
    color: var(--muted);
  }}
  [data-theme="indie"] .past-banner-badge {{
    background: rgba(255, 255, 255, 0.08);
    color: #e2a85a;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    border-radius: 3px;
    padding: 2px 7px;
  }}
  [data-theme="indie"] .past-banner-btn {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 4px;
    color: #eef1f8;
    font-weight: 500;
  }}
  [data-theme="indie"] .past-banner-btn:hover {{
    background: rgba(255, 255, 255, 0.12);
  }}
  .indie-jump-label {{
    display: none;
  }}
  [data-theme="indie"] .indie-jump-label {{
    display: inline-block;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    padding: 1px 5px;
    line-height: 1.2;
    vertical-align: middle;
  }}
  [data-theme="indie"] .venue-map-jump:hover .indie-jump-label {{
    color: #fff;
    border-color: rgba(255, 255, 255, 0.3);
  }}

  /* Anime / Neo-Tokyo Aesthetic */
  [data-theme="anime"] .banner {{
    background-color: #110d28;
    background-image:
      linear-gradient(180deg, rgba(30, 15, 60, 0.45) 0%, rgba(18, 12, 40, 0.78) 58%, rgba(13, 10, 28, 0.98) 100%),
      url('banner.jpg');
    border-bottom: 2px solid rgba(255, 75, 147, 0.3);
    box-shadow: 0 4px 30px rgba(168, 85, 247, 0.18);
  }}
  [data-theme="anime"] .banner-top-tag {{
    color: #00f0ff;
    text-shadow: 0 0 12px rgba(0, 240, 255, 0.7);
    letter-spacing: 0.18em;
    font-weight: 700;
  }}
  [data-theme="anime"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #ff79c6 60%, #00f0ff 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 25px rgba(255, 75, 147, 0.35));
    letter-spacing: -0.02em;
  }}
  [data-theme="anime"] .banner-meta-pill {{
    background: rgba(28, 20, 56, 0.85);
    border: 1px solid rgba(255, 107, 181, 0.35);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4), 0 0 18px rgba(255, 75, 147, 0.22);
    border-radius: 999px;
  }}
  [data-theme="anime"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ff4b93 0%, #9333ea 100%);
    border: 1px solid rgba(255, 255, 255, 0.3);
    color: #fff;
    box-shadow: 0 0 12px rgba(255, 75, 147, 0.45);
    font-weight: 700;
    border-radius: 999px;
  }}
  [data-theme="anime"] .pill-submit-btn:hover {{
    filter: brightness(1.2);
    box-shadow: 0 0 20px rgba(255, 75, 147, 0.7);
    transform: translateY(-1px) scale(1.02);
  }}
  [data-theme="anime"] .live-pulse {{
    background: #00f0ff;
    box-shadow: 0 0 10px #00f0ff, 0 0 20px #00f0ff;
  }}
  [data-theme="anime"] .chip,
  [data-theme="anime"] .loc-chip,
  [data-theme="anime"] .genre-chip,
  [data-theme="anime"] .transit-chip,
  [data-theme="anime"] .sub-chip {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.22);
    color: #d1c7e8;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="anime"] .chip:hover,
  [data-theme="anime"] .loc-chip:hover,
  [data-theme="anime"] .genre-chip:hover,
  [data-theme="anime"] .transit-chip:hover,
  [data-theme="anime"] .sub-chip:hover {{
    border-color: #00f0ff;
    color: #fff;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.4);
    transform: translateY(-2px);
  }}
  [data-theme="anime"] .chip.active,
  [data-theme="anime"] .loc-chip.active,
  [data-theme="anime"] .genre-chip.active,
  [data-theme="anime"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(255, 75, 147, 0.3) 0%, rgba(168, 85, 247, 0.3) 100%);
    border-color: #ff4b93;
    color: #fff;
    box-shadow: 0 0 14px rgba(255, 75, 147, 0.4);
    font-weight: 700;
  }}
  [data-theme="anime"] .day {{
    background: rgba(23, 18, 46, 0.7);
    border: 1px solid rgba(255, 107, 181, 0.18);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    border-radius: var(--radius-lg);
  }}
  [data-theme="anime"] .day h2 {{
    color: #fce7f3;
    border-bottom: 1px solid rgba(255, 107, 181, 0.18);
  }}
  [data-theme="anime"] .day h2 .count {{
    background: rgba(255, 75, 147, 0.2);
    border: 1px solid rgba(255, 75, 147, 0.45);
    color: #ff85be;
    border-radius: 999px;
  }}
  [data-theme="anime"] .event {{
    background: rgba(30, 24, 62, 0.55);
    border: 1px solid rgba(255, 107, 181, 0.15);
    border-radius: var(--radius-md);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}
  [data-theme="anime"] .event:hover {{
    background: rgba(42, 34, 88, 0.85);
    border-color: rgba(255, 75, 147, 0.5);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35), 0 0 14px rgba(255, 75, 147, 0.3);
    transform: translateY(-2px);
  }}
  [data-theme="anime"] .event .what a {{
    color: #f5f0ff;
  }}
  [data-theme="anime"] .event .what a:hover {{
    color: #00f0ff;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }}
  [data-theme="anime"] .cat-pill {{
    border-radius: 999px;
    font-weight: 700;
    box-shadow: 0 0 8px rgba(0, 0, 0, 0.2);
  }}
  [data-theme="anime"] .star-btn:hover,
  [data-theme="anime"] .star-btn.starred {{
    color: #ff4b93;
    text-shadow: 0 0 12px rgba(255, 75, 147, 0.8);
  }}
  [data-theme="anime"] .view-toggle {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.25);
    padding: 3px;
  }}
  [data-theme="anime"] .view-btn {{
    border-radius: 999px;
  }}
  [data-theme="anime"] .view-btn.active {{
    background: linear-gradient(135deg, #ff4b93 0%, #9333ea 100%);
    color: #fff;
    box-shadow: 0 0 12px rgba(255, 75, 147, 0.45);
  }}
  [data-theme="anime"] .share-filter-btn {{
    border-radius: 999px;
    background: rgba(30, 22, 60, 0.65);
    border: 1px solid rgba(255, 107, 181, 0.25);
  }}
  [data-theme="anime"] .share-filter-btn:hover {{
    border-color: #00f0ff;
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.4);
    color: #00f0ff;
  }}
</style>
</head>
<body>
  <div class="banner">
    <div class="banner-inner">
      <div class="banner-top-row">
        <div class="banner-top-tag"><span class="live-pulse"></span> GREATER BOSTON LIVE EVENTS</div>
        <div class="theme-toggle-wrap">
          <span class="theme-toggle-label">Theme:</span>
          <div class="theme-toggle-pills" role="radiogroup" aria-label="Visual Theme">
            <button type="button" class="theme-pill-btn active" data-theme="indie" role="radio" aria-checked="true">Indie Guide</button>
            <button type="button" class="theme-pill-btn" data-theme="classic" role="radio" aria-checked="false">Classic Dark</button>
            <button type="button" class="theme-pill-btn" data-theme="anime" role="radio" aria-checked="false">Anime 🌸</button>
          </div>
        </div>
      </div>
      <div class="banner-title-row">
        <h1 class="banner-title">Wicked Boston Events</h1>
      </div>
      <div class="banner-meta-pill">
        {weather_pill_html}
        <span class="pill-stat"><strong>{total:,}</strong> events · <strong>{len(results)}</strong> venues</span>
        <span class="pill-dot">·</span>
        <button type="button" class="pill-submit-btn" id="btn-open-submit-modal" aria-haspopup="dialog" aria-expanded="false">
          <span>＋ Add Event</span>
        </button>
      </div>
    </div>
  </div>
  {fail_banner}
  {other_note}
  <div class="layout">
    <div class="mobile-filter-bar">
      <button type="button" id="mobile-filter-toggle" class="mobile-filter-btn">
        <span><span class="chip-icon">⚙️ </span>Filter</span>
        <span id="mobile-filter-badge" class="count">All</span>
      </button>
    </div>
    <aside class="filters" id="sidebar-filters">
      <button type="button" id="mobile-filter-close" class="mobile-filter-close">✕ Done Filtering</button>
      <div id="reset-filters-bar" class="reset-filters-bar" style="display: none;">
        <button type="button" id="btn-reset-filters" class="btn-reset-filters">↺ Reset All Filters</button>
      </div>
      <div class="filter-group">
        <h3>Search</h3>
        <div class="search-input-wrap">
          <input type="text" id="search-input" placeholder="Search events, venues, bands…" autocomplete="off">
          <span class="search-kbd" id="search-kbd" title="Press / or Cmd+K to search">/</span>
          <button type="button" id="search-clear" class="search-clear-btn" aria-label="Clear search" hidden>×</button>
        </div>
        <div id="search-status" class="search-status" hidden>
          <span id="search-count">0</span> events found
        </div>
      </div>
      <div class="filter-group">
        <label class="free-toggle" for="free-only-chk">
          <input type="checkbox" id="free-only-chk">
          <span><span class="chip-icon">✨ </span>Free events only</span>
        </label>
      </div>
      <div class="filter-group">
        <h3>Time of Day</h3>
        <div class="chk-grid">
          <label class="chk">
            <input type="radio" name="tod-filter" class="tod-radio" value="all" checked>
            <span>All times</span>
          </label>
          <label class="chk">
            <input type="radio" name="tod-filter" class="tod-radio" value="day">
            <span>Daytime (&lt; 5 PM)</span>
          </label>
          <label class="chk">
            <input type="radio" name="tod-filter" class="tod-radio" value="night">
            <span>Evening (5 PM+)</span>
          </label>
        </div>
      </div>
      <div class="filter-group">
        <h3>Category <span class="spacer"></span> <button type="button" id="cat-all">all</button> <button type="button" id="cat-none">none</button></h3>
        <div class="chk-grid">{bucket_boxes}</div>
      </div>
      <div class="filter-group" id="filter-group-genre">
        <h3>Music Genre <span class="spacer"></span> <button type="button" id="genre-all">all</button> <button type="button" id="genre-none">none</button></h3>
        <div class="chk-grid">{genre_boxes}</div>
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
        <h3>Venue <span id="venue-filter-count" class="filter-badge" style="display:none;"></span><span class="spacer"></span> <button type="button" id="venue-all">all</button> <button type="button" id="venue-none">none</button></h3>
        <div class="chk-grid">{venue_boxes}</div>
      </div>
    </aside>
    <main>
      <div class="view-switch-bar">
        <div class="view-toggle" role="group" aria-label="View mode">
          <button type="button" class="view-btn active" id="btn-view-list" data-view="list">
            <span><span class="chip-icon">📋 </span>List View</span>
          </button>
          <button type="button" class="view-btn" id="btn-view-map" data-view="map">
            <span><span class="chip-icon">🗺️ </span>Map View</span>
          </button>
        </div>
        <div class="view-switch-right">
          <button type="button" id="btn-share-filter" class="share-filter-btn" title="Copy shareable link with current filters">
            <span class="chip-icon">🔗 </span><span id="share-btn-text">Share View</span>
          </button>
          <span id="map-venue-stat" class="map-venue-stat" style="display: none;">
            <strong id="map-venue-count">0</strong> venues on map
          </span>
        </div>
      </div>
      <div class="location-chips-bar" id="location-chips">
        <button type="button" class="loc-chip active" data-city="all"><span class="chip-icon">📍 </span>All Areas</button>
        <button type="button" class="loc-chip" data-city="boston"><span class="city-dot" style="background:#5d9bff"></span>Boston</button>
        <button type="button" class="loc-chip" data-city="cambridge"><span class="city-dot" style="background:#e05a6b"></span>Cambridge</button>
        <button type="button" class="loc-chip" data-city="somerville"><span class="city-dot" style="background:#f29e4c"></span>Somerville</button>
        <button type="button" class="loc-chip" data-city="other"><span class="city-dot" style="background:#9aa3b2"></span>Greater Boston</button>
        <span class="transit-sep" aria-hidden="true"></span>
        <button type="button" class="transit-chip" data-transit="red" title="MBTA Red Line (Harvard, Central, Kendall, Porter, Davis, Downtown, Dorchester)"><span class="t-dot" style="background:#da291c"></span>Red Line</button>
        <button type="button" class="transit-chip" data-transit="green" title="MBTA Green Line (Back Bay, Fenway, Allston, Brookline, Union Sq, Inman, Medford)"><span class="t-dot" style="background:#00843d"></span>Green Line</button>
        <button type="button" class="transit-chip" data-transit="orange" title="MBTA Orange Line (South End, Back Bay, Jamaica Plain, Roxbury, Assembly, Charlestown)"><span class="t-dot" style="background:#ed8b00"></span>Orange Line</button>
        <button type="button" class="transit-chip" data-transit="blue" title="MBTA Blue Line (East Boston, Waterfront, Aquarium)"><span class="t-dot" style="background:#003da5"></span>Blue Line</button>
      </div>
      <div class="subarea-chips-bar" id="subarea-chips-bar" style="display: none;"></div>
      <div class="genre-chips-bar" id="genre-chips-bar">
        <button type="button" class="genre-chip active" data-genre="all"><span class="chip-icon">♪ </span>All Music</button>
        <button type="button" class="genre-chip" data-genre="rock_indie"><span class="chip-icon">🎸 </span>Rock &amp; Indie</button>
        <button type="button" class="genre-chip" data-genre="jazz_blues"><span class="chip-icon">🎷 </span>Jazz &amp; Blues</button>
        <button type="button" class="genre-chip" data-genre="folk_trad"><span class="chip-icon">🪕 </span>Folk &amp; Trad</button>
        <button type="button" class="genre-chip" data-genre="electronic"><span class="chip-icon">🎛 </span>Electronic</button>
        <button type="button" class="genre-chip" data-genre="classical"><span class="chip-icon">🎻 </span>Classical</button>
        <button type="button" class="genre-chip" data-genre="hiphop_rnb"><span class="chip-icon">🎤 </span>Hip-Hop &amp; R&B</button>
        <button type="button" class="genre-chip" data-genre="latin_global"><span class="chip-icon">🪇 </span>Latin &amp; Global</button>
        <button type="button" class="genre-chip" data-genre="pop"><span class="chip-icon">✨ </span>Pop</button>
      </div>
      <div class="quick-chips-bar" id="quick-chips">
        <button type="button" class="chip active" data-time="today"><span class="chip-icon">⚡ </span>Today</button>
        <button type="button" class="chip" data-time="tomorrow">Tomorrow</button>
        <button type="button" class="chip" data-time="weekend"><span class="chip-icon">🎉 </span>This Weekend</button>
        <button type="button" class="chip" data-time="week"><span class="chip-icon">📅 </span>Next 7 Days</button>
        <button type="button" class="chip" data-time="all">All Upcoming</button>
        <button type="button" class="chip chip-starred" id="quick-starred-chip" title="Filter to your saved events"><span class="chip-icon">⭐ </span>Saved <span id="starred-count" style="display:none;">(0)</span></button>
        <button type="button" class="chip chip-copy-plan" id="btn-copy-plan" style="display:none;" title="Copy your saved events as a shareable text itinerary"><span class="chip-icon">📋 </span>Copy Plan</button>
      </div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous">← prev</button>
        <span id="week-label">Today, {today.strftime("%b %d")}</span>
        <button type="button" id="week-next" aria-label="Next">next →</button>
        <button type="button" id="week-today">today</button>
        <button type="button" id="week-all" data-mode="week">show all</button>
        <button type="button" id="cal-toggle" aria-expanded="false"><span class="chip-icon">📅 </span>pick date</button>
      </div>
      <div class="mini-cal" id="mini-cal" hidden>
        <div class="mini-cal-head">
          <button type="button" id="cal-prev-month" aria-label="Previous month">‹</button>
          <span id="cal-month-label"></span>
          <button type="button" id="cal-next-month" aria-label="Next month">›</button>
        </div>
        <div class="mini-cal-grid" id="mini-cal-grid"></div>
      </div>
      <div id="map-view-wrapper" class="map-view-wrapper" style="display: none;">
        <div class="map-header">
          <div class="map-header-title">
            <span class="live-pulse"></span>
            <strong>Greater Boston Live Map</strong>
            <span class="map-hint">· OpenStreetMap · Pins update with your date &amp; filters</span>
          </div>
          <div class="map-header-actions">
            <button type="button" id="map-label-toggle-btn" class="map-tool-btn" title="Toggle between venue names and numbers only"><span class="chip-icon">🏷️ </span>Names: On</button>
            <button type="button" id="map-recenter-btn" class="map-tool-btn" title="Center map on Boston"><span class="chip-icon">🎯 </span>Center Boston</button>
          </div>
        </div>
        <div id="leaflet-map" class="leaflet-map"></div>
        <div id="map-selected-venue" class="map-venue-card" style="display: none;">
          <div class="map-venue-card-head">
            <div>
              <h3 id="panel-venue-name"></h3>
              <p id="panel-venue-sub" class="panel-sub"></p>
            </div>
            <button type="button" id="panel-close-btn" class="panel-close" aria-label="Close panel">✕</button>
          </div>
          <ul id="panel-events-list" class="panel-events"></ul>
        </div>
      </div>
      <div id="no-events-msg" class="no-events-msg" style="display: none;">
        <p>No events found for this selection.</p>
        <div style="display:flex; justify-content:center; gap:8px; flex-wrap:wrap;">
          <button type="button" class="chip" id="no-events-week-btn"><span class="chip-icon">📅 </span>View Next 7 Days</button>
          <button type="button" class="chip" id="no-events-all-btn">All Upcoming</button>
          <button type="button" class="chip" id="no-events-reset-btn" style="display: none;"><span class="chip-icon">↺ </span>Reset All Filters</button>
        </div>
      </div>
      {"".join(initial_sections)}
      <template id="deferred-days">
      {"".join(deferred_sections)}
      </template>
      <div class="week-nav bottom">
        <button type="button" id="week-prev-b" aria-label="Previous week">← prev</button>
        <span id="week-label-b"></span>
        <button type="button" id="week-next-b" aria-label="Next week">next →</button>
      </div>
      {ongoing_section}
    </main>
    {useful_sidebar}
  </div>
  <footer>
    <p>Boston Events · Live local music, comedy, arts, outdoors &amp; community events across Greater Boston.</p>
    <p style="margin-top:6px; font-size:11px; opacity:0.85;">Data compiled directly from venue calendars and official local community feeds. Not affiliated with any commercial ticketing broker.</p>
  </footer>
  <!-- Community Event Submission Modal -->
  <div id="submit-event-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="modal-submit-title" style="display:none;">
    <div class="modal-card" id="submit-modal-card">
      <div class="modal-header">
        <div>
          <h2 class="modal-title" id="modal-submit-title">Add to Boston Events</h2>
          <p class="modal-sub" id="modal-submit-sub">Share an event or suggest a new venue / space for automatic tracking.</p>
        </div>
        <button type="button" class="modal-close-btn" id="btn-close-submit-modal" aria-label="Close modal">✕</button>
      </div>

      <div class="modal-tabs" role="tablist">
        <button type="button" class="modal-tab active" id="tab-btn-event" role="tab" aria-selected="true">
          <span>📅</span> Add an Event
        </button>
        <button type="button" class="modal-tab" id="tab-btn-venue" role="tab" aria-selected="false">
          <span>📍</span> Suggest a Venue
        </button>
      </div>

      <!-- Tab 1: Submit an Event Form -->
      <div id="modal-view-event">
        <form id="community-event-form" class="modal-form" novalidate>
          <!-- Anti-bot honeypot field (hidden from real users) -->
          <input type="text" name="_hp_company" class="hp-field" tabindex="-1" autocomplete="off" aria-hidden="true" style="display:none !important;">

          <div class="form-row">
            <label for="ev-title" class="form-label">
              Event Title <span class="req">*</span>
            </label>
            <input type="text" id="ev-title" name="name" class="form-input" placeholder="e.g., Live Jazz Trio, Somerville Flea, Salsa Night" required maxlength="150">
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-venue" class="form-label">
                Venue / Location <span class="req">*</span>
              </label>
              <input type="text" id="ev-venue" name="venue" class="form-input" placeholder="e.g., The Burren, 26 New St, Boston Common" required maxlength="150">
            </div>
            <div class="form-row">
              <label for="ev-city" class="form-label">
                City / Area <span class="req">*</span>
              </label>
              <select id="ev-city" name="city" class="form-select" required>
                <option value="boston" selected>Boston (incl. Allston, Brighton, South End, Seaport, Brookline)</option>
                <option value="cambridge">Cambridge (Harvard, Central, Kendall, Inman)</option>
                <option value="somerville">Somerville (Davis, Union, Assembly, Spring Hill)</option>
                <option value="other">Other / Greater Boston Suburbs</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <label for="ev-address" class="form-label">
              Street Address / Neighborhood <span class="hint">(optional, helps map accurately)</span>
            </label>
            <input type="text" id="ev-address" name="address" class="form-input" placeholder="e.g., 247 Elm St, Davis Square" maxlength="150">
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-date" class="form-label">
                Date <span class="req">*</span>
              </label>
              <input type="date" id="ev-date" name="date" class="form-input" required>
            </div>
            <div class="form-row">
              <label for="ev-time" class="form-label">
                Start Time <span class="hint">(optional)</span>
              </label>
              <input type="time" id="ev-time" name="time" class="form-input" value="19:00">
            </div>
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="ev-category" class="form-label">
                Category <span class="req">*</span>
              </label>
              <select id="ev-category" name="category" class="form-select" required>
                <option value="music">🎵 Music / Concert</option>
                <option value="comedy">🎙️ Comedy</option>
                <option value="dance">💃 Dance / Social</option>
                <option value="theater">🎭 Stage &amp; Theater</option>
                <option value="art">🎨 Art &amp; Gallery</option>
                <option value="food">🍷 Food &amp; Drink</option>
                <option value="fitness">🏃 Fitness &amp; Outdoors</option>
                <option value="books">📚 Books &amp; Talks</option>
                <option value="gaming">🎲 Trivia &amp; Games</option>
                <option value="community">🤝 Community &amp; Markets</option>
                <option value="clubbing">🪩 Clubbing &amp; DJ</option>
                <option value="other" selected>✨ Other</option>
              </select>
            </div>
            <div class="form-row">
              <label for="ev-price" class="form-label">
                Price <span class="hint">(e.g., Free, $15, $20-$30)</span>
              </label>
              <div class="price-input-row">
                <input type="text" id="ev-price" name="price" class="form-input" placeholder="e.g., Free or $15">
                <button type="button" id="btn-quick-free" class="btn-pill-free">✨ Free</button>
              </div>
            </div>
          </div>

          <div class="form-row">
            <label for="ev-url" class="form-label">
              Event Website / Ticket URL <span class="req">*</span>
            </label>
            <input type="url" id="ev-url" name="url" class="form-input" placeholder="https://..." required>
          </div>

          <div class="form-row">
            <label for="ev-desc" class="form-label">
              Short Description / Notes <span class="hint">(optional)</span>
            </label>
            <textarea id="ev-desc" name="description" class="form-textarea" rows="2" placeholder="Brief note about the performers, dress code, RSVP details..." maxlength="400"></textarea>
          </div>

          <div class="form-status" id="form-submit-status" style="display:none;"></div>

          <div class="form-actions">
            <button type="button" class="btn-cancel" id="btn-cancel-submit">Cancel</button>
            <button type="submit" class="btn-primary-submit" id="btn-submit-action">
              <span class="btn-text">Publish Event ↗</span>
              <span class="btn-spinner" style="display:none;">⏳ Adding...</span>
            </button>
          </div>

          <div class="form-footer-note">
            <span>🛡️ Submissions are instantly verified and added to the live schedule.</span>
          </div>
        </form>
      </div>

      <!-- Tab 2: Suggest a Venue Form -->
      <div id="modal-view-venue" style="display:none;">
        <form id="suggest-venue-form" class="modal-form" novalidate>
          <input type="text" name="_hp_company" class="hp-field" tabindex="-1" autocomplete="off" aria-hidden="true" style="display:none !important;">

          <div class="form-row">
            <label for="vn-name" class="form-label">
              Venue / Space Name <span class="req">*</span>
            </label>
            <input type="text" id="vn-name" name="name" class="form-input" placeholder="e.g., The Burren, Lilypad, Faces Brewing" required maxlength="150">
          </div>

          <div class="form-row">
            <label for="vn-url" class="form-label">
              Venue Website or Calendar Page <span class="req">*</span>
            </label>
            <input type="url" id="vn-url" name="url" class="form-input" placeholder="https://..." required>
          </div>

          <div class="form-grid-2">
            <div class="form-row">
              <label for="vn-city" class="form-label">
                City / Area <span class="req">*</span>
              </label>
              <select id="vn-city" name="city" class="form-select" required>
                <option value="boston" selected>Boston (Allston, Brighton, South End, Seaport, Brookline)</option>
                <option value="cambridge">Cambridge (Harvard, Central, Kendall, Inman)</option>
                <option value="somerville">Somerville (Davis, Union, Assembly, Spring Hill)</option>
                <option value="other">Other / Greater Boston Suburbs</option>
              </select>
            </div>
            <div class="form-row">
              <label for="vn-category" class="form-label">
                Primary Genre / Type
              </label>
              <select id="vn-category" name="category" class="form-select">
                <option value="music" selected>🎵 Live Music &amp; Concerts</option>
                <option value="comedy">🎙️ Comedy</option>
                <option value="theater">🎭 Stage &amp; Theater</option>
                <option value="dance">💃 Dance / Social</option>
                <option value="food">🍺 Brewery / Bar / Food</option>
                <option value="books">📚 Books &amp; Talks</option>
                <option value="art">🎨 Gallery &amp; Art Space</option>
                <option value="clubbing">🪩 Clubbing &amp; DJ</option>
                <option value="community">🤝 Community &amp; Pop-up</option>
                <option value="other">✨ Other</option>
              </select>
            </div>
          </div>

          <div class="form-row">
            <label for="vn-address" class="form-label">
              Address / Neighborhood <span class="hint">(optional)</span>
            </label>
            <input type="text" id="vn-address" name="address" class="form-input" placeholder="e.g., 247 Elm St, Davis Square, Somerville" maxlength="150">
          </div>

          <div class="form-row">
            <label for="vn-notes" class="form-label">
              Notes / Events to Scrape <span class="hint">(optional)</span>
            </label>
            <textarea id="vn-notes" name="notes" class="form-textarea" rows="2" placeholder="e.g., Live traditional sessions every Wednesday and jazz on weekends..." maxlength="400"></textarea>
          </div>

          <div class="form-status" id="form-venue-status" style="display:none;"></div>

          <div class="form-actions">
            <button type="button" class="btn-cancel" id="btn-cancel-venue">Cancel</button>
            <button type="submit" class="btn-primary-submit" id="btn-submit-venue">
              <span class="btn-text">Submit Suggestion ↗</span>
              <span class="btn-spinner" style="display:none;">⏳ Submitting...</span>
            </button>
          </div>

          <div class="form-footer-note">
            <span>💡 Suggested venues are reviewed and plugged into our automated 30-minute scrapers!</span>
          </div>
        </form>
      </div>
    </div>
  </div>

  <script>
    const catBoxes = document.querySelectorAll('.cat-chk');
    const genreBoxes = document.querySelectorAll('.genre-chk');
    const venueBoxes = document.querySelectorAll('.venue-chk');
    const recurBoxes = document.querySelectorAll('.recur-chk');
    const cityBoxes = document.querySelectorAll('.city-chk');
    const searchInput = document.getElementById('search-input');
    const searchKbd = document.getElementById('search-kbd');
    const searchClear = document.getElementById('search-clear');
    const searchStatus = document.getElementById('search-status');
    const searchCount = document.getElementById('search-count');
    const freeOnlyChk = document.getElementById('free-only-chk');

    const locChips = document.querySelectorAll('#location-chips .loc-chip');
    const transitChips = document.querySelectorAll('#location-chips .transit-chip');
    const subareaBar = document.getElementById('subarea-chips-bar');
    const genreChips = document.querySelectorAll('#genre-chips-bar .genre-chip');
    let activeGenre = 'all';
    let activeTransit = 'all';
    let activeTod = 'all';
    let starredOnly = false;
    let starredEvents = new Set();
    const SUBAREAS_DATA = {json.dumps(SUBAREAS_BY_CITY)};
    const CITY_LABELS_MAP = {json.dumps(CITY_LABELS)};
    let activeSubarea = 'all';
    let renderedSubareaCity = null;
    const quickChips = document.querySelectorAll('#quick-chips .chip[data-time]');
    const todRadios = document.querySelectorAll('.tod-radio');
    const quickPopularChip = document.getElementById('quick-popular-chip');
    const quickStarredChip = document.getElementById('quick-starred-chip');
    const starredCountEl = document.getElementById('starred-count');
    const btnCopyPlan = document.getElementById('btn-copy-plan');
    let popularOnly = false;
    let userUpvotes = new Set();
    let cachedVotes = {{}};
    let timeFilter = 'today';
    let currentView = 'list';
    let showPastToday = false;
    let leafletMap = null;
    let markersLayer = null;
    let mapLoading = false;

    const mobileToggle = document.getElementById('mobile-filter-toggle');
    const mobileClose = document.getElementById('mobile-filter-close');
    const sidebarFilters = document.getElementById('sidebar-filters');
    const mobileBadge = document.getElementById('mobile-filter-badge');

    let daySections = Array.from(document.querySelectorAll('.day[data-date]'));
    const ALL_EVENT_DATES = {json.dumps(all_event_dates)};
    const eventDates = new Set(ALL_EVENT_DATES);

    let deferredHydrated = false;
    function ensureDeferredDaysHydrated() {{
      if (deferredHydrated) return;
      deferredHydrated = true;
      const tmpl = document.getElementById('deferred-days');
      if (!tmpl) return;
      const bottomNav = document.querySelector('.week-nav.bottom');
      if (bottomNav && bottomNav.parentNode) {{
        bottomNav.parentNode.insertBefore(tmpl.content, bottomNav);
      }}
      tmpl.remove();
      daySections = Array.from(document.querySelectorAll('.day[data-date]'));
      updateDayHeadings();
      syncInitialUpvotes();
      loadStarredState();
    }}
    function parseISO(s) {{ const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); }}
    function fmtISO(d) {{
      const y = d.getFullYear(), m = String(d.getMonth() + 1).padStart(2, '0'), da = String(d.getDate()).padStart(2, '0');
      return `${{y}}-${{m}}-${{da}}`;
    }}
    function addDays(d, n) {{ const c = new Date(d); c.setDate(c.getDate() + n); return c; }}
    const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    const DAYS_FULL = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    function fmtShort(d) {{ return MONTHS[d.getMonth()] + ' ' + d.getDate(); }}
    function fmtMonth(d) {{ return d.toLocaleString('en-US', {{ month: 'long', year: 'numeric' }}); }}

    function getEasternTodayISO() {{
      try {{
        const formatter = new Intl.DateTimeFormat('en-CA', {{
          timeZone: 'America/New_York',
          year: 'numeric',
          month: '2-digit',
          day: '2-digit'
        }});
        return formatter.format(new Date());
      }} catch (e) {{
        return "{today_iso}";
      }}
    }}

    let todayISO = getEasternTodayISO();
    let anchor = parseISO(todayISO);
    let showAll = false;
    let calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);

    function updateDayHeadings() {{
      const tDate = parseISO(todayISO);
      daySections.forEach(day => {{
        const dStr = day.dataset.date;
        if (!dStr || dStr === 'tba') return;
        const dObj = parseISO(dStr);
        const diffDays = Math.round((dObj - tDate) / 86400000);
        const h2 = day.querySelector('h2');
        if (!h2) return;
        const countSpan = h2.querySelector('.count');
        const countHtml = countSpan ? countSpan.outerHTML : '';
        const dayName = DAYS_FULL[dObj.getDay()];
        const shortStr = `${{MONTHS[dObj.getMonth()]}} ${{dObj.getDate()}}`;
        let prefix = dayName;
        if (diffDays === 0) {{
          prefix = 'Today';
        }} else if (diffDays === 1) {{
          prefix = 'Tomorrow';
        }} else if (diffDays === -1) {{
          prefix = 'Yesterday';
        }}
        h2.innerHTML = `${{prefix}} · ${{dayName}}, ${{shortStr}}${{countHtml}}`;
      }});
    }}

    function repositionPastBanner() {{
      let pastBanner = document.getElementById('past-events-banner');
      const todaySec = document.querySelector(`.day[data-date="${{todayISO}}"]`);
      if (!todaySec) return;
      const h2 = todaySec.querySelector('h2');
      if (!h2) return;
      if (!pastBanner) {{
        pastBanner = document.createElement('div');
        pastBanner.className = 'past-events-banner';
        pastBanner.id = 'past-events-banner';
        pastBanner.style.display = 'none';
        pastBanner.innerHTML = `
          <div class="past-banner-info">
            <span class="past-banner-badge" id="past-banner-badge">⏱️ Live Tonight</span>
            <span class="past-banner-text" id="past-banner-text"></span>
          </div>
          <div class="past-banner-actions">
            <button type="button" class="past-banner-btn" id="btn-toggle-past">Show earlier today</button>
            <button type="button" class="past-banner-btn btn-tomorrow" id="btn-banner-tomorrow" style="display: none;">See Tomorrow →</button>
          </div>
        `;
        h2.insertAdjacentElement('afterend', pastBanner);
      }} else if (pastBanner.parentElement !== todaySec) {{
        h2.insertAdjacentElement('afterend', pastBanner);
      }}
    }}

    function msUntilEasternMidnight() {{
      try {{
        const now = new Date();
        const parts = new Intl.DateTimeFormat('en-US', {{
          timeZone: 'America/New_York',
          hour12: false,
          hour: 'numeric',
          minute: 'numeric',
          second: 'numeric'
        }}).formatToParts(now);
        const h = parseInt(parts.find(p => p.type === 'hour').value, 10) % 24;
        const m = parseInt(parts.find(p => p.type === 'minute').value, 10);
        const s = parseInt(parts.find(p => p.type === 'second').value, 10);
        const ms = now.getMilliseconds();
        const secondsPassed = h * 3600 + m * 60 + s;
        const secondsUntilMidnight = 86400 - secondsPassed;
        return Math.max(1000, (secondsUntilMidnight * 1000) - ms + 1000);
      }} catch (e) {{
        return 60000;
      }}
    }}

    function checkDayRollover() {{
      const currentEasternISO = getEasternTodayISO();
      if (currentEasternISO && currentEasternISO !== todayISO) {{
        const wasToday = (timeFilter === 'today');
        todayISO = currentEasternISO;
        if (wasToday) {{
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }}
        repositionPastBanner();
        updateDayHeadings();
        apply();
      }}
    }}

    function scheduleMidnightRefresh() {{
      const ms = msUntilEasternMidnight();
      setTimeout(() => {{
        checkDayRollover();
        scheduleMidnightRefresh();
      }}, Math.min(ms, 2147483647));
    }}

    function weekDates() {{
      const out = [];
      for (let i = 0; i < 7; i++) out.push(fmtISO(addDays(anchor, i)));
      return out;
    }}
    function updateWeekLabel() {{
      const end = addDays(anchor, 6);
      let label = '';
      if (timeFilter === 'all' || showAll) {{
        label = 'Showing all upcoming';
      }} else if (timeFilter === 'today') {{
        label = `Today, ${{fmtShort(anchor)}}`;
      }} else if (timeFilter === 'tomorrow') {{
        label = `Tomorrow, ${{fmtShort(anchor)}}`;
      }} else if (timeFilter === 'weekend') {{
        const todayDate = parseISO(todayISO);
        const dayOfWeek = todayDate.getDay();
        let daysToSat = (6 - dayOfWeek + 7) % 7;
        if (dayOfWeek === 0) daysToSat = -1;
        const sat = addDays(todayDate, daysToSat);
        const sun = addDays(sat, 1);
        label = `Weekend: ${{fmtShort(sat)}} – ${{fmtShort(sun)}}`;
      }} else if (timeFilter === 'day') {{
        label = `${{DAYS_FULL[anchor.getDay()]}}, ${{fmtShort(anchor)}}, ${{anchor.getFullYear()}}`;
      }} else {{
        label = `${{fmtShort(anchor)}} – ${{fmtShort(end)}}, ${{end.getFullYear()}}`;
      }}
      document.getElementById('week-label').textContent = label;
      const b = document.getElementById('week-label-b');
      if (b) b.textContent = label;
      const btn = document.getElementById('week-all');
      if (btn) {{
        btn.textContent = (timeFilter === 'all' || showAll) ? 'today view' : 'show all';
        btn.setAttribute('aria-pressed', (timeFilter === 'all' || showAll) ? 'true' : 'false');
      }}
    }}

    function escapeHTML(str) {{
      if (!str) return '';
      return String(str)
        .split('&').join('&amp;')
        .split('<').join('&lt;')
        .split('>').join('&gt;')
        .split('"').join('&quot;')
        .split("'").join('&#39;');
    }}

    function loadLeaflet(callback) {{
      if (window.L) {{ callback(); return; }}
      if (mapLoading) {{
        const interval = setInterval(() => {{
          if (window.L) {{ clearInterval(interval); callback(); }}
        }}, 50);
        return;
      }}
      mapLoading = true;
      const css = document.createElement('link');
      css.rel = 'stylesheet';
      css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
      document.head.appendChild(css);

      const script = document.createElement('script');
      script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
      script.onload = () => {{
        mapLoading = false;
        callback();
      }};
      document.head.appendChild(script);
    }}

    function initMap() {{
      if (leafletMap) return;
      const mapEl = document.getElementById('leaflet-map');
      if (!mapEl) return;

      leafletMap = L.map(mapEl, {{
        center: [42.3601, -71.0750],
        zoom: 13,
        minZoom: 10,
        maxZoom: 18,
      }});

      const hashParams = new URLSearchParams(location.search || location.hash.slice(1));
      const cartoKey = hashParams.get('carto_key') || window.CARTO_KEY;

      if (cartoKey) {{
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png?key=' + encodeURIComponent(cartoKey), {{
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> &copy; <a href="https://carto.com/" target="_blank" rel="noopener">CARTO</a>',
          subdomains: 'abcd',
          maxZoom: 19
        }}).addTo(leafletMap);
      }} else {{
        mapEl.classList.add('osm-dark-tiles');
        const osmUrl = (location.protocol === 'file:')
          ? 'https://tile.openstreetmap.de/{{z}}/{{x}}/{{y}}.png'
          : 'https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png';

        const tiles = L.tileLayer(osmUrl, {{
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
          maxZoom: 19
        }});

        tiles.on('tileerror', function(error) {{
          if (error.tile && error.tile.src && error.tile.src.includes('openstreetmap.org')) {{
            error.tile.src = error.tile.src.replace('tile.openstreetmap.org', 'tile.openstreetmap.de');
          }}
        }});

        tiles.addTo(leafletMap);
      }}

      markersLayer = L.layerGroup().addTo(leafletMap);
      updateMapMarkers();
    }}

    function switchView(mode) {{
      currentView = mode;
      const listBtn = document.getElementById('btn-view-list');
      const mapBtn = document.getElementById('btn-view-map');
      const mapWrapper = document.getElementById('map-view-wrapper');
      const mapStat = document.getElementById('map-venue-stat');

      if (listBtn) listBtn.classList.toggle('active', mode === 'list');
      if (mapBtn) mapBtn.classList.toggle('active', mode === 'map');
      if (mapWrapper) mapWrapper.style.display = (mode === 'map') ? 'flex' : 'none';
      if (mapStat) mapStat.style.display = (mode === 'map') ? 'inline-block' : 'none';

      if (mode === 'map') {{
        loadLeaflet(() => {{
          initMap();
          if (leafletMap) {{
            leafletMap.invalidateSize();
            updateMapMarkers();
          }}
        }});
      }}
      stateToHash();
    }}

    function shortenVenueName(name) {{
      if (!name) return '';
      const OVERRIDES = {{
        'Museum of Fine Arts (MFA)': 'MFA',
        'Harvard Museum of Natural History': 'Harvard Nat History',
        'Peabody Museum of Archaeology & Ethnology': 'Peabody Museum',
        'Boch Center (Wang & Shubert)': 'Boch Center',
        'Somerville Community Growing Center': 'Growing Center',
        'The Fenway (Time Out Market & 401 Park)': 'The Fenway',
        'Trident Booksellers & Cafe': 'Trident Books',
        'Crystal Ballroom at Somerville Theatre': 'Crystal Ballroom',
        'Emerson Paramount Center': 'Paramount',
        'Emerson Colonial Theatre': 'Colonial Theatre',
        'Citizens House of Blues': 'House of Blues',
        'Somerville Public Library': 'Somerville Library',
        'Cambridge Public Library': 'Cambridge Library',
        'Boston Public Library': 'BPL',
        'Charles River Speedway': 'Speedway',
        "McCarthy's Toad": 'Toad',
        'Versus Boston (via Eventbrite)': 'Versus',
        'Make Friends After College (via Eventbrite)': 'Make Friends',
        'Arts at the Armory': 'Armory',
        "Moves n' Vibes Dance and Entertainment Company": 'Moves & Vibes',
        'New England Conservatory': 'NEC',
        'Jordan Hall (NEC)': 'Jordan Hall',
        'Kings Dining & Entertainment (Seaport)': 'Kings Seaport',
        'The Jungle Community Music Club': 'The Jungle',
        'Boston Symphony Orchestra': 'BSO',
        'Central Square Farmers Market': 'Central Sq Market',
        'Copley Square Farmers Market': 'Copley Market',
        'Davis Square Farmers Market': 'Davis Sq Market',
        'Harvard University Farmers Market': 'Harvard Market',
      }};
      if (OVERRIDES[name]) return OVERRIDES[name];
      let s = name;
      s = s.replace(/\\s*\\((?:via\\s+[^)]+|Wang\\s*&.*|Time\\s*Out.*|NEC)\\)/gi, '');
      s = s.replace(/,?\\s*(?:Boston|Cambridge|Somerville|Brookline|Allston)$/gi, '');
      s = s.replace(/\\s+(?:Brewing(?:\\s+Co\\.?)?|Brewery|Booksellers(?:\\s*&\\s*Cafe)?|Music\\s+Hall|Jazz\\s+Club|Center\\s+for\\s+the\\s+Arts)$/gi, '');
      s = s.trim();
      if (s.length > 18 && s.startsWith('The ')) {{
        s = s.slice(4).trim();
      }}
      if (s.length > 18) {{
        s = s.slice(0, 16).trim() + '…';
      }}
      return s;
    }}

    function updateMapMarkers() {{
      if (!leafletMap || !markersLayer) return;
      markersLayer.clearLayers();

      const visibleDaySecs = daySections.filter(d => !d.classList.contains('out-of-week') && !d.classList.contains('empty'));
      const venueMap = new Map();

      visibleDaySecs.forEach(day => {{
        const dayDate = day.dataset.date;
        day.querySelectorAll('.event:not(.hidden)').forEach(li => {{
          const lat = parseFloat(li.dataset.lat);
          const lng = parseFloat(li.dataset.lng);
          if (isNaN(lat) || isNaN(lng)) return;

          const vName = li.dataset.venueName || li.dataset.venue || 'Venue';
          const key = `${{lat.toFixed(4)}},${{lng.toFixed(4)}}`;
          if (!venueMap.has(key)) {{
            venueMap.set(key, {{
              lat, lng,
              name: vName,
              neighborhood: li.dataset.neighborhood || li.dataset.subareaName || '',
              events: []
            }});
          }}

          const linkEl = li.querySelector('.what a');
          const title = linkEl ? linkEl.textContent.trim() : (li.querySelector('.what')?.textContent || '');
          const url = linkEl ? linkEl.getAttribute('href') : '';
          const when = li.querySelector('.when')?.textContent.trim() || '';
          const price = li.querySelector('.price')?.textContent.trim() || '';
          const isFree = li.dataset.free === 'true';

          venueMap.get(key).events.push({{
            title, url, when, price, isFree, date: dayDate
          }});
        }});
      }});

      const countBadge = document.getElementById('map-venue-count');
      if (countBadge) countBadge.textContent = venueMap.size;

      venueMap.forEach(v => {{
        const count = v.events.length;
        const shortName = shortenVenueName(v.name);
        const icon = L.divIcon({{
          className: 'custom-venue-icon',
          html: `<div class="venue-marker" title="${{escapeHTML(v.name)}} (${{count}} event${{count === 1 ? '' : 's'}})"><span class="pin-name">${{escapeHTML(shortName)}}</span><span class="pin-count">${{count}}</span></div>`,
          iconSize: null,
          iconAnchor: [0, 0],
        }});

        const marker = L.marker([v.lat, v.lng], {{ icon: icon }});

        let popupHtml = `<div class="map-popup">
          <div class="popup-head">
            <strong>${{escapeHTML(v.name)}}</strong>
            ${{v.neighborhood ? `<span class="popup-neighborhood">📍 ${{escapeHTML(v.neighborhood)}}</span>` : ''}}
          </div>
          <div class="popup-events">`;

        v.events.slice(0, 5).forEach(ev => {{
          popupHtml += `<div class="popup-event-item">
            <span class="popup-time">${{escapeHTML(ev.when)}}</span>
            <a href="${{escapeHTML(ev.url)}}" target="_blank" rel="noopener" class="popup-title">${{escapeHTML(ev.title)}}</a>
            ${{ev.price ? `<span class="popup-price ${{ev.isFree ? 'free' : ''}}">${{escapeHTML(ev.price)}}</span>` : ''}}
          </div>`;
        }});
        if (v.events.length > 5) {{
          popupHtml += `<div class="popup-more">+ ${{v.events.length - 5}} more events</div>`;
        }}
        const mapsQuery = encodeURIComponent(`${{v.name}}, Boston MA`);
        popupHtml += `</div>
          <div class="popup-foot">
            <a href="https://www.google.com/maps/search/?api=1&query=${{mapsQuery}}" target="_blank" rel="noopener" class="popup-dir-link">Google Maps Directions ↗</a>
          </div>
        </div>`;

        marker.bindPopup(popupHtml, {{ maxWidth: 300 }});
        marker.on('click', () => {{
          showVenuePanel(v);
        }});
        markersLayer.addLayer(marker);
      }});
    }}

    function showVenuePanel(v) {{
      const panel = document.getElementById('map-selected-venue');
      if (!panel) return;
      document.getElementById('panel-venue-name').textContent = v.name;
      document.getElementById('panel-venue-sub').textContent = v.neighborhood ? `📍 ${{v.neighborhood}} · ${{v.events.length}} event(s)` : `${{v.events.length}} event(s)`;

      const list = document.getElementById('panel-events-list');
      list.innerHTML = v.events.map(ev => `
        <li class="popup-event-item">
          <span class="popup-time">${{escapeHTML(ev.when)}}</span>
          <a href="${{escapeHTML(ev.url)}}" target="_blank" rel="noopener" class="popup-title">${{escapeHTML(ev.title)}}</a>
          ${{ev.price ? `<span class="popup-price ${{ev.isFree ? 'free' : ''}}">${{escapeHTML(ev.price)}}</span>` : ''}}
        </li>
      `).join('');
      panel.style.display = 'block';
    }}

    function updateQuickChipsUI() {{
      quickChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.time === timeFilter);
      }});
      todRadios.forEach(radio => {{
        radio.checked = (radio.value === activeTod);
      }});
      if (quickPopularChip) {{
        quickPopularChip.classList.toggle('active', popularOnly);
      }}
      if (quickStarredChip) {{
        quickStarredChip.classList.toggle('active', starredOnly);
      }}
      if (starredCountEl) {{
        const n = starredEvents.size;
        starredCountEl.textContent = `(${{n}})`;
        starredCountEl.style.display = n > 0 ? 'inline' : 'none';
      }}
      if (btnCopyPlan) {{
        btnCopyPlan.style.display = starredEvents.size > 0 ? 'inline-flex' : 'none';
      }}
    }}

    function renderSubareaChips(city) {{
      if (!subareaBar) return;
      if (!city || city === 'all' || !SUBAREAS_DATA[city]) {{
        subareaBar.style.display = 'none';
        subareaBar.innerHTML = '';
        renderedSubareaCity = null;
        activeSubarea = 'all';
        return;
      }}

      if (renderedSubareaCity === city) {{
        subareaBar.querySelectorAll('.sub-chip').forEach(b => {{
          b.classList.toggle('active', b.dataset.subarea === activeSubarea);
        }});
        return;
      }}

      renderedSubareaCity = city;
      const subs = SUBAREAS_DATA[city] || [];
      const cityLabel = (CITY_LABELS_MAP && CITY_LABELS_MAP[city]) || city;
      let html = `<button type="button" class="sub-chip ${{activeSubarea === 'all' ? 'active' : ''}}" data-subarea="all"><span class="chip-icon">📍 </span>All ${{cityLabel}}</button>`;
      subs.forEach(s => {{
        const slug = s[0];
        const name = s[1];
        const icon = s[2] || '📍';
        const isAct = (activeSubarea === slug);
        html += `<button type="button" class="sub-chip ${{isAct ? 'active' : ''}}" data-subarea="${{slug}}"><span class="chip-icon">${{icon}} </span>${{name}}</button>`;
      }});
      subareaBar.innerHTML = html;
      subareaBar.style.display = 'flex';

      subareaBar.querySelectorAll('.sub-chip').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const targetSub = btn.dataset.subarea;
          if (activeSubarea === targetSub && targetSub !== 'all') {{
            activeSubarea = 'all';
          }} else {{
            activeSubarea = targetSub;
          }}
          subareaBar.querySelectorAll('.sub-chip').forEach(b => {{
            b.classList.toggle('active', b.dataset.subarea === activeSubarea);
          }});
          apply();
        }});
      }});
    }}

    function updateLocChipsUI() {{
      const allCities = cityBoxes.length;
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      locChips.forEach(chip => {{
        const city = chip.dataset.city;
        if (city === 'all') {{
          chip.classList.toggle('active', (checkedCities.length === allCities || checkedCities.length === 0) && activeTransit === 'all');
        }} else {{
          chip.classList.toggle('active', checkedCities.length === 1 && checkedCities[0] === city);
        }}
      }});
      transitChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.transit === activeTransit);
      }});
      if (checkedCities.length === 1) {{
        renderSubareaChips(checkedCities[0]);
      }} else {{
        renderSubareaChips('all');
      }}
    }}

    function updateSearchUI() {{
      const val = searchInput.value.trim();
      if (searchClear) searchClear.hidden = !val;
      if (searchKbd) searchKbd.hidden = !!val;
      if (searchStatus && searchCount) {{
        if (val) {{
          const matched = document.querySelectorAll('.event:not(.hidden)').length;
          searchCount.textContent = matched;
          searchStatus.hidden = false;
        }} else {{
          searchStatus.hidden = true;
        }}
      }}
    }}

    function updateMobileBadge() {{
      const allCats = catBoxes.length;
      const chkCats = Array.from(catBoxes).filter(b => b.checked).length;
      const allGenres = genreBoxes.length;
      const chkGenres = Array.from(genreBoxes).filter(b => b.checked).length;
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const allCities = cityBoxes.length;
      const chkCities = Array.from(cityBoxes).filter(b => b.checked).length;
      const allRecurs = recurBoxes.length;
      const chkRecurs = Array.from(recurBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isFiltered = (chkCats < allCats) || (chkGenres < allGenres) || (activeGenre !== 'all') || (chkVenues < allVenues) || (chkCities < allCities) || (chkRecurs < allRecurs) || isFree || popularOnly || starredOnly || (activeTransit !== 'all') || (activeTod !== 'all') || (activeSubarea !== 'all') || (searchInput && !!searchInput.value.trim());

      if (mobileBadge) {{
        mobileBadge.textContent = isFiltered ? 'Active' : 'All';
        mobileBadge.style.color = isFiltered ? 'var(--accent)' : '';
      }}

      const resetBar = document.getElementById('reset-filters-bar');
      if (resetBar) {{
        resetBar.style.display = isFiltered ? 'block' : 'none';
      }}
      const noEventsResetBtn = document.getElementById('no-events-reset-btn');
      if (noEventsResetBtn) {{
        noEventsResetBtn.style.display = isFiltered ? 'inline-block' : 'none';
      }}

      const venueFilterCount = document.getElementById('venue-filter-count');
      if (venueFilterCount) {{
        if (chkVenues > 0 && chkVenues < allVenues) {{
          venueFilterCount.textContent = `${{chkVenues}} selected`;
          venueFilterCount.style.display = 'inline';
        }} else {{
          venueFilterCount.style.display = 'none';
        }}
      }}
    }}

    function stateToHash() {{
      const params = new URLSearchParams();
      const q = searchInput.value.trim();
      if (q) params.set('q', q);

      const allCats = Array.from(catBoxes).map(b => b.value);
      const checkedCats = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCats.length > 0 && checkedCats.length < allCats.length) params.set('cat', checkedCats.join(','));

      if (activeGenre && activeGenre !== 'all') {{
        params.set('genre', activeGenre);
      }} else {{
        const allGenres = Array.from(genreBoxes).map(b => b.value);
        const checkedGenres = Array.from(genreBoxes).filter(b => b.checked).map(b => b.value);
        if (checkedGenres.length > 0 && checkedGenres.length < allGenres.length) params.set('genre', checkedGenres.join(','));
      }}

      const allCities = Array.from(cityBoxes).map(b => b.value);
      const checkedCities = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedCities.length > 0 && checkedCities.length < allCities.length) params.set('city', checkedCities.join(','));
      if (activeSubarea && activeSubarea !== 'all') params.set('sub', activeSubarea);
      if (activeTransit && activeTransit !== 'all') params.set('line', activeTransit);
      if (activeTod && activeTod !== 'all') params.set('tod', activeTod);

      const allRecurs = Array.from(recurBoxes).map(b => b.value);
      const checkedRecurs = Array.from(recurBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedRecurs.length > 0 && checkedRecurs.length < allRecurs.length) params.set('recur', checkedRecurs.join(','));

      const allVenues = Array.from(venueBoxes).map(b => b.value);
      const checkedVenues = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenues.length > 0 && checkedVenues.length < allVenues.length) params.set('venues', checkedVenues.join(';'));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');
      if (popularOnly) params.set('pop', '1');
      if (starredOnly) params.set('saved', '1');

      if (timeFilter !== 'today') params.set('t', timeFilter);
      if ((timeFilter === 'day' || timeFilter === 'week') && fmtISO(anchor) !== todayISO) {{
        params.set('d', fmtISO(anchor));
      }}
      if (currentView !== 'list') params.set('v', currentView);
      if (showPastToday) params.set('past', '1');

      const hash = params.toString();
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    }}

    function hashToState() {{
      const hash = location.hash.slice(1);
      const params = hash ? new URLSearchParams(hash) : null;

      if (params) {{
        if (params.has('q')) searchInput.value = params.get('q');
        if (params.get('free') === '1' && freeOnlyChk) freeOnlyChk.checked = true;
        if (params.get('pop') === '1') popularOnly = true;
        if (params.get('saved') === '1') starredOnly = true;
        if (params.get('past') === '1') showPastToday = true;
        if (params.get('v') === 'map') {{
          switchView('map');
        }}

        if (params.has('t')) {{
          timeFilter = params.get('t');
          showAll = (timeFilter === 'all');
        }}

        if (params.has('cat')) {{
          const vals = new Set(params.get('cat').split(','));
          catBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (params.has('genre')) {{
          const gVal = params.get('genre');
          if (gVal.includes(',')) {{
            const vals = new Set(gVal.split(','));
            genreBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          }} else {{
            activeGenre = gVal;
            genreChips.forEach(c => {{
              c.classList.toggle('active', c.dataset.genre === activeGenre);
            }});
          }}
        }}

        if (params.has('city')) {{
          const vals = new Set(params.get('city').split(','));
          cityBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (params.has('sub')) {{
          activeSubarea = params.get('sub');
        }} else {{
          activeSubarea = 'all';
        }}

        if (params.has('line')) {{
          activeTransit = params.get('line');
        }} else {{
          activeTransit = 'all';
        }}

        if (params.has('tod')) {{
          activeTod = params.get('tod');
        }} else {{
          activeTod = 'all';
        }}
        todRadios.forEach(r => {{ r.checked = (r.value === activeTod); }});

        if (params.has('recur')) {{
          const vals = new Set(params.get('recur').split(','));
          recurBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (params.has('venues')) {{
          const rawVenues = params.get('venues').split(';').map(s => s.trim()).filter(Boolean);
          const vals = new Set(rawVenues);
          venueBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          try {{
            localStorage.setItem('boston_saved_venues', JSON.stringify(Array.from(vals)));
          }} catch (_) {{}}
        }}

        if (params.has('d')) {{
          const d = params.get('d');
          if (d === 'all') {{
            showAll = true;
            timeFilter = 'all';
          }} else {{
            anchor = parseISO(d);
            calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
            if (!params.has('t')) {{
              if (d === todayISO) {{
                timeFilter = 'today';
                showAll = false;
              }} else if (d === fmtISO(addDays(parseISO(todayISO), 1))) {{
                timeFilter = 'tomorrow';
                showAll = false;
              }} else {{
                timeFilter = 'day';
                showAll = false;
              }}
            }}
          }}
        }}
      }}

      if (!params || !params.has('venues')) {{
        try {{
          const saved = JSON.parse(localStorage.getItem('boston_saved_venues') || 'null');
          if (Array.isArray(saved) && saved.length > 0 && saved.length < venueBoxes.length) {{
            const savedSet = new Set(saved);
            venueBoxes.forEach(b => {{ b.checked = savedSet.has(b.value); }});
          }}
        }} catch (_) {{}}
      }}
    }}

    function apply() {{
      const cats = new Set(Array.from(catBoxes).filter(b => b.checked).map(b => b.value));
      const checkedGenres = new Set(Array.from(genreBoxes).filter(b => b.checked).map(b => b.value));
      const venues = new Set(Array.from(venueBoxes).filter(b => b.checked).map(b => b.value));
      const recurs = new Set(Array.from(recurBoxes).filter(b => b.checked).map(b => b.value));
      const cities = new Set(Array.from(cityBoxes).filter(b => b.checked).map(b => b.value));
      const searchText = searchInput.value.trim().toLowerCase();
      const freeOnly = freeOnlyChk ? freeOnlyChk.checked : false;
      const week = new Set(weekDates());

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));
      const anchorISO = fmtISO(anchor);

      // Hydrate deferred days if needed
      let needsHydration = (
        timeFilter === 'all' ||
        showAll ||
        starredOnly ||
        popularOnly ||
        activeTransit !== 'all' ||
        searchText.length > 0
      );
      if (!needsHydration) {{
        if (timeFilter === 'day') {{
          needsHydration = !daySections.some(d => d.dataset.date === anchorISO);
        }} else if (timeFilter === 'week') {{
          for (const wDate of week) {{
            if (!daySections.some(d => d.dataset.date === wDate)) {{
              needsHydration = true;
              break;
            }}
          }}
        }}
      }}
      if (needsHydration) {{
        ensureDeferredDaysHydrated();
      }}

      const nowEpoch = Math.floor(Date.now() / 1000);
      const twoHoursAgoEpoch = nowEpoch - 7200;
      const cutoffDate = new Date(Date.now() - 7200 * 1000);
      const cutoffTimeStr = cutoffDate.toLocaleTimeString('en-US', {{
        timeZone: 'America/New_York',
        hour: 'numeric',
        minute: '2-digit'
      }});

      let hiddenPastCount = 0;
      let totalTodayEventsCount = 0;
      let visibleTonightCount = 0;

      const activeDays = [];
      daySections.forEach(day => {{
        const date = day.dataset.date;
        let inTime = true;
        if (timeFilter === 'today') {{
          inTime = (date === todayISO);
        }} else if (timeFilter === 'tomorrow') {{
          inTime = (date === tomorrowISO);
        }} else if (timeFilter === 'weekend') {{
          inTime = (date === satISO || date === sunISO);
        }} else if (timeFilter === 'day') {{
          inTime = (date === anchorISO);
        }} else if (timeFilter === 'week') {{
          inTime = week.has(date);
        }} else {{
          // 'all'
          inTime = showAll || date === 'tba' || week.has(date);
        }}
        day.classList.toggle('out-of-week', !inTime);
        if (inTime) {{
          activeDays.push(day);
        }}
      }});

      activeDays.forEach(day => {{
        const dayDate = day.dataset.date || '';
        const isToday = dayDate === todayISO;
        const isPastDay = dayDate && dayDate !== 'tba' && dayDate < todayISO;

        day.querySelectorAll('.event').forEach(li => {{
          const catOk = cats.has(li.dataset.bucket);
          const venueOk = venues.has(li.dataset.venue);
          const recurOk = recurs.has(li.dataset.recur);
          const cityOk = cities.has(li.dataset.city);
          const subareaOk = (activeSubarea === 'all') || (li.dataset.subarea === activeSubarea);
          const transitOk = (activeTransit === 'all') || ((li.dataset.transit || '').split(',').includes(activeTransit));
          const todOk = (activeTod === 'all') || (li.dataset.tod === activeTod) || (li.dataset.tod === 'all');
          const freeOk = !freeOnly || li.dataset.free === 'true';
          const popularOk = !popularOnly || parseInt(li.dataset.votes || '0', 10) >= 3;
          const starredOk = !starredOnly || starredEvents.has(li.dataset.id || li.dataset.eventId || '');
          const searchOk = !searchText || li.textContent.toLowerCase().includes(searchText);

          const evGenre = li.dataset.genre;
          const isMusicEv = li.dataset.bucket === 'Music & nightlife' || !!evGenre;
          let genreOk = true;
          if (activeGenre !== 'all') {{
            genreOk = (evGenre === activeGenre);
          }} else if (isMusicEv && evGenre) {{
            genreOk = checkedGenres.has(evGenre);
          }}

          const epoch = li.dataset.epoch ? parseInt(li.dataset.epoch, 10) : 0;
          const isPastTime = isToday && epoch > 0 && epoch < twoHoursAgoEpoch;
          const isPast = isPastDay || isPastTime;

          if (isToday && epoch > 0) {{
            totalTodayEventsCount++;
          }}

          li.classList.toggle('past-time', isPast);

          let timePastOk = true;
          if (isPast) {{
            if (!showPastToday) {{
              timePastOk = false;
              hiddenPastCount++;
            }}
          }}

          const isVisible = catOk && genreOk && venueOk && recurOk && cityOk && subareaOk && transitOk && todOk && searchOk && freeOk && timePastOk && popularOk && starredOk;
          li.classList.toggle('hidden', !isVisible);

          if (isToday && isVisible && !isPast) {{
            visibleTonightCount++;
          }}
        }});

        day.querySelectorAll('.bucket').forEach(b => {{
          const visible = b.querySelectorAll('.event:not(.hidden)').length;
          b.classList.toggle('empty', visible === 0);
          const countSpan = b.querySelector('.bucket-head .count');
          if (countSpan) countSpan.textContent = visible;
        }});

        day.querySelectorAll('.city-section').forEach(sec => {{
          const visible = sec.querySelectorAll('.event:not(.hidden)').length;
          sec.classList.toggle('empty', visible === 0);
          const countSpan = sec.querySelector('.city-head .count');
          if (countSpan) countSpan.textContent = visible;
        }});

        const visible = day.querySelectorAll('.event:not(.hidden)').length;
        day.classList.toggle('empty', visible === 0);
        const headingCount = day.querySelector('h2 .count');
        if (headingCount) headingCount.textContent = visible;
      }});

      // Update past events notice banner
      const pastBanner = document.getElementById('past-events-banner');
      if (pastBanner) {{
        const showBanner = (timeFilter === 'today' || (timeFilter === 'all' && showAll)) && (hiddenPastCount > 0 || showPastToday);
        if (showBanner && (hiddenPastCount > 0 || (showPastToday && totalTodayEventsCount > 0))) {{
          pastBanner.style.display = 'flex';
          const badge = document.getElementById('past-banner-badge');
          const text = document.getElementById('past-banner-text');
          const toggleBtn = document.getElementById('btn-toggle-past');
          const tomorrowBtn = document.getElementById('btn-banner-tomorrow');

          if (!showPastToday) {{
            if (visibleTonightCount === 0 && hiddenPastCount > 0) {{
              if (badge) {{ badge.textContent = 'Tonight Wrapped Up'; badge.className = 'past-banner-badge badge-done'; }}
              if (text) {{ text.innerHTML = `All scheduled events for today have started (<strong>${{hiddenPastCount}}</strong> earlier event${{hiddenPastCount === 1 ? '' : 's'}} hidden)`; }}
              if (toggleBtn) {{ toggleBtn.textContent = 'Show earlier today'; }}
              if (tomorrowBtn) {{ tomorrowBtn.style.display = 'inline-block'; }}
            }} else {{
              if (badge) {{ badge.textContent = '⏱️ Live Tonight'; badge.className = 'past-banner-badge'; }}
              if (text) {{ text.innerHTML = `Showing events from <strong>${{cutoffTimeStr}}</strong> onward (<strong>${{hiddenPastCount}}</strong> earlier event${{hiddenPastCount === 1 ? '' : 's'}} hidden)`; }}
              if (toggleBtn) {{ toggleBtn.textContent = 'Show earlier today'; }}
              if (tomorrowBtn) {{ tomorrowBtn.style.display = 'none'; }}
            }}
          }} else {{
            if (badge) {{ badge.textContent = 'All Day'; badge.className = 'past-banner-badge badge-all'; }}
            if (text) {{ text.innerHTML = `Showing all events for today (including earlier events before ${{cutoffTimeStr}})`; }}
            if (toggleBtn) {{ toggleBtn.textContent = 'Hide earlier events'; }}
            if (tomorrowBtn) {{ tomorrowBtn.style.display = 'none'; }}
          }}
        }} else {{
          pastBanner.style.display = 'none';
        }}
      }}

      const ongoingEl = document.querySelector('.ongoing');
      if (ongoingEl) {{
        ongoingEl.style.display = (timeFilter === 'all' || showAll) ? '' : 'none';
      }}

      const visibleDays = activeDays.filter(d => !d.classList.contains('empty')).length;
      const noEventsEl = document.getElementById('no-events-msg');
      if (noEventsEl) {{
        noEventsEl.style.display = (visibleDays === 0) ? 'block' : 'none';
      }}

      renderCal();
      updateWeekLabel();
      updateQuickChipsUI();
      updateLocChipsUI();
      updateSearchUI();
      const allVenues = venueBoxes.length;
      const checkedVenuesList = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenuesList.length > 0 && checkedVenuesList.length < allVenues) {{
        try {{
          localStorage.setItem('boston_saved_venues', JSON.stringify(checkedVenuesList));
        }} catch (_) {{}}
      }} else if (checkedVenuesList.length === allVenues) {{
        try {{
          localStorage.removeItem('boston_saved_venues');
        }} catch (_) {{}}
      }}

      updateMobileBadge();
      if (currentView === 'map') {{
        updateMapMarkers();
      }}
      stateToHash();
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
        if (!showAll && timeFilter === 'week' && week.has(iso)) classes.push('in-week');
        if (iso === fmtISO(anchor)) classes.push('anchor');
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;
    }}

    function shiftNav(delta) {{
      if (timeFilter === 'week') {{
        anchor = addDays(anchor, delta * 7);
      }} else if (timeFilter === 'today' || timeFilter === 'tomorrow' || timeFilter === 'day') {{
        anchor = addDays(anchor, delta);
        const iso = fmtISO(anchor);
        if (iso === todayISO) {{
          timeFilter = 'today';
        }} else if (iso === fmtISO(addDays(parseISO(todayISO), 1))) {{
          timeFilter = 'tomorrow';
        }} else {{
          timeFilter = 'day';
        }}
      }} else if (timeFilter === 'weekend') {{
        anchor = addDays(anchor, delta * 7);
      }} else {{
        // 'all'
        anchor = addDays(parseISO(todayISO), delta > 0 ? 1 : 0);
        const iso = fmtISO(anchor);
        timeFilter = (iso === todayISO) ? 'today' : (iso === fmtISO(addDays(parseISO(todayISO), 1)) ? 'tomorrow' : 'day');
      }}
      showAll = false;
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}

    function setAnchor(iso) {{
      if (iso === todayISO) {{
        timeFilter = 'today';
      }} else if (iso === fmtISO(addDays(parseISO(todayISO), 1))) {{
        timeFilter = 'tomorrow';
      }} else {{
        timeFilter = 'day';
      }}
      showAll = false;
      anchor = parseISO(iso);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}

    quickChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        timeFilter = chip.dataset.time;
        const todayDate = parseISO(todayISO);
        const dayOfWeek = todayDate.getDay();
        let daysToSat = (6 - dayOfWeek + 7) % 7;
        if (dayOfWeek === 0) daysToSat = -1;

        if (timeFilter === 'all') {{
          showAll = true;
        }} else if (timeFilter === 'today') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'tomorrow') {{
          showAll = false;
          anchor = addDays(parseISO(todayISO), 1);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'weekend') {{
          showAll = false;
          anchor = addDays(todayDate, daysToSat);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }} else if (timeFilter === 'week') {{
          showAll = false;
          anchor = parseISO(todayISO);
          calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        }}
        apply();
      }});
    }});

    if (quickFreeChip && freeOnlyChk) {{
      quickFreeChip.addEventListener('click', () => {{
        freeOnlyChk.checked = !freeOnlyChk.checked;
        apply();
      }});
    }}

    if (quickPopularChip) {{
      quickPopularChip.addEventListener('click', () => {{
        popularOnly = !popularOnly;
        apply();
      }});
    }}

    document.addEventListener('keydown', (e) => {{
      if ((e.key === '/' || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k')) &&
          document.activeElement !== searchInput &&
          !['input', 'textarea'].includes((document.activeElement.tagName || '').toLowerCase())) {{
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }} else if (e.key === 'Escape' && document.activeElement === searchInput) {{
        searchInput.value = '';
        searchInput.blur();
        apply();
      }}
    }});

    if (searchClear) {{
      searchClear.addEventListener('click', () => {{
        searchInput.value = '';
        apply();
        searchInput.focus();
      }});
    }}

    if (mobileToggle && sidebarFilters) {{
      mobileToggle.addEventListener('click', () => {{
        sidebarFilters.classList.add('mobile-open');
        document.body.style.overflow = 'hidden';
      }});
    }}
    if (mobileClose && sidebarFilters) {{
      mobileClose.addEventListener('click', () => {{
        sidebarFilters.classList.remove('mobile-open');
        document.body.style.overflow = '';
      }});
    }}

    document.getElementById('week-prev').addEventListener('click', () => shiftNav(-1));
    document.getElementById('week-next').addEventListener('click', () => shiftNav(1));
    const prevB = document.getElementById('week-prev-b');
    if (prevB) prevB.addEventListener('click', () => shiftNav(-1));
    const nextB = document.getElementById('week-next-b');
    if (nextB) nextB.addEventListener('click', () => shiftNav(1));
    document.getElementById('week-today').addEventListener('click', () => {{
      timeFilter = 'today';
      showAll = false;
      anchor = parseISO(todayISO);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});
    document.getElementById('week-all').addEventListener('click', () => {{
      if (showAll || timeFilter === 'all') {{
        showAll = false;
        timeFilter = 'today';
        anchor = parseISO(todayISO);
      }} else {{
        showAll = true;
        timeFilter = 'all';
      }}
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});

    const noEventsWeek = document.getElementById('no-events-week-btn');
    if (noEventsWeek) {{
      noEventsWeek.addEventListener('click', () => {{
        timeFilter = 'week';
        showAll = false;
        anchor = parseISO(todayISO);
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}
    const noEventsAll = document.getElementById('no-events-all-btn');
    if (noEventsAll) {{
      noEventsAll.addEventListener('click', () => {{
        timeFilter = 'all';
        showAll = true;
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}
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

    if (freeOnlyChk) freeOnlyChk.addEventListener('change', apply);
    catBoxes.forEach(b => b.addEventListener('change', apply));
    genreBoxes.forEach(b => b.addEventListener('change', () => {{ apply(); stateToHash(); }}));
    venueBoxes.forEach(b => b.addEventListener('change', apply));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    searchInput.addEventListener('input', apply);
    document.getElementById('cat-all').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('cat-none').addEventListener('click', () => {{ catBoxes.forEach(b => b.checked = false); apply(); }});
    const genreAllBtn = document.getElementById('genre-all');
    if (genreAllBtn) genreAllBtn.addEventListener('click', () => {{
      genreBoxes.forEach(b => b.checked = true);
      activeGenre = 'all';
      genreChips.forEach(c => c.classList.toggle('active', c.dataset.genre === 'all'));
      apply();
      stateToHash();
    }});
    const genreNoneBtn = document.getElementById('genre-none');
    if (genreNoneBtn) genreNoneBtn.addEventListener('click', () => {{
      genreBoxes.forEach(b => b.checked = false);
      activeGenre = 'all';
      genreChips.forEach(c => c.classList.toggle('active', c.dataset.genre === 'all'));
      apply();
      stateToHash();
    }});
    document.getElementById('venue-all').addEventListener('click', () => {{
      venueBoxes.forEach(b => b.checked = true);
      try {{ localStorage.removeItem('boston_saved_venues'); }} catch (_) {{}}
      apply();
    }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ activeSubarea = 'all'; cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ activeSubarea = 'all'; cityBoxes.forEach(b => b.checked = false); apply(); }});

    function setGenre(genre) {{
      if (activeGenre === genre) {{
        activeGenre = 'all';
      }} else {{
        activeGenre = genre;
      }}
      genreChips.forEach(c => {{
        c.classList.toggle('active', c.dataset.genre === activeGenre);
      }});
      apply();
      if (activeGenre !== 'all' && timeFilter === 'today') {{
        const vis = document.querySelectorAll('.day:not(.out-of-week) .event:not(.hidden)').length;
        if (vis === 0) {{
          timeFilter = 'week';
          showAll = false;
          anchor = parseISO(todayISO);
          apply();
        }}
      }}
      stateToHash();
    }}
    genreChips.forEach(c => {{
      c.addEventListener('click', () => {{
        setGenre(c.dataset.genre);
      }});
    }});

    document.addEventListener('click', (e) => {{
      const pill = e.target.closest('.genre-pill');
      if (pill && pill.dataset.genre) {{
        e.preventDefault();
        setGenre(pill.dataset.genre);
        const bar = document.getElementById('genre-chips-bar');
        if (bar) bar.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
      }}
    }});

    function resetAllFilters() {{
      if (searchInput) searchInput.value = '';
      if (freeOnlyChk) freeOnlyChk.checked = false;
      popularOnly = false;
      starredOnly = false;
      activeSubarea = 'all';
      activeTransit = 'all';
      activeTod = 'all';
      todRadios.forEach(r => {{ r.checked = (r.value === 'all'); }});
      activeGenre = 'all';
      genreChips.forEach(c => c.classList.toggle('active', c.dataset.genre === 'all'));
      genreBoxes.forEach(b => b.checked = true);
      catBoxes.forEach(b => b.checked = true);
      cityBoxes.forEach(b => b.checked = true);
      recurBoxes.forEach(b => b.checked = true);
      venueBoxes.forEach(b => b.checked = true);
      try {{ localStorage.removeItem('boston_saved_venues'); }} catch (_) {{}}
      apply();
    }}

    const btnResetFilters = document.getElementById('btn-reset-filters');
    if (btnResetFilters) btnResetFilters.addEventListener('click', resetAllFilters);

    const noEventsResetBtn = document.getElementById('no-events-reset-btn');
    if (noEventsResetBtn) noEventsResetBtn.addEventListener('click', resetAllFilters);

    const btnShareFilter = document.getElementById('btn-share-filter');
    if (btnShareFilter) {{
      btnShareFilter.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(location.href);
          const shareText = document.getElementById('share-btn-text');
          if (shareText) shareText.textContent = '✓ Copied Link!';
          btnShareFilter.classList.add('copied');
          setTimeout(() => {{
            if (shareText) shareText.textContent = 'Share View';
            btnShareFilter.classList.remove('copied');
          }}, 2000);
        }} catch (_) {{
          prompt('Copy this link to share your filtered view:', location.href);
        }}
      }});
    }}

    window.addEventListener('hashchange', () => {{
      hashToState();
      apply();
    }});

    locChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        const targetCity = chip.dataset.city;
        activeSubarea = 'all';
        if (targetCity === 'all') {{
          activeTransit = 'all';
          cityBoxes.forEach(b => {{ b.checked = true; }});
        }} else {{
          const checked = Array.from(cityBoxes).filter(b => b.checked).map(b => b.value);
          if (checked.length === 1 && checked[0] === targetCity) {{
            cityBoxes.forEach(b => {{ b.checked = true; }});
          }} else {{
            cityBoxes.forEach(b => {{
              b.checked = (b.value === targetCity);
            }});
          }}
        }}
        apply();
      }});
    }});

    transitChips.forEach(chip => {{
      chip.addEventListener('click', () => {{
        const line = chip.dataset.transit;
        activeTransit = (activeTransit === line) ? 'all' : line;
        apply();
      }});
    }});

    todRadios.forEach(radio => {{
      radio.addEventListener('change', () => {{
        if (radio.checked) {{
          activeTod = radio.value;
          apply();
        }}
      }});
    }});

    if (quickStarredChip) {{
      quickStarredChip.addEventListener('click', () => {{
        starredOnly = !starredOnly;
        if (starredOnly && timeFilter === 'today') {{
          timeFilter = 'all';
          showAll = true;
        }}
        apply();
      }});
    }}

    function loadStarredState() {{
      try {{
        const raw = JSON.parse(localStorage.getItem('boston_starred_events') || '[]');
        if (Array.isArray(raw)) starredEvents = new Set(raw);
      }} catch (_) {{}}
      document.querySelectorAll('.event[data-id]').forEach(li => {{
        const isStar = starredEvents.has(li.dataset.id);
        const btn = li.querySelector('.star-btn');
        if (btn) {{
          btn.classList.toggle('starred', isStar);
          btn.textContent = isStar ? '★' : '☆';
          btn.setAttribute('aria-pressed', isStar ? 'true' : 'false');
        }}
      }});
    }}

    document.addEventListener('click', (e) => {{
      const sBtn = e.target.closest('.star-btn');
      if (!sBtn) return;
      e.preventDefault();
      e.stopPropagation();
      const li = sBtn.closest('.event');
      if (!li) return;
      const evId = li.dataset.id || li.dataset.eventId;
      if (!evId) return;
      const nowStarred = !starredEvents.has(evId);
      if (nowStarred) starredEvents.add(evId);
      else starredEvents.delete(evId);
      try {{
        localStorage.setItem('boston_starred_events', JSON.stringify(Array.from(starredEvents)));
      }} catch (_) {{}}
      document.querySelectorAll(`.event[data-id="${{evId}}"] .star-btn`).forEach(b => {{
        b.classList.toggle('starred', nowStarred);
        b.textContent = nowStarred ? '★' : '☆';
        b.setAttribute('aria-pressed', nowStarred ? 'true' : 'false');
      }});
      if (starredOnly && starredEvents.size === 0) {{
        starredOnly = false;
      }}
      updateQuickChipsUI();
      if (starredOnly) apply();
    }});

    if (btnCopyPlan) {{
      btnCopyPlan.addEventListener('click', async () => {{
        ensureDeferredDaysHydrated();
        const items = [];
        const seen = new Set();
        document.querySelectorAll('.event[data-id]').forEach(li => {{
          const id = li.dataset.id;
          if (!starredEvents.has(id) || seen.has(id)) return;
          seen.add(id);
          const daySec = li.closest('.day');
          const dateLabel = daySec ? (daySec.querySelector('h2')?.childNodes[0]?.textContent || daySec.dataset.date || '').trim() : '';
          const when = (li.querySelector('.when')?.textContent || '').trim();
          const aEl = li.querySelector('.what a');
          const title = aEl ? aEl.textContent.trim() : '';
          const url = aEl ? aEl.href : '';
          const vName = li.dataset.venueName || (li.querySelector('.venue-link')?.textContent || li.dataset.venue || '').trim();
          items.push(`• ${{dateLabel}} (${{when}}) — ${{title}} @ ${{vName}}${{url ? ' ' + url : ''}}`);
        }});
        if (!items.length) return;
        const nl = String.fromCharCode(10);
        const planText = `My Boston Events Plan (${{items.length}}):` + nl + items.join(nl);
        try {{
          await navigator.clipboard.writeText(planText);
          const orig = btnCopyPlan.textContent;
          btnCopyPlan.textContent = '✓ Copied Plan!';
          setTimeout(() => {{ btnCopyPlan.textContent = orig; }}, 2000);
        }} catch (_) {{
          prompt('Copy your event plan:', planText);
        }}
      }});
    }}

    function extractEventMetaFromLi(li) {{
      const aEl = li.querySelector('.what > a') || li.querySelector('.what a');
      const title = aEl ? aEl.textContent.trim() : 'Event';
      const url = aEl ? aEl.href : location.href;
      const venue = li.dataset.venueName || (li.querySelector('.venue-link')?.textContent || li.dataset.venue || 'Boston, MA').trim();
      const city = li.dataset.city || 'boston';
      const epoch = li.dataset.epoch ? parseInt(li.dataset.epoch, 10) : 0;
      let dt = epoch > 0 ? new Date(epoch * 1000) : null;
      if (!dt || isNaN(dt.getTime())) {{
        const dStr = li.closest('.day')?.dataset.date;
        if (dStr && dStr !== 'tba') dt = new Date(dStr + 'T19:00:00-04:00');
      }}
      return {{ title, url, venue, city, dt }};
    }}

    function toCalUTC(d) {{
      function pad(n) {{ return n < 10 ? '0' + n : '' + n; }}
      return d.getUTCFullYear() + pad(d.getUTCMonth()+1) + pad(d.getUTCDate()) + 'T' +
             pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + 'Z';
    }}

    function downloadICS(title, dt, venue, url) {{
      if (!dt || isNaN(dt.getTime())) return;
      const start = toCalUTC(dt);
      const end = toCalUTC(new Date(dt.getTime() + 2 * 3600 * 1000));
      function cleanText(str) {{
        return (str || '').split(String.fromCharCode(10)).join(' ')
                          .split(String.fromCharCode(13)).join('')
                          .split(',').join('\\\\,');
      }}
      const cleanTitle = cleanText(title || 'Event');
      const cleanVenue = cleanText(venue || 'Boston, MA');
      const cleanUrl = (url || '').split(String.fromCharCode(10)).join('')
                                  .split(String.fromCharCode(13)).join('');
      const ics = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//Wicked Boston Events//EN',
        'BEGIN:VEVENT',
        'SUMMARY:' + cleanTitle,
        'DTSTART:' + start,
        'DTEND:' + end,
        'LOCATION:' + cleanVenue,
        'DESCRIPTION:' + cleanUrl,
        'END:VEVENT',
        'END:VCALENDAR'
      ].join(String.fromCharCode(13, 10));
      const blob = new Blob([ics], {{ type: 'text/calendar;charset=utf-8' }});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = (title.replace(/[^a-zA-Z0-9]/g, '_') || 'event') + '.ics';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}

    document.addEventListener('click', (e) => {{
      const gBtn = e.target.closest('.gcal-btn');
      if (gBtn) {{
        e.preventDefault();
        const li = gBtn.closest('.event');
        if (!li) return;
        const m = extractEventMetaFromLi(li);
        if (!m.dt) return;
        const start = toCalUTC(m.dt);
        const end = toCalUTC(new Date(m.dt.getTime() + 2 * 3600 * 1000));
        const loc = `${{m.venue}}, ${{m.city.charAt(0).toUpperCase() + m.city.slice(1)}}, MA`;
        const nl = String.fromCharCode(10);
        const details = `Details & Tickets: ${{m.url}}` + nl + nl + `Discovered on Wicked Boston Events`;
        const gUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${{encodeURIComponent(m.title)}}&dates=${{start}}/${{end}}&details=${{encodeURIComponent(details)}}&location=${{encodeURIComponent(loc)}}`;
        window.open(gUrl, '_blank', 'noopener');
        return;
      }}
      const btn = e.target.closest('.ics-btn');
      if (!btn) return;
      e.preventDefault();
      const li = btn.closest('.event');
      if (!li) return;
      const m = extractEventMetaFromLi(li);
      downloadICS(m.title, m.dt, m.venue, m.url);
    }});

    const btnViewList = document.getElementById('btn-view-list');
    if (btnViewList) btnViewList.addEventListener('click', () => switchView('list'));

    const btnViewMap = document.getElementById('btn-view-map');
    if (btnViewMap) btnViewMap.addEventListener('click', () => switchView('map'));

    const mapRecenterBtn = document.getElementById('map-recenter-btn');
    if (mapRecenterBtn) {{
      mapRecenterBtn.addEventListener('click', () => {{
        if (leafletMap) {{
          leafletMap.setView([42.3601, -71.0750], 13, {{ animate: true }});
        }}
      }});
    }}

    const mapLabelToggleBtn = document.getElementById('map-label-toggle-btn');
    const mapEl = document.getElementById('leaflet-map');

    function updateLabelToggleState() {{
      if (!mapLabelToggleBtn || !mapEl) return;
      const isMobile = window.innerWidth <= 860;
      if (isMobile) {{
        const namesOn = mapEl.classList.contains('show-pin-names-mobile');
        mapLabelToggleBtn.textContent = namesOn ? '🏷️ Names: On' : '🔢 Numbers Only';
        mapLabelToggleBtn.title = namesOn ? 'Switch to compact numbers only' : 'Show venue names on pins';
      }} else {{
        const namesOff = mapEl.classList.contains('hide-pin-names');
        mapLabelToggleBtn.textContent = namesOff ? '🔢 Numbers Only' : '🏷️ Names: On';
        mapLabelToggleBtn.title = namesOff ? 'Show venue names on pins' : 'Switch to compact numbers only';
      }}
    }}

    if (mapLabelToggleBtn && mapEl) {{
      mapLabelToggleBtn.addEventListener('click', () => {{
        const isMobile = window.innerWidth <= 860;
        if (isMobile) {{
          mapEl.classList.toggle('show-pin-names-mobile');
        }} else {{
          mapEl.classList.toggle('hide-pin-names');
        }}
        updateLabelToggleState();
      }});
      window.addEventListener('resize', updateLabelToggleState);
      updateLabelToggleState();
    }}

    const panelCloseBtn = document.getElementById('panel-close-btn');
    if (panelCloseBtn) {{
      panelCloseBtn.addEventListener('click', () => {{
        const p = document.getElementById('map-selected-venue');
        if (p) p.style.display = 'none';
      }});
    }}

    document.addEventListener('click', (e) => {{
      const jumpBtn = e.target.closest('.venue-map-jump');
      if (jumpBtn) {{
        e.preventDefault();
        const li = jumpBtn.closest('.event');
        const lat = parseFloat(jumpBtn.dataset.lat || (li && li.dataset.lat));
        const lng = parseFloat(jumpBtn.dataset.lng || (li && li.dataset.lng));
        if (isNaN(lat) || isNaN(lng)) return;
        switchView('map');
        loadLeaflet(() => {{
          initMap();
          if (leafletMap) {{
            leafletMap.setView([lat, lng], 15, {{ animate: true }});
            const mapWrap = document.getElementById('map-view-wrapper');
            if (mapWrap) mapWrap.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }}
        }});
      }}
    }});

    document.addEventListener('click', (e) => {{
      if (e.target && e.target.id === 'btn-toggle-past') {{
        showPastToday = !showPastToday;
        apply();
      }} else if (e.target && e.target.id === 'btn-banner-tomorrow') {{
        const tomorrowChip = document.querySelector('#quick-chips .chip[data-time="tomorrow"]');
        if (tomorrowChip) {{
          tomorrowChip.click();
        }}
      }}
    }});

    window.addEventListener('focus', () => {{
      checkDayRollover();
      if (timeFilter === 'today' && !showPastToday) {{
        apply();
      }}
    }});

    document.addEventListener('visibilitychange', () => {{
      if (document.visibilityState === 'visible') {{
        checkDayRollover();
      }}
    }});

    repositionPastBanner();
    updateDayHeadings();
    scheduleMidnightRefresh();
    setInterval(checkDayRollover, 60000);

    // --- Community Event & Venue Submission Modal Logic ---
    const submitModal = document.getElementById('submit-event-modal');
    const btnOpenSubmit = document.getElementById('btn-open-submit-modal');
    const btnCloseSubmit = document.getElementById('btn-close-submit-modal');
    const btnCancelSubmit = document.getElementById('btn-cancel-submit');
    const communityForm = document.getElementById('community-event-form');
    const evDateInput = document.getElementById('ev-date');
    const btnQuickFree = document.getElementById('btn-quick-free');
    const evPriceInput = document.getElementById('ev-price');
    const formStatus = document.getElementById('form-submit-status');
    const btnSubmitAction = document.getElementById('btn-submit-action');

    const tabBtnEvent = document.getElementById('tab-btn-event');
    const tabBtnVenue = document.getElementById('tab-btn-venue');
    const modalViewEvent = document.getElementById('modal-view-event');
    const modalViewVenue = document.getElementById('modal-view-venue');
    const modalSubmitTitle = document.getElementById('modal-submit-title');
    const modalSubmitSub = document.getElementById('modal-submit-sub');
    const formVenueStatus = document.getElementById('form-venue-status');
    const suggestVenueForm = document.getElementById('suggest-venue-form');
    const btnCancelVenue = document.getElementById('btn-cancel-venue');
    const btnSubmitVenue = document.getElementById('btn-submit-venue');

    function switchModalTab(tab) {{
      if (tab === 'venue') {{
        if (tabBtnVenue) {{ tabBtnVenue.classList.add('active'); tabBtnVenue.setAttribute('aria-selected', 'true'); }}
        if (tabBtnEvent) {{ tabBtnEvent.classList.remove('active'); tabBtnEvent.setAttribute('aria-selected', 'false'); }}
        if (modalViewVenue) modalViewVenue.style.display = 'block';
        if (modalViewEvent) modalViewEvent.style.display = 'none';
        if (modalSubmitTitle) modalSubmitTitle.textContent = 'Suggest a Venue to Track';
        if (modalSubmitSub) modalSubmitSub.textContent = 'Know a music venue, comedy club, theater, or community space we should automatically scrape?';
        const vnInput = document.getElementById('vn-name');
        if (vnInput) setTimeout(() => vnInput.focus(), 60);
      }} else {{
        if (tabBtnEvent) {{ tabBtnEvent.classList.add('active'); tabBtnEvent.setAttribute('aria-selected', 'true'); }}
        if (tabBtnVenue) {{ tabBtnVenue.classList.remove('active'); tabBtnVenue.setAttribute('aria-selected', 'false'); }}
        if (modalViewEvent) modalViewEvent.style.display = 'block';
        if (modalViewVenue) modalViewVenue.style.display = 'none';
        if (modalSubmitTitle) modalSubmitTitle.textContent = 'Add an Event to Boston Events';
        if (modalSubmitSub) modalSubmitSub.textContent = 'Hosting a show, dance, meetup, or know of an event we missed? Submit it below.';
        const evInput = document.getElementById('ev-title');
        if (evInput) setTimeout(() => evInput.focus(), 60);
      }}
    }}

    if (tabBtnEvent) tabBtnEvent.addEventListener('click', () => switchModalTab('event'));
    if (tabBtnVenue) tabBtnVenue.addEventListener('click', () => switchModalTab('venue'));

    function openSubmitModal(initialTab) {{
      if (!submitModal) return;
      submitModal.style.display = 'flex';
      document.body.style.overflow = 'hidden';
      switchModalTab(initialTab === 'venue' ? 'venue' : 'event');
      if (evDateInput && !evDateInput.value) {{
        evDateInput.value = todayISO;
      }}
      if (formStatus) {{
        formStatus.style.display = 'none';
        formStatus.className = 'form-status';
      }}
      if (formVenueStatus) {{
        formVenueStatus.style.display = 'none';
        formVenueStatus.className = 'form-status';
      }}
    }}

    function closeSubmitModal() {{
      if (!submitModal) return;
      submitModal.style.display = 'none';
      document.body.style.overflow = '';
      if (formStatus) formStatus.style.display = 'none';
      if (formVenueStatus) formVenueStatus.style.display = 'none';
    }}

    if (btnOpenSubmit) btnOpenSubmit.addEventListener('click', () => openSubmitModal('event'));
    if (btnCloseSubmit) btnCloseSubmit.addEventListener('click', closeSubmitModal);
    if (btnCancelSubmit) btnCancelSubmit.addEventListener('click', closeSubmitModal);
    if (btnCancelVenue) btnCancelVenue.addEventListener('click', closeSubmitModal);

    if (submitModal) {{
      submitModal.addEventListener('click', (e) => {{
        if (e.target === submitModal) {{
          closeSubmitModal();
        }}
      }});
    }}

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape' && submitModal && submitModal.style.display === 'flex') {{
        closeSubmitModal();
      }}
    }});

    if (btnQuickFree && evPriceInput) {{
      btnQuickFree.addEventListener('click', () => {{
        evPriceInput.value = 'Free';
      }});
    }}

    function loadUpvoteState() {{
      try {{
        const saved = JSON.parse(localStorage.getItem('boston_user_upvotes') || '[]');
        if (Array.isArray(saved)) userUpvotes = new Set(saved);
      }} catch (_) {{}}
      try {{
        const cv = JSON.parse(localStorage.getItem('boston_cached_votes') || '{{}}');
        if (cv && typeof cv === 'object') cachedVotes = cv;
      }} catch (_) {{}}
    }}

    function applyVoteToCard(li, count, hasVoted) {{
      li.dataset.votes = String(count);
      const btn = li.querySelector('.btn-upvote');
      if (btn) {{
        btn.classList.toggle('voted', !!hasVoted);
        btn.setAttribute('aria-pressed', hasVoted ? 'true' : 'false');
        const cntSpan = btn.querySelector('.upvote-count');
        if (cntSpan) cntSpan.textContent = String(count);
      }}
      li.classList.toggle('popular', count >= 3 && count < 5);
      li.classList.toggle('glowing', count >= 5);

      const venueTag = li.querySelector('.venue-tag');
      if (venueTag) {{
        let pBadge = venueTag.querySelector('.badge-popular, .badge-glowing');
        if (count >= 5) {{
          if (!pBadge) {{
            pBadge = document.createElement('span');
            venueTag.prepend(pBadge);
          }}
          pBadge.className = 'badge-glowing';
          pBadge.textContent = '⚡ Trending';
        }} else if (count >= 3) {{
          if (!pBadge) {{
            pBadge = document.createElement('span');
            venueTag.prepend(pBadge);
          }}
          pBadge.className = 'badge-popular';
          pBadge.textContent = '🔥 Popular';
        }} else if (pBadge) {{
          pBadge.remove();
        }}
      }}
    }}

    function syncInitialUpvotes() {{
      document.querySelectorAll('.event[data-event-id]').forEach(li => {{
        const evId = li.dataset.eventId;
        let count = parseInt(li.dataset.votes || '0', 10);
        if (cachedVotes[evId] !== undefined) {{
          count = Math.max(count, cachedVotes[evId]);
        }}
        const hasVoted = userUpvotes.has(evId);
        applyVoteToCard(li, count, hasVoted);
      }});
    }}

    async function handleUpvoteClick(btn) {{
      const li = btn.closest('.event');
      if (!li) return;
      const evId = btn.dataset.id || li.dataset.eventId;
      if (!evId) return;

      let currentVotes = parseInt(li.dataset.votes || '0', 10);
      const wasVoted = userUpvotes.has(evId);

      btn.classList.remove('anim-bounce');
      void btn.offsetWidth;
      btn.classList.add('anim-bounce');
      setTimeout(() => btn.classList.remove('anim-bounce'), 350);

      let newVotes;
      if (wasVoted) {{
        userUpvotes.delete(evId);
        newVotes = Math.max(0, currentVotes - 1);
      }} else {{
        userUpvotes.add(evId);
        newVotes = currentVotes + 1;
      }}

      cachedVotes[evId] = newVotes;
      try {{
        localStorage.setItem('boston_user_upvotes', JSON.stringify(Array.from(userUpvotes)));
        localStorage.setItem('boston_cached_votes', JSON.stringify(cachedVotes));
      }} catch (_) {{}}

      applyVoteToCard(li, newVotes, !wasVoted);
      if (popularOnly) {{
        apply();
      }}

      try {{
        const resp = await fetch('/api/upvote', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ id: evId, action: wasVoted ? 'remove' : 'add' }})
        }});
        if (resp.ok) {{
          const data = await resp.json();
          if (typeof data.votes === 'number') {{
            cachedVotes[evId] = data.votes;
            try {{ localStorage.setItem('boston_cached_votes', JSON.stringify(cachedVotes)); }} catch (_) {{}}
            applyVoteToCard(li, data.votes, !wasVoted);
            if (popularOnly) apply();
          }}
        }}
      }} catch (err) {{
        console.warn('Upvote sync failed:', err);
      }}
    }}

    async function fetchLiveUpvotes() {{
      try {{
        const resp = await fetch('/api/upvotes');
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data || typeof data !== 'object') return;
        let changed = false;
        document.querySelectorAll('.event[data-event-id]').forEach(li => {{
          const evId = li.dataset.eventId;
          if (data[evId] !== undefined) {{
            const serverCount = data[evId];
            cachedVotes[evId] = serverCount;
            const hasVoted = userUpvotes.has(evId);
            applyVoteToCard(li, serverCount, hasVoted);
            changed = true;
          }}
        }});
        try {{ localStorage.setItem('boston_cached_votes', JSON.stringify(cachedVotes)); }} catch (_) {{}}
        if (changed && popularOnly) apply();
      }} catch (_) {{}}
    }}

    document.addEventListener('click', (e) => {{
      const btn = e.target.closest('.btn-upvote');
      if (btn) {{
        e.preventDefault();
        e.stopPropagation();
        handleUpvoteClick(btn);
      }}
    }});

    function injectUserEventIntoDOM(ev) {{
      const dateKey = (ev.date || todayISO).slice(0, 10);
      let daySection = document.querySelector(`.day[data-date="${{dateKey}}"]`);
      if (!daySection) {{
        daySection = document.querySelector(`.day[data-date="${{todayISO}}"]`) || document.querySelector('.day');
      }}
      if (!daySection) return;

      const city = ev.city || 'boston';
      let citySection = daySection.querySelector(`.city-section[data-city="${{city}}"]`);
      if (!citySection) {{
        citySection = daySection.querySelector('.city-section') || daySection;
      }}

      let bucketSection = citySection.querySelector('.bucket');
      let targetUl = bucketSection ? bucketSection.querySelector('ul') : null;
      if (!targetUl) {{
        targetUl = daySection.querySelector('ul');
      }}
      if (!targetUl) return;

      let timeStr = 'TBA';
      try {{
        const dt = new Date(ev.date);
        if (!isNaN(dt)) {{
          let h = dt.getHours();
          const m = dt.getMinutes();
          const ampm = h >= 12 ? 'pm' : 'am';
          h = h % 12 || 12;
          timeStr = `${{h}}:${{String(m).padStart(2, '0')}}${{ampm}}`;
        }}
      }} catch (_) {{}}

      const priceTag = ev.price ? `<span class="price ticketed">${{escapeHTML(ev.price)}}</span>` : '<span class="price free">Free</span>';
      const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${{encodeURIComponent(ev.venue + ', MA')}}`;

      let evId = ev.id;
      if (!evId) {{
        const raw = `${{ev.venue || ''}}|${{ev.name || ''}}|${{dateKey}}`.toLowerCase();
        let hash = 0;
        for (let i = 0; i < raw.length; i++) {{
          hash = ((hash << 5) - hash) + raw.charCodeAt(i);
          hash |= 0;
        }}
        evId = 'ev_' + (hash >>> 0).toString(16);
      }}

      const votes = cachedVotes[evId] || 0;
      const hasVoted = userUpvotes.has(evId);

      const li = document.createElement('li');
      li.className = 'event';
      li.dataset.cat = ev.category || 'other';
      li.dataset.bucket = 'Other';
      li.dataset.venue = ev.venue;
      li.dataset.city = city;
      li.dataset.recur = 'once';
      li.dataset.free = (!ev.price || ev.price.toLowerCase().includes('free')) ? 'true' : 'false';
      li.dataset.eventId = evId;
      li.dataset.votes = String(votes);

      li.innerHTML = `
        <div class="when">${{timeStr}}</div>
        <div class="what">
          <a href="${{escapeHTML(ev.url || '#')}}" target="_blank" rel="noopener">${{escapeHTML(ev.name)}}</a>
          ${{priceTag}}
          <span class="cat-pill" style="--cat-c:#4ade80; background:#4ade8018; border-color:#4ade8033; color:#4ade80">✨ Added Just Now</span>
          <div class="venue-tag">
            <a class="venue-link" href="${{mapsUrl}}" target="_blank" rel="noopener">${{escapeHTML(ev.venue)}}</a>
            <span class="badge-community">👤 Community</span>
          </div>
        </div>
        <div class="vote-wrap">
          <button type="button" class="btn-upvote${{hasVoted ? ' voted' : ''}}" data-id="${{evId}}" aria-label="Upvote this event" title="Upvote event" aria-pressed="${{hasVoted ? 'true' : 'false'}}">
            <span class="upvote-arrow">▲</span>
            <span class="upvote-count">${{votes}}</span>
          </button>
        </div>
      `;

      targetUl.prepend(li);
      applyVoteToCard(li, votes, hasVoted);
    }}

    function escapeHTML(str) {{
      return String(str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function loadLocalCommunityEvents() {{
      try {{
        const raw = localStorage.getItem('boston_community_events');
        if (!raw) return;
        const events = JSON.parse(raw);
        if (!Array.isArray(events)) return;
        const nowMs = Date.now();
        events.forEach(ev => {{
          try {{
            const evMs = new Date(ev.date).getTime();
            if (evMs >= nowMs - (24 * 3600 * 1000)) {{
              injectUserEventIntoDOM(ev);
            }}
          }} catch (_) {{}}
        }});
      }} catch (_) {{}}
    }}

    if (communityForm) {{
      communityForm.addEventListener('submit', async (e) => {{
        e.preventDefault();

        const hp = communityForm.querySelector('input[name="_hp_company"]');
        if (hp && hp.value) {{
          closeSubmitModal();
          return;
        }}

        const nameInput = document.getElementById('ev-title');
        const venueInput = document.getElementById('ev-venue');
        const dateInput = document.getElementById('ev-date');
        const timeInput = document.getElementById('ev-time');
        const citySelect = document.getElementById('ev-city');
        const categorySelect = document.getElementById('ev-category');
        const priceInput = document.getElementById('ev-price');
        const urlInput = document.getElementById('ev-url');
        const descInput = document.getElementById('ev-desc');

        const name = (nameInput.value || '').trim();
        const venue = (venueInput.value || '').trim();
        const dateVal = (dateInput.value || '').trim();
        const timeVal = (timeInput.value || '19:00').trim();
        const city = citySelect ? citySelect.value : 'boston';
        const category = categorySelect ? categorySelect.value : 'other';
        const price = (priceInput.value || '').trim();
        const url = (urlInput.value || '').trim();
        const desc = (descInput.value || '').trim();

        const addressInput = document.getElementById('ev-address');
        const address = (addressInput ? addressInput.value : '').trim();

        if (!name || name.length < 2) {{
          showFormStatus('Please enter an event title (at least 2 characters).', 'error');
          nameInput.focus();
          return;
        }}
        if (!venue || venue.length < 2) {{
          showFormStatus('Please enter a venue or location.', 'error');
          venueInput.focus();
          return;
        }}
        if (!dateVal) {{
          showFormStatus('Please choose an event date.', 'error');
          dateInput.focus();
          return;
        }}
        if (!url || !url.startsWith('http')) {{
          showFormStatus('Please enter a valid website link (starting with http:// or https://).', 'error');
          urlInput.focus();
          return;
        }}

        const isoDate = `${{dateVal}}T${{timeVal}}:00-04:00`;

        const newEvent = {{
          name: name,
          venue: venue,
          date: isoDate,
          url: url,
          category: category,
          city: city,
          address: address,
          price: price || null,
          description: desc,
          _is_community: true,
          submitted_at: new Date().toISOString(),
        }};

        if (btnSubmitAction) {{
          btnSubmitAction.disabled = true;
          const btnText = btnSubmitAction.querySelector('.btn-text');
          const btnSpinner = btnSubmitAction.querySelector('.btn-spinner');
          if (btnText) btnText.style.display = 'none';
          if (btnSpinner) btnSpinner.style.display = 'inline';
        }}

        try {{
          const stored = JSON.parse(localStorage.getItem('boston_community_events') || '[]');
          stored.push(newEvent);
          localStorage.setItem('boston_community_events', JSON.stringify(stored.slice(-20)));
        }} catch (_) {{}}

        injectUserEventIntoDOM(newEvent);
        apply();

        const submitEndpoint = window.EVENT_SUBMISSION_ENDPOINT || '';
        if (submitEndpoint) {{
          try {{
            await fetch(submitEndpoint, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(newEvent),
            }});
          }} catch (err) {{
            console.warn('Backend submission failed, kept locally:', err);
          }}
        }}

        showFormStatus('🎉 Event successfully added! It is now live in your feed.', 'success');

        setTimeout(() => {{
          closeSubmitModal();
          communityForm.reset();
          if (btnSubmitAction) {{
            btnSubmitAction.disabled = false;
            const btnText = btnSubmitAction.querySelector('.btn-text');
            const btnSpinner = btnSubmitAction.querySelector('.btn-spinner');
            if (btnText) btnText.style.display = 'inline';
            if (btnSpinner) btnSpinner.style.display = 'none';
          }}
        }}, 1400);
      }});
    }}

    function showFormStatus(msg, type) {{
      if (!formStatus) return;
      formStatus.textContent = msg;
      formStatus.className = `form-status ${{type}}`;
      formStatus.style.display = 'block';
    }}

    function showVenueFormStatus(msg, type) {{
      if (!formVenueStatus) return;
      formVenueStatus.textContent = msg;
      formVenueStatus.className = `form-status ${{type}}`;
      formVenueStatus.style.display = 'block';
    }}

    if (suggestVenueForm) {{
      suggestVenueForm.addEventListener('submit', async (e) => {{
        e.preventDefault();

        const hp = suggestVenueForm.querySelector('input[name="_hp_company"]');
        if (hp && hp.value) {{
          closeSubmitModal();
          return;
        }}

        const nameInput = document.getElementById('vn-name');
        const urlInput = document.getElementById('vn-url');
        const citySelect = document.getElementById('vn-city');
        const catSelect = document.getElementById('vn-category');
        const addrInput = document.getElementById('vn-address');
        const notesInput = document.getElementById('vn-notes');

        const name = (nameInput.value || '').trim();
        const url = (urlInput.value || '').trim();
        const city = citySelect ? citySelect.value : 'boston';
        const category = catSelect ? catSelect.value : 'music';
        const address = (addrInput ? addrInput.value : '').trim();
        const notes = (notesInput ? notesInput.value : '').trim();

        if (!name || name.length < 2) {{
          showVenueFormStatus('Please enter a venue or space name.', 'error');
          nameInput.focus();
          return;
        }}
        if (!url || !url.startsWith('http')) {{
          showVenueFormStatus('Please enter a valid website link (starting with http:// or https://).', 'error');
          urlInput.focus();
          return;
        }}

        const newVenue = {{
          type: 'suggest_venue',
          name: name,
          url: url,
          city: city,
          category: category,
          address: address,
          notes: notes,
          submitted_at: new Date().toISOString(),
        }};

        if (btnSubmitVenue) {{
          btnSubmitVenue.disabled = true;
          const btnText = btnSubmitVenue.querySelector('.btn-text');
          const btnSpinner = btnSubmitVenue.querySelector('.btn-spinner');
          if (btnText) btnText.style.display = 'none';
          if (btnSpinner) btnSpinner.style.display = 'inline';
        }}

        try {{
          const stored = JSON.parse(localStorage.getItem('boston_suggested_venues') || '[]');
          stored.push(newVenue);
          localStorage.setItem('boston_suggested_venues', JSON.stringify(stored.slice(-20)));
        }} catch (_) {{}}

        const submitEndpoint = window.EVENT_SUBMISSION_ENDPOINT || '';
        if (submitEndpoint) {{
          try {{
            await fetch(submitEndpoint, {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json' }},
              body: JSON.stringify(newVenue),
            }});
          }} catch (err) {{
            console.warn('Backend venue submission failed, kept locally:', err);
          }}
        }}

        showVenueFormStatus('🎉 Venue suggestion received! Thank you for helping Boston Events grow.', 'success');

        setTimeout(() => {{
          closeSubmitModal();
          suggestVenueForm.reset();
          if (btnSubmitVenue) {{
            btnSubmitVenue.disabled = false;
            const btnText = btnSubmitVenue.querySelector('.btn-text');
            const btnSpinner = btnSubmitVenue.querySelector('.btn-spinner');
            if (btnText) btnText.style.display = 'inline';
            if (btnSpinner) btnSpinner.style.display = 'none';
          }}
        }}, 1600);
      }});
    }}

    // --- Theme Switcher ---
    const THEME_KEY = 'boston_events_theme';
    function setTheme(t, save) {{
      const validThemes = ['indie', 'classic', 'anime'];
      const theme = validThemes.includes(t) ? t : 'indie';
      document.documentElement.setAttribute('data-theme', theme);
      if (document.body) {{
        document.body.setAttribute('data-theme', theme);
      }}
      document.querySelectorAll('.theme-pill-btn').forEach(b => {{
        const isActive = (b.dataset.theme === theme);
        b.classList.toggle('active', isActive);
        b.setAttribute('aria-checked', isActive ? 'true' : 'false');
      }});
      if (save !== false) {{
        try {{ localStorage.setItem(THEME_KEY, theme); }} catch (_) {{}}
      }}
    }}
    document.querySelectorAll('.theme-pill-btn').forEach(btn => {{
      btn.addEventListener('click', () => setTheme(btn.dataset.theme, true));
    }});
    try {{
      setTheme(localStorage.getItem(THEME_KEY) || 'indie', false);
    }} catch (_) {{
      setTheme('indie', false);
    }}

    loadUpvoteState();
    loadLocalCommunityEvents();
    syncInitialUpvotes();
    fetchLiveUpvotes();
    loadStarredState();

    hashToState();
    apply();

    if ('requestIdleCallback' in window) {{
      requestIdleCallback(() => {{ ensureDeferredDaysHydrated(); }}, {{ timeout: 2500 }});
    }} else {{
      setTimeout(() => {{ ensureDeferredDaysHydrated(); }}, 2500);
    }}
  </script>
</body>
</html>"""
