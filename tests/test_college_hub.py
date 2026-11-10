import unittest
from datetime import datetime, timezone
import template
import college


class CollegeEventDetectionTests(unittest.TestCase):
    def test_bu_athletics_detected(self):
        e = {
            "name": "Boston University Men's Ice Hockey vs Harvard - Heroes Night",
            "venue": "Agganis Arena",
            "_source_venue": "BU Terriers Athletics",
            "date": "2026-11-11T00:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["school_key"], "bu")
        self.assertEqual(info["school_short"], "BU")
        self.assertEqual(info["type_key"], "sports")

    def test_bc_athletics_detected(self):
        e = {
            "name": "Boston College Men's Basketball vs Maryland Eastern Shore",
            "venue": "Conte Forum",
            "_source_venue": "Boston College Eagles Athletics",
            "date": "2026-11-11T00:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["school_key"], "bc")
        self.assertEqual(info["school_short"], "BC")
        self.assertEqual(info["type_key"], "sports")

    def test_neu_athletics_detected(self):
        e = {
            "name": "Northeastern University Men's Basketball vs Harvard",
            "venue": "Cabot Center",
            "_source_venue": "Northeastern Huskies Athletics",
            "date": "2026-11-11T00:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["school_key"], "neu")
        self.assertEqual(info["school_short"], "NEU")
        self.assertEqual(info["type_key"], "sports")

    def test_tufts_athletics_detected(self):
        e = {
            "name": "Tufts University Women's Volleyball vs Trinity",
            "venue": "Cousens Gymnasium",
            "_source_venue": "Tufts Jumbos Athletics",
            "date": "2026-11-14T00:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["school_key"], "tufts")
        self.assertEqual(info["school_short"], "Tufts")
        self.assertEqual(info["type_key"], "sports")

    def test_intercollegiate_ballroom_detected(self):
        e = {
            "name": "Harvard Invitational Ballroom Dance Competition",
            "venue": "Malkin Athletic Center",
            "_source_venue": "Harvard Ballroom Dance Team",
            "date": "2026-11-14T10:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["type_key"], "dance")
        self.assertTrue(info["is_intercollegiate"])

    def test_hackathon_detected(self):
        e = {
            "name": "HackBeanpot 2026",
            "venue": "Curry Student Center",
            "_source_venue": "HackBeanpot",
            "date": "2026-11-20T10:00:00+00:00",
            "price": "Free",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["type_key"], "tech")
        self.assertTrue(info["is_intercollegiate"])

    def test_free_with_student_id_detected(self):
        e = {
            "name": "Museum College Night",
            "venue": "Museum of Fine Arts",
            "_source_venue": "MFA",
            "date": "2026-11-12T18:00:00+00:00",
            "description": "Free admission with valid college student ID for all university students.",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["access_key"], "free_id")

    def test_regular_city_event_not_college(self):
        e = {
            "name": "The Burren Traditional Irish Session",
            "venue": "The Burren",
            "_source_venue": "The Burren",
            "date": "2026-11-11T20:00:00+00:00",
            "category": "music",
        }
        self.assertFalse(college.is_college_event(e))

    def test_harvard_college_ofa_detected(self):
        e = {
            "name": "Office for the Arts Presents Arts for Life's Sake: Yo-Yo Ma & Stephen Colbert",
            "venue": "Richard A. and Susan F. Smith Campus Center",
            "_source_venue": "Harvard College Events",
            "url": "https://events.college.harvard.edu/ofa/event/225033-office-for-the-arts-at-harvard-presents-arts-for",
            "date": "2026-11-12T18:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e))
        info = college.get_college_info(e)
        self.assertEqual(info["school_key"], "harvard")
        self.assertEqual(info["school_short"], "Harvard")

    def test_berklee_and_suffolk_detected(self):
        e_berklee = {
            "name": "Jazz Composers Alliance Orchestra in Concert",
            "venue": "Berklee Performance Center",
            "_source_venue": "Berklee College of Music",
            "url": "https://www.berklee.edu/events/jazz-composers-alliance",
            "date": "2026-11-15T20:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e_berklee))
        self.assertEqual(college.detect_school(e_berklee), "berklee")

        e_suffolk = {
            "name": "International Student Career Lab",
            "venue": "David J. Sargent Hall",
            "_source_venue": "Suffolk University Events",
            "url": "https://events.suffolk.edu/event/123",
            "date": "2026-11-12T14:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e_suffolk))
        self.assertEqual(college.detect_school(e_suffolk), "emerson")

    def test_mit_and_emerson_athletics_detected(self):
        e_mit = {
            "name": "MIT Men's Basketball vs Gordon",
            "venue": "Rockwell Cage",
            "_source_venue": "MIT Engineers Athletics",
            "url": "https://mitathletics.com/calendar.ashx/calendar.ics",
            "date": "2026-11-15T13:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e_mit))
        self.assertEqual(college.detect_school(e_mit), "mit")

        e_emerson = {
            "name": "Emerson Men's Soccer vs Clark",
            "venue": "Rotch Playground",
            "_source_venue": "Emerson Lions Athletics",
            "url": "https://emersonlions.com/calendar.ashx/calendar.ics",
            "date": "2026-11-12T18:00:00+00:00",
        }
        self.assertTrue(college.is_college_event(e_emerson))
        self.assertEqual(college.detect_school(e_emerson), "emerson")


class CollegeHubRenderingTests(unittest.TestCase):
    def setUp(self):
        self.hub = template.HUBS["college"]
        self.sample_events = [
            {
                "name": "Boston University Men's Ice Hockey vs Harvard",
                "date": "2026-11-11T00:00:00+00:00",
                "_time": datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc),
                "venue": "Agganis Arena",
                "_source_venue": "BU Terriers Athletics",
                "url": "https://goterriers.com/game/1",
                "category": "sports",
            },
            {
                "name": "Harvard Invitational Ballroom Dance Competition",
                "date": "2026-11-14T14:00:00+00:00",
                "_time": datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc),
                "venue": "Malkin Athletic Center",
                "_source_venue": "Harvard University",
                "url": "https://harvardballroom.org",
                "category": "dance",
            },
            {
                "name": "The Burren Traditional Irish Music Session",
                "date": "2026-11-11T20:00:00+00:00",
                "_time": datetime(2026, 11, 11, 20, 0, tzinfo=timezone.utc),
                "venue": "The Burren",
                "_source_venue": "The Burren",
                "url": "https://burren.com",
                "category": "music",
            },
        ]
        self.html = template.render_hub_page("college", self.sample_events)

    def test_hub_registered_correctly(self):
        self.assertIn("college", template.HUBS)
        self.assertEqual(self.hub["style"], "college")
        self.assertEqual(self.hub["query"], "#college=1")

    def test_hub_filters_only_college_events(self):
        filtered = template.filter_events_for_hub(self.hub, self.sample_events)
        names = [e["name"] for e in filtered]
        self.assertIn("Boston University Men's Ice Hockey vs Harvard", names)
        self.assertIn("Harvard Invitational Ballroom Dance Competition", names)
        self.assertNotIn("The Burren Traditional Irish Music Session", names)

    def test_hub_renders_collegiate_cards_and_badges(self):
        self.assertIn("col-card col-s-bu", self.html)
        self.assertIn("col-school-pill", self.html)
        self.assertIn("BU", self.html)
        self.assertIn("All-Colleges", self.html)
        self.assertIn("col-filters", self.html)
        self.assertIn("All Campuses", self.html)

    def test_streamlined_nav_header(self):
        self.assertIn('<nav class="hub-nav col-nav">', self.html)
        self.assertIn('<a href="../">All Events</a>', self.html)
        self.assertIn('<a href="../college/" class="active">College &amp; Student Events</a>', self.html)


class MainCalendarCollegeIntegrationTests(unittest.TestCase):
    def test_main_calendar_includes_college_toggle_and_tags(self):
        events = [
            {
                "name": "Boston University Men's Ice Hockey vs Harvard",
                "date": "2026-11-11T00:00:00+00:00",
                "_time": datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc),
                "venue": "Agganis Arena",
                "_source_venue": "BU Terriers Athletics",
                "url": "https://goterriers.com/game/1",
                "category": "sports",
            }
        ]
        venues = [{"venue": "BU Terriers Athletics", "url": "https://goterriers.com", "events": events}]
        html = template.render_page(venues)

        self.assertIn('id="college-only-chk"', html)
        self.assertIn('data-college="true"', html)
        self.assertIn('college-tag', html)
        self.assertIn('useful-students', html)
        self.assertIn('href="college/"', html)


if __name__ == "__main__":
    unittest.main()
