"""College events: which listings count as college events, which school they belong to, the
/college/ hub and the school badge on the main calendar."""
import copy
import os
import re
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import template as T  # noqa: E402
from college import (  # noqa: E402
    COLLEGE_AREAS,
    COLLEGE_SOURCES,
    college_area,
    college_kind,
    college_transit_info,
    detect_school,
    is_college_event,
)
from template import EASTERN  # noqa: E402


def _ev(name, source="Ticketmaster", venue="", category="sports", url=None):
    return {"name": name, "_source_venue": source, "venue": venue, "category": category, "url": url or ""}


def _day_at(days, hour):
    d = datetime.now(EASTERN).date() + timedelta(days=days)
    return datetime(d.year, d.month, d.day, hour, tzinfo=EASTERN)


class WhatCountsAsCollege(unittest.TestCase):
    def test_every_event_from_a_schools_own_calendar(self):
        for source in ("MIT Events", "BU Terriers Athletics", "Jordan Hall (NEC)", "Suffolk University Events"):
            self.assertTrue(is_college_event(_ev("Anything at all", source=source, category="community")), source)

    def test_museums_and_presenters_a_school_runs_are_not_student_events(self):
        """#65 flagged 67 Harvard Art Museums tours, 23 Harvard Film Archive screenings, 68 A.R.T.
        plays and ArtsEmerson's touring shows as college events."""
        for name, source, venue in (("Gallery Talk: Ancient Greek Masks", "Harvard Art Museums", "Harvard Art Museums"),
                                    ("Vertigo", "Harvard Film Archive", "Harvard Film Archive"),
                                    ("1972", "American Repertory Theater", "Loeb Drama Center"),
                                    ("Dream Feed", "ArtsEmerson", "Emerson Paramount Center")):
            self.assertFalse(is_college_event(_ev(name, source=source, venue=venue, category="theater")), name)

    def test_a_campus_venue_alone_is_not_enough(self):
        """Touring shows and pro orchestras play college-owned halls most nights."""
        for name, venue in (("Lizzy McAlpine", "Agganis Arena"), ("Hadestown (Touring)", "Emerson Colonial Theatre"),
                            ("Dover Quartet", "Jordan Hall"), ("Jeremy Denk", "Sanders Theatre"),
                            ("Crystal Ballroom Movie Trivia", "Crystal Ballroom")):
            self.assertFalse(is_college_event(_ev(name, venue=venue, category="music")), name)

    def test_short_school_names_match_whole_words_only(self):
        """#65 matched substrings: "bu" in "Bully Boy", "mit" in "summit", "nec" in "connection"."""
        for name, source in (("Climate Summit Choir Night", "Eventbrite Boston"),
                             ("Connection Band Showcase", "Eventbrite Boston"),
                             ("Mit Liebe: Schubert Orchestra Songs", "Celebrity Series of Boston"),
                             ("Harvard Square Holiday Fair Band Stage", "Harvard Square (HSBA)"),
                             ("Bully Boy Cocktail Night", "Bully Boy Distillers")):
            self.assertFalse(is_college_event(_ev(name, source=source, category="music")), name)
            self.assertNotIn(detect_school(_ev(name, source=source)), ("bu", "mit", "nec", "harvard"), name)

    def test_aggregator_games_and_student_ensembles(self):
        for name, school in (("Boston University Men's Hockey vs. Harvard University Crimson Mens Hockey", "bu"),
                             ("Boston College Eagles at Harvard Crimson Mens Basketball", "harvard"),
                             ("MIT Concert Choir & MIT Symphony Orchestra: Carmina Burana", "mit"),
                             ("Harvard-Radcliffe Orchestra Concert", "harvard")):
            e = _ev(name, source="SeatGeek")
            self.assertTrue(is_college_event(e), name)
            self.assertEqual(detect_school(e), school, name)

    def test_a_school_name_without_a_game_or_ensemble_is_not_enough(self):
        for name in ("Harvard professor discusses her new book", "Tufts alumni happy hour at The Burren"):
            self.assertFalse(is_college_event(_ev(name, source="Eventbrite Boston", category="talks")), name)

    def test_intercollegiate_events_have_no_single_school(self):
        e = _ev("The Beanpot: Semifinals", source="Ticketmaster", venue="TD Garden")
        self.assertTrue(is_college_event(e))
        self.assertIsNone(detect_school(e))


class WhichSchool(unittest.TestCase):
    def test_suffolk_is_its_own_school(self):
        """Fix 7: #65 badged Suffolk University events as Emerson."""
        self.assertEqual(detect_school(_ev("Sankofa Lecture Series", source="Suffolk University Events")), "suffolk")
        self.assertEqual(detect_school(_ev("Suffolk University Rams Men's Basketball vs Emerson", source="SeatGeek")), "suffolk")

    def test_nec_and_berklee_are_separate(self):
        self.assertEqual(detect_school(_ev("Piano Department Concert", source="Jordan Hall (NEC)")), "nec")
        self.assertEqual(detect_school(_ev("Krystal's Trip", source="Berklee College of Music")), "berklee")

    def test_every_college_source_maps_to_a_known_school(self):
        from college import COLLEGE_SCHOOLS
        self.assertTrue(set(COLLEGE_SOURCES.values()) <= set(COLLEGE_SCHOOLS))

    def test_college_sources_are_real_venues(self):
        """A renamed source would silently drop out of the college hub."""
        from scrapers import _ALL_VENUES, MANUAL_RECURRING_EVENTS
        names = {v["name"] for v in _ALL_VENUES} | {r[0] for r in MANUAL_RECURRING_EVENTS}
        self.assertEqual(set(COLLEGE_SOURCES) - names, set())

    def test_kinds(self):
        self.assertEqual(college_kind(_ev("X vs Y", source="MIT Engineers Athletics", category="community")), "sports")
        self.assertEqual(college_kind(_ev("Recital", source="Jordan Hall (NEC)", category="classical")), "performances")
        self.assertEqual(college_kind(_ev("Lecture", source="MIT Events", category="talks")), "talks")
        self.assertEqual(college_kind(_ev("Open house", source="MIT Events", category="community")), "campus")

    def test_areas(self):
        self.assertEqual(college_area("bu"), "comm_ave")
        self.assertEqual(college_area("harvard"), "cambridge")
        self.assertEqual(college_area("mit"), "cambridge")
        self.assertEqual(college_area("neu"), "fenway_symphony")
        self.assertEqual(college_area("berklee"), "fenway_symphony")
        self.assertEqual(college_area("nec"), "fenway_symphony")
        self.assertEqual(college_area("emerson"), "downtown")
        self.assertEqual(college_area("suffolk"), "downtown")
        self.assertEqual(college_area("bc"), "suburbs")
        self.assertEqual(college_area("tufts"), "suburbs")
        self.assertEqual(college_area(None, venue="TD Garden"), "downtown")
        self.assertEqual(college_area(None, venue="Kendall Square"), "cambridge")

    def test_transit_info(self):
        neigh, tr = college_transit_info("bu", "Agganis Arena")
        self.assertIn("Comm Ave", neigh)
        self.assertEqual(tr, "Green Line B")
        neigh, tr = college_transit_info("harvard", "Sanders Theatre")
        self.assertIn("Harvard Square", neigh)
        self.assertEqual(tr, "Red Line")
        neigh, tr = college_transit_info("nec", "Jordan Hall")
        self.assertIn("Symphony", neigh)
        self.assertIn("Green E", tr)


def _venue(source, events):
    return {"venue": source, "url": "https://x.test/" + re.sub(r"\W+", "", source.lower()), "error": None, "events": events}


def _hub_events(venues):
    dated, _, _ = T.group_by_date(copy.deepcopy(venues))
    return [e for _, evs in dated for e in evs]


class CollegeHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        game, talk, later = _day_at(2, 19), _day_at(3, 16), _day_at(40, 19)
        cls.venues = [
            _venue("BU Terriers Athletics", [
                {"name": "Boston University Men's Hockey vs Harvard", "date": game.isoformat(), "category": "sports",
                 "url": "https://goterriers.com/g1", "venue": "Agganis Arena", "price": "$20"},
                {"name": "Boston University Women's Hockey vs Maine", "date": later.isoformat(), "category": "sports",
                 "url": "https://goterriers.com/g2", "venue": "Walter Brown Arena"}]),
            _venue("MIT Events", [
                {"name": "Fall Lecture: The Fight for Facts", "date": talk.isoformat(), "category": "talks",
                 "url": "https://calendar.mit.edu/e/1", "venue": "Kresge Auditorium (MIT)", "price": "Free"}]),
            _venue("Bowery Presents Boston", [
                {"name": "Lizzy McAlpine", "date": game.isoformat(), "category": "music",
                 "url": "https://bowerypresents.com/e/1", "venue": "Agganis Arena"}]),
        ]
        cls.html = T.render_hub_page("college", _hub_events(cls.venues))

    def test_lists_college_events_in_the_next_four_weeks_only(self):
        self.assertIn("Men&#x27;s Hockey vs Harvard", self.html)
        self.assertIn("The Fight for Facts", self.html)
        self.assertNotIn("Lizzy McAlpine", self.html)      # Bowery stays on the main calendar, not here
        self.assertNotIn("vs Maine", self.html)            # 40 days out

    def test_cards_carry_school_kind_and_free_for_the_filters(self):
        self.assertRegex(self.html, r'data-school="bu" data-kind="sports" data-free="0"')
        self.assertRegex(self.html, r'data-school="mit" data-kind="talks" data-free="1"')
        self.assertIn('<span class="badge badge-school">BU</span>', self.html)

    def test_filter_chips_only_for_schools_and_kinds_present(self):
        schools = re.findall(r'data-group="school" data-val="(\w+)"', self.html)
        self.assertEqual(schools, ["all", "bu", "mit"])
        kinds = re.findall(r'data-group="kind" data-val="(\w+)"', self.html)
        self.assertEqual(kinds, ["all", "sports", "talks"])
        self.assertIn('data-group="free" data-val="1"', self.html)
        # The filter script must come after the cards it filters
        self.assertLess(self.html.rindex("<article"), self.html.index("querySelectorAll('.col-chip')"))

    def test_hero_and_art_present(self):
        self.assertIn("col-hero-art", self.html)
        self.assertIn("GREATER BOSTON CAMPUSES", self.html)
        self.assertIn("col-stats", self.html)
        self.assertIn("14 Campuses", self.html)

    def test_top_nav_is_student_focused(self):
        # Student nav includes: All Events, College (active), Markets & Festivals, Kids & Family, Summer Camps, Free Events, Boston EDM, Cambridge Tonight, Live Music
        self.assertIn('<a href="../college/" class="active">College</a>', self.html)
        self.assertIn('<a href="../boston-edm/"', self.html)
        self.assertIn('<a href="../cambridge-events-tonight/"', self.html)
        self.assertIn("markets-festivals-boston", self.html)
        self.assertIn("kids-family-events-boston", self.html)
        self.assertIn("summer-camps", self.html)
        self.assertNotIn("board-game-nights-boston", self.html)

    def test_cards_carry_area_and_transit(self):
        self.assertIn('data-area="comm_ave"', self.html)
        self.assertIn('data-area="cambridge"', self.html)
        self.assertIn("Green Line B", self.html)
        self.assertIn("Red Line", self.html)
        self.assertNotIn("col-area-section", self.html)

    def test_area_filter_chips_present(self):
        areas = re.findall(r'data-group="area" data-val="(\w+)"', self.html)
        self.assertEqual(areas, ["all", "cambridge", "comm_ave"])

    def test_registered_and_in_site_directory(self):
        # Other guide pages' header bar lists only finished pages (template._MAIN_NAV)
        self.assertIn("college", T.HUBS)
        self.assertIn('href="college/"', T.render_page([]))


class MainCalendar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        soon = (datetime.now(EASTERN) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
        venues = [
            _venue("Boston College Eagles Athletics", [
                {"name": "Boston College Men's Basketball vs Maryland Eastern Shore", "date": soon.isoformat(),
                 "category": "sports", "url": "https://bceagles.com/g1", "venue": "Conte Forum"}]),
            _venue("Bowery Presents Boston", [
                {"name": "Lizzy McAlpine", "date": soon.isoformat(), "category": "music",
                 "url": "https://bowerypresents.com/e/1", "venue": "Agganis Arena"}]),
        ]
        with patch("template._load_community_events", return_value=[]):
            cls.html = T.render_page(venues)
        cls.cards = re.findall(r'<li class="event".*?</li>', cls.html, re.S)

    def test_college_events_show_by_default_with_a_school_badge(self):
        bc = [c for c in self.cards if "Maryland Eastern Shore" in c]
        self.assertEqual(len(bc), 1)
        self.assertIn('<a class="college-tag" href="college/#school=bc"', bc[0])
        self.assertNotIn("hidden", bc[0].split(">")[0])

    def test_no_badge_on_other_events(self):
        other = [c for c in self.cards if "Lizzy McAlpine" in c]
        self.assertEqual(len(other), 1)
        self.assertNotIn("college-tag", other[0])

    def test_no_hide_college_checkbox_or_college_hash(self):
        self.assertNotIn("college-only-chk", self.html)
        self.assertNotIn("college=1", self.html)

    def test_title_stays_the_first_link(self):
        """Scripts (My Schedule export, share) take the first ".what a" as the event's own link."""
        bc = [c for c in self.cards if "Maryland Eastern Shore" in c][0]
        what = bc[bc.index('class="what"'):]
        self.assertTrue(re.search(r"<a [^>]*>([^<]+)</a>", what).group(1).startswith("Boston College Men"))


if __name__ == "__main__":
    unittest.main()
