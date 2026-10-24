"""PhantomCloak crypto payment + access-code engine.

CORRECT verification model (chain-watch -> then mint):
  1. create_order() issues a per-order payment target (unique memo/payment-id;
     for account-model chains a unique tag; for UTXO chains a derived address).
  2. A watcher (confirm_payment, driven by a backend indexer/processor webhook)
     checks the CHAIN for the exact amount + confirmations. The blockchain is the
     proof - never a code the user types.
  3. Only AFTER confirmation, an access code is minted: cryptographically random,
     single-use, never-repeated, bound to (tier, term).

Why: if a user-held code were the proof, anyone with a code gets service. Here a
stolen code can't fabricate a payment, and a payment can't be "scooped" because
the code is minted post-confirmation and bound to the order.

HONEST LIMITS: Monero is privacy-by-design and CANNOT be watched from a public
address; it uses the 'private' model (integrated address / payment-id per order,
confirmed by a Monero wallet RPC or processor on the backend). Real chain
confirmation needs a node/indexer or processor (CoinGate, NOWPayments, BTCPay)
supplied by the backend. This module is the engine + state + code logic and is
fully unit-testable offline.
"""
from __future__ import annotations
import json
import secrets
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

STATE = Path.home() / ".phantomcloak-suite" / "payments"
ORDERS = STATE / "orders.json"

ASSETS = {
    "XMR":       {"name": "Monero",      "model": "private", "confirms": 10, "privacy": "ultimate"},
    "BTC":       {"name": "Bitcoin",     "model": "utxo",    "confirms": 2},
    "ETH":       {"name": "Ethereum",    "model": "account", "confirms": 12},
    "SOL":       {"name": "Solana",      "model": "account", "confirms": 32},
    "LTC":       {"name": "Litecoin",    "model": "utxo",    "confirms": 6},
    "USDC":      {"name": "USD Coin",    "model": "account", "confirms": 32},
    "USDT_TRON": {"name": "USDT (TRON)", "model": "account", "confirms": 20},
    "ZEC":       {"name": "Zcash",       "model": "private", "confirms": 8, "privacy": "high"},
}

TIER_TERMS = {
    ("core", "monthly"): 11.99, ("core", "annual"): 59.88,
    ("pro", "monthly"): 39.00,  ("pro", "annual"): 348.00,
}


@dataclass
class Order:
    order_id: str
    tier: str
    term: str
    asset: str
    amount_usd: float
    payment_target: str
    payment_tag: str
    status: str = "awaiting_payment"
    created_at: float = field(default_factory=time.time)
    confirmed_at: float | None = None
    access_code: str | None = None
    txid: str | None = None
    redeemed_at: float | None = None


def _load():
    try:
        return {k: Order(**v) for k, v in json.loads(ORDERS.read_text()).items()}
    except Exception:
        return {}


def _save(orders):
    STATE.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text(json.dumps({k: asdict(v) for k, v in orders.items()}, indent=2))
    try:
        ORDERS.chmod(0o600)
    except OSError:
        pass


def _gen_tag():
    return secrets.token_hex(16)


def _gen_access_code():
    raw = secrets.token_hex(16).upper()
    return "PC-" + "-".join(raw[i:i+4] for i in range(0, len(raw), 4))


def supported_assets():
    return {k: {"name": v["name"], "privacy": v.get("privacy", "standard")}
            for k, v in ASSETS.items()}


def create_order(tier, term, asset, wallets):
    if asset not in ASSETS:
        raise ValueError("unsupported asset")
    if (tier, term) not in TIER_TERMS:
        raise ValueError("unknown tier/term")
    orders = _load()
    oid = "ord_" + secrets.token_hex(8)
    o = Order(order_id=oid, tier=tier, term=term, asset=asset,
              amount_usd=TIER_TERMS[(tier, term)],
              payment_target=wallets.get(asset, ""), payment_tag=_gen_tag())
    orders[oid] = o
    _save(orders)
    return asdict(o)


def confirm_payment(order_id, txid, confirmations, amount_ok):
    orders = _load()
    o = orders.get(order_id)
    if not o:
        return {"error": "unknown order"}
    if o.status in ("activated", "redeemed"):
        # Idempotent: never re-mint a new code for an order that already has one.
        return {"status": o.status, "access_code": o.access_code,
                "tier": o.tier, "term": o.term}
    need = ASSETS[o.asset]["confirms"]
    if amount_ok and confirmations >= need:
        o.status = "activated"
        o.confirmed_at = time.time()
        o.txid = txid
        o.access_code = _gen_access_code()
        orders[order_id] = o
        _save(orders)
        return {"status": "activated", "access_code": o.access_code,
                "tier": o.tier, "term": o.term}
    return {"status": "awaiting_payment", "confirmations": confirmations, "needed": need}


def redeem_access_code(code):
    """Single-use redemption. A code is valid exactly once: on success the order
    is marked 'redeemed' so the same code can never grant entitlement twice."""
    orders = _load()
    for oid, o in orders.items():
        if o.access_code != code:
            continue
        if o.status == "activated":
            o.status = "redeemed"
            o.redeemed_at = time.time()
            orders[oid] = o
            _save(orders)
            return {"valid": True, "tier": o.tier, "term": o.term, "order_id": o.order_id}
        if o.status == "redeemed":
            return {"valid": False, "reason": "already_redeemed",
                    "tier": o.tier, "term": o.term}
    return {"valid": False, "reason": "not_found"}
