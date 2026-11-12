"""Hidden Reddit-roundup posting pages (roundup/weekday/, roundup/weekend/).

Rebuilt every morning so the week's post is ready to copy; kept out of search (noindex,
robots.txt Disallow for every crawler group, not in the sitemap).
"""
import json
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
            self.assertTrue(body.startswith(f"Hey {name}!"))
            days = body.split("\n# 📅 ")[1:]
            self.assertTrue(days, "day headings are top-level '# 📅'")
            for day in days:
                self.assertLessEqual(day.count("\n* "), R.CITY_POST_PICKS)
                for line in day.splitlines():
                    self.assertFalse(line.startswith("  "), "blurbs sit on the event's own line, not below it")
            self.assertIn("Curated from 300+ local venue calendars", body)
            self.assertLessEqual(len(body), R.REDDIT_LIMIT)

    def test_city_line_format(self):
        e = {"name": "Neurodivergent Happy Hour", "url": "https://p.example/e",
             "venue": "Tuck's Arcadium, 36 John F. Kennedy St, Cambridge, MA 02138",
             "_highlight": {"note": "A low-key hangout."}}
        line = R._city_line(e)
        self.assertTrue(line.startswith("* [**Neurodivergent Happy Hour**](https://p.example/e) @ Tuck's Arcadium"), line)
        self.assertTrue(line.endswith(" — A low-key hangout."), line)
        self.assertEqual(R._city_venue({"venue": "The Burren — The Back Room"}), "The Burren (The Back Room)")

    def test_blurb_from_description(self):
        d = "Haitian folk dance and live drumming from a Boston company. Tickets $35."
        self.assertEqual(R._blurb({"description": d}), "Haitian folk dance and live drumming from a Boston company.")
        self.assertEqual(R._blurb({"description": d}, frozenset([d])), "", "venue stock text says nothing about the event")
        self.assertEqual(R._blurb({"description": "Eventbrite - X presents Y - Friday, Nov 13. Find event and ticket information."}), "")
        self.assertEqual(R._blurb({"description": "Doors 7pm / $15 advance / all ages. Bring friends along tonight please."}), "")

    def test_news_labels(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"items": [{"date": "2026-11-12", "label": "EDM fans", "text": "A page."},
                                 {"date": "2026-11-12", "text": "Plain."}]}, f)
        self.assertEqual(R.whats_new(date(2026, 11, 13), f.name), ["* **EDM fans:** A page.", "* Plain."])

    def test_main_post_has_up_to_ten_per_city(self):
        _, body = self.main
        for section in body.split("### ")[1:]:
            self.assertLessEqual(section.split("\n## ")[0].split("---")[0].count("\n* "), R.WEEKEND_PER_CITY)




class RealEventsOnlyTest(unittest.TestCase):
    """Places, standing offers and weekly fixtures aren't weekend events (Nov 13 2026 posts had a
    rooftop pickleball garden, free museum admission and a bike path in every day)."""

    def test_standing_listings(self):
        day = date(2026, 11, 14)
        self.assertTrue(R._is_standing({"time": "Through 12/31", "ends": "2026-12-31"}, day))
        self.assertTrue(R._is_standing({"ends": "2026-11-30"}, day))
        self.assertFalse(R._is_standing({"ends": "2026-11-15"}, day))  # a weekend festival
        self.assertFalse(R._is_standing({"time": "8PM"}, day))

    def test_fixture_titles(self):
        for t in ("Sing Ur Heart Out at Sunday Karaoke", "Painted Burro Bottomless Brunch!!", "Portico Brewing Patio",
                  "Free Admission to the Harvard Art Museums", "DJ at The Chester Tavern"):
            self.assertTrue(R.FIXTURE_TITLE_RE.search(t), t)
        for t in ("Emo Philips", "Lagers and Leaves: A Fall Festival", "Boston Swing Central- Friday Dance"):
            self.assertFalse(R.FIXTURE_TITLE_RE.search(t), t)

    def test_reworded_duplicates_and_mojibake(self):
        self.assertTrue(R._similar_titles("Loy Kra Thong Thai Night Market @ Harvard Square",
                                          "Loy Ka Thong Thai Night Market (Cambridge) - Hostless"))
        self.assertFalse(R._similar_titles("Boston Comedy Festival Presents: Emo Philips",
                                           "BOSTON COMEDY FESTIVAL FINALS"))
        self.assertEqual(R._fix_mojibake("Brian O’Donovan".encode("utf-8").decode("cp1252")), "Brian O’Donovan")
        self.assertEqual(R._fix_mojibake("Café"), "Café")

    def test_built_posts(self):
        import json as _json
        def ev(name, hour, **kw):
            return {"name": name, "date": f"2026-11-14T{hour:02d}:00:00-05:00", "url": "https://example.com/" + name[:5],
                    **kw}
        venues = [
            {"venue": "The Boston Calendar", "events": [
                ev("Secret Rooftop Garden in Kendall Square", 10, venue="Urban Park Roof Garden, Cambridge",
                   time="Through 11/30", ends="2026-11-30"),
                ev("Live Music at Remnant Satellite", 10, venue="Remnant Satellite, Cambridge", time="Through 12/31",
                   ends="2026-12-31")]},
            {"venue": "The Sinclair", "events": [ev("Donny Benet", 20, venue="The Sinclair", price="$40")]},
            {"venue": "Tufts University", "events": [ev("Tufts Choruses", 15, venue="Medford/Somerville campus")]},
        ]
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "events.json"), "w") as f:
                _json.dump({"venues": venues}, f)
            with patch.object(R, "ROOT", d):
                _, cam = R.build_roundup("weekend", "2026-11-13", city="cambridge")
                _, som = R.build_roundup("weekend", "2026-11-13", city="somerville")
        self.assertIn("Donny Benet", cam)
        self.assertNotIn("Rooftop", cam)
        self.assertNotIn("Remnant Satellite", cam)
        self.assertNotIn("Tufts", som)


class WhatsNewAndLinksTest(unittest.TestCase):
    def test_news_shows_for_a_week(self):
        import json as _json
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            _json.dump({"items": [{"date": "2026-11-11", "text": "Markets page"},
                                  {"date": "2026-10-01", "text": "Old news"}]}, f)
        try:
            self.assertEqual(R.whats_new(date(2026, 11, 13), f.name), ["* Markets page"])
            self.assertEqual(R.whats_new(date(2026, 11, 20), f.name), [])   # over a week old
            self.assertEqual(R.whats_new(date(2026, 11, 6), f.name), [])    # not happened yet
        finally:
            os.unlink(f.name)
        self.assertEqual(R.whats_new(date(2026, 11, 13), "/nonexistent.json"), [])

    def test_real_news_file_parses(self):
        import json as _json
        with open(R.NEWS_PATH, encoding="utf-8") as f:
            for it in _json.load(f)["items"]:
                date.fromisoformat(it["date"])
                self.assertTrue(it["text"])

    def test_food_and_drink_deals_are_not_events(self):
        for t in ("$1 Oysters at Vera's!", "$5 Margaritas", "$2 Tacos Tuesday"):
            self.assertTrue(R.DEAL_TITLE_RE.search(t), t)
        for t in ("$5 Comedy Night", "Oyster Festival", "Bob Bradshaw Band"):
            self.assertFalse(R.DEAL_TITLE_RE.search(t), t)

    def test_city_posts_link_the_r_boston_post_main_post_doesnt(self):
        _, city_body = R.build_roundup("weekend", city="cambridge")
        _, main_body = R.build_roundup("weekend")
        self.assertIn(R.BOSTON_POST_PLACEHOLDER, city_body)
        self.assertNotIn(R.BOSTON_POST_PLACEHOLDER, main_body)
        self.assertNotIn("/cambridge/)", city_body)  # no "All Cambridge events" link

    def test_link_box_only_on_pages_with_the_placeholder(self):
        body = f"Hi\n\nSee [the post]({R.BOSTON_POST_PLACEHOLDER}).\n"
        self.assertIn('id="bostonLink"', R.render_roundup_page("weekend", "T", body, page="weekend-somerville"))
        self.assertNotIn('id="bostonLink"', R.render_roundup_page("weekend", "T", "Hi\n", page="weekend"))


if __name__ == "__main__":
    unittest.main()
