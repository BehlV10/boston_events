"""Boston Events — HTML rendering and template logic."""

import hashlib
import json
import os
import shutil
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from urllib.parse import quote, quote_plus, urlparse

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
    luckyseat_open,
    _load_community_events,
    is_placeholder_or_closed_event,
    is_service_ad,
    is_standing_exhibit,
    fix_doubled_url,
    sanitize_event_url,
    is_utility_event,
    is_deal_event,
    is_kid_family_event,
    is_market_or_festival,
    _MARKET_OVERRIDABLE,
)
from venues_geo import resolve_event_geo, nearest_curated_venue, flag_shared_source_points
from lgbtq import is_lgbtq_event
from light_theme import LIGHT_THEME_CSS


DEFAULT_UNCHECKED_BUCKETS = {"Classes & Services", "Kids & Family", "Deals & Specials", "Tech & Startups"}


def _effective_category(e):
    name = e.get("name") or ""
    if is_utility_event(name):
        return "services"
    if is_deal_event(name):
        return "deals"
    if is_kid_family_event(name, e.get("venue")):
        return "family"
    cat = e.get("category") or "other"
    # Also at render time, so pages built from an events.json scraped before a source's markets
    # were classified (or kept from a degraded scrape) still fill the Markets & Festivals page
    if cat in _MARKET_OVERRIDABLE and is_market_or_festival(name):
        return "markets"
    return cat


CITY_RULES = [
    ("somerville", (
        "somerville", "aeronaut", "crystal ballroom", "somerville theatre", "somerville theater",
        "somerville, ma", "(somerville)", ", somerville",
        "davis square", "davis sq", "seven hills park", "assembly row", "union square", "union sq",
        "the burren", "burren", "mccarthy's toad", "mccarthys toad", "remnant somerville",
        "bow market", "upstairs at bow",
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
        "the painted burro", "orlean's restaurant", "orleans restaurant", "thotbot",
    )),
    ("cambridge", (
        "cambridge", "batifol", "passim", "club passim", "monkfish", "mad monkfish",
        "mit ", "m.i.t", "harvard square", "harvard book", "porter square", "sinclair", "comedy studio",
        "brattle", "cambridge, ma", "(cambridge)", ", cambridge",
        "kendall", "kendall center", "urban park", "central square", "inman square", "cantab",
        "havetodance", "have to dance", "ywca cambridge",
        "middle east", "sonia", "regattabar", "arrow street",
        "harvard museum", "hmnh",
        "lovestruck", "lovestruck books",
        "havana club", "lou's", "wearelous", "lizard lounge",
        "lamplighter", "roxy's arcade", "roxys arcade",
        "venture café", "venture cafe", "cic cambridge",
        "the platform", "the platform kendall", "platform kendall",
        "phoenix landing", "manray", "man ray", "prospect st", "middlesex", "middlesex lounge",
        "lilypad", "inman square", "the druid", "druid",
        "plough and stars", "plough & stars", "gather here", "mit open space",
        "remnant satellite", "satellite", "cambridge public library", "cambridge library",
        "harvard university farmers market", "harvard farmers market",
        "q ballroom", "ccae", "cambridge center for adult education",
        "harvard art museum", "peabody museum", "the foundry", "memorial drive",
        "bluesy tuesy", "blues union", "41 hampshire", "dante alighieri",
        "everybody dance now", "multicultural arts center", "the dance complex", "dance complex",
        "first street market", "la fábrica", "la fabrica", "kathryn schultz",
        "an sibin", "an sibín", "the coop", "forage", "52 church", "farkas hall",
        "loeb ex", "pemberton farms", "fusey bluesy", "graymist", "the grove",
        "cambridge art association", "loeb drama", "harvard film archive",
        "graduate school of design", "harvard graduate school of education", "sheraton commander",
        "325 binney", "microsoft new england research", "ef education first",
    )),
    ("boston", (
        "the 88 club", "88 club",
        "bsmnt", "kings seaport", "kings - seaport", "kings dining",
        "midway cafe", "o'brien's pub", "obriens pub", "o'brien's", "obriens",
        "jordan hall", "new england conservatory", "nec (", "nec:", "nec ", "nec hall",
        "improv asylum", "city winery", "royale", "wilbur", "ica boston", "gardner", "boston public library",
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
        "arnold arboretum", "franklin park", "224 boston", "yellow door taqueria", "wyndham boston beacon hill",
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
        "winthrop center", "overlook st gabriel", "harvard stadium", "bright-landry", "goel center",
        "cutler majestic", "kennedy presidential library", "jfk library", "case gymnasium", "case center",
        "warrior ice arena", "tsai performance", "harvard business school", "klarman hall",
        "rubenstein treehouse", "umass boston", "state house", "faneuil hall", "boston public market",
        "egleston", "massart", "massachusetts college of art", "artists for humanity", "lenox hotel",
        "common craft southie", "northeastern university", "cabot center", "icon nightclub",
        "venu nightclub", "bijou", "elephant & castle", "fogo de chão", "fogo de chao", "artesani park",
        "399 boylston", "william e mullins way", "hynes", "off the rails", "lavietes", "31 hemenway", "bully boy",
    )),
]

CITY_LABELS = {
    "boston": "Boston",
    "cambridge": "Cambridge",
    "somerville": "Somerville",
    "other": "Other",
}


_BOSTON_LOCALITIES = {
    "boston", "allston", "brighton", "charlestown", "jamaica plain", "dorchester", "roxbury",
    "south boston", "east boston", "mattapan", "roslindale", "hyde park", "west roxbury",
    "mission hill", "back bay", "beacon hill", "north end", "south end", "fenway", "seaport",
    "brookline",  # grouped with Boston, matching the geo-address fallback below
}


def _city_from_address(e):
    """City from a scraped street address: the locality ("Cambridge"), else the ZIP code.
    Returns None when there's no address or it's outside Boston/Cambridge/Somerville."""
    if not isinstance(e, dict):
        return None
    loc = (e.get("locality") or "").strip().lower()
    addr = (e.get("address") or e.get("location") or "").lower()
    zip_m = re.search(r"\b0(2\d{3})\b", f"{e.get('postal_code') or ''} {addr}")
    if not loc and addr:
        m = re.search(r",\s*([a-z .'-]+?)\s*(?:,\s*(?:ma|massachusetts)\b|\s+0\d{4}\b|$)", addr)
        loc = m.group(1).strip() if m else ""
    if loc == "cambridge":
        return "cambridge"
    if loc == "somerville":
        return "somerville"
    if loc in _BOSTON_LOCALITIES:
        return "boston"
    if zip_m:
        z = int(zip_m.group(1))
        if 2138 <= z <= 2142:
            return "cambridge"
        if 2143 <= z <= 2145:
            return "somerville"
        if 2108 <= z <= 2137 or z in (2163, 2199, 2203, 2210, 2215, 2445, 2446):
            return "boston"
    return None


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
    by_addr = _city_from_address(ev_dict)
    if by_addr:
        return by_addr
    geo = resolve_event_geo(ev_dict)
    if geo and not geo.get("address") and geo.get("lat") is not None:
        # Ticketing sources give coordinates but no address: borrow the nearest known venue's
        near = nearest_curated_venue(float(geo["lat"]), float(geo["lng"]))
        if near:
            geo = near
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
        if any(k in blob for k in ["central square", "cantab", "middle east", "sonia", "manray", "man ray", "middlesex", "phoenix landing", "plough and stars", "plough & stars", "dance complex", "mad monkfish", "la fabrica", "havana club", "roxy", "a4cade"]):
            return ("Central Square", "central_sq")
        if any(k in blob for k in ["harvard square", "sinclair", "brattle", "passim", "harvard book", "harvard museum", "peabody museum", "lou's", "wearelous", "sanders", "farkas", "harvard university", "ccae", "harvard art museum", "main library", "449 broadway", "comedy studio"]):
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
        if any(k in blob for k in ["davis", "somerville theatre", "crystal ballroom", "burren", "rockwell", "underbones", "painted burro", "west branch"]):
            return ("Davis Square", "davis_sq")
        if any(k in blob for k in ["union square", "bow market", "armory", "arts at the armory", "jungle", "remnant", "sally o'brien", "sally obrien", "side quest", "duck duck goof", "dance union", "goofs comedy", "vera's", "warehouse xi", "warehouse 11", "warehouse-xi"]):
            return ("Union Square", "union_sq")
        if any(k in blob for k in ["growing center", "spring hill", "winter hill", "magoun", "highland", "central library", "79 highland", "chester tavern"]):
            return ("Spring & Winter Hill", "spring_winter_hill")
        if any(k in blob for k in ["assembly", "portico", "aeronaut", "east somerville", "boynton", "east branch", "craft loft", "all she wrote"]):
            return ("Assembly & East Somerville", "assembly_east")
        return ("Other Somerville", "somerville_other")

    elif city == "boston":
        if any(k in blob for k in ["fenway", "symphony", "house of blues", "mgm music", "mfa", "museum of fine arts", "jordan hall", "nec ", "nec:", "nec (", "new england conservatory", "berklee", "cafe 939", "time out", "401 park", "bill's bar", "bills bar", "loretta", "kenmore", "wbur cityspace", "890 commonwealth"]):
            return ("Fenway & Kenmore", "fenway_kenmore")
        if any(k in blob for k in ["theater district", "theatre district", "boch", "wang", "shubert", "paramount", "colonial", "royale", "charles playhouse", "downtown", "boston common", "chinatown", "north end", "public garden", "duckling", "orpheum", "bsmnt", "city winery", "big night live", "td garden", "wilbur", "sports museum", "versus", "west end", "legacy", "feral",
                                    "boston public market", "haymarket", "faneuil hall", "quincy market", "city hall plaza"]):
            return ("Downtown & Boston Common", "theater_downtown")
        if any(k in blob for k in ["south end", "beehive", "wally", "club cafe", "club café", "sowa", "reunion bbq", "calderwood", "bca plaza"]):
            return ("South End", "south_end")
        if any(k in blob for k in ["back bay", "copley", "boston public library (central", "700 boylston", "trident", "newbury", "prudential", "dani", "danis", "88 club"]):
            return ("Back Bay & Copley", "back_bay")
        if any(k in blob for k in ["seaport", "south boston", "leader bank", "ica boston", "kings seaport", "kings dining", "greenway", "harbor", "scorpion", "laugh boston"]):
            return ("Seaport & Waterfront", "seaport_waterfront")
        if any(k in blob for k in ["allston", "brighton", "o'brien", "obrien", "brighton music", "speedway", "roadrunner", "lavietes", "notch brewing", "harvard stadium", "sunset cantina", "goel center"]):
            return ("Allston & Brighton", "allston_brighton")
        if any(k in blob for k in ["jamaica plain", "jp", "midway cafe", "arboretum", "franklin park", "dorchester", "roxbury", "mattapan", "roslindale", "hyde park", "columbia point", "kennedy institute"]):
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


from scrapers import admission_price, mentions_free  # noqa: E402

# Activities that are usually free ("open mic", "board games", "run club"). Only a hint: the venue
# may still charge (Queer Board Game Night at Club Café is $5), so a listed price, a ticket link or
# an admission-only venue outweighs it.
_FREE_ACTIVITY_RE = re.compile(
    r"\b("
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
    r"run clubs?"
    r")\b",
    re.IGNORECASE,
)

# Sites that sell paid tickets. Ticketmaster, AXS and the like list paid shows, so a missing price
# there never means free ("Iliza Shlesinger: Free Nights & Weekends" is a tour name).
_PAID_SELLER_RE = re.compile(
    r"(?:^|[/.])(?:ticketmaster|livenation|axs|ticketweb|etix|seetickets|dice\.fm|tixr|showclix|prekindle|"
    r"holdmyticket|eventim|seatgeek|stubhub|vividseats)\.",
    re.IGNORECASE,
)
# Any ticketing page, free or paid; enough to doubt a free guess drawn from an activity word.
_TICKET_LINK_RE = re.compile(
    r"(?:^|[/.])(?:eventbrite|tickettailor|simpletix|ticketleap|brownpapertickets|humanitix|universe|ludus|"
    r"seatengine|eventcombo|withfriends)\.|//tickets?\.|/tickets?(?:[/?#-]|$)|/checkout|/buy-tickets",
    re.IGNORECASE,
)
# Places where an activity is included with paid admission (storytime at the Children's Museum).
_ADMISSION_VENUES = ("children's museum", "childrens museum", "museum of science", "aquarium", "zoo",
                     "discovery museum", "legoland")

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

    # Another listing of the same event names a price ("$5" on the venue's page).
    alts = e.get("_alt_sources") or []
    if not price and any(re.search(r"\$\s?[1-9]", a.get("price") or "") for a in alts):
        return False

    name = (e.get("name") or "").lower()
    desc = (e.get("description") or "").lower()
    source = (e.get("_source_venue") or "").lower()
    venue = (e.get("venue") or "").lower()
    urls = [e.get("url") or ""] + [a.get("url") or "" for a in alts]

    if any(_PAID_SELLER_RE.search(u) for u in urls):
        return False

    if any(k in source or k in venue for k in [
        "library", "bpl", "farmers market", "open market",
        "esplanade association", "greenway", "rose kennedy greenway", "arnold arboretum"
    ]):
        return True

    if mentions_free(name):
        return True

    if any(p in desc for p in _FREE_DESC_PHRASES):
        return True

    if _FREE_ACTIVITY_RE.search(name):
        sells_tickets = any(_TICKET_LINK_RE.search(u) for u in urls)
        charges_admission = any(k in venue or k in source for k in _ADMISSION_VENUES)
        return not (admission_price(desc) or sells_tickets or charges_admission)

    return False


def get_site_url():
    cname_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CNAME")
    if os.path.exists(cname_path):
        try:
            with open(cname_path, "r", encoding="utf-8") as f:
                domain = f.read().strip()
                if domain:
                    return f"https://{domain}"
        except Exception:
            pass
    return os.environ.get("SITE_URL", "https://behlv10.github.io/boston_events").rstrip("/")


def build_seo_meta_tags(site_url=None, title=None, description=None, path="", image_url=None):
    if not site_url:
        site_url = get_site_url()

    clean_path = path.lstrip("/")
    canonical_url = f"{site_url}/{clean_path}" if clean_path else f"{site_url}/"
    default_title = "Wicked Boston Events · Live Music, Comedy, Nightlife & Things to Do in Boston, Cambridge & Somerville"
    default_desc = "Find 8,000+ live music shows, comedy, theater, nightlife, and free events across Boston, Cambridge & Somerville. Filter by neighborhood and MBTA subway lines."

    t = title or default_title
    d = description or default_desc
    img = image_url or f"{site_url}/og-image.jpg?v=2"

    return f"""<!-- SEO & AEO Meta Tags -->
<title>{escape(t)}</title>
<meta name="description" content="{escape(d)}">
<meta name="keywords" content="Boston events, Boston live music, things to do in Boston, Cambridge concerts, Somerville comedy, Boston nightlife, free events Boston, Boston theater, live music Boston tonight, things to do this weekend Boston">
<meta name="author" content="Wicked Boston Events">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<link rel="canonical" href="{escape(canonical_url)}">

<!-- OpenGraph / Social Previews -->
<meta property="og:locale" content="en_US">
<meta property="og:type" content="website">
<meta property="og:title" content="{escape(t)}">
<meta property="og:description" content="{escape(d)}">
<meta property="og:url" content="{escape(canonical_url)}">
<meta property="og:site_name" content="Wicked Boston Events">
<meta property="og:image" content="{escape(img)}">
<meta property="og:image:secure_url" content="{escape(img)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Wicked Boston Events Guide">

<!-- Twitter Cards -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(t)}">
<meta name="twitter:description" content="{escape(d)}">
<meta name="twitter:image" content="{escape(img)}">
<meta name="twitter:site" content="@wickedbostonevents">"""


def build_json_ld(events, site_url=None):
    if not site_url:
        site_url = get_site_url()

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Wicked Boston Events",
        "url": f"{site_url}/",
        "description": "Find 8,000+ live music shows, comedy, theater, nightlife, and free events across Boston, Cambridge & Somerville. Filter by neighborhood and MBTA subway lines.",
        "inLanguage": "en-US",
        "publisher": {
            "@type": "Organization",
            "name": "Wicked Boston Events",
            "url": f"{site_url}/",
            "logo": f"{site_url}/logo-512.png"
        },
        "potentialAction": {
            "@type": "SearchAction",
            "target": f"{site_url}/#q={{search_term_string}}",
            "query-input": "required name=search_term_string"
        }
    }

    faq_schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "What are the best live music venues in Boston and Cambridge?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Top live music stages in Greater Boston include The Sinclair, Middle East (Upstairs & Downstairs), Cantab Lounge, Paradise Rock Club, Midway Cafe, Club Passim, The Rockwell, O'Brien's Pub, Lilypad, Symphony Hall, Berklee Performance Center, and Warehouse XI."
                }
            },
            {
                "@type": "Question",
                "name": "Where can I find free events and comedy in Boston tonight?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "Wicked Boston Events tracks dozens of free and low-cost community events, open mics, and live performances across Boston, Cambridge, and Somerville. Use the 'Free' filter to browse free museum days, brewery trivia, live jazz, and stand-up shows."
                }
            },
            {
                "@type": "Question",
                "name": "What neighborhoods in Greater Boston does this event guide cover?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "The calendar covers Boston (Back Bay, Allston, Brighton, Fenway, Seaport, Downtown, South End, Dorchester, Roslindale), Cambridge (Harvard Square, Central Square, Kendall Square, Inman Square, Porter Square), and Somerville (Davis Square, Union Square, Assembly Row, Spring Hill)."
                }
            },
            {
                "@type": "Question",
                "name": "How often is the Boston Events calendar updated?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": "The calendar is automatically scraped and synchronized daily directly from official venue box offices, artist calendars, and verified community sources."
                }
            }
        ]
    }

    event_items = []
    seen = set()
    for e in events:
        d_str = e.get("date")
        if not d_str or d_str == "tba":
            continue
        title = e.get("title") or e.get("name")
        venue_name = e.get("venue") or e.get("_source_venue") or "Boston Area Venue"
        if not title:
            continue
        k = f"{d_str}_{venue_name}_{title[:30]}".lower()
        if k in seen:
            continue
        seen.add(k)

        t_obj = e.get("_time")
        t_str = e.get("time") or ""
        start_date = d_str
        if t_obj:
            start_date = f"{d_str}T{t_obj.strftime('%H:%M:%S')}-05:00"
        elif ":" in t_str and ("am" in t_str.lower() or "pm" in t_str.lower()):
            try:
                dt_tmp = datetime.strptime(t_str.strip().upper(), "%I:%M %p")
                start_date = f"{d_str}T{dt_tmp.strftime('%H:%M:%S')}-05:00"
            except Exception:
                pass

        geo = resolve_event_geo(e)
        city = _event_city(venue_name, e.get("_source_venue"), e)
        city_label = CITY_LABELS.get(city, "Boston")

        location_obj = {
            "@type": "Place",
            "name": venue_name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city_label,
                "addressRegion": "MA",
                "addressCountry": "US"
            }
        }
        if geo:
            if geo.get("address"):
                location_obj["address"]["streetAddress"] = geo["address"]
            location_obj["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": geo["lat"],
                "longitude": geo["lng"]
            }

        url = e.get("url") or e.get("link") or f"{site_url}/"
        price = e.get("price")
        is_free_val = _is_event_free(e)
        offers_obj = {
            "@type": "Offer",
            "url": url,
            "availability": "https://schema.org/InStock",
            "priceCurrency": "USD"
        }
        if is_free_val:
            offers_obj["price"] = "0"
        elif price:
            m_price = re.search(r"\$?(\d+(\.\d{2})?)", str(price))
            if m_price:
                offers_obj["price"] = m_price.group(1)

        ev_img = e.get("img") or e.get("image") or f"{site_url}/og-image.jpg"
        ev_schema = {
            "@type": "Event",
            "name": title,
            "startDate": start_date,
            "eventStatus": "https://schema.org/EventScheduled",
            "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
            "location": location_obj,
            "image": [ev_img],
            "description": e.get("description") or f"{title} live at {venue_name} in {city_label}, MA",
            "url": url,
            "offers": offers_obj,
            "performer": {
                "@type": "PerformingGroup",
                "name": title
            },
            "organizer": {
                "@type": "Organization",
                "name": e.get("_source_venue") or venue_name,
                "url": url
            }
        }
        event_items.append(ev_schema)
        if len(event_items) >= 75:
            break

    itemlist_schema = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": "Upcoming Greater Boston Events",
        "description": "Curated upcoming live events across Boston, Cambridge, and Somerville.",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": idx + 1,
                "item": ev
            }
            for idx, ev in enumerate(event_items)
        ]
    }

    scripts = [
        f'<script type="application/ld+json">\n{json.dumps(website_schema, ensure_ascii=False, indent=2)}\n</script>',
        f'<script type="application/ld+json">\n{json.dumps(faq_schema, ensure_ascii=False, indent=2)}\n</script>',
        f'<script type="application/ld+json">\n{json.dumps(itemlist_schema, ensure_ascii=False, indent=2)}\n</script>'
    ]
    return "\n".join(scripts)


def build_seo_directory_html(all_events_flat, all_venue_names):
    venue_counts = defaultdict(int)
    for e in all_events_flat:
        v = e.get("venue") or e.get("_source_venue")
        if v:
            venue_counts[v] += 1

    # Prioritize active venues with shows, then alphabetical
    sorted_venues = sorted(all_venue_names, key=lambda v: (-venue_counts.get(v, 0), v.lower()))
    venue_lis = []
    for v in sorted_venues:
        cnt = venue_counts.get(v, 0)
        if cnt == 0 and len(venue_lis) >= 80:
            continue
        cnt_str = f" <span class=\"dir-cnt\">({cnt})</span>" if cnt > 0 else ""
        venue_lis.append(f'<li><a href="#venues={quote(v)}">{escape(v)}</a>{cnt_str}</li>')
    venues_html = "\n".join(venue_lis)

    return f"""<section class="seo-directory" id="boston-directory" aria-label="Greater Boston Events Directory">
  <div class="directory-container">
    <div class="directory-header">
      <h2>Greater Boston Events Directory &amp; Neighborhood Guide</h2>
      <p class="directory-sub">Live independent directory for concerts, stand-up comedy, nightlife, stage theater, and arts across Boston, Cambridge, and Somerville. Data synchronized directly from 40+ official venue box offices.</p>
    </div>

    <div class="directory-grid">
      <!-- Locations & Neighborhoods -->
      <div class="directory-col">
        <h3>📍 Browse by Neighborhood</h3>
        <div class="directory-group">
          <strong class="directory-group-title"><a href="boston/">Boston</a></strong>
          <ul>
            <li><a href="#city=boston&amp;sub=back_bay_copley">Back Bay &amp; Copley</a></li>
            <li><a href="#city=boston&amp;sub=allston_brighton">Allston &amp; Brighton</a></li>
            <li><a href="#city=boston&amp;sub=fenway_kenmore">Fenway &amp; Kenmore</a></li>
            <li><a href="#city=boston&amp;sub=downtown_common">Downtown &amp; Boston Common</a></li>
            <li><a href="#city=boston&amp;sub=seaport_waterfront">Seaport &amp; Waterfront</a></li>
            <li><a href="#city=boston&amp;sub=south_end">South End</a></li>
            <li><a href="#city=boston&amp;sub=brookline">Brookline &amp; Coolidge Corner</a></li>
            <li><a href="#city=boston&amp;sub=dorchester_roxbury">Dorchester &amp; Roxbury</a></li>
          </ul>
        </div>
        <div class="directory-group">
          <strong class="directory-group-title"><a href="cambridge/">Cambridge</a></strong>
          <ul>
            <li><a href="#city=cambridge&amp;sub=harvard_sq">Harvard Square</a></li>
            <li><a href="#city=cambridge&amp;sub=central_sq">Central Square</a></li>
            <li><a href="#city=cambridge&amp;sub=kendall_east">Kendall &amp; East Cambridge</a></li>
            <li><a href="#city=cambridge&amp;sub=inman_porter">Inman &amp; Porter Square</a></li>
          </ul>
        </div>
        <div class="directory-group">
          <strong class="directory-group-title"><a href="somerville/">Somerville</a></strong>
          <ul>
            <li><a href="#city=somerville&amp;sub=davis_sq">Davis Square</a></li>
            <li><a href="#city=somerville&amp;sub=union_sq">Union Square</a></li>
            <li><a href="#city=somerville&amp;sub=assembly_row">Assembly Row</a></li>
            <li><a href="#city=somerville&amp;sub=spring_hill_gilman">Spring Hill &amp; Gilman</a></li>
          </ul>
        </div>
      </div>

      <!-- Categories & Vibes -->
      <div class="directory-col">
        <h3>🎭 Browse by Category</h3>
        <ul>
          <li><a href="music/">Live Music &amp; Concerts</a></li>
          <li><a href="comedy/">Stand-Up Comedy &amp; Improv</a></li>
          <li><a href="#cat=Stage+%26+theater">Stage, Theater &amp; Musicals</a></li>
          <li><a href="#cat=Nightlife+%26+parties">Nightlife &amp; Queer Parties</a></li>
          <li><a href="#cat=Arts+%26+culture">Arts, Galleries &amp; Museum Nights</a></li>
          <li><a href="#cat=Community">Community, Markets &amp; Gatherings</a></li>
          <li><a href="#cat=Film">Cinema &amp; Indie Film Screenings</a></li>
          <li><a href="free/">Free Events in Boston</a></li>
          <li><a href="#picks=1">Curator's Highlights &amp; Picks</a></li>
        </ul>

        <h3 style="margin-top:18px;">🎵 Music Subgenres</h3>
        <ul class="genre-tag-list">
          <li><a href="#cat=Music+%26+nightlife&amp;genre=rock_indie">Indie &amp; Rock</a></li>
          <li><a href="#cat=Music+%26+nightlife&amp;genre=hiphop_rnb">Hip-Hop &amp; R&amp;B</a></li>
          <li><a href="#cat=Music+%26+nightlife&amp;genre=jazz_blues">Jazz, Soul &amp; Blues</a></li>
          <li><a href="#cat=Music+%26+nightlife&amp;genre=electronic">Electronic &amp; Techno</a></li>
          <li><a href="#cat=Music+%26+nightlife&amp;genre=folk_trad">Folk &amp; Americana</a></li>
          <li><a href="#cat=Music+%26+nightlife&amp;genre=classical">Classical &amp; Symphony</a></li>
        </ul>

        <h3 style="margin-top:18px;">🔥 Programmatic Event Guides</h3>
        <ul>
          <li><a href="free-events-boston-this-weekend/">Free Events This Weekend</a></li>
          <li><a href="cambridge-events-tonight/">Cambridge Events Tonight</a></li>
          <li><a href="live-music-somerville/">Somerville Live Music</a></li>
          <li><a href="board-game-nights-boston/">Board Game Nights &amp; Trivia</a></li>
          <li><a href="kids-family-events-boston/">Kids &amp; Family Events</a></li>
          <li><a href="boston-edm/">Boston EDM &amp; Electronic Shows</a></li>
          <li><a href="markets-festivals-boston/">Markets, Fairs &amp; Festivals</a></li>
        </ul>
      </div>

      <!-- Venues A-Z -->
      <div class="directory-col">
        <h3>🏛️ Tracked Venues A–Z</h3>
        <p class="hint">Official box office feeds tracked and refreshed daily.</p>
        <ul class="venue-directory-list">
          {venues_html}
        </ul>
      </div>
    </div>

    <!-- Verified Entity Q&A for AEO (Perplexity, ChatGPT, Gemini, Copilot) -->
    <div class="aeo-faq-block">
      <h3>Frequently Asked Questions about Greater Boston Events</h3>
      <div class="faq-item">
        <h4>Where can I find live music and theater in Boston and Cambridge tonight?</h4>
        <p>Wicked Boston Events tracks over 100+ local stages and theater spaces daily, including Symphony Hall, The Sinclair, Middle East, Central Square Theater, Calderwood Pavilion (BCA), Cantab Lounge, Paradise Rock Club, Midway Cafe, Club Passim, and O'Brien's Pub.</p>
      </div>
      <div class="faq-item">
        <h4>Are there stand-up comedy shows, plays, and free events in Boston this week?</h4>
        <p>Yes! Check our <a href="comedy/">Comedy Guide</a> for shows at Laugh Boston, The Comedy Studio, and Improv Asylum; browse <a href="#cat=Stage+%26+theater">Stage &amp; Theater</a> for Calderwood Pavilion, Central Square Theater, and Huntington Theatre productions; or explore our <a href="free/">Free Events Guide</a> for museum days, Eventbrite community gatherings, open mics, and markets.</p>
      </div>
      <div class="faq-item">
        <h4>How does Boston Events differ from commercial ticketing sites?</h4>
        <p>Wicked Boston Events is an independent community project. It does not sell tickets, charge fees, or take broker markups. Every listing links directly to the venue's own official box office or community organizer.</p>
      </div>
    </div>
  </div>
</section>"""


def _parse_event_eastern_date(e):
    raw = e.get("date")
    if not raw or raw == "tba":
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=EASTERN)
        else:
            dt = dt.astimezone(EASTERN)
        return dt.date()
    except Exception:
        if len(str(raw)) >= 10 and str(raw)[:10].count("-") == 2:
            try:
                return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
            except Exception:
                pass
    return None


def _event_date_matches_time_filter(e, time_filter):
    if not time_filter:
        return True
    ed = _parse_event_eastern_date(e)
    if not ed:
        return False
    today = datetime.now(EASTERN).date()
    if time_filter in ("tonight", "today"):
        return ed == today
    if time_filter == "weekend":
        cur_weekday = today.weekday()
        if cur_weekday == 5:
            weekend_dates = {today + timedelta(days=-1), today, today + timedelta(days=1)}
        elif cur_weekday == 6:
            weekend_dates = {today + timedelta(days=-2), today + timedelta(days=-1), today}
        elif cur_weekday == 4:
            weekend_dates = {today, today + timedelta(days=1), today + timedelta(days=2)}
        else:
            days_to_fri = 4 - cur_weekday
            weekend_dates = {today + timedelta(days=days_to_fri + i) for i in (0, 1, 2)}
        return ed in weekend_dates
    return True


def _event_matches_keywords(e, keywords):
    if not keywords:
        return True
    text = f"{e.get('title', '')} {e.get('name', '')} {e.get('description', '')} {e.get('category', '')} {e.get('genre', '')}".lower()
    return any(k.lower() in text for k in keywords)


def _series_key(e):
    name = re.sub(r"\b20\d\d\b|[^a-z0-9 ]+", " ", (e.get("name") or "").lower())
    # First word of the venue: listings of one series spell it "SoWa" / "SoWa Open Market"
    venue = re.sub(r"^the |[^a-z0-9 ]+", " ", (e.get("venue") or e.get("_source_venue") or "").lower())
    return " ".join(name.split()), (venue.split() or [""])[0]


def _collapse_hub_series(events, show_dates=3):
    """One card per repeating series (a weekly farmers market, a month-long holiday market, the
    two weekends of a fair) at its next date, its later dates listed in the card's description:
    "Also Sat, Nov 28 · Sun, Nov 29 · Sat, Dec 5 and 11 more dates." Events must be date-sorted."""
    groups, order = {}, []
    for e in events:
        k = _series_key(e)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(e)
    out = []
    for k in order:
        first, rest = groups[k][0], groups[k][1:]
        days = []
        for r in rest:
            t = r.get("_time")
            label = t.strftime("%a, %b %-d") if isinstance(t, datetime) else None
            if label and label not in days and (not isinstance(first.get("_time"), datetime)
                                                or t.date() != first["_time"].date()):
                days.append(label)
        if days:
            more = f" and {len(days) - show_dates} more dates" if len(days) > show_dates else ""
            note = f"Also {' · '.join(days[:show_dates])}{more}."
            first = {**first, "description": f"{note} {first.get('description') or ''}".strip(), "_series_dates": len(days)}
        out.append(first)
    return out


# ---------------------------------------------------------------------------------------------
# EDM & Electronic hub: Dark Rave / Cyber Club subgenre detection & tagging.
# ---------------------------------------------------------------------------------------------

_EDM_NON_WORDS = re.compile(
    r'(?i)\b(workshop|lesson|class|watch party|bake off|drag brunch|trivia|board game|book club|storytime|puppet|for littles|lego build)\b'
)
_EDM_TITLE_EXCLUSIONS = re.compile(
    r'(?i)\b(open mic|comedy|podcast|tribute band|karaoke|jazz night|blues jam|acoustic session|open jam)\b'
)

_EDM_SUBGENRE_PATTERNS = [
    ('techno', '⚡ Techno', '⚡', re.compile(r'(?i)\b(techno|acid\s+techno|hard\s+techno|industrial(\s+dance|\s+techno)?|ebm\b|dark\s+techno|minimal\s+techno|infra)\b')),
    ('house', '🎛️ House', '🎛️', re.compile(r'(?i)\b(house\s+music|tech\s+house|deep\s+house|afro\s+house|acid\s+house|disco\s+house|prog(ressive)?\s+house|chicago\s+house|re:set|house\s+party)\b')),
    ('bass', '🔊 Bass & D&B', '🔊', re.compile(r'(?i)\b(drum\s*(&|and)\s*bass|\bdnb\b|\bd&b\b|dubstep|riddim|breakbeat|bass\s+music|jungle|elements|bass\s+house)\b')),
    ('synth', '🌌 Synth & Darkwave', '🌌', re.compile(r'(?i)\b(synthwave|darkwave|electro|electropop|modular\s+synth|synthesizer|vaporwave|ebm|cyberpunk|manray)\b')),
    ('club', '🪩 DJ Sets & Dance', '🪩', re.compile(r'(?i)\b(dj\s+(set|night|party|session|lineup|residency)|dance\s+party|club\s+night|all-night\s+dance|rave\b|boiler\s+room|turntablism|guest\s+dj|resident\s+dj)\b')),
]

def _is_edm_event(e):
    title = (e.get("title") or e.get("name") or "").strip()
    v = (e.get("venue") or e.get("_source_venue") or "").strip()
    desc = (e.get("description") or "").strip()
    cat = (e.get("category") or "").lower()

    if cat in ("comedy", "kids", "theater", "sports", "literature", "learning", "art", "markets & festivals"):
        return False
    if _EDM_NON_WORDS.search(title):
        return False
    if _EDM_TITLE_EXCLUSIONS.search(title):
        return False

    from scrapers import infer_music_genre
    tg = infer_music_genre(title, description=desc)
    if tg in ("jazz_blues", "folk_trad", "classical"):
        return False

    g = e.get("music_genre") or infer_music_genre(title, venue=v, description=desc, category=cat)
    if g == "electronic" or cat == "clubbing":
        return True

    text = f"{title} {desc}"
    for _k, _l, _e, rx in _EDM_SUBGENRE_PATTERNS:
        if rx.search(text):
            return True

    if any(club in v.lower() for club in ["manray", "middlesex lounge", "memoire", "zuzu", "bsmnt", "the grand"]):
        return True

    return False


def filter_events_for_hub(hub, events):
    if hub.get("style") == "edm":
        filtered = [e for e in events if _is_edm_event(e)]
        if hub.get("limit"):
            filtered = filtered[:hub["limit"]]
        return filtered

    if hub.get("style") == "camps":
        from camps import load_camps
        return load_camps()["camps"]

    city_filter = hub.get("city_filter")
    cat_filter = hub.get("cat_filter")
    free_only = hub.get("free_only", False)
    time_filter = hub.get("time_filter")
    keyword_filter = hub.get("keyword_filter")

    filtered = []
    for e in events:
        if city_filter and _event_city(e.get("venue"), e.get("_source_venue"), e) != city_filter:
            continue
        if cat_filter:
            c = _effective_category(e)
            bucket = category_bucket(c)
            direct_cat = c.lower()
            if bucket != cat_filter and direct_cat != cat_filter.lower():
                continue
        if free_only and not _is_event_free(e):
            continue
        if time_filter and not _event_date_matches_time_filter(e, time_filter):
            continue
        if keyword_filter and not _event_matches_keywords(e, keyword_filter):
            continue
        filtered.append(e)

    if hub.get("window_days"):
        last_day = datetime.now(EASTERN).date() + timedelta(days=hub["window_days"])
        filtered = [e for e in filtered if (_parse_event_eastern_date(e) or last_day) <= last_day]

    if time_filter == "weekend" and hub.get("limit"):
        # Share the slots across Fri/Sat/Sun so a busy Friday doesn't crowd out the weekend
        per_day, by_day = hub["limit"] // 3, {}
        for e in filtered:
            by_day.setdefault(_parse_event_eastern_date(e), []).append(e)
        filtered = [e for evs in by_day.values() for e in evs[:per_day]]

    # Fallback if tonight has fewer than 5 events: expand up to 3 days out
    if time_filter in ("tonight", "today") and len(filtered) < 5:
        today = datetime.now(EASTERN).date()
        horizon = today + timedelta(days=3)
        for e in events:
            if e in filtered:
                continue
            if city_filter and _event_city(e.get("venue"), e.get("_source_venue"), e) != city_filter:
                continue
            if cat_filter:
                c = _effective_category(e)
                bucket = category_bucket(c)
                direct_cat = c.lower()
                if bucket != cat_filter and direct_cat != cat_filter.lower():
                    continue
            if free_only and not _is_event_free(e):
                continue
            ed = _parse_event_eastern_date(e)
            if ed and today <= ed <= horizon:
                filtered.append(e)
                if len(filtered) >= 25:
                    break

    return filtered


HUBS = {
    # Standalone page for parents: more cards, with ages/details.
    "kids-family-events-boston": {
        "title": "Kids & Family Events in Boston, Cambridge & Somerville",
        "h1": "Kids & Family Events",
        "city_filter": None,
        "cat_filter": "Kids & Family",
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "show_details": True,
        "limit": None,
        "window_days": 21,
        "style": "kids",  # light daycare-style page with age & activity filters
        "subtitle": "Story times, baby & toddler sing-alongs, puppet shows, museum days, farm visits and nature walks for kids, gathered every day from libraries, museums, parks and nature centers around Greater Boston.",
        "og_badge": "KIDS & FAMILY",
        "og_image": "og-kids-family.jpg",
        "query": "#cat=Kids+%26+Family"
    },
    # Summer camps: hand-checked data in camps.json, see camps.py
    "summer-camps": {
        "title": "Summer Camps Near Boston: Prices, Ages & Sign-Up Dates",
        "h1": "Summer Camps",
        "city_filter": None,
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "show_details": True,
        "limit": 500,
        "style": "camps",
        "subtitle": "City programs, YMCAs, nature camps and day camps around Boston, with prices, ages and sign-up dates checked against each camp's own site.",
        "og_badge": "SUMMER CAMPS",
        "og_image": "og-summer-camps.jpg",
        "query": "summer-camps/"
    },
    # Dedicated Cyber Club / Rave guide for electronic shows and club nights
    "boston-edm": {
        "title": "Boston EDM Calendar, Electronic Shows & Club Nights",
        "h1": "Boston EDM & Electronic Shows",
        "city_filter": None,
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "show_details": True,
        "limit": 600,
        "style": "edm",  # Dark Rave / Cyber Club aesthetic with subgenre & area filters
        "subtitle": "Techno, house, bass, drum 'n' bass, synthwave, underground warehouse sets and major DJ headliners across Royale, Big Night Live, The Phoenix Landing, ManRay, The Grand, and beyond.",
        "og_badge": "BOSTON EDM & ELECTRONIC",
        "og_image": "og-boston-edm.jpg",
        "query": "#cat=Music+%26+nightlife&genre=electronic"
    },
    # Flea, night, farmers and holiday markets, craft fairs and festivals
    "markets-festivals-boston": {
        "title": "Markets, Fairs & Festivals in Boston, Cambridge & Somerville",
        "h1": "Markets, Fairs & Festivals",
        "city_filter": None,
        "cat_filter": "Markets & Festivals",
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "show_details": True,
        "limit": 250,
        "subtitle": "Flea markets, night markets, farmers markets, holiday markets and bazaars, craft and vintage fairs, food fests and street festivals around Greater Boston, updated daily.",
        "collapse_series": True,  # a month of Holiday Pop-Up Market days is one card
        "og_badge": "MARKETS & FESTIVALS",
        "og_image": "og-markets-festivals.jpg",
        "query": "#cat=Markets+%26+Festivals"
    },
    # 1. High-Volume Programmatic Intent Pages
    "free-events-boston-this-weekend": {
        "limit": 200,  # three days of events; 60 ran out on Friday
        "title": "Free Events in Boston This Weekend",
        "h1": "Free Events in Boston This Weekend",
        "city_filter": None,
        "cat_filter": None,
        "free_only": True,
        "time_filter": "weekend",
        "keyword_filter": None,
        "subtitle": "Curated list of completely free concerts, community markets, gallery openings, and comedy across Boston, Cambridge, and Somerville this weekend.",
        "og_badge": "FREE THIS WEEKEND",
        "og_image": "og-free-weekend.jpg",
        "query": "#free=1"
    },
    "cambridge-events-tonight": {
        "title": "Tonight in Cambridge: Live Music, Comedy & Shows",
        "h1": "Cambridge Events Tonight",
        "city_filter": "cambridge",
        "cat_filter": None,
        "free_only": False,
        "time_filter": "tonight",
        "keyword_filter": None,
        "subtitle": "What's happening tonight in Cambridge: live gigs, DJ sets, comedy, and theater across Harvard Square, Central Square, and Kendall.",
        "og_badge": "CAMBRIDGE TONIGHT",
        "og_image": "og-cambridge-tonight.jpg",
        "query": "#city=cambridge"
    },
    "live-music-somerville": {
        "title": "Live Music & Concerts in Somerville",
        "h1": "Somerville Live Music",
        "city_filter": "somerville",
        "cat_filter": "Music & nightlife",
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Upcoming live concerts, indie rock gigs, jazz, and acoustic sessions across Somerville venues (The Rockwell, Burren, Crystal Ballroom, Armory).",
        "og_badge": "SOMERVILLE MUSIC",
        "og_image": "og-somerville-music.jpg",
        "query": "#city=somerville&cat=Music+%26+nightlife"
    },
    "board-game-nights-boston": {
        "title": "Board Game Nights & Trivia in Boston & Cambridge",
        "h1": "Boston Board Game Nights & Trivia",
        "city_filter": None,
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": ["board game", "boardgame", "trivia", "game night", "tabletop", "chess", "arcade", "d&d", "dungeons"],
        "subtitle": "Weekly board game meetups, pub trivia, tabletop gaming, arcade tournaments, and social game nights across Greater Boston.",
        "og_badge": "BOARD GAMES & TRIVIA",
        "og_image": "og-board-games.jpg",
        "query": "#q=trivia"
    },
    "boston-events-today": {
        "title": "Boston Events Today & Tonight",
        "h1": "Boston Events Today",
        "city_filter": "boston",
        "cat_filter": None,
        "free_only": False,
        "time_filter": "today",
        "keyword_filter": None,
        "subtitle": "What's happening today in Boston: live music, theater, comedy clubs, and nightlife across Back Bay, Allston, Fenway, and Downtown.",
        "og_badge": "BOSTON TODAY",
        "og_image": "og-boston-today.jpg",
        "query": "#city=boston"
    },
    "boston-events-this-weekend": {
        "limit": 200,  # three days of events; 60 ran out on Friday
        "title": "Things to Do in Boston This Weekend",
        "h1": "Boston This Weekend",
        "city_filter": "boston",
        "cat_filter": None,
        "free_only": False,
        "time_filter": "weekend",
        "keyword_filter": None,
        "subtitle": "Weekend guide to concerts, comedy, nightlife, pop-up markets, and cultural exhibits across Boston.",
        "og_badge": "BOSTON WEEKEND",
        "og_image": "og-boston-weekend.jpg",
        "query": "#city=boston"
    },

    # 2. Neighborhood & Category Directories
    "boston": {
        "title": "Live Boston Events & Concerts",
        "h1": "Boston Events Directory",
        "city_filter": "boston",
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Curated live calendar for concerts, comedy, nightlife, and arts across Boston (Back Bay, Allston, Brighton, Fenway, Seaport, Downtown, South End).",
        "og_badge": "BOSTON DIRECTORY",
        "og_image": "og-boston.jpg",
        "query": "#city=boston"
    },
    "cambridge": {
        "title": "Cambridge Live Music & Events",
        "h1": "Cambridge Events Directory",
        "city_filter": "cambridge",
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Upcoming live shows, concerts, and cultural events across Harvard Square, Central Square, Kendall, and Inman Square.",
        "og_badge": "CAMBRIDGE DIRECTORY",
        "og_image": "og-cambridge.jpg",
        "query": "#city=cambridge"
    },
    "somerville": {
        "title": "Somerville Shows & Live Events",
        "h1": "Somerville Events Directory",
        "city_filter": "somerville",
        "cat_filter": None,
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Independent concerts, comedy, craft markets, and cinema across Davis Square, Union Square, and Assembly Row.",
        "og_badge": "SOMERVILLE DIRECTORY",
        "og_image": "og-somerville.jpg",
        "query": "#city=somerville"
    },
    "music": {
        "title": "Boston & Cambridge Live Music Calendar",
        "h1": "Boston Live Music Guide",
        "city_filter": None,
        "cat_filter": "Music & nightlife",
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Daily live music directory covering indie rock, jazz, punk, electronic, and folk across 40+ local Boston & Cambridge stages.",
        "og_badge": "LIVE MUSIC GUIDE",
        "og_image": "og-music.jpg",
        "query": "#cat=Music+%26+nightlife"
    },
    "comedy": {
        "title": "Boston Stand-Up Comedy & Shows",
        "h1": "Boston Comedy Guide",
        "city_filter": None,
        "cat_filter": "Comedy",
        "free_only": False,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Live stand-up comedy shows, improv, and open mics across The Comedy Studio, The 88 Club, The Rockwell, and Wilbur.",
        "og_badge": "COMEDY & IMPROV",
        "og_image": "og-comedy.jpg",
        "query": "#cat=Comedy"
    },
    "free": {
        "title": "Free Events in Boston & Cambridge",
        "h1": "Free Things to Do in Boston",
        "city_filter": None,
        "cat_filter": None,
        "free_only": True,
        "time_filter": None,
        "keyword_filter": None,
        "subtitle": "Curated list of free museum days, open mics, community workshops, library events, and outdoor gatherings.",
        "og_badge": "FREE EVENTS",
        "og_image": "og-free.jpg",
        "query": "#free=1"
    }
}


def _hub_place_label(city, e):
    """Neighborhood or town for a guide-page card: "Harvard Square, Cambridge", "Belmont"."""
    city_label = CITY_LABELS.get(city, "Boston")
    try:
        sub = resolve_subarea(city, e)[0]
    except Exception:
        sub = ""
    if city == "other":
        return (e.get("locality") or "").strip() or (sub if sub and sub != "Outer Suburbs" else "Greater Boston")
    if not sub or sub.startswith("Other ") or sub == city_label:
        return city_label
    return f"{sub}, {city_label}"


_HUB_CITY_CHIPS = (("all", "All"), ("boston", "Boston"), ("cambridge", "Cambridge"),
                   ("somerville", "Somerville"), ("other", "Nearby towns"))

_HUB_CITY_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.hub-city-chip');
  if (!chips.length) return;
  var cards = document.querySelectorAll('.hub-card');
  var heads = document.querySelectorAll('.hub-day');
  function show(city) {
    var days = {};
    cards.forEach(function (c) {
      var on = city === 'all' || c.dataset.city === city;
      c.hidden = !on;
      if (on) days[c.dataset.day] = 1;
    });
    heads.forEach(function (h) { h.hidden = !days[h.dataset.day]; });
    chips.forEach(function (b) { b.classList.toggle('active', b.dataset.city === city); });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = Object.keys(days).length > 0;
  }
  chips.forEach(function (b) {
    b.addEventListener('click', function () {
      show(b.dataset.city);
      history.replaceState(null, '', b.dataset.city === 'all' ? location.pathname : '#city=' + b.dataset.city);
    });
  });
  var m = location.hash.match(/city=(\\w+)/);
  show(m && document.querySelector('.hub-city-chip[data-city="' + m[1] + '"]') ? m[1] : 'all');
})();
</script>"""


# ---------------------------------------------------------------------------------------------
# Kids & Family hub: a light, daycare-style page with age and activity filters.
# ---------------------------------------------------------------------------------------------

_KID_AGE_BUCKETS = (  # key, label, (lo, hi) years
    ("baby", "👶 Babies (0–1)", (0, 1.5)),
    ("toddler", "🧸 Toddlers (1–3)", (1, 3)),
    ("preschool", "🖍️ Preschool (3–5)", (3, 5)),
    ("bigkid", "🎒 Kids (5–12)", (5, 12)),
)
_KID_AGE_WORDS = (
    ("baby", r"\b(?:bab(?:y|ies)|newborns?|infants?|pre-?walkers?|lap ?(?:sit|time)|wee ones|0\s*[-–]\s*18 months)\b"),
    ("toddler", r"\b(?:toddlers?|walkers|twos|tots?|little ones)\b"),
    ("preschool", r"\b(?:pre-?school(?:ers)?|pre-?k)\b"),
    ("bigkid", r"\b(?:school[- ]age|elementary|tweens?|kids club|grades? k\b)"),
)
_KID_FAMILY_RE = re.compile(r"(?i)\b(?:famil(?:y|ies)|all ages|caregivers|kids & adults|for everyone)\b")
_KID_RANGE_RES = (
    (re.compile(r"(?i)\bages?\s*(\d{1,2}(?:\.\d)?)\s*(?:-|–|—|to)\s*(\d{1,2}(?:\.\d)?)\b"), 1.0),
    (re.compile(r"(?i)\b(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:months?|mos)\b"), 1 / 12),
    (re.compile(r"(?i)\(\s*(\d{1,2}(?:\.\d)?)\s*(?:-|–|—)\s*(\d{1,2}(?:\.\d)?)\s*\)"), 1.0),
)
_KID_GRADE_RE = re.compile(r"(?i)\bgrades?\s*(k|pre-?k|\d{1,2})\s*(?:-|–|—|to|&)\s*(\d{1,2})\b")
_KID_SINGLE_AGE_RE = re.compile(r"(?i)\bages?\s*(\d{1,2})\s*(?:\+|and up|& up|and older)")

_KID_KINDS = (  # key, label, emoji, pattern (checked in order)
    ("show", "Shows", "🎭", r"\b(?:puppets?|theat(?:er|re)|musical|magic(?:ian)?|circus|ballet|film|movie|cinema|perform(?:ance|ers)?|concert)\b"),
    ("story", "Storytime", "📚", r"\b(?:stor(?:y|ies)|storytimes?|read(?:ing|-?alouds?)?|books?|lap ?time|tales|rhymes?)\b"),
    ("music", "Music & movement", "🎵", r"\b(?:sing(?:-?along|ing)?|songs?|music(?:al)?|danc(?:e|ing)|movement|rave|jam|drums?|rhythm|beats|wiggles?|yoga|groove|ukulele|guitar)\b"),
    ("nature", "Nature & animals", "🌿", r"\b(?:nature|walks?|hikes?|owls?|birds?|birding|gardens?|farm|goats?|animals?|zoo|aquarium|arboretum|ponds?|leaf|leaves|trails?|outdoors?|bugs?|insects?|trees?|turkeys?|fish|penguins?|seals?|whales?)\b"),
    ("make", "Arts, crafts & STEAM", "🎨", r"\b(?:crafts?|art|arts|make|makers?|lego|paint(?:ing)?|draw(?:ing)?|build(?:ing|ers)?|steam|stem|science|scientists?|cook(?:ing)?|bak(?:e|ing)|sew(?:ing)?|clay|creat(?:e|ive|ivity)|engineer(?:ing)?|robots?|coding|experiments?|dinosaurs?|museum)\b"),
    ("play", "Play & games", "🧸", r"\b(?:play(?:group|time|date)?s?|open gym|drop-?in|games?|puzzles?|blocks|chess|pokemon|pokémon|playground|sensory)\b"),
)
_KID_KIND_RES = [(k, lbl, emo, re.compile("(?i)" + pat)) for k, lbl, emo, pat in _KID_KINDS]
_KID_OTHER = ("other", "Everything else", "🎈")


def _kid_tags(e):
    """(age bucket keys, kind key, emoji, age label) for a Kids & Family card, from its title and
    description: "Toddler Tales (ages 1.5-3)" -> (["toddler"], "story", "📚", "Ages 1.5–3")."""
    title = e.get("name") or e.get("title") or ""
    desc = (e.get("description") or "")[:300]
    blob = f"{title} {desc}"
    ages, label = set(), ""
    spans = []
    # ages from the title; else from the description's "ages 2-5" / "for babies" wording
    for rx, scale in _KID_RANGE_RES:
        for m in rx.finditer(title) or ():
            lo, hi = float(m.group(1)) * scale, float(m.group(2)) * scale
            if 0 <= lo <= hi <= 18:
                spans.append((lo, hi))
                if not label:
                    unit = " months" if scale != 1.0 else ""
                    label = (f"Ages {m.group(1)}–{m.group(2)}" if not unit else f"{m.group(1)}–{m.group(2)} months")
    for m in _KID_GRADE_RE.finditer(title):
        g0 = 0 if m.group(1).lower() in ("k", "pre-k", "prek") else int(m.group(1))
        g1 = int(m.group(2))
        if g0 <= g1 <= 12:
            spans.append((g0 + 5, g1 + 6))
            label = label or f"Grades {m.group(1).upper()}–{g1}"
    m = _KID_SINGLE_AGE_RE.search(title)
    if m and int(m.group(1)) <= 12:
        spans.append((int(m.group(1)), 12))
        label = label or f"Ages {m.group(1)}+"
    for lo, hi in spans:
        for key, _lbl, (blo, bhi) in _KID_AGE_BUCKETS:
            if lo < bhi and hi > blo or (lo == hi and blo <= lo <= bhi):
                ages.add(key)
    if not spans:
        for key, pat in _KID_AGE_WORDS:
            if re.search("(?i)" + pat, title):
                ages.add(key)
    if not spans and not ages and desc:
        for rx, scale in _KID_RANGE_RES[:2]:  # "(3-5)" alone in prose is too loose
            for m in rx.finditer(desc):
                lo, hi = float(m.group(1)) * scale, float(m.group(2)) * scale
                if 0 <= lo <= hi <= 18:
                    spans.append((lo, hi))
        for m in _KID_GRADE_RE.finditer(desc):
            g0 = 0 if m.group(1).lower() in ("k", "pre-k", "prek") else int(m.group(1))
            if g0 <= int(m.group(2)) <= 12:
                spans.append((g0 + 5, int(m.group(2)) + 6))
        for lo, hi in spans:
            for key, _lbl, (blo, bhi) in _KID_AGE_BUCKETS:
                if lo < bhi and hi > blo:
                    ages.add(key)
        if not spans:
            for key, pat in _KID_AGE_WORDS:
                if re.search("(?i)" + pat, desc):
                    ages.add(key)
    if not ages or _KID_FAMILY_RE.search(title):
        ages.add("family")
    kind = _KID_OTHER
    for k, lbl, emo, rx in _KID_KIND_RES:
        if rx.search(title):
            kind = (k, lbl, emo)
            break
    else:
        for k, lbl, emo, rx in _KID_KIND_RES:
            if rx.search(blob):
                kind = (k, lbl, emo)
                break
    order = [k for k, _l, _r in _KID_AGE_BUCKETS] + ["family"]
    return sorted(ages, key=order.index), kind[0], kind[2], label


_KID_AGE_PILL = {"baby": "Babies (0–1)", "toddler": "Toddlers (1–3)", "preschool": "Preschool (3–5)", "bigkid": "Kids (5–12)", "family": "All ages"}

_KIDS_FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
               '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
               '<link href="https://fonts.googleapis.com/css2?family=Baloo+2:wght@600;700;800&family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">')

_KIDS_HERO_ART = """<svg class="kids-hero-art" viewBox="0 0 900 220" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
  <defs><linearGradient id="kh-sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#bfe5fb"/><stop offset="1" stop-color="#e6f5fd"/></linearGradient></defs>
  <rect width="900" height="220" fill="url(#kh-sky)"/>
  <g opacity="0.9" fill="none" stroke-linecap="round" stroke-width="16">
    <path d="M590,220 A160,160 0 0 1 910,220" stroke="#ffb3b3"/><path d="M606,220 A144,144 0 0 1 894,220" stroke="#ffd59e"/>
    <path d="M622,220 A128,128 0 0 1 878,220" stroke="#fff1a8"/><path d="M638,220 A112,112 0 0 1 862,220" stroke="#c6efc9"/>
    <path d="M654,220 A96,96 0 0 1 846,220" stroke="#b9dcff"/><path d="M670,220 A80,80 0 0 1 830,220" stroke="#dcc8ff"/>
  </g>
  <g transform="translate(92,62)"><circle r="34" fill="#ffd45c"/>
    <g stroke="#ffd45c" stroke-width="7" stroke-linecap="round">
      <line x1="0" y1="-50" x2="0" y2="-62"/><line x1="0" y1="50" x2="0" y2="62"/><line x1="-50" y1="0" x2="-62" y2="0"/><line x1="50" y1="0" x2="62" y2="0"/>
      <line x1="35" y1="35" x2="44" y2="44"/><line x1="-35" y1="35" x2="-44" y2="44"/><line x1="35" y1="-35" x2="44" y2="-44"/><line x1="-35" y1="-35" x2="-44" y2="-44"/></g>
    <circle cx="-11" cy="-6" r="4" fill="#6b4b1f"/><circle cx="11" cy="-6" r="4" fill="#6b4b1f"/>
    <path d="M-13,9 Q0,21 13,9" stroke="#6b4b1f" stroke-width="4" fill="none" stroke-linecap="round"/>
    <circle cx="-20" cy="7" r="5" fill="#ffab7a" opacity="0.6"/><circle cx="20" cy="7" r="5" fill="#ffab7a" opacity="0.6"/></g>
  <g fill="#ffffff"><g transform="translate(250,58)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g>
    <g transform="translate(470,40) scale(0.7)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g>
    <g transform="translate(800,70) scale(0.8)"><ellipse cx="0" cy="10" rx="58" ry="20"/><circle cx="-24" cy="0" r="22"/><circle cx="8" cy="-10" r="28"/><circle cx="34" cy="4" r="18"/></g></g>
  <g transform="translate(560,40) rotate(12)"><polygon points="0,-34 26,0 0,40 -26,0" fill="#ff8fab"/><line x1="0" y1="-34" x2="0" y2="40" stroke="#fff" stroke-width="3"/><line x1="-26" y1="0" x2="26" y2="0" stroke="#fff" stroke-width="3"/>
    <path d="M0,40 q-14,22 6,38 q18,16 -2,34" stroke="#7a6a9a" stroke-width="2.5" fill="none"/>
    <path d="M-4,66 l-10,-4 l4,10 z M2,96 l-10,-2 l6,9 z" fill="#ffd45c"/></g>
  <g font-family="Baloo 2, Trebuchet MS, sans-serif" font-weight="800" font-size="34" text-anchor="middle">
    <g transform="translate(150,172) rotate(-6)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#ff9aa2"/><text y="12" fill="#fff">A</text></g>
    <g transform="translate(206,178) rotate(5)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#7cc6f5"/><text y="12" fill="#fff">B</text></g>
    <g transform="translate(178,124) rotate(-2)"><rect x="-27" y="-27" width="54" height="54" rx="9" fill="#8fd6a8"/><text y="12" fill="#fff">C</text></g>
  </g>
  <g transform="translate(380,182)"><rect x="-70" y="-9" width="140" height="18" rx="9" fill="#b9a3ff"/><polygon points="70,-9 92,0 70,9" fill="#f3d9b1"/><polygon points="84,-3 92,0 84,3" fill="#5b4a8a"/><rect x="-70" y="-9" width="22" height="18" rx="9" fill="#9a84e8"/></g>
  <g fill="#ffd45c"><path d="M330,120 l5,11 12,2 -9,8 2,12 -10,-6 -10,6 2,-12 -9,-8 12,-2 z"/><path d="M700,30 l3,7 8,1 -6,5 2,8 -7,-4 -7,4 2,-8 -6,-5 8,-1 z"/></g>
  <path d="M0,206 Q150,192 300,206 T600,206 T900,206 L900,220 L0,220 Z" fill="#a8dcb1"/>
</svg>"""

_KIDS_CSS = """
  body.kids-hub {
    --bg: #fbf6ec; --card: #ffffff; --card-hover: #ffffff; --fg: #3a3550; --muted: #7c7590;
    --accent: #2f86c8; --border: #efe4d2; --green: #2f9e5b; --sky: #d6eefc; --sky-deep: #8fcdf0;
    background: #fbf6ec radial-gradient(#efe2cc 1.2px, transparent 1.4px) 0 0 / 22px 22px;
    font-family: "Nunito", "Avenir Next Rounded", "Avenir Next", "Trebuchet MS", system-ui, sans-serif;
  }
  .kids-hub h1, .kids-hub h2, .kids-hub h3, .kids-hub .logo, .kids-hub .kid-chip, .kids-hub .cta-btn {
    font-family: "Baloo 2", "Avenir Next Rounded", "Trebuchet MS", system-ui, sans-serif;
  }
  .kids-hub header {
    background: #ffffffd9;
    backdrop-filter: blur(8px);
    border-bottom: 2px dashed #e7d8bf;
    position: sticky;
    top: env(safe-area-inset-top, 0px);
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 16px;
    padding: 12px 20px;
  }
  .kids-hub .logo { color: var(--fg); font-size: 18px; font-weight: 800; white-space: nowrap; text-decoration: none; }
  .kids-hub .logo span { color: #f27e9a; }
  .kids-hub .kids-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    flex-wrap: wrap;
  }
  .kids-hub .kids-nav a {
    box-sizing: border-box;
    color: var(--muted);
    text-decoration: none;
    padding: 6px 14px;
    border-radius: 999px;
    font-weight: 700;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    border: 2px solid transparent;
    white-space: nowrap;
  }
  .kids-hub .kids-nav a:hover {
    color: var(--accent);
    background: #fffaf2;
    border-color: #efe4d2;
  }
  .kids-hub .kids-nav a.active {
    background: var(--sky);
    border-color: #6dbbea;
    color: #1f5d88;
    box-shadow: 0 3px 0 #9fd3f2;
    font-weight: 800;
  }
  .kids-hub main { max-width: 980px; padding-top: 22px; }
  .kids-hub .hero { border: 0; padding: 0; margin-bottom: 18px; background: #fff; border-radius: 28px;
    overflow: hidden; box-shadow: 0 6px 0 #e9dcc6, 0 14px 30px rgba(120, 100, 60, 0.10); }
  .kids-hero-art { display: block; width: 100%; height: 190px; }
  .kids-hero-copy { padding: 18px 22px 24px; }
  .kids-hub .hero h1 { font-size: clamp(30px, 6vw, 44px); line-height: 1.05; margin: 0 0 8px; color: #2b5d86; letter-spacing: -0.01em; }
  .kids-hub .hero h1 .wave { display: inline-block; transform-origin: 70% 70%; animation: kid-wave 2.4s ease-in-out infinite; }
  @keyframes kid-wave { 0%, 60%, 100% { transform: rotate(0); } 10%, 30% { transform: rotate(14deg); } 20%, 40% { transform: rotate(-8deg); } }
  @media (prefers-reduced-motion: reduce) { .kids-hub .hero h1 .wave { animation: none; } }
  .kids-hub .hero h1 small { display: block; font-size: 0.45em; color: #b08a5a; font-weight: 700; letter-spacing: 0.01em; margin-top: 4px; }
  .kids-hub .hero p { color: var(--muted); font-size: 16px; margin-bottom: 16px; }
  .kids-hub .cta-btn { background: #2f86c8; color: #fff; box-shadow: 0 4px 0 #1f6aa3; font-weight: 700; font-size: 16px; padding: 9px 22px; }
  .kids-hub .cta-btn:hover { transform: translateY(-1px); filter: brightness(1.05); }
  .kids-stats { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 0 0 16px; }
  .kids-stat { background: var(--sky); color: #24648f; border-radius: 999px; padding: 4px 14px; font-weight: 800; font-size: 14px; }
  .kids-filters { background: #fff; border-radius: 22px; padding: 14px 16px 6px; margin-bottom: 18px;
    box-shadow: 0 4px 0 #e9dcc6; border: 2px solid #f1e6d4; }
  .kid-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
  .kid-filter-label { font-weight: 800; color: #b08a5a; font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; min-width: 58px; }
  .kid-chip { font-size: 15px; font-weight: 700; padding: 4px 14px 3px; border-radius: 999px; cursor: pointer;
    border: 2px solid #e6dccb; background: #fffaf2; color: var(--fg); transition: transform 0.12s ease, background 0.12s ease; }
  .kid-chip:hover { transform: translateY(-1px); border-color: var(--sky-deep); }
  .kid-chip.active { background: var(--sky); border-color: #6dbbea; color: #1f5d88; box-shadow: 0 3px 0 #9fd3f2; }
  .kids-hub .hub-day { border: 0; margin: 26px 0 2px; padding: 0; font-size: 22px; color: #2b5d86; display: flex; align-items: center; gap: 10px; }
  .kids-hub .hub-day::before { content: ""; width: 34px; height: 22px; flex: none;
    background: radial-gradient(circle at 30% 60%, #fff 9px, transparent 10px), radial-gradient(circle at 62% 45%, #fff 11px, transparent 12px), radial-gradient(circle at 82% 66%, #fff 8px, transparent 9px), var(--sky);
    border-radius: 12px; }
  .kids-hub .hub-day::after { content: ""; flex: 1; border-bottom: 3px dotted #e2d3ba; }
  .kids-hub .hub-grid { gap: 14px; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 640px) { .kids-hub .hub-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .kids-hub .hub-card a, .kids-hub .hub-desc { overflow-wrap: anywhere; }
  .kids-hub .hub-card { border: 2px solid #f1e6d4; border-radius: 22px; padding: 0; overflow: hidden; justify-content: flex-start; min-width: 0;
    box-shadow: 0 4px 0 #ece0cb; transition: transform 0.15s ease, box-shadow 0.15s ease; }
  .kids-hub .hub-card:hover { transform: translateY(-2px) rotate(-0.3deg); box-shadow: 0 7px 0 #e3d4ba; border-color: #e6d6bb; }
  .kid-card-band { height: 10px; background: var(--band, #d6eefc); }
  .kid-card-body { padding: 12px 16px 14px; display: flex; gap: 12px; }
  .kid-emoji { flex: none; width: 46px; height: 46px; border-radius: 16px; display: grid; place-items: center;
    font-size: 24px; background: var(--band, #d6eefc); }
  .kid-card-main { min-width: 0; flex: 1; }
  .kids-hub .hub-card-head { margin-bottom: 4px; }
  .kids-hub .hub-date { color: #2f86c8; font-size: 13px; font-weight: 800; letter-spacing: 0.02em; text-transform: none; }
  .kids-hub .hub-title { font-family: "Nunito", system-ui, sans-serif; font-weight: 800; font-size: 16.5px; margin-bottom: 6px; }
  .kids-hub .hub-title a { color: #3a3550; }
  .kids-hub .hub-title a:hover { color: #2f86c8; }
  .kids-hub .hub-meta { flex-wrap: wrap; font-size: 13px; }
  .kids-hub .hub-desc { color: #6f6884; font-size: 13.5px; }
  .kid-ages { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
  .kid-age { font-size: 12px; font-weight: 800; padding: 1px 9px; border-radius: 999px; background: #fff4dc; color: #9a6b24; border: 1px solid #f3dfb3; }
  .kids-hub .badge-free { background: #dff5e6; color: #23824a; font-size: 12px; font-weight: 800; }
  .kids-hub .badge-price { background: #f4efe6; color: #6f6884; font-size: 12px; }
  .kid-city-section {
    grid-column: 1 / -1;
    margin-bottom: 22px;
    background: #ffffff;
    border: 1px solid #efe4d2;
    border-left: 4px solid var(--city-color, #2f86c8);
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 4px 0 #ede1cd;
  }
  .kid-city-section[data-city="cambridge"] { --city-color: #f43f5e; }
  .kid-city-section[data-city="somerville"] { --city-color: #f59e0b; }
  .kid-city-section[data-city="boston"] { --city-color: #2f86c8; }
  .kid-city-section[data-city="other"] { --city-color: #8b5cf6; }
  .kid-city-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 10px;
    margin-bottom: 14px;
    border-bottom: 2px dashed #f2e7d5;
  }
  .kid-city-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--city-color);
    font-size: 13.5px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .kid-city-pill .city-dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--city-color);
    box-shadow: 0 0 6px var(--city-color);
    display: inline-block;
  }
  .kid-city-head .count {
    background: #fbf6ec;
    color: #7c7590;
    font-size: 12px;
    font-weight: 800;
    padding: 2px 9px;
    border-radius: 999px;
    border: 1px solid #efe4d2;
  }
  .kid-city-cards {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  @media (min-width: 640px) {
    .kid-city-cards {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  .kid-k-story { --band: #fff1b8; } .kid-k-music { --band: #e7dcff; } .kid-k-nature { --band: #d4f3e1; }
  .kid-k-make { --band: #ffe0cf; } .kid-k-show { --band: #ffd6e6; } .kid-k-play { --band: #d6eefc; } .kid-k-other { --band: #f1e6d4; }
  .kids-hub .no-hub-events { text-align: center; color: var(--muted); font-size: 16px; padding: 30px 0; }
  .kids-hub .kids-later { text-align: center; margin: 28px 0 8px; }
  .kids-hub footer { border-top: 2px dashed #e7d8bf; }
  @media (max-width: 640px) {
    .kids-hub header {
      padding: 10px 14px;
      gap: 8px 10px;
    }
    .kids-hub .logo {
      font-size: 16px;
    }
    .kids-hub .kids-nav {
      gap: 5px;
      font-size: 13px;
    }
    .kids-hub .kids-nav a {
      padding: 5px 10px;
      min-height: 34px;
    }
    .kids-hero-art { height: 130px; }
    .kid-filter-label { min-width: 100%; }
  }
"""

_KIDS_FILTER_JS = """<script>
(function () {
  var cards = document.querySelectorAll('.hub-card');
  var laterBox = document.getElementById('kids-later');
  var laterDays = laterBox ? JSON.parse(laterBox.dataset.days || '[]') : [];
  // The When buttons are made here, not in the page, so "Today" and the week labels stay right
  // on a page built days ago. Weeks run Monday to Sunday and dates are Boston's.
  var ranges = {};
  (function () {
    var row = document.getElementById('kid-when');
    if (!row) return;
    var parts = {};
    new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' })
      .formatToParts(new Date()).forEach(function (p) { parts[p.type] = p.value; });
    var today = parts.year + '-' + parts.month + '-' + parts.day;
    function utc(iso) { return new Date(iso + 'T12:00:00Z'); }
    function addDays(iso, n) { var d = utc(iso); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
    function month(iso) { return utc(iso).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' }); }
    function dayNum(iso) { return String(parseInt(iso.slice(8), 10)); }
    function label(a, b) {
      if (a === b) return month(a) + ' ' + dayNum(a);
      return month(a) + ' ' + dayNum(a) + '–' + (month(a) === month(b) ? '' : month(b) + ' ') + dayNum(b);
    }
    var days = laterDays.slice();
    cards.forEach(function (c) { if (c.dataset.day) days.push(c.dataset.day); });
    if (!days.length) return;
    var last = days.reduce(function (a, b) { return a > b ? a : b; });
    var seen = {};
    function add(val, text, from, to) {
      var key = from + to;
      if (seen[key] || !days.some(function (d) { return d >= from && d <= to; })) return;
      seen[key] = 1;
      ranges[val] = [from, to];
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'kid-chip';
      b.dataset.group = 'when';
      b.dataset.val = val;
      b.textContent = text;
      row.appendChild(b);
    }
    var fromMonday = (utc(today).getUTCDay() + 6) % 7;
    var sunday = addDays(today, 6 - fromMonday);
    var friday = addDays(today, 4 - fromMonday);
    add('today', 'Today', today, today);
    add('weekend', 'This weekend', friday > today ? friday : today, sunday);
    add('thisweek', 'This week', today, sunday);
    for (var monday = addDays(sunday, 1); monday <= last; monday = addDays(monday, 7)) {
      var end = addDays(monday, 6);
      if (end > last) end = last;
      add(monday, label(monday, end), monday, end);
    }
  })();
  var chips = document.querySelectorAll('.kid-chip');
  if (!chips.length) return;
  var heads = document.querySelectorAll('.hub-day');
  var citySecs = document.querySelectorAll('.kid-city-section');
  // Later days (past the first two weeks) load once: near the bottom of the list, on the button,
  // or as soon as a filter is used, so filtered results are complete.
  var laterLoad = null;
  function loadLater() {
    if (!laterBox) return Promise.resolve();
    if (!laterLoad) {
      var btn = laterBox.querySelector('button');
      if (btn) { btn.disabled = true; btn.textContent = 'Loading more dates…'; }
      laterLoad = fetch(laterBox.dataset.src).then(function (r) { return r.ok ? r.text() : ''; }).then(function (html) {
        if (!html) { if (btn) { btn.disabled = false; btn.textContent = 'Show more dates →'; } laterLoad = null; return; }
        laterBox.insertAdjacentHTML('beforebegin', html);
        laterBox.remove();
        laterBox = null;
        cards = document.querySelectorAll('.hub-card');
        heads = document.querySelectorAll('.hub-day');
        citySecs = document.querySelectorAll('.kid-city-section');
        render(false);
      }).catch(function () { laterLoad = null; });
    }
    return laterLoad;
  }
  if (laterBox) {
    laterBox.querySelector('button').addEventListener('click', loadLater);
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es, obs) {
        if (es.some(function (e) { return e.isIntersecting; })) { obs.disconnect(); loadLater(); }
      }, { rootMargin: '1200px 0px' }).observe(laterBox);
    }
  }
  var state = { when: 'all', city: 'all', age: 'all', kind: 'all', price: 'all' };
  function matches(c) {
    if (state.when !== 'all') {
      var range = ranges[state.when], day = c.dataset.day || '';
      if (!range || day < range[0] || day > range[1]) return false;
    }
    if (state.city !== 'all' && c.dataset.city !== state.city) return false;
    if (state.age !== 'all' && (' ' + c.dataset.age + ' ').indexOf(' ' + state.age + ' ') === -1) return false;
    if (state.kind !== 'all' && c.dataset.kind !== state.kind) return false;
    if (state.price !== 'all' && c.dataset.price !== state.price) return false;
    return true;
  }
  function render(save) {
    var days = {}, n = 0;
    cards.forEach(function (c) { var on = matches(c); c.hidden = !on; if (on) { days[c.dataset.day] = 1; n++; } });
    heads.forEach(function (h) { h.hidden = !days[h.dataset.day]; });
    citySecs.forEach(function (sec) {
      var visible = sec.querySelectorAll('.hub-card:not([hidden])').length;
      sec.hidden = (visible === 0);
      var cCount = sec.querySelector('.kid-city-head .count');
      if (cCount) cCount.textContent = visible;
    });
    chips.forEach(function (b) { b.classList.toggle('active', state[b.dataset.group] === b.dataset.val); });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0 || !!laterBox;  // still loading the later days
    if (save) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }
  chips.forEach(function (b) {
    b.addEventListener('click', function () { state[b.dataset.group] = b.dataset.val; render(true); loadLater(); });
  });
  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length === 2 && state.hasOwnProperty(kv[0]) && document.querySelector('.kid-chip[data-group="' + kv[0] + '"][data-val="' + kv[1] + '"]')) state[kv[0]] = kv[1];
  });
  render(false);
  if (Object.keys(state).some(function (k) { return state[k] !== 'all'; })) loadLater();
})();
</script>"""


# ---------------------------------------------------------------------------------------------
# EDM & Electronic hub: Dark Rave / Cyber Club custom aesthetic
# ---------------------------------------------------------------------------------------------

def _edm_tags(e):
    title = (e.get("title") or e.get("name") or "")
    desc = (e.get("description") or "")
    v = (e.get("venue") or e.get("_source_venue") or "")
    text = f"{title} {v} {desc}"
    sub = "club"
    sub_label = "DJ Sets & Dance"
    sub_emoji = "🪩"
    for k, lbl, emo, rx in _EDM_SUBGENRE_PATTERNS:
        if rx.search(text):
            sub, sub_label, sub_emoji = k, lbl, emo
            break

    city = _event_city(e.get("venue"), e.get("_source_venue"), e)
    v_low = v.lower()
    neigh = "Central Sq" if any(x in v_low for x in ["phoenix landing", "middlesex", "manray", "zuzu", "middle east"]) else \
            "Seaport" if any(x in v_low for x in ["the grand", "seaport", "envoy", "lookout"]) else \
            "Downtown" if any(x in v_low for x in ["royale", "big night live", "downtown", "theatre district", "theater district", "icon"]) else \
            "Somerville" if city == "somerville" else \
            "Boston" if city == "boston" else \
            "Cambridge" if city == "cambridge" else "Greater Boston"

    t_obj = e.get("_time")
    now_est = datetime.now(EASTERN)
    time_tag = "upcoming"
    if isinstance(t_obj, datetime):
        t_est = t_obj.astimezone(EASTERN) if t_obj.tzinfo else t_obj
        if t_est.date() == now_est.date():
            time_tag = "tonight"
        elif t_est.weekday() in (4, 5, 6) and 0 <= (t_est.date() - now_est.date()).days < 7:
            time_tag = "weekend"

    is_free = _is_event_free(e)
    return sub, sub_label, sub_emoji, neigh, time_tag, is_free


_EDM_FONTS = ""

_EDM_HERO_ART = """<svg class="edm-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="edm-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#04050a"/>
      <stop offset="60%" stop-color="#0a0d1c"/>
      <stop offset="100%" stop-color="#12182e"/>
    </linearGradient>
    <linearGradient id="edm-neon" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#00f0ff"/>
      <stop offset="50%" stop-color="#a855f7"/>
      <stop offset="100%" stop-color="#ff007f"/>
    </linearGradient>
    <linearGradient id="bar-grad" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.2"/>
      <stop offset="60%" stop-color="#00f0ff" stop-opacity="0.8"/>
      <stop offset="100%" stop-color="#ff007f"/>
    </linearGradient>
    <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="5" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="900" height="200" fill="url(#edm-sky)"/>
  <g opacity="0.35" stroke="#00f0ff" stroke-width="1">
    <line x1="450" y1="40" x2="0" y2="200"/>
    <line x1="450" y1="40" x2="120" y2="200"/>
    <line x1="450" y1="40" x2="240" y2="200"/>
    <line x1="450" y1="40" x2="350" y2="200"/>
    <line x1="450" y1="40" x2="450" y2="200"/>
    <line x1="450" y1="40" x2="550" y2="200"/>
    <line x1="450" y1="40" x2="660" y2="200"/>
    <line x1="450" y1="40" x2="780" y2="200"/>
    <line x1="450" y1="40" x2="900" y2="200"/>
    <line x1="200" y1="130" x2="700" y2="130" opacity="0.5"/>
    <line x1="120" y1="160" x2="780" y2="160" opacity="0.7"/>
    <line x1="0" y1="200" x2="900" y2="200" stroke-width="2" opacity="0.9"/>
  </g>
  <g fill="url(#bar-grad)">
    <rect x="40" y="110" width="8" height="70" rx="3"/>
    <rect x="54" y="90" width="8" height="90" rx="3"/>
    <rect x="68" y="130" width="8" height="50" rx="3"/>
    <rect x="82" y="75" width="8" height="105" rx="3"/>
    <rect x="96" y="105" width="8" height="75" rx="3"/>
    <rect x="110" y="60" width="8" height="120" rx="3"/>
    <rect x="124" y="95" width="8" height="85" rx="3"/>
    <rect x="138" y="125" width="8" height="55" rx="3"/>
    <rect x="152" y="80" width="8" height="100" rx="3"/>
    <rect x="166" y="115" width="8" height="65" rx="3"/>
    <rect x="180" y="70" width="8" height="110" rx="3"/>
    <rect x="194" y="135" width="8" height="45" rx="3"/>
  </g>
  <g fill="url(#bar-grad)">
    <rect x="698" y="135" width="8" height="45" rx="3"/>
    <rect x="712" y="70" width="8" height="110" rx="3"/>
    <rect x="726" y="115" width="8" height="65" rx="3"/>
    <rect x="740" y="80" width="8" height="100" rx="3"/>
    <rect x="754" y="125" width="8" height="55" rx="3"/>
    <rect x="768" y="95" width="8" height="85" rx="3"/>
    <rect x="782" y="60" width="8" height="120" rx="3"/>
    <rect x="796" y="105" width="8" height="75" rx="3"/>
    <rect x="810" y="75" width="8" height="105" rx="3"/>
    <rect x="824" y="130" width="8" height="50" rx="3"/>
    <rect x="838" y="90" width="8" height="90" rx="3"/>
    <rect x="852" y="110" width="8" height="70" rx="3"/>
  </g>
  <g transform="translate(450, 95)" filter="url(#neon-glow)">
    <ellipse rx="130" ry="42" fill="none" stroke="#00f0ff" stroke-width="2.5" opacity="0.8"/>
    <ellipse rx="100" ry="32" fill="none" stroke="#a855f7" stroke-width="2" opacity="0.9"/>
    <ellipse rx="70" ry="22" fill="none" stroke="#ff007f" stroke-width="2" opacity="0.85"/>
    <ellipse rx="35" ry="11" fill="none" stroke="#00f0ff" stroke-width="3" opacity="0.95"/>
    <circle r="6" fill="#00f0ff"/>
    <line x1="-120" y1="0" x2="-260" y2="-60" stroke="#ff007f" stroke-width="2" opacity="0.6"/>
    <line x1="120" y1="0" x2="260" y2="-60" stroke="#00f0ff" stroke-width="2" opacity="0.6"/>
  </g>
  <g transform="translate(450, 26)">
    <rect x="-95" y="-12" width="190" height="24" rx="12" fill="#000" stroke="#00f0ff" stroke-width="1.5" opacity="0.85"/>
    <text x="0" y="4" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="10.5" font-weight="700" fill="#00f0ff" letter-spacing="1">BOSTON RAVE FREQ</text>
  </g>
</svg>"""

_EDM_CSS = """
  .edm-hub {
    --bg: #07080f;
    --card: #0d101d;
    --card-hover: #13172b;
    --fg: #eef2fb;
    --muted: #8893a7;
    --cyan: #00f0ff;
    --pink: #ff007f;
    --purple: #a855f7;
    --lime: #00ff88;
    --yellow: #fcee0a;
    --border: rgba(0, 240, 255, 0.16);
    background: var(--bg) !important;
    color: var(--fg) !important;
  }
  .edm-hub h1, .edm-hub h2, .edm-hub h3, .edm-hub .logo, .edm-hub .edm-chip, .edm-hub .cta-btn, .edm-hub .edm-card-subgenre, .edm-filter-label {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .edm-hub header {
    background: rgba(7, 8, 15, 0.9) !important;
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border) !important;
  }
  .edm-hub .logo { color: #fff !important; font-weight: 800; }
  .edm-hub .logo span {
    color: var(--cyan) !important;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
  }
  .edm-hub .hub-nav a { color: var(--muted); }
  .edm-hub .hub-nav a.active, .edm-hub .hub-nav a:hover { color: var(--cyan); text-shadow: 0 0 8px rgba(0,240,255,0.4); }
  .edm-hub main { max-width: 980px; padding-top: 22px; }
  .edm-hub .hero {
    border: 1px solid var(--border);
    background: #090b16;
    border-radius: 24px;
    overflow: hidden;
    box-shadow: 0 0 30px rgba(0, 240, 255, 0.08), 0 12px 40px rgba(0,0,0,0.6);
    margin-bottom: 22px;
  }
  .edm-hero-art { display: block; width: 100%; height: 190px; }
  .edm-hero-copy { padding: 20px 24px 26px; text-align: center; }
  .edm-hub .hero h1 {
    font-size: clamp(28px, 5.5vw, 44px);
    font-weight: 900;
    margin: 0 0 8px;
    letter-spacing: -0.02em;
    background: linear-gradient(135deg, #fff 30%, var(--cyan) 75%, var(--pink) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .edm-hub .hero h1 small {
    display: block;
    font-size: 0.44em;
    color: var(--cyan);
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    margin-top: 6px;
    -webkit-text-fill-color: var(--cyan);
    text-shadow: 0 0 8px rgba(0, 240, 255, 0.4);
  }
  .edm-hub .hero p {
    color: var(--muted);
    font-size: 15px;
    max-width: 680px;
    margin: 0 auto 18px;
    line-height: 1.5;
  }
  .edm-stats { display: flex; gap: 10px; justify-content: center; flex-wrap: wrap; margin: 0 0 18px; }
  .edm-stat {
    background: rgba(0, 240, 255, 0.08);
    border: 1px solid rgba(0, 240, 255, 0.25);
    color: #d8f8ff;
    border-radius: 999px;
    padding: 4px 14px;
    font-weight: 700;
    font-size: 13px;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.15);
  }
  .edm-hub .cta-btn {
    background: linear-gradient(135deg, var(--cyan), #0077ff);
    color: #04050a;
    font-weight: 800;
    font-size: 15px;
    padding: 8px 22px;
    border-radius: 8px;
    box-shadow: 0 0 16px rgba(0, 240, 255, 0.4);
    text-decoration: none;
    display: inline-block;
  }
  .edm-hub .cta-btn:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .edm-filters {
    background: #090c18;
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 16px 18px 8px;
    margin-bottom: 22px;
    box-shadow: 0 0 20px rgba(0, 240, 255, 0.05);
  }
  .edm-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .edm-filter-label {
    font-weight: 700;
    color: var(--cyan);
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    min-width: 58px;
  }
  .edm-chip {
    font-size: 13px;
    font-weight: 600;
    padding: 6px 14px;
    border-radius: 999px;
    cursor: pointer;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: #0d1122;
    color: var(--fg);
    letter-spacing: normal;
    transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .edm-chip:hover {
    transform: translateY(-1px);
    border-color: var(--cyan);
    box-shadow: 0 0 10px rgba(0, 240, 255, 0.3);
  }
  .edm-chip.active {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.2), rgba(168, 85, 247, 0.25));
    border-color: var(--cyan);
    color: #fff;
    box-shadow: 0 0 14px rgba(0, 240, 255, 0.45);
  }
  .edm-hub .hub-day {
    margin: 32px 0 14px;
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 12px;
    border: 0;
    padding: 0;
  }
  .edm-hub .hub-day::before {
    content: "⚡";
    font-size: 16px;
    filter: drop-shadow(0 0 6px var(--cyan));
  }
  .edm-hub .hub-day::after {
    content: "";
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--cyan), rgba(168, 85, 247, 0.3) 60%, transparent);
  }
  .edm-city-section {
    background: rgba(13, 16, 29, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 16px;
    padding: 14px;
    margin-bottom: 16px;
  }
  .edm-city-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    padding: 0 4px;
  }
  .edm-city-pill {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    padding: 3px 10px;
    border-radius: 999px;
  }
  .edm-city-pill.city-boston {
    background: rgba(0, 240, 255, 0.15);
    color: var(--cyan);
    border: 1px solid rgba(0, 240, 255, 0.35);
  }
  .edm-city-pill.city-cambridge {
    background: rgba(255, 0, 127, 0.15);
    color: var(--pink);
    border: 1px solid rgba(255, 0, 127, 0.35);
  }
  .edm-city-pill.city-somerville {
    background: rgba(168, 85, 247, 0.15);
    color: var(--purple);
    border: 1px solid rgba(168, 85, 247, 0.35);
  }
  .edm-city-pill.city-other {
    background: rgba(255, 214, 0, 0.15);
    color: var(--yellow);
    border: 1px solid rgba(255, 214, 0, 0.35);
  }
  .edm-city-head .count {
    font-size: 11.5px;
    font-weight: 700;
    color: var(--muted);
    background: rgba(255, 255, 255, 0.06);
    padding: 2px 8px;
    border-radius: 999px;
  }
  .edm-city-cards {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 14px;
  }
  @media (min-width: 640px) {
    .edm-city-cards {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
  .hub-card.edm-card {
    background: #0d1020;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    overflow: hidden;
    position: relative;
    display: flex;
    flex-direction: column;
    transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  }
  .hub-card.edm-card:hover {
    transform: translateY(-2px);
    border-color: var(--edm-band);
    box-shadow: 0 0 18px rgba(0, 240, 255, 0.18), 0 8px 24px rgba(0,0,0,0.4);
  }
  .edm-card-band {
    height: 3px;
    background: var(--edm-band);
    box-shadow: 0 0 8px var(--edm-band);
  }
  .edm-k-techno { --edm-band: var(--cyan); }
  .edm-k-house { --edm-band: var(--pink); }
  .edm-k-bass { --edm-band: var(--lime); }
  .edm-k-synth { --edm-band: var(--purple); }
  .edm-k-club { --edm-band: var(--yellow); }
  .edm-card-body {
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
  }
  .edm-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .edm-card-subgenre {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: var(--edm-band);
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .edm-card-title {
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    line-height: 1.3;
    letter-spacing: normal;
  }
  .edm-card-title a {
    color: #fff;
    text-decoration: none;
  }
  .edm-card-title a:hover {
    color: var(--cyan);
    text-decoration: underline;
  }
  .edm-card-venue {
    font-size: 13px;
    color: #a4b3c9;
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .edm-card-neigh {
    font-size: 11px;
    color: var(--muted);
    background: rgba(255,255,255,0.06);
    padding: 1px 6px;
    border-radius: 4px;
  }
  .edm-card-desc {
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.45;
    margin: 2px 0 6px;
    overflow-wrap: anywhere;
  }
  .edm-card-footer {
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 10px;
    border-top: 1px solid rgba(255,255,255,0.06);
  }
  .edm-ticket-btn {
    background: linear-gradient(135deg, rgba(0, 240, 255, 0.15), rgba(168, 85, 247, 0.2));
    border: 1px solid rgba(0, 240, 255, 0.4);
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    padding: 5px 12px;
    border-radius: 6px;
    text-decoration: none;
    transition: all 0.15s ease;
  }
  .edm-ticket-btn:hover {
    background: var(--cyan);
    color: #07080f;
    box-shadow: 0 0 12px rgba(0, 240, 255, 0.5);
    text-decoration: none;
  }
  @media (max-width: 640px) {
    .edm-hero-art { height: 130px; }
    .edm-filter-label { min-width: 100%; }
    .edm-hub .hub-nav { font-size: 12px; gap: 8px 10px; }
  }
"""

_EDM_FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.edm-chip');
  if (!chips.length) return;
  var cards = document.querySelectorAll('.hub-card.edm-card');
  var heads = document.querySelectorAll('.hub-day');
  var citySecs = document.querySelectorAll('.edm-city-section');
  var state = { genre: 'all', area: 'all', when: 'all', cost: 'all' };

  function matches(c) {
    if (state.genre !== 'all' && c.dataset.genre !== state.genre) return false;
    if (state.area !== 'all' && c.dataset.area !== state.area) return false;
    if (state.when === 'tonight' && c.dataset.when !== 'tonight') return false;
    if (state.when === 'weekend' && c.dataset.when !== 'weekend' && c.dataset.when !== 'tonight') return false;
    if (state.cost === 'free' && c.dataset.free !== '1') return false;
    return true;
  }

  function render(save) {
    var days = {}, n = 0;
    cards.forEach(function (c) {
      var on = matches(c);
      c.hidden = !on;
      if (on) { days[c.dataset.day] = 1; n++; }
    });
    heads.forEach(function (h) { h.hidden = !days[h.dataset.day]; });
    citySecs.forEach(function (sec) {
      var visible = sec.querySelectorAll('.hub-card.edm-card:not([hidden])').length;
      sec.hidden = (visible === 0);
      var cCount = sec.querySelector('.edm-city-head .count');
      if (cCount) cCount.textContent = visible;
    });
    chips.forEach(function (b) {
      var g = b.dataset.group, v = b.dataset.val;
      b.classList.toggle('active', state[g] === v);
    });
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;
    if (save) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }

  chips.forEach(function (b) {
    b.addEventListener('click', function () {
      var g = b.dataset.group, v = b.dataset.val;
      if (g === 'cost' && state[g] === v && v !== 'all') {
        state[g] = 'all';
      } else {
        state[g] = v;
      }
      render(true);
    });
  });

  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length === 2 && state.hasOwnProperty(kv[0])) {
      var btn = document.querySelector('.edm-chip[data-group="' + kv[0] + '"][data-val="' + kv[1] + '"]');
      if (btn) state[kv[0]] = kv[1];
    }
  });
  render(false);
})();
</script>"""

_CAMPS_HERO_ART = """<svg class="camps-hero-art" viewBox="0 0 900 200" aria-hidden="true" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="camps-sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#bae6fd"/>
      <stop offset="60%" stop-color="#e0f2fe"/>
      <stop offset="100%" stop-color="#fef3c7"/>
    </linearGradient>
    <linearGradient id="camps-lake" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
    <linearGradient id="camps-sun" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#fde047"/>
      <stop offset="100%" stop-color="#f59e0b"/>
    </linearGradient>
  </defs>
  <rect width="900" height="200" fill="url(#camps-sky)"/>
  <circle cx="450" cy="90" r="46" fill="url(#camps-sun)" opacity="0.95"/>
  <circle cx="450" cy="90" r="65" fill="#fde047" opacity="0.25"/>
  <polygon points="0,150 90,105 210,145 320,95 450,135 560,90 690,140 780,100 900,150 900,200 0,200" fill="#93c5fd" opacity="0.5"/>
  <polygon points="0,165 140,120 280,160 410,115 540,155 670,110 820,160 900,135 900,200 0,200" fill="#60a5fa" opacity="0.4"/>
  <rect x="0" y="150" width="900" height="50" fill="url(#camps-lake)"/>
  <polygon points="20,165 35,115 50,165" fill="#14532d"/>
  <polygon points="40,165 58,105 76,165" fill="#166534"/>
  <polygon points="65,170 82,120 100,170" fill="#15803d"/>
  <polygon points="90,172 105,130 120,172" fill="#166534"/>
  <polygon points="110,175 125,135 140,175" fill="#14532d"/>
  <polygon points="760,175 775,135 790,175" fill="#14532d"/>
  <polygon points="780,172 795,125 810,172" fill="#166534"/>
  <polygon points="800,170 818,115 836,170" fill="#15803d"/>
  <polygon points="825,165 842,105 860,165" fill="#166534"/>
  <polygon points="850,165 865,118 880,165" fill="#14532d"/>
  <g transform="translate(420, 165)">
    <path d="M 0,12 C 15,18 45,18 60,12 C 55,20 20,20 0,12 Z" fill="#dc2626"/>
    <polygon points="24,10 26,1 28,10" fill="#fef08a"/>
    <polygon points="34,10 36,1 38,10" fill="#fef08a"/>
    <line x1="20" y1="8" x2="42" y2="18" stroke="#78350f" stroke-width="2"/>
  </g>
  <polygon points="145,178 165,145 185,178" fill="#ea580c"/>
  <polygon points="165,145 185,178 178,178 165,152" fill="#c2410c"/>
  <polygon points="158,162 165,152 172,162 165,178" fill="#431407"/>
  <g transform="translate(200, 172)">
    <line x1="-6" y1="4" x2="6" y2="-2" stroke="#78350f" stroke-width="2.5"/>
    <line x1="-6" y1="-2" x2="6" y2="4" stroke="#78350f" stroke-width="2.5"/>
    <polygon points="-4,2 0,-8 4,2" fill="#ef4444"/>
    <polygon points="-2,2 0,-5 2,2" fill="#facc15"/>
  </g>
  <g transform="translate(450, 26)">
    <rect x="-120" y="-12" width="240" height="24" rx="12" fill="#ffffff" stroke="#15803d" stroke-width="1.5" opacity="0.95"/>
    <text x="0" y="4" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-size="11" font-weight="800" fill="#15803d" letter-spacing="1.5">SUMMER CAMPS</text>
  </g>
</svg>"""

_CAMPS_CSS = """
  .camps-hub {
    --bg: #f6f8f5; --card: #ffffff; --card-hover: #ffffff; --fg: #17261b; --muted: #4a5a4f;
    --accent: #166534; --border: #d5dfd6; --amber-bg: #fdf3d7; --amber-fg: #6b4b00;
    background: var(--bg) !important; color: var(--fg) !important;
  }
  .camps-hub header {
    background: #f6f8f5 !important;
    border-bottom: 1px solid var(--border) !important;
    position: static;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 16px;
    padding: 14px 20px;
  }
  .camps-hub .logo { color: #14532d !important; font-weight: 800; white-space: nowrap; font-size: 16px; text-decoration: none; }
  .camps-hub .logo span { color: #c2410c !important; }
  .camps-hub .camps-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    flex-wrap: wrap;
  }
  .camps-hub .camps-nav a {
    box-sizing: border-box;
    color: var(--muted);
    text-decoration: none;
    padding: 6px 12px;
    border-radius: 999px;
    font-weight: 600;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .camps-hub .camps-nav a:hover {
    color: var(--accent);
    background: rgba(22, 101, 52, 0.08);
    border-color: var(--border);
  }
  .camps-hub .camps-nav a.active {
    color: #fff;
    background: var(--accent);
    font-weight: 700;
  }
  .camps-hub main { max-width: 1000px; padding-top: 20px; font-size: 16px; line-height: 1.5; }
  .camps-hub .hero { border: 1px solid var(--border); background: #fff; border-radius: 16px; overflow: hidden; margin-bottom: 20px; padding: 0; text-align: left; }
  .camps-hero-art { display: block; width: 100%; height: 120px; }
  .camps-hero-copy { padding: 18px 22px 22px; }
  .camps-hub .hero h1 { font-size: clamp(28px, 6vw, 40px); font-weight: 800; margin: 0 0 6px; color: #14532d; letter-spacing: -0.01em; }
  .camps-hub .hero h1 small { display: block; font-size: 0.45em; font-weight: 700; color: #3f6f52; letter-spacing: 0; margin-top: 4px; }
  .camps-hub .hero p { color: var(--muted); font-size: 17px; margin: 0 0 10px; max-width: 720px; }
  .camps-stats { margin: 0; font-size: 15px; font-weight: 600; color: var(--fg); }
  .camp-panel { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 18px 20px; margin-bottom: 20px; }
  .camp-panel h2 { font-size: 22px; margin: 0 0 4px; color: #14532d; }
  .camp-panel > p { margin: 0 0 12px; color: var(--muted); }
  .camp-date-list { list-style: none; margin: 0; padding: 0; }
  .camp-date-list li { display: grid; grid-template-columns: 190px minmax(0, 1fr) auto; gap: 4px 14px; padding: 12px 0; border-top: 1px solid #e7ede7; align-items: baseline; }
  .camp-date-list li[hidden] { display: none; }
  .camp-date-when { font-weight: 800; color: #14532d; }
  .camp-date-what a { font-weight: 700; color: var(--fg); }
  .camp-date-what span { display: block; color: var(--muted); }
  .camp-date-cal { white-space: nowrap; font-size: 15px; }
  .camp-linkish { background: none; border: 0; padding: 0; font: inherit; font-weight: 600; color: var(--accent); text-decoration: underline; cursor: pointer; }
  .camp-date-cal a { font-weight: 600; color: var(--accent); margin-right: 10px; }
  .camp-more { margin-top: 10px; }
  .camp-panel details { margin-top: 12px; border-top: 1px solid #e7ede7; padding-top: 12px; }
  .camp-panel summary { font-weight: 700; cursor: pointer; color: var(--accent); }
  .camp-panel details ul { margin: 8px 0 0; padding-left: 20px; }
  .camps-filters { background: #fff; border: 1px solid var(--border); border-radius: 16px; padding: 16px 20px 6px; margin-bottom: 14px; }
  .camp-filter-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  .camp-filter-label { font-weight: 800; color: #14532d; font-size: 15px; min-width: 76px; }
  .camp-chip, .camp-age-select { font: inherit; font-size: 15px; font-weight: 600; padding: 7px 14px; border-radius: 999px; cursor: pointer; border: 1px solid #b9c6bb; background: #fff; color: var(--fg); -webkit-tap-highlight-color: transparent; }
  .camp-chip:hover { border-color: var(--accent); }
  .camp-chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
  .camps-count-bar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 16px; font-weight: 700; margin: 0 2px 14px; }
  .camps-hub .hub-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; margin: 0; }
  @media (min-width: 760px) { .camps-hub .hub-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .camps-hub #hub-none { text-align: center; background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 28px 20px; color: var(--muted); }
  .camp-card { background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .camp-card[hidden] { display: none; }
  .camp-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .camp-card h3 { margin: 0; font-size: 19px; line-height: 1.25; font-weight: 800; }
  .camp-card h3 a { color: var(--fg); text-decoration: none; }
  .camp-card h3 a:hover { color: var(--accent); text-decoration: underline; }
  .camp-where { margin: 2px 0 0; color: var(--muted); font-size: 15px; }
  .camp-save { flex: none; font: inherit; font-size: 15px; font-weight: 700; color: var(--accent); background: #fff; border: 1px solid #b9c6bb; border-radius: 8px; padding: 4px 10px; cursor: pointer; }
  .camp-save[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
  .camp-facts { display: grid; grid-template-columns: 88px minmax(0, 1fr); gap: 6px 10px; margin: 0; font-size: 16px; }
  .camp-facts dt { font-weight: 700; color: var(--muted); }
  .camp-facts dd { margin: 0; overflow-wrap: anywhere; word-break: break-word; }
  .camp-facts ul { margin: 2px 0 0; padding: 0; list-style: none; }
  .camp-facts li.next { font-weight: 700; }
  .camp-facts li.past { color: var(--muted); }
  .camp-unknown { color: var(--muted); font-style: italic; }
  .camp-note { margin: 0; color: var(--muted); font-size: 15px; }
  .camp-foot { margin-top: auto; padding-top: 10px; border-top: 1px solid #e7ede7; display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
  .camp-season { font-size: 14px; font-weight: 700; padding: 3px 9px; border-radius: 6px; }
  .camp-season.y2027 { background: #e2f3e6; color: #14532d; }
  .camp-season.y2026 { background: var(--amber-bg); color: var(--amber-fg); }
  .camp-site { font-weight: 700; color: var(--accent); }
  .camp-sources { font-size: 14px; color: var(--muted); width: 100%; }
  .camp-sources a { color: var(--muted); }
  .camp-saved-bar { background: #e2f3e6; border-radius: 12px; padding: 10px 14px; margin-bottom: 14px; font-weight: 600; display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }
  .camp-saved-bar[hidden] { display: none; }
  .camp-after { margin-top: 24px; }
  .camp-after ul { margin: 8px 0 0; padding-left: 20px; }
  @media (max-width: 640px) {
    .camps-hero-art { display: none; }
    .camps-hub header {
      padding: 10px 14px;
      gap: 8px 10px;
    }
    .camps-hub .logo {
      font-size: 15px;
    }
    .camps-hub .camps-nav {
      gap: 5px;
      font-size: 13px;
    }
    .camps-hub .camps-nav a {
      padding: 5px 9px;
      min-height: 34px;
    }
    .camps-hub main {
      padding: 14px 12px 48px;
    }
    .camps-hub .hero {
      border-radius: 12px;
      margin-bottom: 14px;
    }
    .camps-hero-copy {
      padding: 14px 14px 16px;
    }
    .camps-hub .hero h1 {
      font-size: clamp(23px, 6vw, 32px);
      margin-bottom: 4px;
    }
    .camps-hub .hero p {
      font-size: 15px;
      margin-bottom: 8px;
    }
    .camps-stats {
      font-size: 13.5px;
    }
    .camp-panel {
      padding: 14px 14px 16px;
      border-radius: 12px;
      margin-bottom: 14px;
    }
    .camp-panel h2 {
      font-size: 19px;
    }
    .camp-panel > p {
      font-size: 14px;
      margin-bottom: 10px;
    }
    .camp-date-list li {
      grid-template-columns: minmax(0, 1fr);
      gap: 3px;
      padding: 10px 0;
    }
    .camp-date-when {
      font-size: 14px;
    }
    .camp-date-what {
      font-size: 15px;
    }
    .camp-date-what span {
      font-size: 13.5px;
    }
    .camp-date-cal {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px;
      margin-top: 5px;
      font-size: 13.5px;
    }
    .camp-date-cal a, .camp-date-cal .camp-linkish {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
    }
    .camps-filters {
      padding: 12px 12px 6px;
      border-radius: 12px;
      margin-bottom: 12px;
    }
    .camp-filter-row {
      gap: 5px;
      margin-bottom: 10px;
    }
    .camp-filter-label {
      min-width: 100%;
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 2px;
    }
    .camp-chip {
      font-size: 13px;
      padding: 5px 10px;
      min-height: 34px;
      line-height: 1.2;
    }
    .camp-age-select {
      font-size: 13.5px;
      padding: 6px 12px;
      min-height: 36px;
      max-width: 100%;
    }
    .camps-count-bar {
      font-size: 14.5px;
      margin-bottom: 10px;
    }
    .camp-card {
      padding: 14px 14px 12px;
      border-radius: 12px;
      gap: 8px;
    }
    .camp-card h3 {
      font-size: 17.5px;
    }
    .camp-where {
      font-size: 13.5px;
    }
    .camp-save {
      font-size: 13.5px;
      padding: 5px 10px;
      min-height: 36px;
      min-width: 68px;
    }
    .camp-facts {
      grid-template-columns: 66px minmax(0, 1fr);
      gap: 4px 8px;
      font-size: 14px;
      line-height: 1.4;
    }
    .camp-facts dt {
      font-size: 12.5px;
    }
    .camp-facts dd {
      font-size: 14px;
    }
    .camp-note {
      font-size: 13.5px;
    }
    .camp-foot {
      padding-top: 8px;
      gap: 8px;
    }
    .camp-season {
      font-size: 12px;
      padding: 3px 7px;
    }
    .camp-site {
      font-size: 13.5px;
      padding: 4px 10px;
      background: rgba(22, 101, 52, 0.08);
      border-radius: 6px;
      text-decoration: none;
      min-height: 32px;
      display: inline-flex;
      align-items: center;
    }
    .camp-sources {
      font-size: 12px;
    }
  }
"""

_CAMPS_FILTER_JS = """<script>
(function () {
  var chips = document.querySelectorAll('.camp-chip');
  if (!chips.length) return;
  var cards = document.querySelectorAll('.camp-card');
  var ageSel = document.getElementById('camp-age');
  var countEl = document.getElementById('camp-results-count');
  var state = { area: 'all', kind: 'all', cost: 'all', info: 'all', age: 'all' };
  var KEY = 'wbe-saved-camps', saved = {};
  try { (JSON.parse(localStorage.getItem(KEY)) || []).forEach(function (i) { saved[i] = 1; }); } catch (e) {}
  function keep() { try { localStorage.setItem(KEY, JSON.stringify(Object.keys(saved))); } catch (e) {} }
  function num(v) { return v === '' || v === undefined ? null : Number(v); }
  function costOk(d) {
    var lo = num(d.lo);
    if (state.cost === 'free') return lo === 0;
    if (state.cost === 'u300') return lo !== null && lo < 300;
    if (state.cost === 'u500') return lo !== null && lo < 500;
    if (state.cost === 'help') return d.help === '1';
    return true;
  }
  function matches(c) {
    var d = c.dataset;
    if (state.area !== 'all' && d.area !== state.area) return false;
    if (state.kind === 'overnight') { if (d.type !== 'Overnight') return false; }
    else if (state.kind !== 'all' && d.kind !== state.kind) return false;
    if (state.info === 'y2027' && d.season !== '2027') return false;
    if (state.info === 'saved' && !saved[d.id]) return false;
    if (!costOk(d)) return false;
    if (state.age !== 'all') {
      var a = Number(state.age), lo = num(d.min), hi = num(d.max);
      if ((lo !== null && a < lo) || (hi !== null && a > hi)) return false;
    }
    return true;
  }
  function render(write) {
    var n = 0;
    cards.forEach(function (c) { var on = matches(c); c.hidden = !on; if (on) n++; });
    chips.forEach(function (b) { b.classList.toggle('active', state[b.dataset.group] === b.dataset.val); });
    if (ageSel) ageSel.value = state.age;
    if (countEl) countEl.textContent = n;
    var none = document.getElementById('hub-none');
    if (none) none.hidden = n > 0;
    var ids = Object.keys(saved).filter(function (i) { return document.querySelector('.camp-card[data-id="' + i + '"]'); });
    document.querySelectorAll('.camp-save').forEach(function (b) {
      var on = !!saved[b.dataset.id];
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.textContent = on ? '★ Saved' : '☆ Save';
    });
    var bar = document.getElementById('camp-saved-bar');
    if (bar) { bar.hidden = !ids.length; var ct = document.getElementById('camp-saved-n'); if (ct) ct.textContent = ids.length; }
    if (write) {
      var parts = Object.keys(state).filter(function (k) { return state[k] !== 'all'; }).map(function (k) { return k + '=' + state[k]; });
      history.replaceState(null, '', parts.length ? '#' + parts.join('&') : location.pathname);
    }
  }
  function stamp(ev) {
    var d = ev.date.replace(/-/g, '');
    return ev.time ? ';TZID=America/New_York:' + d + 'T' + ev.time.replace(':', '') + '00' : ';VALUE=DATE:' + d;
  }
  function clean(t) { return String(t).replace(/([,;\\\\])/g, '\\\\$1'); }
  function save(events) {
    var now = new Date().toISOString().replace(/[-:.]/g, '').slice(0, 15) + 'Z';
    var out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Wicked Boston Events//Summer Camps//EN'];
    events.forEach(function (ev, i) {
      out.push('BEGIN:VEVENT', 'UID:camp-' + i + '-' + ev.date + '@wickedbostonevents.com', 'DTSTAMP:' + now,
        'DTSTART' + stamp(ev), 'SUMMARY:' + clean(ev.title), 'DESCRIPTION:' + clean('Check the camp site to confirm: ' + ev.url),
        'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + clean(ev.title), 'TRIGGER:-P1D', 'END:VALARM', 'END:VEVENT');
    });
    out.push('END:VCALENDAR');
    var a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([out.join('\\r\\n')], { type: 'text/calendar' }));
    a.download = 'summer-camp-dates.ics';
    document.body.appendChild(a); a.click(); a.remove();
  }
  function today() {
    var p = {};
    new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' })
      .formatToParts(new Date()).forEach(function (x) { p[x.type] = x.value; });
    return p.year + '-' + p.month + '-' + p.day;
  }
  var now = today(), rows = [];
  document.querySelectorAll('.camp-date-list li').forEach(function (li) { if (li.dataset.date >= now) rows.push(li); else li.remove(); });
  var more = document.getElementById('camp-dates-more');
  rows.forEach(function (li, i) { li.hidden = i >= 6; });
  if (more) {
    more.hidden = rows.length <= 6;
    more.textContent = 'Show all ' + rows.length + ' dates';
    more.addEventListener('click', function () { rows.forEach(function (li) { li.hidden = false; }); more.hidden = true; });
  }
  document.querySelectorAll('.camp-ics').forEach(function (b) {
    b.addEventListener('click', function () { save([JSON.parse(b.dataset.ev)]); });
  });
  var all = document.getElementById('camp-saved-ics');
  if (all) all.addEventListener('click', function () {
    var list = [];
    cards.forEach(function (c) {
      if (!saved[c.dataset.id]) return;
      JSON.parse(c.dataset.events || '[]').forEach(function (e) { if (e.date >= now) list.push(e); });
    });
    if (list.length) save(list); else all.textContent = 'No dated sign-ups for these yet';
  });
  var showSaved = document.getElementById('camp-saved-show');
  if (showSaved) showSaved.addEventListener('click', function () { state.info = 'saved'; render(true); });
  document.querySelectorAll('.camp-save').forEach(function (b) {
    b.addEventListener('click', function () {
      if (saved[b.dataset.id]) delete saved[b.dataset.id]; else saved[b.dataset.id] = 1;
      keep(); render(false);
    });
  });
  chips.forEach(function (b) {
    b.addEventListener('click', function () { state[b.dataset.group] = b.dataset.val; render(true); });
  });
  if (ageSel) ageSel.addEventListener('change', function () { state.age = ageSel.value; render(true); });
  location.hash.replace(/^#/, '').split('&').forEach(function (p) {
    var kv = p.split('=');
    if (kv.length !== 2 || !state.hasOwnProperty(kv[0])) return;
    if (kv[0] === 'age' ? (ageSel && ageSel.querySelector('option[value="' + kv[1] + '"]')) : document.querySelector('.camp-chip[data-group="' + kv[0] + '"][data-val="' + kv[1] + '"]')) state[kv[0]] = kv[1];
  });
  render(false);
})();
</script>"""

_CAMP_TYPE_WORDS = {"city": "City or town program", "ymca": "YMCA", "nature": "Mass Audubon nature camp",
                    "nonprofit": "Nonprofit", "museum": "Museum or zoo", "private": "Private camp"}


def _camp_when(ev, year=False):
    d = datetime.strptime(ev["date"], "%Y-%m-%d")
    text = f"{d.strftime('%a, %b')} {d.day}" + (f", {d.year}" if year else "")
    if ev.get("time"):
        t = datetime.strptime(ev["time"], "%H:%M")
        text += f" at {t.hour % 12 or 12}{t.strftime(':%M') if t.minute else ''} {'AM' if t.hour < 12 else 'PM'}"
    return text


def _camp_gcal(title, ev, url):
    day = ev["date"].replace("-", "")
    if ev.get("time"):
        start = datetime.strptime(ev["date"] + ev["time"], "%Y-%m-%d%H:%M")
        dates = f"{start:%Y%m%dT%H%M%S}/{start + timedelta(minutes=30):%Y%m%dT%H%M%S}"
    else:
        end = datetime.strptime(ev["date"], "%Y-%m-%d") + timedelta(days=1)
        dates = f"{day}/{end:%Y%m%d}"
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE&text=" + quote(title) + "&dates=" + dates
            + "&ctz=America/New_York&details=" + quote("Check the camp site to confirm: " + url))


def _camp_fact(label, value):
    shown = escape(value) if value else '<span class="camp-unknown">Not published</span>'
    return f"<dt>{label}</dt><dd>{shown}</dd>"


def _camp_signup(c, today_iso):
    lines = []
    for e in c.get("events") or []:
        if e.get("date"):
            if e["date"] >= today_iso:
                lines.append(f'<li class="next">{escape(_camp_when(e))}: {escape(e["label"])}</li>')
        elif e.get("season") == 2026:
            lines.append(f'<li class="past">Last year: {escape(e["label"])}, {escape(e["when"])}</li>')
        else:
            prefix = "" if e["when"] == "Not posted yet" else f'{escape(e["when"])}: '
            lines.append(f'<li>{prefix}{escape(e["label"])}</li>')
    how = f"<div>{escape(c['signup'])}</div>" if c.get("signup") else ""
    if not how and not lines:
        return '<span class="camp-unknown">Not published</span>'
    return how + (f"<ul>{''.join(lines)}</ul>" if lines else "")


def _camp_card(c):
    today_iso = datetime.now(EASTERN).date().isoformat()
    name, url = escape(c["name"]), escape(c["url"])
    where = " · ".join([c["town"], "Overnight" if c["type"] == "Overnight" else "Day camp", _CAMP_TYPE_WORDS[c["kind"]]])
    upcoming = [{"title": f"{c['name']}: {e['label']}", "date": e["date"], "time": e.get("time"), "url": c["url"]}
                for e in c.get("events") or [] if e.get("date") and e["date"] >= today_iso]
    facts = [_camp_fact("Ages", c.get("ages")), _camp_fact("Cost", c.get("price")), _camp_fact("Dates", c.get("dates")),
             _camp_fact("Hours", c.get("hours")), f"<dt>Sign-up</dt><dd>{_camp_signup(c, today_iso)}</dd>"]
    if c.get("residents"):
        facts.append(_camp_fact("Who", c["residents"]))
    if c.get("aid"):
        facts.append(_camp_fact("Help", c["aid"]))
    note = f'<p class="camp-note">{escape(c["note"])}</p>' if c.get("note") else ""
    season = ('<span class="camp-season y2027">2027 info</span>' if c["season"] == 2027
              else '<span class="camp-season y2026">2026 info, 2027 not posted</span>')
    checked = datetime.strptime(c["checked"], "%Y-%m-%d")
    sources = " · ".join(f'<a href="{escape(u)}" target="_blank" rel="noopener">source {i + 1}</a>'
                         for i, u in enumerate(c["sources"]))
    attrs = {"id": c["id"], "area": c["area"], "kind": c["kind"], "type": c["type"], "season": c["season"],
             "min": "" if c.get("age_min") is None else c["age_min"], "max": "" if c.get("age_max") is None else c["age_max"],
             "lo": "" if c.get("week_low") is None else c["week_low"], "help": 1 if c.get("sliding") or c.get("aid") else 0}
    data = " ".join(f'data-{k}="{escape(str(v))}"' for k, v in attrs.items())
    return f"""<article class="camp-card" {data} data-events="{escape(json.dumps(upcoming))}">
  <div class="camp-head">
    <div><h3><a href="{url}" target="_blank" rel="noopener">{name}</a></h3><p class="camp-where">{escape(where)}</p></div>
    <button type="button" class="camp-save" data-id="{escape(c['id'])}" aria-pressed="false" aria-label="Save {name}">☆ Save</button>
  </div>
  <dl class="camp-facts">{''.join(facts)}</dl>
  {note}
  <div class="camp-foot">{season}<a class="camp-site" href="{url}" target="_blank" rel="noopener">Camp site →</a>
    <span class="camp-sources">Checked {checked.strftime('%b')} {checked.day}, {checked.year}: {sources}</span></div>
</article>"""


def _camp_date_rows(camps, today_iso):
    groups, later, seen_later = {}, [], set()
    for c in camps:
        for e in c.get("events") or []:
            who = e.get("group") or c["name"]
            url = c["url"]
            if e.get("date"):
                if e["date"] >= today_iso:
                    groups.setdefault((e["date"], e.get("time") or "", who, e["label"]), (e, url))
            elif e.get("season") == 2027 and e["when"] != "Not posted yet" and (who, e["label"]) not in seen_later:
                seen_later.add((who, e["label"]))
                later.append((who, e))
    rows = []
    for (_d, _t, who, label), (e, url) in sorted(groups.items()):
        title = f"{who}: {label}"
        ics = json.dumps({"title": title, "date": e["date"], "time": e.get("time"), "url": url})
        rows.append(f"""<li data-date="{escape(e['date'])}"><div class="camp-date-when">{escape(_camp_when(e))}</div>
    <div class="camp-date-what"><a href="{escape(url)}" target="_blank" rel="noopener">{escape(who)}</a><span>{escape(label)}</span></div>
    <div class="camp-date-cal"><a href="{escape(_camp_gcal(title, e, url))}" target="_blank" rel="noopener">Google Calendar</a><button type="button" class="camp-linkish camp-ics" data-ev="{escape(ics)}">Other calendar</button></div></li>""")
    return rows, later


def _camp_summer_year(today=None):
    """The summer parents are shopping for: this year until August, next year from September."""
    today = today or datetime.now(EASTERN).date()
    return today.year + 1 if today.month >= 9 else today.year


def _camps_sections(camps):
    from camps import AREAS, KINDS, load_camps
    data = load_camps()
    today_iso = datetime.now(EASTERN).date().isoformat()
    rows, later = _camp_date_rows(camps, today_iso)

    def chip(group, val, label):
        return f'<button type="button" class="camp-chip" data-group="{group}" data-val="{val}">{escape(label)}</button>'

    present = {c["area"] for c in camps}
    kinds = {c["kind"] for c in camps}
    areas = chip("area", "all", "Anywhere") + "".join(chip("area", k, v) for k, v in AREAS if k in present)
    types = chip("kind", "all", "All") + "".join(chip("kind", k, v) for k, v in KINDS if k in kinds) + chip("kind", "overnight", "Overnight")
    costs = chip("cost", "all", "Any") + chip("cost", "free", "Free") + chip("cost", "u300", "From under $300/wk") + chip("cost", "u500", "From under $500/wk") + chip("cost", "help", "Sliding scale or aid")
    info = chip("info", "all", "All camps") + chip("info", "y2027", "2027 info posted") + chip("info", "saved", "Saved")
    ages = '<option value="all">Any age</option>' + "".join(f'<option value="{a}">{a} years old</option>' for a in range(3, 18))
    hero = f"""<div class="hero">
    {_CAMPS_HERO_ART}
    <div class="camps-hero-copy">
      <h1>Summer Camps Near Boston {_camp_summer_year()}<small>Boston, Cambridge, Somerville &amp; nearby towns</small></h1>
      <p>Prices, ages and sign-up dates for camps around Boston, checked against each camp's own site. Most camps haven't posted everything for 2027, so each one shows which year its details are from.</p>
      <p class="camps-stats">{len(camps)} camps in Boston and nearby towns · {len(rows)} sign-up dates coming up</p>
    </div>
  </div>"""
    later_html = ""
    if later:
        items = "".join(f"<li><strong>{escape(e['when'])}:</strong> {escape(who)}, {escape(e['label'])}</li>" for who, e in later)
        later_html = f"<details><summary>Expected soon, no exact day yet</summary><ul>{items}</ul></details>"
    dates = f"""<section class="camp-panel" aria-labelledby="camp-dates-h">
    <h2 id="camp-dates-h">Next sign-up dates</h2>
    <p>Popular camps fill fast, so add these to your calendar.</p>
    <ol class="camp-date-list">{''.join(rows)}</ol>
    <button type="button" id="camp-dates-more" class="camp-linkish camp-more" hidden>Show all</button>
    {later_html}
  </section>"""
    filters = f"""{dates}
  <div class="camps-filters" role="group" aria-label="Filter summer camps">
    <div class="camp-filter-row"><label class="camp-filter-label" for="camp-age">Child's age</label><select id="camp-age" class="camp-age-select">{ages}</select></div>
    <div class="camp-filter-row"><span class="camp-filter-label">Area</span>{areas}</div>
    <div class="camp-filter-row"><span class="camp-filter-label">Type</span>{types}</div>
    <div class="camp-filter-row"><span class="camp-filter-label">Cost</span>{costs}</div>
    <div class="camp-filter-row"><span class="camp-filter-label">Show</span>{info}</div>
  </div>
  <div id="camp-saved-bar" class="camp-saved-bar" hidden><span><span id="camp-saved-n">0</span> saved on this device</span>
    <button type="button" id="camp-saved-show" class="camp-linkish">Show saved</button>
    <button type="button" id="camp-saved-ics" class="camp-linkish">Add their dates to my calendar</button></div>
  <div class="camps-count-bar"><span><span id="camp-results-count">{len(camps)}</span> camps</span></div>"""

    def link(name, url):
        return f'<a href="{escape(url)}" target="_blank" rel="noopener">{escape(name)}</a>' if url else escape(name)
    leads = "".join(f"<li>{link(l['name'], l['url'])} ({escape(l['town'])})</li>" for l in data["leads"])
    towns_html = "".join(f"<li>{link(t['town'], t.get('url'))}: {escape(t['note'])}</li>" for t in data["towns"])
    not_camps = "".join(f"<li>{link(n['name'], n['url'])}: {escape(n['note'])}</li>" for n in data["not_camps"])
    tail = f"""<div class="camp-after">
  <section class="camp-panel"><h2>Still being checked</h2>
    <p>These may be good options, but we couldn't confirm their prices or dates yet, so check with them directly.</p>
    <details open><summary>Camps nearby</summary><ul>{leads}</ul></details>
    <details><summary>City and town programs</summary><ul>{towns_html}</ul></details>
    <details><summary>Not a camp</summary><ul>{not_camps}</ul></details>
  </section>
  <section class="camp-panel"><h2>How we check this</h2>
    <p>Everything here comes from the camp's own site or a city document, linked on each card. If a fact isn't published we say so, and we never estimate. Dates and prices can change, so confirm with the camp before you plan around them. Spot a mistake or missing camp? Tell us on Instagram at @wickedbostonevents.</p>
  </section>
  <p><a href="../kids-family-events-boston/">See year-round kids and family events →</a></p>
</div>
"""
    return hero, filters, tail


_FAMILY_NAV = (("../", "All Events", None),
               ("../kids-family-events-boston/", "Kids &amp; Family", "kids-family-events-boston"),
               ("../summer-camps/", "Summer Camps", "summer-camps"))


def _family_nav(hub_slug, nav_class):
    """The short header nav on the parent-facing pages (Kids & Family, Summer Camps)."""
    ACTIVE = ' class="active"'
    links = "\n".join(f'    <a href="{href}"{ACTIVE if slug == hub_slug else ""}>{label}</a>'
                      for href, label, slug in _FAMILY_NAV)
    return f'  <nav class="hub-nav {nav_class}">\n{links}\n  </nav>'


KIDS_INLINE_DAYS = 14  # the Kids page carries two weeks; later days load from later.html


def render_hub_page(hub_slug, events, site_url=None, extra_files=None):
    if not site_url:
        site_url = get_site_url()
    hub = HUBS.get(hub_slug)
    if not hub:
        return ""

    flag_shared_source_points(events)
    filtered = filter_events_for_hub(hub, events)
    if hub.get("collapse_series"):
        filtered = _collapse_hub_series(filtered)
    card_limit = hub.get("limit", 60)

    hub_canonical = f"{site_url}/{hub_slug}/"
    og_img_name = hub.get("og_image") or f"og-{hub_slug}.jpg"
    meta_tags = build_seo_meta_tags(
        site_url=site_url,
        title=f"{hub['title']} · Wicked Boston Events",
        description=hub["subtitle"],
        path=f"{hub_slug}/",
        image_url=f"{site_url}/{og_img_name}"
    )

    hub_event_items = []
    for idx, e in enumerate(filtered[:50]):
        d_str = e.get("date")
        if not d_str or d_str == "tba":
            continue
        title = e.get("title") or e.get("name")
        venue_name = e.get("venue") or e.get("_source_venue") or "Boston Area Venue"
        city = _event_city(venue_name, e.get("_source_venue"), e)
        city_label = CITY_LABELS.get(city, "Boston")
        url = e.get("url") or e.get("link") or hub_canonical
        geo = resolve_event_geo(e)

        loc_obj = {
            "@type": "Place",
            "name": venue_name,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city_label,
                "addressRegion": "MA",
                "addressCountry": "US"
            }
        }
        if geo:
            if geo.get("address"):
                loc_obj["address"]["streetAddress"] = geo["address"]
            loc_obj["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": geo["lat"],
                "longitude": geo["lng"]
            }

        ev_img = e.get("img") or e.get("image") or f"{site_url}/og-image.jpg"
        price_val = e.get("price")
        offers_obj = {
            "@type": "Offer",
            "url": url,
            "availability": "https://schema.org/InStock",
            "priceCurrency": "USD"
        }
        if _is_event_free(e):
            offers_obj["price"] = "0"
        elif price_val:
            m_price = re.search(r"\$?(\d+(\.\d{2})?)", str(price_val))
            if m_price:
                offers_obj["price"] = m_price.group(1)

        t_obj = e.get("_time")
        t_str = e.get("time") or ""
        start_date = t_obj.isoformat() if isinstance(t_obj, datetime) else d_str

        hub_event_items.append({
            "@type": "ListItem",
            "position": idx + 1,
            "item": {
                "@type": "Event",
                "name": title,
                "startDate": start_date,
                "eventStatus": "https://schema.org/EventScheduled",
                "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
                "location": loc_obj,
                "image": [ev_img],
                "description": e.get("description") or f"{title} live at {venue_name} in {city_label}, MA",
                "url": url,
                "offers": offers_obj,
                "performer": {
                    "@type": "PerformingGroup",
                    "name": title
                },
                "organizer": {
                    "@type": "Organization",
                    "name": e.get("_source_venue") or venue_name,
                    "url": url
                }
            }
        })

    is_kids = hub.get("style") == "kids"
    is_edm = hub.get("style") == "edm"
    is_camps = hub.get("style") == "camps"
    if is_camps:
        for idx, c in enumerate(filtered[:50]):
            hub_event_items.append({
                "@type": "ListItem",
                "position": idx + 1,
                "item": {
                    "@type": "EducationalOrganization",
                    "name": c["name"],
                    "url": c["url"],
                    "description": f"{c['name']} in {c['town']}",
                    "address": {"@type": "PostalAddress", "addressLocality": c["town"], "addressCountry": "US"}
                }
            })

    hub_ld = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": hub["title"],
        "description": hub["subtitle"],
        "url": hub_canonical,
        "itemListElement": hub_event_items
    }
    json_ld_str = f'<script type="application/ld+json">\n{json.dumps(hub_ld, ensure_ascii=False, indent=2)}\n</script>'

    kid_age_counts, kid_kind_counts, kid_free, kid_places = {}, {}, 0, set()
    edm_sub_counts, edm_free_count, edm_places = {}, 0, set()
    cards_html = []

    if is_kids:
        def _render_kid_card(e):
            nonlocal kid_free
            title = escape(e.get("title") or e.get("name") or "Event")
            venue = escape(e.get("venue") or e.get("_source_venue") or "Venue")
            url = escape(e.get("url") or e.get("link") or "#")
            d_str = escape(e.get("date") or "")
            t_str = escape(e.get("time") or "")
            t_obj = e.get("_time")
            if isinstance(t_obj, datetime):
                d_str = ""
                t_str = "All day" if (t_obj.hour, t_obj.minute) == (0, 0) else t_obj.strftime("%-I:%M %p")
            desc_html = ""
            if hub.get("show_details") and e.get("description"):
                d_txt = re.sub(r"\s+", " ", str(e["description"])).strip()
                desc_html = f'<p class="hub-desc">{escape(d_txt[:160] + ("…" if len(d_txt) > 160 else ""))}</p>'
            price_val = e.get("price")
            price_txt = str(price_val or "").strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", price_txt):
                price_txt = "$" + price_txt
            price_badge = f'<span class="badge badge-price">{escape(price_txt)}</span>' if price_txt else ""
            if _is_event_free(e):
                price_badge = '<span class="badge badge-free">Free</span>'
            city = _event_city(e.get("venue"), e.get("_source_venue"), e)
            city_name = escape(_hub_place_label(city, e))
            day_attr = t_obj.date().isoformat() if isinstance(t_obj, datetime) else ""

            ages, kind, emoji, age_label = _kid_tags(e)
            for a in ages:
                kid_age_counts[a] = kid_age_counts.get(a, 0) + 1
            kid_kind_counts[kind] = kid_kind_counts.get(kind, 0) + 1
            kid_free += 1 if _is_event_free(e) else 0
            kid_places.add(e.get("venue") or "")
            price_attr = "free" if _is_event_free(e) else "paid"
            pills = [age_label] if age_label else [_KID_AGE_PILL[a] for a in ages]
            pills_html = "".join(f'<span class="kid-age">{escape(p)}</span>' for p in pills)
            return f"""<article class="hub-card kid-k-{kind}" data-city="{escape(city)}" data-day="{day_attr}" data-age="{' '.join(ages)}" data-kind="{kind}" data-price="{price_attr}">
  <div class="kid-card-band"></div>
  <div class="kid-card-body">
    <div class="kid-emoji" aria-hidden="true">{emoji}</div>
    <div class="kid-card-main">
      <div class="hub-card-head">
        <time class="hub-date">{' · '.join(x for x in (d_str, t_str) if x)}</time>
        <div class="hub-badges">{price_badge}</div>
      </div>
      <h3 class="hub-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
      <div class="hub-meta">
        <span class="hub-venue">📍 {venue}</span>
        <span class="hub-city">({city_name})</span>
      </div>
      {desc_html}
      <div class="kid-ages">{pills_html}</div>
    </div>
  </div>
</article>"""

        by_day = {}
        for e in filtered[:card_limit]:
            t_obj = e.get("_time")
            d_key = t_obj.date() if isinstance(t_obj, datetime) else None
            by_day.setdefault(d_key, []).append(e)

        city_order = ["cambridge", "somerville", "boston", "other"]
        inline_until = datetime.now(EASTERN).date() + timedelta(days=KIDS_INLINE_DAYS - 1)
        later_html, later_days, inline_html = [], [], cards_html
        for day_obj, day_events in by_day.items():
            # Days past the first two weeks go to later.html (loaded on scroll or filter), keeping
            # the page light on phones; they still count in the stats and the When chips.
            cards_html = later_html if (day_obj and day_obj > inline_until) else inline_html
            if cards_html is later_html:
                later_days.append(day_obj.isoformat())
            if day_obj:
                day_iso = day_obj.isoformat()
                day_heading = day_obj.strftime("%A, %B %-d")
                cards_html.append(f'<h2 class="hub-day" id="{day_iso}" data-day="{day_iso}">{day_heading}</h2>')
            else:
                day_iso = "tba"
                cards_html.append('<h2 class="hub-day" id="tba" data-day="tba">Date TBA</h2>')

            by_city = {c: [] for c in city_order}
            for e in day_events:
                c = _event_city(e.get("venue"), e.get("_source_venue"), e)
                by_city.setdefault(c, []).append(e)

            for cname in city_order:
                cevents = by_city.get(cname) or []
                if not cevents:
                    continue
                cevents.sort(key=lambda ev: ev.get("_time") or datetime.max.replace(tzinfo=EASTERN))
                city_cards = [_render_kid_card(e) for e in cevents]
                city_label = CITY_LABELS.get(cname, cname.title())
                cards_html.append(f'''<div class="kid-city-section" data-city="{escape(cname)}" data-day="{day_iso}">
  <div class="kid-city-head">
    <span class="kid-city-pill"><span class="city-dot"></span>{escape(city_label)}</span>
    <span class="count">{len(cevents)}</span>
  </div>
  <div class="kid-city-cards">
    {"".join(city_cards)}
  </div>
</div>''')
        cards_html = inline_html
        if later_html:
            if extra_files is not None:
                extra_files["later.html"] = "\n".join(later_html)
            first, last = datetime.fromisoformat(later_days[0]), datetime.fromisoformat(later_days[-1])
            span = f"{first.strftime('%b %-d')}–{last.strftime('%-d') if first.month == last.month else last.strftime('%b %-d')}"
            cards_html.append(
                f'<div id="kids-later" class="kids-later" data-src="later.html" data-days="{escape(json.dumps(later_days))}">'
                f'<button type="button" class="cta-btn">Show {span} →</button></div>')
    elif is_edm:
        def _render_edm_card(e):
            nonlocal edm_free_count
            title = escape(e.get("title") or e.get("name") or "Event")
            venue = escape(e.get("venue") or e.get("_source_venue") or "Venue")
            url = escape(e.get("url") or e.get("link") or "#")
            d_str = escape(e.get("date") or "")
            t_str = escape(e.get("time") or "")
            t_obj = e.get("_time")
            if isinstance(t_obj, datetime):
                d_str = ""
                t_str = "All day" if (t_obj.hour, t_obj.minute) == (0, 0) else t_obj.strftime("%-I:%M %p")
            desc_html = ""
            if e.get("description"):
                d_txt = re.sub(r"\s+", " ", str(e["description"])).strip()
                desc_html = f'<p class="edm-card-desc">{escape(d_txt[:160] + ("…" if len(d_txt) > 160 else ""))}</p>'
            price_val = e.get("price")
            price_txt = str(price_val or "").strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", price_txt):
                price_txt = "$" + price_txt
            price_badge = f'<span class="badge badge-price">{escape(price_txt)}</span>' if price_txt else ""
            is_free = _is_event_free(e)
            if is_free:
                edm_free_count += 1
                price_badge = '<span class="badge badge-free" style="background:rgba(0,255,136,0.15);color:#00ff88;border:1px solid rgba(0,255,136,0.4);">Free</span>'

            city = _event_city(e.get("venue"), e.get("_source_venue"), e)
            sub, sub_label, sub_emoji, neigh, time_tag, _ = _edm_tags(e)
            edm_sub_counts[sub] = edm_sub_counts.get(sub, 0) + 1
            edm_places.add(e.get("venue") or "")

            day_attr = t_obj.date().isoformat() if isinstance(t_obj, datetime) else ""
            free_attr = "1" if is_free else "0"
            area_attr = city if city in ("boston", "cambridge", "somerville") else "other"
            time_badge = f'<time class="hub-date">{" · ".join(x for x in (d_str, t_str) if x)}</time>'

            return f"""<article class="hub-card edm-card edm-k-{sub}" data-city="{escape(city)}" data-day="{day_attr}" data-genre="{sub}" data-area="{area_attr}" data-when="{time_tag}" data-free="{free_attr}">
  <div class="edm-card-band"></div>
  <div class="edm-card-body">
    <div class="edm-card-top">
      <div class="edm-card-subgenre"><span aria-hidden="true">{sub_emoji}</span> {escape(sub_label)}</div>
      <div class="hub-badges">{price_badge}</div>
    </div>
    <h3 class="edm-card-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
    <div class="edm-card-venue">
      <span>📍 {venue}</span>
      <span class="edm-card-neigh">{escape(neigh)}</span>
    </div>
    {desc_html}
    <div class="edm-card-footer">
      {time_badge}
      <a href="{url}" target="_blank" rel="noopener" class="edm-ticket-btn">Tickets / Info →</a>
    </div>
  </div>
</article>"""

        by_day = {}
        for e in filtered[:card_limit]:
            t_obj = e.get("_time")
            d_key = t_obj.date() if isinstance(t_obj, datetime) else None
            by_day.setdefault(d_key, []).append(e)

        city_order = ["cambridge", "somerville", "boston", "other"]
        for day_obj, day_events in by_day.items():
            if day_obj:
                day_iso = day_obj.isoformat()
                day_heading = day_obj.strftime("%A, %B %-d")
                cards_html.append(f'<h2 class="hub-day" id="{day_iso}" data-day="{day_iso}">{day_heading}</h2>')
            else:
                day_iso = "tba"
                cards_html.append('<h2 class="hub-day" id="tba" data-day="tba">Date TBA</h2>')

            by_city = {c: [] for c in city_order}
            for e in day_events:
                c = _event_city(e.get("venue"), e.get("_source_venue"), e)
                by_city.setdefault(c, []).append(e)

            for cname in city_order:
                cevents = by_city.get(cname) or []
                if not cevents:
                    continue
                cevents.sort(key=lambda ev: ev.get("_time") or datetime.max.replace(tzinfo=EASTERN))
                city_cards = [_render_edm_card(e) for e in cevents]
                city_label = CITY_LABELS.get(cname, cname.title())
                pill_cls = f"city-{cname}"
                cards_html.append(f'''<div class="edm-city-section" data-city="{escape(cname)}" data-day="{day_iso}">
  <div class="edm-city-head">
    <span class="edm-city-pill {pill_cls}">{escape(city_label)}</span>
    <span class="count">{len(cevents)}</span>
  </div>
  <div class="edm-city-cards">
    {"".join(city_cards)}
  </div>
</div>''')
    elif is_camps:
        cards_html = [_camp_card(c) for c in filtered[:card_limit]]
    else:
        last_day = None
        for e in filtered[:card_limit]:
            title = escape(e.get("title") or e.get("name") or "Event")
            venue = escape(e.get("venue") or e.get("_source_venue") or "Venue")
            url = escape(e.get("url") or e.get("link") or "#")
            d_str = escape(e.get("date") or "")
            t_str = escape(e.get("time") or "")
            t_obj = e.get("_time")
            if isinstance(t_obj, datetime):
                # A "Wednesday, November 4" header starts each day; cards then show just the time
                if t_obj.date() != last_day:
                    last_day = t_obj.date()
                    cards_html.append(f'<h2 class="hub-day" id="{last_day.isoformat()}" data-day="{last_day.isoformat()}">{t_obj.strftime("%A, %B %-d")}</h2>')
                d_str = ""
                t_str = "All day" if (t_obj.hour, t_obj.minute) == (0, 0) else t_obj.strftime("%-I:%M %p")
            desc_html = ""
            if hub.get("show_details") and e.get("description"):
                d_txt = re.sub(r"\s+", " ", str(e["description"])).strip()
                desc_html = f'<p class="hub-desc">{escape(d_txt[:160] + ("…" if len(d_txt) > 160 else ""))}</p>'
            price_val = e.get("price")
            price_txt = str(price_val or "").strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", price_txt):
                price_txt = "$" + price_txt  # bare numbers only; most prices already carry "$"
            price_badge = f'<span class="badge badge-price">{escape(price_txt)}</span>' if price_txt else ""
            if _is_event_free(e):
                price_badge = '<span class="badge badge-free">Free</span>'
            city = _event_city(e.get("venue"), e.get("_source_venue"), e)
            city_name = escape(_hub_place_label(city, e))
            day_attr = t_obj.date().isoformat() if isinstance(t_obj, datetime) else ""
            cards_html.append(f"""<article class="hub-card" data-city="{escape(city)}" data-day="{day_attr}">
  <div class="hub-card-head">
    <time class="hub-date">{' · '.join(x for x in (d_str, t_str) if x)}</time>
    <div class="hub-badges">{price_badge}</div>
  </div>
  <h3 class="hub-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
  <div class="hub-meta">
    <span class="hub-venue">📍 {venue}</span>
    <span class="hub-city">({city_name})</span>
  </div>
  {desc_html}
</article>""")

    city_chips_html, hub_js = "", ""  # the filter script must come after the cards it filters
    if not hub.get("city_filter") and cards_html:
        present = {c for c in ("boston", "cambridge", "somerville", "other") if f'data-city="{c}"' in "".join(cards_html)}
        city_chips_html = '<div class="hub-city-chips" role="group" aria-label="Filter by city">' + "".join(
            f'<button type="button" class="hub-city-chip" data-city="{k}">{lbl}</button>'
            for k, lbl in _HUB_CITY_CHIPS if k == "all" or k in present) + "</div>"
        hub_js = _HUB_CITY_JS

    kids_head, kids_css, body_class = "", "", ""
    hero_html = f"""<div class="hero">
    <h1>{hub['title']}</h1>
    <p>{hub['subtitle']}</p>
    <a href="../{hub['query']}" class="cta-btn">Open Full Interactive Calendar &amp; Filters →</a>
  </div>"""
    if is_kids:
        kids_head, kids_css, body_class = _KIDS_FONTS, _KIDS_CSS, ' class="kids-hub"'
        present = {c for c in ("boston", "cambridge", "somerville", "other") if f'data-city="{c}"' in "".join(cards_html)}

        def chip(group, val, label):
            return f'<button type="button" class="kid-chip" data-group="{group}" data-val="{val}">{label}</button>'
        where = "".join(chip("city", k, lbl) for k, lbl in _HUB_CITY_CHIPS if k == "all" or k in present)
        ages = chip("age", "all", "Any age") + "".join(
            chip("age", k, lbl) for k, lbl, _r in _KID_AGE_BUCKETS if kid_age_counts.get(k)) + (
            chip("age", "family", "🏡 All Ages / Family") if kid_age_counts.get("family") else "")
        kinds = chip("kind", "all", "Everything") + "".join(
            chip("kind", k, f"{emo} {lbl}") for k, lbl, emo, _rx in _KID_KIND_RES if kid_kind_counts.get(k))
        prices = chip("price", "all", "Any price") + chip("price", "free", "💛 Free only")
        city_chips_html = f"""<div class="kids-filters" role="group" aria-label="Filter kids events">
    <div class="kid-filter-row" id="kid-when"><span class="kid-filter-label">When</span>{chip("when", "all", "Any day")}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">Where</span>{where}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">Ages</span>{ages}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">What</span>{kinds}</div>
    <div class="kid-filter-row"><span class="kid-filter-label">Cost</span>{prices}</div>
  </div>"""
        hub_js = _KIDS_FILTER_JS
        n_cards = sum(kid_kind_counts.values())
        n_days = len(set(re.findall(r'<h2 class="hub-day" id="([\d-]+)"', "".join(cards_html)))) + len(later_days) or 1
        hero_html = f"""<div class="hero">
    {_KIDS_HERO_ART}
    <div class="kids-hero-copy">
      <h1>{escape(hub.get('h1') or hub['title'])} <span class="wave" aria-hidden="true">👋</span><small>in Boston, Cambridge, Somerville &amp; nearby</small></h1>
      <p>{hub['subtitle']}</p>
      <div class="kids-stats"><span class="kids-stat">🗓️ {n_cards} activities in the next {n_days} days</span><span class="kids-stat">💛 {kid_free} free</span><span class="kids-stat">📍 {len(kid_places)} places</span></div>
      <a href="../{hub['query']}" class="cta-btn">See them on the full calendar →</a>
    </div>
  </div>"""
    elif is_edm:
        kids_head, kids_css, body_class = _EDM_FONTS, _EDM_CSS, ' class="edm-hub"'
        subgenres_html = (
            '<button type="button" class="edm-chip active" data-group="genre" data-val="all">All Electronic</button>'
            + "".join(f'<button type="button" class="edm-chip" data-group="genre" data-val="{k}">{lbl}</button>'
                      for k, lbl, _emo, _rx in _EDM_SUBGENRE_PATTERNS if edm_sub_counts.get(k))
        )
        areas_html = """<button type="button" class="edm-chip active" data-group="area" data-val="all">All Areas</button>
<button type="button" class="edm-chip" data-group="area" data-val="cambridge">Central Sq &amp; Cambridge</button>
<button type="button" class="edm-chip" data-group="area" data-val="boston">Downtown &amp; Seaport</button>
<button type="button" class="edm-chip" data-group="area" data-val="somerville">Somerville</button>
<button type="button" class="edm-chip" data-group="area" data-val="other">Greater Boston</button>"""
        when_html = """<button type="button" class="edm-chip active" data-group="when" data-val="all">All Dates</button>
<button type="button" class="edm-chip" data-group="when" data-val="tonight">🔥 Tonight</button>
<button type="button" class="edm-chip" data-group="when" data-val="weekend">🎉 This Weekend</button>"""
        cost_html = """<button type="button" class="edm-chip active" data-group="cost" data-val="all">All Prices</button>
<button type="button" class="edm-chip" data-group="cost" data-val="free">💛 Free / No Cover</button>"""
        city_chips_html = f"""<div class="edm-filters" role="group" aria-label="Filter electronic and EDM shows">
    <div class="edm-filter-row"><span class="edm-filter-label">Vibes</span>{subgenres_html}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">Area</span>{areas_html}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">When</span>{when_html}</div>
    <div class="edm-filter-row"><span class="edm-filter-label">Cost</span>{cost_html}</div>
  </div>"""
        hub_js = _EDM_FILTER_JS
        n_cards = len(filtered[:card_limit])
        n_days = len(set(re.findall(r'<h2 class="hub-day" id="([\d-]+)"', "".join(cards_html)))) or 1
        hero_html = f"""<div class="hero">
    {_EDM_HERO_ART}
    <div class="edm-hero-copy">
      <h1>{escape(hub.get('h1') or hub['title'])}<small>Boston · Cambridge · Somerville · Nightclubs &amp; Underground</small></h1>
      <p>{hub['subtitle']}</p>
      <div class="edm-stats"><span class="edm-stat">⚡ {n_cards} shows &amp; club nights</span><span class="edm-stat">💛 {edm_free_count} free / no cover</span><span class="edm-stat">📍 {len(edm_places)} nightlife stages</span></div>
      <a href="../{hub['query']}" class="cta-btn">View on interactive calendar →</a>
    </div>
  </div>"""
    elif is_camps:
        kids_head, kids_css, body_class = "", _CAMPS_CSS, ' class="camps-hub"'
        hero_html, city_chips_html, camps_tail = _camps_sections(filtered)
        hub_js = camps_tail + _CAMPS_FILTER_JS
    cards_joined = "\n".join(cards_html) if cards_html else "<p class='no-hub-events'>No scheduled events matching this directory right now. Check the interactive calendar for all upcoming dates.</p>"

    active_b = 'active' if hub_slug == 'boston' else ''
    active_c = 'active' if hub_slug == 'cambridge' else ''
    active_s = 'active' if hub_slug == 'somerville' else ''
    active_m = 'active' if hub_slug == 'music' else ''
    active_co = 'active' if hub_slug == 'comedy' else ''
    active_f = 'active' if hub_slug == 'free' else ''
    active_fw = 'active' if hub_slug == 'free-events-boston-this-weekend' else ''
    active_ct = 'active' if hub_slug == 'cambridge-events-tonight' else ''
    active_sm = 'active' if hub_slug == 'live-music-somerville' else ''
    active_bg = 'active' if hub_slug == 'board-game-nights-boston' else ''
    active_kf = 'active' if hub_slug == 'kids-family-events-boston' else ''
    active_sc = 'active' if hub_slug == 'summer-camps' else ''
    active_mk = 'active' if hub_slug == 'markets-festivals-boston' else ''
    active_edm = 'active' if hub_slug == 'boston-edm' else ''

    if is_camps or is_kids:
        hub_nav_html = _family_nav(hub_slug, "camps-nav" if is_camps else "kids-nav")
    else:
        hub_nav_html = f"""  <nav class="hub-nav">
    <a href="../">All Events</a>
    <a href="../free-events-boston-this-weekend/" class="{active_fw}">Free Weekend</a>
    <a href="../cambridge-events-tonight/" class="{active_ct}">Cambridge Tonight</a>
    <a href="../live-music-somerville/" class="{active_sm}">Somerville Music</a>
    <a href="../boston-edm/" class="{active_edm}">Boston EDM</a>
    <a href="../board-game-nights-boston/" class="{active_bg}">Board Games</a>
    <a href="../kids-family-events-boston/" class="{active_kf}">Kids &amp; Family</a>
    <a href="../summer-camps/" class="{active_sc}">Summer Camps</a>
    <a href="../markets-festivals-boston/" class="{active_mk}">Markets &amp; Festivals</a>
    <a href="../boston/" class="{active_b}">Boston</a>
    <a href="../cambridge/" class="{active_c}">Cambridge</a>
    <a href="../somerville/" class="{active_s}">Somerville</a>
    <a href="../music/" class="{active_m}">Live Music</a>
    <a href="../comedy/" class="{active_co}">Comedy</a>
    <a href="../free/" class="{active_f}">Free</a>
  </nav>"""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
{meta_tags}
{json_ld_str}
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/logo-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
{kids_head}
<style>
  :root {{
    --bg: #0c0e14;
    --card: #151822;
    --card-hover: #1c202e;
    --fg: #eef1f8;
    --muted: #8e96a8;
    --accent: #5d9bff;
    --border: rgba(255, 255, 255, 0.08);
    --green: #4ade80;
  }}
  body {{
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.5;
  }}
  header {{
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 14px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .logo {{
    font-size: 16px;
    font-weight: 800;
    color: var(--fg);
    text-decoration: none;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .logo span {{ color: var(--accent); }}
  .hub-nav {{
    display: flex;
    gap: 12px;
    font-size: 13px;
    flex-wrap: wrap;
  }}
  .hub-nav a {{
    color: var(--muted);
    text-decoration: none;
    transition: color 0.15s ease;
  }}
  .hub-nav a:hover, .hub-nav a.active {{
    color: var(--accent);
    font-weight: 600;
  }}
  main {{
    max-width: 900px;
    margin: 0 auto;
    padding: 32px 18px 60px;
  }}
  .hero {{
    text-align: center;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }}
  .hero h1 {{
    font-size: 32px;
    font-weight: 800;
    margin: 0 0 10px;
    color: var(--fg);
  }}
  .hero p {{
    font-size: 15px;
    color: var(--muted);
    max-width: 650px;
    margin: 0 auto 20px;
  }}
  .cta-btn {{
    display: inline-block;
    background: var(--accent);
    color: #0c0e14;
    padding: 10px 22px;
    border-radius: 999px;
    font-weight: 700;
    font-size: 14px;
    text-decoration: none;
    box-shadow: 0 2px 12px rgba(93, 155, 255, 0.35);
    transition: transform 0.15s ease, filter 0.15s ease;
  }}
  .cta-btn:hover {{
    filter: brightness(1.1);
    transform: translateY(-1px);
  }}
  .hub-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 12px;
  }}
  @media (min-width: 640px) {{
    .hub-grid {{
      grid-template-columns: repeat(2, 1fr);
    }}
  }}
  .hub-day {{
    grid-column: 1 / -1;
    margin: 20px 0 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--fg);
  }}
  .hub-city-chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0 0 16px;
  }}
  .hub-city-chip {{
    font: inherit;
    font-size: 0.9rem;
    padding: 6px 14px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--card);
    color: var(--fg);
    cursor: pointer;
  }}
  .hub-city-chip.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #0c0e14;
    font-weight: 600;
  }}
  [hidden] {{ display: none !important; }}
  .hub-day:first-child {{
    margin-top: 0;
  }}
  .hub-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: background 0.15s ease, border-color 0.15s ease;
  }}
  .hub-card:hover {{
    background: var(--card-hover);
    border-color: rgba(93, 155, 255, 0.4);
  }}
  .hub-card-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }}
  .hub-date {{
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}
  .badge {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    font-weight: 600;
  }}
  .badge-price {{ background: rgba(255, 255, 255, 0.08); color: var(--fg); }}
  .badge-free {{ background: rgba(74, 222, 128, 0.16); color: var(--green); }}
  .hub-title {{
    font-size: 15px;
    font-weight: 700;
    margin: 0 0 8px;
    line-height: 1.35;
  }}
  .hub-title a {{
    color: var(--fg);
    text-decoration: none;
  }}
  .hub-title a:hover {{
    color: var(--accent);
    text-decoration: underline;
  }}
  .hub-meta {{
    font-size: 12px;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .hub-desc {{ margin: 8px 0 0; color: var(--muted); font-size: 0.85rem; line-height: 1.4; }}
  footer {{
    border-top: 1px solid var(--border);
    padding: 24px 20px;
    text-align: center;
    font-size: 12px;
    color: var(--muted);
  }}
  footer a {{ color: var(--accent); text-decoration: none; }}
  .footer-pwa-btn {{
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
    padding: 0;
    display: inline;
  }}
  .footer-pwa-btn:hover {{ color: var(--accent); }}
{kids_css}
</style>
</head>
<body{body_class}>
<header>
  <a href="../" class="logo"><span>Wicked</span> Boston Events</a>
{hub_nav_html}
</header>
<main>
  {hero_html}
  {city_chips_html}
  <div class="hub-grid">
    {cards_joined}
  </div>
  <p id="hub-none" class="no-hub-events" hidden>{'No camps match those filters. Try removing one.' if is_camps else 'Nothing in this area in the next few weeks. Try another town.'}</p>
  {hub_js}
</main>
<footer>
  <p><a href="../">Wicked Boston Events</a> · Independent Greater Boston Events Calendar · <a href="https://www.instagram.com/wickedbostonevents/" target="_blank" rel="noopener">Instagram: @wickedbostonevents</a><span id="pwa-install-wrap" hidden> · <button type="button" class="footer-pwa-btn" onclick="installPWA()">📲 Add to Home Screen</button></span></p>
</footer>
<script>
  window.addEventListener('beforeinstallprompt', function (e) {{
    e.preventDefault();
    window._pwaPrompt = e;
    var wrap = document.getElementById('pwa-install-wrap');
    if (wrap) wrap.hidden = false;
  }});
  function installPWA() {{
    if (window._pwaPrompt) {{
      window._pwaPrompt.prompt();
      window._pwaPrompt.userChoice.finally(function () {{
        window._pwaPrompt = null;
        var wrap = document.getElementById('pwa-install-wrap');
        if (wrap) wrap.hidden = true;
      }});
    }}
  }}
</script>
</body>
</html>"""



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
        dt = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=EASTERN)
        dt = dt.astimezone(timezone.utc)
        start_str = dt.strftime("%Y%m%dT%H%M%SZ")
        real_end = trusted_end(e)
        end_dt = real_end.astimezone(timezone.utc) if real_end and real_end - dt <= timedelta(hours=12) else dt + timedelta(hours=2)
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
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=EASTERN)
    else:
        dt = dt.astimezone(EASTERN)
    return dt.strftime("%-I:%M %p")


def trusted_end(e):
    """The event's end (Eastern) when we believe it, else None.

    Sources' end times were measured in Nov 2026 (2,937 events, 70 sources): most are real, but
    some are placeholders. Not believed: end at or before the start, an 11:59 PM end, an all-day
    "midnight to midnight" span, exactly 24 hours, or a single sitting under 15 minutes or over 12 hours. Multi-day
    runs (over 24 hours, up to 60 days) are returned for "thru" display; 12-24 hours is dropped
    (an overnight "7 PM to 8 AM" is a bad end, not a two-day event)."""
    raw_start, raw_end = e.get("date") or "", e.get("end") or ""
    if not raw_end or ("T" not in raw_start and " " not in raw_start):
        return None
    try:
        start = datetime.fromisoformat(str(raw_start).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(raw_end).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    start = (start if start.tzinfo else start.replace(tzinfo=EASTERN)).astimezone(EASTERN)
    end = (end if end.tzinfo else end.replace(tzinfo=EASTERN)).astimezone(EASTERN)
    length = end - start
    if length < timedelta(minutes=15) or length == timedelta(days=1) or (end.hour, end.minute) == (23, 59):
        return None
    if (start.hour, start.minute) == (0, 0) and (end.hour, end.minute) == (0, 0):
        return None
    if length <= timedelta(hours=12):
        return end
    if timedelta(days=1) < length <= timedelta(days=60):
        return end
    return None


def _clock(dt, with_ampm=True):
    return dt.strftime("%-I:%M %p" if with_ampm else "%-I:%M")


def format_when(e):
    if not e.get("date") and e.get("ends"):
        try:
            end = datetime.strptime(e["ends"], "%Y-%m-%d")
        except ValueError:
            return format_time(e.get("date"))
        return f"thru {end.month}/{end.day}"
    t_obj = e.get("_time")
    if t_obj:
        raw_d = e.get("date") or ""
        if "T" in raw_d or " " in raw_d:
            end = trusted_end(e)
            start = t_obj.astimezone(EASTERN) if t_obj.tzinfo else t_obj
            if end and end - start > timedelta(hours=12):
                return f"{_clock(start)} · thru {end.strftime('%a %b %-d')}"
            if end:
                same_half = start.strftime("%p") == end.strftime("%p") and end.date() == start.date()
                return f"{_clock(start, not same_half)}–{_clock(end)}"
            return t_obj.strftime("%-I:%M %p")
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
            # Venue is part of the key: a group posting the same title at a different bar each
            # week ("Skip the Small Talk") isn't one recurring event.
            key = (name, e.get("_source_venue") or "", (e.get("venue") or "").strip().lower())
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
    t = unescape(title or "").lower().strip()

    # 1. Strip venue name from title if title starts with venue (e.g. "McCarthys Cambridge Irish Session")
    if venue:
        v_clean = re.sub(r"[^a-z0-9]+", " ", venue.lower()).strip()
        v_core = re.sub(r"^the\s+", "", v_clean).strip()
        t_clean = re.sub(r"[^a-z0-9]+", " ", t).strip()
        for v_cand in [v_clean, v_core]:
            if v_cand and len(v_cand) >= 4 and t_clean.startswith(v_cand):
                t = t_clean[len(v_cand):].strip()
                break

    # 2. Strip leading generic words and prefixes
    t = re.sub(r"^(?:an evening with|an evening of|a night with|in conversation with)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:no cover\s+(?:drag\s+)?|free\s+)", "", t, flags=re.I)
    t = re.sub(r"^(?:live|traditional|weekly|annual)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:a|an)\s+", "", t, flags=re.I)

    # Strip leading author/creator possessives if remainder is a multi-word or long title
    # (e.g. "Harper Lee's To Kill a Mockingbird" -> "to kill a mockingbird")
    m_poss = re.match(r"^(?:[a-z\.\'\-]+\s+){0,3}[a-z\.\'\-]+(?:'s|’s|')\s+(.+)$", t, flags=re.I)
    if m_poss:
        rem = m_poss.group(1).strip()
        if len(rem.split()) >= 2 or len(rem) >= 8:
            t = rem

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
            if sep in (":", " - ", " – ", " — ") and any(left.endswith(suff) for suff in GENERIC_CATEGORY_SUFFIXES):
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
    t = re.sub(r"^(?:a|an)\s+", "", t, flags=re.I)
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
    if s in ("ticketmaster", "seatgeek") or s.startswith("eventbrite"):
        return 1
    if s in ("the boston calendar", "do617", "boston shows", "little muse"):
        return 5
    return 10


# Query parameters that name the event itself: "eventperformances.asp?evt=1252" (24 Hour Music),
# "book?perfcode=931" (Somerville Theatre), "?eventid=206566108" (Trumba). Without them every
# event on such a site has the same URL and they'd all merge.
_EVENT_ID_PARAMS = {"evt", "eid", "eventid", "event_id", "event", "id", "perfcode", "performance", "showid",
                    "show_id", "occurrence", "e"}


def _clean_event_url(u):
    if not u or not isinstance(u, str):
        return ""
    try:
        q = urlparse(u.strip()).query
    except ValueError:
        q = ""
    keep = sorted(p for p in q.split("&") if p.split("=", 1)[0].lower() in _EVENT_ID_PARAMS)
    u = re.sub(r"[?#].*$", "", u).strip().rstrip("/")
    if keep and u:
        return u + "?" + "&".join(keep)
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


_TITLE_FILLER = {"w", "with", "and", "the", "a", "an", "live", "feat", "ft", "presents", "presented", "by"}


def _title_variants(title):
    """Compact spellings of a title for cross-source duplicate detection: the full title and,
    when it has an organizer/series prefix ("MFA: ...", "X presents: ...", "BSO - ..."),
    the part after it. Each variant is lowercase alphanumerics with filler words removed."""
    t = unescape(title or "").lower()
    t = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", t)          # (18+), [SOLD OUT]
    t = re.sub(r"\s+at\s+(?:the\s+)?[\w'\s\.&-]+$", "", t)  # trailing "at The Middle East"
    t = re.sub(r"\s*[-–—|,]\s*(?:boston|cambridge|somerville)(?:,?\s*ma)?\s*$", "", t)  # "LA Phil - Boston"
    pieces = [t]
    m = re.search(r"\bpresents?:?\s+(.+)$", t)
    if m:
        pieces.append(m.group(1))
    for sep in (":", " - ", " – ", " — ", " | "):
        if sep in t:
            # Only the part after the prefix: the prefix itself ("mfa") is shared by
            # unrelated events at the same venue.
            pieces.append(t.split(sep, 1)[1])
    out = [key for rx, key in _SERIES_ALIASES if rx.search(t)]
    for p in pieces:
        toks = [w for w in re.findall(r"[a-z0-9]+", p) if w not in _TITLE_FILLER]
        c = "".join(toks)
        if c and c not in _GENERIC_TITLE_VARIANTS:
            out.append(c)
    return out


# Recurring series each source titles differently. Still only merges at the same venue within
# 90 min (step 5 of _merge_duplicates), so the shared key can't pull in other events.
_SERIES_ALIASES = [
    # "Boston Social Conversations | Millennial Crisis" (Aeronaut), "Boston Conversations @ Aeronaut"
    # (Boston Calendar), "Boston Social Conversations - November Event" (Luma)
    (re.compile(r"\bboston (?:social )?conversations\b"), "series:bostonconversations"),
]

_GENERIC_TITLE_VARIANTS = {"boston", "cambridge", "somerville", "tour", "usa", "concert", "show", "live"}
_VENUE_GENERIC_WORDS = {
    "the", "at", "in", "of", "and", "boston", "cambridge", "somerville", "ma", "public", "library",
    "branch", "main", "central", "west", "east", "north", "south", "university", "college", "school",
    "church", "museum", "theatre", "theater", "hall", "center", "centre", "club", "bar", "pub", "cafe",
    "café", "lounge", "room", "house", "studio", "brewing", "brewery", "company", "co", "downtown",
    "presented", "by", "citizens", "music", "arts", "art",
    # neighborhood / building-type words shared by unrelated places ("Central Square Branch" vs
    # "Copley Square", "Bentley Arena" vs "Warrior Ice Arena")
    "square", "sq", "arena", "stadium", "gymnasium", "gym", "ice", "rink", "field", "park",
}


def _same_physical_venue(e1, e2):
    """Stricter venue check than _merge_duplicates' _venue_match: same geo pin, or a shared
    distinctive word ("Sinclair", "Royale") — not just "Public Library" or "Music Hall"."""
    if e1.get("_venue_unknown") or e2.get("_venue_unknown"):
        return True
    w = lambda v: {re.sub(r"s$", "", x) for x in re.findall(r"\w+", (v or "").lower()) if len(x) >= 2} - _VENUE_GENERIC_WORDS
    if w(e1.get("venue")) & w(e2.get("venue")):
        return True
    g1, g2 = resolve_event_geo(e1), resolve_event_geo(e2)
    if g1 and g2:
        return abs(g1["lat"] - g2["lat"]) < 0.0015 and abs(g1["lng"] - g2["lng"]) < 0.0015
    return False


def _titles_equivalent(a, b):
    """True when any variant pair is identical, or one is a prefix of the other (>= 6 chars)."""
    for x in a:
        for y in b:
            if x == y and len(x) >= 3:
                return True
            short, long_ = (x, y) if len(x) <= len(y) else (y, x)
            if len(short) >= 6 and long_.startswith(short):
                return True
    return False


_RSVP_HOSTS = ("lu.ma", "luma.com", "eventbrite.", "meetup.com", "partiful.com", "heylo.com",
               "dice.fm", "posh.vip", "ticketmaster.", "seatgeek.com", "axs.com", "tixr.com")


def _is_event_specific_link(url):
    """An RSVP/ticket page for one event (lu.ma/8ugz1m1n, eventbrite.com/e/...)."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return False
    path = u.path.strip("/")
    # event slugs carry an id ("8ugz1m1n") or a sub-path ("e/..."); "lu.ma/boston" is a listing
    return any(h in u.netloc.lower() for h in _RSVP_HOSTS) and len(path) >= 6 and bool(re.search(r"\d|/", path))


def _is_generic_link(url):
    """A site root or listing page rather than an event page: "x.com", "x.com/events/"."""
    try:
        u = urlparse((url or "").strip())
    except ValueError:
        return True
    if not u.netloc:
        return True
    path = u.path.strip("/").lower()
    listing = ("", "events", "calendar", "event-calendar", "upcoming-events", "whats-on")
    if "event" in u.fragment.lower():  # "aeronautbrewing.com/visit/somerville/#events"
        return True
    return path.rsplit("/", 1)[-1] in listing and not u.query


_TITLE_STOPWORDS = {"the", "and", "with", "at", "in", "of", "a", "an", "for", "to", "on", "live", "night",
                    "tickets", "presents", "tour", "boston", "show", "featuring", "feat", "event", "events"}


def _title_words(t):
    return {w for w in re.findall(r"[a-z0-9]+", unescape(t or "").lower()) if len(w) > 2 and w not in _TITLE_STOPWORDS}


def _titles_unrelated(t1, t2):
    """No meaningful word in common, and not just a spacing/punctuation variant ("half•alive"/"halfalive")."""
    if not t1 or not t2:
        return False
    w1, w2 = _title_words(t1), _title_words(t2)
    if not w1 or not w2 or (w1 & w2):
        return False
    squash = lambda t: re.sub(r"[^a-z0-9]+", "", unescape(t).lower())
    s1, s2 = squash(t1), squash(t2)
    return not (s1 and s2 and (s1 in s2 or s2 in s1))


_SHARED_WORD_STOP = _TITLE_STOPWORDS | {
    "from", "this", "that", "your", "our", "you", "all", "new", "day", "edition", "special", "guest",
    "guests", "sold", "out", "free", "party", "series", "club", "group", "meeting", "session", "night",
    "nights", "music", "concert", "festival", "celebration", "annual", "part", "vs", "mens", "womens",
    "presented", "conversation", "talk", "book", "author", "event", "premiere", "world", "american",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "weekly", "monthly",
}


def _fold(t):
    t = unicodedata.normalize("NFKD", unescape(t or "")).encode("ascii", "ignore").decode()
    return t.lower()


def _distinctive_words(title, venue_words=()):
    return {w for w in re.findall(r"[a-z]+", _fold(title))
            if len(w) >= 3 and w not in _SHARED_WORD_STOP and w not in venue_words}


def _title_numbers(title):
    """Numbers in a title other than years: "Round 3", "Day 2", "No. 5"."""
    return {n for n in re.findall(r"\d+", _fold(title)) if not re.fullmatch(r"(?:19|20)\d\d", n)}


def _numbers_conflict(t1, t2):
    """Both titles carry numbers and they differ: "Ages 27-37" vs "Ages 36-48", "Round 3" vs "Round 5"."""
    n1, n2 = _title_numbers(t1), _title_numbers(t2)
    # Neither contains the other: "Brutalismus 3000" vs "Brutalismus 3000 (18+)" or "Ho99o9" vs
    # "Ho99o9 & N8NOFACE" is the same show with an extra detail, not a different one
    return bool(n1 and n2 and not (n1 <= n2 or n2 <= n1))


def _venue_words(v):
    return {re.sub(r"s$", "", x) for x in re.findall(r"[a-z0-9]+", _fold(v)) if len(x) >= 2} - _VENUE_GENERIC_WORDS


def title_word_freq(events):
    """How many distinct titles each distinctive word appears in, across the whole calendar."""
    from collections import Counter
    freq = Counter()
    for t in {_fold(e.get("name")).strip() for e in events}:
        freq.update(_distinctive_words(t))
    return freq


def _same_event_retitled(e1, e2, freq):
    """Two sources, same venue, same time, titled differently: "A Conversation with Trisha Paytas"
    (the venue) and "SOLD OUT! Trisha Paytas: Crying on the Kitchen Floor" (the bookstore).
    Requires shared words that are rare across the calendar, so "Sunday Jazz Brunch" and
    "Sunday Drag Brunch" or two hockey games at different rinks never merge."""
    if not freq or (e1.get("_source_venue") or "") == (e2.get("_source_venue") or ""):
        return False
    t1, t2 = e1.get("_time"), e2.get("_time")
    if not t1 or not t2 or (t1.hour, t1.minute) == (0, 0) or (t2.hour, t2.minute) == (0, 0):
        return False
    if abs((t1 - t2).total_seconds()) > 30 * 60:
        return False
    vw1, vw2 = _venue_words(e1.get("venue")), _venue_words(e2.get("venue"))
    if not (vw1 & vw2):
        return False
    if _numbers_conflict(e1.get("name"), e2.get("name")):
        return False  # "Round 3" vs "Round 5"
    vw = vw1 | vw2 | {w.rstrip("s") for w in vw1 | vw2}
    shared = _distinctive_words(e1.get("name"), vw) & _distinctive_words(e2.get("name"), vw)
    if len(shared) >= 3:
        return True
    rare = [w for w in shared if freq.get(w, 0) <= 6]
    if len(shared) == 2 and rare:
        return True
    return len(shared) == 1 and len(rare) == 1 and len(rare[0]) >= 5 and freq.get(rare[0], 0) <= 4


def _merge_duplicates(events, word_freq=None):
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

    def _is_attraction_tour(e):
        n = (e.get("name") or "").lower().strip()
        cat = (e.get("category") or "").lower()
        if cat in ("music", "comedy"):
            return False
        if "sports museum tour" in n:
            return True
        if re.search(r"\b(sports\s+museum|museum|stadium|brewery|distillery|historical|historic|walking)\s+tour\b", n):
            return True
        return False

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
        # If one time is noon (12:00) while the other is an evening/night show (>= 16:00),
        # it is an untimed/placeholder broker listing (e.g. SeatGeek 12 PM default for evening concert)
        if ((t1.hour == 12 and t1.minute == 0 and t2.hour >= 16) or
            (t2.hour == 12 and t2.minute == 0 and t1.hour >= 16)):
            return False
        diff_mins = abs((t1 - t2).total_seconds()) / 60.0
        s1 = (e1.get("_source_venue") or e1.get("source") or "").lower()
        s2 = (e2.get("_source_venue") or e2.get("source") or "").lower()

        # For recurring attraction / museum / venue tours (e.g. "The Sports Museum Tour"):
        # collapse multiple departures on the same date into a single daily listing
        if _is_attraction_tour(e1) and _is_attraction_tour(e2):
            return False

        # Same source with >= 45m diff: distinct show sets (e.g. 7:00 PM and 9:30 PM), unless one
        # listing comes from a ticket reseller, whose times are often doors or off by an hour
        resale = any(h in f"{e1.get('url')} {e2.get('url')}".lower() for h in (
            "eventschaser.com", "vividseats.com", "stubhub.com", "ticketnetwork.com", "tickpick.com"))
        if s1 and s1 == s2 and diff_mins >= 45 and not resale:
            return True
        # Different sources within 90m (doors vs show time): same show
        if s1 != s2 and diff_mins <= 90:
            return False
        # If diff > 90m: separate shows
        if diff_mins > 90:
            return True
        return False

    def _separate_listings(e1, e2):
        """Same source, each with its own event page: the source lists them as two events
        (ICA's "Boston Family Days" and "Museums on Us" both at 10am), so never merge them
        on loose venue/time/keyword similarity."""
        s1 = (e1.get("_source_venue") or "").lower()
        u1, u2 = (e1.get("url") or "").rstrip("/"), (e2.get("url") or "").rstrip("/")
        if not (s1 and s1 == (e2.get("_source_venue") or "").lower() and u1 and u2 and u1 != u2):
            return False
        # A shared fallback (the source's calendar page) is not an event page
        return u1 != (e1.get("venue_url") or "").rstrip("/") and u2 != (e2.get("venue_url") or "").rstrip("/")

    def _far_apart(e1, e2):
        """Same title at two places we can locate, over half a mile apart: separate events,
        e.g. citywide "Boston Family Days" at the ICA and at the Aquarium on the same Sunday."""
        try:
            g1, g2 = resolve_event_geo(e1), resolve_event_geo(e2)
        except Exception:
            return False
        if not (g1 and g2) or g1.get("lat") is None or g2.get("lat") is None:
            return False
        dlat = (g1["lat"] - g2["lat"]) * 69.0
        dlng = (g1["lng"] - g2["lng"]) * 51.3  # miles per degree of longitude at Boston's latitude
        return (dlat * dlat + dlng * dlng) ** 0.5 > 0.5

    def _venue_match(v1, v2, e1, e2):
        if not v1 or not v2:
            return True
        if (e1 and e1.get("_venue_unknown")) or (e2 and e2.get("_venue_unknown")):
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
            "brewing", "cafe", "café", "center", "hall", "club", "studio", "house", "room",
            # every library shares these; branches are told apart by their own names
            "public", "library", "branch", "main", "central", "square", "sq", "arena", "stadium",
        }
        # len >= 2: the "s" of "Dani's" / "Lou's" is not a shared venue word
        w1 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v1_low) if len(w) >= 2} - generic_vwords
        w2 = {re.sub(r"s$", "", w) for w in re.findall(r"\w+", v2_low) if len(w) >= 2} - generic_vwords
        if w1 and w2 and (w1 & w2):
            return True
        if e1 and e2:
            g1 = resolve_event_geo(e1)
            g2 = resolve_event_geo(e2)
            if g1 and g2:
                if g1.get("venue") and g1.get("venue") == g2.get("venue"):
                    return True
                lat1, lng1 = g1.get("lat"), g1.get("lng")
                lat2, lng2 = g2.get("lat"), g2.get("lng")
                if lat1 is not None and lat2 is not None and lng1 is not None and lng2 is not None:
                    if abs(lat1 - lat2) < 0.0015 and abs(lng1 - lng2) < 0.0015:
                        return True
        return False

    for e in events:
        raw_name = unescape(e.get("name") or "").strip()
        e["name"] = raw_name
        full = re.sub(r"[^a-z0-9]+", " ", raw_name.lower()).strip()
        venue_str = e.get("venue") or ""
        head = _normalize_title_head(raw_name, venue=venue_str)
        venue = venue_str.lower()
        curl = _clean_event_url(e.get("url"))

        match = None
        # 0. Canonical specific URL match check
        if curl and curl in seen_url:
            for cand in seen_url[curl]:
                s_cand = (cand.get("_source_venue") or cand.get("source") or "").lower()
                s_cur = (e.get("_source_venue") or e.get("source") or "").lower()
                if s_cand != s_cur or not _is_different_show(e, cand):
                    match = cand
                    break

        # 1. Exact match check
        if not match and full and len(full) >= 4 and full in seen_exact:
            for cand in seen_exact[full]:
                if not _is_different_show(e, cand) and not _far_apart(e, cand):
                    match = cand
                    break

        # 2. Normalized head match check
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS and head in seen_head:
            for cand in seen_head[head]:
                c_venue = (cand.get("venue") or "").lower()
                if _numbers_conflict(raw_name, cand.get("name")):
                    continue
                if _venue_match(venue, c_venue, e, cand):
                    if not _is_different_show(e, cand):
                        match = cand
                        break

        # 3. Same physical venue title prefix/containment match
        if not match and head and len(head) >= 4 and head not in GENERIC_HEADS:
            for cand in out:
                c_venue = (cand.get("venue") or "").lower()
                if _separate_listings(e, cand) or _numbers_conflict(raw_name, cand.get("name")):
                    continue
                if _venue_match(venue, c_venue, e, cand) and not _is_different_show(e, cand):
                    cand_head = _normalize_title_head(cand.get("name") or "", venue=cand.get("venue"))
                    if cand_head and cand_head not in GENERIC_HEADS:
                        if (cand_head in head or head in cand_head) and min(len(head), len(cand_head)) >= 6:
                            match = cand
                            break
                        h_words = head.split()
                        c_words = cand_head.split()
                        if len(h_words) >= 2 and len(c_words) >= 2 and h_words[:2] == c_words[:2]:
                            prefix2 = " ".join(h_words[:2])
                            if prefix2 not in GENERIC_HEADS and len(prefix2) >= 6:
                                match = cand
                                break

        # 4. Same physical venue & same start time window (<= 15 mins) matching
        if not match and venue and len(venue) >= 4:
            for cand in out:
                c_venue = (cand.get("venue") or "").lower()
                if _separate_listings(e, cand):
                    continue
                if _venue_match(venue, c_venue, e, cand) and not _is_different_show(e, cand):
                    t_e = e.get("_time")
                    t_c = cand.get("_time")
                    if t_e and t_c:
                        diff_m = abs((t_e - t_c).total_seconds()) / 60.0
                        if diff_m <= 15:
                            # A. Domain match (both point to same official venue domain, e.g. thecomedystudio.com)
                            u_e = e.get("url") or ""
                            u_c = cand.get("url") or ""
                            host_e = re.sub(r"^https?://(?:www\.)?", "", u_e).split("/")[0].lower()
                            host_c = re.sub(r"^https?://(?:www\.)?", "", u_c).split("/")[0].lower()
                            # Shared platforms host many unrelated events at the same hour (every BPL
                            # branch is on bpl.bibliocommons.com), so a shared host proves nothing there.
                            shared_platform = any(p in host_e for p in (
                                "libcal.com", "bibliocommons.com", "assabetinteractive.com", "lu.ma", "luma.com",
                                "partiful.com", "heylo.com", "humanitix.com", "ticketleap.com", "sched.com",
                                # ticket sellers many bands/promoters share ("Truancy" and "Chick Singer Night")
                                "24hourmusic.com", "tickettailor.com", "etix.com", "ticketweb.com", "showclix.com",
                                "simpletix.com", "eventim", "universe.com", "dice.fm", "tixr.com", "axs.com"))
                            if host_e and host_e == host_c and not shared_platform and host_e not in ("eventbrite.com", "ticketmaster.com", "seatgeek.com", "meetup.com", "facebook.com", "instagram.com", "thebostoncalendar.com", "do617.com"):
                                match = cand
                                break

                            # B. Shared comedy/open mic/theater category and significant keyword overlap
                            cat_e = (e.get("category") or "").lower()
                            cat_c = (cand.get("category") or "").lower()
                            if _numbers_conflict(raw_name, cand.get("name")):
                                pass  # "Round 3" vs "Round 5"
                            elif cat_e and cat_e == cat_c and cat_e in ("comedy", "theater", "dance", "community"):
                                words_e = {w for w in re.findall(r"\w+", raw_name.lower()) if len(w) >= 4} - {"free", "night", "show", "live", "session"}
                                words_c = {w for w in re.findall(r"\w+", (cand.get("name") or "").lower()) if len(w) >= 4} - {"free", "night", "show", "live", "session"}
                                if (words_e and words_c and (words_e & words_c)) or ("open" in raw_name.lower() and "open" in (cand.get("name") or "").lower()):
                                    match = cand
                                    break

        # 5. Same venue, start within 90 min, titles that differ only in formatting
        #    ("half•alive"/"halfalive", "MFA: Late Nites"/"Late Nites", "MPH"/"MPH",
        #    "Global Arts Live presents: LE VENT DU NORD"/"Le Vent du Nord").
        if not match:
            keys_e = _title_variants(raw_name)
            for cand in out:
                if not _same_physical_venue(e, cand) or _is_different_show(e, cand):
                    continue
                keys_c = _title_variants(cand.get("name") or "")
                if _numbers_conflict(raw_name, cand.get("name")):
                    continue  # "Ages 27-37" vs "Ages 36-48", "Round 3" vs "Round 5"
                if _separate_listings(e, cand) and not (
                        (e.get("_time") == cand.get("_time") and keys_e[:1] == keys_c[:1])
                        or (_source_priority(e.get("_source_venue")) < 10 and _titles_equivalent(keys_e, keys_c))):
                    # Same source, two pages: separate events, except the same title at the same minute
                    # (Ticketmaster's "CamelPhat" / "CamelPhat (21 and Over)") or an aggregator listing
                    # one show twice (The Boston Calendar's two "Phoebe Robinson: Feral & Fired Up!")
                    continue
                t_e, t_c = e.get("_time"), cand.get("_time")
                if not t_e or not t_c or abs((t_e - t_c).total_seconds()) > 90 * 60:
                    continue
                if _titles_equivalent(keys_e, keys_c):
                    match = cand
                    break

        # 6. Same venue and time from two sources under different titles (see _same_event_retitled)
        if not match and word_freq:
            for cand in out:
                # No _far_apart check: ticket sellers' venue pins are often off by a few blocks, and
                # the venue-name overlap required here already places both at the same venue.
                if _same_event_retitled(e, cand, word_freq):
                    match = cand
                    break

        if match:
            # Consolidate multiple hourly tour departures into a single daily listing
            if _is_attraction_tour(match) or _is_attraction_tour(e):
                match.setdefault("_tour_times", [])
                t_m = match.get("_time")
                if not t_m and match.get("date"):
                    try:
                        t_m = datetime.fromisoformat(str(match["date"]).replace("Z", "+00:00"))
                        t_m = t_m.replace(tzinfo=EASTERN) if t_m.tzinfo is None else t_m.astimezone(EASTERN)
                        match["_time"] = t_m
                    except Exception:
                        pass
                t_e = e.get("_time")
                if not t_e and e.get("date"):
                    try:
                        t_e = datetime.fromisoformat(str(e["date"]).replace("Z", "+00:00"))
                        t_e = t_e.replace(tzinfo=EASTERN) if t_e.tzinfo is None else t_e.astimezone(EASTERN)
                        e["_time"] = t_e
                    except Exception:
                        pass
                if t_m and t_m not in match["_tour_times"]:
                    match["_tour_times"].append(t_m)
                if t_e and t_e not in match["_tour_times"]:
                    match["_tour_times"].append(t_e)
                if t_m and t_e and t_e < t_m:
                    match["_time"] = t_e
                    if e.get("date"):
                        match["date"] = e["date"]
                all_times = sorted(match["_tour_times"])
                if len(all_times) > 1:
                    min_str = all_times[0].strftime("%-I:%M %p")
                    max_str = all_times[-1].strftime("%-I:%M %p")
                    v_label = match.get("venue") or "the venue"
                    match["description"] = f"Hourly tours departing {min_str} to {max_str} at {v_label}."

            # Upgrade placeholder time (00:00 midnight or 12:00 noon) when confirmed evening showtime arrives
            m_time = match.get("_time")
            e_time = e.get("_time")
            m_is_placeholder = bool(m_time and (m_time.hour == 0 or (m_time.hour == 12 and m_time.minute == 0)))
            e_is_evening = bool(e_time and e_time.hour >= 16)
            if m_is_placeholder and e_is_evening:
                match["_time"] = e_time
                if e.get("date"):
                    match["date"] = e["date"]

            match.setdefault("_alt_sources", [])
            src_url = e.get("url")
            src_name = e.get("_source_venue") or e.get("venue") or "source"
            is_placeholder_url = bool(src_url and ("-12-pm/" in src_url or "-12-am/" in src_url))

            # A venue feed may link only an organizer homepage ("themillennialcrisis.com/events");
            # an RSVP page for this specific event is the better primary link.
            if _is_event_specific_link(src_url) and _is_generic_link(match.get("url")):
                old_url = match.get("url")
                if old_url and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": match.get("_source_venue"), "url": old_url, "price": match.get("price"), "name": match.get("name")})
                match["url"] = src_url

            # If the newly arrived event has higher priority (e.g. direct venue vs aggregator)
            # or if match currently has a placeholder time/URL, upgrade primary info
            cur_prio = _source_priority(match.get("_source_venue"))
            new_prio = _source_priority(e.get("_source_venue"))
            # Equal rank: the venue's own listing beats another organization's ("WBUR CitySpace"'s
            # page for its talk over Brookline Booksmith's "WBUR CitySpace: Sofia Franklyn")
            own = lambda x: bool(_venue_words(x.get("_source_venue")) & _venue_words(x.get("venue")))
            if new_prio == cur_prio and own(e) and not own(match):
                new_prio += 1
            if (m_is_placeholder and e_is_evening) or (new_prio > cur_prio):
                old_url = match.get("url")
                old_src = match.get("_source_venue")
                old_is_placeholder = bool(old_url and ("-12-pm/" in old_url or "-12-am/" in old_url))
                if old_url and not old_is_placeholder and not any(a.get("url") == old_url for a in match["_alt_sources"]):
                    match["_alt_sources"].append({"venue": old_src, "url": old_url, "price": match.get("price"), "name": match.get("name")})
                match["url"] = e.get("url")
                match["name"] = e.get("name")
                # The category goes with the title it describes: a "Time: TBA" placeholder that
                # absorbed a same-day "Pop Up Market" must not label the game watch that replaces it
                if e.get("category") and e["category"] not in ("other", "community"):
                    match["category"] = e["category"]
                if not e.get("_venue_unknown") or match.get("_venue_unknown"):
                    match["venue"] = e.get("venue")  # never replace a real venue with a placeholder
                match["_source_venue"] = e.get("_source_venue")
                if e_time and (e_time.hour != 0 or e_time.minute != 0):
                    match["_time"] = e_time
            elif src_url and not is_placeholder_url and not any(a.get("url") == src_url for a in match["_alt_sources"]) and src_url != match.get("url"):
                match["_alt_sources"].append({"venue": src_name, "url": src_url, "price": e.get("price"), "name": e.get("name")})

            # If match has 19:00:00 (Eventbrite discovery fallback) while e has a real/earlier time, prefer e
            m_time = match.get("_time")
            e_time = e.get("_time")
            m_src = (match.get("_source_venue") or match.get("venue") or "").lower()
            if "eventbrite" in m_src and m_time and m_time.hour == 19 and m_time.minute == 0 and e_time and not (e_time.hour == 19 and e_time.minute == 0):
                match["_time"] = e_time
                if e.get("date"):
                    match["date"] = e["date"]

            # The venue's own price beats a listings site's ("$5 + fee" from Club Café over "Free").
            if new_prio > cur_prio and e.get("price"):
                match["price"] = e["price"]
            elif not match.get("price") and e.get("price"):
                match["price"] = e["price"]

            if match.get("_venue_unknown") and not e.get("_venue_unknown") and e.get("venue"):
                match["venue"] = e["venue"]
                match.pop("_venue_unknown", None)
                for k in ("lat", "lng", "address", "locality", "postal_code"):
                    if e.get(k):
                        match[k] = e[k]

            p_venue = (match.get("venue") or "").lower()
            if p_venue in generic_sources and venue and venue not in generic_sources and not e.get("_venue_unknown"):
                match["venue"] = e.get("venue")

            if (not match.get("category") or match.get("category") in ("other", "community")) and e.get("category") and e.get("category") not in ("other", "community"):
                match["category"] = e["category"]

            if not match.get("genre") and e.get("genre"):
                match["genre"] = e["genre"]

            if not match.get("description") and e.get("description"):
                match["description"] = e["description"]

            if (not match.get("lat") or not match.get("lng")) and e.get("lat") and e.get("lng"):
                match["lat"] = e.get("lat")
                match["lng"] = e.get("lng")
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
            if is_placeholder_or_closed_event(name) or is_standing_exhibit(e):
                continue
            if is_service_ad(name, e.get("venue")):
                continue
            entry = {"venue_url": r["url"], **e, "_source_venue": r["venue"]}
            # Some sources send pre-escaped text ("R&amp;B Jam"); the page escapes again on render
            for k in ("name", "description"):
                if isinstance(entry.get(k), str) and "&" in entry[k]:
                    entry[k] = unescape(entry[k])
            if entry.get("url"):
                entry["url"] = fix_doubled_url(entry["url"])
            entry["url"] = sanitize_event_url(entry.get("url"), fallback=r.get("url"))
            entry["venue"] = e.get("venue") or r["venue"]
            if e.get("venue_unknown") or not (e.get("venue") or "").strip():
                # The source gave no venue (e.g. Meetup hides it from non-members), so "venue" is
                # just the group/source name. Let dedup take the real venue from another listing.
                entry["_venue_unknown"] = True
            if is_utility_event(name):
                entry["category"] = "services"
            elif is_deal_event(name):
                entry["category"] = "deals"
            elif is_kid_family_event(name, entry.get("venue")):
                entry["category"] = "family"
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
    word_freq = title_word_freq([e for evs in buckets.values() for e in evs])
    for date_key, events in list(buckets.items()):
        events.sort(key=lambda e: e["_time"])
        buckets[date_key] = _merge_duplicates(events, word_freq)
    ongoing.sort(key=lambda e: e.get("_time") or datetime.min.replace(tzinfo=EASTERN), reverse=True)
    return sorted(buckets.items()), tba, ongoing


def _load_highlights():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highlights.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    active = []
                    for h in data:
                        exp = h.get("expires")
                        if exp and exp < now_str:
                            continue
                        active.append(h)
                    return active
        except Exception:
            pass
    return []


def _get_event_highlight(e, highlights):
    if not highlights:
        return None
    name = (e.get("name") or "").lower()
    venue = (e.get("venue") or e.get("_source_venue") or "").lower()
    t_obj = e.get("_time")
    if t_obj:
        if getattr(t_obj, "tzinfo", None) is None:
            date_str = t_obj.date().isoformat()
        else:
            date_str = t_obj.astimezone(EASTERN).date().isoformat()
    else:
        raw_d = e.get("date") or ""
        date_str = raw_d[:10]
        try:
            dt = datetime.fromisoformat(raw_d)
            if dt.tzinfo:
                date_str = dt.astimezone(EASTERN).date().isoformat()
        except Exception:
            pass

    for h in highlights:
        m = h.get("match", {})
        nc = m.get("name_contains", "").lower()
        vc = m.get("venue_contains", "").lower()
        if nc and nc not in name:
            continue
        if vc and vc not in venue:
            continue
        sd = h.get("start_date")
        if sd and date_str and sd > date_str:
            continue
        exp = h.get("expires")
        if exp and date_str and exp < date_str:
            continue
        return h
    return None


def get_seasonal_theme(dt: datetime):
    """(theme_key, emoji, label) for the holiday on dt's date, or (None, None, None).
    The holiday list, dates and palettes live in holiday_themes.py."""
    from holiday_themes import holiday_on
    h = holiday_on(dt.date() if isinstance(dt, datetime) else dt)
    return (h["key"], h["emoji"], h["label"]) if h else (None, None, None)


def render_page(results, weather=None, luckyseat_shows=None):
    highlights = _load_highlights()
    if not any(r.get("venue") == "Community Submissions" for r in results):
        comm = _load_community_events()
        if comm:
            results = list(results) + comm
    flag_shared_source_points(results)  # before any resolve_event_geo call below

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
            (e.get("venue") or "").strip().lower(),
        ) in recurring_keys

    def render_event(e):
        raw_title = e.get("name") or "Untitled"
        if "karakoe" in raw_title.lower():
            raw_title = re.sub(r"\bKarakoe\b", "Karaoke", raw_title, flags=re.I)
        title = escape(raw_title)
        ev_id = _event_stable_id(e)
        ev_url = e.get("url") or ""
        if "google.com/calendar/event" in ev_url or "calendar.google.com" in ev_url:
            if "manray" in (e.get("venue") or "").lower():
                ev_url = "https://manrayclub.com/monthly-calendar/"
            else:
                ev_url = ""
        link = (
            f'<a href="{escape(ev_url)}" target="_blank" rel="noopener">{title}</a>'
            if ev_url else title
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

        cat = _effective_category(e)
        genre = e.get("genre")
        if not genre and cat in ("music", "clubbing"):
            genre = infer_music_genre(e.get("name"), e.get("venue"), description=e.get("description"), category=cat)
            e["genre"] = genre

        bucket = category_bucket(cat)
        if genre and genre in MUSIC_GENRES:
            ginfo = MUSIC_GENRES[genre]
            gcolor = ginfo["color"]
            glabel = ginfo["label"]
            cat_tag = f'<span class="cat-pill genre-pill" data-genre="{escape(genre)}" title="Music Genre: {escape(glabel)}" style="--cat-c:{gcolor}; background:{gcolor}18; border-color:{gcolor}33; color:{gcolor}">{escape(glabel)}</span>'
        else:
            color, icon = CATEGORY_STYLES.get(cat, CATEGORY_STYLES["other"])
            cat_tag = f'<span class="cat-pill" style="--cat-c:{color}; background:{color}18; border-color:{color}33; color:{color}"><span class="chip-icon">{icon} </span>{escape(cat)}</span>'
        venue = e.get("venue") or ""
        source = e.get("_source_venue") or ""
        if "88 club" in raw_title.lower() and (not venue or venue.startswith("@") or venue.lower() in ("boston", "massachusetts", "other")):
            venue = "The 88 Club"
            e = dict(e)
            e["venue"] = venue
        if source == "Deep Cuts Medford" and "do617.com" in (e.get("url") or "") and venue.lower() != "deep cuts":
            source = "Do617"
            e = dict(e)
            e["_source_venue"] = source
        city = _event_city(venue, source, e)
        recurring = is_recurring(e)
        is_hourly = bool(e.get("_tour_times") and len(e["_tour_times"]) > 1)
        recur_flag = "hourly" if is_hourly else ("weekly" if recurring else "once")
        recur_badge = '<span class="recur">↻ hourly</span>' if is_hourly else ('<span class="recur">↻ weekly</span>' if recurring else "")
        alts = e.get("_alt_sources") or []
        alt_html = ""
        if alts:
            alt_parts, other_titles = [], []
            for a in alts:
                if not a.get("url"):
                    continue
                v_name = escape(a.get("venue") or "source")
                a_price = f" ({escape(a['price'])})" if a.get("price") and a["price"] != e.get("price") else ""
                # Not "link": that holds the card's own title link, rendered below
                alt_a = f'<a href="{escape(a["url"])}" target="_blank" rel="noopener">'
                if _titles_unrelated(raw_title, a.get("name")):
                    # Merged as the same time & place but titled differently: maybe a different
                    # event (or a tour name vs the band). Show its title so it's never hidden.
                    other_titles.append(f'{alt_a}{escape(a["name"])}</a> <span class="also-src">({v_name})</span>')
                else:
                    alt_parts.append(f'{alt_a}{v_name}{a_price}</a>')
            if alt_parts:
                alt_joined = " · ".join(alt_parts)
                alt_html = f'<span class="alt-sources">also on {alt_joined}</span>'
            if other_titles:
                alt_html += f'<span class="also-listed">Also listed: {" · ".join(other_titles)}</span>'

        compare_html = _build_compare_links(e, raw_title)

        geo = resolve_event_geo(e)
        geo_attrs = ""
        geo_btn = ""
        if geo:
            geo_attrs = f' data-lat="{geo["lat"]}" data-lng="{geo["lng"]}" data-venue-name="{escape(geo["venue"])}" data-neighborhood="{escape(geo["neighborhood"])}"'
            geo_btn = ' <button type="button" class="venue-map-jump" title="View on Map"><span class="chip-icon">📍</span><span class="indie-jump-label">map</span></button>'

        sub_name, sub_slug = resolve_subarea(city, e, geo)
        if sub_slug == "suburbs_other" and e.get("locality"):
            sub_name = e["locality"]  # show the actual town; the filter group stays "Outer Suburbs"
        elif sub_slug == "suburbs_other" and e.get("_venue_unknown"):
            sub_name = "Location TBA"  # the source hid the venue; don't claim it's in the suburbs
        sub_attrs = f' data-subarea="{escape(sub_slug)}"'
        sub_tag = f' <span class="subarea-tag">· {escape(sub_name)}</span>'

        transit_str = resolve_transit_lines(city, sub_slug, e, geo)
        transit_attr = f' data-transit="{escape(transit_str)}"' if transit_str else ""

        t_obj = e.get("_time")
        raw_date = e.get("date") or ""
        is_date_only = "T" not in raw_date and " " not in raw_date
        if t_obj and not is_date_only:
            h = t_obj.hour
            # 6:00 AM to 4:59 PM is daytime; 5:00 PM to 5:59 AM is evening / night
            if 6 <= h < 17:
                tod_val = "day"
            elif h >= 17 or h > 0:
                tod_val = "night"
            else:
                tod_val = "night" if ("00:00" in raw_date or "12:00" in raw_date) else "all"
            time_mins = t_obj.hour * 60 + t_obj.minute
            time_attr = f' data-time-mins="{time_mins}" data-time-str="{t_obj.strftime("%H:%M")}"'
        else:
            tod_val = "all"
            time_attr = ' data-time-mins="-1"'
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
        star_btn = '<button type="button" class="star-btn" title="Add to My Schedule" aria-label="Add to My Schedule">☆</button>'

        raw_desc = (e.get("description") or "").replace("***", "").replace("**", "").replace("__", "").replace("`", "").strip()
        if "[" in raw_desc:
            raw_desc = re.sub(r'\[/?[a-zA-Z0-9_-]+[^\]]*\]?', ' ', raw_desc)
        if "<" in raw_desc:
            raw_desc = re.sub(r'<[^>]+>', ' ', raw_desc)
        raw_desc = re.sub(r'\s+', ' ', raw_desc).strip()
        desc = raw_desc[:180]
        desc_html = f'<div class="desc">{escape(desc)}</div>' if desc else ""
        free_flag = "true" if is_free else "false"
        lgbtq_attr = ' data-lgbtq="true"' if is_lgbtq_event(e) else ''
        epoch_attr = f' data-epoch="{int(t_obj.timestamp())}"' if t_obj else ''
        end_dt = trusted_end(e) if t_obj else None
        if end_dt and end_dt - t_obj <= timedelta(hours=12):
            epoch_attr += f' data-end-epoch="{int(end_dt.timestamp())}"'
        genre_attr = f' data-genre="{escape(genre)}"' if genre else ''
        v_prefix = f" · {venue_html}" if venue_html else ""

        hl = _get_event_highlight(e, highlights)
        hl_class = " highlighted" if hl else ""
        hl_attr = ' data-highlight="true"' if hl else ""
        b_text = (hl.get("badge") or "Editor's Pick") if hl else ""
        note = hl.get("note") if hl else None
        tooltip = f"{b_text} — {note}" if (note and b_text) else (note or b_text or "Curated recommendation")
        hl_badge = f' <span class="badge-highlight" title="{escape(tooltip)}"><span class="chip-icon">✨ </span>{escape(b_text)}</span>' if hl else ""
        note_html = f'<div class="curator-note"><span class="note-label">Why we recommend:</span> {escape(note)}</div>' if note else ""

        return (
            f'<li class="event{hl_class}" data-id="{ev_id}" data-cat="{escape(cat)}" data-bucket="{escape(bucket)}"{genre_attr} '
            f'data-venue="{escape(source)}" data-city="{escape(city)}"{sub_attrs}{transit_attr}{tod_attr}{time_attr} '
            f'data-recur="{recur_flag}" data-free="{free_flag}"{lgbtq_attr}{epoch_attr}{geo_attrs}{hl_attr}>'
            f'<div class="when">{escape(format_when(e))}</div>'
            f'<div class="what">{star_btn}{link}{price_tag}{recur_badge}{hl_badge}'
            f'<div class="venue-tag">{cat_tag}{v_prefix}{sub_tag}{extra_html}{cal_html}</div>'
            f'{desc_html}{note_html}</div></li>'
        )

    bucket_name_order = [b for b, _ in CATEGORY_BUCKETS]
    city_day_order = ["cambridge", "somerville", "boston", "other"]

    def _render_buckets(events):
        by_bucket = {b: [] for b in bucket_name_order}
        for e in events:
            c = _effective_category(e)
            by_bucket.setdefault(category_bucket(c), []).append(e)
        bucket_blocks = []
        for bname in bucket_name_order:
            bucket_events = by_bucket.get(bname) or []
            if not bucket_events:
                continue
            bucket_events.sort(key=lambda ev: ev.get("_time") or datetime.max.replace(tzinfo=EASTERN))
            cats = dict(CATEGORY_BUCKETS).get(bname, [])
            accent = CATEGORY_STYLES.get(cats[0], CATEGORY_STYLES["other"])[0] if cats else CATEGORY_STYLES["other"][0]
            items = "\n".join(render_event(e) for e in bucket_events)
            bucket_blocks.append(f'''
            <div class="bucket" data-bucket="{escape(bname)}" style="--accent:{accent};">
              <div class="bucket-head">
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
            <h3 class="city-head"><span class="city-pill"><span class="city-dot"></span>{escape(CITY_LABELS[cname])}</span><span class="count">{len(city_events)}</span></h3>
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
          <div class="near-me-stream" style="display: none;"></div>
          <div class="cities">{"".join(city_blocks)}</div>
        </section>'''

    # The first three days are in the page. Later days load on demand: one small file per day
    # (days/<date>.html, ~70 KB gzipped) for day and week views, and every later day in one file
    # (deferred_days.html) for "all", search, date ranges and saved lists.
    initial_sections = []
    deferred_sections = []
    deferred_by_date = []
    for idx, (date_obj, events) in enumerate(dated):
        sec_html = _render_day_section(escape(format_date_heading(date_obj)), events, date_obj.isoformat())
        if idx < 3:
            initial_sections.append(sec_html)
        else:
            deferred_sections.append(sec_html)
            deferred_by_date.append((date_obj.isoformat(), sec_html))
    deferred_dates_json = json.dumps([d for d, _ in deferred_by_date])
    # Museum shows have no day of their own: keep them near the top rather than after every date
    on_view = [e for e in tba if e.get("_exhibition")]
    undated = [e for e in tba if not e.get("_exhibition")]
    if on_view:
        on_view.sort(key=lambda e: (e.get("venue") or "", e.get("name") or ""))
        initial_sections.append(_render_day_section("On view now: museum exhibitions", on_view, "tba"))
    if undated:
        deferred_sections.append(_render_day_section("Date TBA", undated, "tba"))

    deferred_content = "".join(deferred_sections)
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, "deferred_days.html"), "w", encoding="utf-8") as f:
            f.write(deferred_content)
        # Rewritten from scratch each build, so days that have passed don't pile up
        days_dir = os.path.join(base_dir, "days")
        shutil.rmtree(days_dir, ignore_errors=True)
        os.makedirs(days_dir, exist_ok=True)
        for iso, sec_html in deferred_by_date:
            with open(os.path.join(days_dir, f"{iso}.html"), "w", encoding="utf-8") as f:
                f.write(sec_html)
    except Exception:
        pass

    all_event_dates = [d.isoformat() for d, _ in dated]

    useful_sidebar = ""
    if STATIC_LINKS or DEAL_LINKS:
        deals_block = ""
        lucky_shows = luckyseat_open(luckyseat_shows) or fetch_luckyseat_boston()
        if DEAL_LINKS or lucky_shows:
            lucky_html = ""
            if lucky_shows:
                def _lucky_li(s):
                    price = s.get("price")
                    price_str = f" · ${price:.0f}" if isinstance(price, (int, float)) else ""
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
          <div class="useful-cat useful-parents" style="margin-bottom:12px"><div class="useful-cat-head" style="color:#f27e9a"><span class="chip-icon">👪 </span>For parents</div><ul><li><a href="kids-family-events-boston/">Kids &amp; family events</a></li><li><a href="summer-camps/">Summer camps near Boston</a></li></ul></div>
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
        c = _effective_category(e)
        bucket_counts[category_bucket(c)] = bucket_counts.get(category_bucket(c), 0) + 1
        if c == "other":
            other_count += 1
        if is_recurring(e):
            recurring_count += 1
        else:
            once_count += 1

    def _bucket_icon_row(bucket_name):
        cats = dict(CATEGORY_BUCKETS).get(bucket_name, [])
        return " ".join(CATEGORY_STYLES.get(c, CATEGORY_STYLES["other"])[1] for c in cats)

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
        f'''<label class="chk chk-subgenre">
            <input type="checkbox" class="genre-chk" value="{escape(gid)}" checked>
            <span><span class="genre-swatch" style="background:{ginfo['color']}"></span>{escape(ginfo['label'])} <span class="count">{genre_counts.get(gid, 0)}</span></span>
          </label>'''
        for gid, ginfo in MUSIC_GENRES.items()
    )

    cat_items = []
    for b in bucket_order:
        is_checked = (b not in DEFAULT_UNCHECKED_BUCKETS)
        chk_attr = " checked" if is_checked else ""
        item_html = f'''<label class="chk">
            <input type="checkbox" class="cat-chk" value="{escape(b)}"{chk_attr}>
            <span>{escape(b)} <span class="count">{bucket_counts.get(b, 0)}</span></span>
          </label>'''
        if b == "Music & nightlife":
            subgenres_html = f'''<div class="subgenre-container filter-group-genre" id="subgenre-container">
            <div class="subgenre-header">
              <span class="subgenre-title">Subgenres</span>
              <span class="spacer"></span>
              <button type="button" id="genre-all" class="subgenre-btn" title="Select all subgenres">all</button>
              <button type="button" id="genre-none" class="subgenre-btn" title="Deselect all subgenres">none</button>
            </div>
            <div class="subgenre-grid">
              {genre_boxes}
            </div>
          </div>'''
            cat_items.append(item_html + "\n" + subgenres_html)
        else:
            cat_items.append(item_html)
    bucket_boxes = "\n".join(cat_items)

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

    transit_counts = {"red": 0, "green": 0, "orange": 0, "blue": 0}
    for e in all_events_flat:
        c = _event_city(e.get("venue"), e.get("_source_venue"), e)
        geo = resolve_event_geo(e)
        _, sub_slug = resolve_subarea(c, e, geo)
        t_str = resolve_transit_lines(c, sub_slug, e, geo)
        if t_str:
            for t in t_str.split(","):
                if t in transit_counts:
                    transit_counts[t] += 1

    transit_boxes = f'''<div class="transit-chips-grid">
      <button type="button" class="transit-chip" data-transit="red" title="Filter by MBTA Red Line"><span class="t-dot" style="background:#da291c"></span>Red Line <span class="count">{transit_counts["red"]:,}</span></button>
      <button type="button" class="transit-chip" data-transit="green" title="Filter by MBTA Green Line"><span class="t-dot" style="background:#00843d"></span>Green Line <span class="count">{transit_counts["green"]:,}</span></button>
      <button type="button" class="transit-chip" data-transit="orange" title="Filter by MBTA Orange Line"><span class="t-dot" style="background:#ed8b00"></span>Orange Line <span class="count">{transit_counts["orange"]:,}</span></button>
      <button type="button" class="transit-chip" data-transit="blue" title="Filter by MBTA Blue Line"><span class="t-dot" style="background:#003da5"></span>Blue Line <span class="count">{transit_counts["blue"]:,}</span></button>
    </div>'''

    fail_banner = ""
    # In live mode, we keep fail_banner and internal notes silent for visitors
    other_note = ""
    genres_map = {gid: {"label": ginfo["label"], "icon": ginfo["icon"], "color": ginfo["color"]} for gid, ginfo in MUSIC_GENRES.items()}

    now_eastern = datetime.now(EASTERN)
    seasonal_key, seasonal_icon, seasonal_label = get_seasonal_theme(now_eastern)
    from holiday_themes import holiday_calendar, HOLIDAY_KEYS, holiday_theme_css, greeting_html
    holiday_calendar_json = json.dumps(holiday_calendar(now_eastern.date() - timedelta(days=2), 400))
    holiday_keys_json = json.dumps(HOLIDAY_KEYS)
    from holiday_themes import HOLIDAYS as _HOLIDAYS
    holiday_meta_json = json.dumps({h["key"]: {"label": h["label"], "emoji": h["emoji"]} for h in _HOLIDAYS}, ensure_ascii=False)
    holiday_css = holiday_theme_css()
    holiday_greetings = greeting_html()
    default_theme = seasonal_key if seasonal_key else "classic"

    site_url = get_site_url()
    seo_meta_tags = build_seo_meta_tags(site_url)
    json_ld_scripts = build_json_ld(all_events_flat, site_url)
    seo_directory_html = build_seo_directory_html(all_events_flat, all_venue_names)

    return f"""<!doctype html>
<html lang="en" data-theme="{default_theme}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
{seo_meta_tags}
{json_ld_scripts}
<script>
  var HOLIDAY_CALENDAR = {holiday_calendar_json};
  var HOLIDAY_KEYS = {holiday_keys_json};
  var HOLIDAY_META = {holiday_meta_json};
  var BASE_THEMES = ['classic', 'light', 'indie', 'anime'];
  function localISODate(dt) {{
    return dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
  }}
  function getClientSeasonalTheme(dt) {{
    return HOLIDAY_CALENDAR[localISODate(dt)] || null;
  }}
  // Visitors who haven't picked a theme get their device's setting: light or dark.
  function systemTheme() {{
    try {{
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'classic';
    }} catch (e) {{ return 'classic'; }}
  }}
  // Which theme to show: a ?theme= preview; else today's holiday, unless the visitor picked a
  // theme today; else the visitor's last regular theme; else their device's light/dark setting.
  function pickTheme() {{
    var preview = new URLSearchParams(location.search).get('theme');
    if (preview && (BASE_THEMES.indexOf(preview) !== -1 || HOLIDAY_KEYS.indexOf(preview) !== -1)) return preview;
    var today = localISODate(new Date());
    var holiday = HOLIDAY_CALENDAR[today] || null;
    var stored = null, pickedOn = null;
    try {{
      stored = localStorage.getItem('boston_events_theme');
      pickedOn = localStorage.getItem('boston_events_theme_manual');
    }} catch (e) {{}}
    if (holiday) return (pickedOn === today && stored) ? stored : holiday;
    return (stored && BASE_THEMES.indexOf(stored) !== -1) ? stored : systemTheme();
  }}
  try {{
    document.documentElement.setAttribute('data-theme', pickTheme());
  }} catch(e) {{}}
</script>
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/logo-192.png" type="image/png" sizes="192x192">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
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
  [data-theme="light"] {{
    color-scheme: light;
    --bg: #f5f6fa;
    --card: #ffffff;
    --card-hover: #f0f2f8;
    --fg: #161a24;
    --muted: #5b6475;
    --accent: #2563eb;
    --accent-glow: rgba(37, 99, 235, 0.16);
    --border: rgba(15, 23, 42, 0.11);
    --border-hover: rgba(15, 23, 42, 0.24);
    --green: #15803d;
    --green-bg: rgba(22, 163, 74, 0.10);
    --green-border: rgba(22, 163, 74, 0.35);
    --warn: #c2410c;
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
    justify-content: flex-end;
    gap: 12px;
  }}
  /* Theme picker row sits at the top of the banner; title and stats stay at the bottom */
  .banner {{ align-items: stretch; }}
  .banner-top-row {{ margin-bottom: auto; }}
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
    flex-wrap: nowrap;
    gap: 8px;
    align-self: flex-start;
    background: rgba(18, 21, 31, 0.72);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 999px;
    padding: 5px 14px;
    font-size: 12.5px;
    color: var(--fg);
    box-shadow: 0 4px 20px rgba(0,0,0,0.35);
    max-width: 100%;
  }}
  .banner-top-actions {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 6px;
    margin-left: auto;
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
    white-space: nowrap;
  }}
  .subgenre-container {{
    margin: 3px 0 6px 14px;
    padding: 6px 8px 6px 10px;
    background: rgba(255, 255, 255, 0.02);
    border-left: 2px solid rgba(255, 255, 255, 0.12);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    transition: opacity 0.2s ease;
  }}
  .subgenre-container.disabled {{
    opacity: 0.4;
    pointer-events: none;
  }}
  .subgenre-header {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--muted);
    margin-bottom: 5px;
  }}
  .subgenre-btn {{
    background: none;
    border: none;
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    cursor: pointer;
    padding: 0 4px;
    border-radius: 3px;
    font-family: inherit;
  }}
  .subgenre-btn:hover {{
    color: #fff;
    background: rgba(255, 255, 255, 0.1);
  }}
  .subgenre-grid {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .chk-subgenre {{
    font-size: 11.5px;
    opacity: 0.9;
  }}
  .chk-saved span {{ font-weight: 600; color: #f59e0b; }}
  .btn-copy-plan-sidebar {{
    grid-column: 1 / -1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    background: rgba(52, 211, 153, 0.12);
    border: 1px solid rgba(52, 211, 153, 0.35);
    color: #34d399;
    border-radius: var(--radius-sm);
    padding: 4px 8px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s ease;
    margin: 2px 0 4px;
  }}
  .btn-copy-plan-sidebar:hover {{
    background: rgba(52, 211, 153, 0.22);
    border-color: #34d399;
    color: #6ee7b7;
  }}
  .pill-submit-btn:hover {{
    transform: translateY(-1px) scale(1.02);
    box-shadow: 0 4px 12px rgba(255, 216, 102, 0.45);
    filter: brightness(1.06);
  }}
  .pill-submit-btn:active {{
    transform: translateY(1px);
  }}
  .pill-social-link {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    text-decoration: none;
    font-size: 11.5px;
    font-weight: 550;
    transition: color 0.15s ease, opacity 0.15s ease, transform 0.15s ease;
    opacity: 0.85;
    padding: 2px 4px;
    border-radius: 4px;
  }}
  .pill-social-link:hover {{
    color: #e1306c;
    opacity: 1;
    transform: scale(1.1);
  }}
  .footer-social-link {{
    color: inherit;
    text-decoration: underline;
    opacity: 0.9;
  }}
  .footer-social-link:hover {{
    opacity: 1;
  }}
  .footer-pwa-btn {{
    background: none;
    border: none;
    color: inherit;
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
    padding: 0;
    display: inline;
    opacity: 0.9;
  }}
  .footer-pwa-btn:hover {{
    opacity: 1;
  }}

  /* Classic Dark: remove distracting emojis from category badges and category filters */
  :root .cat-pill .chip-icon,
  [data-theme="classic"] .cat-pill .chip-icon,
  :root .cat-pill.genre-pill .chip-icon,
  [data-theme="classic"] .cat-pill.genre-pill .chip-icon,
  :root .chk-grid .cat-chk ~ span .chip-icon,
  [data-theme="classic"] .chk-grid .cat-chk ~ span .chip-icon {{
    display: none !important;
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
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  aside.useful {{
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .filter-group.venues .chk-grid::-webkit-scrollbar {{ width: 6px; }}
  .filter-group.venues .chk-grid::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
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
    overflow-x: hidden;
    max-width: 100%;
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

  .genre-pill {{
    cursor: pointer;
    transition: transform 0.12s ease, filter 0.12s ease, box-shadow 0.12s ease;
  }}
  .genre-pill:hover {{
    transform: translateY(-1px);
    filter: brightness(1.25);
  }}
  .genre-pill.active,
  .genre-pill.genre-pill-active {{
    box-shadow: 0 0 0 2px #fff, 0 0 10px currentColor;
    font-weight: 700;
  }}
  .chip-active-genre {{
    background: rgba(122, 162, 247, 0.25) !important;
    border-color: #7aa2f7 !important;
    color: #fff !important;
    font-weight: 700;
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
  .chip-tod.active {{
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
  @media (pointer: coarse) {{
    .star-btn {{ font-size: 18px; padding: 8px 10px 8px 2px; opacity: 0.8; }}
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
    flex-shrink: 0;
  }}
  .transit-chips-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    margin-top: 4px;
  }}
  .transit-filter-group .transit-chip {{
    width: 100%;
    justify-content: flex-start;
  }}
  .transit-chip .count {{
    margin-left: auto;
    font-size: 10px;
    opacity: 0.7;
    font-weight: 500;
    padding: 1px 5px;
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
  .cities {{ display: flex; flex-direction: column; gap: 18px; margin-top: 6px; }}
  .city-section {{
    --city-color: var(--accent);
    --city-bg: rgba(255, 255, 255, 0.02);
    background: var(--city-bg);
    border: 1px solid var(--border);
    border-left: 4px solid var(--city-color);
    border-radius: var(--radius-md);
    padding: 14px 14px 10px 14px;
    transition: border-color 0.15s ease, background 0.15s ease;
  }}
  .city-section:hover {{
    border-color: rgba(255, 255, 255, 0.18);
  }}
  .city-section.empty {{ display: none; }}
  .city-section[data-city="cambridge"] {{ --city-color: #f43f5e; --city-bg: rgba(244, 63, 94, 0.035); }}
  .city-section[data-city="somerville"]{{ --city-color: #f59e0b; --city-bg: rgba(245, 158, 11, 0.035); }}
  .city-section[data-city="boston"]    {{ --city-color: #3b82f6; --city-bg: rgba(59, 130, 246, 0.035); }}
  .city-section[data-city="other"]     {{ --city-color: #a855f7; --city-bg: rgba(168, 85, 247, 0.035); }}
  .city-head {{
    margin: 0 0 12px;
    font-size: 13px;
    font-weight: 700;
    color: var(--fg);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }}
  .city-pill {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    background: rgba(255, 255, 255, 0.04);
    color: var(--city-color);
    border: 1px solid rgba(255, 255, 255, 0.09);
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }}
  .city-pill .city-dot {{
    background: var(--city-color);
    box-shadow: 0 0 8px var(--city-color);
  }}
  .city-head .count {{
    background: rgba(255, 255, 255, 0.06);
    color: var(--muted);
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 999px;
    font-weight: 600;
  }}
  .buckets {{ display: flex; flex-direction: column; gap: 10px; }}
  .bucket {{ border-left: 3px solid var(--accent, #7aa2f7); padding: 2px 0 2px 12px; border-left-color: var(--accent); }}
  .bucket[data-bucket="Music & nightlife"] {{ --accent: #7aa2f7; }}
  .bucket[data-bucket="Dance"]             {{ --accent: #ff7ab2; }}
  .bucket[data-bucket="Stage"]             {{ --accent: #f0a07a; }}
  .bucket[data-bucket="Arts & culture"]    {{ --accent: #9ece6a; }}
  .bucket[data-bucket="Play"]              {{ --accent: #bb9af7; }}
  .bucket[data-bucket="Food & drink"]      {{ --accent: #c678dd; }}
  .bucket[data-bucket="Community"]         {{ --accent: #8fa1b3; }}
  .bucket[data-bucket="Classes & Services"] {{ --accent: #8fa1b3; }}
  .bucket[data-bucket="Kids & Family"]      {{ --accent: #ffb8d1; }}
  .bucket[data-bucket="Deals & Specials"]   {{ --accent: #c678dd; }}
  .bucket[data-bucket="Tech & Startups"]    {{ --accent: #7aa2f7; }}
  .bucket[data-bucket="Markets & Festivals"] {{ --accent: #f4a261; }}
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
  .also-listed {{ display: block; color: var(--muted); font-size: 11px; margin-top: 2px; }}
  .also-listed a {{ color: var(--accent); text-decoration: none; }}
  .also-listed a:hover {{ text-decoration: underline; }}
  .also-listed .also-src {{ color: var(--muted); }}
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
  .lgbtq-toggle {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: #a855f7; user-select: none; }}
  .lgbtq-toggle input {{ accent-color: #a855f7; width: 14px; height: 14px; cursor: pointer; margin: 0; }}
  .timeframe-toggle {{ display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; cursor: pointer; color: var(--accent); user-select: none; }}
  .timeframe-toggle input {{ accent-color: var(--accent); width: 14px; height: 14px; cursor: pointer; margin: 0; }}

  /* Timeframe & Custom Range Controls */
  .custom-time-range {{
    margin-top: 9px;
    padding-top: 9px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }}
  .custom-time-heading {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 10.5px;
    font-weight: 700;
    color: var(--muted);
    margin-bottom: 6px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .btn-clear-time-range {{
    background: none;
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 10px;
    padding: 1px 7px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
  }}
  .btn-clear-time-range:hover {{
    color: var(--accent);
    border-color: var(--accent);
  }}
  .time-select-row {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .time-input-wrap {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .time-input-wrap label {{
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
  }}
  .time-dropdown {{
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--fg);
    padding: 5px 6px;
    border-radius: var(--radius-sm);
    font-size: 11.5px;
    font-family: inherit;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }}
  .time-dropdown:focus {{
    outline: none;
    border-color: var(--accent);
    box-shadow: 0 0 0 2px var(--accent-glow);
  }}
  .time-range-arrow {{
    color: var(--muted);
    font-size: 13px;
    padding-top: 14px;
    user-select: none;
  }}
  .time-range-active-indicator {{
    margin-top: 6px;
    font-size: 11px;
    color: var(--accent);
    font-weight: 600;
    line-height: 1.3;
  }}
  .chip-time-custom {{
    background: rgba(255, 121, 63, 0.15) !important;
    border-color: #ff793f !important;
    color: #ff9f43 !important;
  }}

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
  .week-nav button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; font-family: inherit; transition: all 0.15s ease; }}
  .week-nav button:hover {{ border-color: var(--accent); color: var(--accent); }}
  .week-nav button[aria-pressed="true"], .week-nav button.active {{ background: var(--accent); color: #0c0e14; border-color: var(--accent); font-weight: 600; }}
  .week-nav button.chip-starred.active {{ background: #f59e0b; color: #0c0e14; border-color: #f59e0b; font-weight: 600; }}
  .week-nav button.chip-copy-plan {{ background: rgba(52, 211, 153, 0.12); border-color: rgba(52, 211, 153, 0.35); color: #34d399; font-weight: 500; }}
  .week-nav button.chip-copy-plan:hover {{ background: rgba(52, 211, 153, 0.22); border-color: #34d399; color: #6ee7b7; }}
  #week-label, #week-label-b {{ font-size: 13px; font-weight: 600; color: var(--fg); flex: 1; text-align: center; min-width: 160px; }}
  .week-nav.bottom #week-label-b {{ flex: 0; padding: 0 12px; }}
  .mini-cal {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 10px 12px; contain: content; }}
  .mini-cal-head {{ display:flex; align-items:center; gap:8px; margin-bottom: 6px; }}
  .mini-cal-head button {{ background: transparent; color: var(--fg); border: 1px solid var(--border); border-radius: 6px; padding: 2px 10px; font-size: 14px; cursor: pointer; font-family: inherit; line-height: 1; }}
  .mini-cal-head button:hover {{ border-color: var(--accent); color: var(--accent); }}
  #cal-month-label {{ flex: 1; text-align: center; font-size: 13px; font-weight: 600; }}
  .mini-cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; font-size: 11px; }}
  .mini-cal-grid .dow {{ text-align: center; color: var(--muted); font-size: 10px; padding: 2px 0; letter-spacing: 0.04em; }}
  .mini-cal-grid .d {{ text-align: center; padding: 6px 0; border-radius: 6px; cursor: pointer; color: var(--muted); background: transparent; border: 1px solid transparent; position: relative; user-select: none; transition: background 0.12s ease; }}
  .mini-cal-grid .d.has-events {{ color: var(--fg); }}
  .mini-cal-grid .d.has-events::after {{ content:''; position:absolute; bottom: 2px; left: 50%; transform: translateX(-50%); width: 4px; height: 4px; border-radius: 50%; background: var(--accent); }}
  .mini-cal-grid .d.today {{ border-color: var(--border); }}
  .mini-cal-grid .d.in-week {{ background: rgba(93,155,255,0.12); color: var(--fg); }}
  .mini-cal-grid .d.anchor {{ background: var(--accent); color: #0c0e14; font-weight: 700; }}
  .mini-cal-grid .d.anchor::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.range-start {{ background: var(--accent); color: #0c0e14; font-weight: 700; border-radius: 6px 0 0 6px; }}
  .mini-cal-grid .d.range-start::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.range-end {{ background: var(--accent); color: #0c0e14; font-weight: 700; border-radius: 0 6px 6px 0; }}
  .mini-cal-grid .d.range-end::after {{ background: #0c0e14; }}
  .mini-cal-grid .d.range-start.range-end {{ border-radius: 6px; }}
  .mini-cal-grid .d.in-range {{ background: rgba(93,155,255,0.22); color: var(--fg); border-radius: 0; }}
  .mini-cal-grid .d.blank {{ cursor: default; }}
  .mini-cal-grid .d:not(.blank):hover {{ border-color: var(--accent); }}
  .mini-cal-hint {{ font-size: 11px; color: var(--muted); text-align: center; margin-top: 8px; padding-top: 6px; border-top: 1px solid var(--border); }}
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

  /* Greater Boston SEO & AEO Directory Section */
  .seo-directory {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 24px 22px;
    margin-top: 14px;
    margin-bottom: 20px;
  }}
  .directory-header {{
    margin-bottom: 20px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 14px;
  }}
  .directory-header h2 {{
    font-size: 18px;
    font-weight: 800;
    margin: 0 0 6px;
    color: var(--fg);
  }}
  .directory-sub {{
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
    margin: 0;
  }}
  .directory-grid {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px;
  }}
  @media (max-width: 860px) {{
    .directory-grid {{
      grid-template-columns: 1fr;
      gap: 16px;
    }}
  }}
  .directory-col h3 {{
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--accent);
    margin: 0 0 10px;
  }}
  .directory-col ul {{
    list-style: none;
    padding: 0;
    margin: 0;
  }}
  .directory-col li {{
    font-size: 12px;
    color: var(--muted);
    padding: 2px 0;
  }}
  .directory-col a {{
    color: var(--fg);
    text-decoration: none;
    transition: color 0.15s ease;
  }}
  .directory-col a:hover {{
    color: var(--accent);
    text-decoration: underline;
  }}
  .directory-group {{
    margin-bottom: 12px;
  }}
  .directory-group-title {{
    display: block;
    font-size: 12px;
    font-weight: 700;
    color: var(--fg);
    margin-bottom: 4px;
  }}
  .directory-group-title a {{
    color: var(--accent);
  }}
  .genre-tag-list {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }}
  .genre-tag-list li a {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    font-size: 11px;
  }}
  .venue-directory-list {{
    max-height: 320px;
    overflow-y: auto;
    padding-right: 6px;
  }}
  .dir-cnt {{
    font-size: 10px;
    opacity: 0.7;
  }}
  .aeo-faq-block {{
    margin-top: 24px;
    padding-top: 18px;
    border-top: 1px dashed var(--border);
  }}
  .aeo-faq-block h3 {{
    font-size: 14px;
    color: var(--fg);
    margin: 0 0 12px;
  }}
  .faq-item {{
    margin-bottom: 12px;
  }}
  .faq-item h4 {{
    font-size: 13px;
    color: var(--accent);
    margin: 0 0 4px;
  }}
  .faq-item p {{
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
    margin: 0;
  }}
  .faq-item a {{
    color: var(--accent);
    text-decoration: none;
  }}

  /* View Switcher */
  .view-switch-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 6px 10px;
    white-space: nowrap;
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
    justify-content: center;
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
  .view-actions {{
    display: inline-flex;
    align-items: center;
  }}
  .map-toggle-btn {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 12.5px;
    font-weight: 600;
    padding: 5px 14px;
    border-radius: 999px;
    cursor: pointer;
    font-family: inherit;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: all 0.15s ease;
  }}
  .map-toggle-btn:hover {{
    color: var(--fg);
    border-color: var(--accent);
  }}
  .map-toggle-btn.active {{
    background: rgba(93, 155, 255, 0.18);
    border-color: var(--accent);
    color: var(--accent);
    font-weight: 700;
    box-shadow: 0 0 10px rgba(93, 155, 255, 0.25);
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
  .dist-badge {{
    display: inline-flex;
    align-items: center;
    gap: 3px;
    font-size: 11px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 999px;
    background: rgba(46, 160, 67, 0.15);
    color: #3fb950;
    border: 1px solid rgba(46, 160, 67, 0.35);
    margin-left: 6px;
    vertical-align: middle;
  }}
  [data-theme="indie"] .dist-badge {{
    background: rgba(56, 189, 248, 0.12);
    color: #38bdf8;
    border-color: rgba(56, 189, 248, 0.3);
  }}
  [data-theme="anime"] .dist-badge {{
    background: rgba(255, 75, 147, 0.15);
    color: #ff79c6;
    border-color: rgba(255, 75, 147, 0.35);
  }}
  [data-theme="halloween"] .dist-badge {{
    background: rgba(255, 121, 63, 0.18);
    color: #ff9f43;
    border-color: rgba(255, 121, 63, 0.4);
    box-shadow: 0 0 8px rgba(255, 121, 63, 0.2);
  }}
  .near-stream-banner {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--card);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    padding: 10px 14px;
    border-radius: var(--radius-md);
    margin-bottom: 12px;
    font-size: 13px;
    gap: 10px;
    flex-wrap: wrap;
  }}
  .near-stream-actions {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .pin-hint {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    padding: 8px 12px;
    border: 1px dashed var(--accent);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--fg);
  }}
  .pin-hint[hidden] {{ display: none; }}
  .leaflet-map.placing-pin,
  .leaflet-map.placing-pin .leaflet-interactive {{ cursor: crosshair; }}
  .drop-pin-marker {{ background: none; border: none; }}
  .drop-pin-marker span {{
    font-size: 28px;
    line-height: 1;
    filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.6));
    cursor: grab;
  }}
  .near-stream-info {{
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--fg);
  }}
  .near-stream-clear-btn {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--border);
    color: var(--fg);
    border-radius: 999px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease;
  }}
  .near-stream-clear-btn:hover {{
    background: var(--accent);
    color: #0c0e14;
  }}
  .near-events-list {{
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
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
      font-size: 11.5px;
      padding: 5px 10px;
      gap: 6px 8px;
      max-width: 100%;
      width: auto;
      white-space: nowrap;
      overflow-x: auto;
      display: inline-flex;
      flex-wrap: nowrap;
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
    .view-switch-bar {{
      padding: 4px 6px;
      gap: 8px;
      overflow-x: hidden;
    }}
    .view-toggle {{
      flex: 1.4;
      display: flex;
    }}
    .view-btn {{
      flex: 1 1 0;
      justify-content: center;
      padding: 7px 4px;
      font-size: 12.5px;
      text-align: center;
    }}
    .view-actions {{
      flex: 0.8;
      display: flex;
    }}
    .map-toggle-btn {{
      width: 100%;
      justify-content: center;
      padding: 7px 4px;
      font-size: 12px;
      text-align: center;
    }}
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
      overscroll-behavior: contain;
      -webkit-overflow-scrolling: touch;
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
      padding: 6px 8px;
      gap: 6px;
      overflow-x: hidden;
      justify-content: space-between;
    }}
    .loc-chip {{
      padding: 5px 6px;
      font-size: 12px;
      flex: 1 1 0;
      min-width: 0;
      justify-content: center;
      text-align: center;
    }}
    .loc-chip .chip-icon, .loc-chip .city-dot {{
      margin-right: 2px;
    }}
    .subarea-chips-bar {{
      padding: 5px 8px;
      gap: 5px;
    }}
    .sub-chip {{
      padding: 3px 9px;
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

  /* Curated Highlights / Editor's Picks */
  .badge-highlight {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    background: rgba(255, 184, 0, 0.16);
    border: 1px solid rgba(255, 184, 0, 0.45);
    color: #ffd866;
    vertical-align: middle;
    margin-left: 6px;
    transition: background 0.15s ease, border-color 0.15s ease;
  }}
  .badge-highlight:hover {{
    background: rgba(255, 184, 0, 0.28);
    border-color: rgba(255, 184, 0, 0.7);
  }}
  .curator-note {{
    font-size: 12.5px;
    color: #ffebb8;
    background: rgba(255, 184, 0, 0.08);
    border: 1px solid rgba(255, 184, 0, 0.22);
    border-left: 3px solid #ffb800;
    padding: 6px 10px;
    border-radius: 4px;
    margin-top: 8px;
    font-style: italic;
    line-height: 1.45;
  }}
  .curator-note .note-label {{
    font-weight: 700;
    font-style: normal;
    color: #ffca47;
    margin-right: 5px;
  }}
  .chip-featured.active {{
    background: linear-gradient(135deg, rgba(255, 184, 0, 0.35), rgba(255, 138, 0, 0.28)) !important;
    border-color: #ffb800 !important;
    color: #fff !important;
    box-shadow: 0 0 12px rgba(255, 184, 0, 0.35);
  }}

  /* Submission Modal Overlay */
  .schedule-bar {{
    position: fixed;
    left: 50%;
    transform: translateX(-50%);
    bottom: calc(14px + env(safe-area-inset-bottom, 0px));
    z-index: 9000;
    display: flex;
    gap: 4px;
    padding: 4px;
    background: var(--card);
    border: 1px solid var(--border-hover, var(--border));
    border-radius: 999px;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
    max-width: calc(100vw - 32px);
  }}
  .schedule-bar button {{
    border: 0;
    border-radius: 999px;
    padding: 8px 14px;
    font: inherit;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }}
  .schedule-bar-view {{ background: transparent; color: var(--fg); }}
  .schedule-bar-view[aria-pressed="true"] {{ background: rgba(127, 127, 127, 0.18); }}
  .schedule-bar-share {{ background: var(--accent); color: #0c0e14; }}
  .schedule-bar button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  .schedule-share-card {{ max-width: 460px; display: grid; gap: 8px; }}
  .schedule-share-label {{ font-size: 13px; font-weight: 600; color: var(--muted); margin-top: 6px; }}
  .schedule-share-card input {{
    width: 100%;
    box-sizing: border-box;
    padding: 9px 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: rgba(127, 127, 127, 0.1);
    color: var(--fg);
    font: inherit;
    font-size: 14px;
  }}
  .schedule-share-actions {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin-top: 10px; }}
  .schedule-share-copy, .schedule-share-send {{
    border: 0;
    border-radius: var(--radius-sm);
    padding: 9px 16px;
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }}
  .schedule-share-copy {{ background: var(--accent); color: #0c0e14; }}
  .schedule-share-send {{ background: rgba(127, 127, 127, 0.18); color: var(--fg); }}
  .schedule-share-open {{ color: var(--accent); font-size: 14px; }}
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
  /* Top row: "Greater Boston Live Events" on the left, the theme picker on the right with Add Event
     under it. On phones the theme picker gets the first line to itself and the tag sits lower,
     level with Add Event. */
  .banner-top-row {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: "tag themes" ". add";
    align-items: center;
    width: 100%;
    gap: 8px 12px;
  }}
  .banner-top-tag {{ grid-area: tag; justify-self: start; min-width: 0; }}
  .banner-top-actions {{ grid-area: add; justify-self: end; margin-left: 0; }}
  .theme-toggle-wrap {{
    grid-area: themes;
    justify-self: end;
    display: inline-flex;
    align-items: center;
    background: rgba(15, 18, 25, 0.7);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 999px;
    padding: 3px;
  }}
  @media (max-width: 640px) {{
    .banner-top-row {{
      grid-template-columns: minmax(0, 1fr) auto;
      grid-template-areas: "themes themes" "tag add";
      row-gap: 10px;
    }}
    .banner-top-tag {{ font-size: 10px; letter-spacing: 0.08em; white-space: nowrap; }}
  }}
  .theme-toggle-wrap .theme-pill-btn {{ font-size: 14px; padding: 3px 9px; }}
  .theme-pill-holiday {{ display: inline-flex; align-items: center; gap: 6px; font-weight: 700; color: #fff; }}
  .theme-pill-holiday[hidden] {{ display: none; }}
  .holiday-pill-label {{ font-size: 12px; letter-spacing: 0.01em; white-space: nowrap; }}
  @media (max-width: 520px) {{
    .holiday-pill-label {{ display: none; }}
  }}
  .theme-toggle-label {{
    display: none;
  }}
  .theme-toggle-pills {{
    display: inline-flex;
    gap: 1px;
    background: transparent;
    border-radius: 999px;
    padding: 0;
  }}
  .theme-pill-btn {{
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 11px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 999px;
    cursor: pointer;
    transition: all 0.15s ease;
    font-family: inherit;
    line-height: 1.35;
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
  [data-theme="halloween"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ff793f 0%, #ff4757 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(255, 121, 63, 0.5);
  }}
  [data-theme="election"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #2563eb 0%, #dc2626 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(37, 99, 235, 0.5);
  }}
  [data-theme="veterans"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #d4af37 0%, #1e3a8a 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(212, 175, 55, 0.5);
  }}
  [data-theme="thanksgiving"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #ea580c 0%, #be123c 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(234, 88, 12, 0.5);
  }}
  [data-theme="blackfriday"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #facc15 0%, #eab308 100%);
    color: #000000;
    box-shadow: 0 0 10px rgba(250, 204, 21, 0.5);
  }}
  [data-theme="cybermonday"] .theme-pill-btn.active {{
    background: linear-gradient(135deg, #06b6d4 0%, #9333ea 100%);
    color: #ffffff;
    box-shadow: 0 0 10px rgba(6, 182, 212, 0.5);
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
  /* =========================================================================
     HALLOWEEN & DÍA DE LOS MUERTOS THEME (Nocturnal Twilight, Orange & Black)
     ========================================================================= */
  [data-theme="halloween"] {{
    --bg: #09050e;
    --card: #130a1c;
    --card-hover: #1c1028;
    --fg: #fffcf6;
    --muted: #a395b5;
    --accent: #ff793f;
    --accent-glow: rgba(255, 121, 63, 0.35);
    --border: rgba(255, 121, 63, 0.22);
    --border-hover: rgba(255, 121, 63, 0.45);
    --green: #00d2d3;
    --green-bg: rgba(0, 210, 211, 0.14);
    --green-border: rgba(0, 210, 211, 0.35);
    --warn: #ff9f43;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}

  [data-theme="halloween"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(255, 121, 63, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 90% 40%, rgba(142, 68, 173, 0.06) 0%, transparent 60%);
    background-attachment: fixed;
    color: var(--fg);
  }}

  [data-theme="halloween"] .banner {{
    background-color: #0d0617;
    background-image:
      linear-gradient(180deg, rgba(13, 6, 23, 0.45) 0%, rgba(20, 9, 34, 0.75) 55%, rgba(9, 5, 14, 0.98) 100%),
      url('banner_halloween.jpg');
    background-position: center 85%;
    background-size: cover;
    border-bottom: 2px solid rgba(255, 121, 63, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(255, 121, 63, 0.15);
  }}

  [data-theme="halloween"] .banner-top-tag {{
    color: #ff9f43;
    text-shadow: 0 0 14px rgba(255, 159, 67, 0.7);
    letter-spacing: 0.18em;
    font-weight: 800;
  }}

  [data-theme="halloween"] .live-pulse {{
    background: #ff793f;
    box-shadow: 0 0 10px #ff793f, 0 0 20px #ff793f;
  }}

  [data-theme="halloween"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 15%, #ff9f43 55%, #ff5252 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 25px rgba(255, 121, 63, 0.4));
    letter-spacing: -0.02em;
  }}

  [data-theme="halloween"] .banner-meta-pill {{
    background: rgba(22, 11, 36, 0.88);
    border: 1px solid rgba(255, 121, 63, 0.4);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5), 0 0 16px rgba(255, 121, 63, 0.18);
    border-radius: 999px;
    backdrop-filter: blur(10px);
  }}

  [data-theme="halloween"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ff4757 0%, #ff793f 60%, #f39c12 100%);
    border: 1px solid rgba(255, 255, 255, 0.35);
    color: #fff;
    box-shadow: 0 0 14px rgba(255, 121, 63, 0.5);
    font-weight: 800;
    border-radius: 999px;
  }}

  [data-theme="halloween"] .pill-submit-btn:hover {{
    filter: brightness(1.15);
    box-shadow: 0 0 22px rgba(255, 121, 63, 0.75);
    transform: translateY(-1px) scale(1.02);
  }}

  [data-theme="halloween"] .chip,
  [data-theme="halloween"] .loc-chip,
  [data-theme="halloween"] .genre-chip,
  [data-theme="halloween"] .transit-chip,
  [data-theme="halloween"] .sub-chip {{
    border-radius: 999px;
    background: rgba(26, 14, 42, 0.7);
    border: 1px solid rgba(255, 121, 63, 0.25);
    color: #d8cde8;
    backdrop-filter: blur(8px);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}

  [data-theme="halloween"] .chip:hover,
  [data-theme="halloween"] .loc-chip:hover,
  [data-theme="halloween"] .genre-chip:hover,
  [data-theme="halloween"] .transit-chip:hover,
  [data-theme="halloween"] .sub-chip:hover {{
    border-color: #ff9f43;
    color: #ffffff;
    box-shadow: 0 0 14px rgba(255, 159, 67, 0.4);
    transform: translateY(-2px);
  }}

  [data-theme="halloween"] .chip.active,
  [data-theme="halloween"] .loc-chip.active,
  [data-theme="halloween"] .genre-chip.active,
  [data-theme="halloween"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(255, 121, 63, 0.4) 0%, rgba(224, 86, 253, 0.28) 100%);
    border-color: #ff793f;
    color: #ffeaa7;
    box-shadow: 0 0 14px rgba(255, 121, 63, 0.4);
    font-weight: 700;
  }}

  [data-theme="halloween"] .day {{
    background: rgba(19, 10, 31, 0.75);
    border: 1px solid rgba(255, 121, 63, 0.22);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
    border-radius: var(--radius-lg);
  }}

  [data-theme="halloween"] .day h2 {{
    color: #fff2df;
    border-bottom: 1px solid rgba(255, 121, 63, 0.22);
  }}

  [data-theme="halloween"] .day h2 .count {{
    background: rgba(255, 121, 63, 0.2);
    border: 1px solid rgba(255, 121, 63, 0.5);
    color: #ff9f43;
    border-radius: 999px;
  }}

  [data-theme="halloween"] .event {{
    background: rgba(26, 14, 42, 0.6);
    border: 1px solid rgba(255, 121, 63, 0.18);
    border-radius: var(--radius-md);
    transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }}

  [data-theme="halloween"] .event:hover {{
    background: rgba(36, 20, 58, 0.9);
    border-color: rgba(255, 121, 63, 0.6);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4), 0 0 16px rgba(255, 121, 63, 0.3);
    transform: translateY(-2px);
  }}

  [data-theme="halloween"] .event .what a {{
    color: #ffffff;
  }}

  [data-theme="halloween"] .event .what a:hover {{
    color: #ff9f43;
    text-shadow: 0 0 10px rgba(255, 159, 67, 0.6);
  }}

  [data-theme="halloween"] .filter-group {{
    background: rgba(19, 10, 31, 0.85);
    border: 1px solid rgba(255, 121, 63, 0.25);
  }}

  [data-theme="halloween"] .badge-highlight {{
    background: linear-gradient(135deg, rgba(255, 121, 63, 0.25) 0%, rgba(243, 156, 18, 0.35) 100%);
    border: 1px solid #ff793f;
    color: #ffeaa7;
    box-shadow: 0 0 10px rgba(255, 121, 63, 0.25);
  }}

  /* =========================================================================
     ELECTION DAY / CIVIC BOSTON THEME (Patriotic Royal Blue & Cardinal Red)
     ========================================================================= */
  [data-theme="election"] {{
    --bg: #090d16;
    --card: #121826;
    --card-hover: #1b2438;
    --fg: #f1f5f9;
    --muted: #94a3b8;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.35);
    --border: rgba(59, 130, 246, 0.22);
    --border-hover: rgba(59, 130, 246, 0.45);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.14);
    --green-border: rgba(34, 197, 94, 0.35);
    --warn: #ef4444;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="election"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 20% -10%, rgba(59, 130, 246, 0.10) 0%, transparent 65%),
      radial-gradient(ellipse 70% 40% at 85% 20%, rgba(239, 68, 68, 0.08) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="election"] .banner {{
    background-color: #0c1220;
    border-bottom: 2px solid rgba(59, 130, 246, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(59, 130, 246, 0.15);
  }}
  [data-theme="election"] .banner-top-tag {{
    color: #60a5fa;
    text-shadow: 0 0 12px rgba(96, 165, 250, 0.6);
  }}
  [data-theme="election"] .live-pulse {{
    background: #3b82f6;
    box-shadow: 0 0 10px #3b82f6, 0 0 20px #3b82f6;
  }}
  [data-theme="election"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 15%, #93c5fd 60%, #fca5a5 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(59, 130, 246, 0.35));
  }}
  [data-theme="election"] .pill-submit-btn {{
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #dc2626 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(37, 99, 235, 0.45);
    border-radius: 999px;
  }}
  [data-theme="election"] .chip.active,
  [data-theme="election"] .loc-chip.active,
  [data-theme="election"] .genre-chip.active,
  [data-theme="election"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.35) 0%, rgba(220, 38, 38, 0.25) 100%);
    border-color: #3b82f6;
    color: #ffffff;
    box-shadow: 0 0 12px rgba(59, 130, 246, 0.35);
  }}

  /* =========================================================================
     VETERANS DAY / BUNKER HILL THEME (Naval Blue, Gold Brass & Valor Crimson)
     ========================================================================= */
  [data-theme="veterans"] {{
    --bg: #090d18;
    --card: #111a2e;
    --card-hover: #182542;
    --fg: #f8fafc;
    --muted: #94a3b8;
    --accent: #d4af37;
    --accent-glow: rgba(212, 175, 55, 0.35);
    --border: rgba(212, 175, 55, 0.25);
    --border-hover: rgba(212, 175, 55, 0.50);
    --green: #38bdf8;
    --green-bg: rgba(56, 189, 248, 0.14);
    --green-border: rgba(56, 189, 248, 0.35);
    --warn: #f59e0b;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="veterans"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(212, 175, 55, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 90% 40%, rgba(30, 58, 138, 0.16) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="veterans"] .banner {{
    background-color: #0c1322;
    border-bottom: 2px solid rgba(212, 175, 55, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(212, 175, 55, 0.15);
  }}
  [data-theme="veterans"] .banner-top-tag {{
    color: #fbbf24;
    text-shadow: 0 0 12px rgba(251, 191, 36, 0.6);
  }}
  [data-theme="veterans"] .live-pulse {{
    background: #d4af37;
    box-shadow: 0 0 10px #d4af37, 0 0 20px #d4af37;
  }}
  [data-theme="veterans"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #fde047 65%, #60a5fa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(212, 175, 55, 0.35));
  }}
  [data-theme="veterans"] .pill-submit-btn {{
    background: linear-gradient(135deg, #b45309 0%, #d97706 50%, #1e3a8a 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(212, 175, 55, 0.45);
    border-radius: 999px;
  }}
  [data-theme="veterans"] .chip.active,
  [data-theme="veterans"] .loc-chip.active,
  [data-theme="veterans"] .genre-chip.active,
  [data-theme="veterans"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(212, 175, 55, 0.35) 0%, rgba(30, 58, 138, 0.35) 100%);
    border-color: #d4af37;
    color: #fef08a;
    box-shadow: 0 0 12px rgba(212, 175, 55, 0.35);
  }}

  /* =========================================================================
     THANKSGIVING / NEW ENGLAND HARVEST THEME (Harvest Amber & Cranberry)
     ========================================================================= */
  [data-theme="thanksgiving"] {{
    --bg: #100b08;
    --card: #1a120c;
    --card-hover: #261b12;
    --fg: #fef7ed;
    --muted: #bfa094;
    --accent: #ea580c;
    --accent-glow: rgba(234, 88, 12, 0.35);
    --border: rgba(234, 88, 12, 0.22);
    --border-hover: rgba(234, 88, 12, 0.45);
    --green: #84cc16;
    --green-bg: rgba(132, 204, 22, 0.14);
    --green-border: rgba(132, 204, 22, 0.35);
    --warn: #f59e0b;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 6px;
  }}
  [data-theme="thanksgiving"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(234, 88, 12, 0.09) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 85% 35%, rgba(190, 18, 60, 0.07) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="thanksgiving"] .banner {{
    background-color: #170f0a;
    border-bottom: 2px solid rgba(234, 88, 12, 0.45);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5), 0 0 20px rgba(234, 88, 12, 0.15);
  }}
  [data-theme="thanksgiving"] .banner-top-tag {{
    color: #fb923c;
    text-shadow: 0 0 12px rgba(251, 146, 60, 0.6);
  }}
  [data-theme="thanksgiving"] .live-pulse {{
    background: #ea580c;
    box-shadow: 0 0 10px #ea580c, 0 0 20px #ea580c;
  }}
  [data-theme="thanksgiving"] .banner-title {{
    background: linear-gradient(135deg, #fffbeb 20%, #fb923c 60%, #e11d48 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(234, 88, 12, 0.35));
  }}
  [data-theme="thanksgiving"] .pill-submit-btn {{
    background: linear-gradient(135deg, #c2410c 0%, #ea580c 50%, #be123c 100%);
    color: #fff;
    box-shadow: 0 0 14px rgba(234, 88, 12, 0.5);
    border-radius: 999px;
  }}
  [data-theme="thanksgiving"] .chip.active,
  [data-theme="thanksgiving"] .loc-chip.active,
  [data-theme="thanksgiving"] .genre-chip.active,
  [data-theme="thanksgiving"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(234, 88, 12, 0.4) 0%, rgba(190, 18, 60, 0.3) 100%);
    border-color: #ea580c;
    color: #ffedd5;
    box-shadow: 0 0 12px rgba(234, 88, 12, 0.4);
  }}

  /* =========================================================================
     BLACK FRIDAY THEME (Midnight Stealth Black & High-Voltage Electric Gold)
     ========================================================================= */
  [data-theme="blackfriday"] {{
    --bg: #050608;
    --card: #0f1116;
    --card-hover: #181c24;
    --fg: #fafafa;
    --muted: #a1a1aa;
    --accent: #facc15;
    --accent-glow: rgba(250, 204, 21, 0.35);
    --border: rgba(250, 204, 21, 0.22);
    --border-hover: rgba(250, 204, 21, 0.45);
    --green: #22c55e;
    --green-bg: rgba(34, 197, 94, 0.14);
    --green-border: rgba(34, 197, 94, 0.35);
    --warn: #f97316;
    --radius-lg: 12px;
    --radius-md: 8px;
    --radius-sm: 4px;
  }}
  [data-theme="blackfriday"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(250, 204, 21, 0.08) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 10% 40%, rgba(239, 68, 68, 0.06) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="blackfriday"] .banner {{
    background-color: #07090f;
    border-bottom: 2px solid rgba(250, 204, 21, 0.5);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.6), 0 0 20px rgba(250, 204, 21, 0.2);
  }}
  [data-theme="blackfriday"] .banner-top-tag {{
    color: #facc15;
    text-shadow: 0 0 14px rgba(250, 204, 21, 0.7);
  }}
  [data-theme="blackfriday"] .live-pulse {{
    background: #facc15;
    box-shadow: 0 0 10px #facc15, 0 0 20px #facc15;
  }}
  [data-theme="blackfriday"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #fde047 60%, #f97316 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 22px rgba(250, 204, 21, 0.4));
  }}
  [data-theme="blackfriday"] .pill-submit-btn {{
    background: linear-gradient(135deg, #ca8a04 0%, #eab308 50%, #dc2626 100%);
    color: #000;
    font-weight: 800;
    box-shadow: 0 0 16px rgba(250, 204, 21, 0.5);
    border-radius: 999px;
  }}
  [data-theme="blackfriday"] .chip.active,
  [data-theme="blackfriday"] .loc-chip.active,
  [data-theme="blackfriday"] .genre-chip.active,
  [data-theme="blackfriday"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(250, 204, 21, 0.35) 0%, rgba(249, 115, 22, 0.25) 100%);
    border-color: #facc15;
    color: #fef08a;
    box-shadow: 0 0 12px rgba(250, 204, 21, 0.35);
  }}

  /* =========================================================================
     CYBER MONDAY / KENDALL TECH THEME (Cyberpunk Neon Cyan & Electric Violet)
     ========================================================================= */
  [data-theme="cybermonday"] {{
    --bg: #050811;
    --card: #0c1222;
    --card-hover: #131c35;
    --fg: #f0fdf4;
    --muted: #7dd3fc;
    --accent: #06b6d4;
    --accent-glow: rgba(6, 182, 212, 0.45);
    --border: rgba(6, 182, 212, 0.25);
    --border-hover: rgba(6, 182, 212, 0.55);
    --green: #10b981;
    --green-bg: rgba(16, 185, 129, 0.14);
    --green-border: rgba(16, 185, 129, 0.35);
    --warn: #ec4899;
    --radius-lg: 14px;
    --radius-md: 8px;
    --radius-sm: 5px;
  }}
  [data-theme="cybermonday"] body {{
    background-color: var(--bg);
    background-image:
      radial-gradient(ellipse 80% 50% at 50% -10%, rgba(6, 182, 212, 0.12) 0%, transparent 70%),
      radial-gradient(ellipse 60% 40% at 85% 30%, rgba(168, 85, 247, 0.10) 0%, transparent 60%);
    background-attachment: fixed;
  }}
  [data-theme="cybermonday"] .banner {{
    background-color: #070e1c;
    border-bottom: 2px solid rgba(6, 182, 212, 0.5);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.6), 0 0 20px rgba(6, 182, 212, 0.2);
  }}
  [data-theme="cybermonday"] .banner-top-tag {{
    color: #22d3ee;
    text-shadow: 0 0 14px rgba(34, 211, 238, 0.7);
  }}
  [data-theme="cybermonday"] .live-pulse {{
    background: #06b6d4;
    box-shadow: 0 0 10px #06b6d4, 0 0 20px #06b6d4;
  }}
  [data-theme="cybermonday"] .banner-title {{
    background: linear-gradient(135deg, #ffffff 20%, #22d3ee 60%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 20px rgba(6, 182, 212, 0.4));
  }}
  [data-theme="cybermonday"] .pill-submit-btn {{
    background: linear-gradient(135deg, #0891b2 0%, #06b6d4 50%, #9333ea 100%);
    color: #fff;
    box-shadow: 0 0 16px rgba(6, 182, 212, 0.5);
    border-radius: 999px;
  }}
  [data-theme="cybermonday"] .chip.active,
  [data-theme="cybermonday"] .loc-chip.active,
  [data-theme="cybermonday"] .genre-chip.active,
  [data-theme="cybermonday"] .sub-chip.active {{
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.35) 0%, rgba(168, 85, 247, 0.25) 100%);
    border-color: #06b6d4;
    color: #cffafe;
    box-shadow: 0 0 12px rgba(6, 182, 212, 0.4);
  }}

  /* Holiday themes generated from holiday_themes.py: banner art, greeting, palettes */
  {holiday_css}

  /* Light theme overrides (light_theme.py) */
{LIGHT_THEME_CSS}
</style>
</head>
<body>
  <div class="banner">
    <div class="banner-inner">
      <div class="banner-top-row">
        <div class="banner-top-tag"><span class="live-pulse"></span> GREATER BOSTON LIVE EVENTS</div>
        <div class="banner-top-actions">
          <button type="button" class="pill-submit-btn" id="btn-open-submit-modal" aria-haspopup="dialog" aria-expanded="false">
            <span>＋ Add Event</span>
          </button>
        </div>
        <div class="theme-toggle-wrap">
          <div class="theme-toggle-pills" role="radiogroup" aria-label="Visual Theme">
            <button type="button" class="theme-pill-btn theme-pill-holiday{' active' if seasonal_key else ''}" id="theme-pill-holiday" data-theme="{seasonal_key or ''}" role="radio" aria-checked="{'true' if seasonal_key else 'false'}" title="{escape(seasonal_label or '')} theme"{'' if seasonal_key else ' hidden'}><span class="holiday-pill-emoji">{seasonal_icon or ''}</span><span class="holiday-pill-label">{escape(seasonal_label or '')}</span></button>
            <button type="button" class="theme-pill-btn{' active' if default_theme == 'classic' else ''}" data-theme="classic" role="radio" aria-checked="{'true' if default_theme == 'classic' else 'false'}" title="Classic Dark Theme">🌙</button>
            <button type="button" class="theme-pill-btn{' active' if default_theme == 'light' else ''}" data-theme="light" role="radio" aria-checked="{'true' if default_theme == 'light' else 'false'}" title="Light Theme">☀️</button>
            <button type="button" class="theme-pill-btn{' active' if default_theme == 'indie' else ''}" data-theme="indie" role="radio" aria-checked="{'true' if default_theme == 'indie' else 'false'}" title="Indie Guide Theme">📰</button>
            <button type="button" class="theme-pill-btn{' active' if default_theme == 'anime' else ''}" data-theme="anime" role="radio" aria-checked="{'true' if default_theme == 'anime' else 'false'}" title="Anime Theme">🌸</button>
          </div>
        </div>
      </div>
      <div class="banner-title-row">
        <h1 class="banner-title">Wicked Boston Events</h1>
      </div>
      {holiday_greetings}
      <div class="banner-meta-pill">
        {weather_pill_html}
        <span class="pill-stat"><strong>{total:,}</strong> events · <strong>{len(results)}</strong> venues</span>
        <span class="pill-dot">·</span>
        <a href="https://www.instagram.com/wickedbostonevents/" target="_blank" rel="noopener" class="pill-social-link" title="Follow @wickedbostonevents on Instagram" aria-label="Follow @wickedbostonevents on Instagram">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block; vertical-align:middle;"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg>
        </a>
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
        <label class="lgbtq-toggle" for="lgbtq-only-chk">
          <input type="checkbox" id="lgbtq-only-chk">
          <span><span class="chip-icon">🏳️‍🌈 </span>LGBTQ+ events only</span>
        </label>
        <div class="timeframe-toggle-wrap" style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--border);">
          <label class="timeframe-toggle" for="timeframe-enable-chk">
            <input type="checkbox" id="timeframe-enable-chk">
            <span><span class="chip-icon">⏱️ </span>Set timeframe window</span>
          </label>
          <div class="custom-time-range" id="custom-time-range" style="display: none; margin-top: 10px;">
            <div class="time-select-row">
              <div class="time-input-wrap">
                <label for="time-from-select">From</label>
                <select id="time-from-select" class="time-dropdown"></select>
              </div>
              <div class="time-range-arrow">→</div>
              <div class="time-input-wrap">
                <label for="time-to-select">To</label>
                <select id="time-to-select" class="time-dropdown"></select>
              </div>
            </div>
            <div class="time-range-active-indicator" id="time-range-active-indicator" style="display:none;"></div>
          </div>
        </div>
      </div>
      <div class="filter-group">
        <h3>Category <span class="spacer"></span> <button type="button" id="cat-all">all</button> <button type="button" id="cat-none">none</button></h3>
        <div style="display:none;">
          <label class="chk chk-saved" id="chk-saved-label">
            <input type="checkbox" id="saved-only-chk">
            <span><span class="chip-icon">⭐ </span>Saved <span class="count" id="saved-count" style="display:none;">(0)</span></span>
          </label>
          <button type="button" class="btn-copy-plan-sidebar" id="btn-copy-plan" style="display:none;" title="Copy your saved events as a shareable text itinerary"><span class="chip-icon">📋 </span>Copy Plan</button>
        </div>
        <div class="chk-grid">
          {bucket_boxes}
        </div>
      </div>
      <div class="filter-group">
        <h3>City <span class="spacer"></span> <button type="button" id="city-all">all</button> <button type="button" id="city-none">none</button></h3>
        <div class="chk-grid">{city_boxes}</div>
      </div>
      <div class="filter-group transit-filter-group">
        <h3>MBTA Subway Line</h3>
        {transit_boxes}
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
        <div class="view-toggle" role="group" aria-label="Feed presentation">
          <button type="button" class="view-btn active" id="btn-view-list" data-view="list" title="Browse events grouped by category and city">
            <span>Category</span>
          </button>
          <button type="button" class="view-btn" id="btn-near-me" data-view="near" title="Sort events by distance to your current location">
            <span id="near-me-btn-label">Near Me</span>
          </button>
          <button type="button" class="view-btn" id="btn-drop-pin" data-view="pin" title="Tap the map to drop a pin and sort events by distance from it">
            <span id="drop-pin-btn-label">Drop Pin</span>
          </button>
        </div>
        <div class="view-actions">
          <button type="button" class="map-toggle-btn" id="btn-view-map" title="Toggle interactive venue map">
            <span id="map-btn-label">Map</span>
          </button>
        </div>
      </div>
      <div class="location-chips-bar" id="location-chips">
        <button type="button" class="loc-chip active" data-city="all"><span class="chip-icon">📍 </span>All Areas</button>
        <button type="button" class="loc-chip" data-city="boston"><span class="city-dot" style="background:#5d9bff"></span>Boston</button>
        <button type="button" class="loc-chip" data-city="cambridge"><span class="city-dot" style="background:#e05a6b"></span>Cambridge</button>
        <button type="button" class="loc-chip" data-city="somerville"><span class="city-dot" style="background:#f29e4c"></span>Somerville</button>
      </div>
      <div class="subarea-chips-bar" id="subarea-chips-bar" style="display: none;"></div>
      <div class="week-nav" id="week-nav">
        <button type="button" id="week-prev" aria-label="Previous">← prev</button>
        <span id="week-label">Today, {today.strftime("%b %d")}</span>
        <button type="button" id="week-next" aria-label="Next">next →</button>
        <button type="button" id="week-today">today</button>
        <button type="button" id="cal-toggle" aria-expanded="false"><span class="chip-icon">📅 </span>pick date</button>
        <button type="button" class="chip chip-time-custom" id="quick-custom-time-chip" style="display:none;" title="Click to clear timeframe filter"><span id="active-timeframe-label"></span> <span class="chip-icon" style="margin-left:4px;">✕</span></button>
        <button type="button" class="chip chip-active-genre" id="quick-active-genre-chip" style="display:none;" title="Click to clear genre filter"><span id="active-genre-label"></span> <span class="chip-icon" style="margin-left:4px;">✕</span></button>
      </div>
      <div class="mini-cal" id="mini-cal" hidden>
        <div class="mini-cal-head">
          <button type="button" id="cal-prev-month" aria-label="Previous month">‹</button>
          <span id="cal-month-label"></span>
          <button type="button" id="cal-next-month" aria-label="Next month">›</button>
        </div>
        <div class="mini-cal-grid" id="mini-cal-grid"></div>
        <div class="mini-cal-hint" id="cal-hint">Select a date, or click a 2nd date to pick a range</div>
      </div>
      <div id="map-view-wrapper" class="map-view-wrapper" style="display: none;">
        <div class="map-header">
          <div class="map-header-title">
            <span class="live-pulse"></span>
            <strong>Greater Boston Live Map</strong>
            <span class="map-hint">· <strong id="map-venue-count">0</strong> venues with events · OpenStreetMap</span>
          </div>
          <div class="map-header-actions">
            <button type="button" id="map-label-toggle-btn" class="map-tool-btn" title="Toggle between venue names and numbers only"><span class="chip-icon">🏷️ </span>Names: On</button>
            <button type="button" id="map-recenter-btn" class="map-tool-btn" title="Center map on Boston"><span class="chip-icon">🎯 </span>Center Boston</button>
          </div>
        </div>
        <div id="pin-hint" class="pin-hint" hidden>
          <span><span class="chip-icon">📌 </span><strong>Tap the map to drop your pin.</strong> Events will be sorted by distance from it.</span>
          <button type="button" id="pin-cancel-btn" class="map-tool-btn">Cancel</button>
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
      <template id="deferred-days"></template>
      <div id="days-loading" class="no-events-msg days-loading" style="display: none;" role="status"><p>Loading events…</p></div>
      <div class="week-nav bottom">
        <button type="button" id="week-prev-b" aria-label="Previous week">← prev</button>
        <span id="week-label-b"></span>
        <button type="button" id="week-next-b" aria-label="Next week">next →</button>
      </div>
      {ongoing_section}
      {seo_directory_html}
    </main>
    {useful_sidebar}
  </div>
  <footer>
    <p>Boston Events · Live local music, comedy, arts, outdoors &amp; community events across Greater Boston.</p>
    <p style="margin-top:6px; font-size:11px; opacity:0.85;">Data compiled directly from venue calendars and official local community feeds. Not affiliated with any commercial ticketing broker. · <a href="https://www.instagram.com/wickedbostonevents/" target="_blank" rel="noopener" class="footer-social-link">Instagram: @wickedbostonevents</a><span id="pwa-install-wrap" hidden> · <button type="button" class="footer-pwa-btn" onclick="installPWA()">📲 Add to Home Screen</button></span></p>
  </footer>
  <!-- Community Event Submission Modal -->
  <div id="schedule-bar" class="schedule-bar" style="display:none;">
    <button type="button" class="schedule-bar-view" id="schedule-view" aria-pressed="false">★ My Schedule <span id="schedule-count"></span></button>
    <button type="button" class="schedule-bar-share" id="schedule-share">Share</button>
  </div>
  <div id="schedule-share-modal" class="modal-overlay" role="dialog" aria-modal="true" aria-labelledby="schedule-share-title" style="display:none;">
    <div class="modal-card schedule-share-card">
      <div class="modal-header">
        <div>
          <h2 class="modal-title" id="schedule-share-title">Share your schedule</h2>
          <p class="modal-sub" id="schedule-share-sub"></p>
        </div>
        <button type="button" class="modal-close-btn" id="schedule-share-close" aria-label="Close">✕</button>
      </div>
      <label class="schedule-share-label" for="schedule-share-name">Your name (optional)</label>
      <input type="text" id="schedule-share-name" maxlength="40" placeholder="Shows as “Sam's weekend”" autocomplete="given-name">
      <label class="schedule-share-label" for="schedule-share-link">Link to send</label>
      <input type="text" id="schedule-share-link" readonly>
      <div class="schedule-share-actions">
        <button type="button" class="schedule-share-copy" id="schedule-share-copy">Copy link</button>
        <button type="button" class="schedule-share-send" id="schedule-share-send" style="display:none;">Send</button>
        <a class="schedule-share-open" id="schedule-share-open" href="/schedule/" target="_blank" rel="noopener">Preview</a>
      </div>
    </div>
  </div>
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
    const defaultUncheckedCats = new Set({json.dumps(sorted(DEFAULT_UNCHECKED_BUCKETS))});
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
    const lgbtqOnlyChk = document.getElementById('lgbtq-only-chk');

    const locChips = document.querySelectorAll('#location-chips .loc-chip');
    const transitChips = document.querySelectorAll('.transit-chip');
    const subareaBar = document.getElementById('subarea-chips-bar');
    const GENRES_DATA = {json.dumps(genres_map)};
    let activeGenre = 'all';
    let activeTransit = 'all';
    let timeFrom = null;
    let timeTo = null;
    const timeFromSelect = document.getElementById('time-from-select');
    const timeToSelect = document.getElementById('time-to-select');
    const timeframeEnableChk = document.getElementById('timeframe-enable-chk');
    const customTimeRangeDiv = document.getElementById('custom-time-range');
    const timeRangeIndicator = document.getElementById('time-range-active-indicator');
    const quickCustomTimeChip = document.getElementById('quick-custom-time-chip');
    const activeTimeframeLabel = document.getElementById('active-timeframe-label');

    const HOURLY_TIMES = [
      {{ val: '00:00', mins: 0, label: '12:00 AM (Midnight)' }},
      {{ val: '01:00', mins: 60, label: '1:00 AM' }},
      {{ val: '02:00', mins: 120, label: '2:00 AM' }},
      {{ val: '03:00', mins: 180, label: '3:00 AM' }},
      {{ val: '04:00', mins: 240, label: '4:00 AM' }},
      {{ val: '05:00', mins: 300, label: '5:00 AM' }},
      {{ val: '06:00', mins: 360, label: '6:00 AM' }},
      {{ val: '07:00', mins: 420, label: '7:00 AM' }},
      {{ val: '08:00', mins: 480, label: '8:00 AM' }},
      {{ val: '09:00', mins: 540, label: '9:00 AM' }},
      {{ val: '10:00', mins: 600, label: '10:00 AM' }},
      {{ val: '11:00', mins: 660, label: '11:00 AM' }},
      {{ val: '12:00', mins: 720, label: '12:00 PM (Noon)' }},
      {{ val: '13:00', mins: 780, label: '1:00 PM' }},
      {{ val: '14:00', mins: 840, label: '2:00 PM' }},
      {{ val: '15:00', mins: 900, label: '3:00 PM' }},
      {{ val: '16:00', mins: 960, label: '4:00 PM' }},
      {{ val: '17:00', mins: 1020, label: '5:00 PM' }},
      {{ val: '18:00', mins: 1080, label: '6:00 PM' }},
      {{ val: '19:00', mins: 1140, label: '7:00 PM' }},
      {{ val: '20:00', mins: 1200, label: '8:00 PM' }},
      {{ val: '21:00', mins: 1260, label: '9:00 PM' }},
      {{ val: '22:00', mins: 1320, label: '10:00 PM' }},
      {{ val: '23:00', mins: 1380, label: '11:00 PM' }},
      {{ val: '24:00', mins: 1440, label: '12:00 AM (Next Midnight)' }},
      {{ val: '26:00', mins: 1560, label: '2:00 AM (Late Night)' }}
    ];

    function initTimeDropdowns() {{
      if (!timeFromSelect) return;
      timeFromSelect.innerHTML = '';
      HOURLY_TIMES.slice(0, 24).forEach(item => {{
        const opt = document.createElement('option');
        opt.value = item.val;
        opt.textContent = item.label;
        if (item.val === '20:00') opt.selected = true;
        timeFromSelect.appendChild(opt);
      }});
      syncToOptions(timeFromSelect.value, '24:00');
    }}

    function syncToOptions(fromVal, preferredToVal) {{
      if (!timeToSelect) return;
      const fromMins = parseTimeToMinutes(fromVal) ?? 1200;
      const targetToMins = parseTimeToMinutes(preferredToVal);

      let validOptions = HOURLY_TIMES.filter(item => item.mins > fromMins);
      if (validOptions.length === 0) {{
        validOptions = HOURLY_TIMES.slice(24);
      }}

      timeToSelect.innerHTML = '';
      validOptions.forEach(item => {{
        const opt = document.createElement('option');
        opt.value = item.val;
        opt.textContent = item.label;
        timeToSelect.appendChild(opt);
      }});

      if (targetToMins && targetToMins > fromMins && validOptions.some(o => o.mins === targetToMins)) {{
        timeToSelect.value = formatMinutesToHHMM(targetToMins);
      }} else {{
        const midnight = validOptions.find(o => o.mins === 1440);
        if (fromMins < 1440 && midnight) {{
          timeToSelect.value = '24:00';
        }} else {{
          timeToSelect.value = validOptions[validOptions.length - 1].val;
        }}
      }}
    }}

    function parseTimeToMinutes(str) {{
      if (!str) return null;
      str = String(str).trim().toLowerCase();
      if (str === 'midnight' || str === '12am' || str === '12:00am' || str === '24:00' || str === '24') return 1440;
      if (str === 'noon' || str === '12pm' || str === '12:00pm') return 720;
      if (str === '2am' || str === '2:00am' || str === '26:00' || str === '26') return 1560;

      const ampmMatch = str.match(/^(\d{{1,2}})(?::(\d{{2}}))?\s*(am|pm)$/);
      if (ampmMatch) {{
        let h = parseInt(ampmMatch[1], 10);
        const m = ampmMatch[2] ? parseInt(ampmMatch[2], 10) : 0;
        const ampm = ampmMatch[3];
        if (ampm === 'pm' && h < 12) h += 12;
        if (ampm === 'am' && h === 12) h = 0;
        return h * 60 + m;
      }}

      const colonMatch = str.match(/^(\d{{1,2}}):(\d{{2}})$/);
      if (colonMatch) {{
        const h = parseInt(colonMatch[1], 10);
        const m = parseInt(colonMatch[2], 10);
        return h * 60 + m;
      }}

      const numMatch = str.match(/^(\d{{1,2}})$/);
      if (numMatch) {{
        const n = parseInt(numMatch[1], 10);
        return n * 60;
      }}

      return null;
    }}

    function formatMinutesToHHMM(mins) {{
      if (mins === null || mins === undefined) return '';
      if (mins === 1440) return '24:00';
      if (mins === 1560) return '26:00';
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return `${{String(h).padStart(2, '0')}}:${{String(m).padStart(2, '0')}}`;
    }}

    function formatMinutesToLabel(mins) {{
      if (mins === null || mins === undefined) return '';
      if (mins === 1440) return 'Midnight';
      if (mins === 1560) return '2:00 AM';
      if (mins === 720) return '12:00 PM';
      const h24 = Math.floor(mins / 60) % 24;
      const m = mins % 60;
      const ampm = (Math.floor(mins / 60) >= 12 && Math.floor(mins / 60) < 24) ? 'PM' : 'AM';
      let h12 = h24 % 12;
      if (h12 === 0) h12 = 12;
      return m > 0 ? `${{h12}}:${{String(m).padStart(2, '0')}} ${{ampm}}` : `${{h12}} ${{ampm}}`;
    }}

    function updateTimeUI() {{
      const isCustomActive = (timeFrom !== null || timeTo !== null);
      if (timeframeEnableChk) {{
        timeframeEnableChk.checked = isCustomActive;
      }}
      if (customTimeRangeDiv) {{
        customTimeRangeDiv.style.display = isCustomActive ? 'block' : 'none';
      }}

      if (timeFromSelect && timeFrom !== null) {{
        timeFromSelect.value = formatMinutesToHHMM(timeFrom);
      }}
      const curFrom = (timeFromSelect && timeFromSelect.value) ? timeFromSelect.value : (timeFrom !== null ? formatMinutesToHHMM(timeFrom) : '20:00');
      const curTo = (timeTo !== null) ? formatMinutesToHHMM(timeTo) : (timeToSelect ? timeToSelect.value : '24:00');
      syncToOptions(curFrom, curTo);

      if (timeToSelect && timeTo !== null) {{
        timeToSelect.value = formatMinutesToHHMM(timeTo);
      }}

      if (timeRangeIndicator) {{
        if (isCustomActive) {{
          let desc = '';
          if (timeFrom !== null && timeTo !== null) {{
            desc = `Active: ${{formatMinutesToLabel(timeFrom)}} – ${{formatMinutesToLabel(timeTo)}}`;
          }} else if (timeFrom !== null) {{
            desc = `Active: From ${{formatMinutesToLabel(timeFrom)}} onwards`;
          }} else if (timeTo !== null) {{
            desc = `Active: Until ${{formatMinutesToLabel(timeTo)}}`;
          }}
          timeRangeIndicator.textContent = desc;
          timeRangeIndicator.style.display = 'block';
        }} else {{
          timeRangeIndicator.style.display = 'none';
        }}
      }}

      if (quickCustomTimeChip && activeTimeframeLabel) {{
        if (isCustomActive) {{
          let label = '';
          if (timeFrom !== null && timeTo !== null) {{
            label = `${{formatMinutesToLabel(timeFrom)}} – ${{formatMinutesToLabel(timeTo)}}`;
          }} else if (timeFrom !== null) {{
            label = `From ${{formatMinutesToLabel(timeFrom)}}`;
          }} else if (timeTo !== null) {{
            label = `Until ${{formatMinutesToLabel(timeTo)}}`;
          }}
          activeTimeframeLabel.textContent = `⏱️ ${{label}}`;
          quickCustomTimeChip.style.display = 'inline-flex';
        }} else {{
          quickCustomTimeChip.style.display = 'none';
        }}
      }}
    }}

    function setTimeRange(fromVal, toVal, skipApply = false) {{
      timeFrom = parseTimeToMinutes(fromVal);
      timeTo = parseTimeToMinutes(toVal);
      if (timeFrom !== null && timeTo !== null && timeTo <= timeFrom) {{
        timeTo = (timeFrom < 1440) ? 1440 : timeFrom + 60;
      }}
      if (timeFrom !== null && timeFrom < 720 && timeFilter === 'today') {{
        showPastToday = true;
      }}
      updateTimeUI();
      if (!skipApply) {{
        apply();
        stateToHash();
      }}
    }}

    let starredOnly = false;
    let starredEvents = new Set();
    const SUBAREAS_DATA = {json.dumps(SUBAREAS_BY_CITY)};
    const CITY_LABELS_MAP = {json.dumps(CITY_LABELS)};
    let activeSubarea = 'all';
    let renderedSubareaCity = null;
    const quickChips = document.querySelectorAll('#quick-chips .chip[data-time]');
    const quickPopularChip = document.getElementById('quick-popular-chip');
    const quickFeaturedChip = document.getElementById('quick-featured-chip');
    const quickActiveGenreChip = document.getElementById('quick-active-genre-chip');
    const activeGenreLabel = document.getElementById('active-genre-label');
    const featuredCountEl = document.getElementById('featured-count');
    const quickStarredChip = document.getElementById('quick-starred-chip');
    const starredCountEl = document.getElementById('starred-count');
    const savedOnlyChk = document.getElementById('saved-only-chk');
    const savedCountEl = document.getElementById('saved-count');
    const btnCopyPlan = document.getElementById('btn-copy-plan');
    const scheduleBar = document.getElementById('schedule-bar');
    const scheduleCount = document.getElementById('schedule-count');
    const scheduleView = document.getElementById('schedule-view');
    let popularOnly = false;
    let featuredOnly = false;
    let userUpvotes = new Set();
    let cachedVotes = {{}};
    let timeFilter = 'today';
    let rangeStart = null;
    let rangeEnd = null;
    let currentView = 'list';
    let mapOpen = false;
    let showPastToday = false;
    let leafletMap = null;
    let markersLayer = null;
    let mapLoading = false;
    let nearMeActive = false;
    // A dropped pin works like Near Me, measured from wherever the pin is instead of from you.
    let pinCoords = null;
    let pinPlacing = false;
    let pinMarker = null;

    function nearOrigin() {{
      if (pinCoords) return {{ lat: pinCoords.lat, lng: pinCoords.lng, kind: 'pin' }};
      if (userCoords && userCoords.lat && userCoords.lng) return {{ lat: userCoords.lat, lng: userCoords.lng, kind: 'me' }};
      return null;
    }}

    function updatePinUI() {{
      const hint = document.getElementById('pin-hint');
      if (hint) hint.hidden = !pinPlacing;
      const mapEl = document.getElementById('leaflet-map');
      if (mapEl) mapEl.classList.toggle('placing-pin', pinPlacing);
      const pinBtn = document.getElementById('btn-drop-pin');
      if (pinBtn) pinBtn.classList.toggle('active', pinPlacing || (nearMeActive && !!pinCoords));
      const nearBtn = document.getElementById('btn-near-me');
      if (nearBtn) nearBtn.classList.toggle('active', nearMeActive && !pinCoords);
      const label = document.getElementById('drop-pin-btn-label');
      if (label) label.textContent = pinPlacing ? 'Tap the map…' : (pinCoords ? 'Move Pin' : 'Drop Pin');
    }}

    function drawPin() {{
      if (!leafletMap || typeof L === 'undefined') return;
      if (!pinCoords) {{
        if (pinMarker) {{ leafletMap.removeLayer(pinMarker); pinMarker = null; }}
        return;
      }}
      if (!pinMarker) {{
        pinMarker = L.marker([pinCoords.lat, pinCoords.lng], {{
          icon: L.divIcon({{ className: 'drop-pin-marker', html: '<span>📌</span>', iconSize: [32, 32], iconAnchor: [9, 30] }}),
          draggable: true,
          zIndexOffset: 1000,
          title: 'Your pin: drag to move it',
        }}).addTo(leafletMap);
        pinMarker.on('dragend', () => {{
          const p = pinMarker.getLatLng();
          placePin(p.lat, p.lng);
        }});
      }} else {{
        pinMarker.setLatLng([pinCoords.lat, pinCoords.lng]);
      }}
    }}

    function startPinDrop() {{
      pinPlacing = true;
      updatePinUI();
      toggleMap(true);
      const mapWrapper = document.getElementById('map-view-wrapper');
      if (mapWrapper && mapWrapper.scrollIntoView) mapWrapper.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}

    function cancelPinDrop() {{
      pinPlacing = false;
      updatePinUI();
    }}

    function placePin(lat, lng) {{
      pinCoords = {{ lat: Math.round(lat * 1e5) / 1e5, lng: Math.round(lng * 1e5) / 1e5 }};
      pinPlacing = false;
      drawPin();
      setNearMe(true);
    }}

    function clearPin() {{
      pinCoords = null;
      pinPlacing = false;
      drawPin();
      updatePinUI();
    }}
    let userCoords = null;

    function haversineMiles(lat1, lon1, lat2, lon2) {{
      const R = 3958.8;
      const dLat = (lat2 - lat1) * Math.PI / 180;
      const dLon = (lon2 - lon1) * Math.PI / 180;
      const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                Math.sin(dLon / 2) * Math.sin(dLon / 2);
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
      return R * c;
    }}

    const mobileToggle = document.getElementById('mobile-filter-toggle');
    const mobileClose = document.getElementById('mobile-filter-close');
    const sidebarFilters = document.getElementById('sidebar-filters');
    const mobileBadge = document.getElementById('mobile-filter-badge');

    let daySections = Array.from(document.querySelectorAll('.day[data-date]'));
    const ALL_EVENT_DATES = {json.dumps(all_event_dates)};
    const eventDates = new Set(ALL_EVENT_DATES);

    // Days after the first three aren't in the page. Day and week views fetch just the days they
    // show (days/<date>.html); "all", search, date ranges and saved lists fetch every later day at
    // once (deferred_days.html). DEFERRED_DATES says which days have a file.
    const DEFERRED_DATES = new Set({deferred_dates_json});
    const dayLoads = new Map();  // date -> fetch promise
    let deferredHydrated = DEFERRED_DATES.size === 0;
    let deferredHydrationPromise = null;

    function hasDay(date) {{
      return !!document.querySelector(`.day[data-date="${{date}}"]`);
    }}

    // Insert fetched day sections in date order; a day already on the page is skipped.
    function insertDaySections(html) {{
      const bottomNav = document.querySelector('.week-nav.bottom');
      if (!html || !bottomNav || !bottomNav.parentNode) return;
      const box = document.createElement('div');
      box.innerHTML = html;
      Array.from(box.children).forEach(sec => {{
        const date = sec.dataset ? sec.dataset.date : '';
        if (date && date !== 'tba' && hasDay(date)) return;
        let before = bottomNav;
        if (date && date !== 'tba') {{
          const later = Array.from(document.querySelectorAll('.day[data-date]'))
            .find(d => d.dataset.date !== 'tba' && d.dataset.date > date);
          if (later) before = later;
        }}
        before.parentNode.insertBefore(sec, before);
      }});
      daySections = Array.from(document.querySelectorAll('.day[data-date]'));
      updateDayHeadings();
      if (starredEvents && starredEvents.size > 0) {{
        loadStarredState();
      }}
    }}

    // Fetch the given days (those not on the page or already coming); resolves once they're in.
    function loadDays(dates) {{
      const want = dates.filter(d => DEFERRED_DATES.has(d) && !hasDay(d) && !dayLoads.has(d));
      want.forEach(d => {{
        dayLoads.set(d, fetch(`days/${{d}}.html`).then(r => (r.ok ? r.text() : '')).catch(() => ''));
      }});
      if (!want.length) return Promise.all(dates.map(d => dayLoads.get(d)).filter(Boolean));
      return Promise.all(want.map(d => dayLoads.get(d))).then(htmls => {{
        htmls.forEach(insertDaySections);
        if (htmls.some(h => !h)) ensureDeferredDaysHydrated();  // a day file missing: load them all
        apply();
      }});
    }}

    function ensureDeferredDaysHydrated(callback) {{
      if (deferredHydrated) {{
        if (callback) callback();
        return;
      }}
      if (!deferredHydrationPromise) {{
        deferredHydrationPromise = fetch('deferred_days.html')
          .then(r => (r.ok ? r.text() : ''))
          .then(html => insertDaySections(html))
          .catch(() => {{}})
          .then(() => {{
            deferredHydrated = true;
            apply();
          }});
      }}
      deferredHydrationPromise.then(() => {{ if (callback) callback(); }});
    }}

    // Once the page is idle, fetch the next week's later days so paging ahead is instant.
    const prefetchSoon = () => loadDays(Array.from(DEFERRED_DATES).sort().slice(0, 7));
    if ('requestIdleCallback' in window) {{
      requestIdleCallback(prefetchSoon, {{ timeout: 2500 }});
    }} else {{
      setTimeout(prefetchSoon, 1500);
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
        // "Today · Thursday, Nov 5", but just "Saturday, Nov 7" for other days (not "Saturday · Saturday")
        const prefix = diffDays === 0 ? 'Today' : diffDays === 1 ? 'Tomorrow' : diffDays === -1 ? 'Yesterday' : '';
        h2.innerHTML = `${{prefix ? prefix + ' · ' : ''}}${{dayName}}, ${{shortStr}}${{countHtml}}`;
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
        refreshIfStale(true);  // a new day: the events below may be from yesterday's build
      }}
    }}

    // A tab brought back hours or days later (phone tab switcher, back/forward cache, home-screen app)
    // still holds the copy it loaded back then. On return, ask the server whether the site has been
    // redeployed since (its Last-Modified vs this copy's) and reload if so. Filters live in the URL, so
    // they survive. Offline or no header: keep what's on screen.
    const PAGE_OPENED_AT = Date.now();
    let pageHiddenAt = null;
    let freshCheckBusy = false;
    async function refreshIfStale(force) {{
      if (freshCheckBusy || !/^https?:$/.test(location.protocol)) return;
      const away = pageHiddenAt ? Date.now() - pageHiddenAt : 0;
      if (!force && Date.now() - PAGE_OPENED_AT < 60 * 60 * 1000 && away < 30 * 60 * 1000) return;
      freshCheckBusy = true;
      try {{
        const res = await fetch(location.pathname, {{ method: 'HEAD', cache: 'no-store' }});
        const live = Date.parse(res.headers.get('last-modified') || '');
        const mine = Date.parse(document.lastModified);
        if (res.ok && live && mine && live - mine > 60 * 1000) location.reload();
      }} catch (e) {{
        /* offline */
      }} finally {{
        freshCheckBusy = false;
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
      }} else if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        const s = parseISO(rangeStart);
        const e = parseISO(rangeEnd);
        label = `${{fmtShort(s)}} – ${{fmtShort(e)}}, ${{e.getFullYear()}}`;
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
      const todayBtn = document.getElementById('week-today');
      if (todayBtn) {{
        todayBtn.classList.toggle('active', !showAll && timeFilter === 'today');
      }}
      const calToggle = document.getElementById('cal-toggle');
      if (calToggle) {{
        if (timeFilter === 'range' && rangeStart && rangeEnd) {{
          const s = parseISO(rangeStart);
          const e = parseISO(rangeEnd);
          calToggle.innerHTML = `<span class="chip-icon">📅 </span>${{fmtShort(s)}} – ${{fmtShort(e)}}`;
          calToggle.classList.add('active');
        }} else if (timeFilter === 'day' && fmtISO(anchor) !== todayISO) {{
          calToggle.innerHTML = `<span class="chip-icon">📅 </span>${{fmtShort(anchor)}}`;
          calToggle.classList.add('active');
        }} else {{
          calToggle.innerHTML = '<span class="chip-icon">📅 </span>pick date';
          calToggle.classList.remove('active');
        }}
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
      leafletMap.on('click', (ev) => {{
        if (pinPlacing) placePin(ev.latlng.lat, ev.latlng.lng);
      }});
      drawPin();
      if (pinCoords) leafletMap.setView([pinCoords.lat, pinCoords.lng], 14);  // a shared pin link opens on the pin
    }}

    function toggleMap(forcedState) {{
      if (typeof forcedState === 'boolean') {{
        mapOpen = forcedState;
      }} else {{
        mapOpen = !mapOpen;
      }}
      currentView = mapOpen ? 'map' : 'list';
      if (!mapOpen && pinPlacing) cancelPinDrop();
      const mapBtn = document.getElementById('btn-view-map');
      const mapWrapper = document.getElementById('map-view-wrapper');

      if (mapBtn) mapBtn.classList.toggle('active', mapOpen);
      if (mapWrapper) mapWrapper.style.display = mapOpen ? 'flex' : 'none';

      if (mapOpen) {{
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

    function switchView(mode) {{
      if (mode === 'map') {{
        toggleMap(true);
      }} else {{
        toggleMap(false);
      }}
    }}

    function toggleNearMe() {{
      if (nearMeActive && !pinCoords) {{
        setNearMe(false);
        return;
      }}
      if (pinCoords) {{  // Near Me measures from you, not the pin
        clearPin();
        setNearMe(false);
      }}
      if (userCoords && userCoords.lat && userCoords.lng) {{
        setNearMe(true);
        return;
      }}
      const label = document.getElementById('near-me-btn-label');
      if (label) label.textContent = 'Locating...';
      if (!navigator.geolocation) {{
        alert('Geolocation is not supported by your browser.');
        if (label) label.textContent = 'Near Me';
        return;
      }}
      navigator.geolocation.getCurrentPosition(
        (pos) => {{
          userCoords = {{ lat: pos.coords.latitude, lng: pos.coords.longitude }};
          if (label) label.textContent = 'Near Me';
          setNearMe(true);
        }},
        (err) => {{
          if (label) label.textContent = 'Near Me';
          alert('Could not determine your location (' + (err.message || 'permission denied') + '). Please ensure location permissions are allowed in your browser.');
        }},
        {{ timeout: 10000, enableHighAccuracy: false, maximumAge: 60000 }}
      );
    }}

    function setNearMe(active) {{
      nearMeActive = !!active;
      const listBtn = document.getElementById('btn-view-list');
      const nearBtn = document.getElementById('btn-near-me');
      if (listBtn) listBtn.classList.toggle('active', !nearMeActive);
      if (nearBtn) nearBtn.classList.toggle('active', nearMeActive);
      if (!nearMeActive && pinCoords) clearPin();
      updatePinUI();
      if (!nearMeActive) {{
        daySections.forEach(day => {{
          const nearStream = day.querySelector('.near-me-stream');
          const citiesDiv = day.querySelector('.cities');
          if (nearStream && citiesDiv) {{
            nearStream.style.display = 'none';
            nearStream.innerHTML = '';
            day._nearCache = null;
            citiesDiv.style.display = 'block';
          }}
        }});
      }}
      apply();
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
          // Unchecked cities/categories collapse their section (.empty) without hiding each event
          if (li.closest('.empty')) return;
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
      if (quickPopularChip) {{
        quickPopularChip.classList.toggle('active', popularOnly);
      }}
      if (quickFeaturedChip) {{
        quickFeaturedChip.classList.toggle('active', featuredOnly);
      }}
      if (featuredCountEl) {{
        const totalPicks = document.querySelectorAll('.event.highlighted').length;
        featuredCountEl.textContent = `(${{totalPicks}})`;
        featuredCountEl.style.display = totalPicks > 0 ? 'inline' : 'none';
      }}
      if (quickStarredChip) {{
        quickStarredChip.classList.toggle('active', starredOnly);
      }}
      if (savedOnlyChk) {{
        savedOnlyChk.checked = starredOnly;
      }}
      const n = starredEvents.size;
      if (starredCountEl) {{
        starredCountEl.textContent = `(${{n}})`;
        starredCountEl.style.display = n > 0 ? 'inline' : 'none';
      }}
      if (savedCountEl) {{
        savedCountEl.textContent = `(${{n}})`;
        savedCountEl.style.display = n > 0 ? 'inline' : 'none';
      }}
      if (btnCopyPlan) {{
        btnCopyPlan.style.display = n > 0 ? 'inline-flex' : 'none';
      }}
      updateScheduleBar();
      if (quickActiveGenreChip && activeGenreLabel) {{
        if (activeGenre !== 'all' && GENRES_DATA && GENRES_DATA[activeGenre]) {{
          const gi = GENRES_DATA[activeGenre];
          activeGenreLabel.textContent = gi.label;
          quickActiveGenreChip.style.display = 'inline-flex';
        }} else {{
          quickActiveGenreChip.style.display = 'none';
        }}
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
          chip.classList.toggle('active', checkedCities.length === 1 && checkedCities[0] === city && activeTransit === 'all');
        }}
      }});
      transitChips.forEach(chip => {{
        chip.classList.toggle('active', chip.dataset.transit === activeTransit);
      }});
      if (checkedCities.length === 1 && activeTransit === 'all') {{
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
      const isCatFiltered = Array.from(catBoxes).some(b => defaultUncheckedCats.has(b.value) ? b.checked : !b.checked);
      const allGenres = genreBoxes.length;
      const chkGenres = Array.from(genreBoxes).filter(b => b.checked).length;
      const allVenues = venueBoxes.length;
      const chkVenues = Array.from(venueBoxes).filter(b => b.checked).length;
      const allCities = cityBoxes.length;
      const chkCities = Array.from(cityBoxes).filter(b => b.checked).length;
      const allRecurs = recurBoxes.length;
      const chkRecurs = Array.from(recurBoxes).filter(b => b.checked).length;
      const isFree = freeOnlyChk && freeOnlyChk.checked;
      const isLgbtq = lgbtqOnlyChk && lgbtqOnlyChk.checked;
      const isTimeFiltered = (timeFrom !== null || timeTo !== null);
      const isFiltered = isCatFiltered || (chkGenres < allGenres) || (activeGenre !== 'all') || (chkVenues < allVenues) || (chkCities < allCities) || (chkRecurs < allRecurs) || isFree || isLgbtq || popularOnly || starredOnly || (activeTransit !== 'all') || isTimeFiltered || (activeSubarea !== 'all') || (searchInput && !!searchInput.value.trim());

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

      const isCatFiltered = Array.from(catBoxes).some(b => defaultUncheckedCats.has(b.value) ? b.checked : !b.checked);
      if (isCatFiltered) {{
        const allChecked = Array.from(catBoxes).every(b => b.checked);
        if (allChecked) {{
          params.set('cat', 'all');
        }} else {{
          const checkedCats = Array.from(catBoxes).filter(b => b.checked).map(b => b.value);
          if (checkedCats.length > 0) {{
            params.set('cat', checkedCats.join(','));
          }} else {{
            params.set('cat', 'none');
          }}
        }}
      }}

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

      if (timeFrom !== null || timeTo !== null) {{
        if (timeFrom !== null) params.set('from', formatMinutesToHHMM(timeFrom));
        if (timeTo !== null) params.set('to', formatMinutesToHHMM(timeTo));
      }}

      const allRecurs = Array.from(recurBoxes).map(b => b.value);
      const checkedRecurs = Array.from(recurBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedRecurs.length > 0 && checkedRecurs.length < allRecurs.length) params.set('recur', checkedRecurs.join(','));

      const allVenues = Array.from(venueBoxes).map(b => b.value);
      const checkedVenues = Array.from(venueBoxes).filter(b => b.checked).map(b => b.value);
      if (checkedVenues.length > 0 && checkedVenues.length < allVenues.length) params.set('venues', checkedVenues.join(';'));

      if (freeOnlyChk && freeOnlyChk.checked) params.set('free', '1');
      if (lgbtqOnlyChk && lgbtqOnlyChk.checked) params.set('lgbtq', '1');
      if (popularOnly) params.set('pop', '1');
      if (featuredOnly) params.set('picks', '1');
      if (starredOnly) params.set('saved', '1');

      if (timeFilter !== 'today') params.set('t', timeFilter);
      if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        params.set('d', rangeStart);
        params.set('d_end', rangeEnd);
      }} else if ((timeFilter === 'day' || timeFilter === 'week') && fmtISO(anchor) !== todayISO) {{
        params.set('d', fmtISO(anchor));
      }}
      if (mapOpen) params.set('map', '1');
      if (nearMeActive && pinCoords) params.set('pin', `${{pinCoords.lat}},${{pinCoords.lng}}`);
      else if (nearMeActive) params.set('near', '1');
      if (showPastToday) params.set('past', '1');

      const hash = params.toString();
      history.replaceState(null, '', hash ? '#' + hash : location.pathname + location.search);
    }}

    let hashTimer = null;
    function scheduleStateToHash() {{
      if (hashTimer) clearTimeout(hashTimer);
      hashTimer = setTimeout(stateToHash, 150);
    }}

    function hashToState() {{
      const searchStr = location.search ? location.search.slice(1) : '';
      const hashStr = location.hash ? location.hash.slice(1) : '';
      const sParams = searchStr ? new URLSearchParams(searchStr) : null;
      const hParams = hashStr ? new URLSearchParams(hashStr) : null;

      const getParam = (k) => (hParams && hParams.get(k)) || (sParams && sParams.get(k));
      const hasParam = (k) => (hParams && hParams.has(k)) || (sParams && sParams.has(k));

      if (hParams || sParams) {{
        if (hasParam('q')) searchInput.value = getParam('q');
        if (getParam('free') === '1' && freeOnlyChk) freeOnlyChk.checked = true;
        if (getParam('lgbtq') === '1' && lgbtqOnlyChk) lgbtqOnlyChk.checked = true;
        if (getParam('pop') === '1') popularOnly = true;
        if (getParam('picks') === '1') featuredOnly = true;
        if (getParam('saved') === '1') {{
          starredOnly = true;
          if (savedOnlyChk) savedOnlyChk.checked = true;
        }}
        if (getParam('past') === '1') showPastToday = true;
        if (getParam('v') === 'map' || getParam('map') === '1') {{
          toggleMap(true);
        }}
        const pinParam = hasParam('pin') ? getParam('pin').split(',').map(Number) : null;
        if (pinParam && pinParam.length === 2 && pinParam.every(n => isFinite(n)) &&
            Math.abs(pinParam[0]) <= 90 && Math.abs(pinParam[1]) <= 180) {{
          pinCoords = {{ lat: pinParam[0], lng: pinParam[1] }};
          setNearMe(true);
        }} else if (getParam('near') === '1') {{
          toggleNearMe();
        }}

        if (hasParam('t')) {{
          timeFilter = getParam('t');
          showAll = (timeFilter === 'all');
        }}

        if (hasParam('cat')) {{
          const catVal = getParam('cat');
          if (catVal === 'all') {{
            catBoxes.forEach(b => {{ b.checked = true; }});
          }} else if (catVal === 'none') {{
            catBoxes.forEach(b => {{ b.checked = false; }});
          }} else {{
            const vals = new Set(catVal.split(','));
            catBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          }}
        }}

        if (hasParam('genre')) {{
          const gVal = getParam('genre');
          if (gVal.includes(',')) {{
            const vals = new Set(gVal.split(','));
            genreBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          }} else if (GENRES_DATA && GENRES_DATA[gVal]) {{
            activeGenre = gVal;
            genreBoxes.forEach(b => {{ b.checked = (b.value === gVal); }});
          }}
        }}

        if (hasParam('city')) {{
          const vals = new Set(getParam('city').split(','));
          cityBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (hasParam('sub')) {{
          activeSubarea = getParam('sub');
        }} else {{
          activeSubarea = 'all';
        }}

        if (hasParam('line')) {{
          activeTransit = getParam('line');
        }} else {{
          activeTransit = 'all';
        }}

        if (hasParam('from') || hasParam('tfrom') || hasParam('to') || hasParam('tto')) {{
          const f = getParam('from') || getParam('tfrom');
          const t = getParam('to') || getParam('tto');
          setTimeRange(f, t, true);
        }} else {{
          setTimeRange(null, null, true);
        }}

        if (hasParam('recur')) {{
          const vals = new Set(getParam('recur').split(','));
          recurBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
        }}

        if (hasParam('venues')) {{
          const rawVenues = getParam('venues').split(';').map(s => s.trim()).filter(Boolean);
          const vals = new Set(rawVenues);
          venueBoxes.forEach(b => {{ b.checked = vals.has(b.value); }});
          try {{
            localStorage.setItem('boston_saved_venues', JSON.stringify(Array.from(vals)));
          }} catch (_) {{}}
        }}

        if (hasParam('d')) {{
          const d = getParam('d');
          if (d === 'all') {{
            showAll = true;
            timeFilter = 'all';
          }} else if (hasParam('d_end')) {{
            rangeStart = d;
            rangeEnd = getParam('d_end');
            timeFilter = 'range';
            showAll = false;
            anchor = parseISO(rangeStart);
            calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
          }} else {{
            anchor = parseISO(d);
            calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
            if (!hasParam('t')) {{
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

      if ((!hParams && !sParams) || (!hasParam('venues'))) {{
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
      const lgbtqOnly = lgbtqOnlyChk ? lgbtqOnlyChk.checked : false;
      const week = new Set(weekDates());

      const todayDate = parseISO(todayISO);
      const dayOfWeek = todayDate.getDay();
      let daysToSat = (6 - dayOfWeek + 7) % 7;
      if (dayOfWeek === 0) daysToSat = -1;
      const satISO = fmtISO(addDays(todayDate, daysToSat));
      const sunISO = fmtISO(addDays(todayDate, daysToSat + 1));
      const tomorrowISO = fmtISO(addDays(todayDate, 1));
      const anchorISO = fmtISO(anchor);

      // Load the later days this view needs. Until they arrive, "Loading events…" replaces
      // "No events found".
      let viewLoading = false;
      const needsAllDays = timeFilter === 'all' || showAll || searchText.length > 0 ||
        (timeFilter === 'range' && rangeStart && rangeEnd) ||
        (starredOnly && Array.from(starredEvents).some(id => !document.querySelector(`.event[data-id="${{id}}"]`)));
      if (needsAllDays) {{
        if (!deferredHydrated) {{
          ensureDeferredDaysHydrated();
          viewLoading = true;
        }}
      }} else if (!deferredHydrated) {{
        let viewDates = [todayISO];
        if (timeFilter === 'week') viewDates = Array.from(week);
        else if (timeFilter === 'day') viewDates = [anchorISO];
        else if (timeFilter === 'tomorrow') viewDates = [tomorrowISO];
        else if (timeFilter === 'weekend') viewDates = [satISO, sunISO];
        const missing = viewDates.filter(d => DEFERRED_DATES.has(d) && !hasDay(d));
        if (missing.length) {{
          loadDays(missing);
          viewLoading = true;
        }}
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
        }} else if (timeFilter === 'range' && rangeStart && rangeEnd) {{
          inTime = (date >= rangeStart && date <= rangeEnd);
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
        let dayVisible = 0;

        const citySections = day._citySections || (day._citySections = Array.from(day.querySelectorAll('.city-section')));
        citySections.forEach(sec => {{
          const cCity = sec.getAttribute('data-city') || '';
          if (!cities.has(cCity)) {{
            sec.classList.add('empty');
            const cCount = sec.querySelector('.city-head .count');
            if (cCount && cCount._val !== 0) {{ cCount._val = 0; cCount.textContent = '0'; }}
            return;
          }}

          let cityVisible = 0;
          const buckets = sec._buckets || (sec._buckets = Array.from(sec.querySelectorAll('.bucket')));
          buckets.forEach(b => {{
            const bCat = b.getAttribute('data-bucket') || '';
            if (!cats.has(bCat)) {{
              b.classList.add('empty');
              const bCount = b.querySelector('.bucket-head .count');
              if (bCount && bCount._val !== 0) {{ bCount._val = 0; bCount.textContent = '0'; }}
              return;
            }}

            let bucketVisible = 0;
            const events = b._events || (b._events = Array.from(b.querySelectorAll('.event')));
            events.forEach(li => {{
              let m = li._meta;
              if (!m) {{
                const tm = li.getAttribute('data-time-mins');
                const ep = li.getAttribute('data-epoch');
                const vt = li.getAttribute('data-votes');
                m = {{
                  venue: li.getAttribute('data-venue') || '',
                  recur: li.getAttribute('data-recur') || '',
                  subarea: li.getAttribute('data-subarea') || 'all',
                  transit: li.getAttribute('data-transit') || '',
                  timeMins: tm ? parseInt(tm, 10) : -1,
                  free: li.getAttribute('data-free') === 'true',
                  lgbtq: li.getAttribute('data-lgbtq') === 'true',
                  votes: vt ? parseInt(vt, 10) : 0,
                  id: li.getAttribute('data-id') || li.getAttribute('data-event-id') || '',
                  genre: li.getAttribute('data-genre') || '',
                  epoch: ep ? parseInt(ep, 10) : 0,
                  endEpoch: parseInt(li.getAttribute('data-end-epoch') || '0', 10),
                  featured: li.classList.contains('highlighted'),
                  text: null,
                  hidden: false,
                }};
                li._meta = m;
              }}

              const venueOk = venues.has(m.venue);
              const recurOk = recurs.has(m.recur);
              const subareaOk = (activeSubarea === 'all') || (m.subarea === activeSubarea);
              const transitOk = (activeTransit === 'all') || (m.transit.indexOf(activeTransit) !== -1);
              let todOk = true;
              if (timeFrom !== null || timeTo !== null) {{
                if (m.timeMins >= 0) {{
                  if (timeFrom !== null && timeTo !== null) {{
                    if (timeTo > 1440) {{
                      todOk = (m.timeMins >= timeFrom && m.timeMins <= 1440) || (m.timeMins >= 0 && m.timeMins <= (timeTo - 1440));
                    }} else if (timeFrom > timeTo) {{
                      todOk = (m.timeMins >= timeFrom) || (m.timeMins <= timeTo);
                    }} else {{
                      todOk = (m.timeMins >= timeFrom && m.timeMins <= timeTo);
                    }}
                  }} else if (timeFrom !== null) {{
                    todOk = (m.timeMins >= timeFrom);
                  }} else if (timeTo !== null) {{
                    todOk = (m.timeMins <= timeTo);
                  }}
                }} else {{
                  todOk = false;
                }}
              }}
              const freeOk = !freeOnly || m.free;
              const lgbtqOk = !lgbtqOnly || m.lgbtq;
              const popularOk = !popularOnly || m.votes >= 3;
              const starredOk = !starredOnly || starredEvents.has(m.id);
              const searchOk = !searchText || (m.text || (m.text = li.textContent.toLowerCase())).includes(searchText);

              const isMusicEv = bCat === 'Music & nightlife' || !!m.genre;
              let genreOk = true;
              if (activeGenre !== 'all') {{
                genreOk = (m.genre === activeGenre);
              }} else if (isMusicEv && m.genre) {{
                genreOk = checkedGenres.has(m.genre);
              }}

              // Over once it ends; with no (believable) end time, two hours after it starts.
              const isPastTime = isToday && m.epoch > 0 &&
                (m.endEpoch > 0 ? m.endEpoch <= nowEpoch : m.epoch < twoHoursAgoEpoch);
              const isPast = isPastDay || isPastTime;

              if (isToday && m.epoch > 0) {{
                totalTodayEventsCount++;
              }}

              let timePastOk = true;
              if (isPast) {{
                if (!showPastToday) {{
                  timePastOk = false;
                  hiddenPastCount++;
                }}
              }}

              const featuredOk = !featuredOnly || m.featured;
              const isVisible = genreOk && venueOk && recurOk && subareaOk && transitOk && todOk && searchOk && freeOk && lgbtqOk && timePastOk && popularOk && starredOk && featuredOk;

              const isHidden = !isVisible;
              if (m.hidden !== isHidden) {{
                m.hidden = isHidden;
                li.classList.toggle('hidden', isHidden);
              }}

              if (isVisible) {{
                bucketVisible++;
                if (isToday && !isPast) visibleTonightCount++;
              }}
            }});

            b.classList.toggle('empty', bucketVisible === 0);
            const bCount = b.querySelector('.bucket-head .count');
            if (bCount && bCount._val !== bucketVisible) {{
              bCount._val = bucketVisible;
              bCount.textContent = bucketVisible;
            }}
            cityVisible += bucketVisible;
          }});

          sec.classList.toggle('empty', cityVisible === 0);
          const cCount = sec.querySelector('.city-head .count');
          if (cCount && cCount._val !== cityVisible) {{
            cCount._val = cityVisible;
            cCount.textContent = cityVisible;
          }}
          dayVisible += cityVisible;
        }});

        day.classList.toggle('empty', dayVisible === 0);
        const headingCount = day.querySelector('h2 .count');
        if (headingCount && headingCount._val !== dayVisible) {{
          headingCount._val = dayVisible;
          headingCount.textContent = dayVisible;
        }}

        const origin = nearMeActive ? nearOrigin() : null;
        if (origin) {{
          const nearStream = day.querySelector('.near-me-stream');
          const citiesDiv = day.querySelector('.cities');
          if (nearStream && citiesDiv) {{
            citiesDiv.style.display = 'none';
            nearStream.style.display = 'block';

            // The distance-sorted copy of this day is built once per origin (Near Me position or
            // pin); filter changes after that only show/hide its rows instead of re-measuring,
            // re-sorting and re-cloning every event.
            const allEvents = citiesDiv.querySelectorAll('.event');
            const originKey = `${{origin.lat}},${{origin.lng}}`;
            let near = day._nearCache;
            if (!near || near.key !== originKey || near.count !== allEvents.length || !nearStream.contains(near.list)) {{
              const eventDistances = [];
              allEvents.forEach(ev => {{
                const lat = parseFloat(ev.dataset.lat);
                const lng = parseFloat(ev.dataset.lng);
                let dist = 99999;
                if (!isNaN(lat) && !isNaN(lng)) {{
                  dist = haversineMiles(origin.lat, origin.lng, lat, lng);
                }}
                const timeMins = parseInt(ev.dataset.timeMins || '9999', 10);
                eventDistances.push({{ ev: ev, dist: dist, timeMins: timeMins, clone: null }});
              }});
              eventDistances.sort((a, b) => {{
                if (a.dist !== b.dist) return a.dist - b.dist;
                return a.timeMins - b.timeMins;
              }});
              near = day._nearCache = {{ key: originKey, count: allEvents.length, items: eventDistances, list: null }};
            }}

            // Unchecked cities/categories collapse their section (.empty) without hiding each event
            let locatedCount = 0;
            near.items.forEach(item => {{
              item.show = !item.ev.classList.contains('hidden') && !item.ev.closest('.empty');
              if (item.show && item.dist < 9999) locatedCount++;
            }});
            let banner = nearStream.querySelector('.near-stream-banner');
            if (!banner) {{
              banner = document.createElement('div');
              banner.className = 'near-stream-banner';
              nearStream.appendChild(banner);
            }}
            const fromPin = origin.kind === 'pin';
            banner.innerHTML = `
              <div class="near-stream-info">
                <span class="chip-icon">${{fromPin ? '📌' : '📍'}} </span>
                <span><strong>Sorted by distance from ${{fromPin ? 'your pin' : 'your location'}}</strong> (${{locatedCount}} events nearby)</span>
              </div>
              <div class="near-stream-actions">
                ${{fromPin ? '<button type="button" class="near-stream-clear-btn" id="btn-move-pin">Move Pin</button>' : ''}}
                <button type="button" class="near-stream-clear-btn" id="btn-reset-near">Reset to Category View</button>
              </div>
            `;

            if (!near.list) {{
              let list = nearStream.querySelector('.near-events-list');
              if (!list) {{
                list = document.createElement('ul');
                list.className = 'near-events-list';
                nearStream.appendChild(list);
              }}
              list.innerHTML = '';
              const frag = document.createDocumentFragment();
              near.items.forEach(item => {{
                const clone = item.ev.cloneNode(true);
                clone.classList.remove('hidden');
                if (item.dist < 9999) {{
                  const away = origin.kind === 'pin' ? 'from pin' : 'away';
                  const dStr = item.dist < 0.1 ? `< 0.1 mi ${{away}}` : `${{item.dist.toFixed(1)}} mi ${{away}}`;
                  let badge = clone.querySelector('.dist-badge');
                  if (!badge) {{
                    badge = document.createElement('span');
                    badge.className = 'dist-badge';
                    const vTag = clone.querySelector('.venue-tag');
                    if (vTag) vTag.appendChild(badge);
                  }}
                  badge.title = `${{item.dist.toFixed(2)}} miles ${{away}}`;
                  badge.innerHTML = `<span class="chip-icon">📍 </span>${{dStr}}`;
                }}
                item.clone = clone;
                frag.appendChild(clone);
              }});
              list.appendChild(frag);
              near.list = list;
            }}
            near.items.forEach(item => {{
              if (item.clone.classList.contains('hidden') === item.show) item.clone.classList.toggle('hidden', !item.show);
            }});
          }}
        }}
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
        noEventsEl.style.display = (visibleDays === 0 && !viewLoading) ? 'block' : 'none';
      }}
      const daysLoadingEl = document.getElementById('days-loading');
      if (daysLoadingEl) {{
        daysLoadingEl.style.display = viewLoading ? 'block' : 'none';
      }}

      renderCal();
      updateWeekLabel();
      if (activeGenre !== 'all') {{
        activeDays.forEach(day => {{
          day.querySelectorAll('.genre-pill').forEach(p => {{
            p.classList.toggle('genre-pill-active', p.dataset.genre === activeGenre);
          }});
        }});
      }} else {{
        const activePills = document.querySelectorAll('.genre-pill-active');
        if (activePills.length > 0) activePills.forEach(p => p.classList.remove('genre-pill-active'));
      }}
      updateQuickChipsUI();
      updateLocChipsUI();
      updateSearchUI();
      updateMobileBadge();
      if (mapOpen || currentView === 'map') {{
        updateMapMarkers();
      }}
      scheduleStateToHash();
    }}

    function renderCal() {{
      const cal = document.getElementById('mini-cal');
      if (cal && cal.hasAttribute('hidden')) return;
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

        if (timeFilter === 'range' && rangeStart && rangeEnd) {{
          if (iso === rangeStart) classes.push('range-start', 'anchor');
          else if (iso === rangeEnd) classes.push('range-end', 'anchor');
          else if (iso > rangeStart && iso < rangeEnd) classes.push('in-range');
        }} else if (rangeStart && !rangeEnd) {{
          if (iso === rangeStart) classes.push('range-start', 'anchor');
        }} else {{
          if (!showAll && timeFilter === 'week' && week.has(iso)) classes.push('in-week');
          if (iso === fmtISO(anchor)) classes.push('anchor');
        }}
        html += `<div class="${{classes.join(' ')}}" data-date="${{iso}}">${{d}}</div>`;
      }}
      grid.innerHTML = html;

      const hintEl = document.getElementById('cal-hint');
      if (hintEl) {{
        if (timeFilter === 'range' && rangeStart && rangeEnd) {{
          const s = parseISO(rangeStart), e = parseISO(rangeEnd);
          hintEl.textContent = `Range: ${{fmtShort(s)}} – ${{fmtShort(e)}} (click any date to start new range)`;
        }} else if (rangeStart && !rangeEnd) {{
          const s = parseISO(rangeStart);
          hintEl.textContent = `Selected ${{fmtShort(s)}} — click a 2nd date to set range`;
        }} else {{
          hintEl.textContent = 'Select a date, or click a 2nd date to pick a range';
        }}
      }}
    }}

    function shiftNav(delta) {{
      if (timeFilter === 'range' && rangeStart && rangeEnd) {{
        const s = parseISO(rangeStart);
        const e = parseISO(rangeEnd);
        const diffDays = Math.max(1, Math.round((e - s) / 86400000) + 1);
        rangeStart = fmtISO(addDays(s, delta * diffDays));
        rangeEnd = fmtISO(addDays(e, delta * diffDays));
        anchor = parseISO(rangeStart);
      }} else if (timeFilter === 'week') {{
        rangeStart = null; rangeEnd = null;
        anchor = addDays(anchor, delta * 7);
      }} else if (timeFilter === 'today' || timeFilter === 'tomorrow' || timeFilter === 'day') {{
        anchor = addDays(anchor, delta);
        const iso = fmtISO(anchor);
        rangeStart = iso; rangeEnd = null;
        if (iso === todayISO) {{
          timeFilter = 'today';
        }} else if (iso === fmtISO(addDays(parseISO(todayISO), 1))) {{
          timeFilter = 'tomorrow';
        }} else {{
          timeFilter = 'day';
        }}
      }} else if (timeFilter === 'weekend') {{
        rangeStart = null; rangeEnd = null;
        anchor = addDays(anchor, delta * 7);
      }} else {{
        // 'all'
        anchor = addDays(parseISO(todayISO), delta > 0 ? 1 : 0);
        const iso = fmtISO(anchor);
        rangeStart = iso; rangeEnd = null;
        timeFilter = (iso === todayISO) ? 'today' : (iso === fmtISO(addDays(parseISO(todayISO), 1)) ? 'tomorrow' : 'day');
      }}
      showAll = false;
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }}

    function setAnchor(iso) {{
      rangeStart = iso;
      rangeEnd = null;
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
      }});
    }}
    if (mobileClose && sidebarFilters) {{
      mobileClose.addEventListener('click', () => {{
        sidebarFilters.classList.remove('mobile-open');
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
      rangeStart = null;
      rangeEnd = null;
      showAll = false;
      anchor = parseISO(todayISO);
      calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
      apply();
    }});
    const weekAllBtn = document.getElementById('week-all');
    if (weekAllBtn) {{
      weekAllBtn.addEventListener('click', () => {{
        if (showAll || timeFilter === 'all') {{
          showAll = false;
          timeFilter = 'today';
          rangeStart = null;
          rangeEnd = null;
          anchor = parseISO(todayISO);
        }} else {{
          showAll = true;
          timeFilter = 'all';
          rangeStart = null;
          rangeEnd = null;
        }}
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}

    const noEventsWeek = document.getElementById('no-events-week-btn');
    if (noEventsWeek) {{
      noEventsWeek.addEventListener('click', () => {{
        timeFilter = 'week';
        rangeStart = null;
        rangeEnd = null;
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
        rangeStart = null;
        rangeEnd = null;
        showAll = true;
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
      }});
    }}
    document.getElementById('cal-toggle').addEventListener('click', (e) => {{
      const cal = document.getElementById('mini-cal');
      const open = cal.hasAttribute('hidden');
      if (open) {{
        cal.removeAttribute('hidden');
        renderCal();
      }} else {{
        cal.setAttribute('hidden', '');
      }}
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
      const clicked = cell.dataset.date;
      if (!rangeStart || (rangeStart && rangeEnd)) {{
        rangeStart = clicked;
        rangeEnd = null;
        setAnchor(rangeStart);
      }} else if (rangeStart && !rangeEnd) {{
        if (clicked === rangeStart) {{
          rangeEnd = null;
          timeFilter = (rangeStart === todayISO) ? 'today' : (rangeStart === fmtISO(addDays(parseISO(todayISO), 1)) ? 'tomorrow' : 'day');
          apply();
        }} else {{
          if (clicked < rangeStart) {{
            rangeEnd = rangeStart;
            rangeStart = clicked;
          }} else {{
            rangeEnd = clicked;
          }}
          timeFilter = 'range';
          showAll = false;
          anchor = parseISO(rangeStart);
          apply();
        }}
      }}
    }});

    if (freeOnlyChk) freeOnlyChk.addEventListener('change', apply);
    if (lgbtqOnlyChk) lgbtqOnlyChk.addEventListener('change', apply);
    catBoxes.forEach(b => b.addEventListener('change', () => {{
      if (b.value === 'Music & nightlife') {{
        const musicChecked = b.checked;
        genreBoxes.forEach(gb => {{ gb.checked = musicChecked; }});
        const subContainer = document.getElementById('subgenre-container');
        if (subContainer) subContainer.classList.toggle('disabled', !musicChecked);
      }}
      apply();
    }}));
    genreBoxes.forEach(b => b.addEventListener('change', () => {{
      activeGenre = 'all';
      const anyChecked = Array.from(genreBoxes).some(gb => gb.checked);
      if (anyChecked) {{
        catBoxes.forEach(cb => {{
          if (cb.value === 'Music & nightlife') cb.checked = true;
        }});
        const subContainer = document.getElementById('subgenre-container');
        if (subContainer) subContainer.classList.remove('disabled');
      }}
      apply();
      stateToHash();
    }}));
    function saveVenuesState() {{
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
    }}
    venueBoxes.forEach(b => b.addEventListener('change', () => {{
      saveVenuesState();
      apply();
    }}));
    recurBoxes.forEach(b => b.addEventListener('change', apply));
    cityBoxes.forEach(b => b.addEventListener('change', apply));
    searchInput.addEventListener('input', apply);
    document.getElementById('cat-all').addEventListener('click', () => {{
      catBoxes.forEach(b => b.checked = true);
      genreBoxes.forEach(b => b.checked = true);
      const subContainer = document.getElementById('subgenre-container');
      if (subContainer) subContainer.classList.remove('disabled');
      apply();
    }});
    document.getElementById('cat-none').addEventListener('click', () => {{
      catBoxes.forEach(b => b.checked = false);
      genreBoxes.forEach(b => b.checked = false);
      const subContainer = document.getElementById('subgenre-container');
      if (subContainer) subContainer.classList.add('disabled');
      apply();
    }});
    const genreAllBtn = document.getElementById('genre-all');
    if (genreAllBtn) genreAllBtn.addEventListener('click', () => {{
      catBoxes.forEach(cb => {{
        if (cb.value === 'Music & nightlife') cb.checked = true;
      }});
      genreBoxes.forEach(b => b.checked = true);
      activeGenre = 'all';
      const subContainer = document.getElementById('subgenre-container');
      if (subContainer) subContainer.classList.remove('disabled');
      apply();
      stateToHash();
    }});
    const genreNoneBtn = document.getElementById('genre-none');
    if (genreNoneBtn) genreNoneBtn.addEventListener('click', () => {{
      genreBoxes.forEach(b => b.checked = false);
      activeGenre = 'all';
      apply();
      stateToHash();
    }});
    document.getElementById('venue-all').addEventListener('click', () => {{
      venueBoxes.forEach(b => b.checked = true);
      try {{ localStorage.removeItem('boston_saved_venues'); }} catch (_) {{}}
      apply();
    }});
    document.getElementById('venue-none').addEventListener('click', () => {{ venueBoxes.forEach(b => b.checked = false); saveVenuesState(); apply(); }});
    document.getElementById('city-all').addEventListener('click', () => {{ activeSubarea = 'all'; activeTransit = 'all'; cityBoxes.forEach(b => b.checked = true); apply(); }});
    document.getElementById('city-none').addEventListener('click', () => {{ activeSubarea = 'all'; activeTransit = 'all'; cityBoxes.forEach(b => b.checked = false); apply(); }});

    function setGenre(genre) {{
      if (activeGenre === genre) {{
        activeGenre = 'all';
      }} else {{
        activeGenre = genre;
      }}
      if (activeGenre === 'all') {{
        genreBoxes.forEach(b => {{ b.checked = true; }});
      }} else {{
        catBoxes.forEach(cb => {{
          if (cb.value === 'Music & nightlife') cb.checked = true;
        }});
        const subContainer = document.getElementById('subgenre-container');
        if (subContainer) subContainer.classList.remove('disabled');
        genreBoxes.forEach(b => {{ b.checked = (b.value === activeGenre); }});
      }}
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

    if (quickActiveGenreChip) {{
      quickActiveGenreChip.addEventListener('click', () => {{
        setGenre('all');
      }});
    }}

    document.addEventListener('click', (e) => {{
      const pill = e.target.closest('.genre-pill');
      if (pill && pill.dataset.genre) {{
        e.preventDefault();
        e.stopPropagation();
        setGenre(pill.dataset.genre);
      }}
    }});

    function resetAllFilters() {{
      if (searchInput) searchInput.value = '';
      if (freeOnlyChk) freeOnlyChk.checked = false;
      if (lgbtqOnlyChk) lgbtqOnlyChk.checked = false;
      popularOnly = false;
      featuredOnly = false;
      starredOnly = false;
      if (savedOnlyChk) savedOnlyChk.checked = false;
      activeSubarea = 'all';
      activeTransit = 'all';
      timeFrom = null;
      timeTo = null;
      if (timeframeEnableChk) timeframeEnableChk.checked = false;
      if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
      updateTimeUI();
      activeGenre = 'all';
      genreBoxes.forEach(b => b.checked = true);
      catBoxes.forEach(b => b.checked = !defaultUncheckedCats.has(b.value));
      const subContainer = document.getElementById('subgenre-container');
      if (subContainer) subContainer.classList.remove('disabled');
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
        activeTransit = 'all';
        if (targetCity === 'all') {{
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
        if (activeTransit === line) {{
          activeTransit = 'all';
        }} else {{
          activeTransit = line;
          activeSubarea = 'all';
          cityBoxes.forEach(b => {{ b.checked = true; }});
        }}
        apply();
      }});
    }});

    if (quickCustomTimeChip) {{
      quickCustomTimeChip.addEventListener('click', () => {{
        if (timeframeEnableChk) timeframeEnableChk.checked = false;
        if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
        setTimeRange(null, null);
      }});
    }}

    if (timeframeEnableChk) {{
      timeframeEnableChk.addEventListener('change', () => {{
        if (timeframeEnableChk.checked) {{
          if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'block';
          const f = (timeFromSelect && timeFromSelect.value) ? timeFromSelect.value : '20:00';
          const t = (timeToSelect && timeToSelect.value) ? timeToSelect.value : '24:00';
          setTimeRange(f, t);
        }} else {{
          if (customTimeRangeDiv) customTimeRangeDiv.style.display = 'none';
          setTimeRange(null, null);
        }}
      }});
    }}

    if (timeFromSelect) {{
      timeFromSelect.addEventListener('change', () => {{
        const f = timeFromSelect.value;
        const currentTo = timeToSelect ? timeToSelect.value : '24:00';
        syncToOptions(f, currentTo);
        const t = timeToSelect ? timeToSelect.value : '24:00';
        if (timeframeEnableChk) timeframeEnableChk.checked = true;
        setTimeRange(f, t);
      }});
    }}
    if (timeToSelect) {{
      timeToSelect.addEventListener('change', () => {{
        const f = timeFromSelect ? timeFromSelect.value : '20:00';
        const t = timeToSelect.value;
        if (timeframeEnableChk) timeframeEnableChk.checked = true;
        setTimeRange(f, t);
      }});
    }}

    if (quickFeaturedChip) {{
      quickFeaturedChip.addEventListener('click', () => {{
        featuredOnly = !featuredOnly;
        if (featuredOnly && timeFilter === 'today') {{
          timeFilter = 'all';
          showAll = true;
        }}
        apply();
      }});
    }}

    if (savedOnlyChk) {{
      savedOnlyChk.addEventListener('change', () => {{
        starredOnly = savedOnlyChk.checked;
        if (starredOnly && timeFilter === 'today') {{
          timeFilter = 'all';
          showAll = true;
        }}
        apply();
      }});
    }}

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

    // My Schedule keeps an event for 24 hours after it starts
    function dropPastScheduleEvents() {{
      try {{
        const details = JSON.parse(localStorage.getItem('boston_schedule_events') || '{{}}');
        const cutoff = Math.floor(Date.now() / 1000) - 86400;
        const past = Object.keys(details).filter(id => Array.isArray(details[id]) && details[id][1] < cutoff);
        if (!past.length) return;
        past.forEach(id => {{ delete details[id]; starredEvents.delete(id); }});
        localStorage.setItem('boston_schedule_events', JSON.stringify(details));
        localStorage.setItem('boston_starred_events', JSON.stringify(Array.from(starredEvents)));
      }} catch (_) {{}}
    }}

    function loadStarredState() {{
      try {{
        const raw = JSON.parse(localStorage.getItem('boston_starred_events') || '[]');
        if (Array.isArray(raw)) starredEvents = new Set(raw);
      }} catch (_) {{}}
      dropPastScheduleEvents();
      if (!starredEvents || starredEvents.size === 0) return;
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
      rememberScheduleEvent(evId, nowStarred ? li : null);
      document.querySelectorAll(`.event[data-id="${{evId}}"] .star-btn`).forEach(b => {{
        b.classList.toggle('starred', nowStarred);
        b.textContent = nowStarred ? '★' : '☆';
        b.setAttribute('aria-pressed', nowStarred ? 'true' : 'false');
      }});
      if (starredOnly && starredEvents.size === 0) {{
        starredOnly = false;
        if (savedOnlyChk) savedOnlyChk.checked = false;
      }}
      updateQuickChipsUI();
      if (starredOnly) apply();
    }});

    // My Schedule. Sharing saves the list and gives a short link (schedule-worker/). If that isn't
    // available, the event details go in a long link instead, which needs no server.
    const scheduleModal = document.getElementById('schedule-share-modal');
    const scheduleName = document.getElementById('schedule-share-name');
    const scheduleLink = document.getElementById('schedule-share-link');
    const scheduleSub = document.getElementById('schedule-share-sub');
    const scheduleCopy = document.getElementById('schedule-share-copy');
    const scheduleSend = document.getElementById('schedule-share-send');
    const scheduleOpen = document.getElementById('schedule-share-open');
    const SCHEDULE_DETAILS_KEY = 'boston_schedule_events';
    const SCHEDULE_NAME_KEY = 'boston_schedule_name';
    let scheduleEvents = [];
    let scheduleLinkRun = 0;
    let scheduleNameTimer = null;

    function updateScheduleBar() {{
      if (!scheduleBar) return;
      const n = starredEvents ? starredEvents.size : 0;
      scheduleBar.style.display = n > 0 ? 'flex' : 'none';
      scheduleCount.textContent = n > 0 ? `(${{n}})` : '';
      scheduleView.setAttribute('aria-pressed', starredOnly ? 'true' : 'false');
    }}

    function scheduleDetails() {{
      try {{
        const d = JSON.parse(localStorage.getItem(SCHEDULE_DETAILS_KEY) || '{{}}');
        return (d && typeof d === 'object') ? d : {{}};
      }} catch (_) {{ return {{}}; }}
    }}

    function scheduleRow(li) {{
      const m = extractEventMetaFromLi(li);
      if (!m.dt || isNaN(m.dt.getTime())) return null;
      // The last field marks a listing with a date but no time, so it isn't shown at a made-up hour
      return [m.title, Math.floor(m.dt.getTime() / 1000), m.venue, m.url, li.dataset.epoch ? 0 : 1];
    }}

    function rememberScheduleEvent(id, li) {{
      const d = scheduleDetails();
      const row = li ? scheduleRow(li) : null;
      if (row) d[id] = row; else delete d[id];
      try {{ localStorage.setItem(SCHEDULE_DETAILS_KEY, JSON.stringify(d)); }} catch (_) {{}}
    }}

    async function encodeSchedule(obj) {{
      let bytes = new TextEncoder().encode(JSON.stringify(obj));
      let tag = 'j';
      if (window.CompressionStream) {{
        try {{
          const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream('deflate-raw'));
          bytes = new Uint8Array(await new Response(stream).arrayBuffer());
          tag = 'z';
        }} catch (_) {{}}
      }}
      let bin = '';
      bytes.forEach(b => {{ bin += String.fromCharCode(b); }});
      return tag + btoa(bin).split('+').join('-').split('/').join('_').split('=').join('');
    }}

    async function refreshScheduleLink() {{
      const name = scheduleName.value.trim();
      try {{ localStorage.setItem(SCHEDULE_NAME_KEY, name); }} catch (_) {{}}
      const run = ++scheduleLinkRun;
      const schedule = {{ v: 1, n: name, e: scheduleEvents }};
      scheduleCopy.disabled = true;
      scheduleLink.value = '';
      scheduleLink.placeholder = 'Making your link...';
      const link = await shortScheduleLink(schedule) ||
        `${{location.origin}}/schedule/#${{await encodeSchedule(schedule)}}`;
      if (run !== scheduleLinkRun) return;   // the name changed while this one was being made
      scheduleLink.value = link;
      scheduleOpen.href = link;
      scheduleCopy.disabled = scheduleEvents.length === 0;
    }}

    async function shortScheduleLink(schedule) {{
      if (!schedule.e.length) return null;
      try {{
        const resp = await fetch('/api/schedule', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(schedule),
          signal: AbortSignal.timeout(4000),
        }});
        const url = resp.ok ? (await resp.json()).url : '';
        return String(url).startsWith(`${{location.origin}}/s/`) ? url : null;
      }} catch (_) {{ return null; }}
    }}

    function openScheduleShare() {{
      ensureDeferredDaysHydrated(async () => {{
        const saved = scheduleDetails();
        const rows = new Map();
        document.querySelectorAll('.event[data-id]').forEach(li => {{
          const id = li.dataset.id;
          if (starredEvents.has(id) && !rows.has(id)) {{
            const row = scheduleRow(li);
            if (row) rows.set(id, row);
          }}
        }});
        starredEvents.forEach(id => {{ if (!rows.has(id) && saved[id]) rows.set(id, saved[id]); }});
        const cutoff = Math.floor(Date.now() / 1000) - 86400;
        scheduleEvents = Array.from(rows.values()).filter(r => r[1] >= cutoff).sort((a, b) => a[1] - b[1]);
        const left = starredEvents.size - scheduleEvents.length;
        scheduleSub.textContent = `${{scheduleEvents.length}} upcoming ${{scheduleEvents.length === 1 ? 'event' : 'events'}}` +
          (left > 0 ? `. ${{left}} past or undated ${{left === 1 ? 'event is' : 'events are'}} left out.` : '.');
        try {{ scheduleName.value = localStorage.getItem(SCHEDULE_NAME_KEY) || ''; }} catch (_) {{}}
        scheduleSend.style.display = navigator.share ? 'inline-block' : 'none';
        scheduleModal.style.display = 'flex';
        await refreshScheduleLink();
        scheduleCopy.focus();
      }});
    }}

    function closeScheduleShare() {{
      scheduleModal.style.display = 'none';
    }}

    if (scheduleBar) {{
      scheduleView.addEventListener('click', () => {{
        starredOnly = !starredOnly;
        if (savedOnlyChk) savedOnlyChk.checked = starredOnly;
        if (starredOnly && timeFilter === 'today') {{
          timeFilter = 'all';
          showAll = true;
        }}
        apply();
        if (starredOnly) window.scrollTo({{ top: 0 }});
      }});
      document.getElementById('schedule-share').addEventListener('click', openScheduleShare);
      document.getElementById('schedule-share-close').addEventListener('click', closeScheduleShare);
      scheduleModal.addEventListener('click', e => {{ if (e.target === scheduleModal) closeScheduleShare(); }});
      document.addEventListener('keydown', e => {{
        if (e.key === 'Escape' && scheduleModal.style.display !== 'none') closeScheduleShare();
      }});
      scheduleName.addEventListener('input', () => {{
        // Wait for a pause in typing so each letter doesn't save a new schedule
        scheduleCopy.disabled = true;
        clearTimeout(scheduleNameTimer);
        scheduleNameTimer = setTimeout(refreshScheduleLink, 700);
      }});
      scheduleCopy.addEventListener('click', async () => {{
        try {{
          await navigator.clipboard.writeText(scheduleLink.value);
        }} catch (_) {{
          scheduleLink.select();
          document.execCommand('copy');
        }}
        scheduleCopy.textContent = 'Copied';
        setTimeout(() => {{ scheduleCopy.textContent = 'Copy link'; }}, 1500);
      }});
      scheduleSend.addEventListener('click', () => {{
        navigator.share({{ title: 'My schedule', url: scheduleLink.value }}).catch(() => {{}});
      }});
    }}

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
      const endEp = parseInt(li.dataset.endEpoch || '0', 10);
      const end = endEp > 0 && dt ? new Date(endEp * 1000) : (dt ? new Date(dt.getTime() + 2 * 3600 * 1000) : null);
      return {{ title, url, venue, city, dt, end }};
    }}

    function toCalUTC(d) {{
      function pad(n) {{ return n < 10 ? '0' + n : '' + n; }}
      return d.getUTCFullYear() + pad(d.getUTCMonth()+1) + pad(d.getUTCDate()) + 'T' +
             pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + pad(d.getUTCSeconds()) + 'Z';
    }}

    function downloadICS(title, dt, venue, url, endDt) {{
      if (!dt || isNaN(dt.getTime())) return;
      const start = toCalUTC(dt);
      const end = toCalUTC(endDt || new Date(dt.getTime() + 2 * 3600 * 1000));
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
        const end = toCalUTC(m.end);
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
      downloadICS(m.title, m.dt, m.venue, m.url, m.end);
    }});

    const btnViewList = document.getElementById('btn-view-list');
    if (btnViewList) {{
      btnViewList.addEventListener('click', () => {{
        if (nearMeActive) setNearMe(false);
      }});
    }}

    const btnNearMe = document.getElementById('btn-near-me');
    if (btnNearMe) {{
      btnNearMe.addEventListener('click', () => {{
        if (!nearMeActive || pinCoords) toggleNearMe();
      }});
    }}

    const btnDropPin = document.getElementById('btn-drop-pin');
    if (btnDropPin) {{
      btnDropPin.addEventListener('click', () => {{
        if (pinPlacing) cancelPinDrop();
        else startPinDrop();
      }});
    }}
    const pinCancelBtn = document.getElementById('pin-cancel-btn');
    if (pinCancelBtn) pinCancelBtn.addEventListener('click', cancelPinDrop);

    const btnViewMap = document.getElementById('btn-view-map');
    if (btnViewMap) {{
      btnViewMap.addEventListener('click', () => toggleMap());
    }}

    document.addEventListener('click', (e) => {{
      if (e.target && e.target.id === 'btn-reset-near') {{
        setNearMe(false);
      }}
      if (e.target && e.target.id === 'btn-move-pin') {{
        startPinDrop();
      }}
    }});

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
        toggleMap(true);
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
        rangeStart = null;
        rangeEnd = null;
        timeFilter = 'tomorrow';
        showAll = false;
        anchor = addDays(parseISO(todayISO), 1);
        calMonth = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
        apply();
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
        refreshIfStale(false);
        pageHiddenAt = null;
      }} else {{
        pageHiddenAt = Date.now();
      }}
    }});

    // Restored from the back/forward cache: no load event, and timers were frozen while away.
    window.addEventListener('pageshow', (ev) => {{
      if (ev.persisted) {{
        checkDayRollover();
        refreshIfStale(true);
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
    const THEME_MANUAL_KEY = 'boston_events_theme_manual';  // date (YYYY-MM-DD) of the visitor's last pick
    const validThemesAll = BASE_THEMES.concat(HOLIDAY_KEYS);
    function setTheme(t, save) {{
      const theme = validThemesAll.includes(t) ? t : 'classic';
      document.documentElement.setAttribute('data-theme', theme);
      document.querySelectorAll('.theme-pill-btn').forEach(b => {{
        const isActive = (b.dataset.theme === theme);
        b.classList.toggle('active', isActive);
        b.setAttribute('aria-checked', isActive ? 'true' : 'false');
      }});
      if (save !== false) {{
        try {{
          localStorage.setItem(THEME_KEY, theme);
          localStorage.setItem(THEME_MANUAL_KEY, localISODate(new Date()));
        }} catch (_) {{}}
      }}
    }}
    // The holiday pill: today's holiday (or a ?theme= holiday preview) gets a labeled button
    // at the front of the picker; hidden on ordinary days.
    (function () {{
      const btn = document.getElementById('theme-pill-holiday');
      if (!btn) return;
      const preview = new URLSearchParams(location.search).get('theme');
      const key = HOLIDAY_KEYS.includes(preview) ? preview : getClientSeasonalTheme(new Date());
      const meta = key && HOLIDAY_META[key];
      if (!meta) {{ btn.hidden = true; return; }}
      btn.dataset.theme = key;
      btn.title = meta.label + ' theme';
      btn.innerHTML = '<span class="holiday-pill-emoji">' + meta.emoji + '</span><span class="holiday-pill-label">' + meta.label + '</span>';
      btn.hidden = false;
    }})();
    document.querySelectorAll('.theme-pill-btn').forEach(btn => {{
      btn.addEventListener('click', () => setTheme(btn.dataset.theme, true));
    }});
    try {{
      setTheme(pickTheme(), false);
    }} catch (_) {{
      setTheme('{default_theme}', false);
    }}
    // Until the visitor picks a theme, follow their device when it switches light/dark (e.g. at sunset).
    try {{
      const schemeQuery = window.matchMedia('(prefers-color-scheme: light)');
      const followDevice = () => {{
        let picked = null;
        try {{ picked = localStorage.getItem(THEME_KEY); }} catch (_) {{}}
        if (!picked) setTheme(pickTheme(), false);
      }};
      if (schemeQuery.addEventListener) schemeQuery.addEventListener('change', followDevice);
      else if (schemeQuery.addListener) schemeQuery.addListener(followDevice);
    }} catch (_) {{}}

    loadUpvoteState();
    loadLocalCommunityEvents();
    syncInitialUpvotes();
    fetchLiveUpvotes();
    loadStarredState();
    initTimeDropdowns();
    hashToState();
    apply();

    window.addEventListener('beforeinstallprompt', function (e) {{
      e.preventDefault();
      window._pwaPrompt = e;
      var wrap = document.getElementById('pwa-install-wrap');
      if (wrap) wrap.hidden = false;
    }});
    window.installPWA = function () {{
      if (window._pwaPrompt) {{
        window._pwaPrompt.prompt();
        window._pwaPrompt.userChoice.finally(function () {{
          window._pwaPrompt = null;
          var wrap = document.getElementById('pwa-install-wrap');
          if (wrap) wrap.hidden = true;
        }});
      }}
    }};
  </script>
</body>
</html>"""
