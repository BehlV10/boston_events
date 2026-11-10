"""Club venues found through Resident Advisor's Boston listings, read from their own feeds:
bsmnt (its site's Posh group feed) and Spy Bar (its Wix Events calendar)."""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402
from scrapers import EASTERN  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402


def _posh(name, start_utc, local_wall, slug, **kw):
    ev = {"name": name, "start": local_wall, "startUtc": start_utc, "end": local_wall, "endUtc": start_utc,
          "url": slug, "status": "live", "passwordProtected": False, "isPersonalEvent": False,
          "displayOnThirdPartySites": True, "timezone": "America/New_York",
          "venue": {"name": "bsmnt", "address": "100 Stuart St, Boston, MA 02116, USA"}}
    ev.update(kw)
    return ev


class PoshGroupFeed(unittest.TestCase):
    def _scrape(self, events):
        resp = MagicMock()
        resp.json.return_value = {"group": {"name": "bsmnt"}, "events": events}
        with patch.object(S._SESSION, "get", return_value=resp) as get:
            evs = S.scrape_bsmnt("https://posh.vip/api/web/v2/util/group_url/bsmntboston", "UA")
        self.assertEqual(get.call_count, 1)  # one request: no per-night page fetches
        return evs

    def test_uses_the_real_utc_start_not_the_local_wall_time_marked_z(self):
        """Posh's "start" is 22:00 local written as "22:00Z"; read naively it lands at 5 pm."""
        d = (datetime.now(EASTERN) + timedelta(days=3)).replace(hour=22, minute=0, second=0, microsecond=0)
        utc = d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        wall = d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        evs = self._scrape([_posh("benwal", utc, wall, "benwal")])
        got = datetime.fromisoformat(evs[0]["date"]).astimezone(EASTERN)
        self.assertEqual((got.date(), got.hour), (d.date(), 22))
        self.assertEqual(evs[0]["url"], "https://posh.vip/e/benwal")
        self.assertEqual(evs[0]["venue"], "bsmnt")
        self.assertIsNone(evs[0]["price"])  # Posh says $0 (guest list before 11); not shown as free

    def test_only_live_public_upcoming_nights(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        past = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        evs = self._scrape([
            _posh("public", soon, soon, "a"),
            _posh("last month", past, past, "b"),
            _posh("draft", soon, soon, "c", status="draft"),
            _posh("password", soon, soon, "d", passwordProtected=True),
            _posh("not for other sites", soon, soon, "e", displayOnThirdPartySites=False),
            _posh("someone's birthday", soon, soon, "f", isPersonalEvent=True),
        ])
        self.assertEqual([e["name"] for e in evs], ["public"])


class SpyBar(unittest.TestCase):
    def test_its_own_wix_calendar(self):
        with patch.object(S, "scrape_wix_events", return_value=[]) as wix:
            S.scrape_spy_bar("https://www.spybar.com/event-list", "UA")
        wix.assert_called_once_with("https://www.spybar.com/event-list", "UA", default_venue="Spy Bar",
                                    default_category="clubbing")


class Registered(unittest.TestCase):
    def test_sources(self):
        by_name = {v["name"]: v for v in S._ALL_VENUES}
        self.assertIs(by_name["bsmnt"]["scraper"], S.scrape_bsmnt)
        self.assertIn("posh.vip/api/web/v2/util/group_url/bsmntboston", by_name["bsmnt"]["url"])
        self.assertIs(by_name["Spy Bar"]["scraper"], S.scrape_spy_bar)
        # The only ra.co source is the GraphQL one (test_resident_advisor); clubs with their own
        # feeds are read from those, not from RA.
        ra = [v["name"] for v in S._ALL_VENUES if "ra.co" in v["url"]]
        self.assertEqual(ra, ["Resident Advisor Boston"])
        self.assertIs(by_name["Resident Advisor Boston"]["scraper"], S.scrape_resident_advisor)

    def test_places(self):
        for venue, place, addr in (("bsmnt", "bsmnt", "100 Stuart St, Boston"),
                                   ("Spy Bar", "Spy Bar", "40 Berkeley St, Boston"),
                                   ("Spy Bar, Boston", "Spy Bar", "40 Berkeley St, Boston")):
            g = resolve_event_geo({"venue": venue, "name": "Night", "_source_venue": "x"})
            self.assertEqual((g["venue"], g["address"]), (place, addr), venue)
        self.assertIsNone(resolve_event_geo({"venue": "", "name": "Spy Pond loop walk", "_source_venue": "Meetup Boston"}))


if __name__ == "__main__":
    unittest.main()
