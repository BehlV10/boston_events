"""An aggregator's date for an event is dropped when the venue's own calendar has that event on another date."""
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import template as T  # noqa: E402


def ev(name, venue, source):
    return {"name": name, "venue": venue, "_source_venue": source}


class MisdatedAggregatorTest(unittest.TestCase):
    def test_club_cafe_partner_dancing(self):
        d16, d23 = date(2026, 11, 16), date(2026, 11, 23)
        buckets = {
            d16: [ev("Drag Bingo", "Club Café", "Club Café"),
                  ev("Queer Line & Partner Dancing", "Club Cafe", "The Boston Calendar"),
                  ev("Some Show Club Café Doesn't List", "Club Cafe", "The Boston Calendar")],
            d23: [ev("Queer Line & Partner Dancing", "Club Café (Moonshine Room)", "Club Café"),
                  ev("Queer Line & Partner Dancing", "Club Cafe", "The Boston Calendar")],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 1)
        self.assertEqual([e["name"] for e in buckets[d16]], ["Drag Bingo", "Some Show Club Café Doesn't List"])
        self.assertEqual(len(buckets[d23]), 2)  # the right date is kept, and merges as usual

    def test_renamed_same_day_listing_is_kept(self):
        d1, d2 = date(2026, 11, 24), date(2026, 11, 17)
        buckets = {
            d1: [ev("Trivia Tuesdays – Win Show Tickets", "Club Café", "Club Café"),
                 ev("Trivia Tuesday at Club Cafe", "Club Cafe", "The Boston Calendar"),
                 ev("Comedy Gold w/ host Sarah Fitz", "The Comedy Studio", "The Comedy Studio"),
                 ev("Comedy Gold Stand-Up Showcase", "The Comedy Studio", "The Boston Calendar")],
            d2: [ev("Trivia Tuesday at Club Cafe", "Club Cafe", "The Boston Calendar"),
                 ev("Trivia Tuesday", "Club Café", "Club Café"),
                 ev("Comedy Gold Stand-Up Showcase", "The Comedy Studio", "The Comedy Studio")],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 0)

    def test_short_or_summary_venue_feed_does_not_count(self):
        # Artisans Asylum's Eventbrite page shows a weekly series once, at its next date; the
        # Huntington's feed has no events at all on the aggregator's date.
        d1, d2 = date(2026, 11, 18), date(2026, 11, 25)
        buckets = {
            d1: [ev("Free Circuit Hacking Night!", "Artisans Asylum", "Artisans Asylum")],
            d2: [ev("Free Circuit Hacking Night!", "Artisans Asylum", "The Boston Calendar"),
                 ev("Plasma Cutting 101", "Artisans Asylum", "Artisans Asylum"),
                 ev("Adia & Clora Snatch Joy", "Huntington Theatre", "The Boston Calendar")],
            date(2026, 12, 13): [ev("Adia & Clora Snatch Joy", "The Huntington Theatre", "The Huntington Theatre")],
        }
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 0)

    def test_other_sources_untouched(self):
        d1, d2 = date(2026, 11, 16), date(2026, 11, 23)
        buckets = {d1: [ev("Queer Line & Partner Dancing", "Club Cafe", "Meetup Boston (by topic)")],
                   d2: [ev("Queer Line & Partner Dancing", "Club Café", "Club Café")]}
        self.assertEqual(T._drop_misdated_aggregator_listings(buckets), 0)


if __name__ == "__main__":
    unittest.main()
