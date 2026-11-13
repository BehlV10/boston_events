"""HAN (Allston) files under Boston; LEGO Discovery Center (Assembly Row) under Somerville."""
import unittest

import template as T
from venues_geo import resolve_event_geo


class HanLegoGeoTest(unittest.TestCase):
    def _where(self, ev):
        geo = resolve_event_geo(ev)
        city = T._event_city(ev["venue"], ev["_source_venue"], ev)
        return geo, city, T.resolve_subarea(city, ev, geo)

    def test_han_is_boston_allston(self):
        # Eventbrite gives coordinates but no address
        geo, city, sub = self._where({"venue": "HAN", "_source_venue": "Eventbrite Boston", "name": "HAN Fridays",
                                      "lat": "42.3509805", "lng": "-71.1310421"})
        self.assertEqual(city, "boston")
        self.assertEqual(sub[1], "allston_brighton")
        self.assertIn("186 Harvard Ave", geo["address"])

    def test_lego_discovery_center_is_somerville(self):
        for src in ("Do617", "The Boston Calendar", "Assembly Row"):
            geo, city, sub = self._where({"venue": "LEGO Discovery Center", "_source_venue": src, "name": "Adult Night"})
            self.assertEqual(city, "somerville", src)
            self.assertEqual(sub[1], "assembly_east", src)
            self.assertIn("598 Assembly Row", geo["address"])


if __name__ == "__main__":
    unittest.main()
