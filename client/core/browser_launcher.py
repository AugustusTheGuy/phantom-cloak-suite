#!/usr/bin/env python3
"""
PhantomCloak — Browser Launcher
Launches Camoufox / hardened profile for the chosen location with TZ, locale,
and fingerprint injection. Opens URLs via Camoufox first, then safest fallback.
"""

import subprocess
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

PROFILES_DIR = Path(__file__).parent.parent / "profiles" / "browser"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_location_key(location: str) -> str | None:
    loc_file = PROFILES_DIR.parent / "locations.json"
    with open(loc_file) as f:
        locations = json.load(f)

    if location in locations:
        return location
    loc_lower = location.lower().replace(" ", "").replace(",", "")
    for k, v in locations.items():
        display = v.get("display_name", "").lower().replace(" ", "").replace(",", "")
        if loc_lower == k.lower() or loc_lower in display:
            return k
    return None


def _camoufox_binaries() -> list[Path]:
    candidates = [
        Path.home() / "Applications" / "Camoufox.app" / "Contents" / "MacOS" / "camoufox",
        PROJECT_ROOT / "camoufox" / "Camoufox.app" / "Contents" / "MacOS" / "camoufox",
    ]
    return [p for p in candidates if p.exists()]


def _firefox_binaries() -> list[str]:
    candidates = [
        "/Applications/Firefox.app/Contents/MacOS/firefox",
        "/Applications/Firefox Developer Edition.app/Contents/MacOS/firefox",
        shutil.which("firefox"),
    ]
    return [c for c in candidates if c and Path(c).exists()]


def _launch_browser(cmd: list, label: str) -> dict:
    print(f"Launching via {label}: {' '.join(cmd)}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "opened", "browser": label}


def launch_for_location(location: str, url: str | None = None) -> dict:
    loc_key = _resolve_location_key(location)
    if loc_key is None:
        return {"status": "error", "message": f"Unknown location: {location}"}

    loc_file = PROFILES_DIR.parent / "locations.json"
    with open(loc_file) as f:
        info = json.load(f)[loc_key]
    profile_path = PROFILES_DIR / loc_key

    print(f"Launching protected browser for {info['display_name']}")
    print(f"  Timezone: {info['tz']} | Locale: {info['locale']}")
    print(f"  Profile: {profile_path}")

    return _open_with_profile(profile_path, url)


def open_url(location: str, url: str) -> dict:
    """Open a specific URL through the protected browser stack."""
    if not url or not urlparse(url).scheme:
        return {"status": "error", "message": "Invalid URL"}
    return launch_for_location(location, url)


def _open_with_profile(profile_path: Path, url: str | None = None) -> dict:
    for camoufox in _camoufox_binaries():
        cmd = [str(camoufox), "-profile", str(profile_path)]
        if url:
            cmd.append(url)
        return _launch_browser(cmd, "Camoufox")

    for firefox in _firefox_binaries():
        cmd = [firefox, "-no-remote", "-profile", str(profile_path)]
        if url:
            cmd.append(url)
        return _launch_browser(cmd, "Firefox")

    return {"status": "error", "message": "No Camoufox or Firefox found on this device"}


if __name__ == "__main__":
    import sys
    loc = sys.argv[1] if len(sys.argv) > 1 else "vancouver"
    target_url = sys.argv[2] if len(sys.argv) > 2 else None
    result = launch_for_location(loc, target_url)
    print(result)