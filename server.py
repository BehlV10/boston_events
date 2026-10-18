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


def export_json(path):
    """Run all scrapers and write a single JSON bundle for the static frontend."""
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "venues": get_all_events(force=True),
        "weather": fetch_boston_weather(),
        "luckyseat": fetch_luckyseat_boston(),
        "upvotes": _read_upvotes(),
    }
    with open(path, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    total = sum(len(v["events"]) for v in payload["venues"])
    print(f"wrote {path}: {total} events across {len(payload['venues'])} venues")


def export_html(path, force=False):
    """Render and write a static self-contained HTML page."""
    venues = get_all_events(force=force)
    html = render_page(venues)
    with open(path, "w") as f:
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
                get_all_events(force=True)
            except Exception:
                pass

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("test", "check"):
        filter_arg = sys.argv[2] if len(sys.argv) > 2 else None
        run_diagnostics(filter_arg)
    elif len(sys.argv) > 1 and sys.argv[1] == "export":
        out = sys.argv[2] if len(sys.argv) > 2 else "events.json"
        if out.endswith(".html") or (len(sys.argv) > 2 and sys.argv[2] == "html"):
            target = sys.argv[3] if len(sys.argv) > 3 else "events.html"
            export_html(target)
        else:
            export_json(out)
    else:
        _start_background_refresher()
        host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
        print(f"Boston Events → http://{host}:{PORT}")
        app.run(host=host, port=PORT, debug=False)
