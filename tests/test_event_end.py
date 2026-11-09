"""End times as sources give them, parsed into one form (UTC ISO) by scrapers._event_end.

Scrapers record the end exactly as the source states it, odd or not; the page decides what to trust.
A live sample (Nov 2026, 70 sources, 2,937 events): 85% normal (15 min-6 h, incl. past midnight),
6% end = start (calendars that copy the start when no end is set), 6% no end, ~3% long/multi-day
(conferences, fairs, restaurant weeks), and a few stand-ins (11:59 PM, midnight-to-midnight).
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers as S  # noqa: E402

START = datetime(2026, 11, 13, 19, 0, tzinfo=S.EASTERN)  # Fri 7 PM


def local(iso):
    return datetime.fromisoformat(iso).astimezone(S.EASTERN).strftime("%a %H:%M")


class EventEndTest(unittest.TestCase):
    def test_formats(self):
        cases = {
            "2026-11-13T21:30:00-05:00": "Fri 21:30",   # zoned ISO
            "2026-11-14T02:30:00.000Z": "Fri 21:30",    # UTC "Z"
            "2026-11-13 21:30:00": "Fri 21:30",         # local, space-separated (Tribe)
            "2026-11-13T21:30:00": "Fri 21:30",         # local ISO (Trumba, BiblioCommons)
            "20261114T023000Z": "Fri 21:30",            # iCal
            "21:30": "Fri 21:30",                        # bare clock on the start's day
            "9:30 pm": "Fri 21:30",
            "02:00": "Sat 02:00",                        # earlier than start: past midnight
            int((START + timedelta(hours=2, minutes=30)).timestamp() * 1000): "Fri 21:30",  # epoch ms (Squarespace)
        }
        for raw, want in cases.items():
            self.assertEqual(local(S._event_end(raw, START)), want, raw)
        self.assertEqual(local(S._event_end(timedelta(hours=2), START)), "Fri 21:00")

    def test_missing_or_garbage_is_none(self):
        for raw in (None, "", "TBA", "[2026"):
            self.assertIsNone(S._event_end(raw, START), raw)

    def test_odd_values_are_kept_for_the_page_to_judge(self):
        self.assertEqual(S._event_end("2026-11-13T19:00:00-05:00", START), START.astimezone(timezone.utc).isoformat())

    def test_eventbrite_end_uses_the_events_zone(self):
        self.assertEqual(local(S._eventbrite_end("2026-11-13", "21:30:00", "America/New_York",
                                                 START.astimezone(timezone.utc).isoformat())), "Fri 21:30")
        self.assertIsNone(S._eventbrite_end(None, "21:30:00", "America/New_York", "x"))

    def test_boston_calendar_when_line(self):
        m = S._BC_TIME_RANGE_RE.search("Monday, Nov 09, 2026 5:00p - 10:00p Repeats weekly")
        self.assertEqual((m.group(1), m.group(2), m.group(3)), ("10", "00", "p"))
        e = {"date": START.astimezone(timezone.utc).isoformat()}
        S._bc_apply_details(e, {"end_clock": "22:00"})
        self.assertEqual(local(e["end"]), "Fri 22:00")


if __name__ == "__main__":
    unittest.main()
