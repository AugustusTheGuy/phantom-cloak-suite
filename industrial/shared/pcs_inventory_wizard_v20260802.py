#!/usr/bin/env python3
"""Interactive / non-interactive VPS inventory wizard (industrial only).

Operator CLI for ``~/.pcs_industrial_20260802/vps_inventory.json``.

Hard rules
----------
- Industrial tree + industrial state only. Never writes Suite / ~/.phantomcloak.
- Never invents IPs. Empty stays empty until the operator supplies a real value.
- Rejects RFC1918, loopback, link-local, TEST-NET, placeholders via
  materialize ``is_real_ip`` + readiness ``is_real_public_ip``.
- Never writes secrets (UUID / Reality keys / passwords stay in secrets/).
- Atomic JSON write + chmod 600.

CLI
---
  # Interactive (default when no action flags)
  python3 pcs_inventory_wizard_v20260802.py

  # Non-interactive sets (repeatable)
  python3 pcs_inventory_wizard_v20260802.py \\
      --set dubai=x.x.x.x --set germany=y.y.y.y

  # List / clear / validate
  python3 pcs_inventory_wizard_v20260802.py --list
  python3 pcs_inventory_wizard_v20260802.py --clear-location dubai
  python3 pcs_inventory_wizard_v20260802.py --validate-only
  python3 pcs_inventory_wizard_v20260802.py --set dubai=10.0.0.1 --validate-only
      # dry-run: must fail for private IP; inventory not written

  # After successful write, optionally rematerialize clients
  python3 pcs_inventory_wizard_v20260802.py --set dubai=x.x.x.x --rematerialize

Path injection (tests / alternate state)
----------------------------------------
  --inventory PATH
  --state DIR
  env PCS_INVENTORY_PATH
  env PCS_STATE_DIR   (or PCS_INDUSTRIAL_STATE)

Exit codes
----------
  0  success
  1  validation / write / rematerialize failure
  2  usage / unknown location
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Shared industrial validators (Suite remains read-only)
# ---------------------------------------------------------------------------

try:
    from . import pcs_materialize_singbox_v20260802 as mat
    from . import pcs_server_readiness_v20260802 as ready
except ImportError:  # script-style: python3 path/to/pcs_inventory_wizard_...
    import pcs_materialize_singbox_v20260802 as mat  # type: ignore
    import pcs_server_readiness_v20260802 as ready  # type: ignore

HOME = Path.home()
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"
INVENTORY = STATE / "vps_inventory.json"
MATERIALIZE_SCRIPT = INDUSTRIAL / "shared" / "pcs_materialize_singbox_v20260802.py"

# Canonical locations (aligned with materialize LOCATIONS)
CANONICAL_LOCS: Tuple[str, ...] = tuple(mat.LOCATIONS.keys()) if hasattr(mat, "LOCATIONS") else (
    "dubai",
    "hongkong",
    "vancouver",
    "germany",
    "bahamas",
    "cayman",
    "mauritius",
    "seychelles",
)

# Operator-facing aliases → inventory key
LOC_ALIASES: Dict[str, str] = {
    "frankfurt": "germany",
    "de": "germany",
    "hk": "hongkong",
    "yvr": "vancouver",
    "uae": "dubai",
    "dxb": "dubai",
}

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

SET_PAIR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*)=(.+)$")

INVENTORY_NOTE = (
    "Set each location 'ip' to your real owned VPS public IPv4 (or hostname you control). "
    "Use pcs_inventory_wizard_v20260802.py (preferred) or edit this file carefully. "
    "Env override: PCS_VPS_<LOCATION> e.g. PCS_VPS_DUBAI=<public-ip>. "
    "Forbidden: scraped residential lists, RFC1918, TEST-NET, placeholders."
)


# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------


def configure_paths(
    *,
    home: Optional[Path] = None,
    state: Optional[Path] = None,
    inventory: Optional[Path] = None,
    industrial: Optional[Path] = None,
) -> None:
    """Rebind path globals for tests or alternate layouts."""
    global HOME, STATE, INVENTORY, INDUSTRIAL, MATERIALIZE_SCRIPT

    if home is not None:
        HOME = Path(home)
        if state is None and inventory is None:
            STATE = HOME / ".pcs_industrial_20260802"
            INVENTORY = STATE / "vps_inventory.json"
    if industrial is not None:
        INDUSTRIAL = Path(industrial)
        MATERIALIZE_SCRIPT = INDUSTRIAL / "shared" / "pcs_materialize_singbox_v20260802.py"
    if state is not None:
        STATE = Path(state)
        if inventory is None:
            INVENTORY = STATE / "vps_inventory.json"
    if inventory is not None:
        INVENTORY = Path(inventory)
        # Keep STATE as inventory parent for related ops (do not invent sibling paths)
        if state is None:
            STATE = INVENTORY.parent


def apply_env_path_overrides() -> None:
    """Apply PCS_STATE_DIR / PCS_INVENTORY_PATH before CLI flags (flags win later)."""
    state_env = os.environ.get("PCS_STATE_DIR") or os.environ.get("PCS_INDUSTRIAL_STATE")
    inv_env = os.environ.get("PCS_INVENTORY_PATH")
    kwargs: Dict[str, Path] = {}
    if state_env and str(state_env).strip():
        kwargs["state"] = Path(str(state_env).strip()).expanduser()
    if inv_env and str(inv_env).strip():
        kwargs["inventory"] = Path(str(inv_env).strip()).expanduser()
    if kwargs:
        configure_paths(**kwargs)


# ---------------------------------------------------------------------------
# Location / IP validation
# ---------------------------------------------------------------------------


def normalize_location(name: str) -> Optional[str]:
    """Map operator input to canonical inventory key, or None if unknown."""
    if not name or not isinstance(name, str):
        return None
    key = name.strip().lower().replace(" ", "")
    if not key:
        return None
    if key in LOC_ALIASES:
        key = LOC_ALIASES[key]
    if key in CANONICAL_LOCS:
        return key
    return None


def known_locations_help() -> str:
    aliases = ", ".join(f"{a}→{c}" for a, c in sorted(LOC_ALIASES.items()) if c in CANONICAL_LOCS)
    return f"canonical: {', '.join(CANONICAL_LOCS)}; aliases: {aliases}"


def classify_rejection(value: str) -> str:
    """Human reason an endpoint was rejected (no invention of replacements)."""
    v = (value or "").strip()
    if not v:
        return "empty"
    # Quick structural hints (validators remain authoritative)
    if re.search(
        r"YOUR_VPS|REPLACE_|changeme|example\.com|pending|TODO|0\.0\.0\.0",
        v,
        re.I,
    ):
        return "placeholder"
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", v):
        try:
            parts = [int(x) for x in v.split(".")]
        except ValueError:
            return "invalid_ipv4"
        if any(p < 0 or p > 255 for p in parts):
            return "invalid_ipv4"
        a, b, c = parts[0], parts[1], parts[2]
        if a == 127 or a == 0:
            return "loopback_or_unspecified"
        if a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
            return "rfc1918_private"
        if a == 169 and b == 254:
            return "link_local"
        if (a == 192 and b == 0 and c == 2) or (
            a == 198 and b == 51 and c == 100
        ) or (a == 203 and b == 0 and c == 113):
            return "test_net_documentation"
        if a >= 224:
            return "multicast_or_reserved"
    if v.endswith(".local"):
        return "mdns_local_hostname"
    if re.fullmatch(r"[\d.]+", v):
        return "invalid_ipv4"
    return "not_public_production_endpoint"


def validate_endpoint(value: Optional[str]) -> Tuple[bool, str, str]:
    """Return (ok, reason_code, message).

    Requires **both** materialize ``is_real_ip`` and readiness ``is_real_public_ip``.
    Empty is not valid for --set (clear uses --clear-location).
    """
    if value is None or not isinstance(value, str):
        return False, "empty", "endpoint is empty"
    v = value.strip()
    if not v:
        return False, "empty", "endpoint is empty"

    mat_ok = bool(mat.is_real_ip(v))
    ready_ok = bool(ready.is_real_public_ip(v))
    if mat_ok and ready_ok:
        return True, "ok", "public production endpoint"

    code = classify_rejection(v)
    parts = []
    if not mat_ok:
        parts.append("is_real_ip=false")
    if not ready_ok:
        parts.append("is_real_public_ip=false")
    detail = f"{code} ({', '.join(parts)})"
    return False, code, f"rejected {v!r}: {detail}"


# ---------------------------------------------------------------------------
# Inventory load / save (atomic, chmod 600)
# ---------------------------------------------------------------------------


def default_inventory() -> Dict[str, Any]:
    """Empty skeleton — never pre-fills IPs."""
    return {
        "version": 1,
        "ssh_user": "root",
        "note": INVENTORY_NOTE,
        "locations": {
            loc: {"ip": "", "ssh_user": "", "enabled": True} for loc in CANONICAL_LOCS
        },
        "updated_at": None,
        "updated_by": "pcs_inventory_wizard_v20260802",
    }


def load_inventory(*, create_if_missing: bool = False) -> Dict[str, Any]:
    """Load inventory JSON. Does not invent IPs.

    create_if_missing=False: missing file → in-memory skeleton only (no write).
    """
    if INVENTORY.exists():
        try:
            data = json.loads(INVENTORY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"cannot read inventory {INVENTORY}: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"inventory root must be object: {INVENTORY}")
    else:
        data = default_inventory()
        if create_if_missing:
            # Caller must still call save; we only structure memory here.
            pass

    locs = data.setdefault("locations", {})
    if not isinstance(locs, dict):
        raise ValueError("inventory.locations must be an object")
    for loc in CANONICAL_LOCS:
        entry = locs.get(loc)
        if not isinstance(entry, dict):
            locs[loc] = {"ip": "", "ssh_user": "", "enabled": True}
        else:
            entry.setdefault("ip", "")
            entry.setdefault("ssh_user", "")
            entry.setdefault("enabled", True)
    data.setdefault("version", 1)
    data.setdefault("ssh_user", "root")
    data.setdefault("note", INVENTORY_NOTE)
    return data


def write_json_atomic(path: Path, obj: Any, mode: int = 0o600) -> None:
    """Atomic JSON write: temp in same dir + os.replace + chmod 600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Strip non-serializable bookkeeping if any
    payload_obj = {k: v for k, v in obj.items() if not str(k).startswith("_")}
    payload = json.dumps(payload_obj, indent=2, sort_keys=False) + "\n"
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
        os.chmod(path, mode)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def save_inventory(data: Dict[str, Any]) -> Path:
    """Persist inventory atomically (mode 0600). Never writes secrets."""
    data = dict(data)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["updated_by"] = "pcs_inventory_wizard_v20260802"
    data["note"] = INVENTORY_NOTE
    # Ensure no secret-shaped top-level keys sneak in
    for banned in (
        "private_key",
        "uuid",
        "hy2_password",
        "obfs_password",
        "password",
        "token",
        "api_key",
    ):
        data.pop(banned, None)
    write_json_atomic(INVENTORY, data, mode=0o600)
    return INVENTORY


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


def parse_set_arg(raw: str) -> Tuple[str, str]:
    """Parse ``location=endpoint`` → (canonical_loc, endpoint). Raises ValueError."""
    m = SET_PAIR_RE.match(raw.strip())
    if not m:
        raise ValueError(
            f"invalid --set {raw!r}; expected location=ip (e.g. dubai=203.0.113.1 is "
            f"TEST-NET and will be rejected — use your real owned VPS IP)"
        )
    loc_raw, endpoint = m.group(1), m.group(2).strip()
    loc = normalize_location(loc_raw)
    if loc is None:
        raise ValueError(f"unknown location {loc_raw!r}; {known_locations_help()}")
    if not endpoint:
        raise ValueError(
            f"empty endpoint for {loc}; use --clear-location {loc} to clear"
        )
    return loc, endpoint


def apply_sets(
    data: Dict[str, Any],
    sets: Sequence[Tuple[str, str]],
    *,
    ssh_user: Optional[str] = None,
    enable: bool = True,
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Validate and apply sets in memory. Returns (data, applied_rows).

    Raises ValueError on first invalid endpoint (no partial invent).
    """
    applied: List[Dict[str, str]] = []
    errors: List[str] = []
    for loc, endpoint in sets:
        ok, code, msg = validate_endpoint(endpoint)
        if not ok:
            errors.append(f"{loc}: {msg}")
            continue
        entry = data.setdefault("locations", {}).setdefault(
            loc, {"ip": "", "ssh_user": "", "enabled": True}
        )
        entry["ip"] = endpoint.strip()
        entry["enabled"] = bool(enable)
        if ssh_user is not None and str(ssh_user).strip():
            entry["ssh_user"] = str(ssh_user).strip()
        applied.append(
            {
                "location": loc,
                "ip": entry["ip"],
                "ssh_user": entry.get("ssh_user") or data.get("ssh_user") or "root",
                "enabled": str(bool(entry.get("enabled", True))).lower(),
                "status": "set",
            }
        )
    if errors:
        raise ValueError(
            "validation failed — inventory not modified:\n  - "
            + "\n  - ".join(errors)
        )
    return data, applied


def apply_clears(
    data: Dict[str, Any],
    locations: Sequence[str],
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    cleared: List[Dict[str, str]] = []
    for raw in locations:
        loc = normalize_location(raw)
        if loc is None:
            raise ValueError(f"unknown location {raw!r}; {known_locations_help()}")
        entry = data.setdefault("locations", {}).setdefault(
            loc, {"ip": "", "ssh_user": "", "enabled": True}
        )
        prev = (entry.get("ip") or "").strip()
        entry["ip"] = ""
        cleared.append(
            {
                "location": loc,
                "ip": "",
                "previous": prev,
                "status": "cleared",
            }
        )
    return data, cleared


def inventory_rows(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    locs = data.get("locations") or {}
    for loc in CANONICAL_LOCS:
        entry = locs.get(loc) or {}
        ip = (entry.get("ip") or "").strip()
        ok, code, msg = (True, "empty", "unset") if not ip else validate_endpoint(ip)
        if not ip:
            ok, code, msg = False, "empty", "unset"
        rows.append(
            {
                "location": loc,
                "ip": ip,
                "ssh_user": (entry.get("ssh_user") or data.get("ssh_user") or "root"),
                "enabled": bool(entry.get("enabled", True)),
                "valid": bool(ok) if ip else False,
                "status": "ok" if ok and ip else code,
                "detail": msg,
            }
        )
    return rows


def validate_inventory(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate all set IPs in inventory (and optionally proposed — via apply_sets)."""
    rows = inventory_rows(data)
    set_rows = [r for r in rows if r["ip"]]
    invalid = [r for r in set_rows if not r["valid"]]
    empty = [r for r in rows if not r["ip"]]
    return {
        "ok": len(invalid) == 0,
        "path": str(INVENTORY),
        "exists": INVENTORY.exists(),
        "locations_total": len(rows),
        "ips_set": len(set_rows),
        "ips_valid": len(set_rows) - len(invalid),
        "ips_invalid": len(invalid),
        "ips_empty": len(empty),
        "invalid": [
            {"location": r["location"], "ip": r["ip"], "reason": r["status"]}
            for r in invalid
        ],
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Rematerialize (optional)
# ---------------------------------------------------------------------------


def rematerialize(*, json_mode: bool = False) -> Dict[str, Any]:
    """Call industrial materialize against current STATE / INVENTORY.

    Suite is never written. Uses subprocess for process isolation.
    """
    if not MATERIALIZE_SCRIPT.is_file():
        return {
            "ok": False,
            "error": f"materialize script missing: {MATERIALIZE_SCRIPT}",
        }

    # Align materialize + readiness path globals for in-process fallback
    mat.configure_paths(state=STATE, industrial=INDUSTRIAL)
    ready.configure_paths(state=STATE, industrial=INDUSTRIAL)

    env = os.environ.copy()
    # Prefer file inventory; do not invent env IPs
    cmd = [sys.executable, str(MATERIALIZE_SCRIPT)]
    if json_mode:
        cmd.append("--json")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"rematerialize failed to launch: {e}"}

    out: Dict[str, Any] = {
        "ok": proc.returncode in (0, 2),  # 2 = pending soft success
        "exit_code": proc.returncode,
        "command": cmd,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }
    # Try parse JSON result from stdout
    try:
        parsed = json.loads(proc.stdout or "")
        if isinstance(parsed, dict):
            out["result"] = {
                k: parsed.get(k)
                for k in (
                    "ok",
                    "configured_clients",
                    "pending_ip_locations",
                    "client_written",
                    "skip_reasons",
                    "at",
                )
                if k in parsed
            }
    except json.JSONDecodeError:
        pass
    if not out["ok"]:
        out["error"] = f"materialize exited {proc.returncode}"
    return out


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------


def format_table(rows: List[Dict[str, Any]]) -> str:
    headers = ("LOCATION", "IP", "ENABLED", "STATUS")
    col = [list(headers)]
    for r in rows:
        col.append(
            [
                str(r["location"]),
                r["ip"] or "(empty)",
                "yes" if r.get("enabled", True) else "no",
                str(r.get("status") or ""),
            ]
        )
    widths = [max(len(row[i]) for row in col) for i in range(len(headers))]
    lines = []
    for i, row in enumerate(col):
        line = "  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row))
        lines.append(line)
        if i == 0:
            lines.append("  ".join("-" * widths[j] for j in range(len(headers))))
    return "\n".join(lines)


def print_list(data: Dict[str, Any], *, as_json: bool = False) -> None:
    report = validate_inventory(data)
    if as_json:
        print(json.dumps(report, indent=2))
        return
    print(f"inventory: {INVENTORY}")
    print(f"exists:    {INVENTORY.exists()}")
    print(f"ips_set:   {report['ips_set']}  valid={report['ips_valid']}  "
          f"invalid={report['ips_invalid']}  empty={report['ips_empty']}")
    print()
    print(format_table(report["rows"]))
    if report["invalid"]:
        print()
        print("invalid entries (fix or re-set with public owned VPS IPs):")
        for inv in report["invalid"]:
            print(f"  - {inv['location']}: {inv['ip']!r} ({inv['reason']})")


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------


def run_interactive(
    *,
    ssh_user: Optional[str] = None,
    rematerialize_after: bool = False,
    as_json: bool = False,
) -> int:
    """Prompt per location; blank keeps current; 'clear' clears; Ctrl-C aborts."""
    data = load_inventory(create_if_missing=False)
    print("PCS Industrial — VPS inventory wizard", file=sys.stderr)
    print(f"File: {INVENTORY}", file=sys.stderr)
    print(
        "Enter a public IPv4 or controlled hostname per location.\n"
        "  blank  = keep current\n"
        "  clear  = unset IP\n"
        "  q      = quit without saving\n"
        "Rejected: private/TEST-NET/placeholders (is_real_ip + is_real_public_ip).\n"
        "Never paste scraped residential lists.\n",
        file=sys.stderr,
    )
    print_list(data, as_json=False)
    print(file=sys.stderr)

    pending_sets: List[Tuple[str, str]] = []
    pending_clears: List[str] = []

    try:
        for loc in CANONICAL_LOCS:
            cur = ((data.get("locations") or {}).get(loc) or {}).get("ip") or ""
            prompt = f"{loc} [{cur or 'empty'}]: "
            try:
                raw = input(prompt)
            except EOFError:
                print("\nEOF — aborting without save.", file=sys.stderr)
                return EXIT_USAGE
            ans = (raw or "").strip()
            if ans.lower() in ("q", "quit", "exit"):
                print("Aborted — no changes written.", file=sys.stderr)
                return EXIT_USAGE
            if not ans:
                continue
            if ans.lower() in ("clear", "none", "unset", "-"):
                pending_clears.append(loc)
                continue
            ok, code, msg = validate_endpoint(ans)
            if not ok:
                print(f"  ✗ {msg}", file=sys.stderr)
                # re-prompt once
                raw2 = input(f"  retry {loc} (blank=skip): ").strip()
                if not raw2:
                    continue
                if raw2.lower() in ("clear", "none", "unset", "-"):
                    pending_clears.append(loc)
                    continue
                ok2, _, msg2 = validate_endpoint(raw2)
                if not ok2:
                    print(f"  ✗ still invalid: {msg2} — skipping {loc}", file=sys.stderr)
                    continue
                pending_sets.append((loc, raw2))
                continue
            pending_sets.append((loc, ans))
    except KeyboardInterrupt:
        print("\nInterrupted — no changes written.", file=sys.stderr)
        return EXIT_USAGE

    if not pending_sets and not pending_clears:
        print("No changes.", file=sys.stderr)
        if as_json:
            print(json.dumps({"ok": True, "changed": False, "path": str(INVENTORY)}, indent=2))
        return EXIT_OK

    print(file=sys.stderr)
    print("Pending changes:", file=sys.stderr)
    for loc, ip in pending_sets:
        print(f"  set   {loc} = {ip}", file=sys.stderr)
    for loc in pending_clears:
        print(f"  clear {loc}", file=sys.stderr)
    confirm = input("Write inventory? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Aborted — no changes written.", file=sys.stderr)
        return EXIT_USAGE

    try:
        if pending_clears:
            data, _ = apply_clears(data, pending_clears)
        if pending_sets:
            data, _ = apply_sets(data, pending_sets, ssh_user=ssh_user)
        path = save_inventory(data)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return EXIT_FAIL
    except OSError as e:
        print(f"write failed: {e}", file=sys.stderr)
        return EXIT_FAIL

    result: Dict[str, Any] = {
        "ok": True,
        "changed": True,
        "path": str(path),
        "mode": oct(path.stat().st_mode & 0o777),
        "sets": [{"location": l, "ip": i} for l, i in pending_sets],
        "cleared": list(pending_clears),
    }
    print(f"Wrote {path} mode {result['mode']}", file=sys.stderr)

    if rematerialize_after:
        rm = rematerialize(json_mode=True)
        result["rematerialize"] = rm
        if not rm.get("ok"):
            print(f"rematerialize failed: {rm.get('error')}", file=sys.stderr)
            if as_json:
                print(json.dumps(result, indent=2))
            return EXIT_FAIL
        print("rematerialize: ok", file=sys.stderr)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print_list(load_inventory(), as_json=False)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Non-interactive orchestration
# ---------------------------------------------------------------------------


def run_noninteractive(args: argparse.Namespace) -> int:
    data = load_inventory(create_if_missing=False)
    as_json = bool(args.json)
    validate_only = bool(args.validate_only)
    did_mutate_request = bool(args.set or args.clear_location or getattr(args, "set_pool", None))

    # Multi-IP pool path (inventory v2) — preferred for fleets
    set_pool = list(getattr(args, "set_pool", None) or [])
    if set_pool and not validate_only:
        from shared.pcs_inventory_v2_v20260802 import (
            load_inventory as load_v2,
            parse_pool_string,
            set_pool_ips,
            pool_summary,
        )

        v2 = load_v2()
        all_errs: List[str] = []
        for raw in set_pool:
            if "=" not in raw:
                all_errs.append(f"bad set-pool arg: {raw}")
                continue
            loc, rest = raw.split("=", 1)
            v2, errs = set_pool_ips(
                loc.strip().lower(),
                parse_pool_string(rest),
                ssh_user=args.ssh_user or "",
                data=v2,
            )
            all_errs.extend(errs)
        summary = pool_summary(v2)
        # Refresh legacy view
        data = load_inventory(create_if_missing=False)
        if as_json:
            print(
                json.dumps(
                    {
                        "ok": summary["total_real_ips"] > 0 and not (
                            all_errs and summary["total_real_ips"] == 0
                        ),
                        "mode": "set_pool",
                        "summary": summary,
                        "rejected": all_errs,
                        "wrote": True,
                    },
                    indent=2,
                )
            )
        else:
            print(
                f"set-pool wrote inventory v2  total_real_ips={summary['total_real_ips']}  "
                f"locations={summary['locations_with_ips']}"
            )
            for k, n in sorted(summary["by_location"].items()):
                print(f"  {k}: {n} ip(s)")
            if all_errs:
                print("rejected:", all_errs)
        if args.rematerialize and summary["total_real_ips"] > 0:
            result = rematerialize(json_mode=as_json)
            ok = bool(result.get("ok", result.get("returncode", 1) in (0, 2)))
            return EXIT_OK if ok else EXIT_FAIL
        return EXIT_OK if summary["total_real_ips"] > 0 or not all_errs else EXIT_FAIL

    # --list only
    if args.list and not did_mutate_request and not validate_only:
        print_list(data, as_json=as_json)
        report = validate_inventory(data)
        # list is informational; exit 1 only if invalid IPs present
        return EXIT_OK if report["ok"] else EXIT_FAIL

    proposed_sets: List[Tuple[str, str]] = []
    try:
        for raw in args.set or []:
            proposed_sets.append(parse_set_arg(raw))
    except ValueError as e:
        err = {"ok": False, "error": str(e)}
        if as_json:
            print(json.dumps(err, indent=2))
        else:
            print(str(e), file=sys.stderr)
        return EXIT_USAGE

    # Validate-only path: check existing and/or proposed without writing
    if validate_only:
        report: Dict[str, Any] = {
            "ok": True,
            "validate_only": True,
            "path": str(INVENTORY),
            "wrote": False,
        }
        errors: List[str] = []

        # Existing inventory
        existing = validate_inventory(data)
        report["existing"] = {
            "ips_set": existing["ips_set"],
            "ips_valid": existing["ips_valid"],
            "ips_invalid": existing["ips_invalid"],
            "invalid": existing["invalid"],
        }
        if existing["invalid"] and not proposed_sets and not (args.clear_location):
            # bare --validate-only on dirty inventory
            errors.extend(
                f"{i['location']}: {i['ip']!r} ({i['reason']})" for i in existing["invalid"]
            )

        # Proposed sets
        proposed_ok: List[Dict[str, str]] = []
        proposed_bad: List[Dict[str, str]] = []
        for loc, endpoint in proposed_sets:
            ok, code, msg = validate_endpoint(endpoint)
            row = {"location": loc, "ip": endpoint.strip(), "status": code, "detail": msg}
            if ok:
                proposed_ok.append(row)
            else:
                proposed_bad.append(row)
                errors.append(f"{loc}: {msg}")

        report["proposed_ok"] = proposed_ok
        report["proposed_rejected"] = proposed_bad
        report["ok"] = len(errors) == 0 and (
            # if only validating existing and no invalid
            (bool(proposed_sets) and not proposed_bad)
            or (not proposed_sets and not existing["invalid"])
            or (bool(proposed_sets) and not proposed_bad)
        )
        # Clarify: with proposed sets, existing invalid does not block dry-run of new sets
        if proposed_sets:
            report["ok"] = len(proposed_bad) == 0
        else:
            report["ok"] = len(existing["invalid"]) == 0

        if as_json:
            print(json.dumps(report, indent=2))
        else:
            print(f"validate-only  path={INVENTORY}  wrote=false")
            if proposed_sets:
                print(f"proposed ok:       {len(proposed_ok)}")
                print(f"proposed rejected: {len(proposed_bad)}")
                for b in proposed_bad:
                    print(f"  ✗ {b['location']}: {b['detail']}")
                for g in proposed_ok:
                    print(f"  ✓ {g['location']}: {g['ip']}")
            else:
                print(f"existing invalid:  {existing['ips_invalid']}")
                for i in existing["invalid"]:
                    print(f"  ✗ {i['location']}: {i['ip']!r} ({i['reason']})")
                if existing["ips_invalid"] == 0:
                    print("  ✓ all set endpoints pass is_real_ip + is_real_public_ip")
            if not report["ok"]:
                sys.stdout.flush()
                print("FAIL — no inventory write performed", file=sys.stderr, flush=True)
        return EXIT_OK if report["ok"] else EXIT_FAIL

    # Mutating path
    if not did_mutate_request:
        # No flags → interactive (handled by main)
        return run_interactive(
            ssh_user=args.ssh_user,
            rematerialize_after=bool(args.rematerialize),
            as_json=as_json,
        )

    applied: List[Dict[str, str]] = []
    cleared: List[Dict[str, str]] = []
    try:
        if args.clear_location:
            data, cleared = apply_clears(data, args.clear_location)
        if proposed_sets:
            data, applied = apply_sets(
                data,
                proposed_sets,
                ssh_user=args.ssh_user,
                enable=not bool(args.disable),
            )
        path = save_inventory(data)
    except ValueError as e:
        if as_json:
            print(json.dumps({"ok": False, "error": str(e), "wrote": False}, indent=2))
        else:
            print(str(e), file=sys.stderr)
            print("FAIL — inventory not written", file=sys.stderr)
        return EXIT_FAIL
    except OSError as e:
        if as_json:
            print(json.dumps({"ok": False, "error": str(e), "wrote": False}, indent=2))
        else:
            print(f"write failed: {e}", file=sys.stderr)
        return EXIT_FAIL

    result: Dict[str, Any] = {
        "ok": True,
        "wrote": True,
        "path": str(path),
        "mode": oct(path.stat().st_mode & 0o777),
        "applied": applied,
        "cleared": cleared,
        "summary": validate_inventory(data),
    }

    if args.rematerialize:
        rm = rematerialize(json_mode=True)
        result["rematerialize"] = {
            k: rm.get(k) for k in ("ok", "exit_code", "error", "result") if k in rm or k == "error"
        }
        if not rm.get("ok"):
            result["ok"] = False
            if as_json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Wrote {path} but rematerialize failed: {rm.get('error')}", file=sys.stderr)
            return EXIT_FAIL

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Wrote {path} mode {result['mode']}")
        if applied:
            for a in applied:
                print(f"  set   {a['location']} = {a['ip']}")
        if cleared:
            for c in cleared:
                prev = c.get("previous") or "(empty)"
                print(f"  clear {c['location']} (was {prev})")
        if args.rematerialize:
            print("  rematerialize: ok")
        print()
        print_list(data, as_json=False)
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="pcs_inventory_wizard_v20260802",
        description=(
            "Set / list / clear / validate owned VPS public IPs in industrial "
            "vps_inventory.json. Never invents IPs. Suite is read-only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  %(prog)s --list\n"
            "  %(prog)s --set dubai=x.x.x.x --set germany=y.y.y.y\n"
            "  %(prog)s --set-pool germany=1.2.3.4,5.6.7.8,9.9.9.9\n"
            "  %(prog)s --set dubai=10.0.0.1 --validate-only   # must fail\n"
            "  %(prog)s --clear-location dubai\n"
            "  %(prog)s --set dubai=x.x.x.x --rematerialize\n"
            "  PCS_INVENTORY_PATH=/tmp/inv.json %(prog)s --list\n"
            "\n"
            "exit codes:\n"
            "  0  success\n"
            "  1  validation / write / rematerialize failure\n"
            "  2  usage error\n"
        ),
    )
    p.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="LOC=IP",
        help="Set location endpoint (repeatable). Public IPv4 or controlled hostname.",
    )
    p.add_argument(
        "--set-pool",
        action="append",
        default=[],
        metavar="LOC=IP1,IP2,...",
        help="Set multi-IP pool for location (inventory v2). Comma-separated public IPs.",
    )
    p.add_argument(
        "--clear-location",
        action="append",
        default=[],
        metavar="LOC",
        help="Clear IP for location (repeatable).",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List inventory rows and validation status.",
    )
    p.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate existing and/or --set endpoints; never write.",
    )
    p.add_argument(
        "--rematerialize",
        action="store_true",
        help="After successful write, run pcs_materialize_singbox_v20260802.",
    )
    p.add_argument(
        "--ssh-user",
        metavar="USER",
        help="SSH user stored on --set locations (default inventory ssh_user/root).",
    )
    p.add_argument(
        "--disable",
        action="store_true",
        help="Mark --set locations enabled=false (still stores IP).",
    )
    p.add_argument(
        "--inventory",
        metavar="PATH",
        help="Override inventory path (else PCS_INVENTORY_PATH / default state file).",
    )
    p.add_argument(
        "--state",
        metavar="DIR",
        help="Override state dir (else PCS_STATE_DIR / ~/.pcs_industrial_20260802).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON on stdout.",
    )
    p.add_argument(
        "--interactive",
        action="store_true",
        help="Force interactive prompts even if other flags present (rare).",
    )
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    apply_env_path_overrides()
    args = parse_args(argv)

    if args.state:
        configure_paths(state=Path(args.state).expanduser())
    if args.inventory:
        configure_paths(inventory=Path(args.inventory).expanduser())

    # Keep materialize/readiness validators' path view consistent when rematerializing
    # (validators themselves are path-agnostic; rematerialize calls configure_paths).

    action_flags = bool(
        args.set
        or args.clear_location
        or args.list
        or args.validate_only
        or getattr(args, "set_pool", None)
    )

    if args.interactive or not action_flags:
        return run_interactive(
            ssh_user=args.ssh_user,
            rematerialize_after=bool(args.rematerialize),
            as_json=bool(args.json),
        )

    return run_noninteractive(args)


if __name__ == "__main__":
    sys.exit(main())
