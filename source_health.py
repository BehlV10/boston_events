"""Which sources are working, written after every crawl so a broken or quiet venue gets noticed.

The report lists sources that errored, sites that refused us this run, and sources with nothing
in the next two weeks (with each one's next event, so a seasonal venue is easy to tell from a
broken one), plus the venues we know about but can't read. In GitHub Actions it goes on the run's
summary page; locally it's printed and saved to .cache/source_status.json (not published).
"""
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

WINDOW_DAYS = 14

# Venues with real shows that we can't read, and why. Kept by hand; re-check now and then.
# Their shows come from Boston Shows instead (scrapers.BOSTON_SHOWS_GAP_VENUES).
KNOWN_UNSCRAPABLE = [
    {"venue": "JFK Presidential Library (Dorchester)", "url": "https://www.jfklibrary.org/events-and-awards/forums",
     "reason": "403 to scripts", "next_step": "Some forums appear via Eventbrite; ask the library for a calendar feed"},
    {"venue": "Roslindale Village Main Street", "url": "https://www.roslindale.net/events",
     "reason": "Calendar loads in a Wix widget, nothing in the page", "next_step": "Ask them for a public calendar link"},
    {"venue": "Wally's Cafe", "url": "https://wallyscafe.com/ritual/",
     "reason": "Cloudflare bot check on the whole site (even robots.txt)",
     "next_step": "Covered via Boston Shows; ask Wally's for a calendar feed"},
    {"venue": "The Black Rose", "url": "https://www.blackroseboston.com/live-music1/",
     "reason": "Monthly lineup is posted as an image of a calendar",
     "next_step": "Covered via Boston Shows; ask for a text or calendar version"},
    {"venue": "Kestra (Omni Boston Seaport)",
     "url": "https://www.omnihotels.com/hotels/boston-seaport/things-to-do/event-calendar",
     "reason": "Cloudflare bot check", "next_step": "Covered via Boston Shows; ask the hotel for its Trumba calendar link"},
    {"venue": "Harvard University (music)", "url": "https://music.fas.harvard.edu/events",
     "reason": "Access Denied (Akamai bot block)", "next_step": "Covered via Boston Shows; ask Harvard for a calendar feed"},
    {"venue": "Memorial Church (Harvard)", "url": "https://memorialchurch.harvard.edu/events",
     "reason": "Access Denied (Akamai bot block)", "next_step": "Covered via Boston Shows; ask Harvard for a calendar feed"},
    {"venue": "Rosa y Marigold", "url": "https://www.rosaymarigold.com/",
     "reason": "Site gives the music nights (Mon/Wed/Thu 6:30) but not who's playing",
     "next_step": "Covered via Boston Shows"},
    {"venue": "Silhouette Lounge", "url": "https://www.instagram.com/thesilhouetteallston",
     "reason": "Shows only posted on Instagram (sign-in wall)", "next_step": "Covered via Boston Shows"},
    {"venue": "Southie Live Music Club (Lithuanian Club)", "url": "https://www.instagram.com/southielivemusic",
     "reason": "Shows only posted on Instagram (sign-in wall)", "next_step": "Covered via Boston Shows"},
    {"venue": "An Síbín", "url": "https://www.instagram.com/ansibinpub",
     "reason": "Shows only posted on Instagram (sign-in wall)", "next_step": "Covered via Boston Shows"},
]


def _when(e):
    try:
        t = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def source_status(venues, refused=None, now=None, days=WINDOW_DAYS):
    """One row per source: events overall, in the next `days`, the next event, and a status."""
    now = now or datetime.now(timezone.utc)
    soon = now + timedelta(days=days)
    refused = refused or {}
    rows = []
    for v in venues:
        times = sorted(t for t in (_when(e) for e in v.get("events") or []) if t and t >= now - timedelta(hours=6))
        near = sum(1 for t in times if t <= soon)
        host = urlparse(v.get("url") or "").netloc.lower()
        refusal = next((r for h, r in refused.items() if host == h or host.endswith("." + h) or h.endswith("." + host)), None)
        if v.get("error"):
            status = "error"
        elif refusal:
            status = "refused"
        elif near == 0:
            status = "empty"
        else:
            status = "ok"
        rows.append({
            "source": v.get("venue"), "url": v.get("url"), "status": status,
            "events": len(v.get("events") or []), "next_two_weeks": near,
            "next_event": times[0].date().isoformat() if times else None,
            "error": (v.get("error") or refusal or "")[:200] or None,
            "from_cache": bool(v.get("cached")), "kept_last_good": bool(v.get("fallback")),
        })
    order = {"error": 0, "refused": 1, "empty": 2, "ok": 3}
    rows.sort(key=lambda r: (order[r["status"]], (r["source"] or "").lower()))
    return rows


def _markdown(rows, overnight=()):
    count = lambda s: sum(1 for r in rows if r["status"] == s)
    out = ["## Source health", "",
           f"{len(rows)} sources: **{count('ok')} OK**, {count('error')} errored, {count('refused')} refused us, "
           f"{count('empty')} with nothing in the next {WINDOW_DAYS} days.", ""]
    problems = [r for r in rows if r["status"] != "ok"]
    if problems:
        out += ["| Source | Status | Events | Next event | Note |", "|---|---|---|---|---|"]
        for r in problems:
            note = r["error"] or ("kept last good data" if r["kept_last_good"] else "")
            out.append(f"| [{r['source']}]({r['url']}) | {r['status']} | {r['events']} | {r['next_event'] or '—'} | {note} |")
        out.append("")
    if overnight:
        out += ["### Removed for a 1–6 AM start", "", "Each of these has a wrong time at its source.", "",
                "| Source | Event | Listed start |", "|---|---|---|"]
        out += [f"| {o['source']} | [{o['name']}]({o['url']}) | {o['start'][:16]} |" for o in overnight]
        out.append("")
    out += ["### Venues we can't read", "", "| Venue | Why | Next step |", "|---|---|---|"]
    out += [f"| [{k['venue']}]({k['url']}) | {k['reason']} | {k['next_step']} |" for k in KNOWN_UNSCRAPABLE]
    return "\n".join(out) + "\n"


def write_report(venues, refused=None, path=os.path.join(".cache", "source_status.json"), overnight=()):
    rows = source_status(venues, refused)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "window_days": WINDOW_DAYS,
                   "sources": rows, "known_unscrapable": KNOWN_UNSCRAPABLE,
                   "overnight_removed": list(overnight)}, f, indent=1)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(_markdown(rows, overnight))
    for r in rows:
        if r["status"] != "ok":
            print(f"source {r['status']:7s} {r['source']}: {r['events']} events, next {r['next_event'] or 'none'}"
                  + (f" ({r['error']})" if r["error"] else ""))
    for o in overnight:
        print(f"overnight start removed: {o['source']}: {o['name']} ({o['start'][:16]})")
    return rows
