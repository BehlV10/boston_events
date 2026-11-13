"""Affiliate ticket links: off by default, wrap only switched-on sellers, disclose when used."""
import json
import os
import tempfile
import unittest
from urllib.parse import parse_qs, urlparse
import html

import affiliate as A

TM = (("ticketmaster.com", "livenation.com"), "https://ticketmaster.evyy.net/c/123/264167/4272?u={url}")
PAGE = ('<a href="https://www.ticketmaster.com/show/event/1?a=1&amp;b=2" target="_blank" rel="noopener">Show</a>'
        '<a href="https://www.eventbrite.com/e/2">Other</a>'
        '<a class="x" href="https://concerts.livenation.com/e/3">LN</a>'
        '<footer><p>Not affiliated with any commercial ticketing broker.</p></footer>')


class AffiliateTest(unittest.TestCase):
    def test_committed_config_is_off(self):
        self.assertEqual(A.load_sellers(), [])
        self.assertEqual(A.rewrite_html(PAGE), PAGE)

    def test_wraps_switched_on_seller_only(self):
        out = A.rewrite_html(PAGE, [TM])
        self.assertIn('href="https://www.eventbrite.com/e/2"', out)
        first = out.split('"')[1]
        target = parse_qs(urlparse(html.unescape(first)).query)["u"][0]
        self.assertEqual(target, "https://www.ticketmaster.com/show/event/1?a=1&b=2")
        self.assertIn('rel="noopener sponsored"', out)
        self.assertIn('class="x" href="https://ticketmaster.evyy.net/', out)
        self.assertIn('rel="sponsored">LN', out)

    def test_footer_claim_becomes_disclosure(self):
        out = A.rewrite_html(PAGE, [TM])
        self.assertIn(A.DISCLOSURE, out)
        self.assertNotIn(A._OLD_FOOTER_CLAIM, out)

    def test_no_matching_links_leaves_page_alone(self):
        page = '<a href="https://www.eventbrite.com/e/2">x</a><footer>Not affiliated with any commercial ticketing broker.</footer>'
        self.assertEqual(A.rewrite_html(page, [TM]), page)

    def test_load_skips_bad_templates(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w") as f:
            json.dump({"sellers": [{"hosts": ["a.com"], "template": "https://x/?u={url}"},
                                   {"hosts": ["b.com"], "template": "https://x/no-placeholder"},
                                   {"hosts": ["c.com"], "template": ""}]}, f)
        try:
            self.assertEqual(A.load_sellers(path), [(("a.com",), "https://x/?u={url}")])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
