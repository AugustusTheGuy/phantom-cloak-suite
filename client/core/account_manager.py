#!/usr/bin/env python3
"""PhantomCloak saved account profiles with cloud-synced encrypted credentials."""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from client.core.country_flags import flag_for
from client.core.cloud_vault import CloudVault

ACCOUNTS_DIR = Path.home() / ".phantomcloak" / "accounts"
ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
ACTIVE_FILE = ACCOUNTS_DIR / "_active.json"


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


class AccountManager:
    def __init__(self):
        self.cloud = CloudVault()

    def list_accounts(self) -> List[Dict]:
        accounts = []
        for f in sorted(ACCOUNTS_DIR.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                data = json.loads(f.read_text())
                code = data.get("country", "")
                accounts.append({
                    "id": f.stem,
                    "name": data.get("name", f.stem),
                    "purpose": data.get("purpose"),
                    "country": code,
                    "country_name": data.get("country_name"),
                    "country_flag": flag_for(code),
                    "residential_ip_id": data.get("residential_ip_id"),
                    "protected": bool(data.get("password_hash")),
                    "updated_at": data.get("updated_at"),
                })
            except Exception:
                continue
        return accounts

    def save_account(self, name: str, purpose: str, country: str, country_name: str,
                     residential_ip: Dict, password: Optional[str] = None) -> Dict:
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower())
        path = ACCOUNTS_DIR / f"{safe_name}.json"
        salt = os.urandom(16).hex()
        record = {
            "name": name,
            "purpose": purpose,
            "country": country,
            "country_name": country_name,
            "country_flag": flag_for(country),
            "residential_ip_id": residential_ip.get("id"),
            "residential_ip": residential_ip,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        if password:
            record["password_salt"] = salt
            record["password_hash"] = _hash_password(password, salt)
        path.write_text(json.dumps(record, indent=2))
        path.chmod(0o600)
        sync = self.cloud.store_account_secret(safe_name, record, password)
        return {
            "status": "saved",
            "id": safe_name,
            "name": name,
            "country_flag": flag_for(country),
            "cloud_sync": sync,
        }

    def load_account(self, account_id: str, password: Optional[str] = None) -> Dict:
        path = ACCOUNTS_DIR / f"{account_id}.json"
        if not path.exists():
            return {"status": "error", "message": "Account not found"}
        data = json.loads(path.read_text())
        if data.get("password_hash"):
            if not password:
                return {"status": "password_required", "account_id": account_id, "name": data.get("name")}
            salt = data.get("password_salt", "")
            if _hash_password(password, salt) != data["password_hash"]:
                return {"status": "error", "message": "Incorrect password"}
        self.cloud.fetch_account_envelope(account_id)
        self.set_active(account_id)
        return {"status": "loaded", "account": data, "active": account_id}

    def delete_account(self, account_id: str) -> Dict:
        path = ACCOUNTS_DIR / f"{account_id}.json"
        if path.exists():
            path.unlink()
            return {"status": "deleted"}
        return {"status": "error", "message": "Not found"}

    def set_active(self, account_id: str) -> Dict:
        """Persist the single currently logged-in account (one at a time)."""
        ACTIVE_FILE.write_text(json.dumps({"account_id": account_id,
                                           "since": datetime.now().isoformat()}))
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

    def logout(self) -> Dict:
        try:
            ACTIVE_FILE.unlink()
        except Exception:
            pass
        return {"status": "logged_out"}

    def is_logged_in(self) -> bool:
        return self.get_active() is not None

    def cloud_status(self) -> Dict:
        return self.cloud.get_status()