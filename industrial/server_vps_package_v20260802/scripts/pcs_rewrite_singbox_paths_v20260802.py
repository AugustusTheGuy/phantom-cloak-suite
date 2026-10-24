#!/usr/bin/env python3
"""Rewrite Mac/local absolute cert paths in filled sing-box server JSON → VPS paths.

Industrial only. Used by pcs_deploy_one and deploy_filled_to_vps generation.

Default VPS layout:
  /etc/sing-box/config.json
  /etc/sing-box/hy2_certs/<location>/fullchain.pem
  /etc/sing-box/hy2_certs/<location>/privkey.pem

Usage:
  python3 pcs_rewrite_singbox_paths_v20260802.py \\
      --in  ~/.pcs_industrial_20260802/vps_server_package/sing-box-dubai-reality.json \\
      --out /tmp/sing-box-dubai-vps.json \\
      --location dubai

  # dry-run: print planned rewrites, still write if --out given unless --no-write
  python3 pcs_rewrite_singbox_paths_v20260802.py --in CFG --location dubai --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

VPS_SINGBOX_ROOT = "/etc/sing-box"
PATH_KEYS = frozenset(
    {
        "certificate_path",
        "key_path",
        "certificate",
        "key",
        "cert_path",
        "private_key_path",
    }
)

# Match hy2_certs/<loc>/filename anywhere in a path string
HY2_RE = re.compile(
    r"(?:^|[/\\])hy2_certs[/\\](?P<loc>[A-Za-z0-9_-]+)[/\\](?P<file>[^/\\]+)\s*$"
)
# Mac/home absolute paths that must never ship to VPS as-is
MAC_HOME_RE = re.compile(
    r"^/(?:Users|home)/[^/]+/|^/var/folders/|/Desktop/|/Documents/"
)


def vps_hy2_path(location: str, filename: str) -> str:
    return f"{VPS_SINGBOX_ROOT}/hy2_certs/{location}/{filename}"


def rewrite_path(value: str, location: str) -> Tuple[str, bool]:
    """Return (new_path, changed)."""
    if not isinstance(value, str) or not value.strip():
        return value, False
    raw = value.strip()
    m = HY2_RE.search(raw.replace("\\", "/"))
    if m:
        loc = m.group("loc") or location
        fname = m.group("file")
        # Prefer explicit --location when path loc differs from request (staging packages)
        use_loc = location or loc
        new = vps_hy2_path(use_loc, fname)
        return new, new != raw

    # Basename heuristics for known cert files under any Mac package path
    base = Path(raw.replace("\\", "/")).name
    if base in ("fullchain.pem", "cert.pem", "certificate.pem") and (
        MAC_HOME_RE.search(raw) or "hy2" in raw.lower() or "pcs_industrial" in raw
    ):
        new = vps_hy2_path(location, "fullchain.pem")
        return new, new != raw
    if base in ("privkey.pem", "key.pem", "private.key", "private.pem") and (
        MAC_HOME_RE.search(raw) or "hy2" in raw.lower() or "pcs_industrial" in raw
    ):
        new = vps_hy2_path(location, "privkey.pem")
        return new, new != raw

    # Any remaining Mac absolute path under path-like keys → refuse silently by mapping
    # into /etc/sing-box/<basename> so check fails loud if wrong file.
    if MAC_HOME_RE.search(raw) or raw.startswith("/Users/"):
        new = f"{VPS_SINGBOX_ROOT}/{base}"
        return new, new != raw

    return raw, False


def walk_rewrite(
    obj: Any, location: str, changes: List[Dict[str, str]], path: str = "$"
) -> Any:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            key_path = f"{path}.{k}"
            if k in PATH_KEYS and isinstance(v, str):
                new_v, changed = rewrite_path(v, location)
                if changed:
                    changes.append({"path": key_path, "from": v, "to": new_v})
                out[k] = new_v
            else:
                out[k] = walk_rewrite(v, location, changes, key_path)
        return out
    if isinstance(obj, list):
        return [
            walk_rewrite(item, location, changes, f"{path}[{i}]")
            for i, item in enumerate(obj)
        ]
    return obj


def rewrite_config(
    data: Dict[str, Any], location: str
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    changes: List[Dict[str, str]] = []
    new_data = walk_rewrite(data, location, changes)
    return new_data, changes


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Rewrite sing-box Mac paths → /etc/sing-box")
    p.add_argument("--in", dest="inp", required=True, help="Input server JSON")
    p.add_argument("--out", dest="out", default="", help="Output JSON path")
    p.add_argument("--location", required=True, help="Location key (dubai, hongkong, …)")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned rewrites; do not write unless --out is also forced",
    )
    p.add_argument(
        "--write-on-dry-run",
        action="store_true",
        help="With --dry-run, still write --out (for local staging demos)",
    )
    p.add_argument("--indent", type=int, default=2)
    args = p.parse_args(argv)

    inp = Path(args.inp).expanduser().resolve()
    if not inp.is_file():
        print(f"ERROR: input not found: {inp}", file=sys.stderr)
        return 2

    data = load_json(inp)
    rewritten, changes = rewrite_config(data, args.location.strip().lower())

    print(f"# rewrite location={args.location} in={inp}")
    if not changes:
        print("# no path changes needed (or no cert path keys present)")
    for c in changes:
        print(f"# {c['path']}:")
        print(f"#   from: {c['from']}")
        print(f"#   to:   {c['to']}")

    should_write = bool(args.out) and (not args.dry_run or args.write_on_dry_run)
    if should_write:
        outp = Path(args.out).expanduser()
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(
            json.dumps(rewritten, indent=args.indent) + "\n", encoding="utf-8"
        )
        print(f"# wrote {outp}")
    elif args.dry_run:
        print("# dry-run: skipped write")
    elif not args.out:
        # stdout JSON for piping
        print(json.dumps(rewritten, indent=args.indent))

    # Exit 0 always on success; machine-readable summary on stderr as JSON line
    summary = {
        "ok": True,
        "location": args.location,
        "changes": len(changes),
        "dry_run": bool(args.dry_run),
        "wrote": should_write,
        "out": args.out or None,
    }
    print(json.dumps(summary), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
