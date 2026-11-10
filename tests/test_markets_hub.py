"""Markets & festivals hub: markets from any category plus festivals with stalls, a chip per kind."""
import unittest
from datetime import datetime, timedelta

import template
from scrapers import EASTERN


def _ev(name, days=2, venue="Somewhere", category="markets"):
    t = (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=11, minute=0, second=0, microsecond=0)
    return {"name": name, "venue": venue, "category": category, "_time": t, "date": t.isoformat(),
            "url": "https://example.com/" + name.replace(" ", "-"), "_source_venue": "Test"}


class WhatCountsAsAMarket(unittest.TestCase):
    def test_markets_of_every_kind(self):
        for name, kind in [("Copley Square Farmers Market", "farmers"), ("Somerville Winter Farmers Market", "farmers"),
                           ("Haymarket Open-Air Produce Market", "farmers"), ("Snowport Holiday Market", "holiday"),
                           ("The Arsenal Holiday Bazaar", "holiday"), ("Harvard Square Holiday Fair", "holiday"),
                           ("SoWa Vintage Market", "flea"), ("Fenway Free Market", "flea"),
                           ("Fall Thrift Festival | Select Markets", "flea"), ("Boston Art Book Fair 2026", "craft"),
                           ("Bow Market Small Business Saturday", "craft"), ("Loy Ka Thong Thai Night Market", "night"),
                           ("SoWa Open Market", "other")]:
            e = {"name": name}
            self.assertTrue(template.is_market(e), name)
            self.assertEqual(template.market_type(e), kind, name)

    def test_places_named_market_and_non_markets_are_not(self):
        for name in ("Boston Public Market Tour", "Language Exchange @ Novo Marketplace", "Comedy at Bow Market",
                     "Free Friday Wine Tastings | DeLuca’s Market", "2026 Quincy Market Holiday Tree Arrives in Boston",
                     "Stock Market Basics", "Digital Marketing Meetup", "College Fair", "Boston Calendar Job Fair", "Farmers' Market Visit",
                     "Lagers and Leaves: A Fall Festival", "Passim Presents Fiddle Funk Folk Festival"):
            self.assertFalse(template.is_market({"name": name}), name)

    def test_festivals_with_stalls_count_and_shows_do_not(self):
        for name, cat, kind in [("ABHC’s Second Annual Fall Harvest Fest", "community", "festival"),
                                ("Greek Cuisine Fall Fest 2026 - Our Autumn Indoor Food Event!", "food", "festival"),
                                ("Boston Loy Krathong Festival 2026 At Chinatown", "community", "festival"),
                                ("Harvard Square Oktoberfest", "markets", "festival"),
                                ("Frozen Fire Festival", "markets", "festival"),
                                ("Medford Winter Festival", "community", "holiday"), ("FALL-iday Fair", "community", "festival")]:
            e = {"name": name, "category": cat}
            self.assertTrue(template.is_vendor_festival(e), name)
            self.assertEqual(template.market_type(e), kind, name)
        for name, cat in [("Passim Presents Fiddle Funk Folk Festival", "community"), ("BCMFest: FULL FESTIVAL PASS", "music"),
                          ("Lagers and Leaves: A Fall Festival", "food"), ("Snowport Social - Let's Meet", "community"),
                          ("2026 Quincy Market Annual Tree Lighting", "community"), ("Boston Jazz Festival", "community"),
                          ("Harvest Festival", "music"), ("Boston Calendar Job Fair", "community"),
                          ("Roslindale Book Festival", "community"), ("Block Party (ages 2 and up)", "community"),
                          ("The Festivals of Drunkenness in the Temple of Mut", "community"), ("Slug Fest", "outdoors"),
                          ("VegFest's 2026 Vegan Thanksliving Potluck", "other")]:
            self.assertFalse(template.is_vendor_festival({"name": name, "category": cat}), name)

    def test_market_held_at_a_market_place_still_counts(self):
        self.assertTrue(template.is_market({"name": "Holiday Pop-Up Market at Boston Public Market"}))


class MarketsPage(unittest.TestCase):
    def setUp(self):
        events = [_ev("Copley Square Farmers Market", 1), _ev("Copley Square Farmers Market", 8),
                  _ev("Kids Holiday Market", 3, category="family"), _ev("SoWa Vintage Market", 4),
                  _ev("Jazz Festival", 2, category="music"), _ev("Boston Public Market Tour", 2, category="community"),
                  _ev("Fall Harvest Fest", 5, category="community")]
        self.html = template.render_hub_page("markets-festivals-boston", events, site_url="https://example.com")

    def test_lists_markets_and_stall_festivals_and_nothing_else(self):
        self.assertIn("Kids Holiday Market", self.html)
        self.assertIn("Fall Harvest Fest", self.html)
        self.assertNotIn("Jazz Festival", self.html)
        self.assertNotIn("Boston Public Market Tour", self.html)

    def test_series_collapse_to_one_card(self):
        self.assertEqual(self.html.count(">Copley Square Farmers Market<"), 1)

    def test_kind_chips_only_for_kinds_present(self):
        self.assertIn('data-mtype="farmers"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="holiday"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="flea"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="festival"', self.html)
        self.assertNotIn('class="hub-city-chip hub-type-chip" data-mtype="night"', self.html)
        self.assertIn("state.type", self.html)


if __name__ == "__main__":
    unittest.main()
