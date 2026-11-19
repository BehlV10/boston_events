"""Niche pages pick events by title, category and genre, not by keywords in venue names."""
import unittest

import template as T


def ev(name, venue="", category="music", **kw):
    return {"name": name, "venue": venue, "category": category, **kw}


class NicheMatchingTest(unittest.TestCase):
    def assertNiche(self, niche, e, expected):
        self.assertEqual(T._matches_niche(niche, e), expected, f"{niche}: {e}")

    def test_goth_is_goth_nights_not_every_manray_night(self):
        self.assertNiche("goth", ev("Crypt - ManRay's Weekly Goth/Industrial Night", "ManRay", "clubbing"), True)
        self.assertNiche("goth", ev("Elysium", "Sonia"), True)
        self.assertNiche("goth", ev("Synapse", "Middle East - Upstairs"), True)
        self.assertNiche("goth", ev("Charming Disaster", "Cantab", description="a goth-folk musical duo"), True)
        self.assertNiche("goth", ev("Clown Town", "ManRay", "clubbing"), False)
        self.assertNiche("goth", ev("Daddy - O: Underwear Party", "ManRay", "clubbing"), False)
        self.assertNiche("goth", ev("The Wankers – The Ultimate Britpop/New Wave Experience", "Middle East",
                                    description="British New Wave, post-punk and Britpop"), False)
        self.assertNiche("goth", ev("Gothic Architecture of Boston", "BPL", "talks"), False)

    def test_venue_names_do_not_decide(self):
        self.assertNiche("dance", ev("Indie Band Live", "Crystal Ballroom"), False)
        self.assertNiche("classical", ev("Hamilton", "Citizens Bank Opera House", "theater"), False)
        self.assertNiche("classical", ev("Tchaikovsky Symphonies Nos. 3 and 4", "Symphony Hall"), True)
        self.assertNiche("book", ev("Friday Night Trivia", "Trident Booksellers and Cafe", "community"), False)
        self.assertNiche("jazz", ev("Gabriel Maia Quintet", "Wally's Café"), True)
        self.assertNiche("jazz", ev("Candlelight: Tribute to Taylor Swift", "Simons Theatre", genre="jazz_blues"), False)

    def test_generic_words_need_the_right_kind_of_event(self):
        self.assertNiche("latin", ev("Salsa Making Class", "Some Kitchen", "food"), False)
        self.assertNiche("latin", ev("Bachata Thursdays", "Havana Club", "dance"), True)
        self.assertNiche("karaoke", ev("Toddler Sing-Along", "Library", "kids"), False)
        self.assertNiche("metal", ev("Gallery Opening", "Gallery", "art", description="Sculptures in metal and glass"), False)
        self.assertNiche("metal", ev("Dr. Doom Dunkin Takeover", "Boston", "community"), False)
        self.assertNiche("metal", ev("Metafaction Presents: A Metal Thanksgiving", "Middle East - Zuzu"), True)

    def test_stage_and_fitness_categories_count(self):
        self.assertNiche("theater", ev("A New Play", "Somewhere", "stage"), True)
        self.assertNiche("fitness", ev("Morning Session", "Gym", "fitness"), True)


if __name__ == "__main__":
    unittest.main()
