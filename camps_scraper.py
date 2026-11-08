"""Boston Events — Summer Camps Scraper & Aggregator.

The camp list comes from ACA New England's accredited-camp directory (names,
addresses, distance, day/overnight). Prices, dates, ages and sign-up dates come
ONLY from camps_verified.json, which is checked by hand against each camp's own
website. A camp that isn't in that file shows no price instead of an estimate.
"""

import html
import json
import math
import os
import re
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
CAMPS_JSON_PATH = os.path.join(_HERE, "camps.json")
VERIFIED_JSON_PATH = os.path.join(_HERE, "camps_verified.json")
ACA_CACHE_PATH = os.path.join(_HERE, "camps_aca.json")

BOSTON_LAT, BOSTON_LNG = 42.3601, -71.0589

# Fields copied from a verified entry onto the camp record.
_VERIFIED_FIELDS = (
    "name", "url", "category", "category_label", "ages", "age_groups", "hours",
    "season", "price", "price_tier", "price_year", "price_lines", "registration",
    "reg_dates", "sliding_scale", "sources", "checked",
)


def load_verified():
    with open(VERIFIED_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _clean_text(s):
    if not s:
        return ""
    txt = html.unescape(str(s))
    return re.sub(r"\s+", " ", txt).strip()


def _parse_aca_hours(hours_html):
    """Time range from ACA's opening-hours table, or None when ACA doesn't list one."""
    if not hours_html:
        return None
    m = re.search(r'<time datetime="([^"]+)">([^<]+)</time>\s*–\s*<time datetime="([^"]+)">([^<]+)</time>', hours_html)
    return f"{m.group(2)} – {m.group(4)}" if m else None


def _categorize_camp(name, camp_type):
    low = name.lower()
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


_MA_REGIONS = {
    "boston": ("Boston Proper", ("boston", "roxbury", "dorchester", "east boston", "south boston", "charlestown", "brighton", "allston", "mattapan", "hyde park", "west roxbury", "jamaica plain")),
    "cambridge": ("Cambridge & Somerville", ("cambridge", "somerville")),
    "innersuburbs": ("Brookline, Newton & Nearby", ("arlington", "belmont", "brookline", "chestnut hill", "milton", "newton", "waltham", "west newton", "woburn", "watertown", "medford", "malden", "everett", "chelsea")),
    "metrowest": ("MetroWest", ("bedford", "concord", "dedham", "harvard", "hopkinton", "hudson", "lexington", "lincoln", "littleton", "natick", "sudbury", "wayland", "wellesley", "westwood", "needham", "dover", "weston", "framingham", "acton", "marlborough")),
    "northshore": ("North Shore", ("amesbury", "andover", "beverly", "boxford", "byfield", "manchester", "marblehead", "reading", "salem", "topsfield", "wakefield", "lynn", "swampscott", "danvers", "peabody", "gloucester", "rockport", "ipswich", "newburyport", "north andover")),
    "southshore": ("South Shore", ("assonet", "canton", "duxbury", "kingston", "marshfield", "middleboro", "norfolk", "north scituate", "pembroke", "plymouth", "rehoboth", "seekonk", "sharon", "south easton", "quincy", "braintree", "hingham", "cohasset", "scituate", "norwell", "stoughton", "foxborough", "brockton")),
}


def _assign_region(city, state="MA"):
    # Town names repeat across states (Brookline NH, Manchester NH, North Scituate RI),
    # so only Massachusetts towns get a Massachusetts region.
    if (state or "MA").upper() == "MA":
        c_low = (city or "").lower().strip()
        for key, (label, towns) in _MA_REGIONS.items():
            if c_low in towns:
                return key, label
    return "regional", "Greater MA & Overnight"


def _miles_from_boston(lat, lng):
    if lat is None or lng is None:
        return None
    r = 3958.8
    p1, p2 = math.radians(BOSTON_LAT), math.radians(lat)
    dp, dl = p2 - p1, math.radians(lng - BOSTON_LNG)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 1)


def _apply_verified(camp, entry):
    for k in _VERIFIED_FIELDS:
        if k in entry:
            camp[k] = entry[k]
    camp["verified"] = True


def _apply_url_notes(camp, notes):
    if camp.get("verified"):
        return
    for note in notes:
        if note["url_contains"] in (camp.get("url") or ""):
            camp["registration"] = note["registration"]
            camp["sources"] = [note["source"]]
            camp["checked"] = note["checked"]


def _fetch_aca_records():
    url = "https://www.acanewengland.org/wp-admin/admin-ajax.php?action=store_search&lat=42.3601&lng=-71.0589&radius=100&max_results=200"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build_camps(aca_records, verified):
    by_aca_id = {v["aca_id"]: v for v in verified["camps"] if v.get("aca_id")}
    camps = []
    for rec in aca_records:
        raw_name = _clean_text(rec.get("store"))
        if not raw_name:
            continue
        city = _clean_text(rec.get("city"))
        state = _clean_text(rec.get("state") or "MA")
        camp_type = _clean_text(rec.get("my_type_camp") or "Day")
        try:
            distance = round(float(rec["distance"]), 1) if rec.get("distance") else None
        except ValueError:
            distance = None
        cat_key, cat_label = _categorize_camp(raw_name, camp_type)
        region_key, region_label = _assign_region(city, state)
        camp = {
            "id": f"camp_{rec.get('id')}",
            "name": raw_name,
            "city": city,
            "state": state,
            "address": _clean_text(rec.get("address")),
            "distance_miles": distance,
            "region": region_key,
            "region_label": region_label,
            "type": camp_type,
            "genders": _clean_text(rec.get("my_genders") or "Coed"),
            "url": rec.get("url") or "",
            "hours": _parse_aca_hours(rec.get("hours")),
            "age_groups": [],
            "price": None,
            "price_tier": "unlisted",
            "category": cat_key,
            "category_label": cat_label,
            "accredited": True,
            "verified": False,
            "source": "American Camp Association (ACA) New England",
        }
        entry = by_aca_id.get(camp["id"])
        if entry:
            _apply_verified(camp, entry)
        _apply_url_notes(camp, verified.get("url_notes", []))
        camps.append(camp)

    seen = {c["id"] for c in camps}
    for entry in verified["camps"]:
        if entry.get("aca_id"):
            continue  # only shown when ACA still lists the camp
        if entry["id"] in seen:
            continue
        region_key, region_label = _assign_region(entry["city"], entry.get("state", "MA"))
        camp = {
            "id": entry["id"],
            "city": entry["city"],
            "state": entry.get("state", "MA"),
            "address": entry.get("address", ""),
            "distance_miles": _miles_from_boston(entry.get("lat"), entry.get("lng")),
            "region": region_key,
            "region_label": region_label,
            "type": entry.get("type", "Day"),
            "genders": "Coed",
            "hours": None,
            "age_groups": [],
            "price": None,
            "price_tier": "unlisted",
            "accredited": False,
            "source": "Camp website",
        }
        _apply_verified(camp, entry)
        camps.append(camp)

    camps.sort(key=lambda c: (c.get("distance_miles") is None, c.get("distance_miles") or 999))
    return camps


def _load_aca_cache():
    try:
        with open(ACA_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def fetch_all_camps(force=False):
    """ACA New England camps merged with camps_verified.json.

    The raw ACA list is cached in camps_aca.json and only re-fetched with
    force=True. The merge runs every time, so an edit to camps_verified.json
    shows up on the next site build. camps.json holds the merged result.
    """
    aca_records = [] if force else _load_aca_cache()
    if not aca_records:
        try:
            aca_records = _fetch_aca_records()
            with open(ACA_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(aca_records, f, indent=1, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to fetch live ACA camps: {e}")
            aca_records = _load_aca_cache()  # keep the last good list

    camps_list = build_camps(aca_records, load_verified())
    try:
        with open(CAMPS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(camps_list, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Failed to save camps.json: {e}")
    return camps_list


if __name__ == "__main__":
    camps = fetch_all_camps(force=True)
    n_verified = sum(1 for c in camps if c.get("verified"))
    print(f"Done. {len(camps)} camps, {n_verified} checked against camp websites.")
