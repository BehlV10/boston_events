import json
import re
import subprocess
from datetime import datetime
import zoneinfo

def clean_str(s):
    if not s:
        return ""
    s = s.lower()
    s = re.sub(r'[\'\"’“”:\,\-\(\)\.\!\?\/]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

STOP_WORDS = {
    'the', 'a', 'an', 'at', 'in', 'on', 'and', 'with', 'presents', 'screening',
    'stand-up', 'live', 'show', 'tour', 'musical', 'play', 'exhibition', 'night',
    'edition', 'party', 'hall', 'center', 'theatre', 'theater', 'room'
}

def get_tokens(s):
    cleaned = clean_str(s)
    return {w for w in cleaned.split() if len(w) > 2 and w not in STOP_WORDS}

def to_boston_date(dt_str):
    if not dt_str:
        return ''
    try:
        if 'Z' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        elif '+' in dt_str or '-' in dt_str[10:]:
            dt = datetime.fromisoformat(dt_str)
        else:
            return dt_str[:10]
        boston_tz = zoneinfo.ZoneInfo('America/New_York')
        return dt.astimezone(boston_tz).strftime('%Y-%m-%d')
    except Exception:
        return dt_str[:10]

def parse_user_items():
    with open('/tmp/user_events.txt') as f:
        text = f.read()

    items = []
    current_section = 'UNKNOWN'
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if any(h in line for h in ['THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY', 'ALL WEEKEND', 'ONGOING']) and not line.startswith('['):
            current_section = line
            continue
        if line.startswith('['):
            m = re.match(r'\[(.*?)\]\((.*?)\)(.*)', line)
            if m:
                link_text = m.group(1).strip()
                url = m.group(2).strip()
                desc = m.group(3).strip()
            else:
                link_text = line
                url = ''
                desc = ''
            
            clean_text = re.sub(r'^(ALL WEEKEND\s*-\s*|Ongoing\s*-\s*|SATURDAY & SUNDAY\s*-\s*)', '', link_text, flags=re.IGNORECASE)
            parts = [p.strip() for p in clean_text.split('@')]
            title = parts[0]
            venue = parts[1] if len(parts) > 1 else ''
            time_str = parts[2] if len(parts) > 2 else ''
            
            items.append({
                'section': current_section,
                'title': title,
                'venue': venue,
                'time': time_str,
                'url': url,
                'desc': desc,
                'raw': line
            })
    return items

def load_events():
    events = []
    # Oct 29 snapshot
    try:
        out29 = subprocess.check_output(['git', 'show', 'f1c7e7d:events.json'])
        d29 = json.loads(out29)
        for v in d29.get('venues', []):
            vn = v.get('venue') or ''
            for e in v.get('events', []):
                e['_venue_name'] = vn
                e['_src'] = 'oct29'
                events.append(e)
    except Exception as e:
        print("Error loading oct29:", e)

    # Oct 31 snapshot
    try:
        out31 = subprocess.check_output(['git', 'show', '8422998:events.json'])
        d31 = json.loads(out31)
        for v in d31.get('venues', []):
            vn = v.get('venue') or ''
            for e in v.get('events', []):
                e['_venue_name'] = vn
                e['_src'] = 'oct31'
                events.append(e)
    except Exception as e:
        print("Error loading oct31:", e)

    # Current HEAD
    try:
        with open('events.json') as f:
            dh = json.load(f)
        for v in dh.get('venues', []):
            vn = v.get('venue') or ''
            for e in v.get('events', []):
                e['_venue_name'] = vn
                e['_src'] = 'head'
                events.append(e)
    except Exception as e:
        print("Error loading head:", e)

    for e in events:
        e['_boston_date'] = to_boston_date(e.get('date'))

    return events

def run_audit():
    items = parse_user_items()
    events = load_events()
    print(f"Loaded {len(items)} items from newsletter.")
    print(f"Loaded {len(events)} event records from DB snapshots.")

    results = []
    for it in items:
        it_tokens = get_tokens(it['title'])
        it_v_clean = clean_str(it['venue'])
        
        target_date = None
        if 'OCTOBER 29' in it['section']:
            target_date = '2026-10-29'
        elif 'OCTOBER 30' in it['section']:
            target_date = '2026-10-30'
        elif 'OCTOBER 31' in it['section']:
            target_date = '2026-10-31'
        elif 'NOVEMBER 1' in it['section']:
            target_date = '2026-11-01'

        matches = []
        for ev in events:
            ev_name = ev.get('name') or ''
            ev_date = ev.get('_boston_date') or ''
            ev_venue = ev.get('venue') or ev.get('_venue_name') or ''
            ev_url = ev.get('url') or ''

            date_match = False
            if target_date:
                if ev_date == target_date:
                    date_match = True
            else:
                date_match = True

            ev_tokens = get_tokens(ev_name)
            common_tokens = it_tokens.intersection(ev_tokens) if it_tokens else set()
            overlap_ratio = len(common_tokens) / max(len(it_tokens), 1)

            c_it_t = clean_str(it['title'])
            c_ev_t = clean_str(ev_name)
            substring_match = (c_it_t and c_it_t in c_ev_t) or (c_ev_t and len(c_ev_t) > 6 and c_ev_t in c_it_t)

            c_ev_v = clean_str(ev_venue)
            venue_match = False
            if it_v_clean and c_ev_v:
                venue_match = (it_v_clean in c_ev_v) or (c_ev_v in it_v_clean)
                # Specific aliases
                aliases = [
                    ('coolidge', 'coolidge'),
                    ('somerville theatre', 'somerville'),
                    ('mfa', 'fine arts'),
                    ('mfa', 'mfa'),
                    ('ica', 'contemporary art'),
                    ('ica', 'ica'),
                    ('rockwell', 'rockwell'),
                    ('sinclair', 'sinclair'),
                    ('paradise', 'paradise'),
                    ('brighton music', 'brighton'),
                    ('big night', 'big night'),
                    ('mgm', 'mgm'),
                    ('house of blues', 'house of blues'),
                    ('house of blues', 'hob'),
                    ('wilbur', 'wilbur'),
                    ('crystal ballroom', 'crystal ballroom'),
                    ('laugh boston', 'laugh'),
                    ('comedy studio', 'comedy studio'),
                    ('symphony hall', 'bso'),
                    ('symphony hall', 'symphony'),
                    ('roadrunner', 'roadrunner'),
                    ('city winery', 'city winery'),
                    ('memoire', 'memoire'),
                    ('royale', 'royale'),
                    ('the grand', 'grand'),
                    ('palladium', 'palladium'),
                    ('hanover', 'hanover'),
                    ('chevalier', 'chevalier'),
                    ('shubert', 'shubert'),
                    ('shubert', 'boch'),
                    ('colonial', 'colonial'),
                    ('emerson', 'emerson')
                ]
                for a, b in aliases:
                    if a in it_v_clean and b in c_ev_v:
                        venue_match = True
                        break

            # Match criteria
            is_match = False
            if date_match and venue_match and (overlap_ratio >= 0.35 or substring_match or len(common_tokens) >= 1):
                is_match = True
            elif date_match and (overlap_ratio >= 0.65 or (substring_match and len(c_it_t) > 8)):
                is_match = True
            elif not target_date and venue_match and (overlap_ratio >= 0.4 or substring_match):
                is_match = True

            if is_match:
                matches.append({
                    'ev_name': ev_name,
                    'ev_venue': ev_venue,
                    'ev_date': ev_date,
                    'ev_url': ev_url,
                    'overlap': overlap_ratio,
                    'venue_match': venue_match
                })

        # Deduplicate matches
        unique_matches = []
        seen = set()
        for m in matches:
            key = (m['ev_name'], m['ev_date'], m['ev_venue'])
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)

        results.append({
            'section': it['section'],
            'title': it['title'],
            'venue': it['venue'],
            'time': it['time'],
            'url': it['url'],
            'desc': it['desc'],
            'raw': it['raw'],
            'matched': unique_matches
        })

    with open('/tmp/audit_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    had = [r for r in results if r['matched']]
    missing = [r for r in results if not r['matched']]
    print(f"\nAudit Complete:")
    print(f"Total: {len(results)}")
    print(f"Had: {len(had)} ({len(had)/len(results)*100:.1f}%)")
    print(f"Missing: {len(missing)} ({len(missing)/len(results)*100:.1f}%)")

if __name__ == '__main__':
    run_audit()
