#!/usr/bin/env python3
"""Weekly watch over the summer camps' own pages: which camps need a person to re-check them.

Read-only: camps.json is never written. Every fact on /summer-camps is confirmed by hand from
the camp's site, so this only points at the camps worth re-reading:

  2027 posted?   the camp still shows 2026 info, and 2027 text appeared on its page after it
                 was last checked (so a "2027 Winter Warm-Up" someone already looked at stays quiet)
  changed        the camp-related text on one of its pages changed since the camp was checked
  overdue        a sign-up we expected by a month ("Mid-November 2026") that has come
  coming up      a sign-up or deadline in the next two weeks, worth re-confirming
  link           a page that's gone (404, DNS) or that refuses robots (can't be checked here)

The flags clear themselves: "2027 posted?" and "changed" once the camp's `checked` date is on or
after the day the text appeared (or its season is 2027), "overdue" once its event has a real date.
PDFs are fingerprinted as files; their text isn't read.

State (a fingerprint of each page) lives in a hidden comment in the GitHub issue the workflow
keeps, so nothing is committed. Usage:
    python3 scripts/camps_watch.py --prev prev_issue.md --out issue.md --new new_flags.md
    python3 scripts/camps_watch.py --offline            # flags that need no network only
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

STATE_RE = re.compile(r"<!-- camps-watch-state (\{.*?\}) -->", re.S)
_RELEVANT = re.compile(r"\$\s?\d|\b20\d\d\b|regist|enrol|lottery|sign[\s-]?up|session|tuition|\bfees?\b|"
                       r"\bweeks?\b|\bages?\b|grades?\b|deadline|waitlist|opens?\b", re.I)
_NOISE = re.compile(r"©|copyright|all rights reserved|cookie|\bago\b|privacy policy", re.I)
_MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                       "september", "october", "november", "december"], 1)}
_VAGUE_WHEN = re.compile(r"(?i)\b(?:early|mid|late)?[\s-]*(" + "|".join(_MONTHS) + r")\s+(20\d\d)\b")
SOON_DAYS = 14


# ---------- page text ----------

def page_lines(html):
    """The page's visible text as lines."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    lines = (re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").split("\n"))
    return [ln for ln in lines if ln]


def relevant_lines(lines):
    """Lines about prices, dates, ages and sign-ups: the facts we keep. Sorted and de-duplicated
    so a rotating banner or reordered menu doesn't count as a change."""
    return sorted({ln[:300] for ln in lines if _RELEVANT.search(ln) and not _NOISE.search(ln)})


def fingerprint(lines):
    return hashlib.sha1("\n".join(relevant_lines(lines)).encode()).hexdigest()[:12]


def mentions_2027(lines, limit=2):
    out = []
    for ln in lines:
        if re.search(r"\b2027\b", ln) and not _NOISE.search(ln) and ln not in out:
            out.append(ln if len(ln) <= 160 else ln[:157] + "…")
            if len(out) >= limit:
                break
    return out


# ---------- fetching ----------

def fetch(url):
    """(status, lines): status is "ok", "blocked" (site refuses robots), "dead" or "error"."""
    import requests
    import scrapers
    try:
        r = scrapers._SESSION.get(url, headers={"User-Agent": scrapers.UA_CHROME}, timeout=25, allow_redirects=True)
    except scrapers.SiteRefused:
        return "blocked", []
    except (requests.ConnectionError, requests.exceptions.SSLError):
        return "dead", []
    except Exception:
        return "error", []
    if r.status_code in (401, 403, 429, 999):
        return "blocked", []
    if r.status_code in (404, 410):
        return "dead", []
    if r.status_code >= 400:
        return "error", []
    if "pdf" in r.headers.get("Content-Type", "").lower() or r.content[:5] == b"%PDF-":
        return "ok", ["pdf " + hashlib.sha1(r.content).hexdigest()]  # changes when the file does
    return "ok", page_lines(r.text)


def camp_urls(camp):
    seen = []
    for u in [camp.get("url")] + list(camp.get("sources") or []):
        if u and u.startswith("http") and u not in seen:
            seen.append(u)
    return seen


# ---------- flags ----------

def date_flags(camp, today):
    """Flags that need no network: overdue month-only sign-ups and dated ones coming up."""
    flags = []
    for ev in camp.get("events") or []:
        if ev.get("season", camp.get("season")) < today.year:
            continue
        label = ev.get("label") or ev.get("kind") or "sign-up"
        if ev.get("date"):
            try:
                d = date.fromisoformat(ev["date"])
            except ValueError:
                continue
            if today <= d <= today + timedelta(days=SOON_DAYS):
                flags.append(("soon", f"{label}: {d:%a %b} {d.day} — re-confirm on the camp's site"))
        else:
            m = _VAGUE_WHEN.search(ev.get("when") or "")
            if m and (int(m.group(2)), _MONTHS[m.group(1).lower()]) <= (today.year, today.month):
                flags.append(("overdue", f"{label}: expected {ev['when']}, still no date"))
    return flags


def watch(data, pages, prev_state, today):
    """Flags per camp and the new state. pages: url -> (status, lines)."""
    prev_pages = (prev_state or {}).get("pages", {})
    state_pages = {}
    for url, (status, lines) in pages.items():
        old = prev_pages.get(url, {})
        if status != "ok":
            state_pages[url] = dict(old, status=status)
            continue
        fp = fingerprint(lines) if not lines[:1] or not lines[0].startswith("pdf ") else lines[0][4:16]
        changed_on = old.get("changed_on")
        if old.get("fp") and old["fp"] != fp:
            changed_on = today.isoformat()
        snips = mentions_2027(lines, limit=50) if not lines[0:1] or not lines[0].startswith("pdf ") else []
        y_fp = hashlib.sha1("\n".join(sorted(snips)).encode()).hexdigest()[:12] if snips else None
        y_on = old.get("y2027_on") if y_fp and y_fp == old.get("y2027") else (today.isoformat() if y_fp else None)
        st = {"fp": fp, "status": "ok"}
        if changed_on:
            st["changed_on"] = changed_on
        if y_fp:
            st.update(y2027=y_fp, y2027_on=y_on)
        state_pages[url] = st

    results = []
    for camp in data["camps"]:
        flags = []
        for url in camp_urls(camp):
            status, lines = pages.get(url, ("skipped", []))
            st = state_pages.get(url, {})
            if status in ("dead", "blocked"):
                flags.append(("link", f"{'gone' if status == 'dead' else 'refuses robots, check by hand'}: {url}"))
            if status == "ok" and camp.get("season", 0) < 2027 and st.get("y2027_on", "") > (camp.get("checked") or ""):
                for snip in mentions_2027(lines):
                    flags.append(("2027", f"“{snip}” — {url}"))
            if st.get("changed_on") and st["changed_on"] > (camp.get("checked") or ""):
                flags.append(("changed", f"changed {st['changed_on']}: {url}"))
        flags += date_flags(camp, today)
        if flags:
            results.append((camp, flags))
    return results, {"pages": state_pages}


# ---------- report ----------

_SECTIONS = [("2027", "🆕 May have posted 2027 info (still showing 2026)"),
             ("overdue", "⏰ Sign-up info expected by now"),
             ("soon", f"📅 Sign-ups and deadlines in the next {SOON_DAYS} days"),
             ("changed", "✏️ Page changed since the camp was last checked"),
             ("link", "🔗 Links to fix or check by hand")]


def flag_keys(results):
    return sorted({f"{camp['id']}:{kind}" for camp, flags in results for kind, _ in flags})


def render(results, state, today, checked_pages):
    out = [f"Weekly check of the summer camps' own pages ({today.isoformat()}, {checked_pages} pages). "
           "Re-check the camp's site, update `camps.json` (bump `checked`), and its flag clears next week. "
           "This job never edits camp data.", ""]
    if not results:
        out.append("✅ Nothing to re-check this week.")
    for kind, title in _SECTIONS:
        rows = [(c, [t for k, t in fl if k == kind]) for c, fl in results]
        rows = [(c, ts) for c, ts in rows if ts]
        if not rows:
            continue
        out += ["", f"### {title} ({len(rows)})", ""]
        for camp, texts in rows:
            out.append(f"- [ ] **{camp['name']}** (`{camp['id']}`, season {camp.get('season')}, checked {camp.get('checked')})")
            out += [f"  - {t}" for t in texts[:3]]
    state = dict(state, flags=flag_keys(results))
    out += ["", f"<!-- camps-watch-state {json.dumps(state, separators=(',', ':'), sort_keys=True)} -->"]
    return "\n".join(out) + "\n"


def render_new(results, prev_state):
    before = set((prev_state or {}).get("flags", []))
    names = {}
    for camp, flags in results:
        for kind, _ in flags:
            if f"{camp['id']}:{kind}" not in before:
                names.setdefault(dict(_SECTIONS)[kind], []).append(camp["name"])
    if not names:
        return ""
    return "New this week:\n" + "\n".join(f"- {t}: {', '.join(sorted(set(n)))}" for t, n in names.items()) + "\n"


def read_state(issue_body):
    m = STATE_RE.search(issue_body or "")
    try:
        return json.loads(m.group(1)) if m else {}
    except ValueError:
        return {}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--prev", help="last issue body (holds the saved state)")
    ap.add_argument("--out", help="write the new issue body here")
    ap.add_argument("--new", help="write a summary of flags new since last week here (empty if none)")
    ap.add_argument("--offline", action="store_true", help="don't fetch pages; date flags only")
    args = ap.parse_args(argv)

    import camps
    data = camps.load_camps()
    today = date.today()
    prev = read_state(open(args.prev, encoding="utf-8").read()) if args.prev and os.path.exists(args.prev) else {}

    pages = {}
    if not args.offline:
        urls = sorted({u for c in data["camps"] for u in camp_urls(c)})
        for i, url in enumerate(urls, 1):
            pages[url] = fetch(url)
            print(f"[{i}/{len(urls)}] {pages[url][0]:7} {url}", file=sys.stderr)

    results, state = watch(data, pages, prev, today)
    body = render(results, state, today, len(pages))
    if args.out:
        open(args.out, "w", encoding="utf-8").write(body)
    else:
        print(body)
    if args.new:
        open(args.new, "w", encoding="utf-8").write(render_new(results, prev))
    print(f"{len(results)} camps flagged", file=sys.stderr)


if __name__ == "__main__":
    main()
