#!/usr/bin/env python3
"""Materialize real sing-box server + client configs (industrial tree only).

Follows: PhantomCloak Suite docs/HOWTO_DEPLOY_AND_VERIFY.md

- Copies Suite server/ready-for-vps templates into industrial package (read-only source)
- Generates UUID + Reality keypairs + strong passwords via sing-box / secrets
- Writes filled server configs ready for scp to VPS
- Writes client configs under ~/.pcs_industrial_20260802/singbox/
- Injects public IPs from vps_inventory.json or PCS_VPS_<LOC> env vars

Does NOT overwrite PhantomCloak Suite or ~/.phantomcloak / ~/.delphi originals.
Never invents VPS IPs. Never overwrites Suite. Never prints private keys.

CLI (operator UX — HashiCorp-style plan / apply)
-------------------------------------------------
  python3 pcs_materialize_singbox_v20260802.py [options]

  (default)               Apply: materialize server package + clients (idempotent).
  --check-only            Plan/status only: report inventory, secrets fingerprint,
                          hy2 cert presence. Never creates or mutates any files.
  --rotate-keys           Apply with key regeneration: new UUID / Reality keypairs /
                          hy2 passwords for selected locations, then rematerialize
                          server package + clients. Default without flag: preserve keys.
  --location NAME         Scope to one location (e.g. dubai). Default: all.
  --force-inventory-env   Persist PCS_VPS_<LOC> env overlays into vps_inventory.json
                          (ignored for writes under --check-only; reported only).
  --json                  Machine-readable JSON on stdout; suppress human stderr summary.

  Incompatible: --check-only and --rotate-keys together (exit 1).

Exit codes
----------
  0  success — all requested locations have real public IPs (clients configured)
  2  soft success — one or more locations still pending IP (server packages OK)
  1  hard failure — unknown location, flag conflict, missing deps, write errors

Public summary (stdout JSON always redacted)
--------------------------------------------
  secrets_fingerprint   16-hex of sha256(uuid+public_key+short_id+sni) per loc
  counts                requested / ready_or_configured / pending_ip / servers
  pending_ip_locations  locations still missing a real public IP
  keys_preserved / keys_rotated

Idempotency
-----------
  Re-runs preserve location_keys.json unless --rotate-keys.
  short_id is healed to hex if non-hex. hy2 certs are created once and reused.
  JSON configs use atomic write (temp + os.replace).
  secrets_fingerprint is stable across re-runs without --rotate-keys.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Client builder + schema self-check (shared industrial helper)
try:
    from .pcs_client_singbox_v20260802 import (
        CLIENT_CAVEATS,
        PENDING_FORBIDDEN_KEYS,
        PENDING_PUBLIC_KEYS,
        SCHEMA_VERSION as PENDING_SCHEMA_VERSION,
        build_client_config as _build_client_config_impl,
        build_pending_sidecar,
        client_aliases_for,
        filter_pending_public,
        format_client_caveats,
        pending_contains_forbidden,
        reality_flow as _client_reality_flow,
        uses_http_transport as _client_uses_http_transport,
        validate_client_config_schema,
    )
except ImportError:  # script-style: python3 path/to/pcs_materialize_...
    from pcs_client_singbox_v20260802 import (  # type: ignore
        CLIENT_CAVEATS,
        PENDING_FORBIDDEN_KEYS,
        PENDING_PUBLIC_KEYS,
        SCHEMA_VERSION as PENDING_SCHEMA_VERSION,
        build_client_config as _build_client_config_impl,
        build_pending_sidecar,
        client_aliases_for,
        filter_pending_public,
        format_client_caveats,
        pending_contains_forbidden,
        reality_flow as _client_reality_flow,
        uses_http_transport as _client_uses_http_transport,
        validate_client_config_schema,
    )

HOME = Path.home()
SUITE = HOME / "Desktop" / "PhantomCloak Suite"
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"
SINGBOX_CLIENT = STATE / "singbox"
VPS_PKG = STATE / "vps_server_package"
SECRETS = STATE / "secrets"
INVENTORY = STATE / "vps_inventory.json"
META = STATE / "materialize_meta.json"
SOURCE_TEMPLATES = SUITE / "server" / "ready-for-vps"
READONLY_COPY = STATE / "vps_templates_source_copy"
LOCATION_KEYS = SECRETS / "location_keys.json"

# Never echo these field names/values in stdout summaries or public meta.
SECRET_FIELD_NAMES = frozenset(PENDING_FORBIDDEN_KEYS) | frozenset(
    {
        "privkey",
        "secret",
        "token",
        "api_key",
        "passphrase",
    }
)
# PENDING_PUBLIC_KEYS / PENDING_FORBIDDEN_KEYS imported from client helper (canonical).
# schema_version is part of the pending public allowlist (documents pcs.client.pending).


def configure_paths(
    *,
    home: Optional[Path] = None,
    state: Optional[Path] = None,
    suite: Optional[Path] = None,
    industrial: Optional[Path] = None,
) -> None:
    """Rebind path globals for tests or alternate layouts (production defaults unchanged)."""
    global HOME, SUITE, INDUSTRIAL, STATE, SINGBOX_CLIENT, VPS_PKG, SECRETS
    global INVENTORY, META, SOURCE_TEMPLATES, READONLY_COPY, LOCATION_KEYS

    if home is not None:
        HOME = Path(home)
        if suite is None:
            SUITE = HOME / "Desktop" / "PhantomCloak Suite"
        if state is None:
            STATE = HOME / ".pcs_industrial_20260802"
    if suite is not None:
        SUITE = Path(suite)
    if industrial is not None:
        INDUSTRIAL = Path(industrial)
    if state is not None:
        STATE = Path(state)

    SINGBOX_CLIENT = STATE / "singbox"
    VPS_PKG = STATE / "vps_server_package"
    SECRETS = STATE / "secrets"
    INVENTORY = STATE / "vps_inventory.json"
    META = STATE / "materialize_meta.json"
    SOURCE_TEMPLATES = SUITE / "server" / "ready-for-vps"
    READONLY_COPY = STATE / "vps_templates_source_copy"
    LOCATION_KEYS = SECRETS / "location_keys.json"

# Location → SNI / short_id defaults aligned with Suite ready-for-vps
# short_id MUST be hex (sing-box 1.12+); keep Suite SNI choices
LOCATIONS: Dict[str, Dict[str, Any]] = {
    "dubai": {
        "sni": "www.microsoft.com",
        "short_id": "a1b2c3d4",
        "hy2": True,
        "obfs": "delphi-obfs-dubai",
        "transport_http": True,
    },
    "hongkong": {
        "sni": "www.google.com.hk",
        "short_id": "b0a2025a",
        "hy2": True,
        "obfs": "delphi-hk-obfs",
        "transport_http": False,
    },
    "vancouver": {
        "sni": "www.apple.com",
        "short_id": "ca11c0de",
        "hy2": False,
        "obfs": "delphi-obfs-vancouver",
        "transport_http": False,
    },
    # US/GB first-class keys for MVP 5×5 fleet (CEO beginner guide)
    "us": {
        "sni": "www.microsoft.com",
        "short_id": "a5e10001",
        "hy2": False,
        "obfs": "delphi-obfs-us",
        "transport_http": False,
    },
    "gb": {
        "sni": "www.bbc.co.uk",
        "short_id": "bbee0001",
        "hy2": False,
        "obfs": "delphi-obfs-gb",
        "transport_http": False,
        "client_alias": "uk",
    },
    "germany": {
        "sni": "www.spiegel.de",
        "short_id": "de202501",
        "hy2": False,
        "obfs": "delphi-obfs-germany",
        "transport_http": False,
        "client_alias": "frankfurt",
    },
    "bahamas": {
        "sni": "www.microsoft.com",
        "short_id": "ba0a0001",
        "hy2": False,
        "obfs": "delphi-obfs-bahamas",
        "transport_http": False,
    },
    "cayman": {
        "sni": "www.apple.com",
        "short_id": "ca9a0001",
        "hy2": False,
        "obfs": "delphi-obfs-cayman",
        "transport_http": False,
    },
    "mauritius": {
        "sni": "www.google.com",
        "short_id": "aa001001",
        "hy2": False,
        "obfs": "delphi-obfs-mauritius",
        "transport_http": False,
    },
    "seychelles": {
        "sni": "www.google.com",
        "short_id": "5e9c0001",
        "hy2": False,
        "obfs": "delphi-obfs-seychelles",
        "transport_http": False,
    },
}

PLACEHOLDER_IP_RE = re.compile(
    r"YOUR_VPS|your-.*-vps|REPLACE_|changeme|example\.com|pending|TODO|0\.0\.0\.0",
    re.I,
)
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

EXIT_OK = 0
EXIT_HARD = 1
EXIT_PENDING = 2


# ---------------------------------------------------------------------------
# subprocess / crypto helpers
# ---------------------------------------------------------------------------


def _run(cmd: List[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return r.stdout.strip()


def gen_uuid() -> str:
    try:
        return _run(["sing-box", "generate", "uuid"])
    except Exception:
        return str(__import__("uuid").uuid4())


def gen_reality_keypair() -> Tuple[str, str]:
    out = _run(["sing-box", "generate", "reality-keypair"])
    priv = pub = ""
    for line in out.splitlines():
        if line.lower().startswith("privatekey:"):
            priv = line.split(":", 1)[1].strip()
        elif line.lower().startswith("publickey:"):
            pub = line.split(":", 1)[1].strip()
    if not priv or not pub:
        # Never dump sing-box stdout (may contain key material) into logs/exceptions.
        raise RuntimeError(
            "Could not parse reality-keypair from sing-box (output redacted)"
        )
    return priv, pub


def gen_password(n: int = 28) -> str:
    # URL-safe, no ambiguous padding chars
    return secrets.token_urlsafe(n)[:n]


def _chmod_dir_tree(root: Path, dmode: int = 0o700, fmode: int = 0o600) -> None:
    """Best-effort lockdown for secret-bearing directories on macOS.

    Single os.walk (not Path.rglob) — same security modes, less thrash on large trees.
    """
    if not root.exists():
        return
    if root.is_dir():
        try:
            os.chmod(root, dmode)
        except OSError:
            pass
        for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
            try:
                os.chmod(dirpath, dmode)
            except OSError:
                pass
            for name in filenames:
                try:
                    os.chmod(os.path.join(dirpath, name), fmode)
                except OSError:
                    pass
    elif root.is_file():
        try:
            os.chmod(root, fmode)
        except OSError:
            pass


def harden_secret_paths() -> None:
    """Ensure secrets/ and filled VPS package dirs are not world-readable.

    Also rewrites any *.pending.json that accidentally contain forbidden keys
    (private_key / hy2_password / password) down to the public allowlist.
    """
    STATE.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STATE, 0o700)
    except OSError:
        pass
    SECRETS.mkdir(parents=True, exist_ok=True)
    _chmod_dir_tree(SECRETS, 0o700, 0o600)
    if VPS_PKG.exists():
        _chmod_dir_tree(VPS_PKG, 0o700, 0o600)
    if SINGBOX_CLIENT.exists():
        try:
            os.chmod(SINGBOX_CLIENT, 0o700)
        except OSError:
            pass
        # client configs contain hy2 passwords when written — keep 600
        for p in SINGBOX_CLIENT.glob("*.json"):
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass
        # Strip accidental secrets from pending sidecars (public allowlist only).
        sanitize_pending_sidecars(SINGBOX_CLIENT)


def redact_secrets(obj: Any, depth: int = 0) -> Any:
    """Recursively redact secret field values for stdout / public summaries."""
    if depth > 12:
        return "<max-depth>"
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if (
                kl in SECRET_FIELD_NAMES
                or kl.endswith("_private_key")
                or kl.endswith("privkey")
                or kl.endswith("_password")
            ):
                if isinstance(v, str):
                    out[k] = f"<redacted len={len(v)}>"
                elif isinstance(v, bool):
                    # has_hy2_password etc. — booleans are safe presence flags
                    out[k] = v
                else:
                    out[k] = "<redacted>"
            else:
                out[k] = redact_secrets(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [redact_secrets(x, depth + 1) for x in obj[:100]]
    return obj


def secrets_fingerprint(secrets_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Stable hash of *public* material only (inventory / debug).

    Hashed fields per location: uuid, public_key, short_id, sni.
    Never includes private_key, hy2_password, or obfs_password.
    """
    if secrets_data is None:
        if not LOCATION_KEYS.exists():
            return {
                "exists": False,
                "algorithm": "sha256",
                "fingerprint": None,
                "fingerprint_full": None,
                "locations": 0,
                "hashed_fields": "uuid+public_key+short_id+sni",
            }
        try:
            secrets_data = json.loads(LOCATION_KEYS.read_text())
        except Exception as e:
            return {
                "exists": True,
                "error": type(e).__name__,
                "fingerprint": None,
                "algorithm": "sha256",
            }

    public_rows: List[Dict[str, str]] = []
    for loc in sorted((secrets_data.get("locations") or {}).keys()):
        sec = secrets_data["locations"][loc] or {}
        # skip internal bookkeeping keys that are not location entries
        if not isinstance(sec, dict):
            continue
        public_rows.append(
            {
                "loc": loc,
                "uuid": str(sec.get("uuid") or ""),
                "public_key": str(sec.get("public_key") or ""),
                "short_id": str(sec.get("short_id") or ""),
                "sni": str(sec.get("sni") or ""),
            }
        )
    blob = json.dumps(public_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    full = hashlib.sha256(blob).hexdigest()
    return {
        "exists": True,
        "algorithm": "sha256",
        "fingerprint": full[:16],
        "fingerprint_full": full,
        "locations": len(public_rows),
        "hashed_fields": "uuid+public_key+short_id+sni",
        "secrets_path": str(LOCATION_KEYS),
    }


def secrets_age_check(
    max_days: int = 365,
    *,
    secrets_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Optional age signal for location_keys.json (rotation hygiene).

    Pass preloaded ``secrets_data`` to avoid re-reading the secrets file when
    fingerprint was already computed in the same materialize/check-only call.
    """
    data = secrets_data
    if data is None:
        if not LOCATION_KEYS.exists():
            return {
                "exists": False,
                "age_days": None,
                "stale": False,
                "max_days": max_days,
            }
        try:
            data = json.loads(LOCATION_KEYS.read_text())
        except Exception as e:
            return {
                "exists": True,
                "error": type(e).__name__,
                "age_days": None,
                "stale": False,
                "max_days": max_days,
            }

    created = (data or {}).get("created_at") if isinstance(data, dict) else None
    age_days: Optional[float] = None
    source = "mtime"
    if LOCATION_KEYS.exists():
        mtime = LOCATION_KEYS.stat().st_mtime
        age_days = (datetime.now(timezone.utc).timestamp() - mtime) / 86400.0
        source = "mtime"
    if created:
        try:
            ts = str(created).replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            source = "created_at"
        except Exception:
            pass
    if age_days is None and not LOCATION_KEYS.exists():
        return {"exists": False, "age_days": None, "stale": False, "max_days": max_days}
    stale = age_days is not None and age_days > max_days
    return {
        "exists": True,
        "age_days": round(float(age_days), 2) if age_days is not None else None,
        "source": source,
        "stale": bool(stale),
        "max_days": max_days,
        "note": (
            "stale — consider rotating Reality keypairs / hy2 passwords (--rotate-keys)"
            if stale
            else "within max_days"
        ),
    }


def public_materialize_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """Stdout-safe summary: paths, counts, fingerprint — never private keys/passwords.

    Always injects a compact ``counts`` block for operator dashboards:
    requested / ready_or_configured / pending_ip / servers / keys_rotated.
    """
    safe = redact_secrets(result)
    if not isinstance(safe, dict):
        return {"value": safe}  # type: ignore[return-value]
    for k in list(safe.keys()):
        if str(k).lower() in SECRET_FIELD_NAMES:
            del safe[k]

    requested = list(safe.get("locations_requested") or [])
    pending = list(safe.get("pending_ip_locations") or [])
    ready = list(safe.get("ready_locations") or [])
    servers = safe.get("server_configs") or []
    clients = safe.get("client_configs") or []
    rotated = list(safe.get("keys_rotated") or [])
    configured_n = safe.get("configured_clients")
    if configured_n is None:
        configured_n = len(clients) if clients else len(ready)

    safe["counts"] = {
        "locations_requested": len(requested),
        "ready_or_configured": int(configured_n) if configured_n is not None else 0,
        "pending_ip": len(pending),
        "server_configs": len(servers) if isinstance(servers, list) else int(servers or 0),
        "keys_rotated": len(rotated),
        "keys_preserved": bool(safe.get("keys_preserved", not rotated)),
    }
    # Ensure top-level fingerprint + pending are always visible even if sparse result
    if "secrets_fingerprint" not in safe:
        safe["secrets_fingerprint"] = None
    if "pending_ip_locations" not in safe:
        safe["pending_ip_locations"] = pending
    return safe  # type: ignore[return-value]


def format_operator_summary(result: Dict[str, Any]) -> str:
    """Human stderr banner (no secret values). Safe for --json=False runs."""
    mode = result.get("mode") or "materialize"
    fp = result.get("secrets_fingerprint") or "(none)"
    pending = list(result.get("pending_ip_locations") or [])
    ready = list(result.get("ready_locations") or [])
    configured = result.get("configured_clients")
    if configured is None:
        configured = len(result.get("client_configs") or [])
    requested = list(result.get("locations_requested") or [])
    rotated = list(result.get("keys_rotated") or [])
    preserved = result.get("keys_preserved")
    if preserved is None:
        preserved = not rotated
    servers = result.get("server_configs") or []
    n_servers = len(servers) if isinstance(servers, list) else 0
    lines = [
        f"=== PCS materialize ({mode}) ===",
        f"secrets_fingerprint: {fp}",
        (
            f"counts: requested={len(requested)} "
            f"ready_or_configured={configured} "
            f"pending_ip={len(pending)} "
            f"server_configs={n_servers}"
        ),
    ]
    if ready:
        lines.append(f"ready: {', '.join(ready)}")
    if pending:
        lines.append(f"pending_ip_locations: {', '.join(pending)}")
    else:
        lines.append("pending_ip_locations: (none)")
    if rotated:
        lines.append(f"keys_rotated: {', '.join(rotated)}")
    else:
        lines.append(
            f"keys_preserved: {bool(preserved)} "
            "(pass --rotate-keys to regenerate UUID/Reality/hy2)"
        )
    inv = result.get("inventory")
    if inv:
        lines.append(f"inventory: {inv}")
    return "\n".join(lines)


def pending_public_only(
    loc: str,
    sec: Dict[str, Any],
    meta: Optional[Dict[str, Any]] = None,
    *,
    skip_reason: Optional[str] = None,
    written_as: Optional[str] = None,
    alias_of: Optional[str] = None,
) -> Dict[str, Any]:
    """Informative pending.json: public material only (allowlist = PENDING_PUBLIC_KEYS).

    Never private_key / hy2_password / password / obfs_password.
    Always includes schema_version (documents pcs.client.pending shape).
    Includes aliases, sni, hy2, client_shape, caveats, hint for operators —
    not a runnable sing-box config.
    """
    meta = meta or {}
    try:
        raw = build_pending_sidecar(
            loc,
            meta,
            sec,
            inventory_path=str(INVENTORY),
            aliases=client_aliases_for(loc, meta),
            skip_reason=skip_reason,
        )
    except Exception:
        raw = {
            "schema": "pcs.client.pending",
            "schema_version": PENDING_SCHEMA_VERSION,
            "location": loc,
            "status": "pending_vps_ip",
            "configured": False,
            "uuid": sec.get("uuid"),
            "public_key": sec.get("public_key"),
            "aliases": client_aliases_for(loc, meta),
            "inventory_path": str(INVENTORY),
            "skip_reason": skip_reason,
            "caveats": list(CLIENT_CAVEATS),
            "not_a_singbox_config": True,
            "hint": (
                f"Set locations.{loc}.ip in inventory or export "
                f"PCS_VPS_{loc.upper()}=x.x.x.x then re-run materialize"
            ),
        }
    if written_as:
        raw = {**raw, "written_as": written_as}
    if alias_of:
        raw = {**raw, "alias_of": alias_of}
        raw["hint"] = (
            f"Alias of '{alias_of}'. Set locations.{alias_of}.ip "
            f"(or PCS_VPS_{alias_of.upper()}) then re-run materialize; "
            f"full {written_as or 'alias'}.json is written with a real public IP."
        )
    # Hard allowlist — drop any accidental private/secret fields from helpers
    out = filter_pending_public(raw)
    out.setdefault("schema", "pcs.client.pending")
    out.setdefault("schema_version", PENDING_SCHEMA_VERSION)
    out.setdefault("location", loc)
    out.setdefault("status", "pending_vps_ip")
    out.setdefault("uuid", sec.get("uuid"))
    out.setdefault("public_key", sec.get("public_key"))
    out.setdefault("configured", False)
    out.setdefault("not_a_singbox_config", True)
    # Final pass after setdefaults (still no secrets)
    return filter_pending_public(out)


def write_pending_json(path: Path, obj: Any, mode: int = 0o600) -> None:
    """Atomic write for *.pending.json — always hard-allowlist filtered first.

    Guarantees on-disk sidecar never contains private_key / hy2_password / password.
    """
    safe = filter_pending_public(obj if isinstance(obj, dict) else {})
    write_json(path, safe, mode=mode)


def sanitize_pending_sidecars(
    directory: Optional[Path] = None,
) -> Dict[str, Any]:
    """Rewrite existing *.pending.json to public allowlist only.

    Strips private_key / hy2_password / password / unknown keys if present.
    Never logs secret values — only file names and counts of stripped key names.
    Returns {scanned, rewritten, stripped_keys: {path_name: [key,...]}, errors}.
    """
    root = Path(directory) if directory is not None else SINGBOX_CLIENT
    report: Dict[str, Any] = {
        "directory": str(root),
        "scanned": 0,
        "rewritten": 0,
        "clean": 0,
        "stripped_keys": {},
        "errors": [],
    }
    if not root.is_dir():
        return report
    for path in sorted(root.glob("*.pending.json")):
        report["scanned"] += 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            report["errors"].append(f"{path.name}: read {type(e).__name__}")
            continue
        if not isinstance(raw, dict):
            report["errors"].append(f"{path.name}: not an object")
            continue
        forbidden = pending_contains_forbidden(raw)
        extra = [k for k in raw if k not in PENDING_PUBLIC_KEYS]
        # Rewrite if any forbidden or non-allowlisted keys (or missing schema_version)
        needs = bool(forbidden or extra) or "schema_version" not in raw
        if not needs:
            # Still ensure mode 0600
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            report["clean"] += 1
            continue
        safe = filter_pending_public(raw)
        safe.setdefault("schema", "pcs.client.pending")
        safe.setdefault("schema_version", PENDING_SCHEMA_VERSION)
        safe = filter_pending_public(safe)
        # Record only key *names* that were dropped — never values
        dropped = sorted(set(forbidden) | set(extra))
        try:
            write_json(path, safe, mode=0o600)
            report["rewritten"] += 1
            if dropped:
                report["stripped_keys"][path.name] = dropped
        except Exception as e:
            report["errors"].append(f"{path.name}: write {type(e).__name__}")
    return report


def ensure_hy2_tls_certs(loc: str, create: bool = True) -> Tuple[Optional[Path], Optional[Path]]:
    """Self-signed cert for Hysteria2 (sing-box 1.12+ requires TLS on hy2).

    Created once; subsequent runs reuse existing fullchain.pem + privkey.pem.
    If create=False (check-only / plan mode): pure read — no mkdir, no chmod,
    no openssl. Returns (None, None) when missing.
    """
    cert_dir = SECRETS / "hy2_certs" / loc
    cert = cert_dir / "fullchain.pem"
    key = cert_dir / "privkey.pem"
    if cert.exists() and key.exists():
        if create:
            # Harden only when allowed to mutate (apply path)
            try:
                os.chmod(key, 0o600)
                os.chmod(cert, 0o600)
                os.chmod(cert_dir, 0o700)
            except OSError:
                pass
        return cert, key
    if not create:
        return None, None

    SECRETS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SECRETS, 0o700)
    except OSError:
        pass
    cert_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SECRETS / "hy2_certs", 0o700)
        os.chmod(cert_dir, 0o700)
    except OSError:
        pass
    # openssl self-signed, ~2y, SAN DNS:localhost
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "825",
            "-nodes",
            "-subj",
            f"/CN=pcs-{loc}.local",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    os.chmod(key, 0o600)
    os.chmod(cert, 0o600)
    return cert, key


# ---------------------------------------------------------------------------
# IP / inventory
# ---------------------------------------------------------------------------


def is_real_ip(value: Optional[str]) -> bool:
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if PLACEHOLDER_IP_RE.search(v):
        return False
    if not IPV4_RE.match(v):
        # allow hostname if it is not a placeholder
        if "." in v and not PLACEHOLDER_IP_RE.search(v) and " " not in v:
            if v.endswith(".local"):
                return False
            # dotted pure-numeric but not valid IPv4 (e.g. 1.2.3) is not a hostname
            if re.fullmatch(r"[\d.]+", v):
                return False
            return True
        return False
    parts = [int(x) for x in v.split(".")]
    if any(p > 255 for p in parts):
        return False
    # reject localhost / RFC1918 / link-local / documentation ranges as "production VPS"
    a, b = parts[0], parts[1]
    if a == 127 or a == 0 or a == 10:
        return False
    if a == 192 and b == 168:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 169 and b == 254:
        return False
    # TEST-NET / docs
    if a == 198 and b == 51 and parts[2] == 100:
        return False
    if a == 203 and b == 0 and parts[2] == 113:
        return False
    if a == 192 and b == 0 and parts[2] == 2:
        return False
    return True


def _skip_reason(loc: str, inv_loc: Dict[str, Any], ip: str) -> str:
    """Human reason a location is not deployable."""
    if inv_loc.get("enabled", True) is False:
        return f"{loc}: skipped (enabled=false in inventory)"
    if not ip:
        return (
            f"{loc}: skipped (no IP — set locations.{loc}.ip or pool[] in {INVENTORY} "
            f"or export PCS_VPS_{loc.upper()}=x.x.x.x)"
        )
    if PLACEHOLDER_IP_RE.search(ip):
        return f"{loc}: skipped (placeholder IP {ip!r})"
    if not is_real_ip(ip):
        return f"{loc}: skipped (not a public/production IP: {ip!r})"
    return f"{loc}: skipped (unknown reason)"


def resolve_location_primary(
    inv_loc: Optional[Dict[str, Any]],
    *,
    default_user: str = "root",
) -> Tuple[str, str, Dict[str, Any]]:
    """Resolve primary public IP + ssh_user from a location inventory entry.

    Read order (first real public IP wins):
      1. ``locations.<loc>.ip`` (v1 single-IP + v2 primary mirror)
      2. first enabled ``pool[]`` member with a real public IP (inventory v2)

    Returns ``(ip, ssh_user, member_meta)`` where ``member_meta`` is empty when
    the primary came only from the top-level ``ip`` field, else the pool member dict.

    Client materialize uses ``location_pool_ips`` for full multi-outbound
    (reality-out-1..N + urltest/selector when pool has 2+). This helper remains
    the primary/deploy slot resolver (deploy_filled, check-only ready list).
    """
    inv_loc = inv_loc if isinstance(inv_loc, dict) else {}
    default_user = (default_user or "root").strip() or "root"
    top_ip = (inv_loc.get("ip") or "").strip()
    top_user = (inv_loc.get("ssh_user") or default_user).strip() or default_user
    if is_real_ip(top_ip):
        # Prefer matching pool member metadata when primary mirrors pool[0]
        for m in inv_loc.get("pool") or []:
            if not isinstance(m, dict) or m.get("enabled", True) is False:
                continue
            if (m.get("ip") or "").strip() == top_ip:
                return (
                    top_ip,
                    (m.get("ssh_user") or top_user).strip() or top_user,
                    m,
                )
        return top_ip, top_user, {}

    for m in inv_loc.get("pool") or []:
        if not isinstance(m, dict) or m.get("enabled", True) is False:
            continue
        mip = (m.get("ip") or "").strip()
        if not is_real_ip(mip):
            continue
        user = (m.get("ssh_user") or top_user).strip() or top_user
        return mip, user, m
    return "", top_user, {}


def load_or_init_inventory(
    *,
    force_env: bool = False,
    persist: bool = True,
) -> Dict[str, Any]:
    """Load inventory. Env PCS_VPS_<LOC> overlays in memory.

    force_env=True also persists env IPs into the inventory file (atomic).
    Never invents IPs — empty stays empty.

    Accepts inventory v1 (single ip) and v2 (pool[] + primary ip mirror).
    Env overlay updates the primary ``ip`` field (and pool[0] if present) so
    pool-aware readers still see the env value as primary.
    """
    created = False
    if INVENTORY.exists():
        data = json.loads(INVENTORY.read_text())
        # In-memory v1→v2 shape (pool[]) without forcing a rewrite unless we persist
        try:
            from shared.pcs_inventory_v2_v20260802 import migrate_v1_to_v2
        except ImportError:
            try:
                from pcs_inventory_v2_v20260802 import migrate_v1_to_v2  # type: ignore
            except ImportError:
                migrate_v1_to_v2 = None  # type: ignore
        if migrate_v1_to_v2 is not None and int(data.get("version") or 1) < 2:
            data = migrate_v1_to_v2(data)
        elif migrate_v1_to_v2 is not None and "pool" not in (
            (data.get("locations") or {}).get(next(iter(LOCATIONS), ""), {}) or {}
        ):
            # Mixed/partial: ensure pool keys exist for known locations
            data = migrate_v1_to_v2(data)
    else:
        data = {
            "version": 2,
            "ssh_user": "root",
            "note": (
                "Set locations.<loc>.ip (primary) and/or pool[] of owned public IPv4. "
                "Env override: PCS_VPS_<LOCATION> e.g. PCS_VPS_DUBAI=x.x.x.x "
                "(use --force-inventory-env to persist env into this file). "
                "Never invent IPs."
            ),
            "locations": {
                loc: {"ip": "", "ssh_user": "", "enabled": True, "pool": []}
                for loc in LOCATIONS
            },
        }
        created = True

    locs = data.setdefault("locations", {})
    for loc in LOCATIONS:
        locs.setdefault(
            loc, {"ip": "", "ssh_user": "", "enabled": True, "pool": []}
        )
        if "pool" not in locs[loc] or not isinstance(locs[loc].get("pool"), list):
            locs[loc]["pool"] = []

    env_applied: List[str] = []
    for loc in LOCATIONS:
        env_key = f"PCS_VPS_{loc.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None or not str(env_val).strip():
            continue
        env_ip = str(env_val).strip()
        # Always overlay in memory for this run (primary)
        locs[loc]["ip"] = env_ip
        locs[loc]["enabled"] = True
        # Keep pool[0] in sync when a pool already exists so readers agree
        pool = locs[loc].get("pool") or []
        if pool and isinstance(pool[0], dict):
            pool[0]["ip"] = env_ip
            pool[0]["enabled"] = True
        env_applied.append(loc)

    if persist and (created or (force_env and env_applied)):
        INVENTORY.parent.mkdir(parents=True, exist_ok=True)
        write_json(INVENTORY, data, mode=0o600)
        data["_env_persisted"] = env_applied if force_env else []
    else:
        data["_env_persisted"] = []
    data["_env_applied_memory"] = env_applied
    return data


# ---------------------------------------------------------------------------
# secrets lifecycle (idempotent)
# ---------------------------------------------------------------------------


def _is_hex_short_id(s: str) -> bool:
    return bool(s) and bool(HEX_RE.match(s))


def _heal_short_id(sid: str, fallback: str) -> str:
    """Return hex short_id; heal non-hex to Suite default (or strip non-hex)."""
    if _is_hex_short_id(sid):
        return sid.lower() if sid != sid.lower() and all(c in "0123456789abcdefABCDEF" for c in sid) else sid
    # Prefer canonical Suite default when present and hex
    if _is_hex_short_id(fallback):
        return fallback
    # Last resort: hex-encode first 4 bytes of random
    return secrets.token_hex(4)


def _new_loc_secret(loc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    priv, pub = gen_reality_keypair()
    return {
        "uuid": gen_uuid(),
        "private_key": priv,
        "public_key": pub,
        "short_id": meta["short_id"],
        "hy2_password": gen_password(32),
        "obfs_password": meta["obfs"],
        "sni": meta["sni"],
    }


def _rotate_loc_secret(existing: Dict[str, Any], loc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Rotate crypto material; keep/heal short_id, sni, obfs defaults."""
    priv, pub = gen_reality_keypair()
    sid = _heal_short_id(str(existing.get("short_id") or ""), meta["short_id"])
    return {
        "uuid": gen_uuid(),
        "private_key": priv,
        "public_key": pub,
        "short_id": sid,
        "hy2_password": gen_password(32),
        "obfs_password": existing.get("obfs_password") or meta["obfs"],
        "sni": meta["sni"],
        "rotated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_or_create_secrets(
    *,
    rotate: bool = False,
    only_locations: Optional[Sequence[str]] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """Load secrets; preserve keys unless rotate=True.

    Heals non-hex short_id. Adds missing locations without touching others.
    """
    SECRETS.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SECRETS, 0o700)
    except OSError:
        pass
    target = set(only_locations) if only_locations else set(LOCATIONS.keys())
    changed = False
    rotated: List[str] = []
    healed: List[str] = []

    if LOCATION_KEYS.exists():
        data = json.loads(LOCATION_KEYS.read_text())
    else:
        data = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "locations": {},
        }
        changed = True

    locs = data.setdefault("locations", {})
    # When only_locations is set, do not run sing-box generate for other missing
    # locations (avoids 7 extra reality-keypair subprocesses on --location X).
    scoped = only_locations is not None
    for loc, meta in LOCATIONS.items():
        if loc not in locs:
            # Generate crypto only for requested targets; full runs (only_locations=None)
            # still create all locations when persisting.
            if loc not in target and scoped:
                continue
            if persist or loc in target:
                locs[loc] = _new_loc_secret(loc, meta)
                changed = True
            continue

        entry = locs[loc]
        # Heal short_id always (safe, non-destructive of real keys)
        sid = str(entry.get("short_id") or "")
        healed_sid = _heal_short_id(sid, meta["short_id"])
        if healed_sid != sid:
            entry["short_id"] = healed_sid
            healed.append(loc)
            changed = True
        # Keep SNI aligned with LOCATIONS table
        if entry.get("sni") != meta["sni"]:
            entry["sni"] = meta["sni"]
            changed = True
        if not entry.get("obfs_password"):
            entry["obfs_password"] = meta["obfs"]
            changed = True

        if rotate and loc in target:
            locs[loc] = _rotate_loc_secret(entry, loc, meta)
            rotated.append(loc)
            changed = True

    if persist and changed:
        write_json(LOCATION_KEYS, data, mode=0o600)
    elif LOCATION_KEYS.exists():
        try:
            os.chmod(LOCATION_KEYS, 0o600)
        except OSError:
            pass

    data["_rotated"] = rotated
    data["_healed_short_id"] = healed
    data["_secrets_changed"] = changed
    return data


# ---------------------------------------------------------------------------
# templates / config builders
# ---------------------------------------------------------------------------


def copy_source_templates() -> int:
    """Copy Suite templates into industrial state + package mirror. Never writes Suite."""
    READONLY_COPY.mkdir(parents=True, exist_ok=True)
    VPS_PKG.mkdir(parents=True, exist_ok=True)
    n = 0
    if SOURCE_TEMPLATES.exists():
        for p in SOURCE_TEMPLATES.glob("*.json"):
            dest = READONLY_COPY / p.name
            shutil.copy2(p, dest)
            n += 1
    # industrial tree mirror (docs / packaging only — not Suite overwrite)
    mirror = INDUSTRIAL / "server_vps_package_v20260802" / "templates_source_copy"
    mirror.mkdir(parents=True, exist_ok=True)
    if SOURCE_TEMPLATES.exists():
        for p in SOURCE_TEMPLATES.glob("*.json"):
            shutil.copy2(p, mirror / p.name)
    return n


def _uses_http_transport(meta: Dict[str, Any]) -> bool:
    """HTTP transport is Suite-legacy (dubai only). Vision requires raw TCP."""
    return _client_uses_http_transport(meta)


def _reality_flow(meta: Dict[str, Any]) -> Optional[str]:
    """Best-practice: xtls-rprx-vision on raw TCP Reality; omit with HTTP transport."""
    return _client_reality_flow(meta)


def build_server_config(
    loc: str, meta: Dict[str, Any], sec: Dict[str, Any], *, create_certs: bool = True
) -> Dict[str, Any]:
    """Filled VPS config: VLESS Reality (+ optional HTTP transport) + optional Hy2:8443.

    sing-box 1.12–1.13:
    - short_id must be hex; handshake.server matches server_name (SNI)
    - no geosite route rules
    - Vision flow only without multiplexed transports (not with type=http)
    - Hy2 requires TLS (self-signed industrial certs; paths rewritten on deploy)
    """
    user: Dict[str, Any] = {"name": "pcs", "uuid": sec["uuid"]}
    flow = _reality_flow(meta)
    if flow:
        user["flow"] = flow

    vless: Dict[str, Any] = {
        "type": "vless",
        "tag": "vless-reality",
        "listen": "::",
        "listen_port": 443,
        "users": [user],
        "tls": {
            "enabled": True,
            "server_name": sec["sni"],
            "reality": {
                "enabled": True,
                # Handshake target must match advertised SNI for believable TLS
                "handshake": {"server": sec["sni"], "server_port": 443},
                "private_key": sec["private_key"],
                "short_id": [sec["short_id"]],
            },
        },
    }
    if _uses_http_transport(meta):
        vless["transport"] = {"type": "http"}

    inbounds: List[Dict[str, Any]] = [vless]
    if meta.get("hy2"):
        cert, key = ensure_hy2_tls_certs(loc, create=create_certs)
        if cert is not None and key is not None:
            # Copy certs next to server config so scp package is self-contained
            pkg_cert_dir = VPS_PKG / "hy2_certs" / loc
            pkg_cert_dir.mkdir(parents=True, exist_ok=True)
            pkg_cert = pkg_cert_dir / "fullchain.pem"
            pkg_key = pkg_cert_dir / "privkey.pem"
            if create_certs:
                shutil.copy2(cert, pkg_cert)
                shutil.copy2(key, pkg_key)
            # Local absolute paths so `sing-box check` works on Mac; deploy script
            # rewrites to /etc/sing-box/hy2_certs/<loc>/ on the VPS.
            inbounds.append(
                {
                    "type": "hysteria2",
                    "tag": "hy2-in",
                    "listen": "::",
                    "listen_port": 8443,
                    "users": [{"name": "pcs", "password": sec["hy2_password"]}],
                    "obfs": {"type": "salamander", "password": sec["obfs_password"]},
                    "tls": {
                        "enabled": True,
                        "certificate_path": str(pkg_cert if pkg_cert.exists() else cert),
                        "key_path": str(pkg_key if pkg_key.exists() else key),
                    },
                }
            )

    # No geosite rules — removed in sing-box 1.12+. Keep block for explicit reject tags.
    return {
        "log": {"level": "warn"},
        "inbounds": inbounds,
        "outbounds": [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
    }


def build_client_config(
    loc: str,
    meta: Dict[str, Any],
    sec: Dict[str, Any],
    server_ip: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Production-grade client for sing-box 1.12–1.13 (schema-checked by materialize).

    Implemented in ``pcs_client_singbox_v20260802``:
    - selector + optional urltest (auto when Reality+Hy2 or multi-IP pool), direct/block
    - multi-pool: reality-out-1..N (+ hysteria-out-1..N if Hy2) when server_ips has 2+
    - single-IP: classic reality-out / hysteria-out (no numeric suffix)
    - private bypass via ip_is_private; sniff via route action
    - TUN ``address[]`` (not inet4_address); clash_api off by default
    - Reality: utls chrome, vision flow on raw TCP, multiplex off, packet_encoding xudp
    - Hy2: tls.insecure for industrial self-signed certs

    Pass ``server_ips=[...]`` for multi-IP pools; ``server_ip`` alone keeps single shape.
    """
    return _build_client_config_impl(loc, meta, sec, server_ip, **kwargs)


def location_pool_ips(inv_loc: Optional[Dict[str, Any]]) -> List[str]:
    """Enabled real public IPs for a location (inventory v2 pool[] or legacy ip).

    Order: pool members (enabled + is_real_ip), else single legacy ``ip``.
    Dedupes while preserving order. Never invents addresses.
    """
    if not isinstance(inv_loc, dict):
        return []
    ips: List[str] = []
    seen: set = set()
    pool = inv_loc.get("pool")
    if isinstance(pool, list) and pool:
        for m in pool:
            if not isinstance(m, dict):
                continue
            if m.get("enabled", True) is False:
                continue
            ip = (m.get("ip") or "").strip()
            if not ip or not is_real_ip(ip):
                continue
            if ip in seen:
                continue
            seen.add(ip)
            ips.append(ip)
    if ips:
        return ips
    ip = (inv_loc.get("ip") or "").strip()
    if ip and is_real_ip(ip):
        return [ip]
    return []


def client_shape_summary(loc: str, meta: Dict[str, Any]) -> Dict[str, Any]:
    """Audit-friendly client shape metadata (no server IP — safe for pending sidecars)."""
    flow = _reality_flow(meta)
    multi = bool(meta.get("hy2"))  # Reality + Hy2 → urltest auto
    return {
        "location": loc,
        "aliases": client_aliases_for(loc, meta),
        "protocol": "vless-reality",
        "server_port": 443,
        "flow": flow or "",
        "utls_fingerprint": "chrome",
        "multiplex_enabled": False,
        "packet_encoding": "xudp",
        "transport_http": _uses_http_transport(meta),
        "hy2": bool(meta.get("hy2")),
        "hy2_port": 8443 if meta.get("hy2") else None,
        "hy2_tls_insecure": True if meta.get("hy2") else None,
        "selector": True,
        "urltest": multi,  # optional; auto-on for multi-transport
        "urltest_auto_multi_pool": True,  # pool 2+ IPs → reality-out-1..N + urltest
        "multi_pool_tags": "reality-out-1..N (+ hysteria-out-1..N if hy2)",
        "single_ip_tags": "reality-out (+ hysteria-out if hy2)",
        "direct_block": True,
        "ip_is_private_bypass": True,
        "clash_api_default": False,
        "sniff": "route_action",
        "tun_address_field": "address",
        "tun_requires_root": True,
        "dns": "https://1.1.1.1/dns-query via proxy",
        "sni": meta.get("sni"),
        "short_id_hex": meta.get("short_id"),
        "caveats": list(CLIENT_CAVEATS),
    }


# ---------------------------------------------------------------------------
# atomic JSON I/O
# ---------------------------------------------------------------------------


def write_json(path: Path, obj: Any, mode: int = 0o600) -> None:
    """Atomic JSON write: temp file in same dir + os.replace + chmod."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        # Ensure final mode (replace may preserve prior perms on some FS)
        os.chmod(path, mode)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def write_text_atomic(path: Path, text: str, mode: int = 0o600) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        os.chmod(path, mode)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# deploy script generation (industrial bootstrap + path rewrite)
# ---------------------------------------------------------------------------


def industrial_scripts_dir() -> Path:
    return INDUSTRIAL / "server_vps_package_v20260802" / "scripts"


def sync_deploy_scripts_into_package() -> List[str]:
    """Copy industrial deploy/bootstrap/rewrite scripts into state VPS package."""
    src_dir = industrial_scripts_dir()
    dest_dir = VPS_PKG / "scripts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    names = [
        "pcs_remote_bootstrap_singbox_v20260802.sh",
        "pcs_deploy_one_v20260802.sh",
        "pcs_deploy_pool_v20260802.sh",
        "pcs_rewrite_singbox_paths_v20260802.py",
        "pcs_compose_deploy_v20260802.py",
    ]
    copied: List[str] = []
    for name in names:
        src = src_dir / name
        if not src.is_file():
            continue
        dest = dest_dir / name
        shutil.copy2(src, dest)
        os.chmod(dest, 0o700)
        copied.append(str(dest))
    return copied


def rewrite_server_config_for_vps(src: Path, location: str, dest: Path) -> Path:
    """Robust Mac→/etc/sing-box path rewrite via industrial Python rewriter."""
    rewriter = industrial_scripts_dir() / "pcs_rewrite_singbox_paths_v20260802.py"
    if not rewriter.is_file():
        rewriter = VPS_PKG / "scripts" / "pcs_rewrite_singbox_paths_v20260802.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if rewriter.is_file():
        subprocess.run(
            [
                sys.executable,
                str(rewriter),
                "--in",
                str(src),
                "--out",
                str(dest),
                "--location",
                location,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return dest
    # Fallback if script missing
    data = json.loads(src.read_text(encoding="utf-8"))
    for ib in data.get("inbounds", []):
        tls = ib.get("tls") or {}
        if "certificate_path" in tls or "key_path" in tls:
            tls["certificate_path"] = (
                f"/etc/sing-box/hy2_certs/{location}/fullchain.pem"
            )
            tls["key_path"] = f"/etc/sing-box/hy2_certs/{location}/privkey.pem"
            ib["tls"] = tls
    write_text_atomic(dest, json.dumps(data, indent=2) + "\n", mode=0o600)
    return dest


def _deploy_block_for_loc(
    loc: str,
    meta: Dict[str, Any],
    ip: str,
    user: str,
) -> List[str]:
    """Emit deploy_one invocation (path rewrite + remote bootstrap inside)."""
    target = f"{user}@{ip}"
    return [
        f'echo "=== Deploy {loc} → {target} ==="',
        'if [[ "${PCS_DRY_RUN:-0}" == "1" || "${1:-}" == "--dry-run" || "${1:-}" == "-n" ]]; then',
        f'  bash "$DEPLOY_ONE" --dry-run "{target}" "{loc}"',
        "else",
        f'  bash "$DEPLOY_ONE" "{target}" "{loc}"',
        "fi",
        "",
    ]


def build_deploy_script(
    selected: Sequence[str],
    inventory: Dict[str, Any],
    default_user: str,
) -> Tuple[str, List[str], List[str]]:
    """Return (script_text, deployable_locs, skipped_reasons).

    Uses pcs_deploy_one_v20260802.sh for each real-IP location (robust
    Mac→/etc/sing-box rewrite + remote bootstrap). Empty inventory → safe no-ops.
    Supports: bash deploy_filled_to_vps.sh --dry-run
    """
    scripts_dir = VPS_PKG / "scripts"
    industrial_one = industrial_scripts_dir() / "pcs_deploy_one_v20260802.sh"
    deploy_lines: List[str] = [
        "#!/usr/bin/env bash",
        "# Generated industrial multi-VPS deploy (path rewrite + remote bootstrap)",
        f"# Generated: {datetime.now(timezone.utc).isoformat()}",
        "# Usage:",
        f"#   bash {VPS_PKG}/deploy_filled_to_vps.sh           # live (needs inventory IPs)",
        f"#   bash {VPS_PKG}/deploy_filled_to_vps.sh --dry-run # plan only / no-ops",
        f"#   {scripts_dir}/pcs_deploy_one_v20260802.sh [--dry-run] user@host location",
        "# Placeholders are never invented. No real IPs required for dry-run demos.",
        "set -euo pipefail",
        f'PKG="{VPS_PKG}"',
        f'SCRIPTS="{scripts_dir}"',
        'DEPLOY_ONE="${SCRIPTS}/pcs_deploy_one_v20260802.sh"',
        f'if [[ ! -f "$DEPLOY_ONE" ]]; then DEPLOY_ONE="{industrial_one}"; fi',
        'DRY=0',
        'for a in "$@"; do case "$a" in --dry-run|-n) DRY=1 ;; esac; done',
        'export PCS_DRY_RUN="$DRY"',
        'echo "[deploy_filled] pkg=$PKG dry_run=$DRY deploy_one=$DEPLOY_ONE"',
        "",
    ]
    deployable: List[str] = []
    skipped: List[str] = []

    for loc in selected:
        inv_loc = inventory.get("locations", {}).get(loc, {}) or {}
        # Primary only (v1 single deploy slot). Full pool → pcs_deploy_pool_*.sh
        ip, user, _member = resolve_location_primary(
            inv_loc, default_user=default_user
        )
        enabled = inv_loc.get("enabled", True)
        meta = LOCATIONS[loc]

        if enabled and is_real_ip(ip):
            deployable.append(loc)
            deploy_lines.extend(_deploy_block_for_loc(loc, meta, ip, user))
        else:
            reason = _skip_reason(loc, inv_loc, ip)
            skipped.append(reason)
            deploy_lines.append(f"# NO-OP {reason}")
            deploy_lines.append(f'echo "NO-OP: {reason}"')
            deploy_lines.append("")

    if not deployable:
        deploy_lines.append(
            'echo "No locations with real IPs — edit inventory or set PCS_VPS_<LOC> '
            'and re-run materialize. Dry-run single host:"'
        )
        deploy_lines.append(
            f'echo "  bash $DEPLOY_ONE --dry-run root@203.0.113.10 dubai"'
        )
        # Soft exit 0 so automation can still run --dry-run demos without failure
        deploy_lines.append('if [[ "$DRY" -eq 1 ]]; then')
        deploy_lines.append(
            '  bash "$DEPLOY_ONE" --dry-run root@203.0.113.10 dubai || true'
        )
        deploy_lines.append('  echo "PCS_DEPLOY_FILLED_DRY_RUN=OK (no inventory IPs)"')
        deploy_lines.append("  exit 0")
        deploy_lines.append("fi")
        deploy_lines.append("exit 2")
    else:
        deploy_lines.append(
            f'echo "Deploy blocks emitted for: {", ".join(deployable)}"'
        )
        if skipped:
            deploy_lines.append(
                f'echo "Skipped ({len(skipped)}): see NO-OP lines above"'
            )
        deploy_lines.append(
            'if [[ "$DRY" -eq 1 ]]; then echo "PCS_DEPLOY_FILLED_DRY_RUN=OK"; fi'
        )

    return "\n".join(deploy_lines) + "\n", deployable, skipped


# ---------------------------------------------------------------------------
# check-only / materialize
# ---------------------------------------------------------------------------


def check_only(
    *,
    only_locations: Optional[Sequence[str]] = None,
    force_inventory_env: bool = False,
) -> Dict[str, Any]:
    """Read-only status; no writes (inventory file may already exist)."""
    selected = list(only_locations) if only_locations else list(LOCATIONS.keys())
    for loc in selected:
        if loc not in LOCATIONS:
            raise ValueError(f"unknown location: {loc}")

    # Load inventory without creating if missing; never persist env (read-only plan).
    if INVENTORY.exists():
        inventory = json.loads(INVENTORY.read_text())
        inventory.pop("_missing_file", None)
    else:
        inventory = {
            "locations": {
                loc: {"ip": "", "ssh_user": "", "enabled": True} for loc in LOCATIONS
            },
            "_missing_file": True,
        }
    locs = inventory.setdefault("locations", {})
    for loc in LOCATIONS:
        locs.setdefault(loc, {"ip": "", "ssh_user": "", "enabled": True})
    env_applied: List[str] = []
    for loc in LOCATIONS:
        env_key = f"PCS_VPS_{loc.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is None or not str(env_val).strip():
            continue
        locs[loc]["ip"] = str(env_val).strip()
        locs[loc]["enabled"] = True
        env_applied.append(loc)
    inventory["_env_applied_memory"] = env_applied
    inventory["_env_persisted"] = []
    # --force-inventory-env with --check-only: report would-persist, still no write
    inventory["_env_would_persist"] = env_applied if force_inventory_env and env_applied else []

    secrets_status: Dict[str, Any] = {"exists": LOCATION_KEYS.exists(), "locations": {}}
    # One secrets file read for status + fingerprint + age (no triple open)
    sec_data: Optional[Dict[str, Any]] = None
    if LOCATION_KEYS.exists():
        try:
            sec_data = json.loads(LOCATION_KEYS.read_text())
        except Exception:
            sec_data = None
        if sec_data is not None:
            for loc in selected:
                entry = (sec_data.get("locations") or {}).get(loc)
                if not entry:
                    secrets_status["locations"][loc] = {"present": False}
                    continue
                sid = str(entry.get("short_id") or "")
                # Public material + presence flags only — never private_key / hy2_password values.
                secrets_status["locations"][loc] = {
                    "present": True,
                    "uuid": entry.get("uuid"),
                    "public_key": entry.get("public_key"),
                    "short_id": sid,
                    "short_id_hex": _is_hex_short_id(sid),
                    "sni": entry.get("sni"),
                    "has_private_key": bool(entry.get("private_key")),
                    "has_hy2_password": bool(entry.get("hy2_password")),
                }
        else:
            for loc in selected:
                secrets_status["locations"][loc] = {"present": False}
    else:
        for loc in selected:
            secrets_status["locations"][loc] = {"present": False}

    hy2_status: Dict[str, Any] = {}
    pending: List[str] = []
    ready: List[str] = []
    skipped: List[str] = []

    for loc in selected:
        meta = LOCATIONS[loc]
        inv_loc = inventory.get("locations", {}).get(loc, {}) or {}
        ip, _user, _member = resolve_location_primary(inv_loc)
        enabled = inv_loc.get("enabled", True)
        if meta.get("hy2"):
            cert, key = ensure_hy2_tls_certs(loc, create=False)
            hy2_status[loc] = {
                "required": True,
                "cert_exists": cert is not None and key is not None,
                "cert": str(cert) if cert else None,
            }
        else:
            hy2_status[loc] = {"required": False}

        if enabled and is_real_ip(ip):
            ready.append(loc)
        else:
            pending.append(loc)
            skipped.append(_skip_reason(loc, inv_loc, ip))

    fp = secrets_fingerprint(sec_data)
    age = secrets_age_check(secrets_data=sec_data)
    # Presence-only: never invent or regenerate keys in check-only.
    secrets_present = sum(
        1
        for loc in selected
        if (secrets_status.get("locations") or {}).get(loc, {}).get("present")
    )
    hy2_missing = [
        loc
        for loc, st in hy2_status.items()
        if st.get("required") and not st.get("cert_exists")
    ]
    result = {
        "ok": True,
        "mode": "check-only",
        "mutated": False,
        "locations_requested": selected,
        "ready_locations": ready,
        "pending_ip_locations": pending,
        "configured_clients": len(ready),  # inventory-ready count (plan view)
        "skip_reasons": skipped,
        "secrets": secrets_status,
        "secrets_present_count": secrets_present,
        "secrets_fingerprint": fp.get("fingerprint"),
        "secrets_fingerprint_full": fp.get("fingerprint_full"),
        "secrets_fingerprint_meta": {
            "algorithm": fp.get("algorithm"),
            "hashed_fields": fp.get("hashed_fields"),
            "locations": fp.get("locations"),
        },
        "secrets_age": age,
        "hy2_certs": hy2_status,
        "hy2_certs_missing": hy2_missing,
        "keys_preserved": True,
        "keys_rotated": [],
        "server_configs": [],  # check-only never writes packages
        "client_configs": [],
        "inventory": str(INVENTORY),
        "inventory_exists": INVENTORY.exists(),
        "env_applied_memory": inventory.get("_env_applied_memory", []),
        "env_would_persist": inventory.get("_env_would_persist") or [],
        "force_inventory_env": force_inventory_env,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def materialize(
    *,
    rotate_keys: bool = False,
    only_locations: Optional[Sequence[str]] = None,
    force_inventory_env: bool = False,
) -> Dict[str, Any]:
    selected = list(only_locations) if only_locations else list(LOCATIONS.keys())
    for loc in selected:
        if loc not in LOCATIONS:
            raise ValueError(f"unknown location: {loc}")

    STATE.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(STATE, 0o700)
    except OSError:
        pass
    SINGBOX_CLIENT.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(SINGBOX_CLIENT, 0o700)
    except OSError:
        pass
    VPS_PKG.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(VPS_PKG, 0o700)
    except OSError:
        pass

    n_templates = copy_source_templates()
    secrets_data = load_or_create_secrets(
        rotate=rotate_keys,
        only_locations=selected,
        persist=True,
    )
    harden_secret_paths()
    inventory = load_or_init_inventory(force_env=force_inventory_env, persist=True)
    default_user = inventory.get("ssh_user") or "root"

    # Sync industrial deploy/bootstrap/rewrite scripts into state package
    scripts_copied = sync_deploy_scripts_into_package()

    server_written: List[str] = []
    client_written: List[str] = []
    client_pending_ip: List[str] = []
    skip_reasons: List[str] = []
    vps_path_previews: List[str] = []
    client_schema_reports: List[Dict[str, Any]] = []
    schema_failures: List[str] = []
    keys_preserved = not rotate_keys
    # Optional live sing-box binary check (PCS_SINGBOX_CHECK=1); structural always
    run_sb_check = os.environ.get("PCS_SINGBOX_CHECK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    for loc in selected:
        meta = LOCATIONS[loc]
        sec = secrets_data["locations"][loc]
        aliases = client_aliases_for(loc, meta)
        server_cfg = build_server_config(loc, meta, sec, create_certs=True)
        s_path = VPS_PKG / f"sing-box-{loc}-reality.json"
        write_json(s_path, server_cfg)
        server_written.append(str(s_path))

        # Offline VPS-path preview (Mac absolute → /etc/sing-box) for hy2 locations
        if meta.get("hy2"):
            preview = VPS_PKG / "vps_path_preview" / f"sing-box-{loc}-reality.vps.json"
            try:
                rewrite_server_config_for_vps(s_path, loc, preview)
                vps_path_previews.append(str(preview))
            except Exception:
                pass

        inv_loc = inventory.get("locations", {}).get(loc, {}) or {}
        # Client: full pool → multi-outbound (reality-out-1..N + urltest/selector).
        # Single IP keeps classic reality-out shape. Server pool deploy remains
        # pcs_deploy_pool_v20260802.sh (primary still used for deploy_filled blocks).
        pool_ips = location_pool_ips(inv_loc)
        ip, user, _pool_member = resolve_location_primary(
            inv_loc, default_user=default_user
        )
        # Prefer pool list; fall back to primary resolver (env overlay / legacy)
        if not pool_ips and is_real_ip(ip):
            pool_ips = [ip]
        elif pool_ips and not is_real_ip(ip):
            ip = pool_ips[0]
        enabled = inv_loc.get("enabled", True)

        if enabled and pool_ips:
            client_cfg = build_client_config(
                loc, meta, sec, pool_ips[0], server_ips=pool_ips
            )
            # Schema self-check before write — readiness only marks configured when valid
            report = validate_client_config_schema(
                client_cfg,
                require_real_server=True,
                run_singbox_check=run_sb_check,
            )
            client_schema_reports.append(
                {
                    "location": loc,
                    "ok": report["ok"],
                    "errors": report.get("errors") or [],
                    "warnings": (report.get("warnings") or [])[:8],
                    "urltest": bool((report.get("checks") or {}).get("urltest_present")),
                    "clash_api": bool((report.get("checks") or {}).get("clash_api_enabled")),
                    "pool_size": len(pool_ips),
                    "multi_pool": len(pool_ips) >= 2,
                }
            )
            if not report["ok"]:
                schema_failures.append(
                    f"{loc}: " + "; ".join(report.get("errors") or ["unknown"])
                )
                client_pending_ip.append(loc)
                reason = f"{loc}: schema self-check failed"
                skip_reasons.append(reason)
                # pending.json stays public uuid/public_key only; schema errors go to
                # materialize result (client_schema_reports / skip_reasons), not the sidecar.
                pending = pending_public_only(loc, sec, meta, skip_reason=reason)
                # schema errors stay in materialize result; optional short note on sidecar
                if report.get("errors"):
                    pending = filter_pending_public(
                        {
                            **pending,
                            "status": "schema_self_check_failed",
                            "schema_errors": report.get("errors"),
                        }
                    )
                write_pending_json(SINGBOX_CLIENT / f"{loc}.pending.json", pending, mode=0o600)
                for alias in aliases:
                    write_pending_json(
                        SINGBOX_CLIENT / f"{alias}.pending.json",
                        pending_public_only(
                            loc, sec, meta, skip_reason=reason, written_as=alias, alias_of=loc
                        ),
                        mode=0o600,
                    )
                continue

            c_path = SINGBOX_CLIENT / f"{loc}.json"
            write_json(c_path, client_cfg)
            client_written.append(str(c_path))

            # germany → frankfurt (and any meta.client_alias) — identical full config
            for alias in aliases:
                a_path = SINGBOX_CLIENT / f"{alias}.json"
                write_json(a_path, client_cfg)
                client_written.append(str(a_path))

            # remove stale pending sidecars (canonical + aliases)
            for name in [loc] + list(aliases):
                pending_path = SINGBOX_CLIENT / f"{name}.pending.json"
                if pending_path.exists():
                    try:
                        pending_path.unlink()
                    except OSError:
                        pass
        else:
            client_pending_ip.append(loc)
            reason = _skip_reason(loc, inv_loc, ip)
            skip_reasons.append(reason)
            # Informative sidecar only — never full client JSON with fake IPs.
            # Readiness marks *.pending.json as pending_ip; full *.json only with real IP.
            pending = pending_public_only(loc, sec, meta, skip_reason=reason)
            write_pending_json(SINGBOX_CLIENT / f"{loc}.pending.json", pending, mode=0o600)
            # germany → frankfurt.pending.json (informative alias sidecar)
            for alias in aliases:
                write_pending_json(
                    SINGBOX_CLIENT / f"{alias}.pending.json",
                    pending_public_only(
                        loc, sec, meta, skip_reason=reason, written_as=alias, alias_of=loc
                    ),
                    mode=0o600,
                )
            # Drop stale full JSON if this location no longer has a real IP
            for name in [loc] + list(aliases):
                full_path = SINGBOX_CLIENT / f"{name}.json"
                if full_path.exists():
                    try:
                        full_path.unlink()
                    except OSError:
                        pass

    # Deploy script: full inventory context for all selected; scp only real IPs
    deploy_text, deployable, deploy_skipped = build_deploy_script(
        selected, inventory, default_user
    )
    deploy_sh = VPS_PKG / "deploy_filled_to_vps.sh"
    write_text_atomic(deploy_sh, deploy_text, mode=0o700)

    # README for VPS package
    scripts = VPS_PKG / "scripts"
    readme = VPS_PKG / "README_DEPLOY.md"
    write_text_atomic(
        readme,
        f"""# Industrial VPS package (filled)

Generated: {datetime.now(timezone.utc).isoformat()}

## Guide

Canonical: `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md`  
Industrial: `~/Desktop/PCS_Industrial_20260802/docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md`

## Contents

- `sing-box-*-reality.json` — **filled** server configs (UUID, Reality private key, passwords)
  - Hy2 cert paths may be **Mac absolute** so local `sing-box check` works; deploy rewrites to `/etc/sing-box/...`
- `hy2_certs/<location>/` — self-signed TLS for Hysteria2 (when enabled)
- `vps_path_preview/*.vps.json` — offline rewritten copies with VPS paths
- `deploy_filled_to_vps.sh` — multi-location deploy (**safe no-op** when inventory IPs empty)
- `scripts/pcs_deploy_one_v20260802.sh` — single VPS: `user@host location`
- `scripts/pcs_remote_bootstrap_singbox_v20260802.sh` — Ubuntu 22.04/24.04 bootstrap (idempotent)
- `scripts/pcs_rewrite_singbox_paths_v20260802.py` — Mac → `/etc/sing-box` path rewrite
- `scripts/pcs_compose_deploy_v20260802.py` — standalone deploy composer

## Inventory

Edit: `{INVENTORY}`

```json
{{
  "locations": {{
    "dubai": {{ "ip": "YOUR.REAL.VPS.IP", "enabled": true }}
  }}
}}
```

Or: `export PCS_VPS_DUBAI=x.x.x.x` then re-run materialize.  
Use `--force-inventory-env` to persist env overrides into the inventory file.

**No real VPS IPs are embedded.** Live mode refuses documentation ranges (203.0.113.0/24, etc.).

## Dry-run demo (safe, no network)

```bash
# Path rewrite only
python3 {scripts}/pcs_rewrite_singbox_paths_v20260802.py \\
  --in {VPS_PKG}/sing-box-dubai-reality.json \\
  --location dubai --dry-run

# Single-host plan (no SSH/SCP)
bash {scripts}/pcs_deploy_one_v20260802.sh --dry-run root@203.0.113.10 dubai

# Multi-host (NO-OPs without inventory IPs; dry-run demos dubai rewrite)
bash {VPS_PKG}/deploy_filled_to_vps.sh --dry-run
```

## Live single-VPS deploy

```bash
bash {scripts}/pcs_deploy_one_v20260802.sh root@YOUR_VPS_IP dubai
```

Idempotent remote steps (Ubuntu 22.04/24.04):

1. Install sing-box if missing (official deb-install)
2. Place config → `/etc/sing-box/config.json` (paths already rewritten)
3. Place hy2 certs → `/etc/sing-box/hy2_certs/<loc>/`
4. `sing-box check -c /etc/sing-box/config.json`
5. `systemctl enable --now sing-box`
6. ufw allow `443/tcp` `443/udp` `8443/udp` `22/tcp`
7. Health echo `PCS_BOOTSTRAP_HEALTH=OK`

## Manual (HOWTO-aligned)

```bash
python3 {scripts}/pcs_rewrite_singbox_paths_v20260802.py \\
  --in {VPS_PKG}/sing-box-dubai-reality.json \\
  --out /tmp/sing-box-dubai-vps.json --location dubai
# Prefer industrial deploy_one over ad-hoc scp; Suite deploy_all.sh is not modified.
```

## Client configs

Full sing-box JSON is written **only** when inventory has a real public IP
(schema self-check must pass). Otherwise only informative `*.pending.json`
sidecars exist (public uuid/public_key + caveats — not runnable configs).

Dir: `{SINGBOX_CLIENT}/`

- Alias: **germany → frankfurt** (`frankfurt.json` / `frankfurt.pending.json`)
- Selector + optional urltest (auto when Reality+Hy2); direct/block always present
- Private/LAN bypass: `ip_is_private` → direct
- clash_api **disabled by default** (`PCS_CLASH_API=1` to enable on loopback)
- Log level: `PCS_CLIENT_LOG_LEVEL` (default `warn`)
- Optional binary check: `PCS_SINGBOX_CHECK=1`

Secrets (private keys): `{LOCATION_KEYS}` (chmod 600)

Keys are preserved on re-run unless `--rotate-keys`.

{format_client_caveats(as_markdown=True)}

## Re-materialize / re-compose

```bash
python3 {INDUSTRIAL}/shared/pcs_materialize_singbox_v20260802.py
python3 {scripts}/pcs_compose_deploy_v20260802.py
```
""",
        mode=0o644,
    )

    # industrial docs copy
    ind_docs = INDUSTRIAL / "docs_v20260802"
    ind_docs.mkdir(parents=True, exist_ok=True)
    caveats_md = format_client_caveats(as_markdown=True)
    write_text_atomic(
        ind_docs / "VPS_MATERIALIZE_STATUS_v20260802.md",
        f"""# VPS materialize status

- Templates copied from Suite: {n_templates}
- Server package: `{VPS_PKG}`
- Client dir: `{SINGBOX_CLIENT}`
- Clients written (real IP, schema OK): {len(client_written)}
- Pending IP: {', '.join(client_pending_ip) or '(none)'}
- Schema failures: {', '.join(schema_failures) or '(none)'}
- Keys rotated: {', '.join(secrets_data.get('_rotated') or []) or '(none)'}
- short_id healed: {', '.join(secrets_data.get('_healed_short_id') or []) or '(none)'}
- Inventory: `{INVENTORY}`
- germany alias: frankfurt

{caveats_md}
Re-run:

```bash
python3 {Path(__file__).resolve()}
python3 {Path(__file__).resolve()} --check-only --json
python3 {Path(__file__).resolve()} --location dubai
python3 {Path(__file__).resolve()} --rotate-keys --location dubai
PCS_SINGBOX_CHECK=1 python3 {Path(__file__).resolve()} --location dubai
python3 -c "from pcs_server_readiness_v20260802 import scan_readiness; import json; print(json.dumps(scan_readiness(), indent=2))"
```
""",
        mode=0o644,
    )

    fp = secrets_fingerprint(secrets_data)
    age = secrets_age_check(secrets_data=secrets_data)
    harden_secret_paths()

    result = {
        "ok": True,
        "mode": "materialize",
        "templates_copied": n_templates,
        "locations_requested": selected,
        "server_configs": server_written,
        "client_configs": client_written,
        "pending_ip_locations": client_pending_ip,
        "skip_reasons": skip_reasons or deploy_skipped,
        "deployable_locations": deployable,
        "keys_preserved": keys_preserved,
        "keys_rotated": secrets_data.get("_rotated") or [],
        "short_id_healed": secrets_data.get("_healed_short_id") or [],
        "env_applied_memory": inventory.get("_env_applied_memory") or [],
        "env_persisted": inventory.get("_env_persisted") or [],
        "inventory": str(INVENTORY),
        "client_dir": str(SINGBOX_CLIENT),
        "vps_package": str(VPS_PKG),
        "secrets": str(LOCATION_KEYS),
        "secrets_fingerprint": fp.get("fingerprint"),
        "secrets_fingerprint_full": fp.get("fingerprint_full"),
        "secrets_fingerprint_meta": {
            "algorithm": fp.get("algorithm"),
            "hashed_fields": fp.get("hashed_fields"),
            "locations": fp.get("locations"),
        },
        "secrets_age": age,
        "deploy_script": str(deploy_sh),
        "deploy_scripts_synced": scripts_copied,
        "vps_path_previews": vps_path_previews,
        "deploy_one": str(VPS_PKG / "scripts" / "pcs_deploy_one_v20260802.sh"),
        "remote_bootstrap": str(
            VPS_PKG / "scripts" / "pcs_remote_bootstrap_singbox_v20260802.sh"
        ),
        "path_rewriter": str(
            VPS_PKG / "scripts" / "pcs_rewrite_singbox_paths_v20260802.py"
        ),
        "configured_clients": len(client_written),
        "client_schema_reports": client_schema_reports,
        "schema_failures": schema_failures,
        "client_caveats": list(CLIENT_CAVEATS),
        "at": datetime.now(timezone.utc).isoformat(),
    }
    # Meta on disk is path/count oriented (no private key values). Still redact on write.
    write_json(META, public_materialize_summary(result))
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    locs = ", ".join(LOCATIONS.keys())
    p = argparse.ArgumentParser(
        prog="pcs_materialize_singbox_v20260802",
        description=(
            "Idempotent secretful sing-box materializer (PCS Industrial).\n"
            "Preserves location keys unless --rotate-keys. Never invents VPS IPs.\n"
            "Never prints private keys / hy2 passwords. Atomic JSON writes."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "modes:\n"
            "  (default)     apply — write server package + clients (keys preserved)\n"
            "  --check-only  plan  — read-only status; exit codes match apply readiness\n"
            "  --rotate-keys apply — regenerate keys then rematerialize server package\n"
            "\n"
            "exit codes:\n"
            "  0  success (all requested locations have real public IPs)\n"
            "  2  soft success — pending IPs (server packages OK on apply)\n"
            "  1  hard failure (unknown location, flag conflict, deps, I/O)\n"
            "\n"
            "examples:\n"
            "  %(prog)s --check-only --json\n"
            "  %(prog)s --location dubai\n"
            "  %(prog)s --rotate-keys --location dubai\n"
            "  PCS_VPS_DUBAI=x.x.x.x %(prog)s --force-inventory-env\n"
            "\n"
            f"locations: {locs}\n"
            "public summary always includes secrets_fingerprint, counts, pending_ip_locations.\n"
        ),
    )
    p.add_argument(
        "--rotate-keys",
        action="store_true",
        help=(
            "Regenerate UUID, Reality keypairs, and hy2 passwords for selected "
            "locations, then rematerialize the server package and clients. "
            "Without this flag, existing keys in location_keys.json are preserved."
        ),
    )
    p.add_argument(
        "--check-only",
        action="store_true",
        help=(
            "Plan/status only: report inventory readiness, secrets fingerprint, "
            "and hy2 cert presence. Never creates or mutates files "
            "(incompatible with --rotate-keys)."
        ),
    )
    p.add_argument(
        "--location",
        metavar="NAME",
        help=f"Only process one location ({locs}). Default: all.",
    )
    p.add_argument(
        "--force-inventory-env",
        action="store_true",
        help=(
            "Persist PCS_VPS_<LOC> env overrides into vps_inventory.json on apply. "
            "With --check-only: report env_would_persist only (no write)."
        ),
    )
    p.add_argument(
        "--json",
        action="store_true",
        help=(
            "Machine-readable redacted JSON on stdout only "
            "(suppress human stderr operator summary)."
        ),
    )
    return p.parse_args(argv)


def _exit_code_for(result: Dict[str, Any]) -> int:
    """Map materialize/check-only result to industrial exit code."""
    if result.get("ok") is False:
        return EXIT_HARD
    pending = result.get("pending_ip_locations") or []
    if pending:
        return EXIT_PENDING
    return EXIT_OK


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    only = [args.location] if args.location else None
    if only and only[0] not in LOCATIONS:
        err = {
            "ok": False,
            "error": f"unknown location: {only[0]}",
            "known": list(LOCATIONS.keys()),
        }
        print(json.dumps(err, indent=2))
        return EXIT_HARD

    # Industrial flag hygiene: plan mode never rotates.
    if args.check_only and args.rotate_keys:
        err = {
            "ok": False,
            "error": (
                "--check-only is read-only and cannot be combined with --rotate-keys; "
                "run --rotate-keys without --check-only to regenerate keys and rematerialize"
            ),
            "exit_hint": EXIT_HARD,
        }
        print(json.dumps(err, indent=2))
        return EXIT_HARD

    try:
        if args.check_only:
            r = check_only(
                only_locations=only,
                force_inventory_env=args.force_inventory_env,
            )
        else:
            r = materialize(
                rotate_keys=args.rotate_keys,
                only_locations=only,
                force_inventory_env=args.force_inventory_env,
            )
    except ValueError as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        return EXIT_HARD
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": f"missing dependency: {e}"}, indent=2))
        return EXIT_HARD
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "")[:200] if isinstance(e.stderr, str) else ""
        if any(x in err.lower() for x in ("private", "password", "-----begin")):
            err = "<redacted>"
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "external command failed (sing-box/openssl)",
                    "stderr": err,
                    "cmd": list(e.cmd) if e.cmd else None,
                },
                indent=2,
            )
        )
        return EXIT_HARD
    except OSError as e:
        print(json.dumps({"ok": False, "error": f"io error: {e}"}, indent=2))
        return EXIT_HARD
    except Exception as e:
        # Redact unexpected exception text if it somehow embeds key material.
        msg = str(e)
        if any(x in msg.lower() for x in ("privatekey:", "private_key", "-----begin")):
            msg = f"{type(e).__name__}: <redacted>"
        print(json.dumps({"ok": False, "error": msg, "type": type(e).__name__}, indent=2))
        return EXIT_HARD

    # Never echo private_key / hy2_password / PEM material in stdout summaries.
    public = public_materialize_summary(r)
    print(json.dumps(public, indent=2))
    code = _exit_code_for(r)

    if not args.json:
        # Operator banner to stderr (stdout stays pure JSON for piping)
        print(format_operator_summary(r), file=sys.stderr)
        if code == EXIT_PENDING:
            print(
                "\n# NEXT: set real VPS IPs in "
                f"{r.get('inventory')} or PCS_VPS_<LOC>, then re-run (apply).",
                file=sys.stderr,
            )
            if r.get("mode") != "check-only":
                print(
                    "# Server packages are ready to scp per HOWTO_DEPLOY_AND_VERIFY.md",
                    file=sys.stderr,
                )
            print(
                f"# secrets_fingerprint={r.get('secrets_fingerprint')} "
                f"(public material only; stable without --rotate-keys)",
                file=sys.stderr,
            )
            for reason in r.get("skip_reasons") or []:
                print(f"# SKIP: {reason}", file=sys.stderr)
        elif code == EXIT_OK and r.get("mode") != "check-only":
            print(
                f"# OK: all requested locations configured "
                f"(fingerprint={r.get('secrets_fingerprint')})",
                file=sys.stderr,
            )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
