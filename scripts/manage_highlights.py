#!/usr/bin/env python3
"""Manage curated highlights / sponsor events for Boston Events."""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIGHLIGHTS_FILE = os.path.join(BASE_DIR, "highlights.json")


def load_highlights():
    if not os.path.exists(HIGHLIGHTS_FILE):
        return []
    try:
        with open(HIGHLIGHTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"Error loading {HIGHLIGHTS_FILE}: {e}")
        return []


def save_highlights(highlights):
    with open(HIGHLIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(highlights, f, indent=2)
    print(f"Saved {len(highlights)} highlights to {HIGHLIGHTS_FILE}")


def clean_expired(days_grace=1):
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=days_grace)).strftime("%Y-%m-%d")
    current = load_highlights()
    kept = []
    removed = 0
    for h in current:
        exp = h.get("expires") or h.get("date") or h.get("start_date")
        if exp and exp < cutoff:
            removed += 1
        else:
            kept.append(h)
    if removed:
        save_highlights(kept)
        print(f"Cleaned {removed} expired highlights.")
    return kept


def add_highlight(name_contains, venue_contains=None, date=None, badge="✨ Editor's Pick", note=None, expires=None):
    clean_expired()
    highlights = load_highlights()
    hid = f"hl-{name_contains.lower()[:15].replace(' ', '-')}"
    if date:
        hid += f"-{date}"
    match_dict = {"name_contains": name_contains}
    if venue_contains:
        match_dict["venue_contains"] = venue_contains

    new_item = {
        "id": hid,
        "match": match_dict,
        "badge": badge or "✨ Editor's Pick",
        "note": note or "",
        "start_date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "expires": expires or ((datetime.fromisoformat(date) + timedelta(days=1)).strftime("%Y-%m-%d") if date else None),
    }

    # Replace existing or append
    replaced = False
    for i, h in enumerate(highlights):
        if h.get("id") == hid or (h.get("match") == match_dict and h.get("start_date") == new_item["start_date"]):
            highlights[i] = new_item
            replaced = True
            break
    if not replaced:
        highlights.append(new_item)

    save_highlights(highlights)
    print(f"{'Updated' if replaced else 'Added'} highlight: {badge} {name_contains}")
    return new_item


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for h in load_highlights():
            print(f"- [{h.get('badge')}] {h.get('match')} (date: {h.get('start_date')}, expires: {h.get('expires')}): {h.get('note')}")
    elif len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean_expired()
    else:
        print("Usage: python scripts/manage_highlights.py [list|clean]")
