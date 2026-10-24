"""Competitor-derived feature matrix for PCS Industrial (new file).

Maps personal (Nord/Proton-style) and industrial (Multilogin / business VPN-style)
capabilities into Core vs Pro with implementation status. Does not overwrite
Suite feature_registry.py.

Status vocabulary (FTC-honest product labeling):
  implemented   — code path works for the claimed *scope* in this tree
  config_needed — code exists; operator/runtime config required before customer claim
  scaffold      — partial surface / stub; do not market as shipping
  not_started   — planned only; no product path yet

HARD RULES:
- residential catalog UI ≠ residential proxy / tunnel service
- zero-leak / protect is fail-closed until configured_count > 0
- never claim live VPS tunnel features when inventory has no real IPs
"""
from __future__ import annotations

from collections import Counter
from .pcs_tier_catalog_v20260802 import CORE, PRO, features_for

# Canonical statuses — use only these four strings
STATUS_IMPLEMENTED = "implemented"
STATUS_CONFIG_NEEDED = "config_needed"
STATUS_SCAFFOLD = "scaffold"
STATUS_NOT_STARTED = "not_started"
VALID_STATUSES = frozenset({
    STATUS_IMPLEMENTED,
    STATUS_CONFIG_NEEDED,
    STATUS_SCAFFOLD,
    STATUS_NOT_STARTED,
})

# Competitors noted for substantiation (not claims of affiliation)
MATRIX: dict[str, dict] = {
    # -------------------------------------------------------------------------
    # Core — personal / Nord–Proton-class baseline + PCS differentiators
    # -------------------------------------------------------------------------
    "aes256_or_wireguard_tunnel": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["NordVPN", "Proton VPN", "Mullvad", "Surfshark"],
        "summary": (
            "sing-box client/server packages materialize; live tunnel requires "
            "owned VPS IPs in inventory (configured_count > 0). Not ready to claim "
            "as a working exit until operator config."
        ),
        "evidence": [
            "shared/pcs_materialize_singbox_v20260802.py",
            "shared/pcs_client_singbox_v20260802.py",
            "server_vps_package_v20260802/",
        ],
    },
    "no_logs_local_first": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["Mullvad", "Proton VPN"],
        "summary": "Local-first state under ~/.pcs_industrial_20260802; no telemetry by default.",
        "evidence": ["docs_v20260802/STATE_NOTE_v20260802.md"],
    },
    "kill_switch_pf": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["NordVPN", "Proton VPN", "Surfshark"],
        "summary": (
            "pf-based kill switch under ~/.pcs_industrial_20260802/pf_rules/ "
            "(not /tmp). Auto-arms on Activate; real pf apply needs privilege/PCS_FORCE_PF."
        ),
        "evidence": ["shared/pcs_killswitch_industrial_v20260802.py"],
    },
    "dns_leak_guard": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["all major personal VPNs"],
        "summary": "Preflight DNS resolve check in zero-leak gate; fail-closed with other layers.",
        "evidence": ["shared/pcs_zeroleak_gate_v20260802.py"],
        "fail_closed": True,
    },
    "webrtc_leak_guard": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["NordVPN", "Proton VPN"],
        "summary": (
            "Layer flag + verify-bridge WebRTC guidance exist; full browser-enforced "
            "guard needs profile/browser path configured and post-connect verify."
        ),
        "evidence": ["shared/pcs_preflight_obfuscation_gate_v20260802.py", "shared/pcs_verify_bridge_v20260802.py"],
    },
    "ipv6_leak_guard": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["Mullvad", "NordVPN"],
        "summary": "IPv6 block policy intended in killswitch rules when armed; confirm on target OS before claim.",
        "evidence": ["shared/pcs_killswitch_industrial_v20260802.py"],
    },
    "split_tunnel_policy": {
        "tier": CORE,
        "status": STATUS_SCAFFOLD,
        "competitors": ["NordVPN", "Surfshark", "ExpressVPN"],
        "summary": "App/domain split routing policy surface only — not shipping.",
    },
    "auto_connect_on_untrusted": {
        "tier": CORE,
        "status": STATUS_SCAFFOLD,
        "competitors": ["NordVPN", "Proton VPN"],
        "summary": "Auto-protect on untrusted Wi-Fi — scaffold only.",
    },
    "purpose_wizard": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["PCS differentiator"],
        "summary": "Purpose → location activation wizard (Suite purpose_catalog import + shell).",
        "evidence": ["core_product/pcs_app_shell_v20260802.py"],
    },
    "zeroleak_preflight_gate": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["PCS differentiator vs typical VPN apps"],
        "summary": (
            "Fail-closed protect gate: refuses protected mode when configured_count==0 "
            "or any required enabled layer fails; trips killswitch callback. "
            "Does not claim mathematical impossibility of all side-channels."
        ),
        "evidence": [
            "shared/pcs_zeroleak_gate_v20260802.py",
            "shared/pcs_preflight_obfuscation_gate_v20260802.py",
            "shared/pcs_server_readiness_v20260802.py::gate_snapshot",
        ],
        "fail_closed": True,
        "protect_requires_configured_count_gt_0": True,
    },
    "obfuscation_layers_verify": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["Nord obfuscated servers", "Surfshark Camouflage"],
        "summary": (
            "REALITY/QUIC/ShadowTLS/ws-tls/obfs selection + preflight method check. "
            "Live transport still needs configured VPS endpoints."
        ),
        "evidence": [
            "shared/pcs_obfuscation_catalog_v20260802.py",
            "shared/pcs_preflight_obfuscation_gate_v20260802.py",
        ],
    },
    "tracker_vault_hide_restore": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["browser privacy tools; not standard VPN"],
        "summary": "On-device vault via Suite tracker_vault import: hide/restore on user action only.",
        "evidence": ["core_product/pcs_app_shell_v20260802.py"],
    },
    "dns_threat_blocklists": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["Nord Threat Protection", "Surfshark CleanWeb"],
        "summary": "DNS blocklists for ads/malware domains (Suite dns_blocklists import when Suite present).",
        "evidence": ["core_product/pcs_app_shell_v20260802.py"],
    },
    "multi_device_entitlement_core": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["NordVPN", "Proton VPN"],
        "summary": "Entitlement seats for Core plan — account/billing wiring incomplete.",
    },
    "honest_billing_display": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["FTC-aligned"],
        "summary": "Clear monthly/annual prices in pricing engine + payments surface; no absolute 'undetectable' claims.",
        "evidence": [
            "shared/pcs_pricing_engine_v20260802.py",
            "shared/pcs_payments_industrial_v20260802.py",
            "docs_v20260802/FTC_HONEST_CLAIMS_v20260802.md",
        ],
    },
    "speed_status_panel": {
        "tier": CORE,
        "status": STATUS_SCAFFOLD,
        "competitors": ["all"],
        "summary": "Latency/throughput status panel — scaffold.",
    },
    "trust_center_docs": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["Proton", "Mullvad"],
        "summary": "In-tree trust / security / state / secrets docs under docs_v20260802/.",
        "evidence": ["docs_v20260802/", "README_PCS_INDUSTRIAL.md"],
    },
    "streaming_resilience_profile": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["Nord", "ExpressVPN", "Surfshark"],
        "summary": "Purpose profile for media/streaming exits needs working exits + validation.",
    },
    "auto_obfuscation_select": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["Nord obfuscated", "Surfshark"],
        "summary": "auto_select_method under DPI/block conditions (catalog logic).",
        "evidence": ["shared/pcs_obfuscation_catalog_v20260802.py"],
    },
    "port_forward_opt_in": {
        "tier": CORE,
        "status": STATUS_SCAFFOLD,
        "competitors": ["Mullvad", "Proton"],
        "summary": "Opt-in port forwarding when server supports it — scaffold.",
    },
    "crypto_payment_option": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["Mullvad", "Proton"],
        "summary": "XMR/BTC/ETH/SOL order path in industrial payments; confirm processor/watch addresses before ads.",
        "evidence": ["shared/pcs_payments_industrial_v20260802.py"],
    },
    "anonymous_account_number": {
        "tier": CORE,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["Mullvad"],
        "summary": "Account-number signup without email — not fully productized.",
        "evidence": ["shared/pcs_account_manager_argon2_v20260802.py"],
    },
    "persistent_protection_monitor": {
        "tier": CORE,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["PCS differentiator"],
        "summary": (
            "Layer health via preflight + enabled_layers map; fail-closed trip on fail. "
            "Continuous always-on loop is stronger on Pro watchdog feature."
        ),
        "evidence": ["shared/pcs_preflight_obfuscation_gate_v20260802.py"],
        "fail_closed": True,
        "protect_requires_configured_count_gt_0": True,
    },
    # -------------------------------------------------------------------------
    # Pro — team / multi-profile / industrial
    # -------------------------------------------------------------------------
    "multi_hop_double_onion": {
        "tier": PRO,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["Proton VPN Plus", "Nord Multi-hop"],
        "summary": "Multi-hop / layered exit — needs multi-node inventory + routing config.",
    },
    "dedicated_ip_option": {
        "tier": PRO,
        "status": STATUS_NOT_STARTED,
        "competitors": ["Nord", "Surfshark", "business VPNs"],
        "summary": "Dedicated exit IP product option — not started (infra/product path missing).",
    },
    "residential_exit_pool": {
        "tier": PRO,
        "status": STATUS_CONFIG_NEEDED,
        # Dual truth: catalog UI is ready; tunnel service is not a residential proxy product
        "catalog_ui": STATUS_IMPLEMENTED,
        "tunnel_service": STATUS_CONFIG_NEEDED,
        "competitors": ["residential proxy vendors", "Multilogin stacks"],
        "summary": (
            "Catalog UI ready: synthetic residential-class product catalog "
            "(30–50 entries/country, ISP/latency metadata) for selection UX. "
            "NOT a residential proxy service. Tunnel endpoints still require owned VPS "
            "(or paid static/ISP you control) via vps_inventory.json + materialize. "
            "Catalog IPs never raise configured_count."
        ),
        "evidence": [
            "shared/pcs_residential_pool_industrial_v20260802.py",
            "docs_v20260802/RESIDENTIAL_CATALOG_v20260802.md",
            "docs_v20260802/RESIDENTIAL_IP_VS_VPS_v20260802.md",
            "core_product/pcs_app_shell_v20260802.py",
        ],
        "honest_label": "residential_catalog_ui_ready__tunnel_needs_vps",
    },
    "ip_health_rotator": {
        "tier": PRO,
        "status": STATUS_CONFIG_NEEDED,
        "competitors": ["anti-detect browser suites"],
        "summary": (
            "Catalog refresh stamps last_check (synthetic health). Real exit health "
            "rotation needs live endpoints + probes — not claimed as live proxy farm."
        ),
        "evidence": ["shared/pcs_residential_pool_industrial_v20260802.py"],
    },
    "team_seats_rbac": {
        "tier": PRO,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["business Proton", "enterprise VPN"],
        "summary": "Team seats + RBAC via Suite rbac import when Suite present.",
        "evidence": ["core_product/pcs_app_shell_v20260802.py"],
    },
    "workspaces_audit_log": {
        "tier": PRO,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["enterprise VPN", "MDM"],
        "summary": "Workspaces + audit trail (Suite industrial-adjacent surfaces).",
    },
    "adaptive_anti_dpi": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["industrial DSI tools"],
        "summary": "Adaptive anti-DPI beyond catalog auto-select — scaffold.",
    },
    "profile_cookie_import_export": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["Multilogin", "GoLogin"],
        "summary": "Cookie/profile migration (user-owned data) — scaffold.",
    },
    "multi_window_profile_sync": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["Multilogin"],
        "summary": "Synced multi-profile windows — scaffold.",
    },
    "bulk_proxy_pipelines": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["industrial proxy managers"],
        "summary": "Bulk scheduling + rotation pipelines — scaffold (not a proxy farm).",
    },
    "public_rest_api": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["enterprise VPN APIs"],
        "summary": "REST API for automation — scaffold.",
    },
    "cloud_profile_sync_opt_in": {
        "tier": PRO,
        "status": STATUS_NOT_STARTED,
        "competitors": ["Multilogin cloud"],
        "summary": "Opt-in encrypted cloud profiles — not started.",
    },
    "full_telemetry_self_host_opt_in": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["enterprise observability"],
        "summary": "Self-hosted metrics only if enabled — scaffold.",
    },
    "granular_roles": {
        "tier": PRO,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["business VPN"],
        "summary": "Fine-grained roles (Suite RBAC).",
    },
    "device_mesh": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["Tailscale-class mesh; Zero Trust"],
        "summary": "Device mesh connectivity — scaffold only.",
    },
    "sso_scim_scaffold": {
        "tier": PRO,
        "status": STATUS_NOT_STARTED,
        "competitors": ["Cloudflare Zero Trust", "Zscaler"],
        "summary": "SSO/SCIM enterprise identity — not started (name retains scaffold history).",
    },
    "compliance_export_scaffold": {
        "tier": PRO,
        "status": STATUS_SCAFFOLD,
        "competitors": ["enterprise VPN"],
        "summary": "Compliance export packs — scaffold.",
    },
    "always_on_zeroleak_watchdog": {
        "tier": PRO,
        "status": STATUS_IMPLEMENTED,
        "competitors": ["PCS differentiator"],
        "summary": (
            "Pro continuous zero-leak watchdog registration in preflight layer map; "
            "protect still fail-closed until configured_count > 0."
        ),
        "evidence": ["shared/pcs_preflight_obfuscation_gate_v20260802.py"],
        "fail_closed": True,
        "protect_requires_configured_count_gt_0": True,
    },
}


def _validate_matrix() -> None:
    for key, meta in MATRIX.items():
        st = meta.get("status")
        if st not in VALID_STATUSES:
            raise ValueError(f"{key}: invalid status {st!r}; want one of {sorted(VALID_STATUSES)}")


_validate_matrix()


def for_tier(tier: str) -> dict:
    allowed = features_for(tier)
    return {k: v for k, v in MATRIX.items() if k in allowed}


def status_counts(tier: str | None = None) -> dict:
    items = for_tier(tier) if tier else MATRIX
    return dict(Counter(v["status"] for v in items.values()))


def implemented_keys(tier: str) -> list[str]:
    return [k for k, v in for_tier(tier).items() if v["status"] == STATUS_IMPLEMENTED]


# Backward-compatible alias (old vocabulary used "live")
def live_keys(tier: str) -> list[str]:
    return implemented_keys(tier)


def fail_closed_protect_features(tier: str | None = None) -> list[str]:
    """Features that refuse protect / trip KS until layers + configured_count gate pass."""
    items = for_tier(tier) if tier else MATRIX
    return [
        k
        for k, v in items.items()
        if v.get("fail_closed") or v.get("protect_requires_configured_count_gt_0")
    ]


def residential_truth() -> dict:
    """Explicit dual-status for residential product (catalog ≠ tunnel service)."""
    meta = MATRIX["residential_exit_pool"]
    return {
        "feature": "residential_exit_pool",
        "status": meta["status"],
        "catalog_ui": meta.get("catalog_ui"),
        "tunnel_service": meta.get("tunnel_service"),
        "honest_label": meta.get("honest_label"),
        "summary": meta["summary"],
        "rule": (
            "Residential catalog UI may be marketed as selection metadata only. "
            "Never claim residential proxy service or live tunnel from catalog IPs. "
            "configured_count rises only from owned VPS (or paid endpoint you control)."
        ),
    }


def protect_gate_truth() -> dict:
    """Authoritative protect / zero-leak labeling for dashboards and campaign copy."""
    return {
        "ok_for_protect_rule": "configured_count > 0 AND all required preflight layers pass",
        "fail_closed": True,
        "when_configured_count_zero": (
            "status/dashboard/wizard allowed; protect/activate blocked; "
            "no false 'protected' session"
        ),
        "features": fail_closed_protect_features(),
        "modules": [
            "shared/pcs_server_readiness_v20260802.py::gate_snapshot",
            "shared/pcs_preflight_obfuscation_gate_v20260802.py::activate_protected_session",
            "shared/pcs_zeroleak_gate_v20260802.py",
        ],
        "honest_claim": (
            "Before a session is marked protected, required on-device checks run; "
            "if any fail (including no real VPS client configs), killswitch logic is "
            "engaged and protected mode is refused."
        ),
        "forbidden_claim": (
            "Absolute zero data can ever leave under any OS bug / undetectable forever."
        ),
    }


def as_truth_table(tier: str | None = None) -> list[dict]:
    """Flat rows for docs / dashboards."""
    items = for_tier(tier) if tier else MATRIX
    rows = []
    for key, v in sorted(items.items(), key=lambda kv: (kv[1].get("tier", ""), kv[0])):
        row = {
            "feature": key,
            "tier": v.get("tier"),
            "status": v.get("status"),
            "summary": v.get("summary"),
            "fail_closed": bool(v.get("fail_closed")),
            "protect_requires_configured_count_gt_0": bool(
                v.get("protect_requires_configured_count_gt_0")
            ),
        }
        if key == "residential_exit_pool":
            row["catalog_ui"] = v.get("catalog_ui")
            row["tunnel_service"] = v.get("tunnel_service")
            row["honest_label"] = v.get("honest_label")
        rows.append(row)
    return rows
