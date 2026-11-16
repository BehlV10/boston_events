"""Flyer submissions: website passthrough, Boston-time dates, source probing and discovered sources."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers  # noqa: E402
import template  # noqa: E402


def _load_script(name):
    # Loaded by path: putting scripts/ on sys.path would shadow tests/test_scrapers.py.
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ace = _load_script("add_community_event")
probe_source = _load_script("probe_source")


def _future(days=10):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0)


class SubmissionTest(unittest.TestCase):
    def test_naive_time_is_boston_time_and_website_kept(self):
        when = _future().strftime("%Y-%m-%d") + "T20:00:00"
        e = ace.validate_and_normalize({"name": "Swing", "venue": "The Rockwell", "date": when,
                                        "website": "https://example.org"})
        dt = datetime.fromisoformat(e["date"])
        self.assertEqual(dt.astimezone(scrapers.EASTERN).hour, 20)
        self.assertEqual(e["website"], "https://example.org")

    def test_bad_website_dropped(self):
        when = _future().strftime("%Y-%m-%d")
        e = ace.validate_and_normalize({"name": "Swing", "venue": "Rockwell", "date": when, "website": "javascript:alert(1)"})
        self.assertNotIn("website", e)


class ProbeTest(unittest.TestCase):
    def test_skips_social_ip_and_known_sites(self):
        self.assertFalse(probe_source.probe("https://instagram.com/venue")["found"])
        self.assertFalse(probe_source.probe("http://10.0.0.1/events")["found"])
        known = next(v["url"] for v in scrapers._ALL_VENUES if "eventbrite" not in v["url"])
        r = probe_source.probe(known)
        self.assertFalse(r["found"])
        self.assertIn("already a source", r["reason"])

    def test_first_scraper_with_upcoming_events_wins(self):
        upcoming = [{"name": "Open Mic", "date": _future().isoformat(), "url": "https://newvenue.example/e/1"}]
        past = [{"name": "Old", "date": "2020-01-01T20:00:00+00:00"}]
        fakes = {"tribe": lambda u, ua: past, "squarespace": mock.Mock(side_effect=ValueError("not squarespace")),
                 "jsonld": lambda u, ua: upcoming, "ical": lambda u, ua: [], "eventbrite_org": lambda u, ua: []}
        with mock.patch.dict(scrapers.GENERIC_SCRAPERS, fakes):
            r = probe_source.probe("https://newvenue.example/", "New Venue", "music")
        self.assertTrue(r["found"])
        self.assertEqual((r["scraper"], r["name"], r["default_category"], r["count"]), ("jsonld", "New Venue", "music", 1))
        self.assertIn("Open Mic", probe_source.pr_body(r))

    def test_ical_feed_on_shared_host_is_probed(self):
        feed = "https://calendar.google.com/calendar/ical/abc/public/basic.ics"
        self.assertIsNone(probe_source._skip_reason(feed))
        self.assertEqual(probe_source.candidates(feed), [("ical", feed)])

    def test_apply_adds_once(self):
        r = {"found": True, "website": "https://newvenue.example/", "scraper": "jsonld",
             "url": "https://newvenue.example/events", "name": "New Venue", "default_category": "music"}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "discovered.json")
            self.assertTrue(probe_source.apply(r, path))
            self.assertFalse(probe_source.apply(r, path))
            self.assertEqual(len(json.load(open(path))), 1)


class DiscoveredSourcesTest(unittest.TestCase):
    def test_only_allowlisted_scrapers_load(self):
        rows = [{"name": "Good", "url": "https://good.example/events", "scraper": "jsonld"},
                {"name": "Bad", "url": "https://bad.example", "scraper": "os.system"},
                {"name": "NoUrl", "url": "file:///etc/passwd", "scraper": "ical"}]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            json.dump(rows, open(path, "w"))
            out = scrapers.load_discovered_sources(path)
        self.assertEqual([v["name"] for v in out], ["Good"])
        self.assertIs(out[0]["scraper"], scrapers.scrape_jsonld)

    def test_repo_file_is_valid(self):
        with open(scrapers.DISCOVERED_SOURCES_FILE) as f:
            self.assertIsInstance(json.load(f), list)


class PageTest(unittest.TestCase):
    def test_flyer_upload_hidden_without_endpoint(self):
        with mock.patch.object(template, "SUBMISSION_ENDPOINT_JS", '""'):
            html = template.render_page([])
        self.assertIn('id="flyer-upload" hidden', html)
        self.assertIn("/extract-flyer", html)
        self.assertNotIn(":00-04:00`", html)


if __name__ == "__main__":
    unittest.main()
