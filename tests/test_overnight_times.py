"""Events can't show a start between 1 and 6 AM: each source's cause, and the check behind them."""
import os
import sys
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scrapers as S  # noqa: E402
import source_health  # noqa: E402
import template as T  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402
from scrapers import EASTERN  # noqa: E402


def local(iso):
    return datetime.fromisoformat(iso).astimezone(EASTERN).strftime("%Y-%m-%d %H:%M")


class EventbriteTimes(unittest.TestCase):
    def rows(self, **fields):
        row = dict({"name": "Show", "url": "https://e/1", "start_date": "2030-11-09", "start_time": "22:00"}, **fields)
        page = "<script>window.__SERVER_DATA__ = " + json.dumps({"events": [row]}) + ";</script>"
        return S._parse_eventbrite_server_data(page)

    def test_in_person_time_stays_boston_time_when_organizer_is_set_to_pacific(self):
        self.assertEqual(local(self.rows(timezone="America/Los_Angeles")[0]["date"]), "2030-11-09 22:00")

    def test_online_event_keeps_its_zone(self):
        row = self.rows(timezone="America/Los_Angeles", is_online_event=True)[0]
        self.assertEqual(local(row["date"]), "2030-11-10 01:00")

    def test_event_abroad_is_left_out(self):
        self.assertEqual(self.rows(timezone="Europe/London"), [])

    def test_json_ld_uses_the_listed_clock_time(self):
        item = {"@type": "Event", "name": "Show", "url": "u", "startDate": "2030-11-09T22:00:00-08:00",
                "location": {"@type": "Place", "name": "Legacy"}}
        block = json.dumps({"@type": "ItemList", "itemListElement": [{"item": item}]})
        soup = BeautifulSoup(f'<script type="application/ld+json">{block}</script>', "html.parser")
        self.assertEqual(local(S._parse_eventbrite_json_ld(soup)[0]["date"]), "2030-11-09 22:00")


class MadMonkfishTimes(unittest.TestCase):
    def start(self, title):
        now = datetime(2030, 11, 1, 12, tzinfo=EASTERN)
        soup = BeautifulSoup(f'<a href="/event/x">{title}</a>', "html.parser")
        out = []
        S._mad_monkfish_page(soup, now, out, set())
        return datetime.fromisoformat(out[0]["date"]).strftime("%Y-%m-%d %H:%M"), out[0]["name"]

    def test_midnight_set_starts_at_midnight_after_the_listed_night(self):
        self.assertEqual(self.start("11/7 The Midnight Hour w/Camila Quintero 12-1am"),
                         ("2030-11-08 00:00", "Live Jazz: The Midnight Hour w/Camila Quintero"))

    def test_range_uses_its_start(self):
        self.assertEqual(self.start("11/7 Trio 8-10pm")[0], "2030-11-07 20:00")
        self.assertEqual(self.start("11/7 Late Jam 11-1am")[0], "2030-11-07 23:00")


class BostonCalendarTimes(unittest.TestCase):
    def test_small_hours_mean_afternoon(self):
        self.assertEqual(local(S._parse_boston_calendar_time("Saturday, Nov 07, 2030 2:00a")), "2030-11-07 14:00")
        self.assertEqual(local(S._parse_boston_calendar_time("Saturday, Nov 07, 2030 9:00a")), "2030-11-07 09:00")

    def test_fare_offer_is_not_an_event(self):
        self.assertTrue(S._bc_is_noise("$10 Commuter Rail Weekends and Holidays"))


class OvernightCheck(unittest.TestCase):
    def test_removes_and_records_starts_from_1_to_6_am(self):
        at = lambda h, m=0: datetime(2030, 11, 9, h, m, tzinfo=EASTERN).isoformat()
        results = [{"venue": "X", "events": [{"name": n, "date": d, "url": "u"} for n, d in (
            ("midnight", at(0)), ("late", at(0, 59)), ("one", at(1)), ("five", at(5, 59)), ("six", at(6)),
            ("undated", None), ("utc", "2030-11-09T09:00:00+00:00"))]}]
        S._drop_overnight_starts(results)
        self.assertEqual([e["name"] for e in results[0]["events"]], ["midnight", "late", "six", "undated"])
        self.assertEqual([o["name"] for o in S.OVERNIGHT_DROPPED], ["one", "five", "utc"])
        self.assertIn("Removed for a 1–6 AM start", source_health._markdown([], S.OVERNIGHT_DROPPED))


class KidsWindow(unittest.TestCase):
    def test_kids_hub_shows_three_weeks_with_no_card_limit(self):
        hub = T.HUBS["kids-family-events-boston"]
        today = datetime.now(EASTERN).replace(hour=12)
        events = [{"name": f"Story {n}", "date": (today + timedelta(days=d)).isoformat(), "category": "family"}
                  for n, d in enumerate([0] * 1000 + [21, 22])]
        kept = T.filter_events_for_hub(hub, events)
        self.assertEqual(len(kept), 1001)
        self.assertEqual(len(kept[:hub.get("limit", 60)]), 1001)
