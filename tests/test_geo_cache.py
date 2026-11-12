"""resolve_event_geo is cached: duplicate merging calls it millions of times per build.

Nov 11 2026: uncached, it took ~130 s of the main page's 197 s render, the HTML step passed the
25-minute CI limit, and every build that afternoon timed out without deploying.
"""
import unittest
from unittest import mock

import venues_geo as G


class GeoCache(unittest.TestCase):
    def setUp(self):
        G._GEO_CACHE.clear()

    def test_same_answer_as_uncached(self):
        for e in ({"venue": "The Sinclair"}, {"venue": "Somewhere Unknown", "lat": 42.36, "lng": -71.06},
                  {"venue": "Zoom"}, {"venue": "", "_source_venue": "Brattle Theatre", "name": "Film"}):
            self.assertEqual(G.resolve_event_geo(e), G.resolve_event_geo_uncached(e), e)
            self.assertEqual(G.resolve_event_geo(e), G.resolve_event_geo_uncached(e), e)  # from cache

    def test_resolves_each_venue_once(self):
        e = {"venue": "The Sinclair", "name": "Show"}
        with mock.patch.object(G, "resolve_event_geo_uncached", wraps=G.resolve_event_geo_uncached) as raw:
            for _ in range(1000):
                G.resolve_event_geo(dict(e))
        self.assertEqual(raw.call_count, 1)

    def test_callers_get_their_own_copy(self):
        e = {"venue": "The Sinclair"}
        G.resolve_event_geo(e)["neighborhood"] = "changed"
        self.assertNotEqual(G.resolve_event_geo(e)["neighborhood"], "changed")

    def test_every_field_that_matters_is_in_the_key(self):
        a = G.resolve_event_geo({"venue": "Mystery Hall", "lat": 42.36, "lng": -71.06, "neighborhood": "A"})
        b = G.resolve_event_geo({"venue": "Mystery Hall", "lat": 42.36, "lng": -71.06, "neighborhood": "B"})
        self.assertNotEqual(a, b)

    def test_recomputing_shared_points_clears_the_cache(self):
        G.resolve_event_geo({"venue": "The Sinclair"})
        self.assertTrue(G._GEO_CACHE)
        G.flag_shared_source_points([])
        self.assertFalse(G._GEO_CACHE)

    def test_unhashable_fields_still_resolve(self):
        self.assertEqual(G.resolve_event_geo({"venue": "The Sinclair", "address": ["x"]}),
                         G.resolve_event_geo_uncached({"venue": "The Sinclair", "address": ["x"]}))


if __name__ == "__main__":
    unittest.main()
