"""Do617 venue pages (Boston time, paging, weekly nights), Fenway Park from Ticketmaster,
season-ticket waitlists, and places for nightlife venues."""
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402
from scrapers import EASTERN  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402


def _resp(text, status=200):
    r = MagicMock()
    r.status_code = status
    r.content = text.encode()
    r.text = text
    return r


def _card(href, name, when, venue):
    return (f'<div data-card-kind="event"><a href="{href}"></a><h3>{name}</h3>'
            f'<p class="ds-listing-event-date">{when}</p><p>{venue}</p><p>Food/Drink • Fenway</p></div>')


def _page(venue, cards, next_page=None):
    nxt = f'<a href="/venues/x?page={next_page}">More</a>' if next_page else ""
    return f"<html><h1>{venue}</h1>{''.join(cards)}{nxt}</html>"


def _path(d):
    return f"{d.year}/{d.month}/{d.day}"


class BostonTime(unittest.TestCase):
    def test_winter_and_summer_offsets(self):
        """Do617 shows local times; the old code pinned -04:00, so every show from November to
        March was listed an hour early (Deep Cuts' 7 pm shows read 6 pm)."""
        self.assertEqual(S._do617_local_iso(datetime(2026, 11, 13).date(), "Fri, Nov 13 | 7 pm"),
                         "2026-11-14T00:00:00+00:00")
        self.assertEqual(S._do617_local_iso(datetime(2026, 7, 10).date(), "Fri, Jul 10 | 7:30 pm"),
                         "2026-07-10T23:30:00+00:00")
        self.assertEqual(S._do617_local_iso(datetime(2026, 11, 13).date(), "Today | 12 pm"),
                         "2026-11-13T17:00:00+00:00")

    def test_day_feed_uses_boston_time(self):
        d = datetime.now(EASTERN).date()
        html = _page("", [_card(f"../events/{_path(d)}/some-show-tickets", "Some Show", "Today | 7 pm", "Deep Cuts")])
        with patch.object(S._SESSION, "get", return_value=_resp(html)), \
                patch.object(S, "_do617_ticket_price", return_value=None):
            evs = S.scrape_do617("https://do617.com/events", "UA")
        got = datetime.fromisoformat(evs[0]["date"]).astimezone(EASTERN)
        self.assertEqual((got.date(), got.hour), (d, 19))

    def test_day_feed_dates_a_running_show_on_the_feeds_day(self):
        """An exhibition's card links to the day its run started (/events/2026/9/12/...)."""
        d = datetime.now(EASTERN).date()
        html = _page("", [_card("../events/2026/9/12/chimes-of-freedom", "Chimes of Freedom", "Today | 10 am", "MFA")])
        with patch.object(S._SESSION, "get", return_value=_resp(html)), \
                patch.object(S, "_do617_ticket_price", return_value=None):
            evs = S.scrape_do617("https://do617.com/events", "UA")
        days = sorted(datetime.fromisoformat(e["date"]).astimezone(EASTERN).date() for e in evs)
        self.assertEqual(days[0], d)


class VenuePages(unittest.TestCase):
    def setUp(self):
        today = datetime.now(EASTERN).date()
        self.d1, self.d2, self.d3 = today + timedelta(days=1), today + timedelta(days=8), today + timedelta(days=15)
        self.pages = {
            1: _page("Mighty Squirrel Brewing Co.", [
                _card("../events/weekly/tue/musical-bingo-tickets", "Musical Bingo", "Every Tuesday | 7:30 pm",
                      "Mighty Squirrel Brewing Co."),
                _card(f"../events/{_path(self.d1)}/taproom-trivia-tickets", "Taproom Trivia!",
                      "Tomorrow | 7:30 pm", "Mighty Squirrel Brewing Co."),
                _card(f"../events/{_path(self.d1)}/ciderfeast-tickets", "CiderFeast", "Tomorrow | 1 pm", "Cambridge Crossing"),
            ], next_page=2),
            2: _page("Mighty Squirrel Brewing Co.", [
                _card(f"../events/{_path(self.d2)}/taproom-trivia-tickets", "Taproom Trivia!",
                      "Tue | 7:30 pm", "Mighty Squirrel Brewing Co."),
                _card(f"../events/{_path(self.d3)}/taproom-trivia-tickets", "Taproom Trivia!",
                      "Tue | 7:30 pm", "Mighty Squirrel Brewing Co."),
            ]),
        }
        self.requested = []

        def get(url, **kw):
            self.requested.append(url)
            return _resp(self.pages.get(2 if "page=2" in url else 1 if "page=" not in url else 99, ""), 200)
        self.get = get

    def _scrape(self, price=None):
        lookups = []

        def fake_price(u, ua):
            lookups.append(u)
            return price
        with patch.object(S._SESSION, "get", side_effect=self.get), patch.object(S, "_do617_ticket_price", side_effect=fake_price):
            evs = S.scrape_mighty_squirrel_fenway("https://do617.com/venues/mighty-squirrel-brewing-co", "UA")
        return evs, lookups

    def test_follows_pages_and_stops_when_there_is_no_next_link(self):
        evs, _ = self._scrape()
        self.assertEqual(len(self.requested), 2)
        trivia = sorted(datetime.fromisoformat(e["date"]).astimezone(EASTERN).date() for e in evs if e["name"] == "Taproom Trivia!")
        self.assertEqual(trivia, [self.d1, self.d2, self.d3])

    def test_weekly_cards_become_the_next_four_weeks(self):
        evs, _ = self._scrape()
        bingo = [datetime.fromisoformat(e["date"]).astimezone(EASTERN) for e in evs if e["name"] == "Musical Bingo"]
        self.assertEqual(len(bingo), 4)
        self.assertTrue(all(b.weekday() == 1 and (b.hour, b.minute) == (19, 30) for b in bingo))

    def test_other_venues_cards_are_skipped_and_venue_is_the_location(self):
        evs, _ = self._scrape()
        self.assertNotIn("CiderFeast", {e["name"] for e in evs})
        self.assertEqual({e["venue"] for e in evs}, {"Mighty Squirrel Fenway"})

    def test_one_price_lookup_per_recurring_night(self):
        evs, lookups = self._scrape(price="Free")
        self.assertEqual(len(lookups), 2)  # trivia + bingo, not one per date
        self.assertTrue(all(e["price"] == "Free" for e in evs))


def _tm_event(name, day, time=None, seg="Music", genre="Rock"):
    start = {"localDate": day}
    if time:
        start["localTime"] = time
    return {"name": name, "dates": {"start": start}, "url": "https://tm.test/" + name.replace(" ", "-"),
            "_embedded": {"venues": [{"name": "Fenway Park"}]},
            "classifications": [{"segment": {"name": seg}, "genre": {"name": genre}}]}


class FenwayPark(unittest.TestCase):
    def _scrape(self, events, fn=None):
        resp = MagicMock()
        resp.json.return_value = {"_embedded": {"events": events}}
        with patch.object(S._SESSION, "get", return_value=resp):
            return (fn or S.scrape_fenway_park)("https://app.ticketmaster.com/discovery/v2/events.json?venueId=X", "UA")

    def test_concerts_and_the_game_but_not_red_sox_or_the_waitlist(self):
        day = (datetime.now(EASTERN) + timedelta(days=30)).date().isoformat()
        evs = self._scrape([
            _tm_event("The Game: Harvard-Yale 2026", day, "15:30:00", "Sports", "Football"),
            _tm_event("Boston Red Sox vs. Cincinnati Reds", day, None, "Sports", "Baseball"),
            _tm_event("Noah Kahan: The Last Of The Bugs World Tour", day, "18:00:00"),
            _tm_event("2027 PREMIUM SEASON TICKETS WAITLIST", day, None, "Music", "Other"),
        ])
        self.assertEqual(sorted(e["name"] for e in evs),
                         ["Noah Kahan: The Last Of The Bugs World Tour", "The Game: Harvard-Yale 2026"])

    def test_platinum_copy_only_when_there_is_no_regular_listing(self):
        day = (datetime.now(EASTERN) + timedelta(days=30)).date().isoformat()
        evs = self._scrape([
            _tm_event("Fall Out Boy: Twilight Of The Punks - Platinum Tickets", day, "17:00:00"),
            _tm_event("Fall Out Boy: Twilight Of The Punks", day, "17:30:00"),
            _tm_event("Slipknot: (sic)est Stadium Tour - Platinum Tickets", day, "17:30:00"),
        ], S.scrape_ticketmaster_discovery)
        by_name = {e["name"]: e for e in evs}
        self.assertEqual(set(by_name), {"Fall Out Boy: Twilight Of The Punks", "Slipknot: (sic)est Stadium Tour"})
        self.assertNotIn("Platinum", by_name["Fall Out Boy: Twilight Of The Punks"]["url"])
        self.assertEqual(datetime.fromisoformat(by_name["Fall Out Boy: Twilight Of The Punks"]["date"]).astimezone(EASTERN).hour, 17)
        self.assertEqual(datetime.fromisoformat(by_name["Fall Out Boy: Twilight Of The Punks"]["date"]).astimezone(EASTERN).minute, 30)


class Waitlists(unittest.TestCase):
    def test_season_ticket_waitlists_and_deposits_are_not_events(self):
        for t in ("2027 PREMIUM SEASON TICKETS WAITLIST", "Season Ticket Deposit - 2027", "Season seats wait-list",
                  "**CLOSED**"):  # Midway Cafe's Christmas Day
            self.assertTrue(S.is_placeholder_or_closed_event(t), t)

    def test_a_show_with_a_waitlist_is_still_a_show(self):
        for t in ("Sold Out: Comedy Night (join the waitlist)", "Waitlist Wednesdays Open Mic", "Platinum Blonde"):
            self.assertFalse(S.is_placeholder_or_closed_event(t), t)


class Places(unittest.TestCase):
    def _where(self, venue, name="Event", source="The Boston Calendar"):
        g = resolve_event_geo({"venue": venue, "name": name, "_source_venue": source})
        return g and (g["venue"], g["address"])

    def test_each_mighty_squirrel_taproom_is_its_own_place(self):
        for v in ("Mighty Squirrel Fenway", "Mighty Squirrel Taproom & Kitchen (Fenway)",
                  "Mighty Squirrel Brewing Co. – Fenway (Boston)"):
            self.assertEqual(self._where(v), ("Mighty Squirrel Fenway", "1 David Ortiz Dr, Boston"), v)
        for v in ("Mighty Squirrel Watertown", "Mighty Squirrel Arsenal Yards", "Mighty Squirrel Taproom & Kitchen, Watertown"):
            self.assertEqual(self._where(v)[0], "Mighty Squirrel Arsenal Yards", v)
        self.assertEqual(self._where("Mighty Squirrel Waltham")[0], "Mighty Squirrel Waltham")

    def test_unqualified_mighty_squirrel_is_not_guessed(self):
        self.assertIsNone(self._where("Mighty Squirrel Taproom & Kitchen", source="Meetup Boston"))

    def test_nightlife_venues(self):
        for v, place in (("Lucky's Lounge", "Lucky's Lounge"), ("Luckys Lounge", "Lucky's Lounge"),
                         ("City Tap House", "City Tap House"), ("White Bull Tavern", "White Bull Tavern"),
                         ("Caveau Boston", "Caveau"), ("Ned Devine's", "Ned Devine's"), ("Hong Kong", "Hong Kong"),
                         ("Urban Wild", "Urban Wild"), ("Hava Nightclub", "Hava Nightclub"),
                         ("Havana Club", "Havana Club")):
            self.assertEqual(self._where(v)[0], place, v)

    def test_no_short_needles(self):
        """#65 added "icon", "venu", "hava", "hong kong", "mighty squirrel" as substring rules:
        "Iconic", "venue", "Havana Club", a Harvard Square restaurant and a Waltham taproom
        would all have been placed at the wrong club."""
        self.assertNotEqual((self._where("Hong Kong Restaurant (Harvard Square)") or ("",))[0], "Hong Kong")
        self.assertNotEqual(self._where("Cactus Club Cafe")[0], "Club Café")
        for title in ("Urban Wildlife Walk", "Iconic Venue Tour", "Hong Kong Film Night", "Caveau-style wine tasting"):
            self.assertIsNone(self._where("", name=title, source="Eventbrite Boston"), title)


class Dedupe(unittest.TestCase):
    def test_same_title_at_two_located_bars_stays_two_events(self):
        """Castle Island's scraper gives no venue (the source name stands in), which let its
        Tuesday "Musical Bingo" swallow Mighty Squirrel Fenway's, 2.3 miles away."""
        import copy
        import template as T
        day = (datetime.now(EASTERN) + timedelta(days=7)).replace(hour=18, minute=30, second=0, microsecond=0)
        venues = [
            {"venue": "Castle Island Brewing", "url": "https://castleislandbeer.com/public-events", "error": None,
             "events": [{"name": "Musical Bingo", "date": day.isoformat(), "url": "https://castleislandbeer.com/calendar/mb"}]},
            {"venue": "Mighty Squirrel Fenway", "url": "https://do617.com/venues/mighty-squirrel-brewing-co", "error": None,
             "events": [{"name": "Musical Bingo", "date": (day + timedelta(hours=1)).isoformat(), "venue": "Mighty Squirrel Fenway",
                         "url": "https://do617.com/events/weekly/tue/musical-bingo-tickets"}]},
        ]
        dated, _, _ = T.group_by_date(copy.deepcopy(venues))
        got = sorted((e["venue"], e["_source_venue"]) for _, evs in dated for e in evs)
        self.assertEqual(got, [("Castle Island Brewing", "Castle Island Brewing"),
                               ("Mighty Squirrel Fenway", "Mighty Squirrel Fenway")])


class Sources(unittest.TestCase):
    def test_registered(self):
        by_name = {v["name"]: v for v in S._ALL_VENUES}
        self.assertIs(by_name["Fenway Park"]["scraper"], S.scrape_fenway_park)
        self.assertIs(by_name["Mighty Squirrel Fenway"]["scraper"], S.scrape_mighty_squirrel_fenway)
        for name, slug in (("Hava Nightclub", "hava-nightclub"), ("Urban Wild", "urban-wild")):
            self.assertIs(by_name[name]["scraper"], S.scrape_do617, name)
            self.assertEqual(by_name[name]["url"], f"https://do617.com/venues/{slug}")


class Do617DirectTickets(unittest.TestCase):
    def test_clean_ticket_url_unpacks_redirects_and_filters_noise(self):
        clean = S._do617_clean_ticket_url
        tm = "https://ticketmaster.evyy.net/c/253185/264167/4272?SharedId=DoStuff&u=https%3A%2F%2Fwww.ticketmaster.com%2Fevent%2F010064D10F38B5FD"
        self.assertEqual(clean(tm), "https://www.ticketmaster.com/event/010064D10F38B5FD")

        eb = "https://r.do617.com/aff?url=https%3A%2F%2Fwww.eventbrite.com%2Fe%2Fshow-tickets-12345"
        self.assertEqual(clean(eb), "https://www.eventbrite.com/e/show-tickets-12345")

        axs = "https://www.axs.com/events/1510070/the-bad-plus-tickets?cid=usaffdostuff"
        self.assertEqual(clean(axs), axs)

        self.assertIsNone(clean("https://domorestuff.com/?city=boston"))
        self.assertIsNone(clean("https://do617.com/events/2026/11/11/show"))
        self.assertIsNone(clean("https://twitter.com/intent/tweet"))

    def test_fill_prices_replaces_do617_url_with_primary_ticket(self):
        events = [
            {"name": "Big Concert", "date": "2026-11-12T00:00:00+00:00",
             "url": "https://do617.com/events/2026/11/12/big-concert-tickets", "price": None},
            {"name": "No Ticket Link", "date": "2026-11-12T00:00:00+00:00",
             "url": "https://do617.com/events/2026/11/12/no-link-tickets", "price": None},
        ]
        html_concert = """<html><body>
            <section class="ticket-section">
                <h2>Tickets: $25 - $40</h2>
                <a href="https://ticketmaster.evyy.net/c/1/2/3?u=https%3A%2F%2Fwww.ticketmaster.com%2Fevent%2F123">Find tickets</a>
            </section>
        </body></html>"""
        html_nolink = """<html><body>
            <section class="ticket-section">
                <h2>Tickets: Free</h2>
            </section>
        </body></html>"""

        def mock_get(url, **kw):
            content = html_concert if "big-concert" in url else html_nolink
            resp = MagicMock(status_code=200, content=content.encode("utf-8"))
            return resp

        with patch.object(S, "_SESSION") as session:
            session.get.side_effect = mock_get
            res = S._do617_fill_prices(events, "ua")

        by_name = {e["name"]: e for e in res}
        self.assertEqual(by_name["Big Concert"]["url"], "https://www.ticketmaster.com/event/123")
        self.assertEqual(by_name["Big Concert"]["price"], "$25 - $40")
        self.assertEqual(by_name["No Ticket Link"]["url"], "https://do617.com/events/2026/11/12/no-link-tickets")
        self.assertEqual(by_name["No Ticket Link"]["price"], "Free")


if __name__ == "__main__":
    unittest.main()
