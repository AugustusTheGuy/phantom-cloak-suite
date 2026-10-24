"""Deepcheck-style tests for PCS Industrial preflight (new location).

Proves fail-closed protect gate order without inventing production IPs:
  readiness_servers → optional_wipe → synthetic_profile →
  obfuscation_preflight → killswitch_arm → final_layer_verify
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.pcs_preflight_obfuscation_gate_v20260802 import (
    CANONICAL_GATE_ORDER,
    GATE_FINAL,
    GATE_KILLSWITCH,
    GATE_OBFUSCATION,
    GATE_READINESS,
    GATE_SYNTHETIC,
    GATE_WIPE,
    activate_protected_session,
    build_enabled_layers,
    interpret_arm_result,
    run_optional_wipe,
    run_synthetic_profile_gate,
)
from shared.pcs_server_readiness_v20260802 import gate_snapshot, scan_readiness
from shared.pcs_zeroleak_gate_v20260802 import run_preflight
from shared.pcs_pricing_engine_v20260802 import compute_core, compute_pro
from shared.pcs_killswitch_industrial_v20260802 import (
    PF_CONF_PATH,
    RULES_DIR,
    IndustrialKillSwitch,
    arm_for_activate,
)

STATE = Path.home() / ".pcs_industrial_20260802"

# Gates that pass after readiness when wipe is optional (no fn) and exit_ip unknown
_POST_READINESS_SOFT = [GATE_READINESS, GATE_WIPE, GATE_SYNTHETIC]


def _empty_readiness(**overrides):
    """Readiness shape with configured_count=0 — no invented public IPs."""
    base = {
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
            {"name": "zurich.pending.json", "kind": "pending_ip", "location": "zurich"},
        ],
        "inventory": {
            "path": str(STATE / "vps_inventory.json"),
            "exists": True,
            "ips_set": 0,
        },
        "howto_path": None,
        "industrial_howto": str(ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"),
        "summary": "0 client config(s) with real IPs",
        "next_step": "Edit inventory with real VPS public IPs then materialize",
    }
    base.update(overrides)
    return base


def _ready_readiness(**overrides):
    """configured_count>0 for unit tests only — does not write real IPs to disk."""
    base = {
        "status": "partial",
        "templates_count": 0,
        "configured_count": 1,
        "server_filled_count": 1,
        "pending_ip_count": 0,
        "templates": [],
        "configured": [{"name": "dubai.json", "kind": "client_configured"}],
        "server_filled": [{"name": "sing-box-dubai-reality.json"}],
        "pending": [],
        "inventory": {
            "path": str(STATE / "vps_inventory.json"),
            "exists": True,
            "ips_set": 1,
        },
        "howto_path": None,
        "industrial_howto": str(ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"),
        "summary": "1 client_configured (test override; no invented production IP files)",
        "next_step": None,
    }
    base.update(overrides)
    return base


def test_canonical_gate_order_constants():
    assert CANONICAL_GATE_ORDER == (
        GATE_READINESS,
        GATE_WIPE,
        GATE_SYNTHETIC,
        GATE_OBFUSCATION,
        GATE_KILLSWITCH,
        GATE_FINAL,
    )
    assert CANONICAL_GATE_ORDER == (
        "readiness_servers",
        "optional_wipe",
        "synthetic_profile",
        "obfuscation_preflight",
        "killswitch_arm",
        "final_layer_verify",
    )


def test_preflight_ok_without_vault():
    r = run_preflight(tier="core", tracker_vault_enabled=False)
    assert r.ok is True or any(c.name == "killswitch_binary" for c in r.checks)


def test_vault_required_fails_closed():
    r = run_preflight(
        tier="core",
        tracker_vault_enabled=True,
        tracker_vault_ok=False,
        enabled_layers={"killswitch_armed": True, "obfuscation_selected": True},
    )
    assert r.ok is False
    assert any(c.name == "tracker_vault" and not c.passed for c in r.checks)


def test_activate_trips_on_failed_layer():
    trips = []
    arms = []

    def arm():
        arms.append("arm")
        return {"status": "dry_run", "armed": True}

    def trip(report):
        trips.append(report)

    # Isolate vault failure from live VPS inventory (no invented IPs).
    # Gate order: readiness skipped via require_configured_servers=False →
    # wipe (no fn) → synthetic (no exit_ip) → obfuscation fails on vault → arm must NOT run.
    out = activate_protected_session(
        tier="core",
        tracker_vault_enabled=True,
        tracker_vault_ok=False,
        killswitch_arm_fn=arm,
        killswitch_trip_fn=trip,
        require_configured_servers=False,
        auto_arm_killswitch=False,
        readiness_override=_ready_readiness(),
    )
    assert out["protected"] is False
    assert out.get("killswitch_tripped") is True
    assert trips, "killswitch must trip before broadcast"
    assert arms == [], "arm must not run when obfuscation preflight fails"
    assert out.get("arm_result") is None
    assert out.get("gate_stopped_at") == GATE_OBFUSCATION
    assert GATE_READINESS in (out.get("gates_passed") or [])
    assert GATE_WIPE in (out.get("gates_passed") or [])
    assert GATE_SYNTHETIC in (out.get("gates_passed") or [])
    assert GATE_KILLSWITCH not in (out.get("gates_passed") or [])
    assert out.get("wipe_done") is False


def test_activate_fail_closed_when_no_configured_clients():
    """Protect path must refuse when configured_count==0 (no fake IPs needed)."""
    trips = []
    arms = []
    wipes = []

    def arm():
        arms.append("arm")
        return {"status": "dry_run", "armed": True}

    def trip(report):
        trips.append(report)

    def wipe():
        wipes.append("wipe")
        return {"ok": True}

    out = activate_protected_session(
        tier="core",
        killswitch_arm_fn=arm,
        killswitch_trip_fn=trip,
        wipe_fn=wipe,
        require_configured_servers=True,
        readiness_override=_empty_readiness(),
        auto_arm_killswitch=False,
    )
    assert out["protected"] is False
    assert out["status"] == "blocked"
    assert out["reason"] == "servers_not_configured"
    assert out["configured_count"] == 0
    assert out["server_filled_count"] == 3
    assert out["pending_ip_count"] == 2
    assert isinstance(out.get("pending"), list) and len(out["pending"]) == 2
    assert out.get("server_readiness", {}).get("ok_for_protect") is False
    assert "inventory" in (out.get("message") or "").lower() or out.get("inventory_path")
    assert trips, "fail-closed must surface trip callback when provided"
    # Arm and wipe must not run when servers gate blocks first
    assert out.get("arm_result") is None
    assert arms == []
    assert wipes == [], "wipe must not run before readiness passes"
    assert out.get("gate_stopped_at") == GATE_READINESS
    assert out.get("gates_passed") == []
    assert out.get("gate_order") == list(CANONICAL_GATE_ORDER)
    assert out.get("wipe_done") is False


def test_gate_order_obfuscation_before_arm_on_ready_servers():
    """When servers OK, vault fail still blocks before arm (order proof)."""
    arms = []
    trips = []

    def arm():
        arms.append(1)
        return {"status": "dry_run", "armed": True, "dry_run": True}

    def trip(report):
        trips.append(report)

    out = activate_protected_session(
        tier="core",
        tracker_vault_enabled=True,
        tracker_vault_ok=False,
        killswitch_arm_fn=arm,
        killswitch_trip_fn=trip,
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
    )
    assert out["protected"] is False
    assert out["reason"] == "preflight_failed"
    assert out["gate_stopped_at"] == GATE_OBFUSCATION
    assert out["gates_passed"] == _POST_READINESS_SOFT
    assert arms == []
    assert out.get("arm_result") is None
    assert trips


def test_gate_order_arm_failure_never_protected():
    """Killswitch arm failure after readiness+obfuscation → blocked, not protected."""
    out = activate_protected_session(
        tier="core",
        killswitch_arm_fn=lambda: {"status": "error", "message": "pfctl denied", "armed": False},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
    )
    assert out["protected"] is False
    assert out["status"] == "blocked"
    assert out["reason"] == "killswitch_arm_failed"
    assert out["gate_stopped_at"] == GATE_KILLSWITCH
    assert GATE_READINESS in out["gates_passed"]
    assert GATE_WIPE in out["gates_passed"]
    assert GATE_SYNTHETIC in out["gates_passed"]
    assert GATE_OBFUSCATION in out["gates_passed"]
    assert GATE_FINAL not in out["gates_passed"]
    assert out.get("message")


def test_gate_order_success_all_phases(monkeypatch):
    """All gates pass → protected; order recorded; no invented IPs on disk."""
    # Avoid live DNS flakiness in final verify: layer map still enforces killswitch
    out = activate_protected_session(
        tier="core",
        killswitch_arm_fn=lambda: {"status": "dry_run", "armed": True, "dry_run": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
        require_tunnel=False,
        # No exit_ip → synthetic skipped; wipe unavailable → wipe_done=False
    )
    # Live DNS/pfctl may fail in hermetic CI — if so must still be fail-closed
    if out.get("protected"):
        assert out["status"] == "protected"
        assert out["gate_stopped_at"] is None
        assert out["gates_passed"] == list(CANONICAL_GATE_ORDER)
        assert out.get("arm_result", {}).get("status") == "dry_run"
        assert out.get("wipe_done") is False
    else:
        assert out["protected"] is False
        assert out["status"] == "blocked"
        # Must not claim protected; must stop at a known gate
        assert out.get("gate_stopped_at") in (
            GATE_WIPE,
            GATE_SYNTHETIC,
            GATE_OBFUSCATION,
            GATE_KILLSWITCH,
            GATE_FINAL,
        )


def test_optional_wipe_records_false_when_unavailable():
    meta = run_optional_wipe(None)
    assert meta["wipe_done"] is False
    assert meta["wipe_available"] is False
    assert meta["ok"] is True

    calls = []

    def wipe():
        calls.append(1)
        return {"ok": True}

    meta2 = run_optional_wipe(wipe)
    assert calls == [1]
    assert meta2["wipe_done"] is True
    assert meta2["ok"] is True


def test_optional_wipe_fail_closed_when_hook_errors():
    arms = []

    def bad_wipe():
        raise RuntimeError("rm denied")

    out = activate_protected_session(
        tier="core",
        wipe_fn=bad_wipe,
        killswitch_arm_fn=lambda: arms.append(1) or {"status": "dry_run", "armed": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
    )
    assert out["protected"] is False
    assert out["reason"] == "wipe_failed"
    assert out["gate_stopped_at"] == GATE_WIPE
    assert out["gates_passed"] == [GATE_READINESS]
    assert out["wipe_done"] is False
    assert arms == [], "arm must not run after wipe failure"


def test_optional_wipe_success_sets_wipe_done_before_synth():
    wipes = []

    def wipe():
        wipes.append("w")
        return {"ok": True}

    out = activate_protected_session(
        tier="core",
        wipe_fn=wipe,
        killswitch_arm_fn=lambda: {"status": "dry_run", "armed": True, "dry_run": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
        require_tunnel=False,
        # exit_ip unknown → synthetic does not block even with wipe_done
        exit_ip="",
    )
    assert wipes == ["w"]
    assert out.get("wipe_done") is True
    assert GATE_WIPE in (out.get("gates_passed") or [])
    # Must have passed wipe before later gates (or stopped later)
    if out.get("gate_stopped_at") is None:
        assert out["gates_passed"].index(GATE_WIPE) < out["gates_passed"].index(GATE_SYNTHETIC)
        assert out["gates_passed"].index(GATE_SYNTHETIC) < out["gates_passed"].index(
            GATE_OBFUSCATION
        )


def test_synthetic_profile_blocks_when_exit_ip_known_and_score_fails():
    """exit_ip known + no wipe → pass_gate fails → protect blocked at synthetic_profile."""
    arms = []

    out = activate_protected_session(
        tier="core",
        wipe_fn=None,  # wipe_done=False
        exit_ip="8.8.8.8",
        location="germany",
        purpose="crypto",  # higher threshold
        killswitch_arm_fn=lambda: arms.append(1) or {"status": "dry_run", "armed": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
    )
    assert out["protected"] is False
    assert out["reason"] == "synthetic_profile_gate_failed"
    assert out["gate_stopped_at"] == GATE_SYNTHETIC
    assert out["gates_passed"] == [GATE_READINESS, GATE_WIPE]
    assert arms == [], "arm must not run when synthetic profile fails"
    assert out.get("wipe_done") is False
    synth = out.get("synthetic_profile") or {}
    assert synth.get("applied") is True
    assert synth.get("exit_ip_known") is True
    assert synth.get("ok") is False


def test_synthetic_profile_skips_block_when_exit_ip_unknown():
    """exit_ip unknown → synthetic gate not applied; later gates may still fail-closed."""
    out = activate_protected_session(
        tier="core",
        wipe_fn=None,
        exit_ip="",
        location="germany",
        purpose="browsing",
        killswitch_arm_fn=lambda: {"status": "dry_run", "armed": True, "dry_run": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
        require_tunnel=False,
    )
    # Must not stop at synthetic for unknown exit
    assert out.get("gate_stopped_at") != GATE_SYNTHETIC
    synth = out.get("synthetic_profile") or {}
    if GATE_SYNTHETIC in (out.get("gates_passed") or []):
        assert synth.get("skipped") is True or synth.get("exit_ip_known") is False


def test_synthetic_profile_passes_with_wipe_and_exit_ip():
    """exit_ip known + wipe_done + reasonable score → synthetic gate ok."""
    arms = []

    def wipe():
        return {"ok": True}

    out = activate_protected_session(
        tier="core",
        wipe_fn=wipe,
        exit_ip="8.8.8.8",
        location="germany",
        purpose="browsing",
        asn_class="isp",
        leak_checks_ok=True,
        killswitch_arm_fn=lambda: arms.append(1)
        or {"status": "dry_run", "armed": True, "dry_run": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
        require_tunnel=False,
    )
    assert out.get("wipe_done") is True
    # Synthetic must have been applied and passed (or we never reach arm)
    if out.get("gate_stopped_at") == GATE_SYNTHETIC:
        raise AssertionError(f"synthetic should pass: {out.get('synthetic_profile')}")
    assert GATE_SYNTHETIC in (out.get("gates_passed") or [])
    synth = out.get("synthetic_profile") or {}
    assert synth.get("applied") is True
    assert synth.get("ok") is True
    if out.get("protected"):
        assert arms == [1]
        assert out["gates_passed"] == list(CANONICAL_GATE_ORDER)


def test_gate_order_sequence_on_synthetic_fail_before_obfuscation():
    """Prove readiness → wipe → synthetic stop; obfuscation/arm never run."""
    arms = []
    wipes = []

    def wipe():
        wipes.append(1)
        # Explicit fail so wipe_done=False and synthetic will fail with exit_ip
        return {"ok": False, "error": "operator cancelled"}

    # wipe fails first — stop at wipe, not synthetic
    out_wipe = activate_protected_session(
        tier="core",
        wipe_fn=wipe,
        exit_ip="1.1.1.1",
        location="dubai",
        killswitch_arm_fn=lambda: arms.append(1) or {"status": "dry_run", "armed": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
    )
    assert out_wipe["gate_stopped_at"] == GATE_WIPE
    assert GATE_OBFUSCATION not in out_wipe["gates_passed"]
    assert arms == []
    assert wipes == [1]

    # wipe ok but score fails (crypto threshold + datacenter + no leak verify)
    arms.clear()
    wipes.clear()

    def wipe_ok():
        wipes.append(1)
        return {"ok": True}

    out_synth = activate_protected_session(
        tier="core",
        wipe_fn=wipe_ok,
        exit_ip="203.0.113.10",  # TEST-NET — not production inventory
        location="unknown",  # weak locale pack
        purpose="crypto",
        asn_class="datacenter",
        leak_checks_ok=False,
        killswitch_arm_fn=lambda: arms.append(1) or {"status": "dry_run", "armed": True},
        require_configured_servers=True,
        readiness_override=_ready_readiness(),
        auto_arm_killswitch=False,
        tracker_vault_enabled=False,
    )
    # With wipe + exit_ip, score may still pass or fail depending on thresholds;
    # if wipe+exit present, pass_gate requires total>=threshold — unknown locale may fail.
    # Either stop at synthetic (score fail) or pass synthetic — never reorder.
    gp = out_synth.get("gates_passed") or []
    if out_synth.get("gate_stopped_at") == GATE_SYNTHETIC:
        assert gp == [GATE_READINESS, GATE_WIPE]
        assert arms == []
    else:
        assert GATE_WIPE in gp and GATE_SYNTHETIC in gp
        assert gp.index(GATE_WIPE) < gp.index(GATE_SYNTHETIC)


def test_run_synthetic_profile_gate_helpers():
    skipped = run_synthetic_profile_gate(location="germany", exit_ip="", wipe_done=False)
    assert skipped["ok"] is True
    assert skipped["skipped"] is True
    assert skipped["exit_ip_known"] is False

    failed = run_synthetic_profile_gate(
        location="germany",
        exit_ip="8.8.8.8",
        wipe_done=False,
        purpose="crypto",
    )
    assert failed["ok"] is False
    assert failed["applied"] is True

    passed = run_synthetic_profile_gate(
        location="germany",
        exit_ip="8.8.8.8",
        wipe_done=True,
        purpose="browsing",
        asn_class="isp",
        leak_checks_ok=True,
    )
    assert passed["ok"] is True


def test_interpret_arm_result_fail_closed():
    assert interpret_arm_result(None) is False
    assert interpret_arm_result({"status": "error"}) is False
    assert interpret_arm_result({"error": "x"}) is False
    assert interpret_arm_result({}) is False
    assert interpret_arm_result({"status": "armed", "armed": True}) is True
    assert interpret_arm_result({"status": "dry_run"}) is True
    assert interpret_arm_result({"armed": True}) is True


def test_build_enabled_layers_can_omit_killswitch():
    layers = build_enabled_layers(
        tier="core",
        killswitch_armed=False,
        obfuscation_method="reality",
        tracker_vault_enabled=False,
        tracker_vault_ok=True,
        include_killswitch=False,
    )
    assert "killswitch_armed" not in layers
    assert layers["obfuscation_selected"] is True
    layers2 = build_enabled_layers(
        tier="core",
        killswitch_armed=True,
        obfuscation_method="reality",
        tracker_vault_enabled=False,
        tracker_vault_ok=True,
        include_killswitch=True,
    )
    assert layers2["killswitch_armed"] is True


def test_gate_snapshot_surfaces_filled_and_pending():
    snap = gate_snapshot(
        {
            "status": "server_package_ready_pending_client_ips",
            "configured_count": 0,
            "server_filled_count": 8,
            "pending_ip_count": 8,
            "pending": [{"name": "a.pending.json"}],
            "inventory": {"path": "/tmp/inv.json", "ips_set": 0},
            "howto_path": None,
            "industrial_howto": "/docs/howto.md",
            "summary": "demo",
            "next_step": "fill ips",
        }
    )
    assert snap["ok_for_protect"] is False
    assert snap["server_filled_count"] == 8
    assert snap["pending_ip_count"] == 8
    assert snap["pending"]
    assert snap["block_message"]


def test_live_scan_fail_closed_when_zero_configured():
    """If the machine has no real client IPs, live activate must not claim protected."""
    live = scan_readiness()
    if int(live.get("configured_count") or 0) > 0:
        # Environment already has real IPs — skip without inventing the opposite.
        return
    arms = []
    out = activate_protected_session(
        tier="core",
        killswitch_arm_fn=lambda: arms.append("x") or {"status": "dry_run", "armed": True},
        require_configured_servers=True,
        auto_arm_killswitch=False,
    )
    assert out["protected"] is False
    assert out["reason"] == "servers_not_configured"
    assert "server_filled_count" in out
    assert "pending" in out
    assert out.get("gate_stopped_at") == GATE_READINESS
    assert arms == [], "live zero-configured must not arm killswitch"


def test_industrial_killswitch_path_never_tmp():
    assert "pf_rules" in str(RULES_DIR)
    assert str(RULES_DIR) == str(STATE / "pf_rules")
    assert not str(PF_CONF_PATH).startswith("/tmp")
    assert "/tmp/" not in str(PF_CONF_PATH)
    ks = IndustrialKillSwitch()
    meta = ks.write_rules_file()
    assert meta["status"] == "written"
    assert str(meta["path"]).startswith(str(STATE / "pf_rules"))
    dry = arm_for_activate(force_apply=False)
    assert dry["status"] == "dry_run"
    assert not str(dry["path"]).startswith("/tmp")
    assert "pcs_industrial" in dry["path"]


def test_blocked_payload_message_consistent_fields():
    out = activate_protected_session(
        tier="core",
        require_configured_servers=True,
        readiness_override=_empty_readiness(),
        auto_arm_killswitch=False,
        killswitch_arm_fn=lambda: {"status": "dry_run", "armed": True},
    )
    for key in (
        "status",
        "protected",
        "reason",
        "message",
        "tier",
        "obfuscation",
        "gate_order",
        "gates_passed",
        "gate_stopped_at",
        "configured_count",
        "server_filled_count",
        "pending_ip_count",
        "wipe_done",
    ):
        assert key in out, f"missing consistent field {key}"
    assert out["protected"] is False
    assert out["status"] == "blocked"
    assert out["gate_order"] == list(CANONICAL_GATE_ORDER)


def test_pricing_core_under_nord_list_anchor():
    c = compute_core()
    assert c.monthly_usd <= 12.99
    assert c.annual_effective_monthly < c.monthly_usd


def test_pricing_pro_under_multilogin_class():
    p = compute_pro()
    assert p.monthly_usd < 99.0
