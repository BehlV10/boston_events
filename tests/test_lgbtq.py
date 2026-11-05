"""LGBTQ+ tag and the "LGBTQ+ events only" checkbox (titles below are real listings)."""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402
from lgbtq import is_lgbtq_event  # noqa: E402


def ev(name, venue="Somewhere", source="Somewhere", description=""):
    return {"name": name, "venue": venue, "_source_venue": source, "description": description}


class LgbtqTagTest(unittest.TestCase):
    def test_queer_titles(self):
        for name in ("Queer Board Game Night", "Queeraoke", "Super Smash Bros. Tournament with The Boston Gaymers",
                     "Sapphic Speed Dating | Boston LGBTQ+ Singles | 25-45", "Lesbian Nightlife Tea Dance",
                     "Gay and Allies Tea Dance Party", "Allyship with Trans People", "Holiday Drag Night",
                     "Boston Gay Men's Chorus Presents: Holigays", "Two Dykes and a Mic: Soaking Wet Tour",
                     "FERAL XCX FEST | BOSTON'S LGBTQ RAGER !", "Desi Pride Social",
                     "RuPaul's Drag Race Werq The World 2027 Tour"):
            self.assertTrue(is_lgbtq_event(ev(name)), name)

    def test_queer_venues_and_sources(self):
        self.assertTrue(is_lgbtq_event(ev("Weekend Brunch", venue="Club Café", source="Club Café")))
        self.assertTrue(is_lgbtq_event(ev("Mary Catherine Ward", venue="Club Cafe", source="The Boston Calendar")))
        self.assertTrue(is_lgbtq_event(ev("Karaoke", venue="The Alley Bar", source="Do617")))
        self.assertTrue(is_lgbtq_event(ev("FERAL: GRIFFIN MAXWELL BROOKS", venue="Urban MO's", source="FERAL")))
        self.assertTrue(is_lgbtq_event(ev("Weekend Dance Party", venue="Dani's Queer Bar", source="Do617")))

    def test_description_terms(self):
        self.assertTrue(is_lgbtq_event(ev("Kingdom Class 12 Showcase", description="A drag king showcase")))
        self.assertTrue(is_lgbtq_event(ev("Boston T Party", description="A queer dance night")))
        # Everyday words in a description don't count.
        self.assertFalse(is_lgbtq_event(ev("Open Mic", description="We take pride in our open mic. Drag a friend!")))

    def test_not_queer(self):
        for name in ("Pride and Prejudice", "Pride & Prejudice: A Musical", "Trans-Siberian Orchestra",
                     "Marvin Gaye Tribute", "Drag Racing Night at the Speedway", "Pride of Boston Marching Band",
                     "Transit Planning Workshop", "Irish Pride Pub Crawl", "Gaylord Opry Bus Trip"):
            self.assertFalse(is_lgbtq_event(ev(name)), name)
        self.assertFalse(is_lgbtq_event(ev("Dinner Service", venue="Cactus Club Cafe")))


class LgbtqCheckboxRenderTest(unittest.TestCase):
    def test_checkbox_and_event_flag(self):
        when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0).isoformat()
        venues = [
            {"venue": "Club Café", "url": "https://www.clubcafe.com/", "error": None,
             "events": [{"name": "Queer Board Game Night", "date": when, "venue": "Club Café (Moonshine Room)",
                         "url": "https://www.clubcafe.com/club-events/queer-board-game-night-111626/", "price": "$5",
                         "category": "community"}]},
            {"venue": "The Burren", "url": "https://burren.com/", "error": None,
             "events": [{"name": "Irish Session", "date": when, "venue": "The Burren — The Front Room",
                         "url": "https://burren.com/music.html#irish-session", "price": "Free", "category": "music"}]},
        ]
        with patch("template._load_community_events", return_value=[]):
            html = T.render_page(venues)
        self.assertIn('id="lgbtq-only-chk"', html)
        self.assertIn("LGBTQ+ events only", html)
        cards = {name: c for c in re.findall(r'<li class="event[^"]*".*?</li>', html, re.S)
                 for name in ("Queer Board Game Night", "Irish Session") if name in c}
        self.assertIn('data-lgbtq="true"', cards["Queer Board Game Night"])
        self.assertNotIn("data-lgbtq", cards["Irish Session"])
        # The filter reads the flag and keeps it in the shareable link.
        self.assertIn("const lgbtqOk = !lgbtqOnly || m.lgbtq;", html)
        self.assertIn("params.set('lgbtq', '1')", html)


if __name__ == "__main__":
    unittest.main()
