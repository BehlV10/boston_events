"""Cards show believable end times, and today's events stay listed until they end.

A Snowport-style all-day event used to vanish two hours after it opened. Sources' ends were
measured first (Nov 2026): placeholders (end = start, 11:59 PM, midnight-midnight, 24 h) aren't shown.
"""
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import template as T  # noqa: E402

E = "-05:00"


def ev(start, end=None):
    e = {"name": "X", "date": f"2026-11-13T{start}{E}"}
    if end:
        e["end"] = end if "T" in end else f"2026-11-13T{end}{E}"
    e["_time"] = datetime.fromisoformat(e["date"])
    return e


class TrustedEndTest(unittest.TestCase):
    def test_believed(self):
        self.assertEqual(T.format_when(ev("19:00:00", "22:00:00")), "7:00–10:00 PM")
        self.assertEqual(T.format_when(ev("11:00:00", "14:30:00")), "11:00 AM–2:30 PM")
        self.assertEqual(T.format_when(ev("21:00:00", "2026-11-14T01:00:00" + E)), "9:00 PM–1:00 AM")
        self.assertEqual(T.format_when(ev("19:00:00", "2026-11-14T01:00:00Z")), "7:00–8:00 PM")  # UTC end
        self.assertEqual(T.format_when(ev("08:00:00", "2026-11-25T17:00:00" + E)), "8:00 AM · thru Wed Nov 25")

    def test_not_believed(self):
        for end in (None, "19:00:00", "18:00:00", "19:05:00", "23:59:00", "2026-11-14T19:00:00" + E,
                    "2026-11-14T08:00:00" + E, "2027-03-01T19:00:00" + E, "garbage"):
            self.assertEqual(T.format_when(ev("19:00:00", end)), "7:00 PM", end)
        self.assertIsNone(T.trusted_end({"date": "2026-11-13T00:00:00" + E, "end": "2026-11-14T00:00:00" + E}))
        self.assertIsNone(T.trusted_end({"date": "2026-11-13", "end": "2026-11-14"}))


class CardTest(unittest.TestCase):
    def test_card_carries_end_and_page_uses_it(self):
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        venues = [{"venue": "V", "url": "https://v.example.org/", "error": None, "events": [
            {"name": "Snow Fest", "date": start.isoformat(), "end": (start + timedelta(hours=6)).isoformat(),
             "venue": "Club Passim", "url": "https://v.example.org/a", "category": "music"},
            {"name": "Open Mic", "date": start.isoformat(), "end": start.isoformat(),
             "venue": "The Sinclair", "url": "https://v.example.org/b", "category": "music"}]}]
        with patch("template._load_community_events", return_value=[]):
            html = T.render_page(venues)
        ends = re.findall(r'data-end-epoch="(\d+)"', html)
        self.assertEqual(ends, [str(int((start + timedelta(hours=6)).timestamp()))])
        self.assertIn("m.endEpoch > 0 ? m.endEpoch <= nowEpoch : m.epoch < twoHoursAgoEpoch", html)
        self.assertIn("toCalUTC(m.end)", html)


if __name__ == "__main__":
    unittest.main()
