"""Later days load one file at a time (days/<date>.html) instead of all at once.

Complaint (Nov 2026): refreshing on Friday showed an empty page for seconds. Days after the first
three came from one 14 MB file (1.33 MB gzipped) that had to download and parse before Friday could
show, and "No events found" filled the wait. Checked in throttled headless Chrome: Friday appeared
at 2.5 s instead of 7.1 s, "Loading events…" instead of "No events found", Saturday instant after,
and "All upcoming" still showed every day (123 days, 9,207 events, same as before).
"""
import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import template as T  # noqa: E402

DAYS_DIR = os.path.join(ROOT, "days")


def _render(n_days):
    base = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    venues = [{"venue": f"Venue {i}", "url": f"https://v{i}.example.org/", "error": None,
               "events": [{"name": f"Night {i}", "date": (base + timedelta(days=i)).isoformat(), "venue": "Club Passim",
                           "url": f"https://v{i}.example.org/e", "price": "$10", "category": "music"}]}
              for i in range(n_days)]
    with patch("template._load_community_events", return_value=[]):
        return T.render_page(venues)


class DayFilesTest(unittest.TestCase):
    def test_one_file_per_later_day_and_the_page_lists_them(self):
        stale = os.path.join(DAYS_DIR, "2001-01-01.html")
        os.makedirs(DAYS_DIR, exist_ok=True)
        open(stale, "w").close()
        html = _render(8)
        files = sorted(os.listdir(DAYS_DIR))
        self.assertNotIn("2001-01-01.html", files, "days that have passed are removed")
        listed = json.loads(re.search(r"const DEFERRED_DATES = new Set\((\[.*?\])\);", html).group(1))
        self.assertEqual([f"{d}.html" for d in listed], files)
        self.assertGreaterEqual(len(files), 4)                       # first three days stay in the page
        for d in listed:
            self.assertNotIn(f'data-date="{d}"', html)
            with open(os.path.join(DAYS_DIR, f"{d}.html")) as f:
                self.assertEqual(re.findall(r'<section class="day[^"]*" data-date="([^"]+)"', f.read()), [d])

    def test_view_loads_only_its_days_and_shows_loading(self):
        html = _render(8)
        self.assertIn("fetch(`days/${d}.html`)", html)
        self.assertIn("noEventsEl.style.display = (visibleDays === 0 && !viewLoading)", html)
        self.assertIn('id="days-loading"', html)
        self.assertNotIn("requestIdleCallback(() => ensureDeferredDaysHydrated()", html)  # no 14 MB idle load


if __name__ == "__main__":
    unittest.main()
