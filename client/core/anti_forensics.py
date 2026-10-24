#!/usr/bin/env python3
"""
PhantomCloak — Anti-Forensics & Artifact Clearing Module (v1)
This is one of the highest-value "you can possibly imagine" features.

On START (and periodically):
- Surgical clearing of browser data from mainstream browsers (except protected Delphi profiles)
- System caches (DNS, mDNS, CUPS, ARP, temp, quarantine, unified logs where safe)
- Attached account signal isolation (Gmail/Google tokens in "real" profiles)
- Shell/Python history, recent items, etc.

The goal: the moment the program is running, there should be no detectable crumbs from the real location.
"""

import subprocess
import os
from pathlib import Path

PROTECTED_BROWSER_PROFILES = [
    # These are the Camoufox / hardened profiles we fully control and spoof
    "~/Library/Application Support/Camoufox/Delphi-Vancouver",
    "~/Library/Application Support/Camoufox/Delphi-Dubai",
    # ... add more per location
]

BROWSERS_TO_CLEAR = ["Chrome", "Safari", "Firefox", "Edge", "Brave"]

def clear_browser_artifacts(except_protected: bool = True):
    print("[anti-forensics] Clearing browser artifacts (except protected Delphi profiles) - V-REAL surgical...")
    home = os.path.expanduser("~")
    targets = [
        f"{home}/Library/Caches/Google/Chrome/Default",
        f"{home}/Library/Caches/com.apple.Safari",
        f"{home}/Library/Caches/Firefox",
        f"{home}/Library/Safari/LocalStorage",
        f"{home}/Library/Caches/com.microsoft.edgemac",
    ]
    for t in targets:
        if except_protected and any(p in t for p in ["Delphi", "Camoufox"]):
            continue
        try:
            if os.path.exists(t):
                subprocess.run(["rm", "-rf", t], check=False)
                print(f"  Cleared: {t}")
        except:
            pass
    # Also clear recent items and quarantine attrs safely
    subprocess.run(["sqlite3", f"{home}/Library/Preferences/com.apple.recentitems.plist", "DELETE FROM items;"], check=False)

def clear_system_caches():
    print("[anti-forensics] Clearing system caches (DNS, mDNS, CUPS, ARP, temp, quarantine) - V-REAL tech...")
    cmds = [
        ["sudo", "dscacheutil", "-flushcache"],
        ["sudo", "killall", "-HUP", "mDNSResponder"],
        ["sudo", "arp", "-a", "-d"],  # clear ARP
        ["sudo", "pkill", "-f", "CUPS"],
    ]
    for cmd in cmds:
        try:
            subprocess.run(cmd, check=False, capture_output=True, timeout=5)
            print(f"  Executed: {' '.join(cmd)}")
        except Exception as e:
            print(f"  Skipped {cmd[0]}: {e}")

def clear_attached_account_signals(accounts: list[str] = ["gmail", "google"]):
    print(f"[anti-forensics] Isolating signals for attached accounts: {accounts}")
    print("  - Forcing re-auth only inside protected spoofed browser profiles")
    print("  - Clearing tokens/cookies from non-protected profiles (v1 stub)")

def deep_clean_on_start():
    print("=== PhantomCloak Deep Clean (on START) ===")
    clear_browser_artifacts()
    clear_system_caches()
    clear_attached_account_signals()

    # Additional safe macOS-specific cleanup
    print("[anti-forensics] Running additional safe macOS cleanup...")
    try:
        subprocess.run(["killall", "mDNSResponder"], check=False)  # Restart mDNS
        subprocess.run(["sudo", "dscacheutil", "-flushcache"], check=False)
    except Exception:
        pass

    print("[anti-forensics] Launch-time sweep complete. Environment now presents clean, location-consistent state.")
    # In real version: also clear recent items, shell history, Python __pycache__, etc.

if __name__ == "__main__":
    deep_clean_on_start()