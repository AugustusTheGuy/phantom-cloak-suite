#!/usr/bin/env python3
"""Validate industrial sing-box package + client shapes with `sing-box check`.

Industrial tree only. Does NOT invent inventory IPs or touch Suite originals.

Checks
------
1. Every filled server JSON under ~/.pcs_industrial_20260802/vps_server_package/
2. Every live client JSON under ~/.pcs_industrial_20260802/singbox/*.json
   (skips *.pending.json sidecars)
3. Ephemeral client *shapes* for all LOCATIONS (and pending locs) using a
   non-routable shape-check host that is NEVER written to inventory

Exit codes
----------
  0  all checks passed
  1  sing-box missing, import failure, or any check failed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HOME = Path.home()
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"
VPS_PKG = STATE / "vps_server_package"
SINGBOX_CLIENT = STATE / "singbox"
SHARED = Path(__file__).resolve().parent

# Shape-only dial target for pending client builders. Not written to inventory.
# 198.51.100.0/24 is TEST-NET-2 (RFC 5737 documentation); is_real_ip rejects it.
SHAPE_CHECK_SERVER = "198.51.100.10"


def _ensure_import_path() -> None:
    p = str(SHARED)
    if p not in sys.path:
        sys.path.insert(0, p)


def _sing_box_bin() -> Optional[str]:
    return shutil.which("sing-box")


def _run_check(path: Path) -> Tuple[bool, str]:
    bin_path = _sing_box_bin()
    if not bin_path:
        return False, "sing-box not found on PATH"
    r = subprocess.run(
        [bin_path, "check", "-c", str(path)],
        capture_output=True,
        text=True,
    )
    msg = (r.stderr or r.stdout or "").strip()
    return r.returncode == 0, msg


def _security_audit_server(cfg: Dict[str, Any], path: Path) -> List[str]:
    """Soft security/correctness findings (do not fail check unless structural)."""
    warns: List[str] = []
    inbounds = cfg.get("inbounds") or []
    if not inbounds:
        warns.append("no inbounds")
    has_vless = False
    has_block = False
    for ib in inbounds:
        if ib.get("type") == "vless":
            has_vless = True
            tls = ib.get("tls") or {}
            reality = tls.get("reality") or {}
            if not reality.get("enabled"):
                warns.append("vless without reality.enabled")
            hs = reality.get("handshake") or {}
            sni = tls.get("server_name")
            if sni and hs.get("server") and hs.get("server") != sni:
                warns.append(f"handshake.server ({hs.get('server')}) != server_name ({sni})")
            if hs.get("server_port") not in (443, None):
                warns.append(f"unusual handshake.server_port={hs.get('server_port')}")
            sids = reality.get("short_id") or []
            for sid in sids:
                if not isinstance(sid, str) or not all(
                    c in "0123456789abcdefABCDEF" for c in sid
                ):
                    warns.append(f"non-hex short_id: {sid!r}")
            transport = ib.get("transport") or {}
            users = ib.get("users") or []
            for u in users:
                flow = u.get("flow") or ""
                if transport.get("type") == "http" and flow:
                    warns.append("Vision flow set with HTTP transport (incompatible)")
                if transport.get("type") != "http" and flow not in (
                    "",
                    "xtls-rprx-vision",
                ):
                    warns.append(f"unexpected flow={flow!r}")
        if ib.get("type") == "hysteria2":
            tls = ib.get("tls") or {}
            if not tls.get("enabled"):
                warns.append("hy2 without tls.enabled (required 1.12+)")
            for k in ("certificate_path", "key_path"):
                p = tls.get(k)
                if p and not Path(p).exists():
                    warns.append(f"hy2 {k} missing on disk: {p}")
    for ob in cfg.get("outbounds") or []:
        if ob.get("type") == "block" or ob.get("tag") == "block":
            has_block = True
    if not has_vless:
        warns.append("no vless inbound")
    if not has_block:
        warns.append("no block outbound (recommended for explicit reject)")
    # geosite must not appear
    route = cfg.get("route") or {}
    for rule in route.get("rules") or []:
        if "geosite" in rule or "geoip" in rule:
            warns.append("deprecated geosite/geoip rule present")
    _ = path
    return warns


def _security_audit_client(cfg: Dict[str, Any]) -> List[str]:
    warns: List[str] = []
    for ib in cfg.get("inbounds") or []:
        if ib.get("type") == "tun":
            if "inet4_address" in ib or "inet6_address" in ib:
                warns.append("legacy tun inet4_address/inet6_address (removed in 1.12)")
            if "address" not in ib:
                warns.append("tun missing address[]")
    for ob in cfg.get("outbounds") or []:
        if ob.get("type") == "vless":
            tls = ob.get("tls") or {}
            utls = tls.get("utls") or {}
            if not utls.get("enabled") or utls.get("fingerprint") != "chrome":
                warns.append("vless utls fingerprint should be chrome")
            reality = tls.get("reality") or {}
            if not reality.get("enabled"):
                warns.append("vless without reality")
            mux = ob.get("multiplex") or {}
            if mux.get("enabled") is True:
                warns.append("multiplex enabled on Reality (prefer off)")
            transport = ob.get("transport") or {}
            flow = ob.get("flow") or ""
            if transport.get("type") == "http" and flow == "xtls-rprx-vision":
                warns.append("Vision + HTTP transport")
            if transport.get("type") != "http" and flow and flow != "xtls-rprx-vision":
                warns.append(f"unexpected flow={flow!r}")
    dns = cfg.get("dns") or {}
    for srv in dns.get("servers") or []:
        if isinstance(srv, dict) and "address" in srv and "type" not in srv:
            warns.append("legacy DNS server form (address) — migrate for 1.12+")
    route = cfg.get("route") or {}
    for rule in route.get("rules") or []:
        if "geosite" in rule or "geoip" in rule:
            warns.append("deprecated geosite/geoip rule present")
    return warns


def validate_package_servers() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not VPS_PKG.exists():
        return [
            {
                "kind": "server_package",
                "path": str(VPS_PKG),
                "ok": False,
                "error": "vps_server_package missing — run materialize first",
            }
        ]
    files = sorted(VPS_PKG.glob("sing-box-*-reality.json"))
    if not files:
        results.append(
            {
                "kind": "server_package",
                "path": str(VPS_PKG),
                "ok": False,
                "error": "no sing-box-*-reality.json files",
            }
        )
        return results
    for path in files:
        try:
            cfg = json.loads(path.read_text())
        except Exception as e:
            results.append(
                {
                    "kind": "server",
                    "path": str(path),
                    "ok": False,
                    "error": f"json: {e}",
                }
            )
            continue
        ok, msg = _run_check(path)
        warns = _security_audit_server(cfg, path)
        results.append(
            {
                "kind": "server",
                "path": str(path),
                "name": path.name,
                "ok": ok,
                "error": None if ok else msg,
                "warnings": warns,
            }
        )
    return results


def validate_live_clients() -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not SINGBOX_CLIENT.exists():
        return results
    for path in sorted(SINGBOX_CLIENT.glob("*.json")):
        if path.name.endswith(".pending.json"):
            continue
        try:
            cfg = json.loads(path.read_text())
        except Exception as e:
            results.append(
                {
                    "kind": "client",
                    "path": str(path),
                    "ok": False,
                    "error": f"json: {e}",
                }
            )
            continue
        # Sidecar-like pending without full config
        if cfg.get("status") == "pending_vps_ip":
            continue
        if "outbounds" not in cfg:
            results.append(
                {
                    "kind": "client",
                    "path": str(path),
                    "ok": False,
                    "error": "not a sing-box client config (missing outbounds)",
                }
            )
            continue
        ok, msg = _run_check(path)
        warns = _security_audit_client(cfg)
        results.append(
            {
                "kind": "client",
                "path": str(path),
                "name": path.name,
                "ok": ok,
                "error": None if ok else msg,
                "warnings": warns,
            }
        )
    return results


def validate_pending_and_all_shapes(
    *, only: Optional[Sequence[str]] = None
) -> List[Dict[str, Any]]:
    """Build ephemeral client shapes for each location and run sing-box check."""
    _ensure_import_path()
    from pcs_materialize_singbox_v20260802 import (  # type: ignore
        LOCATIONS,
        build_client_config,
        build_server_config,
        client_shape_summary,
        load_or_create_secrets,
    )

    results: List[Dict[str, Any]] = []
    secrets = load_or_create_secrets(rotate=False, only_locations=None, persist=False)
    locs = list(only) if only else list(LOCATIONS.keys())
    tmp_root = Path(tempfile.mkdtemp(prefix="pcs_sb_validate_"))
    try:
        for loc in locs:
            if loc not in LOCATIONS:
                results.append(
                    {
                        "kind": "shape",
                        "location": loc,
                        "ok": False,
                        "error": "unknown location",
                    }
                )
                continue
            meta = LOCATIONS[loc]
            sec = secrets["locations"][loc]
            # Server shape (no write to package unless already present)
            server_cfg = build_server_config(loc, meta, sec, create_certs=True)
            s_path = tmp_root / f"server-{loc}.json"
            s_path.write_text(json.dumps(server_cfg, indent=2) + "\n")
            ok_s, msg_s = _run_check(s_path)
            warns_s = _security_audit_server(server_cfg, s_path)
            results.append(
                {
                    "kind": "server_shape",
                    "location": loc,
                    "path": str(s_path),
                    "ok": ok_s,
                    "error": None if ok_s else msg_s,
                    "warnings": warns_s,
                }
            )

            client_cfg = build_client_config(loc, meta, sec, SHAPE_CHECK_SERVER)
            c_path = tmp_root / f"client-{loc}.json"
            c_path.write_text(json.dumps(client_cfg, indent=2) + "\n")
            ok_c, msg_c = _run_check(c_path)
            warns_c = _security_audit_client(client_cfg)
            shape = client_shape_summary(loc, meta)
            results.append(
                {
                    "kind": "client_shape",
                    "location": loc,
                    "path": str(c_path),
                    "ok": ok_c,
                    "error": None if ok_c else msg_c,
                    "warnings": warns_c,
                    "shape": shape,
                    "shape_server": SHAPE_CHECK_SERVER,
                }
            )
    finally:
        # Keep temp only if PCS_VALIDATE_KEEP_TMP=1 for debug
        if os.environ.get("PCS_VALIDATE_KEEP_TMP") == "1":
            results.append(
                {
                    "kind": "meta",
                    "ok": True,
                    "path": str(tmp_root),
                    "note": "tmp kept (PCS_VALIDATE_KEEP_TMP=1)",
                }
            )
        else:
            shutil.rmtree(tmp_root, ignore_errors=True)
    return results


def run_all(*, only: Optional[Sequence[str]] = None, shapes: bool = True) -> Dict[str, Any]:
    bin_path = _sing_box_bin()
    if not bin_path:
        return {
            "ok": False,
            "error": "sing-box not found on PATH",
            "results": [],
        }
    ver = subprocess.run(
        [bin_path, "version"], capture_output=True, text=True
    ).stdout.strip().splitlines()
    version_line = ver[0] if ver else "unknown"

    results: List[Dict[str, Any]] = []
    results.extend(validate_package_servers())
    results.extend(validate_live_clients())
    if shapes:
        try:
            results.extend(validate_pending_and_all_shapes(only=only))
        except Exception as e:
            results.append(
                {
                    "kind": "shape_batch",
                    "ok": False,
                    "error": f"{type(e).__name__}: {e}",
                }
            )

    failed = [r for r in results if not r.get("ok", False) and r.get("kind") != "meta"]
    warned = [r for r in results if r.get("warnings")]
    return {
        "ok": len(failed) == 0,
        "sing_box": bin_path,
        "version": version_line,
        "checked": len([r for r in results if r.get("kind") != "meta"]),
        "failed": len(failed),
        "with_warnings": len(warned),
        "package_dir": str(VPS_PKG),
        "client_dir": str(SINGBOX_CLIENT),
        "failures": [
            {
                "kind": r.get("kind"),
                "path": r.get("path") or r.get("location"),
                "error": r.get("error"),
            }
            for r in failed
        ],
        "results": results,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run sing-box check on industrial package + client shapes"
    )
    ap.add_argument(
        "--package-only",
        action="store_true",
        help="Only check on-disk vps_server_package JSON files",
    )
    ap.add_argument(
        "--location",
        action="append",
        dest="locations",
        help="Limit shape checks to location(s); repeatable",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="Only print summary line + failures",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    report = run_all(only=args.locations, shapes=not args.package_only)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"sing-box: {report.get('version')} ({report.get('sing_box')})")
        print(
            f"checked={report.get('checked')} failed={report.get('failed')} "
            f"warnings_on={report.get('with_warnings')} ok={report.get('ok')}"
        )
        if not args.quiet:
            for r in report.get("results") or []:
                if r.get("kind") == "meta":
                    continue
                status = "OK" if r.get("ok") else "FAIL"
                label = r.get("name") or r.get("location") or r.get("path") or r.get("kind")
                line = f"  [{status}] {r.get('kind')}: {label}"
                if r.get("error"):
                    line += f" — {r['error'][:160]}"
                print(line)
                for w in r.get("warnings") or []:
                    print(f"         warn: {w}")
        for f in report.get("failures") or []:
            if args.quiet:
                print(f"FAIL {f.get('kind')} {f.get('path')}: {f.get('error')}")

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
