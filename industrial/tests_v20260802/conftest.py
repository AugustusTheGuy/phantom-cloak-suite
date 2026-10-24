"""Shared hermetic fixtures for industrial tests_v20260802.

Never writes real ~/.pcs_industrial_20260802 secrets or inventory.
All path rebinding goes through module configure_paths + tmp_path.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import pcs_materialize_singbox_v20260802 as mat  # noqa: E402
from shared import pcs_server_readiness_v20260802 as ready  # noqa: E402

# Public-looking IPv4 that passes is_real_ip / is_real_public_ip
# (not RFC1918 / TEST-NET / localhost / docs ranges).
REAL_PUBLIC_IP = "104.21.16.42"
REAL_PUBLIC_IP_2 = "8.8.4.4"

# Stable mock crypto — offline, no sing-box / openssl
MOCK_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
MOCK_PRIVATE_KEY = "PRIVATEKEY_TEST_BASE64URL_xxxxxxxxxxxxxxxxxxxx"
MOCK_PUBLIC_KEY = "PUBLICKEY_TEST_BASE64URL_yyyyyyyyyyyyyyyyyyyyy"


def restore_production_paths() -> None:
    """Rebind materialize + readiness globals to production defaults."""
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


def install_mock_crypto(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline crypto stubs so materialize never shells out to sing-box/openssl."""
    monkeypatch.setattr(mat, "gen_uuid", lambda: MOCK_UUID)
    monkeypatch.setattr(
        mat,
        "gen_reality_keypair",
        lambda: (MOCK_PRIVATE_KEY, MOCK_PUBLIC_KEY),
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
        cert.write_text(
            "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n"
        )
        key.write_text(
            "-----BEGIN PRIVATE KEY-----\nTEST\n-----END PRIVATE KEY-----\n"
        )
        return cert, key

    monkeypatch.setattr(mat, "ensure_hy2_tls_certs", _fake_hy2_certs)


def bind_tmp_industrial_home(tmp_path: Path) -> Dict[str, Path]:
    """Create throwaway home/state/suite and rebind configure_paths on mat + ready."""
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
    return {
        "home": home,
        "state": state,
        "suite": suite,
        "industrial": industrial,
    }


@pytest.fixture
def hermetic_industrial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Dict[str, Any]]:
    """Isolate materialize + readiness under tmp_path with mock crypto.

    Restores production path bindings after the test so later tests (or live
    tools) are not left pointing at the disposable tree.
    """
    paths = bind_tmp_industrial_home(tmp_path)
    install_mock_crypto(monkeypatch)
    yield {
        **paths,
        "real_public_ip": REAL_PUBLIC_IP,
        "real_public_ip_2": REAL_PUBLIC_IP_2,
        "mock_uuid": MOCK_UUID,
        "mock_public_key": MOCK_PUBLIC_KEY,
        "mock_private_key": MOCK_PRIVATE_KEY,
    }
    restore_production_paths()
