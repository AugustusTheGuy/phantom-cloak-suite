"""CLI exit-code + immutability tests for pcs_materialize_singbox (industrial).

Path injection via configure_paths; never touches real ~/.pcs_industrial_20260802.
Covers: --check-only, --rotate-keys conflict, --json, --location, fingerprint stability.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared import pcs_materialize_singbox_v20260802 as mat

REAL_PUBLIC_IP = "104.21.16.42"


def _restore_production_paths() -> None:
    home = Path.home()
    mat.configure_paths(
        home=home,
        state=home / ".pcs_industrial_20260802",
        suite=home / "Desktop" / "PhantomCloak Suite",
        industrial=ROOT,
    )


def _tree_snapshot(root: Path) -> Dict[str, Tuple[int, int]]:
    """path -> (size, mtime_ns) relative to root. Empty if root missing."""
    if not root.exists():
        return {}
    out: Dict[str, Tuple[int, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


def _all_paths_under(root: Path) -> Set[str]:
    if not root.exists():
        return set()
    return {str(p.relative_to(root)) for p in root.rglob("*")}


@pytest.fixture
def hermetic_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate CLI to tmp_path; fake crypto so tests stay offline."""
    home = tmp_path / "home"
    state = home / ".pcs_industrial_20260802"
    suite = home / "Desktop" / "PhantomCloak Suite"
    industrial = tmp_path / "industrial"
    (suite / "server" / "ready-for-vps").mkdir(parents=True)
    industrial.mkdir(parents=True)
    state.mkdir(parents=True)

    mat.configure_paths(home=home, state=state, suite=suite, industrial=industrial)

    monkeypatch.setattr(mat, "gen_uuid", lambda: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    _kp_counter = {"n": 0}

    def _fake_kp():
        _kp_counter["n"] += 1
        n = _kp_counter["n"]
        return (
            f"PRIVATEKEY_TEST_BASE64URL_{n:04d}_xxxxxxxxxxxxxxxx",
            f"PUBLICKEY_TEST_BASE64URL_{n:04d}_yyyyyyyyyyyyyyyyy",
        )

    monkeypatch.setattr(mat, "gen_reality_keypair", _fake_kp)

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
        "kp_counter": _kp_counter,
    }

    _restore_production_paths()


def _run_main(argv: List[str], capsys) -> Tuple[int, Dict[str, Any], str, str]:
    code = mat.main(argv)
    captured = capsys.readouterr()
    body = captured.out.strip()
    data: Dict[str, Any] = {}
    if body:
        data = json.loads(body)
    return code, data, captured.out, captured.err


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestCliExitCodes:
    def test_check_only_empty_state_exit_pending(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, err = _run_main(["--check-only", "--json"], capsys)
        assert code == mat.EXIT_PENDING
        assert data["ok"] is True
        assert data["mode"] == "check-only"
        assert data.get("mutated") is False
        assert len(data["pending_ip_locations"]) == len(mat.LOCATIONS)
        assert data["counts"]["pending_ip"] == len(mat.LOCATIONS)
        assert data["secrets_fingerprint"] is None
        # --json suppresses operator banner
        assert "=== PCS materialize" not in err

    def test_check_only_human_banner_on_stderr(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, err = _run_main(["--check-only"], capsys)
        assert code == mat.EXIT_PENDING
        assert "=== PCS materialize (check-only) ===" in err
        assert "secrets_fingerprint:" in err
        assert "pending_ip_locations:" in err
        assert "private_key" not in _out.lower()
        assert "PRIVATEKEY" not in _out

    def test_materialize_pending_exit_2(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, err = _run_main(["--json"], capsys)
        assert code == mat.EXIT_PENDING
        assert data["mode"] == "materialize"
        assert data["configured_clients"] == 0
        assert data["counts"]["pending_ip"] == len(mat.LOCATIONS)
        assert data["secrets_fingerprint"]
        assert data["keys_preserved"] is True
        assert data["keys_rotated"] == []
        assert "=== PCS materialize" not in err

    def test_materialize_all_ready_exit_0(
        self, hermetic_cli: Dict[str, Path], capsys, monkeypatch: pytest.MonkeyPatch
    ):
        for loc in mat.LOCATIONS:
            monkeypatch.setenv(f"PCS_VPS_{loc.upper()}", REAL_PUBLIC_IP)
        code, data, _out, _err = _run_main(
            ["--force-inventory-env", "--json"], capsys
        )
        assert code == mat.EXIT_OK
        assert data["ok"] is True
        assert data["counts"]["pending_ip"] == 0
        assert data["pending_ip_locations"] == []
        assert data["configured_clients"] >= len(mat.LOCATIONS)

    def test_unknown_location_exit_1(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, _err = _run_main(
            ["--location", "atlantis", "--json"], capsys
        )
        assert code == mat.EXIT_HARD
        assert data["ok"] is False
        assert "unknown location" in data["error"]

    def test_check_only_plus_rotate_keys_exit_1(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, _err = _run_main(
            ["--check-only", "--rotate-keys", "--json"], capsys
        )
        assert code == mat.EXIT_HARD
        assert data["ok"] is False
        assert "--check-only" in data["error"]
        assert "--rotate-keys" in data["error"]

    def test_location_scope_pending(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        code, data, _out, _err = _run_main(
            ["--location", "dubai", "--json"], capsys
        )
        assert code == mat.EXIT_PENDING
        assert data["locations_requested"] == ["dubai"]
        assert data["pending_ip_locations"] == ["dubai"]
        assert data["counts"]["locations_requested"] == 1


# ---------------------------------------------------------------------------
# --check-only immutability
# ---------------------------------------------------------------------------


class TestCheckOnlyImmutable:
    def test_check_only_creates_nothing_on_empty_state(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        state = hermetic_cli["state"]
        before_paths = _all_paths_under(state)
        before_snap = _tree_snapshot(state)

        code, data, _out, _err = _run_main(["--check-only", "--json"], capsys)
        assert code == mat.EXIT_PENDING
        assert data.get("mutated") is False

        after_paths = _all_paths_under(state)
        after_snap = _tree_snapshot(state)
        assert after_paths == before_paths
        assert after_snap == before_snap
        assert not mat.LOCATION_KEYS.exists()
        assert not mat.INVENTORY.exists()
        assert not mat.META.exists()
        assert not mat.VPS_PKG.exists()

    def test_check_only_does_not_mutate_after_materialize(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        # Seed state via apply
        code0, data0, _, _ = _run_main(["--json"], capsys)
        assert code0 == mat.EXIT_PENDING
        fp0 = data0["secrets_fingerprint"]
        snap = _tree_snapshot(hermetic_cli["state"])

        code1, data1, _, _ = _run_main(["--check-only", "--json"], capsys)
        assert code1 == mat.EXIT_PENDING
        assert data1["secrets_fingerprint"] == fp0
        assert data1.get("mutated") is False
        assert _tree_snapshot(hermetic_cli["state"]) == snap

    def test_check_only_force_env_does_not_persist(
        self,
        hermetic_cli: Dict[str, Path],
        capsys,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("PCS_VPS_DUBAI", REAL_PUBLIC_IP)
        assert not mat.INVENTORY.exists()
        code, data, _, _ = _run_main(
            ["--check-only", "--force-inventory-env", "--json"], capsys
        )
        assert code == mat.EXIT_PENDING  # other locs still pending
        assert "dubai" in data.get("ready_locations", [])
        assert "dubai" in (data.get("env_would_persist") or data.get("env_applied_memory") or [])
        assert not mat.INVENTORY.exists()


# ---------------------------------------------------------------------------
# Fingerprint stability + rotate
# ---------------------------------------------------------------------------


class TestFingerprintAndRotate:
    def test_fingerprint_stable_without_rotate(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        c1, d1, _, _ = _run_main(["--json"], capsys)
        c2, d2, _, _ = _run_main(["--json"], capsys)
        assert c1 == mat.EXIT_PENDING
        assert c2 == mat.EXIT_PENDING
        assert d1["secrets_fingerprint"]
        assert d1["secrets_fingerprint"] == d2["secrets_fingerprint"]
        assert d1["secrets_fingerprint_full"] == d2["secrets_fingerprint_full"]
        assert d2["keys_preserved"] is True
        assert d2["keys_rotated"] == []

        # Public key material on disk unchanged
        sec1 = json.loads(mat.LOCATION_KEYS.read_text())
        pubs1 = {
            loc: e.get("public_key")
            for loc, e in sec1["locations"].items()
        }
        c3, d3, _, _ = _run_main(["--json"], capsys)
        sec3 = json.loads(mat.LOCATION_KEYS.read_text())
        pubs3 = {
            loc: e.get("public_key")
            for loc, e in sec3["locations"].items()
        }
        assert pubs1 == pubs3
        assert d3["secrets_fingerprint"] == d1["secrets_fingerprint"]

    def test_rotate_keys_changes_fingerprint_and_rematerializes(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        c1, d1, _, _ = _run_main(["--location", "dubai", "--json"], capsys)
        assert c1 == mat.EXIT_PENDING
        fp1 = d1["secrets_fingerprint"]
        sec_before = json.loads(mat.LOCATION_KEYS.read_text())
        pub_before = sec_before["locations"]["dubai"]["public_key"]
        server_path = mat.VPS_PKG / "sing-box-dubai-reality.json"
        assert server_path.is_file()
        server_before = json.loads(server_path.read_text())
        priv_before = server_before["inbounds"][0]["tls"]["reality"]["private_key"]

        c2, d2, out2, _ = _run_main(
            ["--location", "dubai", "--rotate-keys", "--json"], capsys
        )
        assert c2 == mat.EXIT_PENDING
        assert d2["keys_preserved"] is False
        assert "dubai" in d2["keys_rotated"]
        assert d2["secrets_fingerprint"] != fp1

        sec_after = json.loads(mat.LOCATION_KEYS.read_text())
        assert sec_after["locations"]["dubai"]["public_key"] != pub_before
        assert sec_after["locations"]["dubai"].get("rotated_at")

        server_after = json.loads(server_path.read_text())
        priv_after = server_after["inbounds"][0]["tls"]["reality"]["private_key"]
        assert priv_after != priv_before
        # Rematerialized server package must carry rotated private key from secrets
        assert priv_after == sec_after["locations"]["dubai"]["private_key"]
        # Never leak private material into CLI stdout JSON
        assert priv_after not in out2
        assert "PRIVATEKEY" not in json.dumps(d2)
        assert "private_key" not in out2

    def test_check_only_fingerprint_matches_apply(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        _, d_apply, _, _ = _run_main(["--json"], capsys)
        _, d_check, _, _ = _run_main(["--check-only", "--json"], capsys)
        assert d_check["secrets_fingerprint"] == d_apply["secrets_fingerprint"]
        assert d_check["secrets_fingerprint_full"] == d_apply["secrets_fingerprint_full"]


# ---------------------------------------------------------------------------
# Help / public summary shape
# ---------------------------------------------------------------------------


class TestHelpAndSummary:
    def test_help_mentions_exit_codes_and_flags(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        with pytest.raises(SystemExit) as ei:
            mat.parse_args(["--help"])
        assert ei.value.code == 0
        # argparse --help writes to stdout
        help_out = capsys.readouterr().out
        assert "--check-only" in help_out
        assert "--rotate-keys" in help_out
        assert "--force-inventory-env" in help_out
        assert "--json" in help_out
        assert "exit codes" in help_out.lower() or "  0  " in help_out
        assert "secrets_fingerprint" in help_out

    def test_public_summary_has_counts_and_no_secrets(
        self, hermetic_cli: Dict[str, Path], capsys
    ):
        _, data, out, _ = _run_main(["--json"], capsys)
        assert "counts" in data
        assert set(data["counts"]) >= {
            "locations_requested",
            "ready_or_configured",
            "pending_ip",
            "server_configs",
            "keys_rotated",
            "keys_preserved",
        }
        assert "secrets_fingerprint" in data
        assert "pending_ip_locations" in data
        low = out.lower()
        for banned in ("private_key", "hy2_password", "obfs_password", "begin private"):
            assert banned not in low
