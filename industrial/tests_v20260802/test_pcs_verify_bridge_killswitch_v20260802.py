"""Agent 10 — verify bridge trip_killswitch_recommended contract.

- Live IP mismatch → trip_killswitch_recommended=true (+ optional hook)
- Dry-run / offline → overall NOT_RUN, flag false, hook never invoked
"""
from __future__ import annotations

from typing import Any, Dict, List

from shared.pcs_verify_bridge_v20260802 import (
    build_report,
    evaluate_ip_vs_expected,
    overall_from_checks,
    run_verification,
    trip_killswitch_recommended_from_verdict,
)


def test_evaluate_ip_mismatch_reason():
    v = evaluate_ip_vs_expected(["203.0.113.50"], "104.21.16.42")
    assert v["verdict"] == "fail"
    assert v["reason"] == "ip_mismatch_possible_leak"


def test_trip_flag_only_on_live_ip_mismatch():
    mismatch = {
        "verdict": "fail",
        "reason": "ip_mismatch_possible_leak",
        "observed_ips": ["203.0.113.50"],
        "expected_ip": "104.21.16.42",
    }
    assert trip_killswitch_recommended_from_verdict(
        mismatch, dry_run=False, live_checks=True
    ) is True
    # dry-run never recommends
    assert trip_killswitch_recommended_from_verdict(
        mismatch, dry_run=True, live_checks=False
    ) is False
    assert trip_killswitch_recommended_from_verdict(
        mismatch, dry_run=True, live_checks=True
    ) is False
    # no live checks
    assert trip_killswitch_recommended_from_verdict(
        mismatch, dry_run=False, live_checks=False
    ) is False
    # other fails do not trip recommend
    assert trip_killswitch_recommended_from_verdict(
        {"verdict": "fail", "reason": "no_public_ip_observed"},
        dry_run=False,
        live_checks=True,
    ) is False
    assert trip_killswitch_recommended_from_verdict(
        {"verdict": "pass", "reason": "matches_exit"},
        dry_run=False,
        live_checks=True,
    ) is False
    assert trip_killswitch_recommended_from_verdict(
        None, dry_run=False, live_checks=True
    ) is False


def test_build_report_live_mismatch_sets_flag():
    mismatch = evaluate_ip_vs_expected(["203.0.113.9"], "104.21.16.42")
    report = build_report(
        location="dubai",
        location_source="cli",
        expected_ip="104.21.16.42",
        expected_source="cli",
        discovery={
            "full_suite_runnable": False,
            "present_count": 0,
            "missing": [],
            "tools": {},
        },
        preflight={"configured": True, "status": "configured", "detail": "ok"},
        tunnel={
            "present": True,
            "detail": "sing0",
            "interfaces": ["sing0"],
            "ambient_utun": [],
            "singbox_running": True,
            "required_for_live_checks": True,
        },
        dry_run=False,
        force=False,
        ip_result={
            "observed_ips": ["203.0.113.9"],
            "sources": {},
            "consensus_ip": "203.0.113.9",
            "consistent": True,
        },
        dns_result={"status": "ran", "domains": []},
        suite_result=None,
        ip_verdict=mismatch,
        skip_reasons=[],
    )
    assert report["trip_killswitch_recommended"] is True
    assert report["ceo"]["trip_killswitch_recommended"] is True
    assert report["ceo"]["overall"] == "FAIL"
    assert report["mode"]["live_checks"] is True
    assert report["mode"]["dry_run"] is False


def test_build_report_dry_run_not_run_and_no_trip():
    report = build_report(
        location="dubai",
        location_source="cli",
        expected_ip="104.21.16.42",
        expected_source="cli",
        discovery={
            "full_suite_runnable": True,
            "present_count": 1,
            "missing": [],
            "tools": {
                "full_verification_suite": {
                    "path": "/nonexistent/full_verification_suite.py",
                    "present": True,
                }
            },
        },
        preflight={"configured": False, "status": "pending_vps_ip", "detail": "pending",
                   "skip_reasons": ["client_pending_ip"]},
        tunnel={
            "present": False,
            "detail": "no PCS tunnel",
            "interfaces": [],
            "ambient_utun": ["utun0"],
            "singbox_running": False,
            "required_for_live_checks": True,
        },
        dry_run=True,
        force=False,
        ip_result=None,
        dns_result=None,
        suite_result=None,
        ip_verdict=None,
        skip_reasons=["client_pending_ip", "no_tunnel", "dry_run"],
    )
    assert report["ceo"]["overall"] == "NOT_RUN"
    assert report["trip_killswitch_recommended"] is False
    assert report["ceo"]["trip_killswitch_recommended"] is False
    assert report["mode"]["live_checks"] is False
    # even if a stale mismatch verdict were passed, dry_run must not recommend
    report2 = build_report(
        location="dubai",
        location_source="cli",
        expected_ip="104.21.16.42",
        expected_source="cli",
        discovery={"full_suite_runnable": False, "present_count": 0, "missing": [], "tools": {}},
        preflight={"configured": True, "status": "configured", "detail": "ok"},
        tunnel={
            "present": False,
            "detail": "no tunnel",
            "interfaces": [],
            "ambient_utun": [],
            "singbox_running": False,
            "required_for_live_checks": True,
        },
        dry_run=True,
        force=False,
        ip_result=None,
        dns_result=None,
        suite_result=None,
        ip_verdict={
            "verdict": "fail",
            "reason": "ip_mismatch_possible_leak",
            "observed_ips": ["1.2.3.4"],
            "expected_ip": "104.21.16.42",
        },
        skip_reasons=["dry_run", "no_tunnel"],
    )
    assert report2["trip_killswitch_recommended"] is False
    assert report2["ceo"]["overall"] == "NOT_RUN"


def test_optional_hook_invoked_only_on_live_mismatch(monkeypatch):
    """run_verification with mocked live IP path invokes hook once."""
    calls: List[Dict[str, Any]] = []

    def fake_tunnel() -> Dict[str, Any]:
        return {
            "present": True,
            "interfaces": ["sing0"],
            "ambient_utun": [],
            "singbox_running": True,
            "detail": "sing0",
            "required_for_live_checks": True,
        }

    def fake_ip_checks() -> Dict[str, Any]:
        return {
            "sources": {"ipify": {"ip": "203.0.113.77"}},
            "observed_ips": ["203.0.113.77"],
            "consensus_ip": "203.0.113.77",
            "consistent": True,
        }

    def fake_dns() -> Dict[str, Any]:
        return {"status": "ran", "domains": []}

    def fake_preflight(_loc: Any) -> Dict[str, Any]:
        return {
            "configured": True,
            "status": "configured",
            "detail": "configured",
            "skip_reasons": [],
        }

    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.detect_tunnel", fake_tunnel
    )
    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.run_ip_checks", fake_ip_checks
    )
    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.run_dns_checks", fake_dns
    )
    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.preflight_client_config", fake_preflight
    )
    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.discover_suite_tools",
        lambda: {
            "full_suite_runnable": False,
            "present_count": 0,
            "missing": ["full_verification_suite"],
            "tools": {},
            "suite_root": "",
        },
    )

    def hook(rep: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(rep)
        return {"status": "queued", "armed": False}

    report = run_verification(
        location="dubai",
        expected_ip="104.21.16.42",
        dry_run=False,
        force=False,
        run_suite=False,
        write=False,
        killswitch_trip_fn=hook,
    )
    assert report["trip_killswitch_recommended"] is True
    assert report["ceo"]["overall"] == "FAIL"
    assert report["killswitch_trip_hook"]["invoked"] is True
    assert report["killswitch_trip_hook"]["result"]["status"] == "queued"
    assert len(calls) == 1


def test_optional_hook_not_invoked_on_dry_run(monkeypatch):
    calls: List[Any] = []

    monkeypatch.setattr(
        "shared.pcs_verify_bridge_v20260802.detect_tunnel",
        lambda: {
            "present": False,
            "interfaces": [],
            "ambient_utun": ["utun0"],
            "singbox_running": False,
            "detail": "no tunnel",
            "required_for_live_checks": True,
        },
    )

    report = run_verification(
        location="dubai",
        expected_ip="104.21.16.42",
        dry_run=True,
        force=False,
        run_suite=False,
        write=False,
        killswitch_trip_fn=lambda r: calls.append(r) or {"status": "should_not_run"},
    )
    assert report["ceo"]["overall"] == "NOT_RUN"
    assert report["trip_killswitch_recommended"] is False
    assert report["killswitch_trip_hook"]["invoked"] is False
    assert calls == []


def test_overall_from_checks_skip_is_not_run():
    checks = [
        {"name": "a", "status": "pass", "required": True},
        {"name": "b", "status": "skip", "required": True},
    ]
    assert overall_from_checks(checks) == "NOT_RUN"
