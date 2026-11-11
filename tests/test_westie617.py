"""Westie 617: each dated store product is one Wednesday drop-in class + social dance."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

import scrapers

EXCERPT = "<p>Includes your choice of the 8:15pm <strong>Basic</strong> drop-in class, plus social dancing.</p>"


def _product(day, title="Drop-In Class & Dance", excerpt=EXCERPT, unlimited=True, qty=0):
    stock = None if unlimited else {"quantity": qty}
    return {"title": f"{day:%m/%d/%y} {title}", "fullUrl": "/store/p/abc", "excerpt": excerpt,
            "structuredContent": {"variants": [
                {"attributes": {"Dance": "General admission ($12 + processing fee)"}, "unlimited": unlimited, "stock": stock},
                {"attributes": {"Dance": "Student admission ($10 + processing fee)"}, "unlimited": unlimited, "stock": stock}]}}


def _scrape(*items):
    reply = mock.Mock()
    reply.json.return_value = {"items": list(items)}
    reply.raise_for_status = lambda: None
    with mock.patch.object(scrapers, "_SESSION") as session:
        session.get.return_value = reply
        return scrapers.scrape_westie617("https://www.westie617.com/store", "ua")


class Westie617(unittest.TestCase):
    def setUp(self):
        self.next_week = datetime.now(scrapers.EASTERN).date() + timedelta(days=7)

    def test_product_becomes_one_event_at_class_time(self):
        [e] = _scrape(_product(self.next_week))
        start = datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN)
        self.assertEqual((start.date(), start.hour, start.minute), (self.next_week, 20, 15))
        self.assertEqual((e["venue"], e["price"], e["category"]), ("Westie 617", "$10 - $12", "dance"))
        self.assertEqual(e["url"], "https://www.westie617.com/store/p/abc")

    def test_time_comes_from_the_listing(self):
        [e] = _scrape(_product(self.next_week, excerpt="<p>Join the 7:30pm class</p>"))
        start = datetime.fromisoformat(e["date"]).astimezone(scrapers.EASTERN)
        self.assertEqual((start.hour, start.minute), (19, 30))

    def test_skips_past_sold_out_and_undated_products(self):
        past = self.next_week - timedelta(days=21)
        self.assertEqual(_scrape(_product(past), _product(self.next_week, unlimited=False, qty=0),
                                 {"title": "Gift Card", "excerpt": ""}), [])


if __name__ == "__main__":
    unittest.main()
