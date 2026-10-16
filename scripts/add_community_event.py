#!/usr/bin/env python3
"""Add a user-submitted community event to community_events.json and update the static site."""

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

# Base directories
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMUNITY_FILE = os.path.join(BASE_DIR, "community_events.json")

VALID_CATEGORIES = {
    "music", "comedy", "dance", "theater", "stage", "art", "books",
    "food", "fitness", "community", "gaming", "clubbing", "film", "other",
}


def sanitize_string(s: str, max_len: int = 150) -> str:
    if not s:
        return ""
    # Strip HTML tags
    cleaned = re.sub(r"<[^>]*>", "", str(s)).strip()
    return cleaned[:max_len]


def validate_and_normalize(raw: dict) -> dict:
    name = sanitize_string(raw.get("name") or raw.get("title"), 150)
    if not name or len(name) < 2:
        raise ValueError("Event name must be at least 2 characters")

    venue = sanitize_string(raw.get("venue"), 150)
    if not venue or len(venue) < 2:
        raise ValueError("Venue name must be at least 2 characters")

    date_str = (raw.get("date") or "").strip()
    if not date_str:
        raise ValueError("Event date is required")

    # Validate date format (supports YYYY-MM-DD or ISO 8601)
    try:
        # If pure date (YYYY-MM-DD), parse it
        if len(date_str) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            date_iso = dt.isoformat()
        else:
            # Try ISO 8601
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            date_iso = dt.isoformat()
    except Exception as e:
        raise ValueError(f"Invalid date format '{date_str}': {e}")

    # Check if date is not too far in the past (allow within last 2 days for timezone leeway)
    now = datetime.now(timezone.utc)
    if dt < now - timedelta(days=2):
        raise ValueError(f"Event date cannot be in the past: {date_str}")

    url = (raw.get("url") or "").strip()
    if url:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"Invalid URL: {url}")

    category = (raw.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"

    price = sanitize_string(raw.get("price"), 50)
    if not price:
        price = "Free" if raw.get("is_free") else None

    city = (raw.get("city") or "").strip().lower()
    if city not in ("boston", "cambridge", "somerville", "other"):
        city = None

    address = sanitize_string(raw.get("address"), 150)
    description = sanitize_string(raw.get("description"), 500)

    return {
        "name": name,
        "venue": venue,
        "date": date_iso,
        "url": url,
        "category": category,
        "price": price,
        "city": city,
        "address": address,
        "description": description,
        "_is_community": True,
        "_source_venue": "Community Submission",
        "submitted_at": now.isoformat(),
    }


def add_event(raw_event: dict, rebuild_site: bool = True) -> dict:
    event = validate_and_normalize(raw_event)

    events = []
    if os.path.exists(COMMUNITY_FILE):
        try:
            with open(COMMUNITY_FILE) as f:
                events = json.load(f)
            if not isinstance(events, list):
                events = []
        except Exception:
            events = []

    # Filter out events older than 3 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    clean_events = []
    for e in events:
        try:
            e_dt = datetime.fromisoformat((e.get("date") or "").replace("Z", "+00:00"))
            if e_dt >= cutoff:
                clean_events.append(e)
        except Exception:
            clean_events.append(e)

    # Check for duplicate
    ev_key = (event["name"].lower(), event["venue"].lower(), event["date"][:10])
    replaced = False
    for i, e in enumerate(clean_events):
        k = ((e.get("name") or "").lower(), (e.get("venue") or "").lower(), (e.get("date") or "")[:10])
        if k == ev_key:
            clean_events[i] = event
            replaced = True
            break

    if not replaced:
        clean_events.append(event)

    # Sort by date
    clean_events.sort(key=lambda e: e.get("date") or "")

    # Save to community_events.json
    with open(COMMUNITY_FILE, "w") as f:
        json.dump(clean_events, f, indent=2)

    print(f"Saved event '{event['name']}' at '{event['venue']}' to {COMMUNITY_FILE}")

    if rebuild_site:
        rebuild()

    return event


def rebuild():
    """Trigger site re-render with the newly added event."""
    sys.path.insert(0, BASE_DIR)
    from template import render_page

    events_json_path = os.path.join(BASE_DIR, "events.json")
    if not os.path.exists(events_json_path):
        print(f"Warning: {events_json_path} not found, skipping HTML render")
        return

    with open(events_json_path) as f:
        data = json.load(f)

    venues = data.get("venues") or []

    # Import community events loader
    from scrapers import _load_community_events
    comm_venue = _load_community_events()

    # Merge or replace existing Community Submissions
    filtered_venues = [v for v in venues if v.get("venue") != "Community Submissions"]
    if comm_venue:
        filtered_venues.extend(comm_venue)

    data["venues"] = filtered_venues

    # Save updated events.json
    with open(events_json_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    # Render HTML
    html = render_page(filtered_venues)
    with open(os.path.join(BASE_DIR, "index.html"), "w") as f:
        f.write(html)
    with open(os.path.join(BASE_DIR, "events.html"), "w") as f:
        f.write(html)

    print(f"Re-rendered index.html & events.html ({len(html):,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--rebuild":
            rebuild()
            sys.exit(0)
        try:
            payload = json.loads(arg)
        except Exception:
            # Maybe path to json file
            if os.path.exists(arg):
                with open(arg) as f:
                    payload = json.load(f)
            else:
                print(f"Error: expected JSON string or file path, got: {arg}")
                sys.exit(1)
    else:
        # Read from stdin
        payload = json.load(sys.stdin)

    add_event(payload)
