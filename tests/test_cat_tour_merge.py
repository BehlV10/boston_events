"""One event, four listings (Nov 2026 Somerville Cat Tour): Eventbrite says noon, The Boston
Calendar copied its link with 1 PM, Do617 gave only "Cat Tour" @ "Somerville"."""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import template as T  # noqa: E402

EB = "https://www.eventbrite.com/e/somerville-cat-tour-tickets-1998374511960"
VENUES = [
    {"venue": "Eventbrite Somerville", "url": "https://www.eventbrite.com", "events": [
        {"name": "Somerville Cat Tour", "date": "2026-11-14T17:00:00+00:00", "url": EB,
         "venue": "Tandem Veterinary Clinic - Somerville", "description": "Join us for the 2nd Annual Somerville Cat Tour"}]},
    {"venue": "The Boston Calendar", "url": "https://www.thebostoncalendar.com", "events": [
        {"name": "2026 Somerville Cat Tour x Tandem Vet", "date": "2026-11-14T18:00:00+00:00", "url": EB,
         "venue": "Tandem Vet Somerville", "price": "Free"}]},
    {"venue": "Do617", "url": "https://do617.com", "events": [
        {"name": "Cat Tour", "date": "2026-11-14T17:00:00+00:00",
         "url": "https://do617.com/events/2026/11/14/cat-tour-tickets", "venue": "Somerville"}]},
    {"venue": "The Boston Calendar", "url": "https://www.thebostoncalendar.com", "events": [
        {"name": "Where to Find $1 Oysters Around Boston", "date": "2026-11-14T15:00:00+00:00",
         "url": "https://www.thebostoncalendar.com/events/oysters", "venue": "Boston"}]},
    {"venue": "Downtown Boston BID", "url": "https://www.bostondowntown.org", "events": [
        {"name": "Boston: Freedom Trail Insiders Tour with Museum Entry", "date": "2026-11-14T15:30:00+00:00",
         "url": "https://example.com/freedom-trail", "venue": "Hub Town Tours"}]},
]


class CatTourMergeTest(unittest.TestCase):
    def setUp(self):
        dated, _, _ = T.group_by_date(copy.deepcopy(VENUES))
        self.evs = [e for _, evs in dated for e in evs]

    def test_one_listing_at_the_organizers_time(self):
        cats = [e for e in self.evs if "cat tour" in e["name"].lower()]
        self.assertEqual(len(cats), 1, [e["name"] for e in cats])
        cat = cats[0]
        self.assertEqual(cat["_time"].strftime("%H:%M"), "12:00")  # Eventbrite's own noon, not 1 PM
        self.assertEqual(cat["name"], "Somerville Cat Tour")  # not Do617's bare "Cat Tour"
        self.assertIn("Tandem", cat["venue"])  # not just "Somerville"

    def test_city_only_venue_needs_a_matching_title(self):
        trail = next(e for e in self.evs if "Freedom Trail" in e["name"])
        self.assertFalse(any("Oysters" in (a.get("name") or "") for a in trail.get("_alt_sources") or []))

    def test_helpers(self):
        self.assertTrue(T._owns_link({"_source_venue": "Eventbrite Boston", "url": EB}))
        self.assertFalse(T._owns_link({"_source_venue": "The Boston Calendar", "url": EB}))
        for v in ("Somerville", "Boston, MA", " cambridge "):
            self.assertTrue(T._BARE_CITY_VENUE_RE.match(v), v)
        for v in ("Somerville Theatre", "Boston Public Library"):
            self.assertFalse(T._BARE_CITY_VENUE_RE.match(v), v)


if __name__ == "__main__":
    unittest.main()
