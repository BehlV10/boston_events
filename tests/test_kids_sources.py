"""Kids & family sources: Museum of Science, Arnold Arboretum, town library kids feeds."""

import os
import sys
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


if __name__ == "__main__":
    unittest.main()
