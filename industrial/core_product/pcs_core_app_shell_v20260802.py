#!/usr/bin/env python3
"""Core app shell: resume session, auto killswitch on activate, Argon2 accounts, readiness.

Does not modify Suite/Core original launchers.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PCS_TIER", "core")

from shared.pcs_preflight_obfuscation_gate_v20260802 import activate_protected_session
from shared.pcs_session_resume_v20260802 import (
    extract_selection,
    resume_payload,
    save_session,
)
from shared.pcs_server_readiness_v20260802 import scan_readiness
from shared.pcs_security_audit_engine_v20260802 import run_full_audit
from shared.pcs_killswitch_industrial_v20260802 import IndustrialKillSwitch
from shared.pcs_pricing_engine_v20260802 import compute_core


def main() -> int:
    print("=== PhantomCloak Core · industrial shell ===")
    print("Honest copy: protections active · verify recommended (never 'undetectable')")
    price = compute_core()
    print(f"Price ${price.monthly_usd}/mo · ${price.annual_usd}/yr")

    # Resume restores selection only — never protected from disk
    resume = resume_payload()
    selection = resume.get("selection") or extract_selection(resume.get("session"))
    print("One-tap resume:", resume["label"], "| available=", resume["available"])
    print(
        "  selection:",
        {
            k: selection.get(k)
            for k in ("purpose", "country", "location", "tier", "catalog_ip_id")
            if selection.get(k) is not None
        },
    )
    print("  honesty: protected from disk =", resume.get("protected"), "| requires_preflight=", resume.get("requires_preflight"))

    readiness = scan_readiness()
    print("Server readiness:", readiness["summary"])
    print(
        "  configured_count=",
        readiness.get("configured_count"),
        " server_filled_count=",
        readiness.get("server_filled_count"),
        " pending_ip_count=",
        readiness.get("pending_ip_count"),
    )
    print("  HOWTO:", readiness.get("howto_path") or readiness.get("industrial_howto"))
    print("  inventory:", (readiness.get("inventory") or {}).get("path"))

    audit = run_full_audit(include_suite_readonly=True)
    print(f"Security score chip: {audit['score']} ({audit['grade']})")

    # Re-run readiness (inside gate) + preflight before any protected claim
    # Fail-closed: configured_count==0 → blocked (no false "protected")
    tier = selection.get("tier") or "core"
    print("Activate → server-readiness gate + killswitch auto-on + preflight…")
    print(f"  using restored tier={tier} purpose={selection.get('purpose')} country={selection.get('country')}")
    result = activate_protected_session(
        tier=tier if tier in ("core", "pro") else "core",
        auto_arm_killswitch=True,
        force_pf_apply=os.environ.get("PCS_FORCE_PF") == "1",
        tracker_vault_enabled=False,
        require_tunnel=False,
        require_configured_servers=True,
    )
    keys = (
        "status",
        "protected",
        "reason",
        "message",
        "configured_count",
        "server_filled_count",
        "pending_ip_count",
        "obfuscation",
        "next_step",
        "howto_path",
        "inventory_path",
    )
    print(json.dumps({k: result.get(k) for k in keys if k in result or result.get(k) is not None}, indent=2))
    if result.get("pending") is not None:
        print("pending (sample):", json.dumps(result.get("pending")[:3], indent=2, default=str))
    if result.get("arm_result"):
        print("Killswitch conf path:", result["arm_result"].get("path") or IndustrialKillSwitch().conf_location())

    cfg = int(result.get("configured_count") or 0)
    live_protected = bool(result.get("protected")) and cfg > 0
    if not live_protected:
        print(
            "FAIL-CLOSED: protected browsing refused. "
            "Dashboard/status/config/wizard still OK — fill VPS inventory first."
        )

    # Persist selection for one-tap resume; protected only after live gate + cfg>0
    save_session(
        {
            **selection,
            "purpose": selection.get("purpose") or "browsing",
            "country": selection.get("country") or "CH",
            "location": selection.get("location") or "zurich",
            "country_name": selection.get("country_name")
            or (selection.get("location") or "zurich").replace("_", " ").title(),
            "tier": tier if tier in ("core", "pro") else "core",
            "catalog_ip_id": selection.get("catalog_ip_id"),
            "active": live_protected,
            "protected": live_protected,
            "killswitch": bool(live_protected or result.get("killswitch_tripped")),
            "configured_count": cfg,
            "server_filled_count": result.get("server_filled_count"),
            "pending_ip_count": result.get("pending_ip_count"),
            "preflight": result.get("report"),
            "reason": result.get("reason"),
        },
        configured_count=cfg,
        protected=live_protected,
        allow_protected_claim=live_protected,
    )
    print("Saved industrial session for resume label:", resume_payload()["label"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
