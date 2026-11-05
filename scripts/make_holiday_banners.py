#!/usr/bin/env python3
"""Draw the holiday banners in static/holidays/<key>.svg.

Each holiday gets its own flat-vector scene built around a Boston place tied to the day:
Custom House at dawn (New Year's Day), BU's Marsh Chapel and the "Free at Last" doves (MLK Day),
the Chinatown Gate (Lunar New Year), the Old North Church over a North End café table
(Valentine's), the State House (Presidents' Day), Dorchester Heights (Evacuation Day), the
Boylston St finish line (Marathon Monday), the Garden of Flags on the Common (Memorial Day), the
African Meeting House (Juneteenth), the Hatch Shell fireworks (July 4), Castle Island (Labor
Day), the Blue Hills (Indigenous Peoples' Day), Faneuil Hall (Election Day), the Bunker Hill
Monument (Veterans Day), a cranberry bog harvest (Thanksgiving), Newbury Street (Black Friday),
MIT's Great Dome (Cyber Monday), a Back Bay window menorah (Hanukkah), the Common tree and Frog
Pond (Christmas) and Trinity Church at First Night (New Year's Eve).

Composition: the banner is a wide strip on desktop (shows roughly y 130–490 of the 600px-tall
art) and the full height but only the middle ~60% of the width on phones (x 320–1280). Main
subjects sit inside x 380–1220, y 130–480.

    python scripts/make_holiday_banners.py            # all
    python scripts/make_holiday_banners.py veterans   # one
"""

import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

W, H, HZ = 1600, 600, 400  # canvas and horizon line


# --------------------------------------------------------------------------------------------
# Drawing primitives
# --------------------------------------------------------------------------------------------

class Scene:
    def __init__(self, key):
        self.rng = random.Random(key)
        self.defs, self.body = [], []
        self._ids = 0

    def uid(self, p="g"):
        self._ids += 1
        return f"{p}{self._ids}"

    def add(self, *els):
        self.body.extend(e for e in els if e)

    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
                f'preserveAspectRatio="xMidYMid slice">\n<defs>\n' + "\n".join(self.defs) + "\n</defs>\n"
                + "\n".join(self.body) + "\n</svg>\n")

    # gradients -------------------------------------------------------------------------
    def vgrad(self, stops, x2=0, y2=1):
        gid = self.uid("lg")
        s = "".join(f'<stop offset="{o}" stop-color="{c}"' + (f' stop-opacity="{a}"' if a is not None else "") + "/>"
                    for o, c, a in [(t + (None,))[:3] for t in stops])
        self.defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>')
        return f"url(#{gid})"

    def rgrad(self, stops):
        gid = self.uid("rg")
        s = "".join(f'<stop offset="{o}" stop-color="{c}"' + (f' stop-opacity="{a}"' if a is not None else "") + "/>"
                    for o, c, a in [(t + (None,))[:3] for t in stops])
        self.defs.append(f'<radialGradient id="{gid}">{s}</radialGradient>')
        return f"url(#{gid})"

    # sky & light -------------------------------------------------------------------------
    def sky(self, top, mid, low, bottom=HZ):
        gid = self.uid("sky")
        self.defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="{bottom}">'
                         f'<stop offset="0" stop-color="{top}"/><stop offset="0.55" stop-color="{mid}"/>'
                         f'<stop offset="1" stop-color="{low}"/></linearGradient>')
        self.add(f'<rect width="{W}" height="{H}" fill="url(#{gid})"/>')

    def stars(self, n=80, ymax=300, opacity=1.0):
        r = self.rng
        self.add(*[f'<circle cx="{r.random() * W:.0f}" cy="{r.random() * ymax:.0f}" r="{0.6 + r.random() * 1.6:.1f}" '
                   f'fill="#fff" opacity="{(0.25 + r.random() * 0.65) * opacity:.2f}"/>' for _ in range(n)])

    def glow(self, cx, cy, r, color, a=0.5):
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{self.rgrad([(0, color, a), (1, color, 0)])}"/>')

    def sun(self, cx, cy, r, color, glow=None):
        self.glow(cx, cy, r * 3.2, glow or color, 0.45)
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')

    def moon(self, cx, cy, r, color="#fdf6d8", phase=0.55):
        mid = self.uid("m")
        self.defs.append(f'<mask id="{mid}"><rect width="{W}" height="{H}" fill="#fff"/>'
                         f'<circle cx="{cx + r * phase}" cy="{cy - r * 0.25}" r="{r}" fill="#000"/></mask>')
        self.glow(cx, cy, r * 2.6, color, 0.22)
        self.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" mask="url(#{mid})"/>')

    def clouds(self, items, color="#fff", opacity=0.8):
        for cx, cy, s in items:
            self.add(f'<g transform="translate({cx},{cy}) scale({s})" fill="{color}" opacity="{opacity}">'
                     f'<ellipse cx="0" cy="0" rx="60" ry="18"/><ellipse cx="-28" cy="-10" rx="26" ry="18"/>'
                     f'<ellipse cx="12" cy="-18" rx="32" ry="24"/><ellipse cx="44" cy="-6" rx="22" ry="14"/></g>')

    def rays(self, cx, cy, colors, n=22, opacity=0.12, spread=math.pi):
        for i in range(n):
            a0 = math.pi + spread * i / n + (math.pi - spread) / 2
            a1 = a0 + spread / n * 0.5
            self.add(f'<polygon points="{cx},{cy} {cx + math.cos(a0) * 1800:.0f},{cy + math.sin(a0) * 1800:.0f} '
                     f'{cx + math.cos(a1) * 1800:.0f},{cy + math.sin(a1) * 1800:.0f}" fill="{colors[i % len(colors)]}" opacity="{opacity}"/>')

    # ground & water ------------------------------------------------------------------------
    def ground(self, y, color, top_color=None):
        fill = self.vgrad([(0, top_color or color), (1, color)]) if top_color else color
        self.add(f'<rect x="0" y="{y}" width="{W}" height="{H - y}" fill="{fill}"/>')

    def water(self, y, top, bottom, glint="#ffffff", n=60, glint_opacity=0.35):
        self.add(f'<rect x="0" y="{y}" width="{W}" height="{H - y}" fill="{self.vgrad([(0, top), (1, bottom)])}"/>')
        r = self.rng
        for _ in range(n):
            gy = y + 6 + (r.random() ** 1.4) * (H - y - 10)
            w = 20 + r.random() * 140 * (0.4 + (gy - y) / (H - y))
            self.add(f'<rect x="{r.random() * W:.0f}" y="{gy:.0f}" width="{w:.0f}" height="2" rx="1" fill="{glint}" '
                     f'opacity="{0.08 + r.random() * glint_opacity:.2f}"/>')

    def hills(self, base, color, peaks, opacity=1.0):
        """peaks: [(x, height)], smooth ridge through them."""
        pts = [(-50, base)] + [(x, base - h) for x, h in peaks] + [(W + 50, base)]
        d = f"M{pts[0][0]},{pts[0][1]}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mx = (x0 + x1) / 2
            d += f" C{mx:.0f},{y0:.0f} {mx:.0f},{y1:.0f} {x1:.0f},{y1:.0f}"
        d += f" L{W + 50},{H} L-50,{H} Z"
        self.add(f'<path d="{d}" fill="{color}" opacity="{opacity}"/>')

    # city ------------------------------------------------------------------------------------
    def skyline(self, color, y=HZ, x0=0, x1=W, hmin=40, hmax=150, window=None, towers=True, opacity=1.0):
        """Generic downtown silhouette, optionally with the Pru and Hancock."""
        r = self.rng
        out = [f'<g opacity="{opacity}">']
        x = x0
        while x < x1:
            w = 40 + r.random() * 70
            h = hmin + r.random() * (hmax - hmin)
            out.append(f'<rect x="{x:.0f}" y="{y - h:.0f}" width="{w + 1:.0f}" height="{h:.0f}" fill="{color}"/>')
            if window:
                for _ in range(int(w * h / 1100)):
                    out.append(f'<rect x="{x + 5 + r.random() * (w - 12):.0f}" y="{y - h + 6 + r.random() * (h - 14):.0f}" '
                               f'width="3" height="5" fill="{window}" opacity="{0.3 + r.random() * 0.6:.2f}"/>')
            x += w
        if towers:
            hx, px = x0 + (x1 - x0) * 0.35, x0 + (x1 - x0) * 0.62
            out.append(f'<polygon points="{hx},{y} {hx},{y - hmax - 110} {hx + 22},{y - hmax - 122} {hx + 44},{y - hmax - 110} {hx + 44},{y}" fill="{color}"/>')
            out.append(f'<rect x="{px}" y="{y - hmax - 100}" width="48" height="{hmax + 100}" fill="{color}"/>'
                       f'<rect x="{px + 10}" y="{y - hmax - 112}" width="28" height="14" fill="{color}"/>'
                       f'<rect x="{px + 22}" y="{y - hmax - 146}" width="3" height="36" fill="{color}"/>')
        out.append("</g>")
        self.add("".join(out))

    def windows_grid(self, x, y, w, h, cols, rows, color, lit=None, ww=None, wh=None, arch=False):
        r = self.rng
        ww = ww or w / cols * 0.5
        wh = wh or h / rows * 0.55
        out = []
        for c in range(cols):
            for rr in range(rows):
                cx = x + (c + 0.5) * w / cols - ww / 2
                cy = y + (rr + 0.5) * h / rows - wh / 2
                fill = color if (lit is None or r.random() < lit) else "#1a1a24"
                if arch:
                    out.append(f'<path d="M{cx:.1f},{cy + wh:.1f} L{cx:.1f},{cy + ww / 2:.1f} A{ww / 2:.1f},{ww / 2:.1f} 0 0 1 {cx + ww:.1f},{cy + ww / 2:.1f} L{cx + ww:.1f},{cy + wh:.1f} Z" fill="{fill}"/>')
                else:
                    out.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{ww:.1f}" height="{wh:.1f}" fill="{fill}"/>')
        self.add("".join(out))

    def rowhouses(self, x0, x1, base, colors, h=(110, 170), window="#ffd98a", lit=0.7, trim="#f3ead8", flat=True, stoop=True):
        r = self.rng
        x = x0
        while x < x1:
            w = 70 + r.random() * 40
            hh = h[0] + r.random() * (h[1] - h[0])
            c = r.choice(colors)
            self.add(f'<rect x="{x:.0f}" y="{base - hh:.0f}" width="{w + 1:.0f}" height="{hh:.0f}" fill="{c}"/>')
            if flat:
                self.add(f'<rect x="{x - 2:.0f}" y="{base - hh - 6:.0f}" width="{w + 4:.0f}" height="8" fill="{trim}" opacity="0.85"/>')
            else:
                self.add(f'<polygon points="{x - 3:.0f},{base - hh:.0f} {x + w / 2:.0f},{base - hh - 30:.0f} {x + w + 3:.0f},{base - hh:.0f}" fill="{trim}"/>')
            floors = max(2, int(hh // 42))
            self.windows_grid(x + 8, base - hh + 10, w - 16, hh - 40, 2, floors, window, lit=lit)
            if stoop:
                self.add(f'<rect x="{x + w / 2 - 9:.0f}" y="{base - 30:.0f}" width="18" height="30" fill="#2a1a12"/>'
                         f'<rect x="{x + w / 2 - 16:.0f}" y="{base - 6:.0f}" width="32" height="6" fill="{trim}" opacity="0.6"/>')
            x += w + 2

    def triple_deckers(self, x0, x1, base, colors, window="#fff6d8"):
        r = self.rng
        x = x0
        while x < x1:
            w = 86 + r.random() * 16
            hh = 150
            c = r.choice(colors)
            self.add(f'<rect x="{x:.0f}" y="{base - hh:.0f}" width="{w:.0f}" height="{hh:.0f}" fill="{c}"/>'
                     f'<polygon points="{x - 6:.0f},{base - hh:.0f} {x + w / 2:.0f},{base - hh - 34:.0f} {x + w + 6:.0f},{base - hh:.0f}" fill="#4a4a5a"/>')
            for f in range(3):  # stacked porches
                py = base - hh + f * 50 + 34
                self.add(f'<rect x="{x + 4:.0f}" y="{py:.0f}" width="{w * 0.42:.0f}" height="4" fill="#fff"/>'
                         f'<rect x="{x + 4:.0f}" y="{py - 30:.0f}" width="3" height="30" fill="#fff"/>'
                         f'<rect x="{x + w * 0.42:.0f}" y="{py - 30:.0f}" width="3" height="30" fill="#fff"/>')
            self.windows_grid(x + w * 0.5, base - hh + 8, w * 0.46, hh - 14, 1, 3, window)
            x += w + 26

    # nature --------------------------------------------------------------------------------
    def tree(self, x, y, s, color, trunk="#3b2a1f"):
        self.add(f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})">'
                 f'<rect x="-4" y="-40" width="8" height="40" fill="{trunk}"/>'
                 f'<circle cx="0" cy="-62" r="30" fill="{color}"/><circle cx="-22" cy="-48" r="20" fill="{color}"/>'
                 f'<circle cx="22" cy="-48" r="20" fill="{color}"/></g>')

    def pine(self, x, y, h, color, snow=None):
        w = h * 0.45
        out = [f'<g><rect x="{x - 4:.0f}" y="{y - 10:.0f}" width="8" height="10" fill="#3b2a1f"/>']
        for i in range(3):
            ty = y - 10 - i * h * 0.26
            tw = w * (1 - i * 0.24)
            out.append(f'<polygon points="{x - tw:.0f},{ty:.0f} {x:.0f},{ty - h * 0.42:.0f} {x + tw:.0f},{ty:.0f}" fill="{color}"/>')
            if snow:
                out.append(f'<polygon points="{x - tw * 0.35:.0f},{ty - h * 0.27:.0f} {x:.0f},{ty - h * 0.42:.0f} {x + tw * 0.35:.0f},{ty - h * 0.27:.0f}" fill="{snow}"/>')
        out.append("</g>")
        self.add("".join(out))

    def bare_tree(self, x, y, h, color, depth=5, width=6):
        r = self.rng
        out = []

        def branch(x0, y0, ang, length, w, d):
            x1 = x0 + math.cos(ang) * length
            y1 = y0 + math.sin(ang) * length
            out.append(f'<line x1="{x0:.0f}" y1="{y0:.0f}" x2="{x1:.0f}" y2="{y1:.0f}" stroke="{color}" stroke-width="{w:.1f}" stroke-linecap="round"/>')
            if d > 0:
                for da in (-0.45 - r.random() * 0.2, 0.4 + r.random() * 0.25):
                    branch(x1, y1, ang + da, length * (0.68 + r.random() * 0.12), w * 0.66, d - 1)
            return x1, y1

        branch(x, y, -math.pi / 2, h * 0.38, width, depth)
        self.add("".join(out))
        return out

    # people & things ------------------------------------------------------------------------
    def person(self, x, y, s, color, arms="down", hat=None):
        arm = {"down": "M-9,-38 L-13,-16 M9,-38 L13,-16", "up": "M-9,-40 L-18,-62 M9,-40 L18,-62",
               "wave": "M-9,-38 L-13,-16 M9,-40 L20,-60", "run": "M-9,-38 L-20,-26 M9,-40 L18,-52"}[arms]
        legs = "M-5,-18 L-14,0 M5,-18 L16,-2" if arms == "run" else "M-5,-18 L-6,0 M5,-18 L6,0"
        out = (f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})" fill="{color}" stroke="{color}" stroke-linecap="round">'
               f'<circle cx="0" cy="-54" r="8" stroke="none"/><path d="M-10,-44 Q0,-48 10,-44 L8,-16 L-8,-16 Z" stroke="none"/>'
               f'<path d="{arm} {legs}" stroke-width="5" fill="none"/>')
        if hat:
            out += hat
        self.add(out + "</g>")

    def crowd(self, x0, x1, y, s, colors, arms=("down", "wave", "down", "up")):
        r = self.rng
        x = x0
        while x < x1:
            self.person(x, y + r.random() * 6, s * (0.85 + r.random() * 0.3), r.choice(colors), r.choice(arms))
            x += 18 * s + r.random() * 14 * s

    def bunting(self, x0, y0, x1, y1, sag, colors, size=16):
        n = max(3, int(abs(x1 - x0) / (size * 1.6)))
        out = [f'<path d="M{x0},{y0} Q{(x0 + x1) / 2},{(y0 + y1) / 2 + sag * 2} {x1},{y1}" stroke="#ddd" stroke-width="1.5" fill="none" opacity="0.8"/>']
        for i in range(n):
            t = (i + 0.5) / n
            px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * (x0 + x1) / 2 + t * t * x1
            py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * ((y0 + y1) / 2 + sag * 2) + t * t * y1
            out.append(f'<polygon points="{px - size / 2:.0f},{py:.0f} {px + size / 2:.0f},{py:.0f} {px:.0f},{py + size * 1.2:.0f}" fill="{colors[i % len(colors)]}"/>')
        self.add("".join(out))

    def string_lights(self, x0, y0, x1, y1, sag, colors, n=None, r=4):
        n = n or max(4, int(abs(x1 - x0) / 34))
        out = [f'<path d="M{x0},{y0} Q{(x0 + x1) / 2},{(y0 + y1) / 2 + sag * 2} {x1},{y1}" stroke="#2b2b2b" stroke-width="1.5" fill="none"/>']
        for i in range(n):
            t = (i + 0.5) / n
            px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * (x0 + x1) / 2 + t * t * x1
            py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * ((y0 + y1) / 2 + sag * 2) + t * t * y1
            c = colors[i % len(colors)]
            out.append(f'<circle cx="{px:.0f}" cy="{py + 4:.0f}" r="{r * 3}" fill="{c}" opacity="0.18"/>'
                       f'<circle cx="{px:.0f}" cy="{py + 4:.0f}" r="{r}" fill="{c}"/>')
        self.add("".join(out))

    def bunting_fan(self, cx, cy, r):
        """Half-round red/white/blue patriotic bunting."""
        self.add(f'<path d="M{cx - r},{cy} A{r},{r} 0 0 0 {cx + r},{cy} Z" fill="#b22234"/>'
                 f'<path d="M{cx - r * 0.72},{cy} A{r * 0.72},{r * 0.72} 0 0 0 {cx + r * 0.72},{cy} Z" fill="#f5f5f5"/>'
                 f'<path d="M{cx - r * 0.44},{cy} A{r * 0.44},{r * 0.44} 0 0 0 {cx + r * 0.44},{cy} Z" fill="#3c3b6e"/>'
                 + "".join(star(cx + math.cos(math.pi * (0.2 + 0.3 * i)) * r * 0.24, cy + math.sin(math.pi * (0.2 + 0.3 * i)) * r * 0.24, r * 0.06, "#fff") for i in range(3)))

    def flag_us(self, px, ptop, fw=170, fh=100, pole_h=None, amp=8):
        pole_h = pole_h or 260
        out = [f'<rect x="{px}" y="{ptop}" width="5" height="{pole_h}" fill="#d9d9d9"/>'
               f'<circle cx="{px + 2.5}" cy="{ptop - 4}" r="6" fill="#d4af37"/>']
        sh = fh / 13

        def wave(x):
            return amp * math.sin((x / fw) * 2.2 * math.pi)

        for i in range(13):
            y0 = ptop + 5 + i * sh
            top = " ".join(f"{px + 5 + x:.0f},{y0 + wave(x):.1f}" for x in range(0, fw + 1, 10))
            bot = " ".join(f"{px + 5 + x:.0f},{y0 + sh + wave(x):.1f}" for x in range(fw, -1, -10))
            out.append(f'<polygon points="{top} {bot}" fill="{"#b22234" if i % 2 == 0 else "#f5f5f5"}"/>')
        cw, ch = fw * 0.42, sh * 7
        top = " ".join(f"{px + 5 + x:.0f},{ptop + 5 + wave(x):.1f}" for x in range(0, int(cw) + 1, 6))
        bot = " ".join(f"{px + 5 + x:.0f},{ptop + 5 + ch + wave(x):.1f}" for x in range(int(cw), -1, -6))
        out.append(f'<polygon points="{top} {bot}" fill="#3c3b6e"/>')
        for rr in range(5):
            for c in range(6):
                x = 7 + c * (cw - 10) / 5.5
                out.append(star(px + 5 + x, ptop + 5 + 6 + rr * (ch - 10) / 4.6 + wave(x), fh * 0.025, "#fff"))
        self.add("".join(out))

    def mini_flag(self, x, y, s):
        """Small US flag on a stick, for the Garden of Flags."""
        return (f'<g transform="translate({x:.1f},{y:.1f}) scale({s:.3f})">'
                f'<rect x="0" y="-60" width="2.4" height="60" fill="#c9c9c9"/>'
                + "".join(f'<rect x="2.4" y="{-60 + i * 3.2:.1f}" width="34" height="3.3" fill="{"#b22234" if i % 2 == 0 else "#f5f5f5"}"/>' for i in range(7))
                + '<rect x="2.4" y="-60" width="15" height="12.8" fill="#3c3b6e"/></g>')

    def confetti(self, n, colors, ymin=0, ymax=H, xmin=0, xmax=W, size=(4, 10)):
        r = self.rng
        out = []
        for _ in range(n):
            x, y = xmin + r.random() * (xmax - xmin), ymin + r.random() * (ymax - ymin)
            w = size[0] + r.random() * (size[1] - size[0])
            out.append(f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{w * 1.8:.0f}" fill="{r.choice(colors)}" '
                       f'opacity="{0.55 + r.random() * 0.45:.2f}" transform="rotate({r.random() * 180:.0f} {x:.0f} {y:.0f})"/>')
        self.add("".join(out))

    def snow(self, n, ymax=H, opacity=1.0):
        r = self.rng
        self.add(*[f'<circle cx="{r.random() * W:.0f}" cy="{r.random() * ymax:.0f}" r="{0.8 + r.random() * 3:.1f}" fill="#fff" '
                   f'opacity="{(0.35 + r.random() * 0.55) * opacity:.2f}"/>' for _ in range(n)])

    def firework(self, cx, cy, rad, color, rays=20, dots=True, opacity=1.0, glow=True):
        out = [f'<g opacity="{opacity:.2f}">']
        if glow:
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{rad * 1.2:.0f}" fill="{color}" opacity="0.10"/>')
        for i in range(rays):
            a = 2 * math.pi * i / rays + 0.1
            x1, y1 = cx + math.cos(a) * rad * 0.22, cy + math.sin(a) * rad * 0.22
            x2, y2 = cx + math.cos(a) * rad, cy + math.sin(a) * rad + rad * 0.06
            out.append(f'<path d="M{x1:.0f},{y1:.0f} Q{(x1 + x2) / 2:.0f},{(y1 + y2) / 2 - 4:.0f} {x2:.0f},{y2:.0f}" stroke="{color}" stroke-width="2.4" stroke-linecap="round" fill="none"/>')
            if dots:
                out.append(f'<circle cx="{x2:.0f}" cy="{y2 + 6:.0f}" r="2.4" fill="{color}"/>')
        out.append(f'<circle cx="{cx}" cy="{cy}" r="{max(3, rad * 0.08):.0f}" fill="#fff" opacity="0.9"/></g>')
        self.add("".join(out))

    def lamp_post(self, x, base, h=120, color="#1b1b22", light="#ffd27a"):
        self.glow(x, base - h + 6, 46, light, 0.45)
        self.add(f'<rect x="{x - 3}" y="{base - h + 14}" width="6" height="{h - 14}" fill="{color}"/>'
                 f'<rect x="{x - 9}" y="{base - 8}" width="18" height="8" fill="{color}"/>'
                 f'<polygon points="{x - 11},{base - h + 14} {x + 11},{base - h + 14} {x + 7},{base - h - 6} {x - 7},{base - h - 6}" fill="{light}" stroke="{color}" stroke-width="3"/>'
                 f'<polygon points="{x - 13},{base - h - 6} {x + 13},{base - h - 6} {x},{base - h - 18}" fill="{color}"/>')


def star(cx, cy, r, color, opacity=1.0, rot=0):
    pts = []
    for i in range(10):
        rad = r if i % 2 == 0 else r * 0.42
        a = math.radians(rot - 90 + i * 36)
        pts.append(f"{cx + rad * math.cos(a):.1f},{cy + rad * math.sin(a):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{color}" opacity="{opacity:.2f}"/>'


def heart(cx, cy, s, color, opacity=1.0):
    return (f'<path transform="translate({cx:.0f},{cy:.0f}) scale({s:.2f})" opacity="{opacity:.2f}" fill="{color}" '
            f'd="M0,8 C-14,-6 -22,-18 -12,-26 C-6,-31 0,-27 0,-21 C0,-27 6,-31 12,-26 C22,-18 14,-6 0,8 Z"/>')


def shamrock(cx, cy, s, color, opacity=1.0, rot=0):
    return (f'<g transform="translate({cx:.0f},{cy:.0f}) rotate({rot:.0f}) scale({s:.2f})" fill="{color}" opacity="{opacity:.2f}">'
            + "".join(f'<path d="M0,0 C-14,-8 -14,-24 -4,-24 C0,-24 0,-20 0,-18 C0,-20 0,-24 4,-24 C14,-24 14,-8 0,0 Z" transform="rotate({a})"/>' for a in (0, 120, 240))
            + '<path d="M0,0 Q6,12 4,22" stroke="' + color + '" stroke-width="3" fill="none"/></g>')


def dove(x, y, s, color="#ffffff", opacity=1.0, flip=False):
    sx = -s if flip else s
    return (f'<path transform="translate({x:.0f},{y:.0f}) scale({sx:.2f},{s:.2f})" fill="{color}" opacity="{opacity:.2f}" '
            f'd="M-22,4 C-14,2 -6,4 0,2 C4,-10 10,-26 26,-34 C20,-22 18,-12 16,-4 C22,-6 28,-4 32,0 C26,2 20,4 14,8 '
            f'C8,12 -2,12 -8,10 L-20,16 L-16,8 Z"/>')


def leaf(cx, cy, s, color, rot=0, opacity=1.0):
    return (f'<path transform="translate({cx:.0f},{cy:.0f}) rotate({rot:.0f}) scale({s:.2f})" fill="{color}" opacity="{opacity:.2f}" '
            f'd="M0,-22 C8,-14 16,-12 14,-2 C20,2 16,10 8,8 C8,16 2,20 0,24 C-2,20 -8,16 -8,8 C-16,10 -20,2 -14,-2 C-16,-12 -8,-14 0,-22 Z"/>')


def poppy(cx, cy, s):
    return (f'<g transform="translate({cx:.0f},{cy:.0f}) scale({s:.2f})">'
            f'<path d="M0,10 Q4,45 -2,90" stroke="#1f3d1f" stroke-width="3" fill="none"/>'
            + "".join(f'<ellipse cx="0" cy="-12" rx="13" ry="15" fill="#c8102e" transform="rotate({a})"/>' for a in (0, 90, 180, 270))
            + '<ellipse cx="0" cy="-12" rx="9" ry="10" fill="#e0263f" transform="rotate(45)" opacity="0.6"/>'
            + '<circle cx="0" cy="0" r="7" fill="#111"/></g>')


def lantern(cx, cy, s, red="#d62828", gold="#f5c542", string=60):
    return (f'<g transform="translate({cx:.0f},{cy:.0f}) scale({s:.2f})">'
            f'<line x1="0" y1="{-26 - string}" x2="0" y2="-26" stroke="{gold}" stroke-width="2"/>'
            f'<circle cx="0" cy="0" r="58" fill="{red}" opacity="0.12"/>'
            f'<rect x="-15" y="-30" width="30" height="7" rx="2" fill="{gold}"/>'
            f'<ellipse cx="0" cy="0" rx="32" ry="27" fill="{red}"/>'
            f'<ellipse cx="0" cy="0" rx="20" ry="27" fill="none" stroke="{gold}" stroke-width="1.4" opacity="0.7"/>'
            f'<ellipse cx="0" cy="0" rx="8" ry="27" fill="none" stroke="{gold}" stroke-width="1.4" opacity="0.7"/>'
            f'<rect x="-15" y="23" width="30" height="7" rx="2" fill="{gold}"/>'
            + "".join(f'<line x1="{dx}" y1="30" x2="{dx}" y2="{52 + abs(dx) * -0.4:.0f}" stroke="{gold}" stroke-width="2"/>' for dx in (-8, -3, 3, 8))
            + "</g>")


# --------------------------------------------------------------------------------------------
# Scenes
# --------------------------------------------------------------------------------------------

def scene_newyear(s):
    """New Year's Day: sunrise over the harbor, Custom House clock at 12, streamers left from last night."""
    s.sky("#2b3a78", "#e8857a", "#ffd59a")
    s.sun(800, 395, 70, "#ffe2a6", "#ffb36b")
    s.clouds([(330, 150, 1.1), (1250, 120, 1.3), (980, 210, 0.8)], "#ffc9a8", 0.55)
    s.skyline("#6a4a78", hmin=30, hmax=110, opacity=0.55, towers=True)
    # Custom House Tower
    c, base = 800, HZ
    col = "#4b3358"
    s.add(f'<rect x="{c - 160}" y="{base - 70}" width="320" height="70" fill="{col}"/>'
          + "".join(f'<rect x="{c - 150 + i * 24}" y="{base - 64}" width="10" height="58" fill="#6d5280"/>' for i in range(13))
          + f'<polygon points="{c - 168},{base - 70} {c},{base - 96} {c + 168},{base - 70}" fill="{col}"/>'
          f'<rect x="{c - 42}" y="{base - 300}" width="84" height="210" fill="{col}"/>'
          + "".join(f'<rect x="{c - 30 + i * 22}" y="{base - 280}" width="8" height="170" fill="#6d5280" opacity="0.7"/>' for i in range(3))
          + f'<rect x="{c - 52}" y="{base - 330}" width="104" height="32" fill="{col}"/>'
          + "".join(f'<rect x="{c - 46 + i * 15}" y="{base - 326}" width="5" height="24" fill="#ffd59a" opacity="0.7"/>' for i in range(7))
          + f'<polygon points="{c - 48},{base - 330} {c},{base - 380} {c + 48},{base - 330}" fill="{col}"/>'
          f'<rect x="{c - 1.5}" y="{base - 400}" width="3" height="24" fill="{col}"/>')
    # clock showing midnight
    s.add(f'<circle cx="{c}" cy="{base - 252}" r="26" fill="#fff4dc" stroke="#d4af37" stroke-width="4"/>'
          f'<line x1="{c}" y1="{base - 252}" x2="{c}" y2="{base - 274}" stroke="#2b1d33" stroke-width="3.5" stroke-linecap="round"/>'
          f'<line x1="{c}" y1="{base - 252}" x2="{c}" y2="{base - 268}" stroke="#2b1d33" stroke-width="5" stroke-linecap="round"/>'
          f'<circle cx="{c}" cy="{base - 252}" r="3" fill="#2b1d33"/>')
    s.water(HZ, "#f2a37f", "#3a2f6a", "#fff1c9", 70, 0.5)
    s.add(f'<rect x="{800 - 60}" y="{HZ + 4}" width="120" height="180" fill="{s.vgrad([(0, "#ffe2a6", 0.7), (1, "#ffe2a6", 0)])}"/>')
    # harbor ferry
    s.add(f'<g transform="translate(1120,445)" fill="#2b1d33"><path d="M-70,0 L70,0 L58,16 L-62,16 Z"/><rect x="-46" y="-18" width="84" height="18"/>'
          f'<rect x="-30" y="-30" width="44" height="12"/></g>')
    # streamers from the top and confetti
    for x0, col2 in ((40, "#f5c542"), (160, "#f472b6"), (1440, "#a78bfa"), (1560, "#f5c542"), (300, "#60a5fa"), (1320, "#f472b6")):
        pts = " ".join(f"{x0 + 14 * math.sin(y / 18):.0f},{y}" for y in range(0, 200, 6))
        s.add(f'<polyline points="{pts}" stroke="{col2}" stroke-width="5" fill="none" stroke-linecap="round"/>')
    s.confetti(110, ["#f5c542", "#f472b6", "#a78bfa", "#60a5fa", "#ffffff"], 0, 600, size=(3, 7))


def scene_mlk(s):
    """MLK Day: Boston University's Marsh Chapel (Dr. King earned his PhD at BU) at sunrise, with the
    'Free at Last' sculpture's doves rising."""
    s.sky("#2b2156", "#b0607a", "#ffcf7a")
    s.sun(800, 300, 60, "#fff0c2", "#ffcf7a")
    s.rays(800, 300, ["#fff2c9", "#ffd98a"], 26, 0.10, spread=2 * math.pi)
    s.skyline("#5a3c6a", hmin=30, hmax=90, towers=False, opacity=0.45)
    c, base, col = 800, 430, "#2a1d3a"
    # chapel nave and transepts
    s.add(f'<rect x="{c - 220}" y="{base - 120}" width="440" height="120" fill="{col}"/>'
          f'<polygon points="{c - 230},{base - 120} {c},{base - 175} {c + 230},{base - 120}" fill="{col}"/>'
          f'<rect x="{c - 70}" y="{base - 300}" width="140" height="300" fill="{col}"/>')
    for px in (c - 70, c - 28, c + 28, c + 70):  # pinnacles
        s.add(f'<rect x="{px - 7}" y="{base - 330}" width="14" height="34" fill="{col}"/>'
              f'<polygon points="{px - 7},{base - 330} {px},{base - 356} {px + 7},{base - 330}" fill="{col}"/>')
    # pointed windows glowing
    s.add(f'<path d="M{c - 34},{base - 40} L{c - 34},{base - 180} Q{c},{base - 240} {c + 34},{base - 180} L{c + 34},{base - 40} Z" fill="#ffcf7a" opacity="0.9"/>'
          f'<path d="M{c},{base - 230} L{c},{base - 40} M{c - 34},{base - 130} L{c + 34},{base - 130}" stroke="{col}" stroke-width="4"/>')
    for wx in (c - 170, c - 120, c + 120, c + 170):
        s.add(f'<path d="M{wx - 12},{base - 20} L{wx - 12},{base - 80} Q{wx},{base - 104} {wx + 12},{base - 80} L{wx + 12},{base - 20} Z" fill="#ffcf7a" opacity="0.75"/>')
    # Free at Last: a column of doves rising from a plinth
    s.add(f'<rect x="1080" y="{base - 30}" width="60" height="30" fill="#3b2b4a"/>')
    for i in range(16):
        t = i / 15
        x = 1110 + math.sin(t * 7) * 70 * (0.4 + t) + t * 120
        y = base - 50 - t * 300
        s.add(dove(x, y, 0.6 + t * 0.5, "#ffffff", 0.95, flip=(i % 2 == 0)))
    for i in range(7):
        s.add(dove(500 - i * 60, 120 + (i % 2) * 40, 0.8, "#fff7e6", 0.75))
    s.ground(base, "#2f2440", "#4a3a5a")
    for x in (120, 260, 1340, 1480):
        s.tree(x, base + 4, 1.6, "#2b2238")
    s.add(f'<rect x="0" y="{base}" width="{W}" height="{H - base}" fill="{s.vgrad([(0, "#3a2b4a"), (1, "#1a1326")])}"/>')
    s.add(f'<path d="M{c - 90},{H} L{c - 40},{base} L{c + 40},{base} L{c + 90},{H} Z" fill="#5a4668" opacity="0.6"/>')


def scene_lunarnewyear(s):
    """Lunar New Year: the Chinatown Gate on Beach Street, red lanterns, firecrackers and plum blossoms."""
    s.sky("#2a0608", "#7a1418", "#d2541f")
    s.moon(300, 110, 34, "#ffe9b0", 0.0)
    s.skyline("#3a0a0e", hmin=50, hmax=150, window="#ffb347", opacity=0.9)
    c, base = 800, 440
    stone, roof, gold, red = "#e6dccb", "#1f6f5c", "#f5c542", "#c81e1e"
    # side pillars and lower roofs
    for sx in (c - 260, c + 220):
        s.add(f'<rect x="{sx}" y="{base - 170}" width="40" height="170" fill="{stone}"/>'
              f'<path d="M{sx - 40},{base - 166} Q{sx + 20},{base - 182} {sx + 80},{base - 166} L{sx + 88},{base - 178} Q{sx + 20},{base - 196} {sx - 48},{base - 178} Z" fill="{roof}"/>')
    # main pillars
    for px in (c - 170, c + 130):
        s.add(f'<rect x="{px}" y="{base - 260}" width="40" height="260" fill="{stone}"/>'
              f'<rect x="{px + 6}" y="{base - 240}" width="6" height="200" fill="{red}" opacity="0.85"/>'
              f'<rect x="{px + 28}" y="{base - 240}" width="6" height="200" fill="{red}" opacity="0.85"/>')
    # beams and plaque
    s.add(f'<rect x="{c - 200}" y="{base - 262}" width="400" height="22" fill="{stone}"/>'
          f'<rect x="{c - 200}" y="{base - 214}" width="400" height="14" fill="{stone}"/>'
          f'<rect x="{c - 60}" y="{base - 252}" width="120" height="46" fill="{red}" stroke="{gold}" stroke-width="4"/>'
          f'<rect x="{c - 44}" y="{base - 242}" width="88" height="26" fill="none" stroke="{gold}" stroke-width="2" opacity="0.8"/>')
    # main upswept roof, two tiers
    for (w, y0, lift) in ((520, base - 264, 34), (300, base - 318, 26)):
        s.add(f'<path d="M{c - w / 2},{y0} Q{c},{y0 - 14} {c + w / 2},{y0} L{c + w / 2 + 16},{y0 - lift} Q{c + w / 4},{y0 - 26} {c},{y0 - 30} '
              f'Q{c - w / 4},{y0 - 26} {c - w / 2 - 16},{y0 - lift} Z" fill="{roof}"/>'
              f'<path d="M{c - w / 2 + 10},{y0 - 2} Q{c},{y0 - 14} {c + w / 2 - 10},{y0 - 2}" stroke="{gold}" stroke-width="3" fill="none"/>')
    s.add(f'<rect x="{c - 110}" y="{base - 316}" width="220" height="24" fill="{stone}"/>'
          f'<circle cx="{c}" cy="{base - 356}" r="9" fill="{gold}"/>')
    # guardian lions
    for lx, flip in ((c - 240, 1), (c + 240, -1)):
        s.add(f'<g transform="translate({lx},{base}) scale({flip},1)" fill="#cfc4b0"><rect x="-26" y="-20" width="52" height="20"/>'
              f'<path d="M-20,-20 L-20,-60 Q-6,-80 14,-66 L18,-50 L8,-46 L10,-20 Z"/><circle cx="2" cy="-66" r="14"/></g>')
    s.ground(HZ, "#2a0a0c", "#4a1414")
    s.add(f'<path d="M{c - 200},{H} L{c - 120},{base} L{c + 120},{base} L{c + 200},{H} Z" fill="#8a1c1c" opacity="0.55"/>')
    # strings of lanterns across the top
    for x0, x1, y in ((0, 560, 60), (1040, W, 60)):
        s.add(f'<path d="M{x0},{y} Q{(x0 + x1) / 2},{y + 60} {x1},{y}" stroke="{gold}" stroke-width="2" fill="none"/>')
        for i in range(5):
            t = (i + 0.5) / 5
            lx = x0 + (x1 - x0) * t
            ly = y + 60 * 2 * t * (1 - t) * 1.0 + 30
            s.add(lantern(lx, ly + 20, 0.62, red, gold, string=20))
    s.add(lantern(c, base - 180, 0.9, red, gold, string=40))
    # lion dance: head, body cloth and dancers' legs, plus drum
    lx, ly = 560, 560
    s.add(f'<g transform="translate({lx},{ly})">'
          f'<path d="M0,-60 Q120,-110 260,-70 L260,-20 Q120,-40 0,-10 Z" fill="#f5c542"/>'
          f'<path d="M0,-60 Q120,-110 260,-70" stroke="#c81e1e" stroke-width="8" fill="none"/>'
          + "".join(f'<path d="M{30 + k * 40},-74 q8,-14 16,0" stroke="#c81e1e" stroke-width="5" fill="none"/>' for k in range(6))
          + f'<path d="M260,-70 Q300,-80 300,-40 L270,-20 Z" fill="#ffffff"/>'
          + "".join(f'<rect x="{x0}" y="-14" width="14" height="44" fill="#111"/><rect x="{x0 - 4}" y="26" width="22" height="8" rx="3" fill="#c81e1e"/>' for x0 in (40, 80, 180, 220))
          + f'<g transform="translate(-20,-60)"><ellipse cx="0" cy="0" rx="62" ry="56" fill="#c81e1e"/>'
          f'<ellipse cx="-4" cy="-30" rx="40" ry="18" fill="#f5c542"/><circle cx="-20" cy="-6" r="13" fill="#fff"/><circle cx="18" cy="-6" r="13" fill="#fff"/>'
          f'<circle cx="-18" cy="-6" r="6" fill="#111"/><circle cx="20" cy="-6" r="6" fill="#111"/>'
          f'<path d="M-40,22 Q0,52 40,22 L30,34 Q0,58 -30,34 Z" fill="#fff"/><circle cx="0" cy="12" r="10" fill="#f5c542"/>'
          f'<path d="M-62,-10 q-20,-30 6,-50 M62,-10 q20,-30 -6,-50" stroke="#ffffff" stroke-width="7" fill="none"/>'
          f'<circle cx="0" cy="-58" r="10" fill="#1f6f5c"/></g></g>')
    s.add(f'<g transform="translate(1080,560)"><rect x="-46" y="-50" width="92" height="56" rx="10" fill="#c81e1e" stroke="{gold}" stroke-width="5"/>'
          f'<ellipse cx="0" cy="-50" rx="46" ry="12" fill="#f3e3c3" stroke="{gold}" stroke-width="4"/>'
          f'<line x1="40" y1="-90" x2="10" y2="-56" stroke="#6b3a1a" stroke-width="5"/><line x1="-40" y1="-92" x2="-12" y2="-56" stroke="#6b3a1a" stroke-width="5"/></g>')
    # firecracker strings at the edges
    for fx in (380, 1220):
        for i in range(12):
            y = 120 + i * 20
            s.add(f'<rect x="{fx - 14 + (i % 2) * 14}" y="{y}" width="14" height="22" rx="3" fill="{red}" stroke="{gold}" stroke-width="1.5" '
                  f'transform="rotate({-20 if i % 2 else 20} {fx} {y})"/>')
        s.add(f'<line x1="{fx}" y1="100" x2="{fx}" y2="370" stroke="{gold}" stroke-width="2"/>')
    # plum blossom branches in the top corners
    for bx, by, d in ((0, 0, 1), (W, 0, -1)):
        pts = [(bx, by + 40), (bx + d * 120, by + 90), (bx + d * 240, by + 70), (bx + d * 330, by + 120)]
        s.add(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" stroke="#3b1a12" stroke-width="7" fill="none" stroke-linecap="round"/>')
        for i in range(16):
            t = s.rng.random()
            seg = int(t * 3)
            (x0, y0), (x1, y1) = pts[seg], pts[seg + 1]
            f = t * 3 - seg
            x, y = x0 + (x1 - x0) * f + s.rng.uniform(-14, 14), y0 + (y1 - y0) * f + s.rng.uniform(-16, 14)
            s.add("".join(f'<circle cx="{x + math.cos(a) * 6:.0f}" cy="{y + math.sin(a) * 6:.0f}" r="5" fill="#ffb7c5"/>' for a in [k * 1.2566 for k in range(5)])
                  + f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3" fill="{gold}"/>')
    s.confetti(40, [gold, "#ff6b6b"], 0, 400, size=(3, 6))


def scene_valentines(s):
    """Valentine's Day: a candlelit café table for two on a North End street, the Old North Church
    steeple at sunset, string lights and hearts."""
    s.sky("#3a0f2a", "#a8326a", "#f7a1b6")
    s.sun(1000, 330, 48, "#ffe0d0", "#ffb3c7")
    # Old North Church
    tx, base = 1100, 400
    s.add(f'<rect x="{tx - 40}" y="{base - 190}" width="80" height="190" fill="#5a1f2a"/>'
          f'<rect x="{tx - 32}" y="{base - 232}" width="64" height="44" fill="#f2e6dc"/>'
          f'<rect x="{tx - 24}" y="{base - 268}" width="48" height="38" fill="#f2e6dc"/>'
          f'<rect x="{tx - 16}" y="{base - 300}" width="32" height="34" fill="#f2e6dc"/>'
          f'<polygon points="{tx - 12},{base - 300} {tx},{base - 380} {tx + 12},{base - 300}" fill="#f2e6dc"/>'
          f'<line x1="{tx}" y1="{base - 380}" x2="{tx}" y2="{base - 398}" stroke="#d4af37" stroke-width="3"/>'
          f'<path d="M{tx - 12},{base - 200} L{tx - 12},{base - 222} Q{tx},{base - 236} {tx + 12},{base - 222} L{tx + 12},{base - 200} Z" fill="#3a1520"/>'
          f'<path d="M{tx - 9},{base - 238} L{tx - 9},{base - 256} Q{tx},{base - 266} {tx + 9},{base - 256} L{tx + 9},{base - 238} Z" fill="#3a1520"/>')
    s.windows_grid(tx - 34, base - 180, 68, 170, 2, 4, "#ffd98a", lit=0.8, arch=True)
    # brick walkups framing the street
    s.rowhouses(0, 470, 470, ["#7a2e2e", "#8a3a32", "#6e2a30"], h=(220, 300), window="#ffd98a", lit=0.75, trim="#d9c2b0", stoop=False)
    s.rowhouses(1180, W, 470, ["#7a2e2e", "#8a3a32", "#6e2a30"], h=(220, 300), window="#ffd98a", lit=0.75, trim="#d9c2b0", stoop=False)
    # fire escapes
    for fx in (60, 260, 1250, 1420):
        for i in range(3):
            y = 240 + i * 64
            s.add(f'<rect x="{fx}" y="{y}" width="70" height="4" fill="#1a0a10"/>'
                  + "".join(f'<rect x="{fx + k * 10}" y="{y - 20}" width="2" height="20" fill="#1a0a10"/>' for k in range(8)))
    s.ground(470, "#3a1622", "#5a2433")
    # cobblestones
    for row in range(6):
        y = 480 + row * 20
        for k in range(40):
            x = k * 44 + (row % 2) * 22
            s.add(f'<ellipse cx="{x}" cy="{y}" rx="18" ry="7" fill="#6a3040" opacity="0.5"/>')
    s.string_lights(0, 160, 800, 140, 40, ["#ffe08a", "#ffb3c7", "#fff3c4"])
    s.string_lights(800, 140, W, 170, 40, ["#ffe08a", "#ffb3c7", "#fff3c4"])
    # café table for two
    cx, ty = 760, 445
    s.glow(cx, ty - 60, 140, "#ffd27a", 0.45)
    for chx, d in ((cx - 120, 1), (cx + 120, -1)):
        s.add(f'<g stroke="#1a0a10" stroke-width="5" fill="none" stroke-linecap="round">'
              f'<path d="M{chx},{ty + 40} L{chx},{ty - 70} M{chx},{ty - 10} L{chx + d * 46},{ty - 10} L{chx + d * 46},{ty + 40}"/></g>')
    s.add(f'<rect x="{cx - 4}" y="{ty - 30}" width="8" height="70" fill="#1a0a10"/>'
          f'<ellipse cx="{cx}" cy="{ty + 40}" rx="36" ry="7" fill="#1a0a10"/>'
          f'<ellipse cx="{cx}" cy="{ty - 32}" rx="110" ry="16" fill="#f4e4e8"/>'
          f'<rect x="{cx - 7}" y="{ty - 72}" width="14" height="36" fill="#fff7ea"/>'
          f'<ellipse cx="{cx}" cy="{ty - 80}" rx="5" ry="10" fill="#ffd27a"/>'
          f'<path d="M{cx - 60},{ty - 36} L{cx - 60},{ty - 56} M{cx - 70},{ty - 76} Q{cx - 60},{ty - 50} {cx - 50},{ty - 76} Z" stroke="#f4e4e8" stroke-width="2" fill="#a51d3a"/>'
          f'<path d="M{cx + 60},{ty - 36} L{cx + 60},{ty - 56} M{cx + 50},{ty - 76} Q{cx + 60},{ty - 50} {cx + 70},{ty - 76} Z" stroke="#f4e4e8" stroke-width="2" fill="#a51d3a"/>'
          f'<path d="M{cx + 22},{ty - 40} l12,-14 l8,6 z" fill="#ffffff"/>')  # a cannoli, sort of
    s.glow(cx, ty - 80, 40, "#ffd27a", 0.8)
    # rising hearts
    for i in range(26):
        t = i / 25
        x = cx + math.sin(t * 9) * 80 * t + s.rng.uniform(-30, 30)
        y = ty - 110 - t * 300
        s.add(heart(x, y, 0.5 + t * 0.9, s.rng.choice(["#ff5c8a", "#ffb3c7", "#ffffff", "#e0264f"]), 0.95 - t * 0.35))


def scene_presidents(s):
    """Presidents' Day: the Massachusetts State House's gold dome on a crisp winter day, flags flying,
    bunting on the portico, the snowy Common below."""
    s.sky("#5b8fe0", "#a9cbf7", "#e8f2ff")
    s.clouds([(250, 110, 1.2), (1350, 90, 1.0), (1050, 170, 0.7)], "#ffffff", 0.9)
    s.skyline("#93a9cc", hmin=40, hmax=120, towers=True, opacity=0.6)
    c, base = 800, 410
    brick, white, gold = "#a34a32", "#f4efe6", "#e8b923"
    # wings
    s.add(f'<rect x="{c - 330}" y="{base - 120}" width="660" height="120" fill="{brick}"/>'
          f'<rect x="{c - 336}" y="{base - 126}" width="672" height="8" fill="{white}"/>')
    s.windows_grid(c - 320, base - 112, 140, 100, 4, 2, "#e8f0ff", ww=14, wh=26)
    s.windows_grid(c + 180, base - 112, 140, 100, 4, 2, "#e8f0ff", ww=14, wh=26)
    # central block with arcade and colonnade
    s.add(f'<rect x="{c - 180}" y="{base - 230}" width="360" height="230" fill="{brick}"/>'
          f'<rect x="{c - 160}" y="{base - 60}" width="320" height="60" fill="{white}"/>')
    for i in range(7):
        ax = c - 140 + i * 40
        s.add(f'<path d="M{ax},{base} L{ax},{base - 34} A14,14 0 0 1 {ax + 28},{base - 34} L{ax + 28},{base} Z" fill="#6a4a3a"/>')
    s.add(f'<rect x="{c - 160}" y="{base - 66}" width="320" height="8" fill="{white}"/>')
    for i in range(10):
        s.add(f'<rect x="{c - 150 + i * 33}" y="{base - 160}" width="10" height="94" fill="{white}"/>')
    s.add(f'<rect x="{c - 164}" y="{base - 172}" width="328" height="14" fill="{white}"/>'
          f'<polygon points="{c - 150},{base - 172} {c},{base - 222} {c + 150},{base - 172}" fill="{white}"/>'
          f'<polygon points="{c - 124},{base - 178} {c},{base - 212} {c + 124},{base - 178}" fill="{brick}"/>')
    for i in range(5):
        s.bunting_fan(c - 128 + i * 64, base - 66, 26)
    # dome
    s.add(f'<rect x="{c - 92}" y="{base - 262}" width="184" height="34" fill="{white}"/>'
          + "".join(f'<rect x="{c - 84 + i * 21}" y="{base - 258}" width="8" height="26" fill="#d8d0c0"/>' for i in range(9))
          + f'<path d="M{c - 88},{base - 262} A88,78 0 0 1 {c + 88},{base - 262} Z" fill="{gold}"/>'
          f'<path d="M{c - 60},{base - 270} A70,64 0 0 1 {c - 10},{base - 334}" stroke="#fff2a8" stroke-width="7" fill="none" opacity="0.7"/>'
          f'<rect x="{c - 16}" y="{base - 362}" width="32" height="26" fill="{white}"/>'
          f'<path d="M{c - 18},{base - 362} A18,16 0 0 1 {c + 18},{base - 362} Z" fill="{gold}"/>'
          f'<ellipse cx="{c}" cy="{base - 384}" rx="6" ry="9" fill="{gold}"/>')
    # flags on the roof
    s.flag_us(c - 260, base - 300, fw=110, fh=66, pole_h=180, amp=5)
    s.add(f'<rect x="{c + 250}" y="{base - 300}" width="5" height="180" fill="#d9d9d9"/>'
          f'<path d="M{c + 255},{base - 296} q55,-8 110,0 l0,64 q-55,-8 -110,0 z" fill="#ffffff"/>'
          f'<circle cx="{c + 310}" cy="{base - 266}" r="18" fill="#2a4a9a"/>')
    # Common: snow, iron fence, bare elms
    s.ground(base, "#eef3fb", "#ffffff")
    s.add("".join(f'<rect x="{x}" y="{base + 28}" width="3" height="40" fill="#1e2433"/>' for x in range(0, W, 16))
          + f'<rect x="0" y="{base + 34}" width="{W}" height="4" fill="#1e2433"/><rect x="0" y="{base + 60}" width="{W}" height="3" fill="#1e2433"/>')
    for x, h in ((90, 330), (260, 280), (1340, 300), (1510, 340)):
        s.bare_tree(x, base + 70, h, "#2a2f3d")
    s.add("".join(star(s.rng.random() * W, 470 + s.rng.random() * 120, 6 + s.rng.random() * 6, s.rng.choice(["#b22234", "#3c3b6e"]), 0.25) for _ in range(20)))


def scene_stpatricks(s):
    """St. Patrick's Day & Evacuation Day: the Dorchester Heights monument above South Boston's
    triple-deckers, the parade passing with pipers, green bunting and shamrocks."""
    s.sky("#3fa3d8", "#9fd8f0", "#e8f7ff")
    s.clouds([(300, 100, 1.2), (1300, 130, 1.0), (700, 70, 0.8)], "#fff", 0.95)
    s.rays(800, 120, ["#fff8d0"], 18, 0.12, spread=2 * math.pi)
    # Dorchester Heights on its hill
    s.hills(330, "#4caf6a", [(500, 30), (800, 110), (1100, 30)])
    c, top = 800, 70
    s.add(f'<rect x="{c - 34}" y="{top + 90}" width="68" height="160" fill="#f6f3ea"/>'
          f'<rect x="{c - 40}" y="{top + 84}" width="80" height="10" fill="#e3ddcc"/>'
          f'<rect x="{c - 26}" y="{top + 40}" width="52" height="46" fill="#f6f3ea"/>'
          f'<polygon points="{c - 26},{top + 40} {c},{top - 30} {c + 26},{top + 40}" fill="#f6f3ea"/>'
          f'<path d="M{c - 10},{top + 160} L{c - 10},{top + 130} A10,10 0 0 1 {c + 10},{top + 130} L{c + 10},{top + 160} Z" fill="#a9b8c4"/>'
          f'<path d="M{c - 8},{top + 76} L{c - 8},{top + 58} A8,8 0 0 1 {c + 8},{top + 58} L{c + 8},{top + 76} Z" fill="#a9b8c4"/>'
          f'<rect x="{c - 1}" y="{top - 50}" width="2" height="22" fill="#666"/>')
    s.hills(400, "#3e9a58", [(200, 40), (600, 70), (1000, 70), (1400, 40)])
    # triple-deckers lining the parade route
    pastel = ["#f2d7a6", "#cfe3d4", "#f4c9b8", "#d7dcf0", "#f0e4b8", "#cde8e0"]
    s.triple_deckers(-20, 560, 470, pastel)
    s.triple_deckers(1060, W + 40, 470, pastel)
    for x0 in (0, 1060):
        s.bunting(x0, 340, x0 + 540, 340, 18, ["#169b62", "#ffffff", "#ff883e"], 14)
    s.ground(470, "#5a5f6a", "#7a808c")
    s.add(f'<rect x="0" y="{470}" width="{W}" height="10" fill="#c9c9c9"/>')
    # parade: pipers marching
    for i, x in enumerate(range(560, 1060, 70)):
        y = 540 + (i % 2) * 6
        s.add(f'<g transform="translate({x},{y})">'
              f'<rect x="-11" y="-18" width="22" height="22" fill="#1f6b3a"/>'   # kilt
              f'<path d="M-10,-44 Q0,-48 10,-44 L9,-16 L-9,-16 Z" fill="#14213d"/>'
              f'<circle cx="0" cy="-54" r="8" fill="#e8c6a4"/>'
              f'<rect x="-11" y="-72" width="22" height="14" rx="4" fill="#111"/>'   # feather bonnet
              f'<path d="M6,-40 l26,-6 l4,8 l-24,8 z" fill="#2e7d32"/>'              # bag
              + "".join(f'<line x1="{20 + k * 6}" y1="-46" x2="{24 + k * 8}" y2="-82" stroke="#222" stroke-width="3"/>' for k in range(3))
              + f'<path d="M-5,4 L-6,22 M5,4 L6,22" stroke="#f4f4f4" stroke-width="5"/></g>')
    s.crowd(0, 520, 600, 1.6, ["#1f6b3a", "#2e7d32", "#14213d", "#ff883e"], arms=("wave", "up", "down"))
    s.crowd(1090, W, 600, 1.6, ["#1f6b3a", "#2e7d32", "#14213d", "#ff883e"], arms=("wave", "up", "down"))
    for _ in range(36):
        x = s.rng.random() * W
        if 660 < x < 940:
            x += 300 if x > 800 else -300
        s.add(shamrock(x, s.rng.random() * 300, 0.6 + s.rng.random() * 0.9,
                       s.rng.choice(["#169b62", "#2ecc71", "#0e7a45"]), 0.85, s.rng.random() * 360))


def scene_patriots(s):
    """Patriots' Day & Marathon Monday: the Boylston Street finish line, Old South Church, runners,
    cheering crowds and daffodils."""
    s.sky("#2f6fd1", "#8fc1ff", "#e6f3ff")
    s.clouds([(200, 90, 1.1), (1400, 120, 1.3)], "#fff", 0.9)
    # Hancock tower glass behind
    s.add(f'<polygon points="1240,400 1240,40 1300,22 1360,40 1360,400" fill="{s.vgrad([(0, "#a8d1ff"), (1, "#5b8fd6")], x2=1, y2=0)}"/>')
    # Old South Church campanile
    tx = 380
    s.add(f'<rect x="{tx - 32}" y="140" width="64" height="260" fill="#b9a487"/>'
          + "".join(f'<rect x="{tx - 32}" y="{150 + k * 26}" width="64" height="6" fill="#8a5a4a" opacity="0.7"/>' for k in range(9))
          + f'<rect x="{tx - 38}" y="110" width="76" height="34" fill="#c9b597"/>'
          + "".join(f'<path d="M{tx - 30 + k * 20},{140} L{tx - 30 + k * 20},{122} A6,6 0 0 1 {tx - 18 + k * 20},{122} L{tx - 18 + k * 20},{140} Z" fill="#4a3a2a"/>' for k in range(4))
          + f'<polygon points="{tx - 34},110 {tx},30 {tx + 34},110" fill="#5c7a6a"/>')
    s.rowhouses(0, 340, 430, ["#c9a27e", "#b98a68", "#d8b48e"], h=(130, 200), window="#dfefff", lit=1.0, trim="#efe6d8", stoop=False)
    s.rowhouses(1160, W, 430, ["#c9a27e", "#b98a68", "#d8b48e"], h=(130, 200), window="#dfefff", lit=1.0, trim="#efe6d8", stoop=False)
    s.ground(430, "#5a6270", "#737c8a")
    # finish line gantry
    blue, yellow = "#1f4fbf", "#ffd23f"
    s.add(f'<rect x="470" y="150" width="22" height="300" fill="{blue}"/><rect x="1108" y="150" width="22" height="300" fill="{blue}"/>'
          f'<rect x="460" y="140" width="680" height="70" rx="6" fill="{yellow}"/>'
          f'<rect x="460" y="196" width="680" height="14" fill="{blue}"/>'
          f'<text x="800" y="190" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="46" fill="{blue}" letter-spacing="10">FINISH</text>')
    # painted finish line on the road (perspective)
    s.add(f'<polygon points="430,470 1170,470 1260,500 340,500" fill="{yellow}"/>'
          f'<polygon points="340,500 1260,500 1290,512 310,512" fill="{blue}"/>')
    for k in range(-6, 7):
        s.add(f'<line x1="{800 + k * 60}" y1="430" x2="{800 + k * 160}" y2="{H}" stroke="#ffffff" stroke-width="2" opacity="0.12"/>')
    # runners
    for x, y, sc, col in ((700, 470, 1.7, "#e63946"), (860, 476, 1.8, "#1d3557"), (790, 455, 1.3, "#f4a261"), (960, 452, 1.25, "#2a9d8f"), (600, 450, 1.2, "#6a4c93")):
        s.person(x, y, sc, col, "run" if sc < 1.6 else "up")
        s.add(f'<rect x="{x - 8 * sc:.0f}" y="{y - 38 * sc:.0f}" width="{16 * sc:.0f}" height="{10 * sc:.0f}" fill="#fff"/>')  # bib
    s.crowd(0, 400, 560, 1.7, ["#1f4fbf", "#ffd23f", "#e63946", "#2a9d8f", "#333"], arms=("up", "wave", "up"))
    s.crowd(1200, W, 560, 1.7, ["#1f4fbf", "#ffd23f", "#e63946", "#2a9d8f", "#333"], arms=("up", "wave", "up"))
    # daffodils along the front
    for i in range(34):
        x = s.rng.random() * W
        if 330 < x < 1270:
            continue
        y = 560 + s.rng.random() * 40
        s.add(f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x:.0f}" y2="{y + 40:.0f}" stroke="#3a7d2c" stroke-width="3"/>'
              + "".join(f'<ellipse cx="{x + math.cos(a) * 8:.0f}" cy="{y + math.sin(a) * 8:.0f}" rx="7" ry="4" fill="#ffe14d" transform="rotate({math.degrees(a):.0f} {x + math.cos(a) * 8:.0f} {y + math.sin(a) * 8:.0f})"/>' for a in [k * 1.0472 for k in range(6)])
              + f'<circle cx="{x:.0f}" cy="{y:.0f}" r="5" fill="#ff9f1c"/>')
    s.confetti(90, [blue, yellow, "#ffffff"], 0, 380, size=(3, 7))


def scene_memorial(s):
    """Memorial Day: the Garden of Flags on Boston Common (tens of thousands of small flags around the
    Soldiers and Sailors Monument on Flagstaff Hill) in the evening light."""
    s.sky("#1c2b55", "#6f6aa0", "#f0b27a")
    s.sun(1180, 360, 44, "#ffe0b0", "#ffb36b")
    s.skyline("#2a2f55", hmin=40, hmax=140, window="#ffd27a", opacity=0.75)
    s.hills(360, "#3f5a3a", [(600, 30), (800, 70), (1000, 30)])
    c, top = 800, 120
    s.add(f'<rect x="{c - 60}" y="{top + 150}" width="120" height="30" fill="#c9c3b5"/>'
          f'<rect x="{c - 44}" y="{top + 110}" width="88" height="44" fill="#d8d2c4"/>'
          f'<rect x="{c - 14}" y="{top - 20}" width="28" height="134" fill="#e3ddd0"/>'
          f'<rect x="{c - 20}" y="{top - 28}" width="40" height="10" fill="#c9c3b5"/>'
          f'<path d="M{c - 8},{top - 28} L{c - 6},{top - 70} Q{c},{top - 80} {c + 6},{top - 70} L{c + 8},{top - 28} Z" fill="#c9c3b5"/>'
          f'<circle cx="{c}" cy="{top - 82}" r="7" fill="#c9c3b5"/>')
    for fx in (c - 50, c + 50):
        s.add(f'<rect x="{fx - 2}" y="{top + 110}" width="4" height="44" fill="#bbb"/>')
    s.hills(420, "#4a6b40", [(300, 10), (800, 40), (1300, 10)])
    s.ground(430, "#2f4a2a", "#4a6b40")
    # thousands of flags in perspective rows
    rows = 11
    for r_ in range(rows):
        t = r_ / (rows - 1)
        y = 330 + (t ** 1.6) * 280
        sc = 0.25 + t * 1.0
        spacing = 22 + t * 64
        offset = (r_ % 2) * spacing / 2
        x = -20 + offset
        out = []
        while x < W + 20:
            # leave the path up the hill clear
            if not (abs(x - c) < 30 + t * 60 and y < 420):
                out.append(s.mini_flag(x + s.rng.uniform(-2, 2), y, sc))
            x += spacing
        s.add("".join(out))
    s.add(f'<rect width="{W}" height="{H}" fill="{s.vgrad([(0, "#f0b27a", 0), (0.7, "#f0b27a", 0), (1, "#1c2b55", 0.35)])}"/>')


def scene_juneteenth(s):
    """Juneteenth: the African Meeting House on Beacon Hill (the oldest standing Black church building in
    the US) with the Juneteenth flag and celebration pennants."""
    s.sky("#26458a", "#e67a5a", "#ffd27a")
    s.sun(1240, 250, 54, "#fff0c2", "#ffd27a")
    s.rays(1240, 250, ["#fff2c9"], 24, 0.10, spread=2 * math.pi)
    s.rowhouses(0, 520, 440, ["#8a3a2a", "#9a4a32", "#7a3424"], h=(170, 230), window="#ffe7a8", lit=0.9, trim="#e8d8c0", stoop=True)
    s.rowhouses(1100, W, 440, ["#8a3a2a", "#9a4a32", "#7a3424"], h=(170, 230), window="#ffe7a8", lit=0.9, trim="#e8d8c0", stoop=True)
    # African Meeting House: 3-story brick, arched windows, pediment
    x0, w, base = 560, 380, 440
    s.add(f'<rect x="{x0}" y="{base - 270}" width="{w}" height="270" fill="#9c4a2e"/>'
          f'<polygon points="{x0 - 10},{base - 270} {x0 + w / 2},{base - 340} {x0 + w + 10},{base - 270}" fill="#f1e6d2"/>'
          f'<polygon points="{x0 + 20},{base - 276} {x0 + w / 2},{base - 326} {x0 + w - 20},{base - 276}" fill="#9c4a2e"/>'
          f'<circle cx="{x0 + w / 2}" cy="{base - 296}" r="14" fill="#f1e6d2"/>'
          f'<rect x="{x0 - 6}" y="{base - 274}" width="{w + 12}" height="8" fill="#f1e6d2"/>')
    s.windows_grid(x0 + 20, base - 250, w - 40, 160, 4, 2, "#ffe7a8", ww=36, wh=64, arch=True)
    for dx in (w / 2 - 110, w / 2 - 30, w / 2 + 50):
        s.add(f'<path d="M{x0 + dx},{base} L{x0 + dx},{base - 56} A30,30 0 0 1 {x0 + dx + 60},{base - 56} L{x0 + dx + 60},{base} Z" fill="#3a2418"/>'
              f'<path d="M{x0 + dx + 6},{base - 56} A24,24 0 0 1 {x0 + dx + 54},{base - 56} Z" fill="#ffe7a8" opacity="0.8"/>')
    # Juneteenth flag: blue top, red bottom, white arc and starburst
    px, pt = 1010, 120
    fw, fh = 210, 130

    def wv(x):
        return 7 * math.sin(x / fw * 2 * math.pi)

    top = " ".join(f"{px + 5 + x:.0f},{pt + 5 + wv(x):.1f}" for x in range(0, fw + 1, 10))
    mid = " ".join(f"{px + 5 + x:.0f},{pt + 5 + fh * 0.55 - 26 * math.sin(math.pi * x / fw) + wv(x):.1f}" for x in range(fw, -1, -10))
    mid_f = " ".join(f"{px + 5 + x:.0f},{pt + 5 + fh * 0.55 - 26 * math.sin(math.pi * x / fw) + wv(x):.1f}" for x in range(0, fw + 1, 10))
    bot = " ".join(f"{px + 5 + x:.0f},{pt + 5 + fh + wv(x):.1f}" for x in range(fw, -1, -10))
    s.add(f'<rect x="{px}" y="{pt}" width="5" height="330" fill="#d9d9d9"/>'
          f'<polygon points="{top} {mid}" fill="#0a3161"/><polygon points="{mid_f} {bot}" fill="#b31942"/>'
          f'<polyline points="{mid_f}" stroke="#ffffff" stroke-width="4" fill="none"/>')
    sx, sy = px + 5 + fw * 0.45, pt + 5 + fh * 0.48 + wv(fw * 0.45)
    s.add(star(sx, sy, 34, "#ffffff", 1, 0) + star(sx, sy, 34, "none") )
    s.add(f'<polygon points="{" ".join(f"{sx + (36 if k % 2 == 0 else 22) * math.cos(math.radians(-90 + k * 15)):.1f},{sy + (36 if k % 2 == 0 else 22) * math.sin(math.radians(-90 + k * 15)):.1f}" for k in range(24))}" '
          f'fill="none" stroke="#ffffff" stroke-width="2.5"/>' + star(sx, sy, 15, "#ffffff"))
    # pennants and a celebrating crowd
    s.bunting(0, 120, 540, 150, 30, ["#b31942", "#f5b82e", "#1f8a4c", "#111111"], 18)
    s.bunting(1100, 160, W, 120, 30, ["#b31942", "#f5b82e", "#1f8a4c", "#111111"], 18)
    s.ground(440, "#6e3a28", "#9a5a3a")
    s.add(f'<rect x="0" y="440" width="{W}" height="16" fill="#c9b8a0"/>')
    s.crowd(40, W - 40, 560, 1.9, ["#3a2418", "#5a3420", "#2a1810", "#7a4a2a"], arms=("up", "wave", "down", "up"))
    s.confetti(80, ["#b31942", "#f5b82e", "#1f8a4c", "#ffffff", "#0a3161"], 0, 420, size=(3, 7))


def scene_july4(s):
    """Fourth of July: Boston Pops fireworks over the Charles, the Hatch Shell on the Esplanade and the
    Longfellow Bridge, reflections in the river."""
    s.sky("#050a24", "#162a66", "#3a4f9e", bottom=330)
    s.stars(80, 300, 0.6)
    bursts = [(380, 120, 90, "#ff4d5e"), (620, 80, 70, "#ffffff"), (820, 150, 110, "#5b9cff"), (1060, 90, 80, "#ffd23f"),
              (1260, 140, 95, "#ff4d5e"), (500, 230, 50, "#5b9cff"), (1140, 240, 55, "#ffffff"), (960, 60, 45, "#ff9ad5")]
    for x, y, r, c in bursts:
        s.firework(x, y, r, c, 22)
    s.skyline("#0b1230", y=330, hmin=40, hmax=120, window="#ffd27a", opacity=0.95)
    # Longfellow Bridge (salt-and-pepper towers, arches) on the right
    s.add(f'<rect x="1150" y="300" width="{W - 1150}" height="12" fill="#1a1f3a"/>')
    for i, x in enumerate(range(1170, W, 110)):
        s.add(f'<path d="M{x},{330} A55,26 0 0 1 {x + 110},{330}" fill="none" stroke="#1a1f3a" stroke-width="10"/>')
        if i % 2 == 0:
            s.add(f'<rect x="{x - 10}" y="262" width="20" height="40" fill="#1a1f3a"/><ellipse cx="{x}" cy="262" rx="12" ry="18" fill="#1a1f3a"/>')
    # far bank: the Esplanade with the Hatch Shell
    s.add(f'<rect x="0" y="318" width="{W}" height="22" fill="#0a1026"/>')
    c, base = 800, 338
    s.add(f'<path d="M{c - 150},{base} A150,130 0 0 1 {c + 150},{base} Z" fill="#e9e6dc"/>')
    for k in range(1, 6):
        r = 150 - k * 22
        s.add(f'<path d="M{c - r},{base} A{r},{r * 0.87} 0 0 1 {c + r},{base}" fill="none" stroke="#b9b4a6" stroke-width="3"/>')
    s.add(f'<path d="M{c - 64},{base} A64,56 0 0 1 {c + 64},{base} Z" fill="#ffd27a" opacity="0.85"/>')
    s.glow(c, base - 30, 180, "#ffd27a", 0.25)
    for tx in (120, 260, 420, 1080, 1300):
        s.tree(tx, base, 1.1, "#0b1a1a")
    s.crowd(0, W, 352, 0.7, ["#0a0f22", "#131a33"], arms=("up", "wave", "down"))
    # the river with reflections
    s.water(352, "#22336e", "#060a1e", "#ffffff", 40, 0.25)
    for x, y, r, c2 in bursts:
        ry = 352 + (352 - y) * 0.55
        s.add(f'<ellipse cx="{x}" cy="{ry:.0f}" rx="{r * 0.9:.0f}" ry="{r * 0.35:.0f}" fill="{c2}" opacity="0.13"/>')
        for k in range(5):
            s.add(f'<rect x="{x - r * 0.5 + s.rng.random() * r:.0f}" y="{ry - 20 + k * 10:.0f}" width="{20 + s.rng.random() * 50:.0f}" height="2" fill="{c2}" opacity="0.5"/>')
    # boats watching
    for bx, by, sc in ((300, 470, 1.1), (1250, 500, 1.3), (650, 540, 0.9)):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})" fill="#04060f"><path d="M-50,0 L50,0 L40,14 L-42,14 Z"/>'
              f'<rect x="-2" y="-70" width="3" height="70"/><polygon points="2,-66 2,-6 36,-6"/></g>')


def scene_labor(s):
    """Labor Day: last summer weekend at Castle Island: Fort Independence, sailboats, a plane
    coming into Logan, umbrellas on the beach at Pleasure Bay."""
    s.sky("#2f8fd8", "#8fd0f5", "#fff1c9")
    s.sun(1300, 120, 52, "#fff6c9", "#ffe08a")
    s.clouds([(300, 120, 1.2), (760, 80, 0.9), (1000, 160, 0.7)], "#fff", 0.95)
    # plane on approach
    s.add(f'<g transform="translate(560,110) rotate(8)" fill="#e8eef8"><ellipse cx="0" cy="0" rx="60" ry="9"/>'
          f'<polygon points="-10,0 20,0 -14,-40 -26,-40"/><polygon points="-10,0 20,0 -14,40 -26,40"/>'
          f'<polygon points="-50,-2 -40,-2 -56,-24 -62,-24"/></g>')
    s.skyline("#7aa2c8", y=330, hmin=40, hmax=130, opacity=0.55)
    s.water(330, "#2a8fc4", "#0f5a8a", "#ffffff", 60, 0.45)
    # Fort Independence: low granite star fort on the island
    fx, fy = 820, 345
    s.add(f'<path d="M{fx - 230},{fy + 40} L{fx - 200},{fy - 20} L{fx - 120},{fy - 40} L{fx + 120},{fy - 40} L{fx + 200},{fy - 20} L{fx + 230},{fy + 40} Z" fill="#9aa3ab"/>'
          f'<path d="M{fx - 200},{fy - 20} L{fx - 120},{fy - 40} L{fx + 120},{fy - 40} L{fx + 200},{fy - 20} L{fx + 190},{fy - 8} L{fx - 190},{fy - 8} Z" fill="#b8c0c6"/>'
          + "".join(f'<rect x="{fx - 160 + k * 40}" y="{fy - 4}" width="12" height="20" fill="#5a6470" opacity="0.6"/>' for k in range(9))
          + f'<path d="M{fx - 300},{fy + 40} Q{fx},{fy + 20} {fx + 300},{fy + 40} Z" fill="#5f8a4a"/>')
    s.flag_us(fx - 3, fy - 150, fw=80, fh=48, pole_h=112, amp=4)
    for bx, by, sc in ((380, 380, 0.9), (1180, 370, 0.8), (1400, 400, 1.1), (200, 395, 0.7)):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})"><path d="M-40,0 L40,0 L32,10 L-34,10 Z" fill="#1d3557"/>'
              f'<rect x="-1" y="-80" width="3" height="80" fill="#333"/><polygon points="3,-76 3,-6 44,-6" fill="#fff"/>'
              f'<polygon points="-3,-66 -3,-6 -30,-6" fill="#ffd166"/></g>')
    # Pleasure Bay beach
    s.add(f'<path d="M0,450 Q400,420 800,440 T{W},430 L{W},{H} L0,{H} Z" fill="{s.vgrad([(0, "#f6deaa"), (1, "#e8c483")])}"/>'
          f'<path d="M0,450 Q400,420 800,440 T{W},430" stroke="#ffffff" stroke-width="4" fill="none" opacity="0.8"/>')
    for ux, uy, c1, c2 in ((240, 540, "#ff6b6b", "#ffffff"), (520, 520, "#4dabf7", "#ffd43b"), (1100, 530, "#ffd43b", "#ff6b6b"), (1380, 545, "#51cf66", "#ffffff")):
        s.add(f'<line x1="{ux}" y1="{uy}" x2="{ux + 6}" y2="{uy + 60}" stroke="#6b4a2a" stroke-width="4"/>'
              + "".join(f'<path d="M{ux},{uy} L{ux + 70 * math.cos(math.radians(a)):.0f},{uy + 70 * math.sin(math.radians(a)) + 30:.0f} '
                        f'A70,40 0 0 1 {ux + 70 * math.cos(math.radians(a + 36)):.0f},{uy + 70 * math.sin(math.radians(a + 36)) + 30:.0f} Z" '
                        f'fill="{c1 if k % 2 == 0 else c2}"/>' for k, a in enumerate(range(180, 360, 36)))
              + f'<rect x="{ux - 50}" y="{uy + 50}" width="80" height="18" rx="3" fill="{c1}" opacity="0.8" transform="rotate(-6 {ux} {uy + 60})"/>')
    s.add(f'<circle cx="800" cy="560" r="20" fill="#fff"/><path d="M780,560 A20,20 0 0 1 800,540 L800,560 Z" fill="#ff6b6b"/>'
          f'<path d="M800,540 A20,20 0 0 1 820,560 L800,560 Z" fill="#4dabf7"/><path d="M800,560 L820,560 A20,20 0 0 1 800,580 Z" fill="#ffd43b"/>')
    s.add(f'<g transform="translate(960,560)" fill="#e8c483" stroke="#c9a463" stroke-width="2"><rect x="-40" y="-20" width="80" height="30"/>'
          f'<rect x="-30" y="-46" width="20" height="26"/><rect x="10" y="-46" width="20" height="26"/><rect x="-10" y="-60" width="20" height="40"/>'
          f'<line x1="0" y1="-60" x2="0" y2="-80" stroke="#555"/><polygon points="0,-80 16,-74 0,-68" fill="#ff6b6b" stroke="none"/></g>')


def scene_indigenous(s):
    """Indigenous Peoples' Day: the Blue Hills at autumn sunset (Massachusett, the people the state is
    named for, means 'at the great hill'), the Neponset winding through marsh, geese heading south."""
    s.sky("#2a1a3a", "#a0482a", "#f0a050")
    s.sun(980, 300, 70, "#ffe2a6", "#ffb36b")
    # range of hills, far to near
    s.hills(330, "#6a4a7a", [(150, 60), (420, 120), (700, 210), (980, 150), (1250, 90), (1500, 60)], 0.85)
    # Eliot Tower on Great Blue Hill
    s.add(f'<rect x="688" y="102" width="24" height="26" fill="#4a3458"/><rect x="684" y="98" width="32" height="6" fill="#4a3458"/>')
    s.hills(370, "#4e3a5e", [(100, 60), (380, 90), (900, 70), (1300, 110), (1550, 70)])
    s.hills(410, "#7a3a2a", [(0, 30), (500, 40), (1100, 30), (1600, 40)])
    # autumn forest band
    for i in range(70):
        x = s.rng.random() * W
        y = 400 + s.rng.random() * 30
        s.tree(x, y, 0.5 + s.rng.random() * 0.4, s.rng.choice(["#d9481f", "#e8822a", "#f2b134", "#a8321e", "#c76a1a"]))
    s.ground(430, "#5a3a24", "#7a5a2a")
    # marsh and river
    s.add(f'<path d="M500,430 C700,470 400,520 700,560 C900,590 1100,560 1300,{H} L1000,{H} C850,590 600,600 450,560 C250,510 600,470 380,430 Z" '
          f'fill="{s.vgrad([(0, "#f0a050"), (1, "#7a4a6a")])}"/>')
    for _ in range(26):
        x = s.rng.random() * W
        y = 470 + s.rng.random() * 120
        s.add(f'<path d="M{x:.0f},{y + 40:.0f} Q{x + 4:.0f},{y + 10:.0f} {x + 2:.0f},{y:.0f}" stroke="#3a2a18" stroke-width="3" fill="none"/>'
              f'<ellipse cx="{x + 2:.0f}" cy="{y + 4:.0f}" rx="4" ry="12" fill="#6a3a1a"/>')
    for i in range(80):
        x = s.rng.random() * W
        y = 450 + s.rng.random() * 150
        s.add(f'<path d="M{x:.0f},{y:.0f} q{s.rng.uniform(-6, 6):.0f},-26 {s.rng.uniform(-10, 10):.0f},-40" stroke="#c9a44a" stroke-width="2" fill="none" opacity="0.8"/>')
    # geese in a V, heading south (left)
    for k in range(-5, 6):
        x = 480 + abs(k) * 30
        y = 160 + k * 18
        s.add(f'<path d="M{x - 12},{y} Q{x - 4},{y - 8} {x},{y} Q{x + 4},{y - 8} {x + 12},{y}" stroke="#2a1a24" stroke-width="3" fill="none"/>')
    for _ in range(26):
        s.add(leaf(s.rng.random() * W, s.rng.random() * 420, 0.5 + s.rng.random() * 0.6,
                   s.rng.choice(["#e8822a", "#f2b134", "#c0392b"]), s.rng.random() * 360, 0.85))


def scene_election(s):
    """Election Day: Faneuil Hall with its grasshopper weathervane, patriotic bunting, a ballot box."""
    s.sky("#2b3f8a", "#7d93c8", "#e7ecf7")
    s.clouds([(260, 120, 1.0), (1320, 90, 1.2)], "#fff", 0.85)
    s.skyline("#6b7fae", hmin=60, hmax=160, opacity=0.6)
    c, base = 800, 430
    brick, white, gold = "#9c4630", "#f4efe6", "#e0b33a"
    s.add(f'<rect x="{c - 260}" y="{base - 220}" width="520" height="220" fill="{brick}"/>'
          f'<rect x="{c - 268}" y="{base - 228}" width="536" height="12" fill="{white}"/>'
          f'<polygon points="{c - 268},{base - 228} {c - 220},{base - 262} {c + 220},{base - 262} {c + 268},{base - 228}" fill="#4a4f5a"/>'
          f'<polygon points="{c - 110},{base - 228} {c},{base - 290} {c + 110},{base - 228}" fill="{white}"/>'
          f'<polygon points="{c - 86},{base - 232} {c},{base - 278} {c + 86},{base - 232}" fill="{brick}"/>'
          f'<circle cx="{c}" cy="{base - 252}" r="12" fill="{white}"/>')
    s.windows_grid(c - 250, base - 205, 500, 190, 9, 2, "#e8f0ff", ww=26, wh=60, arch=True)
    # cupola + grasshopper
    s.add(f'<rect x="{c - 30}" y="{base - 340}" width="60" height="54" fill="{white}"/>'
          + "".join(f'<path d="M{c - 22 + k * 16},{base - 296} L{c - 22 + k * 16},{base - 326} A6,6 0 0 1 {c - 10 + k * 16},{base - 326} L{c - 10 + k * 16},{base - 296} Z" fill="#9aa3b5"/>' for k in range(3))
          + f'<rect x="{c - 36}" y="{base - 346}" width="72" height="8" fill="{white}"/>'
          f'<path d="M{c - 24},{base - 346} A24,26 0 0 1 {c + 24},{base - 346} Z" fill="#7a8a7a"/>'
          f'<rect x="{c - 1.5}" y="{base - 398}" width="3" height="30" fill="{gold}"/>'
          f'<g transform="translate({c},{base - 400})" fill="{gold}"><ellipse cx="0" cy="0" rx="22" ry="6"/>'
          f'<path d="M-6,-2 L-22,-14 M6,-2 L22,-14 M-4,2 L-14,10 M4,2 L14,10" stroke="{gold}" stroke-width="3"/><circle cx="22" cy="-2" r="5"/></g>')
    for i in range(6):
        s.bunting_fan(c - 210 + i * 84, base - 120, 30)
    s.ground(base, "#6a6f7a", "#8a909c")
    s.add("".join(f'<rect x="{x}" y="{base}" width="60" height="{H - base}" fill="#7d838f" opacity="{0.25 + (x // 60) % 2 * 0.15}"/>' for x in range(0, W, 60)))
    # ballot box and ballot
    bx, by = 1240, 560
    s.add(f'<rect x="{bx - 80}" y="{by - 120}" width="160" height="120" rx="8" fill="#ffffff" stroke="#1e3a8a" stroke-width="6"/>'
          f'<rect x="{bx - 46}" y="{by - 126}" width="92" height="10" rx="3" fill="#1e3a8a"/>'
          f'<text x="{bx}" y="{by - 46}" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="42" fill="#b91c1c">VOTE</text>'
          f'<g transform="translate({bx + 10},{by - 170}) rotate(-12)"><rect x="-34" y="-46" width="68" height="86" fill="#fff" stroke="#999"/>'
          + "".join(f'<rect x="-24" y="{-34 + k * 18}" width="10" height="10" fill="none" stroke="#333" stroke-width="2"/><rect x="-8" y="{-31 + k * 18}" width="36" height="4" fill="#bbb"/>' for k in range(4))
          + '<path d="M-23,-11 l4,5 l8,-10" stroke="#1e3a8a" stroke-width="3" fill="none"/></g>')
    # "I voted" stickers
    for x, y in ((360, 520), (480, 560), (240, 575)):
        s.add(f'<g transform="translate({x},{y})"><ellipse rx="44" ry="26" fill="#fff" stroke="#1e3a8a" stroke-width="3"/>'
              f'<text y="7" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" font-size="17" fill="#b91c1c">I VOTED</text></g>')
    s.add("".join(star(s.rng.random() * W, s.rng.random() * 220, 5 + s.rng.random() * 8, s.rng.choice(["#ffffff", "#b91c1c", "#1e3a8a"]), 0.8) for _ in range(26)))


def scene_veterans(s):
    """Veterans Day: the Bunker Hill Monument at dusk, a flag over the harbor, poppies along the shore."""
    s.sky("#070d1f", "#1b2d5c", "#c9874a")
    s.stars(90, 260, 0.9)
    s.skyline("#070b18", hmin=50, hmax=150, window="#ffd27a")
    # Breed's Hill and the obelisk
    s.add(f'<path d="M140,{HZ} C240,330 380,300 480,302 C580,304 650,340 760,{HZ} Z" fill="#0b1328"/>')
    mx, top, base = 470, 70, 306
    s.add(f'<polygon points="{mx - 26},{base} {mx - 15},{top + 22} {mx},{top} {mx + 15},{top + 22} {mx + 26},{base}" fill="#c9b79a"/>'
          f'<polygon points="{mx},{top} {mx + 15},{top + 22} {mx + 26},{base} {mx + 4},{base}" fill="#8f7f68"/>'
          f'<rect x="{mx - 38}" y="{base - 4}" width="76" height="12" fill="#6e624f"/>')
    s.glow(mx, base - 120, 160, "#ffd27a", 0.12)
    # Zakim on the far left
    deck = HZ - 40
    s.add(f'<rect x="0" y="{deck}" width="300" height="7" fill="#070b18"/>')
    for cx in (60, 230):
        t = deck - 160
        s.add(f'<polygon points="{cx - 20},{deck + 40} {cx - 4},{t} {cx + 4},{t} {cx + 20},{deck + 40} {cx + 11},{deck + 40} {cx},{t + 40} {cx - 11},{deck + 40}" fill="#070b18"/>'
              + "".join(f'<line x1="{cx}" y1="{t + 12}" x2="{cx + k * 20}" y2="{deck}" stroke="#070b18" stroke-width="1.5"/>' for k in range(-6, 7) if k))
    s.flag_us(1080, 110, fw=200, fh=124, pole_h=HZ - 110, amp=9)
    s.water(HZ, "#3b3550", "#070b18", "#c9874a", 60, 0.35)
    for i in range(30):
        s.add(poppy(20 + i * 54 + s.rng.random() * 20, 520 + s.rng.random() * 50, 0.7 + s.rng.random() * 0.5))


def scene_thanksgiving(s):
    """Thanksgiving: a Massachusetts cranberry bog at harvest: the flooded bog red with floating berries,
    growers in waders with the boom, a red barn, autumn trees, pumpkins and corn stalks."""
    s.sky("#5b6fa6", "#f0b07a", "#ffd8a0")
    s.sun(1150, 230, 50, "#fff0c9", "#ffc97a")
    s.clouds([(300, 110, 1.1), (800, 70, 0.8)], "#ffe6cc", 0.7)
    s.hills(330, "#8a6a4a", [(200, 40), (600, 70), (1000, 50), (1400, 80)], 0.8)
    for i in range(50):
        s.tree(s.rng.random() * W, 335 + s.rng.random() * 20, 0.6 + s.rng.random() * 0.5,
               s.rng.choice(["#d9481f", "#e8822a", "#f2b134", "#a8321e", "#7a8a2a"]))
    # red barn
    bx, by = 1240, 360
    s.add(f'<rect x="{bx - 70}" y="{by - 80}" width="140" height="80" fill="#a8261e"/>'
          f'<polygon points="{bx - 80},{by - 80} {bx - 50},{by - 130} {bx + 50},{by - 130} {bx + 80},{by - 80}" fill="#7a1a14"/>'
          f'<rect x="{bx - 24}" y="{by - 52}" width="48" height="52" fill="#f4efe6"/>'
          f'<path d="M{bx - 24},{by - 52} L{bx + 24},{by} M{bx + 24},{by - 52} L{bx - 24},{by}" stroke="#a8261e" stroke-width="4"/>'
          f'<rect x="{bx - 12}" y="{by - 112}" width="24" height="20" fill="#f4efe6"/>')
    s.ground(360, "#6a7a3a", "#8a8a4a")
    # the flooded bog
    s.add(f'<path d="M140,380 L1460,380 L1560,520 L40,520 Z" fill="#7a1420"/>')
    for i in range(1400):
        x = 40 + s.rng.random() * 1520
        y = 380 + s.rng.random() * 140
        lx = 140 - (y - 380) / 140 * 100
        if x < lx or x > W - lx:
            continue
        s.add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{1.5 + (y - 380) / 140 * 3:.1f}" fill="{s.rng.choice(["#c8102e", "#e0263f", "#a00d24", "#ff4a5a"])}"/>')
    # floating boom and growers in waders
    s.add('<path d="M300,470 Q800,420 1300,470" stroke="#ffd23f" stroke-width="7" fill="none"/>')
    for x, y in ((520, 470), (760, 452), (1020, 458)):
        s.add(f'<g transform="translate({x},{y}) scale(1.4)"><rect x="-10" y="-20" width="20" height="24" fill="#1d3a2a"/>'
              f'<path d="M-10,-44 Q0,-48 10,-44 L9,-18 L-9,-18 Z" fill="#e8c43a"/><circle cx="0" cy="-54" r="8" fill="#d8a47a"/>'
              f'<path d="M-12,-60 L12,-60 L8,-66 L-8,-66 Z" fill="#7a3a1a"/>'
              f'<path d="M9,-40 L30,-20 M-9,-40 L-26,-22" stroke="#e8c43a" stroke-width="5" stroke-linecap="round"/></g>')
    s.add(f'<rect x="0" y="520" width="{W}" height="80" fill="{s.vgrad([(0, "#8a7a3a"), (1, "#5a4a24")])}"/>')
    # pumpkins, corn stalks, a turkey
    for x, r in ((220, 34), (290, 24), (1310, 30), (1380, 40), (1450, 22)):
        s.add(f'<ellipse cx="{x}" cy="{560 - r * 0.4:.0f}" rx="{r * 1.2:.0f}" ry="{r:.0f}" fill="#e8741a"/>'
              f'<ellipse cx="{x}" cy="{560 - r * 0.4:.0f}" rx="{r * 0.45:.0f}" ry="{r:.0f}" fill="none" stroke="#c45a10" stroke-width="2"/>'
              f'<rect x="{x - 3}" y="{560 - r * 1.4:.0f}" width="6" height="12" fill="#4a5a1a"/>')
    for x in (90, 130, 1520, 1560):
        s.add(f'<path d="M{x},600 L{x + 4},420" stroke="#c9a44a" stroke-width="6"/>'
              + "".join(f'<path d="M{x + 2},{560 - k * 34} q{24 * (1 if k % 2 else -1)},-10 {40 * (1 if k % 2 else -1)},10" stroke="#d8b45a" stroke-width="5" fill="none"/>' for k in range(5)))
    tx, ty = 1150, 560
    s.add(f'<g transform="translate({tx},{ty})">'
          + "".join(f'<ellipse cx="{-14 + math.cos(math.radians(a)) * 26:.0f}" cy="{-30 + math.sin(math.radians(a)) * 26:.0f}" rx="9" ry="22" '
                    f'fill="{["#a8321e", "#e8822a", "#f2b134"][k % 3]}" transform="rotate({a + 90} {-14 + math.cos(math.radians(a)) * 26:.0f} {-30 + math.sin(math.radians(a)) * 26:.0f})"/>' for k, a in enumerate(range(180, 361, 30)))
          + f'<ellipse cx="0" cy="-20" rx="22" ry="20" fill="#6a3a1a"/><circle cx="14" cy="-42" r="9" fill="#6a3a1a"/>'
          f'<polygon points="22,-44 30,-40 22,-38" fill="#f2b134"/><path d="M18,-38 q4,8 0,12" stroke="#c8102e" stroke-width="4" fill="none"/>'
          f'<path d="M-4,0 L-6,14 M6,0 L8,14" stroke="#f2b134" stroke-width="3"/></g>')
    for _ in range(30):
        s.add(leaf(s.rng.random() * W, s.rng.random() * 330, 0.5 + s.rng.random() * 0.6,
                   s.rng.choice(["#e8822a", "#f2b134", "#c0392b"]), s.rng.random() * 360, 0.85))


def scene_blackfriday(s):
    """Black Friday: Newbury Street brownstone shops at night, gold-lit windows with sale tags,
    shopping bags and gold confetti."""
    s.sky("#000000", "#111111", "#2a2410")
    s.stars(40, 200, 0.4)
    gold = "#facc15"
    x = -10
    i = 0
    while x < W:
        w = 150 + s.rng.random() * 40
        h = 250 + s.rng.random() * 40
        c = s.rng.choice(["#3a2a24", "#2e2420", "#44302a"])
        s.add(f'<rect x="{x:.0f}" y="{430 - h:.0f}" width="{w + 1:.0f}" height="{h:.0f}" fill="{c}"/>'
              f'<rect x="{x - 3:.0f}" y="{430 - h - 8:.0f}" width="{w + 6:.0f}" height="10" fill="#57463c"/>')
        s.windows_grid(x + 14, 430 - h + 16, w - 28, h - 150, 3, 2, "#ffe08a", lit=0.6, ww=26, wh=40)
        # shop window with awning
        sx, sw = x + 18, w - 36
        s.add(f'<rect x="{sx:.0f}" y="350" width="{sw:.0f}" height="74" fill="#ffe7a0"/>'
              f'<rect x="{sx:.0f}" y="350" width="{sw:.0f}" height="74" fill="{s.vgrad([(0, gold, 0.7), (1, "#ff9f1c", 0.3)])}"/>'
              + "".join(f'<path d="M{sx + k * sw / 6:.0f},336 L{sx + (k + 1) * sw / 6:.0f},336 L{sx + (k + 1) * sw / 6:.0f},350 Q{sx + (k + 0.5) * sw / 6:.0f},360 {sx + k * sw / 6:.0f},350 Z" fill="{"#111" if k % 2 else gold}"/>' for k in range(6))
              + f'<g transform="translate({sx + sw / 2:.0f},388) rotate(-8)"><rect x="-52" y="-16" width="104" height="32" rx="4" fill="#111"/>'
              f'<circle cx="-44" cy="0" r="3" fill="{gold}"/>'
              f'<text x="6" y="7" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="18" fill="{gold}">{["SALE", "50% OFF", "SALE", "DEALS"][i % 4]}</text></g>')
        x += w + 4
        i += 1
    s.ground(430, "#0a0a0a", "#1a1a1a")
    s.add(f'<rect x="0" y="430" width="{W}" height="30" fill="#2a2a2a"/>')
    for lx in (200, 620, 1040, 1460):
        s.lamp_post(lx, 470, 150, "#111", "#ffe08a")
    # shopping bags
    for bx, by, sc, col in ((380, 590, 1.3, gold), (470, 600, 1.0, "#ffffff"), (1130, 595, 1.2, "#111"), (1220, 600, 1.5, gold)):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})"><rect x="-30" y="-70" width="60" height="70" fill="{col}" stroke="{gold}" stroke-width="3"/>'
              f'<path d="M-14,-70 Q-14,-94 0,-94 Q14,-94 14,-70" stroke="{gold if col != gold else "#111"}" stroke-width="4" fill="none"/></g>')
    s.confetti(140, [gold, "#ffffff", "#fde68a"], 0, 600, size=(3, 7))


def scene_cybermonday(s):
    """Cyber Monday: MIT's Great Dome at night, circuit traces glowing across the sky, a neon grid."""
    s.sky("#03061a", "#0b2a5c", "#0e7490")
    s.stars(70, 260, 0.7)
    cyan, purple = "#22d3ee", "#a855f7"
    # circuit traces
    for _ in range(26):
        x, y = s.rng.random() * W, s.rng.random() * 300
        pts = [(x, y)]
        for _ in range(4):
            if s.rng.random() < 0.5:
                x += s.rng.choice([-1, 1]) * (40 + s.rng.random() * 120)
            else:
                y += s.rng.choice([-1, 1]) * (20 + s.rng.random() * 60)
            pts.append((x, y))
        col = s.rng.choice([cyan, purple])
        s.add(f'<polyline points="{" ".join(f"{a:.0f},{b:.0f}" for a, b in pts)}" stroke="{col}" stroke-width="2" fill="none" opacity="0.55"/>'
              f'<circle cx="{pts[-1][0]:.0f}" cy="{pts[-1][1]:.0f}" r="4" fill="{col}"/>')
    c, base = 800, 400
    stone = "#cfd8e3"
    s.glow(c, 200, 300, cyan, 0.18)
    s.add(f'<rect x="{c - 300}" y="{base - 130}" width="600" height="130" fill="#9aa6b5"/>'
          f'<rect x="{c - 170}" y="{base - 170}" width="340" height="170" fill="{stone}"/>'
          + "".join(f'<rect x="{c - 150 + k * 33}" y="{base - 150}" width="14" height="140" fill="#eef3f8"/>' for k in range(10))
          + f'<rect x="{c - 176}" y="{base - 182}" width="352" height="16" fill="#eef3f8"/>'
          f'<polygon points="{c - 170},{base - 182} {c},{base - 216} {c + 170},{base - 182}" fill="#dfe6ee"/>'
          f'<rect x="{c - 120}" y="{base - 250}" width="240" height="40" fill="{stone}"/>'
          + "".join(f'<rect x="{c - 108 + k * 24}" y="{base - 244}" width="10" height="28" fill="{cyan}" opacity="0.7"/>' for k in range(10))
          + f'<rect x="{c - 128}" y="{base - 258}" width="256" height="10" fill="#eef3f8"/>'
          f'<path d="M{c - 122},{base - 258} C{c - 110},{base - 318} {c + 110},{base - 318} {c + 122},{base - 258} Z" fill="#b8c4d2"/>'
          f'<path d="M{c - 96},{base - 266} C{c - 80},{base - 300} {c - 40},{base - 308} {c - 10},{base - 310}" stroke="#ffffff" stroke-width="5" fill="none" opacity="0.6"/>'
          f'<rect x="{c - 12}" y="{base - 324}" width="24" height="14" fill="#eef3f8"/>')
    s.windows_grid(c - 290, base - 120, 110, 100, 3, 2, cyan, ww=14, wh=30)
    s.windows_grid(c + 180, base - 120, 110, 100, 3, 2, cyan, ww=14, wh=30)
    # neon perspective grid floor
    s.add(f'<rect x="0" y="{base}" width="{W}" height="{H - base}" fill="{s.vgrad([(0, "#1a0a3a"), (1, "#03061a")])}"/>')
    for k in range(-14, 15):
        s.add(f'<line x1="{c + k * 40}" y1="{base}" x2="{c + k * 200}" y2="{H}" stroke="{purple}" stroke-width="2" opacity="0.55"/>')
    for k in range(9):
        y = base + (k / 8) ** 1.8 * (H - base)
        s.add(f'<line x1="0" y1="{y:.0f}" x2="{W}" y2="{y:.0f}" stroke="{cyan}" stroke-width="2" opacity="0.55"/>')
    # floating code and a lightning bolt
    for x, y, t in ((280, 120, "&lt;/&gt;"), (1300, 160, "{ }"), (420, 300, "01"), (1180, 300, "10")):
        s.add(f'<text x="{x}" y="{y}" font-family="Menlo, monospace" font-size="44" font-weight="700" fill="{cyan}" opacity="0.8">{t}</text>')
    s.add(f'<polygon points="1060,60 1010,150 1050,150 1020,230 1100,120 1058,120 1090,60" fill="#facc15" opacity="0.9"/>')


def scene_hanukkah(s):
    """Hanukkah: a menorah glowing in a Back Bay bay window on the first night, snow falling."""
    s.sky("#06102a", "#14306e", "#3a64b8")
    s.stars(70, 250, 0.8)
    s.moon(1380, 90, 28, "#f2f6ff", 0.6)
    # neighbors
    s.rowhouses(-10, 430, 470, ["#5a3a32", "#6a443a", "#4e322c"], h=(260, 320), window="#ffd98a", lit=0.5, trim="#c9b8a0", stoop=False)
    s.rowhouses(1170, W, 470, ["#5a3a32", "#6a443a", "#4e322c"], h=(260, 320), window="#ffd98a", lit=0.5, trim="#c9b8a0", stoop=False)
    # the brownstone with a bay window
    x0, x1, base = 440, 1160, 470
    s.add(f'<rect x="{x0}" y="60" width="{x1 - x0}" height="{base - 60}" fill="#6b4434"/>'
          f'<rect x="{x0 - 6}" y="52" width="{x1 - x0 + 12}" height="14" fill="#c9b8a0"/>')
    s.windows_grid(x0 + 20, 80, x1 - x0 - 40, 80, 5, 1, "#ffd98a", lit=0.6, ww=50, wh=56)
    bx0, bx1, by0, by1 = 560, 1040, 190, 420
    s.add(f'<polygon points="{bx0 - 30},{by1 + 14} {bx0},{by0 - 14} {bx1},{by0 - 14} {bx1 + 30},{by1 + 14}" fill="#8a5a44"/>'
          f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" fill="{s.vgrad([(0, "#ffcf7a"), (1, "#ffb347")])}"/>'
          f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" fill="none" stroke="#3a2418" stroke-width="10"/>'
          f'<line x1="{bx0 + (bx1 - bx0) / 3}" y1="{by0}" x2="{bx0 + (bx1 - bx0) / 3}" y2="{by1}" stroke="#3a2418" stroke-width="8"/>'
          f'<line x1="{bx0 + 2 * (bx1 - bx0) / 3}" y1="{by0}" x2="{bx0 + 2 * (bx1 - bx0) / 3}" y2="{by1}" stroke="#3a2418" stroke-width="8"/>'
          f'<rect x="{bx0 - 20}" y="{by1 - 4}" width="{bx1 - bx0 + 40}" height="16" fill="#c9b8a0"/>'
          f'<path d="M{bx0 - 22},{by1 - 4} Q{(bx0 + bx1) / 2},{by1 - 18} {bx1 + 22},{by1 - 4} Z" fill="#ffffff"/>')
    s.glow(800, 330, 260, "#ffd27a", 0.35)
    # menorah on the sill: shamash (center, raised) + first candle lit
    c, sill = 800, by1 - 8
    gold = "#e0b33a"
    s.add(f'<rect x="{c - 6}" y="{sill - 120}" width="12" height="120" fill="{gold}"/>'
          f'<ellipse cx="{c}" cy="{sill - 4}" rx="44" ry="8" fill="{gold}"/>')
    for k in range(1, 5):
        for side in (-1, 1):
            x = c + side * k * 26
            s.add(f'<path d="M{c},{sill - 40} Q{x},{sill - 40} {x},{sill - 100}" stroke="{gold}" stroke-width="5" fill="none"/>')
    holders = [c + side * k * 26 for k in range(4, 0, -1) for side in (1,)][:0]
    positions = [c - 104, c - 78, c - 52, c - 26, c + 26, c + 52, c + 78, c + 104]
    for i, x in enumerate(positions):
        s.add(f'<rect x="{x - 4}" y="{sill - 128}" width="8" height="26" fill="#e8eef8"/>')
        if i == 7:  # first night: the rightmost candle
            s.glow(x, sill - 140, 30, "#ffd27a", 0.7)
            s.add(f'<ellipse cx="{x}" cy="{sill - 138}" rx="5" ry="10" fill="#ffe08a"/>')
    s.add(f'<rect x="{c - 5}" y="{sill - 150}" width="10" height="28" fill="#e8eef8"/>')
    s.glow(c, sill - 162, 34, "#ffd27a", 0.8)
    s.add(f'<ellipse cx="{c}" cy="{sill - 160}" rx="6" ry="12" fill="#ffe08a"/>')
    # dreidel and gelt on the sill
    s.add(f'<g transform="translate({bx0 + 70},{sill - 14})"><polygon points="-14,-30 14,-30 14,-6 0,12 -14,-6" fill="#3a64b8"/>'
          f'<rect x="-3" y="-44" width="6" height="14" fill="#3a64b8"/></g>'
          + "".join(f'<circle cx="{bx1 - 80 + k * 18}" cy="{sill - 10}" r="9" fill="#e0b33a" stroke="#b08a20" stroke-width="2"/>' for k in range(3)))
    # stoop, railing, snow
    s.add(f'<rect x="{x0}" y="{base - 30}" width="{x1 - x0}" height="30" fill="#5a3a2c"/>')
    s.ground(base, "#c9d6ea", "#ffffff")
    s.lamp_post(300, 560, 170, "#111", "#ffe08a")
    s.lamp_post(1300, 560, 170, "#111", "#ffe08a")
    s.snow(240, H, 1.0)
    for _ in range(8):
        x, y = s.rng.random() * W, s.rng.random() * 300
        s.add(star(x, y, 8, "#e8eef8", 0.25))


def scene_christmas(s):
    """Christmas: the Boston Common tree (Nova Scotia's yearly gift), Park Street Church's steeple,
    skaters on the Frog Pond, snow."""
    s.sky("#071422", "#16314a", "#3d6680")
    s.stars(70, 250, 0.7)
    s.skyline("#0b1a28", hmin=60, hmax=150, window="#ffd27a", opacity=0.9)
    # Park Street Church
    px = 400
    s.add(f'<rect x="{px - 70}" y="250" width="140" height="160" fill="#7a2e22"/>'
          f'<rect x="{px - 34}" y="170" width="68" height="84" fill="#f4efe6"/>'
          f'<rect x="{px - 26}" y="118" width="52" height="54" fill="#f4efe6"/>'
          f'<rect x="{px - 18}" y="82" width="36" height="38" fill="#f4efe6"/>'
          f'<polygon points="{px - 14},82 {px},-10 {px + 14},82" fill="#f4efe6"/>'
          f'<circle cx="{px}" cy="200" r="14" fill="#16314a" stroke="#d4af37" stroke-width="3"/>')
    s.windows_grid(px - 60, 270, 120, 120, 3, 2, "#ffd98a", arch=True, ww=20, wh=40)
    s.ground(410, "#c9d6ea", "#eef3fb")
    # bare trees with white lights
    for x, h in ((120, 260), (1450, 280), (600, 200), (1060, 210)):
        branches = s.bare_tree(x, 420, h, "#1a2633", depth=5, width=6)
        for _ in range(26):
            bx = x + s.rng.uniform(-h * 0.35, h * 0.35)
            by = 420 - h * 0.3 - s.rng.random() * h * 0.5
            s.add(f'<circle cx="{bx:.0f}" cy="{by:.0f}" r="2.4" fill="#fff6c9"/><circle cx="{bx:.0f}" cy="{by:.0f}" r="7" fill="#fff6c9" opacity="0.2"/>')
    # the tree
    tx, base = 830, 420
    s.glow(tx, 270, 240, "#ffd27a", 0.25)
    s.add(f'<rect x="{tx - 10}" y="{base - 20}" width="20" height="24" fill="#3b2a1f"/>')
    for k in range(5):
        y = base - 20 - k * 58
        w = 150 - k * 28
        s.add(f'<polygon points="{tx - w},{y} {tx},{y - 110} {tx + w},{y}" fill="{["#0f5132", "#14603c", "#187044", "#1c7a4a", "#208554"][k]}"/>')
    for _ in range(120):
        y = base - 25 - s.rng.random() * 290
        half = (y - (base - 330)) / 310 * 150
        if half < 4:
            continue
        x = tx - half + s.rng.random() * 2 * half
        col = s.rng.choice(["#ef4444", "#ffd23f", "#60a5fa", "#ffffff", "#f472b6"])
        s.add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.4" fill="{col}"/><circle cx="{x:.0f}" cy="{y:.0f}" r="8" fill="{col}" opacity="0.18"/>')
    s.glow(tx, base - 336, 50, "#ffd23f", 0.7)
    s.add(star(tx, base - 336, 22, "#ffd23f"))
    # Frog Pond rink with skaters
    s.add(f'<ellipse cx="800" cy="520" rx="560" ry="70" fill="{s.vgrad([(0, "#d8ecff"), (1, "#a8c8e8")])}" stroke="#ffffff" stroke-width="6"/>')
    for x, y, sc, col, arms in ((520, 530, 1.1, "#c81e1e", "wave"), (640, 512, 0.9, "#1e3a8a", "down"), (900, 540, 1.2, "#0f5132", "up"),
                                (1040, 515, 0.95, "#7a2e8a", "wave"), (1180, 532, 1.05, "#d97706", "down"), (760, 548, 0.8, "#c81e1e", "up")):
        s.person(x, y, sc, col, arms)
        s.add(f'<line x1="{x - 10 * sc:.0f}" y1="{y + 2:.0f}" x2="{x + 10 * sc:.0f}" y2="{y + 2:.0f}" stroke="#ccc" stroke-width="2"/>')
    s.lamp_post(240, 600, 170, "#111", "#ffe08a")
    s.lamp_post(1360, 600, 170, "#111", "#ffe08a")
    s.snow(260, H, 1.0)


def scene_newyearseve(s):
    """New Year's Eve / First Night: Trinity Church in Copley Square at midnight, the Hancock tower
    reflecting it, ice sculptures, fireworks."""
    s.sky("#07051a", "#241a55", "#5b3a8a")
    s.stars(60, 250, 0.6)
    for x, y, r, c in ((300, 110, 90, "#f5c542"), (560, 70, 60, "#f472b6"), (1060, 80, 80, "#a78bfa"), (1320, 140, 100, "#f5c542"), (1200, 60, 50, "#ffffff"), (420, 230, 55, "#60a5fa")):
        s.firework(x, y, r, c, 22)
    # Hancock tower with Trinity reflected
    s.add(f'<polygon points="1000,420 1000,30 1070,10 1140,30 1140,420" fill="{s.vgrad([(0, "#6a7ac8"), (1, "#2a2f6a")], x2=1, y2=0)}"/>'
          + "".join(f'<line x1="1000" y1="{40 + k * 22}" x2="1140" y2="{40 + k * 22}" stroke="#8a9ae0" stroke-width="1" opacity="0.4"/>' for k in range(17)))
    c, base = 720, 420
    stone, roof = "#b5745a", "#4a2a3a"
    # Trinity Church: central tower with pyramid roof and turrets, transepts, arched porch
    s.add(f'<rect x="{c - 230}" y="{base - 130}" width="460" height="130" fill="{stone}"/>'
          f'<polygon points="{c - 240},{base - 130} {c - 150},{base - 200} {c - 60},{base - 130}" fill="{roof}"/>'
          f'<polygon points="{c + 60},{base - 130} {c + 150},{base - 200} {c + 240},{base - 130}" fill="{roof}"/>'
          f'<rect x="{c - 90}" y="{base - 270}" width="180" height="150" fill="{stone}"/>'
          f'<polygon points="{c - 100},{base - 270} {c},{base - 380} {c + 100},{base - 270}" fill="{roof}"/>')
    for tx in (c - 90, c + 90):
        s.add(f'<rect x="{tx - 14}" y="{base - 300}" width="28" height="34" fill="{stone}"/>'
              f'<polygon points="{tx - 16},{base - 300} {tx},{base - 340} {tx + 16},{base - 300}" fill="{roof}"/>')
    s.windows_grid(c - 80, base - 250, 160, 70, 4, 1, "#ffcf7a", arch=True, ww=20, wh=46)
    for k in range(3):
        ax = c - 90 + k * 60
        s.add(f'<path d="M{ax},{base} L{ax},{base - 60} A30,30 0 0 1 {ax + 60},{base - 60} L{ax + 60},{base} Z" fill="#2a1424"/>'
              f'<path d="M{ax + 8},{base} L{ax + 8},{base - 56} A22,22 0 0 1 {ax + 52},{base - 56} L{ax + 52},{base} Z" fill="#ffcf7a" opacity="0.6"/>')
    s.windows_grid(c - 220, base - 110, 120, 60, 2, 1, "#ffcf7a", arch=True, ww=18, wh=40)
    s.windows_grid(c + 100, base - 110, 120, 60, 2, 1, "#ffcf7a", arch=True, ww=18, wh=40)
    s.add(f'<g opacity="0.45"><rect x="1010" y="{base - 160}" width="120" height="70" fill="{stone}"/>'
          f'<polygon points="1010,{base - 160} 1070,{base - 210} 1130,{base - 160}" fill="{roof}"/></g>')
    s.skyline("#120c2a", hmin=50, hmax=110, towers=False, window="#ffd27a", x0=1150, x1=W)
    s.skyline("#120c2a", hmin=50, hmax=110, towers=False, window="#ffd27a", x0=0, x1=470)
    # plaza, ice sculptures, crowd with party hats
    s.ground(base, "#1a1236", "#2a1d50")
    for ix, iy, sc in ((300, 560, 1.0), (1290, 560, 1.15)):
        ice = "#bfe6ff"
        s.add(f'<g transform="translate({ix},{iy}) scale({sc})" opacity="0.85">'
              f'<rect x="-50" y="-20" width="100" height="20" fill="{ice}"/>'
              f'<path d="M-30,-20 C-40,-60 -10,-70 0,-60 C10,-100 50,-110 40,-150 C70,-120 50,-80 30,-60 C50,-50 40,-20 20,-20 Z" fill="{ice}"/>'
              f'<path d="M-10,-56 C0,-90 30,-100 34,-140" stroke="#ffffff" stroke-width="3" fill="none" opacity="0.8"/></g>')
        s.glow(ix, iy - 60, 90, "#60a5fa", 0.25)
    for x in range(440, 1180, 34):
        y = 590 + s.rng.random() * 8
        col = s.rng.choice(["#0d0920", "#151030"])
        s.person(x, y, 1.5, col, s.rng.choice(["up", "wave", "down"]),
                 hat=f'<polygon points="-7,-60 7,-60 0,-80" fill="{s.rng.choice(["#f5c542", "#f472b6", "#a78bfa"])}"/>')
    s.confetti(120, ["#f5c542", "#f472b6", "#a78bfa", "#ffffff"], 0, 600, size=(3, 7))


# --------------------------------------------------------------------------------------------
# More holidays
# --------------------------------------------------------------------------------------------

def diya(x, y, s, flame=True):
    out = (f'<g transform="translate({x:.0f},{y:.0f}) scale({s:.2f})">'
           f'<path d="M-22,0 Q0,22 22,0 Q14,-4 0,-4 Q-14,-4 -22,0 Z" fill="#c2581c"/>'
           f'<path d="M-22,0 Q0,22 22,0" stroke="#f5c542" stroke-width="2" fill="none"/>')
    if flame:
        out += ('<circle cx="0" cy="-14" r="22" fill="#ffd27a" opacity="0.22"/>'
                '<path d="M0,-30 Q8,-16 0,-4 Q-8,-16 0,-30 Z" fill="#ffcf3f"/><path d="M0,-22 Q4,-14 0,-6 Q-4,-14 0,-22 Z" fill="#fff6c9"/>')
    return out + "</g>"


def scene_diwali(s):
    """Diwali: diyas floating on the Charles at night below the Boston skyline, marigold garlands,
    sky lanterns, sparklers and a rangoli on the riverbank."""
    s.sky("#0b0420", "#2a0f4a", "#7a2a5a")
    s.stars(70, 260, 0.7)
    for x, y, r, c in ((300, 110, 70, "#ffcf3f"), (1300, 90, 80, "#ff7ab8"), (1080, 170, 50, "#ffffff")):
        s.firework(x, y, r, c, 24)
    # sky lanterns drifting up
    for _ in range(14):
        x, y = 380 + s.rng.random() * 840, 60 + s.rng.random() * 260
        sc = 0.5 + s.rng.random() * 0.6
        s.glow(x, y, 26 * sc, "#ffb347", 0.5)
        s.add(f'<path transform="translate({x:.0f},{y:.0f}) scale({sc:.2f})" d="M-12,-16 L12,-16 L16,14 L-16,14 Z" fill="#ffb347"/>')
    s.skyline("#140a24", y=360, hmin=50, hmax=140, window="#ffcf7a")
    s.water(360, "#3a1a4a", "#0b0420", "#ffcf7a", 70, 0.35)
    for k in range(40):
        x = s.rng.random() * W
        y = 380 + (s.rng.random() ** 1.3) * 120
        s.add(diya(x, y, 0.5 + (y - 380) / 120 * 0.6))
    # rangoli on the bank
    s.add(f'<rect x="0" y="500" width="{W}" height="100" fill="#1a0a24"/>')
    cx, cy = 800, 560
    ring_colors = ["#ff4d6d", "#ffcf3f", "#2ec4b6", "#ff7ab8", "#7b2ff7", "#ff9f1c"]
    for i, r in enumerate((150, 120, 92, 66, 42, 20)):
        n = 12 + i * 2
        s.add(f'<ellipse cx="{cx}" cy="{cy}" rx="{r}" ry="{r * 0.32:.0f}" fill="{ring_colors[i]}"/>')
        for k in range(n):
            a = 2 * math.pi * k / n
            s.add(f'<circle cx="{cx + math.cos(a) * r * 0.92:.0f}" cy="{cy + math.sin(a) * r * 0.29:.0f}" r="{max(2, r * 0.06):.1f}" fill="#fff6c9"/>')
    for x in list(range(560, 650, 30)) + list(range(960, 1050, 30)):
        s.add(diya(x, 590, 1.0))
    # marigold garlands
    for x0, x1 in ((0, 420), (420, 820), (820, 1220), (1220, W)):
        for i in range(26):
            t = i / 25
            x = x0 + (x1 - x0) * t
            y = 20 + 70 * 4 * t * (1 - t)
            s.add(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" fill="{"#ff9f1c" if i % 3 else "#ffcf3f"}"/>')
        for x in (x0 + 20, x1 - 20):
            for k in range(6):
                s.add(f'<circle cx="{x}" cy="{30 + k * 16}" r="7" fill="#ff9f1c"/>')
    # sparkler trails
    for sx, sy in ((260, 470), (1340, 470)):
        for k in range(28):
            a = s.rng.random() * 2 * math.pi
            r = 10 + s.rng.random() * 46
            s.add(f'<line x1="{sx}" y1="{sy}" x2="{sx + math.cos(a) * r:.0f}" y2="{sy + math.sin(a) * r:.0f}" stroke="#fff6c9" stroke-width="1.6" opacity="0.8"/>')
        s.add(f'<line x1="{sx}" y1="{sy}" x2="{sx + 16}" y2="{sy + 70}" stroke="#888" stroke-width="3"/>')


def scene_easter(s):
    """Easter: the Public Garden in spring: swan boats on the lagoon, the little suspension bridge,
    Make Way for Ducklings, tulips, magnolias and hidden eggs."""
    s.sky("#7ec8f0", "#bfe6fb", "#fdf3fb")
    s.clouds([(250, 90, 1.1), (1350, 120, 1.2), (850, 60, 0.7)], "#fff", 0.95)
    s.skyline("#b6c6dd", hmin=50, hmax=150, opacity=0.6)
    # magnolia & cherry trees
    for x, col in ((150, "#ffc4dd"), (330, "#fff0f6"), (1270, "#ffc4dd"), (1450, "#fff0f6")):
        s.add(f'<rect x="{x - 6}" y="250" width="12" height="150" fill="#6b4a3a"/>')
        for _ in range(26):
            a, r = s.rng.random() * 2 * math.pi, s.rng.random() * 80
            s.add(f'<circle cx="{x + math.cos(a) * r:.0f}" cy="{230 + math.sin(a) * r * 0.7:.0f}" r="{16 + s.rng.random() * 14:.0f}" fill="{col}" opacity="0.92"/>')
    s.ground(HZ - 10, "#7cc46a", "#a6dc8a")
    # lagoon
    s.add(f'<ellipse cx="800" cy="470" rx="620" ry="90" fill="{s.vgrad([(0, "#7ec8f0"), (1, "#4a9ac8")])}"/>')
    for _ in range(30):
        x, y = 260 + s.rng.random() * 1080, 400 + s.rng.random() * 140
        s.add(f'<rect x="{x:.0f}" y="{y:.0f}" width="{30 + s.rng.random() * 60:.0f}" height="2" fill="#ffffff" opacity="0.35"/>')
    # lagoon bridge (suspension) across the back
    s.add('<path d="M420,400 Q800,440 1180,400" stroke="#e9e3d6" stroke-width="10" fill="none"/>'
          '<rect x="440" y="340" width="16" height="64" fill="#e9e3d6"/><rect x="1144" y="340" width="16" height="64" fill="#e9e3d6"/>'
          '<path d="M448,340 Q800,420 1152,340" stroke="#555" stroke-width="3" fill="none"/>'
          + "".join(f'<line x1="{x}" y1="{340 + 80 * ((x - 448) / 704) * (1 - (x - 448) / 704) * 4 * 0.9:.0f}" x2="{x}" y2="{400 + 40 * ((x - 420) / 760) * (1 - (x - 420) / 760) * 4 * 0.5:.0f}" stroke="#777" stroke-width="1.5"/>' for x in range(470, 1140, 40)))
    # swan boats
    for bx, by, sc in ((620, 470, 1.0), (1040, 500, 0.85)):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})">'
              f'<path d="M-110,0 L110,0 L96,18 L-100,18 Z" fill="#f4f1ea"/>'
              + "".join(f'<rect x="{-96 + k * 40}" y="-14" width="30" height="14" fill="#2f6b4a"/>' for k in range(5))
              + f'<path d="M80,0 C90,-30 70,-70 90,-90 C104,-104 122,-96 118,-80 C112,-90 100,-90 98,-78 C96,-50 120,-20 110,0 Z" fill="#ffffff" stroke="#d8d4cc" stroke-width="2"/>'
              f'<polygon points="118,-82 132,-78 118,-74" fill="#ff9f1c"/>'
              f'<path d="M70,-6 C40,-40 100,-50 96,-10 Z" fill="#ffffff" stroke="#d8d4cc" stroke-width="2"/></g>')
        s.person(bx - 60 * sc, by - 14 * sc, 0.6 * sc, "#c45a8a", "wave")
        s.person(bx - 20 * sc, by - 14 * sc, 0.6 * sc, "#4a7ac8", "down")
    # Make Way for Ducklings: Mrs. Mallard and eight ducklings in a line on the path
    def duck(x, y, sc, body="#b9a07a"):
        return (f'<g transform="translate({x:.0f},{y:.0f}) scale({sc:.2f})"><ellipse cx="0" cy="0" rx="26" ry="15" fill="{body}"/>'
                f'<circle cx="22" cy="-16" r="11" fill="{body}"/><polygon points="31,-18 44,-14 31,-11" fill="#d98a1a"/>'
                f'<circle cx="25" cy="-19" r="2" fill="#222"/><path d="M-26,-4 l-10,-8 l2,12 z" fill="{body}"/></g>')
    s.add(f'<path d="M0,580 Q800,520 {W},580 L{W},{H} L0,{H} Z" fill="#d8cbb0"/>')
    s.add(duck(1060, 560, 1.4))
    for k in range(8):
        s.add(duck(1000 - k * 52, 566 + (k % 2) * 3, 0.65))
    # tulips and eggs
    for i in range(46):
        x = s.rng.random() * W
        if 300 < x < 1300 and s.rng.random() < 0.85:
            continue
        y = 520 + s.rng.random() * 70
        col = s.rng.choice(["#ff4d6d", "#ffcf3f", "#ff7ab8", "#b388ff", "#ffffff"])
        s.add(f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x:.0f}" y2="{y + 40:.0f}" stroke="#3a8a2c" stroke-width="3"/>'
              f'<path d="M{x - 9:.0f},{y:.0f} L{x - 9:.0f},{y - 16:.0f} L{x - 3:.0f},{y - 10:.0f} L{x:.0f},{y - 18:.0f} L{x + 3:.0f},{y - 10:.0f} L{x + 9:.0f},{y - 16:.0f} L{x + 9:.0f},{y:.0f} Q{x:.0f},{y + 8:.0f} {x - 9:.0f},{y:.0f} Z" fill="{col}"/>')
    for x, y, col in ((200, 560, "#ffb3d1"), (270, 575, "#b3e5ff"), (1340, 565, "#fff3a8"), (1420, 578, "#c9b3ff"), (720, 590, "#b3ffcf")):
        s.add(f'<ellipse cx="{x}" cy="{y}" rx="13" ry="17" fill="{col}"/>'
              f'<path d="M{x - 13},{y} q6,-6 13,0 t13,0" stroke="#ffffff" stroke-width="2.5" fill="none"/>')


def scene_passover(s):
    """Passover: the seder table set under the full spring moon, Back Bay windows behind."""
    s.sky("#0c1430", "#23326a", "#4a5a9a")
    s.stars(60, 240, 0.7)
    s.glow(1180, 120, 160, "#fff6d8", 0.35)
    s.add('<circle cx="1180" cy="120" r="54" fill="#fdf6d8"/><circle cx="1166" cy="108" r="10" fill="#efe6c0" opacity="0.6"/>'
          '<circle cx="1196" cy="134" r="7" fill="#efe6c0" opacity="0.6"/>')
    s.rowhouses(-10, W + 10, 330, ["#4a3040", "#5a3a46", "#3e2a38"], h=(170, 230), window="#ffd98a", lit=0.6, trim="#b8a8b0", stoop=False)
    # window frame we look through
    s.add(f'<rect x="0" y="330" width="{W}" height="{H - 330}" fill="#2a1a24"/>')
    s.add(f'<rect x="0" y="380" width="{W}" height="{H - 380}" fill="{s.vgrad([(0, "#f7f1e6"), (1, "#e6dcc8")])}"/>'
          f'<rect x="0" y="372" width="{W}" height="12" fill="#ffffff"/>')
    s.glow(800, 300, 420, "#ffcf7a", 0.22)
    # candlesticks
    for cx in (520, 600):
        s.add(f'<rect x="{cx - 8}" y="300" width="16" height="80" fill="#d9c27a"/><ellipse cx="{cx}" cy="380" rx="24" ry="7" fill="#c9b06a"/>'
              f'<rect x="{cx - 5}" y="250" width="10" height="52" fill="#fffaf0"/>')
        s.glow(cx, 238, 40, "#ffd27a", 0.7)
        s.add(f'<ellipse cx="{cx}" cy="238" rx="6" ry="12" fill="#ffe08a"/>')
    # seder plate with six items
    px, py = 800, 440
    s.add(f'<ellipse cx="{px}" cy="{py}" rx="170" ry="48" fill="#ffffff" stroke="#3a64b8" stroke-width="5"/>'
          f'<ellipse cx="{px}" cy="{py}" rx="140" ry="38" fill="none" stroke="#3a64b8" stroke-width="2" opacity="0.6"/>')
    items = [("#7cc46a", "karpas"), ("#e8e0c8", "egg"), ("#c96a3a", "shank"), ("#f2f2e6", "maror"), ("#8a5a3a", "charoset"), ("#5a9a4a", "chazeret")]
    for k, (col, _) in enumerate(items):
        a = 2 * math.pi * k / 6 - math.pi / 2
        x, y = px + math.cos(a) * 100, py + math.sin(a) * 26
        s.add(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="28" ry="10" fill="#f0eadc" stroke="#3a64b8" stroke-width="2"/>'
              f'<ellipse cx="{x:.0f}" cy="{y - 4:.0f}" rx="14" ry="8" fill="{col}"/>')
    # matzah stack with cover
    mx, my = 1100, 430
    s.add(f'<rect x="{mx - 70}" y="{my - 10}" width="140" height="40" rx="6" fill="#2a4a8a"/>'
          f'<rect x="{mx - 70}" y="{my - 10}" width="140" height="8" fill="#d4af37"/>'
          + "".join(f'<rect x="{mx - 64 + k * 4}" y="{my - 22 - k * 6}" width="128" height="10" rx="2" fill="#e8c88a" stroke="#c9a462" stroke-width="1"/>' for k in range(3))
          + "".join(f'<circle cx="{mx - 50 + k * 16}" cy="{my - 30}" r="1.6" fill="#b08040"/>' for k in range(7)))
    # wine cups incl. Elijah's cup
    for wx, big in ((380, False), (1260, True), (960, False)):
        sc = 1.4 if big else 1.0
        s.add(f'<g transform="translate({wx},{420}) scale({sc})"><path d="M-18,-60 L18,-60 L12,-24 Q0,-14 -12,-24 Z" fill="#8a1a3a" stroke="#d9c27a" stroke-width="3"/>'
              f'<rect x="-3" y="-24" width="6" height="30" fill="#d9c27a"/><ellipse cx="0" cy="6" rx="16" ry="5" fill="#d9c27a"/></g>')
    # spring flowers
    s.add(f'<g transform="translate(240,380)"><path d="M-30,0 L30,0 L22,-60 L-22,-60 Z" fill="#a8d0f0" opacity="0.8"/>'
          + "".join(f'<line x1="{dx}" y1="-60" x2="{dx * 1.6:.0f}" y2="-130" stroke="#3a8a2c" stroke-width="3"/><circle cx="{dx * 1.6:.0f}" cy="-134" r="12" fill="{c}"/>' for dx, c in ((-16, "#ff9fb8"), (-4, "#ffcf3f"), (8, "#ffffff"), (18, "#ff9fb8")))
          + "</g>")


def scene_eid(s):
    """Eid al-Fitr: the Islamic Society of Boston Cultural Center in Roxbury (its dome and minaret) under
    the new crescent moon, fanous lanterns and lights."""
    s.sky("#0b1a3a", "#1f4a7a", "#e8a86a")
    s.stars(70, 260, 0.8)
    s.moon(1260, 120, 46, "#fdf0c0", 0.62)
    s.add(star(1340, 96, 10, "#fdf0c0"))
    s.skyline("#13203a", hmin=40, hmax=110, window="#ffd27a", towers=False, opacity=0.9)
    c, base = 760, 420
    col, trim, gold = "#c9a87a", "#e8d6b0", "#d4af37"
    # main hall with arched windows
    s.add(f'<rect x="{c - 240}" y="{base - 150}" width="480" height="150" fill="{col}"/>'
          f'<rect x="{c - 248}" y="{base - 158}" width="496" height="12" fill="{trim}"/>')
    s.windows_grid(c - 230, base - 140, 460, 120, 8, 1, "#ffd98a", arch=True, ww=26, wh=84)
    # dome on drum
    s.add(f'<rect x="{c - 90}" y="{base - 210}" width="180" height="56" fill="{trim}"/>'
          + "".join(f'<path d="M{c - 76 + k * 30},{base - 160} L{c - 76 + k * 30},{base - 192} A9,9 0 0 1 {c - 58 + k * 30},{base - 192} L{c - 58 + k * 30},{base - 160} Z" fill="#ffd98a"/>' for k in range(6))
          + f'<path d="M{c - 96},{base - 210} C{c - 96},{base - 320} {c + 96},{base - 320} {c + 96},{base - 210} Z" fill="#2f7a6a"/>'
          f'<path d="M{c - 70},{base - 222} C{c - 60},{base - 280} {c - 20},{base - 296} {c},{base - 298}" stroke="#7ac8b0" stroke-width="5" fill="none" opacity="0.6"/>'
          f'<rect x="{c - 2}" y="{base - 330}" width="4" height="22" fill="{gold}"/>'
          f'<path d="M{c + 8},{base - 344} A12,12 0 1 1 {c + 8},{base - 320} A9,9 0 1 0 {c + 8},{base - 344} Z" fill="{gold}"/>')
    # minaret
    mx = c + 300
    s.add(f'<rect x="{mx - 18}" y="{base - 330}" width="36" height="330" fill="{col}"/>'
          f'<rect x="{mx - 28}" y="{base - 250}" width="56" height="12" fill="{trim}"/>'
          f'<rect x="{mx - 26}" y="{base - 340}" width="52" height="14" fill="{trim}"/>'
          f'<path d="M{mx - 18},{base - 340} C{mx - 18},{base - 380} {mx},{base - 396} {mx},{base - 404} C{mx},{base - 396} {mx + 18},{base - 380} {mx + 18},{base - 340} Z" fill="#2f7a6a"/>'
          + "".join(f'<path d="M{mx - 8},{base - 236 + k * 60} L{mx - 8},{base - 210 + k * 60} L{mx + 8},{base - 210 + k * 60} L{mx + 8},{base - 236 + k * 60} A8,8 0 0 0 {mx - 8},{base - 236 + k * 60} Z" fill="#ffd98a"/>' for k in range(3)))
    s.ground(base, "#1a2238", "#2a3450")
    s.add(f'<rect x="0" y="{base}" width="{W}" height="14" fill="#3a4460"/>')
    # fanous lanterns hanging from the top
    def fanous(x, y, sc, color):
        return (f'<g transform="translate({x:.0f},{y:.0f}) scale({sc:.2f})"><line x1="0" y1="-80" x2="0" y2="-34" stroke="{gold}" stroke-width="2"/>'
                f'<circle cx="0" cy="0" r="50" fill="{color}" opacity="0.15"/>'
                f'<polygon points="-10,-34 10,-34 18,-22 -18,-22" fill="{gold}"/>'
                f'<polygon points="-18,-22 18,-22 22,14 -22,14" fill="{color}" stroke="{gold}" stroke-width="3"/>'
                f'<line x1="0" y1="-22" x2="0" y2="14" stroke="{gold}" stroke-width="2"/>'
                f'<polygon points="-22,14 22,14 10,30 -10,30" fill="{gold}"/><circle cx="0" cy="36" r="5" fill="{gold}"/></g>')
    for x, y, sc, colr in ((140, 120, 1.0, "#ff9f43"), (300, 90, 0.8, "#2ec4b6"), (460, 140, 0.7, "#ff6b9a"), (1300, 130, 0.9, "#2ec4b6"), (1460, 100, 1.1, "#ff9f43")):
        s.add(fanous(x, y, sc, colr))
    s.string_lights(0, 30, 800, 20, 30, ["#ffe08a", "#ffffff"])
    s.string_lights(800, 20, W, 30, 30, ["#ffe08a", "#ffffff"])
    s.crowd(80, 520, 560, 1.7, ["#2f7a6a", "#c96a3a", "#3a64b8", "#8a3a6a", "#d4af37"], arms=("wave", "down", "up"))
    s.crowd(1080, 1540, 560, 1.7, ["#2f7a6a", "#c96a3a", "#3a64b8", "#8a3a6a", "#d4af37"], arms=("wave", "down", "up"))


def scene_mothers(s):
    """Mother's Day: Lilac Sunday at the Arnold Arboretum (held on Mother's Day): lilac bushes on
    rolling hills, families picnicking, petals in the air."""
    s.sky("#8fb8f0", "#cfe0fb", "#fff0f6")
    s.clouds([(260, 100, 1.1), (1320, 80, 1.3)], "#fff", 0.95)
    s.hills(340, "#9cc98a", [(250, 80), (700, 120), (1150, 90), (1500, 110)])
    s.hills(400, "#7cb86a", [(100, 60), (600, 40), (1000, 70), (1450, 50)])
    lilac = ["#b388e8", "#9b6fd8", "#d6b8f5", "#c49ae8", "#ffffff", "#e8d0ff"]
    for _ in range(26):
        x = s.rng.random() * W
        y = 330 + s.rng.random() * 90
        sc = 0.6 + (y - 330) / 90 * 0.7
        s.add(f'<g transform="translate({x:.0f},{y:.0f}) scale({sc:.2f})">'
              + "".join(f'<ellipse cx="{s.rng.uniform(-60, 60):.0f}" cy="{s.rng.uniform(-60, 0):.0f}" rx="26" ry="22" fill="#5a8a4a"/>' for _ in range(5))
              + "".join(f'<ellipse cx="{s.rng.uniform(-60, 60):.0f}" cy="{s.rng.uniform(-80, -10):.0f}" rx="9" ry="18" fill="{s.rng.choice(lilac)}"/>' for _ in range(16))
              + "</g>")
    s.ground(470, "#6aa85a", "#86c070")
    # picnic blanket with a mom and kids
    bx, by = 800, 520
    s.add(f'<polygon points="{bx - 170},{by} {bx + 150},{by - 20} {bx + 200},{by + 50} {bx - 140},{by + 70}" fill="#ffffff"/>'
          + "".join(f'<line x1="{bx - 170 + k * 34}" y1="{by - k * 2}" x2="{bx - 140 + k * 34}" y2="{by + 70 - k * 2}" stroke="#ff8fab" stroke-width="10" opacity="0.7"/>' for k in range(10))
          + f'<rect x="{bx + 70}" y="{by - 30}" width="60" height="40" rx="8" fill="#c48a4a"/><path d="M{bx + 76},{by - 30} Q{bx + 100},{by - 60} {bx + 124},{by - 30}" stroke="#8a5a2a" stroke-width="4" fill="none"/>')
    s.person(bx - 60, by + 30, 1.5, "#c45a8a", "wave")
    s.person(bx - 10, by + 36, 1.0, "#4a7ac8", "up")
    s.person(bx + 30, by + 34, 0.9, "#ffb703", "up")
    # flowers bouquet with bow
    s.add(f'<g transform="translate({bx - 120},{by + 10})">'
          + "".join(f'<line x1="0" y1="0" x2="{dx}" y2="-50" stroke="#3a8a2c" stroke-width="3"/><circle cx="{dx}" cy="-56" r="10" fill="{c}"/>' for dx, c in ((-20, "#ff7ab8"), (-6, "#ffcf3f"), (8, "#b388e8"), (22, "#ff4d6d")))
          + '<path d="M-10,-10 l-14,-8 l0,16 z M10,-10 l14,-8 l0,16 z" fill="#ff4d6d"/></g>')
    for _ in range(46):
        s.add(f'<ellipse cx="{s.rng.random() * W:.0f}" cy="{s.rng.random() * 420:.0f}" rx="4" ry="7" fill="{s.rng.choice(lilac)}" '
              f'transform="rotate({s.rng.random() * 180:.0f})" opacity="0.8"/>')
    for k in range(12):
        s.add(heart(200 + s.rng.random() * 1200, 60 + s.rng.random() * 220, 0.6 + s.rng.random() * 0.5, s.rng.choice(["#ff7ab8", "#ffffff", "#b388e8"]), 0.7))


def scene_fathers(s):
    """Father's Day: a summer evening on the Charles: a parent and kid sailing past the Esplanade,
    the Back Bay skyline, the Longfellow Bridge."""
    s.sky("#2a6fb0", "#86c0e8", "#ffd8a0")
    s.sun(1240, 300, 60, "#fff0c2", "#ffcf7a")
    s.clouds([(300, 110, 1.2), (900, 70, 0.8)], "#fff", 0.85)
    s.skyline("#3a4a6a", y=360, hmin=50, hmax=150, window="#ffe7a8", opacity=0.9)
    s.add(f'<rect x="0" y="352" width="{W}" height="14" fill="#4a7a4a"/>')
    for x in range(40, W, 140):
        s.tree(x, 360, 0.7, "#3a6a3a")
    s.water(366, "#5a9ac8", "#1a4a7a", "#ffffff", 70, 0.4)
    s.add(f'<rect x="1160" y="376" width="140" height="210" fill="{s.vgrad([(0, "#ffe7a8", 0.6), (1, "#ffe7a8", 0)])}"/>')
    # other boats
    for bx, by, sc, sail in ((300, 420, 0.7, "#ffffff"), (520, 400, 0.5, "#ffd166"), (1420, 410, 0.6, "#ffffff"), (1100, 395, 0.45, "#ff8fab")):
        s.add(f'<g transform="translate({bx},{by}) scale({sc})"><path d="M-40,0 L40,0 L32,10 L-34,10 Z" fill="#1d3557"/>'
              f'<rect x="-1" y="-80" width="3" height="80" fill="#333"/><polygon points="3,-76 3,-6 44,-6" fill="{sail}"/></g>')
    # the hero boat: parent and kid
    bx, by = 800, 520
    s.add(f'<g transform="translate({bx},{by}) scale(1.8)">'
          f'<path d="M-80,0 L80,0 L66,18 L-70,18 Z" fill="#ffffff" stroke="#1d3557" stroke-width="2"/>'
          f'<rect x="-80" y="0" width="160" height="5" fill="#e63946"/>'
          f'<rect x="-2" y="-150" width="4" height="150" fill="#333"/>'
          f'<polygon points="3,-146 3,-8 90,-8" fill="#f4f1ea" stroke="#ccc"/>'
          f'<polygon points="-3,-130 -3,-8 -60,-8" fill="#4dabf7"/>'
          f'<line x1="-3" y1="-8" x2="90" y2="-8" stroke="#333" stroke-width="2"/></g>')
    s.person(bx - 70, by, 1.5, "#1d3557", "wave",
             hat='<rect x="-10" y="-66" width="20" height="6" fill="#e63946"/><rect x="-7" y="-72" width="14" height="8" rx="3" fill="#e63946"/>')
    s.person(bx + 70, by, 1.0, "#ffb703", "up")
    s.add(f'<path d="M{bx - 160},{by + 40} q30,10 60,0 t60,0 t60,0 t60,0 t60,0" stroke="#ffffff" stroke-width="3" fill="none" opacity="0.6"/>')
    for _ in range(6):
        x, y = 200 + s.rng.random() * 1200, 80 + s.rng.random() * 160
        s.add(f'<path d="M{x - 10:.0f},{y:.0f} q5,-6 10,0 q5,-6 10,0" stroke="#ffffff" stroke-width="2.5" fill="none"/>')


def scene_earthday(s):
    """Earth Day: the Earth rising over the Emerald Necklace: neighbors planting trees, bikes,
    a community garden and the Charles in the distance."""
    s.sky("#6ec6f0", "#b9e8fb", "#f0fbf0")
    cx, cy, r = 800, 330, 150
    s.glow(cx, cy, r * 2.2, "#ffffff", 0.5)
    s.add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#3a8ad8"/>'
          f'<path d="M{cx - 110},{cy - 70} C{cx - 60},{cy - 120} {cx - 10},{cy - 90} {cx - 20},{cy - 40} C{cx - 30},{cy} {cx - 80},{cy + 20} {cx - 120},{cy - 10} Z" fill="#5ac46a"/>'
          f'<path d="M{cx + 10},{cy - 130} C{cx + 70},{cy - 120} {cx + 120},{cy - 60} {cx + 100},{cy - 10} C{cx + 80},{cy + 30} {cx + 30},{cy + 10} {cx + 20},{cy - 40} C{cx + 10},{cy - 70} {cx - 10},{cy - 100} {cx + 10},{cy - 130} Z" fill="#5ac46a"/>'
          f'<path d="M{cx - 40},{cy + 40} C{cx},{cy + 30} {cx + 40},{cy + 70} {cx + 10},{cy + 120} C{cx - 20},{cy + 130} {cx - 60},{cy + 90} {cx - 40},{cy + 40} Z" fill="#5ac46a"/>'
          f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#ffffff" stroke-width="4" opacity="0.5"/>'
          f'<path d="M{cx - 120},{cy - 60} A{r - 10},{r - 10} 0 0 1 {cx - 20},{cy - 138}" stroke="#ffffff" stroke-width="10" fill="none" opacity="0.25"/>')
    s.clouds([(260, 110, 1.1), (1340, 140, 1.2)], "#fff", 0.95)
    s.hills(400, "#4caf6a", [(200, 60), (500, 40), (1100, 50), (1400, 70)])
    for i in range(30):
        s.tree(s.rng.random() * W, 400 + s.rng.random() * 20, 0.7 + s.rng.random() * 0.5, s.rng.choice(["#2e8b57", "#3aa860", "#228b4a"]))
    s.ground(430, "#5cb85c", "#7cd07c")
    # winding path with bikes
    s.add(f'<path d="M0,520 C400,470 600,560 900,500 S1400,470 {W},500 L{W},540 C1400,510 1200,560 900,540 S400,520 0,560 Z" fill="#d8cbb0"/>')
    def bike(x, y, sc, col):
        return (f'<g transform="translate({x},{y}) scale({sc})" stroke="{col}" stroke-width="3" fill="none">'
                f'<circle cx="-22" cy="0" r="14"/><circle cx="22" cy="0" r="14"/><path d="M-22,0 L-6,-22 L16,-22 L22,0 M-6,-22 L0,0 L16,-22 M-10,-28 L0,-28 M14,-26 L20,-30"/></g>')
    s.add(bike(380, 510, 1.3, "#1d3557"), bike(1180, 500, 1.3, "#e63946"))
    s.person(380, 486, 1.0, "#1d3557", "down")
    s.person(1180, 476, 1.0, "#e63946", "down")
    # planting a tree
    for px, kid in ((620, False), (720, True)):
        s.person(px, 580, 1.0 if kid else 1.5, "#ff9f1c" if kid else "#2a6f4a", "wave")
    s.add('<rect x="666" y="520" width="6" height="60" fill="#6b4a3a"/><circle cx="669" cy="510" r="22" fill="#3aa860"/>'
          '<path d="M640,582 Q669,566 700,582 Z" fill="#6b4a3a"/>'
          '<path d="M760,590 L790,540 M784,538 l12,-4 l-4,12 z" stroke="#777" stroke-width="4" fill="#777"/>')
    # garden boxes
    for gx in (1000, 1080):
        s.add(f'<rect x="{gx}" y="560" width="70" height="26" fill="#8a5a3a"/>'
              + "".join(f'<circle cx="{gx + 10 + k * 16}" cy="556" r="9" fill="#4caf50"/>' for k in range(4)))
    for _ in range(10):
        s.add(leaf(s.rng.random() * W, 60 + s.rng.random() * 300, 0.6, "#5ac46a", s.rng.random() * 360, 0.8))


def scene_piday(s):
    """Pi Day: a chalkboard night over the Charles, digits of pi arcing across the sky, the Harvard
    Bridge with its smoot marks (364.4 smoots and an ear), MIT's dome, and a pie for a moon."""
    s.sky("#1c3a2e", "#244a3a", "#2e5a46")
    digits = "3.14159265358979323846264338327950288419716939937510582097494459230781640628620899862803482534211706798214808651"
    for i, ch in enumerate(digits):
        t = i / len(digits)
        x = 60 + t * 1480
        y = 230 - math.sin(t * math.pi) * 170 + math.sin(t * 20) * 6
        s.add(f'<text x="{x:.0f}" y="{y:.0f}" font-family="Chalkboard, Comic Sans MS, Marker Felt, sans-serif" font-size="{22 + 10 * math.sin(t * math.pi):.0f}" '
              f'fill="#f4f1e6" opacity="{0.55 + 0.4 * math.sin(t * math.pi):.2f}" text-anchor="middle">{ch}</text>')
    # chalk doodles: a circle with its radius, and C = 2πr
    s.add('<circle cx="250" cy="300" r="60" fill="none" stroke="#f4f1e6" stroke-width="3" opacity="0.6" stroke-dasharray="6 4"/>'
          '<line x1="250" y1="300" x2="310" y2="300" stroke="#f4f1e6" stroke-width="3" opacity="0.6"/>'
          '<text x="268" y="292" font-family="Chalkboard, Comic Sans MS, sans-serif" font-size="20" fill="#f4f1e6" opacity="0.7">r</text>'
          '<text x="1300" y="330" font-family="Chalkboard, Comic Sans MS, sans-serif" font-size="34" fill="#f4f1e6" opacity="0.7">C = 2πr</text>')
    # the pie moon
    px, py, pr = 1240, 110, 64
    s.glow(px, py, pr * 2.2, "#ffd27a", 0.3)
    s.add(f'<circle cx="{px}" cy="{py}" r="{pr}" fill="#d9a05a"/><circle cx="{px}" cy="{py}" r="{pr - 10}" fill="#e8b878"/>'
          + "".join(f'<circle cx="{px + math.cos(a) * (pr - 5):.0f}" cy="{py + math.sin(a) * (pr - 5):.0f}" r="6" fill="#c98a4a"/>' for a in [k * 0.3927 for k in range(16)])
          + f'<text x="{px}" y="{py + 22}" font-family="Georgia, serif" font-size="62" font-weight="700" fill="#a0602a" text-anchor="middle">π</text>')
    # Cambridge bank: MIT dome
    s.add(f'<rect x="0" y="330" width="{W}" height="30" fill="#162a22"/>')
    c = 1360
    s.add(f'<rect x="{c - 120}" y="270" width="240" height="70" fill="#4a5a52"/>'
          f'<rect x="{c - 60}" y="232" width="120" height="40" fill="#5a6a62"/>'
          f'<path d="M{c - 64},232 C{c - 60},190 {c + 60},190 {c + 64},232 Z" fill="#6a7a72"/>')
    s.water(360, "#1e4a3a", "#0e2a20", "#f4f1e6", 50, 0.25)
    # Harvard Bridge with smoot marks
    s.add(f'<rect x="0" y="400" width="{W}" height="22" fill="#5a6a62"/><rect x="0" y="396" width="{W}" height="6" fill="#7a8a82"/>')
    for k, x in enumerate(range(0, W, 120)):
        s.add(f'<path d="M{x},{422} A60,30 0 0 1 {x + 120},{422}" fill="none" stroke="#5a6a62" stroke-width="8"/>'
              f'<rect x="{x - 6}" y="422" width="12" height="80" fill="#4a5a52"/>')
    for k in range(0, 365, 10):
        x = 40 + k * 4.2
        s.add(f'<line x1="{x:.0f}" y1="402" x2="{x:.0f}" y2="412" stroke="#f4f1e6" stroke-width="2"/>'
              + (f'<text x="{x:.0f}" y="392" font-family="Chalkboard, Comic Sans MS, sans-serif" font-size="13" fill="#f4f1e6" text-anchor="middle">{k}</text>' if k % 50 == 0 else ""))
    s.add('<text x="1590" y="452" font-family="Chalkboard, Comic Sans MS, sans-serif" font-size="18" fill="#ffd27a" text-anchor="end">364.4 smoots + 1 ear</text>')
    s.person(700, 396, 0.9, "#0e2a20", "wave")
    s.person(740, 396, 0.9, "#0e2a20", "down")
    s.add(f'<rect x="0" y="502" width="{W}" height="{H - 502}" fill="#0e2a20"/>'
          f'<rect x="0" y="502" width="{W}" height="6" fill="#c9a87a"/>')
    s.add('<g transform="translate(800,560)"><path d="M-90,0 L90,0 L76,30 L-76,30 Z" fill="#e8d6b0"/>'
          '<path d="M-90,0 Q0,-36 90,0 Z" fill="#d9a05a"/><text x="0" y="-4" font-family="Georgia, serif" font-size="30" font-weight="700" fill="#8a4a1a" text-anchor="middle">π</text></g>')


def scene_bunkerhill(s):
    """Bunker Hill Day (June 17, a Suffolk County holiday): the Charlestown parade on a sunny
    morning: the monument, fife and drum corps, bunting on the rowhouses."""
    s.sky("#3a8ad8", "#9cccf5", "#eaf6ff")
    s.clouds([(250, 100, 1.1), (1350, 90, 1.2)], "#fff", 0.95)
    s.hills(360, "#5aa060", [(500, 40), (800, 120), (1100, 40)])
    mx, top, base = 800, 50, 250
    s.add(f'<polygon points="{mx - 34},{base} {mx - 20},{top + 28} {mx},{top} {mx + 20},{top + 28} {mx + 34},{base}" fill="#d8ccb4"/>'
          f'<polygon points="{mx},{top} {mx + 20},{top + 28} {mx + 34},{base} {mx + 4},{base}" fill="#b8aa90"/>'
          f'<rect x="{mx - 50}" y="{base - 4}" width="100" height="14" fill="#a89a80"/>')
    brick = ["#a8452e", "#b8553a", "#98402a"]
    s.rowhouses(-10, 600, 440, brick, h=(160, 220), window="#e8f0ff", lit=1.0, trim="#f1e6d2")
    s.rowhouses(1000, W + 10, 440, brick, h=(160, 220), window="#e8f0ff", lit=1.0, trim="#f1e6d2")
    for x in (60, 230, 400, 1060, 1230, 1400):
        s.bunting_fan(x + 40, 300, 34)
    s.ground(440, "#6a6f7a", "#8a909c")
    # fife & drum corps in tricorns
    tric = '<path d="M-14,-62 L14,-62 L10,-70 L0,-66 L-10,-70 Z" fill="#111"/>'
    for i, x in enumerate(range(620, 1000, 64)):
        y = 520 + (i % 2) * 6
        s.person(x, y, 1.4, "#1e3a8a", "down", hat=tric)
        if i % 2 == 0:
            s.add(f'<g transform="translate({x},{y - 30})"><rect x="-14" y="-6" width="28" height="22" fill="#b22234" stroke="#f1e6d2" stroke-width="2"/>'
                  f'<path d="M-14,-6 L0,16 L14,-6" stroke="#f1e6d2" stroke-width="2" fill="none"/></g>')
        else:
            s.add(f'<line x1="{x + 4}" y1="{y - 70}" x2="{x + 34}" y2="{y - 78}" stroke="#e8d6b0" stroke-width="4"/>')
    # colonial flags carried at the front
    for fx, colr in ((640, "#b22234"), (980, "#ffffff")):
        s.add(f'<rect x="{fx}" y="380" width="4" height="140" fill="#6b4a3a"/>'
              f'<path d="M{fx + 4},382 q30,-6 60,0 l0,40 q-30,-6 -60,0 z" fill="{colr}" stroke="#ccc"/>')
    s.add('<path d="M984,382 q30,-6 60,0 l0,40 q-30,-6 -60,0 z" fill="#ffffff"/><rect x="984" y="382" width="24" height="18" fill="#b22234"/>'
          '<path d="M996,390 l0,30" stroke="#2e7d32" stroke-width="3"/>')
    s.crowd(0, 580, 600, 1.7, ["#b22234", "#1e3a8a", "#f1e6d2", "#555"], arms=("wave", "up", "down"))
    s.crowd(1020, W, 600, 1.7, ["#b22234", "#1e3a8a", "#f1e6d2", "#555"], arms=("wave", "up", "down"))
    s.confetti(60, ["#b22234", "#1e3a8a", "#ffffff"], 0, 380, size=(3, 7))


def scene_teaparty(s):
    """Boston Tea Party anniversary (Dec 16, 1773): the Beaver brig at the Congress Street Bridge at
    night, lanterns, tea chests splashing into the harbor."""
    s.sky("#070b1a", "#16234a", "#2a3a6a")
    s.stars(80, 260, 0.8)
    s.moon(300, 100, 34, "#f2f6ff", 0.6)
    s.skyline("#0a1024", y=340, hmin=60, hmax=160, window="#ffd27a", opacity=0.9)
    s.water(340, "#1a2a50", "#050814", "#ffd27a", 60, 0.3)
    # Congress Street Bridge
    s.add(f'<rect x="0" y="330" width="{W}" height="12" fill="#2a2f40"/>'
          + "".join(f'<rect x="{x}" y="342" width="14" height="40" fill="#2a2f40"/>' for x in range(30, W, 180)))
    # the brig
    bx, by = 820, 470
    hull = "#3a2418"
    s.add(f'<path d="M{bx - 300},{by - 40} L{bx + 280},{by - 40} L{bx + 330},{by - 80} L{bx + 250},{by + 20} L{bx - 260},{by + 20} Z" fill="{hull}"/>'
          f'<rect x="{bx - 290}" y="{by - 44}" width="560" height="8" fill="#c9a462"/>'
          + "".join(f'<rect x="{bx - 250 + k * 60}" y="{by - 24}" width="18" height="12" fill="#ffd27a" opacity="0.8"/>' for k in range(9)))
    for mx, h in ((bx - 140, 300), (bx + 110, 330)):
        s.add(f'<rect x="{mx - 4}" y="{by - 40 - h}" width="8" height="{h}" fill="{hull}"/>')
        for k, (yy, w) in enumerate(((by - 40 - h + 30, 70), (by - 40 - h + 110, 100), (by - 40 - h + 200, 120))):
            s.add(f'<line x1="{mx - w}" y1="{yy}" x2="{mx + w}" y2="{yy}" stroke="{hull}" stroke-width="5"/>'
                  f'<path d="M{mx - w + 6},{yy + 4} L{mx + w - 6},{yy + 4} L{mx + w - 14},{yy + 70 - k * 4} L{mx - w + 14},{yy + 70 - k * 4} Z" fill="#e8dfc8" opacity="0.35"/>')
        s.add(f'<line x1="{mx}" y1="{by - 40 - h}" x2="{bx - 300}" y2="{by - 40}" stroke="{hull}" stroke-width="1.5"/>'
              f'<line x1="{mx}" y1="{by - 40 - h}" x2="{bx + 330}" y2="{by - 80}" stroke="{hull}" stroke-width="1.5"/>')
    s.add(f'<path d="M{bx + 114},{by - 370} l40,6 l-40,8 z" fill="#b22234"/>')
    # lanterns on deck
    for lx in (bx - 260, bx, bx + 240):
        s.glow(lx, by - 64, 40, "#ffd27a", 0.6)
        s.add(f'<rect x="{lx - 6}" y="{by - 74}" width="12" height="18" fill="#ffd27a" stroke="#111" stroke-width="2"/>')
    # patriots heaving chests
    for px, arms in ((bx - 200, "up"), (bx - 60, "up"), (bx + 60, "wave"), (bx + 180, "up")):
        s.person(px, by - 44, 1.2, "#120a06", arms,
                 hat='<path d="M-12,-62 L12,-62 L9,-69 L0,-65 L-9,-69 Z" fill="#120a06"/>')
    def chest(x, y, rot, sc=1.0):
        return (f'<g transform="translate({x:.0f},{y:.0f}) rotate({rot:.0f}) scale({sc:.2f})"><rect x="-22" y="-18" width="44" height="36" fill="#8a5a2a" stroke="#4a2a10" stroke-width="3"/>'
                f'<line x1="-22" y1="0" x2="22" y2="0" stroke="#4a2a10" stroke-width="2"/>'
                f'<text x="0" y="-4" font-family="Georgia, serif" font-size="11" fill="#2a1a08" text-anchor="middle">TEA</text></g>')
    s.add(chest(bx - 200, by - 140, -20), chest(bx - 330, by - 60, 30), chest(bx + 330, by - 20, -40), chest(bx + 380, by + 40, 20, 0.9))
    for sx, sy in ((bx - 360, by + 40), (bx + 390, by + 70), (bx - 120, by + 70)):
        for k in range(10):
            a = math.pi + math.pi * k / 9
            s.add(f'<path d="M{sx},{sy} q{math.cos(a) * 20:.0f},{-30 - k % 3 * 10} {math.cos(a) * 40:.0f},{-10}" stroke="#bfe0ff" stroke-width="3" fill="none" opacity="0.8"/>')
        s.add(f'<ellipse cx="{sx}" cy="{sy}" rx="50" ry="10" fill="#bfe0ff" opacity="0.35"/>')
    # floating tea leaves
    for _ in range(40):
        s.add(f'<ellipse cx="{s.rng.random() * W:.0f}" cy="{500 + s.rng.random() * 100:.0f}" rx="5" ry="2.5" fill="#5a7a3a" opacity="0.7" transform="rotate({s.rng.random() * 180:.0f})"/>')


def scene_pride(s):
    """Pride Month kickoff: the Zakim Bridge lit in rainbow over a celebrating crowd, flags waving,
    rainbow confetti."""
    s.sky("#1a1040", "#3a2a7a", "#7a5aba")
    s.stars(60, 220, 0.6)
    rainbow = ["#e40303", "#ff8c00", "#ffed00", "#008026", "#24408e", "#732982"]
    s.skyline("#140c30", y=380, hmin=50, hmax=150, window="#ffd27a", opacity=0.85)
    # Zakim: two inverted-Y towers, rainbow fan cables
    deck = 360
    s.add(f'<rect x="120" y="{deck}" width="1360" height="14" fill="#e8e6f0"/>')
    for cx in (480, 1120):
        top = deck - 280
        s.add(f'<polygon points="{cx - 40},{deck + 60} {cx - 6},{top} {cx + 6},{top} {cx + 40},{deck + 60} {cx + 22},{deck + 60} {cx},{top + 70} {cx - 22},{deck + 60}" fill="#e8e6f0"/>'
              f'<polygon points="{cx - 6},{top} {cx},{top - 30} {cx + 6},{top}" fill="#e8e6f0"/>')
        for k in range(1, 13):
            col = rainbow[(k - 1) % 6]
            for side in (-1, 1):
                s.add(f'<line x1="{cx}" y1="{top + 10 + k * 6}" x2="{cx + side * k * 28}" y2="{deck}" stroke="{col}" stroke-width="2.6"/>')
        s.glow(cx, top + 60, 140, "#ff7ab8", 0.18)
    s.water(400, "#2a1a5a", "#0a0620", "#ff7ab8", 50, 0.3)
    for i, col in enumerate(rainbow):
        s.add(f'<rect x="{440 + i * 120}" y="410" width="80" height="120" fill="{col}" opacity="0.10"/>')
    # crowd with flags
    s.add(f'<rect x="0" y="520" width="{W}" height="80" fill="#0a0620"/>')
    for i, x in enumerate(range(20, W, 46)):
        y = 600 + (i % 3) * 4
        s.person(x, y, 1.6, ["#1a1040", "#22184a"][i % 2], ["up", "wave", "down", "up"][i % 4])
        if i % 4 == 0:
            s.add(f'<rect x="{x + 16}" y="{y - 150}" width="3" height="80" fill="#ccc"/>'
                  + "".join(f'<rect x="{x + 19}" y="{y - 150 + k * 7}" width="44" height="7" fill="{c}"/>' for k, c in enumerate(rainbow)))
    s.confetti(160, rainbow + ["#ffffff", "#f5a9b8", "#5bcefa"], 0, 560, size=(3, 7))


def scene_openingday(s):
    """Opening Day at Fenway: the Green Monster, the Citgo sign, bunting on the grandstand, a crowd,
    the field in spring sunshine."""
    s.sky("#2f80d0", "#8fc4f5", "#e8f4ff")
    s.clouds([(260, 90, 1.1), (1350, 110, 1.2)], "#fff", 0.95)
    # Citgo sign over the Monster
    sx, sy = 1180, 60
    s.add(f'<rect x="{sx - 4}" y="{sy + 120}" width="8" height="120" fill="#555"/><rect x="{sx + 110}" y="{sy + 120}" width="8" height="120" fill="#555"/>'
          f'<rect x="{sx - 20}" y="{sy}" width="160" height="124" fill="#ffffff" stroke="#999" stroke-width="2"/>'
          f'<polygon points="{sx + 60},{sy + 14} {sx + 100},{sy + 54} {sx + 60},{sy + 94} {sx + 20},{sy + 54}" fill="#e31b23"/>'
          f'<polygon points="{sx + 60},{sy + 34} {sx + 80},{sy + 54} {sx + 60},{sy + 74} {sx + 40},{sy + 54}" fill="#ffffff"/>'
          f'<rect x="{sx + 10}" y="{sy + 102}" width="100" height="12" rx="3" fill="#0a2a6a"/>')
    # light towers
    for lx in (220, 1460):
        s.add(f'<rect x="{lx - 4}" y="90" width="8" height="250" fill="#9aa"/><rect x="{lx - 40}" y="70" width="80" height="34" fill="#cfd8dc" stroke="#9aa" stroke-width="2"/>'
              + "".join(f'<circle cx="{lx - 30 + k * 15}" cy="{80 + r * 14}" r="5" fill="#fff9d0"/>' for k in range(5) for r in range(2)))
    # Green Monster with scoreboard
    s.add(f'<rect x="300" y="230" width="1000" height="150" fill="#1f5a35"/>'
          f'<rect x="300" y="226" width="1000" height="10" fill="#174a2a"/>'
          f'<rect x="760" y="252" width="320" height="100" fill="#174a2a" stroke="#e8e8e8" stroke-width="2"/>'
          + "".join(f'<rect x="{772 + k * 30}" y="268" width="22" height="26" fill="#ffffff"/>' for k in range(10))
          + "".join(f'<rect x="{772 + k * 30}" y="304" width="22" height="26" fill="#ffffff"/>' for k in range(10))
          + '<text x="1150" y="320" font-family="Arial Black, Arial, sans-serif" font-size="40" font-weight="900" fill="#ffffff" opacity="0.9">310</text>')
    for x in range(300, 1300, 30):  # monster seats
        s.add(f'<rect x="{x}" y="212" width="22" height="14" fill="#c62828" opacity="0.8"/>')
    # field
    s.add(f'<rect x="0" y="380" width="{W}" height="{H - 380}" fill="#3a9a4a"/>')
    for k in range(10):
        s.add(f'<rect x="0" y="{380 + k * 24}" width="{W}" height="12" fill="#ffffff" opacity="0.05"/>')
    s.add(f'<path d="M260,{H} L800,420 L1340,{H} Z" fill="#c9905a"/>'
          f'<path d="M560,{H} L800,470 L1040,{H} Z" fill="#3a9a4a"/>'
          f'<path d="M260,{H} L800,420 L1340,{H}" stroke="#ffffff" stroke-width="4" fill="none"/>'
          f'<rect x="790" y="460" width="20" height="20" fill="#ffffff" transform="rotate(45 800 470)"/>')
    # baseball
    s.add(f'<g transform="translate(1120,170)"><circle r="28" fill="#ffffff" stroke="#ddd" stroke-width="2"/>'
          f'<path d="M-18,-20 Q-6,0 -18,20 M18,-20 Q6,0 18,20" stroke="#e31b23" stroke-width="2.5" fill="none" stroke-dasharray="4 3"/></g>'
          f'<path d="M1092,180 q-120,30 -260,10" stroke="#ffffff" stroke-width="2" fill="none" opacity="0.6" stroke-dasharray="8 8"/>')
    # opening day bunting along the front wall and players lined up
    for x in range(40, W, 110):
        s.bunting_fan(x, 386, 40)
    for i, x in enumerate(range(500, 1120, 52)):
        s.person(x, 452, 1.0, "#ffffff", "down",
                 hat='<path d="M-9,-60 Q0,-70 9,-60 L14,-58 L-9,-58 Z" fill="#0a2a6a"/>')
        s.add(f'<text x="{x}" y="420" font-family="Arial, sans-serif" font-size="9" font-weight="700" fill="#c62828" text-anchor="middle">{(i * 7) % 60 + 1}</text>')


def scene_hocr(s):
    """Head of the Charles: eights racing on the Charles under a footbridge, Harvard's river houses
    and their cupolas in peak foliage, crowds on the banks."""
    s.sky("#5a8ad0", "#a8c8f0", "#f8e8d0")
    s.clouds([(280, 100, 1.1), (1300, 80, 1.0)], "#fff", 0.9)
    # Dunster House (red cupola) and Eliot House (blue cupola) towers
    for tx, cup in ((520, "#b22234"), (1080, "#3a64b8")):
        s.add(f'<rect x="{tx - 26}" y="150" width="52" height="200" fill="#a8452e"/>'
              f'<rect x="{tx - 32}" y="140" width="64" height="14" fill="#f1e6d2"/>'
              f'<rect x="{tx - 20}" y="96" width="40" height="46" fill="#f1e6d2"/>'
              f'<path d="M{tx - 22},96 C{tx - 22},60 {tx + 22},60 {tx + 22},96 Z" fill="{cup}"/>'
              f'<rect x="{tx - 1.5}" y="40" width="3" height="28" fill="#d4af37"/>'
              f'<path d="M{tx - 8},106 L{tx - 8},130 L{tx + 8},130 L{tx + 8},106 A8,8 0 0 0 {tx - 8},106 Z" fill="#6a4a3a"/>')
    s.rowhouses(200, 1400, 350, ["#a8452e", "#b8553a"], h=(90, 120), window="#e8f0ff", lit=1.0, trim="#f1e6d2", stoop=False, flat=False)
    for i in range(60):
        s.tree(s.rng.random() * W, 352 + s.rng.random() * 14, 0.7 + s.rng.random() * 0.5,
               s.rng.choice(["#d9481f", "#e8822a", "#f2b134", "#a8321e", "#7a8a2a"]))
    s.add(f'<rect x="0" y="360" width="{W}" height="14" fill="#5a7a3a"/>')
    s.water(372, "#4a7ab8", "#1a3a6a", "#ffffff", 70, 0.35)
    # footbridge (Weeks-style brick arches)
    s.add(f'<rect x="0" y="372" width="{W}" height="22" fill="#a8452e"/><rect x="0" y="368" width="{W}" height="6" fill="#f1e6d2"/>')
    for x in range(-60, W, 260):
        s.add(f'<path d="M{x},440 L{x},394 L{x + 260},394 L{x + 260},440 A130,50 0 0 0 {x},440 Z" fill="#a8452e"/>')
    s.crowd(0, W, 368, 0.55, ["#b22234", "#3a64b8", "#ffb703", "#2a9d8f", "#333"], arms=("up", "wave"))
    # eights racing (rowers + oars)
    def eight(x, y, sc, col):
        out = [f'<g transform="translate({x},{y}) scale({sc})"><path d="M-170,0 L170,0 L190,-4 L170,6 L-170,6 L-186,0 Z" fill="{col}"/>']
        for k in range(8):
            rx = -130 + k * 34
            side = 1 if k % 2 else -1
            out.append(f'<circle cx="{rx}" cy="-16" r="5" fill="#111"/><rect x="{rx - 4}" y="-12" width="8" height="12" fill="#111"/>'
                       f'<line x1="{rx}" y1="-6" x2="{rx - 30}" y2="{14 * side + 8}" stroke="#ddd" stroke-width="2.5"/>'
                       f'<rect x="{rx - 36}" y="{14 * side + 6}" width="12" height="5" fill="{col}"/>')
        out.append(f'<circle cx="152" cy="-10" r="5" fill="#111"/></g>')
        return "".join(out)
    s.add(eight(520, 500, 1.3, "#b22234"), eight(1100, 540, 1.4, "#ffd23f"), eight(980, 460, 0.9, "#3a64b8"))
    for x, y in ((520, 508), (1100, 548), (980, 465)):
        s.add(f'<path d="M{x + 220},{y + 4} q80,6 200,0" stroke="#ffffff" stroke-width="3" fill="none" opacity="0.5"/>')
    for _ in range(26):
        s.add(leaf(s.rng.random() * W, s.rng.random() * 340, 0.5 + s.rng.random() * 0.5,
                   s.rng.choice(["#e8822a", "#f2b134", "#c0392b"]), s.rng.random() * 360, 0.85))


SCENES = {
    "newyear": scene_newyear, "mlk": scene_mlk, "lunarnewyear": scene_lunarnewyear, "valentines": scene_valentines,
    "presidents": scene_presidents, "stpatricks": scene_stpatricks, "patriots": scene_patriots, "memorial": scene_memorial,
    "juneteenth": scene_juneteenth, "july4": scene_july4, "labor": scene_labor, "indigenous": scene_indigenous,
    "election": scene_election, "veterans": scene_veterans, "thanksgiving": scene_thanksgiving,
    "blackfriday": scene_blackfriday, "cybermonday": scene_cybermonday, "hanukkah": scene_hanukkah,
    "christmas": scene_christmas, "newyearseve": scene_newyearseve,
    "diwali": scene_diwali, "easter": scene_easter, "passover": scene_passover, "eid": scene_eid,
    "mothers": scene_mothers, "fathers": scene_fathers, "earthday": scene_earthday, "piday": scene_piday,
    "bunkerhill": scene_bunkerhill, "teaparty": scene_teaparty, "pride": scene_pride,
    "openingday": scene_openingday, "hocr": scene_hocr,
}


def main():
    from holiday_themes import HOLIDAYS
    want = set(sys.argv[1:])
    out_dir = os.path.join(ROOT, "static", "holidays")
    os.makedirs(out_dir, exist_ok=True)
    for h in HOLIDAYS:
        if h.get("banner") or (want and h["key"] not in want):
            continue
        s = Scene(h["key"])
        SCENES[h["key"]](s)
        path = os.path.join(out_dir, f"{h['key']}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(s.svg())
        print(f"{h['key']:14s} {os.path.getsize(path) // 1024:4d} KB")


if __name__ == "__main__":
    main()
