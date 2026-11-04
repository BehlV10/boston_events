"""Render the site icon (dark rounded square, yellow border, blue "B") as real files.

Search engines ignore data: URI favicons, so Google showed a generic globe. This writes
favicon.ico (16/32/48), favicon.svg, apple-touch-icon.png (180) and logo-512.png at the
repo root. Run once on macOS (uses the Impact font): python3 scripts/make_icons.py
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG, BORDER, LETTER = "#0c0e14", "#ffd866", "#5d9bff"
FONTS = ["/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf"]
SVG = ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='16' fill='#0c0e14'/>"
       "<rect x='3' y='3' width='58' height='58' rx='13' fill='none' stroke='#ffd866' stroke-width='3'/>"
       "<text x='32' y='48' font-family='Impact, Arial Black, sans-serif' font-weight='900' font-size='44' "
       "fill='#5d9bff' text-anchor='middle'>B</text></svg>\n")


def render(size=1024, rounded=True):
    k = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=16 * k if rounded else 0, fill=BG)
    d.rounded_rectangle([1.5 * k, 1.5 * k, size - 1.5 * k, size - 1.5 * k], radius=14.5 * k, outline=BORDER, width=round(3 * k))
    font = ImageFont.truetype(next(f for f in FONTS if os.path.exists(f)), round(44 * k))
    d.text((32 * k, 48 * k), "B", font=font, fill=LETTER, anchor="ms")  # centered on the SVG baseline
    return img


big = render()
big.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "logo-512.png"))
# iOS rounds the corners itself and shows transparency as black, so use a square, opaque tile
render(rounded=False).resize((180, 180), Image.LANCZOS).save(os.path.join(ROOT, "apple-touch-icon.png"))
big.resize((48, 48), Image.LANCZOS).save(os.path.join(ROOT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
with open(os.path.join(ROOT, "favicon.svg"), "w") as f:
    f.write(SVG)
print("wrote favicon.ico, favicon.svg, apple-touch-icon.png, logo-512.png")
