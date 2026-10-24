#!/usr/bin/env python3
"""Post-connect leak verification bridge (PCS Industrial 20260802).

Discovers Suite verify tools READ-ONLY (never modifies them):
  ~/Desktop/PhantomCloak Suite/scripts/verify/full_verification_suite.py
  ~/Desktop/PhantomCloak Suite/scripts/verify_leaks.py
  Suite docs/HOWTO_DEPLOY_AND_VERIFY.md

Produces CEO-friendly pass/fail JSON under:
  ~/.pcs_industrial_20260802/verify_reports/

Cannot connect without a live VPS tunnel — this bridge is the ready path:
  preflight → (skip with reasons if no tunnel) → run suite when tunnel up.

Killswitch recommendation (Agent 10)
------------------------------------
  Live IP mismatch (reason=ip_mismatch_possible_leak) sets
  trip_killswitch_recommended=true on the report (ceo + top-level).
  Dry-run / offline / no-tunnel paths stay overall=NOT_RUN and never set
  the flag. Optional killswitch_trip_fn is a hook only — default is
  recommend-only (does not arm/trip industrial pf by itself).

Required env / inputs
---------------------
  PCS_VERIFY_LOCATION   Exit location key (dubai, hongkong, vancouver, …)
                        Fallback: last_session_industrial.json → location
  PCS_VERIFY_EXPECTED_IP
                        Expected public IPv4 of the exit VPS.
                        Fallback: vps_inventory.json locations.<loc>.ip
                        or PCS_VPS_<LOCATION> (e.g. PCS_VPS_DUBAI)
  PCS_VERIFY_FORCE=1    Run live IP/DNS probes even when tunnel not detected
                        (dangerous; reports will usually FAIL — real ISP IP)

Does NOT overwrite PhantomCloak Suite or legacy trees.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

HOME = Path.home()
SUITE = HOME / "Desktop" / "PhantomCloak Suite"
LEGACY = HOME / "Desktop" / "PhantomCloak"
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"
REPORTS = STATE / "verify_reports"
INVENTORY = STATE / "vps_inventory.json"
SESSION = STATE / "last_session_industrial.json"
SINGBOX_CLIENT = STATE / "singbox"

PLACEHOLDER_RE = re.compile(
    r"YOUR_VPS|127\.0\.0\.1|demo-uuid|changeme|placeholder|0\.0\.0\.0|example\.com|"
    r"REPLACE_|your-.*-vps|pending_vps_ip|pending",
    re.I,
)
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")

IP_CHECKERS = {
    "ipify": "https://api.ipify.org?format=json",
    "ipinfo": "https://ipinfo.io/json",
    "ifconfig": "https://ifconfig.me/all.json",
}

DNS_TEST_DOMAINS = ["dnsleaktest.com", "whoami.akamai.net", "ipleak.net"]

WEBRTC_GUIDANCE = {
    "url": "https://browserleaks.com/webrtc",
    "expected": "WebRTC disabled or only VPN/exit IP visible — no LAN / real ISP IP",
    "also": [
        "https://browserleaks.com/ip",
        "https://creepjs.com",
        "https://coveryourtracks.eff.org",
    ],
    "note": (
        "Open these only inside the protected browser profile (Camoufox/Delphi). "
        "Manual check — not automated in dry-run."
    ),
}

BRIDGE_VERSION = "20260802"


# ---------------------------------------------------------------------------
# Discovery (read-only)
# ---------------------------------------------------------------------------


def discover_suite_tools() -> Dict[str, Any]:
    """Locate Suite verification assets without importing or mutating them."""
    full_suite = SUITE / "scripts" / "verify" / "full_verification_suite.py"
    verify_leaks = SUITE / "scripts" / "verify_leaks.py"
    howto = SUITE / "docs" / "HOWTO_DEPLOY_AND_VERIFY.md"
    industrial_howto = INDUSTRIAL / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
    zeroleak = SUITE / "client" / "core" / "zeroleak_verifier.py"

    # legacy fallbacks (still read-only)
    if not full_suite.exists():
        alt = LEGACY / "scripts" / "verify" / "full_verification_suite.py"
        if alt.exists():
            full_suite = alt
    if not verify_leaks.exists():
        alt = LEGACY / "scripts" / "verify_leaks.py"
        if alt.exists():
            verify_leaks = alt
    if not howto.exists():
        alt = LEGACY / "docs" / "HOWTO_DEPLOY_AND_VERIFY.md"
        if alt.exists():
            howto = alt

    tools = {
        "full_verification_suite": {
            "path": str(full_suite),
            "present": full_suite.is_file(),
            "role": "IP/DNS/WebRTC + Top 30 health harness (Suite)",
        },
        "verify_leaks": {
            "path": str(verify_leaks),
            "present": verify_leaks.is_file(),
            "role": "Lightweight multi-source IP check (Suite)",
        },
        "zeroleak_verifier": {
            "path": str(zeroleak),
            "present": zeroleak.is_file(),
            "role": "On-device fail-closed preflight (Suite; industrial uses pcs_zeroleak_gate)",
        },
        "howto_deploy_and_verify": {
            "path": str(howto),
            "present": howto.is_file(),
            "role": "Canonical HOWTO verification section",
        },
        "industrial_howto": {
            "path": str(industrial_howto),
            "present": industrial_howto.is_file(),
            "role": "Industrial deploy link (materialize + inventory)",
        },
    }
    present = [k for k, v in tools.items() if v.get("present")]
    missing = [k for k, v in tools.items() if not v.get("present")]
    return {
        "suite_root": str(SUITE),
        "tools": tools,
        "present_count": len(present),
        "missing": missing,
        "full_suite_runnable": tools["full_verification_suite"]["present"],
    }


# ---------------------------------------------------------------------------
# Location / expected IP resolution
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_location(cli_location: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Return (location, source)."""
    if cli_location and cli_location.strip():
        return cli_location.strip().lower(), "cli"
    env = (os.environ.get("PCS_VERIFY_LOCATION") or "").strip().lower()
    if env:
        return env, "env:PCS_VERIFY_LOCATION"
    sess = _load_json(SESSION)
    if sess:
        loc = (sess.get("location") or "").strip().lower()
        if loc:
            return loc, "session:last_session_industrial.json"
    return None, "unset"


def resolve_expected_ip(location: Optional[str], cli_ip: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Return (ip, source) from CLI / env / inventory / PCS_VPS_<LOC>."""
    if cli_ip and cli_ip.strip():
        return cli_ip.strip(), "cli"
    env_ip = (os.environ.get("PCS_VERIFY_EXPECTED_IP") or "").strip()
    if env_ip:
        return env_ip, "env:PCS_VERIFY_EXPECTED_IP"
    if location:
        env_loc = (os.environ.get(f"PCS_VPS_{location.upper()}") or "").strip()
        if env_loc:
            return env_loc, f"env:PCS_VPS_{location.upper()}"
        inv = _load_json(INVENTORY)
        if inv:
            meta = (inv.get("locations") or {}).get(location) or {}
            ip = (meta.get("ip") or "").strip()
            if ip:
                return ip, f"inventory:{INVENTORY.name}"
    return None, "unset"


def is_real_ip(ip: Optional[str]) -> bool:
    if not ip or not IPV4_RE.match(ip.strip()):
        return False
    if PLACEHOLDER_RE.search(ip):
        return False
    parts = ip.split(".")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    if any(n < 0 or n > 255 for n in nums):
        return False
    # reject obvious non-routable placeholders used in demos
    if nums[0] == 127 or nums[0] == 0:
        return False
    return True


# ---------------------------------------------------------------------------
# Pre-flight: client config configured?
# ---------------------------------------------------------------------------


def preflight_client_config(location: Optional[str]) -> Dict[str, Any]:
    """Ensure client config exists for location and is 'configured' (real server IP)."""
    result: Dict[str, Any] = {
        "location": location,
        "configured": False,
        "status": "unknown",
        "client_path": None,
        "detail": "",
        "skip_reasons": [],
    }
    if not location:
        result["status"] = "skip"
        result["detail"] = "No exit location set (PCS_VERIFY_LOCATION or --location)"
        result["skip_reasons"].append("location_unset")
        return result

    client_path = SINGBOX_CLIENT / f"{location}.json"
    pending_path = SINGBOX_CLIENT / f"{location}.pending.json"
    result["client_path"] = str(client_path)

    if pending_path.is_file() and not client_path.is_file():
        pend = _load_json(pending_path) or {}
        result["status"] = "pending_vps_ip"
        result["detail"] = pend.get("hint") or (
            f"Only {pending_path.name} present — set inventory IP then re-run materialize"
        )
        result["skip_reasons"].append("client_pending_ip")
        result["pending_path"] = str(pending_path)
        return result

    if not client_path.is_file():
        # also check legacy industrial alias (germany → frankfurt already handled by materialize)
        result["status"] = "missing"
        result["detail"] = (
            f"No client config at {client_path}. "
            f"Set VPS IP in {INVENTORY} and run pcs_materialize_singbox_v20260802.py"
        )
        result["skip_reasons"].append("client_config_missing")
        return result

    try:
        text = client_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result["status"] = "unreadable"
        result["detail"] = str(e)[:160]
        result["skip_reasons"].append("client_config_unreadable")
        return result

    if PLACEHOLDER_RE.search(text):
        result["status"] = "placeholder"
        result["detail"] = "Client config still contains placeholder / pending tokens"
        result["skip_reasons"].append("client_config_placeholder")
        return result

    # Extract first non-private server IP from outbounds if possible
    server_ips: List[str] = []
    try:
        cfg = json.loads(text)
        for ob in cfg.get("outbounds") or []:
            sip = ob.get("server")
            if isinstance(sip, str) and is_real_ip(sip):
                server_ips.append(sip)
    except Exception:
        pass

    if not server_ips and not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
        result["status"] = "no_server_ip"
        result["detail"] = "Client config has no parseable public server IP"
        result["skip_reasons"].append("client_config_no_ip")
        return result

    result["configured"] = True
    result["status"] = "configured"
    result["server_ips"] = server_ips
    result["detail"] = f"Client config ready ({', '.join(server_ips) or 'IP present'})"
    return result


# ---------------------------------------------------------------------------
# Tunnel / connectivity probes
# ---------------------------------------------------------------------------


def detect_tunnel() -> Dict[str, Any]:
    """Detect a *PCS / sing-box* tunnel — not bare macOS utun (always present).

    Live leak checks only auto-enable when we see evidence of a real proxy tunnel:
      - interface sing0 / sing* (industrial client config uses interface_name=sing0)
      - running sing-box process
    Generic utun0..N alone is recorded as ambient_utun (NOT sufficient for live checks).
    """
    interfaces: List[str] = []
    ambient_utun: List[str] = []
    sing_ifaces: List[str] = []
    singbox_running = False
    detail = "ifconfig unavailable"
    try:
        out = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, timeout=4, check=False
        ).stdout or ""
        for line in out.splitlines():
            m = re.match(r"^([a-zA-Z][a-zA-Z0-9]*)\s*:", line)
            if not m:
                continue
            name = m.group(1)
            if name.startswith("sing") or name == "sing0":
                sing_ifaces.append(name)
                interfaces.append(name)
            elif name.startswith("utun"):
                ambient_utun.append(name)
    except Exception as e:
        detail = str(e)[:120]
        return {
            "present": False,
            "interfaces": [],
            "ambient_utun": [],
            "singbox_running": False,
            "detail": detail,
            "required_for_live_checks": True,
        }

    # process probe
    try:
        ps = subprocess.run(
            ["pgrep", "-lf", "sing-box"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if ps.returncode == 0 and (ps.stdout or "").strip():
            # avoid matching this verify script path if any
            for line in (ps.stdout or "").splitlines():
                if "sing-box" in line and "pcs_verify" not in line:
                    singbox_running = True
                    break
    except Exception:
        pass

    present = bool(sing_ifaces) or singbox_running
    if present:
        bits = []
        if sing_ifaces:
            bits.append(f"sing_ifaces={sing_ifaces}")
        if singbox_running:
            bits.append("sing-box process running")
        detail = "; ".join(bits)
    else:
        detail = (
            "no PCS tunnel (need sing0 / sing-box). "
            f"ambient utun only: {ambient_utun or 'none'} — live checks skipped"
        )
    return {
        "present": present,
        "interfaces": interfaces,
        "ambient_utun": ambient_utun,
        "singbox_running": singbox_running,
        "detail": detail,
        "required_for_live_checks": True,
    }


def _fetch_ip(name: str, url: str, timeout: float = 10.0) -> Tuple[str, Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PCS-VerifyBridge/20260802"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            return name, data if isinstance(data, dict) else {"raw": data}
    except Exception as e:
        return name, {"error": str(e)[:200]}


def run_ip_checks() -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(_fetch_ip, n, u) for n, u in IP_CHECKERS.items()]
        for f in futs:
            name, data = f.result()
            results[name] = data
    ips: List[str] = []
    for name, data in results.items():
        if "error" in data:
            continue
        ip = data.get("ip") or data.get("query") or data.get("ip_addr")
        if isinstance(ip, str) and ip:
            ips.append(ip)
    unique = sorted(set(ips))
    return {
        "sources": results,
        "observed_ips": unique,
        "consensus_ip": unique[0] if len(unique) == 1 else None,
        "consistent": len(unique) == 1,
    }


def run_dns_checks() -> Dict[str, Any]:
    dig = shutil.which("dig")
    rows: List[Dict[str, Any]] = []
    if not dig:
        return {
            "status": "skipped",
            "reason": "dig_not_available",
            "detail": "Install dig (bind tools) for DNS leak probes",
            "domains": [],
        }
    for domain in DNS_TEST_DOMAINS:
        try:
            r = subprocess.run(
                [dig, "+short", domain],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            ans = (r.stdout or "").strip()[:200]
            rows.append({"domain": domain, "answer": ans, "ok": bool(ans)})
        except Exception as e:
            rows.append({"domain": domain, "answer": "", "ok": False, "error": str(e)[:80]})
    return {
        "status": "ran",
        "domains": rows,
        "note": "Answers should not reveal your real ISP recursive resolvers for sensitive work",
    }


def evaluate_ip_vs_expected(
    observed: List[str], expected_ip: Optional[str]
) -> Dict[str, Any]:
    if not observed:
        return {
            "verdict": "fail",
            "reason": "no_public_ip_observed",
            "detail": "All IP checkers failed or returned empty",
        }
    if not expected_ip or not is_real_ip(expected_ip):
        return {
            "verdict": "inconclusive",
            "reason": "expected_ip_unset",
            "detail": (
                "Observed IP(s) recorded but no expected exit IP from inventory/env. "
                f"Observed={observed}. Set PCS_VERIFY_EXPECTED_IP or inventory."
            ),
            "observed_ips": observed,
        }
    if expected_ip in observed and len(set(observed)) == 1:
        return {
            "verdict": "pass",
            "reason": "matches_exit",
            "detail": f"All checkers report exit IP {expected_ip}",
            "observed_ips": observed,
            "expected_ip": expected_ip,
        }
    if expected_ip in observed:
        return {
            "verdict": "warn",
            "reason": "partial_match",
            "detail": f"Some checkers match {expected_ip}; others differ: {observed}",
            "observed_ips": observed,
            "expected_ip": expected_ip,
        }
    return {
        "verdict": "fail",
        "reason": "ip_mismatch_possible_leak",
        "detail": (
            f"Expected exit {expected_ip} but observed {observed}. "
            "If observed is your residential ISP IP, killswitch/routing failed."
        ),
        "observed_ips": observed,
        "expected_ip": expected_ip,
    }


def trip_killswitch_recommended_from_verdict(
    ip_verdict: Optional[Dict[str, Any]],
    *,
    dry_run: bool = False,
    live_checks: bool = False,
) -> bool:
    """True only when a *live* IP check fails on exit mismatch.

    Rules (industrial / Agent 10):
      - dry_run → always False (overall stays NOT_RUN; no recommend)
      - live_checks must have actually run
      - reason must be ip_mismatch_possible_leak (not inconclusive / no IP)
    Does not apply pf or arm killswitch — recommendation flag only.
    """
    if dry_run or not live_checks:
        return False
    if not ip_verdict:
        return False
    return (
        ip_verdict.get("verdict") == "fail"
        and ip_verdict.get("reason") == "ip_mismatch_possible_leak"
    )


# ---------------------------------------------------------------------------
# Suite runner (subprocess — no Suite imports that mutate state)
# ---------------------------------------------------------------------------


def run_full_verification_suite(
    suite_path: Path, *, as_json: bool = True, timeout: int = 90
) -> Dict[str, Any]:
    """Invoke Suite full_verification_suite.py as a subprocess (read-only use)."""
    if not suite_path.is_file():
        return {
            "status": "skipped",
            "reason": "full_verification_suite_missing",
            "detail": f"Not found: {suite_path}",
        }
    cmd = [sys.executable, str(suite_path)]
    if as_json:
        cmd.append("--json")
    try:
        # CWD = Suite root so BASE_DIR imports (health_harness) resolve
        suite_root = suite_path.resolve().parents[2]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(suite_root),
            check=False,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        parsed: Any = None
        if as_json and out:
            # Suite prints human lines then final JSON when --json
            # Try last JSON object in stdout
            parsed = _extract_trailing_json(out)
        return {
            "status": "ran" if proc.returncode == 0 else "error",
            "returncode": proc.returncode,
            "parsed": parsed,
            "stdout_tail": out[-4000:] if out else "",
            "stderr_tail": err[-1500:] if err else "",
            "command": cmd,
            "cwd": str(suite_root),
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "reason": "timeout",
            "detail": f"Suite exceeded {timeout}s",
        }
    except Exception as e:
        return {"status": "error", "reason": "exception", "detail": str(e)[:200]}


def _extract_trailing_json(text: str) -> Any:
    """Best-effort: parse last JSON object from mixed human+JSON stdout."""
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    # find last '{' that starts a balanced-ish object
    idx = text.rfind("\n{")
    if idx == -1:
        idx = text.find("{")
    else:
        idx = idx + 1
    if idx < 0:
        return None
    chunk = text[idx:]
    try:
        return json.loads(chunk)
    except Exception:
        # progressive trim from end
        for end in range(len(chunk), max(len(chunk) - 5000, 0), -1):
            try:
                return json.loads(chunk[:end])
            except Exception:
                continue
    return None


# ---------------------------------------------------------------------------
# CEO report
# ---------------------------------------------------------------------------


def _check_row(
    name: str,
    status: str,
    detail: str,
    *,
    required: bool = True,
    evidence: Any = None,
) -> Dict[str, Any]:
    """status: pass | fail | skip | warn | info"""
    row: Dict[str, Any] = {
        "name": name,
        "status": status,
        "required": required,
        "detail": detail,
    }
    if evidence is not None:
        row["evidence"] = evidence
    return row


def overall_from_checks(checks: List[Dict[str, Any]]) -> str:
    """CEO rollup: fail > warn > skip(required) > pass."""
    statuses = [c["status"] for c in checks if c.get("required", True)]
    if any(s == "fail" for s in statuses):
        return "FAIL"
    if any(s == "warn" for s in statuses):
        return "WARN"
    # required skips (e.g. no tunnel) → NOT_RUN rather than PASS
    if any(s == "skip" for s in statuses):
        return "NOT_RUN"
    if statuses and all(s in ("pass", "info") for s in statuses):
        return "PASS"
    if not statuses:
        return "NOT_RUN"
    return "WARN"


def build_report(
    *,
    location: Optional[str],
    location_source: str,
    expected_ip: Optional[str],
    expected_source: str,
    discovery: Dict[str, Any],
    preflight: Dict[str, Any],
    tunnel: Dict[str, Any],
    dry_run: bool,
    force: bool,
    ip_result: Optional[Dict[str, Any]],
    dns_result: Optional[Dict[str, Any]],
    suite_result: Optional[Dict[str, Any]],
    ip_verdict: Optional[Dict[str, Any]],
    skip_reasons: List[str],
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    # 1) Discovery
    if discovery.get("full_suite_runnable"):
        checks.append(
            _check_row(
                "suite_tools_discovered",
                "pass",
                f"full_verification_suite present ({discovery['present_count']} tools)",
                evidence={"missing": discovery.get("missing")},
            )
        )
    else:
        checks.append(
            _check_row(
                "suite_tools_discovered",
                "warn",
                "full_verification_suite.py not found — industrial probes only",
                required=False,
                evidence={"missing": discovery.get("missing")},
            )
        )

    # 2) Location
    if location:
        checks.append(
            _check_row(
                "exit_location",
                "pass",
                f"{location} (from {location_source})",
                evidence={"location": location, "source": location_source},
            )
        )
    else:
        checks.append(
            _check_row(
                "exit_location",
                "skip",
                "Set PCS_VERIFY_LOCATION or --location (e.g. dubai)",
                evidence={"source": location_source},
            )
        )
        skip_reasons.append("location_unset")

    # 3) Expected IP
    if expected_ip and is_real_ip(expected_ip):
        checks.append(
            _check_row(
                "expected_exit_ip",
                "pass",
                f"{expected_ip} (from {expected_source})",
                evidence={"ip": expected_ip, "source": expected_source},
            )
        )
    elif expected_ip:
        checks.append(
            _check_row(
                "expected_exit_ip",
                "fail",
                f"Invalid/placeholder expected IP: {expected_ip!r} ({expected_source})",
            )
        )
    else:
        checks.append(
            _check_row(
                "expected_exit_ip",
                "skip",
                "No inventory/env expected IP — live match will be inconclusive",
                evidence={"source": expected_source, "inventory": str(INVENTORY)},
            )
        )
        skip_reasons.append("expected_ip_unset")

    # 4) Client config preflight
    pf_status = preflight.get("status")
    if preflight.get("configured"):
        checks.append(
            _check_row(
                "client_config",
                "pass",
                preflight.get("detail") or "configured",
                evidence=preflight,
            )
        )
    elif pf_status in ("pending_vps_ip", "missing", "placeholder", "no_server_ip"):
        checks.append(
            _check_row(
                "client_config",
                "skip",
                preflight.get("detail") or pf_status,
                evidence=preflight,
            )
        )
        for r in preflight.get("skip_reasons") or []:
            if r not in skip_reasons:
                skip_reasons.append(r)
    else:
        checks.append(
            _check_row(
                "client_config",
                "skip",
                preflight.get("detail") or "not ready",
                evidence=preflight,
            )
        )
        skip_reasons.append("client_config_not_ready")

    # 5) Tunnel
    if tunnel.get("present"):
        checks.append(
            _check_row(
                "tunnel_interface",
                "pass",
                tunnel.get("detail") or "tun present",
                evidence=tunnel,
            )
        )
    else:
        checks.append(
            _check_row(
                "tunnel_interface",
                "skip",
                tunnel.get("detail")
                or "No tunnel — live leak checks skipped (bridge ready for post-connect)",
                evidence=tunnel,
            )
        )
        skip_reasons.append("no_tunnel")

    live_ok = bool(tunnel.get("present")) or force

    # 6) IP leak (ipify etc.)
    if dry_run and not force:
        checks.append(
            _check_row(
                "ip_leak_ipify",
                "skip",
                "Dry-run: not querying public IP services (would expose real IP without tunnel)",
            )
        )
        skip_reasons.append("dry_run")
    elif not live_ok:
        checks.append(
            _check_row(
                "ip_leak_ipify",
                "skip",
                "Skipped: no tunnel. Connect via configured client, then re-run without --dry-run",
            )
        )
    elif ip_result is None:
        checks.append(
            _check_row("ip_leak_ipify", "fail", "IP check did not run (internal)"),
        )
    else:
        verdict = ip_verdict or {}
        v = verdict.get("verdict", "fail")
        status_map = {"pass": "pass", "fail": "fail", "warn": "warn", "inconclusive": "warn"}
        checks.append(
            _check_row(
                "ip_leak_ipify",
                status_map.get(v, "fail"),
                verdict.get("detail") or v,
                evidence={
                    "observed": ip_result.get("observed_ips"),
                    "sources_keys": list((ip_result.get("sources") or {}).keys()),
                    "verdict": verdict,
                },
            )
        )

    # 7) DNS leak
    if dry_run and not force:
        checks.append(
            _check_row(
                "dns_leak",
                "skip",
                "Dry-run: DNS probes skipped",
                required=False,
            )
        )
    elif not live_ok:
        checks.append(
            _check_row(
                "dns_leak",
                "skip",
                "Skipped: no tunnel",
                required=False,
            )
        )
    elif dns_result and dns_result.get("status") == "ran":
        ok_n = sum(1 for d in dns_result.get("domains") or [] if d.get("ok"))
        checks.append(
            _check_row(
                "dns_leak",
                "pass" if ok_n else "warn",
                f"dig probes completed ({ok_n}/{len(dns_result.get('domains') or [])} answered)",
                required=False,
                evidence=dns_result,
            )
        )
    elif dns_result and dns_result.get("status") == "skipped":
        checks.append(
            _check_row(
                "dns_leak",
                "skip",
                dns_result.get("detail") or "dig missing",
                required=False,
                evidence=dns_result,
            )
        )
    else:
        checks.append(
            _check_row("dns_leak", "skip", "DNS check not run", required=False)
        )

    # 8) WebRTC guidance (always info — manual)
    checks.append(
        _check_row(
            "webrtc_guidance",
            "info",
            WEBRTC_GUIDANCE["expected"],
            required=False,
            evidence=WEBRTC_GUIDANCE,
        )
    )

    # 9) Full suite
    suite_path = Path(
        discovery.get("tools", {}).get("full_verification_suite", {}).get("path")
        or ""
    )
    suite_present = discovery.get("full_suite_runnable", False)
    if not suite_present:
        checks.append(
            _check_row(
                "full_verification_suite",
                "skip",
                f"Missing: {suite_path} — industrial IP/DNS/WebRTC guidance still available",
                required=False,
            )
        )
        skip_reasons.append("full_verification_suite_missing")
    elif dry_run and not force:
        checks.append(
            _check_row(
                "full_verification_suite",
                "skip",
                f"Present at {suite_path} — dry-run: Suite not invoked",
                required=False,
                evidence={"path": str(suite_path)},
            )
        )
    elif not live_ok:
        checks.append(
            _check_row(
                "full_verification_suite",
                "skip",
                "Suite present but no PCS tunnel (sing0/sing-box) — "
                "would measure real ISP IP if run now",
                required=False,
                evidence={"path": str(suite_path)},
            )
        )
        skip_reasons.append("suite_deferred_no_tunnel")
    elif suite_result is None:
        checks.append(
            _check_row(
                "full_verification_suite",
                "fail",
                "Suite should have run but result missing",
                required=False,
            )
        )
    else:
        st = suite_result.get("status")
        if st == "ran":
            checks.append(
                _check_row(
                    "full_verification_suite",
                    "pass",
                    "Suite completed (see evidence)",
                    required=False,
                    evidence={
                        "returncode": suite_result.get("returncode"),
                        "parsed_keys": list((suite_result.get("parsed") or {}).keys())
                        if isinstance(suite_result.get("parsed"), dict)
                        else None,
                    },
                )
            )
        elif st == "skipped":
            checks.append(
                _check_row(
                    "full_verification_suite",
                    "skip",
                    suite_result.get("detail") or suite_result.get("reason") or "skipped",
                    required=False,
                    evidence=suite_result,
                )
            )
        else:
            checks.append(
                _check_row(
                    "full_verification_suite",
                    "warn",
                    suite_result.get("detail")
                    or suite_result.get("reason")
                    or f"status={st}",
                    required=False,
                    evidence={
                        "returncode": suite_result.get("returncode"),
                        "stderr_tail": suite_result.get("stderr_tail"),
                    },
                )
            )

    # de-dupe skip_reasons
    seen: set = set()
    uniq_skips: List[str] = []
    for s in skip_reasons:
        if s not in seen:
            seen.add(s)
            uniq_skips.append(s)

    overall = overall_from_checks(checks)
    live_checks = bool(live_ok and not (dry_run and not force))
    # Dry-run / offline: always false. Live IP mismatch only → recommend trip.
    trip_ks = trip_killswitch_recommended_from_verdict(
        ip_verdict,
        dry_run=bool(dry_run and not force),
        live_checks=live_checks,
    )
    next_actions = _next_actions(
        overall, location, expected_ip, preflight, tunnel, uniq_skips
    )
    if trip_ks and "Trip killswitch; do not browse until IP matches exit" not in next_actions:
        next_actions.insert(
            0,
            "Trip killswitch (trip_killswitch_recommended=true); "
            "do not browse until observed IP matches exit",
        )
    ceo = {
        "headline": {
            "PASS": "All automated leak checks passed for the configured exit.",
            "FAIL": "Leak check FAILED — do not use this exit for sensitive work until fixed.",
            "WARN": "Checks completed with warnings — review details before high-stakes use.",
            "NOT_RUN": "Live leak checks not run (missing tunnel / VPS / config). Bridge is ready.",
        }.get(overall, overall),
        "overall": overall,
        "location": location,
        "expected_exit_ip": expected_ip if is_real_ip(expected_ip or "") else None,
        "tunnel_up": bool(tunnel.get("present")),
        "client_configured": bool(preflight.get("configured")),
        "skip_reasons": uniq_skips,
        "pass_count": sum(1 for c in checks if c["status"] == "pass"),
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
        "skip_count": sum(1 for c in checks if c["status"] == "skip"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
        "trip_killswitch_recommended": trip_ks,
        "next_actions": next_actions,
    }

    return {
        "schema": "pcs_verify_report_v1",
        "bridge_version": BRIDGE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": {
            "dry_run": dry_run,
            "force": force,
            "live_checks": live_checks,
        },
        "trip_killswitch_recommended": trip_ks,
        "ceo": ceo,
        "env_contract": {
            "PCS_VERIFY_LOCATION": "Exit location key (dubai, hongkong, …)",
            "PCS_VERIFY_EXPECTED_IP": "Expected public IPv4 of exit VPS",
            "PCS_VPS_<LOCATION>": "Alternate expected IP (e.g. PCS_VPS_DUBAI)",
            "PCS_VERIFY_FORCE": "1 = force live probes without tunnel (not recommended)",
            "inventory": str(INVENTORY),
            "reports_dir": str(REPORTS),
        },
        "discovery": discovery,
        "preflight": preflight,
        "tunnel": tunnel,
        "checks": checks,
        "ip_result": ip_result,
        "dns_result": dns_result,
        "suite_result": suite_result,
        "ip_verdict": ip_verdict,
        "webrtc": WEBRTC_GUIDANCE,
        "howto": discovery.get("tools", {}).get("howto_deploy_and_verify", {}).get("path"),
        "killswitch_trip_hook": {
            "invoked": False,
            "result": None,
            "note": (
                "Optional killswitch_trip_fn runs only when "
                "trip_killswitch_recommended=true; default is recommend-only"
            ),
        },
    }


def _next_actions(
    overall: str,
    location: Optional[str],
    expected_ip: Optional[str],
    preflight: Dict[str, Any],
    tunnel: Dict[str, Any],
    skips: List[str],
) -> List[str]:
    actions: List[str] = []
    if "location_unset" in skips:
        actions.append("Set exit: export PCS_VERIFY_LOCATION=dubai  (or --location dubai)")
    if "expected_ip_unset" in skips or not is_real_ip(expected_ip or ""):
        actions.append(
            f"Set real VPS IP in {INVENTORY} (locations.<loc>.ip) or PCS_VPS_<LOC>=x.x.x.x"
        )
    if "client_pending_ip" in skips or "client_config_missing" in skips:
        actions.append(
            "Run: python3 shared/pcs_materialize_singbox_v20260802.py  "
            "(after inventory IPs set)"
        )
    if "no_tunnel" in skips or not tunnel.get("present"):
        loc = location or "<location>"
        actions.append(
            f"Connect tunnel with client config ~/.pcs_industrial_20260802/singbox/{loc}.json "
            "(sing-box run -c …) once VPS is deployed"
        )
        actions.append(
            "Re-run: python3 -m shared.pcs_verify_bridge_v20260802 --location "
            f"{loc}   # without --dry-run when tunnel is up"
        )
    if overall == "FAIL":
        actions.append("Trip killswitch; do not browse until IP matches exit")
        actions.append("Open protected browser → https://browserleaks.com/webrtc")
    if overall == "PASS":
        actions.append("Confirm WebRTC manually in protected browser profile")
        actions.append("Periodic re-check weekly and after macOS updates")
    if not actions:
        actions.append("See docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md")
    return actions


def write_report(report: Dict[str, Any]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    loc = (report.get("ceo") or {}).get("location") or "noloc"
    overall = (report.get("ceo") or {}).get("overall") or "UNKNOWN"
    path = REPORTS / f"verify_{ts}_{loc}_{overall}.json"
    latest = REPORTS / "latest.json"
    report["report_path"] = str(path)
    report["latest_path"] = str(latest)
    payload = json.dumps(report, indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    latest.write_text(payload, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_verification(
    *,
    location: Optional[str] = None,
    expected_ip: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
    run_suite: bool = True,
    write: bool = True,
    killswitch_trip_fn: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    """Run post-connect leak verification.

    killswitch_trip_fn
        Optional hook. Invoked only when trip_killswitch_recommended is true
        (live IP mismatch). Default None = recommend-only; does not apply pf.
        Callback receives the full report dict; exceptions are caught and
        recorded under killswitch_trip_hook.result (never raise to caller).
    """
    loc, loc_src = resolve_location(location)
    exp, exp_src = resolve_expected_ip(loc, expected_ip)
    discovery = discover_suite_tools()
    preflight = preflight_client_config(loc)
    tunnel = detect_tunnel()
    skip_reasons: List[str] = list(preflight.get("skip_reasons") or [])

    force = force or (os.environ.get("PCS_VERIFY_FORCE") or "").strip() in (
        "1",
        "true",
        "yes",
    )

    # Auto dry-run when no tunnel and not forced (safe default for offline industrial)
    if not tunnel.get("present") and not force:
        dry_run = True

    live_ok = bool(tunnel.get("present")) or force
    ip_result: Optional[Dict[str, Any]] = None
    dns_result: Optional[Dict[str, Any]] = None
    suite_result: Optional[Dict[str, Any]] = None
    ip_verdict: Optional[Dict[str, Any]] = None

    if live_ok and not (dry_run and not force):
        # if force with dry_run false, or tunnel up
        if not dry_run or force:
            ip_result = run_ip_checks()
            ip_verdict = evaluate_ip_vs_expected(
                ip_result.get("observed_ips") or [], exp
            )
            dns_result = run_dns_checks()
            if run_suite and discovery.get("full_suite_runnable"):
                suite_path = Path(
                    discovery["tools"]["full_verification_suite"]["path"]
                )
                suite_result = run_full_verification_suite(suite_path, as_json=True)

    report = build_report(
        location=loc,
        location_source=loc_src,
        expected_ip=exp,
        expected_source=exp_src,
        discovery=discovery,
        preflight=preflight,
        tunnel=tunnel,
        dry_run=dry_run,
        force=force,
        ip_result=ip_result,
        dns_result=dns_result,
        suite_result=suite_result,
        ip_verdict=ip_verdict,
        skip_reasons=skip_reasons,
    )

    # Optional hook: only when live IP mismatch recommended a trip.
    # Dry-run / NOT_RUN never invoke (trip_killswitch_recommended stays false).
    hook_meta = report.get("killswitch_trip_hook") or {
        "invoked": False,
        "result": None,
        "note": "optional killswitch_trip_fn",
    }
    if report.get("trip_killswitch_recommended") and callable(killswitch_trip_fn):
        try:
            hook_result = killswitch_trip_fn(report)
            hook_meta = {
                "invoked": True,
                "result": hook_result,
                "note": "killswitch_trip_fn invoked after live IP mismatch",
            }
        except Exception as e:
            hook_meta = {
                "invoked": True,
                "result": {
                    "status": "error",
                    "detail": f"{type(e).__name__}: {e}"[:240],
                },
                "note": "killswitch_trip_fn raised; recommend flag still true",
            }
    else:
        hook_meta = {
            "invoked": False,
            "result": None,
            "note": (
                "recommend-only (no killswitch_trip_fn or trip not recommended)"
                if not report.get("trip_killswitch_recommended")
                else "trip recommended but no killswitch_trip_fn provided"
            ),
        }
    report["killswitch_trip_hook"] = hook_meta

    if write:
        write_report(report)
    return report


def print_ceo_summary(report: Dict[str, Any]) -> None:
    ceo = report.get("ceo") or {}
    print("=" * 64)
    print("PCS Industrial — Post-Connect Leak Verification")
    print("=" * 64)
    print(f"OVERALL:  {ceo.get('overall')}")
    print(f"Headline: {ceo.get('headline')}")
    print(f"Location: {ceo.get('location') or '(unset)'}")
    print(f"Expected: {ceo.get('expected_exit_ip') or '(unset)'}")
    print(f"Tunnel:   {'UP' if ceo.get('tunnel_up') else 'DOWN'}")
    print(f"Client:   {'configured' if ceo.get('client_configured') else 'not ready'}")
    trip = report.get("trip_killswitch_recommended")
    if trip is None:
        trip = ceo.get("trip_killswitch_recommended")
    print(f"Trip KS:  {'RECOMMENDED' if trip else 'no'}")
    skips = ceo.get("skip_reasons") or []
    if skips:
        print(f"Skips:    {', '.join(skips)}")
    print("-" * 64)
    for c in report.get("checks") or []:
        mark = {
            "pass": "PASS",
            "fail": "FAIL",
            "skip": "SKIP",
            "warn": "WARN",
            "info": "INFO",
        }.get(c.get("status"), "????")
        print(f"  [{mark}] {c.get('name')}: {c.get('detail')}")
    print("-" * 64)
    print("Next actions:")
    for a in ceo.get("next_actions") or []:
        print(f"  • {a}")
    if report.get("report_path"):
        print(f"\nCEO report: {report['report_path']}")
    print(f"Latest:     {report.get('latest_path') or REPORTS / 'latest.json'}")
    print("=" * 64)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="PCS Industrial post-connect leak verify bridge (ipify/DNS/WebRTC guidance)",
    )
    parser.add_argument(
        "--location",
        "-l",
        help="Exit location (dubai, hongkong, …). Default: PCS_VERIFY_LOCATION or session",
    )
    parser.add_argument(
        "--expected-ip",
        help="Expected exit public IP. Default: inventory / PCS_VPS_<LOC>",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run (no live IP/DNS/suite). Auto-enabled when tunnel down.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run live probes even without tunnel (not recommended)",
    )
    parser.add_argument(
        "--no-suite",
        action="store_true",
        help="Do not invoke Suite full_verification_suite.py",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Only print discovered Suite tools and env contract",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full report JSON to stdout",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write report under ~/.pcs_industrial_20260802/verify_reports/",
    )
    args = parser.parse_args(argv)

    if args.discover_only:
        disc = discover_suite_tools()
        out = {
            "discovery": disc,
            "env_contract": {
                "PCS_VERIFY_LOCATION": "Exit location key",
                "PCS_VERIFY_EXPECTED_IP": "Expected public IPv4",
                "PCS_VPS_<LOCATION>": "Alt expected IP",
                "inventory": str(INVENTORY),
                "reports": str(REPORTS),
            },
            "session": str(SESSION),
            "client_dir": str(SINGBOX_CLIENT),
        }
        print(json.dumps(out, indent=2))
        return 0

    report = run_verification(
        location=args.location,
        expected_ip=args.expected_ip,
        dry_run=args.dry_run,
        force=args.force,
        run_suite=not args.no_suite,
        write=not args.no_write,
    )

    if args.json:
        # avoid internal keys if any
        print(json.dumps(report, indent=2))
    else:
        print_ceo_summary(report)

    overall = (report.get("ceo") or {}).get("overall")
    if overall == "FAIL":
        return 2
    if overall == "WARN":
        return 1
    # NOT_RUN and PASS → 0 (NOT_RUN is expected offline)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
