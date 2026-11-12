"""Tests for Broadway & Theater scrapers (Emerson Colonial, Broadway in Boston, Calderwood / BCA Plaza)
and Weekend Bazaars / Community Meetups (Arsenal Holiday Bazaar, Arlington Greek Fest, Special Interest Social)."""
import unittest
from unittest import mock
import json

import scrapers as S
from venues_geo import resolve_event_geo


class EmersonColonialTest(unittest.TestCase):
    def test_emerson_colonial_geo_resolves(self):
        geo = resolve_event_geo({"venue": "Emerson Colonial Theatre", "name": "Hadestown"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Emerson Colonial Theatre")
        self.assertEqual(geo["neighborhood"], "Theater District")
        self.assertIn("106 Boylston St", geo["address"])

    def test_scrape_emerson_colonial(self):
        whats_on_html = """
        <html><body>
          <a href="/events/hadestown/emerson-colonial-theatre/">Hadestown</a>
          <a href="/events/dirty-dancing/emerson-colonial-theatre/">Dirty Dancing</a>
        </body></html>
        """
        hadestown_data = {
            "@context": "https://schema.org",
            "@type": "TheaterEvent",
            "name": "Hadestown",
            "description": "Winner of eight Tony Awards.",
            "url": "https://us.atgtickets.com/events/hadestown/emerson-colonial-theatre/",
            "subEvent": [
                {
                    "@type": "TheaterEvent",
                    "name": "Hadestown",
                    "startDate": "2026-11-13T00:30:00.000Z",
                    "offers": {
                        "url": "https://us.atgtickets.com/events/hadestown/emerson-colonial-theatre/tickets/1/",
                        "availability": "https://schema.org/InStock"
                    }
                },
                {
                    "@type": "TheaterEvent",
                    "name": "Hadestown",
                    "startDate": "2026-11-14T01:00:00.000Z",
                    "offers": {
                        "url": "https://us.atgtickets.com/events/hadestown/emerson-colonial-theatre/tickets/2/",
                        "availability": "https://schema.org/InStock"
                    }
                }
            ]
        }
        hadestown_html = f"""
        <html><head>
          <script type="application/ld+json">{json.dumps(hadestown_data)}</script>
        </head><body>Hadestown Page</body></html>
        """

        with mock.patch.object(S, "_SESSION") as session:
            def _get(url, **kwargs):
                resp = mock.Mock(status_code=200)
                if "whats-on" in url:
                    resp.text = whats_on_html
                elif "hadestown" in url:
                    resp.text = hadestown_html
                else:
                    resp.text = "<html><body></body></html>"
                return resp

            session.get.side_effect = _get
            events = S.scrape_emerson_colonial("https://us.atgtickets.com/venues/emerson-colonial-theatre/whats-on/", "ua")

        self.assertGreaterEqual(len(events), 2)
        show = events[0]
        self.assertEqual(show["name"], "Hadestown")
        self.assertEqual(show["venue"], "Emerson Colonial Theatre")
        self.assertEqual(show["category"], "theater")
        self.assertIn("atgtickets.com", show["url"])


class BroadwayInBostonTest(unittest.TestCase):
    def test_broadway_in_boston_geo_resolves(self):
        geo = resolve_event_geo({"venue": "Citizens Bank Opera House", "name": "Wicked"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Citizens Bank Opera House")
        self.assertEqual(geo["neighborhood"], "Downtown Crossing")
        self.assertIn("539 Washington St", geo["address"])

        alias_geo = resolve_event_geo({"venue": "Broadway In Boston", "name": "Wicked"})
        self.assertIsNotNone(alias_geo)
        self.assertEqual(alias_geo["venue"], "Citizens Bank Opera House")

    def test_scrape_broadway_in_boston(self):
        shows_index_html = """
        <html><body>
          <a href="/shows/wicked-2/">Wicked</a>
        </body></html>
        """
        wicked_html = """
        <html><body>
          <h1>Wicked</h1>
          <div class="engagement-detail-info">Citizens Opera House 539 Washington Street</div>
          <div class="content-slider--performances">
            <div class="performance-card">
              Thu | Nov 12 | <a href="http://www.ticketmaster.com/event/1">7:30pm</a>
            </div>
            <div class="performance-card">
              Fri | Nov 13 | <a href="http://www.ticketmaster.com/event/2">8:00pm</a>
            </div>
            <div class="performance-card">
              Sat | Nov 14 | <a href="http://www.ticketmaster.com/event/3">2:00pm</a> <a href="http://www.ticketmaster.com/event/4">8:00pm</a>
            </div>
          </div>
        </body></html>
        """

        with mock.patch.object(S, "_SESSION") as session:
            def _get(url, **kwargs):
                resp = mock.Mock(status_code=200)
                if url.endswith("/shows/"):
                    resp.text = shows_index_html
                elif "wicked" in url:
                    resp.text = wicked_html
                else:
                    resp.text = "<html><body></body></html>"
                return resp

            session.get.side_effect = _get
            events = S.scrape_broadway_in_boston("https://boston.broadway.com/shows/", "ua")

        self.assertEqual(len(events), 4)
        for e in events:
            self.assertEqual(e["name"], "Wicked")
            self.assertEqual(e["venue"], "Citizens Bank Opera House")
            self.assertEqual(e["category"], "theater")
            self.assertIn("ticketmaster.com", e["url"])


class SpecialInterestSocialTest(unittest.TestCase):
    def test_special_interest_social_geo_resolves(self):
        geo = resolve_event_geo({"venue": "Special Interest Social", "name": "Neurodivergent Happy Hour"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["venue"], "Special Interest Social")
        self.assertEqual(geo["neighborhood"], "Harvard Square")

    def test_scrape_special_interest_social(self):
        profile_json = {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "itemListElement": [
                {"@type": "ListItem", "url": "https://partiful.com/e/testevent123"}
            ]
        }
        profile_html = f"""<html><head><script type="application/ld+json">{json.dumps(profile_json)}</script></head><body></body></html>"""

        event_json = {
            "@context": "https://schema.org",
            "@type": "Event",
            "name": "Neurodivergent Happy Hour",
            "startDate": "2026-11-13T23:00:00.000Z",
            "location": {
                "@type": "Place",
                "name": "Tuck's Arcadium, 36 John F. Kennedy St, Cambridge, MA 02138"
            },
            "offers": {"price": 0},
            "description": "Sensory-friendly meetup for neurodivergent adults."
        }
        event_html = f"""<html><head><script type="application/ld+json">{json.dumps(event_json)}</script></head><body></body></html>"""

        with mock.patch.object(S, "_SESSION") as session:
            def _get(url, **kwargs):
                resp = mock.Mock(status_code=200)
                if "testevent" in url:
                    resp.text = event_html
                else:
                    resp.text = profile_html
                return resp

            session.get.side_effect = _get
            events = S.scrape_special_interest_social("https://specialinterestsocial.com/", "ua")

        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev["name"], "Neurodivergent Happy Hour")
        self.assertEqual(ev["venue"], "Tuck's Arcadium")
        self.assertEqual(ev["price"], "Free")
        self.assertEqual(ev["category"], "community")
        self.assertEqual(ev["url"], "https://partiful.com/e/testevent123")


class WeekendBazaarsAndFallFestTest(unittest.TestCase):
    def test_arlington_greek_fall_fest(self):
        geo = resolve_event_geo({"venue": "Saint Athanasius the Great Greek Orthodox Church", "name": "Greek Cuisine Fall Fest"})
        self.assertIsNotNone(geo)
        self.assertEqual(geo["neighborhood"], "Arlington")
        self.assertIn("4 Appleton St", geo["address"])

        events = S.scrape_arlington_greek_fall_fest("https://www.saintathanasius.org/news/greek-festival/", "ua")
        self.assertEqual(len(events), 3)
        for e in events:
            self.assertEqual(e["name"], "Greek Cuisine Fall Fest 2026")
            self.assertEqual(e["venue"], "Saint Athanasius the Great Greek Orthodox Church")
            self.assertEqual(e["price"], "Free")

    def test_arsenal_holiday_bazaar(self):
        events = S.scrape_arsenal_holiday_bazaar("https://www.arsenalyards.com/events/", "ua")
        self.assertEqual(len(events), 2)
        for e in events:
            self.assertEqual(e["name"], "The Arsenal Holiday Bazaar")
            self.assertEqual(e["venue"], "Arsenal Yards")
            self.assertEqual(e["price"], "Free")

    def test_thanksgiving_market_harbor_fest(self):
        events = S.scrape_thanksgiving_market_harbor_fest("https://bostonpublicmarket.org/", "ua")
        self.assertEqual(len(events), 3)
        for e in events:
            self.assertEqual(e["name"], "Boston Thanksgiving Market & Harbor Festival")
            self.assertEqual(e["venue"], "Christopher Columbus Waterfront Park")
            self.assertEqual(e["price"], "Free")


class BostonJewishFilmFestivalTest(unittest.TestCase):
    def test_jewish_film_festival_geo_resolves(self):
        geo_jcc = resolve_event_geo({"venue": "JCC Riemer-Goldstein Theater", "name": "The Wedding Entertainer"})
        self.assertIsNotNone(geo_jcc)
        self.assertEqual(geo_jcc["venue"], "JCC Greater Boston")
        self.assertEqual(geo_jcc["neighborhood"], "Newton")

        geo_wnc = resolve_event_geo({"venue": "West Newton Cinema", "name": "I Had The Heart"})
        self.assertIsNotNone(geo_wnc)
        self.assertEqual(geo_wnc["venue"], "West Newton Cinema")
        self.assertEqual(geo_wnc["neighborhood"], "West Newton")

        geo_st = resolve_event_geo({"venue": "Somerville Theatre", "name": "Ethan Bloom"})
        self.assertIsNotNone(geo_st)
        self.assertEqual(geo_st["venue"], "Somerville Theatre")
        self.assertEqual(geo_st["neighborhood"], "Davis Square")

    def test_scrape_boston_jewish_film_festival(self):
        popup_html = """
        <html><body>
          <div class="pum-content">
            Ethan Bloom
            Sunday, November 15 | 7pm | Somerville Theatre
            Director: Herschel Faber
            Narrative, 2025, US, 96 min
            <a href="https://ticketing.bostonjfilm.org/websales/pages/info.aspx?evtinfo=580334">Buy Tickets</a>
          </div>
          <div class="pum-content">
            The Wedding Entertainer (The Tale of Moishe Badhan)
            Saturday, November 14 | 7pm | JCC Riemer-Goldstein Theater
            Director: Gidi Dar
            <a href="https://ticketing.bostonjfilm.org/websales/pages/info.aspx?evtinfo=580335">Buy Tickets</a>
          </div>
        </body></html>
        """
        with mock.patch.object(S, "_SESSION") as session:
            resp = mock.Mock(status_code=200, text=popup_html)
            session.get.return_value = resp
            events = S.scrape_boston_jewish_film_festival("https://www.bostonjcc.org/program/boston-jewish-film-festival/", "ua")

        self.assertEqual(len(events), 2)
        ethan = events[0]
        self.assertEqual(ethan["name"], "Boston Jewish Film Festival: Ethan Bloom")
        self.assertEqual(ethan["venue"], "Somerville Theatre")
        self.assertEqual(ethan["category"], "film")
        self.assertIn("ticketing.bostonjfilm.org", ethan["url"])


class DearAnnieAndRebelRebelTest(unittest.TestCase):
    def test_dear_annie_and_rebel_rebel_geo_resolves(self):
        geo_da = resolve_event_geo({"venue": "Dear Annie", "name": "Unruly Maker's Market"})
        self.assertIsNotNone(geo_da)
        self.assertEqual(geo_da["venue"], "Dear Annie")
        self.assertEqual(geo_da["neighborhood"], "Porter Square")
        self.assertIn("1741 Massachusetts Ave", geo_da["address"])

        geo_rr = resolve_event_geo({"venue": "Rebel Rebel", "name": "Natural Wine Tasting"})
        self.assertIsNotNone(geo_rr)
        self.assertEqual(geo_rr["venue"], "Rebel Rebel")
        self.assertEqual(geo_rr["neighborhood"], "Union Square")

        geo_wc = resolve_event_geo({"venue": "Wild Child", "name": "The Big Beaujolais Tasting"})
        self.assertIsNotNone(geo_wc)
        self.assertEqual(geo_wc["venue"], "Wild Child")
        self.assertEqual(geo_wc["neighborhood"], "Union Square")


if __name__ == "__main__":
    unittest.main()

