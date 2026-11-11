"""Every guide page's header bar links the same finished pages, and only those."""
import re
import unittest

import template

FINISHED = ["../", "../markets-festivals-boston/", "../college/", "../kids-family-events-boston/",
            "../summer-camps/", "../boston-edm/"]
PAGES = ["markets-festivals-boston", "college", "kids-family-events-boston", "summer-camps", "boston-edm"]


def nav_links(html):
    nav = re.search(r'<nav class="hub-nav[^"]*">(.*?)</nav>', html, re.S).group(1)
    return re.findall(r'<a href="([^"]+)"', nav)


class HubNav(unittest.TestCase):
    def test_same_bar_on_every_finished_page(self):
        for slug in PAGES:
            html = template.render_hub_page(slug, [], site_url="https://example.com")
            self.assertEqual(nav_links(html), FINISHED, slug)

    def test_current_page_is_highlighted(self):
        html = template.render_hub_page("boston-edm", [], site_url="https://example.com")
        self.assertRegex(html, r'<a href="\.\./boston-edm/" class="active">Boston EDM</a>')

    def test_unfinished_pages_are_not_in_the_bar(self):
        for slug in PAGES:
            links = nav_links(template.render_hub_page(slug, [], site_url="https://example.com"))
            for gone in ("cambridge-events-tonight", "music", "free", "board-game"):
                self.assertFalse(any(gone in l for l in links), f"{slug} links {gone}")


class MarketsDailyStrip(unittest.TestCase):
    def test_open_every_day_is_not_a_dark_gradient_panel(self):
        self.assertNotIn("linear-gradient(135deg, #2a3560, #7a3f5e)", template._MARKETS_CSS)


if __name__ == "__main__":
    unittest.main()
