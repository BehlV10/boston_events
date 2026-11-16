"""Crawling is polite: one request at a time per site, and a site's subdomains share that slot."""
import os
import sys
import threading
import time
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers  # noqa: E402


class PoliteGate(unittest.TestCase):
    def test_one_request_at_a_time_by_default(self):
        self.assertEqual(scrapers.HOST_POLICY_DEFAULT[0], 1)
        for domain, (in_flight, gap) in scrapers.HOST_POLICY.items():
            self.assertEqual(in_flight, 1, domain)
            self.assertGreater(gap, 0, domain)

    def test_subdomains_share_a_site(self):
        s = scrapers._site_of
        self.assertEqual(s("waltham.assabetinteractive.com"), s("medfordlibrary.assabetinteractive.com"))
        self.assertEqual(s("www.eventbrite.com"), "eventbrite.com")
        self.assertEqual(s("www.bbc.co.uk"), "bbc.co.uk")
        self.assertNotEqual(s("www.mfa.org"), s("www.ica.org"))

    def test_subdomains_never_overlap(self):
        gate = scrapers._HostGate()
        live, peak, lock = [0], [0], threading.Lock()

        def hit(host):
            gate.acquire(host)
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            time.sleep(0.02)
            with lock:
                live[0] -= 1
            gate.release(host)

        with unittest.mock.patch.object(scrapers, "HOST_POLICY_DEFAULT", (1, 0.0)):
            ts = [threading.Thread(target=hit, args=(f"lib{i}.assabetinteractive.com",)) for i in range(6)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(peak[0], 1)


if __name__ == "__main__":
    unittest.main()
