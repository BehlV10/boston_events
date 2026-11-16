import importlib.util
import os
import unittest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("sync_post_highlights", os.path.join(ROOT, "scripts", "sync_post_highlights.py"))
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

POST = """Hi Boston!

## 📅 TUESDAY, NOV 17

### 🎓 CAMBRIDGE
* **[☆ Game Night at CanalSide](https://www.meetup.com/unplugged-boston/events/1/)** @ CanalSide · 5:30PM · Cambridge
  Free drop-in board games.
* **[Pouya: The Foreverglades Tour](https://example.com/pouya)** @ Big Night Live · 7PM · West End

## 📅 FRIDAY, NOV 20

### 🏙️ BOSTON
* **[Noah Preminger Quintet](https://wallyscafe.com/ritual/)** @ Wally's Café · 10PM · Free · South End
  Late jazz.
"""


def ev(name, iso, url="", venue=""):
    return {"name": name, "date": iso, "url": url, "venue": venue}


class SyncPostHighlightsTest(unittest.TestCase):
    def test_parse_post(self):
        picks = sp.parse_post(POST, 2026)
        self.assertEqual([(p[0], p[1]) for p in picks], [
            (date(2026, 11, 17), "Game Night at CanalSide"),
            (date(2026, 11, 17), "Pouya: The Foreverglades Tour"),
            (date(2026, 11, 20), "Noah Preminger Quintet"),
        ])
        self.assertEqual(picks[0][4], "Free drop-in board games.")
        self.assertEqual(picks[1][4], "")

    def test_shared_calendar_url_needs_matching_title(self):
        day = [ev("Gabriel Maia Quintet", "2026-11-20T19:00:00-05:00", "https://wallyscafe.com/ritual/", "Wally's Café"),
               ev("Noah Preminger Quintet", "2026-11-20T22:00:00-05:00", "https://wallyscafe.com/ritual/", "Wally's Café")]
        self.assertEqual(sp.find_listing(day, "Noah Preminger Quintet", "https://wallyscafe.com/ritual/")["name"],
                         "Noah Preminger Quintet")

    def test_entry_uses_name_every_listing_shares(self):
        by_day = {date(2026, 11, 17): [
            ev("Pouya - The Foreverglades Tour", "2026-11-17T18:00:00-05:00", "https://example.com/pouya", "Big Night Live"),
            ev("Pouya", "2026-11-17T18:00:00-05:00", "https://seatgeek.com/x", "Big Night Live"),
            ev("Game Night at CanalSide", "2026-11-17T17:30:00-05:00", "https://www.meetup.com/unplugged-boston/events/1/", "CanalSide"),
            ev("TechWalk | Boston", "2026-11-17T18:00:00-05:00", "https://example.com/tw", "Kendall"),
        ]}
        new, already, missing = sp.sync(POST, 2026, [], by_day)
        pouya = next(h for h in new if "pouya" in h["id"])
        self.assertEqual(pouya["match"], {"name_contains": "pouya", "venue_contains": "Big Night Live"})
        self.assertEqual((pouya["start_date"], pouya["expires"]), ("2026-11-17", "2026-11-17"))
        game = next(h for h in new if "game-night" in h["id"])
        self.assertEqual(game["note"], "Free drop-in board games.")
        self.assertEqual([m[1] for m in missing], ["Noah Preminger Quintet"])

    def test_already_highlighted_is_left_alone(self):
        by_day = {date(2026, 11, 17): [ev("Game Night at CanalSide", "2026-11-17T17:30:00-05:00", "", "CanalSide")]}
        existing = [{"id": "x", "match": {"name_contains": "Game Night at CanalSide"}, "start_date": "2026-11-17", "expires": "2026-11-17"}]
        new, already, _ = sp.sync(POST, 2026, existing, by_day)
        self.assertEqual(new, [])
        self.assertEqual(already, [(date(2026, 11, 17), "Game Night at CanalSide")])


class SpotlightTest(unittest.TestCase):
    def test_spotlight_css_and_class(self):
        with open(os.path.join(ROOT, "template.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('" highlighted spotlight" if hl.get("spotlight")', src)
        self.assertIn(".event.spotlight {{", src)


if __name__ == "__main__":
    unittest.main()
