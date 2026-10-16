#!/usr/bin/env python3
"""Add a user-suggested venue to suggested_venues.json."""

import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUGGESTED_FILE = os.path.join(BASE_DIR, "suggested_venues.json")

VALID_CATEGORIES = {
    "music", "comedy", "dance", "theater", "stage", "art", "books",
    "food", "fitness", "community", "gaming", "clubbing", "film", "other",
}


def sanitize_string(s: str, max_len: int = 150) -> str:
    if not s:
        return ""
    cleaned = re.sub(r"<[^>]*>", "", str(s)).strip()
    return cleaned[:max_len]


def validate_and_normalize(raw: dict) -> dict:
    name = sanitize_string(raw.get("name") or raw.get("venue"), 150)
    if not name or len(name) < 2:
        raise ValueError("Venue name must be at least 2 characters")

    url = (raw.get("url") or raw.get("website") or "").strip()
    if not url:
        raise ValueError("Venue website or calendar URL is required")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    city = (raw.get("city") or "").strip().lower()
    if city not in ("boston", "cambridge", "somerville", "other"):
        city = "other"

    category = (raw.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "other"

    address = sanitize_string(raw.get("address"), 150)
    notes = sanitize_string(raw.get("notes") or raw.get("description"), 500)
    now = datetime.now(timezone.utc)

    return {
        "name": name,
        "url": url,
        "city": city,
        "category": category,
        "address": address,
        "notes": notes,
        "submitted_at": now.isoformat(),
        "status": "pending_review",
    }


def add_suggested_venue(raw_venue: dict) -> dict:
    venue = validate_and_normalize(raw_venue)

    venues = []
    if os.path.exists(SUGGESTED_FILE):
        try:
            with open(SUGGESTED_FILE) as f:
                venues = json.load(f)
            if not isinstance(venues, list):
                venues = []
        except Exception:
            venues = []

    # Check for duplicate by name or url
    v_name = venue["name"].lower()
    v_url = venue["url"].lower().rstrip("/")
    for existing in venues:
        ex_name = (existing.get("name") or "").lower()
        ex_url = (existing.get("url") or "").lower().rstrip("/")
        if ex_name == v_name or (v_url and ex_url == v_url):
            print(f"Venue '{venue['name']}' already suggested, updating record.")
            existing.update(venue)
            with open(SUGGESTED_FILE, "w") as f:
                json.dump(venues, f, indent=2)
            return existing

    venues.append(venue)
    with open(SUGGESTED_FILE, "w") as f:
        json.dump(venues, f, indent=2)

    print(f"Saved suggested venue '{venue['name']}' ({venue['url']}) to {SUGGESTED_FILE}")
    return venue


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        try:
            payload = json.loads(arg)
        except Exception:
            if os.path.exists(arg):
                with open(arg) as f:
                    payload = json.load(f)
            else:
                print(f"Error: expected JSON string or file path, got: {arg}")
                sys.exit(1)
    else:
        payload = json.load(sys.stdin)

    add_suggested_venue(payload)
