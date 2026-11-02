#!/usr/bin/env python3
"""Generate a ready-to-post Reddit Markdown roundup for r/boston, r/cambridge, and r/somerville."""

import json
import os
import re
from datetime import datetime, timezone, timedelta
import zoneinfo

EASTERN = zoneinfo.ZoneInfo("America/New_York")


def generate_reddit_post():
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "events.json")
    if not os.path.exists(json_path):
        print(f"Error: {json_path} not found. Run 'python server.py export events.json' first.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    venues = data.get("venues", [])
    now = datetime.now(EASTERN)

    # Determine next Friday, Saturday, Sunday
    days_until_friday = (4 - now.weekday()) % 7
    if days_until_friday == 0 and now.hour >= 21:
        days_until_friday = 7
    friday = (now + timedelta(days=days_until_friday)).date()
    saturday = friday + timedelta(days=1)
    sunday = friday + timedelta(days=2)
    weekend_dates = {friday.strftime("%Y-%m-%d"), saturday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")}

    weekend_label = f"{friday.strftime('%b %d')} – {sunday.strftime('%b %d, %Y')}"

    # Buckets
    stage_events = []
    music_events = []
    free_events = []
    gaming_events = []

    seen = set()

    for v in venues:
        vname = v.get("venue", "")
        for e in v.get("events", []):
            name = e.get("name", "")
            d_str = e.get("date", "")
            if not d_str or not name:
                continue

            try:
                dt = datetime.fromisoformat(d_str.replace("Z", "+00:00")).astimezone(EASTERN)
            except Exception:
                continue

            day_str = dt.strftime("%Y-%m-%d")
            if day_str not in weekend_dates:
                continue

            key = (name.lower(), vname.lower(), day_str)
            if key in seen:
                continue
            seen.add(key)

            cat = (e.get("category") or "").lower()
            price = (e.get("price") or "").strip()
            is_free = (e.get("is_free") or "free" in price.lower() or price in ("$0", "$0.00", "0"))
            time_str = dt.strftime("%a %I:%M %p").replace(" 0", " ")

            item = {
                "name": name,
                "venue": vname,
                "time": time_str,
                "url": e.get("url") or "",
                "price": price,
                "desc": e.get("description") or "",
            }

            if is_free:
                free_events.append(item)
            elif cat in ("theater", "comedy", "dance"):
                stage_events.append(item)
            elif cat in ("gaming", "sports"):
                gaming_events.append(item)
            elif cat in ("music", "classical"):
                music_events.append(item)

    # Format Reddit Markdown
    lines = [
        f"# 🎟️ Weekend Events Guide for Boston, Cambridge & Somerville ({weekend_label})",
        "",
        "Hey everyone! Here is a curated guide of live shows, indie productions, concerts, and free community meetups happening across Greater Boston this weekend.",
        "",
    ]

    if stage_events:
        lines.append("### 🎭 Theater, Stage & Comedy")
        for ev in stage_events[:10]:
            p = f" ({ev['price']})" if ev['price'] else ""
            lines.append(f"* **[{ev['name']}]({ev['url']})** @ {ev['venue']} — {ev['time']}{p}")
        lines.append("")

    if music_events:
        lines.append("### 🎵 Concerts & Live Music")
        for ev in music_events[:10]:
            p = f" ({ev['price']})" if ev['price'] else ""
            lines.append(f"* **[{ev['name']}]({ev['url']})** @ {ev['venue']} — {ev['time']}{p}")
        lines.append("")

    if free_events:
        lines.append("### 🆓 Top Free & Low-Cost Highlights")
        for ev in free_events[:8]:
            lines.append(f"* **[{ev['name']}]({ev['url']})** @ {ev['venue']} — {ev['time']} (Free admission)")
        lines.append("")

    if gaming_events:
        lines.append("### 🕹️ Esports, Tabletop & Community Meetups")
        for ev in gaming_events[:6]:
            lines.append(f"* **[{ev['name']}]({ev['url']})** @ {ev['venue']} — {ev['time']}")
        lines.append("")

    lines.extend([
        "---",
        "*(Compiled from the open-source **[Boston Events Calendar](https://behlv10.github.io/boston_events/)** — 8,000+ local events across 175+ indie venues, updated hourly and filterable by neighborhood & MBTA subway line.)*",
        "",
        "> Looking for specific neighborhood hubs? You can browse directly by [Cambridge Tonight](https://behlv10.github.io/boston_events/cambridge-events-tonight/), [Somerville Live Music](https://behlv10.github.io/boston_events/live-music-somerville/), [Free Events Weekend](https://behlv10.github.io/boston_events/free-events-boston-this-weekend/), or [Boston Comedy Shows](https://behlv10.github.io/boston_events/comedy/).",
    ])

    output = "\n".join(lines)
    out_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reddit_roundup.md")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"Wrote Reddit post to {out_file}")
    print("\n--- Preview ---\n")
    print(output[:1200])


if __name__ == "__main__":
    generate_reddit_post()
