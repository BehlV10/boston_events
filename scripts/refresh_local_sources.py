"""Save exhibition pages that refuse GitHub's runners (the Gardner answers 403) to local_sources.json.

Run from a normal network now and then, then ship the file in a PR:
    python3 scripts/refresh_local_sources.py
Builds use this copy whenever the live fetch fails, dropping exhibitions that have closed, so a
stale file thins out rather than showing old listings.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scrapers as S  # noqa: E402


def main():
    data = S.load_local_sources()
    data.setdefault("exhibitions", {})
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    today = datetime.now(S.EASTERN).date()
    failed = 0

    for venue, page, parse in S._EXHIBITION_PAGES:
        if venue not in S.LOCAL_REFRESH_EXHIBITIONS:
            continue
        try:
            soup = S.fetch_soup(page, S.UA_CHROME)
            found = [S._exhibition(n, link, when, venue, today) for n, link, when in parse(soup, page)]
        except Exception as ex:
            print(f"{venue} exhibitions: failed ({ex}); keeping the saved copy")
            failed += 1
            continue
        data["exhibitions"][venue] = [e for e in found if e]
        print(f"{venue}: {len(data['exhibitions'][venue])} exhibitions")

    data["fetched_at"] = stamp
    with open(S.LOCAL_SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
