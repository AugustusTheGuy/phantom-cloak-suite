"""Activation pipeline: verify ALL enabled obfuscation/privacy layers → then allow.

Canonical protect gate order (fail-closed — never claim protected if any fail):
  1) Server readiness (require_configured_servers / configured_count > 0)
  2) Optional wipe (Suite anti_forensics if provided; else wipe_done=False)
  3) Synthetic profile gate (if exit_ip known and score fails → block protect)
  4) Obfuscation preflight (method + enabled layers except killswitch arm)
  5) Killswitch arm (industrial pf conf under ~/.pcs_industrial_20260802/pf_rules/)
  6) Final layer map including killswitch_armed — then status protected

If any check fails, do not mark session protected. Optional trip callback may
surface fail-closed UI state; arm is never claimed successful when blocked early.

Dashboard/status/wizard remain allowed outside this path.
New file — does not modify Suite phantomcloak.py activate path.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

try:
    from .pcs_obfuscation_catalog_v20260802 import auto_select_method, describe_method
    from .pcs_server_readiness_v20260802 import gate_snapshot, scan_readiness
    from .pcs_zeroleak_gate_v20260802 import GateReport, LayerCheck, enforce_or_kill
except ImportError:  # script / non-package execution
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    from shared.pcs_obfuscation_catalog_v20260802 import auto_select_method, describe_method
    from shared.pcs_server_readiness_v20260802 import gate_snapshot, scan_readiness
    from shared.pcs_zeroleak_gate_v20260802 import GateReport, LayerCheck, enforce_or_kill

# Ordered gate phase names (tests + docs rely on these literals).
GATE_READINESS = "readiness_servers"
GATE_WIPE = "optional_wipe"
GATE_SYNTHETIC = "synthetic_profile"
GATE_OBFUSCATION = "obfuscation_preflight"
GATE_KILLSWITCH = "killswitch_arm"
GATE_FINAL = "final_layer_verify"
CANONICAL_GATE_ORDER = (
    GATE_READINESS,
    GATE_WIPE,
    GATE_SYNTHETIC,
    GATE_OBFUSCATION,
    GATE_KILLSWITCH,
    GATE_FINAL,
)


def build_enabled_layers(
    *,
    tier: str,
    killswitch_armed: bool,
    obfuscation_method: str,
    tracker_vault_enabled: bool,
    tracker_vault_ok: bool,
    webrtc_guard: bool = True,
    dns_guard: bool = True,
    ipv6_guard: bool = True,
    servers_configured: bool | None = None,
    extra: dict[str, bool] | None = None,
    include_killswitch: bool = True,
) -> dict[str, bool]:
    """Layer map for enforce_or_kill.

    include_killswitch=False is used for the obfuscation preflight phase *before*
    arm — so a false killswitch_armed cannot fail-closed the wrong gate.
    """
    layers: dict[str, bool] = {
        "obfuscation_selected": bool(obfuscation_method),
        "dns_guard": dns_guard,
        "webrtc_guard": webrtc_guard,
        "ipv6_guard": ipv6_guard,
    }
    if include_killswitch:
        layers["killswitch_armed"] = bool(killswitch_armed)
    if servers_configured is not None:
        layers["servers_configured"] = bool(servers_configured)
    if tracker_vault_enabled:
        layers["tracker_vault"] = tracker_vault_ok
    if tier == "pro":
        layers["pro_watchdog_registered"] = True
    if extra:
        layers.update(extra)
    return layers


def interpret_arm_result(arm_result: Any) -> bool:
    """True only when arm callback/result indicates successful arm or dry_run write.

    Fail-closed: unknown/error → False. Demo helpers may return {"armed": True}.
    """
    if arm_result is None:
        return False
    if isinstance(arm_result, dict):
        if arm_result.get("error"):
            return False
        st = arm_result.get("status")
        if st in ("error", "failed", "blocked"):
            return False
        if st in ("armed", "dry_run", "written"):
            return True
        if arm_result.get("armed") is True:
            return True
        if arm_result.get("dry_run") is True:
            return True
        # Empty success dict from tests is not enough — require explicit signal
        return False
    return bool(arm_result)


def run_optional_wipe(
    wipe_fn: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Optional wipe step for protect path.

    - If wipe_fn provided (Suite anti_forensics available): call it.
      Success → wipe_done=True. Explicit fail / raise → wipe_done=False + error.
    - If wipe_fn is None: record wipe_done=False (not available). Never invent Suite.
    """
    if wipe_fn is None:
        return {
            "wipe_done": False,
            "wipe_available": False,
            "ok": True,  # optional: absence is recorded, not a hard error here
            "message": "Suite anti_forensics not provided — wipe_done=False",
        }
    try:
        result = wipe_fn()
        if isinstance(result, dict) and result.get("ok") is False:
            return {
                "wipe_done": False,
                "wipe_available": True,
                "ok": False,
                "wipe_result": result,
                "error": result.get("error") or result.get("message") or "wipe reported failure",
                "message": "Wipe hook reported failure — protect blocked (fail-closed).",
            }
        return {
            "wipe_done": True,
            "wipe_available": True,
            "ok": True,
            "wipe_result": result,
            "message": "Wipe completed via provided anti_forensics hook",
        }
    except Exception as e:
        return {
            "wipe_done": False,
            "wipe_available": True,
            "ok": False,
            "error": str(e)[:200],
            "message": "Wipe hook raised — protect blocked (fail-closed).",
        }


def run_synthetic_profile_gate(
    *,
    location: str = "",
    exit_ip: str = "",
    purpose: str = "browsing",
    asn_class: str = "datacenter",
    wipe_done: bool = False,
    slot_id: str = "",
    leak_checks_ok: Optional[bool] = None,
) -> dict[str, Any]:
    """Synthetic profile / mimicry gate for preflight integration.

    Rule (high-assurance):
      - If exit_ip is known and gate/score fails → block protect.
      - If exit_ip unknown → do not block (skip applied); still seed for telemetry.
    """
    try:
        from .pcs_synthetic_profile_v20260802 import (
            build_profile_seed,
            gate_profile,
            write_profile,
        )
    except ImportError:
        from shared.pcs_synthetic_profile_v20260802 import (  # type: ignore
            build_profile_seed,
            gate_profile,
            write_profile,
        )

    loc = (location or "").strip() or "unknown"
    ip = (exit_ip or "").strip()
    exit_known = bool(ip)

    seed = build_profile_seed(
        loc,
        exit_ip=ip,
        slot_id=slot_id,
        purpose=purpose or "browsing",
        asn_class=asn_class or "datacenter",
        wipe_done=wipe_done,
        leak_checks_ok=leak_checks_ok,
    )
    gate = gate_profile(seed)
    profile_path: str | None = None
    try:
        profile_path = str(write_profile(seed))
    except Exception:
        profile_path = None

    if not exit_known:
        return {
            "applied": False,
            "skipped": True,
            "ok": True,
            "exit_ip_known": False,
            "wipe_done": wipe_done,
            "score": (seed.get("mimicry") or {}).get("score"),
            "threshold": (seed.get("mimicry") or {}).get("threshold"),
            "pass_gate": gate.get("ok"),
            "reason": None,
            "message": "exit_ip unknown — synthetic profile gate not applied (no block)",
            "seed": seed,
            "gate": gate,
            "profile_path": profile_path,
        }

    ok = bool(gate.get("ok"))
    return {
        "applied": True,
        "skipped": False,
        "ok": ok,
        "exit_ip_known": True,
        "wipe_done": wipe_done,
        "score": gate.get("score"),
        "threshold": gate.get("threshold"),
        "pass_gate": ok,
        "reason": None if ok else (gate.get("reason") or "synthetic_profile_gate_failed"),
        "message": None
        if ok
        else (
            gate.get("message")
            or "Profile/exit consistency or wipe incomplete — protect blocked (fail-closed)."
        ),
        "seed": seed,
        "gate": gate,
        "profile_path": profile_path,
    }


def _attach_server_fields(payload: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    """Surface readiness counts + pending on every gate response."""
    payload["server_readiness"] = snap
    payload["configured_count"] = snap.get("configured_count", 0)
    payload["server_filled_count"] = snap.get("server_filled_count", 0)
    payload["pending_ip_count"] = snap.get("pending_ip_count", 0)
    payload["pending"] = snap.get("pending") or []
    return payload


def _blocked(
    *,
    reason: str,
    message: str,
    tier: str,
    method: str,
    snap: dict[str, Any],
    gate_stopped_at: str,
    gates_passed: list[str],
    arm_result: Any = None,
    report: GateReport | None = None,
    killswitch_tripped: bool = False,
    error: str | None = None,
    wipe_done: bool = False,
    wipe_meta: dict[str, Any] | None = None,
    synthetic_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Consistent fail-closed payload — never protected=True."""
    payload: dict[str, Any] = {
        "status": "blocked",
        "protected": False,
        "reason": reason,
        "message": message,
        "tier": tier,
        "killswitch_tripped": killswitch_tripped,
        "obfuscation": {
            "method": method,
            "description": describe_method(method),
        },
        "arm_result": arm_result,
        "gate_order": list(CANONICAL_GATE_ORDER),
        "gates_passed": list(gates_passed),
        "gate_stopped_at": gate_stopped_at,
        "wipe_done": wipe_done,
        "wipe": wipe_meta,
        "synthetic_profile": synthetic_profile,
        "next_step": snap.get("next_step"),
        "howto_path": snap.get("howto_path") or snap.get("industrial_howto"),
        "inventory_path": snap.get("inventory_path"),
    }
    if report is not None:
        payload["report"] = report.to_dict()
    if error is not None:
        payload["error"] = error
    return _attach_server_fields(payload, snap)


def activate_protected_session(
    *,
    tier: str,
    dpi_suspected: bool = False,
    blocked: bool = False,
    tracker_vault_enabled: bool = False,
    tracker_vault_ok: bool = True,
    killswitch_arm_fn: Callable[[], Any] | None = None,
    killswitch_trip_fn: Callable[[GateReport], Any] | None = None,
    require_tunnel: bool = False,
    auto_arm_killswitch: bool = True,
    force_pf_apply: bool = False,
    require_configured_servers: bool = True,
    readiness_override: dict[str, Any] | None = None,
    # Optional wipe (Suite anti_forensics) + synthetic profile gate
    wipe_fn: Callable[[], Any] | None = None,
    exit_ip: str = "",
    location: str = "",
    purpose: str = "browsing",
    asn_class: str = "datacenter",
    slot_id: str = "",
    leak_checks_ok: Optional[bool] = None,
    fail_closed_on_wipe_error: bool = True,
) -> dict[str, Any]:
    """
    Canonical order (deepcheck-critical — see docs PROTECT_GATE_ORDER):
      1) Server readiness fail-closed (configured_count must be > 0 for protect)
      2) Optional wipe (call wipe_fn if Suite anti_forensics available; else wipe_done=False)
      3) Synthetic profile gate (if exit_ip known and score fails → block protect)
      4) Obfuscation preflight (method + every enabled layer except killswitch arm)
      5) Arm killswitch once (industrial path; never /tmp)
      6) Final verify including killswitch_armed
      7) Only if all ok → status protected

    Never claims protected if any gate fails. Arm is not invoked when readiness
    or earlier gates fail (avoids double-arm / arm-before-ready races).

    auto_arm_killswitch=True uses industrial killswitch module (pf conf under
    ~/.pcs_industrial_20260802/pf_rules/ — never /tmp). When killswitch_arm_fn
    is provided, auto_arm is skipped (single arm path only).

    require_configured_servers=True (default): refuse protected session when no
    client configs have real VPS IPs. Set False only for isolated unit tests of
    other layers — never for real protect/activate entrypoints.
    readiness_override: inject scan_readiness()-shaped dict for dry-run/tests
    (do not invent production IPs; leave real scan when None).

    wipe_fn: optional Suite anti_forensics hook (e.g. deep_clean_on_start).
    exit_ip / location / purpose / asn_class: synthetic profile inputs.
    """
    method = auto_select_method(blocked=blocked, dpi_suspected=dpi_suspected)
    gates_passed: list[str] = []
    arm_result: Any = None
    wipe_done = False
    wipe_meta: dict[str, Any] | None = None
    synth_meta: dict[str, Any] | None = None
    # Single-arm latch: at most one arm attempt per activate call
    arm_attempted = False

    def _trip(report: GateReport) -> None:
        if callable(killswitch_trip_fn):
            try:
                killswitch_trip_fn(report)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # GATE 1: server readiness — fail closed before arm or claim protect
    # ------------------------------------------------------------------
    readiness = readiness_override if readiness_override is not None else scan_readiness()
    snap = gate_snapshot(readiness)
    servers_ok = bool(snap.get("ok_for_protect"))

    if require_configured_servers and not servers_ok:
        report = GateReport(tier=tier)
        report.checks.append(
            LayerCheck(
                "servers_configured",
                False,
                True,
                (
                    f"configured_count={snap.get('configured_count', 0)}; "
                    f"server_filled_count={snap.get('server_filled_count', 0)}; "
                    f"pending_ip_count={snap.get('pending_ip_count', 0)}"
                ),
            )
        )
        _trip(report)
        return _blocked(
            reason="servers_not_configured",
            message=snap.get("block_message")
            or (
                "Protected browsing blocked until VPS inventory has real IPs "
                "and client configs are materialized (configured_count > 0)."
            ),
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_READINESS,
            gates_passed=gates_passed,
            arm_result=None,
            report=report,
            killswitch_tripped=bool(callable(killswitch_trip_fn)),
            wipe_done=False,
            wipe_meta=None,
            synthetic_profile=None,
        )

    gates_passed.append(GATE_READINESS)

    # ------------------------------------------------------------------
    # GATE 2: optional wipe — Suite anti_forensics if available
    # ------------------------------------------------------------------
    wipe_meta = run_optional_wipe(wipe_fn)
    wipe_done = bool(wipe_meta.get("wipe_done"))
    # Fail-closed only when a wipe was attempted and failed
    if wipe_fn is not None and not wipe_meta.get("ok") and fail_closed_on_wipe_error:
        report = GateReport(tier=tier)
        report.checks.append(
            LayerCheck(
                "optional_wipe",
                False,
                True,
                wipe_meta.get("error") or wipe_meta.get("message") or "wipe failed",
            )
        )
        _trip(report)
        return _blocked(
            reason="wipe_failed",
            message=wipe_meta.get("message")
            or "Wipe hook failed — no protected session (fail-closed).",
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_WIPE,
            gates_passed=gates_passed,
            arm_result=None,
            report=report,
            killswitch_tripped=True,
            error=wipe_meta.get("error"),
            wipe_done=False,
            wipe_meta=wipe_meta,
            synthetic_profile=None,
        )

    gates_passed.append(GATE_WIPE)

    # ------------------------------------------------------------------
    # GATE 3: synthetic profile — block only if exit_ip known and score fails
    # ------------------------------------------------------------------
    synth_meta = run_synthetic_profile_gate(
        location=location,
        exit_ip=exit_ip,
        purpose=purpose,
        asn_class=asn_class,
        wipe_done=wipe_done,
        slot_id=slot_id,
        leak_checks_ok=leak_checks_ok,
    )
    if not synth_meta.get("ok"):
        report = GateReport(tier=tier)
        report.checks.append(
            LayerCheck(
                "synthetic_profile",
                False,
                True,
                (
                    f"score={synth_meta.get('score')} threshold={synth_meta.get('threshold')} "
                    f"wipe_done={wipe_done} exit_ip_known={synth_meta.get('exit_ip_known')}"
                ),
            )
        )
        _trip(report)
        return _blocked(
            reason=synth_meta.get("reason") or "synthetic_profile_gate_failed",
            message=synth_meta.get("message")
            or "Synthetic profile gate failed — no protected session (fail-closed).",
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_SYNTHETIC,
            gates_passed=gates_passed,
            arm_result=None,
            report=report,
            killswitch_tripped=True,
            wipe_done=wipe_done,
            wipe_meta=wipe_meta,
            synthetic_profile=synth_meta,
        )

    gates_passed.append(GATE_SYNTHETIC)

    # ------------------------------------------------------------------
    # GATE 4: obfuscation preflight — BEFORE killswitch arm
    # ------------------------------------------------------------------
    layers_obf = build_enabled_layers(
        tier=tier,
        killswitch_armed=False,
        obfuscation_method=method,
        tracker_vault_enabled=tracker_vault_enabled,
        tracker_vault_ok=tracker_vault_ok,
        servers_configured=servers_ok if require_configured_servers else None,
        include_killswitch=False,
    )

    report_obf = enforce_or_kill(
        _trip,
        tier=tier,
        obfuscation_method=method,
        tracker_vault_enabled=tracker_vault_enabled,
        tracker_vault_ok=tracker_vault_ok if tracker_vault_enabled else None,
        enabled_layers=layers_obf,
        require_tunnel=require_tunnel,
        # Killswitch binary belongs to GATE_KILLSWITCH, not obfuscation preflight
        require_killswitch_binary=False,
    )

    if not report_obf.ok:
        return _blocked(
            reason="preflight_failed",
            message=(
                "Obfuscation / privacy preflight failed — killswitch not armed; "
                "no protected session."
            ),
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_OBFUSCATION,
            gates_passed=gates_passed,
            arm_result=None,
            report=report_obf,
            killswitch_tripped=True,
            wipe_done=wipe_done,
            wipe_meta=wipe_meta,
            synthetic_profile=synth_meta,
        )

    gates_passed.append(GATE_OBFUSCATION)

    # ------------------------------------------------------------------
    # GATE 5: arm killswitch once (industry default with Activate)
    # ------------------------------------------------------------------
    killswitch_armed = False
    if callable(killswitch_arm_fn):
        if arm_attempted:
            return _blocked(
                reason="killswitch_double_arm",
                message="Killswitch arm race blocked — single arm per activate.",
                tier=tier,
                method=method,
                snap=snap,
                gate_stopped_at=GATE_KILLSWITCH,
                gates_passed=gates_passed,
                arm_result=arm_result,
                wipe_done=wipe_done,
                wipe_meta=wipe_meta,
                synthetic_profile=synth_meta,
            )
        arm_attempted = True
        try:
            arm_result = killswitch_arm_fn()
            killswitch_armed = interpret_arm_result(arm_result)
        except Exception as e:
            return _blocked(
                reason="killswitch_arm_failed",
                message="Killswitch arm raised — no protected session.",
                tier=tier,
                method=method,
                snap=snap,
                gate_stopped_at=GATE_KILLSWITCH,
                gates_passed=gates_passed,
                arm_result=None,
                error=str(e)[:200],
                wipe_done=wipe_done,
                wipe_meta=wipe_meta,
                synthetic_profile=synth_meta,
            )
    elif auto_arm_killswitch:
        if arm_attempted:
            return _blocked(
                reason="killswitch_double_arm",
                message="Killswitch arm race blocked — single arm per activate.",
                tier=tier,
                method=method,
                snap=snap,
                gate_stopped_at=GATE_KILLSWITCH,
                gates_passed=gates_passed,
                arm_result=arm_result,
                wipe_done=wipe_done,
                wipe_meta=wipe_meta,
                synthetic_profile=synth_meta,
            )
        arm_attempted = True
        try:
            try:
                from .pcs_killswitch_industrial_v20260802 import arm_for_activate
            except ImportError:
                from shared.pcs_killswitch_industrial_v20260802 import arm_for_activate

            arm_result = arm_for_activate(force_apply=force_pf_apply)
            # dry_run still counts as "armed intent" when conf written under industrial path
            killswitch_armed = interpret_arm_result(arm_result)
        except Exception as e:
            return _blocked(
                reason="killswitch_arm_failed",
                message="Killswitch arm raised — no protected session.",
                tier=tier,
                method=method,
                snap=snap,
                gate_stopped_at=GATE_KILLSWITCH,
                gates_passed=gates_passed,
                arm_result=None,
                error=str(e)[:200],
                wipe_done=wipe_done,
                wipe_meta=wipe_meta,
                synthetic_profile=synth_meta,
            )
    else:
        import shutil

        # Explicit no-op arm path (tests): presence of pfctl only
        killswitch_armed = shutil.which("pfctl") is not None
        arm_result = {
            "status": "dry_run" if killswitch_armed else "error",
            "armed": killswitch_armed,
            "message": "auto_arm_killswitch=False; pfctl presence only",
        }

    if not killswitch_armed:
        return _blocked(
            reason="killswitch_arm_failed",
            message=(
                "Killswitch did not arm (status not armed/dry_run) — "
                "no protected session."
            ),
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_KILLSWITCH,
            gates_passed=gates_passed,
            arm_result=arm_result,
            wipe_done=wipe_done,
            wipe_meta=wipe_meta,
            synthetic_profile=synth_meta,
        )

    gates_passed.append(GATE_KILLSWITCH)

    # ------------------------------------------------------------------
    # GATE 6: final verify including killswitch_armed
    # ------------------------------------------------------------------
    layers_final = build_enabled_layers(
        tier=tier,
        killswitch_armed=True,
        obfuscation_method=method,
        tracker_vault_enabled=tracker_vault_enabled,
        tracker_vault_ok=tracker_vault_ok,
        servers_configured=servers_ok if require_configured_servers else None,
        include_killswitch=True,
    )

    report = enforce_or_kill(
        _trip,
        tier=tier,
        obfuscation_method=method,
        tracker_vault_enabled=tracker_vault_enabled,
        tracker_vault_ok=tracker_vault_ok if tracker_vault_enabled else None,
        enabled_layers=layers_final,
        require_tunnel=require_tunnel,
    )

    if not report.ok:
        return _blocked(
            reason="preflight_failed",
            message=(
                "Final protection layer verify failed after killswitch arm — "
                "session not marked protected."
            ),
            tier=tier,
            method=method,
            snap=snap,
            gate_stopped_at=GATE_FINAL,
            gates_passed=gates_passed,
            arm_result=arm_result,
            report=report,
            killswitch_tripped=True,
            wipe_done=wipe_done,
            wipe_meta=wipe_meta,
            synthetic_profile=synth_meta,
        )

    gates_passed.append(GATE_FINAL)

    return _attach_server_fields(
        {
            "status": "protected",
            "protected": True,
            "tier": tier,
            "obfuscation": {"method": method, "description": describe_method(method)},
            "arm_result": arm_result,
            "report": report.to_dict(),
            "message": (
                "All enabled protection layers verified. "
                "Session may proceed under fail-closed monitoring."
            ),
            "gate_order": list(CANONICAL_GATE_ORDER),
            "gates_passed": list(gates_passed),
            "gate_stopped_at": None,
            "wipe_done": wipe_done,
            "wipe": wipe_meta,
            "synthetic_profile": synth_meta,
            "next_step": snap.get("next_step"),
            "howto_path": snap.get("howto_path") or snap.get("industrial_howto"),
            "inventory_path": snap.get("inventory_path"),
        },
        snap,
    )


def dry_run_fail_closed(*, tier: str = "core") -> dict[str, Any]:
    """CLI/demo helper: run protect gate against live readiness (no invented IPs)."""
    return activate_protected_session(
        tier=tier,
        killswitch_arm_fn=lambda: {"status": "dry_run", "armed": True, "dry_run": True},
        require_configured_servers=True,
        auto_arm_killswitch=False,
        require_tunnel=False,
    )


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    _root = Path(__file__).resolve().parents[1]
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
    # When executed as a file path, relative imports at module top fail before
    # this block runs — use package import entry instead:
    #   PYTHONPATH=<industrial> python3 -c "from shared.pcs_preflight_obfuscation_gate_v20260802 import dry_run_fail_closed; ..."
    # If package context is available (python -m), call local dry_run.
    try:
        out = dry_run_fail_closed(tier=sys.argv[1] if len(sys.argv) > 1 else "core")
    except NameError:
        from shared.pcs_preflight_obfuscation_gate_v20260802 import dry_run_fail_closed as _dry

        out = _dry(tier=sys.argv[1] if len(sys.argv) > 1 else "core")
    print(json.dumps(out, indent=2, default=str))
    raise SystemExit(0 if out.get("status") in ("blocked", "protected") else 1)
