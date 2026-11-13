"""Impact.com site-ownership tag must stay in the home page <head> (affiliate program)."""
import unittest

import template as T


class ImpactVerificationTest(unittest.TestCase):
    def test_tag_in_head(self):
        page = T.render_page([])
        head = page[:page.index("</head>")]
        self.assertIn("<meta name='impact-site-verification' value='52cbf274-6291-449c-829e-6d0f2be81614'>", head)


if __name__ == "__main__":
    unittest.main()
