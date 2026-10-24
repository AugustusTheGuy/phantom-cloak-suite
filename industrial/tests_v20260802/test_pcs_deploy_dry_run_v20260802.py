"""Hermetic dry-run tests for industrial sing-box VPS deploy scripts.

Covers:
  - Mac → /etc/sing-box path rewrite
  - pcs_deploy_one --dry-run prints PLAN without SSH/SCP
  - deploy_filled_to_vps --dry-run is NO-OP when inventory empty
  - live mode rejects TEST-NET / placeholder targets

Industrial tree only. Never scp to real hosts. Suite deploy scripts untouched.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
INDUSTRIAL_SCRIPTS = ROOT / "server_vps_package_v20260802" / "scripts"
REWRITE_PY = INDUSTRIAL_SCRIPTS / "pcs_rewrite_singbox_paths_v20260802.py"
DEPLOY_ONE_SH = INDUSTRIAL_SCRIPTS / "pcs_deploy_one_v20260802.sh"
COMPOSE_PY = INDUSTRIAL_SCRIPTS / "pcs_compose_deploy_v20260802.py"
BOOTSTRAP_SH = INDUSTRIAL_SCRIPTS / "pcs_remote_bootstrap_singbox_v20260802.sh"

# Documentation / TEST-NET ranges (RFC 5737) + placeholders — never live-deploy
TESTNET_TARGETS = (
    "root@203.0.113.10",
    "root@198.51.100.1",
    "ubuntu@192.0.2.55",
)
PLACEHOLDER_TARGETS = (
    "root@YOUR_VPS_IP",
    "root@your-dubai-vps.example.com",
    "deploy@example.com",
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rewrite = _load_module("pcs_rewrite_singbox_paths_v20260802", REWRITE_PY)
compose = _load_module("pcs_compose_deploy_v20260802", COMPOSE_PY)


def _mac_hy2_config(location: str = "dubai", home: str = "/Users/ceo") -> dict:
    """Minimal filled server JSON with Mac absolute cert paths (hy2 + reality)."""
    base = f"{home}/.pcs_industrial_20260802/vps_server_package/hy2_certs/{location}"
    return {
        "log": {"level": "warn"},
        "inbounds": [
            {
                "type": "vless",
                "tag": "vless-reality",
                "listen": "::",
                "listen_port": 443,
                "users": [{"name": "pcs", "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}],
                "tls": {
                    "enabled": True,
                    "server_name": "www.microsoft.com",
                    "reality": {
                        "enabled": True,
                        "private_key": "TEST_PRIVATE_KEY",
                        "short_id": ["abcd1234"],
                    },
                },
            },
            {
                "type": "hysteria2",
                "tag": "hy2-in",
                "listen": "::",
                "listen_port": 8443,
                "users": [{"name": "pcs", "password": "test-hy2-password"}],
                "tls": {
                    "enabled": True,
                    "certificate_path": f"{base}/fullchain.pem",
                    "key_path": f"{base}/privkey.pem",
                },
            },
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
    }


def _stage_pkg(
    tmp: Path,
    *,
    location: str = "dubai",
    with_hy2: bool = True,
    inventory: Optional[dict] = None,
) -> Path:
    """Create a throwaway vps_server_package + inventory tree for subprocess tests."""
    home = tmp / "home"
    state = home / ".pcs_industrial_20260802"
    pkg = state / "vps_server_package"
    scripts = pkg / "scripts"
    scripts.mkdir(parents=True)
    # Copy industrial scripts into staged package (mirrors materialize sync)
    for src in (REWRITE_PY, DEPLOY_ONE_SH, BOOTSTRAP_SH, COMPOSE_PY):
        dest = scripts / src.name
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o700)

    cfg = _mac_hy2_config(location, home=str(home))
    (pkg / f"sing-box-{location}-reality.json").write_text(
        json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
    )
    if with_hy2:
        hy2 = pkg / "hy2_certs" / location
        hy2.mkdir(parents=True)
        (hy2 / "fullchain.pem").write_text("-----BEGIN CERTIFICATE-----\nT\n-----END CERTIFICATE-----\n")
        (hy2 / "privkey.pem").write_text("-----BEGIN PRIVATE KEY-----\nT\n-----END PRIVATE KEY-----\n")

    inv = inventory if inventory is not None else {
        "version": 1,
        "ssh_user": "root",
        "locations": {
            location: {"ip": "", "ssh_user": "", "enabled": True},
        },
    }
    (state / "vps_inventory.json").write_text(json.dumps(inv, indent=2) + "\n", encoding="utf-8")
    return pkg


def _fake_ssh_path(tmp: Path) -> Path:
    """PATH entry with ssh/scp that scream if invoked (must never run on dry-run)."""
    bindir = tmp / "fakebin"
    bindir.mkdir(parents=True, exist_ok=True)
    for name in ("ssh", "scp"):
        p = bindir / name
        p.write_text(
            "#!/bin/sh\n"
            f'echo "{name.upper()}_INVOKED $*" >&2\n'
            "exit 99\n",
            encoding="utf-8",
        )
        p.chmod(0o755)
    return bindir


def _run(
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=full_env,
        cwd=str(cwd) if cwd else None,
        check=False,
    )


# ---------------------------------------------------------------------------
# Path rewrite Mac → /etc/sing-box
# ---------------------------------------------------------------------------


class TestRewriteMacToSingbox:
    def test_hy2_mac_paths_rewrite(self):
        data = _mac_hy2_config("dubai")
        out, changes = rewrite.rewrite_config(data, "dubai")
        tls = out["inbounds"][1]["tls"]
        assert tls["certificate_path"] == "/etc/sing-box/hy2_certs/dubai/fullchain.pem"
        assert tls["key_path"] == "/etc/sing-box/hy2_certs/dubai/privkey.pem"
        assert len(changes) == 2
        assert all(c["to"].startswith("/etc/sing-box/") for c in changes)
        assert not any("/Users/" in c["to"] for c in changes)

    def test_desktop_and_var_folders_paths(self):
        data = {
            "inbounds": [
                {
                    "tls": {
                        "certificate_path": "/var/folders/xx/yy/T/hy2_certs/hongkong/fullchain.pem",
                        "key_path": "~/Desktop/PCS_Industrial_20260802/hy2_certs/hongkong/privkey.pem",
                    }
                }
            ]
        }
        out, changes = rewrite.rewrite_config(data, "hongkong")
        assert out["inbounds"][0]["tls"]["certificate_path"] == (
            "/etc/sing-box/hy2_certs/hongkong/fullchain.pem"
        )
        assert out["inbounds"][0]["tls"]["key_path"] == (
            "/etc/sing-box/hy2_certs/hongkong/privkey.pem"
        )
        assert len(changes) == 2

    def test_already_vps_paths_unchanged(self):
        data = {
            "inbounds": [
                {
                    "tls": {
                        "certificate_path": "/etc/sing-box/hy2_certs/germany/fullchain.pem",
                        "key_path": "/etc/sing-box/hy2_certs/germany/privkey.pem",
                    }
                }
            ]
        }
        out, changes = rewrite.rewrite_config(data, "germany")
        assert changes == []
        assert out["inbounds"][0]["tls"]["certificate_path"].startswith("/etc/sing-box/")

    def test_cli_dry_run_no_write(self, tmp_path: Path):
        cfg = tmp_path / "in.json"
        outp = tmp_path / "out.json"
        cfg.write_text(json.dumps(_mac_hy2_config("cayman")), encoding="utf-8")
        proc = _run(
            [
                sys.executable,
                str(REWRITE_PY),
                "--in",
                str(cfg),
                "--out",
                str(outp),
                "--location",
                "cayman",
                "--dry-run",
            ]
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert not outp.exists(), "dry-run without --write-on-dry-run must not write"
        assert "/etc/sing-box/hy2_certs/cayman/" in proc.stdout
        assert "dry-run: skipped write" in proc.stdout

    def test_cli_write_rewritten(self, tmp_path: Path):
        cfg = tmp_path / "in.json"
        outp = tmp_path / "out.json"
        cfg.write_text(json.dumps(_mac_hy2_config("mauritius")), encoding="utf-8")
        proc = _run(
            [
                sys.executable,
                str(REWRITE_PY),
                "--in",
                str(cfg),
                "--out",
                str(outp),
                "--location",
                "mauritius",
            ]
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        written = json.loads(outp.read_text(encoding="utf-8"))
        assert written["inbounds"][1]["tls"]["certificate_path"] == (
            "/etc/sing-box/hy2_certs/mauritius/fullchain.pem"
        )


# ---------------------------------------------------------------------------
# deploy_one --dry-run → PLAN, no SSH
# ---------------------------------------------------------------------------


class TestDeployOneDryRun:
    def test_dry_run_prints_plan_without_ssh(self, tmp_path: Path):
        pkg = _stage_pkg(tmp_path, location="dubai")
        fakebin = _fake_ssh_path(tmp_path)
        env = {
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
            "PCS_VPS_PKG": str(pkg),
            "HOME": str(tmp_path / "home"),
        }
        proc = _run(
            ["bash", str(DEPLOY_ONE_SH), "--dry-run", "root@203.0.113.10", "dubai"],
            env=env,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "PLAN:" in out
        assert "PLAN: ssh" in out
        assert "PLAN: scp" in out
        assert "DRY-RUN complete — no SSH/SCP performed" in out
        assert "PCS_DEPLOY_ONE_DRY_RUN=OK" in out
        assert "SSH_INVOKED" not in out
        assert "SCP_INVOKED" not in out
        # Rewritten paths visible in dry-run preview
        assert "/etc/sing-box/hy2_certs/dubai/fullchain.pem" in out
        assert "/Users/" not in out.split("inbound[")[-1] if "inbound[" in out else True

    def test_dry_run_env_var(self, tmp_path: Path):
        pkg = _stage_pkg(tmp_path, location="germany")
        fakebin = _fake_ssh_path(tmp_path)
        env = {
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
            "PCS_VPS_PKG": str(pkg),
            "PCS_DRY_RUN": "1",
            "HOME": str(tmp_path / "home"),
        }
        proc = _run(
            ["bash", str(DEPLOY_ONE_SH), "root@198.51.100.9", "germany"],
            env=env,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "PLAN:" in out
        assert "SSH_INVOKED" not in out
        assert "dry_run=1" in out


# ---------------------------------------------------------------------------
# deploy_filled_to_vps --dry-run NO-OP when inventory empty
# ---------------------------------------------------------------------------


class TestDeployFilledEmptyInventory:
    def test_compose_empty_inventory_is_all_noop(self, tmp_path: Path):
        pkg = _stage_pkg(
            tmp_path,
            location="dubai",
            inventory={
                "ssh_user": "root",
                "locations": {
                    "dubai": {"ip": "", "enabled": True},
                    "hongkong": {"ip": "YOUR_VPS_IP", "enabled": True},
                    "vancouver": {"ip": "203.0.113.50", "enabled": True},
                },
            },
        )
        # Also drop empty-IP sibling configs so locations_with_config sees them
        for loc in ("hongkong", "vancouver"):
            (pkg / f"sing-box-{loc}-reality.json").write_text(
                json.dumps(_mac_hy2_config(loc)), encoding="utf-8"
            )

        home = tmp_path / "home"
        state = home / ".pcs_industrial_20260802"
        compose.configure_paths(
            home=home,
            state=state,
            vps_pkg=pkg,
            inventory=state / "vps_inventory.json",
            industrial_scripts=INDUSTRIAL_SCRIPTS,
        )
        try:
            text = compose.compose(dry_run=True)
        finally:
            # Restore production paths
            compose.configure_paths(
                home=Path.home(),
                state=Path.home() / ".pcs_industrial_20260802",
                industrial_scripts=INDUSTRIAL_SCRIPTS,
            )

        assert "NO-OP" in text
        assert "live_targets=0" in text or "pending=" in text
        # Empty / placeholder / TEST-NET must not emit live deploy_one without --dry-run branch only
        assert 'bash "$DEPLOY_ONE" "root@' not in text  # no live (non-dry) invocations
        # No real public IPs baked in
        for bad in ("8.8.8.8", "1.1.1.1", "104."):
            assert bad not in text

    def test_generated_script_dry_run_noop_no_ssh(self, tmp_path: Path):
        """Write compose output and execute --dry-run: NO-OP lines, zero SSH."""
        pkg = _stage_pkg(
            tmp_path,
            location="dubai",
            inventory={
                "ssh_user": "root",
                "locations": {
                    "dubai": {"ip": "", "enabled": True},
                    "seychelles": {"ip": "", "enabled": True},
                },
            },
        )
        (pkg / "sing-box-seychelles-reality.json").write_text(
            json.dumps(_mac_hy2_config("seychelles")), encoding="utf-8"
        )
        home = tmp_path / "home"
        state = home / ".pcs_industrial_20260802"
        compose.configure_paths(
            home=home,
            state=state,
            vps_pkg=pkg,
            inventory=state / "vps_inventory.json",
            industrial_scripts=INDUSTRIAL_SCRIPTS,
        )
        try:
            text = compose.compose(dry_run=False)
        finally:
            compose.configure_paths(
                home=Path.home(),
                state=Path.home() / ".pcs_industrial_20260802",
                industrial_scripts=INDUSTRIAL_SCRIPTS,
            )

        script = pkg / "deploy_filled_to_vps.sh"
        script.write_text(text, encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)

        fakebin = _fake_ssh_path(tmp_path)
        env = {
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
            "HOME": str(home),
            "PCS_VPS_PKG": str(pkg),
        }
        proc = _run(["bash", str(script), "--dry-run"], env=env)
        out = proc.stdout + proc.stderr
        assert proc.returncode == 0, out
        assert "NO-OP" in out
        assert "dubai" in out
        assert "SSH_INVOKED" not in out
        assert "SCP_INVOKED" not in out
        assert "PCS_DEPLOY_FILLED_DRY_RUN=OK" in out
        # No live deploy blocks executed
        assert "=== Deploy" not in out

    def test_materialize_build_deploy_empty_inventory_noop(self, tmp_path: Path):
        """build_deploy_script from materialize: empty IPs → NO-OP + dry-run safe."""
        sys.path.insert(0, str(ROOT))
        from shared import pcs_materialize_singbox_v20260802 as mat

        home = tmp_path / "home"
        state = home / ".pcs_industrial_20260802"
        suite = home / "Desktop" / "PhantomCloak Suite"
        industrial = ROOT  # use real industrial scripts
        (suite / "server" / "ready-for-vps").mkdir(parents=True)
        state.mkdir(parents=True)

        mat.configure_paths(
            home=home,
            state=state,
            suite=suite,
            industrial=industrial,
        )
        try:
            inv = {
                "ssh_user": "root",
                "locations": {
                    "dubai": {"ip": "", "enabled": True},
                    "hongkong": {"ip": "203.0.113.10", "enabled": True},
                },
            }
            text, deployable, skipped = mat.build_deploy_script(
                ["dubai", "hongkong"], inv, "root"
            )
            assert deployable == []
            assert len(skipped) == 2
            assert "NO-OP" in text
            assert "PCS_DEPLOY_FILLED_DRY_RUN=OK" in text
            # Dry-run path may demo deploy_one against TEST-NET only
            assert "203.0.113.10" in text  # documented demo host only under --dry-run
            assert 'bash "$DEPLOY_ONE" "root@203.0.113.10"' not in text  # never live
        finally:
            mat.configure_paths(
                home=Path.home(),
                state=Path.home() / ".pcs_industrial_20260802",
                suite=Path.home() / "Desktop" / "PhantomCloak Suite",
                industrial=ROOT,
            )


# ---------------------------------------------------------------------------
# Live mode rejects TEST-NET / placeholders
# ---------------------------------------------------------------------------


class TestLiveModeRejectsUnsafeTargets:
    @pytest.mark.parametrize("target", TESTNET_TARGETS + PLACEHOLDER_TARGETS)
    def test_deploy_one_refuses_placeholder_live(self, tmp_path: Path, target: str):
        pkg = _stage_pkg(tmp_path, location="dubai")
        fakebin = _fake_ssh_path(tmp_path)
        env = {
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
            "PCS_VPS_PKG": str(pkg),
            "HOME": str(tmp_path / "home"),
            "PCS_DRY_RUN": "0",
        }
        proc = _run(
            ["bash", str(DEPLOY_ONE_SH), target, "dubai"],
            env=env,
        )
        out = proc.stdout + proc.stderr
        assert proc.returncode != 0, out
        assert "refusing placeholder" in out or "documentation target" in out
        assert "SSH_INVOKED" not in out
        assert "SCP_INVOKED" not in out

    def test_compose_is_real_ip_rejects_testnet_and_placeholders(self):
        assert compose.is_real_ip("") is False
        assert compose.is_real_ip(None) is False
        assert compose.is_real_ip("203.0.113.10") is False
        assert compose.is_real_ip("198.51.100.1") is False
        assert compose.is_real_ip("192.0.2.1") is False
        assert compose.is_real_ip("YOUR_VPS_IP") is False
        assert compose.is_real_ip("your-dubai-vps.example.com") is False
        assert compose.is_real_ip("10.0.0.1") is False
        assert compose.is_real_ip("192.168.1.1") is False
        assert compose.is_real_ip("127.0.0.1") is False
        # A known public DNS IP is accepted by the heuristic
        assert compose.is_real_ip("1.1.1.1") is True

    def test_dry_run_allows_testnet_targets(self, tmp_path: Path):
        """TEST-NET is OK under --dry-run (docs demos); still no SSH."""
        pkg = _stage_pkg(tmp_path, location="dubai")
        fakebin = _fake_ssh_path(tmp_path)
        env = {
            "PATH": f"{fakebin}{os.pathsep}{os.environ.get('PATH', '')}",
            "PCS_VPS_PKG": str(pkg),
            "HOME": str(tmp_path / "home"),
        }
        proc = _run(
            ["bash", str(DEPLOY_ONE_SH), "--dry-run", "root@203.0.113.10", "dubai"],
            env=env,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "SSH_INVOKED" not in (proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# Script presence / industrial + state package parity helpers
# ---------------------------------------------------------------------------


class TestScriptLocations:
    def test_industrial_scripts_exist(self):
        for p in (REWRITE_PY, DEPLOY_ONE_SH, COMPOSE_PY, BOOTSTRAP_SH):
            assert p.is_file(), f"missing industrial script: {p}"

    def test_state_package_scripts_exist_if_present(self):
        state = Path.home() / ".pcs_industrial_20260802" / "vps_server_package" / "scripts"
        if not state.is_dir():
            pytest.skip("state vps package not materialized")
        for name in (
            "pcs_rewrite_singbox_paths_v20260802.py",
            "pcs_deploy_one_v20260802.sh",
            "pcs_compose_deploy_v20260802.py",
            "pcs_remote_bootstrap_singbox_v20260802.sh",
        ):
            assert (state / name).is_file(), f"missing state script: {name}"

