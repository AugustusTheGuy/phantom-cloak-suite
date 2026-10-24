"""Feature registry — single source of truth for WHAT exists, in WHICH tier,
and its REAL implementation status. Marketing/UI must treat a feature as
user-ready only when status == 'live', so we never present a control the
product can't back up (FTC substantiation + trust).

status: live | config | scaffold | infra
  live     — functional now in this codebase
  config   — config/interface present; needs backend wiring to be useful
  scaffold — interface defined; core implementation still to build
  infra    — needs server/infra or funded build; not code-only
"""
from __future__ import annotations
from collections import Counter
from . import tier as tier_mod

# key: (tier, status, summary)
FEATURES = {
    # ---- Core ----
    "kill_switch":       ("core", "live",   "Verified-before-send kill switch (zeroleak_verifier)."),
    "entitlement_gate":  ("core", "live",   "Subscription/tier gate, fail-closed."),
    "dns_blocklists":    ("core", "live",   "User-editable + community DNS blocklists (dns_blocklists.py)."),
    "referrals":         ("core", "live",   "Referral engine w/ anti-fraud + LTV controls (referrals.py)."),
    "auto_obfuscation":  ("core", "config", "Auto-select sing-box obfuscation + show active method (obfuscation.py)."),
    "anonymous_signup":  ("core", "config", "Account-number signup, no email required (needs auth backend)."),
    "crypto_payments":   ("core", "config", "Crypto payment option (needs processor integration)."),
    "port_forwarding":   ("core", "scaffold", "Configurable port forwarding (needs server support)."),
    "speed_accelerator": ("core", "scaffold", "Parallel/multipath tunnel accelerator (needs server support)."),
    "gps_spoofing":      ("core", "infra",  "Mobile GPS spoofing — mobile OS hooks; Phase 2/3."),
    # ---- Pro ----
    "granular_roles":    ("pro",  "live",   "RBAC roles/workspaces/permissions (rbac.py)."),
    "multi_hop":         ("pro",  "config", "Multi-hop routing via sing-box chains."),
    "residential_pool":  ("pro",  "config", "Residential IP pool + health/auto-replace."),
    "adaptive_anti_dpi": ("pro",  "scaffold", "Adaptive anti-DPI / anti-AI obfuscation selection."),
    "cookie_import":     ("pro",  "scaffold", "One-click cookie import / profile migration from competitors."),
    "multi_window_sync": ("pro",  "scaffold", "Synchronized multi-profile window control."),
    "bulk_pipelines":    ("pro",  "scaffold", "Bulk scheduling + proxy-rotation pipelines."),
    "public_api":        ("pro",  "scaffold", "REST API for automation/integration."),
    "no_code_rpa":       ("pro",  "infra",  "No-code record/replay automation engine."),
    "cloud_profiles":    ("pro",  "infra",  "Cloud-hosted browser profiles."),
    # ---- Platform / distribution / diskless ----
    "diskless_policy":   ("core", "live",   "Diskless-first server policy + ephemeral client (server_policy.py)."),
    "mobile_ios_bridge": ("core", "config", "iOS via sing-box config import (no dev account, $0)."),
    "mobile_android_apk":("core", "infra",  "Direct-download Android APK (native build + $25 Google verification by Sep 2026)."),
    "mobile_ios_native": ("core", "infra",  "Native iOS app (App Store, $99/yr; no global sideload)."),
}


def by_tier(tier: str) -> dict:
    t = tier_mod.normalize(tier)
    return {k: v for k, v in FEATURES.items()
            if v[0] == t or (t == "pro" and v[0] == "core")}


def status_summary() -> dict:
    return dict(Counter(v[1] for v in FEATURES.values()))


def live_features() -> list:
    return [k for k, v in FEATURES.items() if v[1] == "live"]
