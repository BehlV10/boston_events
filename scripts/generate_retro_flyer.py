#!/usr/bin/env python3
"""
Generate retro psychedelic comic-style Instagram flyers
in the BostonFunEvents aesthetic for @wickedbostonevents.

Supports:
1. Weekly Flyer (--weekly): 7 days cleanly separated by date headers.
2. Daily Flyer (--daily): Today's top 20+ events sorted chronologically by time.
"""

import os
import sys
import json
import base64
import subprocess
from datetime import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "highlights.json")
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
MASCOT_IMG = os.path.join(OUTPUT_DIR, "boston_mascot.jpg")

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"

RETRO_COLORS = [
    {"bg": "#ff4d88", "text": "#1a000a", "pill_bg": "#b3003b", "pill_color": "#ffffff"},  # Hot Pink
    {"bg": "#48cae4", "text": "#002333", "pill_bg": "#0077b6", "pill_color": "#ffffff"},  # Electric Blue
    {"bg": "#ffd166", "text": "#261900", "pill_bg": "#d49700", "pill_color": "#ffffff"},  # Sunny Yellow
    {"bg": "#1d3557", "text": "#ffffff", "pill_bg": "#457b9d", "pill_color": "#ffffff"},  # Deep Navy
]


def get_mascot_base64():
    if os.path.exists(MASCOT_IMG):
        with open(MASCOT_IMG, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
    return ""


def clean_str(s, max_len=28):
    if not s:
        return ""
    if len(s) > max_len:
        return s[:max_len - 1].strip() + "…"
    return s


def load_events_by_date():
    """Load highlights grouped cleanly by date for the 7-day weekly flyer."""
    with open(HIGHLIGHTS_FILE, "r", encoding="utf-8") as f:
        hl = json.load(f)

    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    # Group highlights by start_date
    by_date = defaultdict(list)
    for h in hl:
        by_date[h["start_date"]].append(h)

    sorted_dates = sorted(by_date.keys())[:7]
    days_data = []

    for d_str in sorted_dates:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        picks = by_date[d_str]
        day_events = []

        for p in picks[:3]:  # Top 2-3 picks per day
            title = p.get("match", {}).get("name_contains", "Curated Event")
            venue = p.get("match", {}).get("venue_contains", "Boston")
            badge = p.get("badge", "")

            matched_time = ""
            for v in events_data.get("venues", []):
                for ev in v.get("events", []):
                    ev_date = (ev.get("date") or "")[:10]
                    if ev_date == d_str and title.lower() in ev.get("name", "").lower():
                        title = ev.get("name")
                        venue = ev.get("venue_name") or ev.get("venue") or venue
                        t_str = ev.get("date", "")
                        if "T" in t_str:
                            try:
                                time_dt = datetime.fromisoformat(t_str.replace("Z", "+00:00")).astimezone(EASTERN)
                                matched_time = time_dt.strftime("%-I:%M %p") if time_dt.minute != 0 else time_dt.strftime("%-I %p")
                            except Exception:
                                matched_time = ""
                        break
                if matched_time:
                    break

            day_events.append({
                "time": matched_time or "TBA",
                "title": clean_str(title, 26),
                "venue": clean_str(venue, 24),
                "badge": badge,
            })

        days_data.append({
            "date_str": d_str,
            "header": f"{dt.strftime('%a · %b %d').upper()}",
            "events": day_events,
        })

    return days_data


def load_daily_events(target_date="2026-10-29"):
    """Load today's top 20 events sorted by time for the daily flyer."""
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    candidates = []
    seen = set()

    for v in events_data.get("venues", []):
        for ev in v.get("events", []):
            date_raw = ev.get("date") or ""
            if date_raw[:10] == target_date:
                t_part = ""
                epoch = 9999999999
                if "T" in date_raw:
                    try:
                        time_dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00")).astimezone(EASTERN)
                        t_part = time_dt.strftime("%-I:%M %p") if time_dt.minute != 0 else time_dt.strftime("%-I %p")
                        epoch = int(time_dt.timestamp())
                    except Exception:
                        pass

                name = ev.get("name") or ""
                vname = ev.get("venue_name") or ev.get("venue") or ""
                key = (name.lower(), vname.lower())
                if key in seen or not name:
                    continue
                seen.add(key)

                candidates.append({
                    "name": clean_str(name, 26),
                    "venue": clean_str(vname, 24),
                    "time": t_part or "ALL DAY",
                    "epoch": epoch,
                    "price": ev.get("price") or "",
                })

    candidates.sort(key=lambda x: x["epoch"])
    return candidates[:26]


def build_poster_html(columns_html, headline, date_banner, subhead_banner):
    mascot_src = get_mascot_base64()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Titan+One&family=Plus+Jakarta+Sans:wght@700;800;900&family=JetBrains+Mono:wght@800&display=swap">
<style>
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    width: 1080px;
    height: 1350px;
    background: #fffdf5;
    font-family: 'Plus Jakarta Sans', sans-serif;
    color: #111;
    overflow: hidden;
    position: relative;
    padding: 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  /* Outer psychedelic checkerboard border */
  .checker-border {{
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    border: 14px solid transparent;
    border-image: repeating-linear-gradient(
      45deg,
      #ff3b81 0px, #ff3b81 18px,
      #ffd166 18px, #ffd166 36px,
      #06d6a0 36px, #06d6a0 54px,
      #118ab2 54px, #118ab2 72px,
      #073b4c 72px, #073b4c 90px
    ) 14;
    pointer-events: none;
    z-index: 100;
  }}

  /* Inner frame container */
  .poster-card {{
    width: 100%;
    height: 100%;
    background: #fdfaf0;
    border: 4px solid #000;
    border-radius: 12px;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    box-shadow: 0 10px 0 #000;
  }}

  /* Top Ribbon */
  .top-ribbon {{
    align-self: center;
    background: #ffd166;
    border: 3.5px solid #000;
    border-radius: 999px;
    padding: 6px 32px;
    font-size: 19px;
    font-weight: 900;
    letter-spacing: 0.06em;
    color: #000;
    text-transform: uppercase;
    box-shadow: 0 4px 0 #000;
    margin-bottom: 5px;
  }}

  /* Hero Title BOSTON */
  .title-wrap {{
    text-align: center;
    line-height: 0.85;
    margin-bottom: 6px;
  }}
  .retro-title {{
    font-family: 'Titan One', cursive;
    font-size: 108px;
    color: #ff3b81;
    letter-spacing: 0.03em;
    -webkit-text-stroke: 4px #000;
    text-shadow:
      6px 6px 0 #000,
      -3px -3px 0 #000,
      3px -3px 0 #000,
      -3px 3px 0 #000,
      0 6px 0 #000,
      6px 0 0 #000;
    display: inline-block;
  }}

  /* Black Banner Date */
  .date-banner-wrap {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    margin-bottom: 10px;
  }}
  .date-banner {{
    background: #000;
    color: #fff;
    padding: 6px 28px;
    border-radius: 999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 800;
    letter-spacing: 0.06em;
    box-shadow: 0 4px 0 rgba(0,0,0,0.3);
  }}
  .hood-banner {{
    background: #ffd166;
    border: 2px solid #000;
    color: #000;
    padding: 3px 18px;
    border-radius: 999px;
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 0.08em;
  }}

  /* Mascot Artwork Centerpiece */
  .mascot-frame {{
    width: 100%;
    height: 285px;
    border: 3.5px solid #000;
    border-radius: 14px;
    overflow: hidden;
    position: relative;
    box-shadow: 0 5px 0 #000;
    margin-bottom: 10px;
  }}
  .mascot-frame img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 38%;
  }}

  /* Schedule 2-Column Grid */
  .grid-wrap {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px 14px;
    flex: 1;
    margin-bottom: 10px;
  }}

  .grid-col {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}

  /* Section date headers for weekly view */
  .day-section-header {{
    display: flex;
    align-items: center;
    gap: 6px;
    background: #000;
    color: #ffd166;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    font-weight: 900;
    padding: 3px 10px;
    border-radius: 7px;
    margin-top: 2px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    box-shadow: 0 2.5px 0 rgba(0,0,0,0.4);
  }}

  .event-pill {{
    display: flex;
    align-items: center;
    border: 2.5px solid #000;
    border-radius: 9px;
    padding: 3.5px 7px;
    box-shadow: 0 2.5px 0 #000;
    height: 44px;
  }}

  .pill-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 900;
    padding: 3px 7px;
    border-radius: 6px;
    border: 1.5px solid #000;
    white-space: nowrap;
    margin-right: 7px;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }}

  .pill-details {{
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}

  .pill-title {{
    font-size: 13px;
    font-weight: 900;
    line-height: 1.15;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    letter-spacing: -0.01em;
  }}

  .pill-venue {{
    font-size: 10.5px;
    font-weight: 700;
    opacity: 0.88;
    line-height: 1.15;
    margin-top: 1px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Bottom Ribbon */
  .bottom-ribbon {{
    background: #ffd166;
    border: 3.5px solid #000;
    border-radius: 10px;
    padding: 7px 16px;
    text-align: center;
    font-size: 15px;
    font-weight: 900;
    color: #000;
    letter-spacing: 0.06em;
    box-shadow: 0 4px 0 #000;
    display: flex;
    justify-content: space-around;
    align-items: center;
  }}
  .bottom-ribbon span.star {{
    color: #ff3b81;
    font-size: 18px;
  }}
</style>
</head>
<body>
  <div class="checker-border"></div>

  <div class="poster-card">
    <div class="top-ribbon">⭐ {headline} ⭐</div>

    <div class="title-wrap">
      <div class="retro-title">BOSTON</div>
    </div>

    <div class="date-banner-wrap">
      <div class="date-banner">{date_banner}</div>
      <div class="hood-banner">{subhead_banner}</div>
    </div>

    <div class="mascot-frame">
      <img src="{mascot_src}" alt="Boston Mascot Illustration" />
    </div>

    <div class="grid-wrap">
      {columns_html}
    </div>

    <div class="bottom-ribbon">
      <span class="star">★</span>
      <span>ALL TIMES ET</span>
      <span class="star">★</span>
      <span>WICKEDBOSTONEVENTS.COM</span>
      <span class="star">★</span>
      <span>CHECK DETAILS &amp; TICKETS</span>
      <span class="star">★</span>
    </div>
  </div>
</body>
</html>"""
    return html


def generate_weekly_flyer():
    """Build weekly flyer with 7 days clearly separated by date headers."""
    days_data = load_events_by_date()
    if not days_data:
        print("No days data for weekly flyer")
        return

    # Left Column: Days 1, 2, 3 (Thu, Fri, Sat)
    # Right Column: Days 4, 5, 6, 7 (Sun, Mon, Tue, Wed)
    left_days = days_data[:3]
    right_days = days_data[3:]

    color_idx = 0

    def render_day_column(days_subset):
        nonlocal color_idx
        col_blocks = []
        for d in days_subset:
            col_blocks.append(f'<div class="day-section-header">📅 {d["header"]}</div>')
            for ev in d["events"]:
                c = RETRO_COLORS[color_idx % len(RETRO_COLORS)]
                color_idx += 1
                col_blocks.append(f"""
                <div class="event-pill" style="background:{c['bg']}; color:{c['text']};">
                  <div class="pill-time" style="background:{c['pill_bg']}; color:{c['pill_color']};">
                    {ev['time']}
                  </div>
                  <div class="pill-details">
                    <div class="pill-title">{ev['title']}</div>
                    <div class="pill-venue">{ev['venue']}</div>
                  </div>
                </div>
                """)
        return '<div class="grid-col">' + "\n".join(col_blocks) + '</div>'

    left_html = render_day_column(left_days)
    right_html = render_day_column(right_days)
    columns_html = f"{left_html}\n{right_html}"

    start_d = days_data[0]["header"].split(" · ")[1]
    end_d = days_data[-1]["header"].split(" · ")[1]
    date_banner = f"THIS WEEK · {start_d} – {end_d}, 2026"

    html = build_poster_html(
        columns_html=columns_html,
        headline="TOP WICKED FUN THINGS THIS WEEK",
        date_banner=date_banner,
        subhead_banner="BOSTON · CAMBRIDGE · SOMERVILLE · BROOKLINE"
    )

    out_png = os.path.join(OUTPUT_DIR, "weekly_flyer.png")
    temp_html = os.path.join(OUTPUT_DIR, "weekly_flyer.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html)

    subprocess.run([
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        "--window-size=1080,1350",
        "--virtual-time-budget=3000",
        f"--screenshot={out_png}",
        "--hide-scrollbars",
        temp_html
    ], check=True)
    print(f"Generated weekly flyer: {out_png}")


def generate_daily_flyer(target_date="2026-10-29"):
    """Build daily flyer with today's events sorted chronologically by time."""
    events = load_daily_events(target_date)
    dt = datetime.strptime(target_date, "%Y-%m-%d")

    mid = (len(events) + 1) // 2
    left_items = events[:mid]
    right_items = events[mid:]

    color_idx = 0

    def render_daily_column(col_items):
        nonlocal color_idx
        col_blocks = []
        for it in col_items:
            c = RETRO_COLORS[color_idx % len(RETRO_COLORS)]
            color_idx += 1
            col_blocks.append(f"""
            <div class="event-pill" style="background:{c['bg']}; color:{c['text']};">
              <div class="pill-time" style="background:{c['pill_bg']}; color:{c['pill_color']};">
                {it['time']}
              </div>
              <div class="pill-details">
                <div class="pill-title">{it['name']}</div>
                <div class="pill-venue">{it['venue']}</div>
              </div>
            </div>
            """)
        return '<div class="grid-col">' + "\n".join(col_blocks) + '</div>'

    left_html = render_daily_column(left_items)
    right_html = render_daily_column(right_items)
    columns_html = f"{left_html}\n{right_html}"

    date_banner = f"{dt.strftime('%A · %B %d, %Y').upper()}"

    html = build_poster_html(
        columns_html=columns_html,
        headline=f"{len(events)}+ FUN THINGS TO DO TODAY",
        date_banner=date_banner,
        subhead_banner="BOSTON · CAMBRIDGE · SOMERVILLE · BROOKLINE"
    )

    out_png = os.path.join(OUTPUT_DIR, "daily_flyer.png")
    temp_html = os.path.join(OUTPUT_DIR, "daily_flyer.html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html)

    subprocess.run([
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        "--window-size=1080,1350",
        "--virtual-time-budget=3000",
        f"--screenshot={out_png}",
        "--hide-scrollbars",
        temp_html
    ], check=True)
    print(f"Generated daily flyer: {out_png}")


def main():
    print("Generating both Weekly (separated by date) and Daily flyers...")
    generate_weekly_flyer()
    generate_daily_flyer("2026-10-29")
    print("Done!")


if __name__ == "__main__":
    main()
