"""The Boston Calendar's dateless "goes until 12/31" rows are venue ads and listicles, not events
(Nov 2026: CanalSide food hall, rooftop pickleball, patios and bike paths at "10AM" every day)."""
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402

PAGE = """<ul>
<li class="event"><h3><a href="/events/canalside">CanalSide Food + Drink at CambridgeSide: Food Hall in Cambridge</a></h3>
  <p class="time">goes until 12/20</p><p class="location">CambridgeSide</p></li>
<li class="event"><h3><a href="/events/listicle">16 Karaoke Nights in Boston for Every Day of the Week</a></h3>
  <p class="time">goes until 12/31</p></li>
<li class="event"><h3><a href="/events/oysters">$1 Oysters at Viale</a></h3>
  <p class="time">goes until 12/31</p><p class="location">Viale</p></li>
<li class="event"><h3><a href="/events/wine">Free Wine Tastings - VinoDiVino Newton</a></h3>
  <p class="time">goes until 12/31</p></li>
<li class="event"><h3><a href="/events/show">Real Show</a></h3>
  <p class="time">Friday, November 13, 2026 8:00p</p></li>
<li class="event"><h3><a href="/events/bazaar">The Arsenal Holiday Bazaar</a></h3>
  <p class="time">goes until 11/15</p><p class="location">Arsenal Yards</p></li>
</ul>"""


class StandingRowsTest(unittest.TestCase):
    def test_dateless_rows_dropped_deals_kept(self):
        fixed = datetime(2026, 11, 13, 9, tzinfo=scrapers.EASTERN)
        real_dt = scrapers.datetime

        class _DT(real_dt):
            @classmethod
            def now(cls, tz=None):
                return fixed

        with patch.object(scrapers, "datetime", _DT), \
             patch.object(scrapers, "fetch_soup", lambda url, ua: BeautifulSoup(PAGE, "html.parser")), \
             patch.object(scrapers, "_load_tbc_details_cache", lambda: {}), \
             patch.object(scrapers, "_save_tbc_details_cache", lambda c: None), \
             patch.object(scrapers, "TBC_DETAILS_PER_RUN", 0):
            evs = scrapers.scrape_boston_calendar("https://www.thebostoncalendar.com/events", "ua")
        names = {e["name"] for e in evs}
        self.assertNotIn("CanalSide Food + Drink at CambridgeSide: Food Hall in Cambridge", names)
        self.assertNotIn("16 Karaoke Nights in Boston for Every Day of the Week", names)
        deals = {e["name"] for e in evs if e.get("category") == "deals"}
        self.assertEqual(deals, {"$1 Oysters at Viale", "Free Wine Tastings - VinoDiVino Newton"})
        self.assertNotIn("The Arsenal Holiday Bazaar", names)  # dateless "goes until": dropped too
        self.assertEqual(names - deals, {"Real Show"})


if __name__ == "__main__":
    unittest.main()
