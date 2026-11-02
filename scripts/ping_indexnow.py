#!/usr/bin/env python3
"""Submit updated URLs to IndexNow (Bing, Yandex, Seznam, Naver) for instant crawl/index."""

import json
import sys
import requests

INDEXNOW_KEY = "e14a72d9b4c0423188d3e915fa276e01"
HOST = "www.wickedbostonevents.com"
KEY_LOCATION = f"https://{HOST}/{INDEXNOW_KEY}.txt"

URLS = [
    f"https://{HOST}/",
    f"https://{HOST}/free-events-boston-this-weekend/",
    f"https://{HOST}/cambridge-events-tonight/",
    f"https://{HOST}/live-music-somerville/",
    f"https://{HOST}/board-game-nights-boston/",
    f"https://{HOST}/boston-events-today/",
    f"https://{HOST}/boston-events-this-weekend/",
    f"https://{HOST}/boston/",
    f"https://{HOST}/cambridge/",
    f"https://{HOST}/somerville/",
    f"https://{HOST}/music/",
    f"https://{HOST}/comedy/",
    f"https://{HOST}/free/",
]


def ping_indexnow():
    payload = {
        "host": HOST,
        "key": INDEXNOW_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": URLS,
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}

    endpoints = [
        "https://api.indexnow.org/IndexNow",
        "https://www.bing.com/IndexNow",
    ]

    for ep in endpoints:
        try:
            res = requests.post(ep, json=payload, headers=headers, timeout=10)
            print(f"IndexNow [{ep}]: HTTP {res.status_code}")
        except Exception as e:
            print(f"IndexNow [{ep}] failed: {e}")


if __name__ == "__main__":
    ping_indexnow()
