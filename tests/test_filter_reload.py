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

import template

_CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# Runs after the page's own scripts. With ?untick in the URL it unticks Music the way a click
# does (change event), then reports the hash the page wrote for that state. (A flag in the hash
# wouldn't do: the page rewrites the hash from its state as it starts.)
_PROBE = """<script>
window.addEventListener('load', function () {
  setTimeout(function () {
    var music = Array.from(document.querySelectorAll('.cat-chk')).find(function (b) { return b.value === 'Music & nightlife'; });
    if (location.search.indexOf('untick') >= 0) {
      music.checked = false;
      music.dispatchEvent(new Event('change'));
    }
    setTimeout(function () {
      var genres = Array.from(document.querySelectorAll('.genre-chk'));
      var box = document.getElementById('subgenre-container');
      document.body.setAttribute('data-probe', JSON.stringify({
        music: music.checked,
        genres: genres.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }),
        total: genres.length,
        disabled: !!(box && box.classList.contains('disabled')),
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
        html = template.render_page([])
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
        before = self._load("", query="?untick")
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


if __name__ == "__main__":
    unittest.main()
