import unittest
from datetime import date

import template
import camps_scraper
from camps_scraper import fetch_all_camps, load_verified, build_camps, _assign_region


class SummerCampsHubTests(unittest.TestCase):
    def test_hub_registered_in_hubs(self):
        self.assertIn("summer-camps", template.HUBS)
        hub = template.HUBS["summer-camps"]
        self.assertEqual(hub["style"], "camps")
        self.assertEqual(hub["og_badge"], "SUMMER CAMPS GUIDE")
        self.assertEqual(hub["og_image"], "og-summer-camps.jpg")
        self.assertEqual(hub["query"], "summer-camps/")

    def test_camps_scraper_data(self):
        camps = fetch_all_camps(force=False)
        self.assertGreater(len(camps), 100)
        for key in ("id", "name", "city", "state", "url", "category", "region", "price_tier", "verified"):
            self.assertIn(key, camps[0])
        names_lower = [c["name"].lower() for c in camps]
        self.assertTrue(any("hill house" in n for n in names_lower))
        self.assertTrue(any("ymca" in n for n in names_lower))
        self.assertTrue(any("audubon" in n for n in names_lower))

    def test_filter_events_for_hub_camps(self):
        hub = template.HUBS["summer-camps"]
        res = template.filter_events_for_hub(hub, [])
        self.assertGreater(len(res), 100)

    def test_render_hub_page_camps(self):
        html = template.render_hub_page("summer-camps", [])
        self.assertIn('class="camps-hub"', html)
        self.assertIn('camps-hero-art', html)
        self.assertIn('camps-filters', html)
        self.assertIn('camp-card', html)
        self.assertIn('camp-chip', html)
        self.assertIn('camp-results-count', html)
        self.assertIn('Summer Camps', html)
        self.assertIn('EducationalOrganization', html)
        self.assertIn('id="sliding-scale"', html)
        # Verify typography is crisp standard sans-serif (no wide/stretched fonts)
        self.assertNotIn('Syne', html)
        self.assertNotIn('Orbitron', html)
        # No estimated prices anywhere on the page
        self.assertNotIn('Typical $', html)


class VerifiedCampDataTests(unittest.TestCase):
    """A wrong price or sign-up date costs a family a camp spot, so every figure needs a source."""

    @classmethod
    def setUpClass(cls):
        cls.verified = load_verified()
        cls.camps = fetch_all_camps(force=False)

    def test_every_verified_entry_has_source_and_check_date(self):
        for e in self.verified["camps"]:
            with self.subTest(camp=e["name"]):
                self.assertTrue(e.get("sources"), "needs at least one source URL")
                self.assertTrue(all(u.startswith("http") for u in e["sources"]))
                date.fromisoformat(e["checked"])
                self.assertIn("price_tier", e)
                if e["price_tier"] != "unlisted":
                    self.assertIsInstance(e.get("price_year"), int, "a shown price must say which season it's for")
                for r in e.get("reg_dates") or []:
                    date.fromisoformat(r["date"])

    def test_unverified_camps_show_no_price(self):
        for c in self.camps:
            if not c.get("verified"):
                with self.subTest(camp=c["name"]):
                    self.assertIsNone(c.get("price"))
                    self.assertEqual(c["price_tier"], "unlisted")
                    self.assertFalse(c.get("price_lines"))

    def test_verified_aca_ids_still_in_aca_list(self):
        aca_ids = {f"camp_{r['id']}" for r in camps_scraper._load_aca_cache()}
        for e in self.verified["camps"]:
            if e.get("aca_id"):
                self.assertIn(e["aca_id"], aca_ids, f"{e['name']} is no longer in the ACA list")

    def test_out_of_state_towns_not_in_ma_regions(self):
        self.assertEqual(_assign_region("Brookline", "NH")[0], "regional")
        self.assertEqual(_assign_region("North Scituate", "RI")[0], "regional")
        self.assertEqual(_assign_region("Brookline", "MA")[0], "innersuburbs")
        for c in self.camps:
            if c["state"] != "MA":
                self.assertEqual(c["region"], "regional", c["name"])

    def test_merge_uses_exact_aca_id_not_name_substrings(self):
        verified = {"camps": [{"aca_id": "camp_1", "name": "Park Camp", "price": "$1", "price_tier": "mid",
                               "price_year": 2027, "sources": ["https://x"], "checked": "2026-11-08"}]}
        recs = [{"id": 1, "store": "Park Camp", "city": "Boston", "state": "MA"},
                {"id": 2, "store": "Pine Park Camp", "city": "Boston", "state": "MA"}]
        camps = {c["id"]: c for c in build_camps(recs, verified)}
        self.assertEqual(camps["camp_1"]["price"], "$1")
        self.assertIsNone(camps["camp_2"]["price"])

    def test_last_years_prices_are_labelled(self):
        html = template.render_hub_page("summer-camps", [])
        season = self.verified["upcoming_season"]
        if any(e.get("price_year") and e["price_year"] < season for e in self.verified["camps"]):
            self.assertIn(f"{season} not posted yet", html)

    def test_signups_box_lists_only_upcoming_dates(self):
        camps = [{"name": "A", "url": "https://a", "reg_dates": [{"date": "2026-12-02", "label": "new"}, {"date": "2026-01-01", "label": "old"}]}]
        html = template._camps_signups_html(camps, date(2026, 11, 8))
        self.assertIn("Wed, Dec 2", html)
        self.assertNotIn("old", html)
        self.assertEqual(template._camps_signups_html(camps, date(2027, 1, 1)), "")


if __name__ == "__main__":
    unittest.main()
