"""Client multi-IP pool outbounds: reality-out-1..N + urltest/selector.

Hermetic. Uses public test IPs in memory only — never writes fake inventory.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

import pytest

from shared import pcs_client_singbox_v20260802 as client
from shared import pcs_materialize_singbox_v20260802 as mat

# Public DNS anycast IPs — valid public IPv4 for dry shape / sing-box check only.
# Not production VPS inventory; never written to disk by these tests.
PUBLIC_TEST_IPS = ["1.1.1.1", "8.8.8.8", "8.8.4.4"]
REAL_PUBLIC_IP = "104.21.16.42"

DEMO_SEC: Dict[str, Any] = {
    "uuid": "00000000-0000-4000-8000-000000000001",
    "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
    "short_id": "a1b2c3d4",
    "sni": "www.microsoft.com",
    "hy2_password": "p" * 32,
    "obfs_password": "obfs",
}


def _tags(cfg: Dict[str, Any]) -> List[str]:
    return [o.get("tag") for o in cfg.get("outbounds") or [] if isinstance(o, dict)]


def _by_tag(cfg: Dict[str, Any], tag: str) -> Dict[str, Any]:
    for o in cfg.get("outbounds") or []:
        if isinstance(o, dict) and o.get("tag") == tag:
            return o
    return {}


def _servers(cfg: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for o in cfg.get("outbounds") or []:
        if isinstance(o, dict) and o.get("server"):
            out.append(str(o["server"]))
    return out


class TestSingleIpShapeUnchanged:
    """One IP keeps classic tags: reality-out (+ hysteria-out), no numeric suffix."""

    def test_single_ip_tags_classic(self):
        cfg = client.build_client_config(
            "dubai",
            {"hy2": True, "transport_http": True, "obfs": "x"},
            DEMO_SEC,
            REAL_PUBLIC_IP,
        )
        tags = _tags(cfg)
        assert "reality-out" in tags
        assert "hysteria-out" in tags
        assert "reality-out-1" not in tags
        assert "hysteria-out-1" not in tags
        assert _by_tag(cfg, "reality-out").get("server") == REAL_PUBLIC_IP
        assert _by_tag(cfg, "proxy").get("type") == "selector"
        # Reality + Hy2 → urltest auto
        assert _by_tag(cfg, "auto").get("type") == "urltest"
        rep = client.validate_client_config_schema(cfg, require_real_server=True)
        assert rep["ok"] is True, rep.get("errors")

    def test_single_ip_via_server_ips_list_len_one(self):
        cfg = client.build_client_config(
            "germany",
            {"hy2": False, "transport_http": False, "obfs": "x"},
            DEMO_SEC,
            server_ips=[REAL_PUBLIC_IP],
        )
        tags = _tags(cfg)
        assert "reality-out" in tags
        assert "reality-out-1" not in tags
        # Default: enable_urltest None and one proxy tag → no urltest
        assert _by_tag(cfg, "auto") == {}
        assert _by_tag(cfg, "proxy").get("default") == "reality-out"


class TestMultiPoolOutbounds:
    def test_multi_ip_reality_out_1_to_n_and_urltest_selector(self):
        cfg = client.build_client_config(
            "germany",
            {"hy2": False, "transport_http": False, "obfs": "x"},
            DEMO_SEC,
            server_ips=PUBLIC_TEST_IPS,
        )
        tags = _tags(cfg)
        n = len(PUBLIC_TEST_IPS)
        for i in range(1, n + 1):
            assert f"reality-out-{i}" in tags, tags
        assert "reality-out" not in tags  # multi uses numbered tags only
        assert _by_tag(cfg, "proxy").get("type") == "selector"
        assert _by_tag(cfg, "auto").get("type") == "urltest"
        assert _by_tag(cfg, "proxy").get("default") == "auto"
        ut = _by_tag(cfg, "auto")
        assert ut.get("outbounds") == [f"reality-out-{i}" for i in range(1, n + 1)]
        sel = _by_tag(cfg, "proxy").get("outbounds") or []
        assert "auto" in sel
        assert "direct" in sel
        for i, ip in enumerate(PUBLIC_TEST_IPS, start=1):
            assert _by_tag(cfg, f"reality-out-{i}").get("server") == ip
        assert set(_servers(cfg)) == set(PUBLIC_TEST_IPS)

    def test_multi_ip_with_hy2_numbered_pairs(self):
        cfg = client.build_client_config(
            "vancouver",
            {"hy2": True, "transport_http": False, "obfs": "x"},
            DEMO_SEC,
            server_ips=PUBLIC_TEST_IPS[:2],
        )
        tags = _tags(cfg)
        assert "reality-out-1" in tags and "reality-out-2" in tags
        assert "hysteria-out-1" in tags and "hysteria-out-2" in tags
        assert "hysteria-out" not in tags
        ut_members = _by_tag(cfg, "auto").get("outbounds") or []
        assert "reality-out-1" in ut_members
        assert "hysteria-out-2" in ut_members

    def test_normalize_rejects_placeholder(self):
        with pytest.raises(ValueError, match="placeholder"):
            client.normalize_server_ips(server_ips=["YOUR_VPS_IP", "1.1.1.1"])

    def test_normalize_dedupes(self):
        ips = client.normalize_server_ips(server_ips=["1.1.1.1", "1.1.1.1", "8.8.8.8"])
        assert ips == ["1.1.1.1", "8.8.8.8"]


class TestSingboxCheckMultiOutboundDry:
    """sing-box check must pass for multi-outbound dry config (memory only)."""

    @pytest.mark.skipif(not shutil.which("sing-box"), reason="sing-box not in PATH")
    def test_multi_outbound_singbox_check_passes(self):
        cfg = client.build_client_config(
            "germany",
            {"hy2": False, "transport_http": False, "obfs": "x"},
            DEMO_SEC,
            server_ips=PUBLIC_TEST_IPS,
        )
        # Pure in-memory: validate + sing-box check (temp file only inside helper)
        rep = client.validate_client_config_schema(
            cfg, require_real_server=True, run_singbox_check=True
        )
        assert rep["ok"] is True, rep
        sb = rep.get("singbox_check") or {}
        assert sb.get("skipped") is not True
        assert sb.get("ok") is True, sb

    @pytest.mark.skipif(not shutil.which("sing-box"), reason="sing-box not in PATH")
    def test_multi_outbound_with_hy2_singbox_check(self):
        cfg = client.build_client_config(
            "dubai",
            {"hy2": True, "transport_http": True, "obfs": "x"},
            DEMO_SEC,
            server_ips=PUBLIC_TEST_IPS[:2],
        )
        rep = client.validate_client_config_schema(
            cfg, require_real_server=True, run_singbox_check=True
        )
        assert rep["ok"] is True, rep.get("errors")
        assert (rep.get("singbox_check") or {}).get("ok") is True

    @pytest.mark.skipif(not shutil.which("sing-box"), reason="sing-box not in PATH")
    def test_single_ip_still_passes_singbox_check(self):
        cfg = client.build_client_config(
            "dubai",
            {"hy2": True, "transport_http": True, "obfs": "x"},
            DEMO_SEC,
            REAL_PUBLIC_IP,
        )
        rep = client.validate_client_config_schema(
            cfg, require_real_server=True, run_singbox_check=True
        )
        assert rep["ok"] is True, rep.get("errors")


class TestLocationPoolIpsHelper:
    def test_pool_members_ordered(self):
        inv = {
            "ip": "1.1.1.1",
            "enabled": True,
            "pool": [
                {"id": "g-01", "ip": "1.1.1.1", "enabled": True},
                {"id": "g-02", "ip": "8.8.8.8", "enabled": True},
                {"id": "g-03", "ip": "10.0.0.1", "enabled": True},  # private rejected
                {"id": "g-04", "ip": "8.8.4.4", "enabled": False},
            ],
        }
        ips = mat.location_pool_ips(inv)
        assert ips == ["1.1.1.1", "8.8.8.8"]

    def test_legacy_single_ip(self):
        assert mat.location_pool_ips({"ip": REAL_PUBLIC_IP, "enabled": True}) == [
            REAL_PUBLIC_IP
        ]
        assert mat.location_pool_ips({"ip": "", "pool": []}) == []


class TestMaterializeMultiPool:
    """Materialize writes multi-outbound client when inventory pool has 2+ IPs."""

    def test_materialize_multi_pool_client_outbounds(
        self, hermetic_industrial: Dict[str, Any]
    ):
        inv = mat.load_or_init_inventory()
        inv["locations"]["germany"] = {
            "ip": PUBLIC_TEST_IPS[0],
            "enabled": True,
            "ssh_user": "root",
            "pool": [
                {"id": "germany-01", "ip": PUBLIC_TEST_IPS[0], "enabled": True, "tier": "primary"},
                {"id": "germany-02", "ip": PUBLIC_TEST_IPS[1], "enabled": True, "tier": "rotate"},
                {"id": "germany-03", "ip": PUBLIC_TEST_IPS[2], "enabled": True, "tier": "rotate"},
            ],
        }
        mat.INVENTORY.write_text(json.dumps(inv, indent=2) + "\n")

        result = mat.materialize(only_locations=["germany"])
        assert result["ok"] is True
        assert "germany" not in result.get("pending_ip_locations", [])

        reports = {
            r["location"]: r for r in (result.get("client_schema_reports") or [])
        }
        assert "germany" in reports
        assert reports["germany"].get("multi_pool") is True
        assert reports["germany"].get("pool_size") == 3
        assert reports["germany"].get("urltest") is True

        client_path = mat.SINGBOX_CLIENT / "germany.json"
        assert client_path.is_file()
        body = json.loads(client_path.read_text())
        tags = _tags(body)
        assert "reality-out-1" in tags
        assert "reality-out-2" in tags
        assert "reality-out-3" in tags
        assert "reality-out" not in tags
        assert _by_tag(body, "auto").get("type") == "urltest"
        assert set(_servers(body)) == set(PUBLIC_TEST_IPS)
        # Alias frankfurt should match
        frank = mat.SINGBOX_CLIENT / "frankfurt.json"
        assert frank.is_file()
        assert json.loads(frank.read_text()) == body

    def test_materialize_single_ip_still_classic(
        self, hermetic_industrial: Dict[str, Any]
    ):
        inv = mat.load_or_init_inventory()
        inv["locations"]["dubai"] = {
            "ip": REAL_PUBLIC_IP,
            "enabled": True,
            "pool": [
                {"id": "dubai-01", "ip": REAL_PUBLIC_IP, "enabled": True, "tier": "primary"},
            ],
        }
        mat.INVENTORY.write_text(json.dumps(inv, indent=2) + "\n")
        result = mat.materialize(only_locations=["dubai"])
        assert result["ok"] is True
        body = json.loads((mat.SINGBOX_CLIENT / "dubai.json").read_text())
        tags = _tags(body)
        assert "reality-out" in tags
        assert "reality-out-1" not in tags
        reports = {
            r["location"]: r for r in (result.get("client_schema_reports") or [])
        }
        assert reports["dubai"].get("multi_pool") is False
        assert reports["dubai"].get("pool_size") == 1
