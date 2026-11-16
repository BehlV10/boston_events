#!/usr/bin/env python3
"""Try the generic scrapers on a website read off a submitted flyer.

    probe_source.py --payload '<event json>' --out probe.json   # probe; prints found=true|false
    probe_source.py --apply probe.json                         # add the found source to discovered_sources.json

When run in GitHub Actions it also writes `found`, `branch` and `title` to $GITHUB_OUTPUT and the
PR body to probe_pr.md, so the workflow can open a PR for review. Nothing is added to the site
until that PR is merged.
"""
import argparse
import ipaddress
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import scrapers  # noqa: E402

# Sites that host many organizers' pages or just link elsewhere; a flyer pointing at one of these
# doesn't identify a calendar we could scrape as a single source.
SKIP_DOMAINS = {
    "instagram.com", "facebook.com", "fb.me", "tiktok.com", "x.com", "twitter.com", "linktr.ee",
    "linkin.bio", "bit.ly", "tinyurl.com", "google.com", "forms.gle", "goo.gl", "youtube.com",
    "ticketmaster.com", "livenation.com", "dice.fm", "partiful.com", "meetup.com", "tixr.com",
    "eventbrite.com", "axs.com", "seetickets.us", "venmo.com", "paypal.com", "gofundme.com",
    "posh.vip",  # its terms forbid scrapers; Posh events come in through submissions
}


def _is_ical(url):
    p = urlparse(url)
    path = p.path.lower()
    return path.endswith(".ics") or "/ical/" in path or "/ics/" in path or "format=ical" in p.query.lower()


def _domain(url):
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _skip_reason(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return "not an http(s) link"
    host = p.hostname.lower()
    try:
        ipaddress.ip_address(host)
        return "IP address, not a website"
    except ValueError:
        pass
    if host == "localhost" or "." not in host:
        return "not a public website"
    dom = _domain(url)
    if _is_ical(url):
        return None  # a calendar feed (Google Calendar, Tockify, ...) is scrapeable wherever it's hosted
    is_eb_org = dom.endswith("eventbrite.com") and "/o/" in p.path
    if not is_eb_org and any(dom == d or dom.endswith("." + d) for d in SKIP_DOMAINS):
        return f"{dom} is a social, ticketing or link site, not the venue's own calendar"
    return None


def known_domains():
    doms = set()
    for v in scrapers._ALL_VENUES:
        url = v.get("url") or ""
        if "eventbrite.com/o/" in url or _is_ical(url):
            doms.add(url.rstrip("/").lower())  # organizer pages share a domain; compare whole URLs
        elif url:
            doms.add(_domain(url))
    return doms


def candidates(url):
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if "eventbrite.com" in p.netloc and "/o/" in p.path:
        return [("eventbrite_org", url)]
    if _is_ical(url):
        return [("ical", url)]
    seen, out = set(), []
    for key, u in (
        ("tribe", f"{base}/wp-json/tribe/events/v1/events"),
        ("squarespace", url),
        ("squarespace", f"{base}/events"),
        ("jsonld", url),
        ("jsonld", f"{base}/events"),
        ("jsonld", f"{base}/calendar"),
    ):
        if (key, u.rstrip("/")) not in seen:
            seen.add((key, u.rstrip("/")))
            out.append((key, u))
    return out


def _upcoming(events):
    now = datetime.now(timezone.utc)
    out = []
    for e in events or []:
        try:
            dt = datetime.fromisoformat(str(e.get("date") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=scrapers.EASTERN)
        if dt >= now and e.get("name"):
            out.append(e)
    return out


def probe(website, venue="", category="", ua=None):
    """Return {"found": bool, ...}. found=True includes scraper, url and a sample of events."""
    website = (website or "").strip()
    reason = _skip_reason(website)
    if reason:
        return {"found": False, "website": website, "reason": reason}
    dom = _domain(website)
    known = known_domains()
    shared_host = _is_ical(website) or "eventbrite.com/o/" in website
    if (dom in known and not shared_host) or website.rstrip("/").lower() in known:
        return {"found": False, "website": website, "reason": f"{dom} is already a source"}
    ua = ua or scrapers.UA_CHROME
    tried = []
    for key, url in candidates(website):
        try:
            events = _upcoming(scrapers.GENERIC_SCRAPERS[key](url, ua))
        except Exception as ex:  # a candidate path that 404s or isn't that platform
            tried.append(f"{key} {url}: {type(ex).__name__}")
            continue
        tried.append(f"{key} {url}: {len(events)} upcoming")
        if events:
            events.sort(key=lambda e: e.get("date") or "")
            return {
                "found": True, "website": website, "scraper": key, "url": url,
                "name": (venue or dom).strip()[:120], "default_category": category or "community",
                "count": len(events),
                "sample": [{"name": e.get("name"), "date": e.get("date"), "url": e.get("url")} for e in events[:8]],
                "tried": tried,
            }
    return {"found": False, "website": website, "reason": "no generic scraper found upcoming events", "tried": tried}


def apply(result, path=None):
    path = path or scrapers.DISCOVERED_SOURCES_FILE
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
    except (OSError, ValueError):
        rows = []
    if any(r.get("url") == result["url"] for r in rows):
        return False
    rows.append({"name": result["name"], "url": result["url"], "scraper": result["scraper"],
                 "default_category": result["default_category"],
                 "added": datetime.now(timezone.utc).date().isoformat(), "from_website": result["website"]})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
        f.write("\n")
    return True


def pr_body(result):
    lines = [
        f"A submitted flyer listed **{result['website']}**. The `{result['scraper']}` scraper found "
        f"{result['count']} upcoming events at {result['url']}.",
        "",
        "Merging adds it to `discovered_sources.json`, so every build scrapes it. Check that it's a real "
        "Greater Boston venue or organizer and that the sample looks right.",
        "",
        "| Date | Event |",
        "|---|---|",
    ]
    for e in result["sample"]:
        name = str(e.get("name") or "").replace("|", "/")[:90]
        lines.append(f"| {str(e.get('date') or '')[:16]} | [{name}]({e.get('url') or result['url']}) |")
    lines += ["", "<details><summary>Paths tried</summary>", ""] + [f"- {t}" for t in result.get("tried", [])]
    lines += ["", "</details>", "", "Opened automatically by the community-event workflow."]
    return "\n".join(lines)


def _write_outputs(result):
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if not gh_out:
        return
    slug = re.sub(r"[^a-z0-9]+", "-", _domain(result.get("website") or "").lower()).strip("-")[:40] or "site"
    with open(gh_out, "a", encoding="utf-8") as f:
        f.write(f"found={'true' if result.get('found') else 'false'}\n")
        if result.get("found"):
            title = re.sub(r"[\r\n]", " ", f"Add source from flyer: {result['name']}")[:120]
            f.write(f"branch=source/{slug}\n")
            f.write(f"title={title}\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--payload", help="community event JSON (needs a website field)")
    ap.add_argument("--out", default="probe.json")
    ap.add_argument("--apply", metavar="PROBE_JSON")
    args = ap.parse_args(argv)

    if args.apply:
        with open(args.apply, encoding="utf-8") as f:
            result = json.load(f)
        print("added" if result.get("found") and apply(result) else "nothing to add")
        return 0

    payload = json.loads(args.payload or "{}")
    if isinstance(payload, dict) and "client_payload" in payload:
        payload = payload["client_payload"]
    website = (payload.get("website") or "").strip()
    result = probe(website, payload.get("venue") or "", payload.get("category") or "") if website else \
        {"found": False, "reason": "no website on the submission"}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    if result.get("found"):
        with open(os.path.join(os.path.dirname(os.path.abspath(args.out)), "probe_pr.md"), "w", encoding="utf-8") as f:
            f.write(pr_body(result))
    _write_outputs(result)
    print(f"found={'true' if result.get('found') else 'false'} {result.get('reason') or result.get('url')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
