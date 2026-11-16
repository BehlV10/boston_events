"""Default hub pages (music, comedy, free, boston, ...) are a one-column list grouped by day, then city."""
import os
import sys
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import template as T  # noqa: E402


def _ev(name, venue, address, day, hour):
    t = (datetime.now(T.EASTERN) + timedelta(days=day)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"name": name, "venue": venue, "address": address, "url": "https://example.com/" + name.replace(" ", "-"),
            "category": "music", "_time": t, "date": t.isoformat()}


EVENTS = [
    _ev("Boston Show", "Paradise Rock Club", "967 Commonwealth Ave, Boston, MA 02215", 1, 19),
    _ev("Cambridge Show", "The Sinclair", "52 Church St, Cambridge, MA 02138", 1, 20),
    _ev("Somerville Show", "The Rockwell", "255 Elm St, Somerville, MA 02144", 1, 21),
    _ev("Next Day Show", "The Sinclair", "52 Church St, Cambridge, MA 02138", 2, 20),
]


class HubListLayoutTest(unittest.TestCase):
    def test_multi_city_hub_groups_each_day_by_city(self):
        html = T.render_hub_page("music", list(EVENTS))
        self.assertIn('<body class="list-hub">', html)
        first_day = html.split('class="hub-day"')[1]
        order = [first_day.index(f'class="hub-city-section" data-city="{c}"') for c in ("cambridge", "somerville", "boston")]
        self.assertEqual(order, sorted(order))  # same Cambridge / Somerville / Boston order as the other hubs
        self.assertEqual(html.count('class="hub-day"'), 2)
        self.assertIn('class="hub-card hub-row"', html)

    def test_single_city_hub_has_no_city_sections(self):
        hub_city = T.HUBS["boston"]["city_filter"]
        self.assertTrue(hub_city)
        html = T.render_hub_page("boston", list(EVENTS))
        self.assertIn('<body class="list-hub">', html)
        self.assertNotIn('<div class="hub-city-section"', html)

    def test_special_hubs_keep_their_own_layout(self):
        html = T.render_hub_page("college", list(EVENTS))
        self.assertNotIn('class="list-hub"', html)


if __name__ == "__main__":
    unittest.main()
