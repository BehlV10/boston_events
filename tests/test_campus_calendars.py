"""Campus calendars: Localist (MIT, Boston College, Suffolk) and Harvard College's LiveWhale JSON."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers
from scrapers import EASTERN
from venues_geo import resolve_event_geo


def _iso(days, hour=19):
    return (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _reply(payload):
    r = mock.Mock(status_code=200)
    r.json.return_value = payload
    r.raise_for_status = lambda: None
    return r


def _localist_event(title, days=3, audience=("Public",), types=("Lecture",), venue="Building 10", all_day=False, **extra):
    ev = {"title": title, "status": "live", "experience": "inperson", "location_name": venue,
          "localist_url": f"https://calendar.mit.edu/event/{title.lower().replace(' ', '-')}", "free": True,
          "filters": {"event_audience": [{"name": a} for a in audience], "event_types": [{"name": t} for t in types]},
          "event_instances": [{"event_instance": {"start": _iso(days, 0 if all_day else 19), "all_day": all_day}}]}
    ev.update(extra)
    return {"event": ev}


def _localist(*events, url="https://calendar.mit.edu/api/2/events?days=56&pp=100"):
    with mock.patch.object(scrapers, "_SESSION") as session:
        session.get.return_value = _reply({"events": list(events), "page": {"current": 1, "total": 1}})
        return scrapers.scrape_localist(url, "ua")


class Localist(unittest.TestCase):
    def test_public_in_person_event_kept_with_campus_on_bare_building(self):
        events = _localist(_localist_event("Dresselhaus Lecture", venue="Building 10",
                                           geo={"latitude": "42.3595", "longitude": "-71.0921"}))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["venue"], "Building 10 (MIT)")
        self.assertEqual((e["lat"], e["price"]), (42.3595, "Free"))

    def test_venue_naming_an_institution_gets_no_suffix(self):
        events = _localist(_localist_event("Chorale", venue="Boston College - St. Mary's Chapel"),
                           url="https://events.bc.edu/api/2/events?days=56&pp=100")
        self.assertEqual(events[0]["venue"], "Boston College - St. Mary's Chapel")

    def test_private_virtual_and_audience_restricted_events_dropped(self):
        events = _localist(_localist_event("A", private=True), _localist_event("B", experience="virtual"),
                           _localist_event("C", audience=("Students",)), _localist_event("D", audience=(), types=("Meeting",)))
        self.assertEqual(events, [])

    def test_untagged_audience_kept_only_for_public_kinds(self):
        events = _localist(_localist_event("Fall Concert", audience=(), types=("Performing Arts",)),
                           _localist_event("Lab Lunch", audience=(), types=("Social",)))
        self.assertEqual([e["name"] for e in events], ["Fall Concert"])

    def test_seminars_info_sessions_and_games_dropped(self):
        events = _localist(_localist_event("Chemistry Seminar: Catalysis"), _localist_event("Graduate Information Session"),
                           _localist_event("Boston College Men's Cross Country vs NCAA Northeast Regional"),
                           _localist_event("Men's Hockey vs Notre Dame"))
        self.assertEqual(events, [])

    def test_repeating_all_day_rows_and_exhibitions_listed_once(self):
        rows = [_localist_event("ART CUT BOSTON", days=d, all_day=True) for d in (1, 2, 3)]
        rows += [_localist_event("Exhibition: Shadows and Light", days=d, types=("Exhibits",)) for d in (1, 2)]
        rows += [_localist_event("LitTea", days=d) for d in (1, 8)]  # a weekly event keeps each date
        events = _localist(*rows)
        self.assertEqual(sorted(e["name"] for e in events), ["ART CUT BOSTON", "Exhibition: Shadows and Light", "LitTea", "LitTea"])
        art = next(e for e in events if e["name"] == "ART CUT BOSTON")
        self.assertRegex(art["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_one_event_listed_twice_at_one_time_is_kept_once(self):
        events = _localist(_localist_event("ASTAZA!", types=("Performing Arts",)),
                           _localist_event("ASTAZA in Concert - THE DOOR in Arabic Music", types=("Performing Arts",)),
                           _localist_event("Gaelic Roots ft. Copley Street", types=("Performing Arts",)))
        self.assertEqual([e["name"] for e in events], ["ASTAZA!", "Gaelic Roots ft. Copley Street"])

    def test_campus_fallback_geo_does_not_override_the_calendars_own_point(self):
        own = resolve_event_geo({"venue": "Burns Library (Boston College)", "lat": 42.3358, "lng": -71.1696,
                                 "_source_venue": "Boston College Events"})
        self.assertEqual(own["venue"], "Burns Library (Boston College)")
        fallback = resolve_event_geo({"venue": "Simboli Chapel (Boston College)", "_source_venue": "Boston College Events"})
        self.assertEqual(fallback["venue"], "Boston College")


def _harvard_row(title, days=3, types=("Performances",), all_day=False, **extra):
    row = {"title": title, "date_iso": _iso(days, 0 if all_day else 19), "is_all_day": all_day,
           "event_types": list(types), "location_title": "Sanders Theatre", "url": "https://events.college.harvard.edu/x"}
    row.update(extra)
    return row


def _harvard(*rows):
    with mock.patch.object(scrapers, "_SESSION") as session:
        session.get.return_value = _reply({"data": list(rows)})
        return scrapers.scrape_harvard_college_events("https://events.college.harvard.edu/", "ua")


class HarvardCollege(unittest.TestCase):
    def test_public_performance_kept(self):
        events = _harvard(_harvard_row("Harvard Choruses presents A Christmas Carol", cost="$15"))
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]["venue"], events[0]["category"]), ("Sanders Theatre (Harvard)", "music"))

    def test_student_only_online_and_noise_dropped(self):
        events = _harvard(_harvard_row("Dinner", event_types_audience=["Class of 2029"]),
                          _harvard_row("Concert stream", online_type="online"),
                          _harvard_row("Office Hours with the Dean"),
                          _harvard_row("House Meeting", types=("Student Life",)))
        self.assertEqual(events, [])

    def test_daily_all_day_item_listed_once(self):
        events = _harvard(*[_harvard_row("Dance in Public", days=d, all_day=True) for d in (3, 1, 2)])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date"], (datetime.now(EASTERN) + timedelta(days=1)).date().isoformat())

    def test_own_coordinates_used_when_in_the_area(self):
        e = _harvard(_harvard_row("Recital", location_latitude="42.3762", location_longitude="-71.1149"))[0]
        self.assertEqual((e["lat"], e["lng"]), (42.3762, -71.1149))
        e = _harvard(_harvard_row("Recital", location_latitude="0", location_longitude="0"))[0]
        self.assertNotIn("lat", e)

    def test_busy_ranges_are_split_until_each_request_fits(self):
        full = {"data": [_harvard_row(f"Concert {i}") for i in range(100)]}
        small = {"data": [_harvard_row("Concert")]}
        calls = []
        def get(url, **kw):
            calls.append(url)
            return _reply(full if len(calls) == 1 else small)
        with mock.patch.object(scrapers, "_SESSION") as session:
            session.get.side_effect = get
            scrapers.scrape_harvard_college_events("https://events.college.harvard.edu/", "ua")
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
