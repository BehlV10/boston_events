"""Club Café one-off ticketed shows link to /events/<slug>/ with no ?occurrence= date; the date
comes from the calendar's JSON-LD (Drag Brunch with Mizery, Nov 22 2026, was dropped)."""
import json
import os
import sys
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402


def _article(name, href, time="1:00 pm - 3:00 pm", ld_start=None, price="25", status="EventScheduled"):
    ld = ""
    if ld_start:
        ld = '<script type="application/ld+json">' + json.dumps({
            "@type": "Event", "eventStatus": f"https://schema.org/{status}", "startDate": ld_start,
            "url": href.split("?")[0], "name": name, "offers": {"url": href.split("?")[0], "price": price},
            "description": ""}) + "</script>"
    return (f'{ld}<article class="mec-event-article"><span class="mec-event-time">{time}</span>'
            f'<h4 class="mec-event-title"><a href="{href}">{name}</a></h4>'
            f'<div class="mec-event-loc-place">Moonshine Room</div></article>')


class UndatedClubCafeEvents(unittest.TestCase):
    def _scrape(self, body):
        with patch.object(S, "fetch_soup", return_value=BeautifulSoup(f"<html>{body}</html>", "html.parser")), \
             patch.object(S, "_club_cafe_cost_line", return_value=None):
            return S.scrape_club_cafe("https://www.clubcafe.com/full-calendar/", "ua")

    def test_ticketed_show_dated_from_json_ld(self):
        evs = self._scrape(_article("Drag Brunch with Mizery", "https://www.clubcafe.com/events/boston-drag-brunch-112226/",
                                    ld_start="2026-11-22", status="EventCancelled"))
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["name"], "Drag Brunch with Mizery")
        self.assertEqual(evs[0]["date"], "2026-11-22T18:00:00+00:00")  # 1 pm Eastern
        self.assertEqual(evs[0]["price"], "$25")

    def test_occurrence_links_still_win(self):
        evs = self._scrape(_article("Weekend Brunch", "https://www.clubcafe.com/club-events/weekend-brunch/?occurrence=2026-11-22",
                                    time="11:00 am - 3:00 pm"))
        self.assertEqual([e["date"] for e in evs], ["2026-11-22T16:00:00+00:00"])

    def test_no_date_anywhere_is_skipped(self):
        self.assertEqual(self._scrape(_article("Mystery", "https://www.clubcafe.com/events/mystery/")), [])


if __name__ == "__main__":
    unittest.main()
