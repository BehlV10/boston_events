#!/usr/bin/env python3
"""
Generate a packed, zero-waste 44-event Weekend Rest Instagram flyer
(Tonight Sat Oct 31 & Tomorrow Sun Nov 1, 2026) for @wickedbostonevents.

Features:
- Wide festive illustration banner on top (Dia de los Muertos & Halloween, 200px).
- 44 curated events total (22 Saturday Night, 22 Sunday).
- Zero bottom empty space: cards fill the entire 1350px canvas cleanly.
- Ultra-tight 4px card gap with zero wasted black space.
- Distinct color accents, time badge, price badge, venue/neighborhood, and bold titles.
- High contrast typography, 1080x1350 resolution for Instagram (4:5).
- Direct caption generation under 2,200 characters.
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


# 22 Saturday Night Events (Oct 31, starting 5 PM through midnight)
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
        "time": "5:00 PM",
        "price": "$15",
        "title": "Revived 30+ Halloween Party",
        "venue": "Smokehouse Tavern",
        "hood": "Lowell",
        "accent": "#f39c12",
        "url": "https://wickedbostonevents.com",
    },
    {
        "time": "5:00 PM",
        "price": "FREE",
        "title": "Sazón Noche de Brujas",
        "venue": "Lili Latin Dance",
        "hood": "Somerville",
        "accent": "#ff5252",
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
        "time": "6:00 PM",
        "price": "$15",
        "title": "Halloween Stand Up Showcase",
        "venue": "Goofs Comedy Club",
        "hood": "Somerville",
        "accent": "#e056fd",
        "url": "https://wickedbostonevents.com",
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
        "venue": "Emerson Colonial",
        "hood": "Downtown",
        "accent": "#54a0ff",
        "url": "https://www.emersoncolonialtheatre.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$15",
        "title": "Motörhead / Cure / Velvet Tributes",
        "venue": "O'Brien's Pub",
        "hood": "Allston",
        "accent": "#ff9f43",
        "url": "https://obrienspubboston.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$15",
        "title": "Cambridge Halloween Bar Crawl",
        "venue": "La Fabrica",
        "hood": "Central Sq",
        "accent": "#f39c12",
        "url": "https://www.eventbrite.com/e/official-cambridge-halloween-bar-crawl-tickets-2001242780027",
    },
    {
        "time": "7:30 PM",
        "price": "$35",
        "title": "Cirque of the Dead",
        "venue": "Arts at the Armory",
        "hood": "Somerville",
        "accent": "#ff7675",
        "url": "https://artsatthearmory.org/",
    },
    {
        "time": "7:30 PM",
        "price": "$32",
        "title": "Nightmare on Hanover Street",
        "venue": "Improv Asylum",
        "hood": "North End",
        "accent": "#ff9f43",
        "url": "https://www.improvasylum.com/",
    },
    {
        "time": "8:00 PM",
        "price": "FREE",
        "title": "Lou's Halloween Party",
        "venue": "Lou's",
        "hood": "Harvard Sq",
        "accent": "#1dd1a1",
        "url": "https://wickedbostonevents.com",
    },
    {
        "time": "8:00 PM",
        "price": "FREE",
        "title": "Halloween @ Loretta's Last Call",
        "venue": "Loretta's Last Call",
        "hood": "Fenway",
        "accent": "#ffd866",
        "url": "https://lorettaslastcall.com/",
    },
    {
        "time": "8:00 PM",
        "price": "$20",
        "title": "Haunted Hotel: Halloween Ball",
        "venue": "W Hotel Boston",
        "hood": "Downtown",
        "accent": "#ff793f",
        "url": "https://wickedbostonevents.com",
    },
    {
        "time": "9:00 PM",
        "price": "$10",
        "title": "Halloween @ Bell in Hand",
        "venue": "Bell in Hand Tavern",
        "hood": "Downtown",
        "accent": "#ff7675",
        "url": "https://thebellinhand.com/",
    },
    {
        "time": "9:30 PM",
        "price": "$20",
        "title": "Dueling Pianos Halloween",
        "venue": "D's Keys",
        "hood": "Seaport",
        "accent": "#e056fd",
        "url": "https://dskeys.com/",
    },
    {
        "time": "11:59 PM",
        "price": "$30",
        "title": "12-Hr Horror Marathon",
        "venue": "Coolidge Corner",
        "hood": "Brookline",
        "accent": "#ff5252",
        "url": "https://coolidge.org/",
    },
]

# 22 Sunday Daytime & Evening Events (Nov 1, 2026: Día de los Muertos & Arts)
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
        "accent": "#ff9f43",
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
        "accent": "#ff7675",
        "url": "https://thepaintedburro.com/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "Seaport Smalls Fall Market",
        "venue": "The Rocks at Harbor Way",
        "hood": "Seaport",
        "accent": "#1dd1a1",
        "url": "https://bostonseaport.xyz/",
    },
    {
        "time": "10:00 AM",
        "price": "FREE",
        "title": "SoWa Open & Vintage Market",
        "venue": "SoWa Boston",
        "hood": "South End",
        "accent": "#f39c12",
        "url": "https://www.sowaboston.com/",
    },
    {
        "time": "11:00 AM",
        "price": "FREE",
        "title": "Lizje Sarria: Latin Jazz Brunch",
        "venue": "The Beehive",
        "hood": "South End",
        "accent": "#ff793f",
        "url": "https://beehiveboston.com/",
    },
    {
        "time": "11:00 AM",
        "price": "FREE",
        "title": "Bach Cantata Series",
        "venue": "Emmanuel Church",
        "hood": "Back Bay",
        "accent": "#54a0ff",
        "url": "https://www.emmanuelmusic.org/",
    },
    {
        "time": "11:30 AM",
        "price": "FREE",
        "title": "Sunday Jazz Brunch",
        "venue": "Lou's",
        "hood": "Harvard Sq",
        "accent": "#00d2d3",
        "url": "https://wickedbostonevents.com",
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
        "title": "To Kill a Mockingbird (Broadway)",
        "venue": "Huntington Theatre",
        "hood": "Back Bay",
        "accent": "#a29bfe",
        "url": "https://www.huntingtontheatre.org/",
    },
    {
        "time": "2:00 PM",
        "price": "$20",
        "title": "Rocky Horror w/ Prop Bags",
        "venue": "Somerville Theatre",
        "hood": "Davis Sq",
        "accent": "#ff5252",
        "url": "https://somervilletheatre.com/",
    },
    {
        "time": "3:00 PM",
        "price": "FREE",
        "title": "Día de Los Muertos @ Bow Market",
        "venue": "Bow Market",
        "hood": "Somerville",
        "accent": "#ffd866",
        "url": "https://www.bowmarketsomerville.com/",
    },
    {
        "time": "4:00 PM",
        "price": "$15",
        "title": "ONCE Indie Music Series",
        "venue": "Redbones",
        "hood": "Davis Sq",
        "accent": "#ff7675",
        "url": "https://redbones.com/",
    },
    {
        "time": "7:00 PM",
        "price": "$15",
        "title": "The Commute: Live Theatre",
        "venue": "The Rockwell",
        "hood": "Davis Sq",
        "accent": "#ff793f",
        "url": "https://therockwell.org/",
    },
    {
        "time": "7:30 PM",
        "price": "FREE",
        "title": "Comedy at The 88 Club",
        "venue": "The 88 Club",
        "hood": "Allston",
        "accent": "#00d2d3",
        "url": "https://wickedbostonevents.com",
    },
]


def render_card(ev):
    is_free = "FREE" in ev["price"].upper()
    price_cls = "price-free" if is_free else "price-paid"
    
    return f"""
    <div class="event-card" style="border-left: 3.5px solid {ev['accent']};">
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
    background: #0f071d;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    color: #ffffff;
    display: flex;
    flex-direction: column;
    padding: 16px 20px 14px 20px;
    position: relative;
    overflow: hidden;
  }}

  /* Top Header Bar */
  .top-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 7px;
    flex-shrink: 0;
  }}

  .header-titles {{
    display: flex;
    align-items: baseline;
    gap: 10px;
  }}

  .brand-logo {{
    font-size: 26px;
    font-weight: 900;
    letter-spacing: -0.6px;
    color: #ffffff;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .brand-logo span.glow {{
    color: #ff793f;
    text-shadow: 0 0 14px rgba(255, 121, 63, 0.5);
  }}

  .sub-header-tag {{
    font-size: 13px;
    font-weight: 700;
    color: #ffd866;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}

  .handle-badge {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 800;
    color: #ffeaa7;
    background: rgba(255, 121, 63, 0.22);
    border: 1.5px solid rgba(255, 121, 63, 0.5);
    padding: 3px 10px;
    border-radius: 6px;
    letter-spacing: 0.3px;
  }}

  /* Wide Banner Art */
  .art-banner {{
    width: 100%;
    height: 195px;
    border-radius: 10px;
    overflow: hidden;
    position: relative;
    margin-bottom: 8px;
    flex-shrink: 0;
    border: 1.5px solid #ff793f;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.5), 0 0 16px rgba(255, 121, 63, 0.22);
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
    bottom: 7px;
    right: 9px;
    background: rgba(15, 7, 29, 0.94);
    backdrop-filter: blur(8px);
    border: 1px solid #ff793f;
    color: #ffeaa7;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 0.8px;
    padding: 3px 10px;
    border-radius: 5px;
    text-transform: uppercase;
  }}

  /* 2-Column Content Layout */
  .columns-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    flex: 1;
    min-height: 0;
    margin-bottom: 8px;
  }}

  .day-col {{
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }}

  .col-header {{
    background: #1e1136;
    border-radius: 7px;
    padding: 5px 10px;
    margin-bottom: 5px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border: 1px solid rgba(255, 255, 255, 0.1);
    flex-shrink: 0;
  }}

  .col-title {{
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 5px;
  }}

  .col-header.sat {{
    border-left: 3.5px solid #ff793f;
  }}
  .col-header.sat .col-title {{
    color: #ff9f43;
  }}

  .col-header.sun {{
    border-left: 3.5px solid #2ed573;
  }}
  .col-header.sun .col-title {{
    color: #7bed9f;
  }}

  .col-subtext {{
    font-size: 9.5px;
    font-weight: 800;
    color: #a29bfe;
    letter-spacing: 0.5px;
  }}

  /* Cards List: 4px tight gap, perfectly filling available height */
  .cards-list {{
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    min-height: 0;
  }}

  /* Event Card: Compact, high density, rich deep purple */
  .event-card {{
    background: #1a0e2e;
    border-radius: 5px;
    padding: 3.5px 8.5px;
    border: 1px solid rgba(255, 121, 63, 0.2);
    border-right: 1px solid rgba(255, 121, 63, 0.12);
    border-bottom: 2px solid rgba(255, 121, 63, 0.35);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 1.5px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    flex: 1;
    min-height: 0;
  }}

  .card-top-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}

  .badge-group {{
    display: flex;
    align-items: center;
    gap: 4px;
  }}

  .event-time {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 800;
    color: #ffeaa7;
    background: #2b1446;
    border: 1px solid rgba(255, 121, 63, 0.3);
    padding: 1px 4.5px;
    border-radius: 3px;
    letter-spacing: 0.1px;
    line-height: 1.2;
  }}

  .event-price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 9.5px;
    font-weight: 800;
    padding: 1px 4.5px;
    border-radius: 3px;
    letter-spacing: 0.2px;
    line-height: 1.2;
  }}

  .price-free {{
    background: #00b894;
    color: #ffffff;
  }}

  .price-paid {{
    background: #d35400;
    color: #ffeaa7;
    border: 1px solid #f39c12;
  }}

  .event-location {{
    font-size: 10px;
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

  .event-title {{
    font-size: 13.5px;
    font-weight: 900;
    color: #ffffff;
    line-height: 1.15;
    letter-spacing: -0.2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Bottom Footer Card */
  .footer-card {{
    background: #170d28;
    border-radius: 8px;
    border: 1px solid rgba(255, 121, 63, 0.3);
    padding: 6px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }}

  .footer-left {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11.5px;
    font-weight: 700;
    color: #ffd866;
  }}

  .footer-right {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 800;
    color: #ffffff;
    background: linear-gradient(135deg, #ff4757 0%, #ff793f 60%, #f39c12 100%);
    padding: 3px 10px;
    border-radius: 5px;
    letter-spacing: 0.3px;
    box-shadow: 0 2px 6px rgba(255, 121, 63, 0.4);
  }}
</style>
</head>
<body>

  <!-- Top Header -->
  <div class="top-header">
    <div class="header-titles">
      <div class="brand-logo">
        <span>Halloweekend:</span> <span class="glow">Tonight & Sunday</span>
      </div>
      <div class="sub-header-tag">44 Curated Shows & Events</div>
    </div>
    <div class="handle-badge">@wickedbostonevents</div>
  </div>

  <!-- Wide Banner Art -->
  <div class="art-banner">
    <img src="{art_b64}" alt="Halloween & Día de los Muertos">
    <div class="art-overlay-tag">📍 Boston · Cambridge · Somerville · Fenway</div>
  </div>

  <!-- Columns Grid -->
  <div class="columns-grid">
    <!-- Column 1: Saturday Night -->
    <div class="day-col">
      <div class="col-header sat">
        <span class="col-title">🎃 TONIGHT · SAT OCT 31</span>
        <span class="col-subtext">HALLOWEEN NIGHT (22 PICKS)</span>
      </div>
      <div class="cards-list">
        {sat_cards}
      </div>
    </div>

    <!-- Column 2: Sunday -->
    <div class="day-col">
      <div class="col-header sun">
        <span class="col-title">🌼 TOMORROW · SUN NOV 01</span>
        <span class="col-subtext">DÍA DE MUERTOS & MORE (22 PICKS)</span>
      </div>
      <div class="cards-list">
        {sun_cards}
      </div>
    </div>
  </div>

  <!-- Bottom Footer -->
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
    caption = (
        "🎃 HALLOWEEKEND GUIDE: TONIGHT & SUNDAY! (Oct 31 – Nov 1) 🌼\n\n"
        "Check the flyer above for all 44 curated picks, plus top highlights below!\n\n"
        "🎃 TONIGHT · HALLOWEEN NIGHT HIGHLIGHTS:\n"
        "• Bluegrass Jam – The Burren (5 PM, Free)\n"
        "• Night of Living Dead w/ Live Score – The Underground (5 PM, $20)\n"
        "• The Blair Project Bash – City Hall Plaza (6 PM, Free)\n"
        "• Halloween @ Harpoon x Natalija (6 PM, Free)\n"
        "• Stand Up Comedy – Goofs Comedy Club (6 PM, $15)\n"
        "• Sam Adams Halloween Bash – Sam Adams Taproom (7 PM, Free)\n"
        "• Punkoween 2: Tributes – Middle East Upstairs (7 PM, $18)\n"
        "• SCARY-OKE w/ Jesse Gallagher – The Lilypad (7 PM, $12)\n"
        "• Death Becomes She/Her Drag – Club Café (7 PM, $20)\n"
        "• Blade Runner Live in Concert – Emerson Colonial (7 PM, $65+)\n"
        "• Cambridge Halloween Bar Crawl – La Fabrica (7 PM, $15)\n"
        "• Cirque of the Dead – Arts at the Armory (7:30 PM, $35)\n"
        "• Nightmare on Hanover St – Improv Asylum (7:30 PM, $32)\n"
        "• 12-Hr Horror Marathon – Coolidge Corner (11:59 PM, $30)\n\n"
        "🌼 TOMORROW · SUNDAY HIGHLIGHTS:\n"
        "• Cambridge Half Marathon – Cambridgeside (7 AM, Free)\n"
        "• Día de Muertos: Ofrendas – ICA Watershed (10 AM, Free)\n"
        "• MFA Boston: Diwali Festival – MFA (10 AM, Free*)\n"
        "• Seaport Smalls Fall Market – Harbor Way (10 AM, Free)\n"
        "• SoWa Open & Vintage Market – South End (10 AM, Free)\n"
        "• Latin Jazz Brunch – The Beehive (11 AM, Free)\n"
        "• Day of DeadFest 2026 – The Foundry (12 PM, Free)\n"
        "• Ukrainian FoodFest – St. Andrew Church (12 PM, Free)\n"
        "• Traditional Irish Brunch – The Druid (12 PM, Free)\n"
        "• Chelsea Day of Dead Festival – Chelsea Sq (1 PM, Free)\n"
        "• Wicked Broadway Tour – Citizens Opera House (1 PM, $45+)\n"
        "• Eleanor Alberga Quartets – Gardner Museum (1:30 PM, $36)\n"
        "• Rocky Horror w/ Prop Bags – Somerville Theatre (2 PM, $20)\n"
        "• Día de Los Muertos – Bow Market (3 PM, Free)\n\n"
        "🔗 Direct ticket links & 400+ more live events: wickedbostonevents.com (link in bio)!\n\n"
        "#wickedbostonevents #boston #cambridgema #somervillema #bostonhalloween #bostondatenight #bostonweekend #bostonfoodies #bostonguide #bostonevents"
    )
    return caption


def generate_links_file():
    lines = ["=== WEEKEND REST CURATED EVENT LINKS ===", ""]
    lines.append("--- SATURDAY NIGHT OCT 31 ---")
    for ev in SAT_NIGHT_EVENTS:
        lines.append(f"{ev['time']} | {ev['title']} ({ev['price']}) - {ev['venue']}")
        lines.append(f"  URL: {ev['url']}")
    lines.append("")
    lines.append("--- SUNDAY NOV 01 ---")
    for ev in SUN_EVENTS:
        lines.append(f"{ev['time']} | {ev['title']} ({ev['price']}) - {ev['venue']}")
        lines.append(f"  URL: {ev['url']}")
    
    with open(LINKS_FILE, "w") as f:
        f.write("\n".join(lines))


def main():
    print("Generating 44-Event Zero-Waste Weekend Rest Flyer...")
    html_content = generate_flyer_html()
    with open(FLYER_HTML, "w") as f:
        f.write(html_content)

    # Capture 1080x1350 screenshot
    cmd = [
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--hide-scrollbars",
        "--window-size=1080,1350",
        f"--screenshot={FLYER_PNG}",
        FLYER_HTML,
    ]
    subprocess.run(cmd, check=True)
    print(f"Generated Weekend Rest flyer: {FLYER_PNG}")

    caption = generate_caption()
    with open(CAPTION_FILE, "w") as f:
        f.write(caption)
    print(f"Saved Instagram caption: {CAPTION_FILE} (Length: {len(caption)} chars)")

    generate_links_file()
    print(f"Saved links file: {LINKS_FILE}")


if __name__ == "__main__":
    main()
