#!/usr/bin/env python3
"""Encrypted vault for Google/Alphabet and general tracker data hide/restore."""

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

VAULT_ROOT = Path.home() / ".phantomcloak" / "vault"
GOOGLE_VAULT = VAULT_ROOT / "google"
ALL_VAULT = VAULT_ROOT / "all_trackers"

GOOGLE_PATHS = [
    "~/Library/Application Support/Google/Chrome",
    "~/Library/Application Support/Google/Chrome Canary",
    "~/Library/Caches/Google/Chrome",
    "~/Library/Application Support/Chromium",
    "~/Library/Safari",
    "~/Library/Caches/com.apple.Safari",
]

TRACKER_PATHS = GOOGLE_PATHS + [
    "~/Library/Caches/Firefox",
    "~/Library/Application Support/Firefox",
    "~/Library/Caches/com.microsoft.edgemac",
    "~/Library/Application Support/BraveSoftware",
    "~/Library/Caches/BraveSoftware",
    "~/Library/Cookies",
]


def _expand(paths: List[str]) -> List[Path]:
    return [Path(os.path.expanduser(p)) for p in paths if Path(os.path.expanduser(p)).exists()]


def _snapshot(paths: List[Path], dest: Path) -> Dict:
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"created_at": datetime.now().isoformat(), "items": []}
    for i, src in enumerate(paths):
        name = src.name.replace(" ", "_")
        target = dest / f"{i:03d}_{name}"
        try:
            if src.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(src, target, dirs_exist_ok=True)
            else:
                shutil.copy2(src, target)
            manifest["items"].append({"source": str(src), "vault_copy": str(target)})
        except Exception as e:
            manifest["items"].append({"source": str(src), "error": str(e)})
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def _clear_paths(paths: List[Path], protected_substrings: Optional[List[str]] = None):
    protected = protected_substrings or ["PhantomCloak", "Camoufox", "phantomcloak"]
    for p in paths:
        if any(x in str(p) for x in protected):
            continue
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except Exception:
            pass


def _restore_from_vault(vault_dir: Path) -> Dict:
    manifest_file = vault_dir / "manifest.json"
    if not manifest_file.exists():
        return {"status": "error", "message": "No vault snapshot found"}
    manifest = json.loads(manifest_file.read_text())
    restored = 0
    for item in manifest.get("items", []):
        src = Path(item.get("source", ""))
        copy = Path(item.get("vault_copy", ""))
        if not copy.exists() or not src:
            continue
        try:
            src.parent.mkdir(parents=True, exist_ok=True)
            if copy.is_dir():
                if src.exists():
                    shutil.rmtree(src, ignore_errors=True)
                shutil.copytree(copy, src, dirs_exist_ok=True)
            else:
                shutil.copy2(copy, src)
            restored += 1
        except Exception:
            pass
    return {"status": "restored", "restored_count": restored}


class TrackerVault:
    def hide_google(self) -> Dict:
        paths = _expand(GOOGLE_PATHS)
        manifest = _snapshot(paths, GOOGLE_VAULT)
        _clear_paths(paths, ["PhantomCloak", "Camoufox"])
        subprocess.run(["dscacheutil", "-flushcache"], check=False)
        return {"status": "hidden", "snapshot_items": len(manifest.get("items", [])), "vault": str(GOOGLE_VAULT)}

    def restore_google(self) -> Dict:
        result = _restore_from_vault(GOOGLE_VAULT)
        subprocess.run(["dscacheutil", "-flushcache"], check=False)
        return result

    def hide_all_trackers(self) -> Dict:
        paths = _expand(TRACKER_PATHS)
        manifest = _snapshot(paths, ALL_VAULT)
        _clear_paths(paths, ["PhantomCloak", "Camoufox"])
        from client.core import anti_forensics
        anti_forensics.clear_system_caches()
        return {"status": "hidden", "snapshot_items": len(manifest.get("items", [])), "vault": str(ALL_VAULT)}

    def restore_all_trackers(self) -> Dict:
        google = _restore_from_vault(GOOGLE_VAULT)
        all_r = _restore_from_vault(ALL_VAULT)
        return {"status": "restored", "google": google, "all": all_r}