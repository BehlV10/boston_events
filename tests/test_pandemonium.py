"""Pandemonium Books & Games (Central Square): BookThatApp calendar + Shopify prices."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers as S
from venues_geo import resolve_event_geo


def _parts(dt):
    return [dt.year, dt.month, dt.day, dt.hour, dt.minute, 0]


class _Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code = data, status

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise S.requests.HTTPError(str(self.status_code))


class PandemoniumTest(unittest.TestCase):
    def test_geo_resolves(self):
        geo = resolve_event_geo({"venue": "Pandemonium Books & Games", "name": "FNM: Modern"})
        self.assertEqual(geo["venue"], "Pandemonium Books & Games")
        self.assertEqual(geo["neighborhood"], "Central Square")
        self.assertIn("4 Pleasant St", geo["address"])

    def _run(self, product_status=200):
        day = (datetime.now(S.EASTERN) + timedelta(days=3)).replace(hour=18, minute=30, second=0, microsecond=0)
        schedule = {"schedule": [
            {"handle": "fnm-modern", "title": "FNM: Modern", "start": _parts(day), "end": _parts(day + timedelta(hours=4)),
             "url": "/products/fnm-modern?select=x", "bookedOut": False, "tags": ["all", "bookthat", "visible-event"]},
            {"handle": "spice", "title": "Bringing the Autumn Spice! An 18+ Author Event", "start": _parts(day),
             "end": _parts(day + timedelta(hours=2)), "url": "/products/spice", "bookedOut": True,
             "tags": ["Author Events", "books-product-event"]},
        ]}
        faire = day.replace(hour=12, minute=0)
        announcements = {"events": [
            {"title": "We are CLOSED for Thanksgiving.", "start": _parts(day), "end": _parts(day), "allDay": True},
            {"title": "Join us for our holiday Geek Faire! A craft faire featuring prints, plush, comics. 12 PM to 5 PM.",
             "start": _parts(faire), "end": _parts(faire.replace(hour=20)), "allDay": False},
        ]}
        products = {"products": [{"handle": "fnm-modern", "variants": [{"price": "7.50"}],
                                  "body_html": "<p>Our Friday night Modern tournament!<br>RULES FOR ATTENDING</p>"}]}
        single = {"product": {"handle": "spice", "variants": [{"price": "0.00"}], "body_html": "<p>Four authors read.</p>"}}

        def fake_get(url, **kw):
            if "schedule.json" in url:
                return _Resp(schedule)
            if "calendar/events.json" in url:
                return _Resp(announcements)
            if "collections/bookthat" in url:
                return _Resp(products, product_status)
            return _Resp(single, product_status)

        with mock.patch.object(S, "_SESSION") as session:
            session.get.side_effect = fake_get
            return S.scrape_pandemonium("https://pandemoniumbooks.com/apps/bookthatapp/calendar", "ua")

    def test_scrape(self):
        events = {e["name"]: e for e in self._run()}
        self.assertEqual(set(events), {"FNM: Modern", "Bringing the Autumn Spice! An 18+ Author Event",
                                       "Holiday Geek Faire at Pandemonium"})
        fnm = events["FNM: Modern"]
        self.assertEqual((fnm["category"], fnm["price"]), ("gaming", "$7.50"))
        self.assertEqual(fnm["description"], "Our Friday night Modern tournament!")
        self.assertTrue(fnm["url"].startswith("https://pandemoniumbooks.com/products/fnm-modern"))
        self.assertEqual(datetime.fromisoformat(fnm["date"]).astimezone(S.EASTERN).hour, 18)

        spice = events["Bringing the Autumn Spice! An 18+ Author Event"]
        self.assertEqual((spice["category"], spice["price"]), ("books", "Free"))
        self.assertTrue(spice["description"].startswith("Sold out."))

        faire = events["Holiday Geek Faire at Pandemonium"]
        self.assertEqual(faire["category"], "markets")
        self.assertEqual(datetime.fromisoformat(faire["end"]).astimezone(S.EASTERN).hour, 17)

    def test_prices_refused_still_lists_events(self):
        events = self._run(product_status=429)
        self.assertEqual(len(events), 3)
        self.assertIsNone(next(e for e in events if e["name"] == "FNM: Modern")["price"])


if __name__ == "__main__":
    unittest.main()
