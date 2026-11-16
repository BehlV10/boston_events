"""Charles River Speedway: the API's first page was a year of the weekly run club, hiding
Brighton Bazaar and Standup at the Speedway. The scraper now pages through a date window."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402


def _row(title, when):
    return {"title": title, "start_date": when.strftime("%Y-%m-%d %H:%M:%S"), "url": "https://charlesriverspeedway.com/e",
            "venue": {"venue": "Charles River Speedway"}, "categories": [{"name": "Art"}]}


class Speedway(unittest.TestCase):
    def test_pages_by_date_and_categorizes(self):
        soon = datetime.now(S.EASTERN).replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(days=5)
        pages = {1: [_row("Meters For Liters: Notch Run Club", soon)] * 50,
                 2: [_row("Brighton Bazaar", soon), _row("Standup at the Speedway", soon.replace(hour=20))]}
        calls = []

        class R:
            def __init__(self, rows):
                self.status_code = 200 if rows is not None else 400
                self._rows = rows

            def json(self):
                return {"events": self._rows or []}

        def fake_get(url, **kw):
            calls.append(url)
            page = int(url.split("&page=")[1].split("&")[0])
            return R(pages.get(page))

        with patch.object(S._SESSION, "get", side_effect=fake_get):
            evs = S.scrape_speedway("https://charlesriverspeedway.com", "ua")
        self.assertTrue(calls[0].startswith("https://charlesriverspeedway.com/wp-json/tribe/events/v1/events?"))
        self.assertIn("start_date=", calls[0])
        cats = {e["name"]: e["category"] for e in evs}
        self.assertEqual(cats["Brighton Bazaar"], "markets")
        self.assertEqual(cats["Standup at the Speedway"], "comedy")


if __name__ == "__main__":
    unittest.main()
