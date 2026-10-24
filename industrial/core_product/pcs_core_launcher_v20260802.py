#!/usr/bin/env python3
"""PhantomCloak Core launcher — industrial tree (does not replace Suite launchers)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PCS_TIER", "core")
os.environ.setdefault("PHANTOMCLOAK_TIER", "core")  # Suite compat if bridged later

from shared.pcs_preflight_obfuscation_gate_v20260802 import activate_protected_session
from shared.pcs_pricing_engine_v20260802 import compute_core
from shared.pcs_feature_matrix_v20260802 import (
    for_tier,
    implemented_keys,
    protect_gate_truth,
    residential_truth,
    status_counts,
)
from shared.pcs_server_readiness_v20260802 import scan_readiness
from shared.pcs_tier_catalog_v20260802 import label


def main() -> int:
    tier = "core"
    print("===", label(tier), "===")
    price = compute_core()
    print(f"Price: ${price.monthly_usd}/mo · ${price.annual_usd}/yr (${price.annual_effective_monthly}/mo)")
    print("Feature status:", status_counts(tier))
    implemented = implemented_keys(tier)
    print(
        "Implemented features:",
        ", ".join(implemented[:12]),
        "..." if len(implemented) > 12 else "",
    )
    pg = protect_gate_truth()
    print("Protect gate (fail-closed):", pg["ok_for_protect_rule"])
    rt = residential_truth()
    print(
        "Residential truth: catalog_ui=",
        rt["catalog_ui"],
        "tunnel_service=",
        rt["tunnel_service"],
        "(overall",
        rt["status"] + ")",
    )

    rd = scan_readiness()
    print(
        "Server readiness (status/dashboard OK always):",
        f"configured_count={rd.get('configured_count')}",
        f"server_filled_count={rd.get('server_filled_count')}",
        f"pending_ip_count={rd.get('pending_ip_count')}",
    )

    # Demo activate with fail-closed gate (no real pf force without explicit env)
    # require_configured_servers=True: no inventing IPs; block protect if count==0
    def arm():
        print("[demo] killswitch arm requested (dry logic; set PCS_FORCE_PF=1 for real)")
        return {"armed": True, "dry": os.environ.get("PCS_FORCE_PF") != "1"}

    def trip(report):
        print("[demo] KILLSWITCH TRIP — preflight failed:", [c.name for c in report.failures()])

    result = activate_protected_session(
        tier=tier,
        tracker_vault_enabled=False,
        killswitch_arm_fn=arm,
        killswitch_trip_fn=trip,
        require_tunnel=False,
        require_configured_servers=True,
    )
    print(json.dumps(result, indent=2, default=str))
    if not result.get("protected"):
        print(
            "FAIL-CLOSED protect path:",
            result.get("reason"),
            "| configured_count=",
            result.get("configured_count"),
            "| server_filled_count=",
            result.get("server_filled_count"),
        )

    # Optionally hand off to Suite UI without modifying it
    suite = Path.home() / "Desktop" / "PhantomCloak Suite"
    if suite.is_dir() and os.environ.get("PCS_OPEN_SUITE_UI") == "1":
        os.environ["PHANTOMCLOAK_TIER"] = "core"
        os.environ["PHANTOMCLOAK_DEV"] = "1"
        os.chdir(suite)
        os.execv(sys.executable, [sys.executable, str(suite / "client" / "phantomcloak.py")])
    return 0 if result.get("protected") or result.get("status") == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
