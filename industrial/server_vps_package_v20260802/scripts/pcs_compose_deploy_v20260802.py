#!/usr/bin/env python3
"""Compose industrial deploy_filled_to_vps.sh from inventory (standalone).

Robust Mac→/etc/sing-box path rewrite is delegated to
pcs_rewrite_singbox_paths_v20260802.py + pcs_deploy_one_v20260802.sh.

Usage:
  python3 pcs_compose_deploy_v20260802.py
  python3 pcs_compose_deploy_v20260802.py --dry-run
  python3 pcs_compose_deploy_v20260802.py --out /path/to/deploy_filled_to_vps.sh
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HOME = Path.home()
STATE = HOME / ".pcs_industrial_20260802"
VPS_PKG = STATE / "vps_server_package"
INVENTORY = STATE / "vps_inventory.json"
INDUSTRIAL_SCRIPTS = Path(__file__).resolve().parent

PLACEHOLDER_IP_RE = re.compile(
    r"YOUR_VPS|your-.*-vps|REPLACE_|changeme|example\.com|pending|TODO|0\.0\.0\.0",
    re.I,
)
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def configure_paths(
    *,
    home: Optional[Path] = None,
    state: Optional[Path] = None,
    vps_pkg: Optional[Path] = None,
    inventory: Optional[Path] = None,
    industrial_scripts: Optional[Path] = None,
) -> None:
    """Override module paths (hermetic tests / alternate state roots)."""
    global HOME, STATE, VPS_PKG, INVENTORY, INDUSTRIAL_SCRIPTS
    if home is not None:
        HOME = Path(home)
    if state is not None:
        STATE = Path(state)
    elif home is not None:
        STATE = HOME / ".pcs_industrial_20260802"
    if vps_pkg is not None:
        VPS_PKG = Path(vps_pkg)
    elif state is not None or home is not None:
        VPS_PKG = STATE / "vps_server_package"
    if inventory is not None:
        INVENTORY = Path(inventory)
    elif state is not None or home is not None:
        INVENTORY = STATE / "vps_inventory.json"
    if industrial_scripts is not None:
        INDUSTRIAL_SCRIPTS = Path(industrial_scripts)


def is_real_ip(value: Optional[str]) -> bool:
    if not value or not isinstance(value, str):
        return False
    v = value.strip()
    if PLACEHOLDER_IP_RE.search(v):
        return False
    if not IPV4_RE.match(v):
        if "." in v and not PLACEHOLDER_IP_RE.search(v) and " " not in v:
            if v.endswith(".local"):
                return False
            return True
        return False
    parts = [int(x) for x in v.split(".")]
    if any(p > 255 for p in parts):
        return False
    a, b = parts[0], parts[1]
    if a in (127, 0, 10):
        return False
    if a == 192 and b == 168:
        return False
    if a == 172 and 16 <= b <= 31:
        return False
    if a == 169 and b == 254:
        return False
    if a == 198 and b == 51 and parts[2] == 100:
        return False
    if a == 203 and b == 0 and parts[2] == 113:
        return False
    if a == 192 and b == 0 and parts[2] == 2:
        return False
    return True


def load_inventory() -> Dict[str, Any]:
    if not INVENTORY.exists():
        return {"ssh_user": "root", "locations": {}}
    return json.loads(INVENTORY.read_text(encoding="utf-8"))


def locations_with_config(pkg: Path) -> List[str]:
    locs = []
    for p in sorted(pkg.glob("sing-box-*-reality.json")):
        # sing-box-<loc>-reality.json
        name = p.name
        if name.startswith("sing-box-") and name.endswith("-reality.json"):
            loc = name[len("sing-box-") : -len("-reality.json")]
            locs.append(loc)
    return locs


def compose(dry_run: bool = False) -> str:
    inv = load_inventory()
    default_user = (inv.get("ssh_user") or "root").strip() or "root"
    locs_meta = inv.get("locations") or {}
    scripts_dir = VPS_PKG / "scripts"
    deploy_one = scripts_dir / "pcs_deploy_one_v20260802.sh"
    # Prefer industrial tree script path if package scripts not yet synced
    industrial_deploy_one = INDUSTRIAL_SCRIPTS / "pcs_deploy_one_v20260802.sh"
    deploy_one_ref = deploy_one if deploy_one.exists() else industrial_deploy_one

    lines: List[str] = [
        "#!/usr/bin/env bash",
        "# Generated industrial multi-VPS deploy — NO real IPs embedded by default.",
        f"# Generated: {datetime.now(timezone.utc).isoformat()}",
        "# Usage:",
        f"#   bash {VPS_PKG}/deploy_filled_to_vps.sh           # live (needs inventory IPs)",
        f"#   bash {VPS_PKG}/deploy_filled_to_vps.sh --dry-run # plan only",
        "# Or single host:",
        f"#   {deploy_one_ref} [--dry-run] user@host location",
        "set -euo pipefail",
        f'PKG="{VPS_PKG}"',
        f'SCRIPTS="{scripts_dir}"',
        f'DEPLOY_ONE="${{SCRIPTS}}/pcs_deploy_one_v20260802.sh"',
        'if [[ ! -x "$DEPLOY_ONE" ]]; then',
        f'  DEPLOY_ONE="{industrial_deploy_one}"',
        "fi",
        'DRY=0',
        'for a in "$@"; do',
        '  case "$a" in --dry-run|-n) DRY=1 ;; esac',
        "done",
        'echo "[deploy_filled] pkg=$PKG dry_run=$DRY"',
        "",
    ]

    deployed = 0
    pending: List[str] = []

    for loc in locations_with_config(VPS_PKG):
        meta = locs_meta.get(loc) or {}
        ip = (meta.get("ip") or "").strip()
        user = (meta.get("ssh_user") or default_user).strip() or "root"
        enabled = meta.get("enabled", True)
        env_key = f"PCS_VPS_{loc.upper()}"
        env_ip = os.environ.get(env_key, "").strip()
        if env_ip:
            ip = env_ip

        if not enabled:
            lines.append(f'echo "[deploy_filled] skip {loc} (disabled)"')
            pending.append(loc)
            continue

        if is_real_ip(ip):
            deployed += 1
            target = f"{user}@{ip}"
            lines.append(f'echo "=== Deploy {loc} → {target} ==="')
            lines.append('if [[ "$DRY" -eq 1 ]]; then')
            lines.append(f'  bash "$DEPLOY_ONE" --dry-run "{target}" "{loc}"')
            lines.append("else")
            lines.append(f'  bash "$DEPLOY_ONE" "{target}" "{loc}"')
            lines.append("fi")
            lines.append("")
        else:
            pending.append(loc)
            lines.append(
                f'echo "[deploy_filled] NO-OP {loc}: set locations.{loc}.ip in inventory '
                f'or export {env_key}=x.x.x.x (then re-compose / materialize)"'
            )

    lines.append("")
    lines.append(
        f'echo "[deploy_filled] done. live_targets={deployed} pending={len(pending)}"'
    )
    if pending:
        lines.append(
            f'echo "[deploy_filled] pending locations: {" ".join(pending)}"'
        )
    lines.append(
        'if [[ "$DRY" -eq 1 ]]; then echo "PCS_DEPLOY_FILLED_DRY_RUN=OK"; fi'
    )
    lines.append("")

    # If zero live targets, script is still valid and safe (all no-ops)
    if deployed == 0:
        lines.insert(
            12,
            '# NOTE: no real inventory IPs — this script only prints NO-OP lines unless --dry-run on deploy_one via env demos.',
        )

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Compose deploy_filled_to_vps.sh")
    ap.add_argument(
        "--out",
        default=str(VPS_PKG / "deploy_filled_to_vps.sh"),
        help="Output shell path",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print composed script to stdout; do not write",
    )
    args = ap.parse_args(argv)

    text = compose(dry_run=args.dry_run)
    if args.dry_run:
        print(text)
        print(
            json.dumps({"ok": True, "dry_run": True, "bytes": len(text)}),
            file=sys.stderr,
        )
        return 0

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.chmod(out, 0o700)
    print(
        json.dumps(
            {
                "ok": True,
                "wrote": str(out),
                "bytes": len(text),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
