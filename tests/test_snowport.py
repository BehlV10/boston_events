"""Snowport Holiday Market from its own page (bostonseaport.xyz/holidaymarket).

Do617 lists the market daily without hours. The official page (a Next.js site whose copy sits in
the streamed data) has the season, weekday hours, extended December hours, closed days, the
Christmas Eve early close, and the Mohegan Music Mondays lineup.
"""
import json
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers as S  # noqa: E402

TEXTS = [
    "The Snowport Holiday Market presented by Visa will be open seven days a week November 6 - December 27, 2026.",
    "The Holiday Market will be closed Thanksgiving Day and Christmas Day. It will close early at 6:00pm on Christmas Eve.",
    "Monday - Thursday 3:00pm - 8:00pm", "Friday 11:00am - 9:00pm", "Saturday 10:00am - 9:00pm", "Sunday 10:00am - 8:00pm",
    "During the peak holiday season (December 7 – December 27), the market will have extended hours:",
    "Monday - Thursday 11:00am - 8:00pm", "Friday 11:00am - 9:00pm", "Saturday 10:00am - 9:00pm", "Sunday 10:00am - 8:00pm",
    "November 9: Triinnity Lee", "November 16: Hanna Lauren",
    "Yes. Join us on Mondays starting at 5:00pm for Mohegan Music Mondays.",
]


def _page():
    blob = json.dumps([{"_type": "span", "text": t} for t in TEXTS], separators=(",", ":"))  # as Next.js streams it
    return f'<script>self.__next_f.push([1,{json.dumps(blob)}])</script>'


class SnowportTest(unittest.TestCase):
    def setUp(self):
        resp = MagicMock(text=_page(), raise_for_status=lambda: None)
        with patch.object(S._SESSION, "get", return_value=resp):
            self.events = S.scrape_snowport(S._SNOWPORT_URL, "ua", now=datetime(2026, 11, 9, 8, 0, tzinfo=S.EASTERN))

    def local(self, e, key="date"):
        return datetime.fromisoformat(e[key]).astimezone(S.EASTERN).strftime("%a %b %d %H:%M")

    def market(self):
        return {self.local(e)[:10]: (self.local(e)[11:], self.local(e, "end")[11:])
                for e in self.events if e["category"] == "markets"}

    def test_hours_by_day(self):
        m = self.market()
        self.assertEqual(m["Mon Nov 09"], ("15:00", "20:00"))
        self.assertEqual(m["Sat Nov 14"], ("10:00", "21:00"))
        self.assertEqual(m["Sun Nov 15"], ("10:00", "20:00"))
        self.assertEqual(m["Mon Dec 07"], ("11:00", "20:00"))  # extended hours from Dec 7
        self.assertEqual(m["Thu Dec 24"], ("11:00", "18:00"))  # early close
        self.assertNotIn("Thu Nov 26", m)                      # Thanksgiving
        self.assertNotIn("Fri Dec 25", m)
        self.assertNotIn("Fri Nov 06", m)                      # already over
        self.assertIn("Sun Dec 27", m)

    def test_music_mondays(self):
        music = [(e["name"], self.local(e)) for e in self.events if e["category"] == "music"]
        self.assertEqual(music, [("Mohegan Music Mondays: Triinnity Lee", "Mon Nov 09 17:00"),
                                 ("Mohegan Music Mondays: Hanna Lauren", "Mon Nov 16 17:00")])

    def test_unreadable_page_gives_nothing(self):
        resp = MagicMock(text="<html></html>", raise_for_status=lambda: None)
        with patch.object(S._SESSION, "get", return_value=resp):
            self.assertEqual(S.scrape_snowport(S._SNOWPORT_URL, "ua"), [])


if __name__ == "__main__":
    unittest.main()
