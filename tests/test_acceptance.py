"""Acceptance tests: one per user-visible failure found on wickedbostonevents.com.

Each test reproduces the real case (titles, venues and sources as they appeared on the site)
and checks what a visitor would see. If one fails, that bug is back.
"""
import copy
import importlib.util
import json
import os
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import template as T  # noqa: E402
from template import EASTERN  # noqa: E402


def _soon(hours=2):
    """A start time that renders on today's homepage (later days are deferred to another file)."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(minute=0, second=0, microsecond=0)


def _day_at(days, hour, minute=0):
    d = datetime.now(EASTERN).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=EASTERN)


def _ev(name, source, venue, when, url=None, category="music", price=None, **kw):
    """An event as it looks inside _merge_duplicates (after group_by_date annotated it)."""
    slug = re.sub(r"\W+", "", source.lower())
    e = {"name": name, "_source_venue": source, "venue": venue, "_time": when, "date": when.isoformat(),
         "url": url or f"https://{slug}.test/e/{abs(hash((name, venue, when)))}",
         "venue_url": f"https://{slug}.test/", "category": category, "price": price}
    e.update(kw)
    return e


def _merge(events):
    """_merge_duplicates with a calendar-wide word frequency, as group_by_date runs it."""
    return T._merge_duplicates([copy.deepcopy(e) for e in events], T.title_word_freq(events))


def _visible_text(html):
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class CardRenderingAcceptance(unittest.TestCase):
    def _render(self, venues):
        with patch("template._load_community_events", return_value=[]):
            return T.render_page(venues)

    def test_merged_card_shows_its_title(self):
        """Bachata Room at La Fábrica Central showed "$15 ↻ weekly" with no title: the "also on"
        loop overwrote the title link (138 of 924 homepage cards)."""
        when = _soon().isoformat()
        src = lambda source, url: {"venue": source, "url": "https://" + re.sub(r"\W+", "", source.lower()) + ".test",
                                   "error": None, "events": [{"name": "Bachata Room Boston", "date": when, "url": url,
                                                              "venue": "La Fábrica Central", "category": "dance",
                                                              "price": "$15"}]}
        html = self._render([
            src("Salsa Vida Boston", "https://www.salsavida.com/event/massachusetts/cambridge/bachata-room-boston/"),
            src("Boston Salsa & Bachata", "https://bostonsalsa.org/event/bachata-room-bachata-"),
        ])
        cards = [c for c in re.findall(r'<li class="event".*?</li>', html, re.S) if "La Fábrica Central" in c]
        self.assertEqual(len(cards), 1)
        self.assertIn(">Bachata Room Boston</a>", cards[0])
        self.assertIn("also on", cards[0])
        untitled = re.findall(r'</button><a href="[^"]*" target="_blank" rel="noopener"><(?:span|div)', html)
        self.assertEqual(untitled, [])

    def test_unchecked_categories_hidden_from_map_and_near_me(self):
        """Near Me listed ESOL classes and the map showed every venue after a category was
        unchecked: both must skip events inside collapsed (.empty) sections."""
        html = self._render([])
        self.assertIn("if (li.closest('.empty')) return;", html)          # map markers
        self.assertIn("filter(ev => !ev.closest('.empty'))", html)         # Near Me

    def test_site_says_daily_not_every_30_minutes(self):
        html = self._render([])
        self.assertNotIn("every 30 minutes", html)


class HubPageAcceptance(unittest.TestCase):
    def _hub(self, slug, venues):
        dated, _, _ = T.group_by_date(copy.deepcopy(venues))
        events = [e for _, evs in dated for e in evs]
        return T.render_hub_page(slug, events)

    def test_kids_hub_dates_readable_and_single_dollar(self):
        """Hub pages showed raw timestamps ("2026-11-09T01:00:00+00:00") and prices like "$$18"."""
        when = _day_at(1, 10, 30)
        html = self._hub("kids-family-events-boston", [{
            "venue": "Puppet Showplace Theater", "url": "https://www.puppetshowplace.org", "error": None,
            "events": [{"name": "Dig Down Deep: A Cave Adventure", "date": when.isoformat(), "category": "family",
                        "url": "https://www.puppetshowplace.org/calendar/dig-down-deep", "price": "$18.50",
                        "venue": "Puppet Showplace Theater"}]}])
        text = _visible_text(html)
        self.assertIn("Dig Down Deep", text)
        self.assertNotRegex(text, r"\d{4}-\d\d-\d\dT\d\d:\d\d")
        self.assertNotIn("$$", text)
        self.assertIn(when.strftime("%A"), text)        # "Thursday, November 5" day header
        self.assertIn("10:30", text)


class MergeAcceptance(unittest.TestCase):
    """Duplicates that showed as two cards, and different events that were wrongly one card."""

    # --- the same event twice ---------------------------------------------------------------
    def test_trisha_paytas_venue_and_bookstore_listings_merge(self):
        t = _day_at(8, 19, 30)
        out = _merge([
            _ev("A Conversation with Trisha Paytas", "Crystal Ballroom", "Crystal Ballroom at Somerville Theatre", t),
            _ev("SOLD OUT! Trisha Paytas: Crying on the Kitchen Floor", "Brookline Booksmith", "Crystal Ballroom", t),
        ])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["name"], "A Conversation with Trisha Paytas")   # the venue's own title leads

    def test_wbur_talk_listed_by_booksmith_merges_with_wbur_title(self):
        t = _day_at(7, 19)
        out = _merge([
            _ev("WBUR CitySpace: Sofia Franklyn", "Brookline Booksmith", "WBUR CitySpace", t, category="community"),
            _ev("Daddy Issues: 'Call Her Daddy' co-creator Sofia Franklyn reclaims her story", "WBUR CitySpace",
                "WBUR CitySpace", t, category="community"),
        ])
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["name"].startswith("Daddy Issues"))

    def test_ticketmaster_and_seatgeek_game_titles_merge(self):
        t = _day_at(2, 19)
        out = _merge([
            _ev("Harvard Crimson Hockey vs. Brown University Bears Hockey", "Ticketmaster", "Bright-Landry Hockey Center", t,
                url="https://www.ticketmaster.com/event/Z7r9jZ1AAvx_U", category="sports"),
            _ev("Brown Bears at Harvard Crimson Mens Hockey", "SeatGeek", "Bright-Landry Hockey Center", t,
                url="https://seatgeek.com/harvard-crimson-mens-hockey-tickets/ncaa-hockey/2026-11-06-7-pm/18531058",
                category="sports"),
        ])
        self.assertEqual(len(out), 1)

    def test_ticketmaster_double_listing_merges(self):
        t = _day_at(2, 22)
        out = _merge([
            _ev("CamelPhat", "Ticketmaster", "Royale Boston", t, url="https://www.ticketmaster.com/event/A1"),
            _ev("CamelPhat (21 and Over)", "Ticketmaster", "Royale Boston", t, url="https://www.ticketmaster.com/event/B2"),
            _ev("CamelPhat  (21+)", "Royale Boston", "Royale", t, url="https://link.dice.fm/X9a354cd3dfe"),
        ])
        self.assertEqual(len(out), 1)

    def test_aggregator_double_listing_with_reseller_time_merges(self):
        """The Boston Calendar listed Phoebe Robinson twice: the Wilbur's page (7:30) and a reseller (6:30)."""
        out = _merge([
            _ev("Phoebe Robinson - Feral & Fired Up! Tour", "The Boston Calendar", "Wilbur Theatre", _day_at(9, 18, 30),
                url="https://eventschaser.com/tickets/Phoebe-Robinson-Wilbur-Theatre---MA-Boston-MA/7826233/"),
            _ev("Phoebe Robinson: Feral & Fired Up!", "The Boston Calendar", "The Wilbur", _day_at(9, 19, 30),
                url="https://thewilbur.com/event/phoebe-robinson/"),
        ])
        self.assertEqual(len(out), 1)

    # --- different events wrongly combined --------------------------------------------------
    def test_shows_sharing_a_ticket_site_stay_separate(self):
        """Every 24 Hour Music link reduced to one URL, so three shows became one card."""
        t = _day_at(10, 19)
        out = _merge([
            _ev("Truancy, Some Assembly Required", "The Burren", "The Burren — The Back Room", t,
                url="https://tickets.24hourmusic.com/eventperformances.asp?evt=1601"),
            _ev("Chick Singer Night Boston", "24 Hour Music", "The Burren (Somerville)", t,
                url="https://tickets.24hourmusic.com/eventperformances.asp?evt=1557"),
            _ev("SHK Music Presents: The Hellbender", "24 Hour Music", "Boston Harbor Distillery (Boston)", t,
                url="https://tickets.24hourmusic.com/eventperformances.asp?evt=1612"),
        ])
        self.assertEqual(len(out), 3)

    def test_programs_at_different_libraries_stay_separate(self):
        t = _day_at(8, 15)
        out = _merge([
            _ev("Crafternoon: Tornado in a Jar", "Boston Public Library", "Boston Public Library (Mattapan)", t,
                url="https://bpl.bibliocommons.com/events/6aea388a9d27a000455573ec", category="family"),
            _ev("Tween Crafternoon", "Brookline Public Library", "Brookline Public Library (Brookline Village)", t,
                url="https://brooklinelibrary.libcal.com/event/17280325", category="family"),
        ])
        self.assertEqual(len(out), 2)

    def test_esol_classes_at_central_square_and_copley_stay_separate(self):
        t = _day_at(6, 18)
        out = _merge([
            _ev("Drop-in English Conversation Practice (Central Square)", "Cambridge Public Library",
                "Cambridge Public Library (Central Square Branch)", t, category="community"),
            _ev("Drop-in ESOL Conversation Group (Level 2 and higher)", "Boston Public Library",
                "Boston Public Library (Central Library in Copley Square)", t, category="community"),
        ])
        self.assertEqual(len(out), 2)

    def test_brunches_at_different_bars_stay_separate(self):
        t = _day_at(4, 11, 30)
        out = _merge([
            _ev("Sunday Drag Brunch", "Dani's Queer Bar", "Dani's Queer Bar", t, category="community"),
            _ev("Sunday Jazz Brunch", "The Boston Calendar", "Lou's", t, category="community"),
        ])
        self.assertEqual(len(out), 2)

    def test_numbered_rounds_and_age_groups_stay_separate(self):
        t = _day_at(8, 19)
        self.assertEqual(len(_merge([
            _ev("COMEDY CONTEST PRELIMINARY ROUND 3", "The Boston Calendar", "City Winery", t, category="comedy"),
            _ev("Boston Comedy Festival Comedy Contest Preliminary Round 5", "City Winery Boston",
                "Haymarket Lounge at City Winery Boston", t, category="comedy"),
        ])), 2)
        self.assertEqual(len(_merge([
            _ev("Speed Dating at CanalSide! Ages 27-37, 1 Drink Incl", "Eventbrite Boston", "CanalSide", t,
                category="community"),
            _ev("Speed Dating at CanalSide! Ages 36-48, 1 Drink Incl", "Eventbrite Boston", "CanalSide", t,
                category="community"),
        ])), 2)

    def test_age_groups_in_parentheses_stay_separate(self):
        """Parentheses are dropped when comparing titles, so "(Ages 27-37)" and "(Ages 36-48)"
        looked identical."""
        t = _day_at(8, 18, 30)
        out = _merge([
            _ev("Speed Dating (Ages 27-37)", "Eventbrite Boston", "CanalSide", t, category="community"),
            _ev("Speed Dating (Ages 36-48)", "Eventbrite Boston", "CanalSide", t, category="community"),
        ])
        self.assertEqual(len(out), 2)

    def test_numbers_in_a_name_dont_block_merging(self):
        """ "Brutalismus 3000" and "Brutalismus 3000 (18+)" are one show; so are "HO99O9" and
        "Ho99o9 & N8NOFACE"."""
        t = _day_at(7, 20)
        self.assertEqual(len(_merge([
            _ev("Brutalismus 3000", "Royale Boston", "Royale", t, url="https://www.axs.com/events/1559290/brutalismus-3000"),
            _ev("Brutalismus 3000 (18+)", "The Boston Calendar", "Royale", t,
                url="https://www.thebostoncalendar.com/events/brutalismus-3000"),
        ])), 1)
        t = _day_at(6, 18, 30)
        self.assertEqual(len(_merge([
            _ev("HO99O9", "Paradise Rock Club", "Paradise Rock Club", t, url="https://www.crossroadspresents.com/ho99o9"),
            _ev("Ho99o9 & N8NOFACE – Sincerely___ The Void", "The Boston Calendar", "Paradise Rock Club", t,
                url="https://www.thebostoncalendar.com/events/ho99o9"),
        ])), 1)

    def test_one_venues_separate_programs_stay_separate(self):
        """ICA's "Boston Family Days" and "Museums on Us" at the same hour were one card."""
        t = _day_at(4, 10)
        out = _merge([
            _ev("Bank of America Museums on Us", "ICA Boston", "ICA Boston", t, category="family",
                url="https://www.icaboston.org/events/bank-america-museums-us/"),
            _ev("Boston Family Days", "ICA Boston", "ICA Boston", t, category="family",
                url="https://www.icaboston.org/events/boston-family-days/"),
        ])
        self.assertEqual(len(out), 2)

    def test_same_title_at_far_apart_venues_stays_separate(self):
        out = _merge([
            _ev("Boston Family Days", "New England Aquarium", "New England Aquarium", _day_at(4, 9), category="family",
                url="https://www.neaq.org/event/boston-family-days-4/"),
            _ev("Boston Family Days", "ICA Boston", "ICA Boston", _day_at(4, 10), category="family",
                url="https://www.icaboston.org/events/boston-family-days/"),
        ])
        self.assertEqual(len(out), 2)


class ScraperAcceptance(unittest.TestCase):
    def test_ticketing_zero_price_is_not_shown_as_free(self):
        """Sonia showed "$0" from Ticketmaster; tickets are $29.85."""
        from scrapers import _normalize_and_filter_events
        when = _day_at(1, 20).astimezone(timezone.utc).isoformat()
        out = _normalize_and_filter_events(
            [{"name": "Sonia", "date": when, "url": "https://www.ticketmaster.com/event/X", "venue": "Sonia",
              "price": "$0"}], {"name": "Ticketmaster"})
        self.assertTrue(out)
        self.assertIsNone(out[0].get("price"))

    def test_cambridge_library_kids_program_is_kids_and_family(self):
        """Twilight Music and Movement wasn't in Kids & Family: CPL only says so in the description."""
        from scrapers import scrape_cpl
        day = _day_at(3, 18).strftime("%Y-%m-%d")
        rss = f"""<rss><channel>
          <item><title>Twilight Music and Movement (Central Square)</title>
            <guid>https://cambridgepl.libcal.com/event/1</guid>
            <libcal:date>{day}</libcal:date><libcal:start>18:00:00</libcal:start>
            <libcal:campus>Central Square Branch</libcal:campus>
            <libcal:description>Recommended for children of all ages and their caregivers.</libcal:description></item>
          <item><title>Beginner ESOL (Central Square)</title>
            <guid>https://cambridgepl.libcal.com/event/2</guid>
            <libcal:date>{day}</libcal:date><libcal:start>10:30:00</libcal:start>
            <libcal:campus>Central Square Branch</libcal:campus>
            <libcal:description>English class for adults only.</libcal:description></item>
        </channel></rss>"""
        resp = MagicMock(text=rss, status_code=200)
        resp.raise_for_status = lambda: None
        with patch("scrapers._SESSION.get", return_value=resp):
            evs = {e["name"]: e for e in scrape_cpl(None, "test")}
        self.assertEqual(evs["Twilight Music and Movement (Central Square)"]["category"], "family")
        self.assertNotEqual(evs["Beginner ESOL (Central Square)"]["category"], "family")

    def test_northeastern_tech_talk_goes_to_tech_not_kids(self):
        """Northeastern engineering/AI talks were showing in Kids & Family."""
        from scrapers import scrape_northeastern
        start = _day_at(5, 17).isoformat()
        data = {"events": [{"event": {
            "title": "The Policy School Turns 20", "location_name": "East Village, 17th floor",
            "localist_url": "https://calendar.northeastern.edu/event/policy-school-20",
            "event_instances": [{"event_instance": {"start": start}}],
            "filters": {"departments": [{"name": "Khoury College of Computer Sciences"}]}}}]}
        resp = MagicMock(); resp.json.return_value = data; resp.raise_for_status = lambda: None
        with patch("scrapers._SESSION.get", return_value=resp):
            evs = scrape_northeastern("https://calendar.northeastern.edu/api/2/events", "test")
        self.assertEqual(evs[0]["category"], "tech")

    def test_second_sun_rising_uses_each_dates_venue(self):
        """The December dance was listed at the Masonic Hall; it's at First Street Market."""
        from bs4 import BeautifulSoup
        from scrapers import UA_CHROME, scrape_second_sun_rising
        year = datetime.now(EASTERN).year + 1
        page = f"""<html><body><article><p>Our next event will be January 10th, and we'll be at First Street
          Market, 59 First Street in Cambridge.</p><p>February 14 {year} we'll be at Cambridge Masonic Hall at
          1950 Mass Ave.</p></article></body></html>"""
        with patch("scrapers.fetch_soup", return_value=BeautifulSoup(page, "html.parser")):
            evs = scrape_second_sun_rising("https://secondsunrising.com/", UA_CHROME)
        venues = [e["venue"] for e in evs]
        self.assertIn("First Street Market", venues)
        self.assertIn("Cambridge Masonic Hall", venues)

    def test_little_muse_reads_rss_when_api_is_blocked(self):
        """Little Muse had 0 events on CI: Substack's JSON API refuses GitHub's runners."""
        from scrapers import _little_muse_posts
        rss = """<rss><channel><item><title>This week</title><link>https://littlemuse.substack.com/p/week</link>
          <pubDate>Mon, 02 Nov 2026 12:00:00 GMT</pubDate>
          <content:encoded><![CDATA[<p>🎃 10:00-11:00 AM - <a href="https://x.test/e">Songs, Stories and Play</a></p>]]></content:encoded>
          </item></channel></rss>"""
        feed = MagicMock(text=rss); feed.raise_for_status = lambda: None
        with patch("scrapers._SESSION.get", return_value=feed) as get:
            posts = _little_muse_posts("https://littlemuse.substack.com", "test", 3)
        self.assertEqual(len(posts), 1)
        self.assertIn("Songs, Stories and Play", posts[0]["body_html"])
        self.assertTrue(get.call_args_list[0][0][0].endswith("/feed"))


class RedditPostAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "generate_reddit_roundup", os.path.join(ROOT, "scripts", "generate_reddit_roundup.py"))
        cls.G = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.G)

    def test_placeholder_prices_hidden(self):
        """The draft printed "· Check link ·" as a price."""
        self.assertEqual(self.G._price({"price": "Check link"}), "")
        self.assertEqual(self.G._price({"price": "Tickets"}), "")
        self.assertEqual(self.G._price({"price": "$25"}), "$25")

    def test_off_site_concert_uses_its_own_neighborhood(self):
        """BSO at the Boston Athenaeum was labeled "Fenway & Kenmore" (Symphony Hall's area)."""
        e = {"name": "A Golden Wire: Timæus", "venue": "Bayard Henry Long Room, Boston Athenaeum",
             "_source_venue": "Symphony Hall"}
        self.assertEqual(self.G._area(e), "Beacon Hill")

    def test_week_post_builds_from_current_data(self):
        """End to end on the committed events.json: under Reddit's 40,000-character limit, one
        section per day, and no event listed twice."""
        if not os.path.exists(os.path.join(ROOT, "events.json")):
            self.skipTest("no events.json")
        title, body, _ = self.G.build(self.G._week_start(None))
        self.assertLess(len(body), 40000)
        self.assertEqual(len(re.findall(r"^\*\*(?:MON|TUES|WEDNES|THURS|FRI|SATUR|SUN)DAY, ", body, re.M)) <= 7, True)
        # Same title on the same day twice = a duplicate (two events may share a venue's generic link)
        entries, day = [], None
        for line in body.splitlines():
            m = re.match(r"^\*\*([A-Z]+DAY), ", line)
            if m:
                day = m.group(1)
            m = re.match(r"^\* (?:(\w{3}) · )?\*\*\[([^\]]+)\]", line)
            if m:
                entries.append(((m.group(1) or day or "").upper()[:3], re.sub(r"\W+", "", m.group(2).lower())))
        dupes = [k for k in set(entries) if entries.count(k) > 1]
        self.assertEqual(dupes, [], "an event appears twice in the post")


if __name__ == "__main__":
    unittest.main()
