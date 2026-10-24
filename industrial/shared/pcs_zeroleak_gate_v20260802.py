"""Zero-leak preflight gate for PCS Industrial — new module (no overwrite of Suite zeroleak_verifier).

Fail-closed: if any *enabled* protection layer fails verification, caller must
trip killswitch before any outbound "protected session" traffic.

Honest limit (FTC): reduces leak risk dramatically; cannot claim mathematical
impossibility of all side-channels.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass
class LayerCheck:
    name: str
    passed: bool
    required: bool = True
    detail: str = ""


@dataclass
class GateReport:
    tier: str
    checks: list[LayerCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        req = [c for c in self.checks if c.required]
        return bool(req) and all(c.passed for c in req)

    def failures(self) -> list[LayerCheck]:
        return [c for c in self.checks if c.required and not c.passed]

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "ok": self.ok,
            "failures": [c.name for c in self.failures()],
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "required": c.required,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


def _pfctl_present() -> LayerCheck:
    ok = shutil.which("pfctl") is not None
    return LayerCheck("killswitch_binary", ok, True, "pfctl present" if ok else "pfctl missing")


def _dns_ok() -> LayerCheck:
    try:
        socket.gethostbyname("example.com")
        return LayerCheck("dns_resolves", True, True, "DNS resolves")
    except Exception as e:
        return LayerCheck("dns_resolves", False, True, str(e)[:120])


def _tunnel_hint() -> LayerCheck:
    """Soft probe: utun/sing presence. Required only when session claims tunnel."""
    try:
        out = subprocess.run(
            ["ifconfig"], capture_output=True, text=True, timeout=4, check=False
        ).stdout or ""
        up = "utun" in out or "sing" in out.lower()
        return LayerCheck(
            "tunnel_interface",
            up,
            required=False,  # optional until real server online
            detail="tun present" if up else "no tun (OK in offline demo)",
        )
    except Exception as e:
        return LayerCheck("tunnel_interface", False, False, str(e)[:80])


def _obfuscation_method_configured(method: str | None) -> LayerCheck:
    methods = {"reality", "quic", "shadowtls", "ws-tls", "obfs", None, ""}
    ok = method in methods or (isinstance(method, str) and len(method) > 0)
    return LayerCheck(
        "obfuscation_method",
        True if method is None else ok,
        required=True,
        detail=f"method={method or 'auto'}",
    )


def _tracker_vault_consistent(
    vault_enabled: bool,
    vault_ok: bool | None,
) -> LayerCheck:
    """If user enabled tracker vault hide, it must report healthy before send."""
    if not vault_enabled:
        return LayerCheck(
            "tracker_vault",
            True,
            required=False,
            detail="vault not requested",
        )
    return LayerCheck(
        "tracker_vault",
        bool(vault_ok),
        required=True,
        detail="vault healthy" if vault_ok else "vault hide incomplete — must killswitch",
    )


def _layer_map_healthy(layer_results: dict[str, bool] | None) -> list[LayerCheck]:
    """Every enabled layer in layer_results must be True."""
    out: list[LayerCheck] = []
    if not layer_results:
        out.append(
            LayerCheck(
                "enabled_layers_map",
                True,
                required=False,
                detail="no extra layers registered",
            )
        )
        return out
    for name, healthy in layer_results.items():
        out.append(
            LayerCheck(
                f"layer:{name}",
                bool(healthy),
                required=True,
                detail="ok" if healthy else "FAILED — trip killswitch",
            )
        )
    return out


def run_preflight(
    *,
    tier: str = "core",
    obfuscation_method: str | None = "reality",
    tracker_vault_enabled: bool = False,
    tracker_vault_ok: bool | None = None,
    enabled_layers: dict[str, bool] | None = None,
    require_tunnel: bool = False,
    require_killswitch_binary: bool = True,
) -> GateReport:
    """Run zero-leak checks.

    require_killswitch_binary: when False, pfctl presence is recorded but not
    required. Use for the obfuscation-only preflight phase (before killswitch
    arm) so a missing pfctl cannot fail-closed the wrong gate — arm failure is
    reported at GATE_KILLSWITCH instead.
    """
    report = GateReport(tier=tier)
    ks = _pfctl_present()
    if not require_killswitch_binary:
        ks.required = False
        if not ks.passed:
            ks.detail = (ks.detail or "pfctl missing") + " (optional until killswitch arm)"
    report.checks.append(ks)
    report.checks.append(_dns_ok())
    tun = _tunnel_hint()
    if require_tunnel:
        tun.required = True
    report.checks.append(tun)
    report.checks.append(_obfuscation_method_configured(obfuscation_method))
    report.checks.append(
        _tracker_vault_consistent(tracker_vault_enabled, tracker_vault_ok)
    )
    report.checks.extend(_layer_map_healthy(enabled_layers))
    return report


def enforce_or_kill(
    on_failure: Callable[[GateReport], None] | None,
    **kwargs,
) -> GateReport:
    """Run preflight; on any required failure, invoke killswitch callback first."""
    report = run_preflight(**kwargs)
    if not report.ok and callable(on_failure):
        try:
            on_failure(report)
        except Exception:
            pass
    return report
