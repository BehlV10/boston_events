"""One-day holiday themes for the homepage.

Each holiday has a date rule, a greeting, a palette and a banner (static/holidays/<key>.svg,
drawn by scripts/make_holiday_banners.py). On the holiday the page switches to that theme for
the day only; visitors can still pick another theme from the pills in the banner.

Themes marked "css": "custom" have hand-written CSS in template.py (Halloween, Election Day,
Veterans Day, Thanksgiving, Black Friday, Cyber Monday). The rest get CSS generated from their
palette by holiday_theme_css().
"""

import os
from datetime import date, timedelta

_ROOT = os.path.abspath(os.path.dirname(__file__))


def _nth_weekday(y, m, weekday, n):
    """n-th (1-based) weekday (Mon=0) of month m."""
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y, m, weekday):
    d = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _thanksgiving(y):
    return _nth_weekday(y, 11, 3, 4)


def _election_day(y):
    return _nth_weekday(y, 11, 0, 1) + timedelta(days=1)


def _easter(y):
    """Western Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(y, month, day)


# Moon-calendar holidays: published dates (Hebcal; publicholidays.com). Extend before 2031.
_LUNAR_NEW_YEAR = {2026: date(2026, 2, 17), 2027: date(2027, 2, 6), 2028: date(2028, 1, 26),
                   2029: date(2029, 2, 13), 2030: date(2030, 2, 3)}
# Diwali (Lakshmi Puja): Nov 8 2026, Oct 29 2027 per most calendars; later years from drikpanchang.
_DIWALI = {2026: date(2026, 11, 8), 2027: date(2027, 10, 29), 2028: date(2028, 10, 17),
           2029: date(2029, 11, 5), 2030: date(2030, 10, 26)}
# Passover: the first seder night (Hebcal).
_PASSOVER_FIRST_SEDER = {2027: date(2027, 4, 21), 2028: date(2028, 4, 10), 2029: date(2029, 3, 30),
                         2030: date(2030, 4, 17)}
# Eid al-Fitr: depends on the moon sighting; these are the expected dates. Confirm a week ahead.
_EID_AL_FITR = {2027: date(2027, 3, 9), 2028: date(2028, 2, 26), 2029: date(2029, 2, 14),
                2030: date(2030, 2, 4)}
# Red Sox home openers at Fenway (MLB schedule; add each year when it's released in the summer).
_FENWAY_OPENER = {2027: date(2027, 4, 1)}
_HANUKKAH_FIRST_NIGHT = {2026: date(2026, 12, 4), 2027: date(2027, 12, 24), 2028: date(2028, 12, 12),
                         2029: date(2029, 12, 1), 2030: date(2030, 12, 20)}


def _fixed(m, d):
    return lambda y: [date(y, m, d)]


# Order matters only when two land on the same day (the first one wins).
HOLIDAYS = [
    {"key": "newyear", "label": "New Year's Day", "emoji": "🎆", "motif": "fireworks",
     "greeting": "Happy New Year, Boston!", "dates": _fixed(1, 1),
     "palette": {"accent": "#f5c542", "accent2": "#a78bfa", "bg": "#0b0a1a", "card": "#15132b",
                 "sky": ["#0b0a2a", "#2a1d5c", "#6b3fa0"], "skyline": "#0d0b1f", "water": "#1a1440"}},
    {"key": "mlk", "label": "Martin Luther King Jr. Day", "emoji": "🕊️", "motif": "rays",
     "greeting": "Martin Luther King Jr. Day: a day of service", "dates": lambda y: [_nth_weekday(y, 1, 0, 3)],
     "palette": {"accent": "#f2b544", "accent2": "#7c6ee6", "bg": "#0e0c18", "card": "#18152a",
                 "sky": ["#2b2156", "#7a4b8c", "#f0a75a"], "skyline": "#16112a", "water": "#2d2350"}},
    {"key": "lunarnewyear", "label": "Lunar New Year", "emoji": "🧧", "motif": "lanterns",
     "greeting": "Happy Lunar New Year! Celebrations in Chinatown", "dates": lambda y: [_LUNAR_NEW_YEAR[y]] if y in _LUNAR_NEW_YEAR else [],
     "palette": {"accent": "#ff4d4d", "accent2": "#f5c542", "bg": "#150708", "card": "#220c0e",
                 "sky": ["#2a0608", "#6e1014", "#c2401c"], "skyline": "#1a0507", "water": "#3a0a0d"}},
    {"key": "valentines", "label": "Valentine's Day", "emoji": "💘", "motif": "hearts",
     "greeting": "Happy Valentine's Day! Date-night ideas below", "dates": _fixed(2, 14),
     "palette": {"accent": "#ff5c8a", "accent2": "#ffb3c7", "bg": "#160810", "card": "#24101b",
                 "sky": ["#3a0f2a", "#8e2a5a", "#f07ca0"], "skyline": "#1f0816", "water": "#4a1636"}},
    {"key": "presidents", "label": "Presidents' Day", "emoji": "🇺🇸", "motif": "stars",
     "greeting": "Happy Presidents' Day", "dates": lambda y: [_nth_weekday(y, 2, 0, 3)],
     "palette": {"accent": "#e0414f", "accent2": "#6ea8ff", "bg": "#0a0e1a", "card": "#131a2c",
                 "sky": ["#0b1530", "#1e3a7a", "#5b7fc7"], "skyline": "#0a1022", "water": "#152448"}},
    {"key": "stpatricks", "label": "St. Patrick's Day & Evacuation Day", "emoji": "☘️", "motif": "shamrocks",
     "greeting": "Happy St. Patrick's Day & Evacuation Day!", "dates": _fixed(3, 17),
     "palette": {"accent": "#2ecc71", "accent2": "#f1c40f", "bg": "#07140c", "card": "#0e2216",
                 "sky": ["#06261a", "#0f5a35", "#3fae6a"], "skyline": "#05170e", "water": "#0b3a22"}},
    {"key": "piday", "label": "Pi Day", "emoji": "🥧",
     "greeting": "Happy Pi Day! 3.14159…", "dates": _fixed(3, 14),
     "palette": {"accent": "#f5c542", "accent2": "#7ee2a8", "bg": "#0c1a14", "card": "#14261e",
                 "sky": ["#1c3a2e", "#244a3a", "#2e5a46"], "skyline": "#0e2a20", "water": "#1e4a3a"}},
    {"key": "eid", "label": "Eid al-Fitr", "emoji": "🌙",
     "greeting": "Eid Mubarak!", "dates": lambda y: [_EID_AL_FITR[y]] if y in _EID_AL_FITR else [],
     "palette": {"accent": "#2ec4b6", "accent2": "#f5c542", "bg": "#0a1428", "card": "#122038",
                 "sky": ["#0b1a3a", "#1f4a7a", "#e8a86a"], "skyline": "#13203a", "water": "#1a2a4a"}},
    {"key": "easter", "label": "Easter", "emoji": "🐣",
     "greeting": "Happy Easter! Swan boats & spring in the Public Garden", "dates": lambda y: [_easter(y)],
     "palette": {"accent": "#ff7ab8", "accent2": "#7ec8f0", "bg": "#0f0d14", "card": "#1a1722",
                 "sky": ["#7ec8f0", "#bfe6fb", "#fdf3fb"], "skyline": "#b6c6dd", "water": "#4a9ac8"}},
    {"key": "openingday", "label": "Opening Day at Fenway", "emoji": "⚾",
     "greeting": "Opening Day at Fenway! Play ball", "dates": lambda y: [_FENWAY_OPENER[y]] if y in _FENWAY_OPENER else [],
     "palette": {"accent": "#e31b23", "accent2": "#2e9a4a", "bg": "#08120c", "card": "#101e16",
                 "sky": ["#2f80d0", "#8fc4f5", "#e8f4ff"], "skyline": "#1f5a35", "water": "#3a9a4a"}},
    {"key": "patriots", "label": "Patriots' Day & Marathon Monday", "emoji": "🏃", "motif": "confetti",
     "greeting": "Patriots' Day & Marathon Monday: go runners!", "dates": lambda y: [_nth_weekday(y, 4, 0, 3)],
     "palette": {"accent": "#ffd23f", "accent2": "#3d7bff", "bg": "#08101e", "card": "#111b30",
                 "sky": ["#0e2a5c", "#2f6fd1", "#9cc9ff"], "skyline": "#0b1830", "water": "#1d4a8f"}},
    {"key": "passover", "label": "Passover", "emoji": "🍷",
     "greeting": "Chag Pesach Sameach! The first seder is tonight", "dates": lambda y: [_PASSOVER_FIRST_SEDER[y]] if y in _PASSOVER_FIRST_SEDER else [],
     "palette": {"accent": "#7cb7ff", "accent2": "#d9c27a", "bg": "#0a0f20", "card": "#121a30",
                 "sky": ["#0c1430", "#23326a", "#4a5a9a"], "skyline": "#2a1a24", "water": "#23326a"}},
    {"key": "earthday", "label": "Earth Day", "emoji": "🌎",
     "greeting": "Happy Earth Day! Cleanups, plantings & green events below", "dates": _fixed(4, 22),
     "palette": {"accent": "#3aa860", "accent2": "#3a8ad8", "bg": "#07140c", "card": "#0f2216",
                 "sky": ["#6ec6f0", "#b9e8fb", "#f0fbf0"], "skyline": "#4caf6a", "water": "#3a8ad8"}},
    {"key": "mothers", "label": "Mother's Day", "emoji": "💐",
     "greeting": "Happy Mother's Day! It's Lilac Sunday at the Arnold Arboretum", "dates": lambda y: [_nth_weekday(y, 5, 6, 2)],
     "palette": {"accent": "#c49ae8", "accent2": "#ff7ab8", "bg": "#120c18", "card": "#1c1426",
                 "sky": ["#8fb8f0", "#cfe0fb", "#fff0f6"], "skyline": "#7cb86a", "water": "#9cc98a"}},
    {"key": "memorial", "label": "Memorial Day", "emoji": "🇺🇸", "motif": "poppies",
     "greeting": "Memorial Day: remembering those who gave everything", "dates": lambda y: [_last_weekday(y, 5, 0)],
     "palette": {"accent": "#e0414f", "accent2": "#d4af37", "bg": "#0a0d17", "card": "#131929",
                 "sky": ["#0c1430", "#33406e", "#c7845a"], "skyline": "#0a0f20", "water": "#1b2547"}},
    {"key": "pride", "label": "Pride Month", "emoji": "🏳️‍🌈",
     "greeting": "Happy Pride, Boston!", "dates": _fixed(6, 1),
     "palette": {"accent": "#ff8c00", "accent2": "#732982", "bg": "#0f0a20", "card": "#1a1230",
                 "sky": ["#1a1040", "#3a2a7a", "#7a5aba"], "skyline": "#140c30", "water": "#2a1a5a"}},
    {"key": "bunkerhill", "label": "Bunker Hill Day", "emoji": "🥁",
     "greeting": "Bunker Hill Day: the Charlestown parade is today", "dates": _fixed(6, 17),
     "palette": {"accent": "#b22234", "accent2": "#3a6ad8", "bg": "#0a0e1a", "card": "#131a2c",
                 "sky": ["#3a8ad8", "#9cccf5", "#eaf6ff"], "skyline": "#5aa060", "water": "#3a8ad8"}},
    {"key": "juneteenth", "label": "Juneteenth", "emoji": "✊🏿", "motif": "starburst",
     "greeting": "Juneteenth: celebrating freedom", "dates": _fixed(6, 19),
     "palette": {"accent": "#f5b82e", "accent2": "#e5484d", "bg": "#0f0b08", "card": "#1c1510",
                 "sky": ["#1f1030", "#a0352f", "#f5b82e"], "skyline": "#140c08", "water": "#3a1c14"}},
    {"key": "fathers", "label": "Father's Day", "emoji": "⛵",
     "greeting": "Happy Father's Day!", "dates": lambda y: [_nth_weekday(y, 6, 6, 3)],
     "palette": {"accent": "#4dabf7", "accent2": "#ffb703", "bg": "#08101c", "card": "#101a2a",
                 "sky": ["#2a6fb0", "#86c0e8", "#ffd8a0"], "skyline": "#3a4a6a", "water": "#1a4a7a"}},
    {"key": "july4", "label": "Fourth of July", "emoji": "🎆", "motif": "fireworks",
     "greeting": "Happy Fourth of July! Fireworks over the Charles tonight", "dates": _fixed(7, 4),
     "palette": {"accent": "#ff4d5e", "accent2": "#5b9cff", "bg": "#070b18", "card": "#101729",
                 "sky": ["#050a24", "#162a66", "#3a4f9e"], "skyline": "#060b1e", "water": "#0f1d4a"}},
    {"key": "labor", "label": "Labor Day", "emoji": "☀️", "motif": "sun",
     "greeting": "Happy Labor Day! Last long weekend of summer", "dates": lambda y: [_nth_weekday(y, 9, 0, 1)],
     "palette": {"accent": "#ff9f43", "accent2": "#22c3c3", "bg": "#0c0f14", "card": "#161b24",
                 "sky": ["#1a3a6b", "#e8875a", "#ffd27a"], "skyline": "#12121f", "water": "#2a4d7a"}},
    {"key": "indigenous", "label": "Indigenous Peoples' Day", "emoji": "🪶", "motif": "leaves",
     "greeting": "Indigenous Peoples' Day", "dates": lambda y: [_nth_weekday(y, 10, 0, 2)],
     "palette": {"accent": "#e07a3f", "accent2": "#2bb3a3", "bg": "#120c08", "card": "#1f1610",
                 "sky": ["#2a1a3a", "#a0482a", "#f0a050"], "skyline": "#160d08", "water": "#3a2418"}},
    {"key": "hocr", "label": "Head of the Charles", "emoji": "🚣",
     "greeting": "Head of the Charles Regatta this weekend", "dates": lambda y: [_nth_weekday(y, 10, 5, 3), _nth_weekday(y, 10, 5, 3) + timedelta(days=1)],
     "palette": {"accent": "#e8822a", "accent2": "#3a64b8", "bg": "#120c08", "card": "#1f1610",
                 "sky": ["#5a8ad0", "#a8c8f0", "#f8e8d0"], "skyline": "#a8452e", "water": "#1a3a6a"}},
    {"key": "diwali", "label": "Diwali", "emoji": "🪔",
     "greeting": "Happy Diwali! Festival of lights", "dates": lambda y: [_DIWALI[y]] if y in _DIWALI else [],
     "palette": {"accent": "#ffcf3f", "accent2": "#ff7ab8", "bg": "#0e0618", "card": "#1a0c26",
                 "sky": ["#0b0420", "#2a0f4a", "#7a2a5a"], "skyline": "#140a24", "water": "#3a1a4a"}},
    {"key": "halloween", "label": "Halloween", "emoji": "🎃", "css": "custom", "banner": "banner_halloween.jpg",
     "greeting": "Happy Halloween! Costume parties & haunts below",
     "dates": lambda y: [date(y, 10, 29) + timedelta(days=i) for i in range(4)]},  # Oct 29 – Nov 1
    {"key": "election", "label": "Election Day", "emoji": "🗳️", "css": "custom", "motif": "stars",
     "greeting": "It's Election Day: polls are open 7AM–8PM", "dates": lambda y: [_election_day(y)],
     "palette": {"sky": ["#0b1530", "#2b3f8a", "#b0404a"], "skyline": "#0a1022", "water": "#152448",
                 "accent": "#ef4444", "accent2": "#3b82f6"}},
    {"key": "veterans", "label": "Veterans Day", "emoji": "🎖️", "css": "custom", "motif": "veterans",
     "greeting": "Veterans Day: thank you to everyone who served", "dates": _fixed(11, 11),
     "palette": {"sky": ["#070d1f", "#1b2d5c", "#c9874a"], "skyline": "#070b18", "water": "#13213f",
                 "accent": "#d4af37", "accent2": "#b91c1c"}},
    {"key": "thanksgiving", "label": "Thanksgiving", "emoji": "🦃", "css": "custom", "motif": "leaves",
     "greeting": "Happy Thanksgiving, Boston!", "dates": lambda y: [_thanksgiving(y) - timedelta(days=1), _thanksgiving(y)],
     "palette": {"sky": ["#2a1408", "#8a3a14", "#f0a040"], "skyline": "#170b05", "water": "#3a1c0c",
                 "accent": "#ea580c", "accent2": "#be123c"}},
    {"key": "blackfriday", "label": "Black Friday", "emoji": "🏷️", "css": "custom", "motif": "confetti",
     "greeting": "Black Friday: skip the mall, go see a show", "dates": lambda y: [_thanksgiving(y) + timedelta(days=1), _thanksgiving(y) + timedelta(days=2)],
     "palette": {"sky": ["#000000", "#1a1a1a", "#3a3000"], "skyline": "#000000", "water": "#141414",
                 "accent": "#facc15", "accent2": "#ffffff"}},
    {"key": "cybermonday", "label": "Cyber Monday", "emoji": "⚡", "css": "custom", "motif": "stars",
     "greeting": "Cyber Monday: log off, head out", "dates": lambda y: [_thanksgiving(y) + timedelta(days=4)],
     "palette": {"sky": ["#03061a", "#0b2a5c", "#06b6d4"], "skyline": "#020414", "water": "#062040",
                 "accent": "#22d3ee", "accent2": "#a855f7"}},
    {"key": "teaparty", "label": "Boston Tea Party Night", "emoji": "🫖",
     "greeting": "On this night in 1773: the Boston Tea Party", "dates": _fixed(12, 16),
     "palette": {"accent": "#c9a462", "accent2": "#5b7fc7", "bg": "#070b18", "card": "#0f1626",
                 "sky": ["#070b1a", "#16234a", "#2a3a6a"], "skyline": "#0a1024", "water": "#1a2a50"}},
    {"key": "hanukkah", "label": "Hanukkah", "emoji": "🕎", "motif": "candles",
     "greeting": "Happy Hanukkah! The first candle is lit tonight", "dates": lambda y: [_HANUKKAH_FIRST_NIGHT[y]] if y in _HANUKKAH_FIRST_NIGHT else [],
     "palette": {"accent": "#7cb7ff", "accent2": "#e8eef8", "bg": "#070c18", "card": "#0f172a",
                 "sky": ["#06102a", "#14306e", "#3a64b8"], "skyline": "#050b1e", "water": "#0d2150"}},
    {"key": "christmas", "label": "Christmas", "emoji": "🎄", "motif": "snow",
     "greeting": "Merry Christmas & happy holidays!", "dates": lambda y: [date(y, 12, 24), date(y, 12, 25)],
     "palette": {"accent": "#ef4444", "accent2": "#22c55e", "bg": "#080d10", "card": "#10191e",
                 "sky": ["#071422", "#16314a", "#3d6680"], "skyline": "#06101a", "water": "#122636"}},
    {"key": "newyearseve", "label": "New Year's Eve & First Night", "emoji": "🥂", "motif": "fireworks",
     "greeting": "First Night Boston: happy New Year's Eve!", "dates": _fixed(12, 31),
     "palette": {"accent": "#f5c542", "accent2": "#f472b6", "bg": "#0a0814", "card": "#141026",
                 "sky": ["#07051a", "#241a55", "#5b3a8a"], "skyline": "#08061a", "water": "#17123a"}},
]

HOLIDAY_KEYS = [h["key"] for h in HOLIDAYS]
_BY_KEY = {h["key"]: h for h in HOLIDAYS}


def holiday_on(d):
    """The holiday theme for date d, or None."""
    for h in HOLIDAYS:
        if d in h["dates"](d.year):
            return h
    return None


def holiday_calendar(start, days):
    """{iso date: key} for every holiday day in [start, start + days)."""
    out = {}
    for i in range(days):
        d = start + timedelta(days=i)
        h = holiday_on(d)
        if h:
            out[d.isoformat()] = h["key"]
    return out


def banner_url(h):
    if h.get("banner"):
        return h["banner"]
    key = h["key"]
    jpg_rel = f"static/holidays/{key}.jpg"
    if os.path.exists(os.path.join(_ROOT, jpg_rel)):
        return jpg_rel
    return f"static/holidays/{key}.svg"


def _tint(hex_color, amount):
    """Mix a hex color toward white by `amount` (0..1)."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in rgb)


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {a})"


def holiday_theme_css():
    """CSS for every holiday: the banner art and greeting for all, plus a full palette for
    holidays without hand-written CSS. Inserted into the page as an f-string value, so braces are literal."""
    rules = [
        ".holiday-greeting { display: none; }",
        ".holiday-greeting { align-self: flex-start; align-items: center; gap: 8px; padding: 6px 14px;"
        " border-radius: 999px; font-size: 14px; font-weight: 700; color: #fff;"
        " background: rgba(0, 0, 0, 0.42); border: 1px solid var(--accent); backdrop-filter: blur(6px); }",
    ]
    for h in HOLIDAYS:
        k = h["key"]
        sel = f'[data-theme="{k}"]'
        rules.append(f'{sel} .holiday-greeting[data-for="{k}"] {{ display: inline-flex; }}')
        if h.get("banner") is None:
            # Holiday art is drawn 1600x600 with the subject in the upper-middle; show more of it on
            # the day (taller banner) and darken the bottom so the title stays readable.
            b_url = banner_url(h)
            full_b = os.path.join(_ROOT, b_url)
            if os.path.exists(full_b):
                b_url = f"{b_url}?v={int(os.path.getmtime(full_b))}"
            rules.append(
                f"{sel} .banner {{ min-height: 360px; background-image: linear-gradient(180deg, rgba(0,0,0,0.10) 0%, "
                f"rgba(0,0,0,0) 30%, rgba(0,0,0,0.25) 62%, rgba(8,8,16,0.88) 100%), url('{b_url}'); "
                f"background-position: center 40%; background-size: cover; }}")
            rules.append(f"@media (max-width: 860px) {{ {sel} .banner {{ min-height: 300px; background-position: center 45%; }} }}")
            # Gradient title text can vanish over bright daytime art; a soft shadow keeps it legible.
            rules.append(f"{sel} .banner-title {{ filter: drop-shadow(0 2px 2px rgba(0,0,0,0.9)) drop-shadow(0 0 10px rgba(0,0,0,0.45)); }}")
        if h.get("css") == "custom":
            continue
        p = h["palette"]
        a, a2 = p["accent"], p["accent2"]
        rules.append(
            f"{sel} {{ --bg: {p['bg']}; --card: {p['card']}; --card-hover: {p['card']}; --fg: #f8fafc;"
            f" --muted: #a8b0c0; --accent: {a}; --accent-glow: {_rgba(a, 0.35)};"
            f" --border: {_rgba(a, 0.22)}; --border-hover: {_rgba(a, 0.48)};"
            f" --green: {a2}; --green-bg: {_rgba(a2, 0.14)}; --green-border: {_rgba(a2, 0.35)};"
            f" --warn: {a}; --radius-lg: 16px; --radius-md: 10px; --radius-sm: 6px; }}")
        rules.append(
            f"{sel} body {{ background-color: var(--bg); background-image:"
            f" radial-gradient(ellipse 80% 50% at 50% -10%, {_rgba(a, 0.09)} 0%, transparent 70%),"
            f" radial-gradient(ellipse 60% 40% at 90% 40%, {_rgba(a2, 0.08)} 0%, transparent 60%);"
            f" background-attachment: fixed; color: var(--fg); }}")
        rules.append(f"{sel} .banner {{ border-bottom: 2px solid {_rgba(a, 0.45)};"
                     f" box-shadow: 0 4px 30px rgba(0,0,0,0.5), 0 0 20px {_rgba(a, 0.15)}; }}")
        rules.append(f"{sel} .banner-top-tag {{ color: {a}; text-shadow: 0 0 12px {_rgba(a, 0.6)}; }}")
        rules.append(f"{sel} .live-pulse {{ background: {a}; box-shadow: 0 0 10px {a}, 0 0 20px {a}; }}")
        # Lightened accents so the title reads over bright daytime art (its shadow is set above).
        rules.append(f"{sel} .banner-title {{ background: linear-gradient(135deg, #ffffff 25%, {_tint(a, 0.35)} 62%, {_tint(a2, 0.35)} 100%);"
                     f" -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}")
        rules.append(f"{sel} .pill-submit-btn {{ background: linear-gradient(135deg, {a} 0%, {a2} 100%);"
                     f" color: #fff; box-shadow: 0 0 14px {_rgba(a, 0.45)}; border-radius: 999px; }}")
        rules.append(f"{sel} .chip.active, {sel} .loc-chip.active, {sel} .genre-chip.active, {sel} .sub-chip.active"
                     f" {{ background: linear-gradient(135deg, {_rgba(a, 0.35)} 0%, {_rgba(a2, 0.3)} 100%);"
                     f" border-color: {a}; color: #fff; box-shadow: 0 0 12px {_rgba(a, 0.35)}; }}")
        rules.append(f"{sel} .theme-pill-btn.active {{ background: linear-gradient(135deg, {a} 0%, {a2} 100%);"
                     f" color: #fff; box-shadow: 0 0 10px {_rgba(a, 0.5)}; }}")
        rules.append(f"{sel} .badge-highlight {{ border-color: {a}; color: {a}; }}")
    return "\n  ".join(rules)


def greeting_html():
    from html import escape
    return "".join(
        f'<div class="holiday-greeting" data-for="{h["key"]}">{h["emoji"]} {escape(h["greeting"])}</div>'
        for h in HOLIDAYS)
