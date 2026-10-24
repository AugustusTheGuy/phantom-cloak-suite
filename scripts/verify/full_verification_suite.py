#!/usr/bin/env python3
"""
PhantomCloak — Full Verification Suite + Top 30 Health Harness

Runs IP/DNS/WebRTC checks and the structured Top 30 technique harness.
Use --json for machine-readable output (dashboard integration).
"""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import urllib.request

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

CHECKERS = {
    "ipify": "https://api.ipify.org?format=json",
    "ipinfo": "https://ipinfo.io/json",
    "ifconfig": "https://ifconfig.me/all.json",
}

DNS_TEST_DOMAINS = ["dnsleaktest.com", "whoami.akamai.net", "ipleak.net"]


def check_ip_leaks():
    print("\n=== IP Leak Detection ===")
    results = {}

    def fetch(name, url):
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                data = json.loads(response.read().decode())
                return name, data
        except Exception as e:
            return name, {"error": str(e)}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(fetch, name, url) for name, url in CHECKERS.items()]
        for future in futures:
            name, data = future.result()
            results[name] = data
            if "error" in data:
                print(f"  {name}: ERROR - {data['error']}")
            else:
                ip = data.get("ip", data.get("query", "N/A"))
                print(f"  {name}: {ip}")

    print("\n[IMPORTANT] All reported IPs should match your chosen exit location.")
    print("If any shows your real residential ISP IP, the kill switch or routing has failed.")
    return results


def check_dns_leaks():
    print("\n=== DNS Leak Detection ===")
    for domain in DNS_TEST_DOMAINS:
        try:
            result = subprocess.run(["dig", "+short", domain], capture_output=True, text=True, timeout=5)
            print(f"  {domain}: {result.stdout.strip()[:80]}")
        except Exception:
            print(f"  {domain}: dig not available or failed")


def check_webrtc():
    print("\n=== WebRTC Leak Check ===")
    print("Open the protected browser profile and visit: https://browserleaks.com/webrtc")
    print("Expected: WebRTC disabled or only VPN exit IP visible.")


def check_browser_fingerprint():
    print("\n=== Browser Fingerprinting & Mimicry ===")
    print("Visit creepjs.com and browserleaks.com in the Camoufox profile.")
    print("Fingerprints should match a normal resident of your chosen city.")


def check_mimicry_quality():
    print("\n=== Traffic Mimicry Quality ===")
    print("Capture traffic with Wireshark/tcpdump and compare TLS/QUIC to residential norms.")


def run_health_harness(as_json: bool = False):
    from client.core.health_harness import run_harness

    print("\n=== Top 30 Technique Health Harness ===")
    panel = run_harness(app=None, as_json=as_json)
    if not as_json:
        c = panel.get("counts", {})
        print(f"  Overall: {panel.get('overall', 'unknown').upper()}")
        print(f"  Green: {c.get('green', 0)}  Yellow: {c.get('yellow', 0)}  Red: {c.get('red', 0)}  Idle: {c.get('idle', 0)}")
        for t in panel.get("techniques", []):
            mark = {"green": "✓", "yellow": "!", "red": "✗", "idle": "·"}.get(t["status"], "?")
            print(f"  [{mark}] {t['num']:2}. {t['name']}: {t['reason']}")
    return panel


def main():
    parser = argparse.ArgumentParser(description="PhantomCloak verification suite")
    parser.add_argument("--json", action="store_true", help="Output health harness as JSON")
    parser.add_argument("--harness-only", action="store_true", help="Run only the Top 30 harness")
    args = parser.parse_args()

    if args.harness_only:
        run_health_harness(as_json=args.json)
        return

    print("=== PhantomCloak Full Verification Suite ===")
    print("Validates leaks + Top 30 technique health.\n")

    ip_results = check_ip_leaks()
    check_dns_leaks()
    check_webrtc()
    check_browser_fingerprint()
    check_mimicry_quality()
    panel = run_health_harness(as_json=args.json)

    if args.json:
        print(json.dumps({"ip_checks": ip_results, "health_panel": panel}, indent=2))
    else:
        print("\n" + "=" * 60)
        print("VERIFICATION COMPLETE")
        print("Combine with the dashboard health panel for ongoing Top 30 monitoring.")


if __name__ == "__main__":
    main()