"""Obfuscation method catalog for PCS Industrial (new file; does not overwrite Suite obfuscation.py)."""
from __future__ import annotations

# Consumer + industrial transport camouflage methods (sing-box class)
METHODS = (
    "reality",
    "quic",
    "shadowtls",
    "ws-tls",
    "obfs",
    "hysteria2",
    "amneziawg",
    "meek_scaffold",
)


def auto_select_method(*, blocked: bool = False, dpi_suspected: bool = False) -> str:
    if dpi_suspected:
        return "reality"
    if blocked:
        return "quic"
    return "reality"


def describe_method(method: str) -> str:
    return {
        "reality": "TLS-camouflage (REALITY) — mimics real HTTPS to a real site.",
        "quic": "QUIC / HTTP-3 — blends with modern web traffic.",
        "shadowtls": "ShadowTLS — genuine TLS handshake wrapper.",
        "ws-tls": "WebSocket over TLS — ordinary web-socket appearance.",
        "obfs": "Generic scrambling anti-fingerprint layer.",
        "hysteria2": "Hysteria2 — UDP/QUIC-class resilient transport.",
        "amneziawg": "AmneziaWG-style WireGuard camouflage (when configured).",
        "meek_scaffold": "Domain-fronting-class meek (infra / policy dependent).",
    }.get(method, "unknown method")


def all_methods() -> list[dict]:
    return [{"id": m, "description": describe_method(m)} for m in METHODS]
