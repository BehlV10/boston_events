"""Markets & Festivals category, its hub page and the sources added for it.

Run via:
  python -m unittest discover -s tests
"""

import datetime as _dt
import html
import json
import os
import re
import sys
import unittest
from unittest import mock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import scrapers  # noqa: E402
import template  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402

_EST = _dt.timezone(_dt.timedelta(hours=-5))
NOW = _dt.datetime(2026, 11, 5, 12, 0, tzinfo=_EST)


class _Frozen(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        n = NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
        return cls.combine(n.date(), n.timetz() if tz else n.time())


def _frozen_clock():
    return mock.patch.object(scrapers, "datetime", _Frozen)


def _resp(text="", status=200, payload=None):
    r = mock.Mock(status_code=status, text=text)
    r.json.return_value = payload if payload is not None else {}
    return r


class MarketFestivalClassifierTest(unittest.TestCase):
    def test_markets_fairs_and_festivals_are_recognized(self):
        for title in (
            "Somerville Flea", "Loy Krathong Thai Night Market", "SoWa Vintage Market",
            "The Holiday Market at Snowport 2026", "Haymarket Open-Air Produce Market",
            "Copley Square Farmers Market", "Somerville Winter Farmers Market",
            "Harvard Square Holiday Fair", "The Arsenal Holiday Bazaar", "Bow Market Renaissance Faire",
            "Boston Halal Food Fest", "Lantern Festival", "Oktoberfest Harvard Square",
            "Holiday Pop-Up Shop at Bow Market", "Pop Up Market at The Anchor", "Snowport",
            "Annual Tree Lighting at Faneuil Hall", "Brews and Botanicals Exotic Plant Show",
        ):
            self.assertTrue(scrapers.is_market_or_festival(title), title)

    def test_job_fairs_film_fests_and_shows_are_not(self):
        for title in (
            "Career Fair 2026", "Graduate School Fair", "Acera School STEM Festival and Open House",
            "Hump! Film Fest - Fall Season 2026", "Castle Hill Art Show & Sale",
            "Dog-Friendly Holiday Pop-up Bar", "Market Basket Run Club", "Stock market talk",
            "Jazz Night", "Call for Vendors: Holiday Market",
        ):
            self.assertFalse(scrapers.is_market_or_festival(title), title)

    def test_normalization_moves_generic_categories_but_not_music_or_film(self):
        v = {"name": "Test Source", "url": "https://example.org", "default_category": "community"}
        when = (NOW + _dt.timedelta(days=2)).isoformat()
        raw = [
            {"name": "Somerville Flea", "date": when, "url": "u1", "venue": "Arts at the Armory", "category": "community"},
            {"name": "Inman Square Holiday Market", "date": when, "url": "u2", "venue": "Inman", "category": "art"},
            {"name": "Union Square Farmers Market", "date": when, "url": "u3", "venue": "Union Sq", "category": "food"},
            {"name": "Boston Celtic Music Festival", "date": when, "url": "u4", "venue": "Club Passim", "category": "music"},
            {"name": "Boston Comedy Festival Finals", "date": when, "url": "u5", "venue": "Laugh Boston", "category": "comedy"},
        ]
        out = {e["name"]: e["category"] for e in scrapers._normalize_and_filter_events(raw, v)}
        self.assertEqual(out["Somerville Flea"], "markets")
        self.assertEqual(out["Inman Square Holiday Market"], "markets")
        self.assertEqual(out["Union Square Farmers Market"], "markets")
        self.assertEqual(out["Boston Celtic Music Festival"], "music")
        self.assertEqual(out["Boston Comedy Festival Finals"], "comedy")

    def test_render_time_category_classifies_old_data_too(self):
        self.assertEqual(template._effective_category({"name": "Somerville Flea", "category": "community"}), "markets")
        self.assertEqual(template._effective_category({"name": "Boston Celtic Music Festival", "category": "music"}), "music")
        self.assertEqual(template._effective_category({"name": "Story Time", "category": "community"}), "family")

    def test_markets_is_its_own_default_on_bucket(self):
        self.assertEqual(scrapers.category_bucket("markets"), "Markets & Festivals")
        self.assertIn("markets", scrapers.CATEGORY_STYLES)
        self.assertNotIn("Markets & Festivals", template.DEFAULT_UNCHECKED_BUCKETS)

    def test_adult_night_at_a_kids_venue_is_not_family(self):
        self.assertNotEqual(scrapers.infer_category("Space Out Adult Night @ LEGO", "LEGO Discovery Center", "community"), "family")
        self.assertEqual(scrapers.infer_category("LEGO Build Day", "LEGO Discovery Center", "community"), "family")


class MarketsHubTest(unittest.TestCase):
    def test_hub_lists_market_events_only(self):
        hub = template.HUBS["markets-festivals-boston"]
        when = (_dt.datetime.now(_EST) + _dt.timedelta(days=1)).isoformat()
        events = [
            {"name": "SoWa Vintage Market", "date": when, "venue": "SoWa Vintage Market", "category": "markets", "url": "a"},
            {"name": "Jazz at Wally's", "date": when, "venue": "Wally's Café", "category": "music", "url": "b"},
        ]
        names = [e["name"] for e in template.filter_events_for_hub(hub, events)]
        self.assertEqual(names, ["SoWa Vintage Market"])

    def test_hub_page_renders_and_is_linked(self):
        when = (_dt.datetime.now(_EST) + _dt.timedelta(days=1)).isoformat()
        events = [{"name": "Somerville Flea", "date": when, "venue": "Arts at the Armory", "category": "markets",
                   "url": "https://artsatthearmory.org", "_source_venue": "Arts at the Armory"}]
        page = template.render_hub_page("markets-festivals-boston", events)
        self.assertIn("Markets, Fairs &amp; Festivals", page)
        self.assertIn("Somerville Flea", page)
        self.assertIn('href="../markets-festivals-boston/"', page)
        with open(os.path.join(BASE_DIR, "sitemap.xml")) as f:
            self.assertIn("/markets-festivals-boston/", f.read())


class HubSeriesTest(unittest.TestCase):
    def test_a_repeating_market_is_one_card_with_its_other_dates(self):
        base = _dt.datetime(2026, 11, 28, 11, 0, tzinfo=_EST)
        evs = [{"name": "Holiday Pop-Up Market", "venue": "Boston Public Market", "_time": base + _dt.timedelta(days=d)}
               for d in (0, 1, 7, 8, 14)]
        evs.insert(1, {"name": "Somerville Flea", "venue": "Arts at the Armory", "_time": base})
        evs.append({"name": "Holiday Pop-Up Market", "venue": "Bow Market", "_time": base})  # another venue's own
        out = template._collapse_hub_series(evs)
        self.assertEqual([(e["name"], e["venue"]) for e in out], [
            ("Holiday Pop-Up Market", "Boston Public Market"), ("Somerville Flea", "Arts at the Armory"),
            ("Holiday Pop-Up Market", "Bow Market")])
        self.assertEqual(out[0]["description"], "Also Sun, Nov 29 · Sat, Dec 5 · Sun, Dec 6 and 1 more dates.")
        self.assertNotIn("description", out[1])

    def test_listings_of_one_series_from_different_sources_collapse(self):
        t = _dt.datetime(2026, 11, 8, 10, 0, tzinfo=_EST)
        evs = [{"name": "SoWa Open Market", "venue": "SoWa", "_time": t},
               {"name": "SoWa Open Market", "venue": "SoWa Open Market", "_time": t + _dt.timedelta(days=7)}]
        self.assertEqual(len(template._collapse_hub_series(evs)), 1)


class MergedCategoryTest(unittest.TestCase):
    def test_a_merged_card_keeps_the_category_of_its_title(self):
        """The Anchor lists college games as 'Time: TBA' at midnight. Dedup folded one into the
        day's Pop Up Market, then into the evening's Notre Dame watch party, which then showed
        up on the Markets page as a market."""
        day = (_dt.datetime.now(template.EASTERN) + _dt.timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
        at = lambda h, m=0: day.replace(hour=h, minute=m).astimezone(_dt.timezone.utc).isoformat()
        anchor = {"venue": "The Anchor Boston", "url": "https://www.theanchorboston.com/calendar", "events": [
            {"name": "Oregon V. Ohio State Time: TBA", "date": at(0), "url": "https://www.theanchorboston.com/calendar",
             "venue": "The Anchor Boston", "category": "community"},
            {"name": "Pop Up Market at The Anchor", "date": at(11), "url": "https://www.theanchorboston.com/calendar",
             "venue": "The Anchor Boston", "category": "markets"},
            {"name": "Notre Dame Vs. Miami Game Watch @ The Anchor | 7:30", "date": at(19, 30),
             "url": "https://www.theanchorboston.com/calendar", "venue": "The Anchor Boston", "category": "sports"},
        ]}
        dated, _, _ = template.group_by_date([anchor])
        cats = {e["name"]: e.get("category") for _, evs in dated for e in evs}
        self.assertEqual(cats.get("Notre Dame Vs. Miami Game Watch @ The Anchor | 7:30"), "sports")


class RecurringSeasonTest(unittest.TestCase):
    def test_outdoor_markets_stop_at_the_end_of_their_season(self):
        self.assertTrue(scrapers._in_season("SoWa Open Market", _dt.date(2026, 7, 12)))
        self.assertTrue(scrapers._in_season("SoWa Open Market", _dt.date(2026, 11, 15)))  # last brewery takeover
        self.assertFalse(scrapers._in_season("SoWa Open Market", _dt.date(2026, 11, 22)))
        self.assertFalse(scrapers._in_season("Greenway Artisan Market", _dt.date(2026, 12, 5)))
        self.assertTrue(scrapers._in_season("Copley Square Farmers Market", _dt.date(2026, 11, 20)))
        self.assertFalse(scrapers._in_season("Copley Square Farmers Market", _dt.date(2026, 12, 1)))
        self.assertTrue(scrapers._in_season("The Beehive", _dt.date(2026, 1, 15)))  # no season: year-round

    def test_expansion_skips_out_of_season_weeks(self):
        with _frozen_clock():
            results = {r["venue"]: r["events"] for r in scrapers._expand_manual_recurring()}
        self.assertEqual([e["date"][:10] for e in results["SoWa Open Market"]], ["2026-11-08", "2026-11-15"])
        self.assertEqual(results["Greenway Artisan Market"], [])
        vintage = results["SoWa Vintage Market"]
        self.assertEqual(len(vintage), 8)  # Sundays, year-round
        copley = sorted(e["date"][:10] for e in results["Copley Square Farmers Market"])
        self.assertTrue(copley and copley[-1] <= "2026-11-25", copley)


_BPM_CELL = """<div
	data-eventurl="{url}"
	data-eventid="1"
	data-daydate="{daydate}"
	class="sugar-calendar-block__event-cell">
	<div class="sugar-calendar-block__event-cell__time"><time datetime="{start}">x</time></div>
	<div class="sugar-calendar-block__event-cell__title">
		{title}	</div>
</div>"""


def _bpm_cell(start, title, url="https://bostonpublicmarket.org/bpm-events/x/"):
    daydate = html.escape(json.dumps({"start_date": {"datetime": start, "value": "x"}}))
    return _BPM_CELL.format(url=url, daydate=daydate, start=start, title=html.escape(title))


class BostonPublicMarketTest(unittest.TestCase):
    PAGE = (
        '<script>var sugar_calendar_obj = {"ajax_url":"https://bostonpublicmarket.org/wp-admin/admin-ajax.php","nonce":"abc123"};</script>'
        '<div class="sugar-calendar-block" data-attributes="' + html.escape(json.dumps({"display": "month"})) + '">'
        '<form><input type="hidden" name="sc_calendar_id" value="sc-1" /></form>'
        + _bpm_cell("2026-11-04T18:00:00", "Craft Club")  # yesterday: dropped
        + _bpm_cell("2026-11-06T18:00:00", "The Sopranos Trivia Night")
        + _bpm_cell("2026-11-07T10:30:00", "Face Painting by FaceArt")
        + _bpm_cell("2026-11-08T17:00:00", "Pie & Wine Pairing at Marzae Cellar")
        + _bpm_cell("2026-11-09T00:00:00", "*MARKET CLOSED*")
        + _bpm_cell("2026-11-06T18:00:00", "The Sopranos Trivia Night")  # second block on the page
        + "</div>"
    )
    NEXT_MONTH = _bpm_cell("2026-12-05T11:00:00", "Holiday Pop-Up Market")

    def test_this_month_and_next_with_categories(self):
        session = mock.Mock()
        session.get.return_value = _resp(self.PAGE)
        session.post.return_value = _resp(payload={"success": True, "data": {"body": self.NEXT_MONTH}})
        with _frozen_clock(), mock.patch.object(scrapers, "_SESSION", session):
            events = scrapers.scrape_boston_public_market("https://bostonpublicmarket.org/events/", "ua")
        got = {e["name"]: e for e in events}
        self.assertEqual(sorted(got), ["Face Painting by FaceArt", "Holiday Pop-Up Market",
                                       "Pie & Wine Pairing at Marzae Cellar", "The Sopranos Trivia Night"])
        self.assertEqual(got["The Sopranos Trivia Night"]["date"], "2026-11-06T23:00:00+00:00")  # 6pm EST
        self.assertEqual(got["Face Painting by FaceArt"]["category"], "family")
        self.assertEqual(got["Pie & Wine Pairing at Marzae Cellar"]["category"], "food")
        self.assertEqual(got["The Sopranos Trivia Night"]["category"], "gaming")
        self.assertEqual(got["Holiday Pop-Up Market"]["venue"], "Boston Public Market")
        # Next month is asked for the way the calendar's own arrows do it
        data = dict(session.post.call_args.kwargs["data"])
        self.assertEqual(data["action"], "sugar_calendar_block_update")
        self.assertEqual(data["nonce"], "abc123")
        self.assertEqual((data["calendar_block[month]"], data["calendar_block[year]"]), ("12", "2026"))

    def test_month_change_failure_keeps_this_month(self):
        session = mock.Mock()
        session.get.return_value = _resp(self.PAGE)
        session.post.side_effect = OSError("down")
        with _frozen_clock(), mock.patch.object(scrapers, "_SESSION", session):
            events = scrapers.scrape_boston_public_market("https://bostonpublicmarket.org/events/", "ua")
        self.assertEqual(len(events), 3)


class HarvardSquareHolidayFairTest(unittest.TestCase):
    PAGE = """<html><body>HARVARD SQUARE HOLIDAY FAIR 2026 Corner of JFK St &amp; Winthrop St
      Dec 11th - 13th Friday thru Sunday Dec 18th - 20th Friday thru Sunday
      Fridays: 12-7 Saturdays: 11-7 Sundays: 12-6 Peace, Love &amp; Holiday Shopping since 1986</body></html>"""

    def test_one_event_per_fair_day_at_its_opening_hour(self):
        with _frozen_clock(), mock.patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(self.PAGE, "html.parser")):
            events = scrapers.scrape_harvard_square_holiday_fair("https://www.harvardsquareholidayfair.com/", "ua")
        self.assertEqual([e["date"][:16] for e in events], [
            "2026-12-11T17:00", "2026-12-12T16:00", "2026-12-13T17:00",  # Fri noon, Sat 11am, Sun noon EST
            "2026-12-18T17:00", "2026-12-19T16:00", "2026-12-20T17:00",
        ])
        self.assertTrue(all(e["category"] == "markets" for e in events))

    def test_no_year_no_events(self):
        page = BeautifulSoup("<p>See you next year!</p>", "html.parser")
        with mock.patch.object(scrapers, "fetch_soup", return_value=page):
            self.assertEqual(scrapers.scrape_harvard_square_holiday_fair("u", "ua"), [])


def _meetup_page(events):
    state = {"ROOT_QUERY": {}}
    for i, (title, when, venue, group, etype) in enumerate(events):
        state[f"Group:{i}"] = {"name": group, "urlname": f"g{i}"}
        state[f"Event:{i}"] = {"title": title, "dateTime": when, "eventType": etype,
                               "eventUrl": f"https://www.meetup.com/g{i}/events/{i}/",
                               "venue": venue, "group": {"__ref": f"Group:{i}"},
                               "description": "**Bring** a friend", "feeSettings": None}
    data = {"props": {"pageProps": {"__APOLLO_STATE__": state}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'


class MeetupTopicsTest(unittest.TestCase):
    def test_sweeps_topics_dedupes_and_keeps_narrow_categories(self):
        games = _meetup_page([
            ("Light Game Night (Thursday)", "2026-11-05T19:00:00-05:00",
             {"name": "Unplugged", "city": "Cambridge", "address": "325 Main St"}, "Unplugged Games", "PHYSICAL"),
        ])
        social = _meetup_page([
            ("Light Game Night (Thursday)", "2026-11-05T19:00:00-05:00",
             {"name": "Unplugged", "city": "Cambridge"}, "Unplugged Games", "PHYSICAL"),  # same event, also social
            ("Building AI Agents: a talk", "2026-11-06T18:00:00-05:00", {"name": "CIC", "city": "Cambridge"}, "AI Folks", "PHYSICAL"),
            ("Online book swap", "2026-11-06T18:00:00-05:00", None, "Readers", "ONLINE"),
            ("Far future picnic", "2027-03-01T12:00:00-05:00", {"name": "Common"}, "Picnickers", "PHYSICAL"),
        ])

        def fake_get(url, **kw):
            if "categoryId=535&" in url or url.endswith("categoryId=535"):
                return _resp(games)
            if "categoryId=652" in url:
                return _resp(social)
            return _resp("<html></html>")

        session = mock.Mock()
        session.get.side_effect = fake_get
        with _frozen_clock(), mock.patch.object(scrapers, "_SESSION", session):
            events = scrapers.scrape_meetup_topics("https://www.meetup.com/find/", "ua")
        got = {e["name"]: e for e in events}
        self.assertEqual(sorted(got), ["Building AI Agents: a talk", "Light Game Night (Thursday)"])
        game = got["Light Game Night (Thursday)"]
        self.assertEqual(game["category"], "gaming")  # from the Games topic, not "sports"
        self.assertEqual(game["venue"], "Unplugged (Cambridge)")
        self.assertEqual(game["address"], "325 Main St, Cambridge")
        self.assertEqual(game["description"], "Bring a friend")
        self.assertEqual(got["Building AI Agents: a talk"]["category"], "tech")
        # every topic x window was asked for
        self.assertEqual(session.get.call_count, len(scrapers.MEETUP_FIND_TOPICS) * len(scrapers.MEETUP_FIND_WINDOWS))


class TribePagedTest(unittest.TestCase):
    def test_pages_until_the_api_runs_out_and_skips_noise(self):
        def ev(name, cat="community"):
            return {"name": name, "date": "2026-11-06T23:00:00+00:00", "venue": "Harvard Square", "category": cat}

        pages = {
            1: [ev("Prayer Call @ Harvard Epworth"), ev("Harvard Square Chocolate Tour"), ev("Live Jazz", "music")],
            2: [ev("Harvard Square Chocolate Tour"), ev("Shuttle to Senior Center")],
            3: [],
        }

        def fake(url, ua, default_venue=None, default_category=None):
            page = int(re.search(r"[?&]page=(\d+)", url).group(1))
            self.assertIn("start_date=2026-11-05", url)
            self.assertIn("end_date=2026-11-26", url)
            return [dict(e) for e in pages.get(page, [])]

        with _frozen_clock(), mock.patch.object(scrapers, "scrape_tribe_rest", side_effect=fake) as m:
            events = scrapers.scrape_harvard_square("https://www.harvardsquare.com/wp-json/tribe/events/v1/events", "ua")
        self.assertEqual(m.call_count, 3)
        self.assertEqual([e["name"] for e in events], ["Harvard Square Chocolate Tour", "Live Jazz"])
        self.assertEqual(events[1]["category"], "music")


class BrightonMainStreetsTest(unittest.TestCase):
    def test_keeps_nights_out_and_kids_programs_drops_meetings_and_webinars(self):
        def ev(name, venue, cat="community"):
            return {"name": name, "date": "2026-11-06T23:00:00+00:00", "venue": venue, "category": cat}

        listed = [
            ev("Irish Village, I.V., Live Entertainment", "Irish Village"),
            ev("Open Mic Night", "Porter Belly's Pub", "comedy"),
            ev("Terrific Twos (FNC Allston-Brighton)", "Josephine A. Fiorentino Community Center"),
            ev("AA Meeting – Morbid Reflections", "Brighton Elk's Lodge"),
            ev("Marketing Your Business in the Digital World", "Boston Event"),  # online: no venue
            ev("2026 Medicare Open Enrollment Clinics", "Honan-Allston Branch of the Boston Public Library"),
            ev("BPD Soccer League, 7, 8, 9 year olds", "Rogers Park"),
        ]
        with mock.patch.object(scrapers, "scrape_tribe_rest_paged", return_value=listed):
            got = {e["name"]: e["category"] for e in scrapers.scrape_brighton_main_streets("u", "ua")}
        self.assertEqual(got, {"Irish Village, I.V., Live Entertainment": "music", "Open Mic Night": "comedy",
                               "Terrific Twos (FNC Allston-Brighton)": "family"})

    def test_branch_libraries_are_in_allston_brighton_not_copley(self):
        for venue in ("Honan-Allston Branch of the Boston Public Library", "Brighton Branch Library"):
            e = {"venue": venue, "_source_venue": "Brighton Main Streets"}
            self.assertEqual(template.resolve_subarea("boston", e)[1], "allston_brighton", venue)
        e = {"venue": "Boston Public Market", "_source_venue": "Boston Public Market"}
        self.assertEqual(template.resolve_subarea("boston", e)[1], "theater_downtown")


class NewSourcesRegisteredTest(unittest.TestCase):
    def test_sources_are_in_the_venue_list(self):
        names = {v["name"]: v for v in scrapers._ALL_VENUES}
        for name, fn in (("Harvard Square (HSBA)", scrapers.scrape_harvard_square),
                         ("Kendall Square Association", scrapers.scrape_kendall_square),
                         ("Assembly Row", scrapers.scrape_assembly_row),
                         ("Brighton Main Streets", scrapers.scrape_brighton_main_streets),
                         ("Boston Public Market", scrapers.scrape_boston_public_market),
                         ("Harvard Square Holiday Fair", scrapers.scrape_harvard_square_holiday_fair),
                         ("Meetup Boston (by topic)", scrapers.scrape_meetup_topics)):
            self.assertIn(name, names)
            self.assertIs(names[name]["scraper"], fn)
            self.assertTrue(names[name]["default_category"])  # keep the categories the scraper sets


if __name__ == "__main__":
    unittest.main()
