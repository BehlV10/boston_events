"""Comicazi (Google Calendar), All She Wrote Books (Wix Events) and Boston Center for the Arts
(bostonarts.org/experiences cards), parsed from saved-shape fixtures so CI never calls the sites."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers as S  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402


def _future(days, hour, minute=0):
    d = (datetime.now(S.EASTERN) + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return d


def _ical_event(name, start):
    return {"name": name, "date": start.astimezone(timezone.utc).isoformat(), "url": "x", "venue": None,
            "location": "", "price": None, "description": None}


class ComicaziTest(unittest.TestCase):
    def test_keeps_events_drops_store_notices(self):
        feed = [_ical_event("Board Game Night - $3", _future(2, 18, 30)),
                _ical_event("Manga Book Club - Now in person!", _future(3, 19)),
                _ical_event("Comic Book Club - Downstairs", _future(4, 19, 30)),
                _ical_event("CLOSED", _future(5, 0)),
                _ical_event("50% Off - Premium Back Issue Sale!", _future(6, 0)),
                _ical_event("EARLY CLOSE AT 7PM - STAFF MEETING", _future(7, 0)),
                _ical_event("Private Event", _future(8, 18))]
        with patch.object(S, "scrape_ical", return_value=feed):
            got = S.scrape_comicazi("https://www.comicazi.com/events", S.UA_CHROME)
        self.assertEqual([(e["name"], e["price"], e["category"]) for e in got], [
            ("Board Game Night", "$3", "gaming"), ("Manga Book Club", None, "books"), ("Comic Book Club", None, "books")])
        self.assertTrue(all(e["venue"] == "Comicazi" and e["url"] == "https://www.comicazi.com/events" for e in got))
        self.assertEqual(resolve_event_geo(got[0])["neighborhood"], "Davis Square")


def _wix_page(items):
    data = {"appsWarmupData": {"140603ad": {"widget1": {"events": {"events": items}}}}}
    return f'<html><script type="application/json" id="wix-warmup-data">{json.dumps(data)}</script></html>'


def _wix_item(title, start, loc_name, reg, slug="e"):
    return {"title": title, "slug": slug, "status": 1,
            "scheduling": {"config": {"startDate": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")}},
            "location": {"name": loc_name, "address": "somewhere"}, "registration": reg, "description": "About it"}


class AllSheWroteTest(unittest.TestCase):
    def test_each_event_keeps_its_own_venue_and_price(self):
        items = [
            _wix_item("Queer Silent Book Club", _future(2, 10, 30), "All She Wrote Books",
                      {"type": 1, "ticketing": {"soldOut": True}}, slug="qsbc"),
            _wix_item("Dani's Queer Bar x All She Wrote Books Book Club", _future(3, 19), "Dani's Queer Bar",
                      {"type": 2, "ticketing": {"lowestTicketPriceFormatted": "$7.18",
                                                "highestTicketPriceFormatted": "$21.77"}}),
            _wix_item("An Evening with TJ Klune", _future(4, 19), "Museum of Science",
                      {"type": 3, "external": {"registration": "https://www.mos.org/events/klune"}}),
            _wix_item("Long gone", _future(-3, 19), "All She Wrote Books", {"type": 4}),
        ]
        resp = MagicMock(status_code=200, text=_wix_page(items))
        with patch.object(S._SESSION, "get", return_value=resp):
            got = S.scrape_all_she_wrote("https://www.allshewrotebooks.com/events", S.UA_CHROME)
        self.assertEqual([(e["venue"], e["price"]) for e in got], [
            ("All She Wrote Books", None), ("Dani's Queer Bar", "$7.18–$21.77"), ("Museum of Science", None)])
        self.assertEqual(got[0]["url"], "https://www.allshewrotebooks.com/event-details/qsbc")
        self.assertEqual(got[2]["url"], "https://www.mos.org/events/klune")
        self.assertEqual(resolve_event_geo(got[0])["address"], "75 Washington St, Somerville")
        self.assertEqual(resolve_event_geo(got[1])["address"], "909 Boylston St, Boston")


def _card(kind, title, lines, href):
    p = "<br />".join(lines)
    return (f'<article class="card-event"><a href="{href}"><div class="card-event--text"><h4>{kind}</h4>'
            f'<h5>{" ".join(f"<span>{w}</span>" for w in title.split())}</h5><p>{p}<br /></p></div></a></article>')


class BostonCenterForTheArtsTest(unittest.TestCase):
    def test_timed_cards_and_short_runs_only(self):
        d1, run_start = _future(10, 0), _future(3, 0)
        mdY = lambda d: d.strftime("%m/%d/%Y")  # noqa: E731
        listing = "".join([
            _card("Public Programs, Exhibitions", "Beyond Witnessing: An Artists' Roundtable",
                  ["Shima Taj Bakhsh", mdY(d1), "6pm", "BCA Mills Gallery"], "https://bostonarts.org/event/bw/"),
            _card("Events", "A Creative Space Summit", [mdY(d1), "9:30am-4pm", "The BCA Cyclorama"],
                  "https://bostonarts.org/event/summit/"),
            _card("Boston Art Book Fair", "Boston Art Book Fair 2026",
                  [f"{mdY(run_start)} - {mdY(run_start + timedelta(days=2))}", "The BCA Cyclorama"],
                  "https://bostonarts.org/event/fair/"),
            _card("Dance", "The Head is not the Star of the Body",
                  ["Cassie Wang", f"{mdY(run_start)} - {mdY(run_start + timedelta(days=5))}", "Calderwood Pavilion"],
                  "https://bostonarts.org/event/head/"),
            _card("Exhibitions", "Soft Collapse", ["Shima Taj Bakhsh", f"{mdY(_future(-40, 0))} - {mdY(_future(40, 0))}",
                                                   "BCA Mills Gallery"], "https://bostonarts.org/event/soft/"),
        ])
        day = run_start.strftime("%A, %B %-d")
        pages = {
            "https://bostonarts.org/experiences/": listing,
            "https://bostonarts.org/event/fair/": "<p>Saturday-Sunday: Open to the public (Free admission)</p>",
            "https://bostonarts.org/event/head/": f"<p>Join us for a preview run, {day}th from 7-9 PM, Martin Hall</p>",
        }
        with patch.object(S, "fetch_soup", side_effect=lambda u, ua: BeautifulSoup(pages[u], "html.parser")):
            got = S.scrape_boston_center_for_the_arts("https://bostonarts.org/experiences/", S.UA_CHROME)
        by_name = {e["name"]: e for e in got}
        self.assertEqual(sorted(by_name), ["A Creative Space Summit", "Beyond Witnessing: An Artists' Roundtable",
                                           "The Head is not the Star of the Body"])
        local = lambda e: datetime.fromisoformat(e["date"]).astimezone(S.EASTERN)  # noqa: E731
        self.assertEqual(local(by_name["Beyond Witnessing: An Artists' Roundtable"]).strftime("%H:%M"), "18:00")
        self.assertEqual(local(by_name["A Creative Space Summit"]).strftime("%H:%M"), "09:30")
        head = by_name["The Head is not the Star of the Body"]
        self.assertEqual((local(head).date(), local(head).hour), (run_start.date(), 19))
        self.assertEqual((head["venue"], head["category"]), ("Calderwood Pavilion", "dance"))
        self.assertEqual(resolve_event_geo(by_name["Beyond Witnessing: An Artists' Roundtable"])["venue"],
                         "BCA Mills Gallery")


if __name__ == "__main__":
    unittest.main()
