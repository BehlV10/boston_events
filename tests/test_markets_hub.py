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

    def test_the_boston_calendar_holiday_markets_covered(self):
        """Verify all 26 holiday and Christmas markets from The Boston Calendar's guide count as markets."""
        holiday_markets = [
            "The Holiday Market at Snowport 2026",
            "The Arsenal Holiday Bazaar",
            "11th Annual SoWa Christmas Market | November 20–December 27",
            "Boston Thanksgiving Market & Harbor Festival",
            "Stocking Stuffer Holiday Market",
            "Holiday Maker Market at Marzae Cellar + Provisions",
            "Boston Women's Holiday Market at Warehouse XI",
            "Kilroy Square Holiday Market",
            "Bow Market Small Business Saturday",
            "Boston Public Market Holiday Pop-up Market",
            "Boston Women's Holiday Market at The Armory",
            "Sip & Shop at CambridgeSide",
            "Beacon Hill Holiday Stroll and Tree Lighting 2026",
            "Christkindlmarkt – German Holiday Market",
            "Open Newbury Street Holiday Stroll 2026",
            "Winter Market at Sam Adams Brewery",
            "Union Square Jingle & Holiday Stroll",
            "South End Holiday Stroll",
            "Harvard Square Holiday Fair",
            "Cultural Survival Bazaar",
            "Canal District Kendall Winter Market",
            "2026 Black Business Holiday Marketplace",
            "Station Street Studios Holiday Market - Weekend 1",
            "Holiday Market | Pottery & Art Sale | Open Studio Show",
            "The West End Museum Holiday Market",
            "The Holiday Shoppes at Tuscan Village",
        ]
        for name in holiday_markets:
            e = {"name": name, "category": "markets"}
            is_m = template.is_market(e) or template.is_vendor_festival(e)
            self.assertTrue(is_m, f"Expected {name} to be identified as a market/vendor festival")
            m_type = template.market_type(e)
            self.assertIn(m_type, ("holiday", "craft", "night", "festival", "other"), name)


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

    def test_weekly_market_shows_on_each_of_its_days(self):
        self.assertEqual(self.html.count(">Copley Square Farmers Market<"), 2)
        self.assertNotIn('class="mk-daily"', self.html)  # nothing here is open every day

    def test_days_are_split_by_town(self):
        self.assertIn('class="mk-city" data-city=', self.html)
        self.assertIn('class="mk-city-pill', self.html)
        self.assertIn("mk-hero-art", self.html)

    def test_kind_chips_only_for_kinds_present(self):
        self.assertIn('data-mtype="farmers"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="holiday"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="flea"', self.html)
        self.assertIn('class="hub-city-chip hub-type-chip" data-mtype="festival"', self.html)
        self.assertNotIn('class="hub-city-chip hub-type-chip" data-mtype="night"', self.html)
        self.assertIn("state.type", self.html)

    def test_hero_bar_has_full_calendar_button_on_right(self):
        self.assertIn('class="mk-hero-bar"', self.html)
        self.assertIn('>Full calendar →</a>', self.html)
        self.assertNotIn('>See them on the full calendar →</a>', self.html)


class DailyAndHours(unittest.TestCase):
    def _day(self, d, h=15, end_h=20):
        t = (datetime.now(EASTERN) + timedelta(days=d)).replace(hour=h, minute=0, second=0, microsecond=0)
        e = _ev("Snowport Holiday Market", d, venue="Snowport Holiday Market", category="markets")
        e.update(_time=t, date=t.isoformat(), end=t.replace(hour=end_h).isoformat())
        return e

    def test_a_market_open_every_day_is_one_card_up_top(self):
        snow = [self._day(d) for d in range(1, 15) if d != 6]  # closed one day
        weekly = [_ev("Copley Square Farmers Market", d) for d in (2, 9)]
        events = sorted(snow + weekly, key=lambda e: e["_time"])
        daily, dated = template._markets_split(events)
        self.assertEqual([e["name"] for e in daily], ["Snowport Holiday Market"])
        self.assertEqual([e["name"] for e in dated], ["Copley Square Farmers Market"] * 2)
        html = template.render_hub_page("markets-festivals-boston", events, site_url="https://example.com")
        self.assertEqual(html.count(">Snowport Holiday Market<"), 1)
        self.assertLess(html.index('class="mk-daily"'), html.index(">Copley Square Farmers Market<"))
        closed = (datetime.now(EASTERN) + timedelta(days=6)).strftime("%b %-d")
        self.assertIn("Most days through", html)
        self.assertIn(f"closed {closed}", html)
        self.assertIn("3 – 8 pm", html)

    def test_weekends_only_is_not_daily(self):
        events = [self._day(d) for d in range(1, 29) if d % 7 in (5, 6)]
        daily, dated = template._markets_split(events)
        self.assertEqual((len(daily), len(dated)), (0, len(events)))

    def test_hours(self):
        t = datetime(2026, 11, 14, 10, 0, tzinfo=EASTERN)
        h = lambda **kw: template._market_hours({"_time": t, "date": t.isoformat(), **kw})
        self.assertEqual(h(end=t.replace(hour=16).isoformat()), "10 am – 4 pm")
        self.assertEqual(h(end=t.replace(hour=11, minute=30).isoformat()), "10 – 11:30 am")
        self.assertEqual(h(), "10 am")
        self.assertEqual(h(end=(t - timedelta(hours=1)).isoformat()), "10 am")  # end before start: ignored
        self.assertEqual(template._market_hours({"_time": t, "date": "2026-11-14"}), "Time TBA")


class HeaderBar(unittest.TestCase):
    def test_guide_pages_link_only_finished_pages(self):
        nav = template._main_hub_nav("boston")
        self.assertEqual(nav.count("<a "), 5)
        for href in ("../", "../kids-family-events-boston/", "../summer-camps/", "../markets-festivals-boston/", "../college/"):
            self.assertIn(f'href="{href}"', nav)
        html = template.render_hub_page("markets-festivals-boston", [], site_url="https://example.com")
        self.assertIn('<a href="../markets-festivals-boston/" class="active">Markets &amp; Festivals</a>', html)
        self.assertNotIn('href="../comedy/"', html)


if __name__ == "__main__":
    unittest.main()
