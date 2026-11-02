#!/usr/bin/env python3
"""
Generate a high-contrast, zero-waste 1080x1350 Instagram / LinkedIn flyer
spotlighting top events across Greater Boston for THIS WEEK THROUGH SUNDAY
(Monday Nov 2 through Sunday Nov 8, 2026).
"""

import os
import sys
import json
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "instagram")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FLYER_HTML = os.path.join(OUTPUT_DIR, "this_week_flyer.html")
FLYER_PNG = os.path.join(OUTPUT_DIR, "this_week_flyer.png")
CAPTION_FILE = os.path.join(OUTPUT_DIR, "this_week_caption.txt")

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if not os.path.exists(CHROME_BIN):
    CHROME_BIN = "google-chrome"

# 7 Days of Top Curated Standouts (Nov 2 – Nov 8, 2026)
WEEK_DATA = [
    {
        "day_id": "mon",
        "day_label": "MON · NOV 2",
        "events": [
            {
                "time": "7:30 PM", "price": "FREE", "cat": "Classical", "accent": "#7aa2f7",
                "title": "First Monday at Jordan Hall",
                "venue": "NEC Jordan Hall · Back Bay"
            },
            {
                "time": "7:00 PM", "price": "$15", "cat": "35mm Film", "accent": "#e0af68",
                "title": "Inglourious Basterds (35mm)",
                "venue": "Somerville Theatre · Davis Sq"
            },
            {
                "time": "7:00 PM", "price": "$22", "cat": "Alt-Rock", "accent": "#ff708d",
                "title": "MICO: The Fantasy Tour",
                "venue": "Paradise Rock Club · Comm Ave"
            }
        ]
    },
    {
        "day_id": "tue",
        "day_label": "TUE · NOV 3",
        "events": [
            {
                "time": "7:00 PM", "price": "$38", "cat": "Indie Pop", "accent": "#bb9af7",
                "title": "Kate Nash (Live Concert)",
                "venue": "Arts at the Armory · Somerville"
            },
            {
                "time": "7:00 PM", "price": "$32", "cat": "Indie Pop", "accent": "#7aa2f7",
                "title": "half•alive (Night 1)",
                "venue": "The Sinclair · Harvard Sq"
            },
            {
                "time": "8:00 PM", "price": "$20", "cat": "Folk", "accent": "#9ece6a",
                "title": "Willi Carlisle",
                "venue": "Crystal Ballroom · Davis Sq"
            }
        ]
    },
    {
        "day_id": "wed",
        "day_label": "WED · NOV 4",
        "events": [
            {
                "time": "7:30 PM", "price": "$35", "cat": "Culinary", "accent": "#c678dd",
                "title": "Duff Goldman: Live Bakery Stories",
                "venue": "Crystal Ballroom · Davis Sq"
            },
            {
                "time": "7:30 PM", "price": "FREE", "cat": "Orchestral", "accent": "#7aa2f7",
                "title": "David Loebel & NEC Symphony",
                "venue": "Jordan Hall · Back Bay"
            },
            {
                "time": "7:00 PM", "price": "$18", "cat": "Grunge", "accent": "#ff708d",
                "title": "Pretty Sick: Tour 2026",
                "venue": "Brighton Music Hall · Allston"
            }
        ]
    },
    {
        "day_id": "thu",
        "day_label": "THU · NOV 5",
        "events": [
            {
                "time": "8:00 PM", "price": "$65+", "cat": "Hip-Hop", "accent": "#ff708d",
                "title": "CHIEF KEEF (Live Tour)",
                "venue": "MGM Music Hall · Fenway"
            },
            {
                "time": "7:00 PM", "price": "$35", "cat": "UK Alt-Rock", "accent": "#7aa2f7",
                "title": "Palace: USA & Canada Tour",
                "venue": "House of Blues · Fenway"
            },
            {
                "time": "7:30 PM", "price": "$49+", "cat": "Classic Pop", "accent": "#ffd866",
                "title": "Air Supply: Matter of Time",
                "venue": "Chevalier Theatre · Medford"
            }
        ]
    },
    {
        "day_id": "fri",
        "day_label": "FRI · NOV 6",
        "events": [
            {
                "time": "7:30 PM", "price": "$45+", "cat": "Comedy", "accent": "#f0a07a",
                "title": "Marc Maron: Yammering Tour",
                "venue": "Chevalier Theatre · Medford"
            },
            {
                "time": "9:30 PM", "price": "$40", "cat": "Bass / EDM", "accent": "#e06c75",
                "title": "Svdden Death (18+ Bass)",
                "venue": "Big Night Live · TD Garden"
            },
            {
                "time": "7:00 PM", "price": "$24", "cat": "Indie Surf", "accent": "#73daca",
                "title": "almost monday (Garage Pop)",
                "venue": "Paradise Rock Club · Comm Ave"
            },
            {
                "time": "7:00 PM", "price": "$28", "cat": "Irish Folk", "accent": "#9ece6a",
                "title": "Amble: Headline Tour",
                "venue": "House of Blues · Fenway"
            }
        ]
    },
    {
        "day_id": "sat",
        "day_label": "SAT · NOV 7",
        "events": [
            {
                "time": "7:30 PM", "price": "$45", "cat": "Funk / Soul", "accent": "#ffb8d1",
                "title": "Sammy Rae & The Friends",
                "venue": "MGM Music Hall · Fenway"
            },
            {
                "time": "12:00 PM", "price": "FREE", "cat": "Market", "accent": "#c678dd",
                "title": "Steal My Style Thrift Market",
                "venue": "Castle Island Brewing · Southie"
            },
            {
                "time": "7:00 PM", "price": "$22", "cat": "Indie Folk", "accent": "#ffd866",
                "title": "Porch Light: Hush Tour",
                "venue": "Brighton Music Hall · Allston"
            },
            {
                "time": "1:00 PM", "price": "FREE", "cat": "Faire", "accent": "#4fbf8f",
                "title": "Bow Market Renaissance Faire",
                "venue": "Remnant Brewing · Union Sq"
            }
        ]
    },
    {
        "day_id": "sun",
        "day_label": "SUN · NOV 8",
        "events": [
            {
                "time": "7:00 PM", "price": "$40+", "cat": "Comedy", "accent": "#f0a07a",
                "title": "Ben Schwartz & Friends (Improv)",
                "venue": "Chevalier Theatre · Medford"
            },
            {
                "time": "7:00 PM", "price": "$26", "cat": "UK Rock", "accent": "#ff708d",
                "title": "Boston Manor (Headline)",
                "venue": "The Sinclair · Harvard Sq"
            },
            {
                "time": "3:00 PM", "price": "$45+", "cat": "Piano Recital", "accent": "#7aa2f7",
                "title": "Igor Levit, Piano Master",
                "venue": "Boston Symphony Hall · Back Bay"
            },
            {
                "time": "3:00 PM", "price": "$25", "cat": "Symphony", "accent": "#7aa2f7",
                "title": "Boston Civic Symphony Opener",
                "venue": "NEC Jordan Hall · Back Bay"
            }
        ]
    }
]


def generate_html():
    col1_days = WEEK_DATA[:4]  # Mon, Tue, Wed, Thu (4 days)
    col2_days = WEEK_DATA[4:]  # Fri, Sat, Sun (3 weekend days)

    def render_col(days):
        html = []
        for d in days:
            html.append(f'<div class="day-group">')
            html.append(f'  <div class="day-header"><span class="day-pin">✦</span> {d["day_label"]}</div>')
            html.append(f'  <div class="events-list">')
            for ev in d["events"]:
                price_cls = "free" if ev["price"].upper() == "FREE" else ""
                html.append(f'''    <div class="event-card" style="--accent:{ev["accent"]}">
      <div class="card-top">
        <span class="card-time">{ev["time"]}</span>
        <span class="card-price {price_cls}">{ev["price"]}</span>
        <span class="card-cat">{ev["cat"]}</span>
      </div>
      <div class="card-title">{ev["title"]}</div>
      <div class="card-venue">{ev["venue"]}</div>
    </div>''')
            html.append(f'  </div>')
            html.append(f'</div>')
        return "\n".join(html)

    col1_html = render_col(col1_days)
    col2_html = render_col(col2_days)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800;900&family=JetBrains+Mono:wght@600;700;800&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1080px;
    height: 1350px;
    background: #090c12;
    color: #f1f5f9;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
    display: flex;
    flex-direction: column;
    padding: 24px 28px 20px 28px;
    position: relative;
    overflow: hidden;
  }}

  /* Background Glow Accents */
  .glow-top-left {{
    position: absolute;
    top: -120px;
    left: -100px;
    width: 500px;
    height: 500px;
    background: radial-gradient(circle, rgba(93, 155, 255, 0.18) 0%, rgba(93, 155, 255, 0) 70%);
    pointer-events: none;
  }}
  .glow-bottom-right {{
    position: absolute;
    bottom: -100px;
    right: -100px;
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.14) 0%, rgba(16, 185, 129, 0) 70%);
    pointer-events: none;
  }}

  /* Top Header */
  .header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: 14px;
    border-bottom: 1.5px solid #1e293b;
    margin-bottom: 14px;
    flex-shrink: 0;
  }}
  .brand-block {{
    display: flex;
    flex-direction: column;
    gap: 3px;
  }}
  .brand-logo {{
    font-size: 32px;
    font-weight: 900;
    letter-spacing: -0.8px;
    color: #ffffff;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .brand-logo span.accent {{
    color: #5d9bff;
  }}
  .brand-sub {{
    font-size: 13.5px;
    font-weight: 700;
    color: #94a3b8;
    letter-spacing: 0.4px;
    text-transform: uppercase;
  }}
  .header-badge {{
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 5px;
  }}
  .badge-dates {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 800;
    color: #38bdf8;
    background: rgba(56, 189, 248, 0.12);
    border: 1.5px solid rgba(56, 189, 248, 0.35);
    padding: 5px 14px;
    border-radius: 999px;
    letter-spacing: 0.5px;
  }}
  .badge-stat {{
    font-size: 12px;
    font-weight: 700;
    color: #34d399;
  }}

  /* Main Grid: 2 Columns */
  .grid-container {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    flex: 1;
    min-height: 0;
  }}

  .column {{
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}

  /* Day Section Group */
  .day-group {{
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}

  .day-header {{
    font-size: 13.5px;
    font-weight: 800;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    color: #60a5fa;
    display: flex;
    align-items: center;
    gap: 6px;
    padding-left: 2px;
  }}
  .day-pin {{
    color: #f59e0b;
    font-size: 12px;
  }}

  .events-list {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}

  /* Event Card */
  .event-card {{
    background: #0f1523;
    border: 1px solid #1e293b;
    border-left: 3.5px solid var(--accent, #5d9bff);
    border-radius: 8px;
    padding: 7px 10px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
  }}

  .card-top {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    font-weight: 700;
  }}
  .card-time {{
    font-family: 'JetBrains Mono', monospace;
    color: #94a3b8;
  }}
  .card-price {{
    color: #cbd5e1;
    background: #1e293b;
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 10px;
  }}
  .card-price.free {{
    color: #34d399;
    background: rgba(16, 185, 129, 0.16);
    border: 1px solid rgba(16, 185, 129, 0.3);
    font-weight: 800;
  }}
  .card-cat {{
    margin-left: auto;
    color: var(--accent, #94a3b8);
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.3px;
    text-transform: uppercase;
  }}

  .card-title {{
    font-size: 13.5px;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .card-venue {{
    font-size: 11.5px;
    font-weight: 600;
    color: #94a3b8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}

  /* Footer */
  .footer {{
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1.5px solid #1e293b;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
  }}
  .footer-url {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 15px;
    font-weight: 800;
    color: #5d9bff;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .footer-sub {{
    font-size: 12px;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 0.3px;
  }}
</style>
</head>
<body>
  <div class="glow-top-left"></div>
  <div class="glow-bottom-right"></div>

  <!-- Header -->
  <div class="header">
    <div class="brand-block">
      <div class="brand-logo">Wicked Boston <span class="accent">Events</span></div>
      <div class="brand-sub">The Definitive Live Radar for Greater Boston</div>
    </div>
    <div class="header-badge">
      <div class="badge-dates">WEEK OF NOV 2 – NOV 8</div>
      <div class="badge-stat">● 8,200+ Live Shows Monitored</div>
    </div>
  </div>

  <!-- 2-Column Grid -->
  <div class="grid-container">
    <div class="column">
      {col1_html}
    </div>
    <div class="column">
      {col2_html}
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    <div class="footer-url">
      <span>wickedbostonevents.com</span>
      <span style="color:#475569">·</span>
      <span style="color:#94a3b8; font-family:'Plus Jakarta Sans'">Free Event Radar</span>
    </div>
    <div class="footer-sub">Direct Official Ticket Links · Transit & MBTA Mapped · Updated Hourly</div>
  </div>
</body>
</html>
"""


def generate_caption():
    caption = (
        "🗓️ THIS WEEK IN BOSTON (NOV 2 – NOV 8, 2026) ⚡\n\n"
        "Looking for things to do across Boston, Cambridge & Somerville this week? "
        "Here are the top live concerts, comedy showcases, 35mm cult films, and free community gatherings happening through Sunday:\n\n"
        "✦ MONDAY NOV 2\n"
        "• First Monday @ NEC Jordan Hall (Free chamber masterworks)\n"
        "• Inglourious Basterds in 35mm @ Somerville Theatre (Davis Sq)\n"
        "• MICO: The Fantasy Tour @ Paradise Rock Club (Comm Ave)\n"
        "• The Fringe: 50-Yr Avant-Garde Jazz @ The Lilypad (Inman Sq)\n\n"
        "✦ TUESDAY NOV 3\n"
        "• Kate Nash @ Arts at the Armory (Somerville)\n"
        "• half•alive @ The Sinclair (Harvard Sq)\n"
        "• Willi Carlisle @ Crystal Ballroom (Davis Sq)\n"
        "• Sleeping With Sirens @ House of Blues (Fenway)\n\n"
        "✦ WEDNESDAY NOV 4\n"
        "• Duff Goldman: Live Bakery Stories @ Crystal Ballroom\n"
        "• David Loebel NEC Symphony @ Jordan Hall (Free)\n"
        "• Pretty Sick @ Brighton Music Hall (Allston)\n"
        "• The Getaway Driver @ Central Square Theater\n\n"
        "✦ THURSDAY NOV 5\n"
        "• CHIEF KEEF @ MGM Music Hall at Fenway\n"
        "• Palace (UK Alt-Rock) @ House of Blues\n"
        "• Air Supply @ Chevalier Theatre (Medford)\n"
        "• Joe Alterman Jazz Trio @ Regattabar (Harvard Sq)\n\n"
        "✦ FRIDAY NOV 6\n"
        "• Marc Maron: Yammering into the Void @ Chevalier Theatre\n"
        "• Svdden Death (18+ Bass) @ Big Night Live\n"
        "• almost monday @ Paradise Rock Club\n"
        "• Amble: Irish Folk Tour @ House of Blues\n\n"
        "✦ SATURDAY NOV 7\n"
        "• Sammy Rae & The Friends @ MGM Music Hall at Fenway\n"
        "• Steal My Style Thrift Market @ Castle Island Brewing (Free entry)\n"
        "• Porch Light: Hush Tour @ Brighton Music Hall\n"
        "• Bow Market Renaissance Faire @ Remnant Brewing (Union Sq)\n\n"
        "✦ SUNDAY NOV 8\n"
        "• Ben Schwartz & Friends (Improv) @ Chevalier Theatre\n"
        "• Boston Manor @ The Sinclair (Harvard Sq)\n"
        "• Igor Levit Piano Recital @ Boston Symphony Hall\n"
        "• Boston Civic Symphony Season Opener @ Jordan Hall\n\n"
        "🔗 Filter all 8,200+ live events by MBTA subway line, neighborhood & price at wickedbostonevents.com!\n\n"
        "#wickedbostonevents #bostonevents #boston #cambridgema #somervillema #bostonconcerts #bostonweekend #bostonguide #livemusicboston"
    )
    return caption


def main():
    print("Generating This Week (Nov 2 – Nov 8) Flyer...")
    html_content = generate_html()
    with open(FLYER_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

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
    print(f"Generated weekly flyer: {FLYER_PNG}")

    # Copy to brain artifact directory so it displays to the user
    artifact_dir = "/Users/varunbehl/.gemini/antigravity/brain/97ecc9dc-b692-4686-9928-6e4e041247d4"
    if os.path.exists(artifact_dir):
        artifact_path = os.path.join(artifact_dir, "this_week_top_events_flyer.png")
        shutil.copy2(FLYER_PNG, artifact_path)
        print(f"Copied flyer to artifact directory: {artifact_path}")

    caption = generate_caption()
    with open(CAPTION_FILE, "w", encoding="utf-8") as f:
        f.write(caption)
    print(f"Saved Instagram caption: {CAPTION_FILE} ({len(caption)} chars)")


if __name__ == "__main__":
    main()
