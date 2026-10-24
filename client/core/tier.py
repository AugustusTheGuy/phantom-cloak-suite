"""Tier configuration and feature gating for PhantomCloak Suite.

One codebase, two products: Core (consumer privacy) and Pro (prosumer).
The active tier is resolved from the verified entitlement at runtime; a
PHANTOMCLOAK_TIER env var can override for development/testing.

Only legitimate, legally-marketable capabilities are exposed here. Anything
whose value proposition is defeating platform detection/KYC/fraud systems is
intentionally NOT represented as a sellable feature.
"""
from __future__ import annotations
import os

CORE = "core"
PRO = "pro"
VALID_TIERS = (CORE, PRO)

# Both tiers share the full privacy baseline; Pro adds the professional layer.
_BASELINE = {
    "encryption", "wireguard", "post_quantum", "no_logs", "kill_switch",
    "leak_protection", "threat_blocking", "split_tunnel", "auto_connect",
    "purpose_wizard", "unlimited_devices", "zeroleak_verifier",
    "honest_billing", "leak_speed_panel", "trust_center", "streaming_resilience",
    "auto_obfuscation", "dns_blocklists", "anonymous_signup", "crypto_payments",
    "port_forwarding", "speed_accelerator", "gps_spoofing", "referrals",
}
_PRO_ONLY = {
    "multi_hop", "obfuscation", "tor_over_vpn", "dedicated_ip",
    "residential_pool", "ip_rotator", "device_mesh", "workspaces",
    "team_seats", "audit_log", "ip_health_monitor", "full_telemetry",
    "adaptive_anti_dpi", "cookie_import", "no_code_rpa", "granular_roles",
    "multi_window_sync", "bulk_pipelines", "public_api", "cloud_profiles",
}

TIER_FEATURES = {
    CORE: set(_BASELINE),
    PRO: set(_BASELINE) | set(_PRO_ONLY),
}


def normalize(tier: str | None) -> str:
    t = (tier or CORE).strip().lower()
    return t if t in VALID_TIERS else CORE


def resolve_tier(entitled_tier: str | None = None) -> str:
    """Resolve active tier: env override > entitlement > Core default."""
    return normalize(os.environ.get("PHANTOMCLOAK_TIER") or entitled_tier)


def has_feature(tier: str, feature: str) -> bool:
    return feature in TIER_FEATURES.get(normalize(tier), set())


def feature_map(tier: str) -> dict:
    """All known features -> bool, so the UI can show/lock controls."""
    all_features = _BASELINE | _PRO_ONLY
    enabled = TIER_FEATURES.get(normalize(tier), set())
    return {f: (f in enabled) for f in sorted(all_features)}


def tier_label(tier: str) -> str:
    return {"core": "PhantomCloak Core", "pro": "PhantomCloak Pro"}[normalize(tier)]
