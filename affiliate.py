"""Affiliate ticket links.

affiliates.json lists ticket sellers with an affiliate program. A seller whose "template" is empty
is off. Once it has your deep-link template from the affiliate network (Impact for Ticketmaster
and SeatGeek), every link to that seller on the site's pages goes through it. "{url}" in the
template is replaced by the URL-encoded ticket page.

Only the site's HTML pages are rewritten (rewrite_html is called where they're saved).
events.json, the RSS/iCal feeds and the Reddit roundup pages keep the sellers' plain links.
"""
import html
import json
import os
import re
from urllib.parse import quote, urlparse

AFFILIATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "affiliates.json")

DISCLOSURE = ("Some ticket links are affiliate links: if you buy tickets through them we may earn a "
              "small commission, at no extra cost to you.")
_OLD_FOOTER_CLAIM = "Not affiliated with any commercial ticketing broker."

_A_TAG_RE = re.compile(r"<a\b[^>]*>", re.I)
_HREF_RE = re.compile(r'\bhref="(https?://[^"]+)"', re.I)
_REL_RE = re.compile(r'\brel="([^"]*)"', re.I)


def load_sellers(path=None):
    """Sellers that are switched on: [(hosts, template)]."""
    try:
        with open(path or AFFILIATES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for s in data.get("sellers") or []:
        template = (s.get("template") or "").strip()
        hosts = tuple(h.lower().strip() for h in s.get("hosts") or [] if h.strip())
        if hosts and "{url}" in template and template.startswith("https://"):
            out.append((hosts, template))
    return out


def affiliate_url(url, sellers):
    """The affiliate link for a ticket page, or None when its seller isn't switched on."""
    host = (urlparse(url).hostname or "").lower()
    for hosts, template in sellers:
        if any(host == h or host.endswith("." + h) for h in hosts):
            return template.replace("{url}", quote(url, safe=""))
    return None


def rewrite_html(page, sellers=None):
    """Point ticket links at their affiliate links, mark them rel="sponsored", and swap the footer's
    "not affiliated" line for a disclosure when any link was changed."""
    sellers = load_sellers() if sellers is None else sellers
    if not sellers or not page:
        return page
    changed = 0

    def fix_tag(m):
        nonlocal changed
        tag = m.group(0)
        href = _HREF_RE.search(tag)
        if not href:
            return tag
        new = affiliate_url(html.unescape(href.group(1)), sellers)
        if not new:
            return tag
        changed += 1
        tag = tag[:href.start(1)] + html.escape(new, quote=True) + tag[href.end(1):]
        rel = _REL_RE.search(tag)
        if rel:
            words = rel.group(1).split()
            if "sponsored" not in words:
                tag = tag[:rel.start(1)] + " ".join(words + ["sponsored"]) + tag[rel.end(1):]
        else:
            tag = tag[:-1].rstrip("/").rstrip() + ' rel="sponsored">'
        return tag

    page = _A_TAG_RE.sub(fix_tag, page)
    if changed:
        if _OLD_FOOTER_CLAIM in page:
            page = page.replace(_OLD_FOOTER_CLAIM, DISCLOSURE)
        elif "</footer>" in page and DISCLOSURE not in page:
            page = page.replace("</footer>", f'<p class="affiliate-note">{DISCLOSURE}</p></footer>', 1)
    return page
