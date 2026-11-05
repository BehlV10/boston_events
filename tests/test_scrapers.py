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

from scrapers import _ALL_VENUES, VENUES, UA_CHROME, scrape_luma
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
        self.assertIn('data-subarea="harvard_sq"', html)
        self.assertIn('id="subarea-chips-bar"', html)
        self.assertNotIn('class="quick-chips-bar"', html)
        self.assertIn('id="saved-only-chk"', html)
        self.assertIn('id="btn-copy-plan"', html)
        self.assertIn('id="cal-hint"', html)
        self.assertIn('.range-start', html)

        # Verify inline <script> has valid JavaScript syntax
        import re, shutil, subprocess, tempfile
        if shutil.which("node"):
            scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
            self.assertGreaterEqual(len(scripts), 1)
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
                tf.write(scripts[-1])
                tf_path = tf.name
            try:
                proc = subprocess.run(["node", "--check", tf_path], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"Invalid JS syntax in rendered template:\n{proc.stderr}")
            finally:
                os.remove(tf_path)

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

        fut_dt = datetime.now(timezone.utc) + timedelta(days=5)
        fut_str = fut_dt.strftime("%A / %B %-d, %Y / 7:30 p.m.(EDT)")
        sample_html = f"""
        <div class="event teaser">
            <a href="/events/trio-narae-recital">
                <div class="title">Trio Narae Recital</div>
            </a>
            <div class="field--name-field-event-instance-date">
                <div class="daterange">{fut_str}</div>
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
        fut_iso = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT20:00:00Z")
        test_events = [{"name": "Test Band", "date": fut_iso}]
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
            "Free Rock Climbing- Central Rock Cambridge",
            "Free Rock Climbing Class",
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
            self.assertEqual(bso_events[0]["category"], "music")
            self.assertEqual(bso_events[0]["genre"], "classical")

        # 2. Test The Bebop scraper
        mock_bebop = {
            "items": [
                {
                    "title": "Gypsy Jazz Brunch",
                    "startDate": int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp() * 1000),
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
                    "startDate": int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp() * 1000),
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
        self.assertIn("quick-active-genre-chip", html)
        self.assertIn("filter-group-genre", html)
        self.assertIn('data-genre="jazz_blues"', html)
        self.assertIn("Jazz &amp; Blues", html)
        self.assertIn("genre-pill", html)

    def test_luma_scraper_and_geo(self):
        """Luma Boston scraper should extract structured tech & community events with coordinates."""
        mock_payload = {
            "entries": [
                {
                    "api_id": "evt-mock1",
                    "event": {
                        "name": "Boston AI & Hard Tech Summit",
                        "start_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                        "url": "boston-ai-summit-2026",
                        "geo_address_info": {
                            "mode": "shown",
                            "address": "100 Main St",
                            "city": "Cambridge",
                            "full_address": "100 Main St, Cambridge, MA 02142",
                            "sublocality": "Kendall Square",
                        },
                        "coordinate": {"latitude": 42.3615, "longitude": -71.0855},
                    },
                    "calendar": {
                        "name": "Cambridge Tech Hub",
                        "description_short": "Premier community for builders and AI founders in Kendall Square.",
                    },
                    "hosts": [{"name": "Kendall Tech Collective"}],
                    "ticket_info": {"is_free": False, "price": {"cents": 1500}},
                },
                {
                    "api_id": "evt-mock2",
                    "event": {
                        "name": "Biotech Founder Mixer & Fireside",
                        "start_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                        "url": "biotech-mixer-oct",
                        "geo_address_info": {
                            "mode": "obfuscated",
                            "city": "Boston",
                            "sublocality": "Seaport",
                        },
                        "coordinate": {"latitude": 42.3512, "longitude": -71.0435},
                    },
                    "calendar": {"name": "Personal"},
                    "hosts": [{"name": "BioVentures"}],
                    "ticket_info": {"is_free": True},
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }

        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_payload
        mock_resp.raise_for_status = MagicMock()

        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_luma("https://lu.ma/boston", UA_CHROME)

        self.assertEqual(len(events), 2)
        ev1, ev2 = events[0], events[1]

        # Check event 1 (shown address, paid ticket, custom calendar)
        self.assertEqual(ev1["name"], "Boston AI & Hard Tech Summit")
        self.assertEqual(ev1["venue"], "100 Main St, Cambridge")
        self.assertEqual(ev1["price"], "$15")
        self.assertEqual(ev1["url"], "https://lu.ma/boston-ai-summit-2026")
        self.assertEqual(ev1["category"], "tech")  # AI summit -> default-off Tech & Startups
        self.assertEqual(ev1["lat"], 42.3615)
        self.assertEqual(ev1["lng"], -71.0855)
        self.assertIn("Hosted by Kendall Tech Collective", ev1["description"])
        self.assertIn("Kendall Square", ev1["description"])

        # Check event 2 (obfuscated RSVP address, free ticket)
        self.assertEqual(ev2["name"], "Biotech Founder Mixer & Fireside")
        self.assertEqual(ev2["venue"], "Seaport (RSVP for address)")
        self.assertEqual(ev2["price"], "Free")
        self.assertEqual(ev2["category"], "tech")  # founder mixer

        # Check geo resolution
        geo1 = resolve_event_geo(ev1)
        self.assertIsNotNone(geo1)
        self.assertEqual(geo1["lat"], 42.3615)
        self.assertEqual(geo1["lng"], -71.0855)
        self.assertEqual(geo1["neighborhood"], "Kendall Square")

    def test_improvements_bookstores_categories_and_filters(self):
        """Verify Harvard Book Store multi-month/offsite parsing, word-boundary categories, and transit/tod/star rendering."""
        from unittest.mock import patch
        from bs4 import BeautifulSoup
        from scrapers import scrape_event_list, infer_category, category_bucket, UA_CURL
        from template import resolve_transit_lines

        # 1. Word-boundary category classification (no substring false positives)
        self.assertNotEqual(infer_category("Scientific Discoveries Lecture", "Harvard Science Center"), "clubbing")
        self.assertNotEqual(infer_category("Street Photography Workshop", "Cambridge Public Library"), "music")
        self.assertNotEqual(infer_category("Historic Walking Tour of Beacon Hill", "Boston Common"), "music")
        self.assertEqual(category_bucket("classical"), "Music & nightlife")
        self.assertEqual(category_bucket("arts"), "Arts & culture")
        self.assertEqual(category_bucket("fitness"), "Play")

        # 2. Harvard Book Store multi-month & offsite venue extraction
        fut_dt = datetime.now(timezone.utc) + timedelta(days=10)
        fut_str = fut_dt.strftime("%B %-d, %Y - 7:00 pm")
        hbs_html = f"""
        <article class="event-list">
            <h3 class="event-list__title">
                <a class="event-list__title-link" href="/event/author-talk-first-parish">
                    Author Talk at First Parish Church
                </a>
            </h3>
            <div class="event-list__details--item">
                <span class="event-list__details--label">Date:</span> {fut_str}
            </div>
            <div class="event-list__body">Join us for an evening book discussion in Harvard Square.</div>
        </article>
        """
        with patch("scrapers.fetch_soup", return_value=BeautifulSoup(hbs_html, "html.parser")), \
             patch("scrapers.scrape_eventbrite_org", return_value=[]):
            hbs_events = scrape_event_list("https://www.harvard.com/events", UA_CURL)

        self.assertGreaterEqual(len(hbs_events), 1)
        self.assertEqual(hbs_events[0]["venue"], "First Parish Church")
        geo_fp = resolve_event_geo(hbs_events[0])
        self.assertIsNotNone(geo_fp)
        self.assertEqual(geo_fp["venue"], "First Parish in Cambridge")
        self.assertEqual(geo_fp["neighborhood"], "Harvard Square")

        # 3. Transit line & Time-of-Day & Starred Shortlist rendering
        self.assertIn("red", resolve_transit_lines("cambridge", "harvard_sq", hbs_events[0], geo_fp))
        html = render_page([
            {
                "venue": "Harvard Book Store",
                "url": "https://www.harvard.com/events",
                "error": None,
                "events": hbs_events,
            }
        ])
        self.assertIn('data-transit="red"', html)
        self.assertIn('data-tod="night"', html)
        self.assertIn('class="star-btn"', html)
        self.assertIn('id="saved-only-chk"', html)
        self.assertIn('data-transit="green"', html)

    def test_harvard_book_store_instore_events(self):
        """Verify Harvard Book Store in-store events parsing, Free price extraction, and feed.xml fallback."""
        from unittest.mock import patch, MagicMock
        from bs4 import BeautifulSoup
        from scrapers import scrape_event_list, UA_CURL, _normalize_and_filter_events, VENUES
        from venues_geo import resolve_event_geo

        v_hbs = next(v for v in VENUES if v["name"] == "Harvard Book Store")

        # 1. HTML in-store event with Free tag
        fut_dt = datetime.now(timezone.utc) + timedelta(days=2)
        fut_str = fut_dt.strftime("%B %-d, %Y - 7:00 pm")
        hbs_instore_html = f"""
        <article class="event-list">
            <h3 class="event-list__title">
                <a href="/event/author-talk">Paris Marx at Harvard Book Store</a>
            </h3>
            <span class="event-list__tags">
                <div class="event-tag__term"><a href="/events/tags/free">Free</a></div>
                <div class="event-tag__term"><a href="/events/tags/harvard-book-store">Harvard Book Store</a></div>
            </span>
            <div class="event-list__details--item">
                <span class="event-list__details--label">Date:</span> {fut_str}
            </div>
            <div class="event-list__details--item event-details__location--location">
                <span class="event-list__details--label">Place:</span>
                <address>Harvard Book Store<br/>1256 Massachusetts Ave<br/>Cambridge, MA 02138</address>
            </div>
            <div class="event-list__body">Discussion of new book at the bookstore.</div>
        </article>
        """
        with patch("scrapers.fetch_soup", return_value=BeautifulSoup(hbs_instore_html, "html.parser")), \
             patch("scrapers.scrape_eventbrite_org", return_value=[]):
            evs = scrape_event_list("https://www.harvard.com/events", UA_CURL)

        self.assertGreaterEqual(len(evs), 1)
        self.assertEqual(evs[0]["price"], "Free")
        self.assertIsNone(evs[0]["venue"])  # None defaults to venue name Harvard Book Store
        norm = _normalize_and_filter_events(evs, v_hbs)
        self.assertEqual(norm[0]["venue"], "Harvard Book Store")
        geo = resolve_event_geo(norm[0])
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Harvard Square")
        self.assertEqual(geo["venue"], "Harvard Book Store")

        # 2. Resilient XML feed fallback when HTML fails
        xml_feed = f"""
        <rss version="2.0">
            <channel>
                <item>
                    <title>Christy Scott Cashman at Harvard Book Store</title>
                    <eventDate>{fut_dt.strftime('%A, %B %-d, %Y - 07:00pm')}</eventDate>
                    <location>Harvard Book Store 1256 Massachusetts Ave Cambridge, MA 02138-3820</location>
                    <link>https://www.harvard.com/event/christy-scott-cashman</link>
                    <description>Harvard Book Store welcomes author Christy Scott Cashman for a talk.</description>
                </item>
            </channel>
        </rss>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = xml_feed
        with patch("scrapers.fetch_soup", side_effect=Exception("Cloudflare 403")), \
             patch("subprocess.run", return_value=MagicMock(stdout="")), \
             patch("scrapers._SESSION.get", return_value=mock_resp), \
             patch("scrapers.scrape_eventbrite_org", return_value=[]):
            evs_fallback = scrape_event_list("https://www.harvard.com/events", UA_CURL)

        self.assertGreaterEqual(len(evs_fallback), 1)
        self.assertEqual(evs_fallback[0]["name"], "Christy Scott Cashman at Harvard Book Store")
        self.assertEqual(evs_fallback[0]["price"], "Free")
        self.assertIsNone(evs_fallback[0]["venue"])

    def test_scrapers_lizard_lounge_improv_asylum_passim_winery(self):
        """Verify scrapers for Lizard Lounge, Improv Asylum, Club Passim, and City Winery."""
        from scrapers import (
            scrape_lizard_lounge,
            scrape_improv_asylum,
            scrape_club_passim,
            scrape_city_winery,
            UA_CHROME,
        )
        from unittest.mock import patch, MagicMock

        # 1. Lizard Lounge test with HTML calendar mock
        lizard_html = """
        <html><body>
        <article class="tribe-events-calendar-month__calendar-event">
            <h3 class="tribe-events-calendar-month__calendar-event-title">
                <a href="https://lizardloungeclub.com/event/test-band/">Test Band at Lizard Lounge</a>
            </h3>
            <time datetime="2026-11-15">November 15</time>
            <time datetime="21:00">9:00 pm</time>
            <div>Admission: $15.00</div>
        </article>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = lizard_html
        with patch("scrapers._SESSION.get", return_value=mock_resp), \
             patch("scrapers.scrape_ical", return_value=[]):
            lz_events = scrape_lizard_lounge("https://lizardloungeclub.com", UA_CHROME)

        self.assertEqual(len(lz_events), 1)
        self.assertEqual(lz_events[0]["name"], "Test Band at Lizard Lounge")
        self.assertEqual(lz_events[0]["price"], "$15.00")
        self.assertEqual(lz_events[0]["venue"], "Lizard Lounge")
        self.assertEqual(lz_events[0]["category"], "music")

        # 2. Improv Asylum test with JSON-LD schema mock
        ia_html = """
        <html><head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@graph": [
            {
              "@type": "Event",
              "@id": "https://www.tixr.com/groups/improvasylum/events/main-stage-123",
              "name": "Main Stage Show: Nightmare on Hanover Street",
              "startDate": "2026-11-20T19:30:00-05:00",
              "offers": {"lowPrice": "35"}
            }
          ]
        }
        </script>
        </head><body></body></html>
        """
        mock_ia_resp = MagicMock()
        mock_ia_resp.status_code = 200
        mock_ia_resp.text = ia_html
        mock_ia_resp.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=mock_ia_resp):
            ia_events = scrape_improv_asylum("https://calendar.improvasylum.com", UA_CHROME)

        self.assertEqual(len(ia_events), 1)
        self.assertEqual(ia_events[0]["name"], "Main Stage Show: Nightmare on Hanover Street")
        self.assertEqual(ia_events[0]["venue"], "Improv Asylum")
        self.assertEqual(ia_events[0]["price"], "$35")
        self.assertEqual(ia_events[0]["category"], "comedy")


    def test_do617_modern_markup(self):
        """Verify scrape_do617 accurately parses modern Svelte card markup."""
        from scrapers import scrape_do617, UA_CHROME
        from unittest.mock import patch, MagicMock

        sample_html = """
        <html><body>
        <div class="standard-card svelte-xyz compact" data-card-kind="event">
          <a class="card-link" href="./events/2026/11/15/indie-rock-night">
            <div class="details">
              <h3>Indie Rock Night at Brighton Music Hall</h3>
              <p class="date">Tomorrow | 8 pm</p>
              <p>Brighton Music Hall</p>
              <p class="enrichment">Music • Allston / Brighton</p>
            </div>
          </a>
        </div>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_html
        mock_resp.content = sample_html.encode("utf-8")

        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_do617("https://do617.com/events", UA_CHROME)

        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Indie Rock Night at Brighton Music Hall")
        self.assertEqual(events[0]["venue"], "Brighton Music Hall")
        self.assertIn("https://do617.com/events/2026/11/15/indie-rock-night", events[0]["url"])

    def test_second_sun_rising_abbreviated_date(self):
        """Verify scrape_second_sun_rising accurately parses abbreviated prose dates."""
        from scrapers import scrape_second_sun_rising, UA_CHROME
        from bs4 import BeautifulSoup
        from unittest.mock import patch

        prose_html = """
        <html><body>
        <article>
          <h2>When? Where? How much?</h2>
          <p>November 5-8th is Little Dipper Fusion weekend! Four nights of dancing! Sunday Nov 8th we’ll be at Cambridge Masonic Hall at 1950 Mass Ave.</p>
          <p>Admission is pay-what-you-can.</p>
          <p>Our December event will be December 13th, and we’ll be at First Street Market, 59 First Street in Cambridge. We expect to return to the Masonic Hall for our January 10 2027 dance.</p>
        </article>
        </body></html>
        """
        with patch("scrapers.fetch_soup", return_value=BeautifulSoup(prose_html, "html.parser")):
            events = scrape_second_sun_rising("https://secondsunrising.com/", UA_CHROME)

        # Nov 5 (start of a date range) and the tentative January date are skipped
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["name"], "Second Sun Rising — Fusion Dance")
        self.assertEqual(events[0]["venue"], "Cambridge Masonic Hall")
        self.assertEqual(events[1]["venue"], "First Street Market")
        self.assertEqual(events[1]["address"], "59 First St, Cambridge")
        from scrapers import EASTERN
        local_dt = datetime.fromisoformat(events[0]["date"]).astimezone(EASTERN)
        self.assertEqual(local_dt.month, 11)
        self.assertEqual(local_dt.day, 8)

    def test_venue_ttl_tiers(self):
        """Verify fast, slow, and default cache TTL tiers based on venue characteristics."""
        from scrapers import _get_venue_ttl, FAST_VENUE_TTL, SLOW_VENUE_TTL, DEFAULT_VENUE_TTL

        self.assertEqual(_get_venue_ttl("Eventbrite Boston"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("The Boston Calendar"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Do617"), FAST_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Luma Boston"), FAST_VENUE_TTL)

        self.assertEqual(_get_venue_ttl("Boston Public Library"), SLOW_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Harvard Art Museums"), SLOW_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("Growing Center"), SLOW_VENUE_TTL)

        self.assertEqual(_get_venue_ttl("The Sinclair"), DEFAULT_VENUE_TTL)
        self.assertEqual(_get_venue_ttl("The Burren"), DEFAULT_VENUE_TTL)

    def test_scrape_one_resilient_fallback(self):
        """When live scraping raises an exception, _scrape_one should safely return fallback events with error=None."""
        from scrapers import _scrape_one, _last_known_good
        from unittest.mock import patch

        v_config = {
            "name": "Test Resilient Venue",
            "url": "https://testresilient.com/events",
            "scraper": lambda u, ua: (_ for _ in ()).throw(ConnectionError("Simulated network drop")),
            "ua": "TestUA",
        }
        _last_known_good["Test Resilient Venue"] = [
            {
                "name": "Cached Showcase",
                "date": "2026-11-20T20:00:00Z",
                "url": "https://testresilient.com/event/1",
                "venue": "Test Resilient Venue",
            }
        ]

        res = _scrape_one(v_config, force=True)
        self.assertEqual(res["venue"], "Test Resilient Venue")
        self.assertEqual(len(res["events"]), 1)
        self.assertEqual(res["events"][0]["name"], "Cached Showcase")
        self.assertIsNone(res["error"])
        self.assertTrue(res["fallback"])
        self.assertTrue(res["cached"])

    def test_scrape_dorchester_brewing(self):
        """Verify Dorchester Brewing Company parser extracts events, dates, and categories."""
        from scrapers import scrape_dorchester_brewing
        from unittest.mock import patch, MagicMock

        mock_html = """
        <div class="tribe-events-pro-photo__event">
            <article>
                <h3><a href="https://www.dorchesterbrewing.com/events/event/trivia-night/">General Trivia Night</a></h3>
                <div class="tribe-event-time">November 10, 2026 7:00 pm - 9:00 pm</div>
            </article>
        </div>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_dorchester_brewing("https://www.dorchesterbrewing.com/events/", "test_ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "General Trivia Night")
        self.assertEqual(events[0]["category"], "trivia")
        self.assertEqual(events[0]["price"], "Free")
        self.assertEqual(events[0]["venue"], "Dorchester Brewing Company")
        self.assertIn("2026-11-1", events[0]["date"])

    def test_scrape_huntington_theatre(self):
        """Verify Huntington Theatre scraper parses season productions and run dates."""
        from scrapers import scrape_huntington_theatre
        from unittest.mock import patch, MagicMock

        mock_html = """
        <div class="c-event-card">
            <h3>The Lehman Trilogy</h3>
            <div class="dates">Nov 15 – Dec 20, 2026</div>
            <a href="/season/the-lehman-trilogy">Buy Tickets</a>
        </div>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_huntington_theatre("https://www.huntingtontheatre.org/season/", "test_ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "The Lehman Trilogy")
        self.assertEqual(events[0]["category"], "theater")
        self.assertEqual(events[0]["venue"], "The Huntington Theatre")
        self.assertEqual(events[0]["url"], "https://www.huntingtontheatre.org/season/the-lehman-trilogy")
        self.assertIn("2026-12-2", events[0]["date"])

    def test_scrape_ccae(self):
        """Verify CCAE scraper extracts community workshops and classes."""
        from scrapers import scrape_ccae
        from unittest.mock import patch, MagicMock

        mock_html = """
        <a class="card-image" href="https://ccae.org/happenings/events/watercolor-workshop">
            <h3>Intro to Watercolor Painting</h3>
            <div class="date-time">Nov 12 | 6:00 pm</div>
        </a>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_ccae("https://ccae.org/events", "test_ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "CCAE: Intro to Watercolor Painting")
        self.assertEqual(events[0]["category"], "art")
        self.assertEqual(events[0]["venue"], "Cambridge Center for Adult Education (CCAE)")
        self.assertIn("2026-11-12", events[0]["date"])


    def test_88_club_resolution_and_geocoding(self):
        """Verify The 88 Club maps to Boston, Back Bay, and resolves correct coordinates."""
        from template import _event_city, resolve_subarea
        from venues_geo import resolve_event_geo

        ev1 = {"name": "Comedy at The 88 Club (Free!)", "venue": "The 88 Club", "_source_venue": "The Boston Calendar"}
        geo1 = resolve_event_geo(ev1)
        self.assertIsNotNone(geo1)
        self.assertEqual(geo1["venue"], "The 88 Club")
        self.assertEqual(geo1["neighborhood"], "Back Bay")
        city1 = _event_city("The 88 Club", "The Boston Calendar", ev1)
        self.assertEqual(city1, "boston")
        sub_name1, sub_slug1 = resolve_subarea(city1, ev1, geo1)
        self.assertEqual(sub_slug1, "back_bay")
        self.assertEqual(sub_name1, "Back Bay & Copley")

        ev2 = {"name": "Free Comedy Show at The 88 Club - Boston, MA", "venue": "@BOSCOMEDYSHOWS", "_source_venue": "Do617"}
        geo2 = resolve_event_geo(ev2)
        self.assertIsNotNone(geo2)
        self.assertEqual(geo2["venue"], "The 88 Club")
        self.assertEqual(geo2["neighborhood"], "Back Bay")

    def test_calderwood_and_central_square_theater_geocoding(self):
        """Verify Calderwood Pavilion and Central Square Theater resolve to correct neighborhoods and coordinates."""
        from venues_geo import resolve_event_geo

        ev_c = {"name": "The Wash", "venue": "Calderwood Pavilion"}
        geo_c = resolve_event_geo(ev_c)
        self.assertIsNotNone(geo_c)
        self.assertEqual(geo_c["venue"], "Calderwood Pavilion")
        self.assertEqual(geo_c["neighborhood"], "South End")

        ev_t = {"name": "The Getaway Driver", "venue": "Central Square Theater"}
        geo_t = resolve_event_geo(ev_t)
        self.assertIsNotNone(geo_t)
        self.assertEqual(geo_t["venue"], "Central Square Theater")
        self.assertEqual(geo_t["neighborhood"], "Central Square")

        ev_bso = {"name": "Haydn's The Creation", "venue": "Boston Symphony Orchestra"}
        geo_bso = resolve_event_geo(ev_bso)
        self.assertIsNotNone(geo_bso)
        self.assertEqual(geo_bso["venue"], "Symphony Hall")
        self.assertEqual(geo_bso["neighborhood"], "Fenway / Symphony")

    def test_scrape_harvard_pogo_meetups(self):
        """Verify Harvard PoGO scraper parses official Raid Days and Community Days."""
        from scrapers import scrape_harvard_pogo_meetups
        from unittest.mock import patch, MagicMock

        mock_html = """
        <a class="event-item-link" href="/events/chandelure-super-mega-raid-day-2026/">
          <span class="event-tag-badge">Raid Day</span>
          <h2>Chandelure Super Mega Raid Day</h2>
          <div class="event-countdown" data-countdown="2026-10-31T17:00:00" data-countdown-to="end"></div>
        </a>
        <a class="event-item-link" href="/events/november-communityday2026/">
          <span class="event-tag-badge">Community Day</span>
          <h2>Pawniard Community Day</h2>
          <div class="event-countdown" data-countdown="2026-11-21T14:00:00" data-countdown-to="start"></div>
        </a>
        """
        mock_resp = MagicMock()
        mock_resp.text = mock_html
        with patch("scrapers._SESSION.get", return_value=mock_resp):
            events = scrape_harvard_pogo_meetups("https://campfire.nianticlabs.com", "test_ua")
        self.assertEqual(len(events), 2)
        self.assertIn("Chandelure Super Mega Raid Day", events[0]["name"])
        self.assertEqual(events[0]["venue"], "Harvard Square")
        self.assertEqual(events[0]["category"], "gaming")
        self.assertEqual(events[0]["url"], "https://apps.apple.com/us/app/niantic-campfire/id1608154490")
        self.assertIn("Pawniard Community Day", events[1]["name"])
        self.assertEqual(events[1]["venue"], "Harvard Square")

    def test_utility_event_categorization(self):
        """ESOL, ELL, citizenship, career fairs, studio clinics, and civic services must be categorized as 'services' and bucketed in 'Classes & Services'."""
        from scrapers import infer_category, category_bucket, is_utility_event

        test_titles = [
            "Beginner ESOL Class (Central Square)",
            "High Beginner ESOL (Valente)",
            "English Conversation Practice, Intermediate (O'Neill)",
            "Beginning English Class (Valente)",
            "Online Beginner ELL Class",
            "Online Intermediate ELL Conversation Group",
            "Intermediate English Grammar and Conversation Practice",
            "Citizenship Preparation Classes (Central Square)",
            "Fall 2026 English for U.S. Citizenship",
            "Tech for All: Meet Your Device Workshop",
            "Drop-in Tech Help at the Library (Central Square)",
            "Library Social Work: Drop-in Hours at West",
            "Free Drop-in Tutoring for Teens (Main)",
            "General Exercise - Holland Street (Council on Aging)",
            # Group A: Commercial Language Courses
            "BASE: Language Courses in Boston",
            "Portuguese Class for Beginners",
            "Spanish Classes - Multi-Week",
            # Group B: Professional Certifications / Mandatory Trainings
            "Strength & Group Fitness Teacher Training",
            "Adult & Pediatric First Aid / CPR / AED Course",
            "Overdose Prevention & Narcan Training",
            "Food Safety Manager Certification Course",
            # Group C: Career & Job Fairs
            "Boston Job Fair November 4, 2026",
            "Career Fairs Boston 2026",
            "One-on-One Tech Help & Resume Help",
            # Group D: Studio Rentals & Equipment Clinics
            "Craft Workshop: Machine Maintenance - Clinic",
            "Craft Workshop: Sew by the Hour Studio Time",
            "Craft Workshop: Longarm Studio Time",
            "Craft Workshop: Youth School of Sewing - 6 sessions",
            "8-Week Clown Class with Deby Xiadani",
            # Group E: Makerspace Technical Machine Trainings
            "3D Printing 101",
            "Laser Cutting 101",
            "Hive Safety Training",
            "Studio Recording 101",
        ]
        for title in test_titles:
            self.assertTrue(is_utility_event(title), f"Failed utility match: {title}")
            cat = infer_category(title, "Cambridge Public Library")
            self.assertEqual(cat, "services", f"Failed category inference for: {title}")
            bucket = category_bucket(cat)
            self.assertEqual(bucket, "Classes & Services", f"Failed bucket lookup for: {title}")

        # Creative workshops, social experiences, and music sessions must NOT be matched as utility events
        creative_and_music_titles = [
            "Croissant Workshop at The Foundry",
            "Sip & Paint: Fall Workshop",
            "Friendsgiving Candle Workshop",
            "World Class traditional music",
            "Traditional Irish Music Sessions at The Druid",
            "Sunday Sessions with Special Guests",
            "Blues Jam Session",
            "Bachata Social Dance",
        ]
        for title in creative_and_music_titles:
            self.assertFalse(is_utility_event(title), f"False positive utility match for: {title}")
            cat = infer_category(title, "The Druid")
            self.assertNotEqual(cat, "services", f"Incorrectly inferred as services: {title}")

    def test_the_platform_kendall(self):
        """The Platform Kendall venue, geo resolution, and Algolia scraper verification."""
        from scrapers import _ALL_VENUES, scrape_the_platform_kendall
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        # Venue registered in _ALL_VENUES
        matching = [v for v in _ALL_VENUES if v["name"] == "The Platform Kendall"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["url"], "https://www.theplatformkendall.org/event-listing/")

        # Geo & transit resolution
        mock_ev = {
            "name": "The Platform Opening Day",
            "venue": "The Platform Kendall",
            "_source_venue": "The Platform Kendall",
        }
        geo = resolve_event_geo(mock_ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "The Platform Kendall")
        self.assertEqual(geo["neighborhood"], "Kendall Square")
        self.assertAlmostEqual(geo["lat"], 42.3637, places=3)
        self.assertAlmostEqual(geo["lng"], -71.0827, places=3)

        city = _event_city(mock_ev["venue"], mock_ev["_source_venue"], mock_ev)
        self.assertEqual(city, "cambridge")

        sub_name, sub_slug = resolve_subarea(city, mock_ev, geo)
        self.assertEqual(sub_slug, "kendall_mit")

        transit = resolve_transit_lines(city, sub_slug, mock_ev, geo)
        self.assertEqual(transit, "red")

    def test_middlesex_lounge(self):
        """Middlesex Lounge venue, scraper, geo resolution, and red line transit verification."""
        from scrapers import _ALL_VENUES, scrape_middlesex
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        # Venue registered in _ALL_VENUES
        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Middlesex Lounge", names)

        # Scraper returns events
        events = scrape_middlesex("https://www.msexcambridge.com", UA_CHROME)
        self.assertGreaterEqual(len(events), 3)

        first = events[0]
        self.assertIn("name", first)
        self.assertIn("date", first)
        self.assertEqual(first["venue"], "Middlesex Lounge")
        self.assertEqual(first["category"], "clubbing")

        # Geo, city, subarea, transit verification
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Middlesex Lounge")
        self.assertEqual(geo["neighborhood"], "Central Square")
        self.assertAlmostEqual(geo["lat"], 42.3619, places=3)
        self.assertAlmostEqual(geo["lng"], -71.0988, places=3)

        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "cambridge")

        sub_name, sub_slug = resolve_subarea(city, first, geo)
        self.assertEqual(sub_slug, "central_sq")

        transit = resolve_transit_lines(city, sub_slug, first, geo)
        self.assertEqual(transit, "red")

    def test_roxys_arcade(self):
        """Roxy's Arcade / A4cade venue, scraper, geo resolution, and red line transit verification."""
        from scrapers import _ALL_VENUES, scrape_roxys_arcade
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Roxy's Arcade", names)

        events = scrape_roxys_arcade("https://www.roxysarcade.com/event-schedule", UA_CHROME)
        self.assertGreaterEqual(len(events), 10)

        first = events[0]
        self.assertEqual(first["venue"], "Roxy's Arcade")
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Roxy's Arcade")
        self.assertEqual(geo["neighborhood"], "Central Square")

        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "cambridge")

        sub_name, sub_slug = resolve_subarea(city, first, geo)
        self.assertEqual(sub_slug, "central_sq")
        self.assertEqual(resolve_transit_lines(city, sub_slug, first, geo), "red")

    def test_phoenix_landing(self):
        """The Phoenix Landing venue, scraper, geo resolution, and red line transit verification."""
        from scrapers import _ALL_VENUES, scrape_phoenix_landing
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("The Phoenix Landing", names)

        events = scrape_phoenix_landing("https://www.thephoenixlanding.com/events", UA_CHROME)
        self.assertGreaterEqual(len(events), 10)

        first = events[0]
        self.assertEqual(first["venue"], "The Phoenix Landing")
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "The Phoenix Landing")
        self.assertEqual(geo["neighborhood"], "Central Square")

        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "cambridge")

        sub_name, sub_slug = resolve_subarea(city, first, geo)
        self.assertEqual(sub_slug, "central_sq")
        self.assertEqual(resolve_transit_lines(city, sub_slug, first, geo), "red")

    def test_club_cafe(self):
        """Club Café venue, scraper, geo resolution, and South End orange line transit verification."""
        from scrapers import _ALL_VENUES, scrape_club_cafe
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Club Café", names)

        events = scrape_club_cafe("https://www.clubcafe.com/full-calendar/", UA_CHROME)
        self.assertGreaterEqual(len(events), 15)

        first = events[0]
        self.assertEqual(first["venue"], "Club Café")
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Club Café")
        self.assertEqual(geo["neighborhood"], "South End")

        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "boston")

        sub_name, sub_slug = resolve_subarea(city, first, geo)
        self.assertEqual(sub_slug, "south_end")
        self.assertEqual(resolve_transit_lines(city, sub_slug, first, geo), "orange")

    def test_bow_market_upstairs(self):
        """Bow Market / Upstairs at Bow scraper verification."""
        from scrapers import scrape_bow_market
        from venues_geo import resolve_event_geo
        from template import _event_city, resolve_subarea, resolve_transit_lines

        events = scrape_bow_market("https://tickettailor.com/events/bowmarket", UA_CHROME)
        self.assertGreaterEqual(len(events), 3)
        first = events[0]
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Union Square")
        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "somerville")

    def test_harvard_art_museums(self):
        """Harvard Art Museums scraper and geo verification."""
        from scrapers import _ALL_VENUES, scrape_harvard_art_museums
        from venues_geo import resolve_event_geo
        from template import _event_city

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Harvard Art Museums", names)

        events = scrape_harvard_art_museums("https://harvardartmuseums.org/calendar", UA_CHROME)
        self.assertGreaterEqual(len(events), 20)
        first = events[0]
        self.assertEqual(first["venue"], "Harvard Art Museums")
        self.assertEqual(first["category"], "art")

        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Harvard Square")
        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "cambridge")

    def test_lyric_stage_company(self):
        """Lyric Stage Company scraper and geo verification."""
        from scrapers import _ALL_VENUES, scrape_lyric_stage
        from venues_geo import resolve_event_geo
        from template import _event_city

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Lyric Stage Company", names)

        events = scrape_lyric_stage("https://lyricstage.com/whats-on/", UA_CHROME)
        self.assertGreaterEqual(len(events), 10)
        first = events[0]
        self.assertEqual(first["venue"], "Lyric Stage Company")
        self.assertEqual(first["category"], "theater")

        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Back Bay")
        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "boston")

    def test_celebrity_series(self):
        """Celebrity Series of Boston scraper and geo verification."""
        from scrapers import _ALL_VENUES, scrape_celebrity_series
        from venues_geo import resolve_event_geo
        from template import _event_city

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Celebrity Series of Boston", names)

        events = scrape_celebrity_series("https://www.celebrityseries.org/live-performances/performance-event-calendar/", UA_CHROME)
        self.assertGreaterEqual(len(events), 5)
        first = events[0]
        self.assertTrue(first["venue"].startswith("Celebrity Series"))
        self.assertEqual(first["category"], "music")

        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "boston")

    def test_boston_lyric_opera(self):
        """Boston Lyric Opera Tribe REST scraper and geo verification."""
        from scrapers import _ALL_VENUES, scrape_tribe_rest
        from venues_geo import resolve_event_geo
        from template import _event_city

        names = [v["name"] for v in _ALL_VENUES]
        self.assertIn("Boston Lyric Opera", names)

        events = scrape_tribe_rest("https://blo.org/wp-json/tribe/events/v1/events", UA_CHROME, default_venue="Boston Lyric Opera", default_category="music")
        self.assertGreaterEqual(len(events), 5)
        first = events[0]
        geo = resolve_event_geo(first)
        self.assertIsNotNone(geo)
        city = _event_city(first["venue"], first.get("_source_venue") or first["venue"], first)
        self.assertEqual(city, "boston")


    def test_generic_party_words_defer_to_specific_categories(self):
        """'Party' alone shouldn't make an event nightlife when the title says otherwise."""
        from scrapers import infer_category
        cases = [
            ("Puzzle Party (Main)", "Cambridge Public Library (Main Library)", "gaming"),
            ("Paint Party at the Library (O'Connell)", "Cambridge Public Library", "art"),
            ("Watch Party: Boston Celtics vs. Atlanta Hawks", "Roundhead Brewing", "sports"),
            ("Patriots Watch Party @ Eastern Edge Food Hall", "Eastern Edge Food Hall", "sports"),
            ("Dumpling Making Party In Massachusetts (Fridays)", "The Historic Windsor Inn", "food"),
            # Real nightlife stays clubbing, even at venues whose names hit other categories
            ("90s PARTY", "Middlesex Lounge", "clubbing"),
            ("Saturday Night House Party", "Club Café", "clubbing"),
            ("1 year of hyperlinked: a girl edm + hyperpop party", "The Sinclair", "clubbing"),
            # Band named "Puzzle" is not a puzzle event; the venue makes it music
            ("Puzzle", "Paradise Rock Club", "music"),
        ]
        for name, venue, expected in cases:
            self.assertEqual(infer_category(name, venue), expected, name)

    def test_fuzzy_cross_source_duplicates_merge(self):
        """Same show listed by two sources with formatting differences collapses to one."""
        from template import _merge_duplicates, EASTERN
        from datetime import datetime

        def ev(name, venue, src, hh, mm=0):
            return {"name": name, "venue": venue, "_source_venue": src,
                    "_time": datetime(2026, 11, 6, hh, mm, tzinfo=EASTERN), "url": f"https://{src.replace(' ', '').lower()}.example/{name}"}

        same = [
            (ev("half•alive", "The Sinclair", "The Sinclair", 19), ev("halfalive", "The Sinclair - Cambridge", "SeatGeek", 20)),
            (ev("MPH", "Royale Boston", "Ticketmaster", 22), ev("MPH", "Royale - Boston", "SeatGeek", 22)),
            (ev("Haydn's The Creation", "Symphony Hall", "Symphony Hall", 19, 30),
             ev("Boston Symphony Orchestra - Haydn's The Creation", "Boston Symphony Hall", "SeatGeek", 19, 30)),
            (ev("Le Vent du Nord", "Somerville Theatre", "The Boston Calendar", 20),
             ev("Global Arts Live presents: LE VENT DU NORD", "Somerville Theatre", "Somerville Theatre", 20)),
            (ev("ADULT. & A Place To Bury Strangers", "The Sinclair", "The Sinclair", 19, 30),
             ev("Adult. w/ A Place To Bury Strangers", "The Sinclair Music Hall", "Ticketmaster", 20, 30)),
        ]
        for a, b in same:
            self.assertEqual(len(_merge_duplicates([a, b])), 1, f"{a['name']} / {b['name']}")

        different = [
            # A "- Boston" suffix must not make every "Boston ..." title a prefix match
            (ev("Los Angeles Philharmonic - Boston", "Symphony Hall", "SeatGeek", 20),
             ev("Boston Modern Orchestra Project: Delight of Muses", "Symphony Hall", "The Boston Calendar", 20)),
            # Different library branches are different places
            (ev("Sing-Along (Valente)", "Cambridge Public Library (Valente Branch)", "Cambridge Public Library", 10),
             ev("Singalong with Matt Heaton at West", "Somerville Public Library (West Branch)", "Somerville Public Library", 10)),
            # Same venue, same organizer prefix, different events
            (ev("MFA: Gallery Highlights", "Museum of Fine Arts (MFA)", "Do617", 12),
             ev("MFA: Ask a Conservator", "Museum of Fine Arts (MFA)", "Museum of Fine Arts", 13)),
        ]
        for a, b in different:
            self.assertEqual(len(_merge_duplicates([a, b])), 2, f"{a['name']} / {b['name']}")

    def test_geo_prefers_event_venue_over_presenter(self):
        """A Celebrity Series show at Arrow Street Arts is pinned there, not at Symphony Hall."""
        from venues_geo import resolve_event_geo
        g = resolve_event_geo({"name": "William Basinski", "venue": "Arrow Street Arts",
                               "_source_venue": "Celebrity Series of Boston"})
        self.assertEqual(g["venue"], "Arrow Street Arts")

    def test_city_from_scraped_address(self):
        """Venues with no named rule get their city from the scraped address, not 'Outer Suburbs'."""
        from template import _event_city
        cases = [
            ({"venue": "St. Peter's Episcopal Church", "address": "838 Mass Ave., Cambridge", "locality": "Cambridge"}, "cambridge"),
            ({"venue": "A Hall", "address": "760 Boylston St, Boston", "locality": "Boston"}, "boston"),
            ({"venue": "B Hall", "address": "5 Elm St", "postal_code": "02144"}, "somerville"),
            ({"venue": "C Hall", "address": "1 Kendall Sq, Cambridge, MA 02139"}, "cambridge"),
            ({"venue": "D Hall", "address": "12 Main St, Waltham, MA 02451", "locality": "Waltham"}, "other"),
        ]
        for e, want in cases:
            self.assertEqual(_event_city(e["venue"], "The Boston Calendar", e), want, e)

    def test_boston_calendar_title_and_price_repairs(self):
        from scrapers import _BC_FREE_RE, _title_from_ticket_slug, _bc_apply_details
        self.assertIsNone(_BC_FREE_RE.search("Stress Free Week"))
        self.assertIsNone(_BC_FREE_RE.search("Gluten-Free Baking Class"))
        self.assertIsNotNone(_BC_FREE_RE.search("FREE Yoga in the Park"))
        self.assertEqual(_title_from_ticket_slug("https://www.eventbrite.com/e/author-talk-with-seamus-boshell-tickets-2003750302093"),
                         "Author Talk with Seamus Boshell")
        e = {"name": "Book Event", "price": "Free", "_price_from_title": True}
        _bc_apply_details(e, {"url": "https://www.eventbrite.com/e/author-talk-with-seamus-boshell-tickets-2003750302093",
                              "price": "$10", "addr": {"street": "200 New Boston Dr", "locality": "Canton"}})
        self.assertEqual(e["name"], "Author Talk with Seamus Boshell")
        self.assertEqual(e["price"], "$10")
        self.assertEqual(e["locality"], "Canton")

    def test_meetup_placeholder_venue_takes_real_venue_and_not_weekly(self):
        """A Meetup group hides its venue (venue = group name); a listing elsewhere supplies the real one,
        and the same title at a different bar each week isn't flagged as weekly-recurring."""
        from template import group_by_date, compute_recurring
        grp = "Hey Siri: Make Friends After College"
        venues = [
            {"venue": grp, "url": "https://www.meetup.com/hey-siri/events/", "events": [
                {"name": "Skip the Small Talk", "date": "2026-11-04T19:00:00-05:00", "url": "https://www.meetup.com/hey-siri/events/1/", "venue": grp, "venue_unknown": True},
                {"name": "Skip the Small Talk", "date": "2026-11-11T19:00:00-05:00", "url": "https://www.meetup.com/hey-siri/events/2/", "venue": grp, "venue_unknown": True},
            ]},
            {"venue": "Trident Booksellers & Cafe", "url": "https://tridentbookscafe.com/events", "events": [
                {"name": "Skip the Small Talk", "date": "2026-11-04T19:00:00-05:00", "url": "https://tridentbookscafe.com/events/stst", "venue": "Trident Booksellers & Cafe"},
            ]},
        ]
        dated, _, _ = group_by_date(venues)
        nov4 = [e for d, es in dated if str(d) == "2026-11-04" for e in es]
        self.assertEqual(len(nov4), 1)
        self.assertEqual(nov4[0]["venue"], "Trident Booksellers & Cafe")
        self.assertNotIn(("skip the small talk", grp, grp.lower()), compute_recurring(dated))

    def test_rsvp_link_replaces_organizer_homepage(self):
        from template import _is_event_specific_link, _is_generic_link
        self.assertTrue(_is_event_specific_link("https://lu.ma/8ugz1m1n"))
        self.assertFalse(_is_event_specific_link("https://lu.ma/boston"))
        self.assertTrue(_is_generic_link("https://themillennialcrisis.com/events"))
        self.assertTrue(_is_generic_link(" https://bostonconversations.com"))
        self.assertFalse(_is_generic_link("https://www.aeronautbrewing.com/event/123-trivia"))

    def test_boston_conversations_copies_merge(self):
        """Aeronaut, The Boston Calendar and Luma title the same night differently; one card, Luma link."""
        from template import group_by_date
        when = "2026-11-04T18:30:00-05:00"
        venues = [
            {"venue": "Aeronaut Brewing", "url": "https://d3izki9aezxlkr.cloudfront.net/public_events.json", "events": [
                {"name": "Boston Social Conversations", "date": when, "venue": "Aeronaut Brewing (Somerville)",
                 "url": "https://www.aeronautbrewing.com/visit/somerville/#events"}]},
            {"venue": "The Boston Calendar", "url": "https://www.thebostoncalendar.com/events", "events": [
                {"name": "Boston Conversations @ Aeronaut", "date": when, "venue": "Aeronaut Brewing Company",
                 "url": "https://bostonconversations.com/"}]},
            {"venue": "Luma Calendars", "url": "https://lu.ma/discover", "events": [
                {"name": "Boston Social Conversations - November Event", "date": when,
                 "venue": "Aeronaut Brewing Company, Somerville", "url": "https://lu.ma/8ugz1m1n"}]},
        ]
        dated, _, _ = group_by_date(venues)
        evs = [e for _, es in dated for e in es]
        self.assertEqual(len(evs), 1, [e["name"] for e in evs])
        self.assertEqual(evs[0]["url"], "https://lu.ma/8ugz1m1n")

    def test_luma_tech_events_go_to_default_off_bucket(self):
        from scrapers import TECH_EVENT_RE, category_bucket
        from template import DEFAULT_UNCHECKED_BUCKETS
        for t in ["Founder After Hours", "AgeTech Innovation Showcase", "Boston Alt Cloud Meetup", "Infra Demo Night",
                  "RoboBoston: 9th Annual Robot Block Party", "Claude 101: Setting up Your Workspace"]:
            self.assertTrue(TECH_EVENT_RE.search(t), t)
        for t in ["Boston Social Conversations", "Board Game Night", "Midday Unplug: Reset Your Nervous System",
                  "Winterizing Workshop at Maple Street Food Forest"]:
            self.assertFalse(TECH_EVENT_RE.search(t), t)
        self.assertEqual(category_bucket("tech"), "Tech & Startups")
        self.assertIn("Tech & Startups", DEFAULT_UNCHECKED_BUCKETS)

    def test_long_live_jazz_lineup_parsing(self):
        from unittest.mock import patch
        from bs4 import BeautifulSoup
        import scrapers
        page = ("<p>Jazz Night</p><p>ThursdayS at 6pm</p><p>Nov 19</p><p>Wes Wirth &amp; Fwd</p>"
                "<p>Dec 3</p><p>Stan Strickland &amp; Sundance</p><p>Join us for Thursday Jazz Nights!</p>")
        with patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(page, "html.parser")):
            evs = scrapers.scrape_long_live_roxbury("https://www.longlivebeerworks.com/boston", "ua")
        names = [e["name"] for e in evs]
        self.assertIn("Jazz Night: Wes Wirth & Fwd", names)
        self.assertIn("Jazz Night: Stan Strickland & Sundance", names)
        self.assertEqual(len(evs), 2)

    def test_mfa_skips_daily_guided_tours_and_canceled(self):
        from unittest.mock import patch
        from bs4 import BeautifulSoup
        import scrapers
        rows = [("Guided Tour", "Gallery Highlights", ""), ("Lecture", "Revere and Rodallega", ""),
                ("Educator Workshops", "Teaching Ancient Egypt", "Canceled"), ("Special Event", "Late Nites", "Tickets")]
        page = "".join(f'<div class="row"><span>{t}</span><a href="/event/{i}">{n}</a>'
                       f'<span>Wednesday, November 4, 2026</span><span>7:00 pm</span><span>{x}</span></div>'
                       for i, (t, n, x) in enumerate(rows))
        with patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(page, "html.parser")):
            names = [e["name"] for e in scrapers.scrape_mfa_boston("https://www.mfa.org/programs", "ua")]
        self.assertEqual(names, ["MFA: Revere and Rodallega", "MFA: Late Nites"])

    def test_bibliocommons_kids_audience_and_bpl_branches(self):
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timedelta
        import scrapers
        soon = (datetime.now(scrapers.EASTERN) + timedelta(days=2)).strftime("%Y-%m-%dT10:30")
        payload = {
            "events": {"items": ["a", "b", "c"], "pagination": {"pages": 1}},
            "entities": {
                "events": {
                    "a": {"definition": {"title": "Baby Lapsit", "start": soon, "branchLocationId": "1", "audienceIds": ["ba"]}},
                    "b": {"definition": {"title": "ESL Conversation", "start": soon, "branchLocationId": "2", "audienceIds": ["ad"]}},
                    "c": {"definition": {"title": "Canceled Thing", "start": soon, "isCancelled": True}},
                },
                "locations": {"1": {"name": "Jamaica Plain"}, "2": {"name": "West Roxbury"}},
                "eventAudiences": {"ba": {"name": "Babies: 0 to 18 months"}, "ad": {"name": "Adults: 18 and up"}},
            },
        }
        resp = MagicMock(); resp.json.return_value = payload; resp.raise_for_status = MagicMock()
        with patch("scrapers._SESSION.get", return_value=resp):
            evs = {e["name"]: e for e in scrapers.scrape_bpl("https://bpl.bibliocommons.com/events/search/index", "ua")}
        self.assertEqual(set(evs), {"Baby Lapsit", "ESL Conversation"})
        self.assertEqual(evs["Baby Lapsit"]["category"], "family")
        self.assertNotIn("category", evs["ESL Conversation"])
        self.assertEqual(evs["Baby Lapsit"]["venue"], "Boston Public Library (Jamaica Plain)")
        self.assertEqual(evs["Baby Lapsit"]["address"], "30 South St, Jamaica Plain")
        self.assertEqual(evs["ESL Conversation"]["neighborhood"], "West Roxbury")  # not plain "Roxbury"

    def test_little_muse_listing_parsing(self):
        from unittest.mock import patch, MagicMock
        from datetime import datetime, timedelta
        import scrapers
        d = datetime.now(scrapers.EASTERN) + timedelta(days=1)
        day_hdr = d.strftime("%A, %B %-d").upper()
        body = (f"<h2>{day_hdr}</h2><h3>Afternoon</h3>"
                '<p>🎃 3:30-5:30 PM - <strong><a href="https://www.eventbrite.com/e/halloween-party-at-play-union-tickets-1">'
                "Halloween Party at Play Union</a></strong> (all ages) ~13 min 💲<br/>Play Union, 378 Somerville Ave, Somerville"
                "<br/>A candy-free party. Pricing starting at $28.52.</p>"
                '<p>🎃 1:00-4:00 PM - <strong><a href="https://www.massaudubon.org/programs/x">Creepy Crawly Creations</a></strong>'
                " (all ages) ~5 min ✱<br/>Mass Audubon Nature Center, Magazine Beach Park, 668 Memorial Dr, Cambridge"
                "<br/>Free, register.</p>")
        archive = [{"slug": "week", "audience": "everyone"}]
        post = {"post_date": (d - timedelta(days=2)).isoformat(), "body_html": body,
                "canonical_url": "https://littlemuse.substack.com/p/week"}
        def fake_get(u, **kw):
            r = MagicMock(); r.json.return_value = archive if u.endswith("/archive") else post; return r
        with patch("scrapers._SESSION.get", side_effect=fake_get):
            evs = {e["name"]: e for e in scrapers.scrape_little_muse("https://littlemuse.substack.com", "ua")}
        pu = evs["Halloween Party at Play Union"]
        self.assertEqual((pu["venue"], pu["address"], pu["locality"], pu["price"]),
                         ("Play Union", "378 Somerville Ave, Somerville", "Somerville", "$28.52+"))
        self.assertEqual(datetime.fromisoformat(pu["date"]).astimezone(scrapers.EASTERN).hour, 15)
        cc = evs["Creepy Crawly Creations"]
        self.assertEqual(cc["venue"], "Mass Audubon Nature Center, Magazine Beach Park")
        self.assertEqual(cc["price"], "Free")
        self.assertEqual(cc["category"], "family")
    def test_venue_cache_discarded_when_scraper_code_changes(self):
        import tempfile
        from unittest.mock import patch
        import scrapers
        with tempfile.TemporaryDirectory() as d, patch.object(scrapers, "CACHE_DIR", d):
            def scraper_v1(url, ua):
                return []
            def scraper_v2(url, ua):
                return ["changed"]
            v1 = {"scraper": scraper_v1, "url": "https://example.org/events"}
            v2 = {"scraper": scraper_v2, "url": "https://example.org/events"}
            fp1, fp2 = scrapers._scraper_fingerprint(v1), scrapers._scraper_fingerprint(v2)
            self.assertNotEqual(fp1, fp2)
            scrapers._save_venue_cache("Test Venue", [{"name": "x"}], fingerprint=fp1)
            self.assertIsNotNone(scrapers._load_venue_cache("Test Venue", max_age=3600, fingerprint=fp1))
            self.assertIsNone(scrapers._load_venue_cache("Test Venue", max_age=3600, fingerprint=fp2))
            # stale fallback on network errors still uses whatever is on disk
            self.assertIsNotNone(scrapers._load_venue_cache("Test Venue", max_age=None))

    def test_service_ads_filtered_but_classes_kept(self):
        from scrapers import is_service_ad
        self.assertTrue(is_service_ad("Stress Free Week", "A La Carte Massage"))
        self.assertTrue(is_service_ad("Spa After Dark at Mandarin Oriental Boston", "Mandarin Oriental Boston"))
        self.assertTrue(is_service_ad("Social Spa Night", "Remedy Place"))
        self.assertFalse(is_service_ad("Full Body Massage Techniques With a Partner", "CCAE"))
        self.assertFalse(is_service_ad("Wesleaf Wellness Wednesdays", "wesleaf"))

    def test_deal_specials_get_default_off_bucket(self):
        from scrapers import is_deal_event, category_bucket
        from template import _effective_category, DEFAULT_UNCHECKED_BUCKETS
        deals = ["Posto South End- Happy Hour Deals!", "$1 Oysters at Vera's!", "1/2 OFF APPS at The Chester Tavern",
                 "BOGO Hot Dogs", "Bottomless Maki for $32 at Fat Baby", "$10 Martinis at Petula's"]
        events = ["BoGo - Boston Godot Developers Group!", "Boston Food Drive & Happy Hour", "Neurodivergent Happy Hour",
                  "Fresh Goofs: Standup Comedy Show and $4 Drinks", "Boston Happy Hour Stroll in the South End"]
        for n in deals:
            self.assertTrue(is_deal_event(n), n)
            self.assertEqual(_effective_category({"name": n, "category": "food"}), "deals")
        for n in events:
            self.assertFalse(is_deal_event(n), n)
        self.assertEqual(category_bucket("deals"), "Deals & Specials")
        self.assertIn("Deals & Specials", DEFAULT_UNCHECKED_BUCKETS)

    def test_midnight_runners_first_tuesday_is_5k(self):
        from scrapers import scrape_midnight_runners, EASTERN
        from datetime import datetime
        evs = scrape_midnight_runners("https://www.heylo.com/events/x/", "ua")
        self.assertGreaterEqual(len(evs), 3)
        for e in evs:
            dt = datetime.fromisoformat(e["date"]).astimezone(EASTERN)
            self.assertEqual((dt.weekday(), dt.hour), (1, 19))
            self.assertEqual("5K" in e["name"], dt.day <= 7, e["name"])
            self.assertEqual(e["venue"], "Carrie Nation Cocktail Club")

    def test_sanitize_event_url_and_moved_placeholder(self):
        from scrapers import sanitize_event_url, is_placeholder_or_closed_event
        fb = "https://www.thebostoncalendar.com/"
        self.assertEqual(sanitize_event_url("/cdn-cgi/l/email-protection#abc", fb), fb)
        self.assertEqual(sanitize_event_url("https://thebiltmoregrill.com/happenings/", fb), fb)
        self.assertEqual(sanitize_event_url("https://www.sinclaircambridge.com/x", fb), "https://www.sinclaircambridge.com/x")
        self.assertTrue(is_placeholder_or_closed_event("[moved to Roadrunner!] Michelle Branch"))
        self.assertFalse(is_placeholder_or_closed_event("Michelle Branch"))

    def test_kid_family_category_and_detection(self):
        """Verify is_kid_family_event and Kids & Family bucketing."""
        from scrapers import is_kid_family_event, infer_category, category_bucket
        from template import DEFAULT_UNCHECKED_BUCKETS, _effective_category

        # Positive kid/family events
        positives = [
            "Baby Lapsit at Central",
            "Crafternoon: Library Card Design Contest (Main)",
            "Library Card Design Contest (Collins)",
            "Toddler Story Time (Main)",
            "Preschool Story Time (Main)",
            "Sing-Along (Valente)",
            "Singalong with Matt Heaton at Central",
            "Classical Music for Babies and Kids",
            "2026 Holiday Pops Kids' Matinee",
            "Baby and Me Postpartum Yoga",
            "Mindful Movement: Kids Yoga at West",
            "Indigenous Weaving Workshop for Children",
        ]
        for name in positives:
            self.assertTrue(is_kid_family_event(name), f"Should match kid event: {name}")
            self.assertEqual(infer_category(name, "Library"), "family")
            self.assertEqual(_effective_category({"name": name, "venue": "Library"}), "family")

        # False positives to exclude
        negatives = [
            "A Boogie Wit Da Hoodie with DaBaby",
            "Frost Children",
            "Dinty Child & Mark Erelli",
            "Bottomless Maki for $32 at Fat Baby",
            "Marlon Wayans - Wild Child Tour",
            "R&B Sing-Along: R&B vs. Hip-Hop Pt. 2 with Rey Royale",
            "Ellis Paul & Friends (Beatles Singalong Night! Sam Robbins opens)",
        ]
        for name in negatives:
            self.assertFalse(is_kid_family_event(name), f"Should NOT match kid event: {name}")

        # Bucket & unchecked defaults
        self.assertEqual(category_bucket("family"), "Kids & Family")
        self.assertEqual(category_bucket("kids"), "Kids & Family")
        self.assertIn("Kids & Family", DEFAULT_UNCHECKED_BUCKETS)
        self.assertIn("Classes & Services", DEFAULT_UNCHECKED_BUCKETS)

    def test_deduplication_mad_tsai_and_kate_nash(self):
        """Verify deduplication for Mad Tsai (Sonia/Middle East) and Kate Nash (Arts at the Armory)."""
        from template import _merge_duplicates, _normalize_title_head

        # 1. Mad Tsai
        tsai_events = [
            {
                "name": "Mad Tsai, Mykey",
                "venue": "Sonia",
                "date": "2026-11-03T23:30:00+00:00",
                "price": "$33",
                "url": "https://www.ticketweb.com/event/mad-tsai-mykey-sonia-tickets/14213774",
                "source": "ticketweb",
            },
            {
                "name": "Mad Tsai",
                "venue": "The Middle East presents:",
                "date": "2026-11-03T22:30:00+00:00",
                "url": "https://do617.com/events/2026/11/3/mad-tsai-tickets",
                "source": "do617",
            },
            {
                "name": "Mad Tsai",
                "venue": "Sonia Live Music Venue",
                "date": "2026-11-03T23:30:00Z",
                "url": "https://seatgeek.com/mad-tsai-tickets/cambridge-massachusetts-sonia-live-music-venue-2026-11-03-6-30-pm/concert/18664219",
                "source": "seatgeek",
            },
        ]
        merged_tsai = _merge_duplicates(tsai_events)
        self.assertEqual(len(merged_tsai), 1, "Mad Tsai events across Sonia & Middle East presents should merge into 1")
        self.assertEqual(merged_tsai[0]["price"], "$33")
        self.assertGreaterEqual(len(merged_tsai[0].get("_alt_sources", [])), 2)

        # 2. Kate Nash
        kate_events = [
            {
                "name": "Kate Nash",
                "venue": "The Center for Arts at the Armory",
                "date": "2026-11-04T00:00:00Z",
                "url": "https://seatgeek.com/kate-nash-tickets/somerville-massachusetts-the-center-for-arts-at-the-armory-1-2026-11-03-7-pm/concert/18635055",
                "source": "seatgeek",
            },
            {
                "name": "Kate Nash",
                "venue": "The Center for Arts at the Armory Performance Hall",
                "date": "2026-11-04T00:00:00+00:00",
                "url": "https://www.eventbrite.com/e/kate-nash-tickets-2001392500846",
                "source": "eventbrite",
            },
            {
                "name": "An Evening with Kate Nash",
                "venue": "Arts at the Armory",
                "date": "2026-11-04T00:00:00+00:00",
                "url": "https://artsatthearmory.org/events/an-evening-with-kate-nash/",
                "_source_venue": "Arts at the Armory",
            },
        ]
        merged_kate = _merge_duplicates(kate_events)
        self.assertEqual(len(merged_kate), 1, "Kate Nash events across Arts at the Armory variants should merge into 1")
        self.assertGreaterEqual(len(merged_kate[0].get("_alt_sources", [])), 2)

        # 3. Willi Carlisle (SeatGeek 12 PM placeholder should collapse into confirmed 8 PM Crystal Ballroom show)
        willi_events = [
            {
                "name": "Willi Carlisle",
                "date": "2026-11-03T17:00:00Z",  # 12:00 PM EST placeholder
                "url": "https://seatgeek.com/willi-carlisle-tickets/somerville-massachusetts-crystal-ballroom-at-somerville-theatre-2026-11-03-12-pm/concert/18664484",
                "venue": "Crystal Ballroom at Somerville Theatre",
                "_source_venue": "SeatGeek",
            },
            {
                "name": "Willi Carlisle - The Universal Bubba Tour",
                "date": "2026-11-04T01:00:00Z",  # 8:00 PM EST confirmed
                "url": "https://www.ticketmaster.com/willi-carlisle-the-universal-bubba-tour-somerville-massachusetts-11-03-2026/event/010064EA80986481",
                "venue": "Crystal Ballroom at Somerville Theatre",
                "_source_venue": "Ticketmaster",
            },
            {
                "name": "Willi Carlisle",
                "date": "2026-11-04T01:00:00Z",  # 8:00 PM EST confirmed
                "url": "https://seatgeek.com/willi-carlisle-tickets/somerville-massachusetts-crystal-ballroom-at-somerville-theatre-2026-11-03-8-pm/concert/18376099",
                "venue": "Crystal Ballroom at Somerville Theatre",
                "_source_venue": "SeatGeek",
            },
            {
                "name": "Willi Carlisle",
                "date": "2026-11-04T01:00:00+00:00",  # 8:00 PM EST direct venue
                "url": "https://www.crystalballroomboston.com/events/willi-carlisle/",
                "venue": "Crystal Ballroom",
                "_source_venue": "Crystal Ballroom",
            },
        ]
        # In actual pipeline, events arrive sorted by _time so 12 PM is processed first
        from datetime import datetime
        import zoneinfo
        _eastern = zoneinfo.ZoneInfo("America/New_York")
        for e in willi_events:
            e["_time"] = datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(_eastern)
        willi_events.sort(key=lambda e: e["_time"])

        merged_willi = _merge_duplicates(willi_events)
        self.assertEqual(len(merged_willi), 1, "Willi Carlisle 12 PM placeholder should merge with 8 PM show into 1 event")
        self.assertEqual(merged_willi[0]["_source_venue"], "Crystal Ballroom")
        self.assertEqual(merged_willi[0]["_time"].hour, 20, "Showtime should be 8:00 PM (hour 20), not 12:00 PM")
        self.assertEqual(merged_willi[0]["url"], "https://www.crystalballroomboston.com/events/willi-carlisle/")
        alt_urls = [a.get("url") for a in merged_willi[0].get("_alt_sources", [])]
        self.assertIn("https://seatgeek.com/willi-carlisle-tickets/somerville-massachusetts-crystal-ballroom-at-somerville-theatre-2026-11-03-8-pm/concert/18376099", alt_urls)
        self.assertNotIn("https://seatgeek.com/willi-carlisle-tickets/somerville-massachusetts-crystal-ballroom-at-somerville-theatre-2026-11-03-12-pm/concert/18664484", alt_urls)

        # 4. Comedy Studio (Comedy Hell: Free Comedy Night vs Free Comedy Open-Mic)
        cs_events = [
            {
                "name": "Comedy Hell: Free Comedy Night",
                "venue": "The Comedy Studio",
                "url": "https://www.thecomedystudio.com/events",
                "date": "2026-11-04T00:00:00+00:00",
                "category": "comedy",
                "_source_venue": "The Boston Calendar",
                "_time": datetime(2026, 11, 3, 19, 0, tzinfo=_eastern),
            },
            {
                "name": "Free Comedy Open-Mic",
                "venue": "The Comedy Studio",
                "url": "https://www.thecomedystudio.com/checkout/eecf12b6-6622-418e-9a6c-f7a881b57722",
                "date": "2026-11-04T00:00:00+00:00",
                "category": "comedy",
                "_source_venue": "The Comedy Studio",
                "_time": datetime(2026, 11, 3, 19, 0, tzinfo=_eastern),
            },
        ]
        merged_cs = _merge_duplicates(cs_events)
        self.assertEqual(len(merged_cs), 1, "Comedy Studio Comedy Hell and Free Comedy Open-Mic should merge into 1 event")
        self.assertEqual(merged_cs[0]["_source_venue"], "The Comedy Studio")
        self.assertEqual(merged_cs[0]["url"], "https://www.thecomedystudio.com/checkout/eecf12b6-6622-418e-9a6c-f7a881b57722")

        # 5. To Kill a Mockingbird (Ticketmaster, SeatGeek, and Calderwood Pavilion / Boston Theatre Scene)
        mb_events = [
            {
                "name": "To Kill a Mockingbird (Touring)",
                "venue": "Huntington Theatre",
                "_source_venue": "Ticketmaster",
                "date": "2026-11-04T00:00:00Z",
                "url": "https://www.ticketmaster.com/event/Z7r9jZ1AAv7P9",
                "_time": datetime(2026, 11, 3, 19, 0, tzinfo=_eastern),
            },
            {
                "name": "To Kill a Mockingbird - Boston",
                "venue": "Huntington Avenue Theatre",
                "_source_venue": "SeatGeek",
                "date": "2026-11-04T00:00:00Z",
                "url": "https://seatgeek.com/to-kill-a-mockingbird-tickets/broadway/2026-11-03-7-pm/18498424",
                "_time": datetime(2026, 11, 3, 19, 0, tzinfo=_eastern),
            },
            {
                "name": "Harper Lee's To Kill a Mockingbird",
                "venue": "The Huntington Theatre",
                "_source_venue": "Calderwood Pavilion",
                "date": "2026-11-04T00:30:00+00:00",
                "url": "https://www.bostontheatrescene.com/shows-and-events/tkam/",
                "_time": datetime(2026, 11, 3, 19, 30, tzinfo=_eastern),
            },
        ]
        merged_mb = _merge_duplicates(mb_events)
        self.assertEqual(len(merged_mb), 1, "To Kill a Mockingbird across Huntington Theatre variants should merge into 1 event")
        self.assertEqual(merged_mb[0]["_source_venue"], "Calderwood Pavilion")
        self.assertEqual(merged_mb[0]["url"], "https://www.bostontheatrescene.com/shows-and-events/tkam/")
        self.assertEqual(len(merged_mb[0].get("_alt_sources", [])), 2)

    def test_naive_datetime_eastern_formatting(self):
        """Verify naive datetime strings are always treated as Eastern time, even in UTC environments."""
        from template import format_time, format_when

        # 22:00 local time (10:00 PM) at Plough & Stars
        naive_10pm = "2026-11-03T22:00:00"
        self.assertEqual(format_time(naive_10pm), "10:00 PM")
        self.assertEqual(format_when({"name": "Johnny Trama", "date": naive_10pm}), "10:00 PM")

        # UTC-aware 03:00 UTC on Nov 4 = 10:00 PM EST on Nov 3
        utc_10pm = "2026-11-04T03:00:00+00:00"
        self.assertEqual(format_time(utc_10pm), "10:00 PM")
        self.assertEqual(format_when({"name": "Johnny Trama", "date": utc_10pm}), "10:00 PM")

    def test_life_drawing_boston_scraper(self):
        """Verify Life Drawing Boston scraper parses upcoming sessions with correct art category and coordinates."""
        from scrapers import scrape_life_drawing_boston
        events = scrape_life_drawing_boston("https://www.lifedrawingboston.com/calendar?format=json", UA_CHROME)
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0, "Life Drawing Boston should return upcoming sessions")
        for ev in events:
            self.assertTrue(ev["name"])
            self.assertTrue(ev["date"])
            self.assertTrue(ev["url"].startswith("http"))
            self.assertEqual(ev["venue"], "Life Drawing Boston")
            self.assertEqual(ev["category"], "art")
            geo = resolve_event_geo(ev)
            self.assertIsNotNone(geo, f"Failed to resolve geo for Life Drawing Boston: {ev}")
            self.assertAlmostEqual(geo["lat"], 42.3780, places=3)
            self.assertAlmostEqual(geo["lng"], -71.0920, places=3)
            self.assertEqual(geo["neighborhood"], "East Somerville")

    def test_bostonfac_scraper(self):
        """Verify Boston Figure Art Center scraper parses upcoming sessions with correct art category and coordinates."""
        from scrapers import scrape_bostonfac
        events = scrape_bostonfac("https://www.bostonfac.com/figuresessions", UA_CHROME)
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0, "Boston Figure Art Center should return upcoming sessions")
        for ev in events[:10]:
            self.assertTrue(ev["name"])
            self.assertTrue(ev["date"])
            self.assertTrue(ev["url"].startswith("http"))
            self.assertEqual(ev["venue"], "Boston Figure Art Center")
            self.assertEqual(ev["category"], "art")
            geo = resolve_event_geo(ev)
            self.assertIsNotNone(geo, f"Failed to resolve geo for BFAC: {ev}")
            self.assertAlmostEqual(geo["lat"], 42.3813, places=3)
            self.assertAlmostEqual(geo["lng"], -71.0912, places=3)
            self.assertEqual(geo["neighborhood"], "Union Square")

    def test_sports_museum_tour_deduplication(self):
        """Verify multiple hourly tour departures of The Sports Museum Tour collapse into a single event."""
        from template import _merge_duplicates

        tour_events = [
            {
                "name": "The Sports Museum Tour",
                "date": "2026-11-03T15:00:00Z",
                "venue": "The Sports Museum",
                "url": "https://www.universe.com/events/the-sports-museum-tour-tickets-9YLR74?ref=ticketmaster",
                "category": "sports",
            },
            {
                "name": "The Sports Museum Tour",
                "date": "2026-11-03T16:00:00Z",
                "venue": "The Sports Museum",
                "url": "https://www.universe.com/events/the-sports-museum-tour-tickets-9YLR74?ref=ticketmaster",
                "category": "sports",
            },
            {
                "name": "The Sports Museum Tour",
                "date": "2026-11-03T17:00:00Z",
                "venue": "The Sports Museum",
                "url": "https://www.universe.com/events/the-sports-museum-tour-tickets-9YLR74?ref=ticketmaster",
                "category": "sports",
            },
            {
                "name": "The Sports Museum Tour",
                "date": "2026-11-03T18:00:00Z",
                "venue": "The Sports Museum",
                "url": "https://www.universe.com/events/the-sports-museum-tour-tickets-9YLR74?ref=ticketmaster",
                "category": "sports",
            },
            {
                "name": "The Sports Museum Tour",
                "date": "2026-11-03T19:00:00Z",
                "venue": "The Sports Museum",
                "url": "https://www.universe.com/events/the-sports-museum-tour-tickets-9YLR74?ref=ticketmaster",
                "category": "sports",
            },
        ]
        merged = _merge_duplicates(tour_events)
        self.assertEqual(len(merged), 1, "Hourly Sports Museum tour departures on the same date should collapse into 1 listing")
        self.assertIn("Hourly tours departing", merged[0].get("description", ""))

    def test_midday_music_html_entity_deduplication(self):
        """Verify HTML entities like &amp; in titles deduplicate across sources (Eventbrite & MIT Open Space)."""
        from template import _merge_duplicates

        events = [
            {
                "name": "Midday Music & Soup: Joseph Borsellino and Friends",
                "date": "2026-11-04T17:15:00+00:00",
                "venue": "MIT Welcome Center",
                "url": "https://www.eventbrite.com/e/midday-music-soup-joseph-borsellino-and-friends-tickets-1994594059525",
                "_source_venue": "The Boston Calendar",
            },
            {
                "name": "Midday Music &amp; Soup: Joseph Borsellino and Friends",
                "date": "2026-11-04T17:15:00.668000+00:00",
                "venue": "MIT Open Space",
                "url": "https://openspace.mit.edu/calendar/midday-music-soup-joseph-borsellino-november-2026",
                "_source_venue": "MIT Open Space",
            },
        ]
        merged = _merge_duplicates(events)
        self.assertEqual(len(merged), 1, "Midday Music & Soup events with & vs &amp; must merge into 1")
        self.assertNotIn("&amp;", merged[0]["name"])
        self.assertEqual(merged[0]["name"], "Midday Music & Soup: Joseph Borsellino and Friends")

    def test_ongoing_museum_exhibits_filtered(self):
        """Verify ongoing multi-year museum exhibits and venue self-promotions are excluded."""
        from scrapers import is_placeholder_or_closed_event

        exhibits = [
            "Rubies",
            "Pop Quiz: 1776",
            "Collecting Wonders: Tomorrow's Discoveries",
            "Collecting Wonders: Tomorrow’s Discoveries",
            "From Iran: A Visual Testimony",
            "Harvard Museum of Natural History",
            "The Peabody Museum of Archaeology and Ethnology",
            "Volunteer Opportunities Everyday!",
        ]
        for title in exhibits:
            self.assertTrue(is_placeholder_or_closed_event(title), f"Failed to filter exhibit: {title}")


    def test_standing_exhibit_filter(self):
        """Permanent exhibits/campaigns are dropped; real dated events at the same venues are kept."""
        from scrapers import is_standing_exhibit

        drop = [
            {"name": "Experience The Ruckus!", "url": "https://revolutionaryspaces.org/explore/exhibits/ruckus/", "venue": "Old South Meeting House", "date": "2026-11-04T15:00:00+00:00"},
            {"name": "The Road to Revolution", "url": "https://revolutionaryspaces.org/explore/exhibits/the-road-to-revolution/", "venue": "Old State House", "date": "2026-11-04T15:00:00+00:00"},
            {"name": "Where's Boston? 50 Years Later", "url": "https://do617.com/events/2026/6/15/wheres-boston-50-years-later-tickets", "venue": "Boston Athenæum", "date": "2026-11-04T13:00:00+00:00"},
            {"name": "Winter Coat Drive", "url": "https://do617.com/events/2026/11/3/winter-coat-drive-tickets", "venue": "Boston", "date": "2026-11-04T13:00:00+00:00"},
        ]
        keep = [
            {"name": "The Enigmatic Treasure of a Nubian Queen", "url": "https://hmsc.harvard.edu/2026/04/14/the-enigmatic-treasure-of-a-nubian-queen/", "venue": "Harvard Museum of Natural History", "date": "2026-11-04T16:00:00+00:00"},
            {"name": "Boston Lights: A Lantern Experience", "url": "https://do617.com/events/2026/8/14/boston-lights-a-lantern-experience-1785266685", "venue": "Franklin Park Zoo", "date": "2026-11-04T23:00:00+00:00"},
            {"name": "Gallery Talk", "url": "https://do617.com/events/2026/11/2/gallery-talk-tickets", "venue": "Boston Athenæum", "date": "2026-11-04T23:00:00+00:00"},
            {"name": "Coat Drive Volunteer Night at Allston Hall", "url": "https://do617.com/events/2026/11/4/x", "venue": "Allston Hall", "date": "2026-11-04T23:00:00+00:00"},
        ]
        for e in drop:
            self.assertTrue(is_standing_exhibit(e), f"Should drop: {e['name']}")
        for e in keep:
            self.assertFalse(is_standing_exhibit(e), f"Should keep: {e['name']}")

    def test_fetch_soup_decodes_utf8_without_charset_header(self):
        """Pages that omit an HTTP charset must not be decoded as Latin-1 (mojibake)."""
        from unittest import mock
        import scrapers

        class FakeResp:
            content = "<html><body><h3>Where\u2019s Boston? Boston Athen\u00e6um</h3></body></html>".encode("utf-8")
            text = content.decode("latin-1")
            def raise_for_status(self): pass

        with mock.patch.object(scrapers._SESSION, "get", return_value=FakeResp()):
            soup = scrapers.fetch_soup("http://example.test", "ua")
        self.assertEqual(soup.h3.get_text(), "Where\u2019s Boston? Boston Athen\u00e6um")


    def test_fix_doubled_url(self):
        """Glued absolute URLs are repaired; legitimate embedded/redirect URLs are untouched."""
        from scrapers import fix_doubled_url

        self.assertEqual(
            fix_doubled_url("https://www.bso.orghttps://www.bso.org/events/holiday-pops-2026"),
            "https://www.bso.org/events/holiday-pops-2026",
        )
        self.assertEqual(
            fix_doubled_url("https://photowalks.com/tours/beacon-hill/https://photowalks.com/tours/beacon-hill/"),
            "https://photowalks.com/tours/beacon-hill/",
        )
        untouched = [
            "https://www.bso.org/events/holiday-pops-2026",
            "https://example.com/redirect?url=https://other.com/page",
            "https://www.facebook.com/sharer.php?u=https://site.com/x",
            "",
            None,
        ]
        for u in untouched:
            self.assertEqual(fix_doubled_url(u), u)


if __name__ == "__main__":
    unittest.main()






class SeparateListingsMergeTests(unittest.TestCase):
    def _ev(self, name, hour, url, source="ICA Boston", venue="ICA Boston", **kw):
        from datetime import datetime
        from template import EASTERN
        e = {"name": name, "url": url, "venue": venue, "_source_venue": source,
             "venue_url": "https://www.icaboston.org/events/", "category": kw.get("category", "family"),
             "_time": datetime(2026, 11, 8, hour, 0, tzinfo=EASTERN)}
        e["date"] = e["_time"].isoformat()
        return e

    def test_same_source_different_pages_stay_separate(self):
        from template import _merge_duplicates
        out = _merge_duplicates([
            self._ev("Bank of America Museums on Us", 10, "https://www.icaboston.org/events/bank-america-museums-us/"),
            self._ev("Boston Family Days", 10, "https://www.icaboston.org/events/boston-family-days/"),
        ])
        self.assertEqual(len(out), 2)

    def test_same_title_far_apart_stays_separate(self):
        from template import _merge_duplicates
        out = _merge_duplicates([
            self._ev("Boston Family Days", 9, "https://www.neaq.org/event/boston-family-days-4/",
                     source="New England Aquarium", venue="New England Aquarium"),
            self._ev("Boston Family Days", 10, "https://www.icaboston.org/events/boston-family-days/"),
        ])
        self.assertEqual(len(out), 2)

    def test_same_show_from_two_sources_still_merges(self):
        from template import _merge_duplicates
        out = _merge_duplicates([
            self._ev("Boston Family Days", 10, "https://www.icaboston.org/events/boston-family-days/"),
            self._ev("Boston Family Days", 10, "https://www.thebostoncalendar.com/events/boston-family-days",
                     source="The Boston Calendar"),
        ])
        self.assertEqual(len(out), 1)

    def test_titles_unrelated(self):
        from template import _titles_unrelated
        self.assertTrue(_titles_unrelated("Thursday Long Pose", "Anatomy of the head (3-Week Class)"))
        self.assertFalse(_titles_unrelated("half•alive", "halfalive"))
        self.assertFalse(_titles_unrelated("Boston Family Days", "Family Days at the ICA"))
        self.assertFalse(_titles_unrelated("Amble", None))
