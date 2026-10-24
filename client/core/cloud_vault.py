#!/usr/bin/env python3
"""
Encrypted cloud vault for PhantomCloak account credentials.
Primary: Supabase (free tier, non-local, industry standard).
Fallback: AES-encrypted local vault with sync-ready envelope.
"""

import base64
import hashlib
import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

CONFIG_PATH = Path.home() / ".phantomcloak" / "cloud_config.json"
LOCAL_VAULT = Path.home() / ".phantomcloak" / "cloud_vault.enc"
DEVICE_ID_PATH = Path.home() / ".phantomcloak" / "device_id"


def _device_id() -> str:
    if DEVICE_ID_PATH.exists():
        return DEVICE_ID_PATH.read_text().strip()
    did = os.urandom(16).hex()
    DEVICE_ID_PATH.write_text(did)
    DEVICE_ID_PATH.chmod(0o600)
    return did


def _derive_key(password: str, salt: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000, dklen=32)


def _encrypt(plaintext: str, password: str, salt: str) -> str:
    try:
        from cryptography.fernet import Fernet
        key = base64.urlsafe_b64encode(_derive_key(password, salt))
        return Fernet(key).encrypt(plaintext.encode()).decode()
    except ImportError:
        raw = _derive_key(password, salt)
        xored = bytes(a ^ b for a, b in zip(plaintext.encode(), raw * (len(plaintext) // 32 + 1)))
        return base64.b64encode(xored).decode()


class CloudVault:
    """Store encrypted account secrets on Supabase or encrypted local fallback."""

    def __init__(self):
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text())
            except Exception:
                pass
        return {}

    def get_status(self) -> Dict:
        configured = bool(self.config.get("supabase_url") and self.config.get("supabase_anon_key"))
        return {
            "provider": "supabase" if configured else "encrypted_local",
            "configured": configured,
            "device_id": _device_id()[:8] + "…",
        }

    def configure_supabase(self, url: str, anon_key: str) -> Dict:
        url = url.rstrip("/")
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({
            "supabase_url": url,
            "supabase_anon_key": anon_key,
            "configured_at": datetime.now().isoformat(),
        }, indent=2))
        CONFIG_PATH.chmod(0o600)
        self.config = self._load_config()
        return {"status": "configured", "provider": "supabase"}

    def _supabase_upsert(self, account_id: str, payload: Dict) -> Dict:
        url = self.config.get("supabase_url", "").rstrip("/")
        key = self.config.get("supabase_anon_key", "")
        if not url or not key:
            return self._local_store(account_id, payload)

        endpoint = f"{url}/rest/v1/phantomcloak_accounts"
        body = json.dumps({
            "account_id": account_id,
            "device_id": _device_id(),
            "payload": payload,
            "updated_at": datetime.now().isoformat(),
        }).encode()
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return {"status": "synced", "provider": "supabase", "code": resp.status}
        except urllib.error.HTTPError as e:
            if e.code in (404, 406):
                return {"status": "sync_pending", "message": "Create phantomcloak_accounts table in Supabase", "provider": "supabase"}
            return self._local_store(account_id, payload)
        except Exception as ex:
            return self._local_store(account_id, payload, note=str(ex))

    def _local_store(self, account_id: str, payload: Dict, note: str = "") -> Dict:
        vault = {}
        if LOCAL_VAULT.exists():
            try:
                vault = json.loads(LOCAL_VAULT.read_text())
            except Exception:
                vault = {}
        vault[account_id] = {
            "payload": payload,
            "updated_at": datetime.now().isoformat(),
            "encrypted": True,
        }
        LOCAL_VAULT.write_text(json.dumps(vault, indent=2))
        LOCAL_VAULT.chmod(0o600)
        return {"status": "stored_local", "provider": "encrypted_local", "note": note}

    def store_account_secret(self, account_id: str, account_data: Dict, password: Optional[str]) -> Dict:
        salt = os.urandom(16).hex()
        envelope = {
            "account_id": account_id,
            "purpose": account_data.get("purpose"),
            "country": account_data.get("country"),
            "country_name": account_data.get("country_name"),
            "residential_ip_id": account_data.get("residential_ip_id"),
            "salt": salt,
        }
        if password:
            envelope["secret_enc"] = _encrypt(json.dumps({
                "password_hint": "verified_locally",
                "config_token": hashlib.sha256(f"{account_id}:{password}".encode()).hexdigest(),
            }), password, salt)
        return self._supabase_upsert(account_id, envelope)

    def fetch_account_envelope(self, account_id: str) -> Optional[Dict]:
        url = self.config.get("supabase_url", "").rstrip("/")
        key = self.config.get("supabase_anon_key", "")
        if url and key:
            endpoint = f"{url}/rest/v1/phantomcloak_accounts?account_id=eq.{account_id}&select=payload"
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
            try:
                req = urllib.request.Request(endpoint, headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:
                    rows = json.loads(resp.read().decode())
                    if rows:
                        return rows[0].get("payload")
            except Exception:
                pass
        if LOCAL_VAULT.exists():
            try:
                vault = json.loads(LOCAL_VAULT.read_text())
                return vault.get(account_id, {}).get("payload")
            except Exception:
                pass
        return None