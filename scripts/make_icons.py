"""Render the site icon (dark rounded square, yellow border, blue "B") as real files.

Search engines ignore data: URI favicons, so Google showed a generic globe. This writes, at the
repo root: favicon.ico (16/32/48), favicon.svg, apple-touch-icon.png (180), logo-192.png,
logo-512.png and site.webmanifest.

The SVG draws the "B" as an outline taken from the Impact font rather than as text, so it looks
the same wherever it's rendered (Google's renderer and many phones don't have Impact).

Run on macOS (uses the Impact font; needs Pillow and fontTools): python3 scripts/make_icons.py
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG, BORDER, LETTER = "#0c0e14", "#ffd866", "#5d9bff"
FONTS = ["/System/Library/Fonts/Supplemental/Impact.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf"]
FONT = next(f for f in FONTS if os.path.exists(f))


def letter_path(char="B", size=44, cx=32, baseline=48):
    """The glyph's outline as an SVG path, sized and placed like <text x=cx y=baseline
    font-size=size text-anchor=middle>."""
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    glyphs = font.getGlyphSet()
    name = font.getBestCmap()[ord(char)]
    scale = size / font["head"].unitsPerEm
    left = cx - glyphs[name].width * scale / 2
    pen = SVGPathPen(glyphs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, left, baseline)))
    return pen.getCommands()


def svg():
    return ("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='16' fill='#0c0e14'/>"
            "<rect x='3' y='3' width='58' height='58' rx='13' fill='none' stroke='#ffd866' stroke-width='3'/>"
            f"<path fill='#5d9bff' d='{letter_path()}'/></svg>\n")


def render(size=1024, rounded=True):
    k = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=16 * k if rounded else 0, fill=BG)
    d.rounded_rectangle([1.5 * k, 1.5 * k, size - 1.5 * k, size - 1.5 * k], radius=14.5 * k, outline=BORDER, width=round(3 * k))
    font = ImageFont.truetype(FONT, round(44 * k))
    d.text((32 * k, 48 * k), "B", font=font, fill=LETTER, anchor="ms")  # centered on the SVG baseline
    return img


MANIFEST = {
    "name": "Wicked Boston Events",
    "short_name": "Wicked Boston",
    "start_url": "/",
    "display": "standalone",
    "background_color": BG,
    "theme_color": BG,
    "icons": [
        {"src": "/logo-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/logo-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
}

if __name__ == "__main__":
    big = render()
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "logo-512.png"))
    big.resize((192, 192), Image.LANCZOS).save(os.path.join(ROOT, "logo-192.png"))
    # iOS rounds the corners itself and shows transparency as black, so use a square, opaque tile
    render(rounded=False).resize((180, 180), Image.LANCZOS).save(os.path.join(ROOT, "apple-touch-icon.png"))
    big.resize((48, 48), Image.LANCZOS).save(os.path.join(ROOT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    with open(os.path.join(ROOT, "favicon.svg"), "w") as f:
        f.write(svg())
    with open(os.path.join(ROOT, "site.webmanifest"), "w") as f:
        json.dump(MANIFEST, f, indent=2)
        f.write("\n")
    print("wrote favicon.ico, favicon.svg, apple-touch-icon.png, logo-192.png, logo-512.png, site.webmanifest")
