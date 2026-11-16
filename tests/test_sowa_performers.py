"""SoWa Christmas Market performers come from the entertainment page (Matt Koelsch, Nov 20 2026,
6-9 PM, was missing because only the winter-festival page was read)."""
import os
import sys
import unittest
from datetime import date

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402

PAGE = ("<h4>November 19</h4><p>6:00 PM – 9:00 PM: Yesterday Band</p>"
        "<h4>November 20</h4><p>6:00 PM – 9:00 PM: Matt Koelsch</p>"
        "<h4>December 3</h4><p><strong>Country Night</strong><br />6:00 PM – 9:00 PM: JP Line Dance<br />"
        "5:00 PM – 9:00 PM: Mechanical Bull</p>"
        "<h4>December 19 </h4><p>11:00 AM – 2:00 PM: Matt Koelsche</p>"
        "<h4>Address</h4><p>530 Harrison Ave</p>")


class SowaPerformers(unittest.TestCase):
    def test_each_set_is_an_event(self):
        evs = S._sowa_christmas_performers(BeautifulSoup(PAGE, "html.parser"), today=date(2026, 11, 20))
        got = [(e["date"], e["end"], e["name"]) for e in evs]
        self.assertEqual(got, [
            ("2026-11-20T23:00:00+00:00", "2026-11-21T02:00:00+00:00", "Matt Koelsch at the SoWa Christmas Market"),
            ("2026-12-03T23:00:00+00:00", "2026-12-04T02:00:00+00:00", "Country Night: JP Line Dance at the SoWa Christmas Market"),
            ("2026-12-03T22:00:00+00:00", "2026-12-04T02:00:00+00:00", "Country Night: Mechanical Bull at the SoWa Christmas Market"),
            ("2026-12-19T16:00:00+00:00", "2026-12-19T19:00:00+00:00", "Matt Koelsche at the SoWa Christmas Market"),
        ])
        self.assertTrue(all(e["venue"] == "SoWa Power Station" and e["category"] == "music" for e in evs))

    def test_missing_page(self):
        self.assertEqual(S._sowa_christmas_performers(None), [])


if __name__ == "__main__":
    unittest.main()
