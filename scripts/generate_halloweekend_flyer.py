#!/usr/bin/env python3
"""
Generate a curated Halloweekend Instagram flyer (Thu Oct 29 – Sun Nov 1, 2026)
for @wickedbostonevents with a charming, cute Halloween Boston aesthetic,
zero wasted whitespace, and bespoke curated event cards.
"""

import os
import sys
import json
import base64
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
ART_IMG = os.path.join(OUTPUT_DIR, "boston_halloween.jpg")
FLYER_PNG = os.path.join(OUTPUT_DIR, "halloweekend_flyer.png")
FLYER_HTML = os.path.join(OUTPUT_DIR, "halloweekend_flyer.html")

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"


def get_art_base64():
    if os.path.exists(ART_IMG):
        with open(ART_IMG, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
    return ""


# Hand-curated top picks for Halloweekend from highlights.json + events.json
WEEKEND_DATA = [
    {
        "day_id": "thu",
        "day_label": "THURSDAY · OCT 29",
        "icon": "🍁",
        "badge_color": "#ff7979",
        "events": [
            {
                "time": "7:30 PM",
                "tag": "🎃 COMEDY",
                "tag_bg": "#ff5252",
                "title": "Nightmare on Hanover Street",
                "venue": "Improv Asylum",
                "neighborhood": "North End",
                "note": "Flagship Halloween sketch & improv revue",
            },
            {
                "time": "7:30 PM",
                "tag": "🎻 SYMPHONY",
                "tag_bg": "#70a1ff",
                "title": "Day of the Dead Celebration",
                "venue": "Boston Symphony Hall",
                "neighborhood": "Fenway",
                "note": "Festive symphonic Día de los Muertos concert",
            },
            {
                "time": "7:30 PM",
                "tag": "🎸 INDIE",
                "tag_bg": "#2ed573",
                "title": "Blake Whiten",
                "venue": "The Sinclair",
                "neighborhood": "Harvard Square",
                "note": "Raw blues-rock & broken-glass vocals",
            },
        ],
    },
    {
        "day_id": "fri",
        "day_label": "FRIDAY · OCT 30",
        "icon": "🎪",
        "badge_color": "#ffa502",
        "events": [
            {
                "time": "7:30 PM",
                "tag": "🎪 CIRCUS",
                "tag_bg": "#ff6348",
                "title": "Cirque of the Dead",
                "venue": "Arts at the Armory",
                "neighborhood": "Somerville",
                "note": "Boston Circus Guild's dark Halloween spectacle",
            },
            {
                "time": "7:00 PM",
                "tag": "🎺 SKA / PUNK",
                "tag_bg": "#ffa502",
                "title": "Skalloween + Haunt",
                "venue": "The Rockwell",
                "neighborhood": "Davis Square",
                "note": "High-energy brass, masks & underground ska",
            },
            {
                "time": "7:00 PM",
                "tag": "🌴 LATIN GROOVE",
                "tag_bg": "#1e90ff",
                "title": "Rawayana: World Tour",
                "venue": "MGM Music Hall at Fenway",
                "neighborhood": "Fenway",
                "note": "Grammy-nominated Venezuelan psych-reggae",
            },
            {
                "time": "6:00 PM",
                "tag": "⚡ METAL",
                "tag_bg": "#a55eea",
                "title": "Nekrogoblikon: 20 Years",
                "venue": "Paradise Rock Club",
                "neighborhood": "Allston",
                "note": "Melodic goblin metal costumed mayhem",
            },
        ],
    },
    {
        "day_id": "sat",
        "day_label": "🎃 HALLOWEEN · SAT OCT 31",
        "icon": "👻",
        "badge_color": "#ff4757",
        "is_halloween": True,
        "events": [
            {
                "time": "7:00 PM",
                "tag": "🎬 35MM MARATHON",
                "tag_bg": "#ff4757",
                "title": "25th Halloween Horror Marathon",
                "venue": "Coolidge Corner Theatre",
                "neighborhood": "Brookline",
                "note": "Dusk-to-dawn 12-hour 35mm cult horror classic",
            },
            {
                "time": "7:00 PM",
                "tag": "🎸 UNDERGROUND",
                "tag_bg": "#ff7f50",
                "title": "Punkoween 2: Tributes",
                "venue": "Middle East Upstairs",
                "neighborhood": "Central Sq",
                "note": "Dead Kennedys, Black Flag & Bad Brains covers",
            },
            {
                "time": "1:30 PM",
                "tag": "🎻 FILM & LIVE SCORE",
                "tag_bg": "#2ed573",
                "title": "Coco in Concert Live to Film",
                "venue": "Boston Symphony Hall",
                "neighborhood": "Fenway",
                "note": "Pixar classic with full orchestra live score",
            },
            {
                "time": "7:00 PM",
                "tag": "🎤 PSYCH KARAOKE",
                "tag_bg": "#e056fd",
                "title": "SCARY-OKE w/ Jesse Gallagher",
                "venue": "The Lilypad",
                "neighborhood": "Inman Square",
                "note": "Eccentric costume party & live synth karaoke",
            },
        ],
    },
    {
        "day_id": "sun",
        "day_label": "SUNDAY · NOV 01",
        "icon": "🍂",
        "badge_color": "#2ed573",
        "events": [
            {
                "time": "1:30 PM",
                "tag": "🏛️ PALACE CHAMBER",
                "tag_bg": "#ffa502",
                "title": "Eleanor Alberga Quartets",
                "venue": "Isabella Stewart Gardner Museum",
                "neighborhood": "Fenway",
                "note": "Sunlit Calderwood Hall chamber performance",
            },
            {
                "time": "3:00 PM",
                "tag": "🎬 SILENT FILM LIVE",
                "tag_bg": "#70a1ff",
                "title": "The Eleventh Year (1928)",
                "venue": "Somerville Theatre",
                "neighborhood": "Davis Square",
                "note": "World premiere live score by Psych Cinema Orch",
            },
            {
                "time": "7:30 PM",
                "tag": "🎸 INDIE ROCK",
                "tag_bg": "#2ed573",
                "title": "The Gringos Headline",
                "venue": "The Sinclair",
                "neighborhood": "Harvard Square",
                "note": "High-energy Cambridge indie rock quartet",
            },
        ],
    },
]


def render_day_block(day):
    is_hw = day.get("is_halloween", False)
    header_class = "day-header halloween-header" if is_hw else "day-header"
    
    events_html = []
    for ev in day["events"]:
        events_html.append(f"""
        <div class="event-card {'hw-card' if is_hw else ''}">
          <div class="event-top-line">
            <span class="event-time">{ev['time']}</span>
            <span class="event-tag" style="background:{ev['tag_bg']};">{ev['tag']}</span>
            <span class="event-hood">📍 {ev['neighborhood']}</span>
          </div>
          <div class="event-title">{ev['title']}</div>
          <div class="event-bottom-line">
            <span class="event-venue">🏛️ {ev['venue']}</span>
            <span class="event-bullet">•</span>
            <span class="event-note">{ev['note']}</span>
          </div>
        </div>
        """)

    return f"""
    <div class="day-section {'hw-section' if is_hw else ''}">
      <div class="{header_class}">
        <span class="day-icon">{day['icon']}</span>
        <span class="day-title-text">{day['day_label']}</span>
      </div>
      <div class="day-events-list">
        {"".join(events_html)}
      </div>
    </div>
    """


def generate_flyer_html():
    art_b64 = get_art_base64()
    
    # Left column: Thu + Sat (Halloween)
    # Right column: Fri + Sun
    col_left_html = render_day_block(WEEKEND_DATA[0]) + "\n" + render_day_block(WEEKEND_DATA[2])
    col_right_html = render_day_block(WEEKEND_DATA[1]) + "\n" + render_day_block(WEEKEND_DATA[3])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Halloweekend in Boston</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=JetBrains+Mono:wght@600;700&display=swap" rel="stylesheet">
<style>
  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    -webkit-font-smoothing: antialiased;
  }}

  body {{
    width: 1080px;
    height: 1350px;
    background: #0d0a17;
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #f7f4ee;
    display: flex;
    justify-content: center;
    align-items: center;
    overflow: hidden;
  }}

  /* Outer Poster Container */
  .poster {{
    width: 1080px;
    height: 1350px;
    background: radial-gradient(circle at 50% 0%, #201335 0%, #110c1f 50%, #0a0713 100%);
    padding: 24px 26px 20px 26px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    box-sizing: border-box;
    border: 3px solid #ff9f43;
    outline: 6px solid #1a0f2e;
  }}

  /* Header Section */
  .header-wrap {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 12px;
    border-bottom: 1.5px solid rgba(255, 159, 67, 0.35);
  }}

  .header-left {{
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}

  .eyebrow-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: linear-gradient(90deg, #ff5252, #ff793f);
    color: #fff;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    padding: 4px 14px;
    border-radius: 999px;
    width: fit-content;
    box-shadow: 0 2px 10px rgba(255, 82, 82, 0.35);
  }}

  .main-title {{
    font-family: 'Playfair Display', serif;
    font-size: 42px;
    font-weight: 900;
    line-height: 1.05;
    color: #fffaf0;
    letter-spacing: -0.5px;
    margin-top: 4px;
    text-shadow: 0 2px 12px rgba(0,0,0,0.6);
  }}

  .main-title span {{
    color: #ff9f43;
    font-style: italic;
  }}

  .header-right {{
    text-align: right;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }}

  .date-badge {{
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 159, 67, 0.4);
    padding: 6px 14px;
    border-radius: 12px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    font-weight: 700;
    color: #ffbe76;
    letter-spacing: 0.5px;
  }}

  .sub-tag {{
    font-size: 12px;
    color: #a4b0be;
    font-weight: 600;
    letter-spacing: 0.8px;
  }}

  /* Artwork Banner Frame */
  .art-banner {{
    width: 100%;
    height: 320px;
    margin-top: 12px;
    border-radius: 16px;
    overflow: hidden;
    position: relative;
    border: 2px solid #ff9f43;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6), inset 0 0 20px rgba(255, 159, 67, 0.2);
  }}

  .art-banner img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 46%;
    display: block;
  }}

  .art-overlay-tag {{
    position: absolute;
    bottom: 10px;
    right: 12px;
    background: rgba(13, 10, 23, 0.88);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255, 159, 67, 0.4);
    color: #ffd8a8;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 10px;
    border-radius: 8px;
    text-transform: uppercase;
  }}

  /* Grid Area (4 Days) */
  .grid-container {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-top: 14px;
    flex: 1;
  }}

  .grid-column {{
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}

  .day-section {{
    background: rgba(22, 16, 38, 0.85);
    border: 1.5px solid rgba(255, 255, 255, 0.1);
    border-radius: 14px;
    padding: 11px 13px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3);
  }}

  .day-section.hw-section {{
    background: linear-gradient(180deg, rgba(46, 17, 34, 0.9) 0%, rgba(22, 16, 38, 0.9) 100%);
    border: 1.5px solid #ff4757;
    box-shadow: 0 4px 20px rgba(255, 71, 87, 0.25);
  }}

  .day-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }}

  .day-header.halloween-header {{
    border-bottom: 1px solid rgba(255, 71, 87, 0.4);
  }}

  .day-icon {{
    font-size: 16px;
  }}

  .day-title-text {{
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 900;
    font-size: 14px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #ff9f43;
  }}

  .halloween-header .day-title-text {{
    color: #ff6b81;
    text-shadow: 0 0 10px rgba(255, 71, 87, 0.4);
  }}

  .day-events-list {{
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}

  /* Event Card */
  .event-card {{
    background: rgba(255, 255, 255, 0.04);
    border-radius: 8px;
    padding: 8px 10px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    display: flex;
    flex-direction: column;
    gap: 3px;
    transition: all 0.2s ease;
  }}

  .event-card.hw-card {{
    background: rgba(255, 71, 87, 0.06);
    border: 1px solid rgba(255, 71, 87, 0.2);
  }}

  .event-top-line {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .event-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    background: #0d0a17;
    color: #ffd8a8;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid rgba(255, 159, 67, 0.3);
  }}

  .event-tag {{
    font-size: 10px;
    font-weight: 800;
    color: #ffffff;
    padding: 2px 6px;
    border-radius: 4px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}

  .event-hood {{
    margin-left: auto;
    font-size: 11px;
    font-weight: 700;
    color: #a4b0be;
  }}

  .event-title {{
    font-size: 14px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.25;
    letter-spacing: -0.2px;
  }}

  .event-bottom-line {{
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    color: #ced6e0;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .event-venue {{
    color: #ffbe76;
    font-weight: 700;
  }}

  .event-bullet {{
    color: rgba(255, 255, 255, 0.3);
  }}

  .event-note {{
    color: #a4b0be;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Footer Ribbon */
  .footer-ribbon {{
    margin-top: 12px;
    background: linear-gradient(90deg, #ff4757, #ff9f43);
    border-radius: 12px;
    padding: 10px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 16px rgba(255, 71, 87, 0.3);
  }}

  .footer-left {{
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 1.2px;
    color: #0d0a17;
    text-transform: uppercase;
  }}

  .footer-center {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 800;
    color: #0d0a17;
    letter-spacing: 0.5px;
  }}

  .footer-right {{
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 1px;
    color: #0d0a17;
    text-transform: uppercase;
  }}
</style>
</head>
<body>
  <div class="poster">
    
    <!-- Top Header -->
    <div class="header-wrap">
      <div class="header-left">
        <div class="eyebrow-pill">🎃 WICKED BOSTON GUIDE · HALLOWEEKEND 🍁</div>
        <div class="main-title">Halloweekend in <span>Boston</span></div>
      </div>
      <div class="header-right">
        <div class="date-badge">OCT 29 – NOV 01</div>
        <div class="sub-tag">THU · FRI · SAT · SUN</div>
      </div>
    </div>

    <!-- Illustrated Art Banner -->
    <div class="art-banner">
      <img src="{art_b64}" alt="Halloween in Boston" />
      <div class="art-overlay-tag">📍 BEACON HILL · HARVARD SQ · SOMERVILLE · FENWAY</div>
    </div>

    <!-- 4-Day Curated Event Grid -->
    <div class="grid-container">
      <div class="grid-column">
        {col_left_html}
      </div>
      <div class="grid-column">
        {col_right_html}
      </div>
    </div>

    <!-- Bottom Footer Ribbon -->
    <div class="footer-ribbon">
      <div class="footer-left">⭐ TOP CURATED PICKS</div>
      <div class="footer-center">WICKEDBOSTONEVENTS.COM</div>
      <div class="footer-right">LINK IN BIO FOR TICKETS 🎟️</div>
    </div>

  </div>
</body>
</html>"""
    return html


def main():
    print("Generating Halloweekend flyer...")
    html = generate_flyer_html()
    with open(FLYER_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    
    subprocess.run([
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        "--window-size=1080,1350",
        "--virtual-time-budget=3000",
        f"--screenshot={FLYER_PNG}",
        "--hide-scrollbars",
        FLYER_HTML
    ], check=True)
    print(f"Generated Halloweekend flyer: {FLYER_PNG}")


if __name__ == "__main__":
    main()
