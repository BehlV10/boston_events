"""Venues added from the Boston Shows coverage check, the Boston Shows fallback for venues we
can't read, and the source health report. Fixtures are trimmed copies of each site's markup."""
import datetime as _dt
import os
import sys
import unittest
from unittest import mock

from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import scrapers  # noqa: E402
import source_health  # noqa: E402
from venues_geo import resolve_event_geo  # noqa: E402

FROZEN = _dt.datetime(2026, 11, 5, 12, 0, tzinfo=scrapers.EASTERN)


class _Frozen(_dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN.astimezone(tz) if tz else FROZEN.replace(tzinfo=None)


def _local(ev):
    return _dt.datetime.fromisoformat(ev["date"]).astimezone(scrapers.EASTERN)


class FrozenClock(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(scrapers, "datetime", _Frozen)
        p.start()
        self.addCleanup(p.stop)

    def soup(self, markup):
        p = mock.patch.object(scrapers, "fetch_soup", return_value=BeautifulSoup(markup, "html.parser"))
        p.start()
        self.addCleanup(p.stop)


class HelperTests(FrozenClock):
    def test_clock(self):
        self.assertEqual(scrapers._clock("7:30"), (19, 30))
        self.assertEqual(scrapers._clock("7 PM"), (19, 0))
        self.assertEqual(scrapers._clock("12:15 p.m."), (12, 15))
        self.assertEqual(scrapers._clock("11 am"), (11, 0))
        self.assertIsNone(scrapers._clock("no time here"))

    def test_month_day_picks_nearest_year(self):
        today = _dt.date(2026, 11, 5)
        self.assertEqual(scrapers._month_day("November", 10, today), _dt.date(2026, 11, 10))
        self.assertEqual(scrapers._month_day("Jan", 8, today), _dt.date(2027, 1, 8))
        self.assertEqual(scrapers._month_day("dec", 31, _dt.date(2027, 1, 2)), _dt.date(2026, 12, 31))
        self.assertIsNone(scrapers._month_day("Smarch", 1, today))

    def test_price_from_text(self):
        self.assertEqual(scrapers._price_from_text("$15 (cash or Venmo at the door). Doors 7 PM."), "$15")
        self.assertEqual(scrapers._price_from_text("Free entry, all ages"), "Free")
        self.assertIsNone(scrapers._price_from_text("Doors at 7"))


class ElfsightTests(unittest.TestCase):
    start, end = _dt.date(2026, 11, 5), _dt.date(2026, 11, 26)

    def test_weekly_with_skip_and_reschedule(self):
        ev = {"start": {"date": "2026-10-01", "time": "19:00"}, "repeatPeriod": "weeklyOn",
              "repeatWeeklyOnDays": ["th"], "repeatInterval": 1, "repeatEnds": "never",
              "exceptions": [
                  {"originalDate": int(_dt.datetime(2026, 11, 12, tzinfo=_dt.timezone.utc).timestamp() * 1000),
                   "type": "skip"},
                  {"originalDate": int(_dt.datetime(2026, 11, 19, tzinfo=_dt.timezone.utc).timestamp() * 1000),
                   "type": "reschedule", "rescheduledStart": {"date": "2026-11-20", "time": "20:00"}}]}
        got = sorted(scrapers._elfsight_occurrences(ev, self.start, self.end))
        self.assertEqual(got, [(_dt.date(2026, 11, 5), "19:00"), (_dt.date(2026, 11, 20), "20:00"),
                               (_dt.date(2026, 11, 26), "19:00")])

    def test_nth_weekday_and_end_date(self):
        # First Saturday of the month
        ev = {"start": {"date": "2026-10-03", "time": "15:00"}, "repeatPeriod": "nthDayInMonth"}
        self.assertEqual(scrapers._elfsight_occurrences(ev, self.start, _dt.date(2026, 12, 31)),
                         [(_dt.date(2026, 11, 7), "15:00"), (_dt.date(2026, 12, 5), "15:00")])
        weekly = {"start": {"date": "2026-11-02", "time": "21:00"}, "repeatPeriod": "weeklyOn",
                  "repeatWeeklyOnDays": ["mo"], "repeatEnds": "onDate", "repeatEndsDate": "2026-11-10"}
        self.assertEqual(scrapers._elfsight_occurrences(weekly, self.start, self.end),
                         [(_dt.date(2026, 11, 9), "21:00")])

    def test_toad_venues_by_location(self):
        settings = {"locations": [{"id": "a", "name": "Toad"}, {"id": "b", "name": "Upstairs @ McCarthys"}],
                    "events": [
                        {"name": "Late Night Cover Band", "location": ["a"], "description": "<p>Free!</p>",
                         "start": {"date": "2026-11-06", "time": "22:30"}},
                        {"name": "Irish Session", "location": ["b"], "start": {"date": "2026-11-06", "time": "19:00"}}]}
        with mock.patch.object(scrapers, "_elfsight_settings", return_value=settings), \
                mock.patch.object(scrapers, "datetime", _Frozen):
            evs = scrapers.scrape_toad("https://www.mccarthystoad.com/calendar", scrapers.UA_CHROME)
        self.assertEqual([(e["name"], e["venue"], e["price"]) for e in evs],
                         [("Late Night Cover Band", "Toad", "Free"), ("Irish Session", "McCarthy's", None)])
        self.assertEqual(_local(evs[0]).strftime("%m-%d %H:%M"), "11-06 22:30")


class VenuePageTests(FrozenClock):
    def test_underbones_happenings_and_recurrence(self):
        self.soup("""<ul>
          <li class="rb-event" data-category="music"><a href="/happenings/spirit-hotel">
            <span class="rb-event__day">7</span><span class="rb-event__month">Nov</span>
            <span class="rb-event__venue">Underbones</span><h3 class="rb-event__title">Spirit Hotel, Cult Objects</h3>
            <span class="rb-event__time">7:00 PM - 11:00 PM</span>
            <p>$15 (cash or Venmo at the door). Doors 7 PM. Show 8–11 PM.</p></a></li>
          <li class="rb-event" data-category="trivia">
            <span class="rb-event__day">6</span><span class="rb-event__month">Nov</span>
            <span class="rb-event__venue">Underbones</span><h3 class="rb-event__title">Phrenology Trivia</h3>
            <span class="rb-event__time">7:00 PM - 9:00 PM</span><p>Free. Every Friday until 20 Nov</p></li>
        </ul>""")
        evs = scrapers.scrape_underbones("https://redbones.com/happenings/", scrapers.UA_CHROME)
        show = evs[0]
        self.assertEqual((show["venue"], show["price"], show["category"]), ("Underbones", "$15", "music"))
        self.assertEqual(show["url"], "https://redbones.com/happenings/spirit-hotel")
        trivia = [_local(e).date().day for e in evs if e["name"] == "Phrenology Trivia"]
        self.assertEqual(trivia, [6, 13, 20])
        self.assertTrue(all(e["category"] == "gaming" for e in evs if e["name"] == "Phrenology Trivia"))

    def test_postunderground(self):
        self.soup("""<div><h3>Friday, November 6th</h3><p>7:30</p><p>First Friday Feature:</p>
          <p>(bands performing here for the first time) Nathaniel Plocinski Group (all the way from Maine)!</p>
          <p>8:30</p><p>The Jazz Situation:</p><p>Joe Smith, sax; Ann Lee, bass</p>
          <h3>Sunday, November 8th</h3><p>7 PM: The POSTunderground Jazz Institute Orchestra performs Ellington</p></div>""")
        evs = scrapers.scrape_postunderground("https://postunderground.com/", scrapers.UA_CHROME)
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M")) for e in evs],
                         [("Nathaniel Plocinski Group", "11-06 19:30"), ("The Jazz Situation", "11-06 20:30"),
                          ("The POSTunderground Jazz Institute Orchestra", "11-08 19:00")])
        self.assertTrue(all(e["price"] == "Free" for e in evs))

    def test_lower_mills_tavern(self):
        self.soup("<p>November 5th - The Joneses</p><p>November 10th - Joe Sabourin</p>"
                  "<p>November 26th - CLOSED Happy Thanksgiving</p>")
        evs = scrapers.scrape_lower_mills_tavern("https://www.lowermillstavern.com/livemusicschedule/", "")
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M")) for e in evs],
                         [("The Joneses", "11-05 19:30"), ("Joe Sabourin", "11-10 19:00")])

    def test_kings_chapel(self):
        self.soup("""<p>Recitals are free; $5 suggested donation.</p><h2>Upcoming Performances</h2>
          <p>Ariel Woodwind Quintet</p><p>Tuesday, November 17, 12:15 p.m.</p>
          <h3>Recitals - December</h3><p>1</p><p>Jane Doe, organ</p>""")
        evs = scrapers.scrape_kings_chapel("https://www.kings-chapel.org/music/tuesday-recitals", "")
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M"), e["price"]) for e in evs],
                         [("Ariel Woodwind Quintet", "11-17 12:15", "$5 suggested"),
                          ("Jane Doe, organ", "12-01 12:15", "$5 suggested")])

    def test_off_the_rails_keeps_free_nights(self):
        self.soup("""<ul>
          <li class="otr-rise"><a href="/events/thursday-acoustics"><span>Thu</span><span>5</span><span>Nov</span>
            <h3>Thursday Night Acoustics</h3><span>Show 7:00 PM · Ends 9:00 PM</span><span>Free entry</span></a></li>
          <li class="otr-rise"><a href="/events/anthony-calla"><span>Fri</span><span>6</span><span>Nov</span>
            <h3>Anthony Calla</h3><span>Doors 7:00 PM · Show 8:00 PM</span><span>$17.20</span><span>with fees</span></a></li>
        </ul>""")
        evs = scrapers.scrape_off_the_rails("https://www.offtherailsboston.com/events", "")
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M"), e["price"]) for e in evs],
                         [("Thursday Night Acoustics", "11-05 19:00", "Free"), ("Anthony Calla", "11-06 20:00", "$17.20")])
        self.assertEqual(evs[1]["url"], "https://www.offtherailsboston.com/events/anthony-calla")


class _Resp:
    def __init__(self, text="", data=None):
        self.text, self._data, self.status_code = text, data, 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class ExistingVenueFixTests(FrozenClock):
    def test_brattle_reads_dated_showtimes(self):
        nov5 = int(_dt.datetime(2026, 11, 5, tzinfo=_dt.timezone.utc).timestamp())
        self.soup(f"""<div class="show-list"><div class="show-details">
          <h2>Begotten</h2><a href="https://brattlefilm.org/movies/begotten/">details</a>
          <ol class="showtimes"><li data-date="{nov5}"><a data-showtime_id="1" href="/purchase/1/">10:30 pm</a></li>
          <li data-date="{nov5 + 86400}"><a data-showtime_id="2" href="/purchase/2/">10:30 pm</a></li></ol>
        </div></div>""")
        evs = scrapers.scrape_brattle("https://www.brattlefilm.org/", scrapers.UA_CHROME)
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M")) for e in evs],
                         [("Begotten", "11-05 22:30"), ("Begotten", "11-06 22:30")])
        self.assertEqual(evs[0]["url"], "https://brattlefilm.org/movies/begotten/")

    def test_obriens_store_api(self):
        products = [
            {"sku": "20261114-2", "name": "Jordan Dean W/ Ecce Shnak", "permalink": "https://obrienspubboston.com/show/jordan-dean/",
             "short_description": "<p>Saturday, November 14, 2026 7PM 21+</p>", "is_in_stock": True,
             "prices": {"price": "1860", "currency_minor_unit": 2}},
            {"sku": "20261107-1", "name": "Puppy Pile", "short_description": "Saturday, November 7 2PM 21+",
             "is_in_stock": False, "prices": {"price": "1255", "currency_minor_unit": 2}},
            {"sku": "20261101", "name": "Already happened", "prices": {"price": "1000"}},
        ]
        with mock.patch.object(scrapers._SESSION, "get", return_value=_Resp(data=products)):
            evs = scrapers.scrape_obriens_pub("https://obrienspubboston.com/", scrapers.UA_CHROME)
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M"), e["price"]) for e in evs],
                         [("Jordan Dean W/ Ecce Shnak", "11-14 19:00", "$18.60"),
                          ("Puppy Pile", "11-07 14:00", "$12.55 (sold out)")])

    def test_mad_monkfish_follows_load_more(self):
        page1 = ('<a href="/event/115-trio/">11/5 Trio 7pm</a>'
                 '<div class="paginator" data-paginator-next-url="/jazz-schedule/?p=2"></div>')
        page2 = '<a href="/event/1113-yoko-miwa-trio/">11/13 Yoko Miwa Trio 9pm</a>'
        with mock.patch.object(scrapers._SESSION, "get", side_effect=[_Resp(page1), _Resp(page2)]) as get:
            evs = scrapers.scrape_mad_monkfish("https://www.themadmonkfish.com/jazz-schedule/", scrapers.UA_CHROME)
        self.assertEqual(get.call_args_list[1].args[0], "https://www.themadmonkfish.com/jazz-schedule/?p=2")
        self.assertEqual([(e["name"], _local(e).strftime("%m-%d %H:%M")) for e in evs],
                         [("Live Jazz: Trio", "11-05 19:00"), ("Live Jazz: Yoko Miwa Trio", "11-13 21:00")])


    def test_meetup_shell_page_raises_but_past_only_group_is_empty(self):
        import json as _json

        def page(state):
            data = {"props": {"pageProps": {"__APOLLO_STATE__": state}}}
            return _Resp(f'<script id="__NEXT_DATA__" type="application/json">{_json.dumps(data)}</script>')

        url = "https://www.meetup.com/some-group/events/"
        with mock.patch.object(scrapers._SESSION, "get", return_value=page({"ROOT_QUERY": {}})):
            with self.assertRaises(RuntimeError):  # crawl falls back to the cached list
                scrapers.scrape_meetup_group(url, scrapers.UA_CHROME)
        past = {"Event:1": {"status": "PAST", "dateTime": "2025-04-12T19:00:00-04:00", "eventUrl": url + "1/"}}
        with mock.patch.object(scrapers._SESSION, "get", return_value=page(past)):
            self.assertEqual(scrapers.scrape_meetup_group(url, scrapers.UA_CHROME), [])


class BostonShowsGapTests(FrozenClock):
    def test_only_venues_we_cant_read(self):
        self.soup("""<div class="date-events" data-date="2026-11-05"><table>
          <tr class="event" data-venue="Wally's Cafe"><td class="event-start">7:00pm</td>
            <td class="event-title"><a href="https://wallyscafe.com/ritual/">Benjamin Kassner Quintet</a></td>
            <td class="event-info">free / 21+</td></tr>
          <tr class="event" data-venue="The Sinclair"><td class="event-start">8:00pm</td>
            <td class="event-title"><a href="https://sinclair.example/">Someone We Already Have</a></td>
            <td class="event-info">$25 / 18+</td></tr>
          <tr class="event" data-venue="The Black Rose"><td class="event-start">9:30pm</td>
            <td class="event-title">Erin's Guild</td><td class="event-info">$10 / 21+</td></tr>
        </table></div>
        <div class="date-events" data-date="2026-12-30"><table>
          <tr class="event" data-venue="Wally's Cafe"><td class="event-start">7pm</td>
            <td class="event-title">Too far out</td><td class="event-info">free</td></tr></table></div>""")
        evs = scrapers.scrape_boston_shows_gaps("https://bostonshows.org/", scrapers.UA_CHROME)
        self.assertEqual([(e["name"], e["venue"], e["price"], _local(e).strftime("%H:%M")) for e in evs],
                         [("Benjamin Kassner Quintet", "Wally's Café", "Free", "19:00"),
                          ("Erin's Guild", "The Black Rose", "$10", "21:30")])
        self.assertTrue(all("Boston Shows" in e["description"] for e in evs))

    def test_gap_venues_are_listed_as_unreadable_and_have_locations(self):
        for ours in scrapers.BOSTON_SHOWS_GAP_VENUES.values():
            self.assertIsNotNone(resolve_event_geo({"venue": ours}), ours)
        self.assertGreaterEqual(len(source_health.KNOWN_UNSCRAPABLE), len(scrapers.BOSTON_SHOWS_GAP_VENUES) - 1)

    def test_wallys_placeholder_removed(self):
        src = open(os.path.join(BASE_DIR, "scrapers.py"), encoding="utf-8").read()
        self.assertNotIn('("Wally\'s Café", "https://www.wallyscafe.com/events"', src)


class NewVenueTests(unittest.TestCase):
    NEW = ["Square Root", "POSTunderground", "Lower Mills Tavern", "King's Chapel", "Faces Brewing", "GBH Events",
           "Jazz Urbane Cafe", "Medford Brewing Company", "Village Social Club", "Luthier Collective",
           "Boston Shows (venues we can't read)"]

    def test_registered(self):
        names = {v["name"] for v in scrapers._ALL_VENUES}
        for n in self.NEW:
            self.assertIn(n, names)
        urls = {v["name"]: v["url"] for v in scrapers._ALL_VENUES}
        self.assertEqual(urls["Underbones"], "https://redbones.com/happenings/")
        self.assertEqual(urls["Off the Rails Boston"], "https://www.offtherailsboston.com/events")

    def test_locations(self):
        expect = {"Square Root": "Roslindale", "POSTunderground": "Brookline Village", "Lower Mills Tavern": "Lower Mills",
                  "King's Chapel": "Downtown", "Faces Brewing": "Malden Center", "Jazz Urbane Cafe": "Nubian Square",
                  "Medford Brewing Company": "West Medford", "Village Social Club": "Brookline Village",
                  "Luthier Collective": "Spring Hill", "GBH Fraser Performance Studio": "Brighton",
                  "Boston Public Library (Shaw-Roxbury)": "Nubian Square", "Toad": "Porter Square",
                  "Underbones": "Davis Square"}
        for venue, hood in expect.items():
            self.assertEqual((resolve_event_geo({"venue": venue}) or {}).get("neighborhood"), hood, venue)


class SourceHealthTests(unittest.TestCase):
    def test_statuses(self):
        now = _dt.datetime(2026, 11, 5, 17, 0, tzinfo=_dt.timezone.utc)
        soon, later = "2026-11-08T00:00:00+00:00", "2026-12-20T00:00:00+00:00"
        venues = [
            {"venue": "Good", "url": "https://good.example/", "events": [{"date": soon}]},
            {"venue": "Seasonal", "url": "https://later.example/", "events": [{"date": later}]},
            {"venue": "Broken", "url": "https://broken.example/", "events": [], "error": "HTTP 500"},
            {"venue": "Blocked", "url": "https://www.blocked.example/x", "events": [{"date": soon}]},
        ]
        rows = source_health.source_status(venues, refused={"blocked.example": "403 Forbidden"}, now=now)
        got = {r["source"]: (r["status"], r["next_two_weeks"], r["next_event"]) for r in rows}
        self.assertEqual(got, {"Broken": ("error", 0, None), "Blocked": ("refused", 1, "2026-11-08"),
                               "Seasonal": ("empty", 0, "2026-12-20"), "Good": ("ok", 1, "2026-11-08")})
        self.assertEqual([r["source"] for r in rows], ["Broken", "Blocked", "Seasonal", "Good"])

    def test_report_written_to_cache_and_summary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            summary = os.path.join(d, "summary.md")
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary}), mock.patch("builtins.print"):
                source_health.write_report([{"venue": "Quiet", "url": "https://q.example/", "events": []}],
                                           path=os.path.join(d, "status.json"))
            md = open(summary, encoding="utf-8").read()
            self.assertIn("| [Quiet](https://q.example/) | empty |", md)
            self.assertIn("Venues we can't read", md)
            self.assertTrue(os.path.exists(os.path.join(d, "status.json")))


if __name__ == "__main__":
    unittest.main()
