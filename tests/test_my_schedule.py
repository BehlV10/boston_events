"""The shared-schedule page reads everything from a link anyone can write, so these guard how it
handles that text, and that the home page's schedule script declares what it uses before load."""
import os
import re
import shutil
import subprocess
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


class StarsAreVisible(unittest.TestCase):
    def test_nothing_hides_the_star_button(self):
        """The stars are how events get into My Schedule."""
        for rule in re.findall(r"\.star-btn[^{}]*\{\{(.*?)\}\}", read("template.py"), re.S):
            self.assertNotIn("display: none", rule)


class ShortLinks(unittest.TestCase):
    def test_worker_rules(self):
        if not shutil.which("node"):
            self.skipTest("needs node")
        result = subprocess.run(["node", "--test", "worker.test.mjs"], cwd=os.path.join(ROOT, "schedule-worker"),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_share_falls_back_to_the_long_link(self):
        self.assertIn("await shortScheduleLink(schedule) ||", read("template.py"))

    def test_events_drop_off_a_day_after_they_start(self):
        self.assertIn("var KEEP_SECONDS = 86400;", read("schedule", "index.html"))
        self.assertIn("function dropPastScheduleEvents()", read("template.py"))


if __name__ == "__main__":
    unittest.main()
