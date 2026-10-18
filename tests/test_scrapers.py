"""Boston Events — Automated Unit Test Suite.

Run via:
  python -m unittest discover tests
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scrapers import _ALL_VENUES, VENUES, UA_CHROME
from venues_geo import VENUE_COORDINATES, MIN_LAT, MAX_LAT, MIN_LNG, MAX_LNG, resolve_event_geo
from template import render_page, SUBAREAS_BY_CITY, resolve_subarea, _event_city, _event_stable_id
from scripts.add_community_event import validate_and_normalize as validate_event
from scripts.add_suggested_venue import validate_and_normalize as validate_venue


class TestBostonEvents(unittest.TestCase):

    def test_all_venues_defined(self):
        """Every venue must have a name, non-empty URL, and a callable scraper."""
        self.assertGreater(len(_ALL_VENUES), 80, "Expected at least 80 configured venues")
        for v in _ALL_VENUES:
            self.assertTrue(v.get("name"), f"Missing name in venue config: {v}")
            self.assertTrue(v.get("url"), f"Missing URL in venue config: {v['name']}")
            self.assertTrue(callable(v.get("scraper")), f"Scraper is not callable for venue: {v['name']}")

    def test_geo_bounding_box(self):
        """All curated venue coordinates must fall within Greater Boston bounding box."""
        self.assertGreater(len(VENUE_COORDINATES), 100)
        for vname, (lat, lng, neigh, addr, cname) in VENUE_COORDINATES.items():
            self.assertTrue(
                MIN_LAT <= lat <= MAX_LAT,
                f"Latitude {lat} for '{cname}' outside [{MIN_LAT}, {MAX_LAT}]"
            )
            self.assertTrue(
                MIN_LNG <= lng <= MAX_LNG,
                f"Longitude {lng} for '{cname}' outside [{MIN_LNG}, {MAX_LNG}]"
            )
            self.assertTrue(len(addr) > 0, f"Missing address for '{cname}'")

    def test_geo_resolver(self):
        """resolve_event_geo should accurately match known venues and pattern rules."""
        res_sinclair = resolve_event_geo({"venue": "The Sinclair"})
        self.assertIsNotNone(res_sinclair)
        self.assertIn("Harvard Square", res_sinclair["neighborhood"])
        self.assertEqual(res_sinclair["venue"], "The Sinclair")

        res_danis = resolve_event_geo({"venue": "Dani's Queer Bar"})
        self.assertIsNotNone(res_danis)
        self.assertEqual(res_danis["neighborhood"], "Back Bay")

        res_clubcafe = resolve_event_geo({"venue": "Club Café"})
        self.assertIsNotNone(res_clubcafe)
        self.assertEqual(res_clubcafe["neighborhood"], "South End")

        res_sunset = resolve_event_geo({"venue": "Sunset Cantina"})
        self.assertIsNotNone(res_sunset)
        self.assertIn("Allston", res_sunset["neighborhood"])

        res_feral = resolve_event_geo({"venue": "FERAL"})
        self.assertIsNotNone(res_feral)
        self.assertIn("Theater District", res_feral["neighborhood"])

        res_virtual = resolve_event_geo({"venue": "Online / Zoom"})
        self.assertIsNone(res_virtual)

    def test_community_event_validation_success(self):
        """Valid community event should normalize properly."""
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "name": "Live Acoustic Night",
            "venue": "The Burren",
            "date": tomorrow,
            "url": "https://burren.com/tickets",
            "city": "somerville",
            "price": "$10",
        }
        res = validate_event(payload)
        self.assertEqual(res["name"], "Live Acoustic Night")
        self.assertEqual(res["venue"], "The Burren")
        self.assertEqual(res["city"], "somerville")
        self.assertTrue(res["_is_community"])

    def test_community_event_validation_failures(self):
        """Invalid community events must raise ValueError."""
        # Missing name
        with self.assertRaises(ValueError):
            validate_event({"name": "", "venue": "Club", "date": "2026-10-20"})

        # Missing venue
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "", "date": "2026-10-20"})

        # Past date (>2 days ago)
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "Club", "date": "2020-01-01"})

        # Invalid URL scheme
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        with self.assertRaises(ValueError):
            validate_event({"name": "Show", "venue": "Club", "date": tomorrow, "url": "javascript:alert(1)"})

    def test_suggested_venue_validation(self):
        """Valid suggested venue should normalize properly."""
        payload = {
            "name": "The Burren",
            "url": "https://www.burren.com",
            "city": "somerville",
            "category": "music",
            "address": "247 Elm St",
            "notes": "Live traditional music",
        }
        res = validate_venue(payload)
        self.assertEqual(res["name"], "The Burren")
        self.assertEqual(res["url"], "https://www.burren.com")
        self.assertEqual(res["city"], "somerville")
        self.assertEqual(res["category"], "music")
        self.assertEqual(res["status"], "pending_review")

        # Invalid URL should raise ValueError
        with self.assertRaises(ValueError):
            validate_venue({"name": "Place", "url": "not-a-valid-url"})

    def test_template_rendering(self):
        """render_page() must render complete HTML without template exceptions."""
        mock_data = [
            {
                "venue": "The Sinclair",
                "url": "https://sinclaircambridge.com",
                "error": None,
                "events": [
                    {
                        "name": "Indie Rock Night",
                        "date": datetime.now(timezone.utc).isoformat(),
                        "url": "https://sinclaircambridge.com/event/1",
                        "venue": "The Sinclair",
                        "category": "music",
                        "price": "$25",
                    }
                ],
            }
        ]
        html = render_page(mock_data)
        self.assertIn("<!doctype html>", html.lower())
        self.assertIn("Wicked Boston Events", html)
        self.assertIn("The Sinclair", html)
        self.assertIn("Indie Rock Night", html)
        self.assertIn("modal-view-venue", html)  # Suggest a venue form present
        self.assertIn("Suggest a Venue", html)
        self.assertIn('data-subarea="harvard_sq"', html)
        self.assertIn('id="subarea-chips-bar"', html)

    def test_subarea_mapping_and_coverage(self):
        """All defined subareas must be valid and all scraped events must map cleanly."""
        self.assertIn("cambridge", SUBAREAS_BY_CITY)
        self.assertIn("somerville", SUBAREAS_BY_CITY)
        self.assertIn("boston", SUBAREAS_BY_CITY)
        self.assertIn("other", SUBAREAS_BY_CITY)

        # Test specific canonical venues
        self.assertEqual(resolve_subarea("cambridge", {"venue": "The Sinclair"})[1], "harvard_sq")
        self.assertEqual(resolve_subarea("cambridge", {"venue": "The Middle East"})[1], "central_sq")
        self.assertEqual(resolve_subarea("somerville", {"venue": "The Burren"})[1], "davis_sq")
        self.assertEqual(resolve_subarea("somerville", {"venue": "Bow Market"})[1], "union_sq")
        self.assertEqual(resolve_subarea("boston", {"venue": "Leader Bank Pavilion"})[1], "seaport_waterfront")
        self.assertEqual(resolve_subarea("boston", {"venue": "MGM Music Hall at Fenway"})[1], "fenway_kenmore")
        self.assertEqual(resolve_subarea("boston", {"venue": "Dani's Queer Bar"})[1], "back_bay")
        self.assertEqual(resolve_subarea("boston", {"venue": "Club Café"})[1], "south_end")
        self.assertEqual(resolve_subarea("boston", {"venue": "Club Cafe"})[1], "south_end")
        self.assertEqual(resolve_subarea("boston", {"venue": "Sunset Cantina"})[1], "allston_brighton")
        self.assertEqual(resolve_subarea("boston", {"venue": "FERAL", "name": "FERAL : ASSQUAKE"})[1], "theater_downtown")

        # Test full dataset coverage if events.json is present
        events_json = os.path.join(BASE_DIR, "events.json")
        if os.path.exists(events_json):
            import json
            with open(events_json, "r") as f:
                data = json.load(f)
            total_events = 0
            for v in data.get("venues", []):
                vname = v.get("venue", "")
                for e in v.get("events", []):
                    total_events += 1
                    city = _event_city(e.get("venue"), vname, e)
                    geo = resolve_event_geo(e)
                    sname, sslug = resolve_subarea(city, e, geo)
                    valid_slugs = {s[0] for s in SUBAREAS_BY_CITY[city]}
                    self.assertIn(
                        sslug,
                        valid_slugs,
                        f"Event '{e.get('name')}' at '{e.get('venue')}' produced unmapped slug '{sslug}' in '{city}'"
                    )
            self.assertGreater(total_events, 5000, "Expected at least 5000 events in events.json")

    def test_event_stable_id(self):
        """_event_stable_id must produce deterministic IDs starting with 'ev_'."""
        e1 = {"name": "Jazz Brunch", "venue": "The Beehive", "date": "2026-10-25T11:00:00"}
        e2 = {"name": "jazz brunch", "venue": "the beehive", "date": "2026-10-25T19:00:00"}
        e3 = {"name": "Rock Show", "venue": "The Sinclair", "date": "2026-10-25T20:00:00"}

        id1 = _event_stable_id(e1)
        id2 = _event_stable_id(e2)
        id3 = _event_stable_id(e3)

        self.assertTrue(id1.startswith("ev_"))
        self.assertEqual(id1, id2, "Identical normalized title, venue, and date must generate identical ID")
        self.assertNotEqual(id1, id3, "Different events must have different IDs")

    def test_upvoting_rendering_and_thresholds(self):
        """render_page should keep upvotes and popular badges hidden cleanly."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        mock_venues = [
            {
                "venue": "The Burren",
                "url": "https://burren.com",
                "error": None,
                "events": [
                    {
                        "name": "Normal Event",
                        "venue": "The Burren",
                        "date": f"{today}T18:00:00",
                        "price": "Free",
                        "url": "https://burren.com/e1",
                        "votes": 0,
                    },
                    {
                        "name": "Popular Event",
                        "venue": "The Burren",
                        "date": f"{today}T20:00:00",
                        "price": "$10",
                        "url": "https://burren.com/e2",
                        "votes": 3,
                    },
                ],
            }
        ]
        html = render_page(mock_venues)

        # Quick chips popular filter is hidden for now
        self.assertNotIn('id="quick-popular-chip"', html)
        self.assertNotIn('class="btn-upvote"', html)

    def test_server_upvotes_api(self):
        """Server API /api/upvotes and /api/upvote must correctly manage vote counts."""
        from server import app, UPVOTES_FILE
        client = app.test_client()

        # GET /api/upvotes
        resp = client.get("/api/upvotes")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.get_json(), dict)

        test_id = "ev_test_unittest_99"

        # POST /api/upvote add
        resp_add = client.post("/api/upvote", json={"id": test_id, "action": "add"})
        self.assertEqual(resp_add.status_code, 200)
        data_add = resp_add.get_json()
        self.assertTrue(data_add["success"])
        self.assertGreaterEqual(data_add["votes"], 1)

        # POST /api/upvote remove
        resp_rem = client.post("/api/upvote", json={"id": test_id, "action": "remove"})
        self.assertEqual(resp_rem.status_code, 200)
        data_rem = resp_rem.get_json()
        self.assertTrue(data_rem["success"])

        # Clean up test entry if present in upvotes.json
        if os.path.exists(UPVOTES_FILE):
            import json
            try:
                with open(UPVOTES_FILE, "r") as f:
                    u_data = json.load(f)
                if test_id in u_data:
                    del u_data[test_id]
                    with open(UPVOTES_FILE, "w") as f:
                        json.dump(u_data, f, indent=2)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
