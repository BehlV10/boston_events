"""Boston Shows fill-in: adds shows we're missing, prices shows we have without one, and never
takes one show's price for another because the venues are close together."""
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import boston_shows  # noqa: E402
import scrapers  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

NOW = datetime(2026, 11, 5, 17, 0, tzinfo=timezone.utc)


def _row(venue, start, title, info):
    return (f'<tr class="event" data-venue="{venue}"><td class="event-start">{start}</td>'
            f'<td class="event-title"><a href="https://example.org/{abs(hash(title))}">{title}</a></td>'
            f'<td class="event-venue">at {venue} (Somewhere)</td><td class="event-info">{info}</td></tr>')


def _page(*days):
    return "".join(f'<div class="date-events" data-date="{d}"><table>{"".join(rows)}</table></div>' for d, rows in days)


def _ev(name, local, venue, price=None):
    y, mo, d, h, mi = local
    dt = datetime(y, mo, d, h, mi, tzinfo=scrapers.EASTERN).astimezone(timezone.utc).isoformat()
    return {"name": name, "date": dt, "venue": venue, "price": price, "url": "https://ours.example/"}


class FillInTests(unittest.TestCase):
    def run_fill(self, results, html):
        return boston_shows.apply(results, html, scrapers.EASTERN, resolve_event_geo,
                                  skip_venues=scrapers.BOSTON_SHOWS_GAP_VENUES, now=NOW)

    def test_prices_a_matching_show_and_adds_a_missing_one(self):
        ours = [{"venue": "Symphony Hall", "events": [_ev("Haydn's The Creation", (2026, 11, 7, 20, 0), "Symphony Hall")]}]
        html = _page(("2026-11-07", [_row("Symphony Hall", "8:00pm", "Haydn's The Creation", "$36-$181 / all ages")]),
                     ("2026-11-17", [_row("Deep Cuts", "7:00pm", "Tagua Tagua with Orlas", "$17 / 21+")]))
        out = self.run_fill(ours, html)
        self.assertEqual(ours[0]["events"][0]["price"], "$36-$181")
        self.assertEqual(out["priced_from_boston_shows"], 1)
        self.assertEqual([(e["name"], e["price"]) for e in out["events"]], [("Tagua Tagua with Orlas", "$17")])
        self.assertIn("Boston Shows", out["events"][0]["description"])

    def test_keeps_our_price_and_our_listing(self):
        ours = [{"venue": "The Lilypad", "events": [_ev("The OBGMs", (2026, 11, 8, 20, 0), "The Lilypad", "$20")]}]
        html = _page(("2026-11-08", [_row("The Lilypad", "8:00pm", "The OBGMs", "$15-$18 / 21+")]))
        out = self.run_fill(ours, html)
        self.assertEqual(ours[0]["events"][0]["price"], "$20")
        self.assertEqual(out["events"], [])

    def test_no_price_from_a_different_show_at_the_same_time_nearby(self):
        # The Burren and Somerville Theatre are steps apart in Davis Square
        ours = [{"venue": "Somerville Theatre", "events": [_ev("Warren Miller's Days Off", (2026, 11, 9, 19, 0), "Somerville Theatre")]}]
        html = _page(("2026-11-09", [_row("The Burren", "7:00pm", "Torn And Frayed", "$15 / 21+")]))
        out = self.run_fill(ours, html)
        self.assertIsNone(ours[0]["events"][0]["price"])
        self.assertEqual([e["name"] for e in out["events"]], ["Torn And Frayed"])

    def test_headliner_match_and_renamed_listing(self):
        ours = [{"venue": "TD Garden", "events": [_ev("sombr - You Are The Reason Tour", (2026, 11, 18, 18, 0), "TD Garden")]},
                {"venue": "The Row Hotel", "events": [_ev("Live Music @ The Row Hotel", (2026, 11, 12, 18, 0), "The Row Hotel")]}]
        html = _page(("2026-11-18", [_row("TD Garden", "7:00pm", "Sombr, Dove Cameron, Hannah Jadagu", "$45 / all ages")]),
                     ("2026-11-12", [_row("The Row Hotel", "6:00pm", "Bill McGoldrick's Acoustic Duo", "free / 21+")]))
        out = self.run_fill(ours, html)
        self.assertEqual(ours[0]["events"][0]["price"], "$45")  # same headliner
        self.assertEqual(out["events"], [])  # the Row Hotel's slot is already listed, under another name

    def test_busy_venue_with_another_event_at_the_same_time(self):
        ours = [{"venue": "MIT Events", "events": [_ev("MIT Energy & Climate Hack", (2026, 11, 6, 19, 0), "MIT Campus")]}]
        html = _page(("2026-11-06", [_row("MIT", "7:00pm", "Quantum Concert", "")]))
        out = self.run_fill(ours, html)
        self.assertEqual([e["name"] for e in out["events"]], ["Quantum Concert"])

    def test_venue_date_wins_over_boston_shows_date(self):
        ours = [{"venue": "Club Passim", "events": [_ev("Zachariah Hickman's Power Outage Party", (2026, 11, 20, 19, 30), "Club Passim", "Sold out")]}]
        html = _page(("2026-11-17", [_row("Club Passim", "7:30pm", "Zachariah Hickman's Power Outage Party", "")]))
        self.assertEqual(self.run_fill(ours, html)["events"], [])

    def test_outside_window_gap_venues_and_double_listings(self):
        html = _page(("2026-12-30", [_row("Deep Cuts", "7:00pm", "Too Far Out", "$10")]),
                     ("2026-11-06", [_row("Wally's Cafe", "7:00pm", "Benjamin Kassner Quintet", "free")]),
                     ("2026-11-11", [_row("Redbones", "7:00pm", "SLOWHOLE (NOLA) Slow Quit, Leg Injury", "$13"),
                                     _row("Redbones", "7:00pm", "SLOWHOLE, Slow Quit, Leg Injury", "")]))
        out = self.run_fill([], html)
        self.assertEqual([e["name"] for e in out["events"]], ["SLOWHOLE (NOLA) Slow Quit, Leg Injury"])

    def test_crawl_step_reports_an_unreachable_page(self):
        with mock.patch("boston_shows.get_html", side_effect=RuntimeError("503")):
            entry = scrapers._boston_shows_fill_in([])
        self.assertEqual((entry["venue"], entry["events"], entry["error"]), (boston_shows.SOURCE_NAME, [], "503"))


class PassimTests(unittest.TestCase):
    def test_every_night_of_a_run_and_sold_out(self):
        cards = "".join(
            f'<li><h3><a href="https://www.passim.org/live-music/lori/">Lori McKenna Band</a></h3>'
            f'<div class="date_time_tickets">{day} Doors 4:00PM Show 5:00PM $65 {note}</div></li>'
            for day, note in (("Dec 19th", "Sold Out"), ("Dec 20th", "")))

        class R:
            status_code, text = 200, f"<ul>{cards}</ul>"

        with mock.patch.object(scrapers._SESSION, "get", return_value=R()), \
                mock.patch.object(scrapers, "datetime", type("D", (scrapers.datetime,), {
                    "now": classmethod(lambda cls, tz=None: NOW.astimezone(tz) if tz else NOW)})):
            evs = scrapers.scrape_club_passim("https://www.passim.org/live-music/", scrapers.UA_CHROME)
        nights = sorted((scrapers.datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN).strftime("%m-%d"), e["price"])
                        for e in evs)
        self.assertEqual(nights, [("12-19", "$65 (sold out)"), ("12-20", "$65")])


class ShowTimeTests(unittest.TestCase):
    def test_royale_and_sinclair_doors_become_show_times(self):
        show = _ev("ADULT. & A Place To Bury Strangers", (2026, 11, 6, 20, 30), "The Sinclair")
        doors = _ev("ADULT. & A Place To Bury Strangers", (2026, 11, 6, 19, 30), "The Sinclair")
        typo = _ev("ADULT. & A Place To Bury Strangers at The Sinclair", (2026, 11, 6, 8, 30), "The Sinclair")
        club = _ev("Late Night Party", (2026, 11, 6, 22, 0), "The Sinclair")
        other = _ev("ADULT. at another club", (2026, 11, 6, 19, 0), "Middle East")
        results = [{"venue": "Bowery Presents Boston", "events": [show]},
                   {"venue": "The Sinclair", "events": [doors, club]},
                   {"venue": "Harvard Square (HSBA)", "events": [typo, other]}]
        scrapers._use_show_times(results)
        self.assertEqual(doors["date"], show["date"])
        self.assertEqual(typo["date"], show["date"])
        self.assertNotEqual(club["date"], show["date"])
        self.assertNotEqual(other["date"], show["date"])


class WrongListingTests(unittest.TestCase):
    def test_listing_dropped_only_on_that_date(self):
        keep = _ev("Los Angeles Philharmonic", (2027, 2, 6, 20, 0), "Symphony Hall")
        drop = _ev("Los Angeles Philharmonic - Boston", (2026, 11, 6, 20, 0), "Boston Symphony Hall")
        self.assertTrue(scrapers._is_wrong_listing(drop))
        self.assertFalse(scrapers._is_wrong_listing(keep))


class CoolidgeTests(unittest.TestCase):
    PAGE = """<div class="film-card"><div class="film-card__title"><h2><a href="/films/fargo">Fargo</a></h2></div>
      <span class="showtime-ticket__time">9:45pm</span></div>
      <div class="film-card"><div class="film-card__title"><h2><a href="/films/new">New Film</a></h2></div>
      <span class="showtime-ticket__time">1:30pm</span><span class="showtime-ticket__time">7:00pm</span>
      <span class="showtime-ticket__time">9:45pm</span></div>
      <div class="film-card"><div class="film-card__title"><h2><a href="/films/kids">Matinee</a></h2></div>
      <span class="showtime-ticket__time">11:00am</span></div>"""

    def test_real_times_one_listing_per_film_per_day(self):
        from bs4 import BeautifulSoup
        pages = iter([BeautifulSoup(self.PAGE, "html.parser")] + [BeautifulSoup("", "html.parser")] * 13)
        with mock.patch.object(scrapers, "fetch_soup", side_effect=lambda *a: next(pages)):
            evs = scrapers.scrape_coolidge("https://coolidge.org/", scrapers.UA_CHROME)
        got = {e["name"]: scrapers.datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN).strftime("%H:%M") for e in evs}
        self.assertEqual(got, {"Fargo": "21:45", "New Film": "19:00", "Matinee": "11:00"})
        self.assertIn("1:30pm, 7:00pm, 9:45pm", next(e for e in evs if e["name"] == "New Film")["description"])
        self.assertEqual(evs[0]["url"], "https://coolidge.org/films/fargo")


class FeverTests(unittest.TestCase):
    def test_every_session_at_local_time(self):
        state = {"p": [{"id": "1", "name": "Candlelight: Test", "location": {"name": "The Sanctuary -  Old South Church in Boston"},
                        "sessions": [{"value": "2026-11-13T19:00:00+00:00"}],
                        "also_happening_on": [{"value": "2026-11-21T21:00:00+00:00", "is_sold_out": True}]},
                       {"id": "2", "name": "Candlelight: The Lord of the Rings - Waitlist", "location": {"name": "Old South"},
                        "sessions": [{"value": "2026-11-12T10:00:00+00:00"}]}]}
        ld = '{"@type":"MusicEvent","offers":{"price":"57.00","url":"https://feverup.com/m/1"}}'
        html = f'<script type="application/ld+json">{ld}</script><script id="serverapp-state" type="application/json">{__import__("json").dumps(state)}</script>'

        class R:
            text = html

            def raise_for_status(self):
                pass

        with mock.patch.object(scrapers._SESSION, "get", return_value=R()):
            evs = sorted(scrapers.scrape_fever("", scrapers.UA_CHROME), key=lambda e: e["date"])
        self.assertEqual([(e["venue"], e["price"]) for e in evs], [("Old South Church", "From $57"), ("Old South Church", "Sold out")])
        self.assertEqual(scrapers.datetime.fromisoformat(evs[0]["date"]).astimezone(scrapers.EASTERN).hour, 19)


class ExhibitionTests(unittest.TestCase):
    def test_date_ranges(self):
        from datetime import date
        self.assertEqual(scrapers._exhibit_dates("Through January 24, 2027"), (None, date(2027, 1, 24)))
        self.assertEqual(scrapers._exhibit_dates("Jan 23 – Dec 31, 2026"), (date(2026, 1, 23), date(2026, 12, 31)))
        self.assertEqual(scrapers._exhibit_dates("August 6, 2026 - January 18, 2027"), (date(2026, 8, 6), date(2027, 1, 18)))
        self.assertEqual(scrapers._exhibit_dates("Ongoing"), (None, None))

    def test_only_shows_on_view_now(self):
        from datetime import date
        today = date(2026, 11, 6)
        on = scrapers._exhibition("Maverick Kings", "u", "Through December 6, 2026", "MFA", today)
        self.assertEqual(on["name"], "Maverick Kings (through Dec 6)")
        self.assertIsNone(scrapers._exhibition("Closed", "u", "Through October 1, 2026", "MFA", today))
        self.assertIsNone(scrapers._exhibition("Soon", "u", "December 1, 2026 - March 1, 2027", "MFA", today))
        self.assertIsNone(scrapers._exhibition("Permanent", "u", "Ongoing", "MFA", today))


if __name__ == "__main__":
    unittest.main()
