"""Boston Events — Venue geocoding and coordinate mapping for OpenStreetMap integration.

Provides pre-geocoded coordinates for Greater Boston music venues, comedy clubs,
theatres, museums, breweries, and event spaces to enable instant, zero-latency
client-side mapping without rate limits.
"""

import re
from typing import Optional, Dict, Any, Tuple

# Curated coordinates for Greater Boston venues
# (lat, lng, neighborhood, street_address, canonical_name)
VENUE_COORDINATES: Dict[str, Tuple[float, float, str, str, str]] = {
    # Candlelight concert rooms (sold through Fever)
    "simons theatre": (42.3591, -71.0496, "Waterfront", "1 Central Wharf, Boston, MA 02110", "Simons Theatre"),
    "old south church": (42.3501, -71.0781, "Back Bay", "645 Boylston St, Boston, MA 02116", "Old South Church"),
    "temple ohabei shalom": (42.3436, -71.1145, "Brookline", "1187 Beacon St, Brookline, MA 02446", "Temple Ohabei Shalom"),
    "hyatt regency boston": (42.3530, -71.0612, "Downtown", "1 Avenue de Lafayette, Boston, MA 02111", "Hyatt Regency Boston"),
    # Harvard Square & West Cambridge
    "the sinclair": (42.3746, -71.1207, "Harvard Square", "52 Church St, Cambridge", "The Sinclair"),
    # Club and underground spots listed on Resident Advisor (exact names only, no substring rules)
    "descent": (42.3725, -71.1193, "Harvard Square", "33 Dunster St, Cambridge", "Descent"),
    "52 church": (42.3746, -71.1207, "Harvard Square", "52 Church St, Cambridge", "52 Church"),
    "the chemist": (42.3553, -71.0538, "Financial District", "109 High St, Boston", "The Chemist"),
    "the smoot standard": (42.3625, -71.0985, "Central Square", "313 Massachusetts Ave, Cambridge", "The Smoot Standard"),
    "union tavern": (42.3809, -71.0982, "Union Square", "345 Somerville Ave, Somerville", "Union Tavern"),
    "naicob": (42.3294, -71.1111, "Jamaica Plain", "105 S Huntington Ave, Boston", "NAICOB"),
    "jadu": (42.3102, -71.1153, "Jamaica Plain", "767 Centre St, Boston", "Jadu"),
    "288 green st": (42.3649, -71.1026, "Central Square", "288 Green St, Cambridge", "288 Green St"),
    "city tap fort point": (42.3501, -71.0471, "Fort Point", "10 Boston Wharf Rd, Boston", "City Tap Fort Point"),
    "westin copley place": (42.3485, -71.0772, "Back Bay", "10 Huntington Ave, Boston", "Westin Copley Place"),
    "lou's": (42.3747, -71.1206, "Harvard Square", "50 Church St, Cambridge", "Lou's (Harvard Square)"),
    "club passim": (42.3741, -71.1204, "Harvard Square", "47 Palmer St, Cambridge", "Club Passim"),
    "the comedy studio": (42.3727, -71.1196, "Harvard Square", "5 John F. Kennedy St, Cambridge", "The Comedy Studio"),
    "brattle theatre": (42.3740, -71.1208, "Harvard Square", "40 Brattle St, Cambridge", "Brattle Theatre"),
    "harvard book store": (42.3729, -71.1166, "Harvard Square", "1256 Massachusetts Ave, Cambridge", "Harvard Book Store"),
    "harvard museum of natural history": (42.3787, -71.1155, "Harvard Square", "26 Oxford St, Cambridge", "Harvard Museum of Natural History"),
    "peabody museum": (42.3785, -71.1152, "Harvard Square", "11 Divinity Ave, Cambridge", "Peabody Museum"),
    "harvard art museums": (42.3742, -71.1143, "Harvard Square", "32 Quincy St, Cambridge", "Harvard Art Museums"),
    "harvard art museum": (42.3742, -71.1143, "Harvard Square", "32 Quincy St, Cambridge", "Harvard Art Museums"),
    "harvard square": (42.3736, -71.1190, "Harvard Square", "Harvard Square, Cambridge", "Harvard Square"),
    "harvard yard": (42.3744, -71.1169, "Harvard Square", "Harvard Yard, Cambridge", "Harvard Yard"),
    "harvard/central pogo": (42.3736, -71.1190, "Harvard Square", "Harvard Square & Harvard Yard, Cambridge", "Harvard Square (Harvard/Central PoGO)"),
    "q ballroom": (42.3879, -71.1404, "West Cambridge", "26 New St, Cambridge", "Q Ballroom"),
    "graymist studio & shop": (42.3810, -71.1390, "West Cambridge", "364 Huron Ave, Cambridge", "GrayMist Studio & Shop"),
    "graymist": (42.3810, -71.1390, "West Cambridge", "364 Huron Ave, Cambridge", "GrayMist Studio & Shop"),
    "ccae": (42.3744, -71.1219, "Harvard Square", "42 Brattle St, Cambridge", "CCAE (Cambridge Center for Adult Education)"),
    "lovestruck books": (42.3739, -71.1200, "Harvard Square", "22 Church St, Cambridge", "Lovestruck Books & Cafe"),
    "grendel's den": (42.3721, -71.1207, "Harvard Square", "89 Winthrop St, Cambridge", "Grendel's Den"),
    "charlie's kitchen": (42.3729, -71.1218, "Harvard Square", "10 Eliot St, Cambridge", "Charlie's Kitchen"),
    "the hong kong": (42.3728, -71.1174, "Harvard Square", "1238 Massachusetts Ave, Cambridge", "The Hong Kong"),
    "cambridge public library": (42.3744, -71.1111, "Mid-Cambridge", "449 Broadway, Cambridge", "Cambridge Public Library"),
    "cambridge public library (main library)": (42.3744, -71.1111, "Mid-Cambridge", "449 Broadway, Cambridge", "Cambridge Public Library (Main)"),
    "cambridge public library (central square branch)": (42.3644, -71.1027, "Central Square", "45 Pearl St, Cambridge", "Cambridge Public Library (Central Square)"),
    "cambridge public library (valente branch)": (42.3722, -71.0902, "East Cambridge", "826 Cambridge St, Cambridge", "Cambridge Public Library (Valente Branch)"),
    "cambridge public library (o'connell branch)": (42.3688, -71.0847, "East Cambridge", "48 Sixth St, Cambridge", "Cambridge Public Library (O'Connell Branch)"),
    "cambridge public library (o'neill branch)": (42.3922, -71.1280, "North Cambridge", "70 Rindge Ave, Cambridge", "Cambridge Public Library (O'Neill Branch)"),
    "cambridge public library (boudreau branch)": (42.3838, -71.1319, "West Cambridge", "245 Concord Ave, Cambridge", "Cambridge Public Library (Boudreau Branch)"),
    "cambridge public library (collins branch)": (42.3776, -71.1491, "West Cambridge", "64 Aberdeen Ave, Cambridge", "Cambridge Public Library (Collins Branch)"),
    "copley square farmers market": (42.3501, -71.0766, "Copley Square", "Copley Square, Boston", "Copley Square Farmers Market"),
    "harvard university farmers market": (42.3760, -71.1167, "Harvard Square", "1 Oxford St, Cambridge", "Harvard University Farmers Market"),
    "haymarket boston": (42.3625, -71.0565, "Downtown / North End", "Blackstone St, Boston", "Haymarket"),
    "haymarket": (42.3625, -71.0565, "Downtown / North End", "Blackstone St, Boston", "Haymarket"),
    "improv asylum": (42.3636, -71.0543, "North End", "216 Hanover St, Boston", "Improv Asylum"),
    "regattabar": (42.3723, -71.1222, "Harvard Square", "1 Bennett St, Cambridge", "Regattabar"),
    "the druid": (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid"),
    "druid": (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid"),
    "off the rails boston": (42.3578, -71.0592, "Downtown", "25 School St, Boston", "Off the Rails Boston"),
    "off the rails": (42.3578, -71.0592, "Downtown", "25 School St, Boston", "Off the Rails Boston"),
    "mr. dooley's": (42.3578, -71.0537, "Financial District", "77 Broad St, Boston", "Mr. Dooley's"),
    "mr dooleys": (42.3578, -71.0537, "Financial District", "77 Broad St, Boston", "Mr. Dooley's"),
    "the green dragon tavern": (42.3611, -71.0573, "Faneuil Hall", "11 Marshall St, Boston", "The Green Dragon Tavern"),
    "green dragon tavern": (42.3611, -71.0573, "Faneuil Hall", "11 Marshall St, Boston", "The Green Dragon Tavern"),
    "green dragon": (42.3611, -71.0573, "Faneuil Hall", "11 Marshall St, Boston", "The Green Dragon Tavern"),
    "hennessy's bar": (42.3609, -71.0567, "Faneuil Hall", "25 Union St, Boston", "Hennessy's Bar"),
    "hennessys bar": (42.3609, -71.0567, "Faneuil Hall", "25 Union St, Boston", "Hennessy's Bar"),
    "hennessy's": (42.3609, -71.0567, "Faneuil Hall", "25 Union St, Boston", "Hennessy's Bar"),
    "hennessys": (42.3609, -71.0567, "Faneuil Hall", "25 Union St, Boston", "Hennessy's Bar"),
    "uncommon corner": (42.3524, -71.0653, "Downtown", "Boylston St & Tremont St, Boston", "UnCommon Corner"),
    "make way for ducklings statue, boston public garden": (42.3551, -71.0697, "Boston Common", "Boston Public Garden, 4 Charles St, Boston", "Make Way For Ducklings Statue"),
    "make way for ducklings statue": (42.3551, -71.0697, "Boston Common", "Boston Public Garden, 4 Charles St, Boston", "Make Way For Ducklings Statue"),
    "make way for ducklings": (42.3551, -71.0697, "Boston Common", "Boston Public Garden, 4 Charles St, Boston", "Make Way For Ducklings Statue"),
    "boston public garden": (42.3542, -71.0704, "Boston Common", "4 Charles St, Boston", "Boston Public Garden"),
    "park street station": (42.3564, -71.0624, "Downtown", "Tremont St & Park St, Boston", "Park Street Station"),
    "park street": (42.3564, -71.0624, "Downtown", "Tremont St & Park St, Boston", "Park Street Station"),
    "roundhead brewing": (42.2472, -71.1344, "Hyde Park", "1 Westinghouse Plaza, Suite i107, Hyde Park", "Roundhead Brewing"),
    "roundhead brewing company": (42.2472, -71.1344, "Hyde Park", "1 Westinghouse Plaza, Suite i107, Hyde Park", "Roundhead Brewing"),
    "tufts university": (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Granoff Music Center, Tufts University"),
    "granoff music center, tufts university": (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Granoff Music Center, Tufts University"),
    "granoff music center": (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Granoff Music Center, Tufts University"),
    "redbones": (42.3967, -71.1215, "Davis Square", "55 Chester St, Somerville", "Redbones / Underbones"),
    "redbones bbq": (42.3967, -71.1215, "Davis Square", "55 Chester St, Somerville", "Redbones / Underbones"),
    "the black rose": (42.3596, -71.0543, "Faneuil Hall", "160 State St, Boston", "The Black Rose"),
    "black rose": (42.3596, -71.0543, "Faneuil Hall", "160 State St, Boston", "The Black Rose"),
    "emmets irish pub": (42.3582, -71.0617, "Beacon Hill", "6 Beacon St, Boston", "Emmets Irish Pub"),
    "emmets": (42.3582, -71.0617, "Beacon Hill", "6 Beacon St, Boston", "Emmets Irish Pub"),
    "portico brewing": (42.3748, -71.0911, "Ward Two", "101 South St, Somerville", "Portico Brewing"),

    # Central Square
    "middle east": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "The Middle East"),
    "the middle east": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "The Middle East"),
    "middle east downstairs": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Downstairs"),
    "middle east - downstairs": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Downstairs"),
    "middle east upstairs": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Upstairs"),
    "middle east - upstairs": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Upstairs"),
    "middle east cornerbakery": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Corner/Bakery"),
    "middle east - corner/bakery": (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Corner/Bakery"),
    "middle east zuzu": (42.3638, -71.1018, "Central Square", "474 Massachusetts Ave, Cambridge", "Middle East - ZuZu"),
    "middle east - zuzu": (42.3638, -71.1018, "Central Square", "474 Massachusetts Ave, Cambridge", "Middle East - ZuZu"),
    "zuzu": (42.3638, -71.1018, "Central Square", "474 Massachusetts Ave, Cambridge", "ZuZu"),
    "sonia": (42.3638, -71.1018, "Central Square", "10 Brookline St, Cambridge", "Sonia"),
    "the cantab lounge": (42.3662, -71.1061, "Central Square", "738 Massachusetts Ave, Cambridge", "The Cantab Lounge"),
    "cantab lounge": (42.3662, -71.1061, "Central Square", "738 Massachusetts Ave, Cambridge", "The Cantab Lounge"),
    "cantab underground": (42.3662, -71.1061, "Central Square", "738 Massachusetts Ave, Cambridge (Downstairs)", "Cantab Underground"),
    "havana club": (42.3649, -71.1026, "Central Square", "288 Green St, Cambridge", "Havana Club"),
    "hava nightclub": (42.3507, -71.0647, "Theater District", "246 Tremont St, Boston", "Hava Nightclub"),
    "manray": (42.3662, -71.1027, "Central Square", "40 Prospect St, Cambridge", "ManRay"),
    "middlesex lounge": (42.3619, -71.0988, "Central Square", "315 Massachusetts Ave, Cambridge", "Middlesex Lounge"),
    "middlesex": (42.3619, -71.0988, "Central Square", "315 Massachusetts Ave, Cambridge", "Middlesex Lounge"),
    "the phoenix landing": (42.3641, -71.1019, "Central Square", "512 Massachusetts Ave, Cambridge", "The Phoenix Landing"),
    "phoenix landing": (42.3641, -71.1019, "Central Square", "512 Massachusetts Ave, Cambridge", "The Phoenix Landing"),
    "roxy's arcade": (42.3623, -71.0995, "Central Square", "292 Massachusetts Ave, Cambridge", "Roxy's Arcade"),
    "roxys arcade": (42.3623, -71.0995, "Central Square", "292 Massachusetts Ave, Cambridge", "Roxy's Arcade"),
    "a4cade": (42.3623, -71.0995, "Central Square", "292 Massachusetts Ave, Cambridge", "Roxy's Arcade"),
    "the mad monkfish": (42.3642, -71.1020, "Central Square", "524 Massachusetts Ave, Cambridge", "The Mad Monkfish"),
    "la fabrica central": (42.3633, -71.1011, "Central Square", "450 Massachusetts Ave, Cambridge", "La Fabrica Central"),
    "central square theater": (42.3633, -71.1011, "Central Square", "450 Massachusetts Ave, Cambridge", "Central Square Theater"),
    "central square theatre": (42.3633, -71.1011, "Central Square", "450 Massachusetts Ave, Cambridge", "Central Square Theater"),
    "central square farmers market": (42.3649, -71.1009, "Central Square", "76 Bishop Allen Dr, Cambridge", "Central Square Farmers Market"),
    "ywca cambridge": (42.3668, -71.1043, "Central Square", "7 Temple St, Cambridge", "YWCA Cambridge"),
    "lamplighter brewing": (42.3688, -71.0994, "Cambridgeport", "284 Broadway, Cambridge", "Lamplighter Brewing Co."),
    "the foundry": (42.3666, -71.0828, "East Cambridge", "101 Rogers St, Cambridge", "The Foundry"),
    "the dance complex": (42.3648, -71.1030, "Central Square", "536 Massachusetts Ave, Cambridge", "The Dance Complex"),
    "dance complex": (42.3648, -71.1030, "Central Square", "536 Massachusetts Ave, Cambridge", "The Dance Complex"),
    "dante alighieri society": (42.3728, -71.0994, "Kendall / Inman", "41 Hampshire St, Cambridge", "Dante Alighieri Society"),
    "multicultural arts center": (42.3698, -71.0784, "East Cambridge", "41 Second St, Cambridge", "Multicultural Arts Center"),

    # Inman Square
    "the druid": (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid"),
    "druid": (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid"),
    "the lilypad": (42.3737, -71.1001, "Inman Square", "1353 Cambridge St, Cambridge", "The Lilypad"),
    "lilypad": (42.3737, -71.1001, "Inman Square", "1353 Cambridge St, Cambridge", "The Lilypad"),
    "gather here": (42.3736, -71.1000, "Inman Square", "1343 Cambridge St, Cambridge", "Gather Here"),

    # Kendall Square & MIT
    "mit museum": (42.3621, -71.0858, "Kendall Square", "314 Main St, Cambridge", "MIT Museum"),
    "venture café": (42.3626, -71.0837, "Kendall Square", "1 Broadway, Cambridge", "Venture Café Cambridge"),
    "venture cafe": (42.3626, -71.0837, "Kendall Square", "1 Broadway, Cambridge", "Venture Café Cambridge"),
    "mit strategic games society": (42.3590, -71.0940, "Kendall Square / MIT", "84 Massachusetts Ave, Cambridge", "MIT Strategic Games Society"),
    "mit events": (42.3590, -71.0940, "Kendall Square / MIT", "Cambridge", "MIT Campus"),
    "mit open space": (42.3621, -71.0864, "Kendall Square", "292 Main St, Cambridge", "MIT Open Space"),
    "kendall square farmers market": (42.3634, -71.0820, "Kendall Square", "350 Kendall St, Cambridge", "Kendall Square Farmers Market"),
    "kendall center": (42.3625, -71.0865, "Kendall Square", "90 Broadway, Cambridge", "Kendall Center"),
    "urban park roof garden": (42.3625, -71.0865, "Kendall Square", "90 Broadway, Cambridge", "Urban Park Roof Garden"),
    "cambridge crossing": (42.3724, -71.0746, "Cambridge Crossing", "222 Jacobs St, Cambridge", "Cambridge Crossing"),
    "batifol": (42.3639, -71.0829, "Kendall Square", "291 3rd St, Cambridge", "Batifol"),
    "the platform": (42.3637, -71.0827, "Kendall Square", "315 Kendall St, Cambridge, MA 02142", "The Platform Kendall"),
    "the platform kendall": (42.3637, -71.0827, "Kendall Square", "315 Kendall St, Cambridge, MA 02142", "The Platform Kendall"),

    # Cambridgeport & Central Square
    "the plough and stars": (42.3683, -71.1088, "Cambridgeport", "912 Massachusetts Ave, Cambridge", "The Plough and Stars"),
    "plough and stars": (42.3683, -71.1088, "Cambridgeport", "912 Massachusetts Ave, Cambridge", "The Plough and Stars"),
    "remnant satellite": (42.3725, -71.0905, "East Cambridge", "877 Cambridge St, Cambridge", "Remnant Satellite"),
    "satellite remnant": (42.3725, -71.0905, "East Cambridge", "877 Cambridge St, Cambridge", "Remnant Satellite"),

    # Porter Square & North Cambridge
    "dear annie": (42.3878, -71.1195, "Porter Square", "1741 Massachusetts Ave, Cambridge", "Dear Annie"),
    "mccarthy's toad": (42.3892, -71.1195, "Porter Square", "1920 Massachusetts Ave, Cambridge", "Toad"),
    "toad": (42.3892, -71.1195, "Porter Square", "1920 Massachusetts Ave, Cambridge", "Toad"),
    "porter square books": (42.3888, -71.1192, "Porter Square", "25 White St, Cambridge", "Porter Square Books"),
    "cafe zing": (42.3888, -71.1192, "Porter Square", "25 White St, Cambridge", "Cafe Zing"),
    "ikeda center": (42.3717, -71.1137, "Harvard Square", "396 Harvard St, Cambridge", "Ikeda Center for Peace, Learning, and Dialogue"),
    "lizard lounge": (42.3809, -71.1197, "North Cambridge", "1667 Massachusetts Ave, Cambridge", "Lizard Lounge"),
    "central rock gym": (42.3940, -71.1516, "North Cambridge", "127 Smith Pl, Cambridge", "Central Rock Gym"),

    # Davis Square & Teele Square
    "the burren": (42.3963, -71.1224, "Davis Square", "247 Elm St, Somerville", "The Burren"),
    "westie 617": (42.3937, -71.1194, "Davis Square", "351 Summer St, Somerville", "Westie 617"),
    "somerville theatre": (42.3968, -71.1228, "Davis Square", "55 Davis Sq, Somerville", "Somerville Theatre"),
    "crystal ballroom": (42.3968, -71.1228, "Davis Square", "55 Davis Sq, Somerville", "Crystal Ballroom"),
    "the rockwell": (42.3963, -71.1224, "Davis Square", "255 Elm St, Somerville", "The Rockwell"),
    "underbones": (42.3967, -71.1215, "Davis Square", "55 Chester St, Somerville", "Underbones"),
    "painted burro somerville": (42.3961, -71.1220, "Davis Square", "219 Elm St, Somerville", "Painted Burro"),
    "davis square farmers market": (42.3968, -71.1228, "Davis Square", "Day St & Herbert St, Somerville", "Davis Square Farmers Market"),
    "blues union": (42.3995, -71.1278, "Teele Square", "160 Holland St, Somerville", "Blues Union"),

    # Union Square & Somerville
    "warehouse xi": (42.3807, -71.0957, "Union Square", "11 Sanborn Ct, Somerville", "Warehouse XI"),
    "the jungle": (42.3807, -71.0955, "Union Square", "6 Sanborn Ct, Somerville", "The Jungle Community Music Club"),
    "the jungle community music club": (42.3807, -71.0955, "Union Square", "6 Sanborn Ct, Somerville", "The Jungle Community Music Club"),
    "sally o'brien's": (42.3822, -71.0998, "Union Square", "335 Somerville Ave, Somerville", "Sally O'Brien's"),
    "sally obriens": (42.3822, -71.0998, "Union Square", "335 Somerville Ave, Somerville", "Sally O'Brien's"),
    "duck duck goofs": (42.3802, -71.0962, "Union Square", "10-12 Bow St, Somerville", "Duck Duck Goofs"),
    "goofs comedy club": (42.3802, -71.0962, "Union Square", "10-12 Bow St, Somerville", "Goofs Comedy Club"),
    "side quest books & games": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Side Quest Books & Games"),
    "side quest books": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Side Quest Books & Games"),
    "aeronaut brewing": (42.3814, -71.1066, "Somerville", "14 Tyler St, Somerville", "Aeronaut Brewing"),
    "craft loft": (42.3814, -71.1066, "Somerville", "14 Tyler St, Somerville", "Craft Loft"),
    "remnant brewing": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Remnant Brewing"),
    "remnant somerville": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Remnant Brewing"),
    "bow market": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Bow Market"),
    "rebel rebel": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Rebel Rebel"),
    "rebel rebel wine bar": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Rebel Rebel"),
    "wild child": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Wild Child"),
    "upstairs at bow": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Upstairs at Bow"),
    "dark mode at bow market": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "DARK MODE at Bow Market"),
    "vera's": (42.3797, -71.0962, "Union Square", "70 Union Sq, Somerville", "Vera's"),
    "union square farmers market": (42.3797, -71.0962, "Union Square", "66 Union Sq, Somerville", "Union Square Farmers Market"),
    "arts at the armory": (42.3897, -71.106, "Spring Hill", "191 Highland Ave, Somerville", "Arts at the Armory"),
    "somerville arts council": (42.3875, -71.0995, "Somerville", "Somerville, MA", "Somerville Arts Council"),
    "somerville community growing center": (42.3828, -71.0980, "Spring Hill", "22 Vinal Ave, Somerville", "Somerville Community Growing Center"),
    "growing center": (42.3828, -71.0980, "Spring Hill", "22 Vinal Ave, Somerville", "Somerville Community Growing Center"),
    "sabina mezcalería": (42.3965, -71.1039, "Winter Hill", "514 Medford St, Somerville", "Sabina Mezcalería"),
    "sabina": (42.3965, -71.1039, "Winter Hill", "514 Medford St, Somerville", "Sabina Mezcalería"),
    "somerville public library": (42.3858, -71.0944, "Somerville", "79 Highland Ave, Somerville", "Somerville Public Library"),
    "somerville city hall": (42.3871, -71.0963, "Spring Hill", "93 Highland Ave, Somerville", "Somerville City Hall"),
    "city of somerville": (42.3871, -71.0963, "Spring Hill", "93 Highland Ave, Somerville", "Somerville City Hall"),
    "cisco brewers fenway": (42.3444, -71.0991, "Fenway", "1301 Boylston St, Boston", "Cisco Brewers Fenway"),
    # Nightlife and taproom venues (addresses from each venue's own site, Nov 2026). Exact names
    # only for the short ones: "Hong Kong" alone is the Faneuil Hall club, while "Hong Kong
    # Restaurant (Harvard Square)" is a different place; a bare "Mighty Squirrel" could be any of
    # its three taprooms, so it stays unplaced.
    "mighty squirrel fenway": (42.3477, -71.0991, "Fenway", "1 David Ortiz Dr, Boston", "Mighty Squirrel Fenway"),
    "mighty squirrel arsenal yards": (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards"),
    "mighty squirrel watertown": (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards"),
    "mighty squirrel waltham": (42.3843, -71.2160, "Waltham", "411 Waverley Oaks Rd, Waltham", "Mighty Squirrel Waltham"),
    "luckys lounge": (42.3505, -71.0484, "Fort Point", "355 Congress St, Boston", "Lucky's Lounge"),
    "city tap house": (42.3509, -71.0470, "Seaport", "10 Boston Wharf Rd, Boston", "City Tap House"),
    "white bull tavern": (42.3607, -71.0571, "Faneuil Hall", "1 Union St, Boston", "White Bull Tavern"),
    "caveau": (42.3594, -71.0599, "Government Center", "1 Center Plaza, Boston", "Caveau"),
    "caveau boston": (42.3594, -71.0599, "Government Center", "1 Center Plaza, Boston", "Caveau"),
    "ned devines": (42.3600, -71.0548, "Faneuil Hall", "1 Faneuil Hall Marketplace, Boston", "Ned Devine's"),
    "hong kong": (42.3592, -71.0548, "Faneuil Hall", "65 Chatham St, Boston", "Hong Kong"),
    "hong kong boston": (42.3592, -71.0548, "Faneuil Hall", "65 Chatham St, Boston", "Hong Kong"),
    "urban wild": (42.3810, -71.0745, "Charlestown", "100 Hood Park Dr, Boston", "Urban Wild"),
    "cactus club cafe": (42.3505, -71.0727, "Back Bay", "500 Boylston St, Boston", "Cactus Club Cafe"),
    # Clubs from Bijou's Posh pages, Sissy K's site and the 6one7 / Dope Eventbrite events (Nov 2026).
    "bijou nightclub": (42.3512, -71.0642, "Theater District", "51 Stuart St, Boston", "Bijou Nightclub"),
    "bijou nightclub & lounge": (42.3512, -71.0642, "Theater District", "51 Stuart St, Boston", "Bijou Nightclub"),
    "bijou boston": (42.3512, -71.0642, "Theater District", "51 Stuart St, Boston", "Bijou Nightclub"),
    "sissy ks": (42.3612, -71.0527, "Faneuil Hall", "6 Commercial St, Boston", "Sissy K's"),
    "icon nightclub": (42.3507, -71.0662, "Theater District", "100 Warrenton St, Boston", "Icon Nightclub"),
    "venu nightclub": (42.3507, -71.0662, "Theater District", "100 Warrenton St, Boston", "Venu Nightclub"),
    "clerys": (42.3462, -71.0752, "South End", "113 Dartmouth St, Boston", "Clerys"),
    "scorpion boston": (42.3524, -71.0475, "Seaport", "58 Seaport Blvd, Boston", "Scorpion Bar"),
    "spy bar": (42.3463, -71.0700, "South End", "40 Berkeley St, Boston", "Spy Bar"),
    "spybar": (42.3463, -71.0700, "South End", "40 Berkeley St, Boston", "Spy Bar"),
    "spy bar boston": (42.3463, -71.0700, "South End", "40 Berkeley St, Boston", "Spy Bar"),
    "bsmnt boston": (42.3508, -71.0657, "Theater District", "100 Stuart St, Boston", "bsmnt"),
    "w boston": (42.3508, -71.0657, "Theater District", "100 Stuart St, Boston", "W Boston"),
    "tucks arcadium": (42.3722, -71.1203, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Tuck's Arcadium"),
    "cisco brewers": (42.3444, -71.0991, "Fenway", "1301 Boylston St, Boston", "Cisco Brewers Fenway"),
    "northeastern university": (42.3398, -71.0891, "Fenway", "360 Huntington Ave, Boston", "Northeastern University"),
    "blackman auditorium": (42.3398, -71.0891, "Fenway", "360 Huntington Ave, Boston", "Blackman Auditorium"),
    "once somerville": (42.3748, -71.0911, "Boynton Yards", "101 South St, Somerville", "ONCE Somerville"),
    "all she wrote books": (42.3816, -71.0848, "East Somerville", "75 Washington St, Somerville", "All She Wrote Books"),
    "comicazi": (42.3961, -71.1212, "Davis Square", "407 Highland Ave, Somerville", "Comicazi"),
    "snowport holiday market": (42.3517, -71.0446, "Seaport", "100 Seaport Blvd, Boston", "Snowport Holiday Market"),
    "snowport": (42.3517, -71.0446, "Seaport", "100 Seaport Blvd, Boston", "Snowport Holiday Market"),
    "the bca cyclorama": (42.3448, -71.0714, "South End", "539 Tremont St, Boston", "The BCA Cyclorama"),
    "bca cyclorama": (42.3448, -71.0714, "South End", "539 Tremont St, Boston", "The BCA Cyclorama"),
    "cyclorama": (42.3448, -71.0714, "South End", "539 Tremont St, Boston", "The BCA Cyclorama"),
    "bca mills gallery": (42.3444, -71.0716, "South End", "551 Tremont St, Boston", "BCA Mills Gallery"),
    "mills gallery": (42.3444, -71.0716, "South End", "551 Tremont St, Boston", "BCA Mills Gallery"),
    "the chester tavern": (42.3808, -71.0994, "Somerville Ave", "366 Somerville Ave, Somerville", "The Chester Tavern"),
    "chester tavern": (42.3808, -71.0994, "Somerville Ave", "366 Somerville Ave, Somerville", "The Chester Tavern"),
    "portico brewing": (42.3748, -71.0911, "Boynton Yards", "101 South St, Somerville", "Portico Brewing"),
    "dance union": (42.3807, -71.0973, "Union Square", "16 Bow St, Somerville", "Dance Union"),
    "dance union studio": (42.3807, -71.0973, "Union Square", "16 Bow St, Somerville", "Dance Union"),
    "winter hill brewing": (42.3927, -71.0933, "Winter Hill", "328 Broadway, Somerville", "Winter Hill Brewing Co."),
    "the independent": (42.3799, -71.0946, "Union Square", "75 Union Square, Somerville", "The Independent"),
    "olde magoun's saloon": (42.3966, -71.1040, "Magoun Square", "518 Medford St, Somerville", "Olde Magoun's Saloon"),
    "the biltmore": (42.3750, -71.0955, "Somerville", "1205 Cambridge St, Somerville", "The Biltmore"),
    "somart at the hive": (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "SomArt at the Hive"),
    "boston figure art center": (42.3797, -71.0982, "Union Square", "285 Washington St, Somerville", "Boston Figure Art Center"),
    "boston figurative art center": (42.3797, -71.0982, "Union Square", "285 Washington St, Somerville", "Boston Figure Art Center"),
    "bfac": (42.3797, -71.0982, "Union Square", "285 Washington St, Somerville", "Boston Figure Art Center"),
    "life drawing boston": (42.3786, -71.0866, "East Somerville", "72 Joy St, Somerville", "Life Drawing Boston"),
    "the loov": (42.3786, -71.0866, "East Somerville", "72 Joy St, Somerville", "Life Drawing Boston"),
    "loov": (42.3786, -71.0866, "East Somerville", "72 Joy St, Somerville", "Life Drawing Boston"),
    "perry park": (42.3792, -71.1032, "Somerville", "355 Washington St, Somerville", "Perry Park"),
    "nathan tufts park": (42.4014, -71.1189, "Powderhouse", "Broadway, Somerville", "Nathan Tufts Park"),
    "assembly row": (42.3928, -71.0776, "Assembly Row", "Assembly Row, Somerville", "Assembly Row"),

    # Holiday Markets & Pop-ups
    "arsenal yards": (42.3615, -71.1605, "Watertown", "Bond Sq, Watertown", "Arsenal Yards"),
    "sowa power station": (42.3413, -71.0672, "South End", "540 Harrison Ave, Boston", "SoWa Power Station"),
    "christopher columbus waterfront park": (42.3605, -71.0505, "North End", "110 Atlantic Ave, Boston", "Christopher Columbus Waterfront Park"),
    "christopher columbus park": (42.3605, -71.0505, "North End", "110 Atlantic Ave, Boston", "Christopher Columbus Waterfront Park"),
    "park-9 dog bar": (42.3995, -71.0665, "Everett", "48 Commercial St, Everett", "Park-9 Dog Bar"),
    "park 9 dog bar": (42.3995, -71.0665, "Everett", "48 Commercial St, Everett", "Park-9 Dog Bar"),
    "boston public market": (42.3618, -71.0567, "Downtown", "100 Hanover St, Boston", "Boston Public Market"),
    "kilroy square": (42.2510, -71.0037, "Quincy", "Kilroy Square, Quincy", "Kilroy Square"),
    "charles street": (42.3575, -71.0697, "Beacon Hill", "Charles St, Boston", "Charles Street"),
    "german international school boston": (42.3582, -71.1396, "Allston", "57 Holton St, Boston", "German International School Boston"),
    "newbury street": (42.3503, -71.0815, "Back Bay", "Newbury St, Boston", "Newbury Street"),
    "crimson galleria": (42.3718, -71.1205, "Harvard Square", "57 JFK St, Cambridge", "Crimson Galleria"),
    "boston center for the arts": (42.3448, -71.0714, "South End", "539 Tremont St, Boston", "Boston Center for the Arts"),
    "canal district kendall": (42.3629, -71.0827, "Kendall Square", "300 Athenaeum St, Cambridge", "Canal District Kendall"),
    "one brattle square": (42.3734, -71.1208, "Harvard Square", "1 Brattle Sq, Cambridge", "One Brattle Square"),
    "station st. studios": (42.3333, -71.1197, "Brookline", "15 Station St, Brookline", "Station St. Studios"),
    "station street studios": (42.3333, -71.1197, "Brookline", "15 Station St, Brookline", "Station St. Studios"),
    "the clay table": (42.3648, -71.1028, "Central Square", "19 Brookline St, Cambridge", "The Clay Table"),
    "clay table": (42.3648, -71.1028, "Central Square", "19 Brookline St, Cambridge", "The Clay Table"),
    "tuck's arcadium": (42.3725, -71.1205, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Tuck's Arcadium"),
    "tucks arcadium": (42.3725, -71.1205, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Tuck's Arcadium"),
    "special interest social": (42.3725, -71.1205, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Special Interest Social"),
    "tuscan village": (42.7788, -71.2185, "Salem, NH", "9 Via Toscana, Salem, NH", "Tuscan Village"),
    "seaport common": (42.3517, -71.0446, "Seaport", "85 Northern Ave, Boston", "Seaport Common"),
    "union square": (42.3797, -71.0965, "Union Square", "Union Square, Somerville", "Union Square"),
    "south end": (42.3440, -71.0700, "South End", "Tremont St, Boston", "South End"),

    # Medford, Malden, Arlington & Suburbs
    "idle hands craft ales": (42.4284, -71.0743, "Malden Center", "89 Commercial St, Malden", "Idle Hands Craft Ales"),
    "idle hands": (42.4284, -71.0743, "Malden Center", "89 Commercial St, Malden", "Idle Hands Craft Ales"),
    "boda borg": (42.4271, -71.0664, "Malden Center", "90 Pleasant St, Malden", "Boda Borg"),
    "boda borg boston": (42.4271, -71.0664, "Malden Center", "90 Pleasant St, Malden", "Boda Borg"),
    "hugh o'neill's": (42.4268, -71.0682, "Malden Center", "45 Pleasant St, Malden", "Hugh O'Neill's"),
    "hugh o'neill's pub": (42.4268, -71.0682, "Malden Center", "45 Pleasant St, Malden", "Hugh O'Neill's"),
    "deep cuts": (42.4179, -71.1102, "Medford Square", "21 Main St, Medford", "Deep Cuts"),
    "saint athanasius the great greek orthodox church": (42.4172, -71.1643, "Arlington", "4 Appleton St, Arlington, MA 02476", "Saint Athanasius Greek Orthodox Church"),
    "saint athanasius": (42.4172, -71.1643, "Arlington", "4 Appleton St, Arlington, MA 02476", "Saint Athanasius Greek Orthodox Church"),
    "regent theatre": (42.415, -71.1508, "Arlington", "7 Medford St, Arlington", "Regent Theatre"),
    "painted burro waltham": (42.3765, -71.2372, "Waltham", "665 Main St, Waltham", "Painted Burro Waltham"),
    "gillette stadium": (42.0909, -71.2643, "Foxborough", "1 Patriot Pl, Foxborough", "Gillette Stadium"),

    # Downtown, Theater District & Chinatown
    "royale": (42.3508, -71.0654, "Theater District", "279 Tremont St, Boston", "Royale"),
    "the wilbur": (42.3516, -71.0648, "Theater District", "246 Tremont St, Boston", "The Wilbur"),
    "wilbur theatre": (42.3516, -71.0648, "Theater District", "246 Tremont St, Boston", "The Wilbur"),
    "wilbur theater": (42.3516, -71.0648, "Theater District", "246 Tremont St, Boston", "The Wilbur"),
    "modern theatre": (42.3533, -71.0622, "Downtown Crossing", "525 Washington St, Boston", "Modern Theatre"),
    "modern theatre - suffolk university": (42.3533, -71.0622, "Downtown Crossing", "525 Washington St, Boston", "Modern Theatre"),
    "high street place": (42.3537, -71.0543, "Downtown / Financial District", "100 High St, Boston", "High Street Place"),
    "the huntington theatre": (42.3421, -71.0858, "Back Bay", "264 Huntington Ave, Boston", "The Huntington Theatre"),
    "the substation (roslindale)": (42.2868, -71.1287, "Roslindale", "4228 Washington St, Roslindale", "The Substation (Roslindale)"),
    "distraction brewing": (42.2869, -71.1301, "Roslindale", "2 Belgrade Ave, Roslindale", "Distraction Brewing"),
    "birch st plaza": (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Birch St Plaza"),
    "birch street plaza": (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Birch St Plaza"),
    "roslindale village": (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Roslindale Village"),
    "emerald society": (42.2865, -71.1291, "Roslindale", "10 Birch St, Roslindale, MA 02131", "Emerald Society"),
    "music on centre": (42.2863, -71.1538, "West Roxbury", "1859 Centre St, West Roxbury", "Music on Centre"),
    "edward m. kennedy institute": (42.3154, -71.0340, "Dorchester", "210 Morrissey Blvd, Dorchester", "Edward M. Kennedy Institute"),
    "dorchester historical society": (42.3233, -71.0609, "Dorchester", "195 Boston St, Dorchester", "Dorchester Historical Society"),
    "bca plaza theatre": (42.3440, -71.0708, "South End", "539 Tremont St, Boston", "BCA Plaza Theatre"),
    "multicultural arts center": (42.3697, -71.0793, "East Cambridge", "41 Second St, Cambridge", "Multicultural Arts Center"),
    "mit green building": (42.3604, -71.0894, "Kendall Square", "21 Ames St, Cambridge", "MIT Green Building"),
    "bu studio one": (42.3505, -71.1142, "Fenway", "855 Commonwealth Ave, Boston", "BU Studio ONE"),
    "dorchester brewing company": (42.3219, -71.0626, "Dorchester", "1250 Massachusetts Ave, Boston", "Dorchester Brewing Company"),
    "dorchester brewing": (42.3219, -71.0626, "Dorchester", "1250 Massachusetts Ave, Boston", "Dorchester Brewing Company"),
    "cambridge center for adult education": (42.3744, -71.1219, "Harvard Square", "42 Brattle St, Cambridge", "CCAE (Cambridge Center for Adult Education)"),
    "boch center wang theatre": (42.3509, -71.0651, "Theater District", "270 Tremont St, Boston", "Boch Center Wang Theatre"),
    "boch center shubert theatre": (42.3513, -71.0651, "Theater District", "265 Tremont St, Boston", "Boch Center Shubert Theatre"),
    "emerson colonial theatre": (42.3524, -71.0658, "Theater District", "106 Boylston St, Boston", "Emerson Colonial Theatre"),
    "colonial theatre": (42.3524, -71.0658, "Theater District", "106 Boylston St, Boston", "Emerson Colonial Theatre"),
    "colonial theater": (42.3524, -71.0658, "Theater District", "106 Boylston St, Boston", "Emerson Colonial Theatre"),
    "emerson colonial theater": (42.3524, -71.0658, "Theater District", "106 Boylston St, Boston", "Emerson Colonial Theatre"),
    "charles playhouse": (42.3512, -71.0658, "Theater District", "74 Warrenton St, Boston", "Charles Playhouse"),
    "charles playhouse theater 2": (42.3512, -71.0658, "Theater District", "74 Warrenton St, Boston", "Charles Playhouse"),
    "winthrop center": (42.3541, -71.0568, "Downtown", "115 Federal St, Boston", "Winthrop Center"),
    "the winthrop center park": (42.3541, -71.0568, "Downtown", "115 Federal St, Boston", "Winthrop Center"),
    "emerson paramount center": (42.3533, -71.0628, "Theater District", "559 Washington St, Boston", "Emerson Paramount Center"),
    "emerson cutler majestic theatre": (42.3519, -71.0645, "Theater District", "219 Tremont St, Boston", "Emerson Cutler Majestic Theatre"),
    "cutler majestic theatre": (42.3519, -71.0645, "Theater District", "219 Tremont St, Boston", "Emerson Cutler Majestic Theatre"),
    "citizens bank opera house": (42.3541, -71.0617, "Downtown Crossing", "539 Washington St, Boston", "Citizens Bank Opera House"),
    "citizens opera house": (42.3541, -71.0617, "Downtown Crossing", "539 Washington St, Boston", "Citizens Bank Opera House"),
    "broadway in boston": (42.3541, -71.0617, "Downtown Crossing", "539 Washington St, Boston", "Citizens Bank Opera House"),
    "orpheum theatre": (42.3567, -71.0601, "Downtown", "1 Hamilton Pl, Boston", "Orpheum Theatre"),
    "versus boston": (42.3569, -71.0600, "Downtown Crossing", "42 Province St, Boston", "Versus Boston"),
    "nick's comedy stop": (42.3512, -71.0664, "Theater District", "100 Warrenton St, Boston", "Nick's Comedy Stop"),
    "the tam": (42.3521, -71.0645, "Theater District", "222 Tremont St, Boston", "The Tam"),
    # W Boston basement, per bsmnt's own Posh venue and site (was 140 Boylston St).
    "bsmnt": (42.3508, -71.0657, "Theater District", "100 Stuart St, Boston", "bsmnt"),
    "jacques cabaret": (42.3499, -71.0691, "Bay Village", "79 Broadway, Boston", "Jacques' Cabaret"),
    "jacques' cabaret": (42.3499, -71.0691, "Bay Village", "79 Broadway, Boston", "Jacques' Cabaret"),
    "biddy early's": (42.3551, -71.0544, "Financial District", "141 Pearl St, Boston", "Biddy Early's"),
    "boston common": (42.3550, -71.0656, "Downtown", "139 Tremont St, Boston", "Boston Common"),
    "boston public garden": (42.3542, -71.0704, "Back Bay", "4 Charles St, Boston", "Boston Public Garden"),
    "hatch shell": (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "Hatch Memorial Shell"),
    "esplanade": (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "The Esplanade"),
    "charles river": (42.3600, -71.0720, "Charles River / Esplanade", "Charles River Esplanade, Boston", "Charles River"),
    "charles river esplanade": (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "The Esplanade"),
    "head of the charles": (42.3695, -71.1235, "Charles River", "Charles River, Boston", "Head of the Charles Regatta"),
    "head of the charles regatta": (42.3695, -71.1235, "Charles River", "Charles River, Boston", "Head of the Charles Regatta"),
    "the head of the charles regatta 2026": (42.3695, -71.1235, "Charles River", "Charles River, Boston", "Head of the Charles Regatta"),
    "boston university sailing pavilion": (42.3525, -71.0745, "Charles River", "Charles River Esplanade, Boston", "BU Sailing Pavilion"),
    "bu sailing pavilion": (42.3525, -71.0745, "Charles River", "Charles River Esplanade, Boston", "BU Sailing Pavilion"),
    "charles river boat company": (42.3670, -71.0710, "Charles River", "Charles River, Boston", "Charles River Boat Company"),
    "charlesgate park": (42.3503, -71.0898, "Back Bay / Fenway", "Charlesgate, Boston", "Charlesgate Park"),
    "greenway artisan market": (42.3575, -71.0515, "Downtown Waterfront", "Atlantic Ave, Boston", "Rose Kennedy Greenway"),
    "rose kennedy greenway": (42.3550, -71.0520, "Downtown / Waterfront", "Atlantic Ave, Boston", "Rose Kennedy Greenway"),
    "the greenway": (42.3550, -71.0520, "Downtown / Waterfront", "Atlantic Ave, Boston", "Rose Kennedy Greenway"),

    # North Station, West End & TD Garden
    "td garden": (42.3662, -71.0621, "West End / North Station", "100 Legends Way, Boston", "TD Garden"),
    "big night live": (42.3656, -71.0617, "West End / North Station", "110 Causeway St, Boston", "Big Night Live"),
    "the sports museum": (42.3662, -71.0621, "West End / North Station", "100 Legends Way, Boston", "The Sports Museum"),
    "city winery boston": (42.3644, -71.0601, "West End", "80 Beverly St, Boston", "City Winery Boston"),
    "the tip tap room": (42.3610, -71.0637, "Beacon Hill", "138 Cambridge St, Boston", "The Tip Tap Room"),
    "the anchor boston": (42.3734, -71.0505, "Charlestown Navy Yard", "1 Shipyard Park, Charlestown", "The Anchor Boston"),

    # Seaport & Fort Point
    "ica boston": (42.3528, -71.0432, "Seaport", "25 Harbor Shore Dr, Boston", "ICA Boston"),
    "laugh boston": (42.3462, -71.0433, "Seaport", "425 Summer St, Boston", "Laugh Boston"),
    "lynn memorial auditorium": (42.4647, -70.9512, "Lynn", "3 City Hall Square, Lynn", "Lynn Memorial Auditorium"),
    "lynn auditorium": (42.4647, -70.9512, "Lynn", "3 City Hall Square, Lynn", "Lynn Memorial Auditorium"),
    "leader bank pavilion": (42.3475, -71.0360, "Seaport", "290 Northern Ave, Boston", "Leader Bank Pavilion"),
    "the grand boston": (42.3524, -71.0475, "Seaport", "58 Seaport Blvd, Boston", "The Grand"),
    "scorpion bar boston": (42.3524, -71.0475, "Seaport", "58 Seaport Blvd, Boston", "Scorpion Bar Boston"),
    "trillium fort point": (42.3518, -71.0494, "Fort Point", "50 Thomson Pl, Boston", "Trillium Fort Point"),
    "kings seaport": (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)"),
    "kings - seaport": (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)"),
    "kings dining and entertainment": (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)"),
    "kings dining & entertainment": (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)"),

    # Back Bay & South End
    "boston public library": (42.3496, -71.0779, "Copley Square", "700 Boylston St, Boston", "Boston Public Library"),
    "copley square": (42.3501, -71.0766, "Copley Square", "560 Boylston St, Boston", "Copley Square"),
    "trident booksellers": (42.3484, -71.0863, "Back Bay", "338 Newbury St, Boston", "Trident Booksellers & Cafe"),
    "the beehive": (42.3444, -71.0706, "South End", "541 Tremont St, Boston", "The Beehive"),
    "wally's café": (42.3409, -71.0827, "South End", "427 Massachusetts Ave, Boston", "Wally's Café"),
    "club cafe": (42.3486, -71.0718, "South End", "209 Columbus Ave, Boston", "Club Café"),
    "club café": (42.3486, -71.0718, "South End", "209 Columbus Ave, Boston", "Club Café"),
    "dani's queer bar": (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar"),
    "danis queer bar": (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar"),
    "lyric stage company": (42.3496, -71.0729, "Back Bay", "140 Clarendon St, Boston", "Lyric Stage Company"),
    "lyric stage": (42.3496, -71.0729, "Back Bay", "140 Clarendon St, Boston", "Lyric Stage Company"),
    "speakeasy stage": (42.3448, -71.0701, "South End", "527 Tremont St, Boston", "SpeakEasy Stage Company"),
    "speakeasy stage company": (42.3448, -71.0701, "South End", "527 Tremont St, Boston", "SpeakEasy Stage Company"),
    "boston lyric opera": (42.3519, -71.0645, "Theater District", "219 Tremont St, Boston", "Boston Lyric Opera"),
    "celebrity series of boston": (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Celebrity Series of Boston"),
    "celebrity series": (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Celebrity Series of Boston"),
    "lesbiannightlife": (42.3219, -71.0626, "Dorchester", "1250 Massachusetts Ave, Dorchester", "LesbianNightLife"),
    "balance patch": (42.3516, -71.1215, "Allston / BU", "1031 Commonwealth Ave, Boston", "Balance Patch"),
    "the balance patch": (42.3516, -71.1215, "Allston / BU", "1031 Commonwealth Ave, Boston", "Balance Patch"),
    "legacy": (42.3512, -71.0660, "Theater District", "79 Warrenton St, Boston", "Legacy Boston"),
    "legacy boston": (42.3512, -71.0660, "Theater District", "79 Warrenton St, Boston", "Legacy Boston"),
    "the alley bar": (42.3582, -71.0592, "Downtown", "14 Pi Alley, Boston", "The Alley Bar"),
    "alley bar": (42.3582, -71.0592, "Downtown", "14 Pi Alley, Boston", "The Alley Bar"),
    "downtown boston": (42.3555, -71.0601, "Downtown / Financial District", "Downtown Crossing, Boston", "Downtown Boston"),
    "downtown crossing": (42.3555, -71.0601, "Downtown / Financial District", "Downtown Crossing, Boston", "Downtown Crossing"),
    "downtown boston bid": (42.3555, -71.0601, "Downtown / Financial District", "Downtown Crossing, Boston", "Downtown Boston BID"),
    "old state house": (42.3587, -71.0578, "Downtown / Financial District", "206 Washington St, Boston", "Old State House"),
    "old south meeting house": (42.3569, -71.0594, "Downtown / Financial District", "310 Washington St, Boston", "Old South Meeting House"),
    "sunset cantina": (42.3503, -71.1187, "Allston / BU", "916 Commonwealth Ave, Boston", "Sunset Cantina"),
    "calderwood pavilion": (42.3448, -71.0701, "South End", "527 Tremont St, Boston", "Calderwood Pavilion"),
    "sowa open market": (42.3413, -71.0672, "South End", "530 Harrison Ave, Boston", "SoWa Open Market"),
    "reunion bbq": (42.3468, -71.0688, "South End", "439 Tremont St, Boston", "Reunion BBQ"),
    "posto south end": (42.3450, -71.0680, "South End", "Washington St, Boston", "Posto South End"),
    "urbanity dance": (42.3424, -71.0664, "South End", "1180 Washington St, Boston", "Urbanity Dance"),
    "lifebloom perfume & candle bar": (42.3435, -71.0718, "South End", "568 Tremont St, Boston", "Lifebloom Candle Bar"),
    "lifebloom candle bar & shop": (42.3435, -71.0718, "South End", "568 Tremont St, Boston", "Lifebloom Candle Bar"),
    "lifebloom": (42.3435, -71.0718, "South End", "568 Tremont St, Boston", "Lifebloom Candle Bar"),
    "goethe-institut": (42.3546, -71.0765, "Back Bay", "170 Beacon St, Boston", "Goethe-Institut Boston"),
    "goethe institut": (42.3546, -71.0765, "Back Bay", "170 Beacon St, Boston", "Goethe-Institut Boston"),

    # Fenway, Kenmore & Symphony
    "fenway park": (42.3467, -71.0972, "Fenway", "4 Jersey St, Boston", "Fenway Park"),
    "mgm music hall": (42.3472, -71.0967, "Fenway", "2 Lansdowne St, Boston", "MGM Music Hall at Fenway"),
    "house of blues": (42.3474, -71.0954, "Fenway", "15 Lansdowne St, Boston", "House of Blues Boston"),
    "loretta's last call": (42.3475, -71.0963, "Fenway", "1 Lansdowne St, Boston", "Loretta's Last Call"),
    "bill's bar": (42.3474, -71.0960, "Fenway", "5 Lansdowne St, Boston", "Bill's Bar"),
    "bills bar": (42.3474, -71.0960, "Fenway", "5 Lansdowne St, Boston", "Bill's Bar"),
    "lansdowne pub": (42.3473, -71.0957, "Fenway", "9 Lansdowne St, Boston", "Lansdowne Pub"),
    "bleacher bar": (42.3468, -71.0975, "Fenway", "82A Lansdowne St, Boston", "Bleacher Bar"),
    "cask 'n flagon": (42.3469, -71.0989, "Fenway", "62 Brookline Ave, Boston", "Cask 'n Flagon"),
    "symphony hall": (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall"),
    "boston symphony orchestra": (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall"),
    "bso": (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall"),
    "jordan hall": (42.3418, -71.0864, "Fenway / Symphony", "30 Gainsborough St, Boston", "Jordan Hall (NEC)"),
    "jordan hall (nec)": (42.3418, -71.0864, "Fenway / Symphony", "30 Gainsborough St, Boston", "Jordan Hall (NEC)"),
    "new england conservatory": (42.3418, -71.0864, "Fenway / Symphony", "290 Huntington Ave, Boston", "New England Conservatory"),
    "berklee performance center": (42.3479, -71.0886, "Back Bay / Fenway", "136 Massachusetts Ave, Boston", "Berklee Performance Center"),
    "the red room at cafe 939": (42.3475, -71.0850, "Back Bay", "939 Boylston St, Boston", "The Red Room at Cafe 939"),
    "cafe 939": (42.3475, -71.0850, "Back Bay", "939 Boylston St, Boston", "The Red Room at Cafe 939"),
    "bebop": (42.3472, -71.0886, "Back Bay / Fenway", "1116 Boylston St, Boston", "The Bebop"),
    "wbur cityspace": (42.3512, -71.1166, "Commonwealth Ave", "890 Commonwealth Ave, Boston", "WBUR CitySpace"),
    "huntington theatre": (42.3421, -71.0853, "Symphony", "264 Huntington Ave, Boston", "Huntington Theatre"),
    "museum of fine arts": (42.3394, -71.0940, "Museum District", "465 Huntington Ave, Boston", "Museum of Fine Arts (MFA)"),
    "isabella stewart gardner museum": (42.3382, -71.0991, "Museum District", "25 Evans Way, Boston", "Isabella Stewart Gardner Museum"),
    "time out market": (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "Time Out Market Boston"),
    "time out market boston": (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "Time Out Market Boston"),
    "401 park": (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "401 Park"),
    "the fenway": (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "The Fenway"),
    "the 88 club": (42.3468, -71.0845, "Back Bay", "50 Dalton St, Boston", "The 88 Club"),
    "88 club": (42.3468, -71.0845, "Back Bay", "50 Dalton St, Boston", "The 88 Club"),

    # Allston & Brighton
    "o'brien's pub": (42.3552, -71.1329, "Allston", "3 Harvard Ave, Allston", "O'Brien's Pub"),
    "obriens pub": (42.3552, -71.1329, "Allston", "3 Harvard Ave, Allston", "O'Brien's Pub"),
    "paradise rock club": (42.3519, -71.1201, "Allston", "967 Commonwealth Ave, Boston", "Paradise Rock Club"),
    "brighton music hall": (42.3527, -71.1326, "Allston", "158 Brighton Ave, Allston", "Brighton Music Hall"),
    "roadrunner": (42.3566, -71.1439, "Boston Landing", "89 Guest St, Brighton", "Roadrunner"),
    "charles river speedway": (42.3616, -71.1447, "Brighton", "525 Western Ave, Boston", "Charles River Speedway"),
    "speedway": (42.3616, -71.1447, "Brighton", "525 Western Ave, Boston", "Charles River Speedway"),
    "silhouette lounge": (42.3533, -71.1332, "Allston", "200 Brighton Ave, Allston", "Silhouette Lounge"),
    "model cafe": (42.3537, -71.1378, "Allston", "7 N Beacon St, Allston", "Model Cafe"),
    "agganis arena": (42.3522, -71.1177, "BU / Allston", "925 Commonwealth Ave, Boston", "Agganis Arena"),
    # College athletics: home facilities in the schools' Sidearm feeds and visiting campuses.
    # scrape_college_athletics maps feed facility names onto these keys.
    "case gym": (42.3524, -71.1165, "BU / Allston", "285 Babcock St, Boston", "Case Gym"),
    "nickerson field": (42.3533, -71.1205, "BU / Allston", "285 Babcock St, Boston", "Nickerson Field"),
    "walter brown arena": (42.3525, -71.1160, "BU / Allston", "285 Babcock St, Boston", "Walter Brown Arena"),
    "conte forum": (42.3353, -71.1667, "Chestnut Hill / Brighton", "140 Commonwealth Ave, Chestnut Hill", "Conte Forum"),
    "matthews arena": (42.3413, -71.0847, "Fenway / Northeastern", "238-262 St Botolph St, Boston", "Matthews Arena"),
    "cabot center": (42.3392, -71.0886, "Fenway / Northeastern", "400 Huntington Ave, Boston", "Cabot Center"),
    "cousens gymnasium": (42.4086, -71.1171, "Medford / Tufts", "161 College Ave, Medford", "Cousens Gymnasium"),
    "ellis oval": (42.4085, -71.1180, "Medford / Tufts", "161 College Ave, Medford", "Ellis Oval"),
    "malkin athletic center": (42.3712, -71.1194, "Harvard Square", "39 Holyoke St, Cambridge", "Malkin Athletic Center"),
    "rockwell cage": (42.3585, -71.0963, "Cambridge / MIT", "120 Vassar St, Cambridge", "Rockwell Cage (MIT)"),
    "zesiger center": (42.3588, -71.0965, "Cambridge / MIT", "120 Vassar St, Cambridge", "Zesiger Sports and Fitness Center (MIT)"),
    "gosman sports and convocation center": (42.3656, -71.2597, "Waltham", "415 South St, Waltham", "Gosman Sports Center (Brandeis)"),
    "clark athletic center": (42.3130, -71.0385, "Dorchester / Columbia Point", "100 Morrissey Blvd, Boston", "Clark Athletic Center (UMass Boston)"),
    "rotch playground": (42.3398, -71.0722, "South End", "Harrison Ave & Randolph St, Boston", "Rotch Field (Emerson)"),
    "staake gymnasium": (42.2963, -71.2642, "Wellesley", "231 Forest St, Babson Park", "Staake Gymnasium (Babson)"),
    "zesiger sports and fitness center (mit)": (42.3588, -71.0965, "Cambridge / MIT", "120 Vassar St, Cambridge", "Zesiger Sports and Fitness Center (MIT)"),
    "gosman sports center (brandeis)": (42.3656, -71.2597, "Waltham", "415 South St, Waltham", "Gosman Sports Center (Brandeis)"),
    "clark athletic center (umass boston)": (42.3130, -71.0385, "Dorchester / Columbia Point", "100 Morrissey Blvd, Boston", "Clark Athletic Center (UMass Boston)"),
    "staake gymnasium (babson)": (42.2963, -71.2642, "Wellesley", "231 Forest St, Babson Park", "Staake Gymnasium (Babson)"),
    "rockwell cage (mit)": (42.3585, -71.0963, "Cambridge / MIT", "120 Vassar St, Cambridge", "Rockwell Cage (MIT)"),
    "fitrec (bu)": (42.3519, -71.1166, "BU / Allston", "915 Commonwealth Ave, Boston", "FitRec (BU)"),
    "bu track & tennis center": (42.3551, -71.1214, "BU / Allston", "100 Ashford St, Boston", "BU Track & Tennis Center"),
    "alumni stadium (bc)": (42.3350, -71.1662, "Chestnut Hill / Brighton", "2609 Beacon St, Chestnut Hill", "Alumni Stadium (BC)"),
    "margot connell recreation center (bc)": (42.3369, -71.1669, "Chestnut Hill / Brighton", "140 Commonwealth Ave, Chestnut Hill", "Margot Connell Recreation Center (BC)"),
    "bc newton campus fields": (42.3413, -71.1923, "Newton", "885 Centre St, Newton", "BC Newton Campus Fields"),
    "tufts athletics": (42.4085, -71.1178, "Medford / Tufts", "161 College Ave, Medford", "Tufts Athletics"),
    "mit athletics": (42.3592, -71.0959, "Cambridge / MIT", "120 Vassar St, Cambridge", "MIT Athletics"),
    "plofker gym (emerson)": (42.3522, -71.0653, "Downtown / Theater District", "150 Boylston St, Boston", "Plofker Gym (Emerson)"),
    "babson athletics": (42.2963, -71.2642, "Wellesley", "231 Forest St, Babson Park", "Babson Athletics"),
    "warrior ice arena": (42.3570, -71.1443, "Brighton", "90 Guest St, Boston", "Warrior Ice Arena"),
    "bentley arena": (42.3866, -71.2209, "Waltham", "175 Forest St, Waltham", "Bentley Arena"),
    "harvard athletics": (42.3667, -71.1265, "Allston", "65 N Harvard St, Boston", "Harvard Athletics"),
    "suffolk athletics (ridgeway gym)": (42.3606, -71.0645, "Beacon Hill", "148 Cambridge St, Boston", "Suffolk Athletics (Ridgeway Gym)"),
    "emmanuel college": (42.3412, -71.1026, "Fenway / Longwood", "400 The Fenway, Boston", "Emmanuel College"),
    "wentworth institute of technology": (42.3367, -71.0951, "Fenway / Mission Hill", "550 Huntington Ave, Boston", "Wentworth Institute of Technology"),
    "simmons university": (42.3392, -71.0996, "Fenway / Longwood", "300 The Fenway, Boston", "Simmons University"),
    "lasell university": (42.3456, -71.2483, "Newton", "1844 Commonwealth Ave, Newton", "Lasell University"),
    "jcc riemer-goldstein theater": (42.3025, -71.1995, "Newton", "333 Nahanton St, Newton", "JCC Greater Boston"),
    "jcc greater boston": (42.3025, -71.1995, "Newton", "333 Nahanton St, Newton", "JCC Greater Boston"),
    "west newton cinema": (42.3497, -71.2268, "West Newton", "1296 Washington St, Newton", "West Newton Cinema"),
    "wellesley college": (42.2934, -71.3060, "Wellesley", "106 Central St, Wellesley", "Wellesley College"),
    "curry college": (42.2389, -71.1146, "Milton", "1071 Blue Hill Ave, Milton", "Curry College"),
    "artisans asylum": (42.3598, -71.1415, "Allston", "96 Holton St, Boston", "Artisans Asylum"),
    "scullers jazz club": (42.3603, -71.1183, "Allston", "400 Soldiers Field Rd, Boston", "Scullers Jazz Club"),
    "scullers": (42.3603, -71.1183, "Allston", "400 Soldiers Field Rd, Boston", "Scullers Jazz Club"),
    "broken records": (42.3569, -71.1453, "Brighton", "85 Guest St, Boston", "Broken Records"),
    "harvard stadium": (42.3667, -71.1265, "Allston", "65 N Harvard St, Boston", "Harvard Stadium"),
    "bright-landry hockey center": (42.3667, -71.1265, "Allston", "65 N Harvard St, Boston", "Bright-Landry Hockey Center"),

    # Brookline & Coolidge Corner
    "coolidge corner theatre": (42.3424, -71.1215, "Coolidge Corner", "290 Harvard St, Brookline", "Coolidge Corner Theatre"),
    "coolidge corner theater": (42.3424, -71.1215, "Coolidge Corner", "290 Harvard St, Brookline", "Coolidge Corner Theatre"),
    "brookline booksmith": (42.3422, -71.1218, "Coolidge Corner", "279 Harvard St, Brookline", "Brookline Booksmith"),
    "puppet showplace theater": (42.3323, -71.1172, "Brookline Village", "32 Station St, Brookline", "Puppet Showplace Theater"),
    "puppet showplace": (42.3323, -71.1172, "Brookline Village", "32 Station St, Brookline", "Puppet Showplace Theater"),

    # Jamaica Plain & Roxbury
    "midway cafe": (42.3062, -71.1075, "Jamaica Plain", "3496 Washington St, Jamaica Plain", "Midway Cafe"),
    "jeanie johnston pub": (42.3039, -71.1147, "Jamaica Plain", "144 South St, Jamaica Plain", "Jeanie Johnston Pub"),
    "the haven": (42.3153, -71.1042, "Jamaica Plain", "284 Amory St, Jamaica Plain", "The Haven"),
    "long live roxbury": (42.3278, -71.0763, "Roxbury", "152 Hampden St, Roxbury", "Long Live Roxbury"),

    # Everett & Surrounding
    "mémoire": (42.3956, -71.0691, "Everett", "1 Broadway, Everett (Encore Boston Harbor)", "Mémoire Boston"),
    "memoire": (42.3956, -71.0691, "Everett", "1 Broadway, Everett (Encore Boston Harbor)", "Mémoire Boston"),
    "night shift brewing": (42.4069, -71.0683, "Everett", "87 Santilli Hwy, Everett", "Night Shift Brewing"),
    "night shift": (42.4069, -71.0683, "Everett", "87 Santilli Hwy, Everett", "Night Shift Brewing"),
    "dante alighieri society": (42.3728, -71.0994, "Kendall Square", "41 Hampshire St, Cambridge", "Dante Alighieri Society"),
    "hult international business school": (42.3705, -71.0722, "East Cambridge", "1 Education St, Cambridge", "Hult International Business School"),
}

# Substring needle rules for matching variations in scraped venue titles
# Sofar Sounds keeps each show's address secret until shortly before the show; its API gives
# only a neighborhood. Each neighborhood gets a pin at its centre. The labels carry the words
# template.resolve_subarea keys on ("Theater District", "Downtown", "Allston"), and the area
# addresses (no street number) give the city.
SOFAR_NEIGHBORHOODS: Dict[str, Tuple[float, float, str, str]] = {
    "allston": (42.3539, -71.1337, "Allston", "Allston, Boston"),
    "lower allston": (42.3627, -71.1263, "Lower Allston", "Allston, Boston"),
    "brighton": (42.3484, -71.1530, "Brighton", "Brighton, Boston"),
    "back bay": (42.3503, -71.0810, "Back Bay", "Back Bay, Boston"),
    "beacon hill": (42.3588, -71.0707, "Beacon Hill (Downtown)", "Beacon Hill, Boston"),
    "beacon hill / back bay": (42.3560, -71.0750, "Back Bay / Beacon Hill", "Back Bay, Boston"),
    "bay village": (42.3487, -71.0688, "Bay Village (Theater District)", "Bay Village, Boston"),
    "theater district": (42.3519, -71.0645, "Theater District", "Theater District, Boston"),
    "chinatown": (42.3493, -71.0621, "Chinatown", "Chinatown, Boston"),
    "leather district": (42.3507, -71.0582, "Leather District (Downtown)", "Leather District, Boston"),
    "downtown": (42.3555, -71.0605, "Downtown", "Downtown, Boston"),
    "financial district": (42.3559, -71.0550, "Financial District (Downtown)", "Financial District, Boston"),
    "north end": (42.3647, -71.0542, "North End", "North End, Boston"),
    "fenway": (42.3429, -71.1003, "Fenway", "Fenway, Boston"),
    "south end": (42.3388, -71.0765, "South End", "South End, Boston"),
    "sowa": (42.3420, -71.0660, "SoWa (South End)", "South End, Boston"),
    "seaport district": (42.3497, -71.0420, "Seaport", "Seaport, Boston"),
    "fort point": (42.3505, -71.0500, "Fort Point (Seaport)", "Fort Point, Boston"),
    "south boston": (42.3334, -71.0495, "South Boston", "South Boston, Boston"),
    "southie": (42.3334, -71.0495, "South Boston", "South Boston, Boston"),
    "jamaica plain": (42.3097, -71.1151, "Jamaica Plain", "Jamaica Plain, Boston"),
    "roslindale": (42.2912, -71.1245, "Roslindale", "Roslindale, Boston"),
    "roxbury": (42.3152, -71.0890, "Roxbury", "Roxbury, Boston"),
    "dorchester": (42.3016, -71.0676, "Dorchester", "Dorchester, Boston"),
    "dorchester/roxbury": (42.3100, -71.0780, "Dorchester / Roxbury", "Dorchester, Boston"),
    "mattapan": (42.2771, -71.0914, "Mattapan", "Mattapan, Boston"),
    "brookline": (42.3318, -71.1212, "Brookline", "Brookline, MA"),
    "cambridge": (42.3736, -71.1097, "Cambridge", "Cambridge, MA"),
    "cambridgeport": (42.3601, -71.1070, "Cambridgeport", "Cambridgeport, Cambridge"),
    "cambridge crossing": (42.3720, -71.0760, "Cambridge Crossing (Kendall)", "Cambridge Crossing, Cambridge"),
    "central square": (42.3651, -71.1037, "Central Square", "Central Square, Cambridge"),
    "east cambridge": (42.3696, -71.0790, "East Cambridge", "East Cambridge, Cambridge"),
    "harvard square": (42.3736, -71.1190, "Harvard Square", "Harvard Square, Cambridge"),
    "inman square": (42.3741, -71.1012, "Inman Square", "Inman Square, Cambridge"),
    "kendall square": (42.3629, -71.0901, "Kendall Square", "Kendall Square, Cambridge"),
    "porter square": (42.3884, -71.1191, "Porter Square", "Porter Square, Cambridge"),
    "somerville": (42.3876, -71.0995, "Somerville", "Somerville, MA"),
    "assembly square": (42.3925, -71.0775, "Assembly Square", "Assembly Square, Somerville"),
    "ball square": (42.3995, -71.1110, "Ball Square (Davis)", "Ball Square, Somerville"),
    "bow market": (42.3810, -71.0965, "Union Square (Bow Market)", "Union Square, Somerville"),
    "davis square": (42.3967, -71.1225, "Davis Square", "Davis Square, Somerville"),
    "east somerville": (42.3880, -71.0840, "East Somerville", "East Somerville, Somerville"),
    "union square": (42.3796, -71.0937, "Union Square", "Union Square, Somerville"),
    "arlington": (42.4154, -71.1565, "Arlington", "Arlington, MA"),
    "braintree": (42.2079, -71.0040, "Braintree", "Braintree, MA"),
    "everett": (42.4084, -71.0537, "Everett", "Everett, MA"),
}
for _hood, (_lat, _lng, _label, _addr) in SOFAR_NEIGHBORHOODS.items():
    VENUE_COORDINATES[f"sofar sounds ({_hood})"] = (_lat, _lng, _label, _addr, f"Sofar Sounds ({_label})")


VENUE_RULES = [
    # Music venues added from the Boston Shows coverage check (addresses from the venues' own sites)
    ("square root", (42.2869, -71.1301, "Roslindale", "2 Belgrade Ave, Roslindale", "Square Root")),
    ("postunderground", (42.3344, -71.1226, "Brookline Village", "386 Washington St, Brookline", "POSTunderground")),
    ("lower mills tavern", (42.2730, -71.0681, "Lower Mills", "2269 Dorchester Ave, Dorchester", "Lower Mills Tavern")),
    ("king's chapel", (42.3580, -71.0600, "Downtown", "58 Tremont St, Boston", "King's Chapel")),
    ("kings chapel", (42.3580, -71.0600, "Downtown", "58 Tremont St, Boston", "King's Chapel")),
    ("faces brewing", (42.4265, -71.0686, "Malden Center", "50 Pleasant St, Malden", "Faces Brewing")),
    ("jazz urbane", (42.3302, -71.0836, "Nubian Square", "2300 Washington St, Roxbury", "Jazz Urbane Cafe")),
    ("medford brewing", (42.4204, -71.1336, "West Medford", "30 Harvard Ave, Medford", "Medford Brewing Company")),
    ("village social club", (42.3328, -71.1188, "Brookline Village", "6 Harvard Square, Brookline", "Village Social Club")),
    ("luthier collective", (42.3829, -71.1045, "Spring Hill", "487 Somerville Ave, Somerville", "Luthier Collective")),
    ("eva broadway strings", (42.3829, -71.1045, "Spring Hill", "487 Somerville Ave, Somerville", "Luthier Collective")),
    ("gbh fraser", (42.3569, -71.1479, "Brighton", "1 Guest St, Brighton", "GBH Fraser Performance Studio")),
    ("gbh studios", (42.3569, -71.1479, "Brighton", "1 Guest St, Brighton", "GBH Fraser Performance Studio")),
    ("memorial church", (42.3749, -71.1160, "Harvard Square", "Harvard Yard, Cambridge", "Memorial Church (Harvard)")),
    ("harvard university (harvard square)", (42.3744, -71.1169, "Harvard Square", "Harvard Yard, Cambridge", "Harvard University (Harvard Square)")),
    ("lithuanian club", (42.3379, -71.0489, "South Boston", "368 W Broadway, South Boston", "Lithuanian Club")),
    ("an síbín", (42.3734, -71.0972, "Inman Square", "1193 Cambridge St, Cambridge", "An Síbín")),
    ("an sibin", (42.3734, -71.0972, "Inman Square", "1193 Cambridge St, Cambridge", "An Síbín")),
    ("rosa y marigold", (42.3475, -71.0885, "Back Bay", "400 Newbury St, Boston", "Rosa y Marigold")),
    ("kestra", (42.3470, -71.0426, "Seaport", "Omni Boston Seaport, 450 Summer St, Boston", "Kestra (Omni Boston Seaport)")),
    ("shaw-roxbury", (42.3293, -71.0838, "Nubian Square", "149 Dudley St, Roxbury", "Boston Public Library (Shaw-Roxbury)")),
    ("gbh studio at the boston public library", (42.3495, -71.0780, "Back Bay", "700 Boylston St, Boston", "GBH Studio at the Boston Public Library")),
    # Kids & family venues and town libraries (specific branches before the general names)
    ("brookline public library (putterham", (42.3025, -71.1501, "Brookline", "959 West Roxbury Pkwy, Brookline", "Brookline Public Library (Putterham)")),
    ("brookline public library (coolidge", (42.3435, -71.1191, "Coolidge Corner", "31 Pleasant St, Brookline", "Brookline Public Library (Coolidge Corner)")),
    ("brookline public library", (42.3346, -71.1214, "Brookline Village", "361 Washington St, Brookline", "Brookline Public Library")),
    ("watertown free public library", (42.3667, -71.1856, "Watertown", "123 Main St, Watertown", "Watertown Free Public Library")),
    ("belmont public library", (42.3946, -71.1722, "Belmont", "336 Concord Ave, Belmont", "Belmont Public Library")),
    ("medford public library", (42.4197, -71.1135, "Medford Square", "111 High St, Medford", "Medford Public Library")),
    ("boston children's museum", (42.3518, -71.0498, "Fort Point", "308 Congress St, Boston", "Boston Children's Museum")),
    ("new england aquarium", (42.3591, -71.0498, "Downtown / Waterfront", "1 Central Wharf, Boston", "New England Aquarium")),
    ("somerville museum", (42.3870, -71.1048, "Spring Hill", "1 Westwood Rd, Somerville", "Somerville Museum")),
    ("magazine beach", (42.3558, -71.1154, "Cambridgeport", "668 Memorial Dr, Cambridge", "Mass Audubon Nature Center at Magazine Beach")),
    ("boston nature center", (42.2881, -71.1012, "Mattapan", "500 Walk Hill St, Boston", "Mass Audubon Boston Nature Center")),
    ("puppet showplace", (42.3324, -71.1170, "Brookline Village", "32 Station St, Brookline", "Puppet Showplace Theater")),
    ("ula cafe", (42.3155, -71.1035, "Jamaica Plain", "284 Amory St, Boston", "Ula Cafe")),
    # Top venues
    ("aeronaut", (42.3814, -71.1066, "Somerville", "14 Tyler St, Somerville", "Aeronaut Brewing")),
    ("comedy studio", (42.3727, -71.1196, "Harvard Square", "5 John F. Kennedy St, Cambridge", "The Comedy Studio")),
    ("coolidge corner", (42.3424, -71.1215, "Coolidge Corner", "290 Harvard St, Brookline", "Coolidge Corner Theatre")),
    ("burren", (42.3963, -71.1224, "Davis Square", "247 Elm St, Somerville", "The Burren")),
    ("city winery", (42.3644, -71.0601, "West End", "80 Beverly St, Boston", "City Winery Boston")),
    ("anchor", (42.3734, -71.0505, "Charlestown Navy Yard", "1 Shipyard Park, Charlestown", "The Anchor Boston")),
    ("beehive", (42.3444, -71.0706, "South End", "541 Tremont St, Boston", "The Beehive")),
    ("royale", (42.3508, -71.0654, "Theater District", "279 Tremont St, Boston", "Royale")),
    ("cantab underground", (42.3662, -71.1061, "Central Square", "738 Massachusetts Ave, Cambridge (Downstairs)", "Cantab Underground")),
    ("cantab", (42.3662, -71.1061, "Central Square", "738 Massachusetts Ave, Cambridge", "The Cantab Lounge")),
    # BPL branches before the Central Library (Copley)
    ("honan-allston", (42.3601, -71.1277, "Allston", "300 N Harvard St, Allston", "Honan-Allston Branch Library")),
    ("brighton branch", (42.3476, -71.1526, "Brighton", "40 Academy Hill Rd, Brighton", "Brighton Branch Library")),
    ("boston public library", (42.3496, -71.0779, "Copley Square", "700 Boylston St, Boston", "Boston Public Library")),
    ("wally", (42.3409, -71.0827, "South End", "427 Massachusetts Ave, Boston", "Wally's Café")),
    ("natural history", (42.3787, -71.1155, "Harvard Square", "26 Oxford St, Cambridge", "Harvard Museum of Natural History")),
    ("peabody museum", (42.3785, -71.1152, "Harvard Square", "11 Divinity Ave, Cambridge", "Peabody Museum")),
    ("lou's", (42.3747, -71.1206, "Harvard Square", "50 Church St, Cambridge", "Lou's (Harvard Square)")),
    ("wearelous", (42.3747, -71.1206, "Harvard Square", "50 Church St, Cambridge", "Lou's (Harvard Square)")),
    ("modern theatre", (42.3533, -71.0622, "Downtown Crossing", "525 Washington St, Boston", "Modern Theatre")),
    ("high street place", (42.3537, -71.0543, "Downtown / Financial District", "100 High St, Boston", "High Street Place")),
    ("havana club", (42.3649, -71.1026, "Central Square", "288 Green St, Cambridge", "Havana Club")),
    ("hava nightclub", (42.3507, -71.0647, "Theater District", "246 Tremont St, Boston", "Hava Nightclub")),
    ("big night live", (42.3656, -71.0617, "West End / TD Garden", "110 Causeway St, Boston", "Big Night Live")),
    ("symphony hall", (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall")),
    ("somerville theatre", (42.3968, -71.1228, "Davis Square", "55 Davis Sq, Somerville", "Somerville Theatre")),
    ("crystal ballroom", (42.3968, -71.1228, "Davis Square", "55 Davis Sq, Somerville", "Crystal Ballroom")),
    ("trident", (42.3484, -71.0863, "Back Bay", "338 Newbury St, Boston", "Trident Booksellers & Cafe")),
    ("remnant satellite", (42.3725, -71.0905, "East Cambridge", "877 Cambridge St, Cambridge", "Remnant Satellite")),
    ("satellite remnant", (42.3725, -71.0905, "East Cambridge", "877 Cambridge St, Cambridge", "Remnant Satellite")),
    ("remnant", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Remnant Brewing")),
    ("craft loft", (42.3814, -71.1066, "Somerville", "14 Tyler St, Somerville", "Craft Loft")),
    ("ica boston", (42.3528, -71.0432, "Seaport", "25 Harbor Shore Dr, Boston", "ICA Boston")),
    ("td garden", (42.3662, -71.0621, "West End / North Station", "100 Legends Way, Boston", "TD Garden")),
    ("sports museum", (42.3662, -71.0621, "West End / North Station", "100 Legends Way, Boston", "The Sports Museum")),
    ("ccae", (42.3744, -71.1219, "Harvard Square", "42 Brattle St, Cambridge", "CCAE")),
    ("loretta", (42.3475, -71.0963, "Fenway", "1 Lansdowne St, Boston", "Loretta's Last Call")),
    ("harvard book", (42.3729, -71.1166, "Harvard Square", "1256 Massachusetts Ave, Cambridge", "Harvard Book Store")),
    ("laugh boston", (42.3462, -71.0433, "Seaport", "425 Summer St, Boston", "Laugh Boston")),
    ("toad", (42.3892, -71.1195, "Porter Square", "1920 Massachusetts Ave, Cambridge", "Toad")),
    ("porter square book", (42.3888, -71.1192, "Porter Square", "25 White St, Cambridge", "Porter Square Books")),
    ("brookline booksmith", (42.3422, -71.1218, "Coolidge Corner", "279 Harvard St, Brookline", "Brookline Booksmith")),
    ("deep cuts", (42.4179, -71.1102, "Medford Square", "21 Main St, Medford", "Deep Cuts")),
    ("versus", (42.3569, -71.0600, "Downtown Crossing", "42 Province St, Boston", "Versus Boston")),
    ("wilbur", (42.3516, -71.0648, "Theater District", "246 Tremont St, Boston", "The Wilbur")),
    ("smfa", (42.3388, -71.0967, "Fenway", "230 Fenway, Boston", "SMFA at Tufts")),
    ("museum of fine arts", (42.3394, -71.0940, "Museum District", "465 Huntington Ave, Boston", "Museum of Fine Arts (MFA)")),
    ("mfa", (42.3394, -71.0940, "Museum District", "465 Huntington Ave, Boston", "Museum of Fine Arts (MFA)")),
    ("middle east - downstairs", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Downstairs")),
    ("middle east downstairs", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Downstairs")),
    ("middle east - upstairs", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Upstairs")),
    ("middle east upstairs", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Upstairs")),
    ("middle east - corner/bakery", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Corner/Bakery")),
    ("middle east corner", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "Middle East - Corner/Bakery")),
    ("middle east - zuzu", (42.3638, -71.1018, "Central Square", "474 Massachusetts Ave, Cambridge", "Middle East - ZuZu")),
    ("zuzu", (42.3638, -71.1018, "Central Square", "474 Massachusetts Ave, Cambridge", "ZuZu")),
    ("middle east", (42.3638, -71.1018, "Central Square", "472 Massachusetts Ave, Cambridge", "The Middle East")),
    ("sinclair", (42.3746, -71.1207, "Harvard Square", "52 Church St, Cambridge", "The Sinclair")),
    ("colonial theatre", (42.3524, -71.0658, "Theater District", "106 Boylston St, Boston", "Emerson Colonial Theatre")),
    ("paramount center", (42.3533, -71.0628, "Theater District", "559 Washington St, Boston", "Emerson Paramount Center")),
    ("cutler majestic", (42.3519, -71.0645, "Theater District", "219 Tremont St, Boston", "Emerson Cutler Majestic Theatre")),
    ("opera house", (42.3541, -71.0617, "Downtown Crossing", "539 Washington St, Boston", "Citizens Bank Opera House")),
    ("wang thea", (42.3509, -71.0651, "Theater District", "270 Tremont St, Boston", "Boch Center Wang Theatre")),
    ("shubert thea", (42.3513, -71.0651, "Theater District", "265 Tremont St, Boston", "Boch Center Shubert Theatre")),
    ("roadrunner", (42.3566, -71.1439, "Boston Landing", "89 Guest St, Brighton", "Roadrunner")),
    ("paradise rock", (42.3519, -71.1201, "Allston", "967 Commonwealth Ave, Boston", "Paradise Rock Club")),
    ("brighton music hall", (42.3527, -71.1326, "Allston", "158 Brighton Ave, Allston", "Brighton Music Hall")),
    ("house of blues", (42.3474, -71.0954, "Fenway", "15 Lansdowne St, Boston", "House of Blues Boston")),
    ("mgm music hall", (42.3472, -71.0967, "Fenway", "2 Lansdowne St, Boston", "MGM Music Hall at Fenway")),
    ("leader bank pavilion", (42.3475, -71.0360, "Seaport", "290 Northern Ave, Boston", "Leader Bank Pavilion")),
    ("the grand", (42.3524, -71.0475, "Seaport", "58 Seaport Blvd, Boston", "The Grand")),
    ("scorpion bar", (42.3524, -71.0475, "Seaport", "58 Seaport Blvd, Boston", "Scorpion Bar")),
    ("bow market", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Bow Market")),
    ("dark mode", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "DARK MODE at Bow Market")),
    ("vera's", (42.3797, -71.0962, "Union Square", "70 Union Sq, Somerville", "Vera's")),
    ("armory", (42.3897, -71.106, "Spring Hill", "191 Highland Ave, Somerville", "Arts at the Armory")),
    ("sabina", (42.3965, -71.1039, "Winter Hill", "514 Medford St, Somerville", "Sabina Mezcalería")),
    ("bobas", (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "Hatch Shell (Esplanade)")),
    ("esplanade", (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "The Esplanade")),
    ("hatch shell", (42.3582, -71.0735, "Esplanade", "47 David G Mugar Way, Boston", "Hatch Shell")),
    ("boston common", (42.3550, -71.0656, "Downtown", "139 Tremont St, Boston", "Boston Common")),
    ("public garden", (42.3542, -71.0704, "Back Bay", "4 Charles St, Boston", "Boston Public Garden")),
    ("copley", (42.3501, -71.0766, "Copley Square", "560 Boylston St, Boston", "Copley Square")),
    ("sowa", (42.3413, -71.0672, "South End", "530 Harrison Ave, Boston", "SoWa Open Market")),
    ("reunion bbq", (42.3468, -71.0688, "South End", "439 Tremont St, Boston", "Reunion BBQ")),
    ("posto", (42.3450, -71.0680, "South End", "Washington St, Boston", "Posto South End")),
    # Location-qualified Mighty Squirrel names from event sources ("Mighty Squirrel Taproom &
    # Kitchen (Fenway)", "Mighty Squirrel Brewing Co. – Fenway (Boston)", "..., Watertown").
    ("mighty squirrel taproom & kitchen (fenway)", (42.3477, -71.0991, "Fenway", "1 David Ortiz Dr, Boston", "Mighty Squirrel Fenway")),
    ("mighty squirrel brewing co. – fenway", (42.3477, -71.0991, "Fenway", "1 David Ortiz Dr, Boston", "Mighty Squirrel Fenway")),
    ("mighty squirrel fenway", (42.3477, -71.0991, "Fenway", "1 David Ortiz Dr, Boston", "Mighty Squirrel Fenway")),
    ("mighty squirrel taproom & kitchen, watertown", (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards")),
    ("mighty squirrel at arsenal yards", (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards")),
    ("mighty squirrel arsenal yards", (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards")),
    ("mighty squirrel watertown", (42.3614, -71.1584, "Arsenal Yards", "102 Arsenal Yards Blvd, Watertown", "Mighty Squirrel Arsenal Yards")),
    ("mighty squirrel waltham", (42.3843, -71.2160, "Waltham", "411 Waverley Oaks Rd, Waltham", "Mighty Squirrel Waltham")),
    ("lucky's lounge", (42.3505, -71.0484, "Fort Point", "355 Congress St, Boston", "Lucky's Lounge")),
    ("city tap house", (42.3509, -71.0470, "Seaport", "10 Boston Wharf Rd, Boston", "City Tap House")),
    ("white bull tavern", (42.3607, -71.0571, "Faneuil Hall", "1 Union St, Boston", "White Bull Tavern")),
    ("ned devine's", (42.3600, -71.0548, "Faneuil Hall", "1 Faneuil Hall Marketplace, Boston", "Ned Devine's")),
    ("cactus club cafe", (42.3505, -71.0727, "Back Bay", "500 Boylston St, Boston", "Cactus Club Cafe")),
    ("bijou nightclub", (42.3512, -71.0642, "Theater District", "51 Stuart St, Boston", "Bijou Nightclub")),
    ("sissy k's", (42.3612, -71.0527, "Faneuil Hall", "6 Commercial St, Boston", "Sissy K's")),
    ("icon nightclub", (42.3507, -71.0662, "Theater District", "100 Warrenton St, Boston", "Icon Nightclub")),
    ("venu nightclub", (42.3507, -71.0662, "Theater District", "100 Warrenton St, Boston", "Venu Nightclub")),
    ("spy bar boston", (42.3463, -71.0700, "South End", "40 Berkeley St, Boston", "Spy Bar")),
    ("spy bar at the revolution", (42.3463, -71.0700, "South End", "40 Berkeley St, Boston", "Spy Bar")),
    ("tuck's arcadium", (42.3722, -71.1203, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Tuck's Arcadium")),
    ("special interest social", (42.3722, -71.1203, "Harvard Square", "36 John F. Kennedy St, Cambridge", "Special Interest Social")),
    ("dear annie", (42.3878, -71.1195, "Porter Square", "1741 Massachusetts Ave, Cambridge", "Dear Annie")),
    ("rebel rebel", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Rebel Rebel")),
    ("wild child", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Wild Child")),
    ("riemer-goldstein", (42.3025, -71.1995, "Newton", "333 Nahanton St, Newton", "JCC Greater Boston")),
    ("west newton cinema", (42.3497, -71.2268, "West Newton", "1296 Washington St, Newton", "West Newton Cinema")),
    ("club café", (42.3486, -71.0718, "South End", "209 Columbus Ave, Boston", "Club Café")),
    ("club cafe", (42.3486, -71.0718, "South End", "209 Columbus Ave, Boston", "Club Café")),
    ("dani's", (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar")),
    ("danis", (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar")),
    ("lyric stage", (42.3496, -71.0729, "Back Bay", "140 Clarendon St, Boston", "Lyric Stage Company")),
    ("speakeasy stage", (42.3448, -71.0701, "South End", "527 Tremont St, Boston", "SpeakEasy Stage Company")),
    ("boston lyric opera", (42.3519, -71.0645, "Theater District", "219 Tremont St, Boston", "Boston Lyric Opera")),
    ("celebrity series", (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Celebrity Series of Boston")),
    ("lesbiannightlife", (42.3219, -71.0626, "Dorchester", "1250 Massachusetts Ave, Dorchester", "LesbianNightLife")),
    ("the 88 club", (42.3468, -71.0845, "Back Bay", "50 Dalton St, Boston", "The 88 Club")),
    ("88 club", (42.3468, -71.0845, "Back Bay", "50 Dalton St, Boston", "The 88 Club")),
    ("legacy", (42.3512, -71.0660, "Theater District", "79 Warrenton St, Boston", "Legacy Boston")),
    ("the alley bar", (42.3582, -71.0592, "Downtown", "14 Pi Alley, Boston", "The Alley Bar")),
    ("sunset cantina", (42.3503, -71.1187, "Allston / BU", "916 Commonwealth Ave, Boston", "Sunset Cantina")),
    ("feral", (42.3512, -71.0660, "Theater District", "79 Warrenton St, Boston", "Legacy Boston (FERAL)")),
    ("darryl's", (42.3400, -71.0805, "South End", "604 Columbus Ave, Boston", "Darryl's Corner Bar & Kitchen")),
    ("urbanity dance", (42.3424, -71.0664, "South End", "1180 Washington St, Boston", "Urbanity Dance")),
    ("fenway park", (42.3467, -71.0972, "Fenway", "4 Jersey St, Boston", "Fenway Park")),
    ("bleacher bar", (42.3468, -71.0975, "Fenway", "82A Lansdowne St, Boston", "Bleacher Bar")),
    ("lansdowne pub", (42.3473, -71.0957, "Fenway", "9 Lansdowne St, Boston", "Lansdowne Pub")),
    ("bill's bar", (42.3474, -71.0960, "Fenway", "5 Lansdowne St, Boston", "Bill's Bar")),
    ("cask 'n flagon", (42.3469, -71.0989, "Fenway", "62 Brookline Ave, Boston", "Cask 'n Flagon")),
    ("huntington thea", (42.3421, -71.0853, "Symphony", "264 Huntington Ave, Boston", "Huntington Theatre")),
    ("gardner museum", (42.3382, -71.0991, "Museum District", "25 Evans Way, Boston", "Isabella Stewart Gardner Museum")),
    ("isabella stewart", (42.3382, -71.0991, "Museum District", "25 Evans Way, Boston", "Isabella Stewart Gardner Museum")),
    ("cafe 939", (42.3475, -71.0850, "Back Bay", "939 Boylston St, Boston", "The Red Room at Cafe 939")),
    ("berklee", (42.3479, -71.0886, "Back Bay / Fenway", "136 Massachusetts Ave, Boston", "Berklee Performance Center")),
    ("bebop", (42.3472, -71.0886, "Back Bay / Fenway", "1116 Boylston St, Boston", "The Bebop")),
    ("artisans asylum", (42.3598, -71.1415, "Allston", "96 Holton St, Boston", "Artisans Asylum")),
    ("silhouette", (42.3533, -71.1332, "Allston", "200 Brighton Ave, Allston", "Silhouette Lounge")),
    ("model cafe", (42.3537, -71.1378, "Allston", "7 N Beacon St, Allston", "Model Cafe")),
    ("agganis arena", (42.3522, -71.1177, "BU / Allston", "925 Commonwealth Ave, Boston", "Agganis Arena")),
    ("midway cafe", (42.3062, -71.1075, "Jamaica Plain", "3496 Washington St, Jamaica Plain", "Midway Cafe")),
    ("jeanie johnston", (42.3039, -71.1147, "Jamaica Plain", "144 South St, Jamaica Plain", "Jeanie Johnston Pub")),
    ("the haven", (42.3153, -71.1042, "Jamaica Plain", "284 Amory St, Jamaica Plain", "The Haven")),
    ("gillette stadium", (42.0909, -71.2643, "Foxborough", "1 Patriot Pl, Foxborough", "Gillette Stadium")),
    ("regent thea", (42.415, -71.1508, "Arlington", "7 Medford St, Arlington", "Regent Theatre")),
    ("painted burro", (42.3961, -71.1220, "Davis Square", "219 Elm St, Somerville", "Painted Burro")),
    ("blues union", (42.3995, -71.1278, "Teele Square", "160 Holland St, Somerville", "Blues Union")),
    ("foundry", (42.3666, -71.0828, "East Cambridge", "101 Rogers St, Cambridge", "The Foundry")),
    ("lamplighter", (42.3688, -71.0994, "Cambridgeport", "284 Broadway, Cambridge", "Lamplighter Brewing")),
    ("lovestruck", (42.3739, -71.1200, "Harvard Square", "22 Church St, Cambridge", "Lovestruck Books & Cafe")),
    ("all she wrote", (42.3816, -71.0848, "East Somerville", "75 Washington St, Somerville", "All She Wrote Books")),
    ("manray", (42.3662, -71.1027, "Central Square", "40 Prospect St, Cambridge", "ManRay")),
    ("passim", (42.3741, -71.1204, "Harvard Square", "47 Palmer St, Cambridge", "Club Passim")),
    ("lizard lounge", (42.3809, -71.1197, "North Cambridge", "1667 Massachusetts Ave, Cambridge", "Lizard Lounge")),
    ("somerville public library (east branch)", (42.3888, -71.0825, "East Somerville", "115 Broadway, Somerville", "Somerville Public Library (East Branch)")),
    ("somerville public library (west branch)", (42.3986, -71.1218, "Davis Square", "40 College Ave, Somerville", "Somerville Public Library (West Branch)")),
    ("somerville public library", (42.3858, -71.0944, "Somerville", "79 Highland Ave, Somerville", "Somerville Public Library (Central)")),
    ("somerville library", (42.3858, -71.0944, "Somerville", "79 Highland Ave, Somerville", "Somerville Public Library (Central)")),
    ("cambridge public library (central square", (42.3644, -71.1027, "Central Square", "45 Pearl St, Cambridge", "Cambridge Public Library (Central Square)")),
    ("cambridge public library (valente", (42.3722, -71.0902, "East Cambridge", "826 Cambridge St, Cambridge", "Cambridge Public Library (Valente Branch)")),
    ("cambridge public library (o'connell", (42.3688, -71.0847, "East Cambridge", "48 Sixth St, Cambridge", "Cambridge Public Library (O'Connell Branch)")),
    ("cambridge public library (o'neill", (42.3922, -71.1280, "North Cambridge", "70 Rindge Ave, Cambridge", "Cambridge Public Library (O'Neill Branch)")),
    ("cambridge public library (boudreau", (42.3838, -71.1319, "West Cambridge", "245 Concord Ave, Cambridge", "Cambridge Public Library (Boudreau Branch)")),
    ("cambridge public library (collins", (42.3776, -71.1491, "West Cambridge", "64 Aberdeen Ave, Cambridge", "Cambridge Public Library (Collins Branch)")),
    ("cambridge library", (42.3744, -71.1111, "Mid-Cambridge", "449 Broadway, Cambridge", "Cambridge Public Library")),
    ("copley square farmers market", (42.3501, -71.0766, "Copley Square", "Copley Square, Boston", "Copley Square Farmers Market")),
    ("harvard university farmers market", (42.3760, -71.1167, "Harvard Square", "1 Oxford St, Cambridge", "Harvard University Farmers Market")),
    ("haymarket", (42.3625, -71.0565, "Downtown / North End", "Blackstone St, Boston", "Haymarket")),
    ("mit open space", (42.3621, -71.0864, "Kendall Square", "292 Main St, Cambridge", "MIT Open Space")),
    ("mit ", (42.3590, -71.0940, "Kendall Square / MIT", "Cambridge", "MIT Campus")),
    ("memoire", (42.3956, -71.0691, "Everett", "1 Broadway, Everett (Encore Boston Harbor)", "Mémoire Boston")),
    ("night shift", (42.4069, -71.0683, "Everett", "87 Santilli Hwy, Everett", "Night Shift Brewing")),
    ("dante alighieri", (42.3728, -71.0994, "Kendall Square", "41 Hampshire St, Cambridge", "Dante Alighieri Society")),
    ("hult", (42.3705, -71.0722, "East Cambridge", "1 Education St, Cambridge", "Hult International Business School")),
    ("venture café", (42.3626, -71.0837, "Kendall Square", "1 Broadway, Cambridge", "Venture Café Cambridge")),
    ("venture cafe", (42.3626, -71.0837, "Kendall Square", "1 Broadway, Cambridge", "Venture Café Cambridge")),
    ("the druid", (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid")),
    ("druid", (42.3738, -71.1002, "Inman Square", "1357 Cambridge St, Cambridge", "The Druid")),
    ("charles river speedway", (42.3616, -71.1447, "Brighton", "525 Western Ave, Boston", "Charles River Speedway")),
    ("speedway", (42.3616, -71.1447, "Brighton", "525 Western Ave, Boston", "Charles River Speedway")),
    ("time out market", (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "Time Out Market Boston")),
    ("401 park", (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "401 Park")),
    ("the fenway", (42.3441, -71.1031, "Fenway", "401 Park Dr, Boston", "The Fenway")),
    ("rose kennedy greenway", (42.3550, -71.0520, "Downtown / Waterfront", "Atlantic Ave, Boston", "Rose Kennedy Greenway")),
    ("greenway", (42.3550, -71.0520, "Downtown / Waterfront", "Atlantic Ave, Boston", "Rose Kennedy Greenway")),
    ("kendall center", (42.3625, -71.0865, "Kendall Square", "90 Broadway, Cambridge", "Kendall Center")),
    ("urban park", (42.3625, -71.0865, "Kendall Square", "90 Broadway, Cambridge", "Urban Park Roof Garden")),
    ("the platform", (42.3637, -71.0827, "Kendall Square", "315 Kendall St, Cambridge, MA 02142", "The Platform Kendall")),
    ("somerville arts council", (42.3875, -71.0995, "Somerville", "Somerville, MA", "Somerville Arts Council")),
    ("jacque", (42.3499, -71.0691, "Bay Village", "79 Broadway, Boston", "Jacques' Cabaret")),
    ("jungle", (42.3807, -71.0955, "Union Square", "6 Sanborn Ct, Somerville", "The Jungle Community Music Club")),
    ("lilypad", (42.3737, -71.1001, "Inman Square", "1353 Cambridge St, Cambridge", "The Lilypad")),
    ("lily pad", (42.3737, -71.1001, "Inman Square", "1353 Cambridge St, Cambridge", "The Lilypad")),
    ("plough and stars", (42.3683, -71.1088, "Cambridgeport", "912 Massachusetts Ave, Cambridge", "The Plough and Stars")),
    ("plough & stars", (42.3683, -71.1088, "Cambridgeport", "912 Massachusetts Ave, Cambridge", "The Plough and Stars")),
    ("sally o'brien", (42.3822, -71.0998, "Union Square", "335 Somerville Ave, Somerville", "Sally O'Brien's")),
    ("sally obrien", (42.3822, -71.0998, "Union Square", "335 Somerville Ave, Somerville", "Sally O'Brien's")),
    ("side quest", (42.3804, -71.0970, "Union Square", "1 Bow Market Way, Somerville", "Side Quest Books & Games")),
    ("duck duck goof", (42.3802, -71.0962, "Union Square", "10-12 Bow St, Somerville", "Duck Duck Goofs")),
    ("middlesex", (42.3619, -71.0988, "Central Square", "315 Massachusetts Ave, Cambridge", "Middlesex Lounge")),
    ("roxy", (42.3623, -71.0995, "Central Square", "292 Massachusetts Ave, Cambridge", "Roxy's Arcade")),
    ("a4cade", (42.3623, -71.0995, "Central Square", "292 Massachusetts Ave, Cambridge", "Roxy's Arcade")),
    ("phoenix landing", (42.3641, -71.1019, "Central Square", "512 Massachusetts Ave, Cambridge", "The Phoenix Landing")),
    ("gather here", (42.3736, -71.1000, "Inman Square", "1343 Cambridge St, Cambridge", "Gather Here")),
    ("underbones", (42.3967, -71.1215, "Davis Square", "55 Chester St, Somerville", "Underbones")),
    ("growing center", (42.3828, -71.0980, "Spring Hill", "22 Vinal Ave, Somerville", "Somerville Community Growing Center")),
    ("bsmnt", (42.3508, -71.0657, "Theater District", "100 Stuart St, Boston", "bsmnt")),
    ("batifol", (42.3639, -71.0829, "Kendall Square", "291 3rd St, Cambridge", "Batifol")),
    ("kings seaport", (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)")),
    ("kings - seaport", (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)")),
    ("kings dining", (42.3529, -71.0470, "Seaport", "60 Seaport Blvd, Boston", "Kings Dining & Entertainment (Seaport)")),
    ("rockwell", (42.3963, -71.1224, "Davis Square", "255 Elm St, Somerville", "The Rockwell")),
    ("monkfish", (42.3642, -71.1020, "Central Square", "524 Massachusetts Ave, Cambridge", "The Mad Monkfish")),
    ("o'brien", (42.3552, -71.1329, "Allston", "3 Harvard Ave, Allston", "O'Brien's Pub")),
    ("obrien", (42.3552, -71.1329, "Allston", "3 Harvard Ave, Allston", "O'Brien's Pub")),
    ("jordan hall", (42.3418, -71.0864, "Fenway / Symphony", "30 Gainsborough St, Boston", "Jordan Hall (NEC)")),
    ("new england conservatory", (42.3418, -71.0864, "Fenway / Symphony", "290 Huntington Ave, Boston", "New England Conservatory")),
    ("q ballroom", (42.3879, -71.1404, "West Cambridge", "26 New St, Cambridge", "Q Ballroom")),
    ("head of the charles", (42.3695, -71.1235, "Charles River", "Charles River, Boston", "Head of the Charles Regatta")),
    ("charles river", (42.3600, -71.0720, "Charles River / Esplanade", "Charles River Esplanade, Boston", "Charles River")),
    ("wbur cityspace", (42.3512, -71.1166, "Commonwealth Ave", "890 Commonwealth Ave, Boston", "WBUR CitySpace")),
    ("chester tavern", (42.3808, -71.0994, "Somerville Ave", "366 Somerville Ave, Somerville", "The Chester Tavern")),
    ("dance complex", (42.3648, -71.1030, "Central Square", "536 Massachusetts Ave, Cambridge", "The Dance Complex")),
    ("portico brewing", (42.3748, -71.0911, "Boynton Yards", "101 South St, Somerville", "Portico Brewing")),
    ("dance union", (42.3807, -71.0973, "Union Square", "16 Bow St, Somerville", "Dance Union")),
    ("winter hill brewing", (42.3927, -71.0933, "Winter Hill", "328 Broadway, Somerville", "Winter Hill Brewing Co.")),
    ("the independent", (42.3799, -71.0946, "Union Square", "75 Union Square, Somerville", "The Independent")),
    ("olde magoun", (42.3966, -71.1040, "Magoun Square", "518 Medford St, Somerville", "Olde Magoun's Saloon")),
    ("scullers", (42.3603, -71.1183, "Allston", "400 Soldiers Field Rd, Boston", "Scullers Jazz Club")),
    ("bills bar", (42.3474, -71.0960, "Fenway", "5 Lansdowne St, Boston", "Bill's Bar")),
    ("bill's bar", (42.3474, -71.0960, "Fenway", "5 Lansdowne St, Boston", "Bill's Bar")),
    ("sports museum", (42.3662, -71.0621, "West End / TD Garden", "100 Legends Way, Boston", "The Sports Museum")),
    ("multicultural arts", (42.3698, -71.0784, "East Cambridge", "41 Second St, Cambridge", "Multicultural Arts Center")),
    ("harvard art museum", (42.3742, -71.1143, "Harvard Square", "32 Quincy St, Cambridge", "Harvard Art Museums")),
    ("charles playhouse", (42.3512, -71.0658, "Theater District", "74 Warrenton St, Boston", "Charles Playhouse")),
    ("winthrop center", (42.3541, -71.0568, "Downtown", "115 Federal St, Boston", "Winthrop Center")),
    ("lifebloom", (42.3435, -71.0718, "South End", "568 Tremont St, Boston", "Lifebloom Candle Bar")),
    ("broken records", (42.3569, -71.1453, "Brighton", "85 Guest St, Boston", "Broken Records")),
    ("goethe", (42.3546, -71.0765, "Back Bay", "170 Beacon St, Boston", "Goethe-Institut Boston")),
    ("graymist", (42.3810, -71.1390, "West Cambridge", "364 Huron Ave, Cambridge", "GrayMist Studio & Shop")),
    ("coolidge corner", (42.3424, -71.1215, "Coolidge Corner", "290 Harvard St, Brookline", "Coolidge Corner Theatre")),
    ("puppet showplace", (42.3323, -71.1172, "Brookline Village", "32 Station St, Brookline", "Puppet Showplace Theater")),
    ("life drawing boston", (42.3786, -71.0866, "East Somerville", "72 Joy St, Somerville", "Life Drawing Boston")),
    ("the loov", (42.3786, -71.0866, "East Somerville", "72 Joy St, Somerville", "Life Drawing Boston")),
    ("boston figure art center", (42.3797, -71.0982, "Union Square", "285 Washington St, Somerville", "Boston Figure Art Center")),
    ("boston figurative art center", (42.3797, -71.0982, "Union Square", "285 Washington St, Somerville", "Boston Figure Art Center")),
    ("warehouse xi", (42.3807, -71.0957, "Union Square", "11 Sanborn Ct, Somerville", "Warehouse XI")),
    ("downtown boston", (42.3555, -71.0601, "Downtown / Financial District", "Downtown Crossing, Boston", "Downtown Boston")),
    ("downtown crossing", (42.3555, -71.0601, "Downtown / Financial District", "Downtown Crossing, Boston", "Downtown Crossing")),
    ("old state house", (42.3587, -71.0578, "Downtown / Financial District", "206 Washington St, Boston", "Old State House")),
    ("old south meeting house", (42.3569, -71.0594, "Downtown / Financial District", "310 Washington St, Boston", "Old South Meeting House")),
    ("mccarthy", (42.3892, -71.1195, "Porter Square", "1920 Massachusetts Ave, Cambridge", "Toad / McCarthy's")),
    ("museum of science", (42.3672, -71.0711, "West End", "1 Science Park, Boston", "Museum of Science")),
    ("central rock", (42.3940, -71.1516, "North Cambridge", "127 Smith Pl, Cambridge", "Central Rock Gym")),
    ("democracy brewing", (42.3548, -71.0617, "Downtown Crossing", "35 Temple Pl, Boston", "Democracy Brewing")),
    ("288 green", (42.3649, -71.1026, "Central Square", "288 Green St, Cambridge", "Havana Club")),
    ("hatch shell", (42.3582, -71.0717, "Esplanade", "47 David G Mugar Way, Boston", "Hatch Memorial Shell")),
    ("moves & vibes", (42.3813, -71.1068, "Somerville", "44 Park St, Somerville", "Moves & Vibes Dance")),
    ("umass boston", (42.3134, -71.0354, "Dorchester", "100 William T Morrissey Blvd, Boston", "UMass Boston")),
    ("beacon hill", (42.3588, -71.0678, "Beacon Hill", "Beacon Hill, Boston", "Beacon Hill")),
    ("phoenix boston", (42.3238, -71.0719, "Roxbury", "54 Shirley St, Boston", "The Phoenix Boston")),
    ("fourth presbyterian", (42.3307, -71.0540, "South Boston", "340 Dorchester St, Boston", "Fourth Presbyterian Church")),
    ("kadampa", (42.3951, -71.1279, "North Cambridge", "2298 Massachusetts Ave, Cambridge", "Kadampa Meditation Center")),
    ("chevalier", (42.4203, -71.1091, "Medford Square", "30 Forest St, Medford", "Chevalier Theatre")),
    ("arrow street arts", (42.3708, -71.1146, "Harvard Square", "2 Arrow St, Cambridge", "Arrow Street Arts")),
    ("brendan behan", (42.3220, -71.1093, "Jamaica Plain", "378 Centre St, Jamaica Plain", "The Brendan Behan Pub")),
    ("emmanuel church", (42.3523, -71.0734, "Back Bay", "15 Newbury St, Boston", "Emmanuel Church")),
    ("church of the covenant", (42.3524, -71.0722, "Back Bay", "67 Newbury St, Boston", "Church of the Covenant")),
    ("davis square plaza", (42.3967, -71.1224, "Davis Square", "Elm St & College Ave, Somerville", "Davis Square Plaza")),
    ("statue park", (42.3967, -71.1224, "Davis Square", "Davis Square, Somerville", "Statue Park")),
    ("faneuil hall", (42.3598, -71.0568, "Downtown / Faneuil Hall", "4 S Market St, Boston", "Faneuil Hall")),
    ("boston city hall", (42.3603, -71.0580, "Government Center", "1 City Hall Sq, Boston", "Boston City Hall")),
    ("city hall plaza", (42.3603, -71.0580, "Government Center", "1 City Hall Sq, Boston", "Boston City Hall Plaza")),
    ("castle island brewing", (42.3378, -71.0566, "South Boston", "10 Old Colony Ave, South Boston", "Castle Island Brewing")),
    ("athenaeum", (42.3582, -71.0628, "Beacon Hill", "10 1/2 Beacon St, Boston", "Boston Athenaeum")),
    ("improv asylum", (42.3636, -71.0543, "North End", "216 Hanover St, Boston", "Improv Asylum")),
    ("paul revere mall", (42.3662, -71.0534, "North End", "The Prado, Hanover St, Boston", "Paul Revere Mall")),
    ("african american history", (42.3601, -71.0664, "Beacon Hill", "46 Joy St, Boston", "Museum of African American History")),
    ("hibernian hall", (42.3292, -71.0841, "Roxbury / Dudley", "184 Dudley St, Roxbury", "Hibernian Hall")),
    ("massart", (42.3371, -71.0998, "Fenway / Longwood", "621 Huntington Ave, Boston", "MassArt Art Museum")),
    ("comicazi", (42.3961, -71.1212, "Davis Square", "407 Highland Ave, Somerville", "Comicazi")),
    ("snowport", (42.3517, -71.0446, "Seaport", "100 Seaport Blvd, Boston", "Snowport Holiday Market")),
    ("cyclorama", (42.3448, -71.0714, "South End", "539 Tremont St, Boston", "The BCA Cyclorama")),
    ("mills gallery", (42.3444, -71.0716, "South End", "551 Tremont St, Boston", "BCA Mills Gallery")),
    ("calderwood", (42.3444, -71.0706, "South End", "527 Tremont St, Boston", "Calderwood Pavilion")),
    ("wimberly", (42.3444, -71.0706, "South End", "527 Tremont St, Boston", "Calderwood Pavilion")),
    ("bostontheatrescene", (42.3444, -71.0706, "South End", "527 Tremont St, Boston", "Calderwood Pavilion")),
    ("central square theater", (42.3633, -71.1011, "Central Square", "450 Massachusetts Ave, Cambridge", "Central Square Theater")),
    ("central square theatre", (42.3633, -71.1011, "Central Square", "450 Massachusetts Ave, Cambridge", "Central Square Theater")),
    ("piano craft", (42.3396, -71.0817, "South End", "793 Tremont St, Boston", "Piano Craft Gallery")),
    ("church of the advent", (42.3571, -71.0711, "Beacon Hill", "30 Brimmer St, Boston", "Church of the Advent")),
    ("tremont temple", (42.3580, -71.0607, "Downtown", "88 Tremont St, Boston", "Tremont Temple Baptist Church")),
    ("central square", (42.3650, -71.1030, "Central Square", "45 Pearl St, Cambridge", "Cambridge Public Library (Central Square)")),
    ("o'neill", (42.3922, -71.1280, "North Cambridge", "70 Rindge Ave, Cambridge", "Cambridge Public Library (O'Neill)")),
    ("west branch", (42.3985, -71.1220, "Davis Square", "40 College Ave, Somerville", "Somerville Public Library (West Branch)")),
    ("first church in jamaica plain", (42.3106, -71.1147, "Jamaica Plain", "6 Eliot St, Jamaica Plain", "First Church in Jamaica Plain")),
    ("more than words", (42.3448, -71.0632, "South End", "242 E Berkeley St, Boston", "More Than Words")),
    ("west end museum", (42.3644, -71.0645, "West End", "150 Staniford St, Boston", "West End Museum")),
    ("modern renaissance", (42.3998, -71.1179, "Somerville", "115 College Ave, Somerville", "Museum of Modern Renaissance")),
    ("kehillath israel", (42.3458, -71.1255, "Brookline", "384 Harvard St, Brookline", "Congregation Kehillath Israel")),
    ("eitz chayim", (42.3585, -71.1111, "Cambridgeport", "136 Magazine St, Cambridge", "Congregation Eitz Chayim")),
    ("ignatius of loyola", (42.3364, -71.1687, "Chestnut Hill / BC", "28 Commonwealth Ave, Chestnut Hill", "St. Ignatius of Loyola")),
    ("donut villa", (42.4146, -71.1506, "Arlington", "319 Broadway, Arlington", "Donut Villa Arlington")),
    ("the well", (42.3524, -71.0649, "Theater District", "204 Tremont St, Boston", "The Well (Tremont St)")),
    ("conservatory lab", (42.2785, -71.0662, "Dorchester", "2120 Dorchester Ave, Dorchester", "Conservatory Lab Charter School")),
    ("german centre", (42.2737, -71.1586, "West Roxbury", "2222 Centre St, West Roxbury", "German Centre")),
    ("union church", (42.3429, -71.0784, "South End", "485 Columbus Ave, Boston", "Union Church")),
    ("morningside", (42.3308, -71.0837, "Roxbury", "2307 Washington St, Roxbury", "Morningside Annex")),
    ("sowa", (42.3413, -71.0672, "South End", "530 Harrison Ave, Boston", "SoWa Open Market")),
    ("longy", (42.3785, -71.1235, "Harvard Square", "27 Garden St, Cambridge", "Longy School of Music")),
    ("boston symphony", (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall")),
    ("balance patch", (42.3516, -71.1215, "Allston / BU", "1031 Commonwealth Ave, Boston", "Balance Patch")),
    ("dani's queer", (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar")),
    ("danis queer", (42.3485, -71.0843, "Back Bay", "909 Boylston St, Boston", "Dani's Queer Bar")),
    ("bso", (42.3428, -71.0858, "Fenway / Symphony", "301 Massachusetts Ave, Boston", "Symphony Hall")),
    ("boston conservatory", (42.3458, -71.0898, "Fenway", "31 Hemenway St, Boston", "Boston Conservatory Theater")),
    ("seully hall", (42.3466, -71.0895, "Fenway", "8 Fenway, Boston", "Seully Hall (Berklee)")),
    ("houston hall", (42.3466, -71.0895, "Fenway", "8 Fenway, Boston", "Houston Hall (Berklee)")),
    ("berk recital hall", (42.3466, -71.0895, "Fenway", "1140 Boylston St, Boston", "Berk Recital Hall (Berklee)")),
    ("regattabar", (42.3723, -71.1222, "Harvard Square", "1 Bennett St, Cambridge", "Regattabar")),
    ("off the rails", (42.3578, -71.0592, "Downtown", "25 School St, Boston", "Off the Rails Boston")),
    ("dooley", (42.3578, -71.0537, "Financial District", "77 Broad St, Boston", "Mr. Dooley's")),
    ("green dragon", (42.3611, -71.0573, "Faneuil Hall", "11 Marshall St, Boston", "The Green Dragon Tavern")),
    ("hennessy", (42.3609, -71.0567, "Faneuil Hall", "25 Union St, Boston", "Hennessy's Bar")),
    ("uncommon corner", (42.3524, -71.0653, "Downtown", "Boylston St & Tremont St, Boston", "UnCommon Corner")),
    ("roundhead", (42.2472, -71.1344, "Hyde Park", "1 Westinghouse Plaza, Suite i107, Hyde Park", "Roundhead Brewing")),
    ("granoff", (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Granoff Music Center, Tufts University")),
    ("tufts", (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Granoff Music Center, Tufts University")),
    ("redbones", (42.3967, -71.1215, "Davis Square", "55 Chester St, Somerville", "Redbones / Underbones")),
    ("black rose", (42.3596, -71.0543, "Faneuil Hall", "160 State St, Boston", "The Black Rose")),
    ("emmet", (42.3582, -71.0617, "Beacon Hill", "6 Beacon St, Boston", "Emmets Irish Pub")),
    ("portico", (42.3748, -71.0911, "Ward Two", "101 South St, Somerville", "Portico Brewing")),
    ("nec (", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "New England Conservatory (NEC)")),
    ("williams hall", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "Williams Hall (NEC)")),
    ("burnes hall", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "Burnes Hall (NEC)")),
    ("brown hall", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "Brown Hall (NEC)")),
    ("keller room", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "Keller Room (NEC)")),
    ("plimpton shattuck", (42.3412, -71.0866, "Fenway / Symphony", "290 Huntington Ave, Boston", "Plimpton Shattuck Black Box (NEC)")),
    ("oliver colvin", (42.3466, -71.0895, "Fenway", "1140 Boylston St, Boston", "Oliver Colvin Recital Hall (Berklee)")),
    ("david friend recital", (42.3484, -71.0846, "Fenway", "921 Boylston St, Boston", "David Friend Recital Hall (Berklee)")),
    ("notch brewing", (42.3619, -71.1440, "Brighton", "525 Western Ave, Brighton", "Notch Brewing (Brighton)")),
    ("medford/somerville campus", (42.4055, -71.1165, "Medford / Somerville", "20 Talbot Ave, Medford", "Tufts University")),
    ("orpheum theatre", (42.3562, -71.0610, "Downtown Crossing", "1 Hamilton Pl, Boston", "Orpheum Theatre")),
    ("phoenix landing", (42.3641, -71.1019, "Central Square", "512 Massachusetts Ave, Cambridge", "The Phoenix Landing")),
    ("google cambridge", (42.3626, -71.0864, "Kendall Square", "325 Main St, Cambridge", "Google Cambridge (325 Main St)")),
    ("325 main", (42.3626, -71.0864, "Kendall Square", "325 Main St, Cambridge", "Google Cambridge (325 Main St)")),
    ("memorial drive", (42.3688, -71.1152, "Harvard Square", "Memorial Drive, Cambridge", "Memorial Drive Riverbend Park")),
    ("harvard square", (42.3736, -71.1190, "Harvard Square", "Harvard Square, Cambridge", "Harvard Square")),
    ("harvard yard", (42.3744, -71.1169, "Harvard Square", "Harvard Yard, Cambridge", "Harvard Yard")),
    ("harvard/central pogo", (42.3736, -71.1190, "Harvard Square", "Harvard Square & Harvard Yard, Cambridge", "Harvard Square (Harvard/Central PoGO)")),
    ("first parish", (42.3746, -71.1190, "Harvard Square", "3 Church St, Cambridge", "First Parish in Cambridge")),
    ("science center", (42.3764, -71.1166, "Harvard Square", "1 Oxford St, Cambridge", "Harvard Science Center")),
    ("tony demarco", (42.3632, -71.0548, "North End", "193 Hanover St, Boston", "North End (Tony DeMarco Statue)")),
    ("439 tremont", (42.3468, -71.0685, "South End", "439 Tremont St, Boston", "439 Tremont St (South End)")),
    ("swing in the square", (42.3797, -71.0952, "Union Square", "Union Square Plaza, Somerville", "Union Square Plaza")),
    ("wang theatre", (42.3502, -71.0649, "Theater District", "270 Tremont St, Boston", "Boch Center Wang Theatre")),
    ("shubert theatre", (42.3504, -71.0652, "Theater District", "265 Tremont St, Boston", "Boch Center Shubert Theatre")),
    ("memoire", (42.3949, -71.0706, "Everett", "1 Broadway, Everett", "Mémoire Boston")),
    # Frequently-listed venues that previously had no pin
    ("sanders theatre", (42.3763, -71.1147, "Harvard Square", "45 Quincy St, Cambridge", "Sanders Theatre")),
    ("paine concert hall", (42.3779, -71.1164, "Harvard Square", "3 Oxford St, Cambridge", "John Knowles Paine Concert Hall")),
    ("paine hall", (42.3779, -71.1164, "Harvard Square", "3 Oxford St, Cambridge", "John Knowles Paine Concert Hall")),
    ("cathedral church of saint paul", (42.3561, -71.0623, "Downtown", "138 Tremont St, Boston", "Cathedral Church of St. Paul")),
    ("cathedral church of st. paul", (42.3561, -71.0623, "Downtown", "138 Tremont St, Boston", "Cathedral Church of St. Paul")),
    ("ica watershed", (42.3637, -71.0337, "East Boston", "256 Marginal St, East Boston", "ICA Watershed")),
    ("ica/boston", (42.3528, -71.0432, "Seaport", "25 Harbor Shore Dr, Boston", "ICA Boston")),
    ("liberty hotel", (42.3620, -71.0706, "Beacon Hill / West End", "215 Charles St, Boston", "The Liberty Hotel")),
    ("hynes convention", (42.3471, -71.0840, "Back Bay", "900 Boylston St, Boston", "Hynes Convention Center")),
    ("view boston", (42.3471, -71.0820, "Back Bay", "800 Boylston St, Boston", "View Boston (Prudential Tower)")),
    ("prudential center", (42.3471, -71.0820, "Back Bay", "800 Boylston St, Boston", "Prudential Center")),
    ("franklin park zoo", (42.3036, -71.0870, "Franklin Park", "1 Franklin Park Rd, Boston", "Franklin Park Zoo")),
    ("samuel adams boston brewery", (42.3145, -71.1034, "Jamaica Plain", "30 Germania St, Boston", "Samuel Adams Boston Brewery")),
    ("sam adams boston brewery", (42.3145, -71.1034, "Jamaica Plain", "30 Germania St, Boston", "Samuel Adams Boston Brewery")),
    ("cambridgeside", (42.3681, -71.0763, "East Cambridge", "100 CambridgeSide Pl, Cambridge", "CambridgeSide")),
    ("park street church", (42.3568, -71.0620, "Downtown", "1 Park St, Boston", "Park Street Church")),
    ("cambridge masonic hall", (42.3893, -71.1194, "Porter Square", "1950 Massachusetts Ave, Cambridge", "Cambridge Masonic Hall")),
    ("steriti memorial rink", (42.3683, -71.0572, "North End", "561 Commercial St, Boston", "Steriti Memorial Rink")),
    ("boston landing", (42.3570, -71.1393, "Brighton", "Boston Landing, Brighton", "Boston Landing")),
    ("east boston social centers", (42.3753, -71.0386, "East Boston", "68 Central Sq, East Boston", "East Boston Social Centers")),
    ("kenney park", (42.3975, -71.1205, "Davis Square", "Kenney Park, Somerville", "Kenney Park (Davis Square)")),
    ("seven hills park", (42.3963, -71.1214, "Davis Square", "Seven Hills Park, Somerville", "Seven Hills Park (Davis Square)")),
    ("davis square t station", (42.3967, -71.1220, "Davis Square", "Holland St, Somerville", "Davis Square T Station")),
    ("life alive, union square", (42.3797, -71.0950, "Union Square", "Union Square, Somerville", "Life Alive (Union Square)")),
    ("casey's, 173 broadway", (42.3891, -71.0863, "East Somerville", "173 Broadway, Somerville", "Casey's (East Somerville)")),
    ("long live roxbury", (42.3278, -71.0749, "Roxbury", "152 Hampden St, Boston", "Long Live Roxbury")),
    ("dick's house of sport", (42.3489, -71.0819, "Back Bay", "760 Boylston St, Boston", "DICK'S House of Sport (Boylston St)")),
    ("st. peter's episcopal church", (42.3673, -71.1058, "Central Square", "838 Massachusetts Ave, Cambridge", "St. Peter's Episcopal Church (Central Sq)")),
    ("saint peter's episcopal church", (42.3673, -71.1058, "Central Square", "838 Massachusetts Ave, Cambridge", "St. Peter's Episcopal Church (Central Sq)")),
    ("carrie nation", (42.3580, -71.0613, "Beacon Hill / Downtown", "11 Beacon St, Boston", "Carrie Nation Cocktail Club")),
    ("farkas hall", (42.3722, -71.1176, "Harvard Square", "10 Holyoke St, Cambridge", "Farkas Hall (A.R.T.)")),
    ("loeb drama center", (42.3762, -71.1240, "Harvard Square", "64 Brattle St, Cambridge", "Loeb Drama Center (A.R.T.)")),
    ("goel center", (42.3640, -71.1282, "Allston", "175 N Harvard St, Boston", "Goel Center for Creativity & Performance (A.R.T.)")),
    ("harvard film archive", (42.3734, -71.1140, "Harvard Square", "24 Quincy St, Cambridge", "Harvard Film Archive")),
    ("scandinavian cultural center", (42.3599, -71.2214, "West Newton", "206 Waltham St, Newton", "Scandinavian Cultural Center")),
    # Campus-calendar fallbacks (scrapers.scrape_localist / scrape_harvard_college_events add the
    # school to bare building names). Area addresses, so a calendar's own point for the
    # building wins (resolve_event_geo step 2); used when the calendar gives none.
    ("(boston college)", (42.3355, -71.1685, "Chestnut Hill", "Boston College, Chestnut Hill", "Boston College")),
    ("(harvard)", (42.3744, -71.1169, "Harvard Square", "Harvard Yard, Cambridge", "Harvard University")),
    ("(mit)", (42.3590, -71.0940, "Kendall Square / MIT", "MIT, Cambridge", "MIT Campus")),
    ("athanasius", (42.4172, -71.1643, "Arlington", "4 Appleton St, Arlington, MA 02476", "Saint Athanasius Greek Orthodox Church")),
    ("4 appleton", (42.4172, -71.1643, "Arlington", "4 Appleton St, Arlington, MA 02476", "Saint Athanasius Greek Orthodox Church")),
    ("bootleg special", (42.3468, -71.0673, "South End", "400 Tremont St, Boston, MA 02116", "Bootleg Special")),
    ("wcat", (42.3768, -70.9831, "Winthrop", "105 Pauline St, Winthrop, MA 02152", "WCAT Building")),
    ("adams park", (42.2863, -71.1306, "Roslindale", "Washington St & Cummins Hwy, Boston, MA 02131", "Adams Park")),
    ("adam park", (42.2863, -71.1306, "Roslindale", "Washington St & Cummins Hwy, Boston, MA 02131", "Adams Park")),
    ("birch st plaza", (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Birch St Plaza")),
    ("birch street", (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Birch St Plaza")),
    ("roslindale village", (42.2868, -71.1294, "Roslindale", "Birch St Plaza, Roslindale, MA 02131", "Roslindale Village")),
    ("emerald society", (42.2865, -71.1291, "Roslindale", "10 Birch St, Roslindale, MA 02131", "Emerald Society")),
    ("446 west broadway", (42.3364, -71.0475, "South Boston", "446 W Broadway, South Boston, MA 02127", "446 West Broadway")),
    ("brighton elk", (42.3512, -71.1554, "Brighton", "326 Washington St, Brighton, MA 02135", "Brighton Elks Lodge")),
    ("marzae cellar", (42.4842, -71.4429, "Acton", "63 Elm St, Acton, MA 01720", "Marzae Cellar + Provisions")),
    ("reggie lewis", (42.3312, -71.0963, "Roxbury", "1350 Columbus Ave, Boston, MA 02120", "Reggie Lewis Track and Athletic Center")),
    ("turtle books", (42.3411, -71.1251, "Brookline", "1324 Beacon St, Brookline, MA 02446", "Turtle Books")),
    ("cambridge antique market", (42.3705, -71.0772, "East Cambridge", "201 Msgr O'Brien Hwy, Cambridge, MA 02141", "Cambridge Antique Market")),
    ("brattle square", (42.3739, -71.1198, "Harvard Square", "1 Brattle Sq, Cambridge, MA 02138", "1 Brattle Square")),
    ("brigham circle", (42.3340, -71.1060, "Mission Hill", "Tremont St & Huntington Ave, Boston, MA 02120", "Brigham Circle")),
    ("brookline farmers market", (42.3424, -71.1215, "Brookline", "Centre St West Parking Lot, Brookline, MA 02446", "Brookline Farmers Market")),
    ("community resources & wellness", (42.3712, -71.0375, "East Boston", "282 Meridian St, East Boston, MA 02128", "Community Resources & Wellness Center")),
    ("dudley town commons", (42.3276, -71.0825, "Roxbury", "Dudley St & Blue Hill Ave, Boston, MA 02119", "Dudley Town Commons")),
    ("jamaica plain farmers", (42.3125, -71.1140, "Jamaica Plain", "677 Centre St, Jamaica Plain, MA 02130", "Jamaica Plain Farmers Market")),
    ("roxbury crossing", (42.3315, -71.0945, "Roxbury", "1400 Tremont St, Boston, MA 02120", "Roxbury Crossing")),
    ("60 beach st", (42.3516, -71.0601, "Chinatown", "60 Beach St, Boston, MA 02111", "Chinatown (60 Beach St)")),
    ("brighton allston congregational", (42.3496, -71.1539, "Brighton", "404 Washington St, Brighton, MA 02135", "Brighton Allston Congregational Church")),
    ("church of the good shepherd", (42.3683, -71.1738, "Watertown", "9 Russell Ave, Watertown, MA 02472", "Church of the Good Shepherd")),
    ("holy trinity", (42.5621, -70.9338, "Danvers", "16 Newcomb St, Danvers, MA 01923", "Holy Trinity United Methodist Church")),
]

# Coordinate bounding box for valid Greater Boston / Eastern MA events
MIN_LAT, MAX_LAT = 41.8, 42.8
MIN_LNG, MAX_LNG = -71.8, -70.5


# Sources whose coordinates are approximate (Ticketmaster often returns an area point, not the
# building: Royale and the Emerson Colonial share one point ~800 m from both). A curated match
# on the venue name always beats these.
LOW_TRUST_COORD_SOURCES = ("ticketmaster",)
# A trusted source's point this far from a venue-name pattern match means the pattern hit an
# umbrella name ("Boston Public Library (South End)" matches the Copley library's pattern,
# "MIT Building E62" matches "MIT Campus").
UMBRELLA_MISMATCH_METERS = 400
# Points one source assigns to several different venues are placeholders, not locations.
_SHARED_SOURCE_POINTS: set = set()


def _meters(lat1, lng1, lat2, lng2):
    import math
    dy = (lat2 - lat1) * 111_000
    dx = (lng2 - lng1) * 111_000 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def _geo(entry):
    lat, lng, neigh, addr, cname = entry
    return {"lat": lat, "lng": lng, "venue": cname, "neighborhood": neigh, "address": addr}


def _exact_venue_match(v_lower):
    norm_v = re.sub(r"[^\w\s]", "", v_lower).strip()
    for key in (v_lower, norm_v):
        if key and key in VENUE_COORDINATES:
            return VENUE_COORDINATES[key]
    return None


def _rule_match(hay):
    if hay:
        for needle, entry in VENUE_RULES:
            if needle in hay:
                return entry
    return None


def _point_key(lat, lng):
    return (round(float(lat), 4), round(float(lng), 4))


def _native_point(event):
    lat = event.get("lat") or event.get("latitude")
    lng = event.get("lng") or event.get("lon") or event.get("longitude")
    if lat is None or lng is None:
        return None
    try:
        flat, flng = float(lat), float(lng)
    except (ValueError, TypeError):
        return None
    if not (MIN_LAT <= flat <= MAX_LAT and MIN_LNG <= flng <= MAX_LNG):
        return None
    if _point_key(flat, flng) in _SHARED_SOURCE_POINTS:
        return None
    return flat, flng


def flag_shared_source_points(events_or_venues) -> int:
    """Find coordinates a source uses for several different venues (placeholder points) so
    resolve_event_geo ignores them. Accepts scraper results (dicts with "events") or a flat
    event list. Returns how many points were flagged."""
    by_point = {}
    for item in events_or_venues or []:
        evs = item.get("events") if isinstance(item, dict) and "events" in item else [item]
        src = item.get("venue", "") if isinstance(item, dict) and "events" in item else ""
        for e in evs or []:
            lat = e.get("lat") or e.get("latitude")
            lng = e.get("lng") or e.get("lon") or e.get("longitude")
            if lat is None or lng is None:
                continue
            try:
                key = _point_key(lat, lng)
            except (ValueError, TypeError):
                continue
            v_lower = (e.get("venue") or e.get("_source_venue") or src or "").strip().lower()
            entry = _exact_venue_match(v_lower) or _rule_match(v_lower)
            by_point.setdefault(key, {})[entry[4] if entry else re.sub(r"[^a-z0-9]", "", v_lower)] = entry
    _SHARED_SOURCE_POINTS.clear()
    _GEO_CACHE.clear()  # answers depend on the flagged points
    for key, venues in by_point.items():
        if len(venues) < 2:
            continue
        known = [v for v in venues.values() if v]
        # A point sitting on one of its venues is that venue's real location (other names for
        # the same building, e.g. "465 Huntington Ave" for the MFA), not a placeholder.
        if any(_meters(key[0], key[1], v[0], v[1]) <= 150 for v in known):
            continue
        # Rooms of one building (Middle East Upstairs/Downstairs) share a point legitimately.
        spread = max((_meters(a[0], a[1], b[0], b[1]) for a in known for b in known), default=0)
        if spread > 150 or len(venues) - len(known) >= 3:
            _SHARED_SOURCE_POINTS.add(key)
    return len(_SHARED_SOURCE_POINTS)


# resolve_event_geo is called millions of times per build (duplicate merging compares event
# pairs), so answers are cached by everything they depend on: the fields read below, plus the
# shared-point set (the cache is cleared whenever flag_shared_source_points recomputes it).
_GEO_CACHE: Dict[tuple, Optional[Dict[str, Any]]] = {}
_GEO_CACHE_MAX = 200_000


def resolve_event_geo(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """resolve_event_geo_uncached, cached; returns a fresh dict each call."""
    key = (event.get("venue"), event.get("_source_venue"), event.get("name"), event.get("title"),
           event.get("lat"), event.get("latitude"), event.get("lng"), event.get("lon"), event.get("longitude"),
           event.get("neighborhood"), event.get("address"))
    try:
        hit = _GEO_CACHE[key]
    except KeyError:
        hit = resolve_event_geo_uncached(event)
        if len(_GEO_CACHE) >= _GEO_CACHE_MAX:
            _GEO_CACHE.clear()
        _GEO_CACHE[key] = hit
    except TypeError:  # an unhashable field (a list where a string belongs): don't cache
        return resolve_event_geo_uncached(event)
    return dict(hit) if hit is not None else None


def resolve_event_geo_uncached(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve latitude, longitude, neighborhood, and venue name for an event.

    Order:
    1. Exact curated venue name.
    2. Venue-name pattern (VENUE_RULES) on the event's own venue field, unless a trusted
       source's own point is over 1 km away (the pattern matched an umbrella name).
    3. The source's own coordinates, unless flagged as a shared placeholder point.
    4. Venue-name pattern on the source/presenter name or title (last resort: "Sing-A-Long
       LIVE" in a title must not place a Lynn show at Long Live Roxbury).
    """
    venue_raw = (event.get("venue") or "").strip()
    source_raw = (event.get("_source_venue") or "").strip()
    title_raw = (event.get("name") or event.get("title") or "").strip()

    # Discard non-physical venues
    v_lower = venue_raw.lower()
    if v_lower in ("zoom", "online", "virtual", "online event", "tba", "various") or "(virtual)" in v_lower or "online event" in v_lower:
        return None

    native = _native_point(event)
    trusted_native = native and not any(s in source_raw.lower() for s in LOW_TRUST_COORD_SOURCES)

    # 1. Exact curated venue
    entry = _exact_venue_match(v_lower)
    if entry:
        return _geo(entry)

    # 2. Pattern on the venue field itself
    entry = _rule_match(v_lower)
    if entry and not (trusted_native and (
            _meters(native[0], native[1], entry[0], entry[1]) > UMBRELLA_MISMATCH_METERS
            or not re.search(r"\d", entry[3]))):  # area match ("Harvard Square"), not a building
        return _geo(entry)

    # 3. The source's own coordinates
    if native:
        return {
            "lat": round(native[0], 5),
            "lng": round(native[1], 5),
            "venue": venue_raw or source_raw,
            "neighborhood": event.get("neighborhood") or "",
            "address": event.get("address") or "",
        }

    # 4. Pattern on source/presenter name and title
    entry = _rule_match(f"{v_lower} {source_raw.lower()} {title_raw.lower()}")
    if entry:
        return _geo(entry)

    return None


def nearest_curated_venue(lat, lng, max_meters=200):
    """Closest curated venue (with a street address) to a coordinate, if within max_meters.
    Used to place events whose source gives coordinates but no address."""
    import math
    best, best_d = None, None
    entries = list(VENUE_COORDINATES.values()) + [v for _, v in VENUE_RULES]
    for vlat, vlng, neigh, addr, cname in entries:
        if not addr or "," not in addr:
            continue
        dy = (vlat - lat) * 111_000
        dx = (vlng - lng) * 111_000 * math.cos(math.radians(lat))
        d = math.hypot(dx, dy)
        if best_d is None or d < best_d:
            best, best_d = (vlat, vlng, neigh, addr, cname), d
    if best is not None and best_d <= max_meters:
        return {"lat": best[0], "lng": best[1], "neighborhood": best[2], "address": best[3], "venue": best[4]}
    return None
