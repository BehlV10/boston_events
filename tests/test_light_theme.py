"""Light theme: a ☀️ choice in the theme picker that only changes pages showing data-theme="light"."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402
from light_theme import LIGHT_THEME_CSS  # noqa: E402


def _render():
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
    venues = [{"venue": "Club Passim", "url": "https://www.passim.org/", "error": None,
               "events": [{"name": "Folk Night", "date": when, "venue": "Club Passim",
                           "url": "https://www.passim.org/e/1", "price": "$20", "category": "music"}]}]
    with patch("template._load_community_events", return_value=[]):
        return T.render_page(venues)


class LightThemeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render()

    def test_picker_has_light_next_to_dark(self):
        self.assertIn('data-theme="light" role="radio"', self.html)
        self.assertLess(self.html.index('title="Classic Dark Theme"'), self.html.index('title="Light Theme"'))
        # A remembered light choice is honored on the next visit like the other regular themes.
        self.assertIn("var BASE_THEMES = ['classic', 'light', 'indie', 'anime'];", self.html)

    def test_palette_defined(self):
        block = re.search(r'\[data-theme="light"\] \{(.*?)\}', self.html, re.S).group(1)
        for token in ("--bg", "--card", "--fg", "--muted", "--accent", "--border", "--green"):
            self.assertIn(token + ":", block)
        self.assertIn("color-scheme: light", block)

    def test_overrides_only_touch_the_light_theme(self):
        css = re.sub(r"/\*.*?\*/", "", LIGHT_THEME_CSS, flags=re.S)
        selectors = [s.strip() for sel in re.findall(r"([^{}]+)\{[^{}]*\}", css) for s in sel.split(",")]
        self.assertGreater(len(selectors), 50)
        unscoped = [s for s in selectors if not s.startswith('[data-theme="light"]')]
        self.assertEqual(unscoped, [], "every light rule must be scoped so dark themes don't change")
        self.assertIn(LIGHT_THEME_CSS.strip()[:40], self.html)

    def test_dark_text_on_white_for_links_and_map(self):
        self.assertIn('[data-theme="light"] .what a { color: #1d4ed8; }', LIGHT_THEME_CSS)
        # The dark map inverts its tiles; the light map shows them as they are.
        self.assertRegex(LIGHT_THEME_CSS, r'\[data-theme="light"\] \.leaflet-container\.osm-dark-tiles \.leaflet-tile-pane \{ filter: saturate')


if __name__ == "__main__":
    unittest.main()
