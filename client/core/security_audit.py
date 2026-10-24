#!/usr/bin/env python3
"""PhantomCloak security audit — protections, permissions, vault hygiene, process hygiene."""

from __future__ import annotations

import os
import stat
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

STATE_DIR = Path.home() / ".phantomcloak"
ACCOUNTS_DIR = STATE_DIR / "accounts"
SENSITIVE_NAMES = (
    "last_session.json",
    "cloud_config.json",
    "cloud_vault.enc",
    "device_id",
    "pre_phantomcloak_state.json",
    "pre_anti_detection_state.json",
    "translation.json",
)


def _check_file_perms(path: Path, max_mode: int = 0o600) -> Dict[str, Any]:
    if not path.exists():
        return {"ok": True, "note": "not present"}
    mode = path.stat().st_mode & 0o777
    return {"ok": mode <= max_mode, "mode": oct(mode), "path": str(path)}


def harden_state_permissions() -> List[Dict[str, Any]]:
    """Best-effort: tighten ~/.phantomcloak sensitive files (owner-only)."""
    fixed: List[Dict[str, Any]] = []
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(STATE_DIR, 0o700)
        fixed.append({"path": str(STATE_DIR), "mode": "0o700"})
    except OSError as e:
        fixed.append({"path": str(STATE_DIR), "error": str(e)})
    for name in SENSITIVE_NAMES:
        p = STATE_DIR / name
        if p.is_file():
            try:
                p.chmod(0o600)
                fixed.append({"path": str(p), "mode": "0o600"})
            except OSError as e:
                fixed.append({"path": str(p), "error": str(e)})
    if ACCOUNTS_DIR.is_dir():
        try:
            ACCOUNTS_DIR.chmod(0o700)
        except OSError:
            pass
        for f in ACCOUNTS_DIR.glob("*.json"):
            try:
                f.chmod(0o600)
                fixed.append({"path": str(f), "mode": "0o600"})
            except OSError as e:
                fixed.append({"path": str(f), "error": str(e)})
    log = STATE_DIR / "killswitch.log"
    if log.is_file():
        try:
            log.chmod(0o600)
            fixed.append({"path": str(log), "mode": "0o600"})
        except OSError:
            pass
    return fixed


def run_audit(app=None, *, auto_harden: bool = True) -> Dict[str, Any]:
    findings: List[Dict[str, Any]] = []
    score = 100
    hardened: List[Dict[str, Any]] = []
    if auto_harden:
        hardened = harden_state_permissions()

    # Directory mode
    if STATE_DIR.exists():
        dmode = STATE_DIR.stat().st_mode & 0o777
        if dmode & 0o077:
            findings.append({
                "severity": "medium",
                "issue": "State directory group/world accessible",
                "detail": {"mode": oct(dmode), "path": str(STATE_DIR)},
            })
            score -= 8

    for name in SENSITIVE_NAMES:
        p = STATE_DIR / name
        r = _check_file_perms(p)
        if p.exists() and not r["ok"]:
            findings.append({
                "severity": "medium",
                "issue": f"Loose permissions on {p.name}",
                "detail": r,
            })
            score -= 5

    if ACCOUNTS_DIR.exists():
        for f in ACCOUNTS_DIR.glob("*.json"):
            r = _check_file_perms(f)
            if not r["ok"]:
                findings.append({
                    "severity": "medium",
                    "issue": f"Account file permissions: {f.name}",
                    "detail": r,
                })
                score -= 3

    # Password hashing strength (account vault)
    weak_hash = False
    if ACCOUNTS_DIR.exists():
        for f in ACCOUNTS_DIR.glob("*.json"):
            try:
                data = __import__("json").loads(f.read_text())
                if data.get("password_hash") and data.get("password_salt"):
                    # Single-round SHA256 is offline-brute-force friendly
                    weak_hash = True
                    break
            except Exception:
                continue
    if weak_hash:
        findings.append({
            "severity": "medium",
            "issue": "Account passwords use single-round SHA-256 (prefer Argon2id/scrypt/bcrypt)",
            "detail": {"recommendation": "Upgrade client/core/account_manager.py hashing"},
        })
        score -= 8

    # Killswitch / active consistency
    ks_active = getattr(app, "kill_switch_armed", False) if app else False
    active = getattr(app, "phantomcloak_active", False) if app else False
    if active and not ks_active:
        findings.append({
            "severity": "high",
            "issue": "PhantomCloak active without killswitch",
            "detail": {},
        })
        score -= 15
    elif active and ks_active:
        findings.append({
            "severity": "info",
            "issue": "Killswitch armed while active",
            "detail": {"ok": True},
        })

    # pf status
    try:
        pf = subprocess.run(
            ["pfctl", "-s", "info"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        pf_on = "Enabled" in (pf.stdout or "")
        if active and not pf_on:
            findings.append({
                "severity": "high",
                "issue": "pf firewall not enabled during active session",
            })
            score -= 20
        elif not active:
            findings.append({
                "severity": "info",
                "issue": f"pf Enabled={pf_on} (standby expected while inactive)",
                "detail": {"pf_enabled": pf_on},
            })
    except Exception:
        findings.append({"severity": "low", "issue": "Could not verify pf status"})
        score -= 2

    # Tunnel process
    singbox_running = False
    try:
        r = subprocess.run(
            ["pgrep", "-f", "sing-box"],
            capture_output=True,
            timeout=2,
            check=False,
        )
        singbox_running = r.returncode == 0
    except Exception:
        pass
    if active and not singbox_running:
        findings.append({
            "severity": "medium",
            "issue": "sing-box not detected while session marked active",
        })
        score -= 10

    # pf conf in /tmp (world-readable risk if not cleaned)
    tmp_pf = Path("/tmp/delphi_killswitch.pf.conf")
    if tmp_pf.exists():
        mode = tmp_pf.stat().st_mode & 0o777
        findings.append({
            "severity": "low" if mode <= 0o600 else "medium",
            "issue": "Killswitch rules written under /tmp (prefer ~/.phantomcloak)",
            "detail": {"path": str(tmp_pf), "mode": oct(mode)},
        })
        score -= 3 if mode <= 0o600 else 6

    # Stale "active" session without process
    session = STATE_DIR / "last_session.json"
    if session.exists() and not active:
        try:
            s = __import__("json").loads(session.read_text())
            if s.get("active") and not singbox_running:
                findings.append({
                    "severity": "low",
                    "issue": "last_session.json marks active=true but suite not running (stale session flag)",
                    "detail": {"saved_at": s.get("saved_at")},
                })
                score -= 3
        except Exception:
            pass

    cloud_cfg = STATE_DIR / "cloud_config.json"
    if not cloud_cfg.exists():
        findings.append({
            "severity": "info",
            "issue": "Cloud vault using encrypted local fallback",
            "detail": {"recommendation": "Configure Supabase only if multi-device sync is required"},
        })

    score = max(0, min(100, score))
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
    return {
        "timestamp": datetime.now().isoformat(),
        "score": score,
        "grade": grade,
        "findings": findings,
        "checks_passed": sum(1 for f in findings if f.get("severity") == "info"),
        "issues": sum(1 for f in findings if f.get("severity") in ("high", "medium")),
        "hardened": hardened,
        "summary": {
            "active": active,
            "killswitch": ks_active,
            "singbox_running": singbox_running,
            "state_dir": str(STATE_DIR),
        },
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_audit(None, auto_harden=True), indent=2))
