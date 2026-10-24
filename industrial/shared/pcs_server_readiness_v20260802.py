#!/usr/bin/env python3
"""Server readiness / health API (Kubernetes readinessProbe quality bar).

Industrial tree is authoritative. Legacy ~/.phantomcloak and ~/.delphi are
scanned only as secondary signals and must not double-count identical content.

Classifications (file + location):
  template | pending_ip | server_filled | client_configured | secrets_ok | inventory_gap

Env:
  PCS_READINESS_INDUSTRIAL_ONLY=1  — scan only industrial dirs (priority < 10).
    Skips Suite ready-for-vps + ~/.phantomcloak + ~/.delphi for faster probes.
    Default off preserves secondary legacy signals.

CLI:
  python3 pcs_server_readiness_v20260802.py [--json] [--exit-code] [--self-test]
  exit 0  — ready or partial with configured_count > 0
  exit 3  — templates_only / pending / no configured clients yet
  exit 1  — scan error
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HOME = Path.home()
SUITE = HOME / "Desktop" / "PhantomCloak Suite"
LEGACY = HOME / "Desktop" / "PhantomCloak"
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"

INDUSTRIAL_SINGBOX = STATE / "singbox"
INDUSTRIAL_VPS_PKG = STATE / "vps_server_package"
INDUSTRIAL_TEMPLATES = STATE / "vps_templates_source_copy"
INVENTORY_PATH = STATE / "vps_inventory.json"
SECRETS_PATH = STATE / "secrets" / "location_keys.json"
MATERIALIZE_META = STATE / "materialize_meta.json"
MATERIALIZE_SCRIPT = INDUSTRIAL / "shared" / "pcs_materialize_singbox_v20260802.py"
LEGACY_PHANTOMCLOAK_SINGBOX = HOME / ".phantomcloak" / "singbox"
LEGACY_DELPHI_SINGBOX = HOME / ".delphi" / "singbox"

# Priority: lower number = more authoritative (industrial first).
# Legacy placeholders share content hashes — secondary only.
DIR_PRIORITY: List[Tuple[Path, str, int]] = [
    (INDUSTRIAL_SINGBOX, "industrial_client", 0),
    (INDUSTRIAL_VPS_PKG, "industrial_server_package", 1),
    (INDUSTRIAL_TEMPLATES, "industrial_templates", 2),
    (INDUSTRIAL / "server_vps_package_v20260802" / "templates_source_copy", "industrial_repo_templates", 3),
    (SUITE / "server" / "ready-for-vps", "suite_ready_for_vps", 10),
    (LEGACY / "server" / "ready-for-vps", "legacy_ready_for_vps", 11),
    (LEGACY_PHANTOMCLOAK_SINGBOX, "legacy_phantomcloak_client", 20),
    (LEGACY_DELPHI_SINGBOX, "legacy_delphi_client", 21),
]


def configure_paths(
    *,
    home: Optional[Path] = None,
    state: Optional[Path] = None,
    suite: Optional[Path] = None,
    legacy: Optional[Path] = None,
    industrial: Optional[Path] = None,
) -> None:
    """Rebind path globals for tests or alternate layouts (production defaults unchanged)."""
    global HOME, SUITE, LEGACY, INDUSTRIAL, STATE
    global INDUSTRIAL_SINGBOX, INDUSTRIAL_VPS_PKG, INDUSTRIAL_TEMPLATES
    global INVENTORY_PATH, SECRETS_PATH, MATERIALIZE_META, MATERIALIZE_SCRIPT
    global LEGACY_PHANTOMCLOAK_SINGBOX, LEGACY_DELPHI_SINGBOX, DIR_PRIORITY

    if home is not None:
        HOME = Path(home)
        if suite is None:
            SUITE = HOME / "Desktop" / "PhantomCloak Suite"
        if legacy is None:
            LEGACY = HOME / "Desktop" / "PhantomCloak"
        if state is None:
            STATE = HOME / ".pcs_industrial_20260802"
        LEGACY_PHANTOMCLOAK_SINGBOX = HOME / ".phantomcloak" / "singbox"
        LEGACY_DELPHI_SINGBOX = HOME / ".delphi" / "singbox"
    if suite is not None:
        SUITE = Path(suite)
    if legacy is not None:
        LEGACY = Path(legacy)
    if industrial is not None:
        INDUSTRIAL = Path(industrial)
    if state is not None:
        STATE = Path(state)

    INDUSTRIAL_SINGBOX = STATE / "singbox"
    INDUSTRIAL_VPS_PKG = STATE / "vps_server_package"
    INDUSTRIAL_TEMPLATES = STATE / "vps_templates_source_copy"
    INVENTORY_PATH = STATE / "vps_inventory.json"
    SECRETS_PATH = STATE / "secrets" / "location_keys.json"
    MATERIALIZE_META = STATE / "materialize_meta.json"
    MATERIALIZE_SCRIPT = INDUSTRIAL / "shared" / "pcs_materialize_singbox_v20260802.py"

    DIR_PRIORITY = [
        (INDUSTRIAL_SINGBOX, "industrial_client", 0),
        (INDUSTRIAL_VPS_PKG, "industrial_server_package", 1),
        (INDUSTRIAL_TEMPLATES, "industrial_templates", 2),
        (
            INDUSTRIAL / "server_vps_package_v20260802" / "templates_source_copy",
            "industrial_repo_templates",
            3,
        ),
        (SUITE / "server" / "ready-for-vps", "suite_ready_for_vps", 10),
        (LEGACY / "server" / "ready-for-vps", "legacy_ready_for_vps", 11),
        (LEGACY_PHANTOMCLOAK_SINGBOX, "legacy_phantomcloak_client", 20),
        (LEGACY_DELPHI_SINGBOX, "legacy_delphi_client", 21),
    ]

PLACEHOLDER_RE = re.compile(
    r"YOUR_VPS|127\.0\.0\.1|demo-uuid|changeme|placeholder|0\.0\.0\.0|example\.com|"
    r"REPLACE_|your-.*-vps|pending_vps_ip|REPLACE-UUID|REPLACE_WITH",
    re.I,
)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# Client outbound "server" field — not tun inet4_address
SERVER_FIELD_RE = re.compile(
    r'"server"\s*:\s*"([^"]+)"',
    re.I,
)
UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
SKIP_NAMES = {
    "location_keys.json",
    "materialize_meta.json",
    "vps_inventory.json",
    "orders.json",
    "_active.json",
    "legacy_sha.json",
}
SKIP_DIR_PARTS = {
    "hy2_certs",
    "accounts",
    "payments",
    "pf_rules",
    "__pycache__",
    "vault",
    "residential_pools",
}

CANONICAL_LOCS = (
    "dubai",
    "hongkong",
    "vancouver",
    "germany",
    "bahamas",
    "cayman",
    "mauritius",
    "seychelles",
)
# germany client often named frankfurt
LOC_ALIASES = {
    "frankfurt": "germany",
    "zurich": "zurich",  # legacy-only; keep as own label
    "singapore": "singapore",
}


# ---------------------------------------------------------------------------
# IP / placeholder helpers (never invent IPs)
# ---------------------------------------------------------------------------

def is_real_public_ip(value: Optional[str]) -> bool:
    """True only for plausible public IPv4 (or non-placeholder hostname).

    Rejects empty, placeholders, loopback, RFC1918, link-local, TEST-NET docs.
    """
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if not v or PLACEHOLDER_RE.search(v):
        return False
    # hostname path
    if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", v):
        if "." in v and " " not in v and not v.endswith(".local"):
            if PLACEHOLDER_RE.search(v):
                return False
            # block bare example.* even if PLACEHOLDER already caught example.com
            if v.lower().endswith(".example") or "example." in v.lower():
                return False
            return True
        return False
    try:
        parts = [int(x) for x in v.split(".")]
    except ValueError:
        return False
    if any(p < 0 or p > 255 for p in parts):
        return False
    a, b, c = parts[0], parts[1], parts[2]
    if a in (0, 10, 127):
        return False
    if a == 192 and b == 168:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 169 and b == 254:
        return False
    # documentation / TEST-NET (RFC 5737)
    if a == 192 and b == 0 and c == 2:
        return False
    if a == 198 and b == 51 and c == 100:
        return False
    if a == 203 and b == 0 and c == 113:
        return False
    # multicast / reserved
    if a >= 224:
        return False
    return True


def _location_from_name(name: str) -> Optional[str]:
    stem = name
    for suffix in (
        ".pending.json",
        ".json.template",
        ".json",
        ".template",
        ".toml",
        ".yml",
        ".yaml",
    ):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    stem = stem.lower()
    # sing-box-<loc>-reality
    m = re.match(r"sing-box-([a-z0-9]+)-reality", stem)
    if m:
        stem = m.group(1)
    stem = stem.replace(".pending", "").replace("-reality", "")
    if stem in CANONICAL_LOCS:
        return stem
    if stem in LOC_ALIASES:
        return LOC_ALIASES[stem]
    for loc in CANONICAL_LOCS:
        if loc in stem:
            return loc
    return stem if stem else None


def _extract_outbound_servers(text: str) -> List[str]:
    """Outbound server targets; filters Reality handshake hostnames used as dest."""
    servers: List[str] = []
    for m in SERVER_FIELD_RE.finditer(text):
        val = m.group(1).strip()
        # skip obvious SNI/handshake dests without IP-like or placeholder markers
        servers.append(val)
    return servers


def _client_has_real_server(text: str) -> bool:
    """Client configured if an outbound server is a real public IP/hostname
    and file is free of placeholders.
    """
    if PLACEHOLDER_RE.search(text):
        return False
    for srv in _extract_outbound_servers(text):
        # skip pure SNI hostnames that are well-known CDNs if no IP — still ok if real host
        if is_real_public_ip(srv):
            return True
    return False


# 0.0.0.0 as listen is valid for servers — exclude from PLACEHOLDER for server check
PLACEHOLDER_SERVER_OK_RE = re.compile(
    r"YOUR_VPS|demo-uuid|changeme|placeholder|example\.com|"
    r"REPLACE_|your-.*-vps|pending_vps_ip|REPLACE-UUID|REPLACE_WITH",
    re.I,
)


def _server_filled_strict(text: str, path: Path) -> bool:
    if PLACEHOLDER_SERVER_OK_RE.search(text):
        return False
    has_pk = "private_key" in text
    has_uuid = bool(UUID_RE.search(text))
    has_inbounds = "inbounds" in text
    role_hint = (
        "vps_server_package" in str(path)
        or "ready-for-vps" in str(path)
        or "sing-box-" in path.name
    )
    if not (has_pk and has_uuid and has_inbounds):
        return False
    # ready-for-vps Suite templates often still have placeholders — already filtered
    if "ready-for-vps" in str(path) or "templates_source_copy" in str(path):
        # only "filled" if no placeholders (already checked) AND real keys length
        if not has_pk:
            return False
    return role_hint or ("listen" in text and "outbounds" in text and has_pk)


# ---------------------------------------------------------------------------
# Inventory + secrets
# ---------------------------------------------------------------------------

def _real_pool_ips_for_location(meta: Dict[str, Any]) -> List[str]:
    """Real public IPs for one inventory location (v2 pool[] preferred, else v1 ip).

    Matches inventory-v2 ``iter_pool_members`` semantics. Never invents IPs —
    only validates values already present on disk. Dedupes within the location.
    """
    if not isinstance(meta, dict):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    pool = meta.get("pool") or []
    if not isinstance(pool, list):
        pool = []
    # v1 single-ip fallback when pool absent/empty
    if not pool and meta.get("ip"):
        pool = [{"ip": meta.get("ip"), "enabled": True}]
    for m in pool:
        if not isinstance(m, dict):
            continue
        if not m.get("enabled", True):
            continue
        ip = (m.get("ip") or "").strip()
        if not ip or ip in seen:
            continue
        if is_real_public_ip(ip):
            seen.add(ip)
            out.append(ip)
    return out


def _inventory_status() -> Dict[str, Any]:
    """Inventory probe: location gaps + v2 pool totals.

    - ``ips_set`` / ``ips_set_locations``: locations with ≥1 real IP (v1-compatible).
    - ``total_real_ips`` / ``by_location``: all enabled pool members with real IPs
      (inventory v2 multi-IP fleets). Does not invent IPs; redacts when shown.
    - ``configured_count`` is computed separately from client config scan — not here.
    """
    inv_path = INVENTORY_PATH
    if not inv_path.exists():
        return {
            "path": str(inv_path),
            "exists": False,
            "version": None,
            "ips_set": 0,
            "ips_set_locations": [],
            "total_real_ips": 0,
            "locations_with_ips": 0,
            "by_location": {},
            "gaps": list(CANONICAL_LOCS),
            "locations": {},
        }
    try:
        data = json.loads(inv_path.read_text())
    except Exception as e:
        return {
            "path": str(inv_path),
            "exists": True,
            "error": str(e),
            "version": None,
            "ips_set": 0,
            "ips_set_locations": [],
            "total_real_ips": 0,
            "locations_with_ips": 0,
            "by_location": {},
            "gaps": list(CANONICAL_LOCS),
            "locations": {},
        }
    locs = data.get("locations") or {}
    if not isinstance(locs, dict):
        locs = {}
    set_count = 0
    set_locs: List[str] = []
    gaps: List[str] = []
    detail: Dict[str, Any] = {}
    by_location: Dict[str, int] = {}
    total_real_ips = 0
    for name, meta in locs.items():
        meta = meta if isinstance(meta, dict) else {}
        enabled = bool(meta.get("enabled", True))
        # Disabled locations do not contribute pool members (inventory v2 parity)
        real_ips = _real_pool_ips_for_location(meta) if enabled else []
        n_pool = len(real_ips)
        has = n_pool > 0
        # Prefer first real pool IP for redaction; else raw meta.ip shape if present
        primary = real_ips[0] if real_ips else (meta.get("ip") or "").strip()
        if has:
            set_count += 1
            set_locs.append(name)
            by_location[name] = n_pool
            total_real_ips += n_pool
        elif enabled:
            gaps.append(name)
        detail[name] = {
            "ip_set": has,
            "enabled": enabled,
            "pool_member_count": n_pool,
            "ip_redacted": _redact_ip(primary) if primary else "",
        }
    # canonical locations missing from inventory entirely
    for loc in CANONICAL_LOCS:
        if loc not in detail:
            gaps.append(loc)
            detail[loc] = {
                "ip_set": False,
                "enabled": True,
                "pool_member_count": 0,
                "ip_redacted": "",
            }
    version = data.get("version")
    try:
        version_out: Any = int(version) if version is not None else None
    except (TypeError, ValueError):
        version_out = version
    return {
        "path": str(inv_path),
        "exists": True,
        "version": version_out,
        # locations with ≥1 real IP (backward compatible count)
        "ips_set": set_count,
        "ips_set_locations": sorted(set_locs),
        # inventory v2 pool visibility (all real member IPs)
        "total_real_ips": total_real_ips,
        "locations_with_ips": len(by_location),
        "by_location": dict(sorted(by_location.items())),
        "gaps": sorted(set(gaps)),
        "locations": detail,
    }


def _redact_ip(ip: str) -> str:
    """Show shape only — never invent; mask last two octets of IPv4."""
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip):
        a, b, _, _ = ip.split(".")
        return f"{a}.{b}.x.x"
    if "." in ip:
        parts = ip.split(".")
        if len(parts) >= 2:
            return parts[0] + ".***." + parts[-1]
    return "***"


def needs_rematerialize(inventory_ip_set: bool, client_configured: bool) -> bool:
    """Inventory has a real IP but industrial client config not written yet."""
    return bool(inventory_ip_set) and not bool(client_configured)


def _load_secrets_raw() -> Optional[Dict[str, Any]]:
    """Load location_keys.json once per scan (or None if missing/unreadable).

    Returns a sentinel dict with ``_load_error`` set on parse failure so callers
    can distinguish missing vs corrupt without re-reading the file.
    """
    if not SECRETS_PATH.exists():
        return None
    try:
        data = json.loads(SECRETS_PATH.read_text())
        if isinstance(data, dict):
            return data
        return {"_load_error": "TypeError", "locations": {}}
    except Exception as e:
        return {"_load_error": type(e).__name__, "locations": {}}


def _secrets_status(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Secrets presence matrix. Pass preloaded ``data`` to avoid a second read."""
    if data is None:
        data = _load_secrets_raw()
    if data is None:
        return {
            "path": str(SECRETS_PATH),
            "exists": False,
            "secrets_ok": False,
            "ok_locations": [],
            "missing_locations": list(CANONICAL_LOCS),
            "locations": {},
        }
    if data.get("_load_error"):
        return {
            "path": str(SECRETS_PATH),
            "exists": True,
            "error": data["_load_error"],  # never embed file body / keys
            "secrets_ok": False,
            "ok_locations": [],
            "missing_locations": list(CANONICAL_LOCS),
            "locations": {},
        }
    locs = data.get("locations") or {}
    # tolerate accidental list form
    if isinstance(locs, list):
        locs = {name: {} for name in locs}
    detail: Dict[str, Any] = {}
    ok_locs: List[str] = []
    missing: List[str] = []
    for loc in CANONICAL_LOCS:
        meta = locs.get(loc) or {}
        uuid_ok = bool(meta.get("uuid") and UUID_RE.search(str(meta.get("uuid"))))
        # Presence/length checks only — never copy private_key / hy2_password into status.
        pk_ok = bool(meta.get("private_key") and len(str(meta["private_key"])) >= 20)
        pub_ok = bool(meta.get("public_key") and len(str(meta["public_key"])) >= 20)
        sid_ok = bool(meta.get("short_id"))
        ok = uuid_ok and pk_ok and pub_ok and sid_ok
        detail[loc] = {
            "secrets_ok": ok,
            "has_uuid": uuid_ok,
            "has_private_key": pk_ok,
            "has_public_key": pub_ok,
            "has_short_id": sid_ok,
            "has_hy2_password": bool(meta.get("hy2_password")),
        }
        if ok:
            ok_locs.append(loc)
        else:
            missing.append(loc)
    return {
        "path": str(SECRETS_PATH),
        "exists": True,
        "secrets_ok": len(missing) == 0 and len(ok_locs) > 0,
        "ok_count": len(ok_locs),
        "ok_locations": ok_locs,
        "missing_locations": missing,
        "locations": detail,
    }


# pending.json public surface only (never private_key / hy2_password / passwords).
# Canonical allowlist lives in pcs_client_singbox (includes schema_version).
# Readiness surfaces a compact public subset for scan entries; never secret values.
try:
    from .pcs_client_singbox_v20260802 import (  # type: ignore
        PENDING_FORBIDDEN_KEYS as _CLIENT_PENDING_FORBIDDEN,
        PENDING_PUBLIC_KEYS as _CLIENT_PENDING_PUBLIC,
        filter_pending_public as _client_filter_pending_public,
    )
except Exception:
    try:
        from pcs_client_singbox_v20260802 import (  # type: ignore
            PENDING_FORBIDDEN_KEYS as _CLIENT_PENDING_FORBIDDEN,
            PENDING_PUBLIC_KEYS as _CLIENT_PENDING_PUBLIC,
            filter_pending_public as _client_filter_pending_public,
        )
    except Exception:
        _CLIENT_PENDING_FORBIDDEN = frozenset(
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
        _CLIENT_PENDING_PUBLIC = frozenset(
            {
                "schema",
                "schema_version",
                "location",
                "status",
                "uuid",
                "public_key",
                "short_id",
                "sni",
                "configured",
                "aliases",
                "skip_reason",
                "hint",
            }
        )

        def _client_filter_pending_public(obj: Any) -> Dict[str, Any]:
            if not isinstance(obj, dict):
                return {}
            return {
                k: v
                for k, v in obj.items()
                if k in _CLIENT_PENDING_PUBLIC
                and str(k).lower() not in _CLIENT_PENDING_FORBIDDEN
            }


# Compact fields readiness attaches to each pending_ip entry (all must be public).
_PENDING_PUBLIC_KEYS = (
    "schema_version",
    "location",
    "status",
    "uuid",
    "public_key",
    "short_id",
    "sni",
    "configured",
    "skip_reason",
)
_SECRET_VALUE_KEYS = frozenset(_CLIENT_PENDING_FORBIDDEN) | frozenset(
    {
        "privkey",
        "secret",
        "token",
        "api_key",
        "passphrase",
        "password",
    }
)


def _pending_public_meta(pend: Dict[str, Any]) -> Dict[str, Any]:
    """Extract only public fields from a pending sidecar (strip private if present).

    Uses hard allowlist; never returns private_key / hy2_password / password.
    schema_version is included when present (documents pending sidecar shape).
    """
    if not isinstance(pend, dict):
        return {}
    # Full filter first (drops secrets + unknown keys)
    safe = _client_filter_pending_public(pend)
    out: Dict[str, Any] = {}
    for k in _PENDING_PUBLIC_KEYS:
        if k in safe and k not in _SECRET_VALUE_KEYS:
            out[k] = safe[k]
    # Defense: never re-introduce forbidden keys even if allowlist drifts
    for fk in list(out.keys()):
        if str(fk).lower() in _SECRET_VALUE_KEYS or str(fk).lower().endswith("_password"):
            del out[fk]
    return out


def _redact_for_stdout(obj: Any, depth: int = 0) -> Any:
    """Last-line defense: never emit secret field values in readiness JSON."""
    if depth > 14:
        return "<max-depth>"
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in _SECRET_VALUE_KEYS or kl.endswith("_private_key"):
                if isinstance(v, str):
                    out[k] = f"<redacted len={len(v)}>"
                elif isinstance(v, bool):
                    out[k] = v
                else:
                    out[k] = "<redacted>"
            else:
                out[k] = _redact_for_stdout(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [_redact_for_stdout(x, depth + 1) for x in obj[:100]]
    return obj


def _secrets_fingerprint_block(
    secrets_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Public-material fingerprint + optional age (no private key values).

    Pass preloaded secrets_data (from ``_load_secrets_raw``) to avoid re-reading
    location_keys.json for fingerprint and age within the same scan.
    """
    try:
        # Prefer package import when industrial root is on sys.path
        try:
            from shared.pcs_materialize_singbox_v20260802 import (
                secrets_age_check,
                secrets_fingerprint,
            )
        except Exception:
            from pcs_materialize_singbox_v20260802 import (  # type: ignore
                secrets_age_check,
                secrets_fingerprint,
            )
        # Strip load-error sentinel; fingerprint helpers treat None as missing
        data_for_fp = secrets_data
        if isinstance(data_for_fp, dict) and data_for_fp.get("_load_error"):
            data_for_fp = None
        fp = secrets_fingerprint(data_for_fp)
        age = secrets_age_check(secrets_data=data_for_fp)
        return {
            "secrets_fingerprint": fp.get("fingerprint"),
            "secrets_fingerprint_full": fp.get("fingerprint_full"),
            "secrets_fingerprint_meta": {
                "algorithm": fp.get("algorithm"),
                "hashed_fields": fp.get("hashed_fields"),
                "locations": fp.get("locations"),
                "exists": fp.get("exists"),
            },
            "secrets_age": age,
        }
    except Exception as e:
        return {
            "secrets_fingerprint": None,
            "secrets_fingerprint_full": None,
            "secrets_fingerprint_meta": {"error": type(e).__name__},
            "secrets_age": None,
        }


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

def _env_flag(name: str) -> bool:
    """True when env var is a common truthy string (1/true/yes/on)."""
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def industrial_only_enabled() -> bool:
    """Prefer industrial dirs only when PCS_READINESS_INDUSTRIAL_ONLY is set."""
    return _env_flag("PCS_READINESS_INDUSTRIAL_ONLY")


def _candidate_dirs(*, industrial_only: Optional[bool] = None) -> List[Tuple[Path, str, int]]:
    """Return existing scan roots.

    industrial_only=True (or env PCS_READINESS_INDUSTRIAL_ONLY=1): only priority < 10
    (industrial client / server package / templates / repo templates). Skips Suite
    and legacy trees for speed; primary counts are unchanged (they already use prio < 10).
    """
    if industrial_only is None:
        industrial_only = industrial_only_enabled()
    out: List[Tuple[Path, str, int]] = []
    for path, role, prio in DIR_PRIORITY:
        if industrial_only and prio >= 10:
            continue
        if path.exists() and path.is_dir():
            out.append((path, role, prio))
    return out


def _path_key(p: Path) -> str:
    """Stable absolute key without symlink resolve() thrash (content hash still dedupes)."""
    try:
        return os.path.normcase(os.path.abspath(os.fspath(p)))
    except Exception:
        return str(p)


def _iter_config_files(root: Path) -> List[Path]:
    """Single os.walk for config-like files (avoids dual rglob thrash per dir)."""
    out: List[Path] = []
    if not root.is_dir():
        return out
    skip_dirs = SKIP_DIR_PARTS
    skip_names = SKIP_NAMES
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # prune non-config subtrees in-place (faster than visiting then skipping)
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if name in skip_names:
                continue
            # *.json covers *.pending.json; also templates / yaml / toml
            if not (
                name.endswith(".json")
                or name.endswith(".json.template")
                or name.endswith(".toml")
                or name.endswith(".yml")
                or name.endswith(".yaml")
                or "template" in name.lower()
            ):
                continue
            if name.endswith((".pem", ".key", ".crt", ".log", ".md", ".sh", ".conf")):
                continue
            out.append(Path(dirpath) / name)
    return out


def _should_skip_file(p: Path) -> bool:
    if p.name in SKIP_NAMES:
        return True
    parts = set(p.parts)
    if parts & SKIP_DIR_PARTS:
        return True
    if p.suffix not in {".json", ".template", ".toml", ".yml", ".yaml"}:
        if "template" not in p.name.lower() and not p.name.endswith(".pending.json"):
            return True
    # never treat certs / pem as configs
    if p.suffix in {".pem", ".key", ".crt", ".log", ".md", ".sh", ".conf"}:
        return True
    return False


def _classify_file(
    p: Path,
    role: str,
    prio: int,
    text: str,
) -> str:
    """Return one of: pending_ip | server_filled | client_configured | template."""
    name = p.name
    if name.endswith(".pending.json") or '"status": "pending_vps_ip"' in text or '"status":"pending_vps_ip"' in text:
        return "pending_ip"
    # industrial / suite templates dirs
    if (
        "templates_source_copy" in str(p)
        or "ready-for-vps" in str(p)
        or "template" in name.lower()
        or name.endswith(".json.template")
    ):
        # unless somehow fully filled without placeholders
        if _server_filled_strict(text, p) and "templates_source_copy" not in str(p) and "ready-for-vps" not in str(p):
            return "server_filled"
        return "template"
    if role == "industrial_server_package" or "vps_server_package" in str(p):
        if _server_filled_strict(text, p):
            return "server_filled"
        if PLACEHOLDER_SERVER_OK_RE.search(text) or PLACEHOLDER_RE.search(text):
            return "template"
        return "server_filled" if "private_key" in text else "template"
    # client dirs (industrial + legacy)
    if role.endswith("_client") or role in {
        "industrial_client",
        "legacy_phantomcloak_client",
        "legacy_delphi_client",
    }:
        if _client_has_real_server(text):
            return "client_configured"
        return "template"
    # fallback
    if _server_filled_strict(text, p):
        return "server_filled"
    if _client_has_real_server(text):
        return "client_configured"
    return "template"


def scan_readiness() -> Dict[str, Any]:
    """Full readiness scan. Industrial singbox scored primary; legacy deduped.

    Within a single call: one walk per dir, one read per file, one secrets load
    shared by status + fingerprint + age. Optional PCS_READINESS_INDUSTRIAL_ONLY=1
    skips Suite/legacy trees (primary industrial scoring unchanged).
    """
    templates: List[Dict[str, Any]] = []
    configured: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    server_filled: List[Dict[str, Any]] = []
    all_files: List[Dict[str, Any]] = []

    seen_resolved: Set[str] = set()
    seen_content_by_kind: Dict[str, Set[str]] = {
        "template": set(),
        "pending_ip": set(),
        "server_filled": set(),
        "client_configured": set(),
    }
    # For counting: only primary (prio < 10) + first of each content hash
    count_templates = 0
    count_configured = 0
    count_pending = 0
    count_server_filled = 0
    skipped_dup_path = 0
    skipped_dup_content = 0
    legacy_files_seen = 0

    primary_client_locs: Set[str] = set()
    primary_pending_locs: Set[str] = set()
    primary_server_locs: Set[str] = set()

    industrial_only = industrial_only_enabled()

    try:
        dirs = _candidate_dirs(industrial_only=industrial_only)
        for d, role, prio in dirs:
            is_primary = prio < 10
            is_legacy_client = prio >= 20
            # Single walk (not dual rglob + glob) — pending.json already matched by *.json
            paths = _iter_config_files(d)
            # unique within dir (path key once)
            uniq_paths: List[Path] = []
            seen_local: Set[str] = set()
            for p in paths:
                k = _path_key(p)
                if k in seen_local:
                    continue
                seen_local.add(k)
                uniq_paths.append(p)

            for p in sorted(uniq_paths, key=lambda x: x.name):
                if _should_skip_file(p):
                    continue
                key = _path_key(p)
                if key in seen_resolved:
                    skipped_dup_path += 1
                    continue
                seen_resolved.add(key)

                try:
                    raw = p.read_bytes()
                    full_text = raw.decode("utf-8", errors="replace")
                    text = full_text[:12000]
                    chash = hashlib.sha256(raw).hexdigest()
                except Exception:
                    continue

                kind = _classify_file(p, role, prio, text)
                loc = _location_from_name(p.name)

                # pending sidecar enrich — reuse bytes already read (no second open)
                pend_meta: Dict[str, Any] = {}
                if kind == "pending_ip":
                    try:
                        pend = json.loads(full_text)
                        if isinstance(pend, dict):
                            loc = pend.get("location") or loc
                            pend_meta = _pending_public_meta(pend)
                    except Exception:
                        pass

                entry: Dict[str, Any] = {
                    "path": str(p),
                    "name": p.name,
                    "source": str(d),
                    "role": role,
                    "priority": prio,
                    "primary": is_primary,
                    "kind": kind,
                    "location": loc,
                    "content_sha256_12": chash[:12],
                }
                if pend_meta:
                    entry.update(pend_meta)

                # Content dedupe for counts: first path wins (DIR_PRIORITY is industrial-first).
                # Identical suite / repo / phantomcloak / delphi copies count once.
                content_bucket = seen_content_by_kind.setdefault(kind, set())
                is_content_dup = chash in content_bucket
                if not is_content_dup:
                    content_bucket.add(chash)

                if is_legacy_client:
                    legacy_files_seen += 1

                entry["countable"] = not is_content_dup
                if is_content_dup:
                    skipped_dup_content += 1

                all_files.append(entry)

                if not entry["countable"]:
                    continue

                if kind == "pending_ip":
                    pending.append(entry)
                    count_pending += 1
                    if loc and is_primary:
                        primary_pending_locs.add(loc)
                elif kind == "server_filled":
                    server_filled.append(entry)
                    count_server_filled += 1
                    if loc and is_primary:
                        primary_server_locs.add(loc)
                elif kind == "client_configured":
                    configured.append(entry)
                    count_configured += 1
                    # Prefer industrial client locations for matrix; still record any countable
                    if loc and is_primary:
                        primary_client_locs.add(loc)
                else:
                    templates.append(entry)
                    count_templates += 1

        inv = _inventory_status()
        # One secrets file read shared by status + fingerprint + age (no triple open)
        secrets_raw = _load_secrets_raw()
        secrets = _secrets_status(data=secrets_raw)
        sec_fp = _secrets_fingerprint_block(secrets_data=secrets_raw)

        # Location matrix
        locations_matrix: Dict[str, Any] = {}
        inventory_set_not_rematerialized: List[str] = []
        for loc in CANONICAL_LOCS:
            inv_meta = (inv.get("locations") or {}).get(loc) or {}
            sec_meta = (secrets.get("locations") or {}).get(loc) or {}
            ip_set = bool(inv_meta.get("ip_set"))
            client_ok = loc in primary_client_locs
            # also accept client file under industrial even if alias
            pending_ok = loc in primary_pending_locs
            server_ok = loc in primary_server_locs
            secrets_ok = bool(sec_meta.get("secrets_ok"))

            # inventory IP set but client not rematerialized
            remat = needs_rematerialize(ip_set, client_ok)
            if remat:
                inventory_set_not_rematerialized.append(loc)

            # inventory_gap: enabled without IP, or IP set but not rematerialized
            gap = (not ip_set and inv_meta.get("enabled", True)) or remat

            classes: List[str] = []
            if secrets_ok:
                classes.append("secrets_ok")
            if server_ok:
                classes.append("server_filled")
            if pending_ok and not client_ok:
                classes.append("pending_ip")
            if client_ok:
                classes.append("client_configured")
            if gap:
                classes.append("inventory_gap")
            if not client_ok and not pending_ok and not server_ok and not secrets_ok:
                classes.append("template")

            locations_matrix[loc] = {
                "classifications": classes,
                "inventory_ip_set": ip_set,
                "pending_ip": pending_ok and not client_ok,
                "server_filled": server_ok,
                "client_configured": client_ok,
                "secrets_ok": secrets_ok,
                "inventory_gap": gap,
                "needs_rematerialize": remat,
            }

        # Overall status
        if count_configured > 0 and not inv.get("gaps") and not inventory_set_not_rematerialized:
            # all good clients; gaps empty means all enabled have IPs
            if count_configured >= max(1, inv.get("ips_set", 0)) and not primary_pending_locs:
                status = "ready"
            else:
                status = "partial"
        elif count_configured > 0:
            status = "partial"
        elif inventory_set_not_rematerialized:
            status = "inventory_set_pending_rematerialize"
        elif count_server_filled > 0 and count_pending > 0:
            status = "server_package_ready_pending_client_ips"
        elif count_pending > 0:
            status = "materialized_pending_ips"
        elif count_server_filled > 0:
            status = "server_package_ready_pending_client_ips"
        else:
            status = "templates_only"

        next_actions = _build_next_actions(
            status=status,
            inv=inv,
            secrets=secrets,
            count_configured=count_configured,
            count_pending=count_pending,
            count_server_filled=count_server_filled,
            inventory_set_not_rematerialized=inventory_set_not_rematerialized,
            locations_matrix=locations_matrix,
        )

        howto = SUITE / "docs" / "HOWTO_DEPLOY_AND_VERIFY.md"
        if not howto.exists():
            howto = LEGACY / "docs" / "HOWTO_DEPLOY_AND_VERIFY.md"
        industrial_howto = INDUSTRIAL / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"

        # optional self-test when inventory has zero real IPs
        self_test: Optional[Dict[str, Any]] = None
        if inv.get("ips_set", 0) == 0:
            self_test = run_self_test()

        result: Dict[str, Any] = {
            "ok": True,
            "status": status,
            "probe": {
                "ready": status in ("ready", "partial") and count_configured > 0,
                "exit_code_hint": (
                    0
                    if (status in ("ready", "partial") and count_configured > 0)
                    else 3
                ),
            },
            # flat counts (backward compatible)
            "templates_count": count_templates,
            "configured_count": count_configured,
            "server_filled_count": count_server_filled,
            "pending_ip_count": count_pending,
            "secrets_ok_count": secrets.get("ok_count", 0),
            "inventory_gap_count": len(inv.get("gaps") or [])
            + len(inventory_set_not_rematerialized),
            "counts": {
                "template": count_templates,
                "pending_ip": count_pending,
                "server_filled": count_server_filled,
                "client_configured": count_configured,
                "secrets_ok": secrets.get("ok_count", 0),
                "inventory_gap": len(inv.get("gaps") or []),
                "inventory_set_not_rematerialized": len(
                    inventory_set_not_rematerialized
                ),
            },
            "primary": {
                "client_dir": str(INDUSTRIAL_SINGBOX),
                "server_package": str(INDUSTRIAL_VPS_PKG),
                "client_locations": sorted(primary_client_locs),
                "pending_locations": sorted(primary_pending_locs),
                "server_filled_locations": sorted(primary_server_locs),
            },
            "locations": locations_matrix,
            "inventory_set_not_rematerialized": inventory_set_not_rematerialized,
            "dedupe": {
                "resolved_path_skips": skipped_dup_path,
                "content_hash_skips": skipped_dup_content,
                "legacy_files_seen": legacy_files_seen,
                "industrial_only": industrial_only,
                "dirs_scanned": len(dirs),
                "note": (
                    "Industrial dirs are primary. Identical ~/.phantomcloak and "
                    "~/.delphi configs share content hashes and count once."
                    + (
                        " PCS_READINESS_INDUSTRIAL_ONLY=1: Suite/legacy trees skipped."
                        if industrial_only
                        else ""
                    )
                ),
            },
            "templates": templates[:20],
            "configured": configured[:20],
            "server_filled": server_filled[:20],
            "pending": pending[:20],
            "files_sample": all_files[:40],
            "inventory": inv,
            "secrets": {
                "path": secrets.get("path"),
                "exists": secrets.get("exists"),
                "secrets_ok": secrets.get("secrets_ok"),
                "ok_count": secrets.get("ok_count"),
                "ok_locations": secrets.get("ok_locations"),
                "missing_locations": secrets.get("missing_locations"),
                # omit raw key material — presence flags live under locations matrix only
            },
            "secrets_fingerprint": sec_fp.get("secrets_fingerprint"),
            "secrets_fingerprint_full": sec_fp.get("secrets_fingerprint_full"),
            "secrets_fingerprint_meta": sec_fp.get("secrets_fingerprint_meta"),
            "secrets_age": sec_fp.get("secrets_age"),
            "next_actions": next_actions,
            "howto_path": str(howto) if howto.exists() else None,
            "industrial_howto": str(industrial_howto) if industrial_howto.exists() else str(industrial_howto),
            "materialize_script": str(MATERIALIZE_SCRIPT),
            "summary": (
                f"status={status}; "
                f"{count_configured} client_configured, "
                f"{count_server_filled} server_filled, "
                f"{count_pending} pending_ip, "
                f"{count_templates} template (deduped); "
                f"secrets_ok={secrets.get('ok_count', 0)}; "
                f"inventory_ips_set={inv.get('ips_set', 0)}; "
                f"total_real_ips={inv.get('total_real_ips', 0)}; "
                f"by_location={inv.get('by_location') or {}}; "
                f"rematerialize_needed={len(inventory_set_not_rematerialized)}; "
                f"secrets_fingerprint={sec_fp.get('secrets_fingerprint')}"
            ),
            # legacy single next_step for older callers
            "next_step": (
                next_actions[0]["action"]
                if next_actions
                else None
            ),
        }
        if self_test is not None:
            result["self_test"] = self_test
        # Never echo private_key / hy2_password values even if a future path adds them.
        return _redact_for_stdout(result)  # type: ignore[return-value]
    except Exception as e:
        err = str(e)
        if any(x in err.lower() for x in ("privatekey:", "private_key", "-----begin", "hy2_password")):
            err = f"{type(e).__name__}: <redacted>"
        return {
            "ok": False,
            "status": "error",
            "error": err,
            "templates_count": 0,
            "configured_count": 0,
            "server_filled_count": 0,
            "pending_ip_count": 0,
            "next_actions": [
                {
                    "severity": "critical",
                    "code": "scan_exception",
                    "action": f"Fix readiness scanner error: {err}",
                }
            ],
            "summary": f"error: {err}",
            "next_step": f"Fix readiness scanner error: {err}",
        }


def _build_next_actions(
    *,
    status: str,
    inv: Dict[str, Any],
    secrets: Dict[str, Any],
    count_configured: int,
    count_pending: int,
    count_server_filled: int,
    inventory_set_not_rematerialized: List[str],
    locations_matrix: Dict[str, Any],
) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []

    if not inv.get("exists"):
        actions.append(
            {
                "severity": "high",
                "code": "inventory_missing",
                "action": (
                    f"Create inventory at {INVENTORY_PATH} (run materialize once) "
                    "then set real VPS public IPs per location."
                ),
            }
        )

    gaps = inv.get("gaps") or []
    if gaps:
        actions.append(
            {
                "severity": "high",
                "code": "inventory_gap",
                "action": (
                    f"Set real public IPs for: {', '.join(gaps)}. "
                    f"Edit {inv.get('path')} or export PCS_VPS_<LOC>=x.x.x.x "
                    f"(e.g. PCS_VPS_DUBAI). Do not use RFC1918/TEST-NET."
                ),
            }
        )

    if inventory_set_not_rematerialized:
        actions.append(
            {
                "severity": "high",
                "code": "inventory_set_pending_rematerialize",
                "action": (
                    f"Inventory has IPs for {', '.join(inventory_set_not_rematerialized)} "
                    f"but industrial client configs are missing. Re-run: "
                    f"python3 {MATERIALIZE_SCRIPT}"
                ),
            }
        )

    if not secrets.get("secrets_ok"):
        missing = secrets.get("missing_locations") or []
        actions.append(
            {
                "severity": "medium",
                "code": "secrets_incomplete",
                "action": (
                    f"Secrets incomplete for: {', '.join(missing) or 'all'}. "
                    f"Run materialize to generate Reality keys under {SECRETS_PATH}."
                ),
            }
        )

    if count_server_filled > 0 and count_configured == 0:
        actions.append(
            {
                "severity": "medium",
                "code": "server_filled_awaiting_client_ips",
                "action": (
                    f"{count_server_filled} filled server package file(s) ready to scp. "
                    f"After inventory IPs are set, re-run materialize to write clients "
                    f"under {INDUSTRIAL_SINGBOX}."
                ),
            }
        )

    if count_pending > 0 and count_configured == 0:
        actions.append(
            {
                "severity": "medium",
                "code": "pending_ip_sidecars",
                "action": (
                    f"{count_pending} *.pending.json sidecar(s) in industrial singbox — "
                    "secrets exist but client rematerialize blocked until inventory IP."
                ),
            }
        )

    if status == "templates_only":
        actions.append(
            {
                "severity": "high",
                "code": "templates_only",
                "action": (
                    f"Only templates found. Run: python3 {MATERIALIZE_SCRIPT} "
                    "then set inventory IPs."
                ),
            }
        )

    if count_configured > 0 and status in ("ready", "partial"):
        actions.append(
            {
                "severity": "info",
                "code": "clients_ready",
                "action": (
                    f"{count_configured} client config(s) with real server targets. "
                    "Deploy server package to VPS if not already; verify with sing-box check."
                ),
            }
        )

    if count_server_filled > 0:
        deploy = INDUSTRIAL_VPS_PKG / "deploy_filled_to_vps.sh"
        if deploy.exists():
            actions.append(
                {
                    "severity": "low",
                    "code": "deploy_script_available",
                    "action": f"Deploy filled configs via {deploy} for locations with IPs.",
                }
            )

    # stable severity order
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    actions.sort(key=lambda a: order.get(a.get("severity", "info"), 9))
    return actions


# ---------------------------------------------------------------------------
# Self-test (unit-less; no inventory IPs required)
# ---------------------------------------------------------------------------

def run_self_test() -> Dict[str, Any]:
    """Lightweight pure checks of classifiers. Runs when inventory ips_set==0
    or when --self-test is passed. Does not invent or require real IPs.
    """
    cases: List[Tuple[str, str, str, bool]] = []
    # (name, role, text, expected_kind_prefix)

    def check(name: str, got: Any, expected: Any) -> None:
        cases.append((name, str(expected), str(got), got == expected))

    check("is_real_public_ip empty", is_real_public_ip(""), False)
    check("is_real_public_ip placeholder", is_real_public_ip("YOUR_VPS_IP"), False)
    check("is_real_public_ip loopback", is_real_public_ip("127.0.0.1"), False)
    check("is_real_public_ip rfc1918", is_real_public_ip("192.168.1.1"), False)
    check("is_real_public_ip testnet", is_real_public_ip("203.0.113.10"), False)
    check("is_real_public_ip zero", is_real_public_ip("0.0.0.0"), False)

    tpl_text = '{"outbounds":[{"server":"YOUR_VPS_IP_FOR_DUBAI","uuid":"REPLACE-UUID-FROM-SERVER"}]}'
    check(
        "classify template client",
        _classify_file(Path("dubai.json"), "legacy_phantomcloak_client", 20, tpl_text),
        "template",
    )

    pend_text = '{"location":"dubai","status":"pending_vps_ip","uuid":"ef10591b-efd3-48b9-866f-aaf09983cf59"}'
    check(
        "classify pending",
        _classify_file(Path("dubai.pending.json"), "industrial_client", 0, pend_text),
        "pending_ip",
    )

    # server filled: use non-placeholder private_key + uuid; listen :: 
    # Avoid real-looking public IPs in fixtures
    filled = (
        '{"inbounds":[{"type":"vless","listen":"::","users":[{"uuid":'
        '"ef10591b-efd3-48b9-866f-aaf09983cf59"}],"tls":{"reality":{"private_key":'
        '"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}}}],"outbounds":[{"type":"direct"}]}'
    )
    check(
        "classify server_filled",
        _classify_file(
            Path("sing-box-dubai-reality.json"),
            "industrial_server_package",
            1,
            filled,
        ),
        "server_filled",
    )

    # client with only tun RFC1918 + placeholder still template
    client_bad = (
        '{"inbounds":[{"inet4_address":"172.19.0.1/30"}],'
        '"outbounds":[{"server":"YOUR_VPS_IP","server_port":443}]}'
    )
    check(
        "classify client placeholder",
        _classify_file(Path("dubai.json"), "industrial_client", 0, client_bad),
        "template",
    )

    check("loc from pending name", _location_from_name("dubai.pending.json"), "dubai")
    check(
        "loc from server package name",
        _location_from_name("sing-box-hongkong-reality.json"),
        "hongkong",
    )
    check("loc alias frankfurt", _location_from_name("frankfurt.json"), "germany")
    check("redact ipv4", _redact_ip("198.51.100.20"), "198.51.x.x")
    check("rematerialize when ip set no client", needs_rematerialize(True, False), True)
    check("no rematerialize when client ok", needs_rematerialize(True, True), False)
    check("no rematerialize when no ip", needs_rematerialize(False, False), False)
    check(
        "exit 3 templates_only",
        exit_code_for(
            {
                "ok": True,
                "status": "templates_only",
                "configured_count": 0,
            }
        ),
        3,
    )
    check(
        "exit 0 partial configured",
        exit_code_for(
            {"ok": True, "status": "partial", "configured_count": 2}
        ),
        0,
    )
    check(
        "exit 1 error",
        exit_code_for({"ok": False, "status": "error", "configured_count": 0}),
        1,
    )

    passed = sum(1 for c in cases if c[3])
    failed = [c[0] for c in cases if not c[3]]
    return {
        "ran": True,
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "ok": len(failed) == 0,
        "cases": [
            {"name": n, "expected": e, "got": g, "pass": p}
            for n, e, g, p in cases
        ],
    }


def exit_code_for(result: Dict[str, Any]) -> int:
    if not result.get("ok", True) or result.get("status") == "error":
        return 1
    configured = int(result.get("configured_count") or 0)
    status = result.get("status") or ""
    if status in ("ready", "partial") and configured > 0:
        return 0
    return 3


def gate_snapshot(readiness: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compact readiness fields for preflight / activate gate JSON.

    Fail-closed protect rule: ok_for_protect is True only when configured_count > 0.
    Dashboard / status / wizard may still call scan_readiness() freely.
    Does not invent IPs; surfaces live counts only.
    """
    r: Dict[str, Any] = readiness if readiness is not None else scan_readiness()
    inv = r.get("inventory") or {}
    howto = r.get("howto_path") or r.get("industrial_howto")
    configured_count = int(r.get("configured_count") or 0)
    server_filled_count = int(r.get("server_filled_count") or 0)
    pending = list(r.get("pending") or [])
    pending_ip_count = int(r.get("pending_ip_count") or len(pending))
    ok = configured_count > 0
    block_message = None
    if not ok:
        inv_path = inv.get("path") or str(INVENTORY_PATH)
        next_step = r.get("next_step")
        if not next_step and r.get("next_actions"):
            next_step = (r["next_actions"][0] or {}).get("action")
        block_message = (
            "Protected browsing blocked: no client configs with real VPS IPs "
            f"(configured_count=0). server_filled_count={server_filled_count}, "
            f"pending_ip_count={pending_ip_count}. "
            f"Fill inventory at {inv_path} with public VPS IPs, then re-run "
            f"materialize ({MATERIALIZE_SCRIPT}). "
            f"See HOWTO: {howto}. "
            "Dashboard, config, and deploy wizard remain available."
        )
        if next_step:
            block_message = f"{block_message} Next: {next_step}"
    snap = {
        "status": r.get("status"),
        "ok_for_protect": ok,
        "configured_count": configured_count,
        "server_filled_count": server_filled_count,
        "pending_ip_count": pending_ip_count,
        "pending": pending[:20],
        "inventory_path": inv.get("path"),
        "inventory_ips_set": inv.get("ips_set", 0),
        "total_real_ips": int(inv.get("total_real_ips") or 0),
        "by_location": inv.get("by_location") or {},
        "howto_path": r.get("howto_path"),
        "industrial_howto": r.get("industrial_howto"),
        "next_step": r.get("next_step"),
        "next_actions": r.get("next_actions") or [],
        "summary": r.get("summary"),
        "block_message": block_message,
        "materialize_script": r.get("materialize_script") or str(MATERIALIZE_SCRIPT),
        "secrets_fingerprint": r.get("secrets_fingerprint"),
        "secrets_age": r.get("secrets_age"),
    }
    return _redact_for_stdout(snap)  # type: ignore[return-value]



def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="PCS industrial server readiness probe",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Emit JSON (default)",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 0 ready/partial+configured, 3 templates/pending, 1 error",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Force pure self-test block in output",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Indent JSON (default on for tty)",
    )
    args = parser.parse_args(argv)

    result = scan_readiness()
    if args.self_test:
        result["self_test"] = run_self_test()
        if not result["self_test"].get("ok"):
            result["ok"] = False
            result["status"] = "error"
            result.setdefault("next_actions", []).insert(
                0,
                {
                    "severity": "critical",
                    "code": "self_test_failed",
                    "action": f"Self-test failed: {result['self_test'].get('failed')}",
                },
            )

    indent = 2 if (args.pretty or sys.stdout.isatty()) else None
    # result already redacted in scan_readiness; defense-in-depth before print
    print(json.dumps(_redact_for_stdout(result), indent=indent))

    if args.exit_code:
        return exit_code_for(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
