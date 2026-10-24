"""Obfuscation config surface — auto-select the best sing-box transport.

Explains/implements the "surface + auto-select + QUIC" idea. PhantomCloak runs
on sing-box, which supports several obfuscation transports (REALITY/VLESS,
ShadowTLS, QUIC/HTTP-3, WebSocket-over-TLS, obfs-style scrambling). This module
chooses a method for current network conditions and EXPOSES which one is active
(transparency competitors hide). Applying the choice is done by singbox_manager.
"""
from __future__ import annotations

METHODS = ["reality", "quic", "shadowtls", "ws-tls", "obfs"]


def auto_select(blocked: bool = False, dpi_suspected: bool = False) -> str:
    if dpi_suspected:
        return "reality"     # strongest camouflage vs DPI / AI traffic profiling
    if blocked:
        return "quic"        # blends with modern HTTP/3 traffic vs port/proto blocks
    return "reality"


def describe(method: str) -> str:
    return {
        "reality":  "TLS-camouflage (REALITY) — mimics real HTTPS to a real site.",
        "quic":     "QUIC / HTTP-3 transport — blends with modern web traffic.",
        "shadowtls":"ShadowTLS — wraps traffic in a genuine TLS handshake.",
        "ws-tls":   "WebSocket over TLS — looks like ordinary web sockets.",
        "obfs":     "obfs-style scrambling — generic anti-fingerprint layer.",
    }.get(method, "unknown")
