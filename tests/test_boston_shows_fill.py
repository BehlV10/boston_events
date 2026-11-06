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


if __name__ == "__main__":
    unittest.main()
