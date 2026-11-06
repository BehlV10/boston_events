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


class ZooHours(unittest.TestCase):
    def test_range_with_one_meridiem(self):
        self.assertEqual(scrapers._zoo_start(", 5:00 – 10:30 p.m. Prepare to be dazzled"), (17, 0))

    def test_range_with_two_meridiems(self):
        self.assertEqual(scrapers._zoo_start(", 9:00 a.m. - 4:00 p.m. In honor"), (9, 0))

    def test_no_hours(self):
        self.assertIsNone(scrapers._zoo_start(" Various dates in December"))


class ListingFixes(unittest.TestCase):
    def fixed(self, source, **event):
        results = [{"venue": source, "events": [event]}]
        scrapers._fix_listings(results)
        return results[0]["events"][0]

    def local(self, e):
        return scrapers.datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN).strftime("%a %H:%M")

    def test_snowport_opens_by_weekday(self):
        monday = self.fixed("Do617", name="Snowport", date="2026-11-09T15:00:00+00:00", venue="Seaport")
        saturday = self.fixed("Do617", name="Snowport", date="2026-11-07T15:00:00+00:00", venue="Seaport")
        self.assertEqual(self.local(monday), "Mon 15:00")
        self.assertEqual(self.local(saturday), "Sat 10:00")

    def test_book_fair_price_follows_the_day(self):
        friday = self.fixed("The Boston Calendar", name="Boston International Antiquarian Book Fair",
                            date="2026-11-06T21:00:00+00:00", venue="Hynes Convention Center", price="$10")
        self.assertEqual(friday["price"], "$25")

    def test_undated_listing_gets_the_range(self):
        e = self.fixed("The Boston Calendar", name="Boston International Antiquarian Book Fair", date=None,
                       venue="Hynes Convention Center", price="$10")
        self.assertEqual(e["price"], "$10 - $25")

    def test_other_events_are_left_alone(self):
        e = self.fixed("Do617", name="The Washing Machine", date="2026-11-08T15:00:00+00:00", venue="Calderwood")
        self.assertEqual(e["date"], "2026-11-08T15:00:00+00:00")

    def test_cancelled_night_and_placeholder_are_dropped(self):
        self.assertTrue(scrapers._is_wrong_listing({"name": "Boston Lights: A Lantern Experience", "venue": "Franklin Park Zoo",
                                                    "date": "2026-11-06T22:00:00+00:00"}))
        self.assertFalse(scrapers._is_wrong_listing({"name": "Boston Lights: A Lantern Experience", "venue": "Franklin Park Zoo",
                                                     "date": "2026-11-07T22:00:00+00:00"}))


class NewNeighborhoodSources(unittest.TestCase):
    def test_substation_drops_private_bookings_and_opening_hours(self):
        rows = [{"name": "Closed for Private Event"}, {"name": "The Substation Bar"},
                {"name": "The Substation Bar: BINGO NIGHT"}, {"name": "Paint &amp; Sip"}]
        with mock.patch.object(scrapers, "scrape_squarespace_events", return_value=rows):
            names = [e["name"] for e in scrapers.scrape_substation("u", "ua")]
        self.assertEqual(names, ["The Substation Bar: BINGO NIGHT", "Paint & Sip"])

    def test_kennedy_institute_keeps_only_timed_future_programs(self):
        html = """<div class="list-item-area"><h2><a href="https://x/y">Future Talk</a></h2><p>Friday, November 6, 2099 at 5:30pm</p></div>
                  <div class="list-item-area"><h2>Old Talk</h2><p>Monday, September 14, 2020 at 6:00pm</p></div>
                  <div class="list-item-area"><h2>Recording</h2><p>Monday, October 19, 2099</p></div>"""
        with mock.patch.object(scrapers, "fetch_soup", return_value=scrapers.BeautifulSoup(html, "html.parser")):
            events = scrapers.scrape_kennedy_institute("u", "ua")
        self.assertEqual([e["name"] for e in events], ["Future Talk"])
        self.assertEqual(events[0]["url"], "https://x/y")


class CentralSquarePerformances(unittest.TestCase):
    def test_reads_shows_and_skips_the_talks(self):
        show = '<a href="/calendar/buy-tickets-to-x/">Buy</a>'
        buy = ("The Getaway Driver 28 dec 2:00 pm 2:00 pm (GMT-05:00) Buy Tickets "
               "Artists & Audiences for The Getaway Driver 28 dec 9:00 pm 9:00 pm "
               "The Getaway Driver (captioned) 29 dec 7:30 pm 7:30 pm")
        pages = [scrapers.BeautifulSoup(show, "html.parser"), scrapers.BeautifulSoup(f"<p>{buy}</p>", "html.parser")]
        with mock.patch.object(scrapers, "fetch_soup", side_effect=pages):
            found = scrapers._central_square_performances("https://site/shows/x/", "The Getaway Driver", "ua")
        self.assertEqual([d.strftime("%m-%d %H:%M") for d in found], ["12-28 14:00", "12-29 19:30"])


class MiddlesexNights(unittest.TestCase):
    def night(self, name):
        return [{"name": name, "date": "2026-11-07T21:00:00-05:00", "venue": "Middlesex Lounge"}]

    def test_party_then_guest_becomes_two_listings(self):
        party, guest = scrapers._split_middlesex_nights(self.night("90s PARTY then SLICK VICK"))
        self.assertEqual((party["name"], party["date"]), ("90s PARTY", "2026-11-07T19:00:00-05:00"))
        self.assertEqual((guest["name"], guest["date"]), ("SLICK VICK", "2026-11-07T22:00:00-05:00"))

    def test_party_alone_moves_to_the_early_slot(self):
        events = scrapers._split_middlesex_nights(self.night("90s PARTY"))
        self.assertEqual([e["date"] for e in events], ["2026-11-07T19:00:00-05:00"])

    def test_guest_nights_are_unchanged(self):
        self.assertEqual(scrapers._split_middlesex_nights(self.night("KNIFE")), self.night("KNIFE"))
