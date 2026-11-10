"""College athletics feeds (Sidearm Sports calendar.ashx iCal) and date-only "Time TBA" listings."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers
import template
from scrapers import EASTERN


def _stamp(days, hour=19):
    dt = (datetime.now(EASTERN) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return dt.astimezone(scrapers.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _day(days):
    return (datetime.now(EASTERN) + timedelta(days=days)).strftime("%Y%m%d")


def _vevent(summary, location, start, all_day=False, uid="x"):
    head = "DTSTART;VALUE=DATE" if all_day else "DTSTART"
    return (f"BEGIN:VEVENT\r\nUID:{uid}\r\n{head}:{start}\r\nLOCATION:{location}\r\n"
            f"SUMMARY:{summary}\r\nURL:https://admin.bceagles.com/calendar.aspx?game_id=1&amp;sport_id=2\r\nEND:VEVENT\r\n")


def _feed(*vevents):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(vevents) + "END:VCALENDAR\r\n").encode("utf-8")


def _scrape(body, url="https://bceagles.com/calendar.ashx/calendar.ics"):
    reply = mock.Mock(status_code=200, content=body)
    reply.raise_for_status = lambda: None
    with mock.patch.object(scrapers, "_SESSION") as session:
        session.get.return_value = reply
        return scrapers.scrape_college_athletics(url, "ua")


class SidearmLocation(unittest.TestCase):
    def test_forms_seen_in_the_feeds(self):
        loc = scrapers._sidearm_location
        self.assertEqual(loc("Boston, MA"), ("boston", "ma", ""))
        self.assertEqual(loc("Medford, MA / Cousens Gym"), ("medford", "ma", "Cousens Gym"))
        self.assertEqual(loc("Chestnut Hill\\, Mass.\\, Conte Forum"), ("chestnut hill", "mass", "Conte Forum"))
        self.assertEqual(loc("Chestnut, Hill"), ("chestnut hill", "", ""))
        self.assertEqual(loc(", Conte Forum"), ("", "", "Conte Forum"))
        self.assertEqual(loc("South Portland, Maine (Wainwright Recreation Complex)"),
                         ("south portland", "maine", "Wainwright Recreation Complex"))
        self.assertEqual(loc("TBA"), ("tba", "", ""))
        self.assertEqual(loc(""), (None, "", ""))


class CollegeAthletics(unittest.TestCase):
    def test_home_game_gets_curated_venue_and_coordinates(self):
        events = _scrape(_feed(_vevent("[W] Boston College Women's Hockey vs Providence College", ", Conte Forum", _stamp(3))))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e["name"], "Boston College Women's Hockey vs Providence College")  # result tag dropped
        self.assertEqual((e["venue"], e["category"]), ("Conte Forum", "sports"))
        self.assertAlmostEqual(e["lat"], 42.3353, places=3)
        self.assertEqual(e["url"], "https://bceagles.com/calendar.aspx?game_id=1&sport_id=2")

    def test_home_game_without_facility_uses_the_schools_home_venue(self):
        events = _scrape(_feed(_vevent("Boston College Football vs Syracuse", "Chestnut Hill, Mass.", _stamp(3))))
        self.assertEqual(events[0]["venue"], "Conte Forum")

    def test_far_away_and_out_of_state_games_are_dropped(self):
        body = _feed(_vevent("Boston College Sailing at Hewitt Trophy", "Brunswick, ME", _stamp(2), uid="1"),
                     _vevent("Boston College Football vs Stanford", "Stanford, CA", _stamp(2), uid="2"),
                     _vevent("BC Women's Hockey vs Penn State", "Arlington, Va.", _stamp(2), uid="3"),
                     _vevent("BC Track vs Invite", "Worcester, Mass.", _stamp(2), uid="4"))
        self.assertEqual(_scrape(body), [])

    def test_unplaceable_games_are_dropped(self):
        body = _feed(_vevent("BC Women's Hockey vs Penn State", ", MedStar Capitals Iceplex", _stamp(2), uid="1"),
                     _vevent("MIT Volleyball vs NEWMAC Semifinals", "TBA", _day(2), all_day=True, uid="2"),
                     _vevent("Tufts Hockey vs Albertus Magnus", "Boston, MA", _stamp(2), uid="3"))
        self.assertEqual(_scrape(body), [])

    def test_local_away_game_kept_only_when_the_host_is_not_scraped(self):
        body = _feed(_vevent("Boston College Women's Hockey at Boston University", "Boston, MA", _stamp(2), uid="1"),
                     _vevent("Boston College Men's Hockey at Harvard", "Boston, MA", _stamp(3), uid="2"),
                     _vevent("Boston College Women's Basketball at Suffolk University", "Boston, MA", _stamp(4), uid="3"))
        names = {e["name"]: e["venue"] for e in _scrape(body)}
        self.assertEqual(names, {"Boston College Men's Hockey at Harvard": "Harvard Athletics",
                                 "Boston College Women's Basketball at Suffolk University": "Suffolk Athletics (Ridgeway Gym)"})

    def test_unknown_facility_in_a_known_town_is_pinned_to_the_town(self):
        events = _scrape(_feed(_vevent("Tufts University Men's Ice Hockey vs Williams College", "Malden, MA / Malden Valley Forum",
                                       _stamp(5))), url="https://gotuftsjumbos.com/calendar.ashx/calendar.ics")
        self.assertEqual(events[0]["venue"], "Malden Valley Forum")
        self.assertEqual(events[0]["neighborhood"], "Malden")

    def test_tournament_name_in_facility_field_is_not_a_venue(self):
        events = _scrape(_feed(_vevent("Brandeis Women's Fencing vs Carla-Mae Richards Invitational",
                                       "Waltham, MA / Carla-Mae Richards Invitational", _stamp(5))),
                         url="https://brandeisjudges.com/calendar.ashx/calendar.ics")
        self.assertEqual(events[0]["venue"], "Gosman Sports Center (Brandeis)")

    def test_all_day_game_is_date_only(self):
        events = _scrape(_feed(_vevent("Boston College Football vs Syracuse", "Chestnut Hill, Mass., Alumni Stadium",
                                       _day(4), all_day=True)))
        self.assertRegex(events[0]["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(events[0]["venue"], "Alumni Stadium (BC)")

    def test_utf8_feed_without_charset_is_decoded(self):
        body = _feed(_vevent("Boston University Women’s Basketball vs UMass Boston", 'Boston, MA / Case Gym – "The Roof"',
                             _stamp(2)))
        events = _scrape(body, url="https://goterriers.com/calendar.ashx/calendar.ics")
        self.assertIn("Women’s", events[0]["name"])
        self.assertEqual(events[0]["venue"], "Case Gym")

    def test_bot_wall_page_returns_nothing(self):
        self.assertEqual(_scrape(b"<html><script src='/_Incapsula_Resource'></script></html>"), [])


class GameDeduplication(unittest.TestCase):
    """How athletics listings merge with each other and with Ticketmaster/SeatGeek."""

    def _game(self, name, venue, source, hour=16, url=None, date=None):
        t = datetime(2026, 11, 14, hour, 0, tzinfo=EASTERN)
        return {"name": name, "venue": venue, "_source_venue": source, "category": "sports", "_time": t,
                "date": date or t.astimezone(scrapers.timezone.utc).isoformat(), "url": url or ""}

    def test_game_pages_keep_their_game_id(self):
        self.assertEqual(template._clean_event_url("https://goterriers.com/calendar.aspx?game_id=33154&sport_id=16"),
                         "https://goterriers.com/calendar.aspx?game_id=33154")

    def test_two_games_from_one_feed_on_one_day_stay_separate(self):
        # Before game_id was kept, every Sidearm link cleaned to ".../calendar.aspx" and a timed game
        # merged into a "Time TBA" game from the same feed.
        hockey = self._game("Boston University Women's Ice Hockey vs Boston College", "Walter Brown Arena",
                            "BU Terriers Athletics", url="https://goterriers.com/calendar.aspx?game_id=1&sport_id=16")
        soccer = self._game("Boston University Men's Soccer vs PL Final", "Nickerson Field", "BU Terriers Athletics",
                            hour=0, date="2026-11-14", url="https://goterriers.com/calendar.aspx?game_id=2&sport_id=8")
        self.assertEqual(len(template._merge_duplicates([soccer, hockey], {})), 2)

    def test_ticket_seller_listings_fold_into_the_schools_own(self):
        own = self._game("Boston University Women's Ice Hockey vs Boston College - Faculty & Staff Appreciation",
                         "Walter Brown Arena", "BU Terriers Athletics")
        tm = self._game("Boston University Womens Hockey vs. Boston College Womens Hockey", "Walter Brown Arena", "Ticketmaster")
        sg = self._game("Boston College Eagles at Boston University Terriers Womens Hockey", "Walter Brown Arena", "SeatGeek")
        freq = template.title_word_freq([own, tm, sg])
        self.assertEqual(len(template._merge_duplicates([tm, sg, own], freq)), 1)

    def test_mens_and_womens_games_at_the_same_time_stay_separate(self):
        men = self._game("Tufts University Men's Squash vs Cornell University", "Tufts Athletics", "Tufts Jumbos Athletics")
        women = self._game("Tufts University Women's Squash vs Cornell University", "Tufts Athletics", "Tufts Jumbos Athletics")
        freq = template.title_word_freq([men, women])
        self.assertEqual(len(template._merge_duplicates([men, women], freq)), 2)

    def test_different_rinks_sharing_a_generic_word_stay_separate(self):
        bc = self._game("Boston College Men's Hockey vs UMass Lowell", "Conte Forum", "Boston College Eagles Athletics", hour=19)
        tufts = self._game("Tufts University Men's Ice Hockey vs Williams College", "Malden Valley Forum",
                           "Tufts Jumbos Athletics", hour=19)
        freq = template.title_word_freq([bc, tufts])
        self.assertEqual(len(template._merge_duplicates([bc, tufts], freq)), 2)


class DateOnlyListings(unittest.TestCase):
    def test_main_page_says_time_tba(self):
        e = {"date": "2026-11-21", "_time": datetime(2026, 11, 21, tzinfo=EASTERN)}
        self.assertEqual(template.format_when(e), "Time TBA")

    def test_hub_card_says_time_tba(self):
        e = {"date": "2026-11-21"}
        self.assertEqual(template._hub_time_label(e, datetime(2026, 11, 21, tzinfo=EASTERN)), "Time TBA")
        e = {"date": "2026-11-21T05:00:00+00:00"}
        self.assertEqual(template._hub_time_label(e, datetime(2026, 11, 21, tzinfo=EASTERN)), "All day")

    def test_today_date_only_listing_is_kept_all_day(self):
        today = datetime.now(EASTERN).date()
        source = {"name": "BU Terriers Athletics", "default_category": "sports"}
        kept = scrapers._normalize_and_filter_events(
            [{"name": "BU Soccer vs PL Final", "date": today.isoformat(), "venue": "Nickerson Field", "category": "sports"},
             {"name": "BU Soccer vs Lehigh", "date": (today - timedelta(days=1)).isoformat(), "venue": "Nickerson Field",
              "category": "sports"}], source)
        self.assertEqual([e["name"] for e in kept], ["BU Soccer vs PL Final"])


if __name__ == "__main__":
    unittest.main()
