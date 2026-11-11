"""Filters survive a reload: the page's own JavaScript, run in headless Chrome.

Bug (Nov 2026): untick "Music & nightlife", reload
/#cat=Arts+%26+culture&t=range&d=...&d_end=..., and every music subgenre came back ticked
under the unticked Music box. Unticking Music unticks all genres, the URL then carries no
genre= (it only lists a partial selection), and the reload left the genres at their default.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from datetime import datetime, timedelta

import template
from scrapers import EASTERN

_CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# Runs after the page's own scripts. ?untick=<category box> or ?untickart=<art|books|talks|film>
# in the URL unticks that box the way a click does (change event); then it reports the state
# and the hash the page wrote for it. (A flag in the hash wouldn't do: the page rewrites the
# hash from its state as it starts.)
_PROBE = """<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var q = new URLSearchParams(location.search);
    var cats = Array.from(document.querySelectorAll('.cat-chk'));
    var arts = Array.from(document.querySelectorAll('.artsub-chk'));
    var find = function (list, v) { return list.find(function (b) { return b.value === v; }); };
    var click = function (b) { b.checked = false; b.dispatchEvent(new Event('change')); };
    if (q.get('untick')) click(find(cats, q.get('untick')));
    if (q.get('untickart')) click(find(arts, q.get('untickart')));
    setTimeout(function () {
      var on = function (list) { return list.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }); };
      var genres = Array.from(document.querySelectorAll('.genre-chk'));
      var box = document.getElementById('subgenre-container');
      var artsBox = document.getElementById('artsub-container');
      var shown = Array.from(document.querySelectorAll('li.event[data-cat]')).filter(function (li) {
        return (li.getAttribute('data-venue') || '').indexOf('Test Venue') >= 0;
      }).filter(function (li) {
        return !li.classList.contains('hidden') && !li.closest('.bucket.empty');
      }).map(function (li) { return li.getAttribute('data-cat'); });
      document.body.setAttribute('data-probe', JSON.stringify({
        music: find(cats, 'Music & nightlife').checked,
        genres: on(genres), total: genres.length,
        disabled: !!(box && box.classList.contains('disabled')),
        artsOn: find(cats, 'Arts & culture').checked, arts: on(arts),
        artsDisabled: !!(artsBox && artsBox.classList.contains('disabled')),
        shown: Array.from(new Set(shown)).sort(),
        hash: location.hash
      }));
    }, 400);
  }, 300);
});
</script>"""


def _chrome():
    for c in _CHROME_CANDIDATES:
        path = shutil.which(c) or (c if os.path.isfile(c) else None)
        if path:
            return path
    return None


class MusicGenresAfterReload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = _chrome()
        if not cls.chrome:
            raise unittest.SkipTest("no Chrome/Chromium to run the page's JavaScript")
        when = (datetime.now(EASTERN) + timedelta(days=2)).replace(hour=19, minute=0, second=0, microsecond=0)
        venues = [{"venue": "Test Venue", "url": "https://example.com", "error": None, "events": [
            {"name": name, "date": when.replace(hour=hour).isoformat(), "category": cat, "venue": "Test Venue",
             "url": f"https://example.com/{cat}"}
            for name, cat, hour in (("Watercolor Afternoon", "art", 13), ("Romance Book Club", "books", 15),
                                    ("Ralph Lowell Annual Lecture", "talks", 17), ("Midnight Movie", "film", 21))]}]
        html = template.render_page(venues)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.page = os.path.join(cls.tmp.name, "index.html")
        with open(cls.page, "w", encoding="utf-8") as f:
            f.write(html.replace("</body>", _PROBE + "</body>"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _load(self, hash_, query=""):
        url = "file://" + self.page + query + hash_
        with tempfile.TemporaryDirectory() as profile:
            out = subprocess.run(
                [self.chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={profile}",
                 "--virtual-time-budget=5000", "--dump-dom", url],
                capture_output=True, text=True, timeout=90).stdout
        m = re.search(r'data-probe="([^"]*)"', out)
        self.assertIsNotNone(m, "probe didn't run; page JavaScript may have failed")
        return json.loads(m.group(1).replace("&quot;", '"').replace("&amp;", "&"))

    def test_unticked_music_stays_unticked_with_its_genres_after_reload(self):
        before = self._load("", query="?untick=Music+%26+nightlife")
        self.assertFalse(before["music"])
        self.assertEqual(before["genres"], [])
        self.assertIn("cat=", before["hash"])
        self.assertNotIn("Music", before["hash"])

        after = self._load(before["hash"])  # reload with the hash the page wrote
        self.assertFalse(after["music"])
        self.assertEqual(after["genres"], [], "genres came back ticked under an unticked Music box")
        self.assertTrue(after["disabled"])

    def test_the_reported_link(self):
        got = self._load("#cat=Arts+%26+culture&t=range&d=2026-11-10&d_end=2026-11-13")
        self.assertFalse(got["music"])
        self.assertEqual(got["genres"], [])

    def test_music_on_keeps_every_genre(self):
        got = self._load("#cat=Arts+%26+culture,Music+%26+nightlife")
        self.assertTrue(got["music"])
        self.assertEqual(len(got["genres"]), got["total"])
        self.assertFalse(got["disabled"])

    def test_one_genre_link_still_works(self):
        got = self._load("#cat=Music+%26+nightlife&genre=jazz_blues")
        self.assertTrue(got["music"])
        self.assertEqual(got["genres"], ["jazz_blues"])


class ArtsSubfilters(MusicGenresAfterReload):
    """Art / Books / Talks / Film under Arts & culture (same page, same probe)."""
    test_unticked_music_stays_unticked_with_its_genres_after_reload = None
    test_the_reported_link = test_music_on_keeps_every_genre = test_one_genre_link_still_works = None

    def test_only_books_and_talks(self):
        got = self._load("#cat=Arts+%26+culture&arts=books,talks&t=all")
        self.assertTrue(got["artsOn"])
        self.assertEqual(sorted(got["arts"]), ["books", "talks"])
        self.assertEqual(got["shown"], ["books", "talks"])

    def test_unticked_film_stays_off_after_reload(self):
        before = self._load("#t=all", query="?untickart=film")
        self.assertNotIn("film", before["shown"])
        self.assertIn("arts=", before["hash"])
        after = self._load(before["hash"])
        self.assertEqual(sorted(after["arts"]), ["art", "books", "talks"])
        self.assertEqual(after["shown"], ["art", "books", "talks"])

    def test_unticked_arts_keeps_its_subfilters_off_after_reload(self):
        before = self._load("#t=all", query="?untick=Arts+%26+culture")
        self.assertEqual(before["arts"], [])
        after = self._load(before["hash"])
        self.assertFalse(after["artsOn"])
        self.assertEqual(after["arts"], [])
        self.assertTrue(after["artsDisabled"])
        self.assertEqual(after["shown"], [])

    def test_old_books_and_talks_links(self):
        got = self._load("#cat=Books+%26+Talks&t=all")
        self.assertTrue(got["artsOn"])
        self.assertEqual(sorted(got["arts"]), ["books", "talks"])
        self.assertEqual(got["shown"], ["books", "talks"])


if __name__ == "__main__":
    unittest.main()
