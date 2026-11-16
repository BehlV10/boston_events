"""Children's classes with an age range in the title go to Kids & Family, whatever the source filed them under."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scrapers import is_kid_family_event  # noqa: E402


class KidsByAge(unittest.TestCase):
    def test_kids_classes(self):
        for name in ("Primary Ballet I (Ages 4-6)", "Ballet I/II (Ages 8+)", "Creative Movement (Ages 6-7)",
                     "Art Lab (Ages 6–12)", "Drawing Workshop (Ages 8-14)", "Robotics for Grades K-2"):
            self.assertTrue(is_kid_family_event(name), name)

    def test_teen_and_adult_ranges_stay_put(self):
        for name in ("Ballet IV/V (Ages 14+)", "Contemporary (Ages 13+)", "Jazz (Ages 11+)",
                     "Svdden Death (Ages 18+)", "Comedy Night - Ages 21+", "Tour Stage Ages 21 and up"):
            self.assertFalse(is_kid_family_event(name), name)


if __name__ == "__main__":
    unittest.main()
