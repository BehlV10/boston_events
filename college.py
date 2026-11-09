"""College & Student Events directory for Greater Boston.

Identifies, tags, and categorizes college sports games, intercollegiate competitions
(ballroom dance, hackathons, a cappella), campus concerts, lectures, and student life
across Greater Boston universities (BU, BC, Northeastern, Harvard, MIT, Tufts,
Berklee/NEC, Emerson, etc.).
"""
import re

# College schools and institutions with display colors and metadata
COLLEGE_SCHOOLS = {
    "bu": {
        "slug": "bu",
        "name": "Boston University",
        "short": "BU",
        "color": "#CC0000",
        "accent": "rgba(204, 0, 0, 0.12)",
        "mascot": "Terriers",
    },
    "bc": {
        "slug": "bc",
        "name": "Boston College",
        "short": "BC",
        "color": "#8A100B",
        "accent": "rgba(138, 16, 11, 0.12)",
        "mascot": "Eagles",
    },
    "neu": {
        "slug": "neu",
        "name": "Northeastern University",
        "short": "NEU",
        "color": "#C8102E",
        "accent": "rgba(200, 16, 46, 0.12)",
        "mascot": "Huskies",
    },
    "harvard": {
        "slug": "harvard",
        "name": "Harvard University",
        "short": "Harvard",
        "color": "#A51C30",
        "accent": "rgba(165, 28, 48, 0.12)",
        "mascot": "Crimson",
    },
    "mit": {
        "slug": "mit",
        "name": "MIT",
        "short": "MIT",
        "color": "#7B1113",
        "accent": "rgba(123, 17, 19, 0.12)",
        "mascot": "Engineers",
    },
    "tufts": {
        "slug": "tufts",
        "name": "Tufts University",
        "short": "Tufts",
        "color": "#3E8EDE",
        "accent": "rgba(62, 142, 222, 0.12)",
        "mascot": "Jumbos",
    },
    "berklee": {
        "slug": "berklee",
        "name": "Berklee & Conservatories",
        "short": "Berklee/NEC",
        "color": "#111827",
        "accent": "rgba(17, 24, 39, 0.12)",
        "mascot": "Musicians",
    },
    "emerson": {
        "slug": "emerson",
        "name": "Emerson & Downtown",
        "short": "Emerson/Suffolk",
        "color": "#581c87",
        "accent": "rgba(88, 28, 135, 0.12)",
        "mascot": "Downtown",
    },
    "intercollegiate": {
        "slug": "intercollegiate",
        "name": "Cross-Campus / All Colleges",
        "short": "Cross-Campus",
        "color": "#0284c7",
        "accent": "rgba(2, 132, 199, 0.12)",
        "mascot": "All-Colleges",
    },
}

# Dedicated college sources from scrapers.py (case-folded)
COLLEGE_SOURCES = {
    "bu terriers athletics",
    "boston university athletics",
    "boston university",
    "northeastern huskies athletics",
    "northeastern university athletics",
    "northeastern university",
    "boston college eagles athletics",
    "boston college athletics",
    "boston college",
    "boston college events",
    "tufts jumbos athletics",
    "tufts university athletics",
    "tufts music (granoff music center)",
    "tufts music",
    "mit events",
    "mit open space",
    "mit strategic games society",
    "harvard film archive",
    "harvard art museums",
    "new england conservatory",
    "jordan hall (nec)",
    "berklee performance center",
}

# Collegiate venues in Greater Boston
_COLLEGE_VENUE_PATTERNS = [
    (re.compile(r"\b(?:agganis\s+arena|case\s+gym|nickerson\s+field|walter\s+brown\s+arena|fitrec|tsai\s+performance\s+center|bu\s+beach)\b", re.I), "bu"),
    (re.compile(r"\b(?:conte\s+forum|alumni\s+stadium|kelley\s+rink|gasson\s+hall|mcmullen\s+museum)\b", re.I), "bc"),
    (re.compile(r"\b(?:matthews\s+arena|cabot\s+center|parsons\s+field|blackman\s+auditorium|curry\s+student\s+center)\b", re.I), "neu"),
    (re.compile(r"\b(?:malkin\s+athletic\s+center|\bmac\b|lavietes\s+pavilion|harvard\s+stadium|blodgett\s+pool|sanders\s+theatre|memorial\s+church|harvard\s+film\s+archive|harvard\s+art\s+museums?|fong\s+auditorium|boylston\s+hall)\b", re.I), "harvard"),
    (re.compile(r"\b(?:kresge\s+auditorium|rockwell\s+cage|johnson\s+athletics|walker\s+memorial|mit\s+open\s+space|mit\s+student\s+center|met\s+warehouse|building\s+(?:10|w41|e51|4|14))\b", re.I), "mit"),
    (re.compile(r"\b(?:cousens\s+gymnasium|ellis\s+oval|granoff\s+music\s+center|distler\s+performance\s+hall)\b", re.I), "tufts"),
    (re.compile(r"\b(?:jordan\s+hall|berklee\s+performance\s+center|red\s+room\s+at\s+cafe\s+939|boston\s+conservatory)\b", re.I), "berklee"),
    (re.compile(r"\b(?:cutler\s+majestic\s+theatre|paramount\s+center|emerson\s+colonial)\b", re.I), "emerson"),
]

# Intercollegiate / cross-campus competitions & events
_INTERCOLLEGIATE_RE = re.compile(
    r"\b(?:ballroom\s+(?:dance\s+)?(?:competition|invitational|comp|classic)|"
    r"(?:invitational\s+)?ballroom|intercollegiate|collegiate|"
    r"hackbeanpot|hackmit|beanpot|varsity\s+vocals|\bicca\b|head\s+of\s+the\s+charles|"
    r"college\s+night|student\s+id\s+night|student\s+rush|all[- ]colleges?|cross[- ]campus)\b",
    re.I
)

# Collegiate athletics & sports patterns
_SPORTS_RE = re.compile(
    r"\b(?:men'?s|women'?s)?\s*(?:ice\s+hockey|hockey|basketball|soccer|field\s+hockey|lacrosse|"
    r"volleyball|swimming|diving|track\s+(?:&|and)\s+field|cross\s+country|rowing|baseball|softball|"
    r"tennis)\b|\b(?:vs\.?|at)\s+(?:boston\s+college|boston\s+university|northeastern|harvard|mit|tufts|"
    r"umass|providence|vermont|maine|new\s+hampshire|merrimack|connecticut|quinnipiac)\b",
    re.I
)

# Ballroom & dance patterns
_DANCE_RE = re.compile(
    r"\b(?:ballroom|waltz|tango|salsa|bachata|swing\s+dance|dance\s+competition|dance\s+comp|"
    r"invitational|dance\s+showcase|terrier\s+dance|crimson\s+dance)\b",
    re.I
)

# Hackathons & collegiate tech patterns
_TECH_RE = re.compile(
    r"\b(?:hackathon|hackbeanpot|hackmit|datathon|makeathon|colleg(?:e|iate)\s+hackathon|"
    r"developer\s+summit|student\s+hack)\b",
    re.I
)

# Arts, concerts & a cappella
_ARTS_RE = re.compile(
    r"\b(?:a\s*cappella|\bicca\b|choral\s+society|wind\s+ensemble|symphony\s+orchestra|brass\s+choir|"
    r"jazz\s+ensemble|student\s+recital|senior\s+recital|master\s+class|conservatory|chamber\s+music|"
    r"commencement\s+concert|campus\s+theater|student\s+production)\b",
    re.I
)

# Student ID / Student discount patterns
_STUDENT_ID_RE = re.compile(
    r"\b(?:free\s+with\s+(?:student|college|university)\s+id|with\s+valid\s+(?:student|college)\s+id|"
    r"student\s+discount|college\s+id|student\s+rush|college\s+night|students?\s+free)\b",
    re.I
)


def detect_school(e):
    """Detect which school an event belongs to (or 'intercollegiate')."""
    source = (e.get("_source_venue") or "").strip().lower()
    venue = (e.get("venue") or "").strip().lower()
    name = (e.get("name") or e.get("title") or "").strip()
    loc = (e.get("location") or "").strip()
    full_text = f"{source} {venue} {name} {loc}".lower()

    if _INTERCOLLEGIATE_RE.search(name) or "beanpot" in full_text or "hackbeanpot" in full_text:
        return "intercollegiate"

    # Match source first
    if "bu" in source or "boston university" in source:
        return "bu"
    if "bc" in source or "boston college" in source:
        return "bc"
    if "northeastern" in source or "neu" in source:
        return "neu"
    if "harvard" in source:
        return "harvard"
    if "mit" in source or "open space" in source:
        return "mit"
    if "tufts" in source:
        return "tufts"
    if "berklee" in source or "conservatory" in source or "jordan hall" in source or "nec" in source:
        return "berklee"

    # Match venues
    for pattern, slug in _COLLEGE_VENUE_PATTERNS:
        if pattern.search(venue) or pattern.search(loc) or pattern.search(name):
            return slug

    # Match names/teams
    if re.search(r"\bboston\s+university\b|\bterriers?\b", name, re.I):
        return "bu"
    if re.search(r"\bboston\s+college\b|\beagles?\b", name, re.I):
        return "bc"
    if re.search(r"\bnortheastern\b|\bhuskies?\b", name, re.I):
        return "neu"
    if re.search(r"\bharvard\b|\bcrimson\b", name, re.I):
        return "harvard"
    if re.search(r"\bmit\b|\bmassachusetts\s+institute\s+of\s+technology\b", name, re.I):
        return "mit"
    if re.search(r"\btufts\b|\bjumbos?\b", name, re.I):
        return "tufts"
    if re.search(r"\bberklee\b|\bnew\s+england\s+conservatory\b|\bjordan\s+hall\b", name, re.I):
        return "berklee"
    if re.search(r"\bemerson\b|\bsuffolk\b", name, re.I):
        return "emerson"

    return "intercollegiate"


def detect_college_type(e):
    """Categorize college event into: sports, dance, tech, arts, talks, social."""
    name = (e.get("name") or e.get("title") or "")
    desc = (e.get("description") or "")
    cat = (e.get("category") or "").lower()
    text = f"{name} {desc}".lower()

    if _TECH_RE.search(text) or cat == "tech":
        return "tech", "💻", "Hackathons & Tech"
    if _DANCE_RE.search(text) or "ballroom" in text or cat == "dance":
        return "dance", "💃", "Ballroom & Dance"
    if _SPORTS_RE.search(text) or "athletics" in (e.get("_source_venue") or "").lower() or " vs " in name:
        return "sports", "🏒", "Sports & Rivalries"
    if _ARTS_RE.search(text) or cat in ("music", "classical", "theater", "stage", "art"):
        return "arts", "🎭", "Concerts & Arts"
    if re.search(r"\b(?:seminar|colloquium|lecture|keynote|symposium|speaker|talk|defense)\b", text):
        return "talks", "🎓", "Talks & Expos"
    return "social", "🍻", "Student Life"


def detect_access_type(e):
    """Determine accessibility: free_id, intercollegiate, public."""
    name = (e.get("name") or e.get("title") or "")
    desc = (e.get("description") or "")
    price = str(e.get("price") or "").lower()
    text = f"{name} {desc} {price}".lower()

    if _STUDENT_ID_RE.search(text):
        return "free_id", "🪪 Free w/ Student ID"
    if _INTERCOLLEGIATE_RE.search(text) or "open to all" in text:
        return "intercollegiate", "🤝 Open to All Colleges"
    if "free" in price or price in ("$0", "0"):
        return "free", "💛 Free Admission"
    return "public", "🎟️ Tickets / Public"


def is_college_event(e):
    """Determine if an event is a college or student-targeted event."""
    source = (e.get("_source_venue") or "").strip().lower()
    if source in COLLEGE_SOURCES or "athletics" in source:
        return True

    venue = (e.get("venue") or "").strip().lower()
    loc = (e.get("location") or "").strip().lower()
    name = (e.get("name") or e.get("title") or "")
    desc = (e.get("description") or "")
    combined = f"{venue} {loc} {name} {desc}".lower()

    # Check for college venues
    for pattern, _ in _COLLEGE_VENUE_PATTERNS:
        if pattern.search(venue) or pattern.search(loc):
            return True

    # Check for intercollegiate keywords or student events
    if _INTERCOLLEGIATE_RE.search(name) or _STUDENT_ID_RE.search(combined):
        return True

    # Check for college vs games (e.g. "Boston University Men's Ice Hockey vs Harvard")
    if (" vs " in name or " vs. " in name) and any(s in combined for s in ["boston university", "boston college", "northeastern", "harvard", "mit", "tufts"]):
        return True

    # High signal university keywords in title
    if re.search(r"\b(?:boston\s+university|boston\s+college|northeastern\s+university|harvard|mit|tufts\s+university|berklee)\b", name, re.I):
        if any(w in combined for w in ["hockey", "basketball", "soccer", "recital", "concert", "hackathon", "symposium", "ballroom", "orchestra", "showcase", "championship", "invite"]):
            return True

    return False


def get_college_info(e):
    """Return structured college metadata for rendering badges and filters."""
    school_key = detect_school(e)
    school = COLLEGE_SCHOOLS.get(school_key, COLLEGE_SCHOOLS["intercollegiate"])
    ctype, cicon, clabel = detect_college_type(e)
    access_key, access_label = detect_access_type(e)
    is_inter = (school_key == "intercollegiate" or _INTERCOLLEGIATE_RE.search(e.get("name") or ""))

    return {
        "school_key": school_key,
        "school_name": school["name"],
        "school_short": school["short"],
        "school_color": school["color"],
        "school_accent": school["accent"],
        "school_mascot": school["mascot"],
        "type_key": ctype,
        "type_icon": cicon,
        "type_label": clabel,
        "access_key": access_key,
        "access_label": access_label,
        "is_intercollegiate": bool(is_inter),
    }
