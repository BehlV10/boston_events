"""Boston Events — Dynamic OpenGraph (OG) image generator.

Generates custom 1200x630 social preview cards for programmatic landing pages
and city hubs using Pillow. Unfurls crisply on iMessage, Slack, Discord, Twitter/X.
"""

import os
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _get_font(size, bold=False):
    """Attempt to load a crisp system TTF font with fallback to default."""
    if not HAS_PIL:
        return None
    font_paths = [
        # macOS
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFCompact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        # Linux / Ubuntu (GitHub Actions)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_single_card(output_path, badge_text, title, event_count, subtitle=None, mascot_path=None):
    """Render a modern 1200x630 OpenGraph card."""
    if not HAS_PIL:
        return False

    width, height = 1200, 630
    img = Image.new("RGB", (width, height), color="#0b0f17")
    draw = ImageDraw.Draw(img)

    # Gradient-like top accent bar
    colors = ["#10b981", "#06b6d4", "#6366f1", "#a855f7"]
    for i, col in enumerate(colors):
        draw.rectangle([(i * 300, 0), ((i + 1) * 300, 8)], fill=col)

    # Decorative background glow circles
    draw.ellipse([(900, -100), (1300, 300)], fill="#132338")
    draw.ellipse([(-100, 400), (300, 800)], fill="#111c2a")

    # Inner card frame
    draw.rounded_rectangle([(40, 36), (1160, 594)], radius=24, outline="#1e293b", width=2)

    # Mascot avatar if present
    if mascot_path and os.path.exists(mascot_path):
        try:
            mascot = Image.open(mascot_path).convert("RGBA")
            mascot = mascot.resize((140, 140))
            # Create circular mask
            mask = Image.new("L", (140, 140), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, 140, 140), fill=255)
            img.paste(mascot, (980, 70), mask)
            # Outline ring
            draw.ellipse([(978, 68), (1122, 212)], outline="#10b981", width=3)
        except Exception:
            pass

    font_badge = _get_font(20, bold=True)
    font_title = _get_font(50, bold=True)
    font_sub = _get_font(25, bold=False)
    font_footer = _get_font(19, bold=True)

    # Category Pill Badge
    pill_text = f"● {badge_text.upper()}"
    bbox = draw.textbbox((0, 0), pill_text, font=font_badge)
    tw = bbox[2] - bbox[0]
    draw.rounded_rectangle([(80, 76), (80 + tw + 28, 114)], radius=8, fill="#064e3b", outline="#10b981", width=1)
    draw.text((94, 82), pill_text, fill="#34d399", font=font_badge)

    # Live Event Count Badge
    if event_count and event_count > 0:
        cnt_text = f"{event_count:,} LIVE SHOWS"
        c_bbox = draw.textbbox((0, 0), cnt_text, font=font_badge)
        c_tw = c_bbox[2] - c_bbox[0]
        start_x = 80 + tw + 44
        draw.rounded_rectangle([(start_x, 76), (start_x + c_tw + 28, 114)], radius=8, fill="#1e293b")
        draw.text((start_x + 14, 82), cnt_text, fill="#94a3b8", font=font_badge)

    # Title with word-wrapping
    words = title.split(" ")
    lines = []
    cur = ""
    for w in words:
        cand = (cur + " " + w).strip()
        t_box = draw.textbbox((0, 0), cand, font=font_title)
        if (t_box[2] - t_box[0]) > 840:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)

    y = 150
    for line in lines[:2]:
        draw.text((80, y), line, fill="#ffffff", font=font_title)
        y += 66

    # Subtitle / description
    if subtitle:
        sub_words = subtitle.split(" ")
        sub_lines = []
        cur_sub = ""
        for w in sub_words:
            cand = (cur_sub + " " + w).strip()
            s_box = draw.textbbox((0, 0), cand, font=font_sub)
            if (s_box[2] - s_box[0]) > 880:
                if cur_sub:
                    sub_lines.append(cur_sub)
                cur_sub = w
            else:
                cur_sub = cand
        if cur_sub:
            sub_lines.append(cur_sub)
        y = max(y + 10, 305)
        for s_line in sub_lines[:2]:
            draw.text((80, y), s_line, fill="#94a3b8", font=font_sub)
            y += 36

    # Bottom Divider
    draw.line([(80, 500), (1120, 500)], fill="#1e293b", width=1)

    # Footer Branding
    draw.text((80, 530), "WICKED BOSTON EVENTS", fill="#f8fafc", font=font_footer)
    draw.text((360, 530), "·", fill="#64748b", font=font_footer)
    draw.text((385, 530), "OFFICIAL BOX OFFICE LINKS", fill="#10b981", font=font_footer)
    draw.text((690, 530), "·", fill="#64748b", font=font_footer)
    draw.text((715, 530), "ZERO TICKET BROKER FEES", fill="#94a3b8", font=font_footer)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=90, optimize=True)
    return True


def generate_crisp_main_card(output_path, total_events=8200):
    """Render a crisp, modern, human-designed 1200x630 product showcase OG card."""
    if not HAS_PIL:
        return False

    W, H = 1200, 630
    img = Image.new("RGB", (W, H), color="#090d16")
    draw = ImageDraw.Draw(img)

    # Decorative background glow
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for r in range(280, 0, -20):
        alpha = int(24 * (r / 280.0))
        glow_draw.ellipse([(-40 + 280 - r, -40 + 280 - r), (-40 + 280 + r, -40 + 280 + r)], fill=(35, 75, 155, alpha))
    for r in range(320, 0, -25):
        alpha = int(20 * (r / 320.0))
        glow_draw.ellipse([(1000 - r, 500 - r), (1000 + r, 500 + r)], fill=(16, 150, 130, alpha))
    img.paste(glow, (0, 0), glow)

    # Radar grid lines
    for gx in range(50, W, 70):
        draw.line([(gx, 0), (gx, H)], fill="#0f1626", width=1)
    for gy in range(40, H, 70):
        draw.line([(0, gy), (W, gy)], fill="#0f1626", width=1)

    # Top accent bar
    draw.rectangle([(0, 0), (280, 6)], fill="#3b82f6")
    draw.rectangle([(280, 0), (580, 6)], fill="#60a5fa")
    draw.rectangle([(580, 0), (880, 6)], fill="#10b981")
    draw.rectangle([(880, 0), (W, 6)], fill="#a855f7")

    font_brand_sm = _get_font(15, bold=True)
    font_tag_pill = _get_font(12, bold=True)
    font_hero_title = _get_font(52, bold=True)
    font_subhead = _get_font(20, bold=False)
    font_badge_bold = _get_font(19, bold=True)
    font_badge_sub = _get_font(14, bold=False)
    font_card_head = _get_font(13, bold=True)
    font_event_cat = _get_font(12, bold=True)
    font_event_time = _get_font(12, bold=False)
    font_event_title = _get_font(16, bold=True)
    font_event_venue = _get_font(13, bold=False)
    font_footer = _get_font(16, bold=True)

    # --- LEFT HERO COLUMN ---
    px, py = 70, 56
    draw.rounded_rectangle([(px, py), (px + 140, py + 32)], radius=16, fill="#063228", outline="#10b981", width=1)
    draw.ellipse([(px + 12, py + 11), (px + 22, py + 21)], fill="#10b981")
    draw.text((px + 28, py + 8), "LIVE RADAR", fill="#34d399", font=font_brand_sm)
    draw.text((px + 158, py + 8), "GREATER BOSTON GUIDE", fill="#64748b", font=font_brand_sm)

    draw.text((px, 114), "Wicked Boston", fill="#ffffff", font=font_hero_title)
    draw.text((px, 174), "Events", fill="#5d9bff", font=font_hero_title)
    draw.text((px, 246), "The definitive live event radar for Greater Boston.", fill="#94a3b8", font=font_subhead)

    count_str = f"{total_events:,}+" if total_events else "8,200+"
    badges = [
        (count_str, "LIVE EVENTS", "Music, Comedy, Nightlife, Arts & Theatre", "#f59e0b", "#1c140a", "#d97706"),
        ("100+", "MONITORED VENUES", "Fenway, Somerville, Cambridge & Downtown", "#38bdf8", "#0c1828", "#0284c7"),
        ("DIRECT", "OFFICIAL BOX OFFICE", "Zero ticket broker markups · Verified links", "#10b981", "#06261f", "#059669")
    ]
    by = 296
    for tag, b_title, desc, col, bg_col, border_col in badges:
        draw.rounded_rectangle([(px, by), (px + 450, by + 70)], radius=12, fill=bg_col, outline=border_col, width=1)
        draw.rounded_rectangle([(px + 16, by + 16), (px + 90, by + 40)], radius=6, fill=border_col)
        t_box = draw.textbbox((0, 0), tag, font=font_tag_pill)
        tw = t_box[2] - t_box[0]
        tx = (px + 16) + (74 - tw) // 2
        draw.text((tx, by + 21), tag, fill="#ffffff", font=font_tag_pill)
        draw.text((px + 104, by + 16), b_title, fill=col, font=font_badge_bold)
        draw.text((px + 104, by + 40), desc, fill="#94a3b8", font=font_badge_sub)
        by += 82

    draw.line([(px, 552), (px + 450, 552)], fill="#1e293b", width=1)
    draw.text((px, 572), "wickedbostonevents.com", fill="#60a5fa", font=font_footer)
    draw.text((px + 235, 572), "·", fill="#475569", font=font_footer)
    draw.text((px + 252, 572), "Updated Hourly · Transit-Mapped", fill="#94a3b8", font=font_badge_sub)

    # --- RIGHT PRODUCT MOCKUP ---
    mx, my, mw, mh = 566, 52, 564, 526
    draw.rounded_rectangle([(mx, my), (mx + mw, my + mh)], radius=18, fill="#0f1523", outline="#1e293b", width=2)

    # Mock Window Top Bar (Search & Category chips)
    draw.rounded_rectangle([(mx + 18, my + 16), (mx + mw - 18, my + 60)], radius=10, fill="#161e31", outline="#25334d", width=1)
    chips = [
        ("All Events", "#3b82f6", "#1d2e4d", True),
        ("Music", "#7aa2f7", "#161e31", False),
        ("Comedy", "#bb9af7", "#161e31", False),
        ("Arts", "#9ece6a", "#161e31", False),
        ("Map View", "#f0a07a", "#161e31", False)
    ]
    cx = mx + 28
    for label, col, bg, active in chips:
        pill_w = 90
        draw.rounded_rectangle([(cx, my + 24), (cx + pill_w, my + 52)], radius=6, fill=bg, outline=col if active else "#25334d", width=1)
        l_box = draw.textbbox((0, 0), label, font=font_card_head)
        lw = l_box[2] - l_box[0]
        lx = cx + (pill_w - lw) // 2
        draw.text((lx, my + 31), label, fill="#ffffff" if active else "#94a3b8", font=font_card_head)
        cx += pill_w + 10

    # 4 Event Cards Mock
    mock_events = [
        ("MUSIC", "#7aa2f7", "Tonight · 8:00 PM", "Khruangbin — A La Sala Tour", "MGM Music Hall at Fenway · Boston"),
        ("COMEDY", "#bb9af7", "Tomorrow · 7:30 PM", "Taylor Tomlinson: Live Standup", "The Wilbur Theatre · Boston"),
        ("INDIE / ROCK", "#7dcfff", "Friday · 8:30 PM", "Japanese Breakfast with Guests", "Roadrunner · Brighton / Boston"),
        ("STAGE & ARTS", "#f0a07a", "Saturday · 7:00 PM", "Boston Symphony Orchestra", "Symphony Hall · Back Bay")
    ]
    ey = my + 74
    for cat, accent_col, time_str, event_title, venue_str in mock_events:
        draw.rounded_rectangle([(mx + 18, ey), (mx + mw - 18, ey + 88)], radius=10, fill="#141a29", outline="#1e293b", width=1)
        draw.rounded_rectangle([(mx + 18, ey), (mx + 24, ey + 88)], radius=3, fill=accent_col)
        draw.text((mx + 38, ey + 12), cat, fill=accent_col, font=font_event_cat)
        t_box = draw.textbbox((0, 0), time_str, font=font_event_time)
        tw = t_box[2] - t_box[0]
        draw.text((mx + mw - 34 - tw, ey + 12), time_str, fill="#94a3b8", font=font_event_time)
        draw.text((mx + 38, ey + 34), event_title, fill="#f8fafc", font=font_event_title)
        draw.text((mx + 38, ey + 58), venue_str, fill="#64748b", font=font_event_venue)
        ey += 98

    draw.text((mx + 38, my + mh - 36), "● 100+ Live Boston Venues Monitored Hourly", fill="#10b981", font=font_tag_pill)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=92, optimize=True)
    return True


def generate_all_og_cards(base_dir, events, hubs):
    """Generate custom OG cards for all hubs and programmatic pages."""
    if not HAS_PIL:
        print("Note: PIL not available, skipping custom OG card rendering")
        return []

    from template import filter_events_for_hub

    generated = []

    # 1. Main site OpenGraph card
    main_og_path = os.path.join(base_dir, "og-image.jpg")
    try:
        if generate_crisp_main_card(main_og_path, total_events=len(events)):
            generated.append("og-image.jpg")
            print(f"Generated main OG card: og-image.jpg ({len(events):,} events)")
    except Exception as e:
        print(f"Warning: failed to generate main OG card: {e}")

    # 2. Programmatic Hub OG cards
    mascot_path = os.path.join(base_dir, "banner.jpg")
    if not os.path.exists(mascot_path):
        mascot_path = None

    for hub_slug, hub in hubs.items():
        og_filename = hub.get("og_image") or f"og-{hub_slug}.jpg"
        out_path = os.path.join(base_dir, og_filename)
        filtered = filter_events_for_hub(hub, events)
        badge = hub.get("og_badge") or hub.get("title", "Boston Events")
        title = hub.get("h1") or hub.get("title")
        subtitle = hub.get("subtitle")

        success = generate_single_card(
            output_path=out_path,
            badge_text=badge,
            title=title,
            event_count=len(filtered),
            subtitle=subtitle,
            mascot_path=mascot_path
        )
        if success:
            generated.append(og_filename)
            print(f"Generated dynamic OG card: {og_filename} ({len(filtered)} shows)")

    return generated
