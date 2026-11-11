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
        html = R.render_roundup_page("weekday", "Things & stuff", self.BODY)
        self.assertIn('<meta name="robots" content="noindex,nofollow,noarchive">', html)
        self.assertIn('<li><strong><a href="https://x.example/a" target="_blank" rel="noopener">Show &lt;b&gt;</a></strong>'
                      ' @ Club · <em>free</em><br>A blurb.</li>', html)
        self.assertIn("<h2>📅 FRIDAY</h2>", html)
        self.assertIn("Show &lt;b&gt;", re.search(r"<textarea[^>]*>(.*?)</textarea>", html, re.S).group(1))
        for sub, _ in R.SUBREDDITS:
            self.assertIn(f"https://old.reddit.com/r/{sub}/submit?selftext=true&amp;title=Things%20%26%20stuff", html)
        for other in ("weekend", "weekend-cambridge", "weekend-somerville"):
            self.assertIn(f'href="../{other}/"', html)

    def test_city_pages_post_only_to_their_own_sub(self):
        html = R.render_roundup_page("weekend", "T", self.BODY, page="weekend-cambridge")
        self.assertIn("r/CambridgeMA/submit", html)
        for sub in ("r/boston/", "r/Somerville/", "r/BostonSocialClub/"):
            self.assertNotIn(sub + "submit", html)
        self.assertIn("<h1>Cambridge weekend roundup</h1>", html)

    def test_hidden_from_crawlers(self):
        with open(os.path.join(ROOT, "robots.txt")) as f:
            groups = f.read().split("User-agent:")[1:]
        self.assertTrue(groups)
        for g in groups:
            self.assertIn("Disallow: /roundup/", g, g.split()[0])

    def test_writes_every_page(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(R, "build_roundup",
                          side_effect=lambda mode, start=None, city=None: (f"{mode} {city} title", self.BODY)):
            R.write_roundup_pages(d)
            for slug, mode, city in (("weekday", "weekday", None), ("weekend", "weekend", None),
                                     ("weekend-cambridge", "weekend", "cambridge"),
                                     ("weekend-somerville", "weekend", "somerville")):
                with open(os.path.join(d, "roundup", slug, "index.html")) as f:
                    self.assertIn(f"{mode} {city} title", f.read())


class PostFormatTest(unittest.TestCase):
    """**[SIX60](url)** @ Brighton Music Hall · 7PM · $26-$36 · Allston & Brighton, blurb below."""

    def _ev(self, **kw):
        from datetime import datetime
        e = {"name": "SIX60", "url": "https://t.example/six60", "venue": "Brighton Music Hall",
             "price": "$26-$36", "_time": datetime(2026, 11, 13, 19, 0, tzinfo=R.EASTERN),
             "_highlight": {"note": "Kiwi roots-reggae rockers, up close."}}
        e.update(kw)
        return e

    def test_one_at_then_dots(self):
        with patch.object(R, "_area", return_value="Allston & Brighton"):
            line = R._line(self._ev())
        self.assertEqual(line, "* **[SIX60](https://t.example/six60)** @ Brighton Music Hall · 7PM · $26-$36 · "
                               "Allston & Brighton  \n  Kiwi roots-reggae rockers, up close.")
        self.assertEqual(line.count(" @ "), 1)

    def test_missing_parts_leave_no_stray_dots(self):
        from datetime import datetime
        with patch.object(R, "_area", return_value=""):
            line = R._line(self._ev(price="", _highlight=None,
                                    _time=datetime(2026, 11, 13, 0, 0, tzinfo=R.EASTERN)))
        self.assertEqual(line, "* **[SIX60](https://t.example/six60)** @ Brighton Music Hall")

    def test_tracking_params_are_dropped(self):
        self.assertEqual(R._clean_url("https://v.example/e?_gl=1*abc*_ga*X&id=5"), "https://v.example/e?id=5")
        self.assertEqual(R._clean_url("https://v.example/e?fbclid=abc"), "https://v.example/e")
        self.assertEqual(R._clean_url("https://v.example/e?cp=true"), "https://v.example/e?cp=true")

    def test_other_towns_are_not_in_the_city(self):
        self.assertTrue(R.OTHER_TOWN_RE.search("110 S Border Rd (Medford)"))
        self.assertFalse(R.OTHER_TOWN_RE.search("Somerville Theatre"))


class CityPostTest(unittest.TestCase):
    """Built from the real events.json: the city posts carry only their own city."""

    @classmethod
    def setUpClass(cls):
        cls.posts = {c: R.build_roundup("weekend", city=c) for c in ("cambridge", "somerville")}
        cls.main = R.build_roundup("weekend")

    def test_city_posts(self):
        for c, (title, body) in self.posts.items():
            name = R.CITY_NAMES[c]
            self.assertIn(f"Things to do in {name} this weekend", title)
            self.assertNotIn("### ", body.split("---")[0], "a single-city post has no per-city headings")
            for day in body.split("## 📅 ")[1:]:
                self.assertLessEqual(day.split("---")[0].count("\n* "), R.CITY_POST_PICKS)
            self.assertLessEqual(len(body), R.REDDIT_LIMIT)

    def test_main_post_has_up_to_ten_per_city(self):
        _, body = self.main
        for section in body.split("### ")[1:]:
            self.assertLessEqual(section.split("\n## ")[0].split("---")[0].count("\n* "), R.WEEKEND_PER_CITY)



if __name__ == "__main__":
    unittest.main()
