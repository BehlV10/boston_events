"""Boston Events — RSS and iCalendar (.ics) feed generators.

Enables passive syndication to:
- RSS readers, Feedly, and local newsletter curators (feed.xml)
- Apple Calendar and Google Calendar direct subscriptions (events.ics)
"""

import html
import os
import re
from datetime import datetime, timezone
from scrapers import EASTERN


def _clean_ics_text(s):
    if not s:
        return ""
    # Remove control characters, backslash escape special ics chars
    s = re.sub(r"[\r\n]+", " ", str(s)).strip()
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")


def export_rss_feed(events, output_path="feed.xml", site_url="https://behlv10.github.io/boston_events"):
    """Generate RSS 2.0 XML feed of upcoming curated events."""
    now_rfc822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    items = []
    seen = set()
    for e in events:
        title = e.get("title") or e.get("name")
        venue = e.get("venue") or e.get("_source_venue") or "Boston Area"
        date_str = e.get("date")
        if not title or not date_str or date_str == "tba":
            continue
        uid = f"{date_str}_{venue}_{title[:25]}".lower()
        if uid in seen:
            continue
        seen.add(uid)

        url = e.get("url") or e.get("link") or site_url
        desc = html.escape(e.get("description") or f"{title} live at {venue}. Direct box office listing on Wicked Boston Events.")

        items.append(f"""    <item>
      <title>{html.escape(title)} at {html.escape(venue)} ({date_str})</title>
      <link>{html.escape(url)}</link>
      <guid isPermaLink="false">{html.escape(uid)}</guid>
      <pubDate>{now_rfc822}</pubDate>
      <description>{desc}</description>
    </item>""")
        if len(items) >= 60:
            break

    rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Wicked Boston Events · Live Feed</title>
    <link>{site_url}/</link>
    <description>Daily curated independent calendar for concerts, comedy, nightlife, and arts across Greater Boston.</description>
    <language>en-us</language>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
    <atom:link href="{site_url}/feed.xml" rel="self" type="application/rss+xml" />
{chr(10).join(items)}
  </channel>
</rss>
"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss_content)
    print(f"wrote {output_path}: {len(rss_content):,} bytes ({len(items)} items)")
    return True


def export_ics_calendar(events, output_path="events.ics", site_url="https://behlv10.github.io/boston_events"):
    """Generate standard iCalendar (.ics) subscription feed for Apple/Google Calendar."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    vcalendar = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Wicked Boston Events//NONSGML Live Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Boston Live Events & Shows",
        "X-WR-TIMEZONE:America/New_York",
        "X-WR-CALDESC:Curated live shows, concerts, and comedy across Boston, Cambridge, and Somerville.",
    ]

    seen = set()
    count = 0
    for e in events:
        title = e.get("title") or e.get("name")
        venue = e.get("venue") or e.get("_source_venue") or "Boston Area"
        date_raw = e.get("date")
        if not title or not date_raw or date_raw == "tba":
            continue

        clean_date = str(date_raw)[:10].replace("-", "")
        if len(clean_date) != 8:
            continue

        uid = f"{clean_date}_{str(abs(hash(venue + title)))[:10]}@wickedbostonevents.com"
        if uid in seen:
            continue
        seen.add(uid)

        url = e.get("url") or e.get("link") or site_url
        desc = f"{title} live at {venue}. Zero ticket broker fees. Details: {url}"

        vcalendar.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART;VALUE=DATE:{clean_date}",
            f"SUMMARY:{_clean_ics_text(title)} @ {_clean_ics_text(venue)}",
            f"LOCATION:{_clean_ics_text(venue)}, Boston MA",
            f"DESCRIPTION:{_clean_ics_text(desc)}",
            f"URL:{url}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])
        count += 1
        if count >= 100:
            break

    vcalendar.append("END:VCALENDAR\n")
    ics_text = "\r\n".join(vcalendar)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_text)
    print(f"wrote {output_path}: {len(ics_text):,} bytes ({count} events)")
    return True
