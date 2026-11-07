"""Boston Events — Summer Camps Scraper & Aggregator.

Aggregates accredited summer day camps and overnight camps across
Boston, Cambridge, Somerville, MetroWest, North Shore, South Shore,
and Greater Massachusetts from ACA New England and direct camp networks.
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request

CAMPS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camps.json")

# Verified enrichment data for premier Greater Boston & MA camps
_CURATED_ENRICHMENTS = {
    "hill house": {
        "name": "Hill House Summer Camp",
        "ages": "Ages 5–12",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "$575–$640",
        "price_tier": "mid",
        "category": "traditional",
        "category_label": "🏕️ Traditional Day Camp",
        "dates": "Weekly June 15 – August 28",
        "hours": "9:00 AM – 4:00 PM (Extended day 8:00 AM – 5:30 PM)",
        "neighborhood": "Beacon Hill, Boston",
        "highlights": "Sailing on the Charles River, splash pad, athletics, creative arts, field trips.",
        "url": "https://www.hillhouseboston.org/camps/summer-camp/"
    },
    "boston children": {
        "name": "Boston Children's Museum Summer Discovery",
        "ages": "Ages 5–7",
        "age_groups": ["preschool", "elementary"],
        "price_weekly": "$750",
        "price_tier": "premium",
        "category": "arts",
        "category_label": "🎨 Arts & Museum Discovery",
        "dates": "Weekly July 6 – August 21",
        "hours": "9:00 AM – 4:00 PM (Aftercare to 5:30 PM)",
        "neighborhood": "Fort Point / Seaport, Boston",
        "highlights": "Hands-on museum exhibits, STEAM lab workshops, channel explorations.",
        "url": "https://bostonchildrensmuseum.org/"
    },
    "steve & kate": {
        "name": "Steve & Kate's Camp — Boston & Cambridge",
        "ages": "Ages 4–12",
        "age_groups": ["preschool", "elementary", "middle"],
        "price_weekly": "$550 (or $119/day)",
        "price_tier": "mid",
        "category": "stem",
        "category_label": "🤖 Creative Tech & Maker",
        "dates": "Weekly June 15 – August 21",
        "hours": "8:00 AM – 6:00 PM (Full day included)",
        "neighborhood": "Boston & Cambridge",
        "highlights": "Self-directed choice: stop-motion animation, coding, sewing, baking, maker lab. Unused days refunded.",
        "url": "https://steveandkatescamp.com/boston/"
    },
    "linx": {
        "name": "LINX Camps Wellesley",
        "ages": "Ages 3–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "$745–$845",
        "price_tier": "premium",
        "category": "sports",
        "category_label": "⚽ Sports, Theater & STEM",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 4:00 PM",
        "neighborhood": "Wellesley, MA (MetroWest)",
        "highlights": "40+ specialty tracks across sports clinics, musical theater, coding, and camp games.",
        "url": "https://www.linxcamps.com/"
    },
    "nuvu": {
        "name": "NuVu Innovation Studios",
        "ages": "Ages 11–18",
        "age_groups": ["middle", "teens"],
        "price_weekly": "$825 ($1,650/2-wk)",
        "price_tier": "premium",
        "category": "stem",
        "category_label": "🔬 Innovation & Robotics",
        "dates": "2-week modules July – August",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Central Square, Cambridge",
        "highlights": "MIT-inspired studio design: architecture, robotics, bio-design, micro-electronics.",
        "url": "https://cambridge.nuvustudio.com/summer"
    },
    "empow": {
        "name": "Empow Studios STEM Camp",
        "ages": "Ages 7–15",
        "age_groups": ["elementary", "middle", "teens"],
        "price_weekly": "$645–$695",
        "price_tier": "mid",
        "category": "stem",
        "category_label": "💻 Coding & Game Design",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 4:00 PM (Extended day available)",
        "neighborhood": "Newton & Lexington, MA",
        "highlights": "Video game creation, Python coding, Minecraft engineering, 3D animation.",
        "url": "https://empow.me/stem-camps/"
    },
    "boston nature center": {
        "name": "Boston Nature Center Camp (Mass Audubon)",
        "ages": "Ages 5–15",
        "age_groups": ["elementary", "middle", "teens"],
        "price_weekly": "Sliding scale ($250–$820)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🌿 Nature & Wildlife",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 3:30 PM (Aftercare to 5:30 PM)",
        "neighborhood": "Mattapan / JP, Boston",
        "highlights": "Mass Audubon urban sanctuary: pond dipping, wildlife tracking, organic gardens, 5-tier sliding scale.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/boston-nature-center/camp"
    },
    "drumlin farm": {
        "name": "Drumlin Farm Camp (Mass Audubon)",
        "ages": "Ages 4–17",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "Sliding scale ($350–$810)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🚜 Working Farm & Wildlife",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Lincoln, MA (MetroWest)",
        "highlights": "Mass Audubon working farm: farm animals, crop harvesting, hayrides, forest trails.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/drumlin-farm/camp"
    },
    "habitat": {
        "name": "Habitat Nature Camp (Mass Audubon)",
        "ages": "Ages 5–14",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "Sliding scale ($340–$780)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🌿 Forest & Pond Ecology",
        "dates": "Weekly June 22 – August 21",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Belmont, MA",
        "highlights": "Mass Audubon sanctuary: quiet meadow discovery, amphibian studies, nature arts.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/habitat/camp"
    },
    "moose hill": {
        "name": "Moose Hill Nature Camp (Mass Audubon)",
        "ages": "Ages 4–16",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "Sliding scale ($320–$760)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🌲 Wilderness & Survival",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 3:30 PM",
        "neighborhood": "Sharon, MA (South Shore)",
        "highlights": "Mass Audubon oldest sanctuary: vernal pools, outdoor survival skills, bogs, firecraft.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/moose-hill/camp"
    },
    "broadmoor": {
        "name": "Broadmoor Nature Camp (Mass Audubon)",
        "ages": "Ages 5–15",
        "age_groups": ["elementary", "middle", "teens"],
        "price_weekly": "Sliding scale ($330–$770)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🛶 River Ecology & Canoeing",
        "dates": "Weekly June 22 – August 28",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Natick, MA (MetroWest)",
        "highlights": "Mass Audubon sanctuary along the Charles River: canoe trips, vernal pool dip netting, boardwalk walks.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/broadmoor/camp"
    },
    "blue hills": {
        "name": "Blue Hills Nature Camp (Mass Audubon)",
        "ages": "Ages 5–13",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "Sliding scale ($340–$780)",
        "price_tier": "sliding",
        "category": "nature",
        "category_label": "🌲 Forest & Trail Ecology",
        "dates": "Weekly June 22 – August 21",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Milton, MA",
        "highlights": "Mass Audubon sanctuary in the Blue Hills: trail ecology, geology, pond life, 5-tier sliding scale.",
        "url": "https://www.massaudubon.org/places-to-explore/nature-centers/blue-hills/camp"
    },
    "bcyf": {
        "name": "BCYF Summer Camps (City of Boston)",
        "ages": "Ages 6–13",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "Free – $50",
        "price_tier": "free",
        "category": "traditional",
        "category_label": "🏛️ City Community Centers",
        "dates": "Weekly July 6 – August 21",
        "hours": "9:00 AM – 4:00 PM",
        "neighborhood": "30+ Boston Neighborhoods",
        "highlights": "City of Boston Centers for Youth & Families: swimming, arts, sports, breakfast & lunch included.",
        "url": "https://www.boston.gov/departments/community-youth-and-families/bcyf-summer-camps"
    },
    "harbor view": {
        "name": "Camp Harbor View",
        "ages": "Ages 10–14 (Grades 6–8)",
        "age_groups": ["middle"],
        "price_weekly": "Free (100% Covered)",
        "price_tier": "free",
        "category": "nature",
        "category_label": "⛵ Harbor Island Adventure",
        "dates": "Two 4-week sessions July & August",
        "hours": "8:00 AM – 4:30 PM (Ferry pickup)",
        "neighborhood": "Long Island, Boston Harbor",
        "highlights": "100% Free for Boston youth: sailing, climbing wall, leadership, meals and transport provided.",
        "url": "https://campharborview.org/summer-camp/"
    },
    "museum of science": {
        "name": "Museum of Science Summer Courses",
        "ages": "Ages 6–14 (Grades 1–8)",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "$485–$550",
        "price_tier": "mid",
        "category": "stem",
        "category_label": "🔬 Science & Engineering",
        "dates": "Weekly July 6 – August 21",
        "hours": "9:00 AM – 3:00 PM",
        "neighborhood": "Science Park, Boston/Cambridge",
        "highlights": "Behind-the-scenes museum access, hands-on engineering design, Omni theater screenings.",
        "url": "https://www.mos.org/summer-courses"
    },
    "new england aquarium": {
        "name": "New England Aquarium Harbor Camp",
        "ages": "Ages 8–15",
        "age_groups": ["elementary", "middle", "teens"],
        "price_weekly": "$685–$750",
        "price_tier": "premium",
        "category": "nature",
        "category_label": "🐋 Marine Biology & Ocean Fieldwork",
        "dates": "1 & 2-week sessions July – August",
        "hours": "8:30 AM – 4:30 PM",
        "neighborhood": "Central Wharf, Boston",
        "highlights": "Behind-the-scenes animal care, harbor boat excursions, marine biology fieldwork, tide pool labs.",
        "url": "https://www.neaq.org/learn/camps/"
    },
    "zoo new england": {
        "name": "Zoo New England Summer ZooCamp",
        "ages": "Ages 6–13",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "$495–$560",
        "price_tier": "mid",
        "category": "nature",
        "category_label": "🦁 Zoology & Wildlife Care",
        "dates": "Weekly June 29 – August 21",
        "hours": "9:00 AM – 3:30 PM",
        "neighborhood": "Franklin Park Zoo (Boston) & Stone Zoo (Stoneham)",
        "highlights": "Close-up animal encounters, keeper talks, zookeeper training, wildlife conservation.",
        "url": "https://www.zoonewengland.org/act/education/summer-camps/"
    },
    "bb n": {
        "name": "Summer @ BB&N (Buckingham Browne & Nichols)",
        "ages": "Ages 4–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "$725–$820",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🏕️ Traditional & Specialty",
        "dates": "Weekly June 22 – August 14",
        "hours": "8:45 AM – 3:45 PM",
        "neighborhood": "Cambridge, MA (Charles River)",
        "highlights": "Riverside campus: instructional swimming, archery, creative arts, theater, rocketry.",
        "url": "https://www.bbns.org/community/summer-camp"
    },
    "beaver": {
        "name": "Beaver Summer Camp",
        "ages": "Ages 3–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "~$1,335–$1,750",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🏕️ Arts, Swim & Classic Camp",
        "dates": "Weekly & 2-week sessions June 22 – August 14",
        "hours": "8:45 AM – 3:45 PM",
        "neighborhood": "Chestnut Hill, Brookline",
        "highlights": "Heated pools, ropes course, visual & media arts, tennis, instructional swimming.",
        "url": "https://www.bvrcamp.org/"
    },
    "everwood": {
        "name": "Everwood Day Camp",
        "ages": "Ages 4–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "$795–$875",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🌊 Lakefront Outdoor Camp",
        "dates": "2-week minimums June 29 – August 21",
        "hours": "8:30 AM – 4:00 PM (Bus transportation included)",
        "neighborhood": "Sharon, MA (Lake Massapoag)",
        "highlights": "70-acre lakefront campus: motorized boating, sailing, paddleboarding, archery, challenge course, bus routes.",
        "url": "https://www.everwooddaycamp.com/"
    },
    "sewataro": {
        "name": "Camp Sewataro",
        "ages": "Ages 4–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "~$950–$1,050",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🏕️ Traditional Lakefront Camp",
        "dates": "Multi-week sessions late June – August",
        "hours": "8:30 AM – 4:00 PM (Bus routes across Greater Boston)",
        "neighborhood": "Sudbury, MA (MetroWest)",
        "highlights": "54-acre wooded campus: swimming pond, boating, zip line, tennis, equestrian, bus transportation included.",
        "url": "https://www.sewataro.com/"
    },
    "fessenden": {
        "name": "Fessenden Day Camp",
        "ages": "Ages 3.5–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "$915 ($675 half-day)",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🏕️ Campus Day Camp",
        "dates": "Weekly June 22 – August 14",
        "hours": "9:00 AM – 4:00 PM",
        "neighborhood": "West Newton, MA",
        "highlights": "41-acre campus: heated outdoor pools, ice rink, indoor turf, theater, daily hot lunch included.",
        "url": "http://www.fessendensummercamps.org/"
    },
    "belmont day": {
        "name": "Belmont Day School Summer Camp",
        "ages": "Ages 3–14",
        "age_groups": ["preschool", "elementary", "middle"],
        "price_weekly": "$790–$850",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🏕️ Creative Campus Day Camp",
        "dates": "Weekly June 22 – August 14",
        "hours": "8:45 AM – 3:45 PM",
        "neighborhood": "Belmont, MA",
        "highlights": "Swimming lessons, woodworking, gymnastics, ceramics, archery, outdoor adventures.",
        "url": "https://www.belmontday.org/summer/belmont-day-camp/"
    },
    "nobles": {
        "name": "Nobles Day Camp",
        "ages": "Ages 4–14",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "~$800–$875 ($1,600–$1,750/2-wk)",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🎭 Traditional & Arts Camp",
        "dates": "2-week sessions June 22 – August 14",
        "hours": "8:30 AM – 4:00 PM",
        "neighborhood": "Dedham, MA (Charles River)",
        "highlights": "Noble and Greenough School: collegiate athletics, boat basin on the Charles, pottery, musical theatre.",
        "url": "http://www.noblesdaycamp.org/"
    },
    "dexter southfield": {
        "name": "Dexter Southfield Summer Camps",
        "ages": "Ages 3–14",
        "age_groups": ["preschool", "elementary", "middle"],
        "price_weekly": "$775–$825",
        "price_tier": "premium",
        "category": "sports",
        "category_label": "⚽ Sports & Classic Day Camp",
        "dates": "Weekly June 15 – August 14",
        "hours": "8:30 AM – 4:00 PM",
        "neighborhood": "Brookline, MA",
        "highlights": "36-acre campus, Olympic-size indoor ice arena, indoor pool, STEM maker spaces, grass athletic fields.",
        "url": "https://www.dextersouthfield.org/summer-camps/"
    },
    "park": {
        "name": "Summer at Park (The Park School)",
        "ages": "Ages 4–15",
        "age_groups": ["preschool", "elementary", "middle", "teens"],
        "price_weekly": "$760–$820",
        "price_tier": "premium",
        "category": "traditional",
        "category_label": "🎨 Creative & Day Camp",
        "dates": "Weekly June 22 – August 14",
        "hours": "8:45 AM – 3:45 PM",
        "neighborhood": "Brookline, MA",
        "highlights": "Instructional swim, performing arts, outdoor exploration, soccer, robotics.",
        "url": "http://www.summeratpark.org/"
    },
    "ymca": {
        "ages": "Ages 5–13",
        "age_groups": ["elementary", "middle"],
        "price_weekly": "$360–$460",
        "price_tier": "mid",
        "category": "traditional",
        "category_label": "🏕️ YMCA Community Camp",
        "dates": "Weekly June 29 – August 28",
        "hours": "8:30 AM – 5:00 PM",
        "neighborhood": "Boston, Cambridge, Waltham, Dorchester, West Roxbury, Woburn, Reading",
        "highlights": "Swimming lessons, STEM enrichment, field trips, gym sports, EEC state vouchers accepted."
    }
}


def _clean_text(s):
    if not s:
        return ""
    txt = html.unescape(str(s))
    return re.sub(r"\s+", " ", txt).strip()


def _parse_aca_hours(hours_html):
    """Extract standard time range from ACA opening hours HTML table."""
    if not hours_html:
        return "Full Day (e.g. 9:00 AM – 4:00 PM)"
    m = re.search(r'<time datetime="([^"]+)">([^<]+)</time>\s*–\s*<time datetime="([^"]+)">([^<]+)</time>', hours_html)
    if m:
        return f"{m.group(2)} – {m.group(4)}"
    return "9:00 AM – 4:00 PM"


def _categorize_camp(name, desc, camp_type):
    low = f"{name} {desc}".lower()
    if any(k in low for k in ["nature", "wildlife", "audubon", "farm", "animals", "zoo", "aquarium", "marine", "outdoor"]):
        return "nature", "🌿 Nature & Outdoors"
    if any(k in low for k in ["stem", "robot", "code", "coding", "science", "engineering", "tech", "minecraft", "game design", "invention"]):
        return "stem", "💻 STEM & Coding"
    if any(k in low for k in ["art", "arts", "theater", "theatre", "music", "dance", "drama", "creative", "circus", "craft"]):
        return "arts", "🎨 Arts & Performance"
    if any(k in low for k in ["sport", "soccer", "basketball", "tennis", "golf", "swim", "gymnastic", "skate", "hockey", "athletic"]):
        return "sports", "⚽ Sports & Fitness"
    if camp_type and "resident" in camp_type.lower():
        return "sleepaway", "⛺ Sleepaway / Overnight"
    return "traditional", "🏕️ Traditional Day Camp"


def _estimate_price(name, camp_type, distance):
    low = name.lower()
    if "ymca" in low:
        return "$360–$460/wk", "mid", "Financial aid & state childcare vouchers accepted"
    if "bcyf" in low or "city of boston" in low:
        return "Free – $50/wk", "free", "City of Boston community center program"
    if "harbor view" in low:
        return "Free (100% Covered)", "free", "Full scholarship program for Boston youth"
    if camp_type and "resident" in camp_type.lower():
        return "Typical $1,200–$1,800/wk", "overnight", "Includes room, board & activities"
    if distance and distance > 25:
        return "Typical $450–$650/wk", "mid", "Transportation bus routes available"
    return "Typical $550–$750/wk", "mid", "Sibling and early registration discounts"


def _assign_region(city, dist_miles):
    c_low = (city or "").lower().strip()
    if c_low in ("boston", "roxbury", "dorchester", "east boston", "south boston", "charlestown", "brighton", "allston", "mattapan", "hyde park", "west roxbury", "jamaica plain"):
        return "boston", "Boston Proper"
    if c_low in ("cambridge", "somerville"):
        return "cambridge", "Cambridge & Somerville"
    if c_low in ("arlington", "belmont", "brookline", "chestnut hill", "milton", "newton", "waltham", "west newton", "woburn", "watertown", "medford", "malden", "everett", "chelsea"):
        return "innersuburbs", "Brookline, Newton & Nearby"
    if c_low in ("bedford", "concord", "dedham", "harvard", "hopkinton", "hudson", "lexington", "lincoln", "littleton", "natick", "sudbury", "wayland", "wellesley", "westwood", "needham", "dover", "weston", "framingham", "acton", "marlborough"):
        return "metrowest", "MetroWest"
    if c_low in ("amesbury", "andover", "beverly", "boxford", "byfield", "manchester", "marblehead", "reading", "salem", "topsfield", "wakefield", "lynn", "swampscott", "danvers", "peabody", "gloucester", "rockport", "ipswich", "newburyport", "north andover"):
        return "northshore", "North Shore"
    if c_low in ("assonet", "canton", "duxbury", "kingston", "marshfield", "middleboro", "norfolk", "north scituate", "pembroke", "plymouth", "rehoboth", "seekonk", "sharon", "south easton", "quincy", "braintree", "hingham", "cohasset", "scituate", "norwell", "stoughton", "foxborough", "brockton"):
        return "southshore", "South Shore"
    return "regional", "Greater MA & Overnight"


def fetch_all_camps(force=False):
    """Fetch camps from ACA New England API, enrich with curated details, and save to camps.json."""
    if not force and os.path.exists(CAMPS_JSON_PATH):
        try:
            with open(CAMPS_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    camps_list = []
    seen_normalized = set()
    matched_curated_keys = set()

    # 1. Fetch live accredited camps from ACA New England
    try:
        url = "https://www.acanewengland.org/wp-admin/admin-ajax.php?action=store_search&lat=42.3601&lng=-71.0589&radius=100&max_results=200"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            aca_records = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: Failed to fetch live ACA camps: {e}")
        aca_records = []

    for rec in aca_records:
        raw_name = _clean_text(rec.get("store"))
        if not raw_name:
            continue
        norm_name = re.sub(r"[^a-z0-9]+", " ", raw_name.lower()).strip()
        seen_normalized.add(norm_name)

        city = _clean_text(rec.get("city"))
        state = _clean_text(rec.get("state") or "MA")
        address = _clean_text(rec.get("address"))
        camp_url = rec.get("url") or ""
        camp_type = _clean_text(rec.get("my_type_camp") or "Day")
        genders = _clean_text(rec.get("my_genders") or "Coed")
        dist_str = rec.get("distance")
        try:
            distance = float(dist_str) if dist_str else None
        except ValueError:
            distance = None

        hours_str = _parse_aca_hours(rec.get("hours"))
        cat_key, cat_label = _categorize_camp(raw_name, "", camp_type)
        price_wk, price_tier, price_note = _estimate_price(raw_name, camp_type, distance)
        region_key, region_label = _assign_region(city, distance)

        # Check curated enrichment matches
        enrichment = None
        for k_sub, enr in _CURATED_ENRICHMENTS.items():
            norm_k = re.sub(r"[^a-z0-9]+", " ", k_sub.lower()).strip()
            if norm_k in norm_name or norm_name in norm_k:
                enrichment = enr
                matched_curated_keys.add(k_sub)
                break

        display_name = enrichment.get("name", raw_name) if enrichment else raw_name
        effective_url = enrichment.get("url", camp_url) if enrichment and enrichment.get("url") else (camp_url or "https://www.google.com/search?q=" + urllib.parse.quote(raw_name + " Summer Camp MA"))

        camp_data = {
            "id": f"camp_{rec.get('id', abs(hash(raw_name)) % 100000)}",
            "name": display_name,
            "city": city,
            "state": state,
            "address": address,
            "distance_miles": distance,
            "region": region_key,
            "region_label": region_label,
            "type": camp_type,
            "genders": genders,
            "url": effective_url,
            "hours": enrichment["hours"] if enrichment and enrichment.get("hours") else hours_str,
            "ages": enrichment["ages"] if enrichment and enrichment.get("ages") else "Ages 5–14 (Grades K–8)",
            "age_groups": enrichment["age_groups"] if enrichment and enrichment.get("age_groups") else ["elementary", "middle"],
            "dates": enrichment["dates"] if enrichment and enrichment.get("dates") else "Weekly sessions late June – late August",
            "price_weekly": enrichment["price_weekly"] if enrichment and enrichment.get("price_weekly") else price_wk,
            "price_tier": enrichment["price_tier"] if enrichment and enrichment.get("price_tier") else price_tier,
            "price_note": enrichment.get("highlights", price_note) if enrichment else price_note,
            "category": enrichment["category"] if enrichment and enrichment.get("category") else cat_key,
            "category_label": enrichment["category_label"] if enrichment and enrichment.get("category_label") else cat_label,
            "accredited": True,
            "source": "American Camp Association (ACA) New England"
        }
        camps_list.append(camp_data)

    # 2. Add curated camps not in ACA list (or not matched by fuzzy substring)
    for k_sub, enr in _CURATED_ENRICHMENTS.items():
        if k_sub in matched_curated_keys or k_sub == "ymca":
            continue
        norm_k = re.sub(r"[^a-z0-9]+", " ", k_sub.lower()).strip()
        if any(norm_k in s for s in seen_normalized):
            continue

        camp_title = enr.get("name", k_sub.title() + " Summer Camp")
        city = "Boston" if "boston" in enr["neighborhood"].lower() else "Cambridge" if "cambridge" in enr["neighborhood"].lower() else "Wellesley" if "wellesley" in enr["neighborhood"].lower() else "Lincoln"
        dist = 2.5 if city == "Boston" else 3.5 if city == "Cambridge" else 12.0
        region_key, region_label = _assign_region(city, dist)

        camps_list.append({
            "id": f"camp_cur_{abs(hash(k_sub)) % 100000}",
            "name": camp_title,
            "city": city,
            "state": "MA",
            "address": enr.get("neighborhood", ""),
            "distance_miles": dist,
            "region": region_key,
            "region_label": region_label,
            "type": "Day",
            "genders": "Coed",
            "url": enr.get("url", "https://www.google.com/search?q=" + urllib.parse.quote(camp_title + " MA")),
            "hours": enr["hours"],
            "ages": enr["ages"],
            "age_groups": enr["age_groups"],
            "dates": enr["dates"],
            "price_weekly": enr["price_weekly"],
            "price_tier": enr["price_tier"],
            "price_note": enr.get("highlights", ""),
            "category": enr["category"],
            "category_label": enr["category_label"],
            "accredited": True,
            "source": "Direct Verified Provider"
        })

    # Sort camps: by distance from Boston (closest first)
    camps_list.sort(key=lambda c: (c.get("distance_miles") is None, c.get("distance_miles") or 999))

    # Save to camps.json
    try:
        with open(CAMPS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(camps_list, f, indent=2, ensure_ascii=False)
        print(f"Wrote {len(camps_list)} summer camps to {CAMPS_JSON_PATH}")
    except Exception as e:
        print(f"Warning: Failed to save camps.json: {e}")

    return camps_list


if __name__ == "__main__":
    camps = fetch_all_camps(force=True)
    print(f"Done. Collected {len(camps)} camps across Boston and Greater Massachusetts.")
