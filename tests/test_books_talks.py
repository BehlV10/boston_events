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
        self.assertEqual(self._cat("MFA: Suzanne Jackson in Conversation with Imani Perry", "art"), "talks")
        self.assertEqual(self._cat("ECOC Lecture: The Resplendent Quetzal", "art"), "talks")
        self.assertEqual(self._cat("Lectures on Tap", "other"), "talks")

    def test_specific_categories_stay(self):
        self.assertEqual(self._cat("Comedy Panel Discussion", "comedy"), "comedy")
        self.assertEqual(self._cat("Book Club Night: live jazz", "music"), "music")


class BooksVsTalks(unittest.TestCase):
    """Books: you take part (clubs, swaps, writing groups, open mics). Talks: you listen to someone
    (author events, featured readings, lectures)."""
    def _cat(self, name, cat, venue="X", source=None):
        return template._effective_category({"name": name, "category": cat, "venue": venue,
                                             "_source_venue": source or venue})

    def test_author_events_are_talks(self):
        self.assertEqual(self._cat("Alice Hoffman at the Cambridge Public Library", "books",
                                   "Harvard Book Store (Cambridge Public Library)", "Harvard Book Store"), "talks")
        self.assertEqual(self._cat("Sarah Bruhn, author of Holding On to Home, in conversation with Andrea Flores",
                                   "books", "Porter Square Books"), "talks")
        self.assertEqual(self._cat("Amanda Foody and C. L. Herman: A Destiny So Cruel", "books", "Brookline Booksmith"), "talks")
        self.assertEqual(self._cat("Brian D. Goldstein at Harvard Book Store", "community", "Harvard Book Store"), "talks")
        self.assertEqual(self._cat("Harvard Book Store Welcomes James Gleick", "film", "Brattle Theatre"), "talks")

    def test_taking_part_is_books(self):
        for name, cat in (("Charlestown Book Group: The Berry Pickers", "community"), ("Book Swap", "other"),
                          ("Writing Group", "community"), ("PSB: Boston Edition Silent Reading Party", "books"),
                          ("Boston Poetry Slam", "music"), ("Third Thursdays Poetry: Open Mic!", "comedy"),
                          ("The Moth: Boston StorySLAM", "art"), ("Small Press Book Club: Perfection", "books")):
            self.assertEqual(self._cat(name, cat, "Brookline Booksmith"), "books", name)

    def test_bookstore_non_author_events_stay_books(self):
        self.assertEqual(self._cat("Since 1961: 65th Anniversary Party!", "books", "Brookline Booksmith"), "books")
        self.assertEqual(self._cat("Witch-Craft Cinema: Penelope w/ SQBG", "books", "Side Quest Books & Games"), "books")

    def test_talks_from_any_category(self):
        self.assertEqual(self._cat("Boston Speakers Series–Doris Kearns Goodwin", "music", "Symphony Hall"), "talks")
        self.assertEqual(self._cat("Lectures on Tap: How Great Stories Work", "food", "Night Shift Brewing"), "talks")
        self.assertEqual(self._cat("Granoff Music Center Colloquium: Terri Lyne Carrington", "music"), "talks")
        self.assertEqual(self._cat("Ten Lives: Mona Chalabi explores wealth", "other", "WBUR CitySpace"), "talks")
        self.assertEqual(self._cat("Pre-Concert Talk: Beethoven", "music"), "music")

    def test_book_groups_beat_services_but_language_classes_dont(self):
        self.assertEqual(self._cat("Council on Aging Book Group", "services"), "books")
        self.assertEqual(self._cat("Online ESOL Reading and Discussion Class", "services"), "services")


class BookKeywordMisfires(unittest.TestCase):
    def test_substrings_and_towns_are_not_books(self):
        for name, venue in (("Designing Experiences that Delight", "The Foundry"),
                            ("Webcraft 2.0: Designing a Website with Google Sites", "Boston Public Library"),
                            ("Songwriters in the Round", "Cafe Zing"),
                            ("Peer-Led Mandarin Conversation Circle", "Boston Public Library"),
                            ("Mark Roderick - Sunday with the Songbook", "Club Cafe"),
                            ("Made For Mothers Boston Chapter Meetup", "Presence&Co, Reading")):
            self.assertNotEqual(infer_category(name, venue), "books", name)
        self.assertEqual(infer_category("Book Signing with Joanne Chang", "Hummingbird Books"), "books")
        self.assertEqual(infer_category("Silent Reading Hour", "Somewhere"), "books")


if __name__ == "__main__":
    unittest.main()
