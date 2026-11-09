"""SEO and reach for the parent pages (Nov 2026).

- sitemap.xml is written every build with a real lastmod (Google ignores changefreq/priority).
- The home page links both parent pages at the top of Useful links, not only in the footer directory.
- The Kids page carries two weeks; later days are in later.html, loaded on scroll, the button or
  any filter (checked in Chrome: 686 cards at load, 943 after scroll / Free / a week-3 chip / a
  #when= link, no errors). Page: 92 -> 73 KB gzipped, 948 -> 686 cards.
- The Summer Camps H1 says what people search for.
"""
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server  # noqa: E402
import template as T  # noqa: E402


class SitemapTest(unittest.TestCase):
    def test_every_public_page_with_lastmod(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sitemap.xml")
            with patch.object(server, "_camps_checked_date", return_value="2026-11-07"):
                server.write_sitemap(path, "https://www.wickedbostonevents.com")
            with open(path) as f:
                xml = f.read()
        rows = dict(re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", xml))
        base = "https://www.wickedbostonevents.com/"
        self.assertEqual(set(rows), {base} | {f"{base}{slug}/" for slug in T.HUBS})
        self.assertEqual(rows[f"{base}summer-camps/"], "2026-11-07")
        self.assertEqual(rows[f"{base}kids-family-events-boston/"], datetime.now(timezone.utc).date().isoformat())
        self.assertNotIn("roundup", xml)
        self.assertNotIn("changefreq", xml)


def _kid_events(days):
    base = datetime.now(T.EASTERN).replace(hour=10, minute=30, second=0, microsecond=0) + timedelta(days=1)
    return [{"name": f"Story Time {i}", "date": (base + timedelta(days=i)).isoformat(), "_time": base + timedelta(days=i),
             "venue": "Cambridge Public Library", "url": f"https://kids.test/{i}", "category": "family",
             "_source_venue": "Cambridge Public Library"} for i in range(days)]


class KidsLaterDaysTest(unittest.TestCase):
    def test_two_weeks_inline_rest_in_later_file(self):
        extra = {}
        with patch("template._load_community_events", return_value=[]):
            html = T.render_hub_page("kids-family-events-boston", _kid_events(20), extra_files=extra)
        inline = set(re.findall(r'<article class="hub-card[^"]*"[^>]*data-day="([\d-]+)"', html))
        later = set(re.findall(r'<article class="hub-card[^"]*"[^>]*data-day="([\d-]+)"', extra.get("later.html", "")))
        last_inline = datetime.now(T.EASTERN).date() + timedelta(days=T.KIDS_INLINE_DAYS - 1)
        self.assertTrue(inline and later)
        self.assertTrue(all(d <= last_inline.isoformat() for d in inline))
        self.assertTrue(all(d > last_inline.isoformat() for d in later))
        listed = json.loads(re.search(r'data-days="([^"]+)"', html).group(1).replace("&quot;", '"'))
        self.assertEqual(sorted(listed), sorted(later))
        self.assertIn("in the next 20 days", html)  # stats count the later days too
        self.assertIn("loadLater();", html)

    def test_no_later_file_when_everything_fits(self):
        extra = {}
        with patch("template._load_community_events", return_value=[]):
            html = T.render_hub_page("kids-family-events-boston", _kid_events(5), extra_files=extra)
        self.assertNotIn("later.html", extra)
        self.assertNotIn('id="kids-later"', html)


class HomeAndCampsTest(unittest.TestCase):
    def test_home_links_parent_pages_in_useful_links(self):
        with patch("template._load_community_events", return_value=[]):
            html = T.render_page([])
        box = re.search(r'<div class="useful-cat useful-parents"[^>]*>.*?</ul></div>', html, re.S).group(0)
        self.assertIn('href="kids-family-events-boston/"', box)
        self.assertIn('href="summer-camps/"', box)
        self.assertNotIn("banner-parents-pill", html)  # not in the hero

    def test_camps_heading_names_the_summer(self):
        self.assertEqual(T._camp_summer_year(date(2026, 11, 9)), 2027)
        self.assertEqual(T._camp_summer_year(date(2027, 3, 1)), 2027)
        with patch("template._load_community_events", return_value=[]):
            html = T.render_hub_page("summer-camps", [])
        self.assertRegex(html, r"<h1>Summer Camps Near Boston 20\d\d<small>")


if __name__ == "__main__":
    unittest.main()
