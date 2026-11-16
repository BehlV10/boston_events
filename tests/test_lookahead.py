"""Every source should reach at least MIN_LOOKAHEAD_DAYS ahead (paged feeds keep reading)."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402


_BASE = datetime.now(timezone.utc)


def _ev(days, name="x"):
    d = (_BASE + timedelta(days=days)).isoformat()
    return {"name": f"{name}{days}", "date": d, "url": f"https://e/{name}{days}"}


class PagesUntilHorizon(unittest.TestCase):
    def test_reads_pages_until_two_weeks_out(self):
        pages = {n: [_ev(n * 3), _ev(n * 3 + 1)] for n in range(10)}
        calls = []
        out = scrapers._pages_until_horizon(lambda n: calls.append(n) or pages[n], max_pages=10)
        self.assertEqual(calls, [0, 1, 2, 3, 4, 5])  # page 5 (days 15, 16) is the first past two weeks
        self.assertEqual(len(out), 12)

    def test_stops_when_a_page_repeats(self):
        calls = []
        out = scrapers._pages_until_horizon(lambda n: calls.append(n) or [_ev(1)], max_pages=10)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(out), 1)

    def test_only_first_page_failure_raises(self):
        def fetch(n):
            if n:
                raise RuntimeError("page gone")
            return [_ev(1)]
        self.assertEqual(len(scrapers._pages_until_horizon(fetch, max_pages=5)), 1)
        with self.assertRaises(ZeroDivisionError):
            scrapers._pages_until_horizon(lambda n: 1 / 0, max_pages=5)


class TribeIcal(unittest.TestCase):
    def test_steps_list_start_day_until_horizon(self):
        urls = []

        def fake(url, ua):
            urls.append(url)
            k = len(urls) - 1
            return [_ev(k * 2, "a"), _ev(k * 2 + 1, "a")]

        with mock.patch.object(scrapers, "scrape_ical", side_effect=fake):
            out = scrapers.scrape_tribe_ical("https://dance.example/events/?ical=1", "ua")
        self.assertEqual(urls[0], "https://dance.example/events/?ical=1")
        self.assertIn("/events/list/?ical=1&tribe-bar-date=", urls[1])
        self.assertGreaterEqual(max(e["date"] for e in out), scrapers._lookahead_iso())


if __name__ == "__main__":
    unittest.main()
