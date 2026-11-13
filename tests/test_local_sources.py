"""Exhibitions saved from a laptop (local_sources.json) fill in when a museum refuses the build."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import scrapers as S


class LocalExhibitionsTest(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        today = datetime.now(S.EASTERN).date()
        saved = {"exhibitions": {"Isabella Stewart Gardner Museum": [
            {"name": "Open Show", "venue": "Isabella Stewart Gardner Museum", "date": None, "_exhibition": True,
             "_closes": date(today.year + 1, 1, 1).isoformat()},
            {"name": "Closed Show", "venue": "Isabella Stewart Gardner Museum", "date": None, "_exhibition": True,
             "_closes": date(today.year - 1, 1, 1).isoformat()},
        ]}}
        with open(self.path, "w") as f:
            json.dump(saved, f)

    def tearDown(self):
        os.remove(self.path)

    def _scrape(self, gardner_fails):
        def fake_fetch(page, ua):
            if "gardner" in page and gardner_fails:
                raise S.requests.HTTPError("403")
            return None
        pages = (("Museum of Fine Arts (MFA)", "https://www.mfa.org/exhibitions", lambda soup, base: iter(())),
                 ("Isabella Stewart Gardner Museum", "https://www.gardnermuseum.org/exhibitions",
                  lambda soup, base: iter([("Live Show", "https://x", "Through December 31, 2099")])))
        with mock.patch.object(S, "LOCAL_SOURCES_FILE", self.path), \
             mock.patch.object(S, "_EXHIBITION_PAGES", pages), \
             mock.patch.object(S, "fetch_soup", side_effect=fake_fetch):
            return [e["name"] for e in S.scrape_museum_exhibitions("u", "ua") if e["venue"] == "Isabella Stewart Gardner Museum"]

    def test_refused_page_uses_saved_copy_minus_closed(self):
        self.assertEqual(self._scrape(gardner_fails=True), ["Open Show"])

    def test_live_page_wins(self):
        names = self._scrape(gardner_fails=False)
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("Live Show"))

    def test_exhibitions_record_closing_date(self):
        e = S._exhibition("Show", "https://x", "Through January 18, 2099", "V", date(2026, 11, 13))
        self.assertEqual(e["_closes"], "2099-01-18")

    def test_committed_file_is_readable(self):
        data = S.load_local_sources()
        for venue, shows in (data.get("exhibitions") or {}).items():
            self.assertIn(venue, S.LOCAL_REFRESH_EXHIBITIONS)
            for e in shows:
                date.fromisoformat(e["_closes"])


if __name__ == "__main__":
    unittest.main()
