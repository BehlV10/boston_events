"""Distraction Brewing (Roslindale): events from the list its own events page reads."""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402

ROWS = [
    {"date": "2026-11-20", "time": "6:30PM-8:30PM", "title": "Coastwise Radio - Live Music", "description": ""},
    {"date": "2026-11-21", "time": "7-9PM", "title": "History of the WNBA - Rozzie Bound Book Series", "description": ""},
    {"date": "2026-11-22", "time": "6PM-10PM", "title": "Private Event - Taproom Closed", "description": ""},
    {"date": "2026-10-01", "time": "8:00pm", "title": "Past Show", "description": ""},
    {"date": "2026-11-23", "time": "TBD", "title": "Dumpling Fest!", "description": ""},
]


class DistractionBrewingTest(unittest.TestCase):
    def test_events(self):
        fixed = datetime(2026, 11, 12, 9, tzinfo=scrapers.EASTERN)
        real_dt = scrapers.datetime

        class _DT(real_dt):
            @classmethod
            def now(cls, tz=None):
                return fixed

        resp = MagicMock()
        resp.json.return_value = ROWS
        with patch.object(scrapers, "datetime", _DT), patch.object(scrapers._SESSION, "get", return_value=resp):
            evs = scrapers.scrape_distraction_brewing("https://distractionbrewingco.com/events", "ua")
        by = {e["name"]: e for e in evs}
        self.assertEqual(set(by), {"Coastwise Radio", "History of the WNBA - Rozzie Bound Book Series", "Dumpling Fest!"})
        self.assertEqual(by["Coastwise Radio"]["date"], "2026-11-20T23:30:00+00:00")  # 6:30 PM ET
        self.assertEqual(by["Coastwise Radio"]["category"], "music")
        self.assertEqual(by["History of the WNBA - Rozzie Bound Book Series"]["date"], "2026-11-22T00:00:00+00:00")
        self.assertEqual(by["Dumpling Fest!"]["time"], "TBD")
        self.assertTrue(all(e["venue"] == "Distraction Brewing" for e in evs))

    def test_start_times(self):
        for text, want in (("6:30PM-8:30PM", (18, 30)), ("7-9PM", (19, 0)), ("8:00pm", (20, 0)),
                           ("5:15 PM", (17, 15)), ("12-2PM", (12, 0)), ("", None), ("TBD", None)):
            self.assertEqual(scrapers._distraction_start(text), want, text)


if __name__ == "__main__":
    unittest.main()
