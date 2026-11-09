"""Lucky Seat lotteries drop off at their close time, whichever list they come from.

Nov 2026: Hadestown stayed on the site weeks after its run. The API blocks GitHub's runners, so
every build reused a saved list that never expired. Lotteries now carry the API's closeTime and
anything past it (or saved before close times were recorded) is dropped.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers as S  # noqa: E402
import template as T  # noqa: E402

NOW = datetime.now(timezone.utc)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
OPEN = {"name": "Dirty Dancing", "venue": "Emerson Colonial Theatre", "price": 45.0,
        "url": "https://www.luckyseat.com/shows/dd", "closes": iso(NOW + timedelta(days=3))}
CLOSED = {"name": "Hadestown", "venue": "Emerson Colonial Theatre", "price": 45.0,
          "url": "https://www.luckyseat.com/shows/hadestown", "closes": iso(NOW - timedelta(days=1))}
LEGACY = {"name": "Wicked", "venue": "Citizens Opera House", "price": 40.0, "url": "https://www.luckyseat.com/shows/w"}


class LuckySeatExpiryTest(unittest.TestCase):
    def setUp(self):
        S._luckyseat_cache.update(data=None, ts=0.0)

    def test_open_keeps_only_future_close_times(self):
        self.assertEqual(S.luckyseat_open([OPEN, CLOSED, LEGACY, {"closes": "garbage"}]), [OPEN])
        self.assertEqual(S.luckyseat_open(None), [])

    def test_api_list_is_filtered(self):
        api = [{"city": "Boston", "isActive": True, "isTempClosed": False, "showName": n, "eventLocation": "X",
                "priceAndFeesTotal": 40.0, "showAlias": a, "closeTime": c}
               for n, a, c in (("Open", "o", OPEN["closes"]), ("Closed", "c", CLOSED["closes"]))]
        with patch.object(S._SESSION, "get", return_value=MagicMock(status_code=200, json=lambda: api)), \
             patch("builtins.open", side_effect=OSError):
            self.assertEqual([s["name"] for s in S.fetch_luckyseat_boston()], ["Open"])

    def test_blocked_api_skips_stale_saved_lists(self):
        """Old cache (no close times) is skipped for a saved list whose lotteries are still open."""
        files = {S.LUCKYSEAT_CACHE_FILE: [CLOSED, LEGACY], S.LUCKYSEAT_COMMITTED_FILE: [OPEN, CLOSED]}
        real_open = open

        def fake_open(path, *a, **k):
            if path in files and "w" not in (a[0] if a else k.get("mode", "r")):
                from io import StringIO
                return StringIO(json.dumps(files[path]))
            return real_open(path, *a, **k)
        with patch.object(S._SESSION, "get", side_effect=Exception("403")), \
             patch("os.path.exists", side_effect=lambda p: p in files or os.path.lexists(p)), \
             patch("builtins.open", side_effect=fake_open):
            self.assertEqual([s["name"] for s in S.fetch_luckyseat_boston()], ["Dirty Dancing"])

    def test_page_never_shows_a_closed_lottery(self):
        with patch("template._load_community_events", return_value=[]), \
             patch("template.fetch_luckyseat_boston", return_value=[OPEN]):
            html = T.render_page([], luckyseat_shows=[CLOSED, LEGACY])
        self.assertNotIn("Hadestown", html)
        self.assertNotIn("luckyseat.com/shows/w", html)
        self.assertIn("Dirty Dancing", html)

    def test_built_in_fallback_has_close_times(self):
        self.assertTrue(S.LUCKYSEAT_FALLBACK_SHOWS)
        self.assertTrue(all(s.get("closes") for s in S.LUCKYSEAT_FALLBACK_SHOWS))


if __name__ == "__main__":
    unittest.main()
