"""Subscription / tier entitlement gate for PhantomCloak Suite.

Verifies the user has an ACTIVE subscription and WHICH tier before any
PhantomCloak feature unlocks. If unverified, the app stays locked (sign-in /
subscribe screen).

HONEST LIMITATION (do not oversell): this is a client-side gate. A determined
local user can bypass a purely local check. Real enforcement requires a
licensing/entitlement server that validates a signed token or payment-processor
receipt server-side. verify_remote() is where that call goes. Until a backend +
processor exist, set env PHANTOMCLOAK_DEV=1 to run unlocked for development —
this makes the "no real enforcement yet" state explicit rather than hidden.
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from . import tier as tier_mod

STATE_DIR = Path.home() / ".phantomcloak-suite"
ENTITLEMENT_FILE = STATE_DIR / "entitlement.json"
LOCAL_DEV_MODE = os.environ.get("PHANTOMCLOAK_DEV") == "1"


class Entitlement:
    def __init__(self, active, tier, source, expires=None):
        self.active = bool(active)
        self.tier = tier_mod.normalize(tier)
        self.source = source          # "remote" | "cache" | "dev" | "none"
        self.expires = expires

    def to_dict(self):
        return {"active": self.active, "tier": self.tier,
                "source": self.source, "expires": self.expires}


def _load_cache():
    try:
        d = json.loads(ENTITLEMENT_FILE.read_text())
        exp = d.get("expires")
        if exp and time.time() > exp:
            return None
        return Entitlement(d["active"], d["tier"], "cache", exp)
    except Exception:
        return None


def verify_remote(token):
    """Placeholder for server-side entitlement validation. Wire this to your
    licensing endpoint / Stripe receipt validation. Returns None until a
    backend is configured (so the gate stays honest and fail-closed)."""
    return None


def _save(e):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        ENTITLEMENT_FILE.write_text(json.dumps(e.to_dict(), indent=2))
        ENTITLEMENT_FILE.chmod(0o600)
        STATE_DIR.chmod(0o700)
    except OSError:
        pass


def check_entitlement(token=None):
    """Resolve current entitlement, fail-closed to LOCKED when unknown."""
    remote = verify_remote(token)
    if remote is not None:
        _save(remote)
        return remote
    cached = _load_cache()
    if cached is not None:
        return cached
    if LOCAL_DEV_MODE:
        return Entitlement(True, tier_mod.resolve_tier(tier_mod.PRO), "dev")
    return Entitlement(False, tier_mod.CORE, "none")


_TERM_SECONDS = {"monthly": 31 * 86400, "annual": 366 * 86400}


def grant_from_purchase(tier, term, source="purchase"):
    """Grant an entitlement after a verified purchase (redeemed access code).

    The access code is only minted post-confirmation on-chain (see
    crypto_payments.confirm_payment), so reaching here means payment was proven.
    Writes a cached entitlement with a term-based expiry; check_entitlement()
    honors it via _load_cache(). Real cross-device enforcement still requires the
    licensing server in verify_remote() — this cache is the local grant."""
    import time as _t
    dur = _TERM_SECONDS.get(term, _TERM_SECONDS["monthly"])
    e = Entitlement(True, tier, source, expires=_t.time() + dur)
    _save(e)
    return e


def is_unlocked(e):
    return bool(e.active)
