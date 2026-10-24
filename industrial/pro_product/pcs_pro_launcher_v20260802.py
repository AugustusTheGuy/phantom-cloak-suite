#!/usr/bin/env python3
"""PhantomCloak Pro launcher — industrial tree (new path; Suite untouched)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PCS_TIER", "pro")
os.environ.setdefault("PHANTOMCLOAK_TIER", "pro")

from shared.pcs_preflight_obfuscation_gate_v20260802 import activate_protected_session
from shared.pcs_pricing_engine_v20260802 import compute_pro
from shared.pcs_feature_matrix_v20260802 import for_tier, status_counts
from shared.pcs_server_readiness_v20260802 import scan_readiness
from shared.pcs_tier_catalog_v20260802 import label


def main() -> int:
    tier = "pro"
    print("===", label(tier), "===")
    price = compute_pro()
    print(f"Price: ${price.monthly_usd}/mo · ${price.annual_usd}/yr (${price.annual_effective_monthly}/mo)")
    print("Feature status:", status_counts(tier))
    pro_only = [k for k, v in for_tier(tier).items() if v["tier"] == "pro"]
    print("Pro-layer features:", ", ".join(pro_only[:15]))

    rd = scan_readiness()
    print(
        "Server readiness:",
        f"configured_count={rd.get('configured_count')}",
        f"server_filled_count={rd.get('server_filled_count')}",
        f"pending_ip_count={rd.get('pending_ip_count')}",
    )

    def arm():
        print("[demo] Pro killswitch arm")
        return {"armed": True, "tier": "pro"}

    def trip(report):
        print("[demo] PRO KILLSWITCH TRIP:", [f.name for f in report.failures()])

    result = activate_protected_session(
        tier=tier,
        dpi_suspected=True,
        tracker_vault_enabled=True,
        tracker_vault_ok=True,
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
            "| server_filled_count=",
            result.get("server_filled_count"),
            "| pending_ip_count=",
            result.get("pending_ip_count"),
        )

    suite = Path.home() / "Desktop" / "PhantomCloak Suite"
    if suite.is_dir() and os.environ.get("PCS_OPEN_SUITE_UI") == "1":
        os.environ["PHANTOMCLOAK_TIER"] = "pro"
        os.environ["PHANTOMCLOAK_DEV"] = "1"
        os.chdir(suite)
        os.execv(sys.executable, [sys.executable, str(suite / "client" / "phantomcloak.py")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
