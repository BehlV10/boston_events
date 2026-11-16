"""The public highlights page: two weeks shown by default, three weeks in the page, linked and indexed."""
import os
import re
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import highlights_page as hp  # noqa: E402
import server  # noqa: E402

TODAY = date(2026, 11, 16)


def _days():
    pick = {"title": "Show <b>", "url": "https://example.com/show", "venue": "Club", "time": "8PM", "sort": "20:00",
            "price": "$20", "area": "Allston", "city": "boston", "note": "Worth it.", "curated": True}
    plain = dict(pick, title="Other", url="javascript:alert(1)", curated=False, city="cambridge", note="")
    plain["url"] = hp._safe_url(plain["url"])
    return [{"date": TODAY + timedelta(days=i), "picks": [pick, plain]} for i in range(hp.MAX_DAYS)]


class HighlightsPage(unittest.TestCase):
    def setUp(self):
        self.html = hp.render_highlights_page("https://example.com", today=TODAY, days=_days(), runs=[])

    def test_three_weeks_in_page_two_shown(self):
        self.assertEqual(len(re.findall(r'<section class="day"', self.html)), 21)
        self.assertEqual(len(re.findall(r'<section class="day"[^>]* hidden>', self.html)), 7)
        self.assertIn('id="to" value="2026-11-29"', self.html)
        self.assertIn('max="2026-12-06"', self.html)

    def test_escapes_and_drops_unsafe_links(self):
        self.assertIn("Show &lt;b&gt;", self.html)
        self.assertNotIn("javascript:", self.html)

    def test_curated_marked_and_canonical(self):
        self.assertIn('data-curated="1"', self.html)
        self.assertIn("https://example.com/boston-event-highlights/", self.html)
        self.assertIn('<a href="../boston-event-highlights/" class="active">Highlights</a>', self.html)

    def test_in_sitemap(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sitemap.xml")
            server.write_sitemap(path, "https://example.com")
            self.assertIn("<loc>https://example.com/boston-event-highlights/</loc>", open(path).read())

    def test_real_picks_build(self):
        days, runs = hp.build_highlight_days()
        self.assertEqual(len(days), hp.MAX_DAYS)
        for day in days:
            for p in day["picks"]:
                self.assertTrue(p["url"] == "" or p["url"].startswith("http"))


if __name__ == "__main__":
    unittest.main()
