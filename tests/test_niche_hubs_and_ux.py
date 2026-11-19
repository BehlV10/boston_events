"""Tests for the 13 niche subpages, alphabetical venue list, suburb town names,
Simple View toggle, top timeframe window placement, and Map/Drop Pin proximity."""
import re
import unittest

import template as T
from venues_geo import resolve_event_geo


class NicheHubsTest(unittest.TestCase):
    EXPECTED_SLUGS = [
        "goth", "lgbtq", "jazz", "film", "theater", "dance", "book",
        "classical", "metal", "crafts", "karaoke", "fitness", "latin",
    ]

    def test_all_13_niche_hubs_registered(self):
        for slug in self.EXPECTED_SLUGS:
            self.assertIn(slug, T.HUBS, f"Missing hub: {slug}")
            self.assertEqual(T.HUBS[slug].get("niche_filter"), slug)

    def test_niche_matching_and_exclusions(self):
        sample_events = [
            {"name": "Crypt - ManRay's Weekly Goth/Industrial Night", "venue": "ManRay", "date": "2026-11-26T21:00:00-05:00", "category": "clubbing"},
            {"name": "Table Saw: Using the SawStop Industrial Cabinet Saw", "venue": "Artisans Asylum", "date": "2026-12-02T18:00:00-05:00", "category": "art"},
            {"name": "Queer Drag Brunch", "venue": "Club Café", "date": "2026-11-22T12:00:00-05:00", "category": "community"},
            {"name": "Sunday Jazz Quartet", "venue": "Wally's", "date": "2026-11-22T20:00:00-05:00", "category": "music", "music_genre": "jazz_blues"},
            {"name": "Vertigo in 35mm", "venue": "Brattle Theatre", "date": "2026-11-22T19:00:00-05:00", "category": "film"},
            {"name": "Hadestown", "venue": "Emerson Colonial Theatre", "date": "2026-11-22T19:30:00-05:00", "category": "theater"},
            {"name": "Bachata Mondays", "venue": "Havana Club", "date": "2026-11-23T20:15:00-05:00", "category": "dance"},
            {"name": "Author Talk: New Novel Launch", "venue": "Harvard Book Store", "date": "2026-11-23T19:00:00-05:00", "category": "books"},
            {"name": "NEC Chamber Music Recital", "venue": "Jordan Hall", "date": "2026-11-23T19:30:00-05:00", "category": "music", "music_genre": "classical"},
            {"name": "Hardcore Punk Showcase", "venue": "O'Brien's Pub", "date": "2026-11-23T20:00:00-05:00", "category": "music"},
            {"name": "Intro to Sheet Metal Welding", "venue": "Artisans Asylum", "date": "2026-11-23T18:00:00-05:00", "category": "art"},
            {"name": "Beginner Pottery Wheel Workshop", "venue": "The Clay Table", "date": "2026-11-23T18:30:00-05:00", "category": "art"},
            {"name": "Lizard Lounge Poetry Jam & Open Mic", "venue": "Lizard Lounge", "date": "2026-11-22T19:00:00-05:00", "category": "music"},
            {"name": "Oil Painting Portraiture Bootcamp", "venue": "Boston Figure Art Center", "date": "2026-11-22T10:00:00-05:00", "category": "art"},
            {"name": "Morning 5K Run Club", "venue": "Night Shift Brewing", "date": "2026-11-22T09:00:00-05:00", "category": "outdoors"},
            {"name": "Noche Latina: Reggaeton & Perreo", "venue": "La Fabrica Central", "date": "2026-11-22T22:00:00-05:00", "category": "clubbing"},
        ]

        goth_names = [e["name"] for e in T.filter_events_for_hub(T.HUBS["goth"], sample_events)]
        self.assertIn("Crypt - ManRay's Weekly Goth/Industrial Night", goth_names)
        self.assertNotIn("Table Saw: Using the SawStop Industrial Cabinet Saw", goth_names)

        metal_names = [e["name"] for e in T.filter_events_for_hub(T.HUBS["metal"], sample_events)]
        self.assertIn("Hardcore Punk Showcase", metal_names)
        self.assertNotIn("Intro to Sheet Metal Welding", metal_names)

        fitness_names = [e["name"] for e in T.filter_events_for_hub(T.HUBS["fitness"], sample_events)]
        self.assertIn("Morning 5K Run Club", fitness_names)
        self.assertNotIn("Oil Painting Portraiture Bootcamp", fitness_names)

        for slug in self.EXPECTED_SLUGS:
            evs = T.filter_events_for_hub(T.HUBS[slug], sample_events)
            self.assertGreaterEqual(len(evs), 1, f"Hub {slug} should match at least 1 sample event")
            html = T.render_hub_page(slug, sample_events)
            self.assertIn(f'<h1>{T.HUBS[slug]["title"]}</h1>', html)


class SuburbTownResolutionTest(unittest.TestCase):
    def test_suburb_towns_resolved_from_address_geo_and_venue(self):
        cases = [
            ({"venue": "Winchester Public Library", "address": "80 Washington St, Winchester, MA 01890"}, "Winchester"),
            ({"venue": "Burlington Public Library", "address": "22 Sears St, Burlington, MA 01803"}, "Burlington"),
            ({"venue": "Tuscan Village", "address": "9 Via Toscana, Salem, NH"}, "Salem, NH"),
            ({"venue": "The Cabot"}, "Beverly"),
            ({"venue": "Lowell Memorial Auditorium"}, "Lowell"),
            ({"venue": "Stone Zoo"}, "Stoneham"),
            ({"venue": "Tsongas Center"}, "Lowell"),
            ({"venue": "Soundcheck Studios"}, "Pembroke"),
            ({"venue": "Our Lady of La Salette"}, "Attleboro"),
            ({"venue": "Six String Grill and Stage"}, "Foxborough"),
        ]
        for ev, expected_town in cases:
            geo = resolve_event_geo(ev)
            self.assertEqual(T.infer_suburb_town(ev, geo), expected_town, f"Failed for {ev}")

    def test_seaport_and_cambridge_hotels_resolve_geo(self):
        self.assertEqual(resolve_event_geo({"venue": "Yotel"})["neighborhood"], "Seaport")
        self.assertEqual(resolve_event_geo({"venue": "Grace By Nia"})["neighborhood"], "Seaport")
        self.assertEqual(resolve_event_geo({"venue": "Kimpton Marlowe Hotel"})["neighborhood"], "East Cambridge")


class MainPageUXTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        results = [
            {"venue": "Zuzu", "url": "https://example.com/zuzu", "events": [{"name": "Late Show", "date": "2026-11-20T21:00:00-05:00", "venue": "Zuzu", "url": "https://example.com/1", "category": "music"}]},
            {"venue": "Aeronaut Brewing", "url": "https://example.com/aeronaut", "events": [{"name": "Beer Night", "date": "2026-11-20T18:00:00-05:00", "venue": "Aeronaut Brewing", "url": "https://example.com/2", "category": "food"}]},
            {"venue": "Middle East", "url": "https://example.com/mideast", "events": [{"name": "Rock Gig", "date": "2026-11-20T20:00:00-05:00", "venue": "Middle East", "url": "https://example.com/3", "category": "music"}]},
        ]
        cls.html = T.render_page(results)

    def test_venues_sorted_alphabetically_in_sidebar(self):
        venues = re.findall(r'class="venue-chk" value="([^"]+)"', self.html)
        self.assertEqual(venues, sorted(venues, key=lambda v: v.strip().lower()))
        self.assertLess(venues.index("Aeronaut Brewing"), venues.index("Middle East"))
        self.assertLess(venues.index("Middle East"), venues.index("Zuzu"))

    def test_simple_view_toggle_and_css_present(self):
        self.assertIn('id="btn-simple-view"', self.html)
        self.assertIn("body.simple-view li.event .desc", self.html)
        self.assertIn("boston_events_simple_view", self.html)

    def test_timeframe_window_moved_next_to_date_picker(self):
        cal_pos = self.html.index('id="cal-toggle"')
        tf_btn_pos = self.html.index('id="timeframe-toggle-btn"')
        week_nav_pos = self.html.index('id="week-nav"')
        sidebar_end = self.html.index("</aside>")
        self.assertGreater(tf_btn_pos, sidebar_end)
        self.assertGreater(tf_btn_pos, week_nav_pos)
        self.assertGreater(tf_btn_pos, cal_pos)
        self.assertLess(tf_btn_pos - cal_pos, 300)

    def test_map_button_grouped_near_drop_pin(self):
        self.assertIn("justify-content: flex-start;", self.html)
        pin_pos = self.html.index('id="btn-drop-pin"')
        map_pos = self.html.index('id="btn-view-map"')
        self.assertGreater(map_pos, pin_pos)
        self.assertLess(map_pos - pin_pos, 400)


if __name__ == "__main__":
    unittest.main()


class FollowUpFixesTest(unittest.TestCase):
    def test_town_names_inside_streets_and_buildings_are_not_towns(self):
        for venue in ["Hanover Street Chapel", "The Reading Room", "Franklin Park", "Lowell House, Harvard"]:
            ev = {"venue": venue}
            town = T.infer_suburb_town(ev, resolve_event_geo(ev))
            self.assertNotIn(town, ("Hanover", "Reading", "Franklin", "Lowell"), venue)

    def test_every_hub_calendar_link_names_a_real_category(self):
        from urllib.parse import parse_qs
        from scrapers import CATEGORY_BUCKETS
        buckets = {name for name, _ in CATEGORY_BUCKETS}
        for slug, hub in T.HUBS.items():
            q = hub.get("query") or ""
            if not q.startswith("#"):
                continue
            for cat in (parse_qs(q[1:]).get("cat") or [""])[0].split(","):
                if cat:
                    self.assertIn(cat, buckets, f"/{slug}/ links to #cat={cat}")
