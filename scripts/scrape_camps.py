#!/usr/bin/env python3
"""Scrape summer camp websites to find updated dates, prices, and 2027 season details.

Usage:
    python3 scripts/scrape_camps.py               # inspect all camps and report findings
    python3 scripts/scrape_camps.py --camp sewataro # check a single camp by id
    python3 scripts/scrape_camps.py --update      # update verified 2027 info into camps.json
"""

import argparse
import concurrent.futures
import json
import os
import re
import ssl
import sys
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMPS_JSON = os.path.join(ROOT, "camps.json")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

# Avoid SSL errors with older LibreSSL on macOS
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def fetch_url(url, timeout=10):
    """Fetch URL contents with browser-like user agent."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            data = resp.read()
            # Try utf-8 first, fallback to latin-1
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data.decode("latin-1", errors="ignore")
    except Exception as exc:
        return f"ERROR: {exc}"


def clean_text(html):
    """Remove script, style, and tag noise from HTML."""
    no_script = re.sub(r"<(script|style|svg|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", no_script)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def inspect_camp(camp):
    """Inspect a camp's website for 2027 season details, prices, and sign-up dates."""
    cid = camp["id"]
    name = camp["name"]
    urls = [camp.get("url", "")] + (camp.get("sources") or [])
    urls = [u for u in urls if u and u.startswith("http")]
    if not urls:
        return {"id": cid, "name": name, "error": "No valid URL"}

    main_url = urls[0]
    html = fetch_url(main_url)
    if html.startswith("ERROR:"):
        return {"id": cid, "name": name, "url": main_url, "error": html}

    text = clean_text(html)
    results = {
        "id": cid,
        "name": name,
        "url": main_url,
        "current_season": camp.get("season"),
        "has_2027": False,
        "snippets_2027": [],
        "dates_found": [],
        "prices_found": [],
    }

    # Search for 2027 season mentions
    m2027 = re.findall(r"(?:[^\.\n]{0,80}\b2027\b[^\.\n]{0,80})", text, re.I)
    if m2027:
        results["has_2027"] = True
        # Keep top 3 distinct snippets
        seen = set()
        for s in m2027:
            s_clean = s.strip()
            if s_clean not in seen and len(s_clean) > 10:
                seen.add(s_clean)
                results["snippets_2027"].append(s_clean)
            if len(results["snippets_2027"]) >= 3:
                break

    # Look for registration / lottery dates
    reg_matches = re.findall(
        r"(?:registration|lottery|enrollment|sign[- ]up|opens?|begins?|deadline)\s+(?:on|is|opens|at)?\s*([A-Za-z]+ \d{1,2}(?:st|nd|rd|th)?,? \d{4})",
        text, re.I
    )
    if reg_matches:
        results["dates_found"] = list(dict.fromkeys(reg_matches))[:3]

    # Look for pricing patterns ($xxx/wk or $xxx per week)
    price_matches = re.findall(r"\$\s*\d{3,4}(?:\s*(?:–|-|to)\s*\$\s*\d{3,4})?\s*(?:/(?:wk|week)|per week)", text, re.I)
    if price_matches:
        results["prices_found"] = list(dict.fromkeys(price_matches))[:3]

    return results


def run_checks(camp_id=None, max_workers=6):
    """Run checks on camps."""
    with open(CAMPS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    camps = data.get("camps", [])
    if camp_id:
        camps = [c for c in camps if c["id"] == camp_id]
        if not camps:
            print(f"Camp with id {camp_id!r} not found in {CAMPS_JSON}")
            sys.exit(1)

    print(f"Scanning {len(camps)} camps for updated 2027 details...")
    findings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_camp = {executor.submit(inspect_camp, c): c for c in camps}
        for future in concurrent.futures.as_completed(future_to_camp):
            res = future.result()
            findings.append(res)
            marker = "⚡ 2027 POSTED" if res.get("has_2027") else ("❌ ERROR" if res.get("error") else "·")
            print(f"[{marker}] {res['name']}")

    return findings, data


def report(findings):
    """Print readable report of findings."""
    posted_2027 = [f for f in findings if f.get("has_2027")]
    errors = [f for f in findings if f.get("error")]

    print("\n" + "=" * 60)
    print(f"SUMMARY: {len(posted_2027)} of {len(findings)} camps have 2027 info posted!")
    print("=" * 60)

    for item in posted_2027:
        print(f"\n🏕️ {item['name']} ({item['id']})")
        print(f"   URL: {item['url']}")
        if item["dates_found"]:
            print(f"   Dates found: {', '.join(item['dates_found'])}")
        if item["prices_found"]:
            print(f"   Prices found: {', '.join(item['prices_found'])}")
        for snip in item["snippets_2027"][:2]:
            print(f"   Snippet: \"{snip}\"")

    if errors:
        print(f"\n⚠️ {len(errors)} camps had connection or fetch errors:")
        for err in errors[:5]:
            print(f"   - {err['name']}: {err.get('error')}")


def main():
    parser = argparse.ArgumentParser(description="Scrape summer camp websites for updated 2027 info.")
    parser.add_argument("--camp", help="Inspect a single camp by ID")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent HTTP requests")
    parser.add_argument("--update", action="store_true", help="Update verified 2027 camps in camps.json")
    args = parser.parse_args()

    findings, data = run_checks(camp_id=args.camp, max_workers=args.workers)
    report(findings)

    if args.update:
        today_iso = date.today().isoformat()
        updated_count = 0
        camps_by_id = {c["id"]: c for c in data["camps"]}
        for f in findings:
            if f.get("has_2027") and f["id"] in camps_by_id:
                c = camps_by_id[f["id"]]
                if c.get("season") != 2027:
                    c["season"] = 2027
                    c["checked"] = today_iso
                    updated_count += 1
        if updated_count > 0:
            with open(CAMPS_JSON, "w", encoding="utf-8") as out:
                json.dump(data, out, indent=1, ensure_ascii=False)
                out.write("\n")
            print(f"\n✅ Updated {updated_count} camps to season 2027 in {CAMPS_JSON}")


if __name__ == "__main__":
    main()
