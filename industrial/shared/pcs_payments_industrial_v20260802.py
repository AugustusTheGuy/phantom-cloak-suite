"""Operational payment engine for PCS Industrial (new file).

Pricing from PhantomCloak_Pricing_Referral_Features_Report.md:
  Core: $11.99/mo · $4.99/mo billed yearly ($59.88/yr)
  Pro:  $39/mo founder · $29/mo billed yearly ($348/yr)

Crypto: XMR, BTC, ETH, SOL (+ optional stables) — chain-confirm → mint access code
  (same correct model as Suite crypto_payments, isolated industrial state).

Card: Stripe PaymentIntent scaffolding via env STRIPE_SECRET_KEY.
  Without keys: creates pending card orders for local demo.

State: ~/.pcs_industrial_20260802/payments/ (never Suite paths).
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

STATE = Path.home() / ".pcs_industrial_20260802" / "payments"
ORDERS = STATE / "orders.json"
REDEEMED = STATE / "redeemed.json"

# Report prices
TIER_TERMS = {
    ("core", "monthly"): 11.99,
    ("core", "annual"): 59.88,   # $4.99/mo effective
    ("pro", "monthly"): 39.00,   # founder
    ("pro", "annual"): 348.00,   # $29/mo billed yearly
}

ASSETS = {
    "XMR": {"name": "Monero", "model": "private", "confirms": 10},
    "BTC": {"name": "Bitcoin", "model": "utxo", "confirms": 2},
    "ETH": {"name": "Ethereum", "model": "account", "confirms": 12},
    "SOL": {"name": "Solana", "model": "account", "confirms": 32},
    "CARD": {"name": "Credit/Debit Card", "model": "stripe", "confirms": 1},
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
    stripe_pi: str | None = None
    client_secret: str | None = None


def _ensure():
    STATE.mkdir(parents=True, exist_ok=True)
    try:
        STATE.chmod(0o700)
    except OSError:
        pass


def _load() -> dict[str, Order]:
    try:
        raw = json.loads(ORDERS.read_text())
        return {k: Order(**v) for k, v in raw.items()}
    except Exception:
        return {}


def _save(orders: dict[str, Order]) -> None:
    _ensure()
    ORDERS.write_text(json.dumps({k: asdict(v) for k, v in orders.items()}, indent=2))
    try:
        ORDERS.chmod(0o600)
    except OSError:
        pass


def tier_prices() -> dict:
    return {
        "core": {
            "monthly": TIER_TERMS[("core", "monthly")],
            "annual": TIER_TERMS[("core", "annual")],
            "annual_effective_monthly": round(TIER_TERMS[("core", "annual")] / 12, 2),
            "source": "PhantomCloak_Pricing_Referral_Features_Report.md",
        },
        "pro": {
            "monthly": TIER_TERMS[("pro", "monthly")],
            "annual": TIER_TERMS[("pro", "annual")],
            "annual_effective_monthly": round(TIER_TERMS[("pro", "annual")] / 12, 2),
            "founder_note": "Pro $39/mo founder; annual $29/mo effective",
            "source": "PhantomCloak_Pricing_Referral_Features_Report.md",
        },
    }


def supported_methods() -> dict:
    return {k: {"name": v["name"], "model": v["model"]} for k, v in ASSETS.items()}


def _wallets_from_env() -> dict[str, str]:
    return {
        "XMR": os.environ.get("PCS_WALLET_XMR", "XMR_INTEGRATED_OR_SUBADDRESS_PLACEHOLDER"),
        "BTC": os.environ.get("PCS_WALLET_BTC", "bc1q_PLACEHOLDER"),
        "ETH": os.environ.get("PCS_WALLET_ETH", "0x_PLACEHOLDER"),
        "SOL": os.environ.get("PCS_WALLET_SOL", "SoL_PLACEHOLDER"),
    }


def _gen_code() -> str:
    raw = secrets.token_hex(16).upper()
    return "PC-" + "-".join(raw[i : i + 4] for i in range(0, 16, 4))


def create_order(tier: str, term: str, asset: str) -> dict[str, Any]:
    asset = asset.upper()
    tier = tier.lower()
    term = term.lower()
    if asset not in ASSETS:
        raise ValueError(f"unsupported asset {asset}")
    if (tier, term) not in TIER_TERMS:
        raise ValueError(f"unknown tier/term {tier}/{term}")

    orders = _load()
    oid = "ord_" + secrets.token_hex(8)
    amount = TIER_TERMS[(tier, term)]
    tag = secrets.token_hex(16)
    wallets = _wallets_from_env()

    if asset == "CARD":
        pi, secret = _stripe_payment_intent(amount, tier, term, oid)
        o = Order(
            order_id=oid,
            tier=tier,
            term=term,
            asset=asset,
            amount_usd=amount,
            payment_target="stripe",
            payment_tag=tag,
            stripe_pi=pi,
            client_secret=secret,
        )
    else:
        o = Order(
            order_id=oid,
            tier=tier,
            term=term,
            asset=asset,
            amount_usd=amount,
            payment_target=wallets.get(asset, ""),
            payment_tag=tag,
        )
    orders[oid] = o
    _save(orders)
    out = asdict(o)
    out["instructions"] = _instructions(o)
    return out


def _instructions(o: Order) -> str:
    if o.asset == "CARD":
        if o.client_secret and not o.client_secret.startswith("demo_"):
            return "Complete card payment with Stripe client_secret in checkout UI."
        return (
            "Stripe not configured (set STRIPE_SECRET_KEY). "
            "Demo: POST /api/confirm_demo with order_id to mint access code offline."
        )
    if o.asset == "XMR":
        return (
            f"Send ${o.amount_usd} USD equivalent in XMR with payment tag {o.payment_tag}. "
            f"Target: {o.payment_target}. Confirmed via wallet RPC/processor (not public explorer)."
        )
    return (
        f"Send ${o.amount_usd} USD equivalent in {o.asset} to {o.payment_target} "
        f"with memo/tag {o.payment_tag}. Wait for required confirmations, then webhook/confirm."
    )


def _stripe_payment_intent(amount_usd: float, tier: str, term: str, order_id: str) -> tuple[str, str]:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        return ("pi_demo_" + order_id, "demo_secret_" + order_id)
    cents = int(round(amount_usd * 100))
    data = (
        f"amount={cents}&currency=usd"
        f"&metadata[order_id]={order_id}&metadata[tier]={tier}&metadata[term]={term}"
        f"&automatic_payment_methods[enabled]=true"
    ).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/payment_intents",
        data=data,
        method="POST",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
            return body.get("id", ""), body.get("client_secret", "")
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:300]
        return ("pi_error", f"error:{err}")
    except Exception as e:
        return ("pi_error", f"error:{e}")


def confirm_crypto_payment(
    order_id: str, txid: str, confirmations: int, amount_ok: bool
) -> dict[str, Any]:
    """Call after chain watcher / NOWPayments / BTCPay confirms payment."""
    orders = _load()
    o = orders.get(order_id)
    if not o:
        return {"error": "unknown order"}
    if o.status == "activated":
        return {"status": "activated", "access_code": o.access_code}
    if o.asset == "CARD":
        return {"error": "use confirm_card for CARD orders"}
    need = ASSETS[o.asset]["confirms"]
    if amount_ok and confirmations >= need:
        o.status = "activated"
        o.confirmed_at = time.time()
        o.txid = txid
        o.access_code = _gen_code()
        orders[order_id] = o
        _save(orders)
        return {
            "status": "activated",
            "access_code": o.access_code,
            "tier": o.tier,
            "term": o.term,
        }
    return {"status": "awaiting_payment", "confirmations": confirmations, "needed": need}


def confirm_card_payment(order_id: str, payment_intent_id: str | None = None) -> dict[str, Any]:
    """Stripe webhook or poll: confirm PI succeeded then mint code."""
    orders = _load()
    o = orders.get(order_id)
    if not o:
        return {"error": "unknown order"}
    if o.status == "activated":
        return {"status": "activated", "access_code": o.access_code}
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    pi = payment_intent_id or o.stripe_pi
    if key and pi and not str(pi).startswith("pi_demo"):
        req = urllib.request.Request(
            f"https://api.stripe.com/v1/payment_intents/{pi}",
            headers={"Authorization": f"Bearer {key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode())
                if body.get("status") != "succeeded":
                    return {"status": "awaiting_payment", "stripe_status": body.get("status")}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}
    elif not (pi and str(pi).startswith("pi_demo")):
        return {"status": "awaiting_payment", "message": "Stripe not confirmed"}

    o.status = "activated"
    o.confirmed_at = time.time()
    o.txid = pi
    o.access_code = _gen_code()
    orders[order_id] = o
    _save(orders)
    return {"status": "activated", "access_code": o.access_code, "tier": o.tier, "term": o.term}


def confirm_demo(order_id: str) -> dict[str, Any]:
    """Offline/dev only: mint access after local demo payment."""
    orders = _load()
    o = orders.get(order_id)
    if not o:
        return {"error": "unknown order"}
    o.status = "activated"
    o.confirmed_at = time.time()
    o.txid = "demo_tx_" + secrets.token_hex(4)
    o.access_code = _gen_code()
    orders[order_id] = o
    _save(orders)
    return {"status": "activated", "access_code": o.access_code, "demo": True}


def redeem_access_code(code: str) -> dict[str, Any]:
    for o in _load().values():
        if o.access_code == code and o.status == "activated":
            return {"valid": True, "tier": o.tier, "term": o.term, "order_id": o.order_id}
    return {"valid": False}
