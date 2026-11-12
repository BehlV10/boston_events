"""Tests for newly added scrapers: Clay Table in Central Square, Idle Hands Craft Ales in Malden,
Tuck's Arcadium in Harvard Square, and Downtown Boston BID."""
import unittest
from unittest import mock
from datetime import datetime, timezone

import scrapers as S
from venues_geo import resolve_event_geo


class ClayTableTest(unittest.TestCase):
    def test_clay_table_geo_resolves_to_central_square(self):
        geo = resolve_event_geo({"venue": "The Clay Table", "name": "Pottery Market"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Central Square")
        self.assertIn("19 Brookline St", geo["address"])
        self.assertEqual(geo["venue"], "The Clay Table")

    def test_scrape_clay_table_holiday_market(self):
        events = S.scrape_the_clay_table_holiday_market("https://theclaytable.com/holiday-market-2026", S.UA_CHROME)
        self.assertGreaterEqual(len(events), 1)
        names = [e["name"] for e in events]
        self.assertTrue(any("Opening Night" in n or "Holiday Market" in n for n in names))
        for e in events:
            self.assertEqual(e["venue"], "The Clay Table")
            self.assertEqual(e["price"], "Free")
            self.assertIn("19 Brookline St", e["address"])
            self.assertEqual(e["url"], "https://theclaytable.com/holiday-market-2026")


class IdleHandsTest(unittest.TestCase):
    def test_idle_hands_geo_resolves_to_malden_center(self):
        geo = resolve_event_geo({"venue": "Idle Hands Craft Ales", "name": "Beer Fest"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Malden Center")
        self.assertIn("Malden", geo["address"])

    def test_scrape_idle_hands(self):
        fake_events = [
            {"title": "Merry Makers Market", "startDate": 1794670200973, "endDate": 1794686400973,
             "fullUrl": "/events/merry-makers-market", "body": "<p>Local artisan holiday market</p>"},
            {"title": "RUN CLUB", "startDate": 1794958200363, "endDate": 1794961800363,
             "fullUrl": "/events/run-club", "body": "<p>Free weekly fun run!</p>"},
        ]
        with mock.patch.object(S, "_SESSION") as session:
            mock_resp = mock.Mock(status_code=200)
            mock_resp.json.return_value = {"upcoming": fake_events}
            session.get.return_value = mock_resp

            events = S.scrape_idle_hands("https://www.idlehandscraftales.com/events", "ua")

        self.assertEqual(len(events), 2)
        by_name = {e["name"]: e for e in events}
        market = by_name["Merry Makers Market"]
        self.assertEqual(market["venue"], "Idle Hands Craft Ales")
        self.assertEqual(market["category"], "shopping")
        self.assertEqual(market["url"], "https://www.idlehandscraftales.com/events/merry-makers-market")

        run = by_name["RUN CLUB"]
        self.assertEqual(run["category"], "fitness")
        self.assertEqual(run["price"], "Free")


class TucksArcadiumTest(unittest.TestCase):
    def test_tucks_arcadium_geo_resolves_to_harvard_square(self):
        geo = resolve_event_geo({"venue": "Tuck's Arcadium", "name": "Arcade Night"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Harvard Square")
        self.assertIn("36 John F. Kennedy St", geo["address"])

    def test_scrape_tucks_arcadium(self):
        events = S.scrape_tucks_arcadium("https://tucksarcadium.com", S.UA_CHROME)
        self.assertGreaterEqual(len(events), 3)
        for e in events:
            self.assertEqual(e["venue"], "Tuck's Arcadium")
            self.assertEqual(e["price"], "Free")
            self.assertEqual(e["category"], "gaming")
            self.assertEqual(e["url"], "https://tucksarcadium.com")


class DowntownBostonBidTest(unittest.TestCase):
    def test_downtown_boston_geo(self):
        geo = resolve_event_geo({"venue": "Downtown Boston BID", "name": "Market"})
        self.assertIsNotNone(geo)
        self.assertIn("Downtown", geo["neighborhood"])

    def test_scrape_downtown_boston_bid(self):
        fake_api_data = {
            "events": [
                {
                    "title": "Summer St Lunchtime Concert",
                    "start_date": "2026-11-20 12:00:00",
                    "end_date": "2026-11-20 14:00:00",
                    "cost": "Free",
                    "website": "https://example.com/artist",
                    "venue": {
                        "venue": "Downtown Crossing Steps",
                        "address": "Washington St",
                        "city": "Boston",
                        "zip": "02108"
                    },
                    "categories": [{"name": "Music"}]
                }
            ]
        }
        with mock.patch.object(S, "_SESSION") as session:
            mock_resp = mock.Mock(status_code=200)
            mock_resp.json.return_value = fake_api_data
            session.get.return_value = mock_resp

            events = S.scrape_downtown_boston_bid("https://www.downtownboston.org/wp-json/tribe/events/v1/events", "ua")

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "Summer St Lunchtime Concert")
        self.assertEqual(ev["price"], "Free")
        self.assertEqual(ev["venue"], "Downtown Crossing Steps")
        self.assertEqual(ev["url"], "https://example.com/artist")
        self.assertEqual(ev["category"], "music")


class VenueRegistrationTest(unittest.TestCase):
    def test_all_new_venues_are_registered_in_all_venues(self):
        by_name = {v["name"]: v for v in S._ALL_VENUES}
        self.assertIn("The Clay Table Holiday Market", by_name)
        self.assertIn("Idle Hands Craft Ales", by_name)
        self.assertIn("Tuck's Arcadium", by_name)
        self.assertIn("Downtown Boston BID", by_name)

        self.assertIs(by_name["Idle Hands Craft Ales"]["scraper"], S.scrape_idle_hands)
        self.assertIs(by_name["Tuck's Arcadium"]["scraper"], S.scrape_tucks_arcadium)
        self.assertIs(by_name["Downtown Boston BID"]["scraper"], S.scrape_downtown_boston_bid)


if __name__ == "__main__":
    unittest.main()
