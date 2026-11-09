#!/usr/bin/env python3
"""Check curated venue coordinates (venues_geo.py) against independent sources.

    python3 scripts/check_venue_coords.py --refresh-osm   # geocode every curated street address via
                                                          # OpenStreetMap (1 request/s, ~10 min) and save
                                                          # tests/data/venue_osm.json for the offline test
    python3 scripts/check_venue_coords.py --apply-osm     # move curated points onto trustworthy OSM matches
    python3 scripts/check_venue_coords.py                 # report: curated vs saved OSM results, and
                                                          # curated vs coordinates scraped sources report

tests/test_venue_coords.py fails when a venue drifts from its saved OSM point, so after moving a venue,
fixing an address or adding venues, rerun --refresh-osm (or add the address to OSM_WRONG below
when OSM matched a different building).
"""
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import venues_geo as G  # noqa: E402

SNAPSHOT = os.path.join(ROOT, "tests", "data", "venue_osm.json")
NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "wickedbostonevents-venue-check/1.0 (+https://www.wickedbostonevents.com)"
REPORT_METERS = 200


def curated_entries():
    """Every curated (lat, lng, neighborhood, address, name) with where it's defined."""
    out = [(f"VENUE_COORDINATES[{k!r}]", v) for k, v in G.VENUE_COORDINATES.items()]
    out += [(f"VENUE_RULES[{n!r}]", v) for n, v in G.VENUE_RULES]
    return out


def street_address(addr):
    """Geocodable addresses only: a street number and a street, not an area ("Harvard Square")."""
    return bool(addr) and any(ch.isdigit() for ch in addr.split(",")[0])


AMBIGUOUS_METERS = 2000
# Addresses where OSM's answer is wrong and our point is right (checked by hand). Address -> why.
OSM_WRONG = {
    '4 Charles St, Boston': 'OSM picked 4 Charles St in Hyde Park',
    '25 School St, Boston': 'OSM picked School St in Dorchester',
    '11 Beacon St, Boston': 'OSM put 11 Beacon St in Back Bay; it is by the State House',
    '1 Broadway, Everett': "OSM's 1 Broadway is a house up the street; the venue is inside Encore Boston Harbor",
    '256 Marginal St, East Boston': 'OSM matched the Lightship Nantucket berthed at the same shipyard',
}
GENERIC_WORDS = {"boston", "cambridge", "somerville", "public", "library", "center", "centre", "club",
                 "church", "street", "square", "park", "house", "hall", "theatre", "theater", "music"}


def osm_usable(hit, name, meters):
    """Is OSM's answer a trustworthy check on our point?

    No when it only found the street ("Bow Street", no house number), or when it is far away and
    doesn't name the venue: Boston has several Washington/Boylston/School Streets, and OSM often
    picks the one in Brighton or Hyde Park for a downtown address.
    """
    if not hit or hit.get("type", "").startswith("highway/"):
        return False
    words = [w for w in "".join(c if c.isalnum() else " " for c in name.lower()).split() if len(w) > 3 and w not in GENERIC_WORDS]
    named = any(w in hit.get("match", "").lower() for w in words)
    return named or meters <= AMBIGUOUS_METERS


def apply_osm():
    """Move every curated point whose usable OSM match is > REPORT_METERS away onto OSM's point."""
    import re
    with open(SNAPSHOT) as f:
        snap = json.load(f)
    path = os.path.join(ROOT, "venues_geo.py")
    with open(path) as f:
        src = f.read()
    moved = {}
    for _, (lat, lng, _, addr, name) in curated_entries():
        hit = snap.get(addr)
        if addr in OSM_WRONG:
            continue
        d = G._meters(lat, lng, hit["lat"], hit["lng"]) if hit else 0
        if hit and d > REPORT_METERS and osm_usable(hit, name, d):
            moved[addr] = (round(hit["lat"], 4), round(hit["lng"], 4))
    for addr, (lat, lng) in moved.items():
        pat = re.compile(r'\((\s*)-?\d+\.\d+,\s*-?\d+\.\d+,(\s*"[^"]*",\s*)"' + re.escape(addr) + '"')
        src, n = pat.subn(lambda m: f'({m.group(1)}{lat:.4f}, {lng:.4f},{m.group(2)}"{addr}"', src)
        print(f"{n} entr{'y' if n == 1 else 'ies'}  {addr} -> {lat:.4f}, {lng:.4f}")
    with open(path, "w") as f:
        f.write(src)


def osm_query(addr):
    q = addr if (" MA" in addr or addr.endswith("MA")) else f"{addr}, MA"
    params = {"q": q, "format": "json", "limit": 1, "countrycodes": "us",
              "viewbox": f"{G.MIN_LNG},{G.MAX_LAT},{G.MAX_LNG},{G.MIN_LAT}", "bounded": 1}
    req = urllib.request.Request(f"{NOMINATIM}?{urllib.parse.urlencode(params)}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if not res:
        return None
    top = res[0]
    return {"lat": round(float(top["lat"]), 6), "lng": round(float(top["lon"]), 6),
            "match": top.get("display_name", "")[:120], "type": f"{top.get('class')}/{top.get('type')}"}


def refresh_osm():
    try:
        with open(SNAPSHOT) as f:
            snap = json.load(f)
    except (OSError, ValueError):
        snap = {}
    addrs = sorted({v[3] for _, v in curated_entries() if street_address(v[3])})
    todo = [a for a in addrs if a not in snap]
    print(f"{len(addrs)} street addresses, {len(todo)} to geocode")
    for i, addr in enumerate(todo, 1):
        try:
            snap[addr] = osm_query(addr)
        except Exception as ex:  # keep going; a rerun retries what's missing
            print(f"  ! {addr}: {ex}")
            continue
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")
            _save(snap)
        time.sleep(1.1)  # Nominatim usage policy: at most 1 request per second
    _save({a: snap[a] for a in addrs if a in snap})


def _save(snap):
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    with open(SNAPSHOT, "w") as f:
        json.dump(dict(sorted(snap.items())), f, indent=1, ensure_ascii=False)
        f.write("\n")


def report():
    try:
        with open(SNAPSHOT) as f:
            snap = json.load(f)
    except OSError:
        snap = {}
    print(f"== Curated vs OpenStreetMap (> {REPORT_METERS} m)")
    seen, ignored = set(), []
    for where, (lat, lng, _, addr, name) in curated_entries():
        hit = snap.get(addr)
        if not hit or addr in OSM_WRONG or (name, lat, lng) in seen:
            continue
        seen.add((name, lat, lng))
        d = G._meters(lat, lng, hit["lat"], hit["lng"])
        if d > REPORT_METERS:
            if not osm_usable(hit, name, d):
                ignored.append(f"{round(d):>6} m  {name[:34]:34} osm: {hit['match'][:70]}")
                continue
            print(f"{round(d):>6} m  {name[:34]:34} {addr[:40]:40} osm: {hit['match'][:60]}")

    if ignored:
        print(f"\n   (ignored {len(ignored)} where OSM only found the street or a same-named street elsewhere)")
        for line in ignored:
            print("   ", line)
    path = os.path.join(ROOT, "events.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        data = json.load(f)
    venues = data["venues"] if isinstance(data, dict) else data
    gaps = defaultdict(list)
    for v in venues:
        src = v.get("venue", "")
        if any(s in src.lower() for s in G.LOW_TRUST_COORD_SOURCES):
            continue
        for e in v.get("events", []):
            if e.get("lat") is None or e.get("lng") is None:
                continue
            v_lower = (e.get("venue") or "").strip().lower()
            entry = G._exact_venue_match(v_lower) or G._rule_match(v_lower)
            if entry and street_address(entry[3]):
                gaps[(entry[4], src)].append(G._meters(entry[0], entry[1], float(e["lat"]), float(e["lng"])))
    print(f"\n== Curated vs scraped source coordinates (median > {REPORT_METERS} m, 2+ events)")
    for (name, src), ds in sorted(gaps.items(), key=lambda kv: -statistics.median(kv[1])):
        if len(ds) >= 2 and statistics.median(ds) > REPORT_METERS:
            print(f"{round(statistics.median(ds)):>6} m  {name[:34]:34} per {src} ({len(ds)} events)")


if __name__ == "__main__":
    if "--refresh-osm" in sys.argv:
        refresh_osm()
    elif "--apply-osm" in sys.argv:
        apply_osm()
    else:
        report()
