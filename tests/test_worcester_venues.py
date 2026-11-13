"""Worcester venues (Palladium, Hanover Theatre) resolve to Worcester and file under Other > Outer Suburbs."""
import unittest

import scrapers as S
import template as T
from venues_geo import resolve_event_geo


class WorcesterVenuesTest(unittest.TestCase):
    def test_registered(self):
        names = {v["name"] for v in S._ALL_VENUES}
        self.assertIn("The Palladium (Worcester)", names)
        self.assertIn("The Hanover Theatre (Worcester)", names)

    def test_geo_and_area(self):
        for venue, source, want in [("Palladium-MA", "The Palladium (Worcester)", "The Palladium"),
                                    ("Hanover Theatre", "The Hanover Theatre (Worcester)", "The Hanover Theatre")]:
            e = {"venue": venue, "_source_venue": source, "name": "Show"}
            geo = resolve_event_geo(e)
            self.assertEqual(geo["venue"], want)
            self.assertIn("Worcester", geo["address"])
            city = T._event_city(venue, source, e)
            self.assertEqual(city, "other")
            self.assertEqual(T.resolve_subarea(city, e, geo)[1], "suburbs_other")

    def test_boston_hanover_street_unaffected(self):
        geo = resolve_event_geo({"venue": "Bricco", "address": "241 Hanover St, Boston", "name": "x"})
        self.assertNotEqual((geo or {}).get("venue"), "The Hanover Theatre")


if __name__ == "__main__":
    unittest.main()
