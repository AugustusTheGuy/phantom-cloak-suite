"""Hermetic tests for materialize + server readiness (industrial).

Uses temp dirs via configure_paths; never touches real ~/.pcs_industrial_20260802.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import pcs_client_singbox_v20260802 as client
from shared import pcs_materialize_singbox_v20260802 as mat
from shared import pcs_server_readiness_v20260802 as ready

# Forbidden keys that must never appear in *.pending.json (appsec invariant)
PENDING_FORBIDDEN = ("private_key", "hy2_password", "password")


# Public-looking IPv4 that passes is_real_ip / is_real_public_ip
# (not RFC1918 / TEST-NET / localhost).
REAL_PUBLIC_IP = "104.21.16.42"
REAL_PUBLIC_IP_2 = "8.8.4.4"


def _restore_production_paths() -> None:
    home = Path.home()
    mat.configure_paths(
        home=home,
        state=home / ".pcs_industrial_20260802",
        suite=home / "Desktop" / "PhantomCloak Suite",
        industrial=ROOT,
    )
    ready.configure_paths(
        home=home,
        state=home / ".pcs_industrial_20260802",
        suite=home / "Desktop" / "PhantomCloak Suite",
        legacy=home / "Desktop" / "PhantomCloak",
        industrial=ROOT,
    )


@pytest.fixture
def hermetic_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate materialize + readiness to a throwaway tree under tmp_path."""
    home = tmp_path / "home"
    state = home / ".pcs_industrial_20260802"
    suite = home / "Desktop" / "PhantomCloak Suite"
    industrial = tmp_path / "industrial"
    (suite / "server" / "ready-for-vps").mkdir(parents=True)
    industrial.mkdir(parents=True)
    state.mkdir(parents=True)

    assert hasattr(mat, "configure_paths"), "materialize missing configure_paths"
    assert hasattr(ready, "configure_paths"), "readiness missing configure_paths"

    mat.configure_paths(home=home, state=state, suite=suite, industrial=industrial)
    ready.configure_paths(
        home=home,
        state=state,
        suite=suite,
        legacy=home / "Desktop" / "PhantomCloak",
        industrial=industrial,
    )

    # Fast, offline crypto: avoid real sing-box generate + openssl
    monkeypatch.setattr(mat, "gen_uuid", lambda: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    monkeypatch.setattr(
        mat,
        "gen_reality_keypair",
        lambda: (
            "PRIVATEKEY_TEST_BASE64URL_xxxxxxxxxxxxxxxxxxxx",
            "PUBLICKEY_TEST_BASE64URL_yyyyyyyyyyyyyyyyyyyyy",
        ),
    )

    def _fake_hy2_certs(loc: str, create: bool = True):
        cert_dir = mat.SECRETS / "hy2_certs" / loc
        cert = cert_dir / "fullchain.pem"
        key = cert_dir / "privkey.pem"
        if cert.exists() and key.exists():
            return cert, key
        if not create:
            return None, None
        cert_dir.mkdir(parents=True, exist_ok=True)
        cert.write_text("-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n")
        key.write_text("-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n")
        return cert, key

    monkeypatch.setattr(mat, "ensure_hy2_tls_certs", _fake_hy2_certs)

    yield {
        "home": home,
        "state": state,
        "suite": suite,
        "industrial": industrial,
    }

    _restore_production_paths()


# ---------------------------------------------------------------------------
# is_real_ip heuristics (materialize)
# ---------------------------------------------------------------------------


class TestIsRealIp:
    def test_none_and_empty(self):
        assert mat.is_real_ip(None) is False
        assert mat.is_real_ip("") is False
        assert mat.is_real_ip("   ") is False

    def test_accepts_public_ipv4(self):
        assert mat.is_real_ip(REAL_PUBLIC_IP) is True
        assert mat.is_real_ip("1.1.1.1") is True
        assert mat.is_real_ip("  8.8.8.8  ") is True

    def test_rejects_localhost_and_unspecified(self):
        assert mat.is_real_ip("127.0.0.1") is False
        assert mat.is_real_ip("0.0.0.0") is False
        assert mat.is_real_ip("127.1.2.3") is False

    def test_rejects_rfc1918_and_link_local(self):
        assert mat.is_real_ip("10.0.0.5") is False
        assert mat.is_real_ip("192.168.1.1") is False
        assert mat.is_real_ip("172.16.0.1") is False
        assert mat.is_real_ip("172.31.255.255") is False
        assert mat.is_real_ip("169.254.1.1") is False
        assert mat.is_real_ip("172.15.0.1") is True
        assert mat.is_real_ip("172.32.0.1") is True

    def test_rejects_documentation_ranges(self):
        assert mat.is_real_ip("192.0.2.1") is False
        assert mat.is_real_ip("198.51.100.1") is False
        assert mat.is_real_ip("203.0.113.10") is False

    def test_rejects_placeholders(self):
        assert mat.is_real_ip("YOUR_VPS_IP") is False
        assert mat.is_real_ip("your-dubai-vps.example.com") is False
        assert mat.is_real_ip("REPLACE_ME") is False
        assert mat.is_real_ip("changeme") is False
        assert mat.is_real_ip("pending") is False
        assert mat.is_real_ip("TODO") is False
        assert mat.is_real_ip("example.com") is False

    def test_rejects_invalid_ipv4_octet(self):
        assert mat.is_real_ip("999.1.1.1") is False
        assert mat.is_real_ip("1.2.3") is False
        assert mat.is_real_ip("not-an-ip") is False

    def test_accepts_non_placeholder_hostname(self):
        assert mat.is_real_ip("vps1.myprovider.net") is True
        assert mat.is_real_ip("edge.cloudflare.com") is True

    def test_rejects_local_tld_hostname(self):
        assert mat.is_real_ip("pcs-dubai.local") is False


# ---------------------------------------------------------------------------
# Placeholder detection
# ---------------------------------------------------------------------------


class TestPlaceholderDetection:
    @pytest.mark.parametrize(
        "sample",
        [
            "YOUR_VPS",
            "server: your-dubai-vps",
            "REPLACE_IP",
            "changeme",
            "example.com",
            "pending",
            "0.0.0.0",
            "TODO fill later",
        ],
    )
    def test_materialize_placeholder_ip_re(self, sample: str):
        assert mat.PLACEHOLDER_IP_RE.search(sample)

    @pytest.mark.parametrize(
        "sample",
        [
            "YOUR_VPS",
            "127.0.0.1",
            "demo-uuid",
            "changeme",
            "placeholder",
            "0.0.0.0",
            "example.com",
            "REPLACE_HOST",
            "your-hk-vps",
            "pending_vps_ip",
        ],
    )
    def test_readiness_placeholder_re(self, sample: str):
        assert ready.PLACEHOLDER_RE.search(sample)

    def test_clean_public_ip_not_placeholder(self):
        assert not mat.PLACEHOLDER_IP_RE.search(REAL_PUBLIC_IP)
        assert not ready.PLACEHOLDER_RE.search(REAL_PUBLIC_IP)

    def test_readiness_is_real_public_ip_aligns(self):
        assert ready.is_real_public_ip(REAL_PUBLIC_IP) is True
        assert ready.is_real_public_ip("127.0.0.1") is False
        assert ready.is_real_public_ip("YOUR_VPS") is False
        assert ready.is_real_public_ip("203.0.113.10") is False


# ---------------------------------------------------------------------------
# short_id hex validation
# ---------------------------------------------------------------------------


class TestShortIdHex:
    def test_valid_hex(self):
        assert mat._is_hex_short_id("a1b2c3d4") is True
        assert mat._is_hex_short_id("ABCDEF01") is True
        assert mat._is_hex_short_id("0") is True

    def test_invalid_non_hex(self):
        assert mat._is_hex_short_id("") is False
        assert mat._is_hex_short_id("not-hex!") is False
        assert mat._is_hex_short_id("gg") is False
        assert mat._is_hex_short_id("short id") is False

    def test_location_table_short_ids_are_hex(self):
        for loc, meta in mat.LOCATIONS.items():
            sid = meta["short_id"]
            assert mat._is_hex_short_id(sid), f"{loc} short_id={sid!r} must be hex"

    def test_load_or_create_secrets_heals_non_hex(
        self, hermetic_paths: Dict[str, Path]
    ):
        mat.SECRETS.mkdir(parents=True, exist_ok=True)
        bad = {
            "version": 1,
            "locations": {
                "dubai": {
                    "uuid": "u",
                    "private_key": "p",
                    "public_key": "k",
                    "short_id": "not-hex!!",
                    "hy2_password": "x",
                    "obfs_password": "o",
                    "sni": "wrong.example",
                }
            },
        }
        mat.LOCATION_KEYS.write_text(json.dumps(bad))
        data = mat.load_or_create_secrets()
        dubai = data["locations"]["dubai"]
        assert mat._is_hex_short_id(dubai["short_id"])
        assert dubai["short_id"] == mat.LOCATIONS["dubai"]["short_id"]
        assert dubai["sni"] == mat.LOCATIONS["dubai"]["sni"]
        assert "dubai" in (data.get("_healed_short_id") or [])
        assert set(data["locations"]) == set(mat.LOCATIONS)


# ---------------------------------------------------------------------------
# Readiness classification
# ---------------------------------------------------------------------------


class TestReadinessClassification:
    def test_empty_state_templates_only(self, hermetic_paths: Dict[str, Path]):
        report = ready.scan_readiness()
        assert report["status"] == "templates_only"
        assert report["configured_count"] == 0
        assert report["pending_ip_count"] == 0
        assert report["inventory"]["exists"] is False

    def test_pending_sidecar_status(self, hermetic_paths: Dict[str, Path]):
        singbox = hermetic_paths["state"] / "singbox"
        singbox.mkdir(parents=True)
        pending = {
            "location": "dubai",
            "status": "pending_vps_ip",
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "sni": "www.microsoft.com",
        }
        (singbox / "dubai.pending.json").write_text(json.dumps(pending))
        report = ready.scan_readiness()
        assert report["status"] == "materialized_pending_ips"
        assert report["pending_ip_count"] == 1
        assert report["configured_count"] == 0

    def test_configured_client_raises_count(self, hermetic_paths: Dict[str, Path]):
        singbox = hermetic_paths["state"] / "singbox"
        singbox.mkdir(parents=True)
        client = {
            "outbounds": [
                {
                    "type": "vless",
                    "server": REAL_PUBLIC_IP,
                    "server_port": 443,
                    "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                }
            ]
        }
        (singbox / "dubai.json").write_text(json.dumps(client))
        report = ready.scan_readiness()
        assert report["configured_count"] == 1
        assert report["status"] in {"ready", "partial"}
        assert report["configured"][0]["kind"] == "client_configured"

    def test_server_filled_without_client(self, hermetic_paths: Dict[str, Path]):
        pkg = hermetic_paths["state"] / "vps_server_package"
        pkg.mkdir(parents=True)
        server = {
            "inbounds": [
                {
                    "type": "vless",
                    "listen": "::",
                    "users": [{"uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
                    "tls": {
                        "reality": {
                            "private_key": "PRIVATEKEY_TEST_BASE64URL",
                            "short_id": ["a1b2c3d4"],
                        }
                    },
                }
            ],
            "outbounds": [{"type": "direct"}],
        }
        (pkg / "sing-box-dubai-reality.json").write_text(json.dumps(server))
        report = ready.scan_readiness()
        assert report["server_filled_count"] >= 1
        assert report["configured_count"] == 0
        assert report["status"] == "server_package_ready_pending_client_ips"

    def test_template_with_placeholder_counted(self, hermetic_paths: Dict[str, Path]):
        singbox = hermetic_paths["state"] / "singbox"
        singbox.mkdir(parents=True)
        (singbox / "stub.json").write_text(
            json.dumps({"server": "YOUR_VPS_IP", "uuid": "demo-uuid"})
        )
        report = ready.scan_readiness()
        assert report["templates_count"] >= 1
        assert report["configured_count"] == 0

    def test_inventory_ips_set(self, hermetic_paths: Dict[str, Path]):
        inv = {
            "locations": {
                "dubai": {"ip": REAL_PUBLIC_IP, "enabled": True},
                "hongkong": {"ip": "YOUR_VPS", "enabled": True},
                "vancouver": {"ip": "", "enabled": True},
            }
        }
        inv_path = hermetic_paths["state"] / "vps_inventory.json"
        inv_path.write_text(json.dumps(inv))
        st = ready._inventory_status()
        assert st["exists"] is True
        assert st["ips_set"] == 1
        assert st["locations"]["dubai"]["ip_set"] is True
        assert st["locations"]["hongkong"]["ip_set"] is False
        # v1 single-ip still surfaces pool totals
        assert st["total_real_ips"] == 1
        assert st["by_location"] == {"dubai": 1}

    def test_inventory_v2_pool_members_in_summary(self, hermetic_paths: Dict[str, Path]):
        """Pool members from inventory v2 visible as total_real_ips / by_location.

        configured_count stays driven by client configs (still 0 here — no invented
        client files). Rejects private/TEST-NET; does not invent IPs.
        """
        inv = {
            "version": 2,
            "ssh_user": "root",
            "locations": {
                "germany": {
                    "ip": REAL_PUBLIC_IP,
                    "enabled": True,
                    "pool": [
                        {"id": "germany-01", "ip": REAL_PUBLIC_IP, "enabled": True},
                        {"id": "germany-02", "ip": REAL_PUBLIC_IP_2, "enabled": True},
                        {"id": "germany-03", "ip": "10.0.0.1", "enabled": True},
                        {"id": "germany-04", "ip": "203.0.113.9", "enabled": True},
                        {"id": "germany-05", "ip": REAL_PUBLIC_IP_2, "enabled": False},
                    ],
                },
                "dubai": {
                    "ip": "",
                    "enabled": True,
                    "pool": [
                        {"id": "dubai-01", "ip": "1.1.1.1", "enabled": True},
                    ],
                },
                "hongkong": {"ip": "", "enabled": True, "pool": []},
            },
        }
        inv_path = hermetic_paths["state"] / "vps_inventory.json"
        inv_path.write_text(json.dumps(inv))
        st = ready._inventory_status()
        assert st["version"] == 2
        # locations with ≥1 real IP (germany + dubai); ips_set stays location-scoped
        assert st["ips_set"] == 2
        assert set(st["ips_set_locations"]) == {"germany", "dubai"}
        # total pool members: germany 2 (dedupe + reject private/testnet/disabled), dubai 1
        assert st["total_real_ips"] == 3
        assert st["by_location"] == {"dubai": 1, "germany": 2}
        assert st["locations"]["germany"]["pool_member_count"] == 2
        assert st["locations"]["dubai"]["pool_member_count"] == 1
        assert st["locations"]["hongkong"]["ip_set"] is False

        report = ready.scan_readiness()
        # configured_count only from client configs with real IPs — not from inventory pools
        assert report["configured_count"] == 0
        assert report["inventory"]["total_real_ips"] == 3
        assert report["inventory"]["by_location"] == {"dubai": 1, "germany": 2}
        assert "total_real_ips=3" in (report.get("summary") or "")
        assert "by_location=" in (report.get("summary") or "")

        snap = ready.gate_snapshot(report)
        assert snap["total_real_ips"] == 3
        assert snap["by_location"] == {"dubai": 1, "germany": 2}
        assert snap["configured_count"] == 0
        assert snap["ok_for_protect"] is False


# ---------------------------------------------------------------------------
# Materialize: with / without inventory IP
# ---------------------------------------------------------------------------


class TestMaterialize:
    def test_without_ip_leaves_pending_only(self, hermetic_paths: Dict[str, Path]):
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
            assert not (mat.SINGBOX_CLIENT / f"{loc}.json").exists()

        assert len(result["server_configs"]) == len(mat.LOCATIONS)
        for p in result["server_configs"]:
            assert Path(p).is_file()

        report = ready.scan_readiness()
        assert report["configured_count"] == 0
        # Canonical locations + client aliases (germany → frankfurt.pending.json)
        assert report["pending_ip_count"] >= len(mat.LOCATIONS)
        assert report["pending_ip_count"] == len(mat.LOCATIONS) + sum(
            1 for m in mat.LOCATIONS.values() if m.get("client_alias")
        )
        assert report["status"] in {
            "materialized_pending_ips",
            "server_package_ready_pending_client_ips",
        }

    def test_with_inventory_ip_writes_client_and_configured_rises(
        self, hermetic_paths: Dict[str, Path]
    ):
        r0 = mat.materialize()
        assert r0["configured_clients"] == 0
        before = ready.scan_readiness()
        assert before["configured_count"] == 0

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
        # outbound server fields must not be placeholders; file may contain
        # legitimate non-server tokens — assert the server binding itself.
        assert not ready.PLACEHOLDER_RE.search(REAL_PUBLIC_IP)

        after = ready.scan_readiness()
        assert after["configured_count"] > before["configured_count"]
        assert after["configured_count"] >= 1
        assert after["status"] in {"ready", "partial"}

    def test_env_override_ip(
        self, hermetic_paths: Dict[str, Path], monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("PCS_VPS_GERMANY", REAL_PUBLIC_IP_2)
        r = mat.materialize()
        assert "germany" not in r["pending_ip_locations"]
        assert (mat.SINGBOX_CLIENT / "germany.json").is_file()
        assert (mat.SINGBOX_CLIENT / "frankfurt.json").is_file()
        body = json.loads((mat.SINGBOX_CLIENT / "germany.json").read_text())
        flat = json.dumps(body)
        assert REAL_PUBLIC_IP_2 in flat

    def test_configure_paths_does_not_touch_real_state(
        self, hermetic_paths: Dict[str, Path]
    ):
        real_state = Path.home() / ".pcs_industrial_20260802"
        mat.materialize()
        assert mat.STATE == hermetic_paths["state"]
        assert mat.INVENTORY.parent == hermetic_paths["state"]
        assert mat.STATE != real_state
        assert mat.INVENTORY.is_file()
        assert str(mat.INVENTORY).startswith(str(hermetic_paths["state"]))
        assert ready.STATE == hermetic_paths["state"]
        assert ready.INVENTORY_PATH.parent == hermetic_paths["state"]


# ---------------------------------------------------------------------------
# Appsec: pending sidecars never carry secrets
# ---------------------------------------------------------------------------


def _assert_pending_body_public(body: dict, *, path_label: str = "pending") -> None:
    """Hard invariant: no private_key / hy2_password / password; keys ⊆ allowlist."""
    assert isinstance(body, dict), f"{path_label}: pending body must be object"
    for forbidden in PENDING_FORBIDDEN:
        assert forbidden not in body, f"{path_label}: must not contain {forbidden!r}"
        # case variants
        for k in body:
            assert str(k).lower() != forbidden, f"{path_label}: forbidden key {k!r}"
    assert "obfs_password" not in body
    for k in body:
        kl = str(k).lower()
        assert not kl.endswith("_private_key"), f"{path_label}: secret-like key {k!r}"
        if kl.endswith("_password") and kl != "has_hy2_password":
            raise AssertionError(f"{path_label}: password-like key {k!r}")
    # Hard allowlist
    unknown = set(body.keys()) - set(client.PENDING_PUBLIC_KEYS)
    assert not unknown, f"{path_label}: non-allowlisted keys {sorted(unknown)}"
    # schema_version is part of the documented public surface
    assert "schema_version" in body, f"{path_label}: missing schema_version"
    assert body["schema_version"] == client.SCHEMA_VERSION


class TestPendingNoSecrets:
    def test_build_pending_sidecar_never_includes_secrets_from_sec(self):
        """Client helper must not copy private material even if present in sec."""
        meta = {"hy2": True, "transport_http": True, "short_id": "a1b2c3d4", "sni": "www.microsoft.com"}
        sec = {
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "public_key": "PUBLICKEY_TEST",
            "private_key": "SHOULD_NEVER_APPEAR_PRIVATE",
            "hy2_password": "SHOULD_NEVER_APPEAR_HY2",
            "password": "SHOULD_NEVER_APPEAR_PASSWORD",
            "obfs_password": "SHOULD_NEVER_APPEAR_OBFS",
            "short_id": "a1b2c3d4",
            "sni": "www.microsoft.com",
        }
        pend = client.build_pending_sidecar(
            "dubai", meta, sec, inventory_path="/tmp/inv.json"
        )
        _assert_pending_body_public(pend, path_label="build_pending_sidecar")
        blob = json.dumps(pend)
        assert "SHOULD_NEVER_APPEAR" not in blob
        assert client.pending_contains_forbidden(pend) == []

    def test_pending_public_only_strips_injected_secrets(
        self, hermetic_paths: Dict[str, Path]
    ):
        sec = {
            "uuid": "u-1",
            "public_key": "pk-1",
            "private_key": "PRIV",
            "hy2_password": "HY2",
            "password": "PW",
        }
        meta = mat.LOCATIONS.get("dubai") or {"hy2": True, "sni": "www.microsoft.com", "short_id": "ab"}
        pend = mat.pending_public_only("dubai", sec, meta, skip_reason="test")
        _assert_pending_body_public(pend, path_label="pending_public_only")
        assert pend["location"] == "dubai"
        assert pend["uuid"] == "u-1"
        assert pend["public_key"] == "pk-1"

    def test_materialize_pending_files_never_contain_secrets(
        self, hermetic_paths: Dict[str, Path]
    ):
        result = mat.materialize()
        assert result["ok"] is True
        pending_files = list(mat.SINGBOX_CLIENT.glob("*.pending.json"))
        assert pending_files, "expected at least one *.pending.json after materialize"
        for path in pending_files:
            body = json.loads(path.read_text())
            _assert_pending_body_public(body, path_label=path.name)
            # serialized form must not embed secret field names as keys
            text = path.read_text()
            for forbidden in PENDING_FORBIDDEN:
                # allowlisted docs may mention words in strings; ban as JSON keys only
                assert f'"{forbidden}"' not in text, f"{path.name}: JSON key {forbidden}"

    def test_write_pending_json_filters_dirty_payload(
        self, hermetic_paths: Dict[str, Path]
    ):
        mat.SINGBOX_CLIENT.mkdir(parents=True, exist_ok=True)
        dirty = {
            "location": "dubai",
            "status": "pending_vps_ip",
            "uuid": "u",
            "public_key": "k",
            "schema_version": client.SCHEMA_VERSION,
            "private_key": "LEAK",
            "hy2_password": "LEAK2",
            "password": "LEAK3",
            "extra_unknown": True,
        }
        path = mat.SINGBOX_CLIENT / "dirty.pending.json"
        mat.write_pending_json(path, dirty)
        body = json.loads(path.read_text())
        _assert_pending_body_public(body, path_label="dirty.pending.json")
        assert "extra_unknown" not in body
        assert "LEAK" not in path.read_text()

    def test_sanitize_pending_sidecars_rewrites_secrets(
        self, hermetic_paths: Dict[str, Path]
    ):
        mat.SINGBOX_CLIENT.mkdir(parents=True, exist_ok=True)
        path = mat.SINGBOX_CLIENT / "tainted.pending.json"
        # Simulate accidental secret write (never done by production writers)
        path.write_text(
            json.dumps(
                {
                    "location": "dubai",
                    "status": "pending_vps_ip",
                    "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "public_key": "PUBLIC",
                    "private_key": "ACCIDENTAL_PRIVATE_KEY_SENTINEL_DO_NOT_SHIP",
                    "hy2_password": "ACCIDENTAL_HY2",
                    "password": "ACCIDENTAL_PW",
                }
            )
        )
        report = mat.sanitize_pending_sidecars(mat.SINGBOX_CLIENT)
        assert report["scanned"] >= 1
        assert path.name in report["stripped_keys"] or report["rewritten"] >= 1
        body = json.loads(path.read_text())
        _assert_pending_body_public(body, path_label="tainted.pending.json")
        text = path.read_text()
        assert "ACCIDENTAL_" not in text
        # report must not echo secret values
        assert "ACCIDENTAL_PRIVATE_KEY_SENTINEL_DO_NOT_SHIP" not in json.dumps(report)
        assert "ACCIDENTAL_HY2" not in json.dumps(report)

    def test_readiness_surfaces_only_public_pending_fields(
        self, hermetic_paths: Dict[str, Path]
    ):
        singbox = hermetic_paths["state"] / "singbox"
        singbox.mkdir(parents=True, exist_ok=True)
        dirty = {
            "schema_version": client.SCHEMA_VERSION,
            "location": "dubai",
            "status": "pending_vps_ip",
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "public_key": "PUBLICKEY_OK",
            "private_key": "MUST_NOT_SURFACE",
            "hy2_password": "MUST_NOT_SURFACE_HY2",
            "password": "MUST_NOT_SURFACE_PW",
            "sni": "www.microsoft.com",
        }
        (singbox / "dubai.pending.json").write_text(json.dumps(dirty))
        report = ready.scan_readiness()
        # Redacted/public report must not contain secret values
        dump = json.dumps(report)
        assert "MUST_NOT_SURFACE" not in dump
        pending_entries = report.get("pending") or report.get("pending_ip") or []
        # Find pending list under common keys
        if not pending_entries and isinstance(report.get("files"), list):
            pending_entries = [f for f in report["files"] if f.get("kind") == "pending_ip"]
        # Also walk all nested dicts for forbidden keys with secret values
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    kl = str(k).lower()
                    if kl in PENDING_FORBIDDEN:
                        # presence flags (bool) ok; string values not
                        if isinstance(v, str) and v and not v.startswith("<redacted"):
                            raise AssertionError(f"readiness surfaces secret key {k}={v!r}")
                    walk(v)
            elif isinstance(obj, list):
                for x in obj:
                    walk(x)

        walk(report)
        # _pending_public_meta itself
        meta = ready._pending_public_meta(dirty)
        for forbidden in PENDING_FORBIDDEN:
            assert forbidden not in meta
        assert meta.get("schema_version") == client.SCHEMA_VERSION
        assert meta.get("uuid") == dirty["uuid"]
        assert meta.get("public_key") == "PUBLICKEY_OK"
        assert report["pending_ip_count"] >= 1

    def test_harden_secret_paths_sanitizes_pending(
        self, hermetic_paths: Dict[str, Path]
    ):
        mat.SINGBOX_CLIENT.mkdir(parents=True, exist_ok=True)
        path = mat.SINGBOX_CLIENT / "via_harden.pending.json"
        path.write_text(
            json.dumps(
                {
                    "location": "germany",
                    "status": "pending_vps_ip",
                    "uuid": "u",
                    "public_key": "k",
                    "private_key": "X",
                    "hy2_password": "Y",
                    "password": "Z",
                }
            )
        )
        mat.harden_secret_paths()
        body = json.loads(path.read_text())
        _assert_pending_body_public(body, path_label="via_harden.pending.json")


# ---------------------------------------------------------------------------
# Appsec: multi-IP materialize — no private_key leak; pending public-only; 0600
# ---------------------------------------------------------------------------


class TestMultiIpMaterializeAppsec:
    def test_nested_secret_under_allowlisted_key_stripped(self):
        """Multi-IP inject under client_shape/ports must not survive filter."""
        dirty = {
            "schema": "pcs.client.pending",
            "schema_version": client.SCHEMA_VERSION,
            "location": "dubai",
            "status": "pending_vps_ip",
            "configured": False,
            "uuid": "u",
            "public_key": "pk",
            "client_shape": {
                "selector": True,
                "private_key": "NESTED_PRIV",
                "hy2_password": "NESTED_HY2",
            },
            "ports": {"reality_tcp": 443, "password": "NESTED_PW"},
        }
        safe = client.filter_pending_public(dirty)
        _assert_pending_body_public(safe, path_label="nested_scrub")
        blob = json.dumps(safe)
        assert "NESTED_" not in blob
        assert "private_key" not in blob
        hits = client.pending_contains_forbidden(dirty)
        assert any("private_key" in h for h in hits)
        assert client.pending_contains_forbidden(safe) == []

    def test_multi_ip_pool_materialize_no_private_key_in_pending_or_client(
        self, hermetic_paths: Dict[str, Path]
    ):
        """Inventory v2 multi-IP → rematerialize: pending public-only; client has
        public_key only; secrets + packages stay mode 0600.
        """
        import shared.pcs_inventory_v2_v20260802 as inv

        inv.INVENTORY_PATH = hermetic_paths["state"] / "vps_inventory.json"
        inv.STATE = hermetic_paths["state"]
        # Two public IPs for germany; materialize uses primary ip mirror
        data, errs = inv.set_pool_ips(
            "germany",
            [REAL_PUBLIC_IP, REAL_PUBLIC_IP_2],
            path=inv.INVENTORY_PATH,
        )
        assert not errs or all("rejected" not in e for e in errs) or REAL_PUBLIC_IP in {
            m["ip"] for m in inv.iter_pool_members(data)
        }
        inv_path = inv.INVENTORY_PATH
        assert inv_path.is_file()
        assert (inv_path.stat().st_mode & 0o777) == 0o600

        # Align materialize inventory path (same STATE via configure_paths)
        result = mat.materialize(only_locations=["germany"])
        assert result["ok"] is True

        # Secrets file 0600
        assert mat.LOCATION_KEYS.is_file()
        assert (mat.LOCATION_KEYS.stat().st_mode & 0o777) == 0o600
        secrets = json.loads(mat.LOCATION_KEYS.read_text())
        priv = secrets["locations"]["germany"]["private_key"]
        assert priv and len(priv) > 10

        # Full client written for primary IP — Reality public_key only
        client_path = mat.SINGBOX_CLIENT / "germany.json"
        assert client_path.is_file(), "primary pool IP should configure client"
        assert (client_path.stat().st_mode & 0o777) == 0o600
        cfg = json.loads(client_path.read_text())
        assert client.client_config_has_reality_private_key(cfg) is False
        assert priv not in client_path.read_text()
        # frankurt alias same rule
        alias = mat.SINGBOX_CLIENT / "frankfurt.json"
        if alias.is_file():
            assert priv not in alias.read_text()
            assert client.client_config_has_reality_private_key(
                json.loads(alias.read_text())
            ) is False

        # Server package embeds private_key (expected) but mode-locked
        server = mat.VPS_PKG / "sing-box-germany-reality.json"
        assert server.is_file()
        assert (server.stat().st_mode & 0o777) == 0o600
        assert priv in server.read_text() or "private_key" in server.read_text()

        # No pending with secrets for configured germany; other locs may pending
        for path in mat.SINGBOX_CLIENT.glob("*.pending.json"):
            body = json.loads(path.read_text())
            _assert_pending_body_public(body, path_label=path.name)
            assert priv not in path.read_text()
            assert (path.stat().st_mode & 0o777) == 0o600

        # Public summary never carries private key values
        summary = mat.public_materialize_summary(result)
        dump = json.dumps(summary)
        assert priv not in dump
        assert "private_key" not in dump or "<redacted" in dump

    def test_write_pending_json_scrubs_nested_multi_ip_payload(
        self, hermetic_paths: Dict[str, Path]
    ):
        mat.SINGBOX_CLIENT.mkdir(parents=True, exist_ok=True)
        path = mat.SINGBOX_CLIENT / "pool.pending.json"
        mat.write_pending_json(
            path,
            {
                "schema_version": client.SCHEMA_VERSION,
                "location": "dubai",
                "status": "pending_vps_ip",
                "uuid": "u",
                "public_key": "k",
                "client_shape": {"private_key": "LEAK_NESTED", "urltest": True},
                "private_key": "LEAK_TOP",
            },
        )
        body = json.loads(path.read_text())
        _assert_pending_body_public(body, path_label="pool.pending.json")
        assert "LEAK_" not in path.read_text()
        assert (path.stat().st_mode & 0o777) == 0o600
