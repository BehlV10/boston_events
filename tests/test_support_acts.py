"""Openers in titles: the Sinclair list's .supporting line, Bowery's supportingText and TicketWeb's
performer list ("Sweet Pill" was listed without Heart to Gold and Stereosity)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scrapers as S  # noqa: E402
import template as T  # noqa: E402


class WithSupport(unittest.TestCase):
    def test_appends_openers(self):
        self.assertEqual(S._with_support("Sweet Pill", "Heart to Gold, Stereosity"),
                         "Sweet Pill with Heart to Gold, Stereosity")

    def test_skips_acts_already_in_title_and_empty(self):
        self.assertEqual(S._with_support("Jessie Mazin, Anya True", ["Jessie Mazin", "Anya True "]), "Jessie Mazin, Anya True")
        self.assertEqual(S._with_support("Elysium", ""), "Elysium")
        self.assertEqual(S._with_support("Crazy Train", ["Crazy Train", "Wolf's Blood"]), "Crazy Train with Wolf's Blood")

    def test_cleans_with_and_opening_words(self):
        self.assertEqual(S._with_support("UNMUTED - a benefit concert", "Illiterate Light, with Twice-A-Day Ray opening"),
                         "UNMUTED - a benefit concert with Illiterate Light, Twice-A-Day Ray")

    def test_overlong_lineup_left_off(self):
        self.assertEqual(S._with_support("Fest", ["Band %d Long Name Here" % i for i in range(8)]), "Fest")

    def test_still_merges_with_plain_title(self):
        self.assertEqual(T._normalize_title_head("Sweet Pill with Heart to Gold, Stereosity", venue="The Sinclair"),
                         T._normalize_title_head("Sweet Pill", venue="The Sinclair"))


if __name__ == "__main__":
    unittest.main()
