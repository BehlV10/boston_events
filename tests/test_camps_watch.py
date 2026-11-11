"""The weekly camps watch (scripts/camps_watch.py): flags camps to re-check, never edits camps.json."""
import os
import sys
import unittest
from datetime import date

import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Loaded by path: putting scripts/ on sys.path would shadow tests/test_scrapers.py with scripts/test_scrapers.py.
_spec = importlib.util.spec_from_file_location("camps_watch", os.path.join(ROOT, "scripts", "camps_watch.py"))
w = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(w)

TODAY = date(2026, 11, 11)
URL = "https://camp.example/summer"


def camp(**kw):
    c = {"id": "c1", "name": "Camp One", "season": 2026, "checked": "2026-11-07", "url": URL, "sources": [URL]}
    c.update(kw)
    return c


def run(camps, pages, prev=None, today=TODAY):
    results, state = w.watch({"camps": camps}, pages, prev or {}, today)
    return {c["id"]: [k for k, _ in fl] for c, fl in results}, state


PAGE_2026 = ["Summer Camp 2026", "Weeks 1-8: $450 per week", "Ages 5-12", "Contact us"]
PAGE_2027 = PAGE_2026 + ["Registration for Summer 2027 opens January 5"]


class PageText(unittest.TestCase):
    def test_visible_text_only(self):
        html = "<html><script>var x='2027 $99'</script><style>.a{}</style><p>Ages 5-12</p><p>$450 / week</p></html>"
        self.assertEqual(w.page_lines(html), ["Ages 5-12", "$450 / week"])

    def test_fingerprint_ignores_order_and_unrelated_text(self):
        a = ["Ages 5-12", "$450 per week", "Our staff love camp"]
        b = ["Banner of the day", "$450 per week", "Ages 5-12"]
        self.assertEqual(w.fingerprint(a), w.fingerprint(b))
        self.assertNotEqual(w.fingerprint(a), w.fingerprint(["Ages 5-12", "$475 per week"]))

    def test_copyright_years_are_not_2027_news(self):
        self.assertEqual(w.mentions_2027(["© 2027 Camp One. All rights reserved."]), [])
        self.assertEqual(w.mentions_2027(PAGE_2027), ["Registration for Summer 2027 opens January 5"])


class Flags(unittest.TestCase):
    def test_2027_text_flags_a_2026_camp_once(self):
        flags, state = run([camp()], {URL: ("ok", PAGE_2027)})
        self.assertIn("2027", flags["c1"])
        # Someone re-checked it (bumped `checked`), the page is unchanged: quiet.
        flags, _ = run([camp(checked="2026-11-12")], {URL: ("ok", PAGE_2027)}, state, date(2026, 11, 18))
        self.assertNotIn("c1", flags)
        # New 2027 text after that check: flagged again.
        flags, _ = run([camp(checked="2026-11-12")], {URL: ("ok", PAGE_2027 + ["2027 rates: $475 per week"])},
                       state, date(2026, 11, 25))
        self.assertIn("2027", flags["c1"])

    def test_camp_already_on_2027_isnt_flagged_for_2027(self):
        flags, _ = run([camp(season=2027)], {URL: ("ok", PAGE_2027)})
        self.assertNotIn("c1", flags)

    def test_change_flags_until_checked(self):
        _, state = run([camp()], {URL: ("ok", PAGE_2026)})
        flags, state = run([camp()], {URL: ("ok", ["Weeks 1-8: $475 per week", "Ages 5-12"])}, state, date(2026, 11, 18))
        self.assertEqual(flags["c1"], ["changed"])
        flags, _ = run([camp()], {URL: ("ok", ["Weeks 1-8: $475 per week", "Ages 5-12"])}, state, date(2026, 11, 25))
        self.assertEqual(flags["c1"], ["changed"], "still unhandled a week later")
        flags, _ = run([camp(checked="2026-11-20")], {URL: ("ok", ["Weeks 1-8: $475 per week", "Ages 5-12"])},
                       state, date(2026, 11, 25))
        self.assertNotIn("c1", flags)

    def test_first_run_has_no_changes(self):
        flags, _ = run([camp()], {URL: ("ok", PAGE_2026)})
        self.assertNotIn("c1", flags)

    def test_pdf_fingerprint(self):
        _, state = run([camp()], {URL: ("ok", ["pdf aaaaaaaaaaaaaaaa"])})
        flags, _ = run([camp()], {URL: ("ok", ["pdf bbbbbbbbbbbbbbbb"])}, state, date(2026, 11, 18))
        self.assertEqual(flags["c1"], ["changed"])

    def test_links(self):
        flags, _ = run([camp()], {URL: ("dead", [])})
        self.assertEqual(flags["c1"], ["link"])
        flags, _ = run([camp()], {URL: ("blocked", [])})
        self.assertEqual(flags["c1"], ["link"])
        flags, _ = run([camp()], {URL: ("error", [])})  # a 500 or timeout: try again next week
        self.assertNotIn("c1", flags)

    def test_a_failed_fetch_keeps_the_saved_fingerprint(self):
        _, state = run([camp()], {URL: ("ok", PAGE_2026)})
        _, state = run([camp()], {URL: ("error", [])}, state, date(2026, 11, 18))
        flags, _ = run([camp()], {URL: ("ok", PAGE_2026)}, state, date(2026, 11, 25))
        self.assertNotIn("c1", flags)


class DateFlags(unittest.TestCase):
    def test_month_only_signup_overdue_once_the_month_comes(self):
        ev = {"label": "2027 details posted", "when": "Mid-November 2026", "kind": "info", "season": 2027}
        self.assertEqual(w.date_flags(camp(events=[ev]), date(2026, 10, 30)), [])
        self.assertEqual([k for k, _ in w.date_flags(camp(events=[ev]), TODAY)], ["overdue"])

    def test_not_posted_yet_isnt_overdue(self):
        ev = {"label": "2027 details", "when": "Not posted yet", "kind": "info", "season": 2027}
        self.assertEqual(w.date_flags(camp(events=[ev]), TODAY), [])

    def test_dated_signup_in_the_next_two_weeks(self):
        evs = [{"label": "Registration opens", "date": "2026-11-20", "kind": "open", "season": 2027},
               {"label": "Deadline", "date": "2027-01-20", "kind": "deadline", "season": 2027},
               {"label": "Old lottery", "date": "2026-11-12", "kind": "open", "season": 2025}]
        self.assertEqual([t for _, t in w.date_flags(camp(events=evs), TODAY)],
                         ["Registration opens: Fri Nov 20 — re-confirm on the camp's site"])


class IssueBody(unittest.TestCase):
    def test_state_round_trips_through_the_issue(self):
        flags, state = run([camp()], {URL: ("ok", PAGE_2027)})
        results, _ = w.watch({"camps": [camp()]}, {URL: ("ok", PAGE_2027)}, {}, TODAY)
        body = w.render(results, state, TODAY, 1)
        self.assertIn("Camp One", body)
        self.assertIn("never edits camp data", body)
        back = w.read_state(body)
        self.assertEqual(back["pages"], state["pages"])
        self.assertEqual(back["flags"], ["c1:2027"])

    def test_new_flags_only(self):
        results, state = w.watch({"camps": [camp()]}, {URL: ("ok", PAGE_2027)}, {}, TODAY)
        self.assertIn("Camp One", w.render_new(results, {}))
        prev = w.read_state(w.render(results, state, TODAY, 1))
        self.assertEqual(w.render_new(results, prev), "")

    def test_garbled_state_starts_fresh(self):
        self.assertEqual(w.read_state("<!-- camps-watch-state {not json} -->"), {})
        self.assertEqual(w.read_state(""), {})

    def test_real_camps_json_works_offline(self):
        import camps
        results, _ = w.watch(camps.load_camps(), {}, {}, TODAY)
        body = w.render(results, {"pages": {}}, TODAY, 0)
        self.assertLess(len(body), 60000, "GitHub issue bodies max out at 65,536 characters")


class NothingWritesCampData(unittest.TestCase):
    """camps.json is edited by hand from the camps' own pages; no script may rewrite it."""

    def test_camp_scripts_are_read_only(self):
        for name in ("camps_watch.py", "scrape_camps.py"):
            src = open(os.path.join(ROOT, "scripts", name), encoding="utf-8").read()
            self.assertFalse("json.dump(" in src, f"{name} writes JSON")
            self.assertFalse("--update" in src.split('"""', 2)[2], f"{name} has an --update option")


class Workflow(unittest.TestCase):
    def test_weekly_and_issue_only(self):
        src = open(os.path.join(ROOT, ".github", "workflows", "camps-watch.yml")).read()
        self.assertIn("schedule:", src)
        self.assertIn("issues: write", src)
        self.assertNotIn("contents: write", src)  # it can't push changes to camps.json
        self.assertIn("scripts/camps_watch.py", src)


if __name__ == "__main__":
    unittest.main()
