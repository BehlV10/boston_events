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


def generate_all_og_cards(base_dir, events, hubs):
    """Generate custom OG cards for all hubs and programmatic pages."""
    if not HAS_PIL:
        print("Note: PIL not available, skipping custom OG card rendering")
        return []

    from template import filter_events_for_hub

    mascot_candidates = [
        os.path.join(base_dir, "og-image.jpg"),
        os.path.join(base_dir, "banner.jpg"),
    ]
    mascot_path = next((p for p in mascot_candidates if os.path.exists(p)), None)

    generated = []
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
