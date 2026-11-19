"""Tests for improvements ported from nyc_events:
- Fast deploy on push & niche hub dirs in scrape.yml
- Resilient _run_pass post-scrape wrapper
- Source shrink alerts in source_health.py
- Live prime-time OG card event selection in export_og.py
- IFPA pinball tournament scraper for Greater Boston
- Saved category preferences & honest free badges in template.py
"""
import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

import export_og
import scrapers as S
import source_health as SH
import template as T


class SourceShrinkAlertsTest(unittest.TestCase):
    def test_detect_shrunk_sources_flags_50pct_drop_from_10_plus(self):
        prev = [
            {"source": "The Sinclair", "events": 40},
            {"source": "Small Club", "events": 4},
            {"source": "Healthy Venue", "events": 30},
        ]
        cur = [
            {"source": "The Sinclair", "url": "https://sinclair.example", "events": 12, "status": "ok", "next_event": "2026-11-20", "error": None, "kept_last_good": False},
            {"source": "Small Club", "url": "https://small.example", "events": 1, "status": "ok", "next_event": "2026-11-20", "error": None, "kept_last_good": False},
            {"source": "Healthy Venue", "url": "https://healthy.example", "events": 28, "status": "ok", "next_event": "2026-11-20", "error": None, "kept_last_good": False},
        ]
        shrunk = SH.detect_shrunk_sources(cur, prev)
        self.assertEqual(len(shrunk), 1)
        self.assertEqual(shrunk[0]["source"], "The Sinclair")
        self.assertEqual(shrunk[0]["drop_pct"], 70)

        md = SH._markdown(cur, shrunk=shrunk)
        self.assertIn("### Shrunk sources", md)
        self.assertIn("-70%", md)


class OgPicksTest(unittest.TestCase):
    def test_select_og_picks_prefers_varied_prime_time_boston_events(self):
        base = datetime.now(S.EASTERN).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
        events = [
            {"name": "Early 6am Yoga", "venue": "Boston Common", "category": "outdoors", "date": base.replace(hour=6).isoformat()},
            {"name": "Indie Band Live | Fri, Nov 20 @8pm", "venue": "The Sinclair (Cambridge)", "category": "music", "date": base.replace(hour=20).isoformat()},
            {"name": "Stand-Up Showcase", "venue": "The Comedy Studio", "category": "comedy", "date": base.replace(hour=19).isoformat()},
            {"name": "Hadestown", "venue": "Emerson Colonial Theatre", "category": "theater", "date": base.replace(hour=19).isoformat()},
            {"name": "Gallery Opening", "venue": "ICA Boston", "category": "art", "date": base.replace(hour=18).isoformat()},
            {"name": "Far Suburb Event", "venue": "Random Barn", "category": "music", "date": base.replace(hour=20).isoformat()},
        ]
        picks = export_og.select_og_picks(events, count=4)
        self.assertEqual(len(picks), 4)
        cats = [e["category"] for e, _ in picks]
        self.assertEqual(len(set(cats)), 4)
        self.assertEqual(export_og._clean_og_title("Indie Band Live | Fri, Nov 20 @8pm"), "Indie Band Live")
        self.assertEqual(export_og._clean_og_venue("The Sinclair (Cambridge)"), "The Sinclair")


class ResilientPassAndIfpaTest(unittest.TestCase):
    def test_run_pass_logs_and_returns_default_on_exception(self):
        S.RUN_FAILURES.clear()

        def boom():
            raise RuntimeError("boom")

        res = S._run_pass("test_pass", boom, default=[])
        self.assertEqual(res, [])
        self.assertTrue(any("test_pass: RuntimeError: boom" in m for m in S.RUN_FAILURES))

    def test_scrape_ifpa_nearby_parses_boston_tournament(self):
        list_html = """
        <div id="search_result_1">
          <h5><a href="/tournaments/view.php?t=99999">Tilt Through: Roxy's V6</a></h5>
          <p class="mb-1"><small>Cambridge, MA, United States | Womens Division | Dec 8, 2027</small></p>
        </div>
        <div id="search_result_2">
          <h5><a href="/tournaments/view.php?t=99998">Far Away Pinball</a></h5>
          <p class="mb-1"><small>Portland, ME, United States | Open | Dec 9, 2027</small></p>
        </div>
        """
        detail_html = """
        <html><body>
          <address>292 Massachusetts Ave, Cambridge, MA 02139</address>
          <p>Check-in starts 7:00 PM</p>
        </body></html>
        """
        with mock.patch.object(S, "_SESSION") as sess:
            sess.get.return_value = mock.Mock(status_code=200, text=list_html)
            evs = S.scrape_ifpa_nearby(
                "https://www.ifpapinball.com/calendar/search.php?type=near&latitude=42.3601&longitude=-71.0589",
                "ua",
                fetch_detail=lambda u: detail_html,
            )
        self.assertEqual(len(evs), 1)
        self.assertIn("Pinball Tournament", evs[0]["name"])
        self.assertEqual(evs[0]["category"], "gaming")
        self.assertEqual(evs[0]["venue"], "Cambridge")
        self.assertNotIn("time_unknown", evs[0])


class SavedCatsAndFreeBadgesTest(unittest.TestCase):
    def test_saved_cats_and_honest_free_badges_rendered(self):
        results = [
            {
                "venue": "Test Bar",
                "url": "https://example.com/bar",
                "events": [
                    {"name": "DJ Night", "date": "2026-11-20T21:00:00-05:00", "venue": "Test Bar", "url": "https://example.com/1", "category": "clubbing", "price": "Free before 11pm"},
                    {"name": "Jazz Trio", "date": "2026-11-20T20:00:00-05:00", "venue": "Test Bar", "url": "https://example.com/2", "category": "music", "price": "No cover"},
                ],
            }
        ]
        html = T.render_page(results)
        self.assertIn("boston_saved_cats", html)
        self.assertIn("saveCatsState()", html)
        self.assertIn("price free free-catch", html)
        self.assertIn("Free before 11pm", html)
        self.assertIn("No cover", html)


class ScrapeWorkflowTest(unittest.TestCase):
    def test_fast_deploy_on_push_and_niche_hubs_committed(self):
        wf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".github", "workflows", "scrape.yml")
        src = open(wf_path, encoding="utf-8").read()
        self.assertIn('github.event_name', src)
        self.assertIn("reusing existing events.json", src)
        for slug in ("goth/", "lgbtq/", "jazz/", "film/", "theater/", "dance/", "book/",
                     "classical/", "metal/", "crafts/", "karaoke/", "fitness/", "latin/"):
            self.assertIn(slug, src)


if __name__ == "__main__":
    unittest.main()
