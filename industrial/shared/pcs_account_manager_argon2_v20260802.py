#!/usr/bin/env python3
"""Account manager for PCS Industrial — Argon2id passwords (new file).

Does NOT modify Suite client/core/account_manager.py.
Stores accounts under ~/.pcs_industrial_20260802/accounts/ only.

Supports verifying legacy SHA-256 records (if imported) and re-hashing to Argon2id
on successful login/save (upgrade path).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE = Path.home() / ".pcs_industrial_20260802"
ACCOUNTS_DIR = STATE / "accounts"
ACTIVE_FILE = ACCOUNTS_DIR / "_active.json"
ALGO_ARGON2ID = "argon2id"
ALGO_LEGACY_SHA256 = "sha256_legacy"

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError

    _PH = PasswordHasher(
        time_cost=3,
        memory_cost=64 * 1024,  # 64 MiB
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )
    HAS_ARGON2 = True
except ImportError:  # pragma: no cover
    PasswordHasher = None  # type: ignore
    VerifyMismatchError = Exception  # type: ignore
    InvalidHashError = Exception  # type: ignore
    _PH = None
    HAS_ARGON2 = False


def _ensure_dirs() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        STATE.chmod(0o700)
        ACCOUNTS_DIR.chmod(0o700)
    except OSError:
        pass


def _legacy_sha256(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def hash_password(password: str) -> dict[str, str]:
    """Return storage fields for a new password (Argon2id)."""
    if not HAS_ARGON2 or _PH is None:
        raise RuntimeError(
            "argon2-cffi required. Use PCS_Industrial_20260802/.venv "
            "and: pip install argon2-cffi"
        )
    # argon2-cffi embeds salt in the PHC string
    phc = _PH.hash(password)
    return {
        "password_algo": ALGO_ARGON2ID,
        "password_hash": phc,
        "password_salt": "",  # embedded in PHC
    }


def verify_password(password: str, record: dict) -> bool:
    algo = record.get("password_algo") or ALGO_LEGACY_SHA256
    stored = record.get("password_hash") or ""
    if not stored:
        return False
    if algo == ALGO_ARGON2ID or stored.startswith("$argon2"):
        if not HAS_ARGON2 or _PH is None:
            return False
        try:
            return bool(_PH.verify(stored, password))
        except (VerifyMismatchError, InvalidHashError, Exception):
            return False
    # Legacy Suite-compatible SHA-256
    salt = record.get("password_salt") or ""
    return secrets.compare_digest(_legacy_sha256(password, salt), stored)


def needs_rehash(record: dict) -> bool:
    algo = record.get("password_algo") or ""
    stored = record.get("password_hash") or ""
    if algo != ALGO_ARGON2ID and not stored.startswith("$argon2"):
        return True
    if HAS_ARGON2 and _PH is not None and stored.startswith("$argon2"):
        try:
            return bool(_PH.check_needs_rehash(stored))
        except Exception:
            return False
    return False


class PcsAccountManagerArgon2:
    """Industrial account store with Argon2id."""

    def __init__(self) -> None:
        _ensure_dirs()

    def list_accounts(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for f in sorted(ACCOUNTS_DIR.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                data = json.loads(f.read_text())
                out.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "purpose": data.get("purpose"),
                    "country": data.get("country"),
                    "country_name": data.get("country_name"),
                    "location": data.get("location"),
                    "protected": bool(data.get("password_hash")),
                    "password_algo": data.get("password_algo") or ALGO_LEGACY_SHA256,
                    "updated_at": data.get("updated_at"),
                })
            except Exception:
                continue
        return out

    def save_account(
        self,
        name: str,
        purpose: str,
        country: str,
        country_name: str,
        location: str = "",
        residential_ip: Optional[Dict] = None,
        password: Optional[str] = None,
    ) -> Dict[str, Any]:
        _ensure_dirs()
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())
        path = ACCOUNTS_DIR / f"{safe}.json"
        now = datetime.now(timezone.utc).isoformat()
        record: Dict[str, Any] = {
            "name": name,
            "purpose": purpose,
            "country": country,
            "country_name": country_name,
            "location": location or country_name.lower().replace(" ", "_"),
            "residential_ip_id": (residential_ip or {}).get("id"),
            "residential_ip": residential_ip,
            "created_at": now,
            "updated_at": now,
        }
        if password:
            record.update(hash_password(password))
        path.write_text(json.dumps(record, indent=2))
        path.chmod(0o600)
        return {"status": "saved", "id": safe, "password_algo": record.get("password_algo")}

    def load_account(self, account_id: str, password: Optional[str] = None) -> Dict[str, Any]:
        path = ACCOUNTS_DIR / f"{account_id}.json"
        if not path.exists():
            return {"status": "error", "message": "Account not found"}
        data = json.loads(path.read_text())
        if data.get("password_hash"):
            if not password:
                return {
                    "status": "password_required",
                    "account_id": account_id,
                    "name": data.get("name"),
                }
            if not verify_password(password, data):
                return {"status": "error", "message": "Incorrect password"}
            # Upgrade legacy SHA-256 → Argon2id on successful login
            if needs_rehash(data):
                data.update(hash_password(password))
                data["updated_at"] = datetime.now(timezone.utc).isoformat()
                data["password_upgraded_to"] = ALGO_ARGON2ID
                path.write_text(json.dumps(data, indent=2))
                path.chmod(0o600)
        self.set_active(account_id)
        return {"status": "loaded", "account": data, "active": account_id}

    def set_active(self, account_id: str) -> Dict[str, Any]:
        ACTIVE_FILE.write_text(
            json.dumps({"account_id": account_id, "since": datetime.now(timezone.utc).isoformat()})
        )
        try:
            ACTIVE_FILE.chmod(0o600)
        except OSError:
            pass
        return {"status": "active", "account_id": account_id}

    def get_active(self) -> Optional[str]:
        try:
            d = json.loads(ACTIVE_FILE.read_text())
            aid = d.get("account_id")
            if aid and (ACCOUNTS_DIR / f"{aid}.json").exists():
                return aid
        except Exception:
            pass
        return None


if __name__ == "__main__":
    # smoke
    am = PcsAccountManagerArgon2()
    r = am.save_account("demo", "browsing", "CH", "Zurich", "zurich", password="test-pass-please-change")
    print(r)
    print(am.load_account(r["id"], "test-pass-please-change")["status"])
