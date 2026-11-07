import unittest
import template
from camps_scraper import fetch_all_camps

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
        first = camps[0]
        for key in ("id", "name", "city", "state", "price_weekly", "url", "category", "ages", "region"):
            self.assertIn(key, first)
        # Check presence of key curated and ACA programs
        names_lower = [c["name"].lower() for c in camps]
        self.assertTrue(any("hill house" in n for n in names_lower))
        self.assertTrue(any("ymca" in n for n in names_lower))
        self.assertTrue(any("nature" in n or "audubon" in n for n in names_lower))

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
        # Verify typography is crisp standard sans-serif (no wide/stretched fonts)
        self.assertNotIn('Syne', html)
        self.assertNotIn('Orbitron', html)

if __name__ == "__main__":
    unittest.main()
