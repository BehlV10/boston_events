"""Banner top row layout, and two kinds of look-alike listings: a sold-out early show next to its
late show, and the city posting one meeting twice."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import scrapers  # noqa: E402
from template import render_page  # noqa: E402


def _soon(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class SoldOutAndPromoterPrefixTests(unittest.TestCase):
    venue = {"name": "Arts at the Armory", "default_category": "arts"}

    def norm(self, events):
        return [(e["name"], e.get("price")) for e in scrapers._normalize_and_filter_events(events, self.venue)]

    def test_early_sold_out_and_late_show_share_a_name(self):
        got = self.norm([
            {"name": "[SOLD OUT] Bill Blumenreich Presents Joanne McNally: Pinotphile", "date": _soon(2)},
            {"name": "Bill Blumenreich Presents Joanne McNally: Pinotphile", "date": _soon(5), "price": "$45"},
        ])
        self.assertEqual(got, [("Joanne McNally: Pinotphile", "Sold out"), ("Joanne McNally: Pinotphile", "$45")])

    def test_sold_out_variants(self):
        got = self.norm([
            {"name": "SOLD OUT: Big Show", "date": _soon(3), "price": "$20"},
            {"name": "*SOLD OUT* Other Show", "date": _soon(3), "price": "Sold out"},
            {"name": "Soldier's Story", "date": _soon(3)},
        ])
        self.assertEqual(got, [("Big Show", "$20 (sold out)"), ("Other Show", "Sold out"), ("Soldier's Story", None)])


class SomervilleMeetingCopiesTests(unittest.TestCase):
    def test_generic_copy_dropped_only_at_the_same_time(self):
        a, b = "2026-11-05T23:30:00+00:00", "2026-11-19T23:30:00+00:00"
        events = [
            {"name": "Land Use Committee - Joint Session with the Planning Board", "date": a},
            {"name": "Land Use Committee Meeting", "date": a},
            {"name": "Land Use Committee Meeting", "date": b},
            {"name": "City Council Meeting", "date": a},
        ]
        kept = [(e["name"], e["date"]) for e in scrapers._drop_generic_meeting_copies(events)]
        self.assertEqual(kept, [("Land Use Committee - Joint Session with the Planning Board", a),
                                ("Land Use Committee Meeting", b), ("City Council Meeting", a)])


class BannerTopRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = render_page([])

    def test_tag_first_themes_last(self):
        row = re.search(r'<div class="banner-top-row">(.*?)<div class="banner-title-row">', self.html, re.S).group(1)
        order = [row.index(k) for k in ('class="banner-top-tag"', 'id="btn-open-submit-modal"', 'class="theme-toggle-wrap"')]
        self.assertEqual(order, sorted(order))

    def test_grid_areas_desktop_and_phone(self):
        self.assertIn('grid-template-areas: "tag add themes";', self.html)
        phone = re.search(r'@media \(max-width: 640px\) \{\s*\.banner-top-row \{(.*?)\}', self.html, re.S)
        self.assertIsNotNone(phone)
        self.assertIn('"themes themes" "tag add"', phone.group(1))


if __name__ == "__main__":
    unittest.main()
