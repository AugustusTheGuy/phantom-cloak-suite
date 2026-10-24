"""Referral engine — double-sided referral with anti-fraud + LTV controls.

Strategy encoded here:
  * Reward the REFERRER only after the referred user's first successful charge
    AND the refund window closes (blocks charge-then-refund abuse).
  * LTV guard: reward gated on referred user's RETENTION past a hold window,
    not just signup — directly answers the "low-LTV referrals" problem.
  * Reward as ACCOUNT CREDIT, never cash (kills cash-out fraud rings).
  * Fixed credit (1 month), not a perpetual discount (protects the price anchor).
  * Referred friend gets a first-period discount (lifts conversion).
  * Per-account caps + device/payment fingerprint dedupe (audience is
    unusually skilled at multi-accounting).

Persistence + payment/refund events come from the host/backend; this module is
the pure, unit-testable decision logic.
"""
from __future__ import annotations
import time
from dataclasses import dataclass

REFUND_WINDOW_DAYS = 7
REWARD_HOLD_DAYS = REFUND_WINDOW_DAYS + 1        # release on day 8
MAX_REWARDED_REFERRALS_PER_MONTH = 10
FRIEND_FIRST_PERIOD_DISCOUNT = 0.30              # 30% off month one
REFERRER_CREDIT_MONTHS = 1


@dataclass
class Referral:
    referrer_id: str
    friend_id: str
    created_at: float
    first_charge_at: float | None = None
    refunded: bool = False
    friend_active: bool = True
    device_fp: str | None = None
    payment_fp: str | None = None
    rewarded: bool = False


def is_reward_due(r: Referral, now: float | None = None):
    now = now or time.time()
    if r.rewarded:
        return False, "already rewarded"
    if r.first_charge_at is None:
        return False, "no successful charge yet"
    if r.refunded:
        return False, "referred charge was refunded"
    if not r.friend_active:
        return False, "referred user churned before retention gate (LTV guard)"
    days = (now - r.first_charge_at) / 86400.0
    if days < REWARD_HOLD_DAYS:
        return False, "in refund/retention hold window"
    return True, "eligible"


def count_rewarded(referrals, referrer_id, since_days=30, now=None):
    now = now or time.time()
    cutoff = now - since_days * 86400
    return sum(1 for x in referrals
               if x.referrer_id == referrer_id and x.rewarded and x.created_at >= cutoff)


def evaluate(r: Referral, all_referrals, referrer_fp=None, now=None):
    now = now or time.time()
    due, reason = is_reward_due(r, now)
    if not due:
        return {"release": False, "reason": reason}
    if referrer_fp and (r.device_fp == referrer_fp.get("device")
                        or r.payment_fp == referrer_fp.get("payment")):
        return {"release": False, "reason": "self-referral fingerprint match — flagged for review"}
    if count_rewarded(all_referrals, r.referrer_id, now=now) >= MAX_REWARDED_REFERRALS_PER_MONTH:
        return {"release": False, "reason": "monthly referral cap reached"}
    return {"release": True, "reason": "eligible",
            "referrer_credit_months": REFERRER_CREDIT_MONTHS,
            "friend_discount": FRIEND_FIRST_PERIOD_DISCOUNT}
