"""Markets & festivals hub: markets from any category plus festivals with stalls, a chip per kind."""
import unittest
from datetime import date, datetime, timedelta

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


class NearMeAndGeocoding(unittest.TestCase):
    def test_near_me_origins_and_sorting_structure(self):
        t1 = datetime.now(EASTERN) + timedelta(days=2)
        t2 = datetime.now(EASTERN) + timedelta(days=3)
        ev1 = _ev("Central Square Flea", 2, venue="Central Square", category="markets")
        ev1.update(_time=t1, date=t1.isoformat())
        ev2 = _ev("Arlington Greek Cuisine Fall Fest", 3, venue="Saint Athanasius the Great Greek Orthodox Church", category="markets")
        ev2.update(_time=t2, date=t2.isoformat())
        html = template.render_hub_page("markets-festivals-boston", [ev1, ev2], site_url="https://example.com")

        # Origin dropdown includes Central Square option
        self.assertIn("Cambridge (Central Sq)", html)
        self.assertIn("42.3653,-71.1030", html)

        # Day sections with dist-grid container for each day
        self.assertIn('class="mk-day-section"', html)
        self.assertIn('class="mk-day-dist-grid mk-grid" hidden', html)

        # Script sorts within day section and daily section, keeping day sections in order
        self.assertIn("document.querySelectorAll('.mk-day-section').forEach", html)
        self.assertIn("sec.querySelector('.mk-day-dist-grid')", html)
        self.assertIn("c._origParent.insertBefore(c, c._origNext || null)", html)

    def test_arlington_greek_fest_and_unknown_venue_coordinates(self):
        t = datetime.now(EASTERN) + timedelta(days=1)
        greek_ev = _ev("Arlington Greek Cuisine Fall Fest", 1, venue="Saint Athanasius the Great Greek Orthodox Church", category="markets")
        greek_ev.update(_time=t, date=t.isoformat())
        card_html = template._render_market_card(greek_ev, "2026-11-13")
        self.assertIn('data-lat="42.4172"', card_html)
        self.assertIn('data-lng="-71.1643"', card_html)

        # An event with no geocoded venue must NOT get fake city_defaults
        unknown_ev = _ev("Mysterious Suburban Flea", 1, venue="Nowhere In Particular 123", category="markets")
        unknown_ev.update(_time=t, date=t.isoformat())
        card_unknown = template._render_market_card(unknown_ev, "2026-11-13")
        self.assertIn('data-lat=""', card_unknown)
        self.assertIn('data-lng=""', card_unknown)
        self.assertNotIn('data-lat="42.3550"', card_unknown)

    def test_tba_date_markets_stay_at_bottom(self):
        t = datetime.now(EASTERN) + timedelta(days=1)
        dated_ev = _ev("Tomorrow Farmers Market", 1, venue="Copley Square", category="markets")
        dated_ev.update(_time=t, date=t.isoformat())
        tba_ev = _ev("Future Festival TBA", 0, venue="Central Square", category="markets")
        tba_ev.update(_time=None, date=None)
        html = template.render_hub_page("markets-festivals-boston", [dated_ev, tba_ev], site_url="https://example.com")
        self.assertIn('id="tba"', html)
        self.assertIn("Date TBA", html)
        self.assertLess(html.index(">Tomorrow Farmers Market<"), html.index(">Future Festival TBA<"))


    def test_multiday_festival_expansion_main_page_and_hub(self):
        # 3-day festival: Fri Nov 13 to Sun Nov 15
        d1 = date(2026, 11, 13)
        d2 = date(2026, 11, 14)
        d3 = date(2026, 11, 15)
        raw_events = [{
            "venue": "Saint Athanasius",
            "url": "https://example.com/arlington",
            "events": [{
                "name": "Arlington Greek Festival",
                "date": "2026-11-13T11:00:00-05:00",
                "end": "2026-11-15T19:00:00-05:00",
                "venue": "Saint Athanasius",
                "category": "markets"
            }]
        }]
        dated, tba, ongoing = template.group_by_date(raw_events)
        dated_dict = {d: evs for d, evs in dated}
        self.assertIn(d1, dated_dict, "Should appear on Friday Nov 13")
        self.assertIn(d2, dated_dict, "Should appear on Saturday Nov 14")
        self.assertIn(d3, dated_dict, "Should appear on Sunday Nov 15")

        # Format on Friday and Saturday shows thru date; Sunday shows Final day
        e_fri = dated_dict[d1][0]
        e_sat = dated_dict[d2][0]
        e_sun = dated_dict[d3][0]
        self.assertIn("thru Sun Nov 15", template.format_when(e_fri))
        self.assertIn("thru Sun Nov 15", template.format_when(e_sat))
        self.assertIn("Final day", template.format_when(e_sun))

        # Check rendering on the markets hub
        hub_events = [e_fri, e_sat, e_sun]
        html = template.render_hub_page("markets-festivals-boston", hub_events, site_url="https://example.com")
        self.assertIn("2026-11-13", html)
        self.assertIn("2026-11-14", html)
        self.assertIn("2026-11-15", html)
        self.assertIn("Through Sun, Nov 15", html)
        self.assertIn("Final day", html)

    def test_multiday_running_today_shows_in_today_bucket(self):
        # Event started yesterday, runs through tomorrow
        today = datetime.now(EASTERN).date()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        raw_events = [{
            "venue": "Boston City Hall Plaza",
            "url": "https://example.com/plaza",
            "events": [{
                "name": "Plaza Weekend Festival",
                "date": f"{yesterday.isoformat()}T10:00:00-05:00",
                "end": f"{tomorrow.isoformat()}T18:00:00-05:00",
                "venue": "City Hall Plaza",
                "category": "markets"
            }]
        }]
        dated, tba, ongoing = template.group_by_date(raw_events)
        dated_dict = {d: evs for d, evs in dated}
        self.assertIn(today, dated_dict, "Festival active today must appear in today's dated bucket")
        self.assertIn(tomorrow, dated_dict, "Festival running tomorrow must appear in tomorrow's bucket")
        self.assertNotIn(yesterday, dated_dict, "Past day should not be in upcoming dated buckets")
        self.assertEqual(len(ongoing), 0, "Actively running multi-day festival should not be relegated to ongoing")

    def test_overnight_event_not_expanded_to_next_day(self):
        # 9 PM Friday to 2 AM Saturday is an overnight show, not a 2-day festival
        raw_events = [{
            "venue": "Middle East",
            "url": "https://example.com/mideast",
            "events": [{
                "name": "Late Night Rock Show",
                "date": "2026-11-13T21:00:00-05:00",
                "end": "2026-11-14T02:00:00-05:00",
                "venue": "The Middle East",
                "category": "music"
            }]
        }]
        dated, tba, ongoing = template.group_by_date(raw_events)
        dated_dict = {d: evs for d, evs in dated}
        self.assertIn(date(2026, 11, 13), dated_dict)
        self.assertNotIn(date(2026, 11, 14), dated_dict, "Overnight show ending 2 AM should not appear on Saturday")

    def test_roslindale_holiday_market_scraper_and_geo(self):
        from scrapers import scrape_roslindale_holiday_market
        from venues_geo import resolve_event_geo
        events = scrape_roslindale_holiday_market("https://www.roslindale.net/2026-holiday-market", "Mozilla/5.0")
        self.assertGreater(len(events), 0)
        ev = events[0]
        self.assertIn("Roslindale Village Annual Holiday Market", ev["name"])
        self.assertEqual(ev["venue"], "Birch St Plaza")
        self.assertEqual(ev["price"], "Free")

        geo = resolve_event_geo(ev)
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Roslindale")
        self.assertAlmostEqual(geo["lat"], 42.2868, places=3)
        self.assertAlmostEqual(geo["lng"], -71.1294, places=3)

    def test_markets_hub_lookahead_and_window(self):
        hub_cfg = template.HUBS["markets-festivals-boston"]
        self.assertEqual(hub_cfg["limit"], 600)
        self.assertEqual(hub_cfg["window_days"], 90)

    def test_all_holiday_markets_have_direct_official_urls(self):
        from scrapers import _ALL_VENUES
        market_venues = [
            "The Arsenal Holiday Bazaar", "11th Annual SoWa Christmas Market",
            "Boston Thanksgiving Market & Harbor Festival", "Stocking Stuffer Holiday Market",
            "Holiday Maker Market at Marzae", "Boston Women's Market at Warehouse XI",
            "Kilroy Square Holiday Market", "Boston Women's Market at The Armory",
            "Sip & Shop at CambridgeSide", "Beacon Hill Holiday Stroll",
            "Christkindlmarkt – German Holiday Market", "Open Newbury Street Holiday Stroll",
            "Winter Market at Sam Adams Brewery", "Union Square Jingle & Holiday Stroll",
            "South End Holiday Stroll", "Cultural Survival Bazaar",
            "Canal District Kendall Winter Market", "2026 Black Business Holiday Marketplace",
            "Station Street Studios Holiday Market", "The Clay Table Holiday Market",
            "The West End Museum Holiday Market", "The Holiday Shoppes at Tuscan Village",
            "Roslindale Village Main Street", "Harvard Square Holiday Fair",
            "Snowport Holiday Market"
        ]
        by_name = {v["name"]: v for v in _ALL_VENUES}
        for name in market_venues:
            self.assertIn(name, by_name, f"Venue {name} must be registered in _ALL_VENUES")
            url = by_name[name]["url"]
            self.assertNotIn("thebostoncalendar.com", url, f"Venue {name} must not point to thebostoncalendar.com: {url}")
            events = by_name[name]["scraper"](url, "Mozilla/5.0")
            self.assertGreater(len(events), 0, f"Scraper for {name} must produce events")
            for ev in events:
                self.assertNotIn("thebostoncalendar.com", ev.get("url", ""), f"Event url for {name} must not be thebostoncalendar: {ev.get('url')}")


if __name__ == "__main__":
    unittest.main()

