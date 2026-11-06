"""The shared-schedule page reads everything from a link anyone can write, so these guard how it
handles that text, and that the home page's schedule script declares what it uses before load."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*path):
    with open(os.path.join(ROOT, *path), encoding="utf-8") as f:
        return f.read()


class SchedulePage(unittest.TestCase):
    def setUp(self):
        self.page = read("schedule", "index.html")

    def test_link_contents_never_become_html(self):
        script = self.page[self.page.rindex("<script>"):]
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("insertAdjacentHTML", script)
        self.assertNotIn("document.write", script)

    def test_only_web_links_are_kept(self):
        self.assertIn("url.protocol === 'https:' || url.protocol === 'http:'", self.page)

    def test_shared_schedules_stay_out_of_search(self):
        self.assertIn('<meta name="robots" content="noindex">', self.page)


class ScheduleOnHomePage(unittest.TestCase):
    def setUp(self):
        self.template = read("template.py")

    def test_bar_elements_are_declared_before_first_use(self):
        # updateQuickChipsUI can run during load, so a later const would throw
        declared = self.template.index("const scheduleBar = ")
        used = self.template.index("function updateQuickChipsUI")
        self.assertLess(declared, used)

    def test_untimed_events_are_flagged_rather_than_given_an_hour(self):
        self.assertIn("li.dataset.epoch ? 0 : 1", self.template)
        self.assertIn("'DTSTART;VALUE=DATE:'", read("schedule", "index.html"))

    def test_star_is_labeled_for_the_schedule(self):
        self.assertTrue(re.search(r'class="star-btn" title="Add to My Schedule"', self.template))


if __name__ == "__main__":
    unittest.main()
