"""Drop a pin: tap the map, then events sort by distance from the pin like Near Me does from you.

The browser behavior (tap -> pin -> sorted list -> shareable #pin= link -> Reset clears it) was
checked in headless Chrome; these tests keep the pieces wired together in the rendered page.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402


def _render():
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
    venues = [{"venue": "Club Passim", "url": "https://www.passim.org/", "error": None,
               "events": [{"name": "Folk Night", "date": when, "venue": "Club Passim",
                           "url": "https://www.passim.org/e/1", "price": "$20", "category": "music"}]}]
    with patch("template._load_community_events", return_value=[]):
        return T.render_page(venues)


class DropPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _render()

    def test_button_next_to_near_me_and_map_hint(self):
        near, pin, maps = (self.html.index('id="btn-near-me"'), self.html.index('id="btn-drop-pin"'),
                           self.html.index('id="btn-view-map"'))
        self.assertLess(near, pin)
        self.assertLess(pin, maps)
        self.assertIn('id="pin-hint"', self.html)
        self.assertIn("Tap the map to drop your pin.", self.html)

    def test_sorting_uses_the_pin_when_there_is_one(self):
        js = self.html
        self.assertIn("if (pinCoords) return {{ lat: pinCoords.lat".replace("{{", "{"), js)
        self.assertIn("haversineMiles(origin.lat, origin.lng, lat, lng)", js)
        self.assertNotIn("haversineMiles(userCoords.lat", js)
        self.assertIn("Sorted by distance from ${fromPin ? 'your pin' : 'your location'}", js)

    def test_distance_list_built_once_per_origin(self):
        """Filter changes re-show/hide the sorted copy; only a new origin re-measures and re-clones."""
        self.assertIn("near.key !== originKey", self.html)
        self.assertIn("day._nearCache = null;", self.html)  # cleared when Near Me turns off

    def test_tap_places_pin_only_while_placing(self):
        self.assertIn("if (pinPlacing) placePin(ev.latlng.lat, ev.latlng.lng);", self.html)
        self.assertIn("draggable: true", self.html)

    def test_pin_is_shareable(self):
        self.assertIn("params.set('pin', `${pinCoords.lat},${pinCoords.lng}`)", self.html)
        self.assertIn("getParam('pin').split(',').map(Number)", self.html)

    def test_page_script_parses(self):
        """The pin code lives in a Python f-string; a stray brace would break the whole page."""
        scripts = re.findall(r"<script>(.*?)</script>", self.html, re.S)
        main = max(scripts, key=len)
        try:
            subprocess.run(["node", "--version"], capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            self.skipTest("node not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(main)
        try:
            proc = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
        finally:
            os.unlink(f.name)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
