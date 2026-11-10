"""College & student events: which listings count, and which school each belongs to.

An event is a college event when either
  1. it comes from a school's own calendar (campus calendars, athletics feeds, conservatory
     concert calendars), listed in COLLEGE_SOURCES with the school it belongs to, or
  2. an aggregator (Ticketmaster, Eventbrite, Luma...) lists it, its title names a school and
     the title reads as a game or a student ensemble ("Boston University Men's Hockey vs. Harvard",
     "MIT Concert Choir"), or it's a known intercollegiate event (Beanpot, HackMIT).

A venue on its own never makes an event a college event: Jordan Hall, Sanders Theatre, the
Berklee Performance Center, Agganis Arena and the Emerson Colonial host touring shows and
professional orchestras most nights. Venues are only used to tell which school an event belongs to.

Every school pattern is a word-boundary regex: #65 used substrings, so "bu" matched "Bully Boy",
"mit" matched "summit" and "nec" matched "connection".
"""
import re

# key -> (short badge label, full name). Order is the hub's School filter order.
COLLEGE_SCHOOLS = {
    "bu": ("BU", "Boston University"),
    "bc": ("BC", "Boston College"),
    "neu": ("Northeastern", "Northeastern University"),
    "harvard": ("Harvard", "Harvard University"),
    "mit": ("MIT", "MIT"),
    "tufts": ("Tufts", "Tufts University"),
    "berklee": ("Berklee", "Berklee College of Music"),
    "nec": ("NEC", "New England Conservatory"),
    "longy": ("Longy", "Longy School of Music"),
    "emerson": ("Emerson", "Emerson College"),
    "suffolk": ("Suffolk", "Suffolk University"),
    "brandeis": ("Brandeis", "Brandeis University"),
    "babson": ("Babson", "Babson College"),
    "umb": ("UMass Boston", "UMass Boston"),
}
GENERIC_SCHOOL = ("College", "College & student")

# The schools' own calendars. Every event they list is a college event.
# Not here on purpose: Harvard Art Museums, Harvard Film Archive, the Arnold Arboretum,
# Harvard Museums of Science & Culture and ArtsEmerson are public museums and professional
# presenters that a school happens to run; their listings aren't student events.
COLLEGE_SOURCES = {
    "MIT Events": "mit",
    "MIT Open Space": "mit",
    "MIT Strategic Games Society": "mit",
    "MIT Engineers Athletics": "mit",
    "Boston College Events": "bc",
    "Boston College Eagles Athletics": "bc",
    "Suffolk University Events": "suffolk",
    "Harvard College Events": "harvard",
    "Northeastern University": "neu",
    "Northeastern Huskies Athletics": "neu",
    "BU Terriers Athletics": "bu",
    "Tufts Jumbos Athletics": "tufts",
    "Tufts Music (Granoff Music Center)": "tufts",
    "Berklee College of Music": "berklee",
    "Jordan Hall (NEC)": "nec",
    "Longy School of Music": "longy",
    "Emerson Lions Athletics": "emerson",
    "Brandeis Judges Athletics": "brandeis",
    "UMass Boston Beacons Athletics": "umb",
    "Babson Beavers Athletics": "babson",
}
ATHLETICS_SOURCES = {s for s in COLLEGE_SOURCES if s.endswith(" Athletics")}

# School names as they appear in titles. Harvard skips the places named after it
# (Harvard Square, Harvard Ave, Harvard Book Store); MIT must be upper case ("Mit" is a word in German titles).
_SCHOOL_NAME_RES = [
    ("bu", re.compile(r"\bBoston\s+University\b|\bBU\s+(?:Terriers|Men'?s|Women'?s)\b|\bTerriers\b", re.I)),
    ("bc", re.compile(r"\bBoston\s+College\b|\bBC\s+(?:Eagles|Men'?s|Women'?s)\b", re.I)),
    ("neu", re.compile(r"\bNortheastern(?:\s+University|\s+Huskies)?\b(?!\s+(?:Ave|Avenue|Mass|Massachusetts))", re.I)),
    ("harvard", re.compile(r"\bHarvard\b(?!\s+(?:Square|Sq\b|St\b|Street|Ave|Avenue|Book|Bridge|Business\s+District))", re.I)),
    ("mit", re.compile(r"\bMIT\b|\bMassachusetts\s+Institute\s+of\s+Technology\b")),
    ("tufts", re.compile(r"\bTufts\b(?!\s+(?:Medical|Health))", re.I)),
    ("berklee", re.compile(r"\bBerklee\b", re.I)),
    ("nec", re.compile(r"\bNew\s+England\s+Conservatory\b|\bNEC\b")),
    ("longy", re.compile(r"\bLongy\b", re.I)),
    ("emerson", re.compile(r"\bEmerson\s+(?:College|Lions)\b", re.I)),
    ("suffolk", re.compile(r"\bSuffolk\s+(?:University|Rams)\b", re.I)),
    ("brandeis", re.compile(r"\bBrandeis\b", re.I)),
    ("babson", re.compile(r"\bBabson\b", re.I)),
    ("umb", re.compile(r"\bUMass[\s-]+Boston\b|\bUMB\s+Beacons\b", re.I)),
]

# Campus buildings, used only to tell which school an already-college event belongs to.
_SCHOOL_VENUE_RES = [
    ("bu", re.compile(r"\b(?:agganis|case\s+gym|nickerson\s+field|walter\s+brown\s+arena|fitrec|track\s+&\s+tennis\s+center)\b", re.I)),
    ("bc", re.compile(r"\b(?:conte\s+forum|alumni\s+stadium|kelley\s+rink|gasson\s+hall|mcmullen\s+museum|robsham)\b", re.I)),
    ("neu", re.compile(r"\b(?:matthews\s+arena|cabot\s+(?:center|cage)|parsons\s+field|blackman\s+auditorium|curry\s+student\s+center)\b", re.I)),
    ("harvard", re.compile(r"\b(?:bright[- ]landry|lavietes|harvard\s+stadium|blodgett\s+pool|sanders\s+theatre|smith\s+campus\s+center|memorial\s+church|loeb\s+drama)\b", re.I)),
    ("mit", re.compile(r"\b(?:kresge\s+auditorium|rockwell\s+cage|zesiger|steinbrenner\s+stadium|briggs\s+field|walker\s+memorial)\b", re.I)),
    ("tufts", re.compile(r"\b(?:cousens\s+gym|ellis\s+oval|gantcher|granoff\s+music|distler\s+performance)\b", re.I)),
    ("berklee", re.compile(r"\b(?:berklee\s+performance\s+center|david\s+friend\s+recital|cafe\s+939)\b", re.I)),
    ("nec", re.compile(r"\b(?:jordan\s+hall|williams\s+hall|brown\s+hall)\b", re.I)),
    ("brandeis", re.compile(r"\b(?:gosman|spingold)\b", re.I)),
    ("babson", re.compile(r"\bstaake\s+gym", re.I)),
    ("umb", re.compile(r"\bclark\s+athletic\s+center\b", re.I)),
]

# Hostnames of the schools' sites, for aggregator listings that link straight to them.
_SCHOOL_HOSTS = [
    ("bu", ("bu.edu", "goterriers.com")),
    ("bc", ("bc.edu", "bceagles.com")),
    ("neu", ("northeastern.edu", "nuhuskies.com")),
    ("harvard", ("harvard.edu", "gocrimson.com")),
    ("mit", ("mit.edu", "mitathletics.com")),
    ("tufts", ("tufts.edu", "gotuftsjumbos.com")),
    ("berklee", ("berklee.edu",)),
    ("nec", ("necmusic.edu",)),
    ("longy", ("longy.edu",)),
    ("emerson", ("emerson.edu", "emersonlions.com")),
    ("suffolk", ("suffolk.edu", "suffolkathletics.com")),
    ("brandeis", ("brandeis.edu", "brandeisjudges.com")),
    ("babson", ("babson.edu", "babsonathletics.com")),
    ("umb", ("umb.edu", "beaconsathletics.com")),
]

# A college game: a sport, or a "vs"/"at" between teams ("Boston University Men's Hockey vs. Harvard")
_GAME_RE = re.compile(
    r"\b(?:men'?s|women'?s|mens|womens)\s+\w+|\b(?:ice\s+hockey|hockey|basketball|soccer|lacrosse|volleyball|"
    r"football|baseball|softball|swimming|squash|wrestling|rowing|regatta|fencing)\b", re.I)
_VERSUS_RE = re.compile(r"\s(?:vs\.?|v\.|at)\s", re.I)
# A student ensemble or production ("MIT Concert Choir & MIT Symphony Orchestra")
_ENSEMBLE_RE = re.compile(
    r"\b(?:choir|chorus|chorale|glee\s+club|orchestra|symphony|philharmonic|wind\s+ensemble|jazz\s+ensemble|"
    r"band|a\s*cappella|dance\s+(?:company|team|marathon)|players|student\s+(?:recital|showcase|production)|"
    r"commencement|homecoming|family\s+weekend)\b", re.I)
# Intercollegiate events and nights aimed at students, whoever lists them
_INTERCOLLEGIATE_RE = re.compile(
    r"\b(?:beanpot|hack\s?mit|hack\s?beanpot|head\s+of\s+the\s+charles|intercollegiate|college\s+night|student\s+night)\b", re.I)


def _text(e):
    return (e.get("name") or e.get("title") or "").strip()


def _school_from_title(title):
    """The home school: named first in "Northeastern ... vs Harvard", after "at" in "BC Eagles at Harvard Crimson"."""
    m = re.search(r"\s+at\s+", title)
    if m and _GAME_RE.search(title):
        home = _school_from_title(title[m.end():])
        if home:
            return home
    best = None
    for key, rx in _SCHOOL_NAME_RES:
        m = rx.search(title)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), key)
    return best[1] if best else None


def _school_from_host(url):
    m = re.match(r"https?://([^/]+)", (url or "").lower())
    host = m.group(1) if m else ""
    for key, domains in _SCHOOL_HOSTS:
        if any(host == d or host.endswith("." + d) for d in domains):
            return key
    return None


def is_college_event(e):
    source = (e.get("_source_venue") or "").strip()
    if source in COLLEGE_SOURCES:
        return True
    title = _text(e)
    if not title:
        return False
    if _INTERCOLLEGIATE_RE.search(title):
        return True
    if not _school_from_title(title):
        return False
    is_game = bool(_GAME_RE.search(title) and (_VERSUS_RE.search(title) or "athletics" in title.lower()))
    return is_game or bool(_ENSEMBLE_RE.search(title))


def detect_school(e):
    """The school key for a college event, or None for cross-campus/student events with no single school."""
    source = (e.get("_source_venue") or "").strip()
    if source in COLLEGE_SOURCES:
        return COLLEGE_SOURCES[source]
    key = _school_from_title(_text(e)) or _school_from_host(e.get("url"))
    if key:
        return key
    venue = e.get("venue") or ""
    for key, rx in _SCHOOL_VENUE_RES:
        if rx.search(venue):
            return key
    return None


def college_kind(e, category=None):
    """sports / performances / talks / campus, from the source and the site's own category."""
    cat = (category or e.get("category") or "").lower()
    if (e.get("_source_venue") or "") in ATHLETICS_SOURCES or cat == "sports":
        return "sports"
    if cat in ("music", "classical", "clubbing", "dance", "comedy", "theater", "stage", "film"):
        return "performances"
    if cat in ("talks", "books", "tech"):
        return "talks"
    return "campus"


COLLEGE_KINDS = [
    ("sports", "🏒", "Games"),
    ("performances", "🎻", "Concerts & shows"),
    ("talks", "🎓", "Talks & lectures"),
    ("campus", "🏛️", "Campus life"),
]


def school_label(key):
    return (COLLEGE_SCHOOLS.get(key) or GENERIC_SCHOOL)[0]
