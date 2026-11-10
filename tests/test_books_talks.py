"""The Books & Talks filter: author events and lectures/panels, split out of Arts & culture and Community."""
import unittest

import scrapers
import template
from scrapers import category_bucket, infer_category


class BooksAndTalksBucket(unittest.TestCase):
    def test_bucket_membership(self):
        self.assertEqual(category_bucket("books"), "Books & Talks")
        self.assertEqual(category_bucket("talks"), "Books & Talks")
        self.assertEqual(category_bucket("art"), "Arts & culture")
        self.assertEqual(category_bucket("film"), "Arts & culture")
        self.assertIn("talks", scrapers.CATEGORY_STYLES)

    def test_old_shared_links_still_show_books(self):
        html = template.render_page([])
        self.assertIn("if (vals.has('Arts & culture')) vals.add('Books & Talks');", html)


class TalkInference(unittest.TestCase):
    def test_lectures_and_panels_are_talks(self):
        for name in ("Second Ralph Lowell Annual Lecture featuring Marty Baron",
                     "Unseen and Unhoused • Panel Discussion", "BIDMC Cancer Center Annual Symposium",
                     "Garden Club of Brookline: Talk with Tree Warden of Brookline"):
            self.assertEqual(infer_category(name, "Somewhere"), "talks", name)

    def test_stronger_categories_keep_priority(self):
        self.assertEqual(infer_category("Lecture-Recital: Bach Cello Suites", "Jordan Hall"), "music")
        self.assertEqual(infer_category("Film Screening and Panel Discussion", "Brattle"), "film")
        self.assertEqual(infer_category("Author Talk: Jhumpa Lahiri", "Harvard Book Store"), "books")


class RenderTimeRecategorisation(unittest.TestCase):
    def _cat(self, name, cat):
        return template._effective_category({"name": name, "venue": "X", "category": cat})

    def test_catch_all_categories_move(self):
        self.assertEqual(self._cat("Connolly Book Discussion Group", "community"), "books")
        self.assertEqual(self._cat("MFA: Suzanne Jackson in Conversation with Imani Perry", "art"), "books")
        self.assertEqual(self._cat("ECOC Lecture: The Resplendent Quetzal", "art"), "talks")
        self.assertEqual(self._cat("Lectures on Tap", "other"), "talks")

    def test_specific_categories_stay(self):
        self.assertEqual(self._cat("Comedy Panel Discussion", "comedy"), "comedy")
        self.assertEqual(self._cat("Book Club Night: live jazz", "music"), "music")


if __name__ == "__main__":
    unittest.main()
