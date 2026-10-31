#!/usr/bin/env python3
"""
Generate Instagram Story (1080x1920) and Feed (1080x1350) graphics
for @wickedbostonevents using curated 7-day highlights.
"""

import os
import json
import subprocess
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "highlights.json")
EVENTS_FILE = os.path.join(BASE_DIR, "events.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    # Try linux/github actions binary
    CHROME_BIN = "google-chrome"


def load_week_highlights():
    with open(HIGHLIGHTS_FILE, "r", encoding="utf-8") as f:
        hl = json.load(f)

    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    by_date = defaultdict(list)
    for h in hl:
        by_date[h["start_date"]].append(h)

    # Sort dates and pick the top event for each day (up to 7 days)
    sorted_dates = sorted(by_date.keys())[:7]
    days_data = []

    for d_str in sorted_dates:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        day_picks = by_date[d_str]
        top = day_picks[0]

        # Find venue & title
        title = top.get("match", {}).get("name_contains", "Curated Event")
        venue = top.get("match", {}).get("venue_contains", "Boston Venue")

        # Match from events.json if possible for exact name
        matched_event = None
        for v in events_data.get("venues", []):
            for ev in v.get("events", []):
                ev_date = (ev.get("date") or "")[:10]
                if ev_date == d_str:
                    if top.get("match", {}).get("name_contains", "").lower() in ev.get("name", "").lower():
                        matched_event = ev
                        break
            if matched_event:
                break

        if matched_event:
            title = matched_event.get("name", title)
            venue = matched_event.get("venue_name") or matched_event.get("venue") or venue

        days_data.append({
            "date_str": d_str,
            "day_name": dt.strftime("%a").upper(),
            "month_day": dt.strftime("%b %d").upper(),
            "badge": top.get("badge", "Editor's Pick"),
            "title": title,
            "venue": venue,
            "note": top.get("note", ""),
        })

    return days_data


def generate_html_template(days, mode="story"):
    """
    mode = 'story' (1080x1920) or 'feed' (1080x1350)
    """
    is_story = (mode == "story")
    height = 1920 if is_story else 1350
    width = 1080

    start_label = days[0]["month_day"] if days else "THIS WEEK"
    end_label = days[-1]["month_day"] if days else "NEXT WEEK"

    cards_html = []
    for d in days:
        cards_html.append(f"""
        <div class="event-row">
          <div class="day-badge">
            <span class="day-dow">{d['day_name']}</span>
            <span class="day-num">{d['month_day']}</span>
          </div>
          <div class="event-info">
            <div class="badge-pill">✨ {d['badge']}</div>
            <div class="event-title">{d['title']}</div>
            <div class="event-venue">📍 {d['venue']}</div>
            <div class="event-note">{d['note']}</div>
          </div>
        </div>
        """)

    cards_block = "\n".join(cards_html)

    footer_content = """
      <div class="story-sticker-zone">
        <div class="sticker-hint">👆 TAP LINK STICKER TO VIEW FULL WEEKLY SCHEDULE</div>
        <div class="site-url">wickedbostonevents.com</div>
        <div class="sub-features">70+ Curated Highlights · Filter by Genre, Subway & Free Entry</div>
      </div>
    """ if is_story else """
      <div class="feed-footer">
        <div class="site-url">wickedbostonevents.com</div>
        <div class="feed-sub">Link in bio for full 70+ event lineup, tickets, and interactive maps</div>
      </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@700&display=swap');

  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    width: {width}px;
    height: {height}px;
    background: #090c10;
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #f0f6fc;
    overflow: hidden;
    position: relative;
    padding: 44px 48px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  /* Ambient glowing background gradients */
  .bg-glow-1 {{
    position: absolute;
    top: -120px;
    right: -100px;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(255, 184, 0, 0.16) 0%, rgba(255, 120, 0, 0.05) 50%, transparent 70%);
    filter: blur(60px);
    pointer-events: none;
  }}
  .bg-glow-2 {{
    position: absolute;
    bottom: -150px;
    left: -100px;
    width: 700px;
    height: 700px;
    background: radial-gradient(circle, rgba(93, 155, 255, 0.14) 0%, rgba(187, 154, 247, 0.06) 50%, transparent 70%);
    filter: blur(80px);
    pointer-events: none;
  }}

  /* Header Section */
  .header {{
    position: relative;
    z-index: 10;
    border-bottom: 1.5px solid rgba(255, 255, 255, 0.08);
    padding-bottom: 24px;
  }}
  .brand-chip {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: rgba(255, 184, 0, 0.14);
    border: 1px solid rgba(255, 184, 0, 0.4);
    color: #ffda66;
    padding: 6px 16px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 14px;
  }}
  .main-title {{
    font-size: {'52px' if is_story else '46px'};
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.08;
    background: linear-gradient(135deg, #ffffff 30%, #ffd866 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .subtitle {{
    font-size: 19px;
    color: #8b949e;
    margin-top: 8px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .subtitle .date-span {{
    color: #ffda66;
    font-weight: 700;
  }}

  /* Events Container */
  .events-list {{
    position: relative;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: {'14px' if is_story else '10px'};
    margin: 18px 0;
  }}

  .event-row {{
    display: flex;
    align-items: center;
    gap: 20px;
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 16px;
    padding: {'14px 20px' if is_story else '10px 18px'};
    backdrop-filter: blur(10px);
  }}

  .day-badge {{
    min-width: 90px;
    padding: 10px 8px;
    background: linear-gradient(180deg, rgba(255, 184, 0, 0.16) 0%, rgba(255, 140, 0, 0.08) 100%);
    border: 1px solid rgba(255, 184, 0, 0.35);
    border-radius: 12px;
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }}
  .day-dow {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 700;
    color: #ffd866;
    letter-spacing: 0.05em;
  }}
  .day-num {{
    font-size: 12px;
    font-weight: 700;
    color: #c9d1d9;
    margin-top: 2px;
    white-space: nowrap;
  }}

  .event-info {{
    flex: 1;
    min-width: 0;
  }}

  .badge-pill {{
    display: inline-block;
    padding: 2px 9px;
    background: rgba(255, 184, 0, 0.15);
    border: 1px solid rgba(255, 184, 0, 0.35);
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 700;
    color: #ffd866;
    margin-bottom: 4px;
  }}

  .event-title {{
    font-size: {'19px' if is_story else '17px'};
    font-weight: 700;
    color: #ffffff;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .event-venue {{
    font-size: {'14.5px' if is_story else '13.5px'};
    font-weight: 600;
    color: #5d9bff;
    margin-top: 3px;
  }}

  .event-note {{
    font-size: {'13.5px' if is_story else '12.5px'};
    color: #8b949e;
    margin-top: 4px;
    line-height: 1.35;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-style: italic;
  }}

  /* Footer */
  .footer {{
    position: relative;
    z-index: 10;
  }}

  .story-sticker-zone {{
    background: linear-gradient(135deg, rgba(255, 184, 0, 0.12), rgba(93, 155, 255, 0.08));
    border: 1.5px dashed rgba(255, 184, 0, 0.5);
    border-radius: 20px;
    padding: 24px;
    text-align: center;
  }}
  .sticker-hint {{
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #ffd866;
    margin-bottom: 8px;
  }}
  .site-url {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 26px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.01em;
  }}
  .sub-features {{
    font-size: 14px;
    color: #8b949e;
    margin-top: 8px;
    font-weight: 500;
  }}

  .feed-footer {{
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 16px;
    text-align: center;
  }}
  .feed-sub {{
    font-size: 14px;
    color: #8b949e;
    margin-top: 4px;
  }}
</style>
</head>
<body>
  <div class="bg-glow-1"></div>
  <div class="bg-glow-2"></div>

  <div class="header">
    <div class="brand-chip">✨ WICKED BOSTON EVENTS · WEEKLY CURATION</div>
    <div class="main-title">TOP EVENTS THIS WEEK</div>
    <div class="subtitle">
      <span class="date-span">🗓️ {start_label} – {end_label}</span>
      <span>· Live Music, Art, Comedy & Nightlife</span>
    </div>
  </div>

  <div class="events-list">
    {cards_block}
  </div>

  <div class="footer">
    {footer_content}
  </div>
</body>
</html>"""
    return html


def render_screenshot(html_content, out_png, width, height):
    temp_html = out_png.replace(".png", ".html")
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    cmd = [
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        f"--window-size={width},{height}",
        f"--screenshot={out_png}",
        "--hide-scrollbars",
        temp_html
    ]
    subprocess.run(cmd, check=True)
    if os.path.exists(temp_html):
        os.remove(temp_html)
    print(f"Generated: {out_png} ({width}x{height})")


def generate_caption(days):
    start = days[0]['month_day']
    end = days[-1]['month_day']
    lines = [
        f"✨ WHAT'S HAPPENING IN BOSTON ({start} – {end}) ✨",
        "",
        "Here are our curated top picks for each day of the upcoming week across Greater Boston, Cambridge & Somerville:",
        ""
    ]
    for d in days:
        lines.append(f"• {d['day_name']} ({d['month_day']}): {d['title']}")
        lines.append(f"  📍 {d['venue']} | {d['badge']}")
        lines.append(f"  💬 \"{d['note']}\"")
        lines.append("")

    lines.extend([
        "👉 Tap the link sticker or visit wickedbostonevents.com for 70+ curated picks, full times, ticket links, genre pills, and interactive transit maps!",
        "",
        "#BostonEvents #WickedBoston #CambridgeMA #SomervilleMA #BostonMusic #ThingsToDoInBoston #BostonNightlife #HarvardSquare #BostonComedy #LiveMusicBoston"
    ])
    return "\n".join(lines)


def main():
    days = load_week_highlights()
    if not days:
        print("No highlights found!")
        return

    # 1. Instagram Story (1080x1920)
    story_html = generate_html_template(days, mode="story")
    story_png = os.path.join(OUTPUT_DIR, "weekly_story.png")
    render_screenshot(story_html, story_png, 1080, 1920)

    # 2. Instagram Feed (1080x1350)
    feed_html = generate_html_template(days, mode="feed")
    feed_png = os.path.join(OUTPUT_DIR, "weekly_feed.png")
    render_screenshot(feed_html, feed_png, 1080, 1350)

    # 3. Instagram Caption
    caption = generate_caption(days)
    caption_file = os.path.join(OUTPUT_DIR, "caption.txt")
    with open(caption_file, "w", encoding="utf-8") as f:
        f.write(caption)
    print(f"Generated caption: {caption_file}")

    print("\n" + "="*50)
    print(caption)
    print("="*50)


if __name__ == "__main__":
    main()
