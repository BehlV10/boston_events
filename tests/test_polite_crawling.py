"""Polite crawling: per-site limits, backing off when a site says no, never dodging a refusal.

Measured on a full crawl before this change: 1,014 requests to The Boston Calendar 25 at a time,
Boston Children's Museum answering 504 at four at a time, Eventbrite/Meetup/Ticketmaster at seven
at a time, and Porter Square Books' 403s retried through curl.
"""
import inspect
import os
import sys
import threading
import time
import unittest
from unittest import mock

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapers  # noqa: E402
from scrapers import HOST_GATE, SiteRefused, _host_policy  # noqa: E402


def _resp(status, headers=None):
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = b""
    return r


class _FakeNetwork:
    """Stands in for requests.Session.request: records concurrency and answers from a script."""

    def __init__(self, answers=None, delay=0.02):
        self.answers = list(answers or [])
        self.delay = delay
        self.calls = []
        self.active = {}
        self.peak = {}
        self.lock = threading.Lock()

    def __call__(self, method, url, *a, **kw):
        host = scrapers._host_of(url)
        with self.lock:
            self.calls.append((time.monotonic(), host))
            self.active[host] = self.active.get(host, 0) + 1
            self.peak[host] = max(self.peak.get(host, 0), self.active[host])
        time.sleep(self.delay)
        with self.lock:
            self.active[host] -= 1
            status = self.answers.pop(0) if self.answers else 200
        return status if isinstance(status, requests.Response) else _resp(status)


class PoliteSessionTest(unittest.TestCase):
    def setUp(self):
        HOST_GATE.reset()
        self.sleeps = []
        # Keep the real pacing but shrink it so the test is fast.
        self.policy = mock.patch.dict(scrapers.HOST_POLICY, {"eventbrite.com": (1, 0.03)})
        self.policy.start()
        self.default = mock.patch.object(scrapers, "HOST_POLICY_DEFAULT", (2, 0.0))
        self.default.start()

    def tearDown(self):
        self.policy.stop()
        self.default.stop()
        HOST_GATE.reset()

    def _fetch_all(self, urls):
        threads = [threading.Thread(target=lambda u=u: scrapers._SESSION.get(u)) for u in urls]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_one_at_a_time_and_spaced_for_bot_protected_sites(self):
        net = _FakeNetwork()
        with mock.patch.object(requests.Session, "request", net):
            self._fetch_all([f"https://www.eventbrite.com/d/ma--boston/events/?page={i}" for i in range(5)])
        self.assertEqual(net.peak["www.eventbrite.com"], 1)
        starts = sorted(t for t, _ in net.calls)
        gaps = [b - a for a, b in zip(starts, starts[1:])]
        self.assertTrue(all(g >= 0.02 for g in gaps), gaps)  # 30ms apart, less thread wake-up jitter

    def test_at_most_two_at_a_time_elsewhere(self):
        net = _FakeNetwork(delay=0.05)
        with mock.patch.object(requests.Session, "request", net):
            self._fetch_all([f"https://www.thebostoncalendar.com/events/e{i}" for i in range(8)])
        self.assertEqual(net.peak["www.thebostoncalendar.com"], 2)

    def test_policy_matches_subdomains(self):
        self.assertEqual(_host_policy("www.meetup.com"), scrapers.HOST_POLICY["meetup.com"])
        self.assertEqual(_host_policy("bostonchildrensmuseum.org"), (1, 1.0))
        self.assertEqual(_host_policy("example.org"), scrapers.HOST_POLICY_DEFAULT)

    def test_429_waits_retry_after_then_stops_asking(self):
        net = _FakeNetwork([_resp(429, {"Retry-After": "7"}), 429])
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            r = scrapers._SESSION.get("https://www.meetup.com/find/?page=1")
            self.assertEqual(r.status_code, 429)
            self.assertIn(7, self.sleeps)
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://www.meetup.com/find/?page=2")
        self.assertEqual(len(net.calls), 2, "one retry, then no more requests to that site")

    def test_403_is_never_retried(self):
        net = _FakeNetwork([403])
        with mock.patch.object(requests.Session, "request", net):
            self.assertEqual(scrapers._SESSION.get("https://portersquarebooks.com/events").status_code, 403)
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://portersquarebooks.com/events/2026/12")
        self.assertEqual(len(net.calls), 1)
        # Other sites are unaffected, and the next crawl asks again.
        with mock.patch.object(requests.Session, "request", _FakeNetwork([200])):
            self.assertEqual(scrapers._SESSION.get("https://www.harvard.com/events").status_code, 200)
        HOST_GATE.reset()
        with mock.patch.object(requests.Session, "request", _FakeNetwork([200])):
            self.assertEqual(scrapers._SESSION.get("https://portersquarebooks.com/events").status_code, 200)

    def test_overloaded_site_gets_one_retry_then_a_rest(self):
        net = _FakeNetwork([504, 200])
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            self.assertEqual(scrapers._SESSION.get("https://bostonchildrensmuseum.org/events/a").status_code, 200)
        self.assertEqual(len(net.calls), 2)
        net = _FakeNetwork([504] * 2 * scrapers.OVERLOADED_AFTER)
        with mock.patch.object(requests.Session, "request", net), \
                mock.patch.object(scrapers.time, "sleep", side_effect=self.sleeps.append):
            for i in range(scrapers.OVERLOADED_AFTER):
                scrapers._SESSION.get(f"https://bostonchildrensmuseum.org/events/{i}")
            with self.assertRaises(SiteRefused):
                scrapers._SESSION.get("https://bostonchildrensmuseum.org/events/next")


class RefusedSourceKeepsDataTest(unittest.TestCase):
    def tearDown(self):
        HOST_GATE.reset()

    def test_last_good_events_survive_a_refusal(self):
        old = [{"name": "Author Talk", "date": "2026-12-01T23:00:00+00:00", "url": "https://portersquarebooks.com/e/1",
                "venue": "Porter Square Books"}]

        def blocked_scraper(url, ua):
            HOST_GATE.refuse("portersquarebooks.com", "403")
            return []

        v = {"name": "Porter Square Books", "url": "https://portersquarebooks.com/events", "ua": "UA",
             "scraper": blocked_scraper, "default_category": "books"}
        with mock.patch.object(scrapers, "_load_venue_cache", side_effect=[None, {"events": old}]), \
                mock.patch.object(scrapers, "_save_venue_cache") as save, \
                mock.patch.object(scrapers, "_normalize_and_filter_events", side_effect=lambda evs, v: list(evs)):
            res = scrapers._scrape_one(v)
        self.assertEqual([e["name"] for e in res["events"]], ["Author Talk"])
        self.assertTrue(res["fallback"])
        save.assert_not_called()


class NoDodgingTest(unittest.TestCase):
    def test_no_curl_retries(self):
        src = inspect.getsource(scrapers)
        self.assertNotIn('"curl"', src)
        self.assertNotIn("subprocess", src)

    def test_boston_calendar_catch_up_is_spread_out(self):
        self.assertLessEqual(scrapers.TBC_DETAILS_PER_RUN, 150)
        self.assertNotIn("max_workers=25", inspect.getsource(scrapers.scrape_boston_calendar))


if __name__ == "__main__":
    unittest.main()
