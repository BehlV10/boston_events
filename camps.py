"""Summer camp data for /summer-camps/.

camps.json is curated by hand. Every price, date and age in it was read from the camp's own
site or a city document on the date in `checked`. Nothing here is estimated: a fact we couldn't
confirm stays empty and the page says so.
"""

import json
import os
import re
from datetime import date

CAMPS_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "camps.json")

AREAS = (("boston", "Boston"), ("cam_som", "Cambridge & Somerville"), ("north", "North"),
         ("west", "West"), ("south", "South"), ("north_shore", "North Shore"), ("away", "Farther away"))
KINDS = (("city", "City & town"), ("ymca", "YMCA"), ("nature", "Nature"),
         ("nonprofit", "Nonprofit"), ("museum", "Museum & zoo"), ("private", "Private day camp"))
_REQUIRED = ("id", "name", "town", "area", "kind", "focus", "type", "season", "url", "sources", "checked")


def load_camps(path=CAMPS_JSON_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is_guess(text):
    return bool(re.search(r"\b(typical|estimate|approx|around|about)\b|~", text or "", re.I))


def validate(data):
    """Return a list of problems, so a bad entry fails the tests instead of reaching parents."""
    problems = []
    areas, kinds = dict(AREAS), dict(KINDS)
    seen = set()
    for c in data["camps"]:
        who = c.get("id") or c.get("name")
        for key in _REQUIRED:
            if not c.get(key):
                problems.append(f"{who}: missing {key}")
        if who in seen:
            problems.append(f"{who}: duplicate id")
        seen.add(who)
        if c.get("area") not in areas:
            problems.append(f"{who}: unknown area")
        if c.get("kind") not in kinds:
            problems.append(f"{who}: unknown kind")
        for url in [c.get("url", "")] + (c.get("sources") or []):
            if not url.startswith("http") or "google." in url:
                problems.append(f"{who}: bad source {url}")
        if _is_guess(c.get("price")):
            problems.append(f"{who}: price reads like a guess")
        low, high = c.get("week_low"), c.get("week_high")
        if (low is None) != (high is None) or (low is not None and low > high):
            problems.append(f"{who}: bad weekly price range")
        if low is not None and not c.get("price"):
            problems.append(f"{who}: weekly range with no published price")
        for e in c.get("events") or []:
            if e.get("date"):
                try:
                    date.fromisoformat(e["date"])
                except ValueError:
                    problems.append(f"{who}: bad date {e['date']}")
                if e.get("season") != 2027:
                    problems.append(f"{who}: exact dates must be for the 2027 season")
            elif not e.get("when"):
                problems.append(f"{who}: event has no date")
    return problems
