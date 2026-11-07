import json
import re
import unittest

import camps
import template


class CampDataTests(unittest.TestCase):
    def setUp(self):
        self.data = camps.load_camps()

    def test_every_entry_passes_validation(self):
        self.assertEqual(camps.validate(self.data), [])

    def test_validation_rejects_guessed_and_unsourced_entries(self):
        good = dict(self.data["camps"][0])
        cases = [dict(good, price="Typical $550–$750/wk"), dict(good, url="https://www.google.com/search?q=camp"),
                 dict(good, sources=[]), dict(good, week_low=500, week_high=None),
                 dict(good, events=[{"label": "Opens", "date": "2026-01-02", "season": 2026}])]
        for bad in cases:
            self.assertTrue(camps.validate({"camps": [bad]}), bad)

    def test_covers_city_programs_and_nearby_towns(self):
        towns = {c["town"] for c in self.data["camps"]}
        for town in ("Boston", "Cambridge", "Somerville", "Medford", "Watertown", "Belmont", "Newton", "Quincy", "Lexington", "Arlington"):
            self.assertIn(town, towns)
        self.assertGreaterEqual(sum(c["kind"] == "city" for c in self.data["camps"]), 8)

    def test_every_area_and_kind_has_a_camp(self):
        self.assertEqual({k for k, _ in camps.AREAS}, {c["area"] for c in self.data["camps"]})
        self.assertEqual({k for k, _ in camps.KINDS}, {c["kind"] for c in self.data["camps"]})

    def test_estimator_is_gone(self):
        with self.assertRaises(ImportError):
            __import__("camps_scraper")


class CampPageTests(unittest.TestCase):
    def setUp(self):
        self.hub = template.HUBS["summer-camps"]
        self.html = template.render_hub_page("summer-camps", [])

    def test_hub_settings(self):
        self.assertEqual(self.hub["style"], "camps")
        self.assertEqual(self.hub["query"], "summer-camps/")
        self.assertEqual(len(template.filter_events_for_hub(self.hub, [])), len(camps.load_camps()["camps"]))

    def test_page_shows_every_camp_with_its_source(self):
        data = camps.load_camps()
        self.assertEqual(self.html.count('<article class="camp-card"'), len(data["camps"]))
        for c in data["camps"]:
            self.assertIn(template.escape(c["sources"][0]), self.html)

    def test_page_makes_no_old_claims(self):
        for word in ("Accredited", "accredited", "Typical", "camp-badge-aca", "google.com/search"):
            self.assertNotIn(word, self.html)

    def test_missing_facts_are_labelled(self):
        self.assertIn("Not published", self.html)

    def test_every_filter_button_matches_a_card(self):
        cards = re.findall(r'<article class="camp-card" data-id="[^"]*" data-area="(\w+)" data-kind="(\w+)" data-type="(\w+)"', self.html)
        for group, val in re.findall(r'class="camp-chip" data-group="(area|kind)" data-val="(\w+)"', self.html):
            if val == "all":
                continue
            column = 0 if group == "area" else 1
            found = any(c[column] == val or (val == "overnight" and c[2] == "Overnight") for c in cards)
            self.assertTrue(found, (group, val))

    def test_sign_up_dates_are_upcoming_and_calendar_ready(self):
        days = re.findall(r'<li data-date="([\d-]+)">', self.html)
        self.assertEqual(days, sorted(days))
        self.assertIn("calendar.google.com/calendar/render", self.html)
        self.assertIn('class="camp-linkish camp-ics"', self.html)

    def test_structured_data_is_valid_json(self):
        blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)
        self.assertTrue(blocks)
        for block in blocks:
            json.loads(block)


if __name__ == "__main__":
    unittest.main()
