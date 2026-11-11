import datetime as _dt
import unittest
from scrapers import EASTERN as _EST
import template

class EdmHubTests(unittest.TestCase):
    def test_hub_registered_in_hubs(self):
        self.assertIn("boston-edm", template.HUBS)
        hub = template.HUBS["boston-edm"]
        self.assertEqual(hub["style"], "edm")
        self.assertEqual(hub["og_badge"], "BOSTON EDM & ELECTRONIC")
        self.assertEqual(hub["og_image"], "og-boston-edm.jpg")

    def test_filter_events_for_hub_edm(self):
        hub = template.HUBS["boston-edm"]
        now = _dt.datetime.now(_EST)
        events = [
            {"name": "CamelPhat 3-Hour Set", "venue": "Royale", "date": (now + _dt.timedelta(days=1)).isoformat(), "category": "music", "music_genre": "electronic", "url": "https://example.com/1"},
            {"name": "Infra: Underground Techno", "venue": "The Phoenix Landing", "date": (now + _dt.timedelta(days=2)).isoformat(), "category": "clubbing", "url": "https://example.com/2"},
            {"name": "Elements D&B Night", "venue": "The Phoenix Landing", "date": (now + _dt.timedelta(days=3)).isoformat(), "category": "clubbing", "url": "https://example.com/3"},
            {"name": "Jazz Brunch with Open Jam", "venue": "The Bebop", "date": (now + _dt.timedelta(days=1)).isoformat(), "category": "music", "url": "https://example.com/4"},
            {"name": "Kids Puppet Storytime", "venue": "Puppet Showplace", "date": (now + _dt.timedelta(days=1)).isoformat(), "category": "kids", "url": "https://example.com/5"},
            {"name": "Standup Comedy Showcase", "venue": "Wilbur", "date": (now + _dt.timedelta(days=1)).isoformat(), "category": "comedy", "url": "https://example.com/6"},
        ]
        filtered = template.filter_events_for_hub(hub, events)
        names = [e["name"] for e in filtered]
        self.assertIn("CamelPhat 3-Hour Set", names)
        self.assertIn("Infra: Underground Techno", names)
        self.assertIn("Elements D&B Night", names)
        self.assertNotIn("Jazz Brunch with Open Jam", names)
        self.assertNotIn("Kids Puppet Storytime", names)
        self.assertNotIn("Standup Comedy Showcase", names)

    def test_edm_tags_subgenre_classification(self):
        now = _dt.datetime.now(_EST)
        ev_techno = {"name": "Hard Techno Night", "venue": "bsmnt", "_time": now}
        sub, lbl, emo, neigh, time_tag, is_free = template._edm_tags(ev_techno)
        self.assertEqual(sub, "techno")
        self.assertEqual(lbl, "⚡ Techno")

        ev_house = {"name": "Deep House Sessions", "venue": "Phoenix Landing", "_time": now}
        sub_h, lbl_h, emo_h, neigh_h, _, _ = template._edm_tags(ev_house)
        self.assertEqual(sub_h, "house")
        self.assertEqual(neigh_h, "Central Sq")

        ev_bass = {"name": "Drum & Bass Extravaganza", "venue": "Big Night Live", "_time": now}
        sub_b, lbl_b, _, neigh_b, _, _ = template._edm_tags(ev_bass)
        self.assertEqual(sub_b, "bass")
        self.assertEqual(neigh_b, "Downtown")

        ev_synth = {"name": "Darkwave & Synthwave Night", "venue": "ManRay", "_time": now}
        sub_s, lbl_s, _, _, _, _ = template._edm_tags(ev_synth)
        self.assertEqual(sub_s, "synth")

    def test_render_hub_page_edm(self):
        now = _dt.datetime.now(_EST)
        events = [
            {
                "name": "Infra Techno Resident Night",
                "venue": "The Phoenix Landing",
                "date": now.isoformat(),
                "_time": now,
                "price": "Free",
                "url": "https://phoenixlandingboston.com",
                "description": "Weekly underground techno in Central Square."
            }
        ]
        html = template.render_hub_page("boston-edm", events)
        self.assertIn('class="edm-hub"', html)
        self.assertIn("edm-hero-art", html)
        self.assertIn("edm-filters", html)
        self.assertIn("All Electronic", html)
        self.assertIn("⚡ Techno", html)
        self.assertIn("Infra Techno Resident Night", html)
        self.assertIn("Tickets / Info", html)
        self.assertIn("Central Sq", html)
        self.assertIn('data-group="cost"', html)
        self.assertIn("All Prices", html)
        self.assertIn("💛 Free / No Cover", html)
        self.assertIn('data-free="1"', html)
        # Verify streamlined nightlife nav
        self.assertIn('class="hub-nav edm-nav"', html)
        self.assertIn('href="../boston-edm/" class="active">Boston EDM</a>', html)
        for page in ("college", "kids-family-events-boston", "summer-camps", "markets-festivals-boston"):
            self.assertIn(f'href="../{page}/"', html)
        # Verify sleek hero art badge
        self.assertIn("BOSTON UNDERGROUND &amp; CLUBS", html)
        # Verify sidebar filter and city sections
        self.assertIn("edm-sidebar", html)
        self.assertIn("edm-city-section", html)
        self.assertIn("edm-city-head", html)
        self.assertIn("edm-city-pill", html)

    def test_edm_list_structure_multiple_cities(self):
        now = _dt.datetime.now(_EST)
        events = [
            {
                "name": "House Anthems Boston",
                "venue": "Royale",
                "date": now.isoformat(),
                "_time": now,
                "category": "clubbing",
                "url": "https://example.com/royale",
            },
            {
                "name": "Infra Techno Night",
                "venue": "The Phoenix Landing",
                "date": now.isoformat(),
                "_time": now,
                "category": "clubbing",
                "url": "https://example.com/infra",
            },
        ]
        html = template.render_hub_page("boston-edm", events)
        # Verify city grouping in cards: Cambridge events appear before Boston events matching main page
        self.assertIn('<h2 class="hub-day"', html)
        self.assertIn("edm-city-section", html)
        self.assertIn("edm-city-head", html)
        cards_body = html[html.index("<main"):]
        self.assertIn("Infra Techno Night", cards_body)
        self.assertIn("House Anthems Boston", cards_body)
        infra_idx = cards_body.index("Infra Techno Night")
        house_idx = cards_body.index("House Anthems Boston")
        self.assertLess(infra_idx, house_idx)


if __name__ == "__main__":
    unittest.main()
