#!/usr/bin/env python3
"""
Delphi Anti-Detection - Camoufox / Firefox Profile Generator
Generates realistic, location-specific browser profiles with active fingerprint injection.

This implements many methods from Categories 2 and 8 of the 300+ list:
- Timezone/Locale/Navigator consistency
- Canvas/WebGL/Audio spoofing (via prefs + Camoufox engine)
- Font lists, hardware spoofing, pointer events, etc.
- WebRTC hardening
"""

import json
import os
import random
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROFILES_DIR = BASE_DIR / "profiles" / "browser"
LOCATIONS_FILE = BASE_DIR / "profiles" / "locations.json"

# Common realistic fonts per region (simplified but effective)
FONT_SETS = {
    "vancouver": [
        "SF Pro", "Helvetica Neue", "Arial", "Menlo", "Monaco",
        "Apple Color Emoji", "PingFang SC", "Hiragino Sans GB"
    ],
    "dubai": [
        "SF Pro", "Helvetica Neue", "Arial", "Amiri", "Noto Sans Arabic",
        "DejaVu Sans", "FreeSans"
    ],
    "singapore": [
        "SF Pro", "Helvetica Neue", "Arial", "PingFang SC", "Noto Sans SC",
        "Microsoft YaHei", "DejaVu Sans"
    ],
    "zurich": [
        "SF Pro", "Helvetica Neue", "Arial", "DejaVu Sans", "Liberation Sans",
        "Noto Sans", "FreeSans"
    ]
}

# Hardware profiles that look real for the region
HARDWARE_PROFILES = {
    "vancouver": {"hardwareConcurrency": 8, "deviceMemory": 16, "platform": "MacIntel"},
    "dubai": {"hardwareConcurrency": 8, "deviceMemory": 8, "platform": "MacIntel"},
    "singapore": {"hardwareConcurrency": 12, "deviceMemory": 16, "platform": "MacIntel"},
    "zurich": {"hardwareConcurrency": 8, "deviceMemory": 16, "platform": "MacIntel"},
}

def generate_prefs_js(location_key: str, info: dict) -> str:
    hw = HARDWARE_PROFILES.get(location_key, HARDWARE_PROFILES["vancouver"])
    fonts = FONT_SETS.get(location_key, FONT_SETS["vancouver"])

    prefs = f"""// Delphi Anti-Detection - Generated profile for {info['display_name']}
// Generated: {datetime.now(timezone.utc).isoformat()}Z
// DO NOT EDIT MANUALLY - use generate_profiles.py

// === Location & Locale Consistency (Critical for Claude/Anthropic/300 methods) ===
user_pref("intl.locale.requested", "{info['locale']}");
user_pref("intl.accept_languages", "{info['locale']},en");
user_pref("calendar.timezone.local", "{info['tz']}");

// Use Camoufox's advanced spoofing instead of resistFingerprinting for believable results
user_pref("privacy.resistFingerprinting", false);
user_pref("privacy.fingerprintingProtection", false);
user_pref("privacy.fingerprintingProtection.pbmode", false);

// === Comprehensive Active Spoofing / Anti-Detection (from 300 methods) ===
// Canvas/WebGL/Audio - Camoufox engine does deep injection; these support it
user_pref("webgl.disabled", false);
user_pref("webgl.force-enabled", true);
user_pref("webgl.disable-fail-if-major-performance-caveat", true);
user_pref("webgl.renderer-string-override", "ANGLE (Apple, Apple M2, OpenGL 4.1)");
user_pref("webgl.vendor-string-override", "Apple Inc.");

// Hardware & device spoofing correlated to location/region
user_pref("dom.maxHardwareConcurrency", {hw['hardwareConcurrency']});
user_pref("dom.webaudio.enabled", true);
user_pref("media.navigator.enabled", false); // reduce media leaks

// Font control - match common fonts in the region
user_pref("font.default.x-western", "sans-serif");
user_pref("font.name-list.sans-serif.x-western", "{', '.join(fonts)}");

// WebRTC - proxy only, no local leaks (key 300 method)
user_pref("media.peerconnection.enabled", true);
user_pref("media.peerconnection.ice.default_address_only", true);
user_pref("media.peerconnection.ice.no_host", true);
user_pref("media.peerconnection.ice.tcp", false);

// === Strong Anti-Leak & Obfuscation Hardening ===
user_pref("geo.enabled", false);
user_pref("geo.provider.testing", false);
user_pref("network.proxy.type", 0);  // full system/sing-box routing
user_pref("network.trr.mode", 3);
user_pref("network.trr.uri", "https://dns.quad9.net/dns-query");
user_pref("network.trr.custom_uri", "https://dns.quad9.net/dns-query");

// Disable telemetry and fingerprintable features
user_pref("dom.battery.enabled", false);
user_pref("dom.gamepad.enabled", false);
user_pref("dom.vr.enabled", false);
user_pref("dom.enable_user_timing", false);
user_pref("dom.enable_resource_timing", false);
user_pref("media.navigator.permission.disabled", true);

// === Additional comprehensive anti-detection from 300 list ===
user_pref("network.http.referer.spoofSource", true);
user_pref("network.http.referer.XOriginPolicy", 2);
user_pref("network.http.referer.XOriginTrimmingPolicy", 2);
user_pref("privacy.donottrackheader.enabled", true);
user_pref("privacy.trackingprotection.enabled", true);

// Camoufox note: For full engine-level canvas/WebGL/font/audio spoofing that perfectly correlates with the exit IP geo and local device population, always launch this profile via Delphi's Camoufox launcher using the downloaded Camoufox.app.
"""

    return prefs

def generate_user_js(location_key: str) -> str:
    return """// user.js overrides - loaded after prefs.js
// Add any extra per-profile tweaks here if needed.
"""

def create_profile(location_key: str, info: dict):
    profile_path = PROFILES_DIR / location_key
    profile_path.mkdir(parents=True, exist_ok=True)

    # Main prefs
    (profile_path / "prefs.js").write_text(generate_prefs_js(location_key, info))

    # user.js
    (profile_path / "user.js").write_text(generate_user_js(location_key))

    # Create some realistic directories so the profile looks lived-in
    (profile_path / "chrome").mkdir(exist_ok=True)
    (profile_path / "datareporting").mkdir(exist_ok=True)

    # Add a simple README inside the profile
    (profile_path / "DELPHI_PROFILE_README.txt").write_text(
        f"Delphi Anti-Detection Profile\n"
        f"Location: {info['display_name']}\n"
        f"Timezone: {info['tz']}\n"
        f"Locale: {info['locale']}\n\n"
        f"This profile is designed for use with Camoufox or hardened Firefox.\n"
        f"Always launch via Delphi Anti-Detection tools for full protection.\n"
    )

    print(f"[+] Generated profile for {info['display_name']}: {profile_path}")

def main():
    print("=== Delphi Anti-Detection - Camoufox Profile Generator ===")

    with open(LOCATIONS_FILE) as f:
        locations = json.load(f)

    PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    for key, info in locations.items():
        create_profile(key, info)

    print("\n[✓] All location profiles generated.")
    print("    Recommended: Use Camoufox for best engine-level fingerprint injection.")
    print("    Launch with: delphi-anti-detection launch-browser --location dubai")

if __name__ == "__main__":
    main()