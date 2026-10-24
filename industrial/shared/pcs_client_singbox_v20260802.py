#!/usr/bin/env python3
"""Production-grade macOS TUN client sing-box config builder + schema self-check.

Industrial only. Used by ``pcs_materialize_singbox_v20260802``.

Caveats (always document in pending sidecars and package README):
  - TUN inbound requires root/admin (create utun/sing0, auto_route).
  - Hysteria2 industrial certs are self-signed → client uses tls.insecure=true.
  - clash_api is OFF by default (no local controller bind).
  - Private/LAN traffic bypasses proxy via route rule ip_is_private → direct.
  - No geosite/geoip databases (removed in sing-box 1.12+).
  - Never invent production VPS IPs; full client JSON only when inventory has a real IP.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# --- Public constants -----------------------------------------------------------------

SCHEMA_VERSION = 2

CLIENT_CAVEATS: List[str] = [
    "TUN inbound needs root/admin on macOS (interface create + auto_route/strict_route).",
    "Hysteria2 uses industrial self-signed certs: client tls.insecure=true (not public CA).",
    "clash_api disabled by default; enable only on loopback with a secret if needed.",
    "Private/LAN traffic bypasses proxy via route rule ip_is_private → direct.",
    "Kill-switch is separate (pf under ~/.pcs_industrial_20260802/pf_rules/), not sing-box alone.",
    "sing-box 1.12+: no geosite/geoip; sniff via route action, not inbound fields.",
]

# Location key → legacy client filename aliases (e.g. germany → frankfurt)
LOCATION_ALIASES: Dict[str, str] = {
    "germany": "frankfurt",
}

# Canonical reverse map
ALIAS_TO_LOCATION: Dict[str, str] = {v: k for k, v in LOCATION_ALIASES.items()}

PLACEHOLDER_RE = re.compile(
    r"YOUR_VPS|your-.*-vps|REPLACE_|changeme|example\.com|pending|TODO|0\.0\.0\.0|"
    r"127\.0\.0\.1|demo-uuid|placeholder",
    re.I,
)

REQUIRED_OUTBOUND_TAGS = ("proxy", "direct", "block")
TUN_INTERFACE_DEFAULT = "sing0"

# ---------------------------------------------------------------------------
# *.pending.json public surface (canonical allowlist)
# ---------------------------------------------------------------------------
# Informative sidecar only — NOT a runnable sing-box config.
# schema_version documents the pending sidecar shape (pcs.client.pending).
# NEVER include private_key, hy2_password, password, or any secret material.
#
# Writers (build_pending_sidecar / materialize pending_public_only) and
# readers (readiness _pending_public_meta) MUST filter through this allowlist.

PENDING_PUBLIC_KEYS: frozenset = frozenset(
    {
        "schema",  # "pcs.client.pending"
        "schema_version",  # int — documents pending sidecar shape version
        "location",
        "aliases",
        "status",
        "configured",
        "uuid",
        "public_key",
        "short_id",
        "sni",
        "hy2",
        "transport_http",
        "flow",
        "ports",
        "client_shape",
        "inventory_path",
        "skip_reason",
        "hint",
        "caveats",
        "not_a_singbox_config",
        "written_as",
        "alias_of",
        "schema_errors",
    }
)

# Explicit denylist — never persist or surface these in pending sidecars.
PENDING_FORBIDDEN_KEYS: frozenset = frozenset(
    {
        "private_key",
        "hy2_password",
        "obfs_password",
        "password",
        "privkey",
        "secret",
        "token",
        "api_key",
        "passphrase",
    }
)


def _is_forbidden_pending_key(key: Any) -> bool:
    """True if a key name must never appear in pending sidecars (top-level or nested)."""
    kl = str(key).lower()
    if kl in PENDING_FORBIDDEN_KEYS or kl == "password":
        return True
    if kl.endswith("_private_key") or kl.endswith("privkey"):
        return True
    # Presence flags like has_hy2_password are bools and allowed when top-level
    # allowlisted elsewhere; nested *_password string secrets are not.
    if kl.endswith("_password") and kl != "has_hy2_password":
        return True
    return False


def _scrub_nested_secrets(value: Any, depth: int = 0) -> Any:
    """Drop forbidden secret keys from nested dicts/lists inside allowlisted fields.

    Multi-IP / client_shape / ports / schema_errors must not smuggle private_key
    or passwords under an otherwise-public parent key.
    """
    if depth > 10:
        return "<max-depth>"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if _is_forbidden_pending_key(k):
                continue
            out[str(k)] = _scrub_nested_secrets(v, depth + 1)
        return out
    if isinstance(value, list):
        return [_scrub_nested_secrets(x, depth + 1) for x in value[:100]]
    return value


def filter_pending_public(obj: Any) -> Dict[str, Any]:
    """Hard allowlist: keep only PENDING_PUBLIC_KEYS; drop secrets and unknowns.

    Never returns private_key / hy2_password / password (or any forbidden key).
    Nested objects under allowlisted parents are deep-scrubbed (multi-IP harden).
    """
    if not isinstance(obj, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        ks = str(k)
        kl = ks.lower()
        if _is_forbidden_pending_key(ks) or kl.endswith("_private_key") or (
            kl.endswith("_password") and kl != "has_hy2_password"
        ):
            continue
        if ks in PENDING_PUBLIC_KEYS:
            out[ks] = _scrub_nested_secrets(v)
    return out


def pending_contains_forbidden(obj: Any, *, depth: int = 0) -> List[str]:
    """Return list of forbidden key names present (top-level + nested).

    Used by sanitize reports and multi-IP appsec tests. Paths use dotted notation
    for nested hits (e.g. client_shape.private_key).
    """
    if depth > 10:
        return []
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            if _is_forbidden_pending_key(ks):
                found.append(ks)
            for sub in pending_contains_forbidden(v, depth=depth + 1):
                found.append(f"{ks}.{sub}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj[:100]):
            for sub in pending_contains_forbidden(item, depth=depth + 1):
                found.append(f"[{i}].{sub}")
    return found


def client_config_has_reality_private_key(cfg: Any) -> bool:
    """True if a full client JSON embeds Reality private_key (must never happen).

    Client configs use public_key only; private_key belongs solely in server package
    + location_keys.json. Safe for multi-IP / multi-outbound builders to call.
    """
    if not isinstance(cfg, dict):
        return False
    blob = json.dumps(cfg)
    # structural: any tls.reality.private_key or top-level private_key
    if '"private_key"' in blob:
        return True
    return False


TUN_ADDRESS_DEFAULT = "172.19.0.1/30"
URLTEST_URL_DEFAULT = "https://www.gstatic.com/generate_204"
URLTEST_INTERVAL_DEFAULT = "3m"
CLASH_API_LISTEN_DEFAULT = "127.0.0.1:9090"


def resolve_location_name(name: str) -> str:
    """Map alias → canonical location (frankfurt → germany); identity otherwise."""
    n = (name or "").strip().lower()
    return ALIAS_TO_LOCATION.get(n, n)


def client_aliases_for(loc: str, meta: Optional[Dict[str, Any]] = None) -> List[str]:
    """Return extra client basenames for a location (germany → [frankfurt])."""
    aliases: List[str] = []
    if meta and meta.get("client_alias"):
        a = str(meta["client_alias"]).strip().lower()
        if a and a != loc:
            aliases.append(a)
    elif loc in LOCATION_ALIASES:
        aliases.append(LOCATION_ALIASES[loc])
    seen: set = set()
    out: List[str] = []
    for a in aliases:
        if a not in seen:
            seen.add(a)
            out.append(a)
    return out


def format_client_caveats(*, as_markdown: bool = False) -> str:
    if as_markdown:
        lines = ["## Client config caveats", ""]
        for c in CLIENT_CAVEATS:
            lines.append(f"- {c}")
        return "\n".join(lines) + "\n"
    return "\n".join(f"- {c}" for c in CLIENT_CAVEATS)


def uses_http_transport(meta: Dict[str, Any]) -> bool:
    """HTTP transport is Suite-legacy (dubai). Vision requires raw TCP."""
    return bool(meta.get("transport_http"))


def reality_flow(meta: Dict[str, Any]) -> Optional[str]:
    """Best-practice: xtls-rprx-vision on raw TCP Reality; omit with HTTP transport."""
    if uses_http_transport(meta):
        return None
    return "xtls-rprx-vision"


# --- Build ----------------------------------------------------------------------------


def normalize_server_ips(
    server_ip: Optional[str] = None,
    server_ips: Optional[Sequence[str]] = None,
) -> List[str]:
    """Normalize pool IPs for client build. Dedupes, strips, rejects placeholders.

    Preference: ``server_ips`` (pool) when provided and non-empty; else single ``server_ip``.
    Never invents IPs — caller must supply real public addresses from inventory.
    """
    raw: List[str] = []
    if server_ips:
        for item in server_ips:
            if item is None:
                continue
            s = str(item).strip()
            if s:
                raw.append(s)
    if not raw and server_ip is not None and str(server_ip).strip():
        raw.append(str(server_ip).strip())
    if not raw:
        raise ValueError("server_ip / server_ips required for full client config (no fake IPs)")

    seen: set = set()
    out: List[str] = []
    for ip in raw:
        if PLACEHOLDER_RE.search(ip):
            raise ValueError(f"refusing placeholder server_ip: {ip!r}")
        if ip in seen:
            continue
        seen.add(ip)
        out.append(ip)
    if not out:
        raise ValueError("server_ip / server_ips required for full client config (no fake IPs)")
    return out


def _build_reality_outbound(
    *,
    tag: str,
    server_ip: str,
    sec: Dict[str, Any],
    meta: Dict[str, Any],
) -> Dict[str, Any]:
    """Single VLESS Reality outbound (tag + server vary for multi-pool)."""
    flow = reality_flow(meta)
    reality_out: Dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": server_ip,
        "server_port": 443,
        "uuid": sec["uuid"],
        "packet_encoding": "xudp",
        # mux fights Reality/Vision fingerprinting
        "multiplex": {"enabled": False},
        "tls": {
            "enabled": True,
            "server_name": sec["sni"],
            "utls": {"enabled": True, "fingerprint": "chrome"},
            "reality": {
                "enabled": True,
                "public_key": sec["public_key"],
                "short_id": sec["short_id"],
            },
        },
    }
    if flow:
        reality_out["flow"] = flow
    if uses_http_transport(meta):
        reality_out["transport"] = {"type": "http"}
    return reality_out


def _build_hysteria_outbound(
    *,
    tag: str,
    server_ip: str,
    loc: str,
    sec: Dict[str, Any],
) -> Dict[str, Any]:
    """Single Hysteria2 outbound (industrial self-signed TLS)."""
    return {
        "type": "hysteria2",
        "tag": tag,
        "server": server_ip,
        "server_port": 8443,
        "password": sec["hy2_password"],
        "obfs": {"type": "salamander", "password": sec["obfs_password"]},
        "tls": {
            "enabled": True,
            # Matches industrial self-signed CN (ensure_hy2_tls_certs)
            "server_name": f"pcs-{loc}.local",
            "insecure": True,  # self-signed industrial certs — documented caveat
        },
    }


def build_client_config(
    loc: str,
    meta: Dict[str, Any],
    sec: Dict[str, Any],
    server_ip: str = "",
    *,
    server_ips: Optional[Sequence[str]] = None,
    enable_urltest: Optional[bool] = None,
    enable_clash_api: Optional[bool] = None,
    log_level: Optional[str] = None,
    enable_sniff: bool = True,
    enable_dns: bool = True,
    clash_api_listen: str = CLASH_API_LISTEN_DEFAULT,
    clash_api_secret: str = "",
    tun_interface: str = TUN_INTERFACE_DEFAULT,
    tun_address: str = TUN_ADDRESS_DEFAULT,
    urltest_url: str = URLTEST_URL_DEFAULT,
    urltest_interval: str = URLTEST_INTERVAL_DEFAULT,
    mtu: int = 1500,
) -> Dict[str, Any]:
    """Build a production-grade macOS TUN client config for sing-box 1.12+/1.13.

    Parameters
    ----------
    server_ip:
        Single exit IP (legacy / single-pool member). Required when ``server_ips`` omitted.
    server_ips:
        Optional multi-IP pool for one location. When len >= 2, outbounds are
        ``reality-out-1..N`` (+ ``hysteria-out-1..N`` if Hy2) with urltest + selector.
        When len == 1, keeps the classic single-IP shape (``reality-out``, optional
        ``hysteria-out``) — no numeric suffix.
    enable_urltest:
        None → auto: True when 2+ proxy outbounds (multi-transport or multi-IP pool).
    enable_clash_api:
        None → env PCS_CLASH_API in {1,true,yes,on}; default False (disabled).
    log_level:
        None → env PCS_CLIENT_LOG_LEVEL or \"warn\".
    enable_sniff:
        Safe for this stack: route action ``sniff`` (not legacy inbound sniff fields).
    """
    ips = normalize_server_ips(server_ip, server_ips)
    multi_pool = len(ips) >= 2

    log_level = (log_level or os.environ.get("PCS_CLIENT_LOG_LEVEL") or "warn").strip()
    if enable_clash_api is None:
        enable_clash_api = os.environ.get("PCS_CLASH_API", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    has_hy2 = bool(meta.get("hy2"))
    proxy_tags: List[str] = []
    transport_outbounds: List[Dict[str, Any]] = []

    if multi_pool:
        # Multi-IP pool: reality-out-1..N (+ hysteria-out-1..N when Hy2)
        for i, ip in enumerate(ips, start=1):
            r_tag = f"reality-out-{i}"
            proxy_tags.append(r_tag)
            transport_outbounds.append(
                _build_reality_outbound(tag=r_tag, server_ip=ip, sec=sec, meta=meta)
            )
        if has_hy2:
            for i, ip in enumerate(ips, start=1):
                h_tag = f"hysteria-out-{i}"
                proxy_tags.append(h_tag)
                transport_outbounds.append(
                    _build_hysteria_outbound(tag=h_tag, server_ip=ip, loc=loc, sec=sec)
                )
    else:
        # Single IP: keep current shape (reality-out / hysteria-out, no numeric suffix)
        ip = ips[0]
        proxy_tags = ["reality-out"]
        transport_outbounds = [
            _build_reality_outbound(tag="reality-out", server_ip=ip, sec=sec, meta=meta)
        ]
        if has_hy2:
            proxy_tags.append("hysteria-out")
            transport_outbounds.append(
                _build_hysteria_outbound(tag="hysteria-out", server_ip=ip, loc=loc, sec=sec)
            )

    if enable_urltest is None:
        # Auto: urltest when multiple proxy outbounds (multi-transport or multi-IP)
        enable_urltest = len(proxy_tags) >= 2
        if not enable_urltest and os.environ.get("PCS_CLIENT_URLTEST", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            enable_urltest = True

    selector_members: List[str] = []
    outbounds: List[Dict[str, Any]] = []

    if enable_urltest and proxy_tags:
        selector_members.append("auto")
        outbounds.append(
            {
                "type": "urltest",
                "tag": "auto",
                "outbounds": list(proxy_tags),
                "url": urltest_url,
                "interval": urltest_interval,
                "tolerance": 50,
            }
        )

    selector_members.extend(proxy_tags)
    # Always expose direct for manual fail-open / debugging via selector
    selector_members.append("direct")

    default_sel = "auto" if "auto" in selector_members else proxy_tags[0]
    outbounds.insert(
        0,
        {
            "type": "selector",
            "tag": "proxy",
            "outbounds": selector_members,
            "default": default_sel,
        },
    )
    outbounds.extend(transport_outbounds)
    outbounds.append({"type": "direct", "tag": "direct"})
    # Keep block outbound for explicit selector/rule targets; prefer action reject in rules
    outbounds.append({"type": "block", "tag": "block"})

    rules: List[Dict[str, Any]] = []
    if enable_sniff:
        # Safe: route action, not removed inbound sniff fields (sing-box 1.11+/1.13)
        rules.append({"action": "sniff", "timeout": "300ms"})
    if enable_dns:
        rules.append({"protocol": "dns", "action": "hijack-dns"})
    # Private IP / RFC1918 / link-local bypass (no geoip database)
    rules.append({"ip_is_private": True, "outbound": "direct"})

    route: Dict[str, Any] = {
        "rules": rules,
        "final": "proxy",
        "auto_detect_interface": True,
    }
    if enable_dns:
        # Required by sing-box 1.12+ when DNS servers present
        route["default_domain_resolver"] = "dns-local"

    cfg: Dict[str, Any] = {
        "log": {"level": log_level, "timestamp": True},
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": tun_interface,
                # sing-box 1.10+: address (not inet4_address)
                "address": [tun_address],
                "mtu": int(mtu),
                "auto_route": True,
                "strict_route": True,
                "stack": "system",
            }
        ],
        "outbounds": outbounds,
        "route": route,
    }

    if enable_dns:
        # DNS: 1.12+ typed servers. Resolve through proxy to avoid ISP DNS leaks.
        # DoH server is an IP so dialing it does not require a bootstrap domain.
        cfg["dns"] = {
            "servers": [
                {
                    "type": "https",
                    "tag": "dns-remote",
                    "server": "1.1.1.1",
                    "path": "/dns-query",
                    "detour": "proxy",
                },
                {
                    "type": "local",
                    "tag": "dns-local",
                    "detour": "direct",
                },
            ],
            "rules": [
                {"ip_is_private": True, "server": "dns-local"},
            ],
            "final": "dns-remote",
            "strategy": "prefer_ipv4",
        }

    # clash_api optional — disabled by default (no experimental block)
    if enable_clash_api:
        experimental: Dict[str, Any] = {
            "clash_api": {
                "external_controller": clash_api_listen or CLASH_API_LISTEN_DEFAULT,
            }
        }
        secret = (clash_api_secret or os.environ.get("PCS_CLASH_SECRET") or "").strip()
        if secret:
            experimental["clash_api"]["secret"] = secret
        experimental["cache_file"] = {"enabled": True, "path": "cache.db"}
        cfg["experimental"] = experimental

    # Do NOT put custom operator keys at top level — sing-box rejects unknown fields.
    return cfg


def build_pending_sidecar(
    loc: str,
    meta: Dict[str, Any],
    sec: Dict[str, Any],
    *,
    inventory_path: str,
    aliases: Optional[Sequence[str]] = None,
    skip_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Informative pending-IP sidecar (NOT a sing-box config).

    Public material only — hard allowlist PENDING_PUBLIC_KEYS (includes schema_version).
    Never private_key / hy2_password / password / obfs_password even if present in ``sec``.
    Readiness treats ``*.pending.json`` as pending_ip; full ``*.json`` only with real IP.
    """
    aliases_list = list(aliases) if aliases is not None else client_aliases_for(loc, meta)
    flow = reality_flow(meta)
    # Build only from public fields of sec — never copy private_key / hy2_password.
    raw: Dict[str, Any] = {
        "schema": "pcs.client.pending",
        "schema_version": SCHEMA_VERSION,
        "location": loc,
        "aliases": aliases_list,
        "status": "pending_vps_ip",
        "configured": False,
        "uuid": sec.get("uuid"),
        "public_key": sec.get("public_key"),
        # short_id + sni are client-public (also appear in full configs once IP is set)
        "short_id": sec.get("short_id") or meta.get("short_id"),
        "sni": sec.get("sni") or meta.get("sni"),
        "hy2": bool(meta.get("hy2")),
        "transport_http": uses_http_transport(meta),
        "flow": flow or "",
        "ports": {
            "reality_tcp": 443,
            "hysteria2_udp": 8443 if meta.get("hy2") else None,
        },
        "client_shape": {
            "selector": True,
            "urltest_auto_when_multi_transport": True,
            "multi_pool_ips": "reality-out-1..N + urltest/selector when pool has 2+ IPs",
            "single_ip_shape": "reality-out (+ hysteria-out if hy2); no numeric suffix",
            "direct_block": True,
            "ip_is_private_bypass": True,
            "clash_api_default": False,
            "sniff": "route_action",
            "tun": "address[] + auto_route + strict_route",
            "tun_requires_root": True,
            "hy2_tls_insecure": bool(meta.get("hy2")),
        },
        "inventory_path": inventory_path,
        "skip_reason": skip_reason,
        "hint": (
            f"Set locations.{loc}.ip in inventory or export PCS_VPS_{loc.upper()}=x.x.x.x "
            f"then re-run materialize. Full client JSON is written only with a real public IP."
        ),
        "caveats": list(CLIENT_CAVEATS),
        "not_a_singbox_config": True,
    }
    # Last line of defense: hard allowlist (strips any accidental secret keys).
    return filter_pending_public(raw)


# --- Schema self-check ----------------------------------------------------------------


def validate_client_config_schema(
    cfg: Dict[str, Any],
    *,
    require_real_server: bool = True,
    run_singbox_check: bool = False,
    singbox_bin: Optional[str] = None,
) -> Dict[str, Any]:
    """Structural self-check for a client full config. Used by materialize.

    Returns dict: ok, errors[], warnings[], checks{}, singbox_check (optional).
    """
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}

    def need(cond: bool, key: str, msg: str) -> None:
        checks[key] = bool(cond)
        if not cond:
            errors.append(msg)

    need(isinstance(cfg, dict), "is_object", "config must be a JSON object")
    if not isinstance(cfg, dict):
        return {"ok": False, "errors": errors, "warnings": warnings, "checks": checks}

    log = cfg.get("log") or {}
    need(isinstance(log, dict) and log.get("level"), "log_level", "log.level required")

    inbounds = cfg.get("inbounds") or []
    need(isinstance(inbounds, list) and len(inbounds) >= 1, "has_inbound", "inbounds required")
    tun = next((i for i in inbounds if isinstance(i, dict) and i.get("type") == "tun"), None)
    need(tun is not None, "has_tun", "tun inbound required")
    if tun:
        need(
            "address" in tun and isinstance(tun["address"], list) and tun["address"],
            "tun_address",
            "tun.address[] required (sing-box 1.10+; not inet4_address)",
        )
        if "inet4_address" in tun or "inet6_address" in tun:
            errors.append("legacy tun inet4_address/inet6_address removed in sing-box 1.12+")
            checks["tun_no_legacy_address"] = False
        else:
            checks["tun_no_legacy_address"] = True
        for legacy in ("sniff", "sniff_override_destination", "domain_strategy", "sniff_timeout"):
            if legacy in tun:
                errors.append(f"legacy inbound field {legacy!r} removed in sing-box 1.13+")
                checks[f"tun_no_{legacy}"] = False
            else:
                checks[f"tun_no_{legacy}"] = True
        if not tun.get("auto_route"):
            warnings.append("tun.auto_route is not true — system routes may not install")
        if not tun.get("strict_route"):
            warnings.append("tun.strict_route is not true — leak risk without kill-switch")

    outbounds = cfg.get("outbounds") or []
    need(isinstance(outbounds, list) and len(outbounds) >= 2, "has_outbounds", "outbounds required")
    tags = [o.get("tag") for o in outbounds if isinstance(o, dict)]
    types = {o.get("tag"): o.get("type") for o in outbounds if isinstance(o, dict)}

    for t in REQUIRED_OUTBOUND_TAGS:
        need(t in tags, f"tag_{t}", f"outbound tag {t!r} required")

    need(types.get("proxy") == "selector", "proxy_is_selector", "proxy must be type selector")
    need(types.get("direct") == "direct", "direct_type", "direct outbound required")
    need(types.get("block") == "block", "block_type", "block outbound required")

    sel = next((o for o in outbounds if isinstance(o, dict) and o.get("tag") == "proxy"), None)
    if sel:
        members = sel.get("outbounds") or []
        need(isinstance(members, list) and len(members) >= 1, "selector_members", "selector.outbounds empty")
        default = sel.get("default")
        if default and default not in members:
            errors.append(f"selector default {default!r} not in outbounds {members}")
            checks["selector_default"] = False
        else:
            checks["selector_default"] = True
        if "direct" not in members:
            warnings.append("selector does not include direct (manual fail-open harder)")

    urltests = [o for o in outbounds if isinstance(o, dict) and o.get("type") == "urltest"]
    checks["urltest_present"] = bool(urltests)
    for ut in urltests:
        ut_outs = ut.get("outbounds") or []
        if not ut_outs:
            errors.append(f"urltest {ut.get('tag')!r} has empty outbounds")
        for ref in ut_outs:
            if ref not in tags:
                errors.append(f"urltest references missing outbound {ref!r}")

    transports = [
        o
        for o in outbounds
        if isinstance(o, dict) and o.get("type") in ("vless", "hysteria2", "trojan", "shadowsocks")
    ]
    need(len(transports) >= 1, "has_transport", "at least one proxy transport outbound required")

    for o in transports:
        server = o.get("server") or ""
        need(bool(server), f"server_{o.get('tag')}", f"{o.get('tag')}: server required")
        if require_real_server and server:
            if PLACEHOLDER_RE.search(str(server)):
                errors.append(f"{o.get('tag')}: placeholder server not allowed")
                checks[f"real_server_{o.get('tag')}"] = False
            else:
                checks[f"real_server_{o.get('tag')}"] = True
        if o.get("type") == "vless":
            tls = o.get("tls") or {}
            need(tls.get("enabled") is True, f"vless_tls_{o.get('tag')}", "vless tls.enabled required")
            reality = tls.get("reality") or {}
            need(reality.get("enabled") is True, f"reality_{o.get('tag')}", "reality.enabled required")
            need(bool(reality.get("public_key")), f"pubkey_{o.get('tag')}", "reality.public_key required")
            need(bool(o.get("uuid")), f"uuid_{o.get('tag')}", "vless uuid required")
            mux = o.get("multiplex")
            if isinstance(mux, dict) and mux.get("enabled") is True:
                warnings.append(f"{o.get('tag')}: multiplex enabled — often hurts Reality/Vision fingerprint")
        if o.get("type") == "hysteria2":
            tls = o.get("tls") or {}
            if tls.get("insecure") is True:
                checks[f"hy2_insecure_{o.get('tag')}"] = True
                warnings.append(
                    f"{o.get('tag')}: tls.insecure=true (expected for industrial self-signed Hy2 certs)"
                )
            else:
                checks[f"hy2_insecure_{o.get('tag')}"] = False
                warnings.append(
                    f"{o.get('tag')}: tls.insecure is not true — self-signed Hy2 may fail handshake"
                )

    route = cfg.get("route") or {}
    need(isinstance(route, dict), "has_route", "route required")
    need(
        route.get("final") == "proxy" or route.get("final") in tags,
        "route_final",
        "route.final should be proxy",
    )
    rrules = route.get("rules") or []
    need(isinstance(rrules, list), "route_rules", "route.rules must be list")

    has_private = any(
        isinstance(r, dict) and r.get("ip_is_private") is True and r.get("outbound") == "direct"
        for r in rrules
    )
    need(has_private, "ip_is_private_bypass", "route rule ip_is_private → direct required")

    has_sniff_action = any(isinstance(r, dict) and r.get("action") == "sniff" for r in rrules)
    checks["sniff_via_route_action"] = has_sniff_action
    if not has_sniff_action:
        warnings.append("no route action sniff (optional but recommended for protocol detect)")

    if "dns" in cfg:
        dns = cfg["dns"] or {}
        servers = dns.get("servers") or []
        need(
            isinstance(servers, list) and len(servers) >= 1,
            "dns_servers",
            "dns.servers required when dns present",
        )
        for s in servers:
            if isinstance(s, dict) and "address" in s and "type" not in s:
                warnings.append("legacy dns server address= form; prefer type/server (sing-box 1.12+)")
        if not route.get("default_domain_resolver"):
            missing_dr = [
                o.get("tag")
                for o in transports
                if isinstance(o, dict) and not o.get("domain_resolver")
            ]
            if missing_dr:
                errors.append(
                    "dns present but missing route.default_domain_resolver "
                    f"(and transports without domain_resolver: {missing_dr})"
                )
                checks["domain_resolver"] = False
            else:
                checks["domain_resolver"] = True
        else:
            checks["domain_resolver"] = True

    exp = cfg.get("experimental") or {}
    clash = exp.get("clash_api") if isinstance(exp, dict) else None
    checks["clash_api_enabled"] = bool(clash)
    if clash:
        ctrl = str(clash.get("external_controller") or "")
        if ctrl and not (
            ctrl.startswith("127.0.0.1")
            or ctrl.startswith("localhost")
            or ctrl.startswith("[::1]")
        ):
            warnings.append(
                f"clash_api external_controller {ctrl!r} is not loopback — bind carefully"
            )
        if not clash.get("secret"):
            warnings.append("clash_api enabled without secret")
    else:
        checks["clash_api_disabled_default"] = True

    result: Dict[str, Any] = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "schema_version": SCHEMA_VERSION,
        "outbound_tags": tags,
        "caveats": list(CLIENT_CAVEATS),
    }

    if run_singbox_check:
        result["singbox_check"] = run_singbox_check_config(cfg, singbox_bin=singbox_bin)
        if not result["singbox_check"].get("ok") and not result["singbox_check"].get("skipped"):
            result["ok"] = False
            errors.append(
                "sing-box check failed: " + (result["singbox_check"].get("stderr") or "unknown")
            )
            result["errors"] = errors

    return result


def run_singbox_check_config(
    cfg: Dict[str, Any],
    *,
    singbox_bin: Optional[str] = None,
) -> Dict[str, Any]:
    """Optional: invoke ``sing-box check -c`` if binary available."""
    bin_path = singbox_bin or shutil.which("sing-box")
    if not bin_path:
        return {"ok": False, "skipped": True, "reason": "sing-box not in PATH"}
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(cfg, f, indent=2)
            path = f.name
        r = subprocess.run(
            [bin_path, "check", "-c", path],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stderr": (r.stderr or "")[:800],
            "stdout": (r.stdout or "")[:400],
            "bin": bin_path,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "bin": bin_path}


def assert_client_config_or_raise(
    cfg: Dict[str, Any],
    *,
    run_singbox_check: bool = False,
) -> Dict[str, Any]:
    report = validate_client_config_schema(cfg, run_singbox_check=run_singbox_check)
    if not report["ok"]:
        raise ValueError(
            "client config schema self-check failed: " + "; ".join(report.get("errors") or [])
        )
    return report


if __name__ == "__main__":
    demo_meta = {"hy2": True, "transport_http": True, "obfs": "x"}
    demo_sec = {
        "uuid": "00000000-0000-4000-8000-000000000001",
        "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "short_id": "a1b2c3d4",
        "sni": "www.microsoft.com",
        "hy2_password": "p" * 32,
        "obfs_password": "obfs",
    }
    # Single-IP shape (classic tags)
    c1 = build_client_config("dubai", demo_meta, demo_sec, "1.1.1.1")
    rep1 = validate_client_config_schema(c1, run_singbox_check=bool(shutil.which("sing-box")))
    # Multi-IP pool dry shape (public test IPs in memory only — no inventory write)
    multi_ips = ["1.1.1.1", "8.8.8.8", "8.8.4.4"]
    c_multi = build_client_config(
        "germany",
        {"hy2": False, "transport_http": False, "obfs": "x"},
        demo_sec,
        server_ips=multi_ips,
    )
    rep_multi = validate_client_config_schema(
        c_multi, run_singbox_check=bool(shutil.which("sing-box"))
    )
    print(
        json.dumps(
            {
                "single": rep1,
                "multi_pool": {
                    **rep_multi,
                    "pool_ips": multi_ips,
                    "outbound_tags": rep_multi.get("outbound_tags"),
                },
            },
            indent=2,
        )
    )
    ok = rep1["ok"] and rep_multi["ok"]
    raise SystemExit(0 if ok else 1)
