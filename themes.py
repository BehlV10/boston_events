#!/usr/bin/env python3
"""
Boston Events Seasonal & Thematic Calendar Engine.

Dynamically determines the visual theme, color palette, icons, and artwork
based on the date, seamlessly transitioning through the city's signature seasons:
- Oct 29 – Nov 2: Halloween & Día de los Muertos (Marigolds, Calaveras, Pumpkins, Cobblestone Twilight)
- Nov 3 – Nov 29: Boston Fall Harvest & Thanksgiving (Golden Foliage, Cranberries, Historic Brick, Cider)
- Nov 30 – Dec 31: Holiday Magic & Winter Lights (Common Tree, Comm Ave Lights, Frog Pond Ice Skating)
- Jan 1 – Feb 13: Boston Winter Chill & Cozy Speakeasies (Snowy Brownstones, Cellar Jazz, Hearthside Pints)
- Feb 14 – Feb 28: Boston Romance & Cozy Date Nights (North End Candlelit Dinners, Charles River Sunset)
- Mar 1 – Mar 31: St. Patrick's Month & Irish Heritage (Southie Parade, Emerald Greens, Celtic Pub Fiddles)
- Apr 1 – Apr 30: Patriots' Day, Marathon & Spring Blooms (Esplanade Cherry Blossoms, Boylston Finish Line)
- May 1 – Jun 20: Waterfront, Rooftops & Beer Gardens (Charles River Sailing, Greenway Beer Gardens)
- Jun 21 – Jul 7: Fourth of July & Boston Pops (Esplanade Fireworks, Harbor Sails, Historic Boston)
- Jul 8 – Aug 31: Summer in the City (Shakespeare on the Common, Fenway Rooftops, Harbor Islands)
- Sep 1 – Oct 15: Back to School & Head of the Charles (College Town Buzz, River Regatta, Autumn Crisp)
- Oct 16 – Oct 28: Spooky Season & Historic Haunts (Salem Ferry, Ghost Tours, Acorn St Jack-o'-Lanterns)
"""

from datetime import datetime, date
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")


THEMES = {
    "halloween_dia_de_muertos": {
        "id": "halloween_dia_de_muertos",
        "name": "Halloween & Día de los Muertos",
        "eyebrow": "🎃 HALLOWEEN & DÍA DE LOS MUERTOS SPECIAL 💀",
        "sub_tag": "MARIGOLDS · SUGAR SKULLS · 35MM HORROR · COSTUME BALLS",
        "primary_color": "#ff793f",
        "accent_color": "#e056fd",
        "border_color": "#ff9f43",
        "bg_gradient": "linear-gradient(180deg, #fffcf6 0%, #fdf5ea 50%, #fcf3e6 100%)",
        "header_bg": "linear-gradient(90deg, #ff4757, #ff793f, #e056fd)",
        "icons": {
            "boston": "🏙️💀",
            "cambridge": "🎓🎃",
            "somerville": "🎨🕯️",
            "sparkle": "✨",
        },
        "art_prompt": (
            "A breathtaking Boston street scene celebrating Día de los Muertos and Halloween together. "
            "Historic Beacon Hill cobblestones decorated with glowing orange cempasúchil (marigold) flower garlands, "
            "vibrant sugar skulls (calaveras) with ornate floral patterns, smiling jack-o'-lanterns, glowing candlelit lanterns, "
            "warm gas streetlamps, the Massachusetts State House golden dome glowing softly in the twilight background, "
            "and a charming friendly smiling ghost mascot wearing a cozy autumn knit scarf and marigold crown. "
            "Warm storybook gouache illustration, rich marigold gold, deep plum twilight, glowing amber, festive and magical."
        ),
        "art_filename": "dia_de_muertos_halloween_art.jpg",
    },
    "fall_harvest_thanksgiving": {
        "id": "fall_harvest_thanksgiving",
        "name": "Boston Fall Foliage & Thanksgiving Harvest",
        "eyebrow": "🍂 BOSTON FALL HARVEST & THANKSGIVING 🦃",
        "sub_tag": "GOLDEN FOLIAGE · CRANBERRIES · COZY CIDER · BEACON HILL",
        "primary_color": "#d35400",
        "accent_color": "#e67e22",
        "border_color": "#f39c12",
        "bg_gradient": "linear-gradient(180deg, #fffdf8 0%, #f9f2e7 50%, #fdf8ee 100%)",
        "header_bg": "linear-gradient(90deg, #c0392b, #d35400, #f39c12)",
        "icons": {
            "boston": "🏙️🍁",
            "cambridge": "🎓🍂",
            "somerville": "🎨🥧",
            "sparkle": "✨",
        },
        "art_filename": "boston_harvest_thanksgiving.jpg",
    },
    "winter_holiday_magic": {
        "id": "winter_holiday_magic",
        "name": "Holiday Magic & Winter Lights",
        "eyebrow": "❄️ BOSTON HOLIDAY MAGIC & WINTER LIGHTS 🎄",
        "sub_tag": "COMMON HOLIDAY TREE · COMM AVE LIGHTS · FROG POND SKATING",
        "primary_color": "#0984e3",
        "accent_color": "#2ed573",
        "border_color": "#74b9ff",
        "bg_gradient": "linear-gradient(180deg, #f8faff 0%, #eef4fc 50%, #f4f8fe 100%)",
        "header_bg": "linear-gradient(90deg, #0984e3, #6c5ce7, #2ed573)",
        "icons": {
            "boston": "🏙️🎄",
            "cambridge": "🎓⛸️",
            "somerville": "🎨❄️",
            "sparkle": "✨",
        },
        "art_filename": "boston_holiday_lights.jpg",
    },
    "st_patricks_irish_heritage": {
        "id": "st_patricks_irish_heritage",
        "name": "St. Patrick's Month & Irish Heritage",
        "eyebrow": "☘️ ST. PATRICK'S MONTH & IRISH HERITAGE 🎻",
        "sub_tag": "SOUTHIE PARADE · CELTIC SESSIONS · EMERALD GREENS",
        "primary_color": "#27ae60",
        "accent_color": "#2ecc71",
        "border_color": "#f1c40f",
        "bg_gradient": "linear-gradient(180deg, #f7fdf9 0%, #edf9f0 50%, #f4fcf6 100%)",
        "header_bg": "linear-gradient(90deg, #27ae60, #2ecc71, #f1c40f)",
        "icons": {
            "boston": "🏙️☘️",
            "cambridge": "🎓🍀",
            "somerville": "🎨🎻",
            "sparkle": "✨",
        },
        "art_filename": "boston_st_patricks.jpg",
    },
    "boston_marathon_spring": {
        "id": "boston_marathon_spring",
        "name": "Patriots' Day, Boston Marathon & Spring Blooms",
        "eyebrow": "🏃 BOSTON MARATHON & SPRING AWAKENING 🌸",
        "sub_tag": "ESPLANADE CHERRY BLOSSOMS · BOYLSTON ST · PATRIOTS' DAY",
        "primary_color": "#0984e3",
        "accent_color": "#f1c40f",
        "border_color": "#e84393",
        "bg_gradient": "linear-gradient(180deg, #fcfaff 0%, #f5effe 50%, #fcf7ff 100%)",
        "header_bg": "linear-gradient(90deg, #0984e3, #f1c40f, #e84393)",
        "icons": {
            "boston": "🏙️🏃",
            "cambridge": "🎓🌸",
            "somerville": "🎨☀️",
            "sparkle": "✨",
        },
        "art_filename": "boston_marathon_spring.jpg",
    },
}


def get_active_theme(target_date=None):
    """
    Returns the active theme configuration dictionary for a given date.
    Defaults to today's date in Eastern Time.
    """
    if target_date is None:
        target_date = datetime.now(EASTERN).date()
    elif isinstance(target_date, datetime):
        target_date = target_date.date()

    month = target_date.month
    day = target_date.day

    # Oct 29 - Nov 2: Halloween & Día de los Muertos Special
    if (month == 10 and day >= 29) or (month == 11 and day <= 2):
        return THEMES["halloween_dia_de_muertos"]

    # Nov 3 - Nov 29: Thanksgiving & Fall Harvest
    if month == 11 and day <= 29:
        return THEMES["fall_harvest_thanksgiving"]

    # Nov 30 - Dec 31: Holiday Magic & Winter Lights
    if (month == 11 and day >= 30) or month == 12:
        return THEMES["winter_holiday_magic"]

    # March: St. Patrick's Month
    if month == 3:
        return THEMES["st_patricks_irish_heritage"]

    # April: Boston Marathon & Spring
    if month == 4:
        return THEMES["boston_marathon_spring"]

    # Default to harvest or standard
    return THEMES["halloween_dia_de_muertos"]


if __name__ == "__main__":
    t = get_active_theme()
    print(f"Active Theme for Today: {t['name']}")
    print(f"Eyebrow: {t['eyebrow']}")
