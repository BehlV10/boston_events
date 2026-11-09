"""Hidden Reddit-roundup posting pages (roundup/weekday/, roundup/weekend/).

Rebuilt every morning so the week's post is ready to copy; kept out of search (noindex,
robots.txt Disallow for every crawler group, not in the sitemap).
"""
import os
import re
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import importlib.util  # noqa: E402

# Loaded by path: putting scripts/ on sys.path would shadow tests/ modules (scripts/test_scrapers.py)
_spec = importlib.util.spec_from_file_location("generate_weekday_reddit_roundup",
                                               os.path.join(ROOT, "scripts", "generate_weekday_reddit_roundup.py"))
R = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R)


class RoundupDatesTest(unittest.TestCase):
    def test_weekend_is_this_one_until_sunday(self):
        for today, fri in (("2026-11-09", "2026-11-13"), ("2026-11-13", "2026-11-13"), ("2026-11-14", "2026-11-13")):
            self.assertEqual(R._weekend_start(today), date.fromisoformat(fri), today)
        with patch.object(R, "datetime") as dt:
            dt.now.return_value.date.return_value = date(2026, 11, 15)  # Sunday: next weekend
            self.assertEqual(R._weekend_start(), date(2026, 11, 20))

    def test_days(self):
        self.assertEqual([d.isoformat() for d in R.roundup_days("weekend", "2026-11-13")],
                         ["2026-11-13", "2026-11-14", "2026-11-15"])
        self.assertEqual(len(R.roundup_days("weekday", "2026-11-09")), 5)


class RoundupPageTest(unittest.TestCase):
    BODY = ("Hi **Boston**!\n\n## 📅 FRIDAY\n\n### 🏙️ BOSTON\n"
            "* **[Show <b>](https://x.example/a)** @ Club · *free*  \n  A blurb.\n* Plain\n\n---\n")

    def test_page(self):
        html = R.render_roundup_page("weekend", "Things & stuff", self.BODY)
        self.assertIn('<meta name="robots" content="noindex,nofollow,noarchive">', html)
        self.assertIn('<li><strong><a href="https://x.example/a" target="_blank" rel="noopener">Show &lt;b&gt;</a></strong>'
                      ' @ Club · <em>free</em><br>A blurb.</li>', html)
        self.assertIn("<h2>📅 FRIDAY</h2>", html)
        self.assertIn("Show &lt;b&gt;", re.search(r"<textarea[^>]*>(.*?)</textarea>", html, re.S).group(1))
        for sub, _ in R.SUBREDDITS:
            self.assertIn(f"https://old.reddit.com/r/{sub}/submit?selftext=true&amp;title=Things%20%26%20stuff", html)
        self.assertIn('href="../weekday/"', html)

    def test_hidden_from_crawlers(self):
        with open(os.path.join(ROOT, "robots.txt")) as f:
            groups = f.read().split("User-agent:")[1:]
        self.assertTrue(groups)
        for g in groups:
            self.assertIn("Disallow: /roundup/", g, g.split()[0])

    def test_writes_both_pages(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(R, "build_roundup", side_effect=lambda mode, start=None: (f"{mode} title", self.BODY)):
            R.write_roundup_pages(d)
            for mode in ("weekday", "weekend"):
                with open(os.path.join(d, "roundup", mode, "index.html")) as f:
                    self.assertIn(f"{mode} title", f.read())


if __name__ == "__main__":
    unittest.main()
