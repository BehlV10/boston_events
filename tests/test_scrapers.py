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
from template import render_page
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


if __name__ == "__main__":
    unittest.main()
