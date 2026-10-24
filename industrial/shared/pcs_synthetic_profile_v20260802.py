#!/usr/bin/env python3
"""Location-consistent synthetic browser profile seeds + mimicry score.

On-device only. After wipe of trackable session residue. Not a warranty of undetectability.

Industrial use: seed Camoufox/browser dirs with locale/tz/geo aligned to the
chosen exit metro. Does **not** create third-party accounts (no Google/email
fraud). History/bookmarks stay empty or locale-template only after wipe.

Purpose-aware mimicry thresholds (fail-closed when score < threshold or wipe/IP missing)
---------------------------------------------------------------------------
| purpose                 | threshold | gate behaviour                          |
|-------------------------|-----------|-----------------------------------------|
| crypto, streaming       | 70        | high-stakes — fail-closed below 70      |
| browsing, digital_nomad,| 55        | default industrial hygiene gate         |
| other, * (unknown)      | 55        | same default                            |

pass_gate also requires wipe_done=True and a non-empty exit_ip (IPv4 dotted).
Score components (weights sum toward 100): exit_ready 25, locale_match 20,
leak_policy 25, asn_class 15, fp_complete 15. See DETECTION_SURFACE_CATALOG.

Write path: write_profile() persists seed JSON under PROFILE_DIR. App shell
status() may soft-call seed+write for the current location/purpose (hygiene
only — never invents exit IPs or claims detectability).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

STATE = Path.home() / ".pcs_industrial_20260802"
PROFILE_DIR = STATE / "synthetic_profiles"
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

# High-stakes purposes use a stricter mimicry threshold (see module docstring).
HIGH_STAKES_PURPOSES: Set[str] = {"crypto", "streaming"}
THRESHOLD_HIGH_STAKES = 70
THRESHOLD_DEFAULT = 55

# Country / location → locale pack (keys match purpose routing + inventory).
# Required industrial codes: us, gb, au, pt, es, th, mx, co, jp, fr, is, nl, ch, sg
# plus existing fleet metros (germany, dubai, …).
LOCALE_PACKS: Dict[str, Dict[str, Any]] = {
    # --- existing fleet metros ---
    "germany": {
        "tz": "Europe/Berlin",
        "locale": "de-DE",
        "languages": ["de-DE", "de", "en-US"],
        "geo": {"lat": 50.11, "lon": 8.68, "city": "Frankfurt"},
    },
    "frankfurt": {
        "tz": "Europe/Berlin",
        "locale": "de-DE",
        "languages": ["de-DE", "de", "en-US"],
        "geo": {"lat": 50.11, "lon": 8.68, "city": "Frankfurt"},
    },
    "dubai": {
        "tz": "Asia/Dubai",
        "locale": "en-AE",
        "languages": ["en-AE", "ar", "en"],
        "geo": {"lat": 25.2, "lon": 55.27, "city": "Dubai"},
    },
    "hongkong": {
        "tz": "Asia/Hong_Kong",
        "locale": "zh-HK",
        "languages": ["zh-HK", "en-HK", "en"],
        "geo": {"lat": 22.32, "lon": 114.17, "city": "Hong Kong"},
    },
    "vancouver": {
        "tz": "America/Vancouver",
        "locale": "en-CA",
        "languages": ["en-CA", "en", "fr-CA"],
        "geo": {"lat": 49.28, "lon": -123.12, "city": "Vancouver"},
    },
    "cayman": {
        "tz": "America/Cayman",
        "locale": "en-KY",
        "languages": ["en-KY", "en"],
        "geo": {"lat": 19.31, "lon": -81.25, "city": "George Town"},
    },
    "bahamas": {
        "tz": "America/Nassau",
        "locale": "en-BS",
        "languages": ["en-BS", "en"],
        "geo": {"lat": 25.05, "lon": -77.35, "city": "Nassau"},
    },
    "mauritius": {
        "tz": "Indian/Mauritius",
        "locale": "en-MU",
        "languages": ["en-MU", "fr", "en"],
        "geo": {"lat": -20.16, "lon": 57.50, "city": "Port Louis"},
    },
    "seychelles": {
        "tz": "Indian/Mahe",
        "locale": "en-SC",
        "languages": ["en-SC", "fr", "en"],
        "geo": {"lat": -4.62, "lon": 55.45, "city": "Victoria"},
    },
    "singapore": {
        "tz": "Asia/Singapore",
        "locale": "en-SG",
        "languages": ["en-SG", "zh-CN", "en"],
        "geo": {"lat": 1.35, "lon": 103.82, "city": "Singapore"},
    },
    "zurich": {
        "tz": "Europe/Zurich",
        "locale": "de-CH",
        "languages": ["de-CH", "fr-CH", "en"],
        "geo": {"lat": 47.37, "lon": 8.54, "city": "Zurich"},
    },
    # --- industrial country codes (purpose routing + Priority A/B) ---
    "us": {
        "tz": "America/New_York",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "geo": {"lat": 40.71, "lon": -74.01, "city": "New York"},
    },
    "gb": {
        "tz": "Europe/London",
        "locale": "en-GB",
        "languages": ["en-GB", "en"],
        "geo": {"lat": 51.51, "lon": -0.13, "city": "London"},
    },
    "au": {
        "tz": "Australia/Sydney",
        "locale": "en-AU",
        "languages": ["en-AU", "en"],
        "geo": {"lat": -33.87, "lon": 151.21, "city": "Sydney"},
    },
    "pt": {
        "tz": "Europe/Lisbon",
        "locale": "pt-PT",
        "languages": ["pt-PT", "pt", "en"],
        "geo": {"lat": 38.72, "lon": -9.14, "city": "Lisbon"},
    },
    "es": {
        "tz": "Europe/Madrid",
        "locale": "es-ES",
        "languages": ["es-ES", "es", "en"],
        "geo": {"lat": 40.42, "lon": -3.70, "city": "Madrid"},
    },
    "th": {
        "tz": "Asia/Bangkok",
        "locale": "th-TH",
        "languages": ["th-TH", "th", "en"],
        "geo": {"lat": 13.76, "lon": 100.50, "city": "Bangkok"},
    },
    "mx": {
        "tz": "America/Mexico_City",
        "locale": "es-MX",
        "languages": ["es-MX", "es", "en"],
        "geo": {"lat": 19.43, "lon": -99.13, "city": "Mexico City"},
    },
    "co": {
        "tz": "America/Bogota",
        "locale": "es-CO",
        "languages": ["es-CO", "es", "en"],
        "geo": {"lat": 4.71, "lon": -74.07, "city": "Bogota"},
    },
    "jp": {
        "tz": "Asia/Tokyo",
        "locale": "ja-JP",
        "languages": ["ja-JP", "ja", "en"],
        "geo": {"lat": 35.68, "lon": 139.69, "city": "Tokyo"},
    },
    "fr": {
        "tz": "Europe/Paris",
        "locale": "fr-FR",
        "languages": ["fr-FR", "fr", "en"],
        "geo": {"lat": 48.86, "lon": 2.35, "city": "Paris"},
    },
    "is": {
        "tz": "Atlantic/Reykjavik",
        "locale": "is-IS",
        "languages": ["is-IS", "is", "en"],
        "geo": {"lat": 64.15, "lon": -21.94, "city": "Reykjavik"},
    },
    "nl": {
        "tz": "Europe/Amsterdam",
        "locale": "nl-NL",
        "languages": ["nl-NL", "nl", "en"],
        "geo": {"lat": 52.37, "lon": 4.90, "city": "Amsterdam"},
    },
    "ch": {
        "tz": "Europe/Zurich",
        "locale": "de-CH",
        "languages": ["de-CH", "fr-CH", "en"],
        "geo": {"lat": 47.37, "lon": 8.54, "city": "Zurich"},
    },
    "sg": {
        "tz": "Asia/Singapore",
        "locale": "en-SG",
        "languages": ["en-SG", "zh-CN", "en"],
        "geo": {"lat": 1.35, "lon": 103.82, "city": "Singapore"},
    },
}

# Friendly aliases (same pack objects as primary keys).
_ALIAS_TO_KEY = {
    "uk": "gb",
    "usa": "us",
    "united_states": "us",
    "switzerland": "ch",
    "iceland": "is",
    "netherlands": "nl",
    "portugal": "pt",
    "spain": "es",
    "thailand": "th",
    "mexico": "mx",
    "colombia": "co",
    "japan": "jp",
    "france": "fr",
    "australia": "au",
    "ca": "vancouver",
    "de": "germany",
    "ae": "dubai",
    "hk": "hongkong",
    "ky": "cayman",
}


def threshold_for_purpose(purpose: str) -> int:
    """Return purpose-aware mimicry pass threshold."""
    p = (purpose or "browsing").strip().lower()
    if p in HIGH_STAKES_PURPOSES:
        return THRESHOLD_HIGH_STAKES
    return THRESHOLD_DEFAULT


def locale_for_location(location: str) -> Dict[str, Any]:
    key = (location or "").lower().strip().replace(" ", "_")
    if key in LOCALE_PACKS:
        return dict(LOCALE_PACKS[key])
    aliased = _ALIAS_TO_KEY.get(key)
    if aliased and aliased in LOCALE_PACKS:
        return dict(LOCALE_PACKS[aliased])
    return {
        "tz": "UTC",
        "locale": "en-US",
        "languages": ["en-US", "en"],
        "geo": {"lat": 0.0, "lon": 0.0, "city": "Unknown"},
    }


@dataclass
class MimicryBreakdown:
    exit_ready: int = 0
    locale_match: int = 0
    leak_policy: int = 0
    asn_class: int = 0
    fp_complete: int = 0

    def total(self) -> int:
        return min(100, self.exit_ready + self.locale_match + self.leak_policy + self.asn_class + self.fp_complete)


def build_profile_seed(
    location: str,
    *,
    exit_ip: str = "",
    slot_id: str = "",
    purpose: str = "browsing",
    asn_class: str = "datacenter",  # datacenter | isp | residential
    wipe_done: bool = False,
    leak_checks_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    pack = locale_for_location(location)
    seed = {
        "schema": "pcs.synthetic_profile",
        "schema_version": 1,
        "location": location,
        "slot_id": slot_id,
        "purpose": purpose,
        "exit_ip": exit_ip,
        "timezone": pack["tz"],
        "locale": pack["locale"],
        "languages": pack["languages"],
        "geolocation_policy": {
            "mode": "exit_metro",
            "latitude": pack["geo"]["lat"],
            "longitude": pack["geo"]["lon"],
            "city": pack["geo"]["city"],
        },
        "webrtc_policy": "block_non_proxied",
        "dns_policy": "tunnel_only",
        "camoufox_profile_dir": str(PROFILE_DIR / location / (slot_id or "default")),
        "wipe_required_before_use": True,
        "wipe_done": wipe_done,
        "asn_class": asn_class,
        "seeded_artifacts": {
            "bookmarks": "locale_templates_optional",
            "history": "empty_after_wipe",
            "note": "On-device only; no third-party account fraud (no Google/email account creation)",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "not_a_warranty": True,
    }
    score = score_mimicry(
        location=location,
        exit_ip=exit_ip,
        pack=pack,
        asn_class=asn_class,
        wipe_done=wipe_done,
        leak_checks_ok=leak_checks_ok,
        seed=seed,
    )
    seed["mimicry"] = score
    return seed


def score_mimicry(
    *,
    location: str,
    exit_ip: str,
    pack: Dict[str, Any],
    asn_class: str,
    wipe_done: bool,
    leak_checks_ok: Optional[bool],
    seed: Dict[str, Any],
) -> Dict[str, Any]:
    b = MimicryBreakdown()
    # exit_ready 25
    if exit_ip and exit_ip.count(".") == 3:
        b.exit_ready = 25
    # locale 20
    if pack.get("tz") and pack.get("locale") and pack.get("tz") != "UTC":
        b.locale_match = 20
    elif pack.get("tz"):
        b.locale_match = 10
    # leak 25
    if leak_checks_ok is True:
        b.leak_policy = 25
    elif leak_checks_ok is None:
        b.leak_policy = 10  # policy declared but not live-verified
    else:
        b.leak_policy = 0
    # asn 15
    b.asn_class = {"residential": 15, "isp": 12, "datacenter": 5}.get(asn_class, 5)
    # fp complete 15
    fp = 0
    if seed.get("timezone") and seed.get("locale"):
        fp += 5
    if seed.get("languages"):
        fp += 3
    if seed.get("geolocation_policy"):
        fp += 3
    if wipe_done:
        fp += 4
    b.fp_complete = min(15, fp)

    total = b.total()
    purpose = seed.get("purpose") or "browsing"
    threshold = threshold_for_purpose(str(purpose))
    return {
        "score": total,
        "threshold": threshold,
        "purpose": purpose,
        "pass_gate": total >= threshold and wipe_done and bool(exit_ip),
        "breakdown": asdict(b),
        "fail_closed_if_below": True,
        "honest_limit": "Score is operational hygiene, not a guarantee against all detectors.",
    }


def write_profile(seed: Dict[str, Any]) -> Path:
    loc = seed.get("location") or "unknown"
    slot = seed.get("slot_id") or "default"
    d = PROFILE_DIR / str(loc)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{slot}.json"
    path.write_text(json.dumps(seed, indent=2) + "\n")
    os.chmod(path, 0o600)
    return path


def seed_and_write_from_status(
    *,
    location: str,
    purpose: str = "browsing",
    exit_ip: str = "",
    slot_id: str = "status",
    asn_class: str = "datacenter",
    wipe_done: bool = False,
    leak_checks_ok: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build + persist a profile seed for app-shell status / operator hygiene.

    Never invents exit IPs. Does not create third-party accounts.
    Soft-fail callers should catch exceptions.
    """
    seed = build_profile_seed(
        location or "unknown",
        exit_ip=exit_ip or "",
        slot_id=slot_id or "status",
        purpose=purpose or "browsing",
        asn_class=asn_class,
        wipe_done=wipe_done,
        leak_checks_ok=leak_checks_ok,
    )
    path = write_profile(seed)
    gate = gate_profile(seed)
    return {
        "path": str(path),
        "location": seed.get("location"),
        "purpose": seed.get("purpose"),
        "timezone": seed.get("timezone"),
        "locale": seed.get("locale"),
        "mimicry_score": (seed.get("mimicry") or {}).get("score"),
        "threshold": (seed.get("mimicry") or {}).get("threshold"),
        "pass_gate": gate.get("ok"),
        "wipe_done": seed.get("wipe_done"),
        "exit_ip_present": bool(seed.get("exit_ip")),
        "not_a_warranty": True,
        "no_third_party_accounts": True,
        "note": "On-device seed only; no Google/email account fraud",
        "gate": gate,
    }


def gate_profile(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Return gate decision for preflight integration."""
    m = seed.get("mimicry") or {}
    ok = bool(m.get("pass_gate"))
    return {
        "ok": ok,
        "score": m.get("score", 0),
        "threshold": m.get("threshold", THRESHOLD_DEFAULT),
        "wipe_done": seed.get("wipe_done", False),
        "reason": None if ok else "synthetic_profile_gate_failed",
        "message": (
            None
            if ok
            else "Profile/exit consistency or wipe incomplete — protect blocked (fail-closed)."
        ),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--location", default="germany")
    ap.add_argument("--ip", default="")
    ap.add_argument("--purpose", default="browsing")
    ap.add_argument("--asn", default="datacenter", choices=["datacenter", "isp", "residential"])
    ap.add_argument("--wipe-done", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    seed = build_profile_seed(
        args.location,
        exit_ip=args.ip,
        purpose=args.purpose,
        asn_class=args.asn,
        wipe_done=args.wipe_done,
    )
    path = write_profile(seed)
    gate = gate_profile(seed)
    if args.json:
        print(json.dumps({"seed": seed, "path": str(path), "gate": gate}, indent=2))
    else:
        print(f"wrote {path}")
        print(f"score={seed['mimicry']['score']} pass_gate={gate['ok']}")
    return 0 if gate["ok"] or not args.ip else 0


if __name__ == "__main__":
    raise SystemExit(main())
