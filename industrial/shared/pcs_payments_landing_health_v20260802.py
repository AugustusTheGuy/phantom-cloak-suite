#!/usr/bin/env python3
"""PCS payments + landing dry health probe (industrial only).

Checkout reliability without live card charges. No production Stripe keys
required. Does not open external payment processors for dry checks.

Checks:
  1. Import path for payments + pricing + HTTP landing modules
  2. Pricing engine smoke (Core/Pro report prices)
  3. Order store path writable (~/.pcs_industrial_20260802/payments/)
  4. Static landing exists (landing_v20260802/index.html)
  5. Optional short localhost serve probe (stdlib only, no charges)

Serve locally
-------------
From the industrial tree root (PCS_Industrial_20260802):

  # Prefer industrial venv
  export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
  .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
  # Landing: http://127.0.0.1:8787/
  # GET  /api/pricing   POST /api/create_order  POST /api/confirm_demo

Or:

  ./launches_v20260802/Serve_PCS_Landing_Payments_v20260802.command
  # optional port: ...command 8790

Or module entry:

  .venv/bin/python -m shared.pcs_payments_http_v20260802

Dry health (this file):

  .venv/bin/python -m shared.pcs_payments_landing_health_v20260802
  .venv/bin/python -m shared.pcs_payments_landing_health_v20260802 --json
  .venv/bin/python -m shared.pcs_payments_landing_health_v20260802 --probe-serve

Exit codes:
  0  all required checks pass (optional probe skip is OK)
  1  one or more required checks failed
  2  unexpected probe error
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Paths (industrial tree only)
# ---------------------------------------------------------------------------

INDUSTRIAL = Path(__file__).resolve().parents[1]
SHARED = INDUSTRIAL / "shared"
LANDING_DIR = INDUSTRIAL / "landing_v20260802"
LANDING_HTML = LANDING_DIR / "index.html"
SERVE_LAUNCHER = (
    INDUSTRIAL / "launches_v20260802" / "Serve_PCS_Landing_Payments_v20260802.command"
)
STATE = Path.home() / ".pcs_industrial_20260802" / "payments"
ORDERS_PATH = STATE / "orders.json"

# Report anchors (must match pricing engine + payments industrial)
EXPECTED_CORE_MONTHLY = 11.99
EXPECTED_CORE_ANNUAL = 59.88
EXPECTED_PRO_MONTHLY = 39.00
EXPECTED_PRO_ANNUAL = 348.00

# Never require or prefer live Stripe for dry health
_DRY_ENV_BLOCK = ("STRIPE_SECRET_KEY",)  # documented: dry path works without these


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    required: bool = True
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthReport:
    ok: bool
    industrial_root: str
    checks: list[CheckResult]
    serve_howto: dict[str, str]
    stripe_keys_required: bool = False
    live_charges: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "industrial_root": self.industrial_root,
            "stripe_keys_required": self.stripe_keys_required,
            "live_charges": self.live_charges,
            "timestamp": self.timestamp,
            "serve_howto": self.serve_howto,
            "checks": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "detail": c.detail,
                    "required": c.required,
                    "data": c.data,
                }
                for c in self.checks
            ],
            "summary": {
                "passed": sum(1 for c in self.checks if c.ok),
                "failed": sum(1 for c in self.checks if not c.ok and c.required),
                "skipped_or_optional_fail": sum(
                    1 for c in self.checks if not c.ok and not c.required
                ),
            },
        }


def _ensure_industrial_on_path() -> None:
    root = str(INDUSTRIAL)
    if root not in sys.path:
        sys.path.insert(0, root)


def check_imports() -> CheckResult:
    """Import payments + pricing + HTTP modules without side effects that charge."""
    _ensure_industrial_on_path()
    mods = [
        "shared.pcs_pricing_engine_v20260802",
        "shared.pcs_payments_industrial_v20260802",
        "shared.pcs_payments_http_v20260802",
    ]
    loaded: dict[str, str] = {}
    try:
        for name in mods:
            m = __import__(name, fromlist=["*"])
            loaded[name] = getattr(m, "__file__", "?") or "?"
        # Surface expected public symbols
        from shared import pcs_payments_http_v20260802 as http_mod
        from shared import pcs_payments_industrial_v20260802 as pay
        from shared import pcs_pricing_engine_v20260802 as price

        for attr, obj in (
            ("compute_core", price),
            ("compute_pro", price),
            ("all_plans", price),
            ("tier_prices", pay),
            ("create_order", pay),
            ("confirm_demo", pay),
            ("STATE", pay),
            ("ORDERS", pay),
            ("serve", http_mod),
            ("LANDING", http_mod),
        ):
            if not hasattr(obj, attr):
                return CheckResult(
                    name="imports",
                    ok=False,
                    detail=f"missing symbol {attr} on {obj.__name__}",
                    data={"loaded": loaded},
                )
        return CheckResult(
            name="imports",
            ok=True,
            detail=f"loaded {len(loaded)} modules",
            data={"loaded": loaded},
        )
    except Exception as e:
        return CheckResult(
            name="imports",
            ok=False,
            detail=f"{type(e).__name__}: {e}",
            data={"traceback": traceback.format_exc()[-800:]},
        )


def check_pricing_smoke() -> CheckResult:
    """Pricing engine + industrial tier_prices agree with report anchors."""
    _ensure_industrial_on_path()
    try:
        from shared.pcs_payments_industrial_v20260802 import tier_prices
        from shared.pcs_pricing_engine_v20260802 import (
            all_plans,
            as_dict,
            compute_core,
            compute_pro,
        )

        core = compute_core()
        pro = compute_pro()
        prices = tier_prices()
        issues: list[str] = []

        if core.monthly_usd != EXPECTED_CORE_MONTHLY:
            issues.append(f"core monthly {core.monthly_usd} != {EXPECTED_CORE_MONTHLY}")
        if core.annual_usd != EXPECTED_CORE_ANNUAL:
            issues.append(f"core annual {core.annual_usd} != {EXPECTED_CORE_ANNUAL}")
        if pro.monthly_usd != EXPECTED_PRO_MONTHLY:
            issues.append(f"pro monthly {pro.monthly_usd} != {EXPECTED_PRO_MONTHLY}")
        if pro.annual_usd != EXPECTED_PRO_ANNUAL:
            issues.append(f"pro annual {pro.annual_usd} != {EXPECTED_PRO_ANNUAL}")

        if prices["core"]["monthly"] != EXPECTED_CORE_MONTHLY:
            issues.append("tier_prices core monthly mismatch")
        if prices["core"]["annual"] != EXPECTED_CORE_ANNUAL:
            issues.append("tier_prices core annual mismatch")
        if prices["pro"]["monthly"] != EXPECTED_PRO_MONTHLY:
            issues.append("tier_prices pro monthly mismatch")
        if prices["pro"]["annual"] != EXPECTED_PRO_ANNUAL:
            issues.append("tier_prices pro annual mismatch")

        plans = all_plans()
        if len(plans) != 2:
            issues.append(f"all_plans len={len(plans)}")
        catalog = as_dict()
        if "plans" not in catalog:
            issues.append("as_dict missing plans")

        data = {
            "core": {
                "monthly_usd": core.monthly_usd,
                "annual_usd": core.annual_usd,
                "annual_effective_monthly": core.annual_effective_monthly,
            },
            "pro": {
                "monthly_usd": pro.monthly_usd,
                "annual_usd": pro.annual_usd,
                "annual_effective_monthly": pro.annual_effective_monthly,
            },
            "tier_prices": prices,
        }
        if issues:
            return CheckResult(
                name="pricing_engine_smoke",
                ok=False,
                detail="; ".join(issues),
                data=data,
            )
        return CheckResult(
            name="pricing_engine_smoke",
            ok=True,
            detail=(
                f"Core ${core.monthly_usd}/mo · ${core.annual_usd}/yr; "
                f"Pro ${pro.monthly_usd}/mo · ${pro.annual_usd}/yr"
            ),
            data=data,
        )
    except Exception as e:
        return CheckResult(
            name="pricing_engine_smoke",
            ok=False,
            detail=f"{type(e).__name__}: {e}",
            data={"traceback": traceback.format_exc()[-800:]},
        )


def check_order_store_writable() -> CheckResult:
    """Ensure industrial payments state dir is creatable and writable."""
    _ensure_industrial_on_path()
    try:
        from shared.pcs_payments_industrial_v20260802 import ORDERS, STATE as PAY_STATE

        PAY_STATE.mkdir(parents=True, exist_ok=True)
        try:
            PAY_STATE.chmod(0o700)
        except OSError:
            pass

        probe = PAY_STATE / ".health_write_probe"
        token = f"ok-{time.time_ns()}"
        probe.write_text(token, encoding="utf-8")
        try:
            probe.chmod(0o600)
        except OSError:
            pass
        read_back = probe.read_text(encoding="utf-8")
        try:
            probe.unlink(missing_ok=True)
        except TypeError:
            # py<3.8 style not needed on industrial; keep simple
            if probe.exists():
                probe.unlink()

        if read_back != token:
            return CheckResult(
                name="order_store_writable",
                ok=False,
                detail="write/read mismatch on probe file",
                data={"state": str(PAY_STATE), "orders": str(ORDERS)},
            )

        # Confirm ORDERS path parent is the state dir (industrial isolation)
        if ORDERS.parent != PAY_STATE:
            return CheckResult(
                name="order_store_writable",
                ok=False,
                detail=f"ORDERS parent {ORDERS.parent} != STATE {PAY_STATE}",
                data={"state": str(PAY_STATE), "orders": str(ORDERS)},
            )
        if "pcs_industrial_20260802" not in str(PAY_STATE):
            return CheckResult(
                name="order_store_writable",
                ok=False,
                detail="order store is not under industrial state tree",
                data={"state": str(PAY_STATE)},
            )

        return CheckResult(
            name="order_store_writable",
            ok=True,
            detail=f"writable {PAY_STATE}",
            data={
                "state": str(PAY_STATE),
                "orders": str(ORDERS),
                "orders_exists": ORDERS.exists(),
            },
        )
    except Exception as e:
        return CheckResult(
            name="order_store_writable",
            ok=False,
            detail=f"{type(e).__name__}: {e}",
            data={"state": str(STATE), "orders": str(ORDERS_PATH)},
        )


def check_static_landing() -> CheckResult:
    """Static marketing/checkout landing HTML present and non-empty."""
    exists = LANDING_HTML.is_file()
    launcher_ok = SERVE_LAUNCHER.is_file()
    size = LANDING_HTML.stat().st_size if exists else 0
    snippets_ok = False
    detail_bits: list[str] = []
    if not exists:
        detail_bits.append(f"missing {LANDING_HTML}")
    elif size < 200:
        detail_bits.append(f"landing too small ({size} bytes)")
    else:
        text = LANDING_HTML.read_text(encoding="utf-8", errors="replace")
        need = ("pricing", "PhantomCloak", "plan")
        missing = [n for n in need if n.lower() not in text.lower()]
        if missing:
            detail_bits.append(f"landing missing markers: {missing}")
        else:
            snippets_ok = True
            detail_bits.append(f"landing ok ({size} bytes)")
    if not launcher_ok:
        detail_bits.append(f"launcher missing: {SERVE_LAUNCHER.name}")
    else:
        detail_bits.append("Serve_PCS_Landing launcher present")

    ok = exists and size >= 200 and snippets_ok and launcher_ok
    return CheckResult(
        name="static_landing",
        ok=ok,
        detail="; ".join(detail_bits),
        data={
            "landing": str(LANDING_HTML),
            "exists": exists,
            "size": size,
            "serve_launcher": str(SERVE_LAUNCHER),
            "serve_launcher_exists": launcher_ok,
        },
    )


def check_dry_order_no_stripe() -> CheckResult:
    """Create + confirm demo order without STRIPE_SECRET_KEY (no live charge)."""
    _ensure_industrial_on_path()
    # Temporarily ensure we do not accidentally use a live key for this dry path.
    saved = os.environ.pop("STRIPE_SECRET_KEY", None)
    try:
        from shared.pcs_payments_industrial_v20260802 import (
            confirm_demo,
            create_order,
            redeem_access_code,
        )

        order = create_order("core", "annual", "BTC")
        oid = order.get("order_id")
        if not oid or order.get("amount_usd") != EXPECTED_CORE_ANNUAL:
            return CheckResult(
                name="dry_order_demo",
                ok=False,
                detail=f"unexpected order payload: {order!r}"[:300],
                data={"order": {k: order.get(k) for k in ("order_id", "amount_usd", "status", "asset")}},
            )
        # Card path without Stripe key must stay demo-safe
        card = create_order("pro", "monthly", "CARD")
        if not str(card.get("stripe_pi", "")).startswith("pi_demo_"):
            return CheckResult(
                name="dry_order_demo",
                ok=False,
                detail="CARD order without STRIPE_SECRET_KEY did not use pi_demo_ prefix",
                data={"stripe_pi": card.get("stripe_pi")},
            )

        confirmed = confirm_demo(oid)
        if confirmed.get("status") != "activated" or not confirmed.get("access_code"):
            return CheckResult(
                name="dry_order_demo",
                ok=False,
                detail=f"confirm_demo failed: {confirmed!r}"[:300],
                data={"confirmed": confirmed},
            )
        redeem = redeem_access_code(confirmed["access_code"])
        if not redeem.get("valid"):
            return CheckResult(
                name="dry_order_demo",
                ok=False,
                detail="access code not redeemable after demo confirm",
                data={"redeem": redeem},
            )
        return CheckResult(
            name="dry_order_demo",
            ok=True,
            detail=f"demo order {oid} activated; card path pi_demo_ without Stripe key",
            data={
                "order_id": oid,
                "access_code_prefix": str(confirmed.get("access_code", ""))[:6] + "…",
                "card_pi": card.get("stripe_pi"),
                "stripe_key_used": False,
            },
        )
    except Exception as e:
        return CheckResult(
            name="dry_order_demo",
            ok=False,
            detail=f"{type(e).__name__}: {e}",
            data={"traceback": traceback.format_exc()[-800:]},
        )
    finally:
        if saved is not None:
            os.environ["STRIPE_SECRET_KEY"] = saved


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def check_localhost_serve_probe(timeout_s: float = 2.5) -> CheckResult:
    """Optional: bind 127.0.0.1 only, GET landing + /api/pricing, shut down.

    Safe/short: ephemeral port, loopback only, no create_order with CARD/Stripe
    network, no external hosts.
    """
    _ensure_industrial_on_path()
    # Do not send Stripe traffic during probe
    saved = os.environ.pop("STRIPE_SECRET_KEY", None)
    httpd = None
    thread: Optional[threading.Thread] = None
    try:
        from http.server import ThreadingHTTPServer

        from shared.pcs_payments_http_v20260802 import Handler

        port = _free_port()
        httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        httpd.timeout = 0.5
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.15)

        base = f"http://127.0.0.1:{port}"
        results: dict[str, Any] = {}

        def _get(path: str) -> tuple[int, bytes]:
            req = urllib.request.Request(base + path, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                return resp.getcode(), resp.read()

        code, body = _get("/")
        results["landing_status"] = code
        results["landing_bytes"] = len(body)
        if code != 200 or len(body) < 200:
            return CheckResult(
                name="localhost_serve_probe",
                ok=False,
                required=False,
                detail=f"GET / -> {code} bytes={len(body)}",
                data=results,
            )
        if b"PhantomCloak" not in body and b"pricing" not in body.lower():
            return CheckResult(
                name="localhost_serve_probe",
                ok=False,
                required=False,
                detail="landing body missing expected markers",
                data=results,
            )

        code_p, body_p = _get("/api/pricing")
        results["pricing_status"] = code_p
        payload = json.loads(body_p.decode())
        results["pricing"] = {
            "core_monthly": payload.get("core", {}).get("monthly"),
            "pro_monthly": payload.get("pro", {}).get("monthly"),
        }
        if code_p != 200:
            return CheckResult(
                name="localhost_serve_probe",
                ok=False,
                required=False,
                detail=f"GET /api/pricing -> {code_p}",
                data=results,
            )
        if payload.get("core", {}).get("monthly") != EXPECTED_CORE_MONTHLY:
            return CheckResult(
                name="localhost_serve_probe",
                ok=False,
                required=False,
                detail="pricing API mismatch",
                data=results,
            )

        return CheckResult(
            name="localhost_serve_probe",
            ok=True,
            required=False,
            detail=f"loopback serve ok on 127.0.0.1:{port} (landing + pricing)",
            data=results,
        )
    except Exception as e:
        return CheckResult(
            name="localhost_serve_probe",
            ok=False,
            required=False,
            detail=f"{type(e).__name__}: {e}",
            data={"traceback": traceback.format_exc()[-600:]},
        )
    finally:
        if httpd is not None:
            try:
                httpd.shutdown()
            except Exception:
                pass
            try:
                httpd.server_close()
            except Exception:
                pass
        if thread is not None:
            thread.join(timeout=1.0)
        if saved is not None:
            os.environ["STRIPE_SECRET_KEY"] = saved


def serve_howto() -> dict[str, str]:
    return {
        "launcher": str(SERVE_LAUNCHER),
        "app_shell": (
            f'cd "{INDUSTRIAL}" && export PYTHONPATH="$(pwd):${{PYTHONPATH:-}}" && '
            ".venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787"
        ),
        "module": (
            f'cd "{INDUSTRIAL}" && export PYTHONPATH="$(pwd):${{PYTHONPATH:-}}" && '
            ".venv/bin/python -m shared.pcs_payments_http_v20260802"
        ),
        "url": "http://127.0.0.1:8787/",
        "health": (
            f'cd "{INDUSTRIAL}" && export PYTHONPATH="$(pwd):${{PYTHONPATH:-}}" && '
            ".venv/bin/python -m shared.pcs_payments_landing_health_v20260802 --probe-serve"
        ),
        "notes": (
            "Industrial only. Without STRIPE_SECRET_KEY, CARD orders use pi_demo_ "
            "and confirm_demo mints access codes offline — no live charges."
        ),
    }


def run_health(*, probe_serve: bool = False) -> HealthReport:
    checks: list[CheckResult] = [
        check_imports(),
        check_pricing_smoke(),
        check_order_store_writable(),
        check_static_landing(),
        check_dry_order_no_stripe(),
    ]
    if probe_serve:
        checks.append(check_localhost_serve_probe())
    else:
        checks.append(
            CheckResult(
                name="localhost_serve_probe",
                ok=True,
                required=False,
                detail="skipped (pass --probe-serve to run short loopback probe)",
                data={"skipped": True},
            )
        )

    required_ok = all(c.ok for c in checks if c.required)
    return HealthReport(
        ok=required_ok,
        industrial_root=str(INDUSTRIAL),
        checks=checks,
        serve_howto=serve_howto(),
        stripe_keys_required=False,
        live_charges=False,
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="PCS payments + landing dry health (no live charges)",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable JSON only")
    p.add_argument(
        "--probe-serve",
        action="store_true",
        help="Optional short 127.0.0.1 HTTP probe (landing + /api/pricing)",
    )
    p.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 1 if required checks fail (default when not --json-only behavior)",
    )
    args = p.parse_args(argv)

    try:
        report = run_health(probe_serve=args.probe_serve)
    except Exception:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": traceback.format_exc()[-1200:]},
                    indent=2,
                )
            )
        else:
            traceback.print_exc()
        return 2

    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        status = "PASS" if report.ok else "FAIL"
        print(f"PCS payments landing health: {status}")
        print(f"  industrial: {report.industrial_root}")
        print(f"  live_charges: {report.live_charges}  stripe_keys_required: {report.stripe_keys_required}")
        for c in report.checks:
            mark = "OK" if c.ok else ("SKIP/OPT" if not c.required else "FAIL")
            req = "req" if c.required else "opt"
            print(f"  [{mark}/{req}] {c.name}: {c.detail}")
        print("\nServe locally:")
        howto = report.serve_howto
        print(f"  launcher: {howto['launcher']}")
        print(f"  shell:    {howto['app_shell']}")
        print(f"  url:      {howto['url']}")
        print(f"  notes:    {howto['notes']}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
