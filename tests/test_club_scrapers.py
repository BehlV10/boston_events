"""Club sources: Bijou (via its Posh pages), Sissy K's (Wix Events), the 6one7 and Dope
Eventbrite organizers, two Partiful links, and places for the clubs."""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402
from scrapers import EASTERN  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402


def _posh_page(name, start, price=22.12, url="https://posh.vip/e/x"):
    """A posh.vip page as served: the JSON-LD is a string pushed into the Next.js payload."""
    ld = {"@context": "https://schema.org", "@type": "Event", "name": name, "startDate": start,
          "url": url, "location": {"@type": "Place", "name": "Bijou Nightclub & Lounge"},
          "offers": {"@type": "Offer", "url": url, "price": price, "priceCurrency": "USD"}}
    pushed = json.dumps(json.dumps(ld, indent=2))[1:-1]
    return ('<html><script>self.__next_f.push([1,"0:{\\"P\\":null}"])</script>'
            f'<script>self.__next_f.push([1,"51:T82b,"])</script><script>self.__next_f.push([1,"{pushed}"])</script></html>')


def _resp(text, url):
    r = MagicMock()
    r.status_code, r.text, r.url = 200, text, url
    return r


class Posh(unittest.TestCase):
    def test_reads_the_event_from_the_nextjs_payload(self):
        e = S._posh_event(_posh_page("Jamback", "2026-12-11T22:00:00-05:00", url="https://posh.vip/e/jamback-1"),
                          "https://posh.vip/e/jamback-1")
        self.assertEqual(e["name"], "Jamback")
        self.assertEqual(e["date"], "2026-12-12T03:00:00+00:00")
        self.assertEqual(e["url"], "https://posh.vip/e/jamback-1")
        self.assertTrue(e["price"].startswith("$22"))

    def test_page_without_an_event(self):
        self.assertIsNone(S._posh_event("<html>nothing</html>", "https://posh.vip/e/x"))


class Bijou(unittest.TestCase):
    def test_real_times_and_prices_from_each_posh_page(self):
        """#65 listed every Bijou night at 10 pm for "$20–$40"; CNRY's REPLAY is a 3 pm day party."""
        d = (datetime.now(EASTERN) + timedelta(days=4)).date()
        past = (datetime.now(EASTERN) - timedelta(days=3)).date()
        site = BeautifulSoup(
            '<a href="https://posh.vip/e/replay?t=bijou">REPLAY</a><a href="https://posh.vip/f/e440f">Jamback</a>'
            '<a href="https://posh.vip/f/e440f">again</a><a href="https://posh.vip/f/old">old</a>'
            '<a href="/private-events">Private events</a>', "html.parser")
        pages = {
            "https://posh.vip/e/replay?t=bijou": ("https://posh.vip/e/replay", _posh_page("CNRY PRESENTS: REPLAY", f"{d}T15:00:00-05:00", 30, "https://posh.vip/e/replay")),
            "https://posh.vip/f/e440f": ("https://posh.vip/e/jamback-1", _posh_page("Jamback", f"{d}T22:00:00-05:00", 22.12, "https://posh.vip/e/jamback-1")),
            "https://posh.vip/f/old": ("https://posh.vip/e/old", _posh_page("Last Week", f"{past}T22:00:00-05:00", 20, "https://posh.vip/e/old")),
        }
        requested = []

        def get(url, **kw):
            requested.append(url)
            final, html = pages[url]
            return _resp(html, final)
        with patch.object(S, "fetch_soup", return_value=site), patch.object(S._SESSION, "get", side_effect=get):
            evs = S.scrape_bijou("https://www.bijouboston.com", "UA")
        self.assertEqual(len(requested), 3)  # each Posh link once; the private-events page is not a show
        by_name = {e["name"]: e for e in evs}
        self.assertEqual(set(by_name), {"CNRY PRESENTS: REPLAY", "Jamback"})
        self.assertEqual(datetime.fromisoformat(by_name["CNRY PRESENTS: REPLAY"]["date"]).astimezone(EASTERN).hour, 15)
        self.assertEqual(by_name["CNRY PRESENTS: REPLAY"]["price"], "$30")
        self.assertTrue(all(e["venue"] == "Bijou Nightclub" and e["category"] == "clubbing" for e in evs))


class SissyKs(unittest.TestCase):
    def test_uses_the_wix_events_reader_with_its_own_name(self):
        with patch.object(S, "scrape_wix_events", return_value=[]) as wix:
            S.scrape_sissy_ks("https://www.sissykevents.com/", "UA")
        wix.assert_called_once_with("https://www.sissykevents.com/", "UA", default_venue="Sissy K's", default_category="clubbing")


class Sources(unittest.TestCase):
    def test_registered(self):
        by_name = {v["name"]: v for v in S._ALL_VENUES}
        self.assertIs(by_name["Bijou Nightclub"]["scraper"], S.scrape_bijou)
        self.assertIs(by_name["Sissy K's"]["scraper"], S.scrape_sissy_ks)
        for org in ("6one7 Productions (Venu & Icon)", "Dope Entertainment (Venu, Icon, Clerys)"):
            self.assertIs(by_name[org]["scraper"], S.scrape_eventbrite_org)
            self.assertIn("eventbrite.com/o/", by_name[org]["url"])

    def test_partiful_links(self):
        with open(S.PARTIFUL_SOURCES_FILE) as f:
            links = json.load(f)
        self.assertIn("https://partiful.com/u/w95OjAZPEGDsSylMEd3O", links)
        self.assertEqual(len(links), len(set(links)))


class Places(unittest.TestCase):
    def test_clubs(self):
        for venue, place, addr in (
                ("Bijou Nightclub", "Bijou Nightclub", "51 Stuart St, Boston"),
                ("Bijou Nightclub & Lounge", "Bijou Nightclub", "51 Stuart St, Boston"),
                ("Sissy K's", "Sissy K's", "6 Commercial St, Boston"),
                ("ICON Nightclub", "Icon Nightclub", "100 Warrenton St, Boston"),
                ("Venu Nightclub", "Venu Nightclub", "100 Warrenton St, Boston"),
                ("Clerys", "Clerys", "113 Dartmouth St, Boston"),
                ("Scorpion Boston", "Scorpion Bar", "58 Seaport Blvd, Boston"),
                ("W Boston", "W Boston", "100 Stuart St, Boston"),
                ("Tuck's Arcadium, 36 John F. Kennedy St, Cambridge, MA 02138", "Tuck's Arcadium",
                 "36 John F. Kennedy St, Cambridge")):
            g = resolve_event_geo({"venue": venue, "name": "Night", "_source_venue": "x"})
            self.assertEqual((g["venue"], g["address"]), (place, addr), venue)

    def test_no_bare_icon_or_venu(self):
        for title in ("Iconic Boston Tour", "Venue TBA", "Bijou-inspired jewelry workshop"):
            self.assertIsNone(resolve_event_geo({"venue": "", "name": title, "_source_venue": "Eventbrite Boston"}), title)


if __name__ == "__main__":
    unittest.main()
