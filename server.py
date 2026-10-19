#!/usr/bin/env python3
"""Boston Events — scrape a handful of venue sites and serve a simple list at localhost:3000."""

import json
import os
import sys
from datetime import datetime, timezone

from flask import Flask, jsonify, request


def _load_dotenv():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


_load_dotenv()

from scrapers import (  # noqa: E402
    VENUES,
    get_all_events,
    _do_scrape_all,
    fetch_boston_weather,
    fetch_luckyseat_boston,
)
from template import render_page  # noqa: E402
import threading
import time


from flask import Flask, jsonify, request, send_from_directory


PORT = int(os.environ.get("PORT", 3000))

app = Flask(__name__)


UPVOTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upvotes.json")


def _read_upvotes():
    if os.path.exists(UPVOTES_FILE):
        try:
            with open(UPVOTES_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}


def _write_upvotes(data):
    try:
        with open(UPVOTES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving upvotes: {e}")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.get("/banner.jpg")
@app.get("/static/banner.jpg")
def banner_img():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "banner.jpg")


@app.get("/")
def index():
    return render_page(get_all_events(force="refresh" in request.args))


@app.get("/api/events")
def api_events():
    return jsonify(get_all_events(force="refresh" in request.args))


@app.get("/api/upvotes")
def api_get_upvotes():
    return jsonify(_read_upvotes())


@app.post("/api/upvote")
def api_post_upvote():
    body = request.get_json(silent=True) or {}
    ev_id = body.get("id")
    action = body.get("action", "add")
    if not ev_id or not isinstance(ev_id, str):
        return jsonify({"error": "Missing or invalid event id"}), 400

    data = _read_upvotes()
    current = int(data.get(ev_id, 0))
    if action == "remove":
        new_votes = max(0, current - 1)
    else:
        new_votes = current + 1

    if new_votes == 0:
        data.pop(ev_id, None)
    else:
        data[ev_id] = new_votes

    _write_upvotes(data)
    return jsonify({"success": True, "id": ev_id, "votes": new_votes})


def export_json(path="events.json", force=False):
    """Run scrapers with per-venue TTL caching and write events.json bundle."""
    force = force or (os.environ.get("FORCE_SCRAPE", "").lower() in ("1", "true"))
    venues = _do_scrape_all(force=force)
    new_total = sum(len(v["events"]) for v in venues)

    # Guard against degraded cloud scrapes (preserving existing data if scrape yields < 50% events)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as existing_file:
                existing_payload = json.load(existing_file)
            existing_venues = existing_payload.get("venues") or []
            old_total = sum(len(v.get("events", [])) for v in existing_venues)
            if new_total < old_total * 0.50 and new_total < 3000:
                print(f"Preserving existing {path} ({old_total} events) — new scrape yielded only {new_total} events (likely rate-limited)")
                return
        except Exception:
            pass

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venues": venues,
        "weather": fetch_boston_weather(),
        "luckyseat": fetch_luckyseat_boston(),
        "upvotes": _read_upvotes(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {path}: {new_total} events across {len(venues)} venues")


def export_html(path="index.html", force=False, source_json="events.json"):
    """Render and write a static self-contained HTML page."""
    venues = None
    if not force and os.path.exists(source_json):
        try:
            with open(source_json, "r", encoding="utf-8") as f:
                payload = json.load(f)
            venues = payload.get("venues") if isinstance(payload, dict) else payload
        except Exception:
            venues = None

    if not venues:
        venues = get_all_events(force=force)

    html = render_page(venues)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {path}: {len(html):,} bytes")


def run_diagnostics(filter_name=None):
    """Test all venue scrapers (or a specific venue) and report health status."""
    targets = VENUES
    if filter_name:
        targets = [v for v in VENUES if filter_name.lower() in v["name"].lower()]
        if not targets:
            print(f"No venues matched '{filter_name}'. Available: {', '.join(v['name'] for v in VENUES)}")
            return

    print(f"\n{'Venue':<44} {'Status':<9} {'Events':<8} {'Time':<8} Notes")
    print("=" * 85)
    total_events = 0
    ok_count = 0
    err_count = 0
    empty_count = 0
    t_start = time.time()

    for v in targets:
        t0 = time.time()
        try:
            evs = v["scraper"](v["url"], v["ua"])
            dur = time.time() - t0
            count = len(evs)
            total_events += count
            if count > 0:
                ok_count += 1
                status = "OK"
                note = ""
            else:
                empty_count += 1
                status = "EMPTY"
                note = "No upcoming events parsed"
        except Exception as e:
            dur = time.time() - t0
            err_count += 1
            count = 0
            status = "ERROR"
            note = str(e)[:30]

        print(f"{v['name'][:42]:<44} {status:<9} {count:<8} {dur:.2f}s   {note}")

    total_time = time.time() - t_start
    print("=" * 85)
    print(f"Summary: {ok_count} OK | {empty_count} EMPTY | {err_count} ERROR | {total_events} Events | {total_time:.1f}s Total\n")


def _start_background_refresher():
    def _loop():
        while True:
            time.sleep(30 * 60)
            try:
                get_all_events(force=False)
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("test", "check"):
        filter_arg = sys.argv[2] if len(sys.argv) > 2 else None
        run_diagnostics(filter_arg)
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        force_flag = ("--force" in sys.argv) or (os.environ.get("FORCE_SCRAPE", "").lower() in ("1", "true"))
        args = [a for a in sys.argv[2:] if a != "--force"]
        out = args[0] if args else "events.json"
        if out.endswith(".html") or (args and args[0] == "html"):
            target = args[1] if len(args) > 1 else "events.html"
            export_html(target, force=force_flag)
        else:
            export_json(out, force=force_flag)
    else:
        _start_background_refresher()
        host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
        print(f"Boston Events → http://{host}:{PORT}")
        app.run(host=host, port=PORT, debug=False)
