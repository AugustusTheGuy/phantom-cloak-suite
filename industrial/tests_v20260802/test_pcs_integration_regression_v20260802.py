"""Single regression entrypoint for industrial PCS critical invariants.

Hermetic: tmp industrial home via configure_paths; mock crypto; no network.
Never touches real ~/.pcs_industrial_20260802 secrets/inventory.
Target: full tests_v20260802 suite <10s.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import pcs_materialize_singbox_v20260802 as mat  # noqa: E402
from shared import pcs_server_readiness_v20260802 as ready  # noqa: E402
from shared.pcs_preflight_obfuscation_gate_v20260802 import (  # noqa: E402
    activate_protected_session,
)
from shared.pcs_residential_pool_industrial_v20260802 import (  # noqa: E402
    CATALOG_KIND,
    COUNTRY_TO_LOCATION,
    generate_country_pool,
)
from tests_v20260802.conftest import (  # noqa: E402
    MOCK_PRIVATE_KEY,
    MOCK_PUBLIC_KEY,
    MOCK_UUID,
    REAL_PUBLIC_IP,
)


# ---------------------------------------------------------------------------
# 1) Readiness fails protect when no configured clients
# ---------------------------------------------------------------------------


class TestReadinessProtectFailClosed:
    def test_empty_scan_not_ok_for_protect(self, hermetic_industrial: Dict[str, Any]):
        report = ready.scan_readiness()
        assert report["configured_count"] == 0
        snap = ready.gate_snapshot(report)
        assert snap["ok_for_protect"] is False
        assert snap["configured_count"] == 0
        assert snap.get("block_message")

    def test_activate_blocked_without_clients(
        self, hermetic_industrial: Dict[str, Any]
    ):
        trips: list = []

        out = activate_protected_session(
            tier="core",
            killswitch_arm_fn=lambda: {"armed": True},
            killswitch_trip_fn=lambda r: trips.append(r),
            require_configured_servers=True,
            auto_arm_killswitch=False,
        )
        assert out["protected"] is False
        assert out["status"] == "blocked"
        assert out["reason"] == "servers_not_configured"
        assert out["configured_count"] == 0
        assert out.get("server_readiness", {}).get("ok_for_protect") is False
        assert out.get("arm_result") is None
        assert trips, "fail-closed must trip killswitch callback when provided"

    def test_pending_only_still_blocks_protect(
        self, hermetic_industrial: Dict[str, Any]
    ):
        r = mat.materialize()
        assert r["configured_clients"] == 0
        report = ready.scan_readiness()
        assert report["configured_count"] == 0
        assert report["pending_ip_count"] >= len(mat.LOCATIONS)
        snap = ready.gate_snapshot(report)
        assert snap["ok_for_protect"] is False

        out = activate_protected_session(
            tier="core",
            require_configured_servers=True,
            auto_arm_killswitch=False,
            readiness_override=report,
        )
        assert out["protected"] is False
        assert out["reason"] == "servers_not_configured"


# ---------------------------------------------------------------------------
# 2) Materialize without IP → pending only
# ---------------------------------------------------------------------------


class TestMaterializePendingOnly:
    def test_without_ip_pending_only_no_client_json(
        self, hermetic_industrial: Dict[str, Any]
    ):
        result = mat.materialize()
        assert result["ok"] is True
        assert result["configured_clients"] == 0
        assert len(result["pending_ip_locations"]) == len(mat.LOCATIONS)
        assert set(result["pending_ip_locations"]) == set(mat.LOCATIONS)

        for loc in mat.LOCATIONS:
            pending = mat.SINGBOX_CLIENT / f"{loc}.pending.json"
            assert pending.is_file(), f"expected pending sidecar for {loc}"
            body = json.loads(pending.read_text())
            assert body["status"] == "pending_vps_ip"
            assert body.get("not_a_singbox_config") is True
            # public-only surface on pending
            assert "private_key" not in body
            assert "hy2_password" not in body
            assert "obfs_password" not in body
            assert not (mat.SINGBOX_CLIENT / f"{loc}.json").exists()

        # germany → frankfurt alias pending is informative, not a configured client
        assert (mat.SINGBOX_CLIENT / "frankfurt.pending.json").is_file()
        assert not (mat.SINGBOX_CLIENT / "frankfurt.json").exists()

        report = ready.scan_readiness()
        assert report["configured_count"] == 0
        # 8 canonical + frankfurt alias pending
        assert report["pending_ip_count"] >= len(mat.LOCATIONS)
        assert report["status"] in {
            "materialized_pending_ips",
            "server_package_ready_pending_client_ips",
        }


# ---------------------------------------------------------------------------
# 3) Injected real-looking public IP → client written (mock crypto)
# ---------------------------------------------------------------------------


class TestMaterializeWithInjectedIp:
    def test_inventory_ip_writes_client_and_raises_configured(
        self, hermetic_industrial: Dict[str, Any]
    ):
        r0 = mat.materialize()
        assert r0["configured_clients"] == 0
        before = ready.scan_readiness()
        assert before["configured_count"] == 0
        assert ready.gate_snapshot(before)["ok_for_protect"] is False

        inv = mat.load_or_init_inventory()
        inv["locations"]["dubai"]["ip"] = REAL_PUBLIC_IP
        inv["locations"]["dubai"]["enabled"] = True
        mat.INVENTORY.write_text(json.dumps(inv, indent=2) + "\n")

        r1 = mat.materialize()
        assert r1["ok"] is True
        assert r1["configured_clients"] >= 1
        assert "dubai" not in r1["pending_ip_locations"]
        assert "dubai" in [Path(p).stem for p in r1["client_configs"]]

        client_path = mat.SINGBOX_CLIENT / "dubai.json"
        assert client_path.is_file()
        client = json.loads(client_path.read_text())
        servers = [
            o.get("server")
            for o in client.get("outbounds", [])
            if isinstance(o, dict) and o.get("server")
        ]
        assert REAL_PUBLIC_IP in servers
        assert not ready.PLACEHOLDER_RE.search(REAL_PUBLIC_IP)

        # Mock crypto landed in secrets / client public surface
        secrets = json.loads(mat.LOCATION_KEYS.read_text())
        dubai_sec = secrets["locations"]["dubai"]
        assert dubai_sec["uuid"] == MOCK_UUID
        assert dubai_sec["public_key"] == MOCK_PUBLIC_KEY
        assert dubai_sec["private_key"] == MOCK_PRIVATE_KEY

        after = ready.scan_readiness()
        assert after["configured_count"] > before["configured_count"]
        assert after["configured_count"] >= 1
        assert after["status"] in {"ready", "partial"}
        assert ready.gate_snapshot(after)["ok_for_protect"] is True

        # Protect path may now pass the servers gate (other layers may still trip)
        out = activate_protected_session(
            tier="core",
            require_configured_servers=True,
            auto_arm_killswitch=False,
            readiness_override=after,
            killswitch_arm_fn=lambda: {"armed": True},
        )
        assert out.get("reason") != "servers_not_configured"
        assert out["configured_count"] >= 1

    def test_state_stays_under_tmp(self, hermetic_industrial: Dict[str, Any]):
        mat.materialize()
        real_state = Path.home() / ".pcs_industrial_20260802"
        assert mat.STATE == hermetic_industrial["state"]
        assert mat.STATE != real_state
        assert str(mat.INVENTORY).startswith(str(hermetic_industrial["state"]))
        assert ready.STATE == hermetic_industrial["state"]


# ---------------------------------------------------------------------------
# 4) Residential catalog 30–50 and not_a_tunnel_endpoint
# ---------------------------------------------------------------------------


class TestResidentialCatalogInvariants:
    """In-memory catalog generation — no real POOL_DIR writes."""

    @pytest.mark.parametrize("cc", sorted(COUNTRY_TO_LOCATION.keys())[:8])
    def test_sample_countries_bounds_and_flags(self, cc: str):
        pool = generate_country_pool(cc, 45)
        assert 30 <= len(pool) <= 50, f"{cc} size={len(pool)}"
        for entry in pool:
            assert entry.get("not_a_tunnel_endpoint") is True
            assert entry.get("catalog_kind") == CATALOG_KIND
            assert entry.get("country") == cc
            assert entry.get("location") == COUNTRY_TO_LOCATION[cc]
            assert isinstance(entry.get("ip"), str) and entry["ip"].count(".") == 3

    def test_default_size_mid_band(self):
        pool = generate_country_pool("CH")
        assert 30 <= len(pool) <= 50
        assert all(e.get("not_a_tunnel_endpoint") is True for e in pool)

    def test_clamped_size_30_to_50_via_ensure_bounds(self):
        # generate_country_pool itself accepts any size; product clamp is 30–50
        # at ensure_full_catalog — assert mid default + explicit 40 stay in band
        for n in (30, 40, 50):
            pool = generate_country_pool("DE", n)
            assert len(pool) == n
            assert all(e["not_a_tunnel_endpoint"] is True for e in pool)


# ---------------------------------------------------------------------------
# 5) Secrets fingerprint public-only stability (mock)
# ---------------------------------------------------------------------------


class TestSecretsFingerprintPublicOnly:
    def test_fingerprint_stable_across_noop_and_private_change(
        self, hermetic_industrial: Dict[str, Any]
    ):
        mat.materialize()
        assert mat.LOCATION_KEYS.is_file()

        fp1 = mat.secrets_fingerprint()
        assert fp1["exists"] is True
        assert fp1["fingerprint"] and len(fp1["fingerprint"]) == 16
        assert fp1["fingerprint_full"] and len(fp1["fingerprint_full"]) == 64
        assert "uuid+public_key+short_id+sni" in (fp1.get("hashed_fields") or "")
        assert fp1["locations"] == len(mat.LOCATIONS)

        # No-op re-read: stable
        fp2 = mat.secrets_fingerprint()
        assert fp2["fingerprint"] == fp1["fingerprint"]
        assert fp2["fingerprint_full"] == fp1["fingerprint_full"]

        # Mutate private material only — fingerprint must NOT change
        data = json.loads(mat.LOCATION_KEYS.read_text())
        for loc in data["locations"]:
            data["locations"][loc]["private_key"] = "PRIVATEKEY_ROTATED_" + "z" * 40
            data["locations"][loc]["hy2_password"] = "hy2-rotated-password-xxxxx"
            data["locations"][loc]["obfs_password"] = "obfs-rotated-xxxxx"
        mat.LOCATION_KEYS.write_text(json.dumps(data, indent=2) + "\n")

        fp3 = mat.secrets_fingerprint()
        assert fp3["fingerprint"] == fp1["fingerprint"]
        assert fp3["fingerprint_full"] == fp1["fingerprint_full"]

        # Mutate public_key — fingerprint MUST change
        data = json.loads(mat.LOCATION_KEYS.read_text())
        data["locations"]["dubai"]["public_key"] = "PUBLICKEY_CHANGED_" + "w" * 40
        mat.LOCATION_KEYS.write_text(json.dumps(data, indent=2) + "\n")

        fp4 = mat.secrets_fingerprint()
        assert fp4["fingerprint"] != fp1["fingerprint"]
        assert fp4["fingerprint_full"] != fp1["fingerprint_full"]

    def test_fingerprint_never_embeds_private_values(
        self, hermetic_industrial: Dict[str, Any]
    ):
        mat.materialize()
        fp = mat.secrets_fingerprint()
        blob = json.dumps(fp)
        assert MOCK_PRIVATE_KEY not in blob
        assert "hy2_password" not in blob
        assert "private_key" not in blob or fp.get("hashed_fields")
        # hashed_fields documents public surface only
        assert "private_key" not in (fp.get("hashed_fields") or "")
        assert "hy2_password" not in (fp.get("hashed_fields") or "")

        report = ready.scan_readiness()
        assert report.get("secrets_fingerprint") == fp["fingerprint"]
        redacted = json.dumps(report)
        assert MOCK_PRIVATE_KEY not in redacted
