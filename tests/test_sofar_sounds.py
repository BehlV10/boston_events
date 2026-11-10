"""Sofar Sounds: secret shows placed in their announced neighborhood."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

import scrapers
import template
from venues_geo import SOFAR_NEIGHBORHOODS, resolve_event_geo


def _iso(days, hour=1):
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


def _show(i, hood, days=3, price=2500, sold_out=False, cancelled=False, themes=(), on_venue=False, city="boston"):
    n = {"title": hood}
    return {"id": str(i), "startsAt": _iso(days), "guestsArriveAt": _iso(days, 0), "ticketPrice": price,
            "isSoldOut": sold_out, "cancelled": cancelled, "city": {"cachedSlug": city},
            "neighborhood": None if on_venue else n, "venue": {"neighborhood": n if on_venue else None},
            "eventThemes": [{"title": t} for t in themes]}


def _scrape(*shows):
    reply = mock.Mock(status_code=200)
    reply.json.return_value = {"data": {"events": {"events": list(shows), "metadata": {"totalRecords": len(shows)}}}}
    reply.raise_for_status = lambda: None
    with mock.patch.object(scrapers, "_SESSION") as session:
        session.post.return_value = reply
        return scrapers.scrape_sofar_sounds("https://www.sofarsounds.com/cities/boston", "ua")


class SofarSounds(unittest.TestCase):
    def test_show_is_placed_in_its_neighborhood(self):
        e = _scrape(_show(66467, "Harvard Square", themes=("Drink Included", "Soulful Songwriters")))[0]
        self.assertEqual(e["name"], "Sofar Sounds: Secret Show in Harvard Square (Soulful Songwriters)")
        self.assertEqual((e["venue"], e["price"], e["category"]), ("Sofar Sounds (Harvard Square)", "$25", "music"))
        self.assertEqual(e["url"], "https://www.sofarsounds.com/events/66467")
        e["_source_venue"] = "Sofar Sounds"
        geo = resolve_event_geo(e)
        self.assertEqual(geo["venue"], "Sofar Sounds (Harvard Square)")
        city = template._event_city(e["venue"], "Sofar Sounds", e)
        self.assertEqual((city, template.resolve_subarea(city, e, geo)[1]), ("cambridge", "harvard_sq"))

    def test_neighborhood_from_the_venue_when_the_event_has_none(self):
        self.assertEqual(_scrape(_show(1, "Union Square", on_venue=True))[0]["venue"], "Sofar Sounds (Union Square)")

    def test_sold_out_cancelled_unknown_and_other_city_shows(self):
        shows = _scrape(_show(1, "Fenway", sold_out=True), _show(2, "Fenway", cancelled=True),
                        _show(3, "Narnia"), _show(4, "Back Bay", city="providence"))
        self.assertEqual([(e["venue"], e["price"]) for e in shows], [("Sofar Sounds (Fenway)", "Sold out")])

    def test_every_sofar_neighborhood_resolves_to_its_own_pin(self):
        for hood, (lat, lng, label, _addr) in SOFAR_NEIGHBORHOODS.items():
            geo = resolve_event_geo({"name": "Sofar Sounds: Secret Show", "venue": f"Sofar Sounds ({hood.title()})",
                                     "_source_venue": "Sofar Sounds", "lat": lat, "lng": lng})
            self.assertEqual(geo["venue"], f"Sofar Sounds ({label})", hood)

    def test_api_error_returns_nothing(self):
        with mock.patch.object(scrapers, "_SESSION") as session:
            session.post.side_effect = scrapers.requests.RequestException("down")
            self.assertEqual(scrapers.scrape_sofar_sounds("https://www.sofarsounds.com/cities/boston", "ua"), [])


if __name__ == "__main__":
    unittest.main()
