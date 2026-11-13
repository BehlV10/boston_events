"""Footlight Club (Jamaica Plain) via the OvationTix public calendar API."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers as S
import template as T
from venues_geo import resolve_event_geo


def _show(pid, perf, start, **kw):
    return {"productionId": pid, "performanceId": perf, "performanceStartTime": start.strftime("%Y-%m-%d %H:%M"),
            "performanceEndTime": (start + timedelta(hours=2, minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "isVisible": True, "isCancelled": False, "isSoldOut": False, "remainingTix": True, **kw}


class FootlightClubTest(unittest.TestCase):
    def test_scrape(self):
        day = (datetime.now(S.EASTERN) + timedelta(days=2)).replace(hour=19, minute=30, second=0, microsecond=0)
        past = datetime.now(S.EASTERN) - timedelta(days=1)
        data = [
            {"date": day.strftime("%Y-%m-%d"), "productions": [
                {"productionId": 1, "name": "Annie", "hidden": False, "showtimes": [
                    _show(1, 10, day), _show(1, 11, day.replace(hour=14), remainingTix=False),
                    _show(1, 12, day.replace(hour=16), isCancelled=True), _show(1, 13, past)]},
                {"productionId": 2, "name": "Footlight Reunion &amp; BBQ", "hidden": False, "showtimes": [_show(2, 20, day)]},
            ]},
        ]
        with mock.patch.object(S, "_SESSION") as session:
            session.get.return_value = mock.Mock(status_code=200, json=lambda: data, raise_for_status=lambda: None)
            events = S.scrape_footlight_club("https://ci.ovationtix.com/36903", "ua")
            self.assertEqual(session.get.call_args.kwargs["headers"]["clientId"], "36903")
        annie = [e for e in events if e["name"] == "Annie"]
        self.assertEqual(len(annie), 2)
        self.assertEqual({e.get("description") for e in annie}, {None, "Sold out."})
        self.assertEqual(annie[0]["url"], "https://ci.ovationtix.com/36903/production/1")
        self.assertEqual(annie[0]["category"], "stage")
        bbq = next(e for e in events if e["name"] == "Footlight Reunion & BBQ")
        self.assertEqual(bbq["category"], "community")

    def test_geo(self):
        e = {"venue": "Footlight Club", "name": "Annie"}
        geo = resolve_event_geo(e)
        self.assertEqual(geo["neighborhood"], "Jamaica Plain")
        city = T._event_city("Footlight Club", "Footlight Club", e)
        self.assertEqual(city, "boston")
        self.assertEqual(T.resolve_subarea(city, e, geo)[1], "jp_dorchester")


if __name__ == "__main__":
    unittest.main()
