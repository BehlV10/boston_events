"""Hand-entered exhibitions (MIT Museum) show while open and drop off after closing."""
import unittest
from unittest import mock

import scrapers as S


class CuratedExhibitionsTest(unittest.TestCase):
    def test_split_second_listed_while_open(self):
        with mock.patch.object(S, "_EXHIBITION_PAGES", (("X", "u", lambda s, b: iter(())),)), \
             mock.patch.object(S, "fetch_soup", return_value=None):
            events = S.scrape_museum_exhibitions("u", "ua")
        mit = [e for e in events if e["venue"] == "MIT Museum"]
        if S.datetime.now(S.EASTERN).date() <= S.date(2027, 1, 4):
            self.assertEqual(len(mit), 1)
            self.assertTrue(mit[0]["name"].startswith("Split | Second (through Jan 4)"))
            self.assertTrue(mit[0]["_exhibition"])

    def test_curated_entries_are_well_formed(self):
        for name, url, venue, opens, closes in S._CURATED_EXHIBITIONS:
            self.assertLess(opens, closes, name)
            self.assertTrue(url.startswith("https://"), name)


if __name__ == "__main__":
    unittest.main()
