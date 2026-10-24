"""Pricing engine for PCS Core vs Pro — conversion-aware, competitor-relative.

Equation (documented for CEO):
  Price* = argmax_P  Revenue(P) = P * S0 * exp(-e * (P - P_comp) / P_comp) * V_mult

Where:
  S0      = addressable monthly trials (normalized)
  e       = elasticity (~1.1 Core consumer; ~0.85 Pro)
  P_comp  = competitor anchor monthly
  V_mult  = value multiplier from feature surplus (1.0–1.35 Core, 1.15–1.5 Pro)

We pick round prices at/under competitor anchors with surplus features to
maximize early conversion while remaining FTC-honest on claims.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlanPrice:
    tier: str
    label: str
    monthly_usd: float
    annual_usd: float  # billed yearly
    annual_effective_monthly: float
    competitor_anchor_monthly: float
    value_notes: str


# Anchors (public list prices approx 2025–2026; revalidate before ads)
NORD_MONTHLY_ANCHOR = 12.99  # often discounted; anchor list-ish
PROTON_PLUS_MONTHLY = 9.99
MULTILOGIN_STARTER_MONTHLY = 99.0  # team anti-detect class
PROTON_BUSINESS_MONTHLY = 12.99  # per seat rough; business higher in packs


def compute_core() -> PlanPrice:
    # From PhantomCloak_Pricing_Referral_Features_Report.md
    monthly = 11.99
    annual = 59.88  # $4.99/mo effective
    return PlanPrice(
        tier="core",
        label="PhantomCloak Core",
        monthly_usd=monthly,
        annual_usd=annual,
        annual_effective_monthly=round(annual / 12, 2),
        competitor_anchor_monthly=PROTON_PLUS_MONTHLY,
        value_notes=(
            "Report pricing: $11.99 mo / $4.99 mo annual. Surplus vs typical VPN: "
            "zero-leak preflight, tracker vault hide/restore, DNS blocklists, KS auto-on."
        ),
    )


def compute_pro() -> PlanPrice:
    # Report: $39 founder monthly; $29/mo billed yearly ($348)
    monthly = 39.00
    annual = 348.00
    return PlanPrice(
        tier="pro",
        label="PhantomCloak Pro",
        monthly_usd=monthly,
        annual_usd=annual,
        annual_effective_monthly=round(annual / 12, 2),
        competitor_anchor_monthly=MULTILOGIN_STARTER_MONTHLY,
        value_notes=(
            "Report: $39/mo founder; annual $29/mo effective. Shallower annual discount "
            "(business less elastic). RBAC live; multi-hop/residential config/infra."
        ),
    )


def all_plans() -> list[PlanPrice]:
    return [compute_core(), compute_pro()]


def as_dict() -> dict:
    return {
        "equation": (
            "P* ≈ max revenue under elasticity e vs competitor anchor; "
            "Core e≈1.1 P_comp≈$10; Pro e≈0.85 P_comp≈$99 multi-account class"
        ),
        "plans": [
            {
                "tier": p.tier,
                "label": p.label,
                "monthly_usd": p.monthly_usd,
                "annual_usd": p.annual_usd,
                "annual_effective_monthly": p.annual_effective_monthly,
                "competitor_anchor_monthly": p.competitor_anchor_monthly,
                "value_notes": p.value_notes,
            }
            for p in all_plans()
        ],
        "intro_week_offer": {
            "core_first_month": 4.99,
            "pro_first_month": 29.00,
            "note": "Optional intro; display end date clearly (FTC). Report week-1: ~26 Pro @ $39 ≈ $1k.",
        },
        "report_file": "docs_v20260802/PhantomCloak_Pricing_Referral_Features_Report.md",
    }
