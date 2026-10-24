#!/usr/bin/env python3
"""PCS Industrial fail-closed smoke harness (Google SRE production-readiness bar).

Industrial tree only:
  ~/Desktop/PCS_Industrial_20260802/
  ~/.pcs_industrial_20260802/

Does NOT modify PhantomCloak Suite / PhantomCloak originals.
Does NOT invent production VPS IPs or scrape residential proxies.
Catalog residential IPs are product metadata — NOT tunnel endpoints.

Ordered probes
--------------
1. import_health          — shared modules import cleanly
2. readiness_scan         — scan_readiness + exit_code_for semantics
3. preflight_fail_closed  — configured_count==0 → not protected
4. materialize_check_only — --check-only (if available)
5. singbox_package_validate — pcs_validate_singbox_packages (if present)
6. residential_catalog    — 36 countries, 30–50 entries each
7. deploy_multi_dry_run   — compose multi-deploy dry-run no-op
8. verify_bridge_dry_run  — leak verify bridge --dry-run

CEO JSON: ~/.pcs_industrial_20260802/smoke_reports/latest.json

Exit codes
----------
  0  all expected-pass / hard probes passed
  1  one or more hard failures
  2  harness internal error (could not complete report)
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Paths (industrial only)
# ---------------------------------------------------------------------------

HOME = Path.home()
INDUSTRIAL = Path(__file__).resolve().parents[1]
STATE = HOME / ".pcs_industrial_20260802"
SMOKE_REPORTS = STATE / "smoke_reports"
SHARED = INDUSTRIAL / "shared"
SMOKE_VERSION = "20260802"
SCHEMA = "pcs_smoke_report_v1"

# Shared modules required for import-health (industrial surface)
REQUIRED_IMPORTS: Tuple[str, ...] = (
    "shared.pcs_server_readiness_v20260802",
    "shared.pcs_preflight_obfuscation_gate_v20260802",
    "shared.pcs_materialize_singbox_v20260802",
    "shared.pcs_zeroleak_gate_v20260802",
    "shared.pcs_residential_pool_industrial_v20260802",
    "shared.pcs_obfuscation_catalog_v20260802",
    "shared.pcs_client_singbox_v20260802",
    "shared.pcs_killswitch_industrial_v20260802",
)

OPTIONAL_IMPORTS: Tuple[str, ...] = (
    "shared.pcs_validate_singbox_packages_v20260802",
    "shared.pcs_verify_bridge_v20260802",
    "shared.pcs_feature_matrix_v20260802",
    "shared.pcs_tier_catalog_v20260802",
    "shared.pcs_pricing_engine_v20260802",
    "shared.pcs_session_resume_v20260802",
    "shared.pcs_security_audit_engine_v20260802",
)

# Residential catalog contract
EXPECTED_COUNTRY_COUNT = 36
POOL_MIN = 30
POOL_MAX = 50

# Probe severity
# hard     — failure → harness non-zero exit
# soft     — informative; failure recorded but does not fail harness (optional tooling)
# expected — probe must demonstrate correct fail-closed / soft-success semantics


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_path() -> None:
    root = str(INDUSTRIAL)
    if root not in sys.path:
        sys.path.insert(0, root)
    # Prefer industrial venv sing-box path tooling
    homebrew = "/opt/homebrew/bin"
    usr_local = "/usr/local/bin"
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep)
    for p in (homebrew, usr_local):
        if p not in parts:
            parts.insert(0, p)
    os.environ["PATH"] = os.pathsep.join(parts)


def _probe(
    name: str,
    *,
    severity: str,
    status: str,
    detail: str,
    evidence: Optional[Dict[str, Any]] = None,
    expected_pass: bool = True,
) -> Dict[str, Any]:
    """status: pass | fail | skip | warn"""
    return {
        "name": name,
        "severity": severity,  # hard | soft | expected
        "status": status,
        "expected_pass": expected_pass,
        "detail": detail,
        "evidence": evidence or {},
        "ts": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def probe_import_health() -> Dict[str, Any]:
    """Import shared industrial modules."""
    ok: List[str] = []
    failed: List[Dict[str, str]] = []
    optional_ok: List[str] = []
    optional_miss: List[str] = []

    for mod in REQUIRED_IMPORTS:
        try:
            importlib.import_module(mod)
            ok.append(mod)
        except Exception as e:
            failed.append({"module": mod, "error": f"{type(e).__name__}: {e}"[:240]})

    for mod in OPTIONAL_IMPORTS:
        try:
            importlib.import_module(mod)
            optional_ok.append(mod)
        except Exception:
            optional_miss.append(mod)

    if failed:
        return _probe(
            "import_health",
            severity="hard",
            status="fail",
            detail=f"{len(failed)} required import(s) failed",
            evidence={
                "ok": ok,
                "failed": failed,
                "optional_ok": optional_ok,
                "optional_miss": optional_miss,
            },
        )
    return _probe(
        "import_health",
        severity="hard",
        status="pass",
        detail=f"{len(ok)} required + {len(optional_ok)} optional modules importable",
        evidence={
            "ok": ok,
            "optional_ok": optional_ok,
            "optional_miss": optional_miss,
        },
    )


def probe_readiness_scan() -> Dict[str, Any]:
    """Run scan_readiness + verify exit_code_for semantics."""
    try:
        from shared.pcs_server_readiness_v20260802 import (  # type: ignore
            exit_code_for,
            scan_readiness,
        )
    except Exception as e:
        return _probe(
            "readiness_scan",
            severity="hard",
            status="fail",
            detail=f"import failed: {e}",
        )

    try:
        result = scan_readiness()
    except Exception as e:
        return _probe(
            "readiness_scan",
            severity="hard",
            status="fail",
            detail=f"scan_readiness raised: {type(e).__name__}: {e}",
            evidence={"traceback": traceback.format_exc()[-800:]},
        )

    code = exit_code_for(result)
    configured = int(result.get("configured_count") or 0)
    status = result.get("status") or ""
    server_filled = int(result.get("server_filled_count") or 0)
    pending = int(result.get("pending_ip_count") or 0)

    # Semantic checks (unit-style, no invented IPs)
    semantic_ok = True
    semantic_notes: List[str] = []
    live_scan_error = (not result.get("ok", True)) or status == "error"

    if live_scan_error:
        # Live scanner exception is a hard fail; still record whether exit_code_for==1
        if code != 1:
            semantic_ok = False
            semantic_notes.append(f"error status should exit 1, got {code}")
        semantic_notes.append(
            f"live scan error: {result.get('error') or result.get('summary') or status}"
        )
    elif status in ("ready", "partial") and configured > 0:
        if code != 0:
            semantic_ok = False
            semantic_notes.append(f"ready/partial+configured should exit 0, got {code}")
    else:
        # templates_only / pending / server_package_ready_pending_client_ips /
        # configured==0 → 3 (soft offline baseline — not a harness failure)
        if code != 3:
            semantic_ok = False
            semantic_notes.append(
                f"pending/templates/configured==0 should exit 3, got {code} (status={status})"
            )

    # Synthetic exit_code_for cases (pure function)
    synthetic = [
        ("error→1", exit_code_for({"ok": False, "status": "error", "configured_count": 0}), 1),
        ("ready+cfg→0", exit_code_for({"ok": True, "status": "ready", "configured_count": 2}), 0),
        ("partial+cfg→0", exit_code_for({"ok": True, "status": "partial", "configured_count": 1}), 0),
        ("templates→3", exit_code_for({"ok": True, "status": "templates_only", "configured_count": 0}), 3),
        ("pending→3", exit_code_for({"ok": True, "status": "pending", "configured_count": 0}), 3),
    ]
    syn_fail = [n for n, got, exp in synthetic if got != exp]
    if syn_fail:
        semantic_ok = False
        semantic_notes.append(f"synthetic exit_code_for failed: {syn_fail}")

    evidence = {
        "status": status,
        "configured_count": configured,
        "server_filled_count": server_filled,
        "pending_ip_count": pending,
        "exit_code": code,
        "summary": result.get("summary"),
        "next_step": result.get("next_step"),
        "inventory_ips_set": (result.get("inventory") or {}).get("ips_set"),
        "error": result.get("error"),
        "semantic_notes": semantic_notes,
        "synthetic": [
            {"name": n, "got": g, "expected": e, "pass": g == e}
            for n, g, e in synthetic
        ],
    }

    if live_scan_error or not semantic_ok:
        return _probe(
            "readiness_scan",
            severity="hard",
            status="fail",
            detail="; ".join(semantic_notes) or "readiness scan failed",
            evidence=evidence,
        )

    # Live scan success (exit 3 with configured==0 is expected offline baseline)
    detail = (
        f"status={status} configured={configured} server_filled={server_filled} "
        f"pending={pending} exit_code={code}"
    )
    return _probe(
        "readiness_scan",
        severity="hard",
        status="pass",
        detail=detail,
        evidence=evidence,
    )


def probe_preflight_fail_closed() -> Dict[str, Any]:
    """configured_count==0 must refuse protected session (fail-closed)."""
    try:
        from shared.pcs_preflight_obfuscation_gate_v20260802 import (  # type: ignore
            activate_protected_session,
            dry_run_fail_closed,
        )
        from shared.pcs_server_readiness_v20260802 import (  # type: ignore
            gate_snapshot,
            scan_readiness,
        )
    except Exception as e:
        return _probe(
            "preflight_fail_closed",
            severity="hard",
            status="fail",
            detail=f"import failed: {e}",
        )

    # A) Forced empty readiness (no invented IPs)
    empty_readiness = {
        "status": "templates_only",
        "templates_count": 2,
        "configured_count": 0,
        "server_filled_count": 3,
        "pending_ip_count": 2,
        "templates": [],
        "configured": [],
        "server_filled": [{"name": "sing-box-dubai-reality.json"}],
        "pending": [
            {"name": "dubai.pending.json", "kind": "pending_ip", "location": "dubai"},
        ],
        "inventory": {
            "path": str(STATE / "vps_inventory.json"),
            "exists": True,
            "ips_set": 0,
        },
        "howto_path": None,
        "industrial_howto": str(
            INDUSTRIAL / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
        ),
        "summary": "0 client config(s) with real IPs",
        "next_step": "Edit inventory with real VPS public IPs then materialize",
    }

    forced = activate_protected_session(
        tier="core",
        killswitch_arm_fn=lambda: {"armed": True, "dry_run": True},
        killswitch_trip_fn=lambda _r: None,
        require_configured_servers=True,
        readiness_override=empty_readiness,
        auto_arm_killswitch=False,
        require_tunnel=False,
    )

    forced_ok = (
        forced.get("protected") is False
        and forced.get("status") == "blocked"
        and forced.get("reason") == "servers_not_configured"
        and int(forced.get("configured_count") or 0) == 0
    )

    # B) Live dry_run_fail_closed against real readiness
    live = dry_run_fail_closed(tier="core")
    live_snap = gate_snapshot(scan_readiness())
    live_cfg = int(live_snap.get("configured_count") or 0)

    if live_cfg == 0:
        live_ok = (
            live.get("protected") is False
            and live.get("status") == "blocked"
            and live.get("reason") == "servers_not_configured"
        )
        live_note = "live: configured_count==0 correctly blocks protect"
    else:
        # Real IPs present — protect path may pass other layers; still must not
        # claim protected when servers_not_configured. If configured > 0, ok_for_protect
        # is True and other layers may still block (killswitch etc.).
        live_ok = live.get("status") in ("blocked", "protected") and (
            live.get("protected") is True or live.get("protected") is False
        )
        # Never allow protected=True with configured_count==0 (already covered).
        if live.get("protected") is True and live_cfg == 0:
            live_ok = False
        live_note = (
            f"live: configured_count={live_cfg} status={live.get('status')} "
            f"protected={live.get('protected')}"
        )

    evidence = {
        "forced_empty": {
            "protected": forced.get("protected"),
            "status": forced.get("status"),
            "reason": forced.get("reason"),
            "configured_count": forced.get("configured_count"),
            "ok": forced_ok,
        },
        "live": {
            "protected": live.get("protected"),
            "status": live.get("status"),
            "reason": live.get("reason"),
            "configured_count": live.get("configured_count"),
            "ok_for_protect": live_snap.get("ok_for_protect"),
            "note": live_note,
            "ok": live_ok,
        },
    }

    if not forced_ok:
        return _probe(
            "preflight_fail_closed",
            severity="hard",
            status="fail",
            detail="forced configured_count==0 did NOT refuse protected session",
            evidence=evidence,
        )
    if not live_ok:
        return _probe(
            "preflight_fail_closed",
            severity="hard",
            status="fail",
            detail="live dry_run_fail_closed violated fail-closed contract",
            evidence=evidence,
        )

    return _probe(
        "preflight_fail_closed",
        severity="hard",
        status="pass",
        detail=(
            "configured_count==0 → protected=False (forced + live). " + live_note
        ),
        evidence=evidence,
    )


def probe_materialize_check_only() -> Dict[str, Any]:
    """Run materialize --check-only (read-only). Soft success includes pending IPs."""
    script = SHARED / "pcs_materialize_singbox_v20260802.py"
    if not script.is_file():
        return _probe(
            "materialize_check_only",
            severity="hard",
            status="fail",
            detail=f"missing {script}",
        )

    try:
        from shared.pcs_materialize_singbox_v20260802 import (  # type: ignore
            check_only,
            public_materialize_summary,
        )

        r = check_only()
        summary = public_materialize_summary(r) if callable(public_materialize_summary) else r
        pending = list(r.get("pending_ip_locations") or [])
        # check-only must not write — presence of result is enough
        detail = (
            f"check-only ok pending={len(pending)} "
            f"ready={len(r.get('ready_locations') or r.get('ready') or [])}"
        )
        return _probe(
            "materialize_check_only",
            severity="hard",
            status="pass",
            detail=detail,
            evidence={
                "pending_ip_locations": pending[:16],
                "keys": sorted(list(summary.keys()))[:40]
                if isinstance(summary, dict)
                else [],
                "mode": "in_process_check_only",
            },
        )
    except Exception as e:
        # Fallback: subprocess CLI
        try:
            proc = subprocess.run(
                [sys.executable, str(script), "--check-only", "--json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(INDUSTRIAL),
                env={**os.environ, "PYTHONPATH": str(INDUSTRIAL)},
            )
            # exit 0 or 2 (pending) are soft success for check-only
            if proc.returncode in (0, 2):
                return _probe(
                    "materialize_check_only",
                    severity="hard",
                    status="pass",
                    detail=f"CLI --check-only exit={proc.returncode}",
                    evidence={
                        "returncode": proc.returncode,
                        "stdout_tail": (proc.stdout or "")[-600:],
                        "mode": "subprocess",
                    },
                )
            return _probe(
                "materialize_check_only",
                severity="hard",
                status="fail",
                detail=f"CLI --check-only hard fail exit={proc.returncode}: {e}",
                evidence={
                    "returncode": proc.returncode,
                    "stderr_tail": (proc.stderr or "")[-400:],
                    "in_process_error": f"{type(e).__name__}: {e}"[:240],
                },
            )
        except Exception as e2:
            return _probe(
                "materialize_check_only",
                severity="hard",
                status="fail",
                detail=f"check-only failed: {type(e2).__name__}: {e2}",
            )


def probe_singbox_package_validate() -> Dict[str, Any]:
    """Validate industrial sing-box packages if module exists."""
    mod_name = "shared.pcs_validate_singbox_packages_v20260802"
    script = SHARED / "pcs_validate_singbox_packages_v20260802.py"
    if not script.is_file():
        return _probe(
            "singbox_package_validate",
            severity="soft",
            status="skip",
            detail="pcs_validate_singbox_packages_v20260802.py not present",
            expected_pass=False,
        )

    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        return _probe(
            "singbox_package_validate",
            severity="hard",
            status="fail",
            detail=f"module present but import failed: {e}",
        )

    # Prefer package-only (faster, no shape writes); shapes if sing-box available
    try:
        run_all = getattr(mod, "run_all", None)
        if not callable(run_all):
            return _probe(
                "singbox_package_validate",
                severity="hard",
                status="fail",
                detail="run_all() missing on validate module",
            )

        # package-only first for baseline
        report_pkg = run_all(shapes=False)
        sing_box = report_pkg.get("sing_box")
        if report_pkg.get("error") == "sing-box not found on PATH" or not sing_box:
            return _probe(
                "singbox_package_validate",
                severity="soft",
                status="skip",
                detail="sing-box binary not on PATH — package validate deferred",
                evidence={"error": report_pkg.get("error"), "report": {
                    "ok": report_pkg.get("ok"),
                    "checked": report_pkg.get("checked"),
                    "failed": report_pkg.get("failed"),
                }},
                expected_pass=False,
            )

        # Full validate including shapes when binary present
        report = run_all(shapes=True)
        if report.get("ok"):
            return _probe(
                "singbox_package_validate",
                severity="hard",
                status="pass",
                detail=(
                    f"checked={report.get('checked')} failed={report.get('failed')} "
                    f"version={report.get('version')}"
                ),
                evidence={
                    "checked": report.get("checked"),
                    "failed": report.get("failed"),
                    "with_warnings": report.get("with_warnings"),
                    "version": report.get("version"),
                    "failures": report.get("failures") or [],
                },
            )
        return _probe(
            "singbox_package_validate",
            severity="hard",
            status="fail",
            detail=(
                f"validate failed: checked={report.get('checked')} "
                f"failed={report.get('failed')}"
            ),
            evidence={
                "failures": (report.get("failures") or [])[:20],
                "version": report.get("version"),
            },
        )
    except Exception as e:
        return _probe(
            "singbox_package_validate",
            severity="hard",
            status="fail",
            detail=f"run_all raised: {type(e).__name__}: {e}",
            evidence={"traceback": traceback.format_exc()[-600:]},
        )


def probe_residential_catalog() -> Dict[str, Any]:
    """36 countries, 30–50 entries each; not tunnel endpoints."""
    try:
        from shared.pcs_residential_pool_industrial_v20260802 import (  # type: ignore
            CATALOG_KIND,
            COUNTRY_TO_LOCATION,
            POOL_DIR,
            ensure_full_catalog,
        )
    except Exception as e:
        return _probe(
            "residential_catalog",
            severity="hard",
            status="fail",
            detail=f"import failed: {e}",
        )

    n_countries = len(COUNTRY_TO_LOCATION)
    if n_countries != EXPECTED_COUNTRY_COUNT:
        return _probe(
            "residential_catalog",
            severity="hard",
            status="fail",
            detail=(
                f"expected {EXPECTED_COUNTRY_COUNT} countries, "
                f"got {n_countries}"
            ),
            evidence={"countries": sorted(COUNTRY_TO_LOCATION.keys())},
        )

    # Ensure on-disk catalog (idempotent synthetic product catalog only)
    try:
        ensure_full_catalog(pool_size=45)
    except Exception as e:
        return _probe(
            "residential_catalog",
            severity="hard",
            status="fail",
            detail=f"ensure_full_catalog failed: {e}",
        )

    shortfalls: List[Dict[str, Any]] = []
    bad_flags: List[str] = []
    total = 0

    for cc in sorted(COUNTRY_TO_LOCATION.keys()):
        path = POOL_DIR / f"{cc}.json"
        if not path.is_file():
            shortfalls.append({"country": cc, "count": 0, "error": "missing file"})
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            shortfalls.append({"country": cc, "count": 0, "error": str(e)[:80]})
            continue
        if not isinstance(data, list):
            shortfalls.append({"country": cc, "count": 0, "error": "not a list"})
            continue
        n = len(data)
        total += n
        if not (POOL_MIN <= n <= POOL_MAX):
            shortfalls.append({"country": cc, "count": n, "error": "out of bounds"})
        # Spot-check first entry flags
        if data:
            e0 = data[0]
            if e0.get("not_a_tunnel_endpoint") is not True:
                bad_flags.append(f"{cc}:not_a_tunnel_endpoint")
            if e0.get("catalog_kind") != CATALOG_KIND:
                bad_flags.append(f"{cc}:catalog_kind")

    meta_path = POOL_DIR / "_catalog_meta.json"
    meta: Dict[str, Any] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    evidence = {
        "countries": n_countries,
        "total_entries": total,
        "pool_dir": str(POOL_DIR),
        "shortfalls": shortfalls[:20],
        "bad_flags": bad_flags[:20],
        "catalog_kind": meta.get("catalog_kind") or CATALOG_KIND,
        "note": meta.get("note"),
        "bounds": f"{POOL_MIN}-{POOL_MAX} per country",
    }

    if shortfalls or bad_flags:
        return _probe(
            "residential_catalog",
            severity="hard",
            status="fail",
            detail=(
                f"catalog contract violated: shortfalls={len(shortfalls)} "
                f"bad_flags={len(bad_flags)}"
            ),
            evidence=evidence,
        )

    return _probe(
        "residential_catalog",
        severity="hard",
        status="pass",
        detail=(
            f"{n_countries} countries, {total} entries "
            f"({POOL_MIN}-{POOL_MAX} each); not tunnel endpoints"
        ),
        evidence=evidence,
    )


def probe_deploy_multi_dry_run() -> Dict[str, Any]:
    """Compose multi-VPS deploy script in dry-run (no scp, no invented IPs)."""
    compose_candidates = [
        INDUSTRIAL
        / "server_vps_package_v20260802"
        / "scripts"
        / "pcs_compose_deploy_v20260802.py",
        STATE / "vps_server_package" / "scripts" / "pcs_compose_deploy_v20260802.py",
    ]
    script = next((p for p in compose_candidates if p.is_file()), None)
    if script is None:
        return _probe(
            "deploy_multi_dry_run",
            severity="hard",
            status="fail",
            detail="pcs_compose_deploy_v20260802.py not found in industrial paths",
            evidence={"searched": [str(p) for p in compose_candidates]},
        )

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(script.parent),
            env={**os.environ, "PYTHONPATH": str(INDUSTRIAL)},
        )
    except Exception as e:
        return _probe(
            "deploy_multi_dry_run",
            severity="hard",
            status="fail",
            detail=f"subprocess failed: {e}",
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    # Dry-run should print a bash script plan; zero live targets → NO-OP lines OK
    looks_like_script = (
        "#!/usr/bin/env bash" in stdout
        or "deploy_filled" in stdout
        or "NO-OP" in stdout
        or "PCS_DEPLOY" in stdout
    )
    ok = proc.returncode == 0 and looks_like_script

    # Also try in-process compose when importable from state scripts
    evidence = {
        "script": str(script),
        "returncode": proc.returncode,
        "stdout_bytes": len(stdout),
        "stderr_tail": stderr[-300:],
        "has_noop": "NO-OP" in stdout,
        "looks_like_script": looks_like_script,
    }

    if not ok:
        return _probe(
            "deploy_multi_dry_run",
            severity="hard",
            status="fail",
            detail=(
                f"compose --dry-run failed exit={proc.returncode} "
                f"looks_like_script={looks_like_script}"
            ),
            evidence=evidence,
        )

    return _probe(
        "deploy_multi_dry_run",
        severity="hard",
        status="pass",
        detail=(
            f"compose --dry-run exit=0 bytes={len(stdout)} "
            f"noop_lines={'yes' if evidence['has_noop'] else 'no_live_or_embedded'}"
        ),
        evidence=evidence,
    )


def probe_verify_bridge_dry_run() -> Dict[str, Any]:
    """Verify bridge dry-run — NOT_RUN expected offline (not a hard fail)."""
    script = SHARED / "pcs_verify_bridge_v20260802.py"
    if not script.is_file():
        return _probe(
            "verify_bridge_dry_run",
            severity="soft",
            status="skip",
            detail="pcs_verify_bridge_v20260802.py missing",
            expected_pass=False,
        )

    try:
        from shared.pcs_verify_bridge_v20260802 import run_verification  # type: ignore

        report = run_verification(
            location="dubai",
            expected_ip=None,
            dry_run=True,
            force=False,
            run_suite=False,
            write=False,  # smoke writes its own CEO report; avoid clobbering verify latest
        )
        ceo = report.get("ceo") or {}
        overall = ceo.get("overall")
        trip_ks = bool(
            report.get("trip_killswitch_recommended")
            or ceo.get("trip_killswitch_recommended")
        )
        # Dry-run offline: NOT_RUN / WARN with skips is success of the bridge path
        # FAIL on dry-run would be unexpected (no live checks)
        # trip_killswitch_recommended must stay false on dry-run
        if overall == "FAIL":
            return _probe(
                "verify_bridge_dry_run",
                severity="hard",
                status="fail",
                detail=f"dry-run overall=FAIL (unexpected): {ceo.get('headline')}",
                evidence={
                    "overall": overall,
                    "skip_reasons": ceo.get("skip_reasons"),
                    "pass_count": ceo.get("pass_count"),
                    "fail_count": ceo.get("fail_count"),
                    "trip_killswitch_recommended": trip_ks,
                },
            )
        if trip_ks:
            return _probe(
                "verify_bridge_dry_run",
                severity="hard",
                status="fail",
                detail="dry-run set trip_killswitch_recommended=true (must be false)",
                evidence={
                    "overall": overall,
                    "trip_killswitch_recommended": trip_ks,
                    "mode": (report.get("mode") or {}),
                },
            )
        return _probe(
            "verify_bridge_dry_run",
            severity="hard",
            status="pass",
            detail=(
                f"overall={overall} skips={ceo.get('skip_count')} "
                f"trip_ks={trip_ks} "
                f"headline={str(ceo.get('headline') or '')[:120]}"
            ),
            evidence={
                "overall": overall,
                "skip_reasons": ceo.get("skip_reasons"),
                "pass_count": ceo.get("pass_count"),
                "fail_count": ceo.get("fail_count"),
                "warn_count": ceo.get("warn_count"),
                "trip_killswitch_recommended": trip_ks,
                "mode": (report.get("mode") or {}),
            },
        )
    except Exception as e:
        # CLI fallback
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--location",
                    "dubai",
                    "--dry-run",
                    "--no-suite",
                    "--no-write",
                    "--json",
                ],
                capture_output=True,
                text=True,
                timeout=90,
                cwd=str(INDUSTRIAL),
                env={**os.environ, "PYTHONPATH": str(INDUSTRIAL)},
            )
            # NOT_RUN and PASS → 0; WARN → 1; FAIL → 2
            if proc.returncode in (0, 1):
                return _probe(
                    "verify_bridge_dry_run",
                    severity="hard",
                    status="pass",
                    detail=f"CLI dry-run exit={proc.returncode}",
                    evidence={
                        "returncode": proc.returncode,
                        "stdout_tail": (proc.stdout or "")[-500:],
                        "in_process_error": f"{type(e).__name__}: {e}"[:200],
                    },
                )
            return _probe(
                "verify_bridge_dry_run",
                severity="hard",
                status="fail",
                detail=f"CLI dry-run exit={proc.returncode}",
                evidence={
                    "returncode": proc.returncode,
                    "stderr_tail": (proc.stderr or "")[-400:],
                },
            )
        except Exception as e2:
            return _probe(
                "verify_bridge_dry_run",
                severity="hard",
                status="fail",
                detail=f"verify bridge failed: {type(e2).__name__}: {e2}",
            )


# ---------------------------------------------------------------------------
# Runner / CEO report
# ---------------------------------------------------------------------------

PROBE_ORDER: List[Tuple[str, Callable[[], Dict[str, Any]]]] = [
    ("import_health", probe_import_health),
    ("readiness_scan", probe_readiness_scan),
    ("preflight_fail_closed", probe_preflight_fail_closed),
    ("materialize_check_only", probe_materialize_check_only),
    ("singbox_package_validate", probe_singbox_package_validate),
    ("residential_catalog", probe_residential_catalog),
    ("deploy_multi_dry_run", probe_deploy_multi_dry_run),
    ("verify_bridge_dry_run", probe_verify_bridge_dry_run),
]


def run_smoke(*, stop_on_hard_fail: bool = False) -> Dict[str, Any]:
    """Execute ordered probes and build CEO report."""
    _ensure_path()
    probes: List[Dict[str, Any]] = []

    for name, fn in PROBE_ORDER:
        try:
            row = fn()
        except Exception as e:
            row = _probe(
                name,
                severity="hard",
                status="fail",
                detail=f"probe crashed: {type(e).__name__}: {e}",
                evidence={"traceback": traceback.format_exc()[-800:]},
            )
        # Ensure name stable
        row["name"] = name
        probes.append(row)
        if (
            stop_on_hard_fail
            and row.get("severity") == "hard"
            and row.get("status") == "fail"
        ):
            break

    hard_fails = [
        p
        for p in probes
        if p.get("severity") == "hard"
        and p.get("status") == "fail"
        and p.get("expected_pass", True)
    ]
    soft_fails = [
        p for p in probes if p.get("severity") == "soft" and p.get("status") == "fail"
    ]
    passed = [p for p in probes if p.get("status") == "pass"]
    skipped = [p for p in probes if p.get("status") == "skip"]
    warned = [p for p in probes if p.get("status") == "warn"]

    overall = "PASS" if not hard_fails else "FAIL"
    exit_code = 0 if overall == "PASS" else 1

    table = [
        {
            "probe": p["name"],
            "severity": p.get("severity"),
            "status": p.get("status"),
            "detail": (p.get("detail") or "")[:200],
        }
        for p in probes
    ]

    report: Dict[str, Any] = {
        "schema": SCHEMA,
        "smoke_version": SMOKE_VERSION,
        "generated_at": _utc_now(),
        "industrial_root": str(INDUSTRIAL),
        "state_dir": str(STATE),
        "ceo": {
            "overall": overall,
            "headline": (
                "All expected-pass smoke probes passed (fail-closed baseline green)."
                if overall == "PASS"
                else f"Smoke FAIL: {len(hard_fails)} hard probe(s) failed."
            ),
            "exit_code": exit_code,
            "pass_count": len(passed),
            "fail_count": len(hard_fails),
            "soft_fail_count": len(soft_fails),
            "skip_count": len(skipped),
            "warn_count": len(warned),
            "hard_failures": [p["name"] for p in hard_fails],
            "next_actions": _next_actions(probes, hard_fails),
        },
        "table": table,
        "probes": probes,
        "contracts": {
            "residential_countries": EXPECTED_COUNTRY_COUNT,
            "residential_pool_bounds": [POOL_MIN, POOL_MAX],
            "catalog_not_tunnel_endpoints": True,
            "never_invent_vps_ips": True,
            "industrial_only": True,
        },
    }
    return report


def _next_actions(
    probes: List[Dict[str, Any]], hard_fails: List[Dict[str, Any]]
) -> List[str]:
    actions: List[str] = []
    names = {p["name"] for p in hard_fails}
    if "import_health" in names:
        actions.append(
            f"Fix shared imports under {INDUSTRIAL}/shared (PYTHONPATH=industrial root)"
        )
    if "readiness_scan" in names:
        actions.append(
            f"Debug scan_readiness / exit_code_for — see {SHARED}/pcs_server_readiness_v20260802.py"
        )
    if "preflight_fail_closed" in names:
        actions.append(
            "CRITICAL: protect path must refuse when configured_count==0 "
            "(pcs_preflight_obfuscation_gate)"
        )
    if "materialize_check_only" in names:
        actions.append("Repair pcs_materialize_singbox_v20260802.py --check-only path")
    if "singbox_package_validate" in names:
        actions.append(
            "Install sing-box on PATH and/or fix vps_server_package JSON "
            "(Validate_SingBox_Packages_v20260802.command)"
        )
    if "residential_catalog" in names:
        actions.append(
            "Regenerate catalog: python3 -m shared.pcs_residential_pool_industrial_v20260802"
        )
    if "deploy_multi_dry_run" in names:
        actions.append("Fix pcs_compose_deploy_v20260802.py dry-run path")
    if "verify_bridge_dry_run" in names:
        actions.append("Fix pcs_verify_bridge_v20260802 --dry-run")
    if not hard_fails:
        # Green baseline next steps for CEO (no invented IPs)
        readiness = next((p for p in probes if p["name"] == "readiness_scan"), None)
        cfg = 0
        if readiness:
            cfg = int((readiness.get("evidence") or {}).get("configured_count") or 0)
        if cfg == 0:
            actions.append(
                f"Baseline green with configured_count=0 — set owned VPS IPs in "
                f"{STATE}/vps_inventory.json then re-run materialize "
                f"(see docs_v20260802/CEO_VPS_RUNBOOK_v20260802.md)"
            )
        else:
            actions.append(
                "configured_count>0 — deploy filled packages and run verify bridge post-connect"
            )
    return actions


def write_report(report: Dict[str, Any]) -> Dict[str, str]:
    SMOKE_REPORTS.mkdir(parents=True, exist_ok=True)
    latest = SMOKE_REPORTS / "latest.json"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    overall = (report.get("ceo") or {}).get("overall") or "UNKNOWN"
    stamped = SMOKE_REPORTS / f"smoke_{ts}_{overall}.json"
    text = json.dumps(report, indent=2) + "\n"
    # Atomic write for latest
    tmp = latest.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, latest)
    stamped.write_text(text, encoding="utf-8")
    try:
        os.chmod(latest, 0o600)
        os.chmod(stamped, 0o600)
    except OSError:
        pass
    return {"latest": str(latest), "stamped": str(stamped)}


def print_table(report: Dict[str, Any]) -> None:
    ceo = report.get("ceo") or {}
    print("=" * 72)
    print(f"PCS Industrial Smoke v{SMOKE_VERSION}")
    print(f"OVERALL:  {ceo.get('overall')}  (exit {ceo.get('exit_code')})")
    print(f"HEADLINE: {ceo.get('headline')}")
    print("-" * 72)
    print(f"{'PROBE':<28} {'SEV':<8} {'STATUS':<8} DETAIL")
    print("-" * 72)
    for row in report.get("table") or []:
        print(
            f"{row.get('probe', ''):<28} "
            f"{row.get('severity', ''):<8} "
            f"{str(row.get('status', '')).upper():<8} "
            f"{(row.get('detail') or '')[:80]}"
        )
    print("-" * 72)
    print(
        f"pass={ceo.get('pass_count')} hard_fail={ceo.get('fail_count')} "
        f"skip={ceo.get('skip_count')} soft_fail={ceo.get('soft_fail_count')}"
    )
    if ceo.get("hard_failures"):
        print("hard failures:", ", ".join(ceo["hard_failures"]))
    print("Next actions:")
    for a in ceo.get("next_actions") or []:
        print(f"  • {a}")
    paths = report.get("report_paths") or {}
    if paths.get("latest"):
        print(f"\nCEO report: {paths['latest']}")
    print("=" * 72)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="PCS Industrial fail-closed smoke harness (v20260802)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print full CEO report JSON to stdout",
    )
    ap.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write smoke_reports/latest.json",
    )
    ap.add_argument(
        "--stop-on-hard-fail",
        action="store_true",
        help="Stop after first hard failure",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        report = run_smoke(stop_on_hard_fail=args.stop_on_hard_fail)
    except Exception as e:
        # Harness internal failure
        err = {
            "schema": SCHEMA,
            "smoke_version": SMOKE_VERSION,
            "generated_at": _utc_now(),
            "ceo": {
                "overall": "FAIL",
                "headline": f"Smoke harness crashed: {type(e).__name__}: {e}",
                "exit_code": 2,
            },
            "error": traceback.format_exc()[-1200:],
        }
        if not args.no_write:
            try:
                paths = write_report(err)
                err["report_paths"] = paths
            except Exception:
                pass
        if args.json:
            print(json.dumps(err, indent=2))
        else:
            print(err["ceo"]["headline"], file=sys.stderr)
        return 2

    if not args.no_write:
        paths = write_report(report)
        report["report_paths"] = paths

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_table(report)

    return int((report.get("ceo") or {}).get("exit_code") or 0)


if __name__ == "__main__":
    raise SystemExit(main())
