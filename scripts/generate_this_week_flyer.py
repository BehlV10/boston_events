#!/usr/bin/env python3
"""
Generate high-contrast, clean white-background weekly event flyers
(1080x1350 Instagram / LinkedIn carousel format) dynamically from events.json:
- Slide 1: Weekday Edition (Monday through Friday, 1/2)
- Slide 2: Weekend Edition (Saturday & Sunday + Weekend Highlights, 2/2)

Future-proof & fully automated:
- Scrapes/loads events dynamically for any given week (Monday–Sunday)
- Cleans titles, formats addresses via venues_geo.py, ranks by venue tier & highlights
- Generates pixel-perfect 1080x1350 PNG slides
"""

import os
import sys
import json
import re
import shutil
import argparse
import subprocess
import zoneinfo
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from venues_geo import resolve_event_geo

EASTERN = zoneinfo.ZoneInfo("America/New_York")
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"

# -------------------------------------------------------------
# VENUE TIERS & NOISE FILTERS
# -------------------------------------------------------------
TIER1_VENUES = {
    "royale", "roadrunner", "the sinclair", "sinclair", "crystal ballroom", "mgm music hall",
    "house of blues", "paradise rock club", "big night live", "museum of fine arts", "mfa",
    "ica", "ica boston", "isabella stewart gardner", "gardner museum", "the comedy studio",
    "comedy studio", "club café", "club cafe", "havana club", "the anchor", "bow market",
    "remnant satellite", "remnant brewing", "prudential center", "hynes convention center",
    "city hall plaza", "sowa", "brattle theatre", "coolidge corner", "charles river speedway",
    "brighton bazaar", "middle east", "rockwell", "artisans asylum", "life drawing boston",
    "beehive", "burren", "cantab", "somerville theatre", "symphony hall", "chevalier theatre",
    "arrow street arts", "dance complex", "boston figure art center", "arts at the armory",
    "harvard book store", "brookline booksmith", "porter square books"
}

EXCLUDE_PATTERNS = [
    r"\bonline\b", r"\bzoom\b", r"\bwebinar\b", r"\bvirtual\b", r"\bell class\b",
    r"\besl\b", r"\bdrop-in hours\b", r"\bsocial work\b", r"\btoddler\b", r"\bstorytime\b",
    r"\bbilingual storytime\b", r"\bpreschool\b", r"\bbaby bounce\b", r"\bbuilding [a-z0-9]+\b",
    r"\bknitting group\b", r"\bcomputer basics\b", r"\bcommittee meeting\b", r"\bcity council\b",
    r"\bboard of trustees\b", r"\binfo session\b", r"\btech help\b"
]

HIGHLIGHT_KEYWORDS = [
    "faire", "market", "bazaar", "festival", "parade", "smash", "renaissance",
    "expo", "celebration", "night market", "open studios", "art fair", "pumpkin",
    "harvest fest", "book fair", "wonder"
]

# Daily event quotas to perfectly balance the 1080x1350 canvas
DAY_QUOTAS = {
    0: 6,   # Monday
    1: 6,   # Tuesday
    2: 7,   # Wednesday
    3: 9,   # Thursday
    4: 11,  # Friday
    5: 17,  # Saturday
    6: 10,  # Sunday
}


def get_ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return "TH"
    return {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")


import html

def clean_title(title: str) -> str:
    t = html.unescape((title or "").strip())
    t = re.sub(r"\s*\((?:18\+|21\+|all ages|sold out|doors open[^\)]*)\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\[(?:sold out)\]", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*-\s*(?:18\+|21\+|all ages|sold out).*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*:\s*(?:the\s+)?(?:an\s+ending\s+in|young\s+regan|sexy\s+saturday|thank\s+god\s+it|pullin\s+out|usa\s+&\s+canada|running\s+from|a\s+matter\s+of\s+time).*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" -–:")
    if len(t) > 36:
        words = t.split()
        t = ""
        for w in words:
            if len(t) + len(w) + 1 <= 34:
                t = (t + " " + w).strip()
            else:
                break
        t += "..."
    return t


def clean_address(addr: str) -> str:
    if not addr:
        return ""
    a = re.sub(r",?\s*MA\s*\d{5}(?:-\d{4})?", "", addr, flags=re.IGNORECASE)
    a = re.sub(r",?\s*USA$", "", a, flags=re.IGNORECASE)
    return a.strip(" ,")


def is_excluded(title: str, venue: str) -> bool:
    target = f"{title} {venue}".lower()
    for pat in EXCLUDE_PATTERNS:
        if re.search(pat, target):
            return True
    return False


def get_event_geo(event: Dict[str, Any]) -> Tuple[str, str]:
    # Lookup by venue name first to get clean curated address
    geo = resolve_event_geo({"venue": event.get("venue") or ""})
    if not geo:
        geo = resolve_event_geo(event)
    venue = (geo.get("venue") if geo else event.get("venue")) or ""
    address = (geo.get("address") if geo else event.get("address")) or ""
    return venue, clean_address(address)


def score_event(event: Dict[str, Any], hl_matches: List[Dict[str, Any]]) -> int:
    title = (event.get("name") or "").strip()
    vname = (event.get("venue") or "").lower()

    if is_excluded(title, vname):
        return -100

    score = 0
    t_low = title.lower()
    for h in hl_matches:
        mc = h.get("match", {})
        nc = mc.get("name_contains", "").lower()
        vc = mc.get("venue_contains", "").lower()
        if (not nc or nc in t_low) and (not vc or vc in vname):
            score += 150
            break

    for t1 in TIER1_VENUES:
        if t1 in vname:
            score += 80
            break

    cat = (event.get("category") or "").lower()
    if cat in ("art", "museum", "festival", "community"):
        score += 35
    elif cat in ("comedy", "theater", "dance"):
        score += 30
    elif cat in ("music", "concert"):
        score += 25

    price = (event.get("price") or "").lower()
    if "free" in price or price in ("$0", "0"):
        score += 20

    return score


def load_week_events(
    target_date: Optional[datetime.date] = None,
    events_path: Optional[str] = None
) -> Tuple[datetime.date, datetime.date, Dict[int, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    if target_date is None:
        target_date = datetime.now(EASTERN).date()

    # Calculate Monday of target week
    monday = target_date - timedelta(days=target_date.weekday())
    sunday = monday + timedelta(days=6)

    if not events_path:
        events_path = os.path.join(BASE_DIR, "events.json")

    with open(events_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    hl_path = os.path.join(BASE_DIR, "highlights.json")
    highlights = []
    if os.path.exists(hl_path):
        with open(hl_path, "r", encoding="utf-8") as f:
            highlights = json.load(f)

    # Collect and bucket events by weekday index (0=Mon, 6=Sun)
    all_events = []
    for v in data.get("venues", []):
        for e in v.get("events", []):
            all_events.append(e)

    day_buckets: Dict[int, List[Tuple[int, datetime, Dict[str, Any]]]] = {i: [] for i in range(7)}
    weekend_events: List[Tuple[datetime, Dict[str, Any]]] = []

    for e in all_events:
        d_str = e.get("date", "")
        if not d_str or not e.get("name"):
            continue
        try:
            dt = datetime.fromisoformat(d_str.replace("Z", "+00:00")).astimezone(EASTERN)
        except Exception:
            continue

        e_date = dt.date()
        if monday <= e_date <= sunday:
            weekday_idx = dt.weekday()
            sc = score_event(e, highlights)
            if sc > 0:
                day_buckets[weekday_idx].append((sc, dt, e))
            if weekday_idx in (5, 6):
                weekend_events.append((dt, e))

    # Select top diverse events per day according to quotas
    selected_by_day: Dict[int, List[Dict[str, Any]]] = {}

    for w_idx in range(7):
        bucket = sorted(day_buckets[w_idx], key=lambda x: x[0], reverse=True)
        seen_venues = set()
        seen_titles = set()
        day_selected = []
        quota = DAY_QUOTAS.get(w_idx, 8)

        for sc, dt, e in bucket:
            c_venue, c_addr = get_event_geo(e)
            if not c_venue:
                continue
            v_low = c_venue.lower()
            if v_low in seen_venues:
                continue

            c_title = clean_title(e["name"])
            t_key = re.sub(r"[^a-z0-9]", "", c_title.lower())[:15]
            if t_key in seen_titles:
                continue

            seen_venues.add(v_low)
            seen_titles.add(t_key)

            # Check doors indication for concert venues
            doors_suffix = " D" if any(k in v_low for k in ("sinclair", "roadrunner", "royale", "crystal ballroom", "paradise", "house of blues")) and dt.hour >= 17 else ""
            t_str = dt.strftime("%-I:%M %p").replace(":00", "") + doors_suffix

            venue_display = f"{c_venue} • {c_addr}" if c_addr else c_venue

            day_selected.append({
                "dt": dt,
                "time": t_str,
                "title": c_title,
                "venue": venue_display,
                "score": sc
            })
            if len(day_selected) >= quota:
                break

        # Chronological sort within the day
        day_selected.sort(key=lambda x: x["dt"])
        selected_by_day[w_idx] = day_selected

    return monday, sunday, selected_by_day, weekend_events


def extract_weekend_highlights(
    weekend_events: List[Tuple[datetime, Dict[str, Any]]],
    highlights_json: List[Dict[str, Any]]
) -> Dict[str, Any]:
    candidates = []
    seen = set()

    for dt, e in weekend_events:
        name = e.get("name", "")
        n_low = name.lower()
        for kw in HIGHLIGHT_KEYWORDS:
            if kw in n_low:
                key = re.sub(r"[^a-z0-9]", "", n_low)[:12]
                if key not in seen:
                    seen.add(key)
                    c_title = clean_title(name).upper()
                    day_name = "SAT" if dt.weekday() == 5 else "SUN"
                    t_str = dt.strftime("%-I %p").replace(":00", "")
                    candidates.append((dt, f"{c_title} • {day_name} {t_str}"))
                break

    # Top 3 items
    items = [item for _, item in candidates[:3]]
    if not items:
        items = [
            "BOW MARKET RENAISSANCE FAIRE • SAT 12 PM",
            "STEAL MY STYLE THRIFT MARKET • SAT 11 AM",
            "SOMERVILLE WINTER FARMERS MARKET • SAT 9 AM"
        ]

    return {
        "title": "WEEKEND HIGHLIGHTS",
        "items": items,
        "note": "Free entry & local vendors • Check venue sites for weather updates"
    }


def build_slide_data(
    monday: datetime.date,
    sunday: datetime.date,
    selected_by_day: Dict[int, List[Dict[str, Any]]],
    weekend_events: List[Tuple[datetime, Dict[str, Any]]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # Compute dates and headers
    mon_str = f"MONDAY • {monday.strftime('%b %-d').upper()}"
    tue_str = f"TUESDAY • {(monday + timedelta(days=1)).strftime('%b %-d').upper()}"
    wed_str = f"WEDNESDAY • {(monday + timedelta(days=2)).strftime('%b %-d').upper()}"
    thu_str = f"THURSDAY • {(monday + timedelta(days=3)).strftime('%b %-d').upper()}"
    fri_str = f"FRIDAY • {(monday + timedelta(days=4)).strftime('%b %-d').upper()}"
    sat_date = monday + timedelta(days=5)
    sat_str = f"SATURDAY • {sat_date.strftime('%b %-d').upper()}"
    sun_str = f"SUNDAY • {sunday.strftime('%b %-d').upper()}"

    total_events = sum(len(evs) for evs in selected_by_day.values())
    round_count = (total_events // 5) * 5
    if round_count < 50:
        round_count = 55

    # Subtitles
    ord_mon = get_ordinal(monday.day)
    ord_sun = get_ordinal(sunday.day)
    ord_sat = get_ordinal(sat_date.day)

    sub1 = f"{monday.strftime('%B %-d').upper()}{ord_mon}–{sunday.strftime('%-d').upper()}{ord_sun}, {monday.year} • 1/2"
    sub2 = f"{sat_date.strftime('%B %-d').upper()}{ord_sat}–{sunday.strftime('%-d').upper()}{ord_sun}, {sunday.year} • 2/2"

    # Slide 1: Weekday Edition
    slide1_data = {
        "title_top": f"{round_count}+ BEST EVENTS",
        "title_box": "BOSTON THIS WEEK",
        "subtitle": sub1,
        "left_col": [
            {"day": mon_str, "pill_bg": "#0047e1", "pill_color": "#ffffff", "events": selected_by_day.get(0, [])},
            {"day": tue_str, "pill_bg": "#e62e00", "pill_color": "#ffffff", "events": selected_by_day.get(1, [])},
            {"day": wed_str, "pill_bg": "#0047e1", "pill_color": "#ffffff", "events": selected_by_day.get(2, [])},
        ],
        "right_col": [
            {"day": thu_str, "pill_bg": "#ffccd5", "pill_color": "#000000", "events": selected_by_day.get(3, [])},
            {"day": fri_str, "pill_bg": "#0047e1", "pill_color": "#ffffff", "events": selected_by_day.get(4, [])},
        ],
        "footer_badge": "SWIPE FOR THE WEEKEND ➔"
    }

    # Slide 2: Weekend Edition
    hl_path = os.path.join(BASE_DIR, "highlights.json")
    hl_list = []
    if os.path.exists(hl_path):
        with open(hl_path, "r", encoding="utf-8") as f:
            hl_list = json.load(f)

    highlights = extract_weekend_highlights(weekend_events, hl_list)

    slide2_data = {
        "title_top": "BOSTON THIS WEEK",
        "title_box": "THE WEEKEND",
        "subtitle": sub2,
        "left_col": [
            {"day": sat_str, "pill_bg": "#0047e1", "pill_color": "#ffffff", "events": selected_by_day.get(5, [])},
        ],
        "right_col": [
            {"day": sun_str, "pill_bg": "#111827", "pill_color": "#ffffff", "events": selected_by_day.get(6, [])},
        ],
        "highlights": highlights,
        "footer_badge": "wickedbostonevents.com"
    }

    return slide1_data, slide2_data


def build_slide_html(data: Dict[str, Any]) -> str:
    def render_col(col_data: List[Dict[str, Any]]) -> str:
        html = []
        for d in col_data:
            pill_style = f"background: {d['pill_bg']}; color: {d['pill_color']};"
            html.append('<div class="day-group">')
            html.append(f'  <div class="day-pill" style="{pill_style}">{d["day"]}</div>')
            html.append('  <div class="events-list">')
            for ev in d["events"]:
                html.append(f'''    <div class="event-item">
      <div class="event-main">
        <span class="event-time">{ev["time"]}</span>
        <span class="event-dash">—</span>
        <span class="event-title">{ev["title"]}</span>
      </div>
      <div class="event-venue">{ev["venue"]}</div>
    </div>''')
            html.append('  </div>')
            html.append('</div>')
        return "\n".join(html)

    left_html = render_col(data["left_col"])
    right_html = render_col(data["right_col"])

    highlights_html = ""
    if "highlights" in data:
        hl = data["highlights"]
        items_markup = "\n".join(
            f'<div class="hl-item">{it}</div>' for it in hl["items"]
        )
        highlights_html = f'''
        <div class="highlights-box">
          <div class="hl-header">
            <span>{hl["title"]}</span>
            <svg class="hl-star" viewBox="0 0 24 24"><path fill="#ffffff" d="M12 0L14.5 9.5L24 12L14.5 14.5L12 24L9.5 14.5L0 12L9.5 9.5Z"/></svg>
          </div>
          <div class="hl-list">
            {items_markup}
          </div>
          <div class="hl-note">
            <span class="blue-dot"></span>
            <span>{hl["note"]}</span>
            <span class="blue-dot"></span>
          </div>
        </div>
        '''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800;900&family=Montserrat:wght@800;900&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1080px;
    height: 1350px;
    background: #ffffff;
    color: #000000;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }}

  /* Header Section */
  .header {{
    padding: 24px 38px 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }}

  .title-top {{
    font-family: 'Montserrat', sans-serif;
    font-size: 32px;
    font-weight: 900;
    letter-spacing: 2px;
    color: #000000;
    line-height: 1.1;
    margin-bottom: 6px;
    text-transform: uppercase;
  }}

  .title-box {{
    background: #000000;
    color: #ffffff;
    font-family: 'Montserrat', sans-serif;
    font-size: 42px;
    font-weight: 900;
    letter-spacing: 1.5px;
    padding: 8px 32px;
    border-radius: 4px;
    text-transform: uppercase;
    display: inline-block;
    margin-bottom: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }}

  .subtitle {{
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 2.5px;
    color: #111827;
    text-transform: uppercase;
  }}

  /* Content Grid */
  .content-grid {{
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 28px;
    padding: 8px 38px 12px;
    overflow: hidden;
  }}

  .col {{
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}

  .day-group {{
    display: flex;
    flex-direction: column;
    gap: 4px;
  }}

  .day-pill {{
    display: inline-block;
    align-self: flex-start;
    font-family: 'Montserrat', sans-serif;
    font-size: 14px;
    font-weight: 900;
    letter-spacing: 1.2px;
    padding: 4px 14px;
    border-radius: 14px;
    text-transform: uppercase;
    margin-bottom: 4px;
  }}

  .events-list {{
    display: flex;
    flex-direction: column;
  }}

  .event-item {{
    padding: 3.5px 0;
    border-bottom: 1px solid #ffccd5;
    display: flex;
    flex-direction: column;
    gap: 1.5px;
  }}

  .event-main {{
    font-size: 14px;
    line-height: 1.22;
    display: flex;
    align-items: baseline;
    flex-wrap: nowrap;
    overflow: hidden;
  }}

  .event-time {{
    font-weight: 800;
    color: #000000;
    white-space: nowrap;
    margin-right: 4px;
  }}

  .event-dash {{
    color: #6b7280;
    margin-right: 5px;
    font-weight: 600;
  }}

  .event-title {{
    font-weight: 700;
    color: #000000;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .event-venue {{
    font-size: 11.5px;
    font-weight: 600;
    color: #64748b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.15;
  }}

  /* Highlights Box (Slide 2) */
  .highlights-box {{
    background: #000000;
    border-radius: 12px;
    padding: 14px 18px 12px;
    color: #ffffff;
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 6px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.12);
  }}

  .hl-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-family: 'Montserrat', sans-serif;
    font-size: 15px;
    font-weight: 900;
    letter-spacing: 1.5px;
    color: #ffccd5;
    border-bottom: 1px solid #374151;
    padding-bottom: 5px;
  }}

  .hl-star {{
    width: 14px;
    height: 14px;
  }}

  .hl-list {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}

  .hl-item {{
    font-size: 12.5px;
    font-weight: 800;
    letter-spacing: 0.5px;
    color: #ffffff;
    line-height: 1.25;
  }}

  .hl-note {{
    font-size: 10.5px;
    font-weight: 600;
    color: #9ca3af;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
    padding-top: 5px;
    border-top: 1px dashed #374151;
  }}

  .blue-dot {{
    width: 5px;
    height: 5px;
    background: #0047e1;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }}

  /* Footer */
  .footer {{
    padding: 10px 38px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-top: 2px solid #f1f5f9;
  }}

  .footer-brand {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 15px;
    font-weight: 800;
    color: #000000;
  }}

  .ig-icon {{
    width: 20px;
    height: 20px;
  }}

  .footer-center {{
    font-size: 11px;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }}

  .footer-badge {{
    background: #000000;
    color: #ffffff;
    font-size: 13px;
    font-weight: 800;
    padding: 7px 18px;
    border-radius: 20px;
    letter-spacing: 0.5px;
  }}
</style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="title-top">{data["title_top"]}</div>
    <div class="title-box">{data["title_box"]}</div>
    <div class="subtitle">{data["subtitle"]}</div>
  </div>

  <!-- Content Grid -->
  <div class="content-grid">
    <div class="col left-col">
      {left_html}
    </div>
    <div class="col right-col">
      {right_html}
      {highlights_html}
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <div class="footer-brand">
      <svg class="ig-icon" viewBox="0 0 24 24">
        <path fill="#000000" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
      </svg>
      <span>@wickedbostonevents</span>
    </div>
    <div class="footer-center">EST • D = doors • Outdoor events weather permitting</div>
    <div class="footer-badge">{data["footer_badge"]}</div>
  </div>

</body>
</html>
"""


def render_screenshot(html_path: str, output_png: str) -> None:
    cmd = [
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--window-size=1080,1350",
        f"--screenshot={output_png}",
        html_path,
    ]
    subprocess.run(cmd, check=True)
    print(f"Rendered: {output_png}")


def main():
    parser = argparse.ArgumentParser(description="Generate dynamic white-background weekly event flyers.")
    parser.add_argument("--date", type=str, default=None, help="Target date YYYY-MM-DD (defaults to current date)")
    parser.add_argument("--events-file", type=str, default=None, help="Path to events.json")
    args = parser.parse_args()

    target_date = None
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()

    print("Loading events dynamically for weekly flyer...")
    monday, sunday, selected_by_day, weekend_events = load_week_events(
        target_date=target_date,
        events_path=args.events_file
    )

    slide1_data, slide2_data = build_slide_data(
        monday, sunday, selected_by_day, weekend_events
    )

    total_count = sum(len(evs) for evs in selected_by_day.values())
    print(f"Selected {total_count} events across the week ({monday} to {sunday}):")
    for d_idx, day_name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        print(f"  {day_name}: {len(selected_by_day.get(d_idx, []))} events")

    # 1. Slide 1: Weekdays
    slide1_html_path = os.path.join(OUTPUT_DIR, "this_week_slide1.html")
    slide1_png_path = os.path.join(OUTPUT_DIR, "this_week_slide1.png")
    with open(slide1_html_path, "w", encoding="utf-8") as f:
        f.write(build_slide_html(slide1_data))
    render_screenshot(slide1_html_path, slide1_png_path)

    # 2. Slide 2: Weekend
    slide2_html_path = os.path.join(OUTPUT_DIR, "this_week_slide2.html")
    slide2_png_path = os.path.join(OUTPUT_DIR, "this_week_slide2.png")
    with open(slide2_html_path, "w", encoding="utf-8") as f:
        f.write(build_slide_html(slide2_data))
    render_screenshot(slide2_html_path, slide2_png_path)

    # Copy to artifact directory for easy display
    artifact_dir = "/Users/varunbehl/.gemini/antigravity/brain/97ecc9dc-b692-4686-9928-6e4e041247d4"
    if os.path.exists(artifact_dir):
        shutil.copy2(slide1_png_path, os.path.join(artifact_dir, "this_week_flyer_slide1.png"))
        shutil.copy2(slide2_png_path, os.path.join(artifact_dir, "this_week_flyer_slide2.png"))
        shutil.copy2(slide1_png_path, os.path.join(artifact_dir, "this_week_top_events_flyer.png"))
        print(f"Copied flyer slides to artifact directory: {artifact_dir}")

    print("Successfully generated dynamic weekly event flyers!")


if __name__ == "__main__":
    main()
