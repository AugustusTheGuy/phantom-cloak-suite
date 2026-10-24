#!/usr/bin/env python3
"""
Delphi Anti-Detection Verification Suite
Checks for leaks and validates mimicry quality.
"""

import requests
import sys
from concurrent.futures import ThreadPoolExecutor

CHECKERS = [
    "https://api.ipify.org?format=json",
    "https://ifconfig.me/all.json",
    "https://ipinfo.io/json",
]

def check_ip():
    results = []
    def fetch(url):
        try:
            r = requests.get(url, timeout=8)
            return url, r.json() if 'json' in url else r.text
        except Exception as e:
            return url, str(e)

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(fetch, CHECKERS))

    print("=== IP / Leak Verification ===")
    for url, data in results:
        print(f"{url}: {data}")
    print("\nIf any result shows your real residential IP, the kill switch has failed.")

if __name__ == "__main__":
    check_ip()
    print("\nFor full browser fingerprint verification, open https://browserleaks.com and https://creepjs.com inside the protected profile.")