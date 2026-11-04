#!/usr/bin/env python3
"""Check every event link on the site.

Usage:
    python3 scripts/check_links.py                 # all unique event URLs in events.json
    python3 scripts/check_links.py --date 2026-11-04   # only events on that Eastern date
    python3 scripts/check_links.py --out /tmp/links.json

Classification:
    ok        2xx/3xx
    blocked   401/403/429/999 or Cloudflare/captcha challenge: real browsers usually load these
    dead      404/410, DNS failure, connection refused, TLS failure, or 5xx after retry
    timeout   no response in time (retry later; not conclusive)
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
EASTERN = ZoneInfo("America/New_York")
BLOCKED = {401, 403, 429, 999}


def collect(date=None):
    with open(os.path.join(ROOT, "events.json"), encoding="utf-8") as f:
        data = json.load(f)
    urls = defaultdict(list)
    for v in data.get("venues", []):
        for e in v.get("events", []):
            u = (e.get("url") or "").strip()
            if not u.startswith("http"):
                continue
            if date and e.get("date"):
                try:
                    d = datetime.fromisoformat(str(e["date"]).replace("Z", "+00:00"))
                    d = d.astimezone(EASTERN) if d.tzinfo else d
                    if d.date().isoformat() != date:
                        continue
                except ValueError:
                    continue
            elif date:
                continue
            urls[u].append(e.get("name") or "")
    return urls


def check(url, session):
    last = ("timeout", None, "")
    for attempt in range(2):
        try:
            r = session.get(url, headers={"User-Agent": UA}, timeout=12,
                            allow_redirects=True, stream=True)
            code = r.status_code
            body = ""
            if code == 200:
                body = r.raw.read(4096, decode_content=True).decode("utf-8", "ignore").lower()
            r.close()
            if code in BLOCKED or (code == 200 and ("just a moment" in body and "cloudflare" in body)):
                return ("blocked", code, r.url)
            if code in (404, 410):
                return ("dead", code, r.url)
            if code >= 500:
                last = ("dead", code, r.url)
                continue
            return ("ok", code, r.url)
        except requests.exceptions.Timeout:
            last = ("timeout", None, "")
        except requests.exceptions.SSLError as ex:
            return ("dead", "ssl", str(ex)[:120])
        except requests.exceptions.ConnectionError as ex:
            last = ("dead", "conn", str(ex)[:120])
        except requests.exceptions.RequestException as ex:
            last = ("dead", "err", str(ex)[:120])
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    urls = collect(args.date)
    print(f"Checking {len(urls)} unique URLs...", file=sys.stderr)
    results = {}
    session = requests.Session()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(check, u, session): u for u in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            results[futs[fut]] = fut.result()
            if i % 200 == 0:
                print(f"  {i}/{len(urls)}", file=sys.stderr)

    summary = defaultdict(int)
    for status, _, _ in results.values():
        summary[status] += 1
    print(dict(summary))
    for status in ("dead", "timeout"):
        rows = [(u, results[u]) for u in results if results[u][0] == status]
        if rows:
            print(f"\n== {status.upper()} ({len(rows)}) ==")
            for u, (_, code, info) in sorted(rows):
                print(f"  [{code}] {u}  <- {urls[u][0][:60]}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({u: {"status": s, "code": c, "final": i, "events": urls[u][:3]}
                       for u, (s, c, i) in results.items()}, f, indent=1)


if __name__ == "__main__":
    main()
