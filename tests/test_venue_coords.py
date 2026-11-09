"""Are venue locations right, and does the site measure distance from them correctly?

- Every name pattern in VENUE_RULES finds its own venue. A broader pattern listed earlier used to
  win ("remnant" sent Remnant Satellite variants to Somerville, "mfa" sent SMFA to the MFA).
- A venue isn't listed twice with different points (WBUR CitySpace was in two places 778 m apart).
- Each curated street address sits where OpenStreetMap puts it, using a saved snapshot
  (tests/data/venue_osm.json) so CI never calls OSM. Refresh it with
  `python3 scripts/check_venue_coords.py --refresh-osm` after adding or moving venues; when OSM is the
  one that's wrong, add the address to OSM_WRONG in that script.
- The page's haversineMiles gives the right distances, and in a real browser the Near Me / pin list
  is sorted nearest first, follows the filters, and is built once per location.
"""
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import venues_geo as G  # noqa: E402

SNAPSHOT = os.path.join(ROOT, "tests", "data", "venue_osm.json")
SAME_PLACE_METERS = 150
OSM_TOLERANCE_METERS = 250

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import check_venue_coords as C  # noqa: E402  (OSM_WRONG: addresses OSM gets wrong; osm_usable: street-only/far matches)


def _entries():
    return [(f"VENUE_COORDINATES[{k!r}]", v) for k, v in G.VENUE_COORDINATES.items()] + \
           [(f"VENUE_RULES[{n!r}]", v) for n, v in G.VENUE_RULES]


def _has_street_number(addr):
    return bool(addr) and any(ch.isdigit() for ch in addr.split(",")[0])


def _miles(lat1, lng1, lat2, lng2):
    """Independent great-circle distance (spherical law of cosines) to check the page's haversine."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lng2 - lng1)
    return 3958.8 * math.acos(min(1.0, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)))


class VenueDataTest(unittest.TestCase):
    def test_every_pattern_finds_its_own_venue(self):
        wrong = []
        for needle, entry in G.VENUE_RULES:
            hit = G._rule_match(needle)
            if hit is not entry and G._meters(hit[0], hit[1], entry[0], entry[1]) > SAME_PLACE_METERS:
                first = next(n for n, e in G.VENUE_RULES if e is hit)
                wrong.append(f"{needle!r} ({entry[4]}) is caught first by {first!r} ({hit[4]}); move it above")
        self.assertEqual(wrong, [], "\n".join(wrong))

    def test_one_location_per_venue(self):
        """Different names/patterns for one venue must agree. Areas (no street number) may differ."""
        points = {}
        for where, (lat, lng, _, addr, name) in _entries():
            if _has_street_number(addr):
                points.setdefault(name, []).append((where, lat, lng))
        bad = []
        for name, pts in points.items():
            for i, (w1, a1, b1) in enumerate(pts):
                for w2, a2, b2 in pts[i + 1:]:
                    d = G._meters(a1, b1, a2, b2)
                    if d > SAME_PLACE_METERS:
                        bad.append(f"{name}: {w1} and {w2} are {round(d)} m apart")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_inside_service_area(self):
        for where, (lat, lng, *_rest) in _entries():
            self.assertTrue(G.MIN_LAT <= lat <= G.MAX_LAT and G.MIN_LNG <= lng <= G.MAX_LNG, where)

    def test_matches_openstreetmap(self):
        if not os.path.exists(SNAPSHOT):
            self.skipTest("no OSM snapshot; run scripts/check_venue_coords.py --refresh-osm")
        with open(SNAPSHOT) as f:
            snap = json.load(f)
        bad, checked = [], 0
        for where, (lat, lng, _, addr, name) in _entries():
            hit = snap.get(addr)
            if not hit or addr in C.OSM_WRONG:
                continue
            d = G._meters(lat, lng, hit["lat"], hit["lng"])
            if not C.osm_usable(hit, name, d):
                continue
            checked += 1
            if d > OSM_TOLERANCE_METERS:
                bad.append(f"{where} {name} ({addr}) is {round(d)} m from OSM's {hit['lat']},{hit['lng']} "
                           f"[{hit['match'][:70]}]")
        self.assertGreater(checked, 100)
        self.assertEqual(sorted(set(bad)), [], "\n".join(sorted(set(bad))))

    def test_osm_mismatch_list_has_no_stale_entries(self):
        addrs = {v[3] for _, v in _entries()}
        self.assertEqual([a for a in C.OSM_WRONG if a not in addrs], [])


def _node():
    return shutil.which("node")


def _chrome():
    for c in (os.environ.get("CHROME_PATH"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
              shutil.which("chromium"), shutil.which("chromium-browser")):
        if c and os.path.exists(c):
            return c
    return None


# Pin at Harvard Square; venues at known distances from it.
PIN = (42.3736, -71.1190)
VENUES = [  # (venue name as a source would write it, title, category)
    ("Club Passim", "Folk Songwriter Night", "music"),          # ~0.1 mi
    ("The Sinclair", "Indie Rock Double Bill", "music"),        # ~0.1 mi
    ("Remnant Satellite", "Cask Ale Tasting", "food"),          # East Cambridge, ~1.5 mi
    ("Brighton Music Hall", "Synthpop Album Release", "music"),  # Allston, ~1.6 mi
    ("Laugh Boston", "Stand-up Showcase", "comedy"),            # Seaport, ~4.3 mi
    ("Somewhere Unmappable", "Basement Jazz Jam", "music"),     # no location: listed last
]


def _render_page():
    import template as T
    when = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    # Each on its own site: two same-time events on one host at neighboring venues merge as one listing.
    venues = [{"venue": name, "url": f"https://venue{i}.example.org/", "error": None,
               "events": [{"name": title, "date": when.isoformat(), "venue": name,
                           "url": f"https://venue{i}.example.org/e/{i}", "price": "$10", "category": cat}]}
              for i, (name, title, cat) in enumerate(VENUES)]
    with patch("template._load_community_events", return_value=[]):
        return T.render_page(venues)


class DistanceInPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render_page()

    def test_haversine_matches_known_distances(self):
        if not _node():
            self.skipTest("node not installed")
        src = re.search(r"function haversineMiles\(.*?\n    }", self.html, re.S).group(0)
        pairs = [((42.3736, -71.1190), (42.3967, -71.1223)),   # Harvard Sq -> Davis Sq
                 ((42.3550, -71.0656), (42.3736, -71.1190)),   # Boston Common -> Harvard Sq
                 ((42.3601, -71.0589), (42.3601, -71.0589)),   # same point
                 ((42.0, -71.0), (43.0, -71.0))]               # one degree of latitude
        calls = ",".join(f"haversineMiles({a[0]},{a[1]},{b[0]},{b[1]})" for a, b in pairs)
        out = subprocess.run([_node(), "-e", f"{src}\nconsole.log(JSON.stringify([{calls}]))"],
                             capture_output=True, text=True, check=True).stdout
        got = json.loads(out)
        for (a, b), miles in zip(pairs, got):
            self.assertAlmostEqual(miles, _miles(*a, *b), delta=0.005, msg=(a, b))
        self.assertAlmostEqual(got[0], 1.6, delta=0.1)   # Harvard -> Davis on a map: ~1.6 mi
        self.assertAlmostEqual(got[3], 69.1, delta=0.1)  # 1 degree latitude

    def test_near_me_list_in_browser(self):
        chrome, node = _chrome(), _node()
        if not (chrome and node):
            self.skipTest("needs node and Chrome")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "index.html")
            with open(page, "w") as f:
                f.write(self.html)
            proc = subprocess.run([node, os.path.join(ROOT, "tests", "browser", "near_me.mjs"), chrome, page,
                                   str(port), f"{PIN[0]},{PIN[1]}"], capture_output=True, text=True, timeout=90)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        r = json.loads(proc.stdout.strip().splitlines()[-1])

        rows = r["rows"]
        self.assertEqual(len(rows), len(VENUES), r)
        miles = [x["miles"] for x in rows]
        located = [m for m in miles if m is not None]
        self.assertEqual(located, sorted(located), "nearest first")
        self.assertIsNone(miles[-1], "events without a location go last")
        self.assertEqual(len(located), len(VENUES) - 1)
        self.assertLess(located[0], 0.2)                      # Club Passim, around the corner
        self.assertAlmostEqual(located[-1], 4.4, delta=0.5)   # Laugh Boston in the Seaport
        self.assertIn("Sorted by distance from your pin", r["banner"])
        self.assertIn(f"({len(located)} events nearby)", r["banner"])

        # Filter change: rows of the unchecked category disappear, come back, and are reused, not rebuilt.
        self.assertIsNotNone(r["uncheckedCategory"])
        off = r["rowsWithCategoryOff"]
        self.assertTrue(off and all(x["bucket"] != r["uncheckedCategory"] for x in off), r)
        self.assertLess(len(off), len(rows))
        self.assertEqual(r["rowsRestored"], rows)
        self.assertTrue(r["reused"], "list should be built once per location")


if __name__ == "__main__":
    unittest.main()
