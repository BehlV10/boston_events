"""Resident Advisor (ra.co GraphQL): Boston club nights, unlisted venues and RA's cost strings."""
import json
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers as S
import template
from scrapers import EASTERN
from venues_geo import resolve_event_geo


def _local(days, hour=22):
    return (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def _row(eid, title, venue, address=None, days=3, hours=4, cost="10"):
    start = _local(days)
    fmt = "%Y-%m-%dT%H:%M:%S.000"
    return {"event": {"id": str(eid), "title": title, "contentUrl": f"/events/{eid}", "cost": cost,
                      "startTime": start.strftime(fmt), "endTime": (start + timedelta(hours=hours)).strftime(fmt),
                      "venue": {"name": venue, "address": address}}}


def _reply(rows, total=None, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = {"data": {"eventListings": {"totalResults": len(rows) if total is None else total, "data": rows}}}
    r.raise_for_status = lambda: None
    return r


def _scrape(*replies):
    with mock.patch.object(S, "_SESSION") as session:
        session.post.side_effect = list(replies)
        events = S.scrape_resident_advisor("https://ra.co/events/us/boston", "ua")
        return events, session


class Venues(unittest.TestCase):
    def test_unlisted_spots_get_name_and_address(self):
        v = S._ra_venue
        self.assertEqual(v("TBA - NAICOB - 105 S. Huntington Ave. Jamaica Plain, 02130", None),
                         ("NAICOB", "105 S. Huntington Ave. Jamaica Plain, 02130"))
        self.assertEqual(v("TBA - Jadu 767 Centre St, Jamaica Plain, MA 02130", None)[0], "Jadu")
        self.assertEqual(v("TBA - 288 Green St. Cambridge", None)[0], "288 Green St")

    def test_secret_locations_have_no_place(self):
        for name in ("TBA", "TBA - Secret Location", "TBA - Location TBA", "TBA - Call Infoline for Secret Location"):
            self.assertEqual(S._ra_venue(name, None), ("Location TBA", ""), name)
        self.assertIsNone(resolve_event_geo({"venue": "Location TBA", "name": "Infra presents: Rrose",
                                             "_source_venue": "Resident Advisor Boston"}))

    def test_ra_names_map_to_known_places(self):
        for ra_name, place in (("Dx", "Descent"), ("Descent", "Descent"), ("Phoenix Landing", "The Phoenix Landing"),
                               ("Bsmnt", "bsmnt"), ("52 Church", "52 Church"), ("The Chemist", "The Chemist"),
                               ("The Smoot Standard", "The Smoot Standard"), ("Westin Copley", "Westin Copley Place")):
            venue, _ = S._ra_venue(ra_name, "x")
            g = resolve_event_geo({"venue": venue, "name": "Night", "_source_venue": "Resident Advisor Boston"})
            self.assertEqual(g and g["venue"], place, ra_name)
        self.assertEqual(resolve_event_geo({"venue": "NAICOB", "name": "x"})["neighborhood"], "Jamaica Plain")


class Prices(unittest.TestCase):
    def test_cost_strings(self):
        p = S._ra_price
        self.assertEqual(p("10"), "$10")
        self.assertEqual(p("$5 - $20"), "$5–20")
        self.assertEqual(p("20+"), "$20+")
        self.assertEqual(p("0"), "Free")
        self.assertIsNone(p(""))
        self.assertIsNone(p("$"))


class Scrape(unittest.TestCase):
    def test_times_are_boston_local_with_end(self):
        events, _ = _scrape(_reply([_row(1, "Modular presents: X", "Phoenix Landing", "512 Massachusetts Avenue; Cambridge, MA")]))
        e = events[0]
        start = datetime.fromisoformat(e["date"]).astimezone(EASTERN)
        self.assertEqual((start.hour, start.minute), (22, 0))
        self.assertEqual(datetime.fromisoformat(e["end"]) - datetime.fromisoformat(e["date"]), timedelta(hours=4))
        self.assertEqual((e["url"], e["price"], e["venue"], e["category"]),
                         ("https://ra.co/events/1", "$10", "The Phoenix Landing", "clubbing"))
        self.assertEqual(e["address"], "512 Massachusetts Avenue, Cambridge, MA")

    def test_pages_until_total_and_skips_repeats_and_past(self):
        page1 = [_row(i, f"Night {i}", "Royale") for i in range(100)]
        page2 = [_row(5, "Night 5", "Royale"), _row(200, "Old", "Royale", days=-2), _row(201, "Last", "Royale")]
        events, session = _scrape(_reply(page1, total=103), _reply(page2, total=103))
        self.assertEqual(session.post.call_count, 2)
        sent = json.loads(json.dumps(session.post.call_args.kwargs["json"]))
        self.assertEqual(sent["variables"]["filters"]["areas"], {"eq": 530})
        self.assertEqual(len(events), 101)
        self.assertNotIn("Old", [e["name"] for e in events])

    def test_blocked_returns_nothing(self):
        events, _ = _scrape(_reply([], status=403))
        self.assertEqual(events, [])

    def test_registered_below_venue_feeds(self):
        v = next(x for x in S._ALL_VENUES if x["name"] == "Resident Advisor Boston")
        self.assertIs(v["scraper"], S.scrape_resident_advisor)
        self.assertLess(template._source_priority("Resident Advisor Boston"), template._source_priority("Royale"))


if __name__ == "__main__":
    unittest.main()
