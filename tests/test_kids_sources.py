"""Kids & family sources: Museum of Science, Arnold Arboretum, town library kids feeds."""

import os
import sys
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import scrapers as S  # noqa: E402
from scrapers import EASTERN  # noqa: E402


class ClockTimeTest(unittest.TestCase):
    def test_first_time_in(self):
        cases = {
            " | 8:00 – 9:00 am": (8, 0),
            " | 4:30 – 6:30 pm": (16, 30),
            " | Family-friendly session – 12:00 pm; fireside chat – 7:30 pm": (12, 0),
            " | 8:00 pm; February 27, 2027 | 2:00 pm and 8:00 pm": (20, 0),
            " | 10:00 am – 4:00 pm": (10, 0),
            " | 7 p.m.": (19, 0),
            " | All Day": None,
            " | 27, 2027": None,
        }
        for text, want in cases.items():
            self.assertEqual(S._first_time_in(text), want, text)


class MuseumOfScienceTest(unittest.TestCase):
    def _card(self, when, title, summary, info=None):
        info = info or f"{when:%A, %B} {when.day}, {when.year} | 4:30 – 6:30 pm"
        return {"event_listing": (
            '<div class="listing-item js-stretched-link"><a href="/events/x" class="listing-item__image"></a>'
            '<div class="listing-item__content"><div class="listing-item__content-info">'
            '<div class="listing-item__content-type taxonomy-tag">Event</div><div class="listing-item__date ui-label-md">'
            f'<div class="field field--name-field-date-time-info field--type-string field--label-hidden field__item">{info}</div>'
            f'</div></div><h3 class="listing-item__title heading-e-clamp"><a href="/events/{title[:5].lower()}">{title}</a></h3>'
            f'<div class="listing-item__summary">{summary}</div></div></div>')}

    def test_cards_become_events(self):
        when = datetime.now(EASTERN) + timedelta(days=10)
        data = {"pager": {"total_pages": 1}, "results": [
            self._card(when, "Beyond the Screen with NOVA: Evolution", "A special family-focused event."),
            self._card(when, "Clearing the Air", "A panel discussion on wildfire smoke.",
                       info=f"{when:%A, %B} {when.day}, {when.year} | 7:00 pm"),
            self._card(when, "Trust in Science Community Day", "Keynotes and more.",
                       info=f"{when:%A, %B} {when.day}, {when.year} | All Day"),
        ]}
        resp = MagicMock(); resp.json.return_value = data; resp.raise_for_status.return_value = None
        with patch("scrapers._SESSION.get", return_value=resp):
            evs = S.scrape_museum_of_science("https://www.mos.org/api/v1/event-listing/x", "ua")
        self.assertEqual([e["name"] for e in evs], ["Beyond the Screen with NOVA: Evolution", "Clearing the Air",
                                                    "Trust in Science Community Day"])
        nova, air, day = evs
        self.assertEqual(nova["category"], "family")
        self.assertNotEqual(air["category"], "art")  # "Museum" in the venue isn't evidence of art
        start = datetime.fromisoformat(nova["date"]).astimezone(EASTERN)
        self.assertEqual((start.hour, start.minute), (16, 30))
        self.assertEqual(datetime.fromisoformat(air["date"]).astimezone(EASTERN).hour, 19)
        self.assertEqual(datetime.fromisoformat(day["date"]).astimezone(EASTERN).hour, 10)
        self.assertTrue(nova["url"].startswith("https://www.mos.org/events/"))
        self.assertEqual(nova["venue"], "Museum of Science")


class ArboretumTest(unittest.TestCase):
    def test_skips_daily_tours_and_names_the_venue(self):
        when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        raw = [
            {"name": "Arboretum Highlights Tour", "date": when, "venue": "in front of the Hunnewell Building", "category": "outdoors"},
            {"name": "Family Wellness Walk", "date": when, "venue": "in front of the Hunnewell Building", "category": "family"},
            {"name": "Owl Prowl", "date": when, "venue": "Flora Way Gate", "category": "outdoors"},
        ]
        with patch("scrapers.scrape_tribe_rest", return_value=raw):
            evs = S.scrape_arnold_arboretum("https://arboretum.harvard.edu/wp-json/tribe/events/v1/events", "ua")
        self.assertEqual([e["name"] for e in evs], ["Family Wellness Walk", "Owl Prowl"])
        self.assertTrue(all(e["venue"] == "Arnold Arboretum" for e in evs))
        self.assertEqual(evs[0]["category"], "family")
        self.assertEqual(evs[1]["description"], "Meet at Flora Way Gate.")


class TownLibraryKidsTest(unittest.TestCase):
    def test_libcal_keeps_kids_programs_only(self):
        when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        raw = [
            {"name": "Make Way for Storytime", "date": when, "venue": "Cambridge Public Library (Main Library)", "category": "family"},
            {"name": "Teen D&D", "date": when, "venue": "Cambridge Public Library (Main Library)", "category": "family"},
            {"name": "Tween & Teen Craft Night", "date": when, "venue": "Cambridge Public Library (Main Library)", "category": "family"},
            {"name": "Memoir Writing Group", "date": when, "venue": "Cambridge Public Library (Main Library)", "category": "community"},
            {"name": "Baby Rhyme Time", "date": when, "venue": "Cambridge Public Library (Virtual)", "category": "family"},
            {"name": "Toddler Time", "date": when, "venue": "Cambridge Public Library (Auburndale)", "category": "community"},
        ]
        with patch("scrapers.scrape_cpl", return_value=raw):
            evs = S.scrape_newton_library_kids("https://newtonfreelibrary.libcal.com/rss.php", "ua")
        self.assertEqual([e["name"] for e in evs], ["Make Way for Storytime", "Tween & Teen Craft Night", "Toddler Time"])
        self.assertEqual(evs[0]["venue"], "Newton Free Library")
        self.assertEqual(evs[2]["venue"], "Newton Free Library (Auburndale)")
        self.assertTrue(all(e["locality"] == "Newton" and e["category"] == "family" for e in evs))


class KidsVenuesRegisteredTest(unittest.TestCase):
    def test_new_sources_are_scraped(self):
        names = {v["name"] for v in S._ALL_VENUES}
        for n in ("Museum of Science", "Arnold Arboretum", "Newton Library (kids)", "Malden Library (kids)",
                  "Mass Audubon Drumlin Farm", "Mount Auburn Cemetery", "Jeff Jam Singalongs",
                  "Zoo New England", "Artysh Lab", "The Street Chestnut Hill"):
            self.assertIn(n, names)


class ParentCalendarsAndCityEvents(unittest.TestCase):
    CITY_PAGE = """<h2 class="listing-group-title">November 28, 2030</h2>
    <article id="a"><span class="time-range"> 5:00pm-6:00pm </span><div class="title"> Lighting of the Ship </div>
    <div itemprop="streetAddress" class="addr-a"> Martins Park <br /> 64 Sleeper Street </div>
    <span itemprop="addressLocality" class="locality">Boston</span>
    <div class="dl-t">Price:</div> <div class="detail-item__body--secondary dl-d"> FREE </div>
    <div class="intro-text"><p>Holiday crafts for kids.</p></div>
    <a class="button" href="/node/10836">Event details</a></article>
    <article id="b"><span class="time-range"> 6:00pm-7:00pm </span><div class="title"> Back Bay: 207 Newbury St Abutters Meeting </div>
    <div itemprop="streetAddress"> Virtual </div><a class="button" href="/node/2">Event details</a></article>
    <article id="c"><span class="time-range"> 10:00am-11:00am </span><div class="title"> Support Group For Dementia Care Partners </div>
    <div itemprop="streetAddress"> BCYF </div><a class="button" href="/node/3">Event details</a></article>"""

    class Reply:
        status_code = 200

        def __init__(self, text):
            self.text = text

    def test_city_events_keep_the_citys_price_and_skip_civic_meetings(self):
        replies = lambda u, **k: self.Reply(self.CITY_PAGE)
        with patch.object(S._SESSION, "get", replies), patch.object(S.time, "sleep"):
            events = S.scrape_boston_gov("https://www.boston.gov/events", "ua")
        self.assertEqual([e["name"] for e in events], ["Lighting of the Ship"])
        e = events[0]
        self.assertEqual((e["price"], e["venue"], e["category"]), ("Free", "Martins Park", "family"))
        self.assertEqual(e["url"], "https://www.boston.gov/node/10836")
        self.assertTrue(e["date"].startswith("2030-11-28T22:00"))

    def test_city_scraper_stops_when_refused(self):
        calls = []

        def refused(url, **k):
            calls.append(url)
            reply = self.Reply("")
            reply.status_code = 503
            return reply
        with patch.object(S._SESSION, "get", refused), patch.object(S.time, "sleep"):
            self.assertEqual(S.scrape_boston_gov("https://www.boston.gov/events", "ua"), [])
        self.assertEqual(len(calls), 2)  # one for the calendar, one for the family list; no retries

    def test_macaroni_keeps_new_local_kids_events_only(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y%m%dT%H%M%SZ")
        row = {"id": "a1", "title": "Turtle Storytime", "place": "224 Washington St, Brookline, MA 02445",
               "org": "Turtle Books", "orgName": "", "cats": ["Kids & Family"], "multi": False, "allDay": False,
               "utcFrom": soon, "desc": "Songs"}
        rows = [row,
                {**row, "id": "a2", "title": "Far Away", "place": "2 Baker St, Foxborough, MA 02035"},
                {**row, "id": "a3", "title": "Virginia", "place": "1 Main St, Arlington, VA 22203"},
                {**row, "id": "a4", "title": "Have It", "org": "Cary Memorial Library"},
                {**row, "id": "a5", "title": "Parent Workshop"},
                {**row, "id": "a6", "title": "Grown-ups", "cats": ["Lifestyle"]},
                {**row, "id": "a7"}]  # the same event from another edition
        page = '<script id="mk-list-data">' + json.dumps({"tz": "x", "events": rows}) + "</script>"
        with patch.object(S._SESSION, "get", lambda u, **k: self.Reply(page)), \
                patch.object(S.time, "sleep"):
            events = S.scrape_macaroni_kid("x", "ua")
        self.assertEqual([e["name"] for e in events], ["Turtle Storytime"])
        self.assertEqual(events[0]["url"], "https://newton.macaronikid.com/events?yodelEventId=a1")
        self.assertEqual(events[0]["venue"], "Turtle Books")

    def test_eventbrite_free_flag_inside_ticket_availability(self):
        event = {"name": "Dance Party", "url": "https://www.eventbrite.com/e/1", "start_date": "2030-01-05",
                 "start_time": "10:00", "timezone": "America/New_York",
                 "ticket_availability": {"is_free": True}}
        page = "window.__SERVER_DATA__ = " + json.dumps({"events": {"results": [event]}}) + ";</script>"
        found = S._parse_eventbrite_server_data(page)
        self.assertEqual([e["price"] for e in found], ["Free"])



class DirectFamilyCalendars(unittest.TestCase):
    def test_cambridge_reads_the_visible_time_not_the_12_hour_attribute(self):
        page = """<li class="eventItem"><time datetime="2030-11-05 06:15:00"><strong><span>6:15 PM</span></strong></time>
        <a id="x" href="/citycalendar/view.aspx?guid=abc123">Family Literacy Night</a>
        <em class="location">City Hall, 795 Massachusetts Ave</em><p>Free for families.</p></li>"""
        (start, title, link, place, summary), = S._cambridge_rows(page)
        self.assertEqual((start.hour, start.minute, title), (18, 15, "Family Literacy Night"))
        self.assertEqual(place, "City Hall, 795 Massachusetts Ave")

    def test_discovery_museum_skips_members_only(self):
        card = ('<h3 class="teaser-title h2"><a href="/events-programs/{0}">{1}</a></h3>'
                '<time datetime="2030-11-12T10:00:00-05:00">10:00am</time>')
        page = card.format("eat", "Eat Like a Bird") + card.format("m", "Members-Only Evening")
        replies = [MagicMock(text=page), MagicMock(text="")]
        with patch.object(S._SESSION, "get", side_effect=replies), patch.object(S.time, "sleep"):
            events = S.scrape_discovery_museum("https://www.discoveryacton.org/visit/events-programs", "ua")
        self.assertEqual([e["name"] for e in events], ["Eat Like a Bird"])
        self.assertEqual(events[0]["url"], "https://www.discoveryacton.org/events-programs/eat")

    def test_emerald_necklace_skips_cards_without_a_time(self):
        page = ('<a class="c" href="./calendar/walk">Nov 14 Sat Second Saturdays Jamaica Pond 10:00am - 12:00pm</a>'
                '<a class="c" href="./calendar/drive">Oct 19 Mon Winter Clothing Drive</a>')
        now = datetime(2030, 11, 1, tzinfo=EASTERN)
        with patch.object(S._SESSION, "get", return_value=MagicMock(text=page)), patch.object(S, "datetime", wraps=datetime) as fake:
            fake.now.return_value = now
            events = S.scrape_emerald_necklace("https://www.emeraldnecklace.org/calendar", "ua")
        self.assertEqual([e["venue"] for e in events], ["Jamaica Pond"])
        self.assertEqual(events[0]["url"], "https://www.emeraldnecklace.org/calendar/walk")


if __name__ == "__main__":
    unittest.main()
