"""A tab restored hours or days later reloads if the site was redeployed since.

Complaint (Nov 2026): opening wickedbostonevents.com from a tab left open for days still showed the
old day. The page rolls its "today" forward on return, but its events are from the old build.
Checked in headless Chrome over HTTP: restored from back/forward cache with a newer deploy -> reload;
same deploy -> stay; quick tab switch -> no request; back after 2 h with a newer deploy -> reload.
"""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402


class StaleRefreshTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("template._load_community_events", return_value=[]):
            cls.html = T.render_page([])

    def test_compares_live_deploy_with_this_copy(self):
        self.assertIn("fetch(location.pathname, { method: 'HEAD', cache: 'no-store' })", self.html)
        self.assertIn("Date.parse(document.lastModified)", self.html)
        self.assertIn("if (res.ok && live && mine && live - mine > 60 * 1000) location.reload();", self.html)

    def test_runs_on_return_restore_and_new_day(self):
        self.assertIn("refreshIfStale(false);", self.html)                 # tab shown again
        self.assertIn("if (ev.persisted) {", self.html)                    # back/forward cache restore
        self.assertIn("refreshIfStale(true);  // a new day", self.html)    # date rolled over

    def test_skips_quick_switches_on_a_fresh_page(self):
        self.assertIn("Date.now() - PAGE_OPENED_AT < 60 * 60 * 1000 && away < 30 * 60 * 1000", self.html)


if __name__ == "__main__":
    unittest.main()
