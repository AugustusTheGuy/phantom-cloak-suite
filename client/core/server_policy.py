"""Server & client privacy policy — 'diskless-first' enforcement.

Two layers:
  1. SERVER: only route through exit servers reporting diskless=True (RAM-only).
     Modes (env PHANTOMCLOAK_DISKLESS): off | preferred | required.
       - preferred (default NOW): prefer diskless, fall back if none exist yet.
       - required: refuse to connect if no diskless server is available
         (fail-closed). Flip to this once diskless servers are deployed.
  2. CLIENT: ephemeral mode — the client persists no sensitive state to disk
     (session in memory; logs off). The on-device analog of 'diskless'.

HONESTY: 'diskless / RAM-only' is a SERVER property. A phone/desktop app cannot
be 'diskless' the way a server is; the client analog is ephemeral, no-local-log
operation. Full RAM-only servers are ops work (tmpfs+overlayfs now; stboot-style
secure boot later), not client code. Do NOT flip MODE to 'required' or claim
RAM-only publicly until diskless servers actually exist.
"""
from __future__ import annotations
import os

MODE = os.environ.get("PHANTOMCLOAK_DISKLESS", "preferred").lower()   # off|preferred|required
CLIENT_EPHEMERAL = os.environ.get("PHANTOMCLOAK_EPHEMERAL", "1") == "1"


def _diskless(s):
    if isinstance(s, dict):
        return bool(s.get("diskless"))
    return bool(getattr(s, "diskless", False))


def allowed_servers(servers):
    """Filter exit servers per policy. Returns (allowed_list, note)."""
    diskless = [s for s in servers if _diskless(s)]
    if MODE == "off":
        return servers, "diskless policy off"
    if MODE == "required":
        if diskless:
            return diskless, "diskless-only enforced"
        return [], "NO diskless servers available — connection blocked (fail-closed)"
    # preferred
    if diskless:
        return diskless, "diskless preferred"
    return servers, "no diskless servers yet — using standard (preferred mode)"


def is_fail_closed(servers):
    """True if 'required' mode would block all connections (no diskless servers)."""
    return MODE == "required" and not any(_diskless(s) for s in servers)


def client_writes_disk_allowed():
    """When ephemeral, the app must not persist sensitive state to disk."""
    return not CLIENT_EPHEMERAL
