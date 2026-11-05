"""Holiday theme calendar, art and CSS (holiday_themes.py)."""

import os
import sys
import unittest
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import holiday_themes as H  # noqa: E402


class HolidayDatesTest(unittest.TestCase):
    def test_rule_based_dates(self):
        cases = {
            date(2026, 11, 11): "veterans",
            date(2026, 11, 26): "thanksgiving",  # 4th Thursday
            date(2026, 11, 25): "thanksgiving",  # the Wednesday before too
            date(2026, 11, 27): "blackfriday",
            date(2026, 11, 30): "cybermonday",
            date(2027, 1, 18): "mlk",  # 3rd Monday of January
            date(2027, 2, 15): "presidents",
            date(2027, 3, 17): "stpatricks",
            date(2027, 3, 28): "easter",
            date(2027, 4, 19): "patriots",  # 3rd Monday of April
            date(2027, 5, 9): "mothers",  # 2nd Sunday of May
            date(2027, 5, 31): "memorial",  # last Monday of May
            date(2027, 6, 20): "fathers",  # 3rd Sunday of June
            date(2027, 9, 6): "labor",
            date(2027, 10, 11): "indigenous",
            date(2027, 10, 16): "hocr",  # 3rd Saturday of October
            date(2027, 10, 17): "hocr",
            date(2027, 10, 31): "halloween",
        }
        for d, key in cases.items():
            h = H.holiday_on(d)
            self.assertIsNotNone(h, d)
            self.assertEqual(h["key"], key, d)

    def test_easter_algorithm(self):
        known = {2025: date(2025, 4, 20), 2026: date(2026, 4, 5), 2027: date(2027, 3, 28),
                 2028: date(2028, 4, 16), 2030: date(2030, 4, 21)}
        for y, d in known.items():
            self.assertEqual(H._easter(y), d)

    def test_ordinary_days_have_no_holiday(self):
        for d in (date(2026, 11, 5), date(2027, 3, 3), date(2027, 8, 12)):
            self.assertIsNone(H.holiday_on(d), d)

    def test_calendar_covers_the_coming_year(self):
        cal = H.holiday_calendar(date(2026, 11, 5), 365)
        keys = set(cal.values())
        # every holiday in the table shows up within a year
        self.assertEqual(keys, set(H.HOLIDAY_KEYS))
        self.assertGreater(len(cal), 30)

    def test_keys_unique(self):
        self.assertEqual(len(H.HOLIDAY_KEYS), len(set(H.HOLIDAY_KEYS)))


class HolidayAssetsTest(unittest.TestCase):
    def test_every_holiday_has_banner_art(self):
        for h in H.HOLIDAYS:
            path = os.path.join(ROOT, H.banner_url(h))
            self.assertTrue(os.path.exists(path), f"{h['key']}: missing {path}")

    def test_css_has_greeting_and_banner_for_every_holiday(self):
        css = H.holiday_theme_css()
        self.assertNotIn("{{", css)
        for h in H.HOLIDAYS:
            self.assertIn(f'.holiday-greeting[data-for="{h["key"]}"]', css)
            if h.get("banner") is None:
                self.assertIn(H.banner_url(h), css)

    def test_greetings_html(self):
        html = H.greeting_html()
        for h in H.HOLIDAYS:
            self.assertIn(f'data-for="{h["key"]}"', html)


if __name__ == "__main__":
    unittest.main()
