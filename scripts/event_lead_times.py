#!/usr/bin/env python3
"""When do events show up on our calendars? Uses the git history of events.json (committed on
every build) as a daily record of what each source listed.

    python3 scripts/event_lead_times.py stats
        How far ahead events were first listed: same day / 1–2 days / 3–6 / 1–2 weeks / 2+ weeks,
        by category and by source. Only sources that usually list 3+ weeks ahead count, and only
        events with 14+ days of history before them, so our own cutoffs don't look like late adds.

    python3 scripts/event_lead_times.py new-since 2026-11-16 [--from 2026-11-17] [--to 2026-11-30]
        Events in the date range that weren't listed at the end of that day: what to look at
        when topping up highlights.json after an earlier pass.

"first listed" means first seen by us: a renamed listing or a newly added source also looks new.
"""
import argparse
import collections
import json
import os
import re
import statistics
import subprocess
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo("America/New_York")
BUCKETS = [(0, 0, "same day"), (1, 2, "1–2 days"), (3, 6, "3–6 days"), (7, 13, "1–2 weeks"), (14, 10 ** 6, "2+ weeks")]


def _git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout


def daily_snapshots():
    """{day: commit} with the last events.json commit of each Boston day, oldest first."""
    out = {}
    for line in filter(None, _git("log", "--reverse", "--format=%H %cI", "--", "events.json").split("\n")):
        h, t = line.split()
        out[datetime.fromisoformat(t).astimezone(ET).date()] = h
    return dict(sorted(out.items()))


def _load(commit=None):
    if commit:
        data = json.loads(_git("show", f"{commit}:events.json"))
    else:
        with open(os.path.join(ROOT, "events.json"), encoding="utf-8") as f:
            data = json.load(f)
    return data["venues"] if isinstance(data, dict) else data


def _event_day(e):
    try:
        d = datetime.fromisoformat(str(e.get("date")).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (d.astimezone(ET) if d.tzinfo else d).date()


def _key(name, day, venue):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())[:40], day, venue


def _events(venues, on_or_after):
    for v in venues:
        for e in v.get("events") or []:
            d = _event_day(e)
            if d and d >= on_or_after:
                yield v, e, d


def stats(min_history=14, deep_days=21):
    snaps = daily_snapshots()
    first_seen, horizon, venue_first, cat = {}, collections.defaultdict(list), {}, {}
    for day, commit in snaps.items():
        try:
            venues = _load(commit)
        except Exception:
            continue
        far = collections.defaultdict(int)
        for v, e, d in _events(venues, day):
            vn = v["venue"]
            venue_first.setdefault(vn, day)
            far[vn] = max(far[vn], (d - day).days)
            k = _key(e.get("name"), d, vn)
            if k not in first_seen:
                first_seen[k] = day
                cat[k] = e.get("category") or v.get("default_category") or "other"
        for vn, n in far.items():
            horizon[vn].append(n)
    start, end = min(snaps), max(snaps)
    deep = {vn for vn, hs in horizon.items() if len(hs) >= 7 and statistics.median(hs) >= deep_days}
    rows = [((d - fs).days, cat[k], vn) for k, fs in first_seen.items() for _, d, vn in [k]
            if vn in deep and d <= end and (d - max(start, venue_first[vn])).days >= min_history]
    if not rows:
        print("Not enough history yet.")
        return
    print(f"{len(snaps)} daily snapshots, {start} to {end}; {len(deep)} of {len(horizon)} sources list "
          f"{deep_days}+ days ahead. {len(rows)} events with {min_history}+ days of history:\n")
    for a, b, lbl in BUCKETS:
        n = sum(a <= r[0] <= b for r in rows)
        print(f"  {lbl:10} {n:6}  {100 * n / len(rows):5.1f}%")
    print("\nBy category (share first listed under a week ahead):")
    by = collections.defaultdict(list)
    for lead, c, _ in rows:
        by[c].append(lead)
    for c, leads in sorted(by.items(), key=lambda x: -len(x[1])):
        if len(leads) >= 50:
            print(f"  {c:14} {100 * sum(x < 7 for x in leads) / len(leads):5.1f}%   median {statistics.median(leads):.0f} days ahead  (n={len(leads)})")
    print("\nSources with the most events first listed under 3 days ahead:")
    by = collections.defaultdict(list)
    for lead, _, vn in rows:
        by[vn].append(lead)
    top = sorted(((sum(x < 3 for x in ls) / len(ls), len(ls), vn) for vn, ls in by.items() if len(ls) >= 40), reverse=True)
    for share, n, vn in top[:15]:
        print(f"  {vn[:40]:40} {100 * share:5.1f}%  (n={n})")
    short = sorted((statistics.median(hs), vn) for vn, hs in horizon.items() if len(hs) >= 7 and statistics.median(hs) < 14)
    if short:
        print("\nSources that usually list under 14 days ahead (median days):")
        print("  " + ", ".join(f"{vn} ({m:.0f})" for m, vn in short))


def new_since(cutoff, start=None, end=None):
    snaps = {d: c for d, c in daily_snapshots().items() if d <= cutoff}
    if not snaps:
        sys.exit(f"No events.json snapshot on or before {cutoff}.")
    then_day = max(snaps)
    start = start or date.today()
    end = end or start + timedelta(days=13)
    old = {_key(e.get("name"), d, v["venue"]) for v, e, d in _events(_load(snaps[then_day]), start)}
    new = collections.defaultdict(list)
    seen = set()
    for v, e, d in _events(_load(), start):
        k = _key(e.get("name"), d, v["venue"])
        if d <= end and k not in old and k not in seen:
            seen.add(k)
            new[d].append((e.get("name") or "", e.get("venue") or v["venue"], e.get("url") or ""))
    total = sum(map(len, new.values()))
    print(f"{total} events between {start} and {end} not listed at the end of {then_day}:\n")
    for d in sorted(new):
        print(f"## {d.strftime('%a %b %-d')} ({len(new[d])})")
        for name, venue, url in sorted(new[d]):
            print(f"  - {name} @ {venue}  {url}")
        print()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    ns = sub.add_parser("new-since")
    ns.add_argument("cutoff", type=date.fromisoformat)
    ns.add_argument("--from", dest="start", type=date.fromisoformat)
    ns.add_argument("--to", dest="end", type=date.fromisoformat)
    a = ap.parse_args()
    if a.cmd == "stats":
        stats()
    else:
        new_since(a.cutoff, a.start, a.end)


if __name__ == "__main__":
    main()
