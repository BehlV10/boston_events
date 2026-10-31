#!/usr/bin/env python3
"""
Generate a packed 28-event Weekend Rest Instagram flyer (Tonight Sat Oct 31 & Tomorrow Sun Nov 1, 2026)
for @wickedbostonevents with zero wasted whitespace and high-density, easily readable event cards.

Features:
- Balanced 2-column layout:
  - Left Column: 🎃 TONIGHT · SAT OCT 31 (14 Halloween Night picks)
  - Right Column: 🌼 TOMORROW · SUN NOV 01 (14 Día de los Muertos & Sunday picks)
- High contrast typography, 1080x1350 resolution for Instagram (4:5).
- Tight, balanced spacing with NO giant gaps of whitespace.
- Start Time, Price / FREE badge, Venue & Neighborhood on top row.
- Bold punchy event title on bottom row.
- Direct caption generation with links and Instagram tags.
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

OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
ART_IMG = os.path.join(OUTPUT_DIR, "dia_de_muertos_halloween.jpg")
FLYER_PNG = os.path.join(OUTPUT_DIR, "weekend_rest_flyer.png")
FLYER_HTML = os.path.join(OUTPUT_DIR, "weekend_rest_flyer.html")
CAPTION_FILE = os.path.join(OUTPUT_DIR, "weekend_rest_caption.txt")
LINKS_FILE = os.path.join(OUTPUT_DIR, "weekend_rest_links.txt")

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"


def get_art_base64():
    if os.path.exists(ART_IMG):
        with open(ART_IMG, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("utf-8")
    return ""


SAT_NIGHT_EVENTS = [
    {
        "time": "5:00 PM",
        "price": "FREE",
        "title": "Bluegrass Session & Jam",
        "venue": "The Burren Front Room",
        "hood": "Davis Sq",
        "accent": "#00d2d3",
        "url": "https://www.burren.com/",
    },
    {
        "time": "5:00 PM",
        "price": "$20",
        "title": "Night of Living Dead w/ Live Score",
        "venue": "The Underground",
        "hood": "Downtown",
        "accent": "#ff7675",
        "url": "https://wickedbostonevents.com",
    },
    {
        "time": "6:00 PM",
        "price": "FREE",
        "title": "The Blair Project Halloween Bash",
        "venue": "City Hall Plaza",
        "hood": "Downtown",
        "accent": "#ffd866",
        "url": "https://www.boston.gov/",
    },
    {
        "time": "6:00 PM",
        "price": "FREE",
        "title": "Halloween @ Harpoon x Natalija",
        "venue": "Harpoon Beer Hall",
        "hood": "Seaport",
        "accent": "#ff9f43",
        "url": "https://www.harpoonbrewery.com/",
    },
    {
        "time": "7:00 PM",
        "price": "FREE",
        "title": "Sam Adams Halloween Bash",
        "venue": "Sam Adams Taproom",
        "hood": "Downtown",
        "accent": "#ff6b6b",
        "url": "https://www.samadamsbostontaproom.com/events",
    },
    {
        "time": "7:00 PM",
        "price": "$18",
        "title": "Punkoween 2: Tributes",
        "venue": "Middle East Upstairs",
        "hood": "Central Sq",
        "accent": "#ff793f",
        "url": "https://www.mideastoffers.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$12",
        "title": "SCARY-OKE w/ Jesse Gallagher",
        "venue": "The Lilypad",
        "hood": "Inman Sq",
        "accent": "#e056fd",
        "url": "https://www.lilypadinman.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$20",
        "title": "Death Becomes She/Her: Drag",
        "venue": "Club Café",
        "hood": "South End",
        "accent": "#ff5252",
        "url": "https://www.clubcafe.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$65+",
        "title": "Blade Runner Live in Concert",
        "venue": "Emerson Colonial Theatre",
        "hood": "Downtown",
        "accent": "#54a0ff",
        "url": "https://www.emersoncolonialtheatre.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$15",
        "title": "Motörhead / Cure / Velvet Underground",
        "venue": "O'Brien's Pub",
        "hood": "Allston",
        "accent": "#ff9f43",
        "url": "https://obrienspubboston.com/",
    },
    {
        "time": "7:30 PM",
        "price": "$35",
        "title": "Cirque of the Dead",
        "venue": "Arts at the Armory",
        "hood": "Somerville",
        "accent": "#ff9f43",
        "url": "https://artsatthearmory.org/events/cirque-of-the-dead/",
    },
    {
        "time": "7:30 PM",
        "price": "$32",
        "title": "Nightmare on Hanover Street",
        "venue": "Improv Asylum",
        "hood": "North End",
        "accent": "#ff7675",
        "url": "https://improvasylum.com/",
    },
    {
        "time": "8:00 PM",
        "price": "FREE",
        "title": "Lou's Halloween Party",
        "venue": "Lou's",
        "hood": "Harvard Sq",
        "accent": "#00d2d3",
        "url": "https://lousharvardsq.com/",
    },
    {
        "time": "11:59 PM",
        "price": "$30",
        "title": "12-Hr Horror Marathon",
        "venue": "Coolidge Corner Theatre",
        "hood": "Brookline",
        "accent": "#a29bfe",
        "url": "https://coolidge.org/",
    },
]

SUN_EVENTS = [
    {
        "time": "7:00 AM",
        "price": "FREE",
        "title": "Cambridge Half Marathon",
        "venue": "Cambridgeside",
        "hood": "Cambridge",
        "accent": "#00d2d3",
        "url": "https://cambridgehalf.com/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Día de Muertos: Ofrendas Altar",
        "venue": "ICA Watershed",
        "hood": "East Boston",
        "accent": "#10ac84",
        "url": "https://www.icaboston.org/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE*",
        "title": "MFA Boston: Diwali Festival",
        "venue": "Museum of Fine Arts",
        "hood": "Fenway",
        "accent": "#ffd866",
        "url": "https://www.mfa.org/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Raúl The Third: Book Signing & Art",
        "venue": "Painted Burro",
        "hood": "Davis Sq",
        "accent": "#ff9f43",
        "url": "https://thepaintedburro.com/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Seaport Smalls Fall Market",
        "venue": "The Rocks at Harbor Way",
        "hood": "Seaport",
        "accent": "#54a0ff",
        "url": "https://bostonseaport.xyz/",
    },
    {
        "time": "12:00 PM",
        "price": "FREE",
        "title": "Day of DeadFest 2026",
        "venue": "The Foundry",
        "hood": "Cambridge",
        "accent": "#ff6b6b",
        "url": "https://cambridgefoundry.org/",
    },
    {
        "time": "12:00 PM",
        "price": "FREE",
        "title": "Ukrainian FoodFest",
        "venue": "St. Andrew Church",
        "hood": "Boston",
        "accent": "#54a0ff",
        "url": "https://standrewuoc.org/",
    },
    {
        "time": "12:00 PM",
        "price": "FREE",
        "title": "Traditional Irish Music Brunch",
        "venue": "The Druid",
        "hood": "Inman Sq",
        "accent": "#1dd1a1",
        "url": "https://thedruid.co/",
    },
    {
        "time": "12:00 PM",
        "price": "FREE",
        "title": "Scottish Session Brunch",
        "venue": "McCarthy's Toad",
        "hood": "Porter Sq",
        "accent": "#f39c12",
        "url": "https://mccarthystoad.com/",
    },
    {
        "time": "1:00 PM",
        "price": "FREE",
        "title": "Chelsea Day of Dead Festival",
        "venue": "Chelsea Square Park",
        "hood": "Chelsea",
        "accent": "#ff793f",
        "url": "https://chelseama.gov/",
    },
    {
        "time": "1:00 PM",
        "price": "$45+",
        "title": "Wicked (Broadway National Tour)",
        "venue": "Citizens Opera House",
        "hood": "Downtown",
        "accent": "#2ed573",
        "url": "https://boston.broadway.com/",
    },
    {
        "time": "1:30 PM",
        "price": "$36",
        "title": "Eleanor Alberga Quartets",
        "venue": "Gardner Museum",
        "hood": "Fenway",
        "accent": "#e056fd",
        "url": "https://www.gardnermuseum.org/",
    },
    {
        "time": "2:00 PM",
        "price": "$25+",
        "title": "To Kill a Mockingbird",
        "venue": "Huntington Theatre",
        "hood": "Back Bay",
        "accent": "#a29bfe",
        "url": "https://www.huntingtontheatre.org/",
    },
    {
        "time": "7:00 PM",
        "price": "$15",
        "title": "The Commute: Live Theatre",
        "venue": "The Rockwell",
        "hood": "Davis Sq",
        "accent": "#ff7675",
        "url": "https://therockwell.org/",
    },
]


def render_card(ev):
    is_free = "FREE" in ev["price"].upper()
    price_cls = "price-free" if is_free else "price-paid"
    
    return f"""
    <div class="event-card" style="border-left: 4.5px solid {ev['accent']};">
      <div class="card-top-row">
        <div class="badge-group">
          <span class="event-time">{ev['time']}</span>
          <span class="event-price {price_cls}">{ev['price']}</span>
        </div>
        <div class="event-location">
          <strong>{ev['venue']}</strong> · {ev['hood']}
        </div>
      </div>
      <div class="event-title">{ev['title']}</div>
    </div>
    """


def generate_flyer_html():
    art_b64 = get_art_base64()
    sat_cards = "\n".join(render_card(e) for e in SAT_NIGHT_EVENTS)
    sun_cards = "\n".join(render_card(e) for e in SUN_EVENTS)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Halloweekend: Tonight & Sunday Events Flyer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800;900&family=JetBrains+Mono:wght@700;800&display=swap" rel="stylesheet">
<style>
  * {{
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }}

  body {{
    width: 1080px;
    height: 1350px;
    background: #0d061a;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    color: #ffffff;
    display: flex;
    flex-direction: column;
    padding: 20px 24px 18px 24px;
    position: relative;
    overflow: hidden;
  }}

  /* Halloween Atmosphere background glow */
  body::before {{
    content: '';
    position: absolute;
    top: -120px;
    left: 20%;
    width: 600px;
    height: 350px;
    background: radial-gradient(ellipse at center, rgba(255, 121, 63, 0.22) 0%, rgba(13, 6, 26, 0) 70%);
    pointer-events: none;
    z-index: 0;
  }}

  body::after {{
    content: '';
    position: absolute;
    bottom: -150px;
    right: 10%;
    width: 650px;
    height: 400px;
    background: radial-gradient(ellipse at center, rgba(162, 155, 254, 0.16) 0%, rgba(13, 6, 26, 0) 70%);
    pointer-events: none;
    z-index: 0;
  }}

  .header-card {{
    background: #170d28;
    border-radius: 12px;
    border: 1.5px solid rgba(255, 121, 63, 0.4);
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.5), 0 0 25px rgba(255, 121, 63, 0.15);
    padding: 10px 18px 10px 14px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 10px;
    position: relative;
    z-index: 1;
    flex-shrink: 0;
  }}

  .header-art {{
    width: 74px;
    height: 74px;
    border-radius: 10px;
    object-fit: cover;
    border: 2px solid #ff793f;
    box-shadow: 0 0 12px rgba(255, 121, 63, 0.5);
    flex-shrink: 0;
  }}

  .header-info {{
    flex: 1;
  }}

  .header-top-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 2px;
  }}

  .brand-tag {{
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    color: #ffd866;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .handle-tag {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 700;
    color: #ffeaa7;
    background: rgba(255, 121, 63, 0.2);
    border: 1px solid rgba(255, 121, 63, 0.45);
    padding: 2px 7.5px;
    border-radius: 5px;
  }}

  .main-title {{
    font-size: 29px;
    font-weight: 900;
    letter-spacing: -0.5px;
    color: #ffffff;
    line-height: 1.1;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .main-title span.glow {{
    color: #ff793f;
    text-shadow: 0 0 16px rgba(255, 121, 63, 0.6);
  }}

  .sub-tagline {{
    font-size: 12.5px;
    color: #d1c4e9;
    font-weight: 600;
    margin-top: 2px;
  }}

  /* 2-Column Content Layout */
  .columns-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    flex: 1;
    position: relative;
    z-index: 1;
    min-height: 0;
  }}

  .day-col {{
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }}

  .col-header {{
    background: #201237;
    border-radius: 8px;
    padding: 6px 12px;
    margin-bottom: 7px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid rgba(255, 255, 255, 0.1);
    flex-shrink: 0;
  }}

  .col-title {{
    font-size: 13px;
    font-weight: 900;
    letter-spacing: 1.1px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .col-header.sat {{
    border-left: 4px solid #ff793f;
  }}
  .col-header.sat .col-title {{
    color: #ff9f43;
  }}

  .col-header.sun {{
    border-left: 4px solid #2ed573;
  }}
  .col-header.sun .col-title {{
    color: #7bed9f;
  }}

  .col-subtext {{
    font-size: 10.5px;
    font-weight: 700;
    color: #a29bfe;
    letter-spacing: 0.5px;
  }}

  .cards-list {{
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: 1;
  }}

  /* Event Card: Compact, high density, rich dark purple */
  .event-card {{
    background: #190e2d;
    border-radius: 7px;
    padding: 6.5px 11px 6.5px 11px;
    border: 1px solid rgba(255, 121, 63, 0.22);
    border-right: 1px solid rgba(255, 121, 63, 0.14);
    border-bottom: 2px solid rgba(255, 121, 63, 0.38);
    display: flex;
    flex-direction: column;
    gap: 3px;
    box-shadow: 0 1.5px 6px rgba(0, 0, 0, 0.25);
  }}

  .card-top-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .badge-group {{
    display: flex;
    align-items: center;
    gap: 5px;
  }}

  .event-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 800;
    color: #ffeaa7;
    background: #2d1549;
    border: 1px solid rgba(255, 121, 63, 0.35);
    padding: 1.5px 6px;
    border-radius: 4px;
    letter-spacing: 0.2px;
  }}

  .event-price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 800;
    padding: 1.5px 6px;
    border-radius: 4px;
    letter-spacing: 0.2px;
  }}

  .price-free {{
    background: #00b894;
    color: #ffffff;
    box-shadow: 0 1px 4px rgba(0, 184, 148, 0.3);
  }}

  .price-paid {{
    background: #d35400;
    color: #ffeaa7;
    border: 1px solid #f39c12;
  }}

  .event-location {{
    font-size: 12px;
    font-weight: 600;
    color: #c9bbde;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 250px;
    text-align: right;
  }}

  .event-location strong {{
    color: #ffeaa7;
    font-weight: 800;
  }}

  .event-title {{
    font-size: 16.5px;
    font-weight: 900;
    color: #ffffff;
    line-height: 1.15;
    letter-spacing: -0.2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Footer Card */
  .footer-card {{
    background: #170d28;
    border-radius: 10px;
    border: 1px solid rgba(255, 121, 63, 0.3);
    margin-top: 9px;
    padding: 7px 18px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    z-index: 1;
    flex-shrink: 0;
  }}

  .footer-left {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    font-weight: 700;
    color: #ffd866;
  }}

  .footer-right {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12.5px;
    font-weight: 800;
    color: #ffffff;
    background: linear-gradient(135deg, #ff4757 0%, #ff793f 60%, #f39c12 100%);
    padding: 3.5px 11px;
    border-radius: 6px;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 8px rgba(255, 121, 63, 0.4);
  }}
</style>
</head>
<body>

  <!-- Header -->
  <div class="header-card">
    <img src="{art_b64}" class="header-art" alt="Halloween & Día de los Muertos">
    <div class="header-info">
      <div class="header-top-row">
        <span class="brand-tag">⚡ WICKED BOSTON EVENTS</span>
        <span class="handle-tag">@wickedbostonevents</span>
      </div>
      <div class="main-title">
        <span>HALLOWEEKEND:</span> <span class="glow">TONIGHT & SUNDAY</span>
      </div>
      <div class="sub-tagline">
        28 Top Curated Halloween Parties, Live Shows & Día de los Muertos in Boston, Cambridge & Somerville
      </div>
    </div>
  </div>

  <!-- Columns Grid -->
  <div class="columns-grid">
    <!-- Column 1: Saturday Night -->
    <div class="day-col">
      <div class="col-header sat">
        <span class="col-title">🎃 TONIGHT · SAT OCT 31</span>
        <span class="col-subtext">HALLOWEEN NIGHT (14 PICKS)</span>
      </div>
      <div class="cards-list">
        {sat_cards}
      </div>
    </div>

    <!-- Column 2: Sunday -->
    <div class="day-col">
      <div class="col-header sun">
        <span class="col-title">🌼 TOMORROW · SUN NOV 01</span>
        <span class="col-subtext">DÍA DE MUERTOS & MORE (14 PICKS)</span>
      </div>
      <div class="cards-list">
        {sun_cards}
      </div>
    </div>
  </div>

  <!-- Footer -->
  <div class="footer-card">
    <div class="footer-left">
      <span>📍 400+ More Live Events & Direct Ticket Links:</span>
    </div>
    <div class="footer-right">
      wickedbostonevents.com
    </div>
  </div>

</body>
</html>
"""


def generate_caption():
    lines = [
        "🎃 HALLOWEEKEND GUIDE: TONIGHT & SUNDAY (OCT 31 – NOV 1) 🌼",
        "",
        "The weekend isn't over yet! Whether you're heading out for Halloween tonight or exploring Día de los Muertos & Diwali festivals on Sunday, here are 28 top handpicked events across Boston, Cambridge & Somerville:",
        "",
        "🎃 TONIGHT · SATURDAY OCT 31 (Halloween Night):",
    ]
    for ev in SAT_NIGHT_EVENTS:
        lines.append(f"• {ev['time']} — {ev['title']} @ {ev['venue']} ({ev['hood']}) · {ev['price']}")
    
    lines.append("\n🌼 TOMORROW · SUNDAY NOV 01 (Día de los Muertos, Festivals & Sunday Vibes):")
    for ev in SUN_EVENTS:
        lines.append(f"• {ev['time']} — {ev['title']} @ {ev['venue']} ({ev['hood']}) · {ev['price']}")
    
    lines.append("\n🎟️ Tap the LINK IN BIO to visit wickedbostonevents.com for 400+ more live events, interactive transit maps & ticket links!")
    lines.append("\n#wickedbostonevents #boston #bostonevents #halloweekend #halloweeninboston #bostonhalloween #diadelosmuertos #cambridgema #somervillema #harvardsquare #davissquare #centralsquare #thingstodoinboston #bostondatenight #bostonparties\n")

    with open(CAPTION_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    # Also save direct links file
    links = ["🎃 HALLOWEEKEND DIRECT EVENT & TICKET LINKS\n"]
    links.append("SATURDAY OCT 31:")
    for ev in SAT_NIGHT_EVENTS:
        links.append(f"• {ev['title']} @ {ev['venue']}: {ev['url']}")
    links.append("\nSUNDAY NOV 01:")
    for ev in SUN_EVENTS:
        links.append(f"• {ev['title']} @ {ev['venue']}: {ev['url']}")
    
    with open(LINKS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(links))


def main():
    print("Generating 28-Event Weekend Rest Flyer...")
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
    print(f"Generated Weekend Rest flyer: {FLYER_PNG}")
    
    generate_caption()
    print(f"Saved Instagram caption: {CAPTION_FILE}")


if __name__ == "__main__":
    main()
