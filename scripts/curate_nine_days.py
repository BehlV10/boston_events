#!/usr/bin/env python3
"""
Curate 15 high-quality recommendations per day for 9 consecutive days
(Monday Nov 2 through Tuesday Nov 10, 2026) in highlights.json.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "highlights.json")

NINE_DAYS_CURATION = {
    "2026-11-02": [
        # Existing 10 + 5 new to make 15
        {
            "id": "2026-11-02-jordan-hall",
            "match": {"name_contains": "First Monday", "venue_contains": "Jordan Hall"},
            "badge": "🎻 World-Class Classical",
            "note": "Renowned free chamber concert series in NEC's acoustically celebrated Jordan Hall.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-coolidge-network",
            "match": {"name_contains": "Network", "venue_contains": "Coolidge"},
            "badge": "🎬 Cult Cinema",
            "note": "Sidney Lumet's razor-sharp 1976 media satire on the big screen.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-somerville-basterds",
            "match": {"name_contains": "Inglourious Basterds", "venue_contains": "Somerville Theatre"},
            "badge": "📽️ 35mm Masterpiece",
            "note": "Tarantino's alt-history WWII epic projected in glorious vintage 35mm film in Davis Square.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-paradise-mico",
            "match": {"name_contains": "MICO", "venue_contains": "Paradise Rock"},
            "badge": "🎸 Alt-Pop/Rock",
            "note": "Rising indie powerhouse with dynamic vocal chops taking the iconic Comm Ave stage.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-rockwell-menopunks",
            "match": {"name_contains": "Menopunks", "venue_contains": "Rockwell"},
            "badge": "🎭 Underground Comedy",
            "note": "High-octane musical comedy riot tackling aging and rebellion in Davis Square.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-lilypad-fringe",
            "match": {"name_contains": "The Fringe", "venue_contains": "Lilypad"},
            "badge": "🎷 50-Year Jazz Tradition",
            "note": "Legendary Monday avant-garde jazz residency led by saxophone titan George Garzone.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-city-winery-oday",
            "match": {"name_contains": "Aubrey O'Day", "venue_contains": "City Winery"},
            "badge": "🎤 Pop Intimate",
            "note": "Danity Kane star brings an intimate acoustic and storytelling evening to Boston.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-remnant-royer",
            "match": {"name_contains": "Royer Family Band", "venue_contains": "Remnant"},
            "badge": "🪕 Bluegrass Monday",
            "note": "Free tight family harmonies, banjo picking, and craft beer at Bow Market in Somerville.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-versus-arcade",
            "match": {"name_contains": "VERSUS", "venue_contains": "VERSUS"},
            "badge": "🕹️ Retro Gaming Night",
            "note": "Downtown Boston's neon-drenched arcade bar with unlimited retro pinball and draft pours.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-beehive-hoedown",
            "match": {"name_contains": "HOEDOWN", "venue_contains": "Beehive"},
            "badge": "🎻 Honky Tonk & Soul",
            "note": "Boot-stomping Americana and country-blues jam in the bohemian South End cellar.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-wallys-jazz",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 Boston Jazz Heritage",
            "note": "Historic 1947 South End venue with zero cover charge and world-class Berklee players.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-burren-traditional",
            "match": {"name_contains": "Irish Session", "venue_contains": "Burren"},
            "badge": "☘️ Authentic Celtic Tradition",
            "note": "Traditional acoustic fiddle, bodhrán, and accordion session in Davis Square's Front Room.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-bebop-jazz-jam",
            "match": {"name_contains": "Monday Jazz Jam", "venue_contains": "Bebop"},
            "badge": "🎶 Free Live Jazz Jam",
            "note": "Spirited Monday jazz jam steps from Berklee with Boston's sharpest up-and-coming players.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-cantab-open-mic",
            "match": {"name_contains": "Open Mic", "venue_contains": "Cantab"},
            "badge": "🎤 Central Sq Open Mic",
            "note": "Cambridge's favorite long-running Monday musical proving ground with cold pints and local camaraderie.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        },
        {
            "id": "2026-11-02-passim-open-mic",
            "match": {"name_contains": "Open Mic", "venue_contains": "Passim"},
            "badge": "⭐ Harvard Sq Songwriter Stage",
            "note": "Folk music royalty's basement stage welcoming acoustic singer-songwriters every Monday.",
            "start_date": "2026-11-02", "expires": "2026-11-02"
        }
    ],

    "2026-11-03": [
        {
            "id": "2026-11-03-sinclair-halfalive",
            "match": {"name_contains": "half•alive", "venue_contains": "Sinclair"},
            "badge": "⚡ Indie Pop Movement",
            "note": "Explosive choreography and infectious indie-pop anthems in Harvard Square.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-crystal-carlisle",
            "match": {"name_contains": "Willi Carlisle", "venue_contains": "Crystal Ballroom"},
            "badge": "🪕 Folk & Storytelling",
            "note": "Folksinger, poet, and punk-hearted multi-instrumentalist brings rowdy hootenanny to Somerville.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-armory-kate-nash",
            "match": {"name_contains": "Kate Nash", "venue_contains": "Armory"},
            "badge": "🎹 UK Indie Pop Legend",
            "note": "Brit Award-winning feminist pop icon brings her powerhouse new tour to Somerville.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-somerville-eraserhead",
            "match": {"name_contains": "Eraserhead", "venue_contains": "Somerville Theatre"},
            "badge": "🎬 Lynchian Cult Night",
            "note": "David Lynch's surrealist 1977 masterpiece in all its nightmarish audio-visual glory.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-coolidge-open-screen",
            "match": {"name_contains": "Boston Open Screen", "venue_contains": "Coolidge"},
            "badge": "🎥 Micro-Cinema Showcase",
            "note": "Boston's longest-running open mic for local filmmakers: bring your project, watch on the big screen.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-jordan-centennial",
            "match": {"name_contains": "Centennial Celebration", "venue_contains": "Jordan Hall"},
            "badge": "🎼 Avant-Garde Soundscapes",
            "note": "NEC faculty and students celebrate 100 years of groundbreaking contemporary compositions.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-hob-sirens",
            "match": {"name_contains": "Sleeping With Sirens", "venue_contains": "House of Blues"},
            "badge": "⚡ Post-Hardcore Anthem",
            "note": "Kellin Quinn and crew celebrate 10 years of 'Let's Cheers to This' with deafening Fenway energy.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-danis-bingo",
            "match": {"name_contains": "Drag Bingo", "venue_contains": "Dani's"},
            "badge": "👑 Tuesday Drag & Games",
            "note": "Fierce queens, drink specials, and hilarious high-stakes bingo at Back Bay's queer bar.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-aeronaut-trivia",
            "match": {"name_contains": "INDIE TRIVIA", "venue_contains": "Aeronaut"},
            "badge": "🧠 Craft Beer Trivia",
            "note": "High-octane, geek-friendly trivia hosted by Ben C in Aeronaut's soaring brewery hall.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-cantab-harvest",
            "match": {"name_contains": "Harvest Fest", "venue_contains": "Cantab"},
            "badge": "🎷 Central Sq Jump",
            "note": "Upbeat local jazz and funk grooves in Cambridge's beloved subterranean music institution.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-manray-karaoke",
            "match": {"name_contains": "Karaoke Noir", "venue_contains": "ManRay"},
            "badge": "🖤 Goth & Alt Karaoke",
            "note": "Sing your favorite darkwave, 80s post-punk, and alternative tunes with no cover in Central Square.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-wallys-blues",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 Historic Tuesday Jam",
            "note": "Legendary South End jazz dive running 365 nights a year with raw virtuosity.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-lamplighter-trivia",
            "match": {"name_contains": "Broadway Trivia", "venue_contains": "Lamplighter"},
            "badge": "🍻 Brewery Brainiacs",
            "note": "Test your general knowledge over fresh IPAs and wood-fired pies in Cambridgeport.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-lilypad-jazz",
            "match": {"name_contains": "Jazz", "venue_contains": "Lilypad"},
            "badge": "🎹 Inman Sq Improvisers",
            "note": "Intimate cutting-edge acoustic ensemble improvisations in Inman Square.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        },
        {
            "id": "2026-11-03-beehive-tuesday",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Beehive"},
            "badge": "🍸 South End Supper Club",
            "note": "Atmospheric jazz lounge dining with craft cocktails and sultry live rhythms.",
            "start_date": "2026-11-03", "expires": "2026-11-03"
        }
    ],

    "2026-11-04": [
        {
            "id": "2026-11-04-sinclair-halfalive-n2",
            "match": {"name_contains": "half•alive", "venue_contains": "Sinclair"},
            "badge": "⚡ Sold Out Encore",
            "note": "Night two of the viral indie pop hitmakers in Harvard Square.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-jordan-loebel",
            "match": {"name_contains": "David Loebel", "venue_contains": "Jordan Hall"},
            "badge": "🎻 Free Master Orchestral",
            "note": "NEC Symphony performs masterworks conducted by David Loebel in historic Jordan Hall.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-crystal-duff-goldman",
            "match": {"name_contains": "Duff Goldman", "venue_contains": "Crystal Ballroom"},
            "badge": "🎂 Live Culinary Storytelling",
            "note": "Ace of Cakes culinary pioneer Duff Goldman brings behind-the-scenes bakery tales to Davis Sq.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-somerville-warren-miller",
            "match": {"name_contains": "Warren Miller", "venue_contains": "Somerville Theatre"},
            "badge": "⛷️ Action Film Premiere",
            "note": "Annual winter ski and snowboard pilgrimage film packed with jaw-dropping big-mountain cinematography.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-brighton-pretty-sick",
            "match": {"name_contains": "Pretty Sick", "venue_contains": "Brighton Music Hall"},
            "badge": "🎸 90s Grunge Revival",
            "note": "Sabrina Fuentes leads raw, visceral NYC grunge-pop and sludgy bass hooks in Allston.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-armory-horror-karaoke",
            "match": {"name_contains": "Karaoke", "venue_contains": "Armory"},
            "badge": "🎤 Performance Art",
            "note": "Experimental vocal expressions, live music, and dark karaoke in the Armory Café.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-lilypad-variety",
            "match": {"name_contains": "Variety Show", "venue_contains": "Lilypad"},
            "badge": "🎭 Inman Underground",
            "note": "Puppetry, music, standup, and offbeat performance oddities in Cambridge's creative clubhouse.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-cantab-poetry-slam",
            "match": {"name_contains": "Poetry Slam", "venue_contains": "Cantab"},
            "badge": "🎙️ Spoken Word Championship",
            "note": "The legendary Boston Poetry Slam brings national champions and fiery verses to Central Sq.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-midway-vinyl",
            "match": {"name_contains": "Wax & Stacks", "venue_contains": "Midway"},
            "badge": "💿 Analog Vinyl Session",
            "note": "DJs spin deep cuts on original wax in Jamaica Plain's quintessential punk and rock dive.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-aeronaut-survivor",
            "match": {"name_contains": "Survivor", "venue_contains": "Aeronaut"},
            "badge": "📺 Cult Community Viewing",
            "note": "Cheer on tribal council with craft beer, giant projection screens, and passionate superfans.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-central-sq-theater",
            "match": {"name_contains": "The Getaway Driver", "venue_contains": "Central Square Theater"},
            "badge": "🎭 Acclaimed World Premiere",
            "note": "Gripping, high-octane comedy-drama exploring freedom and identity on Mass Ave.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-burren-traditional",
            "match": {"name_contains": "Irish Session", "venue_contains": "Burren"},
            "badge": "☘️ Midweek Trad Jam",
            "note": "Acoustic reels, jigs, and hearty pub dinners in the cozy Davis Square front snug.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-beehive-jazz",
            "match": {"name_contains": "Live Music", "venue_contains": "Beehive"},
            "badge": "🎷 South End Bohemia",
            "note": "Live Afro-Cuban jazz and swing grooves alongside bistro dining in the South End.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-wallys-nightly",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 Nightly Berklee Chops",
            "note": "Intimate historic jazz bar hosting the next generation of jazz greats with zero cover.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        },
        {
            "id": "2026-11-04-porter-sq-books",
            "match": {"name_contains": "Howard Mansfield", "venue_contains": "Porter Square Books"},
            "badge": "📖 Literary Talk & Signing",
            "note": "Author Howard Mansfield discusses 'Invisible Monuments' in Cambridge's indie haven.",
            "start_date": "2026-11-04", "expires": "2026-11-04"
        }
    ],

    "2026-11-05": [
        {
            "id": "2026-11-05-mgm-chief-keef",
            "match": {"name_contains": "CHIEF KEEF", "venue_contains": "MGM Music Hall"},
            "badge": "🔥 Drill Hip-Hop Icon",
            "note": "Chicago drill founding father brings groundbreaking energy and mega-hits to Fenway.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-hob-palace",
            "match": {"name_contains": "Palace", "venue_contains": "House of Blues"},
            "badge": "✨ Lush UK Alt-Rock",
            "note": "London indie dreamers bring sweeping, emotional guitars and soaring vocals on their 2026 tour.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-chevalier-air-supply",
            "match": {"name_contains": "Air Supply", "venue_contains": "Chevalier"},
            "badge": "🎶 Classic Soft Rock Hits",
            "note": "Legendary Australian duo performs timeless stadium singalongs at historic Chevalier Theatre.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-bmh-kylie-morgan",
            "match": {"name_contains": "Kylie Morgan", "venue_contains": "Brighton Music Hall"},
            "badge": "🤠 Country-Pop Rising",
            "note": "Healed Cowgirl Tour brings honest, infectious Nashville anthems to Allston.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-paradise-regan",
            "match": {"name_contains": "Ethan Regan", "venue_contains": "Paradise Rock"},
            "badge": "🎸 Heartland Indie",
            "note": "Gritty folk-rock ballads and vulnerable songwriting on the historic Paradise stage.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-regattabar-alterman",
            "match": {"name_contains": "Joe Alterman", "venue_contains": "Regattabar"},
            "badge": "🎹 World-Class Jazz Trio",
            "note": "Ahmad Jamal-praised jazz pianist brings swinging, soul-stirring blues to Harvard Square.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-sonia-late-night",
            "match": {"name_contains": "Late Night Thoughts", "venue_contains": "Sonia"},
            "badge": "⚡ Local Indie Spotlight",
            "note": "Boston pop-rock favorites and Sneaky Miles team up for high-energy dancing in Central Sq.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-improv-asylum",
            "match": {"name_contains": "Main Stage", "venue_contains": "Improv Asylum"},
            "badge": "😂 North End Improv",
            "note": "Fast-paced sketch and audience-fueled improv in Boston's underground North End comedy den.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-castle-island-trivia",
            "match": {"name_contains": "Trivia With TIm", "venue_contains": "Castle Island"},
            "badge": "🍻 Southie Taproom Trivia",
            "note": "South Boston harbor views, smash burgers, and lively team trivia showdowns.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-beehive-thursday",
            "match": {"name_contains": "Live Music", "venue_contains": "Beehive"},
            "badge": "🎷 Gypsy Jazz & Soul",
            "note": "South End cellar club delivering sultry acoustic jazz rhythms and candlelit craft cocktails.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-burren-bluegrass",
            "match": {"name_contains": "Irish Session", "venue_contains": "Burren"},
            "badge": "☘️ Davis Square Trad",
            "note": "Authentic reels, hearty Guinness, and lively pub banter in the Front Room.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-wallys-night",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 South End Midnight Jam",
            "note": "Zero cover, red-hot solos, and raw Boston jazz authenticity at 427 Mass Ave.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-somerville-theatre",
            "match": {"name_contains": "The Room", "venue_contains": "Somerville Theatre"},
            "badge": "🎬 Cult Classic Screening",
            "note": "Special midnight cult film showing in Davis Square's century-old movie palace.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-trident-trivia",
            "match": {"name_contains": "Trivia", "venue_contains": "Trident"},
            "badge": "📚 Newbury St Bookish Trivia",
            "note": "Boston's favorite indie bookstore café hosts lively trivia with books, draft ciders, and pub bites.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        },
        {
            "id": "2026-11-05-bebop-thursday",
            "match": {"name_contains": "Live Music", "venue_contains": "Bebop"},
            "badge": "🎸 Back Bay Acoustic Jam",
            "note": "Cozy Boylston Street Irish and acoustic music joint buzzing with student and veteran talent.",
            "start_date": "2026-11-05", "expires": "2026-11-05"
        }
    ],

    "2026-11-06": [
        {
            "id": "2026-11-06-chevalier-maron",
            "match": {"name_contains": "Marc Maron", "venue_contains": "Chevalier"},
            "badge": "🎙️ Comedy Icon",
            "note": "WTF podcast pioneer brings his blistering, introspective stand-up tour to Chevalier Theatre.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-bnl-svdden-death",
            "match": {"name_contains": "Svdden Death", "venue_contains": "Big Night Live"},
            "badge": "🔊 Heavy Bass & Dubstep",
            "note": "Ground-shaking bass heavyweight headlines Big Night Live's concert hall next to TD Garden.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-paradise-almost-monday",
            "match": {"name_contains": "almost monday", "venue_contains": "Paradise Rock"},
            "badge": "🌴 Sun-Drenched Indie Pop",
            "note": "California garage-surf pop trio brings infectious hooks and dance grooves to Comm Ave.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-hob-amble",
            "match": {"name_contains": "Amble", "venue_contains": "House of Blues"},
            "badge": "☘️ Irish Contemporary Folk",
            "note": "Fast-rising Irish acoustic trio sells out international dates with soulful songwriting.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-bmh-kyle-hume",
            "match": {"name_contains": "Kyle Hume", "venue_contains": "Brighton Music Hall"},
            "badge": "✨ Melodic Pop Spotlight",
            "note": "Viral singer-songwriter delivers emotive electronic-pop hooks in Allston.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-scullers-elan-trotman",
            "match": {"name_contains": "ELAN TROTMAN", "venue_contains": "Scullers Jazz"},
            "badge": "🎷 25 Years of Smooth Jazz",
            "note": "Acclaimed saxophonist Elan Trotman celebrates 25 years of groove on the Charles River.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-sonia-meet-me-altar",
            "match": {"name_contains": "Meet Me @ The Altar", "venue_contains": "Sonia"},
            "badge": "⚡ Pop-Punk Explosion",
            "note": "Fueled By Ramen pop-punk breakout icons tear down the Sonia stage in Central Square.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-sinclair-friday",
            "match": {"name_contains": "Indie", "venue_contains": "Sinclair"},
            "badge": "🎸 Harvard Square Friday",
            "note": "Top touring indie acts and dual-level rock club vibes in the heart of Cambridge.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-improv-asylum-weekend",
            "match": {"name_contains": "Main Stage", "venue_contains": "Improv Asylum"},
            "badge": "😂 Friday Comedy Revue",
            "note": "High-octane comedic improv fueled by audience chaos in the North End.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-beehive-friday-jazz",
            "match": {"name_contains": "Live Music", "venue_contains": "Beehive"},
            "badge": "🍸 Weekend Soul & Funk",
            "note": "Electric weekend energy, craft dining, and late-night funk in the South End basement.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-burren-backroom",
            "match": {"name_contains": "Back Room", "venue_contains": "Burren"},
            "badge": "🎶 Davis Square Live",
            "note": "Top regional rock, Celtic-rock, and folk bands rocking the Burren's legendary Back Room.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-wallys-weekend",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 South End Midnight Jazz",
            "note": "Friday night jazz jam packing the tiny historic bar with world-class horn sections.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-cantab-friday",
            "match": {"name_contains": "Live Music", "venue_contains": "Cantab"},
            "badge": "🍺 Central Sq Rock & Blues",
            "note": "Classic Cambridge dive bar energy, sticky floors, and high-voltage guitar riffs.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-remnant-friday",
            "match": {"name_contains": "Music", "venue_contains": "Remnant"},
            "badge": "✨ Bow Market Craft Beers",
            "note": "Tasting room beats and late-night eats nestled in Somerville's premier open-air market.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        },
        {
            "id": "2026-11-06-mfa-first-fridays",
            "match": {"name_contains": "First Fridays", "venue_contains": "MFA"},
            "badge": "🎨 Museum After Dark",
            "note": "World-class art galleries, guest DJs, signature cocktails, and vibrant Boston socializing.",
            "start_date": "2026-11-06", "expires": "2026-11-06"
        }
    ],

    "2026-11-07": [
        {
            "id": "2026-11-07-mgm-sammy-rae",
            "match": {"name_contains": "Sammy Rae & The Friends", "venue_contains": "MGM Music Hall"},
            "badge": "✨ Big Band Funk Celebration",
            "note": "Soul-funk joy, powerhouse rhythm section, and inclusive community dancing at Fenway.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-bmh-porch-light",
            "match": {"name_contains": "Porch Light", "venue_contains": "Brighton Music Hall"},
            "badge": "🎸 Indie Folk-Rock",
            "note": "Hush Tour brings stirring acoustic arrangements and rich multi-part harmonies to Allston.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-paradise-mr-fantasy",
            "match": {"name_contains": "Mr. Fantasy", "venue_contains": "Paradise Rock"},
            "badge": "⚡ Saturday Night Funk",
            "note": "Groove-heavy psychedelic rock and soulful retro showmanship on Comm Ave.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-castle-island-thrift",
            "match": {"name_contains": "Steal My Style", "venue_contains": "Castle Island"},
            "badge": "🛍️ Vintage & Thrift Market",
            "note": "Dozens of curated local vintage dealers, streetwear, craft beer, and Southie waterfront vibes.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-remnant-renaissance",
            "match": {"name_contains": "Renaissance Faire", "venue_contains": "Remnant"},
            "badge": "⚔️ Bow Market Faire",
            "note": "Mead, artisan goods, costumes, and whimsical medieval festivities in Union Square.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-improv-asylum-raunch",
            "match": {"name_contains": "Raunch", "venue_contains": "Improv Asylum"},
            "badge": "🔥 Late-Night Adult Improv",
            "note": "Midnight no-holds-barred dirty comedy show in the North End.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-crystal-ballroom",
            "match": {"name_contains": "Concert", "venue_contains": "Crystal Ballroom"},
            "badge": "🪩 Davis Sq Historic Ballroom",
            "note": "Restored 1914 Somerville ballroom hosting high-energy touring bands and dance parties.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-longy-chamber",
            "match": {"name_contains": "Recital", "venue_contains": "Longy"},
            "badge": "🎻 Free Harvard Sq Classical",
            "note": "Intimate acoustic chamber performances in the historic Rey-Waldstein Building.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-beehive-saturday",
            "match": {"name_contains": "Live Music", "venue_contains": "Beehive"},
            "badge": "🍸 South End Saturday Jam",
            "note": "Top jazz and R&B headliners, vibrant South End dining, and candlelit ambiance.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-burren-saturday-session",
            "match": {"name_contains": "Irish Session", "venue_contains": "Burren"},
            "badge": "☘️ Saturday Afternoon Trad",
            "note": "Relaxed acoustic Irish trad jam starting at 3 PM in Davis Square's Front Room.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-wallys-saturday",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 South End Jazz Institution",
            "note": "Packed house, fiery trumpets, and raw improvisation running till 1 AM.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-aeronaut-saturday",
            "match": {"name_contains": "Music", "venue_contains": "Aeronaut"},
            "badge": "🍻 Brewery Stage Sessions",
            "note": "Local brass bands and singer-songwriters filling Aeronaut's sprawling Somerville community taproom.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-rockwell-comedy",
            "match": {"name_contains": "Comedy", "venue_contains": "Rockwell"},
            "badge": "🎭 Davis Sq Black Box",
            "note": "Underground variety shows, indie standup, and cheeky cabaret in Somerville.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-cantab-saturday",
            "match": {"name_contains": "Live Music", "venue_contains": "Cantab"},
            "badge": "🎸 Saturday Night Rock",
            "note": "Sweaty, beer-spilling rock and roll rhythms right by the Central Sq Red Line stop.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        },
        {
            "id": "2026-11-07-somerville-theatre-cinema",
            "match": {"name_contains": "Film", "venue_contains": "Somerville Theatre"},
            "badge": "📽️ Historic 35mm Screenings",
            "note": "Fresh movie popcorn and celluloid screenings in Somerville's beloved community jewel.",
            "start_date": "2026-11-07", "expires": "2026-11-07"
        }
    ],

    "2026-11-08": [
        {
            "id": "2026-11-08-chevalier-ben-schwartz",
            "match": {"name_contains": "Ben Schwartz", "venue_contains": "Chevalier"},
            "badge": "😂 Long-Form Improv Master",
            "note": "Parks & Rec star and special celebrity guests create an entire two-hour comedy show from thin air.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-sinclair-boston-manor",
            "match": {"name_contains": "Boston Manor", "venue_contains": "Sinclair"},
            "badge": "⚡ UK Alt-Rock Heavyweights",
            "note": "Blackpool post-hardcore powerhouse brings blistering riffs and emotional anthems to Harvard Sq.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-symphony-igor-levit",
            "match": {"name_contains": "Igor Levit", "venue_contains": "Symphony Hall"},
            "badge": "🎹 Virtuoso Classical Recital",
            "note": "World-renowned pianist Igor Levit commands Boston Symphony Hall with jaw-dropping precision.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-jordan-civic-symphony",
            "match": {"name_contains": "Boston Civic Symphony", "venue_contains": "Jordan Hall"},
            "badge": "🎻 Season Opener Orchestral",
            "note": "Boston's second-oldest orchestra launches its monumental new season in Jordan Hall.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-bmh-red-leather",
            "match": {"name_contains": "Red Leather", "venue_contains": "Brighton Music Hall"},
            "badge": "🎸 Raw Heartland Rock",
            "note": "Tahoe Tour delivers mysterious masked alt-rock and confessional outlaw storytelling in Allston.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-hob-wheeler-walker",
            "match": {"name_contains": "Wheeler Walker", "venue_contains": "House of Blues"},
            "badge": "🤠 Outlaw Country Satire",
            "note": "Farewell Tour with Channing Wilson bringing rowdy, hilariously explicit country anthems to Fenway.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-bnl-ten",
            "match": {"name_contains": "TEN", "venue_contains": "Big Night Live"},
            "badge": "✨ International Pop Showcase",
            "note": "Global pop superstar and dancer TEN takes the stage for an electrifying showcase tour.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-passim-maya-de-vitry",
            "match": {"name_contains": "Maya de Vitry", "venue_contains": "Passim"},
            "badge": "⭐ Folk & Roots Songwriting",
            "note": "Acclaimed songwriter and former Stray Birds member weaves poetic melodies in Harvard Sq.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-somerville-silents",
            "match": {"name_contains": "Grass: A Nation's Battle", "venue_contains": "Somerville Theatre"},
            "badge": "📽️ Live Silent Cinema with Organ",
            "note": "1925 adventure masterpiece accompanied live on the Mighty Wurlitzer theater pipe organ.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-beehive-blues-brunch",
            "match": {"name_contains": "Bruce Bears", "venue_contains": "Beehive"},
            "badge": "🍳 Sunday Blues Brunch",
            "note": "Award-winning Hammond B3 blues, eggs benedict, and mimosas in the bohemian South End.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-burren-diamond-blues",
            "match": {"name_contains": "DIAMOND BLUES", "venue_contains": "Burren"},
            "badge": "⚡ Jerry Garcia Band Tribute",
            "note": "Soulful rock-gospel-soul exploratory grooves honoring the magic of JGB.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-lilypad-jca",
            "match": {"name_contains": "Jazz Composers Alliance", "venue_contains": "Lilypad"},
            "badge": "🎷 Big Band Orchestral Jazz",
            "note": "JCA Orchestra features Boston's finest jazz composers pushing harmonic boundaries in Inman Sq.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-bebop-bluegrass-brunch",
            "match": {"name_contains": "Bluegrass Brunch", "venue_contains": "Bebop"},
            "badge": "🪕 Sunday Fiddle & Banjos",
            "note": "Free weekend bluegrass picking, breakfast skillets, and craft brews across from Berklee.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-armory-circus-up",
            "match": {"name_contains": "Circus Up", "venue_contains": "Armory"},
            "badge": "🎪 Aerial & Circus Arts",
            "note": "Jaw-dropping acrobatics, aerial silks, and community circus benefit performance in Somerville.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        },
        {
            "id": "2026-11-08-wallys-sunday",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 Sunday Night Sessions",
            "note": "The legendary South End stage keeps swinging into Monday morning with zero cover.",
            "start_date": "2026-11-08", "expires": "2026-11-08"
        }
    ],

    "2026-11-09": [
        {
            "id": "2026-11-09-sinclair-hiss-golden",
            "match": {"name_contains": "Hiss Golden Messenger", "venue_contains": "Sinclair"},
            "badge": "🌾 Folk-Rock Royalty",
            "note": "M.C. Taylor's Grammy-nominated soulful Americana and country-funk hymns in Harvard Sq.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-paradise-george-clanton",
            "match": {"name_contains": "George Clanton", "venue_contains": "Paradise Rock"},
            "badge": "🌊 Vaporwave & Electronic",
            "note": "100% Electronica pioneer brings shimmering 90s trip-hop, acid-rave synths, and wild energy to Comm Ave.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-bmh-six60",
            "match": {"name_contains": "SIX60", "venue_contains": "Brighton Music Hall"},
            "badge": "⚡ New Zealand Stadium Reggae",
            "note": "Record-shattering Kiwi stadium roots-reggae rockers deliver a rare intimate club show in Allston.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-royale-blasting-company",
            "match": {"name_contains": "Blasting Company", "venue_contains": "Royale"},
            "badge": "🎺 'Over the Garden Wall' Live",
            "note": "Beloved soundtrack creators perform whimsically macabre orchestral folk and gypsy brass.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-somerville-blues-brothers",
            "match": {"name_contains": "The Blues Brothers", "venue_contains": "Somerville Theatre"},
            "badge": "🕶️ 35mm Musical Riot",
            "note": "John Belushi and Dan Aykroyd are on a mission from God in glorious vintage 35mm film.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-jordan-stephenson",
            "match": {"name_contains": "Clayton Stephenson", "venue_contains": "Jordan Hall"},
            "badge": "🎹 Cliburn Finalist Recital",
            "note": "First Black finalist at Van Cliburn Competition performs breathtaking virtuoso piano pieces.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-berklee-jca",
            "match": {"name_contains": "Jazz Composers Alliance", "venue_contains": "Berklee"},
            "badge": "🎷 Modern Big Band Premiere",
            "note": "Large-scale contemporary jazz orchestra premiere at the prestigious Berklee Performance Center.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-passim-john-sisters",
            "match": {"name_contains": "The John Sisters", "venue_contains": "Passim"},
            "badge": "⭐ Passim Discovery Series",
            "note": "Intimate acoustic showcase spotlighting Massachusetts' brightest new folk songwriting duos.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-lilypad-bergonzi",
            "match": {"name_contains": "Jerry Bergonzi", "venue_contains": "Lilypad"},
            "badge": "🎷 Tenor Saxophone Legend",
            "note": "World-class tenor jazz master Jerry Bergonzi commands the intimate Inman Square stage.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-beehive-hoedown",
            "match": {"name_contains": "HOEDOWN", "venue_contains": "Beehive"},
            "badge": "🎻 Monday Night Hoedown",
            "note": "Raw Americana, slide guitars, and craft cocktails in the South End cellar.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-burren-trivia",
            "match": {"name_contains": "Trivia", "venue_contains": "Burren"},
            "badge": "🧠 Davis Square Pub Trivia",
            "note": "Long-running Monday pub quiz packed with locals, clever rounds, and pint prizes.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-wallys-nightly",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 South End Jazz Beacon",
            "note": "Historic Monday night jam session with zero cover charge since 1947.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-castle-island-comedy",
            "match": {"name_contains": "Brews & Laughs", "venue_contains": "Castle Island"},
            "badge": "😂 Southie Stand-Up Comedy",
            "note": "Top Boston comics, harbor drafts, and award-winning smash burgers in South Boston.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-bebop-jam",
            "match": {"name_contains": "Monday Jazz Jam", "venue_contains": "Bebop"},
            "badge": "🎶 Boylston St Jazz Jam",
            "note": "Berklee prodigies and veteran jazz heads trading hot eight-bar solos.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        },
        {
            "id": "2026-11-09-porter-pitchapalooza",
            "match": {"name_contains": "PITCHAPALOOZA", "venue_contains": "Porter Square Books"},
            "badge": "📚 'American Idol' for Authors",
            "note": "Aspiring authors pitch book concepts to top literary agents with 1 minute on the clock.",
            "start_date": "2026-11-09", "expires": "2026-11-09"
        }
    ],

    "2026-11-10": [
        {
            "id": "2026-11-10-colonial-hadestown",
            "match": {"name_contains": "Hadestown", "venue_contains": "Colonial"},
            "badge": "🎭 Tony-Winning Musical",
            "note": "Anaïs Mitchell's haunting, genre-defying underworld journey opens at Emerson Colonial Theatre.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-roadrunner-geese",
            "match": {"name_contains": "Geese", "venue_contains": "Roadrunner"},
            "badge": "⚡ Explosive Art-Punk",
            "note": "Brooklyn art-punk prodigies bring chaotic, critically acclaimed guitar riffs to Boston's premier hall.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-armory-pokey-lafarge",
            "match": {"name_contains": "Pokey LaFarge", "venue_contains": "Armory"},
            "badge": "🪕 Vintage Americana & Swing",
            "note": "Early jazz, ragtime, and folk troubadour Pokey LaFarge charms the Somerville Armory.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-sinclair-olllam",
            "match": {"name_contains": "the olllam", "venue_contains": "Sinclair"},
            "badge": "☘️ Neo-Celtic Post-Rock",
            "note": "Belfast and Detroit virtuosos fuse traditional Irish uilleann pipes with muscular jazz-rock drums.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-bmh-michigander",
            "match": {"name_contains": "Michigander", "venue_contains": "Brighton Music Hall"},
            "badge": "🎸 Emotive Indie Rock",
            "note": "Jason Singer's soaring hooks, heartfelt lyrics, and infectious indie pop-rock in Allston.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-hob-ax-hatchetmen",
            "match": {"name_contains": "Ax and the Hatchetmen", "venue_contains": "House of Blues"},
            "badge": "🎺 Brass-Infused Indie Rock",
            "note": "High-octane horns, surf guitars, and collegiate camaraderie on their Late Checkout Tour.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-middle-east-ho99o9",
            "match": {"name_contains": "Ho99o9", "venue_contains": "Middle East"},
            "badge": "⚡ Industrial Punk-Rap",
            "note": "Visceral, boundary-shredding industrial rap and hardcore punk in the storied Downstairs cellar.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-passim-kelsey-waldon",
            "match": {"name_contains": "Kelsey Waldon", "venue_contains": "Passim"},
            "badge": "⭐ John Prine Protégé",
            "note": "Kentucky-born songwriter delivers authentic, unvarnished country roots in Harvard Square.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-somerville-el-topo",
            "match": {"name_contains": "El Topo", "venue_contains": "Somerville Theatre"},
            "badge": "🎬 Acid-Western 35mm",
            "note": "Alejandro Jodorowsky's legendary 1970 midnight movie landmark in original 35mm film.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-coolidge-coen-brothers",
            "match": {"name_contains": "Coen Brothers", "venue_contains": "Coolidge"},
            "badge": "🎥 Cinema Seminar & Screening",
            "note": "Film scholar deep-dive into the crime, comedy, and chaos of Joel & Ethan Coen's early classics.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-jordan-water",
            "match": {"name_contains": "Shahzad Ismaily", "venue_contains": "Jordan Hall"},
            "badge": "🌊 Experimental Soundscapes",
            "note": "Multi-instrumentalist Shahzad Ismaily joins CMA for an immersive meditation on water.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-improv-asylum-house",
            "match": {"name_contains": "HOUSE TEAMS", "venue_contains": "Improv Asylum"},
            "badge": "😂 Tuesday Improv Brawl",
            "note": "Emerging comedy gladiators battle for laughs in Boston's North End cellar.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-aeronaut-indie-trivia",
            "match": {"name_contains": "INDIE TRIVIA", "venue_contains": "Aeronaut"},
            "badge": "🧠 Tuesday Brain Buster",
            "note": "Somerville's most popular weekly team trivia with craft IPAs and local food pop-ups.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-beehive-tuesday",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Beehive"},
            "badge": "🍸 South End Jazz Supper",
            "note": "Vibrant Tuesday night jazz rhythms, artisanal cocktails, and bohemian warmth.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        },
        {
            "id": "2026-11-10-wallys-nightly",
            "match": {"name_contains": "Live Jazz", "venue_contains": "Wally"},
            "badge": "🎺 Boston Heritage Jam",
            "note": "Zero cover, historic walls, and scorching live jazz solos late into Tuesday night.",
            "start_date": "2026-11-10", "expires": "2026-11-10"
        }
    ]
}


def main():
    if os.path.exists(HIGHLIGHTS_FILE):
        with open(HIGHLIGHTS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    # Filter out highlights on or after 2026-11-02 to replace with our clean 15-per-day curated set
    preserved = [h for h in existing if (h.get("start_date") or "") < "2026-11-02"]

    new_highlights = list(preserved)
    total_added = 0
    for day_str, items in NINE_DAYS_CURATION.items():
        assert len(items) == 15, f"Day {day_str} has {len(items)} items instead of 15"
        for item in items:
            new_highlights.append(item)
            total_added += 1

    with open(HIGHLIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_highlights, f, indent=2)

    print(f"Successfully wrote {len(new_highlights)} highlights to {HIGHLIGHTS_FILE}.")
    print(f"Preserved {len(preserved)} earlier highlights, added {total_added} fresh curated picks (15/day for 9 days).")


if __name__ == "__main__":
    main()
