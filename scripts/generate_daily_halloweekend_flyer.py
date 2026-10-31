#!/usr/bin/env python3
"""
Generate a 20-event Daily Instagram flyer split by city (Boston, Cambridge, Somerville)
for @wickedbostonevents.

Features:
- Exactly 20 curated events: 10 in Boston, 5 in Cambridge, 5 in Somerville.
- Chronological order within each city.
- Balanced 2-column layout:
  - Left Column: BOSTON (10 events)
  - Right Column: CAMBRIDGE (5 events) + SOMERVILLE (5 events)
- Light, colorful, warm-ivory aesthetic.
- High-contrast, easily readable typography on mobile screens.
- Start Time, Price / FREE badge, and Venue · Neighborhood on top row.
- Big bold title (18.5px) on bottom row.
"""

import os
import sys
import json
import base64
import shutil
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from themes import get_active_theme

OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
ART_IMG = os.path.join(OUTPUT_DIR, "dia_de_muertos_halloween.jpg")
FLYER_PNG = os.path.join(OUTPUT_DIR, "today_flyer.png")
CITY_PNG = os.path.join(OUTPUT_DIR, "today_flyer_by_city.png")
FLYER_HTML = os.path.join(OUTPUT_DIR, "today_flyer.html")
CAPTION_FILE = os.path.join(OUTPUT_DIR, "today_caption.txt")
LINKS_FILE = os.path.join(OUTPUT_DIR, "today_events_with_urls.txt")

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"


def get_art_base64():
    if os.path.exists(ART_IMG):
        with open(ART_IMG, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
    return ""


# 20 Curated Events for Saturday, October 31, 2026 split by City & sorted chronologically
BOSTON_EVENTS = [
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "VROCC Día de Muertos Celebration",
        "venue": "East Boston",
        "hood": "East Boston",
        "accent": "#ff793f",
        "url": "https://vrocc.org/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Watershed Community Mariachi",
        "venue": "ICA Watershed",
        "hood": "East Boston",
        "accent": "#10ac84",
        "url": "https://www.icaboston.org/events/watershed-community-event-veronica-robles-cultural-center",
    },
    {
        "time": "2:00 PM",
        "price": "$35+",
        "title": "Disney's Coco in Concert",
        "venue": "Symphony Hall",
        "hood": "Fenway",
        "accent": "#e67e22",
        "url": "https://www.bso.org/",
    },
    {
        "time": "7:00 PM",
        "price": "FREE",
        "title": "Sam Adams Halloween Party",
        "venue": "Sam Adams Taproom",
        "hood": "Downtown",
        "accent": "#ff6b6b",
        "url": "https://www.samadamsbostontaproom.com/events",
    },
    {
        "time": "7:00 PM",
        "price": "$20",
        "title": "Death Becomes She/Her: Drag Musical",
        "venue": "Club Café",
        "hood": "South End",
        "accent": "#e056fd",
        "url": "https://www.clubcafe.com/",
    },
    {
        "time": "7:30 PM",
        "price": "$25",
        "title": "Nightmare on Hanover Street",
        "venue": "Improv Asylum",
        "hood": "North End",
        "accent": "#ff4757",
        "url": "https://improvasylum.com/",
    },
    {
        "time": "8:00 PM",
        "price": "$25",
        "title": "ICA Halloween: It's Magic!",
        "venue": "ICA Boston",
        "hood": "Seaport",
        "accent": "#6c5ce7",
        "url": "https://www.icaboston.org/events/ica-halloween-its-magic",
    },
    {
        "time": "9:00 PM",
        "price": "$35",
        "title": "Trixie & Katya's Dance Party",
        "venue": "Royale",
        "hood": "Theatre Dist",
        "accent": "#fd79a8",
        "url": "https://royaleboston.com/",
    },
    {
        "time": "9:00 PM",
        "price": "$20",
        "title": "Entre Mundos: Día de los Muertos",
        "venue": "Luma Seaport",
        "hood": "Seaport",
        "accent": "#f39c12",
        "url": "https://thebostoncalendar.com",
    },
    {
        "time": "10:00 PM",
        "price": "FREE",
        "title": "Halloween @ Collective 64",
        "venue": "Partiful Boston",
        "hood": "Downtown",
        "accent": "#2d3436",
        "url": "https://partiful.com/",
    },
]

CAMBRIDGE_EVENTS = [
    {
        "time": "12:00 PM",
        "price": "FREE",
        "title": "Tarot DJ Brunch w/ Rattbott",
        "venue": "Lou's",
        "hood": "Harvard Sq",
        "accent": "#9b59b6",
        "url": "https://thebostoncalendar.com",
    },
    {
        "time": "7:00 PM",
        "price": "$23",
        "title": "Punkoween 2: Misfits & Slapshot",
        "venue": "Middle East Downstairs",
        "hood": "Central Sq",
        "accent": "#d63031",
        "url": "https://www.mideastoffers.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$35",
        "title": "Benny Green Jazz Trio",
        "venue": "Scullers Jazz Club",
        "hood": "Cambridge",
        "accent": "#e67e22",
        "url": "https://scullersjazz.com/",
    },
    {
        "time": "9:00 PM",
        "price": "$20",
        "title": "Halloween with Dub Apocalypse!",
        "venue": "Lizard Lounge",
        "hood": "Cambridge",
        "accent": "#00b894",
        "url": "https://lizardloungecambridge.com/",
    },
    {
        "time": "9:00 PM",
        "price": "$20",
        "title": "DIVALAND OF THE DEAD!!!",
        "venue": "The Sinclair",
        "hood": "Harvard Sq",
        "accent": "#e84393",
        "url": "https://www.sinclaircambridge.com/",
    },
]

SOMERVILLE_EVENTS = [
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Halloween Bulb Blitz",
        "venue": "Somerville Growing Ctr",
        "hood": "Somerville",
        "accent": "#27ae60",
        "url": "https://thebostoncalendar.com",
    },
    {
        "time": "7:00 PM",
        "price": "FREE",
        "title": "Halloween Bonanza & Brass Band",
        "venue": "Aeronaut Brewing",
        "hood": "Somerville",
        "accent": "#f39c12",
        "url": "https://www.aeronautbrewing.com/events/",
    },
    {
        "time": "7:00 PM",
        "price": "$20",
        "title": "Fright Night in Davis Square",
        "venue": "The Rockwell",
        "hood": "Davis Sq",
        "accent": "#6c5ce7",
        "url": "https://therockwell.org/",
    },
    {
        "time": "8:00 PM",
        "price": "$15",
        "title": "Rocky Horror 35mm w/ Prop Bags",
        "venue": "Somerville Theatre",
        "hood": "Davis Sq",
        "accent": "#d63031",
        "url": "https://www.somervilletheatre.com/",
    },
    {
        "time": "8:00 PM",
        "price": "$35",
        "title": "Cirque of the Dead",
        "venue": "Arts at the Armory",
        "hood": "Somerville",
        "accent": "#8e44ad",
        "url": "https://artsatthearmory.org/",
    },
]


def render_event_card(ev):
    is_free = ev["price"] == "FREE"
    price_cls = "price-free" if is_free else "price-paid"
    
    return f"""
    <div class="event-card" style="border-left: 4.5px solid {ev['accent']};">
      <div class="card-top-row">
        <div class="badge-group">
          <span class="event-time">{ev['time']}</span>
          <span class="event-price {price_cls}">{ev['price']}</span>
        </div>
        <div class="event-location">📍 {ev['venue']} · <strong>{ev['hood']}</strong></div>
      </div>
      <div class="event-title">{ev['title']}</div>
    </div>
    """


def render_city_section(city_name, icon, bg_color, events):
    cards_html = "".join([render_event_card(ev) for ev in events])
    return f"""
    <div class="city-section">
      <div class="city-header" style="background: {bg_color};">
        <span class="city-header-title">{icon} {city_name}</span>
        <span class="city-header-count">{len(events)} EVENTS</span>
      </div>
      <div class="city-cards-list">
        {cards_html}
      </div>
    </div>
    """


def generate_today_html():
    art_b64 = get_art_base64()
    
    boston_col_html = render_city_section("BOSTON", "🏙️", "linear-gradient(90deg, #ff4757, #ff793f)", BOSTON_EVENTS)
    cambridge_html = render_city_section("CAMBRIDGE", "🎓", "linear-gradient(90deg, #6c5ce7, #0984e3)", CAMBRIDGE_EVENTS)
    somerville_html = render_city_section("SOMERVILLE", "🎨", "linear-gradient(90deg, #fd79a8, #e17055)", SOMERVILLE_EVENTS)
    
    right_col_html = f"""
    <div class="right-stacked-col">
      {cambridge_html}
      {somerville_html}
    </div>
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Tonight in Boston · 20 Top Events by City</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@600;700;800;900&family=Playfair+Display:ital,wght@0,700;0,900;1,700;1,900&family=JetBrains+Mono:wght@700;800&display=swap" rel="stylesheet">
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
    background: #0d0617;
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #ffffff;
    display: flex;
    justify-content: center;
    align-items: center;
    overflow: hidden;
  }}

  /* Outer Poster Container */
  .poster {{
    width: 1080px;
    height: 1350px;
    background: linear-gradient(180deg, #120722 0%, #1b0d30 50%, #0d0519 100%);
    padding: 26px 24px 18px 24px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    position: relative;
    box-sizing: border-box;
    box-shadow: inset 0 0 0 5px #ff793f, inset 0 0 0 9px #2d144b, 0 0 30px rgba(255, 121, 63, 0.25);
  }}

  /* Top Header */
  .header-wrap {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 2px;
    padding-bottom: 8px;
    border-bottom: 2px solid rgba(255, 121, 63, 0.45);
  }}

  .header-left {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}

  .eyebrow-pill {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: linear-gradient(90deg, #ff4757, #ff793f, #e056fd);
    color: #ffffff;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 3.5px 13px;
    border-radius: 999px;
    width: fit-content;
    box-shadow: 0 2px 10px rgba(255, 121, 63, 0.4);
  }}

  .main-title {{
    font-family: 'Playfair Display', serif;
    font-size: 40px;
    font-weight: 900;
    line-height: 1.05;
    color: #ffffff;
    letter-spacing: -0.5px;
    margin-top: 2px;
    text-shadow: 0 2px 12px rgba(0,0,0,0.6);
  }}

  .main-title span {{
    color: #ff9f43;
    font-style: italic;
    text-shadow: 0 0 16px rgba(255, 159, 67, 0.45);
  }}

  .header-right {{
    text-align: right;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 3px;
  }}

  .date-badge {{
    background: #25123d;
    border: 1.5px solid #ff793f;
    padding: 5px 14px;
    border-radius: 10px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14.5px;
    font-weight: 800;
    color: #ffeaa7;
    letter-spacing: 0.6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }}

  .sub-tag {{
    font-size: 11.5px;
    color: #c8b9de;
    font-weight: 800;
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }}

  /* Illustrated Art Banner — highlighting ghost mascot, skeletons & pumpkins at bottom */
  .art-banner {{
    width: 100%;
    height: 195px;
    margin-top: 8px;
    border-radius: 12px;
    overflow: hidden;
    position: relative;
    border: 2px solid #ff793f;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45), 0 0 14px rgba(255, 121, 63, 0.2);
  }}

  .art-banner img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 88%;
    display: block;
  }}

  .art-overlay-tag {{
    position: absolute;
    bottom: 6px;
    right: 10px;
    background: rgba(18, 7, 34, 0.94);
    backdrop-filter: blur(8px);
    border: 1.5px solid #ff793f;
    color: #ffeaa7;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.8px;
    padding: 3.5px 11px;
    border-radius: 6px;
    text-transform: uppercase;
    box-shadow: 0 2px 8px rgba(0,0,0,0.5);
  }}

  /* 2-Column Grid Area */
  .grid-container {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-top: 8px;
    flex: 1;
  }}

  .left-col {{
    display: flex;
    flex-direction: column;
    height: 100%;
  }}

  /* City Section Box */
  .city-section {{
    display: flex;
    flex-direction: column;
    gap: 4.5px;
    height: 100%;
  }}

  .city-header {{
    padding: 5px 12px;
    border-radius: 7px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }}

  .city-header-title {{
    font-size: 13.5px;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: 1px;
    text-transform: uppercase;
    text-shadow: 0 1px 4px rgba(0,0,0,0.4);
  }}

  .city-header-count {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 800;
    color: #ffffff;
    background: rgba(0, 0, 0, 0.35);
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.5px;
  }}

  .city-cards-list {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    justify-content: space-between;
  }}

  .right-stacked-col {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    height: 100%;
    justify-content: space-between;
  }}

  /* Event Card: tighter gap, larger text, rich dark purple */
  .event-card {{
    background: #1e1233;
    border-radius: 8px;
    padding: 8px 12px 7.5px 12px;
    border: 1px solid rgba(255, 121, 63, 0.3);
    border-right: 1px solid rgba(255, 121, 63, 0.18);
    border-bottom: 2.5px solid rgba(255, 121, 63, 0.45);
    display: flex;
    flex-direction: column;
    gap: 3.5px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
  }}

  .card-top-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .badge-group {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  /* Time Badge */
  .event-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13.5px;
    font-weight: 800;
    color: #ffeaa7;
    background: #341954;
    border: 1px solid rgba(255, 121, 63, 0.35);
    padding: 2px 7.5px;
    border-radius: 4px;
    letter-spacing: 0.2px;
  }}

  /* Price Badge */
  .event-price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    font-weight: 800;
    padding: 2px 7.5px;
    border-radius: 4px;
    letter-spacing: 0.3px;
  }}

  .price-free {{
    background: #00b894;
    color: #ffffff;
    box-shadow: 0 1px 5px rgba(0, 184, 148, 0.3);
  }}

  .price-paid {{
    background: #d35400;
    color: #ffeaa7;
    border: 1px solid #f39c12;
  }}

  /* Location on Top Right */
  .event-location {{
    font-size: 13.5px;
    font-weight: 600;
    color: #c9bbde;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 260px;
    text-align: right;
  }}

  .event-location strong {{
    color: #ffeaa7;
    font-weight: 800;
  }}

  /* Bold, Large, Punchy Title for Mobile Readability */
  .event-title {{
    font-size: 19.5px;
    font-weight: 900;
    color: #ffffff;
    line-height: 1.15;
    letter-spacing: -0.2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-shadow: 0 1px 3px rgba(0,0,0,0.3);
  }}

  /* Bottom Ribbon */
  .footer-ribbon {{
    margin-top: 8px;
    background: linear-gradient(90deg, #ff4757, #ff793f, #e056fd);
    border-radius: 10px;
    padding: 9px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 3px 14px rgba(255, 121, 63, 0.4);
  }}

  .footer-left {{
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 1.2px;
    color: #ffffff;
    text-transform: uppercase;
  }}

  .footer-center {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13.5px;
    font-weight: 800;
    color: #ffeaa7;
    background: #200d36;
    border: 1.5px solid #ff793f;
    padding: 2.5px 12px;
    border-radius: 5px;
    letter-spacing: 0.5px;
  }}

  .footer-right {{
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 1px;
    color: #ffffff;
    text-transform: uppercase;
  }}
</style>
</head>
<body>
  <div class="poster">
    
    <!-- Top Header -->
    <div class="header-wrap">
      <div class="header-left">
        <div class="eyebrow-pill">🎃 HALLOWEEN &amp; DÍA DE LOS MUERTOS · 20 PICKS 💀</div>
        <div class="main-title">Tonight in <span>Boston</span></div>
      </div>
      <div class="header-right">
        <div class="date-badge">SATURDAY · OCT 31</div>
        <div class="sub-tag">BOSTON · CAMBRIDGE · SOMERVILLE</div>
      </div>
    </div>

    <!-- Illustrated Art Banner -->
    <div class="art-banner">
      <img src="{art_b64}" alt="Halloween &amp; Día de los Muertos in Boston" />
      <div class="art-overlay-tag">📍 EAST BOSTON · SYMPHONY · HARVARD SQ · DAVIS SQ · SEAPORT</div>
    </div>

    <!-- 2-Column Grid Split by City (Boston on Left, Cambridge & Somerville on Right) -->
    <div class="grid-container">
      <div class="left-col">
        {boston_col_html}
      </div>
      {right_col_html}
    </div>

    <!-- Bottom Footer Ribbon -->
    <div class="footer-ribbon">
      <div class="footer-left">⭐ TODAY'S CURATED GUIDE</div>
      <div class="footer-center">WICKEDBOSTONEVENTS.COM</div>
      <div class="footer-right">LINK IN BIO FOR TICKETS 🎟️</div>
    </div>

  </div>
</body>
</html>"""
    return html


def generate_caption():
    caption_lines = [
        "🎃 TONIGHT'S TOP 20 EVENTS BY CITY (SATURDAY, OCT 31) 💀\n",
        "Happy Halloween & Día de los Muertos! Here are today's 20 top curated picks sorted chronologically across Boston, Cambridge, and Somerville — with start times, venues, neighborhoods, and retail prices:\n",
        "🏙️ BOSTON (10 PICKS):",
    ]
    for ev in BOSTON_EVENTS:
        price_tag = "FREE" if ev["price"] == "FREE" else ev["price"]
        caption_lines.append(f"✨ {ev['time']} | {ev['title']} | {ev['venue']} ({ev['hood']}) · {price_tag}")

    caption_lines.append("\n🎓 CAMBRIDGE (5 PICKS):")
    for ev in CAMBRIDGE_EVENTS:
        price_tag = "FREE" if ev["price"] == "FREE" else ev["price"]
        caption_lines.append(f"✨ {ev['time']} | {ev['title']} | {ev['venue']} ({ev['hood']}) · {price_tag}")

    caption_lines.append("\n🎨 SOMERVILLE (5 PICKS):")
    for ev in SOMERVILLE_EVENTS:
        price_tag = "FREE" if ev["price"] == "FREE" else ev["price"]
        caption_lines.append(f"✨ {ev['time']} | {ev['title']} | {ev['venue']} ({ev['hood']}) · {price_tag}")

    caption_lines.append("\n🎟️ Tap the LINK IN BIO for direct ticket links, RSVP pages & 400+ more events happening today at wickedbostonevents.com!")
    caption_lines.append("💬 Or COMMENT \"LINKS\" and we'll DM you the direct ticket link for every single event!\n")
    caption_lines.append("#wickedbostonevents #boston #bostonevents #tonightinboston #cambridgema #somervillema #halloweeninboston #diadelosmuertos #bostondatenight #thingstodoinboston #bostonhalloween\n")

    text = "\n".join(caption_lines)
    with open(CAPTION_FILE, "w", encoding="utf-8") as f:
        f.write(text)

    # Save URLs file
    all_events = [("BOSTON", BOSTON_EVENTS), ("CAMBRIDGE", CAMBRIDGE_EVENTS), ("SOMERVILLE", SOMERVILLE_EVENTS)]
    links_lines = ["🎃 TONIGHT IN BOSTON — 20 DIRECT EVENT & TICKET LINKS BY CITY (OCT 31)\n"]
    for city, ev_list in all_events:
        links_lines.append(f"\n📍 {city}:")
        for ev in ev_list:
            links_lines.append(f"• {ev['time']} — {ev['title']} @ {ev['venue']} ({ev['hood']}) · {ev['price']}")
            links_lines.append(f"  🔗 {ev['url']}\n")
    
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(links_lines))


def main():
    print("Generating 20-Event Flyer Split by City...")
    html = generate_today_html()
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
    print(f"Generated Today flyer: {FLYER_PNG}")
    
    # Save cache-busting copy
    shutil.copyfile(FLYER_PNG, CITY_PNG)
    print(f"Copied to: {CITY_PNG}")
    
    generate_caption()
    print(f"Saved Instagram caption: {CAPTION_FILE}")


if __name__ == "__main__":
    main()
