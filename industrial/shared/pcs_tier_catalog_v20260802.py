"""PCS Industrial tier catalog — new file, does not modify Suite/tier.py.

Tier 1 = PhantomCloak Core (personal privacy VPN/DSI-class)
Tier 2 = PhantomCloak Pro  (prosumer / multi-seat industrial privacy)

FTC-honest: features labeled implemented | config_needed | scaffold | not_started.
See shared/pcs_feature_matrix_v20260802.py and docs_v20260802/FEATURE_TRUTH_MATRIX_v20260802.md.
"""
from __future__ import annotations

CORE = "core"
PRO = "pro"
VALID = (CORE, PRO)

# Competitor-aligned personal baseline (Nord/Proton free-plus style + PCS edges)
CORE_FEATURES = frozenset({
    "aes256_or_wireguard_tunnel",
    "no_logs_local_first",
    "kill_switch_pf",
    "dns_leak_guard",
    "webrtc_leak_guard",
    "ipv6_leak_guard",
    "split_tunnel_policy",
    "auto_connect_on_untrusted",
    "purpose_wizard",
    "zeroleak_preflight_gate",
    "obfuscation_layers_verify",
    "tracker_vault_hide_restore",  # Google/browser tracker vault — not "reinjection"
    "dns_threat_blocklists",
    "multi_device_entitlement_core",
    "honest_billing_display",
    "speed_status_panel",
    "trust_center_docs",
    "streaming_resilience_profile",
    "auto_obfuscation_select",
    "port_forward_opt_in",
    "crypto_payment_option",
    "anonymous_account_number",
    "persistent_protection_monitor",
})

# Business / multi-account / industrial (Multilogin-class + enterprise VPN-ish)
PRO_FEATURES = CORE_FEATURES | frozenset({
    "multi_hop_double_onion",
    "dedicated_ip_option",
    "residential_exit_pool",
    "ip_health_rotator",
    "team_seats_rbac",
    "workspaces_audit_log",
    "adaptive_anti_dpi",
    "profile_cookie_import_export",
    "multi_window_profile_sync",
    "bulk_proxy_pipelines",
    "public_rest_api",
    "cloud_profile_sync_opt_in",
    "full_telemetry_self_host_opt_in",
    "granular_roles",
    "device_mesh",
    "sso_scim_scaffold",
    "compliance_export_scaffold",
    "always_on_zeroleak_watchdog",
})


def normalize(tier: str | None) -> str:
    t = (tier or CORE).strip().lower()
    return t if t in VALID else CORE


def label(tier: str) -> str:
    return {
        CORE: "PhantomCloak Core",
        PRO: "PhantomCloak Pro",
    }[normalize(tier)]


def features_for(tier: str) -> frozenset:
    return PRO_FEATURES if normalize(tier) == PRO else CORE_FEATURES


def has_feature(tier: str, feature: str) -> bool:
    return feature in features_for(tier)
