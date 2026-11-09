"""Which coordinates win when a venue match and a source's own point disagree.

Real cases from events.json (Nov 2026): Ticketmaster put Royale and the Emerson Colonial on one
area point ~800 m from both; the BPL feed's branch points are right while the "boston public
library" pattern points at Copley; a title containing "Sing-A-Long LIVE" matched Long Live Roxbury.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import venues_geo as G  # noqa: E402


def near(geo, lat, lng, meters=150):
    return G._meters(geo["lat"], geo["lng"], lat, lng) <= meters


class ResolveEventGeoTest(unittest.TestCase):
    def setUp(self):
        G.flag_shared_source_points([])

    def test_curated_venue_beats_ticketmaster_area_point(self):
        e = {"venue": "The Sinclair Music Hall", "_source_venue": "Ticketmaster", "lat": 42.380199, "lng": -71.134697}
        geo = G.resolve_event_geo(e)
        self.assertEqual(geo["venue"], "The Sinclair")
        self.assertTrue(near(geo, 42.3746, -71.1207))

    def test_trusted_branch_point_beats_umbrella_pattern(self):
        e = {"venue": "Boston Public Library (South End)", "_source_venue": "Boston Public Library",
             "lat": 42.3416, "lng": -71.0763}
        self.assertTrue(near(G.resolve_event_geo(e), 42.3416, -71.0763, 10))

    def test_title_words_do_not_override_source_point(self):
        e = {"name": "CoComelon: Sing-A-Long LIVE", "venue": "Lynn Arts Annex", "_source_venue": "Ticketmaster",
             "lat": 42.4648, "lng": -70.9512}
        geo = G.resolve_event_geo(e)
        self.assertNotEqual(geo["venue"], "Long Live Roxbury")
        self.assertTrue(near(geo, 42.4648, -70.9512, 10))

    def test_title_pattern_still_used_when_nothing_else(self):
        geo = G.resolve_event_geo({"name": "Jazz night at Wally's", "venue": "", "_source_venue": "Some Calendar"})
        self.assertEqual(geo["venue"], "Wally's Café")

    def test_shared_placeholder_point_is_ignored(self):
        point = {"lat": 42.349602, "lng": -71.075302}
        G.flag_shared_source_points([{"venue": "Ticketmaster", "events": [
            dict(point, venue="Royale Boston"), dict(point, venue="Emerson Colonial Theatre")]}])
        geo = G.resolve_event_geo(dict(point, venue="Some Unlisted Club", _source_venue="Ticketmaster"))
        self.assertIsNone(geo)

    def test_point_on_one_of_its_venues_is_not_a_placeholder(self):
        mfa = {"lat": 42.3394, "lng": -71.0940}
        flagged = G.flag_shared_source_points([{"venue": "Luma", "events": [
            dict(mfa, venue="Museum of Fine Arts"), dict(mfa, venue="465 Huntington Ave, Boston")]}])
        self.assertEqual(flagged, 0)

    def test_rooms_of_one_building_are_not_a_placeholder(self):
        p = {"lat": 42.3633, "lng": -71.1012}
        flagged = G.flag_shared_source_points([{"venue": "Ticketmaster", "events": [
            dict(p, venue="Middle East - Upstairs"), dict(p, venue="Middle East - Downstairs")]}])
        self.assertEqual(flagged, 0)


if __name__ == "__main__":
    unittest.main()
