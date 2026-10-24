"""Resume honesty tests (industrial only).

Guarantees under test:
  1. Resume restores purpose / country / tier / catalog selection.
  2. Disk never restores protected=true / active=true as a live claim.
  3. configured_count==0 → never protected (save + load + resume_and_protect).
  4. Full resume path re-runs readiness + preflight before any protected claim.
  5. last_session path stays under industrial state (configure_paths hermetic).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import pcs_session_resume_v20260802 as resume


@pytest.fixture
def hermetic_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate last_session under a throwaway industrial state tree."""
    state = tmp_path / ".pcs_industrial_20260802"
    state.mkdir(parents=True)
    session_file = state / "last_session_industrial.json"
    legacy = tmp_path / ".phantomcloak" / "last_session.json"
    legacy.parent.mkdir(parents=True)

    resume.configure_paths(state=state, session_file=session_file, legacy_session=legacy)

    yield {
        "state": state,
        "session_file": session_file,
        "legacy": legacy,
    }

    # Restore production paths so other tests / interactive use stay correct
    home = Path.home()
    resume.configure_paths(
        state=home / ".pcs_industrial_20260802",
        session_file=home / ".pcs_industrial_20260802" / "last_session_industrial.json",
        legacy_session=home / ".phantomcloak" / "last_session.json",
    )


def test_save_path_is_industrial_only(hermetic_session):
    resume.save_session(
        {"purpose": "streaming", "country": "DE", "location": "frankfurt", "tier": "pro"},
        configured_count=0,
        protected=False,
    )
    assert hermetic_session["session_file"].exists()
    assert ".pcs_industrial_20260802" in str(hermetic_session["session_file"])
    raw = json.loads(hermetic_session["session_file"].read_text())
    assert raw["purpose"] == "streaming"
    assert raw["country"] == "DE"
    assert raw["tier"] == "pro"


def test_never_save_protected_when_configured_count_zero(hermetic_session):
    """HARD RULE: configured_count==0 ⇒ protected/active false even if caller lies."""
    out = resume.save_session(
        {
            "purpose": "browsing",
            "country": "CH",
            "location": "zurich",
            "active": True,
            "protected": True,
            "configured_count": 0,
        },
        configured_count=0,
        protected=True,
        allow_protected_claim=True,  # even with allow flag, count==0 wins
    )
    assert out["protected"] is False
    assert out["active"] is False
    assert out["configured_count"] == 0
    disk = json.loads(hermetic_session["session_file"].read_text())
    assert disk["protected"] is False
    assert disk["active"] is False


def test_allow_protected_only_with_count_and_flag(hermetic_session):
    denied = resume.save_session(
        {"purpose": "browsing", "country": "CH", "active": True, "protected": True},
        configured_count=3,
        protected=True,
        allow_protected_claim=False,  # no live gate acknowledgment
    )
    assert denied["protected"] is False
    assert denied["active"] is False

    ok = resume.save_session(
        {
            "purpose": "browsing",
            "country": "CH",
            "location": "zurich",
            "tier": "core",
            "catalog_ip_id": "CH-001",
            "active": True,
            "protected": True,
        },
        configured_count=3,
        protected=True,
        allow_protected_claim=True,
    )
    assert ok["protected"] is True
    assert ok["active"] is True
    assert ok["configured_count"] == 3
    assert ok["catalog_ip_id"] == "CH-001"


def test_load_strips_stale_protected_claims(hermetic_session):
    """Poison disk with protected=true; honest load must clear it."""
    poison = {
        "purpose": "banking",
        "country": "AE",
        "location": "dubai",
        "country_name": "Dubai",
        "tier": "pro",
        "catalog_ip_id": "AE-002",
        "residential_ip": {"id": "AE-002", "city": "Dubai", "isp": "Etisalat Home"},
        "active": True,
        "protected": True,
        "tunnel_active": True,
        "zero_leak_verified": True,
        "configured_count": 0,
        "saved_at": "2026-01-01T00:00:00+00:00",
    }
    hermetic_session["session_file"].write_text(json.dumps(poison, indent=2))

    s = resume.load_session(honest=True)
    assert s is not None
    assert s["purpose"] == "banking"
    assert s["country"] == "AE"
    assert s["location"] == "dubai"
    assert s["tier"] == "pro"
    assert s["catalog_ip_id"] == "AE-002"
    assert s["protected"] is False
    assert s["active"] is False
    assert s["tunnel_active"] is False
    assert s["zero_leak_verified"] is False
    assert s.get("honesty", {}).get("restored_selection_only") is True


def test_load_strips_protected_even_when_disk_count_positive(hermetic_session):
    """Selection restored; protection still requires live re-gate."""
    hermetic_session["session_file"].write_text(
        json.dumps(
            {
                "purpose": "streaming",
                "country": "DE",
                "location": "frankfurt",
                "tier": "core",
                "catalog_ip_id": "DE-001",
                "active": True,
                "protected": True,
                "configured_count": 5,
            }
        )
    )
    s = resume.load_session(honest=True)
    assert s["purpose"] == "streaming"
    assert s["country"] == "DE"
    assert s["tier"] == "core"
    assert s["catalog_ip_id"] == "DE-001"
    assert s["protected"] is False
    assert s["active"] is False
    assert "re-run readiness" in (s.get("honesty") or {}).get("reason", "").lower() or s.get(
        "honesty", {}
    ).get("restored_selection_only")


def test_resume_payload_never_claims_protected(hermetic_session):
    hermetic_session["session_file"].write_text(
        json.dumps(
            {
                "purpose": "browsing",
                "country": "CH",
                "location": "zurich",
                "tier": "pro",
                "active": True,
                "protected": True,
                "configured_count": 9,
            }
        )
    )
    p = resume.resume_payload()
    assert p["available"] is True
    assert p["protected"] is False
    assert p["active"] is False
    assert p["requires_preflight"] is True
    assert p["requires_readiness"] is True
    assert p["tier"] == "pro"
    assert p["purpose"] == "browsing"
    assert p["country"] == "CH"
    assert "Zurich" in p["label"] or "zurich" in p["label"].lower()
    assert p["selection"]["tier"] == "pro"


def test_extract_selection_and_activate_kwargs(hermetic_session):
    sel = resume.extract_selection(
        {
            "purpose": "work",
            "country": "ca",
            "location": "vancouver",
            "tier": "PRO",
            "residential_ip": {"id": "CA-015", "city": "Vancouver", "isp": "Rogers Home"},
            "protected": True,
            "active": True,
        }
    )
    assert sel["country"] == "CA"
    assert sel["tier"] == "pro"
    assert sel["catalog_ip_id"] == "CA-015"
    assert "protected" not in sel
    assert "active" not in sel

    kwargs = resume.activate_kwargs_from_session(sel)
    assert kwargs["purpose"] == "work"
    assert kwargs["country_code"] == "CA"
    assert kwargs["ip_id"] == "CA-015"


def test_resume_and_protect_blocks_when_count_zero(hermetic_session):
    """Full resume path: restore selection, live readiness=0 → not protected."""
    resume.save_session(
        {
            "purpose": "banking",
            "country": "SG",
            "location": "singapore",
            "country_name": "Singapore",
            "tier": "pro",
            "catalog_ip_id": "SG-003",
        },
        configured_count=0,
        allow_protected_claim=False,
    )

    def fake_readiness() -> Dict[str, Any]:
        return {
            "status": "templates_only",
            "configured_count": 0,
            "server_filled_count": 8,
            "pending_ip_count": 8,
            "summary": "0 configured",
        }

    # activate_fn must NOT be called when count==0 (gate first)
    called = {"n": 0}

    def should_not_run(**_kwargs):
        called["n"] += 1
        return {"protected": True}  # would be dishonest if used

    out = resume.resume_and_protect(
        readiness_scan_fn=fake_readiness,
        activate_fn=should_not_run,
        require_configured_servers=True,
    )
    assert called["n"] == 0
    assert out["protected"] is False
    assert out["active"] is False
    assert out["reason"] == "servers_not_configured"
    assert out["selection"]["purpose"] == "banking"
    assert out["selection"]["country"] == "SG"
    assert out["selection"]["tier"] == "pro"
    assert out["selection"]["catalog_ip_id"] == "SG-003"
    assert out["configured_count"] == 0

    # Disk still honest after resume attempt
    reloaded = resume.load_session(honest=True)
    assert reloaded["protected"] is False
    assert reloaded["active"] is False
    assert reloaded["purpose"] == "banking"
    assert reloaded["country"] == "SG"


def test_resume_and_protect_reruns_preflight_before_protected(hermetic_session):
    """When readiness ok, activate/preflight must run; protected follows live result."""
    resume.save_session(
        {
            "purpose": "browsing",
            "country": "CH",
            "location": "zurich",
            "tier": "core",
            "catalog_ip_id": "CH-001",
            "protected": True,  # stale claim on prior intent only
            "active": True,
        },
        configured_count=0,  # will be overridden by live readiness
        allow_protected_claim=False,
    )

    def fake_readiness() -> Dict[str, Any]:
        return {
            "status": "ready",
            "configured_count": 2,
            "server_filled_count": 2,
            "pending_ip_count": 0,
            "summary": "2 configured",
        }

    calls = []

    def fake_activate(**kwargs):
        calls.append(kwargs)
        return {
            "protected": True,
            "status": "protected",
            "configured_count": 2,
            "server_filled_count": 2,
            "pending_ip_count": 0,
            "report": {"ok": True},
        }

    out = resume.resume_and_protect(
        readiness_scan_fn=fake_readiness,
        activate_fn=fake_activate,
        require_configured_servers=True,
    )
    assert len(calls) == 1
    assert calls[0]["purpose"] == "browsing"
    assert calls[0]["country_code"] == "CH"
    assert calls[0]["ip_id"] == "CH-001"
    assert calls[0]["tier"] == "core"
    assert out["protected"] is True
    assert out["selection"]["catalog_ip_id"] == "CH-001"

    # Honest load after successful protect still strips for next cold start
    cold = resume.load_session(honest=True)
    assert cold["purpose"] == "browsing"
    assert cold["catalog_ip_id"] == "CH-001"
    assert cold["protected"] is False  # disk never re-authorizes without re-gate


def test_resume_and_protect_preflight_failure_not_protected(hermetic_session):
    resume.save_session(
        {"purpose": "browsing", "country": "CH", "location": "zurich", "tier": "core"},
        configured_count=0,
    )

    def fake_readiness():
        return {"configured_count": 4, "server_filled_count": 4, "pending_ip_count": 0}

    def fail_activate(**_k):
        return {
            "protected": False,
            "status": "blocked",
            "reason": "preflight_failed",
            "configured_count": 4,
            "killswitch_tripped": True,
        }

    out = resume.resume_and_protect(
        readiness_scan_fn=fake_readiness,
        activate_fn=fail_activate,
    )
    assert out["protected"] is False
    assert out["reason"] == "preflight_failed"
    disk = json.loads(hermetic_session["session_file"].read_text())
    assert disk["protected"] is False
    assert disk["active"] is False
    assert disk["purpose"] == "browsing"


def test_resume_and_protect_ignores_false_protected_when_activate_lies_with_zero(
    hermetic_session,
):
    """If activate returns protected but configured_count==0, still refuse."""
    resume.save_session(
        {"purpose": "browsing", "country": "CH", "location": "zurich"},
        configured_count=0,
    )

    # readiness reports >0 so activate runs; activate returns dishonest combo
    def fake_readiness():
        return {"configured_count": 1, "server_filled_count": 1, "pending_ip_count": 0}

    def dishonest_activate(**_k):
        return {
            "protected": True,
            "status": "protected",
            "configured_count": 0,  # contradiction
        }

    out = resume.resume_and_protect(
        readiness_scan_fn=fake_readiness,
        activate_fn=dishonest_activate,
    )
    assert out["protected"] is False
    disk = json.loads(hermetic_session["session_file"].read_text())
    assert disk["protected"] is False


def test_legacy_seed_does_not_import_protected(hermetic_session):
    hermetic_session["legacy"].write_text(
        json.dumps(
            {
                "purpose": "browsing",
                "country": "CH",
                "location": "zurich",
                "active": True,
                "protected": True,
            }
        )
    )
    # No industrial session yet
    assert not hermetic_session["session_file"].exists()
    s = resume.load_session(honest=True)
    assert s is not None
    assert s.get("from_legacy") is True
    assert s["purpose"] == "browsing"
    assert s["protected"] is False
    assert s["active"] is False


def test_resume_label_uses_selection(hermetic_session):
    s = {
        "purpose": "streaming",
        "country": "DE",
        "location": "frankfurt",
        "country_name": "Frankfurt",
    }
    label = resume.resume_label(s)
    assert "Resume" in label
    assert "Frankfurt" in label
    assert "Streaming" in label


def test_shell_resume_last_restores_selection_and_regates(hermetic_session, monkeypatch):
    """Shell path: apply selection then activate (preflight), never disk-protected."""
    # Import shell after paths configured
    from core_product.pcs_app_shell_v20260802 import PcsAppShell

    resume.save_session(
        {
            "purpose": "work",
            "country": "CA",
            "location": "vancouver",
            "tier": "pro",
            "catalog_ip_id": "CA-001",
            "protected": True,
            "active": True,
            "configured_count": 0,
        },
        configured_count=0,
        allow_protected_claim=False,
    )

    shell = PcsAppShell(tier="core")
    sel = shell.apply_resume_selection()
    assert sel["purpose"] == "work"
    assert sel["country"] == "CA"
    assert sel["tier"] == "pro"
    assert shell.tier == "pro"
    assert shell.current_purpose == "work"
    assert shell.selected_country == "CA"
    assert shell.phantomcloak_active is False  # never from disk

    # Stub activate to assert kwargs + fail-closed result
    captured = {}

    def fake_activate(purpose="browsing", country_code="CH", ip_id=None, **kwargs):
        captured["purpose"] = purpose
        captured["country_code"] = country_code
        captured["ip_id"] = ip_id
        return {
            "status": "blocked",
            "protected": False,
            "reason": "servers_not_configured",
            "configured_count": 0,
            "message": "blocked",
        }

    monkeypatch.setattr(shell, "activate", fake_activate)
    out = shell.resume_last()
    assert out["protected"] is False
    assert out["requires_preflight"] is True
    assert out["selection"]["purpose"] == "work"
    assert captured["purpose"] == "work"
    assert captured["country_code"] == "CA"
    assert captured["ip_id"] == "CA-001"
