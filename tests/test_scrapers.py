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

        res_wxi = resolve_event_geo({"venue": "Warehouse XI"})
        self.assertIsNotNone(res_wxi)
        self.assertIn("Union Square", res_wxi["neighborhood"])

        res_dt = resolve_event_geo({"venue": "Downtown Boston BID"})
        self.assertIsNotNone(res_dt)
        self.assertIn("Downtown", res_dt["neighborhood"])

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
        self.assertEqual(resolve_subarea("somerville", {"venue": "Warehouse XI"})[1], "union_sq")
        self.assertEqual(resolve_subarea("boston", {"venue": "Downtown Boston BID"})[1], "theater_downtown")

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

    def test_boston_shows_feed_and_mapping(self):
        """Boston Shows scraper must parse events with coordinates and neighborhood."""
        from unittest.mock import patch, MagicMock
        from scrapers import scrape_boston_shows
        import json

        mock_payload = {
            "venues": {
                "The Burren": {
                    "city": "Somerville",
                    "lat": 42.3963,
                    "lng": -71.1215,
                    "neighborhood": "Davis Square",
                    "address": "247 Elm St, Somerville",
                    "link": "https://burren.com"
                }
            },
            "events": [
                {
                    "venue": "The Burren",
                    "city": "Somerville",
                    "title": "Traditional Irish Session",
                    "link": "https://burren.com/irish-session",
                    "start": "2026-10-25T19:00:00",
                    "genre": "folk"
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status.return_value = None

        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_boston_shows("https://bostonshows.org/events.json", UA_CHROME)

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "Traditional Irish Session")
        self.assertEqual(ev["venue"], "The Burren")
        self.assertEqual(ev["neighborhood"], "Davis Square")
        self.assertEqual(ev["category"], "music")
        self.assertAlmostEqual(ev["lat"], 42.3963, places=3)
        self.assertAlmostEqual(ev["lng"], -71.1215, places=3)
        self.assertTrue(ev["date"].endswith("+00:00") or ev["date"].endswith("Z"))

        # Test resolve_event_geo on Boston Shows event
        geo = resolve_event_geo(ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "The Burren")

    def test_venue_ttl_and_disk_cache(self):
        """Test per-venue TTL categorization, cache saving, and loading."""
        from scrapers import (
            _get_venue_ttl, FAST_VENUE_TTL, SLOW_VENUE_TTL, DEFAULT_VENUE_TTL,
            _venue_cache_path, _save_venue_cache, _load_venue_cache, _scrape_one
        )

        # 1. TTL checks
        self.assertEqual(_get_venue_ttl("Ticketmaster"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Boston Shows"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Boston Public Library"), SLOW_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("The Sinclair"), DEFAULT_VENUE_TTL)

        # 2. Cache save and load
        test_vname = "Test Venue TTL"
        test_events = [{"name": "Test Band", "date": "2026-10-25T20:00:00Z"}]
        cpath = _venue_cache_path(test_vname)

        try:
            _save_venue_cache(test_vname, test_events, duration=0.5)
            self.assertTrue(os.path.exists(cpath))

            # Fresh load
            loaded = _load_venue_cache(test_vname, max_age=3600)
            self.assertIsNotNone(loaded)
            self.assertEqual(len(loaded["events"]), 1)
            self.assertEqual(loaded["events"][0]["name"], "Test Band")

            # Expired load
            expired = _load_venue_cache(test_vname, max_age=-1)
            self.assertIsNone(expired)

            # Test _scrape_one using cache
            mock_venue = {
                "name": test_vname,
                "url": "https://example.com",
                "ua": "TestUA",
                "scraper": lambda u, a: self.fail("Scraper should not be invoked when cache is valid!"),
                "default_category": "music"
            }
            res = _scrape_one(mock_venue, force=False)
            self.assertTrue(res.get("cached"))
            self.assertEqual(len(res["events"]), 1)
        finally:
            if os.path.exists(cpath):
                os.remove(cpath)


    def test_middle_east_scraper_and_geo(self):
        """Test Middle East Cambridge scraper extracts exact showtimes, rooms, and geocodes accurately."""
        from unittest.mock import patch
        from bs4 import BeautifulSoup
        from scrapers import scrape_middle_east, EASTERN

        sample_html = """
        <div class="tw-section">
            <a class="tw-buy-tix-btn" href="https://www.ticketweb.com/event/trivia" aria-label="Event Image Link- Trivia Night | 18 October 5:00 PM">Buy Tickets</a>
            <div class="tw-name">Trivia Night</div>
            <span class="tw-event-date">10.18</span>
            <span class="tw-event-time">Show: 5:00PM</span>
            <span class="tw-venue-name">@ Middle East - Corner/Bakery</span>
            <span class="tw-price">$15.00</span>
        </div>
        <div class="tw-section">
            <a class="tw-buy-tix-btn" href="https://www.ticketweb.com/event/rock-show" aria-label="Event Image Link- Rock Band | 18 October 9:30 PM">Buy Tickets</a>
            <div class="tw-name">Rock Band</div>
            <span class="tw-event-date">10.18</span>
            <span class="tw-event-time">Show: 9:30PM</span>
            <span class="tw-venue-name">@ Middle East - Downstairs</span>
            <span class="tw-price">$25.00</span>
        </div>
        <div class="tw-section">
            <a class="tw-buy-tix-btn" href="https://www.ticketweb.com/event/sonia-show" aria-label="Event Image Link- Indie Pop | 18 October 8:00 PM">Buy Tickets</a>
            <div class="tw-name">Indie Pop</div>
            <span class="tw-event-date">10.18</span>
            <span class="tw-event-time">Show: 8:00PM</span>
            <span class="tw-venue-name">@ Sonia</span>
            <span class="tw-price">$20.00</span>
        </div>
        """
        def mock_fetch(url, ua):
            if "page/2" in url:
                return BeautifulSoup("", "html.parser")
            return BeautifulSoup(sample_html, "html.parser")

        with patch("scrapers.fetch_soup", side_effect=mock_fetch):
            events = scrape_middle_east("https://mideastoffers.com", "TestUA")

        self.assertEqual(len(events), 3)

        # Event 1: Trivia at 5:00 PM in Corner/Bakery
        e1 = events[0]
        self.assertEqual(e1["name"], "Trivia Night")
        self.assertEqual(e1["venue"], "Middle East - Corner/Bakery")
        self.assertEqual(e1["price"], "$15.00")
        dt1 = datetime.fromisoformat(e1["date"]).astimezone(EASTERN)
        self.assertEqual(dt1.hour, 17)
        self.assertEqual(dt1.minute, 0)
        geo1 = resolve_event_geo(e1)
        self.assertIsNotNone(geo1)
        self.assertAlmostEqual(geo1["lat"], 42.3638, places=3)
        self.assertEqual(geo1["neighborhood"], "Central Square")

        # Event 2: Rock Band at 9:30 PM in Downstairs
        e2 = events[1]
        self.assertEqual(e2["name"], "Rock Band")
        self.assertEqual(e2["venue"], "Middle East - Downstairs")
        self.assertEqual(e2["price"], "$25.00")
        dt2 = datetime.fromisoformat(e2["date"]).astimezone(EASTERN)
        self.assertEqual(dt2.hour, 21)
        self.assertEqual(dt2.minute, 30)
        geo2 = resolve_event_geo(e2)
        self.assertIsNotNone(geo2)
        self.assertEqual(geo2["venue"], "Middle East - Downstairs")

        # Event 3: Sonia at 8:00 PM
        e3 = events[2]
        self.assertEqual(e3["name"], "Indie Pop")
        self.assertEqual(e3["venue"], "Sonia")
        dt3 = datetime.fromisoformat(e3["date"]).astimezone(EASTERN)
        self.assertEqual(dt3.hour, 20)
        self.assertEqual(dt3.minute, 0)
        geo3 = resolve_event_geo(e3)
        self.assertIsNotNone(geo3)
        self.assertEqual(geo3["venue"], "Sonia")


if __name__ == "__main__":
    unittest.main()
