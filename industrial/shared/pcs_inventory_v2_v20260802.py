#!/usr/bin/env python3
"""Multi-IP inventory v2 for industrial fleet pools.

Compatible with v1 single-ip locations; upgrades to pool[] members.
"""
from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STATE = Path.home() / ".pcs_industrial_20260802"
INVENTORY_PATH = STATE / "vps_inventory.json"

# Import IP validation from materialize when available
def _is_real_ip(value: str) -> bool:
    try:
        from shared.pcs_materialize_singbox_v20260802 import is_real_ip

        return is_real_ip(value)
    except Exception:
        pass
    if not value or not re.match(r"^(?:\d{1,3}\.){3}\d{1,3}$", value.strip()):
        return False
    parts = [int(x) for x in value.split(".")]
    if any(p > 255 for p in parts):
        return False
    a, b = parts[0], parts[1]
    if a in (0, 10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
        return False
    if a == 169 and b == 254:
        return False
    if (a, b, parts[2]) in ((192, 0, 2), (198, 51, 100), (203, 0, 113)):
        return False
    return True


def _purpose_routing_template() -> Dict[str, List[str]]:
    try:
        from shared.pcs_purpose_routing_v20260802 import purpose_routing_template

        return purpose_routing_template()
    except Exception:
        return {}


def ensure_purpose_routing(data: Dict[str, Any]) -> bool:
    """Ensure non-empty purpose_routing on inventory dict. Returns True if mutated."""
    existing = data.get("purpose_routing")
    if isinstance(existing, dict) and existing:
        return False
    data["purpose_routing"] = _purpose_routing_template()
    return True


def default_inventory_v2() -> Dict[str, Any]:
    return {
        "version": 2,
        "ssh_user": "root",
        "note": "pool[].ip = owned public IPv4 only. purpose_routing maps use-cases to location keys.",
        "locations": {},
        "purpose_routing": _purpose_routing_template(),
    }


def load_inventory(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load inventory; migrate v1→v2 and always persist purpose_routing when missing."""
    p = path or INVENTORY_PATH
    if not p.exists():
        data = default_inventory_v2()
        save_inventory(data, p)
        return data
    raw = json.loads(p.read_text())
    had_routing = bool(isinstance(raw.get("purpose_routing"), dict) and raw.get("purpose_routing"))
    was_v1 = int(raw.get("version") or 1) < 2
    data = migrate_v1_to_v2(raw)
    routing_filled = ensure_purpose_routing(data)
    # Write purpose_routing (and any v1→v2 upgrade) into inventory on load
    if was_v1 or not had_routing or routing_filled:
        save_inventory(data, p)
    return data


def migrate_v1_to_v2(data: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(data)
    out["version"] = 2
    locs = out.setdefault("locations", {})
    for name, meta in list(locs.items()):
        if not isinstance(meta, dict):
            continue
        if "pool" in meta and isinstance(meta["pool"], list):
            continue
        ip = (meta.get("ip") or "").strip()
        pool = []
        if ip:
            pool.append(
                {
                    "id": f"{name}-01",
                    "ip": ip,
                    "ssh_user": meta.get("ssh_user") or out.get("ssh_user") or "root",
                    "tier": "primary",
                    "enabled": meta.get("enabled", True),
                }
            )
        meta["pool"] = pool
        # keep ip as primary mirror for v1 readers
        meta["ip"] = pool[0]["ip"] if pool else ""
        locs[name] = meta
    ensure_purpose_routing(out)
    return out


def save_inventory(data: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Atomic inventory write at mode 0600 (never secrets; still ops-sensitive).

    Temp file is chmod'd before replace so multi-IP pool writes never briefly
    land world-readable under a permissive umask.
    """
    import tempfile

    p = path or INVENTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p.parent, 0o700)
    except OSError:
        pass
    payload = json.dumps(data, indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{p.name}.",
        suffix=".tmp",
        dir=str(p.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, p)
        os.chmod(p, 0o600)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise
    return p


def ensure_location(data: Dict[str, Any], loc: str) -> Dict[str, Any]:
    locs = data.setdefault("locations", {})
    if loc not in locs:
        locs[loc] = {"ip": "", "ssh_user": "", "enabled": True, "pool": []}
    if "pool" not in locs[loc]:
        locs[loc] = migrate_v1_to_v2({"locations": {loc: locs[loc]}, "version": 1})["locations"][loc]
    return locs[loc]


def set_pool_ips(
    loc: str,
    ips: List[str],
    *,
    ssh_user: str = "",
    data: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Replace location pool with validated IPs. Returns (data, errors)."""
    data = data if data is not None else load_inventory(path)
    errors: List[str] = []
    clean: List[str] = []
    for raw in ips:
        ip = (raw or "").strip()
        if not ip:
            continue
        if not _is_real_ip(ip):
            errors.append(f"rejected:{ip}")
            continue
        if ip not in clean:
            clean.append(ip)
    if errors and not clean:
        return data, errors
    meta = ensure_location(data, loc)
    user = ssh_user or meta.get("ssh_user") or data.get("ssh_user") or "root"
    pool = []
    for i, ip in enumerate(clean, 1):
        pool.append(
            {
                "id": f"{loc}-{i:02d}",
                "ip": ip,
                "ssh_user": user,
                "tier": "primary" if i == 1 else "rotate",
                "enabled": True,
            }
        )
    meta["pool"] = pool
    meta["ip"] = clean[0] if clean else ""
    meta["enabled"] = True
    meta["ssh_user"] = user
    save_inventory(data, path)
    return data, errors


def parse_pool_string(s: str) -> List[str]:
    """'a.b.c.d,e.f.g.h' or space-separated."""
    parts = re.split(r"[,;\s]+", (s or "").strip())
    return [p for p in parts if p]


def iter_pool_members(data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    data = data if data is not None else load_inventory()
    out: List[Dict[str, Any]] = []
    for loc, meta in (data.get("locations") or {}).items():
        if not isinstance(meta, dict):
            continue
        if not meta.get("enabled", True):
            continue
        pool = meta.get("pool") or []
        if not pool and meta.get("ip"):
            pool = [{"id": f"{loc}-01", "ip": meta["ip"], "ssh_user": meta.get("ssh_user") or "root"}]
        for m in pool:
            if not m.get("enabled", True):
                continue
            ip = (m.get("ip") or "").strip()
            if ip and _is_real_ip(ip):
                out.append(
                    {
                        "location": loc,
                        "id": m.get("id") or f"{loc}-x",
                        "ip": ip,
                        "ssh_user": m.get("ssh_user") or data.get("ssh_user") or "root",
                        "tier": m.get("tier") or "rotate",
                    }
                )
    return out


def pool_summary(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    members = iter_pool_members(data)
    by_loc: Dict[str, int] = {}
    for m in members:
        by_loc[m["location"]] = by_loc.get(m["location"], 0) + 1
    return {
        "version": 2,
        "total_real_ips": len(members),
        "locations_with_ips": len(by_loc),
        "by_location": by_loc,
        "members": members,
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Inventory v2 multi-IP pools")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--set-pool", action="append", default=[], help="loc=ip1,ip2,ip3")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = load_inventory()
    errs_all: List[str] = []
    for item in args.set_pool:
        if "=" not in item:
            errs_all.append(f"bad:{item}")
            continue
        loc, rest = item.split("=", 1)
        data, errs = set_pool_ips(loc.strip().lower(), parse_pool_string(rest), data=data)
        errs_all.extend(errs)
    s = pool_summary(data)
    if args.json:
        print(json.dumps({"summary": s, "errors": errs_all}, indent=2))
    else:
        print(f"total_real_ips={s['total_real_ips']} locations={s['locations_with_ips']}")
        for k, v in sorted(s["by_location"].items()):
            print(f"  {k}: {v}")
        if errs_all:
            print("errors:", errs_all)
    return 1 if errs_all and s["total_real_ips"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
