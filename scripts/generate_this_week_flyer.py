#!/usr/bin/env python3
"""
Generate high-contrast, clean white-background weekly event flyers
(1080x1350 Instagram / LinkedIn carousel format) matching the exact
style of Boston Fun Events:
- Slide 1: Weekday Edition (Monday through Friday, 1/2)
- Slide 2: Weekend Edition (Saturday & Sunday + Highlights, 2/2)
"""

import os
import sys
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"

# -------------------------------------------------------------
# WEEKDAY DATA (SLIDE 1: MON - FRI)
# -------------------------------------------------------------
SLIDE1_DATA = {
    "title_top": "55+ BEST EVENTS",
    "title_box": "BOSTON THIS WEEK",
    "subtitle": "NOVEMBER 2ND–8TH, 2026 • 1/2",
    "left_col": [
        {
            "day": "MONDAY • NOV 2",
            "pill_bg": "#0047e1",
            "pill_color": "#ffffff",
            "events": [
                {"time": "6 PM", "title": "Saborcito: Salsa & Bachata", "venue": "The Anchor • 1 Shipyard Park, Charlestown"},
                {"time": "7 PM", "title": "This Is Lorelei", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "7 PM D", "title": "Madra Salach", "venue": "The Sinclair • 52 Church St, Cambridge"},
                {"time": "7:30 PM", "title": "Queer Line & Partner Dancing", "venue": "Club Café • 209 Columbus Ave, Boston"},
                {"time": "8 PM", "title": "Bluegrass: Royer Family Band", "venue": "Remnant Satellite • 877 Cambridge St, Cambridge"},
                {"time": "8 PM", "title": "Bachata Mondays", "venue": "Havana Club • 288 Green St, Cambridge"},
            ]
        },
        {
            "day": "TUESDAY • NOV 3",
            "pill_bg": "#e62e00",
            "pill_color": "#ffffff",
            "events": [
                {"time": "7 PM", "title": "Free Comedy Open-Mic", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
                {"time": "7 PM D", "title": "half•alive", "venue": "The Sinclair • 52 Church St, Cambridge"},
                {"time": "7 PM", "title": "AJ McLean: The Better Man Tour", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "7:30 PM", "title": "Tuesday Trivia Night", "venue": "Remnant Satellite • 877 Cambridge St, Cambridge"},
                {"time": "8 PM", "title": "Willi Carlisle", "venue": "Crystal Ballroom • 55 Davis Sq, Somerville"},
                {"time": "8 PM", "title": "Salsa & Bachata Social", "venue": "Havana Club • 288 Green St, Cambridge"},
            ]
        },
        {
            "day": "WEDNESDAY • NOV 4",
            "pill_bg": "#0047e1",
            "pill_color": "#ffffff",
            "events": [
                {"time": "10 AM", "title": "Fleurs de Villes WONDER", "venue": "Prudential Center • 800 Boylston St, Boston"},
                {"time": "11 AM", "title": "Fall Foliage Walk", "venue": "Daisy Field • 217 Jamaicaway, Jamaica Plain"},
                {"time": "6:30 PM", "title": "Remnant Run Club", "venue": "Remnant Brewing • 2 Bow Market Way, Somerville"},
                {"time": "7 PM D", "title": "Michelle Branch", "venue": "Roadrunner • 89 Guest St, Boston"},
                {"time": "7 PM D", "title": "half•alive", "venue": "The Sinclair • 52 Church St, Cambridge"},
                {"time": "7:30 PM", "title": "Rising Stars Comedy Showcase", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
                {"time": "8 PM", "title": "Karaoke Wednesdays", "venue": "Club Café • 209 Columbus Ave, Boston"},
            ]
        }
    ],
    "right_col": [
        {
            "day": "THURSDAY • NOV 5",
            "pill_bg": "#ffccd5",
            "pill_color": "#000000",
            "events": [
                {"time": "10 AM", "title": "Fleurs de Villes WONDER", "venue": "Prudential Center • 800 Boylston St, Boston"},
                {"time": "5 PM", "title": "ICA Free Thursday Night", "venue": "ICA Boston • 25 Harbor Shore Dr, Boston"},
                {"time": "5 PM", "title": "Connecting with Gratitude", "venue": "Gardner Museum • 25 Evans Way, Boston"},
                {"time": "7 PM D", "title": "Clara La San", "venue": "Roadrunner • 89 Guest St, Boston"},
                {"time": "7 PM", "title": "Winyah", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "7:30 PM", "title": "Brian Longwell & Friends", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
                {"time": "8 PM", "title": "Emancipator", "venue": "Crystal Ballroom • 55 Davis Sq, Somerville"},
                {"time": "9 PM", "title": "The People's Karaoke", "venue": "The Middle East • 480 Massachusetts Ave, Cambridge"},
                {"time": "9:30 PM", "title": "Free Game Night", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
            ]
        },
        {
            "day": "FRIDAY • NOV 6",
            "pill_bg": "#0047e1",
            "pill_color": "#ffffff",
            "events": [
                {"time": "10 AM", "title": "Fleurs de Villes WONDER", "venue": "Prudential Center • 800 Boylston St, Boston"},
                {"time": "11 AM", "title": "Allandale Woods Foliage Walk", "venue": "Allandale Woods • 7 VFW Pkwy, West Roxbury"},
                {"time": "11 AM", "title": "Snowport Holiday Market Opens", "venue": "100 Seaport Blvd, Boston"},
                {"time": "4 PM", "title": "Boston Antiquarian Book Fair", "venue": "Hynes Convention Center • 900 Boylston St, Boston"},
                {"time": "5 PM", "title": "SoWa First Friday", "venue": "SoWa Artists Guild • 450 Harrison Ave, Boston"},
                {"time": "6 PM", "title": "Colors of Rhythm: First Fridays", "venue": "ICA Boston • 25 Harbor Shore Dr, Boston"},
                {"time": "6 PM", "title": "Hovvdy", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "7 PM D", "title": "nimino", "venue": "Roadrunner • 89 Guest St, Boston"},
                {"time": "8 PM", "title": "Deerhoof", "venue": "Crystal Ballroom • 55 Davis Sq, Somerville"},
                {"time": "8 PM", "title": "MFA Late Nites", "venue": "Museum of Fine Arts • 465 Huntington Ave, Boston"},
                {"time": "10 PM", "title": "CamelPhat", "venue": "Royale • 279 Tremont St, Boston"},
            ]
        }
    ],
    "footer_badge": "SWIPE FOR THE WEEKEND ➔"
}

# -------------------------------------------------------------
# WEEKEND DATA (SLIDE 2: SAT - SUN + HIGHLIGHTS)
# -------------------------------------------------------------
SLIDE2_DATA = {
    "title_top": "BOSTON THIS WEEK",
    "title_box": "THE WEEKEND",
    "subtitle": "NOVEMBER 7TH–8TH, 2026 • 2/2",
    "left_col": [
        {
            "day": "SATURDAY • NOV 7",
            "pill_bg": "#0047e1",
            "pill_color": "#ffffff",
            "events": [
                {"time": "10 AM", "title": "Bow Market Renaissance Faire", "venue": "Bow Market • 1 Bow Market Way, Somerville"},
                {"time": "10 AM", "title": "Snowport Holiday Market", "venue": "100 Seaport Blvd, Boston"},
                {"time": "10 AM", "title": "Fleurs de Villes WONDER", "venue": "Prudential Center • 800 Boylston St, Boston"},
                {"time": "11 AM", "title": "Brighton Bazaar: Fall Finale", "venue": "Brighton Elks Lodge • 326 Washington St, Brighton"},
                {"time": "11 AM", "title": "Pumpkin Smash", "venue": "English High School lot • 144 McBride St, Jamaica Plain"},
                {"time": "11 AM", "title": "Harboring Creativity", "venue": "ICA Watershed • 256 Marginal St, East Boston"},
                {"time": "12 PM", "title": "Boston Veterans Parade", "venue": "Starts near Copley/BPL • 700 Boylston St, Boston"},
                {"time": "12 PM", "title": "Boston Antiquarian Book Fair", "venue": "Hynes Convention Center • 900 Boylston St, Boston"},
                {"time": "3 PM", "title": "Americana: Ruth & Ben String Band", "venue": "Remnant Satellite • 877 Cambridge St, Cambridge"},
                {"time": "4 PM", "title": "Loy Krathong Thai Night Market", "venue": "4 Brattle St, Harvard Square, Cambridge"},
                {"time": "6 PM D", "title": "Earlybirds Club", "venue": "The Sinclair • 52 Church St, Cambridge"},
                {"time": "6 PM", "title": "Fruit Bats", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "7:15 PM", "title": "Comedy Gold", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
                {"time": "8 PM", "title": "Now or Never: Powerhouse", "venue": "City Hall Plaza • 1 City Hall Square, Boston"},
                {"time": "8 PM", "title": "City of Four", "venue": "Remnant Satellite • 877 Cambridge St, Cambridge"},
                {"time": "9 PM D", "title": "One Year of Hyperlinked", "venue": "The Sinclair • 52 Church St, Cambridge"},
                {"time": "10 PM", "title": "MPH: Boston, Forever", "venue": "Royale • 279 Tremont St, Boston"},
            ]
        }
    ],
    "right_col": [
        {
            "day": "SUNDAY • NOV 8",
            "pill_bg": "#111827",
            "pill_color": "#ffffff",
            "events": [
                {"time": "10 AM", "title": "Fleurs de Villes WONDER", "venue": "Prudential Center • 800 Boylston St, Boston"},
                {"time": "11 AM", "title": "Brighton Bazaar: Fall Finale", "venue": "Brighton Elks Lodge • 326 Washington St, Brighton"},
                {"time": "11 AM", "title": "Boston Antiquarian Book Fair", "venue": "Hynes Convention Center • 900 Boylston St, Boston"},
                {"time": "11 AM", "title": "SoWa Open Market", "venue": "500 Harrison Ave, South End, Boston"},
                {"time": "11 AM", "title": "SoWa Sunday Open Studios", "venue": "450 Harrison Ave, South End, Boston"},
                {"time": "11 AM", "title": "Memorial Drive Recreation Sunday", "venue": "Memorial Dr • Western Ave to JFK St, Cambridge"},
                {"time": "11 AM", "title": "Fixit Clinic", "venue": "Artisan's Asylum • 96 Holton St, Allston"},
                {"time": "4 PM", "title": "Somerville Art Fair Auction Night", "venue": "Upstairs at Bow • 1 Bow Market Way, Somerville"},
                {"time": "6 PM", "title": "Sunday Best Comedy", "venue": "The Comedy Studio • 5 JFK St, Cambridge"},
                {"time": "7 PM", "title": "Voilà: Moonbloom", "venue": "Royale • 279 Tremont St, Boston"},
                {"time": "8 PM", "title": "Sunday Karaoke", "venue": "Remnant Satellite • 877 Cambridge St, Cambridge"},
            ]
        }
    ],
    "highlights": {
        "title": "WEEKEND HIGHLIGHTS",
        "items": [
            "RENAISSANCE FAIRE • SAT 10 AM",
            "THAI NIGHT MARKET • SAT 4–10 PM",
            "BRIGHTON BAZAAR • SAT & SUN 11 AM–5 PM",
        ],
        "note": "Bow Market opens 10 AM; Remnant activities from noon."
    },
    "footer_badge": "wickedbostonevents.com"
}


def build_slide_html(data):
    def render_col(col_data):
        html = []
        for d in col_data:
            pill_style = f"background: {d['pill_bg']}; color: {d['pill_color']};"
            html.append(f'<div class="day-group">')
            html.append(f'  <div class="day-pill" style="{pill_style}">{d["day"]}</div>')
            html.append(f'  <div class="events-list">')
            for ev in d["events"]:
                html.append(f'''    <div class="event-item">
      <div class="event-main">
        <span class="event-time">{ev["time"]}</span>
        <span class="event-dash">—</span>
        <span class="event-title">{ev["title"]}</span>
      </div>
      <div class="event-venue">{ev["venue"]}</div>
    </div>''')
            html.append(f'  </div>')
            html.append(f'</div>')
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
    position: relative;
  }}

  /* Top Banner */
  .top-banner {{
    background: #ff4338;
    height: 145px;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    padding-top: 6px;
  }}

  .circle-decor-1 {{
    position: absolute;
    width: 160px;
    height: 160px;
    border-radius: 50%;
    background: #0047e1;
    top: -40px;
    left: -40px;
  }}
  .circle-decor-2 {{
    position: absolute;
    width: 170px;
    height: 170px;
    border-radius: 50%;
    background: #ff7588;
    top: -50px;
    right: -40px;
  }}
  .circle-decor-3 {{
    position: absolute;
    width: 110px;
    height: 110px;
    border-radius: 50%;
    background: #0047e1;
    bottom: -35px;
    right: 45px;
  }}

  .star-white {{
    position: absolute;
    left: 80px;
    top: 36px;
    width: 68px;
    height: 68px;
  }}
  .star-blue {{
    position: absolute;
    right: 80px;
    top: 48px;
    width: 58px;
    height: 58px;
  }}

  .headline-top {{
    font-family: 'Montserrat', 'Plus Jakarta Sans', sans-serif;
    font-size: 52px;
    font-weight: 900;
    color: #000000;
    letter-spacing: -1px;
    line-height: 0.95;
    z-index: 2;
    text-transform: uppercase;
  }}

  .headline-box {{
    background: #ffffff;
    color: #000000;
    font-family: 'Montserrat', 'Plus Jakarta Sans', sans-serif;
    font-size: 42px;
    font-weight: 900;
    letter-spacing: -0.5px;
    line-height: 1;
    padding: 2px 24px 4px 24px;
    margin-top: 4px;
    z-index: 2;
    text-transform: uppercase;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }}

  .subtitle-pill {{
    font-size: 16px;
    font-weight: 800;
    color: #000000;
    margin-top: 6px;
    z-index: 2;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}

  /* Main Grid */
  .content-grid {{
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 22px;
    padding: 16px 22px 10px 22px;
    background: #ffffff;
  }}

  .col {{
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }}

  /* Day Group */
  .day-group {{
    display: flex;
    flex-direction: column;
    margin-bottom: 10px;
  }}
  .day-group:last-child {{
    margin-bottom: 0;
  }}

  .day-pill {{
    font-family: 'Montserrat', 'Plus Jakarta Sans', sans-serif;
    font-size: 20px;
    font-weight: 900;
    letter-spacing: 0.6px;
    padding: 5px 12px 6px 12px;
    border-radius: 4px;
    text-transform: uppercase;
    margin-bottom: 5px;
  }}

  .events-list {{
    display: flex;
    flex-direction: column;
  }}

  .event-item {{
    padding: 6px 2px 6.5px 2px;
    border-bottom: 1.5px solid #ffccd5;
    line-height: 1.2;
  }}
  .event-item:last-child {{
    border-bottom: none;
  }}

  .event-main {{
    font-size: 14px;
    font-weight: 800;
    color: #000000;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  .event-time {{
    font-weight: 900;
  }}
  .event-dash {{
    color: #64748b;
    margin: 0 4px;
  }}
  .event-title {{
    font-weight: 800;
    color: #000000;
  }}

  .event-venue {{
    font-size: 11.5px;
    font-weight: 600;
    color: #374151;
    margin-top: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Weekend Highlights Box */
  .highlights-box {{
    margin-top: 10px;
    border-radius: 6px;
    overflow: hidden;
    border: 2px solid #0047e1;
    display: flex;
    flex-direction: column;
  }}

  .hl-header {{
    background: #0047e1;
    color: #ffffff;
    font-family: 'Montserrat', sans-serif;
    font-size: 21px;
    font-weight: 900;
    padding: 7px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    letter-spacing: 0.5px;
  }}
  .hl-star {{
    width: 22px;
    height: 22px;
  }}

  .hl-list {{
    padding: 6px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: #ffffff;
  }}

  .hl-item {{
    background: #ffdbe2;
    color: #000000;
    font-family: 'Montserrat', sans-serif;
    font-weight: 900;
    font-size: 15.5px;
    padding: 6px 10px;
    border-radius: 4px;
    text-align: center;
    letter-spacing: 0.3px;
  }}

  .hl-note {{
    font-size: 11px;
    font-weight: 700;
    color: #111827;
    text-align: center;
    padding: 5px 6px 6px 6px;
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
  }}
  .blue-dot {{
    width: 7px;
    height: 7px;
    background: #0047e1;
    border-radius: 50%;
    display: inline-block;
  }}

  /* Footer */
  .footer {{
    height: 48px;
    background: #ffffff;
    border-top: 2px solid #ffccd5;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 16px 0 16px;
  }}

  .footer-brand {{
    display: flex;
    align-items: center;
    gap: 7px;
    font-family: 'Montserrat', sans-serif;
    font-size: 20px;
    font-weight: 900;
    color: #000000;
    letter-spacing: -0.3px;
  }}
  .ig-icon {{
    width: 22px;
    height: 22px;
  }}

  .footer-center {{
    font-size: 12px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: 0.2px;
  }}

  .footer-badge {{
    background: #0047e1;
    color: #ffffff;
    font-family: 'Montserrat', sans-serif;
    font-size: 15px;
    font-weight: 900;
    padding: 5px 14px 6px 14px;
    border-radius: 4px;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }}
</style>
</head>
<body>

  <!-- Top Banner -->
  <div class="top-banner">
    <div class="circle-decor-1"></div>
    <div class="circle-decor-2"></div>
    <div class="circle-decor-3"></div>

    <!-- Starburst SVGs -->
    <svg class="star-white" viewBox="0 0 100 100">
      <polygon fill="#ffffff" points="50,0 59,38 97,25 68,50 97,75 59,62 50,100 41,62 3,75 32,50 3,25 41,38"/>
    </svg>
    <svg class="star-blue" viewBox="0 0 100 100">
      <polygon fill="#0047e1" points="50,0 59,38 97,25 68,50 97,75 59,62 50,100 41,62 3,75 32,50 3,25 41,38"/>
    </svg>

    <div class="headline-top">{data["title_top"]}</div>
    <div class="headline-box">{data["title_box"]}</div>
    <div class="subtitle-pill">{data["subtitle"]}</div>
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


def render_screenshot(html_path, output_png):
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
    print("Generating Clean White-Background Weekly Event Flyers (1080x1350)...")

    # 1. Slide 1: Weekdays
    slide1_html_path = os.path.join(OUTPUT_DIR, "this_week_slide1.html")
    slide1_png_path = os.path.join(OUTPUT_DIR, "this_week_slide1.png")
    with open(slide1_html_path, "w", encoding="utf-8") as f:
        f.write(build_slide_html(SLIDE1_DATA))
    render_screenshot(slide1_html_path, slide1_png_path)

    # 2. Slide 2: Weekend
    slide2_html_path = os.path.join(OUTPUT_DIR, "this_week_slide2.html")
    slide2_png_path = os.path.join(OUTPUT_DIR, "this_week_slide2.png")
    with open(slide2_html_path, "w", encoding="utf-8") as f:
        f.write(build_slide_html(SLIDE2_DATA))
    render_screenshot(slide2_html_path, slide2_png_path)

    # Copy to artifact directory for easy display
    artifact_dir = "/Users/varunbehl/.gemini/antigravity/brain/97ecc9dc-b692-4686-9928-6e4e041247d4"
    if os.path.exists(artifact_dir):
        shutil.copy2(slide1_png_path, os.path.join(artifact_dir, "this_week_flyer_slide1.png"))
        shutil.copy2(slide2_png_path, os.path.join(artifact_dir, "this_week_flyer_slide2.png"))
        # Also copy slide 1 as default this_week_top_events_flyer.png
        shutil.copy2(slide1_png_path, os.path.join(artifact_dir, "this_week_top_events_flyer.png"))
        print(f"Copied flyer slides to artifact directory: {artifact_dir}")

    print("Successfully generated clean white-background weekly event flyers!")


if __name__ == "__main__":
    main()
