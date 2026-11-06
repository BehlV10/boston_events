"""Corrections found by checking listings against venues' own pages, Nov 2026."""
import unittest
from datetime import date
from unittest import mock

import scrapers


class MarketSeasons(unittest.TestCase):
    def test_union_square_ends_with_october(self):
        self.assertTrue(scrapers._in_season("Union Square Farmers Market", date(2026, 10, 31)))
        self.assertFalse(scrapers._in_season("Union Square Farmers Market", date(2026, 11, 7)))

    def test_kendall_ends_in_early_october(self):
        self.assertTrue(scrapers._in_season("Kendall Square Farmers Market", date(2026, 10, 8)))
        self.assertFalse(scrapers._in_season("Kendall Square Farmers Market", date(2026, 10, 15)))

    def test_sowa_opens_at_eleven(self):
        sowa = next(m for m in scrapers.MANUAL_RECURRING_EVENTS if m[0] == "SoWa Open Market")
        self.assertEqual(sowa[3][0][3:5], (11, 0))


class TicketmasterPrices(unittest.TestCase):
    def response(self, low, high):
        event = {"name": "Boston Manor", "url": "https://www.ticketmaster.com/event/x",
                 "dates": {"start": {"dateTime": "2026-11-09T00:30:00Z", "localDate": "2026-11-08"}},
                 "priceRanges": [{"min": low, "max": high, "currency": "USD"}],
                 "_embedded": {"venues": [{"name": "The Sinclair", "city": {"name": "Cambridge"}}]}}
        reply = mock.Mock(status_code=200)
        reply.json.return_value = {"_embedded": {"events": [event]}, "page": {"totalPages": 1}}
        return reply

    def discovery_price(self, low, high):
        with mock.patch.object(scrapers, "_SESSION") as session, \
                mock.patch.dict("os.environ", {"TICKETMASTER_API_KEY": "test"}):
            session.get.return_value = self.response(low, high)
            events = scrapers.scrape_ticketmaster_discovery(
                "https://app.ticketmaster.com/discovery/v2/events.json?venueId=x", "ua")
        return events[0]["price"] if events else "no events"

    def test_zero_range_is_no_price_rather_than_free(self):
        self.assertIsNone(self.discovery_price(0, 0))

    def test_real_range_is_kept(self):
        self.assertEqual(self.discovery_price(32, 32), "$32")


class BigNightLiveTimes(unittest.TestCase):
    def test_ticketmaster_time_replaces_the_assumed_seven_pm(self):
        own = {"venue": "Big Night Live", "events": [
            {"name": "Svdden Death", "date": "2026-11-07T00:00:00+00:00", "venue": "Big Night Live"}]}
        feed = {"venue": "Leader Bank Pavilion", "events": [
            {"name": "Svdden Death ( 18+ )", "date": "2026-11-07T02:00:00+00:00", "venue": "Big Night Live"}]}
        scrapers._use_show_times([own, feed])
        self.assertEqual(own["events"][0]["date"], "2026-11-07T02:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
