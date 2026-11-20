import unittest
from datetime import datetime

import scrapers
import template
from scrapers import EASTERN


def _ev(name, venue, source, url, hour=20):
    t = datetime(2026, 12, 5, hour, 0, tzinfo=EASTERN)
    return {"name": name, "venue": venue, "_source_venue": source, "category": "music", "_time": t,
            "date": t.astimezone(scrapers.timezone.utc).isoformat(), "url": url}


TM = "https://www.ticketmaster.com/the-national-boston-massachusetts-12-05-2026/event/01006123ABCD"
AXS = "https://www.axs.com/events/1234567/the-national-tickets"
OWN = "https://www.mgmmusichall.com/events/the-national"


class SellerLinks(unittest.TestCase):
    def _merge(self, events):
        batch = [dict(e) for e in events]
        return template._merge_duplicates(batch, template.title_word_freq(batch))

    def test_ticketmaster_beats_the_venue_website_either_order(self):
        own = _ev("The National", "MGM Music Hall at Fenway", "MGM Music Hall at Fenway", OWN)
        tm = _ev("The National", "MGM Music Hall", "Ticketmaster", TM)
        for order in ([own, tm], [tm, own]):
            merged = self._merge(order)
            self.assertEqual(len(merged), 1, order)
            self.assertEqual(merged[0]["url"], TM)
            self.assertIn(OWN, [a["url"] for a in merged[0].get("_alt_sources") or []])
            self.assertNotIn(TM, [a["url"] for a in merged[0].get("_alt_sources") or []])
            self.assertEqual(merged[0]["venue"], "MGM Music Hall at Fenway")  # venue's own details kept

    def test_axs_is_used_when_that_is_the_venues_seller(self):
        own = _ev("Mt. Joy", "Roadrunner", "Roadrunner", "https://www.roadrunnerboston.com/events/mt-joy")
        axs = _ev("Mt. Joy", "Roadrunner", "AXS Boston", AXS)
        self.assertEqual(self._merge([own, axs])[0]["url"], AXS)

    def test_seller_listing_at_another_venue_is_not_promoted(self):
        m = {"name": "Jazz Night", "venue": "Wally's Cafe", "url": "https://wallyscafe.com/calendar/jazz-night-1205",
             "_source_venue": "Wally's Cafe"}
        template._prefer_seller_link(m, [("https://www.ticketweb.com/event/jazz-night-tickets/123456",
                                         "Mezzrow", "TicketWeb")])
        self.assertEqual(m["url"], "https://wallyscafe.com/calendar/jazz-night-1205")

    def test_seller_listing_at_a_different_time_is_not_promoted(self):
        own = _ev("To Kill a Mockingbird", "Huntington Theatre", "Huntington Theatre",
                  "https://www.huntingtontheatre.org/tkam/", hour=19)
        own["_time"] = own["_time"].replace(minute=30)
        tm = _ev("To Kill a Mockingbird", "Huntington Theatre", "Ticketmaster",
                 "https://www.ticketmaster.com/event/Z7r9jZ1AAv7P9", hour=19)
        merged = self._merge([tm, own])
        self.assertEqual(merged[0]["url"], "https://www.huntingtontheatre.org/tkam/")

    def test_seller_pages_that_are_not_one_event_are_ignored(self):
        self.assertFalse(template._primary_seller_link("https://www.ticketmaster.com/venue/12345"))
        self.assertFalse(template._primary_seller_link("https://www.axs.com/venues/101/roadrunner"))
        self.assertTrue(template._primary_seller_link("https://www.etix.com/ticket/p/12345678/show-boston"))
        self.assertTrue(template._primary_seller_link(TM))

    def test_venue_names(self):
        self.assertTrue(template._same_venue_name("House of Blues Boston", "House of Blues"))
        self.assertFalse(template._same_venue_name("Smalls", "Mezzrow"))


if __name__ == "__main__":
    unittest.main()
