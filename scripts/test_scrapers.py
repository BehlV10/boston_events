#!/usr/bin/env python3
"""Boston Events — Scraper & Link Testing Suite.

Run all venue scrapers, validate event schemas, check website HTTP links,
and verify site integrity.

Usage:
  python scripts/test_scrapers.py                  # Run all scrapers in parallel with schema validation
  python scripts/test_scrapers.py --venue "Sinclair"  # Test a specific venue and preview events
  python scripts/test_scrapers.py --links          # Check HTTP status of venue calendar URLs
  python scripts/test_scrapers.py --smoke          # Fast smoke test of top venue scrapers (~3s)
  python scripts/test_scrapers.py --schema         # Validate static JSON files and geo coordinates
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, Any, List, Optional
import urllib.parse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import requests
from scrapers import VENUES, _ALL_VENUES, UA_CHROME
from venues_geo import VENUE_COORDINATES, MIN_LAT, MAX_LAT, MIN_LNG, MAX_LNG
from template import render_page


VALID_CATEGORIES = {
    "music", "comedy", "dance", "theater", "stage", "art", "books",
    "food", "fitness", "community", "gaming", "clubbing", "film", "other",
}


def validate_event_schema(ev: Dict[str, Any], venue_name: str) -> List[str]:
    """Validate that an event dictionary has all required and valid fields."""
    errors = []
    name = ev.get("name")
    if not name or not isinstance(name, str) or len(name.strip()) < 2:
        errors.append(f"Invalid event name: {repr(name)}")

    date_str = ev.get("date")
    if not date_str or not isinstance(date_str, str):
        errors.append(f"Missing date string: {repr(date_str)}")
    else:
        # Date should either be TBA or match ISO/date format
        if date_str != "tba":
            try:
                datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                if not re.match(r"^\d{4}-\d{2}-\d{2}", date_str):
                    errors.append(f"Invalid date format: '{date_str}'")

    url = ev.get("url")
    if url and isinstance(url, str) and url.strip():
        if not (url.startswith("http://") or url.startswith("https://")):
            errors.append(f"URL not http(s): '{url}'")

    cat = ev.get("category")
    if cat and cat not in VALID_CATEGORIES:
        errors.append(f"Unrecognized category: '{cat}'")

    return errors


def test_single_venue(v: Dict[str, Any], show_sample: bool = False) -> Dict[str, Any]:
    """Execute a single venue scraper and return diagnostic statistics."""
    name = v["name"]
    url = v["url"]
    ua = v.get("ua", UA_CHROME)
    scraper_func = v["scraper"]

    t0 = time.time()
    try:
        events = scraper_func(url, ua)
        dur = time.time() - t0

        if not isinstance(events, list):
            return {
                "name": name,
                "url": url,
                "status": "ERROR",
                "events_count": 0,
                "duration": dur,
                "error": f"Scraper did not return list (got {type(events).__name__})",
                "schema_errors": 0,
                "events": [],
            }

        # Validate events
        schema_errs = []
        for ev in events:
            errs = validate_event_schema(ev, name)
            if errs:
                schema_errs.extend(errs)

        status = "OK" if len(events) > 0 else "EMPTY"
        return {
            "name": name,
            "url": url,
            "status": status,
            "events_count": len(events),
            "duration": dur,
            "error": None,
            "schema_errors": len(schema_errs),
            "schema_error_details": schema_errs[:3],
            "events": events if show_sample else events[:3],
        }
    except Exception as e:
        dur = time.time() - t0
        return {
            "name": name,
            "url": url,
            "status": "ERROR",
            "events_count": 0,
            "duration": dur,
            "error": str(e),
            "schema_errors": 0,
            "events": [],
        }


def check_http_link(url: str, timeout: int = 8) -> Dict[str, Any]:
    """Perform an HTTP request to verify if a calendar or event URL is responsive."""
    headers = {"User-Agent": UA_CHROME}
    t0 = time.time()
    try:
        # Try HEAD first for speed; fall back to GET if 405 Method Not Allowed or 501 Not Implemented
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code in (405, 501):
            resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        dur = time.time() - t0
        is_ok = (resp.status_code < 400)
        return {
            "url": url,
            "status_code": resp.status_code,
            "ok": is_ok,
            "duration": dur,
            "error": None if is_ok else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        dur = time.time() - t0
        return {
            "url": url,
            "status_code": 0,
            "ok": False,
            "duration": dur,
            "error": str(e)[:40],
        }


def run_all_scrapers(targets: List[Dict[str, Any]], max_workers: int = 16) -> int:
    """Run all target scrapers concurrently and print an executive summary."""
    print(f"\n🔍 Testing {len(targets)} venue scrapers with {max_workers} worker threads...\n")
    print(f"{'Venue':<44} {'Status':<8} {'Events':<7} {'Time':<7} Notes")
    print("=" * 86)

    results = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(test_single_venue, v): v for v in targets}
        for future in as_completed(future_map):
            res = future.result()
            results.append(res)

            status = res["status"]
            dur = f"{res['duration']:.2f}s"
            count = res["events_count"]
            note = ""

            if status == "OK":
                if res["schema_errors"] > 0:
                    note = f"⚠️ {res['schema_errors']} schema warnings"
            elif status == "EMPTY":
                note = "No upcoming events found on site"
            elif status == "ERROR":
                note = f"❌ {res['error'][:32]}"

            print(f"{res['name'][:42]:<44} {status:<8} {count:<7} {dur:<7} {note}")

    total_time = time.time() - t_start
    ok_count = sum(1 for r in results if r["status"] == "OK")
    empty_count = sum(1 for r in results if r["status"] == "EMPTY")
    err_count = sum(1 for r in results if r["status"] == "ERROR")
    total_events = sum(r["events_count"] for r in results)

    print("=" * 86)
    print(f"📊 SUMMARY: {ok_count} OK | {empty_count} EMPTY | {err_count} ERROR | {total_events:,} Events | {total_time:.1f}s Total\n")

    if err_count > 0:
        print("⚠️ Errors encountered in:")
        for r in results:
            if r["status"] == "ERROR":
                print(f"   • {r['name']}: {r['error']}")
        print()

    return 0 if err_count == 0 else 1


def run_links_check(targets: List[Dict[str, Any]], max_workers: int = 16) -> int:
    """Check venue URLs for broken links (404, SSL errors, timeouts)."""
    print(f"\n🌐 Checking HTTP status of {len(targets)} venue calendar URLs...\n")
    print(f"{'Venue':<42} {'Status':<8} {'Code':<6} {'Time':<7} URL")
    print("=" * 86)

    t_start = time.time()
    results = []

    def _check(v):
        link_res = check_http_link(v["url"])
        link_res["venue"] = v["name"]
        return link_res

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for res in executor.map(_check, targets):
            results.append(res)
            status = "OK" if res["ok"] else "FAIL"
            code = res["status_code"] or "ERR"
            dur = f"{res['duration']:.2f}s"
            print(f"{res['venue'][:40]:<42} {status:<8} {str(code):<6} {dur:<7} {res['url'][:30]}")

    total_time = time.time() - t_start
    failed = [r for r in results if not r["ok"]]
    print("=" * 86)
    print(f"📊 LINK SUMMARY: {len(results) - len(failed)} Live | {len(failed)} Failed | {total_time:.1f}s Total\n")

    if failed:
        print("❌ Failed links:")
        for f in failed:
            print(f"   • {f['venue']}: {f['url']} ({f['error']})")
        print()

    return 0 if not failed else 1


def run_schema_and_geo_check() -> int:
    """Verify JSON files and geo coordinate bounds."""
    print("\n📐 Verifying schemas, geo coordinates, and static files...\n")
    issues = 0

    # 1. Geo coordinates
    print(f"1. Checking {len(VENUE_COORDINATES)} curated venues in venues_geo.py...")
    out_of_bounds = []
    for vname, (lat, lng, neigh, addr, cname) in VENUE_COORDINATES.items():
        if not (MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG):
            out_of_bounds.append((cname, lat, lng))
    if out_of_bounds:
        issues += len(out_of_bounds)
        print(f"   ❌ {len(out_of_bounds)} venues out of Greater Boston bounding box:")
        for name, lat, lng in out_of_bounds:
            print(f"      • {name}: ({lat}, {lng})")
    else:
        print(f"   ✓ All {len(VENUE_COORDINATES)} venues within valid lat/lng bounds [{MIN_LAT}..{MAX_LAT}, {MIN_LNG}..{MAX_LNG}].")

    # 2. community_events.json
    comm_path = os.path.join(BASE_DIR, "community_events.json")
    if os.path.exists(comm_path):
        try:
            with open(comm_path) as f:
                comm_data = json.load(f)
            print(f"2. Checking community_events.json ({len(comm_data)} events)...")
            comm_errs = []
            for ev in comm_data:
                errs = validate_event_schema(ev, ev.get("venue", "Community"))
                if errs:
                    comm_errs.extend(errs)
            if comm_errs:
                issues += len(comm_errs)
                print(f"   ⚠️ Found {len(comm_errs)} validation warnings in community_events.json")
            else:
                print(f"   ✓ community_events.json is valid.")
        except Exception as e:
            issues += 1
            print(f"   ❌ community_events.json invalid JSON: {e}")

    # 3. suggested_venues.json
    sugg_path = os.path.join(BASE_DIR, "suggested_venues.json")
    if os.path.exists(sugg_path):
        try:
            with open(sugg_path) as f:
                sugg_data = json.load(f)
            print(f"3. Checking suggested_venues.json ({len(sugg_data)} pending venues)...")
            print(f"   ✓ suggested_venues.json is valid.")
        except Exception as e:
            issues += 1
            print(f"   ❌ suggested_venues.json invalid JSON: {e}")

    # 4. template render check
    print("4. Testing HTML page generator with sample dataset...")
    mock_venues = [
        {
            "venue": "Test Venue",
            "url": "https://example.com",
            "error": None,
            "events": [
                {
                    "name": "Live Concert",
                    "date": datetime.now().strftime("%Y-%m-%dT20:00:00-04:00"),
                    "url": "https://example.com/tickets",
                    "venue": "Test Venue",
                    "category": "music",
                    "price": "$20",
                }
            ],
        }
    ]
    try:
        html = render_page(mock_venues)
        assert len(html) > 1000
        assert "Wicked Boston Events" in html
        print(f"   ✓ render_page() successfully produced valid HTML ({len(html):,} bytes).")
    except Exception as e:
        issues += 1
        print(f"   ❌ render_page() failed: {e}")

    print(f"\n📊 SCHEMA CHECK: {'✓ All checks passed!' if issues == 0 else f'❌ {issues} issue(s) detected.'}\n")
    return 0 if issues == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Test Boston Events scrapers, links, and schemas.")
    parser.add_argument("--venue", "-v", help="Filter and test specific venue(s) by name")
    parser.add_argument("--links", "-l", action="store_true", help="Check HTTP responsiveness of venue calendar links")
    parser.add_argument("--smoke", "-s", action="store_true", help="Run quick smoke test on top venues")
    parser.add_argument("--schema", action="store_true", help="Validate schemas, geo coordinates, and template rendering")
    parser.add_argument("--workers", "-w", type=int, default=16, help="Number of concurrent workers (default: 16)")

    args = parser.parse_args()

    if args.schema:
        sys.exit(run_schema_and_geo_check())

    targets = VENUES
    if args.venue:
        filter_str = args.venue.lower()
        targets = [v for v in VENUES if filter_str in v["name"].lower()]
        if not targets:
            print(f"No venues matched '{args.venue}'. Available: {', '.join(v['name'] for v in VENUES[:10])}...")
            sys.exit(1)

        print(f"\n🎯 Testing single venue: {targets[0]['name']}")
        res = test_single_venue(targets[0], show_sample=True)
        print(f"Status:   {res['status']}")
        print(f"Events:   {res['events_count']}")
        print(f"Duration: {res['duration']:.2f}s")
        print(f"URL:      {res['url']}")
        if res["error"]:
            print(f"Error:    {res['error']}")
        if res["events"]:
            print(f"\nUpcoming Events Preview ({len(res['events'])} shown):")
            for i, ev in enumerate(res["events"][:8], 1):
                date_str = ev.get("date", "TBA")
                price = f" ({ev['price']})" if ev.get("price") else ""
                print(f"  {i}. [{date_str[:16]}] {ev.get('name')}{price} -> {ev.get('url')}")
        print()
        sys.exit(0 if res["status"] in ("OK", "EMPTY") else 1)

    if args.smoke:
        # Pick 6 diverse scrapers: iCal, Eventbrite, custom HTML, JSON-LD, etc.
        smoke_names = {"The Sinclair", "The Rockwell", "O'Brien's Pub", "Aeronaut Brewing", "City Winery Boston", "Wilbur Theatre"}
        targets = [v for v in VENUES if v["name"] in smoke_names]
        print(f"🚀 Running fast smoke test on {len(targets)} diverse venues...")
        sys.exit(run_all_scrapers(targets, max_workers=6))

    if args.links:
        sys.exit(run_links_check(targets, max_workers=args.workers))

    # Default: Run full parallel scraper health check
    sys.exit(run_all_scrapers(targets, max_workers=args.workers))


if __name__ == "__main__":
    main()
