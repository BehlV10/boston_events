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

    def test_berklee_scraper_and_mapping(self):
        """Berklee scraper must parse events with proper date/time, sub-venues, and mapping."""
        from unittest.mock import patch
        from bs4 import BeautifulSoup
        from scrapers import scrape_berklee

        sample_html = """
        <div class="event teaser">
            <a href="/events/trio-narae-recital">
                <div class="title">Trio Narae Recital</div>
            </a>
            <div class="field--name-field-event-instance-date">
                <div class="daterange">Saturday / October 24, 2026 / 7:30 p.m.(EDT)</div>
            </div>
            <div class="fieldgroup-event-venue">
                <div class="field--name-field-event-venue-title">Berklee Performance Center</div>
                <div class="venue-address">136 Massachusetts Avenue, Boston, MA 02115</div>
            </div>
        </div>
        """
        def mock_fetch(url, ua):
            if "page=1" in url or "page=2" in url or "page=3" in url:
                return BeautifulSoup("", "html.parser")
            return BeautifulSoup(sample_html, "html.parser")

        with patch("scrapers.fetch_soup", side_effect=mock_fetch):
            events = scrape_berklee("https://www.berklee.edu/events", UA_CHROME)

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "Trio Narae Recital")
        self.assertEqual(ev["venue"], "Berklee Performance Center")
        self.assertEqual(ev["category"], "music")
        geo = resolve_event_geo(ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Berklee Performance Center")

    def test_venue_ttl_and_disk_cache(self):
        """Test per-venue TTL categorization, cache saving, and loading."""
        from scrapers import (
            _get_venue_ttl, FAST_VENUE_TTL, SLOW_VENUE_TTL, DEFAULT_VENUE_TTL,
            _venue_cache_path, _save_venue_cache, _load_venue_cache, _scrape_one
        )

        # 1. TTL checks
        self.assertEqual(_get_venue_ttl("Ticketmaster"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Do617"), FAST_VENUE_TTL)
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


    def test_is_placeholder_or_closed_event(self):
        """Ensure dummy calendar placeholders, closures, and cancellations are caught while preserving real shows."""
        from scrapers import is_placeholder_or_closed_event

        # Must be detected as placeholders / closures
        placeholders = [
            "No Event Tonight-Check Our Calendar For Upcoming Events",
            "No Live Music",
            "No Gypsy Jazz",
            "No Bluegrass Jam Due To Thanksgiving",
            "club closed",
            "Closed for the Thanksgiving Holiday",
            "Closed for the Christmas Holiday",
            "Closed for New Year's Day",
            "** Private Event **",
            "*PRIVATE EVENT*",
            "SATELLITE: Closed for a Private Event",
            "[Satellite] CLOSING at 5 pm for a Private Party",
            "CANCELED Andy Gross",
            "POSTPONED Recital: Max Ignas",
            "CANCELLED: Free Drop-in Tutoring for Teens",
            "Tbd",
            "TBA",
        ]
        for title in placeholders:
            self.assertTrue(is_placeholder_or_closed_event(title), f"Failed to detect placeholder: {title}")

        # Must NOT be detected as placeholders (real events)
        real_events = [
            "Vince Staples, Private School",
            "Diles que no me maten",
            "Straight No Chaser",
            "No Static: Celebrating the 50th anniversary of Aja",
            "No Cover Drag Bingo with Wilhelmina",
            "No Cover Karaoke w/ Miss Jade Rock",
            "Jimmy O. Yang Has No Friends Tour",
            "No Relation Hidden Sushi Bar",
            "Your Own Private Bookstore 11_20_26",
            "No Grave / Violabajo / Do Whatever Die Whenever",
            "Down in Davis Presents DOLLY PARTON SING ALONG BRUNCH (Postponed from Sept 25)",
        ]
        for title in real_events:
            self.assertFalse(is_placeholder_or_closed_event(title), f"False positive on real event: {title}")

    def test_deduplication_and_timezones(self):
        """Verify URL matching, cross-source venue deduplication, and timezone handling."""
        from template import _merge_duplicates, _clean_event_url, _normalize_title_head, group_by_date, EASTERN

        # 1. Clean event url test
        self.assertEqual(_clean_event_url("https://www.passim.org/live-music/events/will-varley/"), "https://www.passim.org/live-music/events/will-varley")
        self.assertEqual(_clean_event_url("https://www.passim.org/live-music/events/will-varley/#buy-tix?ref=1"), "https://www.passim.org/live-music/events/will-varley")
        self.assertEqual(_clean_event_url("https://www.passim.org/live-music"), "")
        self.assertEqual(_clean_event_url("https://burren.com/music.html"), "")
        self.assertEqual(_clean_event_url("https://bostonshows.org"), "")

        # 2. Will Varley deduplication (Passim vs Boston Shows at 5 PM, preserving 8 PM)
        dt_5pm = datetime(2026, 10, 19, 17, 0, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
        dt_8pm = datetime(2026, 10, 19, 20, 0, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
        passim_events = [
            {
                "name": "Will Varley (Will Lawrence opens)",
                "date": dt_5pm,
                "venue": "Club Passim",
                "price": "$30",
                "url": "https://www.passim.org/live-music/events/will-varley/",
                "source": "club passim",
            },
            {
                "name": "Will Varley",
                "date": dt_5pm,
                "venue": "Club Passim",
                "url": "https://www.passim.org/live-music/events/will-varley/",
                "source": "the boston calendar",
            },
            {
                "name": "Will Varley (Will Lawrence opens)",
                "date": dt_8pm,
                "venue": "Club Passim",
                "price": "$30",
                "url": "https://www.passim.org/live-music/events/will-varley-late-show/",
                "source": "club passim",
            },
        ]
        merged_passim = _merge_duplicates(passim_events)
        self.assertEqual(len(merged_passim), 2, "5 PM and 8 PM shows should result in 2 separate events")
        ev_5pm = next(e for e in merged_passim if "17:00" in datetime.fromisoformat(e["date"]).astimezone(EASTERN).strftime("%H:%M"))
        ev_8pm = next(e for e in merged_passim if "20:00" in datetime.fromisoformat(e["date"]).astimezone(EASTERN).strftime("%H:%M"))
        self.assertEqual(ev_5pm["price"], "$30")
        self.assertEqual(ev_5pm["name"], "Will Varley (Will Lawrence opens)")
        # Identical canonical URLs deduplicate cleanly without redundant self-referencing alt link
        self.assertEqual(len(ev_5pm.get("_alt_sources", [])), 0)

        # 3. McCarthy's Irish Session title & venue normalization deduplication
        dt_7pm = datetime(2026, 10, 19, 19, 0, tzinfo=EASTERN).astimezone(timezone.utc).isoformat()
        mccarthys_events = [
            {
                "name": "Irish Session with Eamonn Sefton and friends",
                "date": dt_7pm,
                "venue": "McCarthy's",
                "url": "https://www.mccarthystoad.com/calendar#event-1",
                "source": "do617",
            },
            {
                "name": "McCarthys Cambridge Irish Session",
                "date": dt_7pm,
                "venue": "McCarthys Cambridge",
                "url": "https://www.thebostoncalendar.com/events/mccarthys-cambridge-irish-session--345",
                "source": "the boston calendar",
            },
            {
                "name": "Live Irish Music Session @ McCarthy's",
                "date": dt_7pm,
                "venue": "McCarthy's Toad",
                "url": "https://www.mccarthystoad.com/calendar#event-2",
                "source": "mccarthy's toad",
            },
        ]
        merged_mccarthys = _merge_duplicates(mccarthys_events)
        self.assertEqual(len(merged_mccarthys), 1, "All 3 McCarthy's Irish session entries should merge into 1")
        self.assertEqual(len(merged_mccarthys[0].get("_alt_sources", [])), 2)

        # 4. Sally O'Brien's 7:30 PM timezone verification
        # 19:30 EDT = 23:30 UTC. When grouped by date, it must resolve to 19:30 EDT (7:30 PM), never 15:30 (3:30 PM).
        target_date = datetime.now(EASTERN).date() + timedelta(days=1)
        target_dt = datetime(target_date.year, target_date.month, target_date.day, 19, 30, tzinfo=EASTERN)
        sally_date_utc = target_dt.astimezone(timezone.utc).isoformat()
        venue_res = [{"venue": "Sally O'Brien's", "url": "https://www.sallyobriensbar.com/music", "events": [{"name": "The White Owls", "date": sally_date_utc, "venue": "Sally O'Brien's"}]}]
        dated, _, _ = group_by_date(venue_res)
        date_map = dict(dated)
        self.assertIn(target_date, date_map)
        item = date_map[target_date][0]
        self.assertEqual(item["_time"].hour, 19)
        self.assertEqual(item["_time"].minute, 30)

    def test_direct_music_scrapers(self):
        """Test Symphony Hall, Berklee, and The Bebop direct scrapers and verify aggregator removal."""
        from scrapers import _ALL_VENUES, scrape_symphony_hall, scrape_the_bebop, scrape_berklee
        from unittest.mock import patch, MagicMock

        # Verify Boston Shows aggregator is not in configured venues
        venue_names = [v["name"] for v in _ALL_VENUES]
        self.assertNotIn("Boston Shows", venue_names)
        self.assertIn("Symphony Hall", venue_names)
        self.assertIn("Berklee College of Music", venue_names)
        self.assertIn("The Bebop", venue_names)
        self.assertIn("Longy School of Music", venue_names)

        # 1. Test Symphony Hall scraper
        mock_typesense = {
            "hits": [
                {
                    "document": {
                        "title": "Andris Nelsons conducts Mahler 5",
                        "performance_date": 1792625400,
                        "performance_link": "https://www.bso.org/events/mahler-5",
                        "performance_venue": [{"name": "Symphony Hall"}],
                        "subhead": "BSO Masterworks Series",
                    }
                }
            ]
        }
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_typesense
            mock_get.return_value = mock_resp

            bso_events = scrape_symphony_hall("https://www.bso.org/events", "TestUA")
            self.assertEqual(len(bso_events), 1)
            self.assertEqual(bso_events[0]["name"], "Andris Nelsons conducts Mahler 5")
            self.assertEqual(bso_events[0]["venue"], "Symphony Hall")
            self.assertEqual(bso_events[0]["category"], "classical")

        # 2. Test The Bebop scraper
        mock_bebop = {
            "items": [
                {
                    "title": "Gypsy Jazz Brunch",
                    "startDate": 1793462400000,
                    "fullUrl": "/new-events/gypsy-jazz-brunch",
                    "excerpt": "Live acoustic gypsy jazz every Sunday.",
                }
            ]
        }
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_bebop
            mock_get.return_value = mock_resp

            bebop_events = scrape_the_bebop("https://thebebopboston.com/new-events", "TestUA")
            self.assertEqual(len(bebop_events), 1)
            self.assertEqual(bebop_events[0]["name"], "Gypsy Jazz Brunch")
            self.assertEqual(bebop_events[0]["venue"], "The Bebop")
            self.assertEqual(bebop_events[0]["price"], "Free")
            self.assertEqual(bebop_events[0]["category"], "music")

        # 3. Test Ticketmaster Discovery API scraper
        from scrapers import (
            scrape_ticketmaster_discovery,
            scrape_ticketweb,
            scrape_trumba,
            scrape_squarespace,
        )

        mock_tm_discovery = {
            "_embedded": {
                "events": [
                    {
                        "name": "Interpol - Antics 20th Anniversary Tour",
                        "url": "https://www.ticketmaster.com/event/01006095AABBCCDD",
                        "dates": {
                            "start": {
                                "localDate": "2026-11-15",
                                "localTime": "19:00:00",
                            }
                        },
                        "priceRanges": [
                            {"min": 45.0, "max": 75.0}
                        ],
                        "_embedded": {
                            "venues": [{"name": "Paradise Rock Club"}]
                        }
                    }
                ]
            }
        }
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_tm_discovery
            mock_get.return_value = mock_resp

            tm_events = scrape_ticketmaster_discovery("https://app.ticketmaster.com/discovery/v2/events.json?venueId=KovZpZA11JtA", "TestUA")
            self.assertEqual(len(tm_events), 1)
            self.assertEqual(tm_events[0]["name"], "Interpol - Antics 20th Anniversary Tour")
            self.assertEqual(tm_events[0]["venue"], "Paradise Rock Club")
            self.assertEqual(tm_events[0]["price"], "$45-$75")

        # 4. Test TicketWeb LD+JSON scraper
        mock_tw_html = """
        <html><head>
        <script type="application/ld+json">
        [
          {
            "@type": "MusicEvent",
            "name": "The Lemonheads Live at Sonia",
            "startDate": "2026-11-20T20:00",
            "url": "https://www.ticketweb.com/event/lemonheads-sonia-tickets/123456",
            "location": {"name": "Sonia"}
          }
        ]
        </script>
        </head><body></body></html>
        """
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = mock_tw_html
            mock_get.return_value = mock_resp

            tw_events = scrape_ticketweb("https://www.ticketweb.com/venue/sonia-cambridge-ma/435615", "TestUA")
            self.assertEqual(len(tw_events), 1)
            self.assertEqual(tw_events[0]["name"], "The Lemonheads Live at Sonia")
            self.assertEqual(tw_events[0]["venue"], "Sonia")

        # 5. Test Trumba feed scraper (Tufts / NEC)
        mock_trumba_json = [
            {
                "title": "Tufts Wind Ensemble Fall Concert",
                "startDateTime": "2026-11-18T20:00:00",
                "permaLinkUrl": "https://as.tufts.edu/music/events/fall-concert",
                "location": "Granoff Music Center"
            }
        ]
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_trumba_json
            mock_get.return_value = mock_resp

            trumba_events = scrape_trumba("https://www.trumba.com/calendars/tts-wms-managed-music.json", "TestUA")
            self.assertEqual(len(trumba_events), 1)
            self.assertEqual(trumba_events[0]["name"], "Tufts Wind Ensemble Fall Concert")
            self.assertEqual(trumba_events[0]["venue"], "Granoff Music Center")

        # 6. Test Squarespace scraper (Remnant Satellite / Portico)
        mock_sq_json = {
            "upcoming": [
                {
                    "title": "Jazz Jam Session at Satellite",
                    "startDate": 1793462400000,
                    "fullUrl": "/live/jazz-jam-session",
                }
            ]
        }
        with patch("scrapers._SESSION.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_sq_json
            mock_get.return_value = mock_resp

            sq_events = scrape_squarespace("https://www.remnantsomerville.com/live", "TestUA")
            self.assertEqual(len(sq_events), 1)
            self.assertEqual(sq_events[0]["name"], "Jazz Jam Session at Satellite")
            self.assertIn("remnantsomerville.com", sq_events[0]["url"])

        # 7. Verify all newly added venues exist in _ALL_VENUES
        for target in [
            "Paradise Rock Club", "Brighton Music Hall", "MGM Music Hall at Fenway",
            "Citizens House of Blues Boston", "Orpheum Theatre", "Leader Bank Pavilion",
            "Chevalier Theatre", "Sonia", "Scullers Jazz Club", "Regattabar",
            "Off the Rails Boston", "Mr. Dooley's", "The Green Dragon Tavern",
            "Hennessy's Bar", "UnCommon Corner", "Roundhead Brewing",
            "Tufts Music (Granoff Music Center)", "Remnant Satellite", "Portico Brewing"
        ]:
            self.assertIn(target, venue_names, f"Missing {target} in _ALL_VENUES")

    def test_music_genre_classification_and_rendering(self):
        """Verify music genre mapping, rule inference, negative filters, and HTML badge rendering."""
        from scrapers import infer_music_genre, map_native_genre, MUSIC_GENRES, EASTERN
        from template import render_page

        # 1. Test native genre mapping
        self.assertEqual(map_native_genre("Rock"), "rock_indie")
        self.assertEqual(map_native_genre("Alternative"), "rock_indie")
        self.assertEqual(map_native_genre("Hip-Hop/Rap"), "hiphop_rnb")
        self.assertEqual(map_native_genre("Trap"), "hiphop_rnb")
        self.assertEqual(map_native_genre("Pop"), "pop")
        self.assertEqual(map_native_genre("Electro Pop"), "pop")
        self.assertEqual(map_native_genre("Jazz"), "jazz_blues")
        self.assertEqual(map_native_genre("Blues"), "jazz_blues")
        self.assertEqual(map_native_genre("Folk"), "folk_trad")
        self.assertEqual(map_native_genre("Bluegrass"), "folk_trad")
        self.assertEqual(map_native_genre("Dance/Electronic"), "electronic")
        self.assertEqual(map_native_genre("Techno"), "electronic")
        self.assertEqual(map_native_genre("Classical"), "classical")
        self.assertEqual(map_native_genre("Latin"), "latin_global")
        self.assertEqual(map_native_genre("Bachata"), "latin_global")
        self.assertIsNone(map_native_genre("Undefined"))

        # 2. Test venue anchor inference
        self.assertEqual(infer_music_genre("Evening Concert", "Boston Symphony Orchestra"), "classical")
        self.assertEqual(infer_music_genre("Friday Jam", "Wally's Cafe"), "jazz_blues")
        self.assertEqual(infer_music_genre("Acoustic Night", "Club Passim"), "folk_trad")
        self.assertEqual(infer_music_genre("Industrial Night", "ManRay"), "electronic")

        # 3. Test keyword rules & negative exceptions
        self.assertEqual(infer_music_genre("Dark Star Orchestra", "Paradise Rock Club"), "rock_indie")
        self.assertEqual(infer_music_genre("Beethoven Symphony No. 5", "Random Hall"), "classical")
        self.assertEqual(infer_music_genre("Irish Trad Session", "Local Pub"), "folk_trad")
        self.assertEqual(infer_music_genre("Techno Dance Party", "Local Club"), "electronic")
        self.assertEqual(infer_music_genre("Hip-Hop Showcase", "Underground Lounge"), "hiphop_rnb")
        self.assertEqual(infer_music_genre("Maestros de la Bachata", "Music Hall"), "latin_global")
        self.assertEqual(infer_music_genre("Taylor Swift Night", "Lounge"), "pop")

        # 4. Test HTML output includes genre chips bar and sidebar group
        sample_results = [
            {
                "venue": "Wally's Cafe",
                "url": "https://wallyscafe.com",
                "events": [
                    {
                        "name": "Live Jazz Trio",
                        "date": (datetime.now(EASTERN) + timedelta(hours=3)).isoformat(),
                        "url": "https://wallyscafe.com/shows",
                        "venue": "Wally's Cafe",
                        "category": "music",
                    }
                ]
            }
        ]
        html = render_page(sample_results)
        self.assertIn("genre-chips-bar", html)
        self.assertIn("filter-group-genre", html)
        self.assertIn('data-genre="jazz_blues"', html)
        self.assertIn("Jazz &amp; Blues", html)
        self.assertIn("genre-pill", html)


if __name__ == "__main__":
    unittest.main()



