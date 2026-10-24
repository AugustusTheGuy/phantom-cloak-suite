#!/usr/bin/env python3
"""Security audit engine for PCS Industrial tree + optional Suite path (read-only).

Senior designer + pentester lens. Writes nothing into legacy PhantomCloak dirs.

Scores industrial runtime paths under ~/.pcs_industrial_20260802/:
  - secrets permissions
  - pf_rules location (must not be /tmp)
  - readiness fail-closed (configured_count==0 blocks protect)
  - inventory empty (ops gap — honest, not false zero from scanners)
  - singbox package present
  - residential catalog flagged synthetic

Emits: ~/.pcs_industrial_20260802/audit_reports/latest.json

CLI:
  python3 -m shared.pcs_security_audit_engine_v20260802
  python3 shared/pcs_security_audit_engine_v20260802.py [--no-suite] [--no-write] [--json]
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

PCS_STATE = Path.home() / ".pcs_industrial_20260802"
INDUSTRIAL_ROOT = Path(__file__).resolve().parents[1]
AUDIT_REPORTS_DIR = PCS_STATE / "audit_reports"
LATEST_REPORT = AUDIT_REPORTS_DIR / "latest.json"

# Directories never scanned for AST (prevents false-zero scores from third-party code)
_SKIP_DIR_PARTS = frozenset({
    ".venv",
    "venv",
    "site-packages",
    "dist-packages",
    "__pycache__",
    ".git",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
    ".eggs",
    "build",
    "dist",
})

_SYNTHETIC_KIND = "synthetic_product_catalog_v20260802"


# ---------------------------------------------------------------------------
# Path helpers (relative_to safe across industrial / state / suite / absolute)
# ---------------------------------------------------------------------------

def _rel(path: Path, *bases: Path) -> str:
    """Return path relative to the first matching base; never raise on mismatch."""
    resolved = Path(path)
    try:
        resolved = resolved.resolve()
    except OSError:
        resolved = Path(path)
    candidates: list[Path] = list(bases) if bases else []
    candidates.extend([INDUSTRIAL_ROOT, PCS_STATE, Path.home()])
    seen: set[str] = set()
    for base in candidates:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        try:
            b = base.resolve()
        except OSError:
            b = Path(base)
        try:
            return str(resolved.relative_to(b))
        except ValueError:
            continue
    return str(resolved)


def _mode(path: Path) -> Optional[int]:
    try:
        return path.stat().st_mode & 0o777
    except OSError:
        return None


def _is_world_or_group_readable(mode: int) -> bool:
    return bool(mode & (stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH))


def _should_skip_path(path: Path) -> bool:
    return any(part in _SKIP_DIR_PARTS for part in path.parts)


# ---------------------------------------------------------------------------
# AST scan (industrial product code only)
# ---------------------------------------------------------------------------

def _scan_py(path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        src = path.read_text(errors="replace")
        tree = ast.parse(src, filename=str(path))
    except Exception as e:
        return [{
            "severity": "low",
            "issue": f"parse fail {path.name}",
            "detail": str(e)[:120],
            "file": _rel(path),
            "check": "ast_scan",
        }]

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "shell"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    findings.append({
                        "severity": "high",
                        "issue": "subprocess shell=True",
                        "file": _rel(path),
                        "line": getattr(node, "lineno", None),
                        "check": "ast_scan",
                    })
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("eval", "exec"):
                findings.append({
                    "severity": "high",
                    "issue": f"use of {name}()",
                    "file": _rel(path),
                    "line": getattr(node, "lineno", None),
                    "check": "ast_scan",
                })
    # Weak *account/password* hashing only — not VPN hy2 passwords or content fingerprints.
    # Require a hash-call near a password variable, and no modern KDF in file.
    lower = src.lower()
    has_kdf = any(k in lower for k in ("pbkdf2", "argon2", "scrypt", "bcrypt"))
    weak_pwd_hash = (
        not has_kdf
        and (
            "hashlib.sha256" in lower or "sha256(" in lower
        )
        and any(
            pat in lower
            for pat in (
                "sha256(password",
                "sha256(passwd",
                "sha256(pwd",
                "hashlib.sha256(password",
                "hashlib.sha256(passwd",
                ".sha256(password.encode",
                "hash_password",
                "password_hash",
                "hashlib.sha256(pwd",
            )
        )
    )
    if weak_pwd_hash:
        findings.append({
            "severity": "medium",
            "issue": "possible weak password hashing (sha256 without pbkdf2/argon2)",
            "file": _rel(path),
            "check": "ast_scan",
        })
    return findings


def _iter_industrial_py() -> Iterable[Path]:
    for p in INDUSTRIAL_ROOT.rglob("*.py"):
        if _should_skip_path(p):
            continue
        yield p


# ---------------------------------------------------------------------------
# Industrial path checks (product runtime posture)
# ---------------------------------------------------------------------------

def _check_secrets_perms() -> tuple[dict[str, Any], list[dict]]:
    """Secrets dirs 0700, secret files 0600 (or no group/other access)."""
    findings: list[dict] = []
    secrets = PCS_STATE / "secrets"
    detail: dict[str, Any] = {
        "path": str(secrets),
        "state_mode": None,
        "secrets_mode": None,
        "bad_paths": [],
        "checked_files": 0,
        "checked_dirs": 0,
    }
    state_mode = _mode(PCS_STATE)
    detail["state_mode"] = oct(state_mode) if state_mode is not None else None
    if state_mode is not None and _is_world_or_group_readable(state_mode):
        findings.append({
            "severity": "high",
            "issue": "PCS state root is group/world accessible",
            "file": _rel(PCS_STATE, PCS_STATE),
            "detail": f"mode={oct(state_mode)}; expected 0o700",
            "check": "secrets_perms",
        })

    if not secrets.is_dir():
        findings.append({
            "severity": "high",
            "issue": "secrets directory missing",
            "file": str(secrets),
            "check": "secrets_perms",
        })
        return {
            "id": "secrets_perms",
            "pass": False,
            "severity": "high",
            "summary": "secrets/ missing",
            "detail": detail,
        }, findings

    sec_mode = _mode(secrets)
    detail["secrets_mode"] = oct(sec_mode) if sec_mode is not None else None
    if sec_mode is not None and _is_world_or_group_readable(sec_mode):
        findings.append({
            "severity": "high",
            "issue": "secrets/ is group/world accessible",
            "file": _rel(secrets, PCS_STATE),
            "detail": f"mode={oct(sec_mode)}; expected 0o700",
            "check": "secrets_perms",
        })
        detail["bad_paths"].append({"path": str(secrets), "mode": oct(sec_mode), "kind": "dir"})

    for root, dirs, files in os.walk(secrets):
        rp = Path(root)
        detail["checked_dirs"] += 1
        dm = _mode(rp)
        if dm is not None and _is_world_or_group_readable(dm):
            findings.append({
                "severity": "high",
                "issue": "secret subdirectory group/world accessible",
                "file": _rel(rp, PCS_STATE),
                "detail": f"mode={oct(dm)}",
                "check": "secrets_perms",
            })
            detail["bad_paths"].append({"path": str(rp), "mode": oct(dm), "kind": "dir"})
        for name in files:
            fp = rp / name
            detail["checked_files"] += 1
            fm = _mode(fp)
            if fm is not None and _is_world_or_group_readable(fm):
                findings.append({
                    "severity": "high",
                    "issue": "secret file group/world accessible",
                    "file": _rel(fp, PCS_STATE),
                    "detail": f"mode={oct(fm)}; expected 0o600",
                    "check": "secrets_perms",
                })
                detail["bad_paths"].append({"path": str(fp), "mode": oct(fm), "kind": "file"})

    ok = not any(f.get("check") == "secrets_perms" for f in findings)
    return {
        "id": "secrets_perms",
        "pass": ok,
        "severity": "high",
        "summary": "secrets permissions tight (0700/0600)" if ok else "secrets permission failures",
        "detail": detail,
    }, findings


def _check_pf_rules_location() -> tuple[dict[str, Any], list[dict]]:
    """Industrial pf conf must live under PCS_STATE/pf_rules — never /tmp."""
    findings: list[dict] = []
    expected_dir = PCS_STATE / "pf_rules"
    expected_conf = expected_dir / "pcs_killswitch_v20260802.pf.conf"
    detail: dict[str, Any] = {
        "expected_dir": str(expected_dir),
        "expected_conf": str(expected_conf),
        "conf_exists": expected_conf.is_file(),
        "module_pf_path": None,
        "under_tmp": False,
    }

    # Runtime path from industrial killswitch module (source of truth)
    module_path: Optional[Path] = None
    try:
        try:
            from shared.pcs_killswitch_industrial_v20260802 import PF_CONF_PATH, RULES_DIR
        except ImportError:
            from pcs_killswitch_industrial_v20260802 import PF_CONF_PATH, RULES_DIR  # type: ignore
        module_path = Path(PF_CONF_PATH)
        detail["module_pf_path"] = str(module_path)
        detail["module_rules_dir"] = str(RULES_DIR)
    except Exception as e:
        findings.append({
            "severity": "medium",
            "issue": "could not import industrial killswitch PF path",
            "detail": str(e)[:160],
            "check": "pf_rules_location",
        })

    under_tmp = False
    for candidate in filter(None, [module_path, expected_conf if expected_conf.exists() else None]):
        parts = [p.lower() for p in Path(candidate).parts]
        if "tmp" in parts or str(candidate).startswith("/tmp") or str(candidate).startswith("/var/tmp"):
            under_tmp = True
    detail["under_tmp"] = under_tmp

    if under_tmp:
        findings.append({
            "severity": "high",
            "issue": "pf rules path resolves under /tmp (insecure / ephemeral)",
            "file": str(module_path or expected_conf),
            "detail": "Industrial killswitch must use ~/.pcs_industrial_20260802/pf_rules/",
            "check": "pf_rules_location",
        })

    if module_path is not None:
        try:
            module_path.resolve().relative_to(PCS_STATE.resolve())
            in_state = True
        except ValueError:
            in_state = False
        if not in_state and not under_tmp:
            findings.append({
                "severity": "high",
                "issue": "PF_CONF_PATH not under industrial state dir",
                "file": str(module_path),
                "check": "pf_rules_location",
            })

    # Source guard: industrial killswitch file should declare non-/tmp path
    ks_src = INDUSTRIAL_ROOT / "shared" / "pcs_killswitch_industrial_v20260802.py"
    if ks_src.is_file():
        text = ks_src.read_text(errors="replace")
        if "PF_CONF_PATH" in text and "/tmp/" in text and "pf_rules" not in text.split("PF_CONF_PATH", 1)[-1][:200]:
            # only flag if assignment itself points at /tmp (legacy comment mentions /tmp OK)
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("PF_CONF_PATH") and "/tmp" in stripped and "pf_rules" not in stripped:
                    findings.append({
                        "severity": "high",
                        "issue": "industrial killswitch PF_CONF_PATH assigned under /tmp",
                        "file": _rel(ks_src),
                        "check": "pf_rules_location",
                    })
                    break

    if not expected_dir.is_dir():
        findings.append({
            "severity": "medium",
            "issue": "pf_rules directory missing under industrial state",
            "file": str(expected_dir),
            "check": "pf_rules_location",
        })

    ok = not any(
        f.get("check") == "pf_rules_location" and f.get("severity") == "high"
        for f in findings
    ) and not under_tmp and (module_path is None or str(PCS_STATE) in str(module_path))
    # Soft: dir may be empty before first arm — still pass if path policy correct
    if under_tmp:
        ok = False
    elif module_path is not None:
        try:
            Path(module_path).resolve().relative_to(PCS_STATE.resolve())
            ok = True
            # drop medium-only as still pass for location policy
        except ValueError:
            ok = False
    else:
        ok = expected_dir.is_dir() and not under_tmp

    return {
        "id": "pf_rules_location",
        "pass": ok,
        "severity": "high",
        "summary": (
            "pf rules under industrial state (not /tmp)"
            if ok
            else "pf rules path policy failed"
        ),
        "detail": detail,
    }, findings


def _check_readiness_fail_closed() -> tuple[dict[str, Any], list[dict]]:
    """Protect path must refuse when configured_count == 0."""
    findings: list[dict] = []
    detail: dict[str, Any] = {
        "gate_ok_for_protect_on_zero": None,
        "require_configured_servers_default": None,
        "dry_run_protected": None,
        "live_configured_count": None,
    }

    try:
        try:
            from shared.pcs_server_readiness_v20260802 import gate_snapshot
            from shared.pcs_preflight_obfuscation_gate_v20260802 import (
                activate_protected_session,
            )
        except ImportError:
            from pcs_server_readiness_v20260802 import gate_snapshot  # type: ignore
            from pcs_preflight_obfuscation_gate_v20260802 import (  # type: ignore
                activate_protected_session,
            )

        zero_ready = {
            "status": "templates_only",
            "configured_count": 0,
            "server_filled_count": 0,
            "pending": [],
            "pending_ip_count": 0,
            "inventory": {"path": str(PCS_STATE / "vps_inventory.json"), "ips_set": 0},
            "howto_path": str(
                INDUSTRIAL_ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
            ),
            "next_step": "fill_inventory",
        }
        snap = gate_snapshot(zero_ready)
        detail["gate_ok_for_protect_on_zero"] = snap.get("ok_for_protect")
        if snap.get("ok_for_protect") is not False:
            findings.append({
                "severity": "high",
                "issue": "gate_snapshot allows protect when configured_count=0 (not fail-closed)",
                "detail": json.dumps({k: snap.get(k) for k in (
                    "ok_for_protect", "configured_count", "status"
                )}, default=str)[:200],
                "check": "readiness_fail_closed",
            })

        # Default parameter inspection via dry-run activate with empty readiness
        blocked = activate_protected_session(
            tier="core",
            auto_arm_killswitch=False,
            require_configured_servers=True,
            readiness_override=zero_ready,
        )
        detail["dry_run_protected"] = blocked.get("protected")
        detail["dry_run_status"] = blocked.get("status")
        detail["dry_run_reason"] = blocked.get("reason")
        if blocked.get("protected") is True or blocked.get("status") == "protected":
            findings.append({
                "severity": "high",
                "issue": "activate_protected_session marks protected with zero configured servers",
                "detail": "fail-closed broken on protect path",
                "check": "readiness_fail_closed",
            })

        # Source default for require_configured_servers
        pre_src = INDUSTRIAL_ROOT / "shared" / "pcs_preflight_obfuscation_gate_v20260802.py"
        if pre_src.is_file():
            src = pre_src.read_text(errors="replace")
            if "require_configured_servers: bool = True" in src:
                detail["require_configured_servers_default"] = True
            elif "require_configured_servers: bool = False" in src:
                detail["require_configured_servers_default"] = False
                findings.append({
                    "severity": "high",
                    "issue": "require_configured_servers defaults to False (fail-open)",
                    "file": _rel(pre_src),
                    "check": "readiness_fail_closed",
                })
            else:
                detail["require_configured_servers_default"] = "unknown"

        try:
            live = gate_snapshot()
            detail["live_configured_count"] = live.get("configured_count")
            detail["live_ok_for_protect"] = live.get("ok_for_protect")
        except Exception as e:
            detail["live_scan_error"] = str(e)[:120]

    except Exception as e:
        findings.append({
            "severity": "high",
            "issue": "readiness fail-closed check could not run",
            "detail": str(e)[:200],
            "check": "readiness_fail_closed",
        })

    ok = not any(f.get("check") == "readiness_fail_closed" for f in findings)
    return {
        "id": "readiness_fail_closed",
        "pass": ok,
        "severity": "high",
        "summary": (
            "protect path fail-closed on configured_count=0"
            if ok
            else "fail-closed readiness gate broken"
        ),
        "detail": detail,
    }, findings


def _check_inventory_empty() -> tuple[dict[str, Any], list[dict]]:
    """Flag empty VPS inventory honestly (ops gap, not a scanner false zero)."""
    findings: list[dict] = []
    inv_path = PCS_STATE / "vps_inventory.json"
    detail: dict[str, Any] = {
        "path": str(inv_path),
        "exists": inv_path.is_file(),
        "locations": 0,
        "ips_set": 0,
        "empty_locations": [],
        "filled_locations": [],
    }

    if not inv_path.is_file():
        findings.append({
            "severity": "high",
            "issue": "vps_inventory.json missing",
            "file": str(inv_path),
            "check": "inventory_empty",
        })
        return {
            "id": "inventory_empty",
            "pass": False,
            "severity": "high",
            "summary": "inventory file missing",
            "detail": detail,
        }, findings

    try:
        data = json.loads(inv_path.read_text(errors="replace"))
    except Exception as e:
        findings.append({
            "severity": "high",
            "issue": "vps_inventory.json unreadable",
            "detail": str(e)[:120],
            "check": "inventory_empty",
        })
        return {
            "id": "inventory_empty",
            "pass": False,
            "severity": "high",
            "summary": "inventory unreadable",
            "detail": detail,
        }, findings

    locs = data.get("locations") or {}
    if not isinstance(locs, dict):
        locs = {}
    detail["locations"] = len(locs)
    for name, meta in locs.items():
        if not isinstance(meta, dict):
            continue
        ip = (meta.get("ip") or "").strip()
        if ip:
            detail["ips_set"] += 1
            detail["filled_locations"].append(name)
        else:
            detail["empty_locations"].append(name)

    # Empty inventory is real ops posture — score it, do not invent IPs
    if detail["ips_set"] == 0:
        findings.append({
            "severity": "medium",
            "issue": "VPS inventory has zero public IPs set (production not ready)",
            "file": _rel(inv_path, PCS_STATE),
            "detail": (
                f"locations={detail['locations']}; ips_set=0; "
                "fill inventory then materialize client configs"
            ),
            "check": "inventory_empty",
            "scope": "ops",
        })
        ok = False
        summary = "inventory empty (honest ops gap)"
    else:
        ok = True
        summary = f"inventory has {detail['ips_set']} IP(s) set"
        if detail["empty_locations"]:
            findings.append({
                "severity": "low",
                "issue": "some inventory locations still lack IPs",
                "file": _rel(inv_path, PCS_STATE),
                "detail": f"empty={detail['empty_locations'][:12]}",
                "check": "inventory_empty",
                "scope": "ops",
            })

    return {
        "id": "inventory_empty",
        "pass": ok,
        "severity": "medium",
        "summary": summary,
        "detail": detail,
    }, findings


def _check_singbox_package_present() -> tuple[dict[str, Any], list[dict]]:
    """Server package materialized under industrial state."""
    findings: list[dict] = []
    pkg = PCS_STATE / "vps_server_package"
    client = PCS_STATE / "singbox"
    repo_templates = (
        INDUSTRIAL_ROOT / "server_vps_package_v20260802" / "templates_source_copy"
    )
    detail: dict[str, Any] = {
        "package_dir": str(pkg),
        "package_exists": pkg.is_dir(),
        "server_configs": 0,
        "client_pending_or_json": 0,
        "repo_templates": 0,
    }

    server_cfgs: list[str] = []
    if pkg.is_dir():
        server_cfgs = sorted(
            p.name for p in pkg.glob("sing-box-*-reality.json") if p.is_file()
        )
        detail["server_configs"] = len(server_cfgs)
        detail["server_config_names"] = server_cfgs[:20]

    if client.is_dir():
        detail["client_pending_or_json"] = sum(
            1 for p in client.glob("*.json") if p.is_file()
        )

    if repo_templates.is_dir():
        detail["repo_templates"] = sum(
            1 for p in repo_templates.glob("sing-box-*-reality.json") if p.is_file()
        )

    if detail["server_configs"] == 0 and detail["repo_templates"] == 0:
        findings.append({
            "severity": "high",
            "issue": "no sing-box server package configs found",
            "file": str(pkg),
            "detail": "Run materialize to populate vps_server_package/",
            "check": "singbox_package_present",
        })
        ok = False
        summary = "singbox package missing"
    elif detail["server_configs"] == 0:
        findings.append({
            "severity": "medium",
            "issue": "repo templates present but state vps_server_package empty",
            "file": str(pkg),
            "detail": f"repo_templates={detail['repo_templates']}",
            "check": "singbox_package_present",
        })
        ok = False
        summary = "singbox package not materialized into state"
    else:
        ok = True
        summary = f"singbox package present ({detail['server_configs']} server configs)"

    return {
        "id": "singbox_package_present",
        "pass": ok,
        "severity": "high" if detail["server_configs"] == 0 and detail["repo_templates"] == 0 else "medium",
        "summary": summary,
        "detail": detail,
    }, findings


def _check_residential_catalog_synthetic() -> tuple[dict[str, Any], list[dict]]:
    """Catalog must be explicitly synthetic — never implied as live tunnel endpoints."""
    findings: list[dict] = []
    pool_dir = PCS_STATE / "residential_pools"
    meta_path = pool_dir / "_catalog_meta.json"
    detail: dict[str, Any] = {
        "pool_dir": str(pool_dir),
        "meta_exists": meta_path.is_file(),
        "catalog_kind": None,
        "sample_checked": 0,
        "synthetic_ok": False,
    }

    if not pool_dir.is_dir():
        findings.append({
            "severity": "medium",
            "issue": "residential_pools directory missing",
            "file": str(pool_dir),
            "check": "residential_catalog_synthetic",
        })
        return {
            "id": "residential_catalog_synthetic",
            "pass": False,
            "severity": "medium",
            "summary": "residential catalog missing",
            "detail": detail,
        }, findings

    if not meta_path.is_file():
        findings.append({
            "severity": "medium",
            "issue": "residential _catalog_meta.json missing (cannot prove synthetic)",
            "file": str(meta_path),
            "check": "residential_catalog_synthetic",
        })
    else:
        try:
            meta = json.loads(meta_path.read_text(errors="replace"))
            detail["catalog_kind"] = meta.get("catalog_kind")
            detail["note"] = (meta.get("note") or "")[:160]
            detail["countries"] = meta.get("countries")
            detail["total_entries"] = meta.get("total_entries")
            if meta.get("catalog_kind") != _SYNTHETIC_KIND:
                findings.append({
                    "severity": "high",
                    "issue": "residential catalog_kind not synthetic_product_catalog",
                    "file": _rel(meta_path, PCS_STATE),
                    "detail": f"got {meta.get('catalog_kind')!r}",
                    "check": "residential_catalog_synthetic",
                })
            note = (meta.get("note") or "").lower()
            if "synthetic" not in note and "not vps" not in note and "not" not in note:
                findings.append({
                    "severity": "medium",
                    "issue": "catalog meta note does not declare synthetic / not-VPS",
                    "file": _rel(meta_path, PCS_STATE),
                    "check": "residential_catalog_synthetic",
                })
        except Exception as e:
            findings.append({
                "severity": "medium",
                "issue": "catalog meta unreadable",
                "detail": str(e)[:120],
                "check": "residential_catalog_synthetic",
            })

    # Spot-check country pools
    samples = sorted(pool_dir.glob("??.json"))[:6]
    bad_entries = 0
    for sp in samples:
        try:
            data = json.loads(sp.read_text(errors="replace"))
        except Exception:
            continue
        if not isinstance(data, list) or not data:
            continue
        entry = data[0]
        detail["sample_checked"] += 1
        if entry.get("catalog_kind") != _SYNTHETIC_KIND:
            bad_entries += 1
        if entry.get("not_a_tunnel_endpoint") is not True:
            bad_entries += 1
            findings.append({
                "severity": "high",
                "issue": "residential entry missing not_a_tunnel_endpoint=True",
                "file": _rel(sp, PCS_STATE),
                "detail": f"id={entry.get('id')}",
                "check": "residential_catalog_synthetic",
            })
    detail["bad_sample_entries"] = bad_entries
    detail["synthetic_ok"] = (
        detail.get("catalog_kind") == _SYNTHETIC_KIND and bad_entries == 0
    )

    if detail["sample_checked"] == 0 and meta_path.is_file():
        findings.append({
            "severity": "low",
            "issue": "no country pool samples to verify synthetic flags",
            "file": str(pool_dir),
            "check": "residential_catalog_synthetic",
        })

    ok = detail["synthetic_ok"] and not any(
        f.get("severity") in ("high", "medium") and f.get("check") == "residential_catalog_synthetic"
        for f in findings
    )
    # If only low findings and synthetic_ok, pass
    if detail["synthetic_ok"] and not any(
        f.get("check") == "residential_catalog_synthetic" and f.get("severity") in ("high", "medium")
        for f in findings
    ):
        ok = True

    return {
        "id": "residential_catalog_synthetic",
        "pass": ok,
        "severity": "high",
        "summary": (
            "residential catalog flagged synthetic (not tunnel endpoints)"
            if ok
            else "residential catalog synthetic flags missing/incorrect"
        ),
        "detail": detail,
    }, findings


def run_industrial_path_checks() -> tuple[list[dict[str, Any]], list[dict]]:
    checks: list[dict[str, Any]] = []
    findings: list[dict] = []
    for fn in (
        _check_secrets_perms,
        _check_pf_rules_location,
        _check_readiness_fail_closed,
        _check_inventory_empty,
        _check_singbox_package_present,
        _check_residential_catalog_synthetic,
    ):
        check, fnds = fn()
        checks.append(check)
        findings.extend(fnds)
    return checks, findings


# ---------------------------------------------------------------------------
# Hardening (state dir only — never Suite)
# ---------------------------------------------------------------------------

def harden_pcs_state() -> list[dict]:
    fixed = []
    PCS_STATE.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(PCS_STATE, 0o700)
        fixed.append({"path": str(PCS_STATE), "mode": "0o700"})
    except OSError as e:
        fixed.append({"path": str(PCS_STATE), "error": str(e)})
    secrets = PCS_STATE / "secrets"
    if secrets.is_dir():
        try:
            os.chmod(secrets, 0o700)
            fixed.append({"path": str(secrets), "mode": "0o700"})
        except OSError as e:
            fixed.append({"path": str(secrets), "error": str(e)})
    return fixed


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _compute_score(findings: list[dict], industrial_checks: list[dict]) -> dict[str, Any]:
    """Honest score: code findings + failed industrial controls.

    Avoids false zeros from third-party trees (those are not scanned).
    Empty inventory is a real medium deduction, not a silent zero.
    """
    highs = sum(1 for f in findings if f.get("severity") == "high")
    meds = sum(1 for f in findings if f.get("severity") == "medium")
    lows = sum(1 for f in findings if f.get("severity") == "low")

    # Cap code-scan pressure so one noisy pattern cannot collapse the board alone
    code_highs = sum(
        1 for f in findings if f.get("severity") == "high" and f.get("check") == "ast_scan"
    )
    other_highs = highs - code_highs
    code_meds = sum(
        1 for f in findings if f.get("severity") == "medium" and f.get("check") == "ast_scan"
    )
    other_meds = meds - code_meds

    score = 100
    score -= min(code_highs, 6) * 12  # cap code high impact
    score -= other_highs * 15
    score -= min(code_meds, 8) * 4
    score -= other_meds * 5
    score -= lows * 1

    # Industrial control pass rate as floor signal (6 controls)
    passed = sum(1 for c in industrial_checks if c.get("pass"))
    total = max(len(industrial_checks), 1)
    control_ratio = passed / total
    # If all critical industrial controls pass, soft floor at 55 even with ops gaps
    # (inventory empty still deducts via findings above)
    detail = {
        "highs": highs,
        "mediums": meds,
        "lows": lows,
        "code_highs": code_highs,
        "code_meds": code_meds,
        "industrial_passed": passed,
        "industrial_total": total,
        "control_ratio": round(control_ratio, 3),
    }
    score = max(0, min(100, int(score)))
    return {"score": score, "grade": _grade(score), "scoring": detail}


# ---------------------------------------------------------------------------
# Report I/O
# ---------------------------------------------------------------------------

def write_audit_report(report: dict[str, Any], path: Optional[Path] = None) -> Path:
    out = path or LATEST_REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.parent.chmod(0o700)
    except OSError:
        pass
    text = json.dumps(report, indent=2, default=str) + "\n"
    out.write_text(text)
    try:
        out.chmod(0o600)
    except OSError:
        pass
    # Also stamp a dated copy for continuous audit history
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stamped = out.parent / f"audit_{ts}.json"
    try:
        stamped.write_text(text)
        stamped.chmod(0o600)
    except OSError:
        pass
    return out


def run_full_audit(
    *,
    include_suite_readonly: bool = True,
    write_report: bool = True,
    report_path: Optional[Path] = None,
) -> dict[str, Any]:
    findings: list[dict] = []
    hardened = harden_pcs_state()

    # --- AST scan: industrial product tree only (skip .venv / site-packages) ---
    scanned_files = 0
    for p in _iter_industrial_py():
        scanned_files += 1
        findings.extend(_scan_py(p))

    suite_scanned = 0
    if include_suite_readonly:
        suite = Path.home() / "Desktop" / "PhantomCloak Suite" / "client"
        if suite.is_dir():
            for rel in (
                "phantomcloak.py",
                "core/killswitch.py",
                "core/account_manager.py",
                "core/anti_forensics.py",
                "core/zeroleak_verifier.py",
            ):
                fp = suite / rel
                if fp.is_file():
                    suite_scanned += 1
                    for f in _scan_py(fp):
                        f["scope"] = "suite_readonly"
                        # relative_to industrial would fail — use suite base
                        if "file" in f:
                            f["file"] = _rel(fp, suite, Path.home())
                        findings.append(f)

    # --- Industrial runtime path scoring ---
    industrial_checks, path_findings = run_industrial_path_checks()
    findings.extend(path_findings)

    # Design / known product risks (code-review, not false operational zeros)
    findings.append({
        "severity": "medium",
        "issue": "Legacy Suite activate may set zero_leak_verified=True without full probe",
        "detail": "Industrial pipeline uses pcs_preflight_obfuscation_gate_v20260802 instead",
        "scope": "design",
        "check": "design_review",
    })
    findings.append({
        "severity": "medium",
        "issue": "Demo sing-box configs with placeholder credentials",
        "detail": "Must not ship production without real VPS keys / inventory IPs",
        "scope": "ops",
        "check": "design_review",
    })
    findings.append({
        "severity": "low",
        "issue": "anti_forensics uses rm -rf on cache paths — high blast radius",
        "detail": "Keep dry-run default; confirm UI before deep clean",
        "scope": "suite_readonly",
        "check": "design_review",
    })

    scored = _compute_score(findings, industrial_checks)
    report: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "engine": "pcs_security_audit_engine_v20260802",
        "industrial_root": str(INDUSTRIAL_ROOT),
        "pcs_state": str(PCS_STATE),
        "score": scored["score"],
        "grade": scored["grade"],
        "scoring": scored["scoring"],
        "industrial_checks": industrial_checks,
        "industrial_pass_count": sum(1 for c in industrial_checks if c.get("pass")),
        "industrial_check_count": len(industrial_checks),
        "scanned_py_files": scanned_files,
        "suite_readonly_files": suite_scanned,
        "findings": findings,
        "findings_count": len(findings),
        "hardened": hardened,
        "report_path": str(report_path or LATEST_REPORT),
        "report_written": None,
        "note": (
            "Originals under Desktop/PhantomCloak* were not modified. "
            "Suite scanned read-only if present. "
            ".venv/site-packages excluded from AST scan to avoid false-zero scores."
        ),
    }

    if write_report:
        target = Path(report_path) if report_path is not None else LATEST_REPORT
        report["report_written"] = str(target)
        report["report_path"] = str(target)
        write_audit_report(report, target)
    else:
        report["report_written"] = None

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="PCS Industrial security audit engine (ASVS-aligned light audit)",
    )
    parser.add_argument(
        "--no-suite",
        action="store_true",
        help="Skip read-only Suite client module scan",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write ~/.pcs_industrial_20260802/audit_reports/latest.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Print full JSON report to stdout (default)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print short human summary instead of full JSON",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 0 if score>=75, 3 if score>=40, else 1",
    )
    args = parser.parse_args(argv)

    report = run_full_audit(
        include_suite_readonly=not args.no_suite,
        write_report=not args.no_write,
    )

    if args.summary:
        print(f"score={report['score']} grade={report['grade']}")
        print(
            f"industrial_checks={report['industrial_pass_count']}/"
            f"{report['industrial_check_count']}"
        )
        for c in report.get("industrial_checks") or []:
            flag = "PASS" if c.get("pass") else "FAIL"
            print(f"  [{flag}] {c.get('id')}: {c.get('summary')}")
        print(f"findings={report.get('findings_count')} report={report.get('report_written')}")
    else:
        print(json.dumps(report, indent=2, default=str))

    if args.exit_code:
        s = int(report.get("score") or 0)
        if s >= 75:
            return 0
        if s >= 40:
            return 3
        return 1
    return 0


if __name__ == "__main__":
    # Ensure industrial root on sys.path for `python3 path/to/engine.py`
    _root = str(INDUSTRIAL_ROOT)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    raise SystemExit(main())
