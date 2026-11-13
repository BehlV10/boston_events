"""Don't Tell Aunty's Eventbrite organizer page, and its geo placement."""
import unittest
from unittest import mock

import scrapers as S
import template as T
from venues_geo import resolve_event_geo

CHUNK = ('{"eventbrite_event_id":"123","name":"Bollywood Saturdays","url":"https://www.eventbrite.com/e/bollywood-saturdays-tickets-123",'
         '"start_date":"2099-04-25","start_time":"22:00:00","end_date":"2099-04-26","end_time":"02:00:00",'
         '"timezone":"America/New_York","is_free":true}')


class DontTellAuntyTest(unittest.TestCase):
    def test_registered(self):
        self.assertIn("Don't Tell Aunty", {v["name"] for v in S._ALL_VENUES})

    def test_scrape_sets_venue_and_category(self):
        with mock.patch.object(S, "_SESSION") as session:
            session.get.return_value = mock.Mock(status_code=200, text="<html>" + CHUNK + "</html>",
                                                 raise_for_status=lambda: None)
            events = S.scrape_dont_tell_aunty("https://www.eventbrite.com/o/dont-tell-aunty-121023442169", "ua")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Bollywood Saturdays")
        self.assertEqual(events[0]["venue"], "Don't Tell Aunty")
        self.assertEqual(events[0]["category"], "clubbing")
        self.assertEqual(events[0]["price"], "Free")

    def test_geo_is_back_bay_boston(self):
        e = {"venue": "Don't Tell Aunty", "_source_venue": "Don't Tell Aunty", "name": "x"}
        geo = resolve_event_geo(e)
        city = T._event_city(e["venue"], e["_source_venue"], e)
        self.assertEqual(city, "boston")
        self.assertEqual(T.resolve_subarea(city, e, geo)[1], "back_bay")
        self.assertIn("1080 Boylston", geo["address"])


if __name__ == "__main__":
    unittest.main()
