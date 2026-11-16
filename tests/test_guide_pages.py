import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import guide_pages as gp  # noqa: E402
import highlights_page as hp  # noqa: E402


def pick(title, curated=False, sort="19:00", city="boston"):
    return {"title": title, "url": f"https://example.com/{title.replace(' ', '-')}", "venue": "Venue", "time": "7PM",
            "sort": sort, "price": "", "area": "", "city": city, "note": "Why" if curated else "", "curated": curated}


def fake_days(today, days=None):
    days = days or [today]
    return [{"date": d, "picks": [pick(f"Show {d.day} {i}", curated=(i == 11)) for i in range(12)]} for d in days], []


class GuidePagesTest(unittest.TestCase):
    def test_writes_main_and_three_month_pages_and_removes_old_months(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, gp.SLUG, "october"))
            with mock.patch.object(gp, "build_highlight_days", side_effect=fake_days):
                gp.write_guide_pages(tmp, "https://example.org", today=date(2026, 11, 16))
            root = os.path.join(tmp, gp.SLUG)
            self.assertEqual(sorted(os.listdir(root)), ["december", "index.html", "january", "november"])
            main = open(os.path.join(root, "index.html"), encoding="utf-8").read()
            self.assertEqual(main.count("<title>"), 1)
            self.assertIn("<title>Things to Do in Boston This Week · Wicked Boston Events</title>", main)
            self.assertIn('href="https://example.org/things-to-do-boston/"', main)  # canonical
            # each day keeps its top picks, hand picks first
            self.assertEqual(main.count('<li class="pick"'), 7 * gp.WEEK_PER_DAY)
            self.assertIn("Show 16 11", main)
            ld = json.loads(re.search(r'ld\+json">(.*?)</script>', main, re.S).group(1))
            self.assertEqual({g["@type"] for g in ld["@graph"]}, {"CollectionPage", "FAQPage"})
            dec = open(os.path.join(root, "december", "index.html"), encoding="utf-8").read()
            self.assertIn("Things to Do in Boston in December 2026", dec)
            self.assertIn('href="../../"', dec)  # nav one level deeper
            self.assertIn('href="../january/"', dec)

    def test_guide_paths_for_sitemap(self):
        self.assertEqual(gp.guide_paths(date(2026, 12, 5)), [
            "things-to-do-boston/", "things-to-do-boston/december/", "things-to-do-boston/january/",
            "things-to-do-boston/february/"])

    def test_highlights_page_has_one_title(self):
        html = hp.render_highlights_page("https://example.org", today=date(2026, 11, 16),
                                         days=[{"date": date(2026, 11, 16), "picks": [pick("A")]}], runs=[])
        self.assertEqual(html.count("<title>"), 1)


if __name__ == "__main__":
    unittest.main()
