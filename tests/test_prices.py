"""Prices: never show a ticketed event as Free, and read prices from the venue's own listing.

Queer Board Game Night at Club Café is $5 + fee, but it showed a green Free pill: Club Café's
scraper ignored the venue's Cost data, and the site then guessed "free" because board game
nights usually are.
"""
import os
import sys
import unittest
import zoneinfo
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bs4 import BeautifulSoup  # noqa: E402

import scrapers  # noqa: E402
from scrapers import (  # noqa: E402
    _club_cafe_price,
    _do617_fill_prices,
    _do617_ticket_price,
    _partiful_price,
    admission_price,
    mentions_free,
    scrape_club_cafe,
)
from template import _is_event_free, _merge_duplicates  # noqa: E402

EASTERN = zoneinfo.ZoneInfo("America/New_York")


def _resp(text, status=200):
    r = mock.Mock()
    r.status_code = status
    r.text = text
    r.content = text.encode("utf-8")
    r.raise_for_status = mock.Mock()
    return r


class PriceTextTest(unittest.TestCase):
    def test_admission_price(self):
        cases = {
            "21+, $10 CASH ONLY cover": "$10",
            "🎟️: $10 CASH OR VENMO (RSVP NOW)": "$10",
            "Jackbox, Social Board Games & more? $5 Tickets.": "$5",
            "Tickets: $5 + fee": "$5",
            "Tickets $15 adv / $20 door": "$15–$20",
            "$40 & $30 + fee": "$30–$40",
            "Admission: $12.50": "$12.50",
            "$10 to enter": "$10",
        }
        for text, want in cases.items():
            self.assertEqual(admission_price(text), want, text)

    def test_amounts_that_are_not_admission(self):
        for text in ("Bring $3 for bag check", "Win $100 in prizes, free to play", "We raised $5,000",
                     "$1 Oysters", "$10 Pizza Night", "Free admission"):
            self.assertIsNone(admission_price(text), text)

    def test_mentions_free_needs_the_word(self):
        for text in ("FREE Early Movie Screening", "No Cover Karaoke", "Fenway Free Market", "Free Thursday Nights"):
            self.assertTrue(mentions_free(text), text)
        for text in ("Alice Howe & Freebo", "Hot Slander & Dogs Run Free", "Verveine: Gluten Free Cafe",
                     "feel free to bring a friend"):
            self.assertFalse(mentions_free(text), text)


class ClubCafeTest(unittest.TestCase):
    def test_price_from_the_venues_cost_data(self):
        self.assertEqual(_club_cafe_price("Queer Board Game Night", "5.00", "$5 Tickets."), "$5")
        self.assertEqual(_club_cafe_price("Drag Bingo", "0", ""), "Free")
        self.assertEqual(_club_cafe_price("Sunday Tea Dance", "", ""), "Free")
        self.assertEqual(_club_cafe_price("Orville Peck Concert Pre-Party", "", "No cover!"), "Free")
        self.assertIsNone(_club_cafe_price("Thanksgiving Dinner 2026", "", ""))
        # Two figures run together ("$15 after 10 pm" -> "1510") are read off the event page.
        self.assertEqual(_club_cafe_price("Saturday Night House Party", "1510", "", "$15 after 10 pm"), "$15 after 10 pm")
        self.assertEqual(_club_cafe_price("The Ladies Who Brunch", "3025", "Tickets $30.00 and $25"), "$25–$30")
        self.assertEqual(_club_cafe_price("Traitors", "2030", ""), "Ticketed")

    def test_a_listed_price_beats_a_no_cover_title(self):
        self.assertEqual(_club_cafe_price("Karaoke Wednesdays: Holiday Special", "20", ""), "$20")

    def test_scrape_uses_json_ld_offers(self):
        def article(name, slug, day, time="7:00 pm - 10:00 pm"):
            return f"""<article class="mec-event-article"><div class="mec-event-time">{time}</div>
              <h4 class="mec-event-title"><a href="https://www.clubcafe.com/club-events/{slug}/?occurrence={day}">{name}</a></h4>
              <div class="mec-event-loc-place">Moonshine Room</div></article>"""

        def ld(name, slug, day, price, desc=""):
            return f"""<script type="application/ld+json">{{"@context": "http://schema.org", "@type": "Event",
              "name": "{name}", "url": "https://www.clubcafe.com/club-events/{slug}/?occurrence={day}",
              "description": "{desc}", "offers": {{"url": "x", "price": "{price}", "priceCurrency": "$"}}}}</script>"""

        page = "<html><body>" + "".join([
            article("Queer Board Game Night", "queer-board-game-night-111626", "2026-11-16"),
            ld("Queer Board Game Night", "queer-board-game-night-111626", "2026-11-16", "5.00", "$5 Tickets."),
            article("Sunday Tea Dance", "sunday-tea-dance-110826", "2026-11-08", "4:00 pm - 10:00 pm"),
            ld("Sunday Tea Dance", "sunday-tea-dance-110826", "2026-11-08", ""),
            article("Saturday Night House Party", "saturday-night-darrin-2026", "2026-11-07", "10:00 pm - 2:00 am"),
            ld("Saturday Night House Party", "saturday-night-darrin-2026", "2026-11-07", "1510"),
        ]) + "</body></html>"
        detail = '<div class="mec-event-cost"><dd class="mec-events-event-cost">$15 after 10 pm</dd></div>'
        with mock.patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(page, "html.parser")), \
                mock.patch.object(scrapers._SESSION, "get", return_value=_resp(detail)) as get:
            events = scrape_club_cafe("https://www.clubcafe.com/full-calendar/", "UA")
        prices = {e["name"]: e["price"] for e in events}
        self.assertEqual(prices["Queer Board Game Night"], "$5")
        self.assertEqual(prices["Sunday Tea Dance"], "Free")
        self.assertEqual(prices["Saturday Night House Party"], "$15 after 10 pm")
        self.assertEqual(get.call_count, 1, "only the unreadable price needs the event page")
        self.assertFalse(_is_event_free(next(e for e in events if e["name"] == "Queer Board Game Night")))


class Do617Test(unittest.TestCase):
    PAGE = """<html><head>{ld}</head><body><div class="event-summary">
      <section class="ticket-section"><h2>{line}</h2><span>On sale</span></section></div></body></html>"""

    def _price(self, line, ld=""):
        page = self.PAGE.format(line=line, ld=ld) if line is not None else f"<html><head>{ld}</head><body></body></html>"
        with mock.patch.object(scrapers._SESSION, "get", return_value=_resp(page)):
            return _do617_ticket_price("https://do617.com/events/2026/11/16/queer-board-game-night-tickets", "UA")

    def test_ticket_line(self):
        self.assertEqual(self._price("Tickets: $5 + fee"), "$5 + fee")
        self.assertEqual(self._price("Tickets: $46-$138+"), "$46-$138+")
        self.assertEqual(self._price("Tickets: $66-$195, plus fees"), "$66-$195")
        self.assertEqual(self._price("Tickets: Free, 21+"), "Free")
        self.assertIsNone(self._price("Tickets"))
        self.assertIsNone(self._price("Tickets: Dates and times vary"))
        self.assertIsNone(self._price(None))

    def test_free_flag_in_json_ld(self):
        ld = ('<script type="application/ld+json">{"@graph": [{"@type": "Event", "name": "Snowport",'
              ' "isAccessibleForFree": true}]}</script>')
        self.assertEqual(self._price(None, ld), "Free")

    def test_fill_prices_only_for_do617_pages(self):
        events = [
            {"name": "Queer Board Game Night", "url": "https://do617.com/events/2026/11/16/queer-board-game-night-tickets"},
            {"name": "Elsewhere", "url": "https://example.com/e/1"},
            {"name": "Priced", "url": "https://do617.com/events/2026/11/16/priced", "price": "$12"},
        ]
        with mock.patch.object(scrapers, "_do617_ticket_price", return_value="$5 + fee") as fetch:
            _do617_fill_prices(events, "UA")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual([e.get("price") for e in events], ["$5 + fee", None, "$12"])


class PartifulTest(unittest.TestCase):
    def test_cover_in_description(self):
        self.assertEqual(_partiful_price({"title": "Uplifting Tinashe", "isPublic": True,
                                          "description": "21+, $10 CASH ONLY cover ★ RSVP"}), "$10")
        self.assertEqual(_partiful_price({"title": "fruitstand's 3rd birthday", "isPublic": True,
                                          "description": "$15 cash cover, $10 for first 100 RSVPs"}), "$10–$15")

    def test_public_with_no_charge_is_free(self):
        self.assertEqual(_partiful_price({"title": "Boston Sapphic Craft Meetup", "isPublic": True,
                                          "description": "Bring a project!"}), "Free")

    def test_charge_without_amount_is_unknown(self):
        self.assertIsNone(_partiful_price({"title": "Warehouse Party", "isPublic": True,
                                           "description": "Tickets at the link"}))


class IsEventFreeTest(unittest.TestCase):
    def ev(self, name, **kw):
        e = {"name": name, "venue": kw.pop("venue", "Somewhere"), "_source_venue": kw.pop("source", "Somewhere"),
             "url": kw.pop("url", "https://example.com/event")}
        e.update(kw)
        return e

    def test_activity_words_still_suggest_free(self):
        self.assertTrue(_is_event_free(self.ev("Board Games @ Walker Memorial")))
        self.assertTrue(_is_event_free(self.ev("Poetry Open Mic", venue="Trident Booksellers & Cafe")))
        self.assertTrue(_is_event_free(self.ev("YA Book Club", source="Boston Public Library")))

    def test_but_not_when_the_listing_says_otherwise(self):
        bgn = "Queer Board Game Night"
        self.assertFalse(_is_event_free(self.ev(bgn, description="Hosted by Boston Gaymers. $5 Tickets.")))
        self.assertFalse(_is_event_free(self.ev(bgn, _alt_sources=[{"venue": "Do617", "price": "$5 + fee"}])))
        self.assertFalse(_is_event_free(self.ev(bgn, price="$5")))
        self.assertFalse(_is_event_free(self.ev("Open Mic with Live Band", url="https://www.ticketweb.com/event/open-mic")))
        self.assertFalse(_is_event_free(self.ev("Kids Open Mic", url="https://tickets.24hourmusic.com/eventperformances.asp?evt=11")))
        self.assertFalse(_is_event_free(self.ev("The Magic Lab: Open Mic Magic Show",
                                                url="https://www.eventbrite.com/e/the-magic-lab-tickets-1")))
        self.assertFalse(_is_event_free(self.ev("Wonder and Learn: Storytime!", venue="Boston Children's Museum")))

    def test_free_in_a_name_is_not_always_admission(self):
        self.assertFalse(_is_event_free(self.ev("Iliza Shlesinger: Free Nights & Weekends",
                                                url="https://www.ticketmaster.com/iliza-shlesinger-free-nights")))
        self.assertFalse(_is_event_free(self.ev("Hot Slander & Dogs Run Free")))
        self.assertFalse(_is_event_free(self.ev("Verveine: Gluten Free Cafe & Bakery")))
        self.assertFalse(_is_event_free(self.ev("Alice Howe & Freebo")))
        self.assertTrue(_is_event_free(self.ev("Free Thursday Nights", venue="Isabella Stewart Gardner Museum")))

    def test_explicit_free_price_still_wins(self):
        self.assertTrue(_is_event_free(self.ev("Drag Bingo", price="Free", url="https://www.ticketweb.com/x")))


class MergePriceTest(unittest.TestCase):
    def test_venue_price_beats_listing_site_free(self):
        t = datetime(2026, 11, 16, 19, 0, tzinfo=EASTERN)
        events = [
            {"name": "Queer Board Game Night", "venue": "Club Cafe", "date": "2026-11-17T00:00:00+00:00",
             "url": "https://do617.com/events/2026/11/16/queer-board-game-night-tickets", "price": "Free",
             "category": "community", "_source_venue": "Do617", "_time": t},
            {"name": "Queer Board Game Night", "venue": "Club Café (Moonshine Room)", "date": "2026-11-17T00:00:00+00:00",
             "url": "https://www.clubcafe.com/club-events/queer-board-game-night-111626/?occurrence=2026-11-16",
             "price": "$5", "category": "community", "_source_venue": "Club Café", "_time": t},
        ]
        merged = _merge_duplicates(events)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["_source_venue"], "Club Café")
        self.assertEqual(merged[0]["price"], "$5")
        self.assertFalse(_is_event_free(merged[0]))


class ComedyStudioLocationTest(unittest.TestCase):
    def test_harvard_square(self):
        from template import _event_city, resolve_subarea, resolve_transit_lines
        from venues_geo import resolve_event_geo
        e = {"name": "Comedy Hell", "venue": "The Comedy Studio", "_source_venue": "The Comedy Studio"}
        geo = resolve_event_geo(e)
        self.assertEqual(geo["address"], "5 John F. Kennedy St, Cambridge")
        city = _event_city(e["venue"], e["_source_venue"], e)
        self.assertEqual(city, "cambridge")
        name, slug = resolve_subarea(city, e, geo)
        self.assertEqual(slug, "harvard_sq")
        self.assertEqual(resolve_transit_lines(city, slug, e, geo), "red")


if __name__ == "__main__":
    unittest.main()
