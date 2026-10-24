#!/usr/bin/env python3
"""PCS Industrial app shell — drives Suite modules by import only.

ZERO OVERWRITES of Desktop/PhantomCloak or Desktop/PhantomCloak Suite.
Adds industrial preflight + killswitch (not /tmp) before any protected session.

Usage:
  .venv/bin/python core_product/pcs_app_shell_v20260802.py
  .venv/bin/python core_product/pcs_app_shell_v20260802.py --tier pro
  .venv/bin/python core_product/pcs_app_shell_v20260802.py --activate browsing CH
  .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

INDUSTRIAL_ROOT = Path(__file__).resolve().parents[1]
SUITE_ROOT = Path.home() / "Desktop" / "PhantomCloak Suite"
LEGACY_ROOT = Path.home() / "Desktop" / "PhantomCloak"

# Industrial packages first, then Suite for read-only imports
sys.path.insert(0, str(INDUSTRIAL_ROOT))
if SUITE_ROOT.is_dir():
    sys.path.insert(0, str(SUITE_ROOT))

os.environ.setdefault("PCS_TIER", "core")


def _import_industrial_residential_pool():
    """Prefer industrial synthetic catalog; returns module or None."""
    try:
        from shared import pcs_residential_pool_industrial_v20260802 as industrial_pool  # type: ignore

        return industrial_pool
    except Exception:
        return None


def _import_suite():
    """Import Suite client modules without modifying them."""
    if not SUITE_ROOT.is_dir():
        raise FileNotFoundError(f"Suite not found at {SUITE_ROOT}")
    # Suite expects `from client.core...`
    import client.core.purpose_catalog as purpose_catalog  # type: ignore
    import client.core.residential_pool as residential_pool  # type: ignore
    import client.core.singbox_manager as singbox_manager  # type: ignore
    import client.core.browser_launcher as browser_launcher  # type: ignore
    import client.core.anti_forensics as anti_forensics  # type: ignore
    import client.core.tracker_vault as tracker_vault  # type: ignore
    import client.core.dns_blocklists as dns_blocklists  # type: ignore
    import client.core.rbac as rbac  # type: ignore
    import client.core.referrals as referrals  # type: ignore
    import client.core.feature_registry as feature_registry  # type: ignore
    import client.core.tier as suite_tier  # type: ignore
    return SimpleNamespace(
        purpose_catalog=purpose_catalog,
        residential_pool=residential_pool,
        singbox_manager=singbox_manager,
        browser_launcher=browser_launcher,
        anti_forensics=anti_forensics,
        tracker_vault=tracker_vault,
        dns_blocklists=dns_blocklists,
        rbac=rbac,
        referrals=referrals,
        feature_registry=feature_registry,
        tier=suite_tier,
    )


class PcsAppShell:
    """Shell app state + Suite adapters + industrial preflight."""

    def __init__(self, tier: str = "core"):
        from shared.pcs_tier_catalog_v20260802 import normalize, label

        self.tier = normalize(tier)
        self.tier_label = label(self.tier)
        self.suite = None
        self.suite_error = None
        try:
            self.suite = _import_suite()
        except Exception as e:
            self.suite_error = str(e)

        self.current_purpose = "browsing"
        self.selected_country = "CH"
        self.current_location = "zurich"
        self.selected_residential_ip = None
        self.phantomcloak_active = False
        self.kill_switch_armed = False
        self.google_hidden = False
        self.all_trackers_hidden = False
        self.zero_leak_verified = False
        self.vault = None
        # Industrial catalog preferred; Suite residential_pool is fallback only
        self._industrial_pool = _import_industrial_residential_pool()
        if self.suite:
            self.vault = self.suite.tracker_vault.TrackerVault()

    def _get_residential_pool(self, country_code: str):
        """Prefer industrial get_pool; fall back to Suite residential_pool."""
        if self._industrial_pool is not None and hasattr(self._industrial_pool, "get_pool"):
            return self._industrial_pool.get_pool(country_code)
        if self.suite is not None:
            return self.suite.residential_pool.get_pool(country_code)
        raise RuntimeError("No residential pool available (industrial or Suite)")

    def _country_to_location_map(self) -> dict:
        if self._industrial_pool is not None:
            loc = getattr(self._industrial_pool, "COUNTRY_TO_LOCATION", None)
            if isinstance(loc, dict) and loc:
                return loc
        if self.suite is not None:
            loc = getattr(self.suite.residential_pool, "COUNTRY_TO_LOCATION", None)
            if isinstance(loc, dict) and loc:
                return loc
        return {}

    def status(self) -> dict[str, Any]:
        """Dashboard / operator status — always allowed even when Suite is missing.

        Protect remains fail-closed via protect_gate.ok_for_protect.
        Partial Suite import failure must not prevent readiness surface.
        """
        from shared.pcs_session_resume_v20260802 import resume_payload

        # --- readiness (industrial; independent of Suite) ---
        readiness: dict[str, Any] = {}
        gate: dict[str, Any] = {}
        readiness_error: str | None = None
        try:
            from shared.pcs_server_readiness_v20260802 import gate_snapshot, scan_readiness

            readiness = scan_readiness()
            gate = gate_snapshot(readiness)
        except Exception as e:
            readiness_error = f"{type(e).__name__}: {e}"
            readiness = {
                "ok": False,
                "status": "error",
                "error": readiness_error,
                "configured_count": 0,
                "server_filled_count": 0,
                "pending_ip_count": 0,
                "next_actions": [
                    {
                        "severity": "critical",
                        "code": "readiness_exception",
                        "action": f"Fix readiness scanner: {readiness_error}",
                    }
                ],
                "summary": f"error: {readiness_error}",
            }
            gate = {
                "status": "error",
                "ok_for_protect": False,
                "configured_count": 0,
                "server_filled_count": 0,
                "pending_ip_count": 0,
                "pending": [],
                "next_actions": readiness["next_actions"],
                "next_step": readiness["next_actions"][0]["action"],
                "block_message": (
                    "Status available; protect blocked (readiness error). "
                    "Dashboard / wizard / HOWTO remain available."
                ),
                "inventory_path": str(Path.home() / ".pcs_industrial_20260802" / "vps_inventory.json"),
                "howto_path": str(
                    INDUSTRIAL_ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
                ),
                "secrets_fingerprint": None,
            }

        # --- security audit (Suite optional / read-only) ---
        audit: dict[str, Any] = {"score": None, "grade": None}
        audit_error: str | None = None
        try:
            from shared.pcs_security_audit_engine_v20260802 import run_full_audit

            audit = run_full_audit(include_suite_readonly=bool(self.suite))
        except Exception as e:
            audit_error = f"{type(e).__name__}: {e}"
            audit = {"score": None, "grade": None, "error": audit_error}

        # --- pricing / methods (industrial; soft-fail) ---
        pricing: dict[str, Any] = {}
        payment_methods: list[Any] = []
        try:
            from shared.pcs_payments_industrial_v20260802 import tier_prices, supported_methods

            pricing = tier_prices()
            payment_methods = supported_methods()
        except Exception as e:
            pricing = {"error": f"{type(e).__name__}: {e}"}

        # --- residential catalog (counts only; never tunnel claim) ---
        residential: dict[str, Any] = {
            "catalog_kind": None,
            "countries_count": 0,
            "total_entries": 0,
            "not_a_tunnel_endpoint": True,
            "claims_tunnel_readiness": False,
            "note": "Residential catalog unavailable",
        }
        try:
            if self._industrial_pool is not None and hasattr(
                self._industrial_pool, "catalog_summary"
            ):
                residential = self._industrial_pool.catalog_summary()
            else:
                from shared.pcs_residential_pool_industrial_v20260802 import catalog_summary

                residential = catalog_summary()
        except Exception as e:
            residential = {
                "catalog_kind": None,
                "countries_count": 0,
                "total_entries": 0,
                "not_a_tunnel_endpoint": True,
                "claims_tunnel_readiness": False,
                "note": f"Residential catalog unavailable: {type(e).__name__}",
                "error": f"{type(e).__name__}: {e}",
            }

        # --- resume (soft) ---
        try:
            resume = resume_payload()
        except Exception as e:
            resume = {"available": False, "label": "Resume unavailable", "error": str(e)}

        secrets_fp = gate.get("secrets_fingerprint")
        if secrets_fp is None:
            secrets_fp = readiness.get("secrets_fingerprint")

        industrial_howto = str(
            INDUSTRIAL_ROOT / "docs_v20260802" / "HOWTO_DEPLOY_LINK_v20260802.md"
        )
        fleet_playbook = str(
            INDUSTRIAL_ROOT
            / "docs_v20260802"
            / "CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md"
        )
        howto = (
            gate.get("howto_path")
            or gate.get("industrial_howto")
            or readiness.get("howto_path")
            or readiness.get("industrial_howto")
            or industrial_howto
        )
        inventory_path = (
            gate.get("inventory_path")
            or (readiness.get("inventory") or {}).get("path")
            or str(Path.home() / ".pcs_industrial_20260802" / "vps_inventory.json")
        )

        # --- purpose top5 (pure data; always available offline) ---
        purpose_top5: dict[str, Any] = {
            "purposes": [],
            "by_purpose": {},
            "mvp_ips": 0,
            "note": "Purpose routing unavailable",
        }
        try:
            from shared.pcs_purpose_routing_v20260802 import purpose_top5_summary

            purpose_top5 = purpose_top5_summary()
        except Exception as e:
            purpose_top5 = {
                "purposes": [],
                "by_purpose": {},
                "mvp_ips": 0,
                "note": f"Purpose routing unavailable: {type(e).__name__}",
                "error": f"{type(e).__name__}: {e}",
            }

        # --- inventory pool (v2 total_real_ips; soft-fail, never invents IPs) ---
        inventory_pool: dict[str, Any] = {
            "version": 2,
            "total_real_ips": 0,
            "locations_with_ips": 0,
            "by_location": {},
            "note": "No real owned VPS IPs in inventory yet",
        }
        try:
            from shared.pcs_inventory_v2_v20260802 import pool_summary

            ps = pool_summary()
            inventory_pool = {
                "version": int(ps.get("version") or 2),
                "total_real_ips": int(ps.get("total_real_ips") or 0),
                "locations_with_ips": int(ps.get("locations_with_ips") or 0),
                "by_location": ps.get("by_location") or {},
                "note": (
                    "Owned public IPs in inventory pools only — not catalog entries."
                    if int(ps.get("total_real_ips") or 0) > 0
                    else "No real owned VPS IPs in inventory yet"
                ),
            }
        except Exception as e:
            inventory_pool = {
                "version": 2,
                "total_real_ips": 0,
                "locations_with_ips": 0,
                "by_location": {},
                "note": f"Inventory pool unavailable: {type(e).__name__}",
                "error": f"{type(e).__name__}: {e}",
            }

        # --- synthetic profile seed write-path (soft-fail; never invents exit IP) ---
        synthetic_profile: dict[str, Any] = {
            "available": False,
            "not_a_warranty": True,
            "no_third_party_accounts": True,
        }
        try:
            from shared.pcs_synthetic_profile_v20260802 import seed_and_write_from_status

            synthetic_profile = seed_and_write_from_status(
                location=self.current_location or "zurich",
                purpose=self.current_purpose or "browsing",
                exit_ip="",  # status never invents IPs; gate stays fail-closed
                slot_id="status",
                wipe_done=False,
            )
            synthetic_profile["available"] = True
        except Exception as e:
            synthetic_profile = {
                "available": False,
                "not_a_warranty": True,
                "no_third_party_accounts": True,
                "error": f"{type(e).__name__}: {e}",
            }

        # Compact gate for dashboards (status always allowed; protect is gated)
        # Fail-closed: configured_count=0 ⇒ ok_for_protect false (never invent readiness)
        cfg_n = int(gate.get("configured_count") or 0)
        ok_protect = bool(gate.get("ok_for_protect")) and cfg_n > 0
        protect_gate = {
            "status": gate.get("status") or readiness.get("status"),
            "ok_for_protect": ok_protect,
            "configured_count": cfg_n,
            "server_filled_count": int(gate.get("server_filled_count") or 0),
            "pending_ip_count": int(gate.get("pending_ip_count") or 0),
            "pending": gate.get("pending") or [],
            "next_actions": gate.get("next_actions") or readiness.get("next_actions") or [],
            "next_step": gate.get("next_step") or readiness.get("next_step"),
            "block_message": gate.get("block_message")
            or (
                None
                if ok_protect
                else (
                    f"Protect blocked: configured_count={cfg_n}. "
                    "Fill inventory (see CEO fleet playbook), materialize, then re-scan."
                )
            ),
            "inventory_path": inventory_path,
            "howto_path": howto,
            "industrial_howto": gate.get("industrial_howto")
            or readiness.get("industrial_howto")
            or industrial_howto,
            "fleet_playbook_path": fleet_playbook,
            "materialize_script": gate.get("materialize_script")
            or readiness.get("materialize_script"),
            "secrets_fingerprint": secrets_fp,  # public short hash only
            "secrets_age": gate.get("secrets_age") or readiness.get("secrets_age"),
            "summary": gate.get("summary") or readiness.get("summary"),
            "total_real_ips": inventory_pool["total_real_ips"],
        }

        suite_partial = bool(self.suite_error) or (
            SUITE_ROOT.is_dir() and self.suite is None
        )

        return {
            "tier": self.tier,
            "tier_label": self.tier_label,
            "suite_available": self.suite is not None,
            "suite_partial": suite_partial,
            "suite_error": self.suite_error,
            "suite_required_for_status": False,
            "status_ok_without_suite": True,
            "active": self.phantomcloak_active,
            "killswitch": self.kill_switch_armed,
            "zero_leak_verified": self.zero_leak_verified,
            "location": self.current_location,
            "country": self.selected_country,
            "purpose": self.current_purpose,
            "resume": resume,
            "server_readiness": readiness,
            "protect_gate": protect_gate,
            # Top-level mirrors for simple dashboard bindings
            "status": protect_gate["status"],
            "configured_count": protect_gate["configured_count"],
            "server_filled_count": protect_gate["server_filled_count"],
            "pending_ip_count": protect_gate["pending_ip_count"],
            "next_actions": protect_gate["next_actions"],
            "secrets_fingerprint": secrets_fp,
            "ok_for_protect": protect_gate["ok_for_protect"],
            "inventory_path": inventory_path,
            "howto_path": howto,
            "fleet_playbook_path": fleet_playbook,
            "purpose_top5": purpose_top5,
            "inventory_pool": inventory_pool,
            "total_real_ips": inventory_pool["total_real_ips"],
            "synthetic_profile": synthetic_profile,
            "residential_catalog": residential,
            "security_score": audit.get("score"),
            "security_grade": audit.get("grade"),
            "audit_error": audit_error,
            "readiness_error": readiness_error,
            "pricing": pricing,
            "payment_methods": payment_methods,
            "honest_copy": "protections active · verify recommended",
            "industrial_root": str(INDUSTRIAL_ROOT),
            "suite_root": str(SUITE_ROOT),
            "overwrites": "none — Suite/legacy read-only imports only",
            "cta": {
                "inventory_path": inventory_path,
                "wizard": "Open VPS deploy wizard in Command Center",
                "howto_path": howto,
                "industrial_howto": industrial_howto,
                "fleet_playbook_path": fleet_playbook,
                "fleet_playbook_label": "CEO Fleet Beginner Playbook",
                "fleet_playbook_cta": (
                    "Open CEO_FLEET_BEGINNER_PLAYBOOK — own VPS IPs → raise configured_count"
                ),
                "materialize_script": protect_gate.get("materialize_script"),
                "launch_dashboard": str(
                    INDUSTRIAL_ROOT
                    / "launches_v20260802"
                    / "Open_PCS_CommandCenter_v2.command"
                ),
            },
        }

    def feature_inventory(self) -> dict[str, Any]:
        from shared.pcs_feature_matrix_v20260802 import for_tier, status_counts

        inv = {
            "industrial_matrix": for_tier(self.tier),
            "industrial_status_counts": status_counts(self.tier),
        }
        if self.suite:
            inv["suite_registry_summary"] = self.suite.feature_registry.status_summary()
            inv["suite_live"] = self.suite.feature_registry.live_features()
        return inv

    def activate(
        self,
        purpose: str = "browsing",
        country_code: str = "CH",
        ip_id: str | None = None,
        *,
        tracker_vault: bool = False,
        force_pf: bool = False,
        deep_clean: bool = False,
    ) -> dict[str, Any]:
        """Activate with industrial preflight FIRST, then Suite helpers (import-only)."""
        from shared.pcs_preflight_obfuscation_gate_v20260802 import activate_protected_session
        from shared.pcs_killswitch_industrial_v20260802 import IndustrialKillSwitch, arm_for_activate
        from shared.pcs_session_resume_v20260802 import save_session

        self.current_purpose = purpose
        self.selected_country = country_code.upper()

        # Resolve location + catalog IP: industrial pool first, Suite fallback
        loc_map = self._country_to_location_map()
        if loc_map:
            self.current_location = loc_map.get(self.selected_country, "zurich")
        try:
            pool = self._get_residential_pool(country_code)
            if ip_id:
                entry = pool.get_by_id(ip_id)
                if entry:
                    self.selected_residential_ip = entry
            else:
                tops = pool.top_n(1)
                if tops:
                    self.selected_residential_ip = tops[0]
                    ip_id = tops[0].get("id")
        except Exception:
            # Catalog is optional UX metadata — never block activate on pool load
            pass

        vault_ok = True
        if tracker_vault and self.vault:
            try:
                res = self.vault.hide_google()
                vault_ok = res.get("status") in ("ok", "hidden", "done", None) or bool(res)
                self.google_hidden = True
            except Exception:
                vault_ok = False

        ks = IndustrialKillSwitch()

        def arm():
            # Industry default: auto-on with Activate; conf NOT in /tmp.
            # Single arm path only — auto_arm_killswitch=False below (no double-arm).
            return arm_for_activate(force_apply=force_pf or os.environ.get("PCS_FORCE_PF") == "1")

        def trip(report):
            # Fail-closed UI state only — do NOT re-invoke arm (avoids double-arm races).
            self.kill_switch_armed = True
            self.phantomcloak_active = False
            self.zero_leak_verified = False
            # Refresh conf on disk without applying twice
            try:
                ks.write_rules_file()
            except Exception:
                pass

        # Optional wipe hook: Suite anti_forensics if importable; else gate records wipe_done=False.
        # Detection pipeline: WIPE before protect. deep_clean is retained for API compat
        # (wipe always runs when Suite present; deep_clean=True is same path).
        _wipe_fn: Any = None
        if self.suite and getattr(self.suite, "anti_forensics", None) is not None:
            af = self.suite.anti_forensics

            def _suite_wipe() -> dict[str, Any]:
                af.deep_clean_on_start()
                return {
                    "ok": True,
                    "source": "suite.anti_forensics.deep_clean_on_start",
                    "deep_clean": bool(deep_clean),
                }

            _wipe_fn = _suite_wipe

        # Exit IP for synthetic profile gate (known → score fail blocks protect)
        exit_ip = ""
        if isinstance(self.selected_residential_ip, dict):
            exit_ip = str(
                self.selected_residential_ip.get("ip")
                or self.selected_residential_ip.get("public_ip")
                or ""
            ).strip()

        # Gate order enforced inside activate_protected_session:
        # readiness → optional wipe → synthetic profile → obfuscation → killswitch arm
        # → final verify; never claim protected if any fail
        pre = activate_protected_session(
            tier=self.tier,
            tracker_vault_enabled=tracker_vault,
            tracker_vault_ok=vault_ok,
            killswitch_arm_fn=arm,
            killswitch_trip_fn=trip,
            require_tunnel=False,
            # Explicit: arm only via killswitch_arm_fn (prevents double-arm with auto path)
            auto_arm_killswitch=False,
            force_pf_apply=force_pf or os.environ.get("PCS_FORCE_PF") == "1",
            require_configured_servers=True,
            wipe_fn=_wipe_fn,
            exit_ip=exit_ip,
            location=self.current_location or "",
            purpose=purpose or self.current_purpose or "browsing",
            slot_id=str(ip_id or ""),
        )

        cfg = int(pre.get("configured_count") or 0)

        # HARD: never claim protected when gate fails or configured_count==0
        if not pre.get("protected") or cfg <= 0:
            self.phantomcloak_active = False
            self.zero_leak_verified = False
            save_session(
                {
                    "purpose": purpose,
                    "country": self.selected_country,
                    "location": self.current_location,
                    "country_name": self.current_location.replace("_", " ").title(),
                    "tier": self.tier,
                    "catalog_ip_id": ip_id,
                    "residential_ip": self.selected_residential_ip,
                    "active": False,
                    "protected": False,
                    "killswitch": True,
                    "preflight": pre.get("report"),
                    "configured_count": cfg,
                    "server_filled_count": pre.get("server_filled_count"),
                    "pending_ip_count": pre.get("pending_ip_count"),
                    "reason": pre.get("reason") or "preflight_failed",
                },
                configured_count=cfg,
                protected=False,
                allow_protected_claim=False,
            )
            reason = pre.get("reason") or (
                "servers_not_configured" if cfg <= 0 else "preflight_failed"
            )
            if reason == "servers_not_configured" or cfg <= 0:
                msg = pre.get("message") or (
                    "Protected browsing blocked — no client configs with real VPS IPs "
                    "(configured_count=0). Fill inventory + materialize; see HOWTO. "
                    "Status/dashboard/wizard still allowed."
                )
            elif reason == "killswitch_arm_failed":
                msg = pre.get("message") or (
                    "Killswitch arm failed — no protected session (fail-closed)."
                )
            elif reason == "wipe_failed":
                msg = pre.get("message") or (
                    "Wipe hook failed — no protected session (fail-closed)."
                )
            elif reason == "synthetic_profile_gate_failed":
                msg = pre.get("message") or (
                    "Synthetic profile / mimicry gate failed — no protected session "
                    "(fail-closed)."
                )
            elif reason == "preflight_failed":
                stopped = pre.get("gate_stopped_at") or "obfuscation_preflight"
                msg = pre.get("message") or (
                    f"Preflight failed at {stopped} — no protected session (fail-closed)."
                )
            else:
                msg = pre.get("message") or (
                    "Protect path blocked — no protected session (fail-closed)."
                )
            return {
                "status": "blocked",
                "protected": False,
                "reason": reason,
                "message": msg,
                "preflight": pre,
                "configured_count": cfg,
                "server_filled_count": pre.get("server_filled_count", 0),
                "pending_ip_count": pre.get("pending_ip_count", 0),
                "pending": pre.get("pending") or [],
                "server_readiness": pre.get("server_readiness"),
                "next_step": pre.get("next_step"),
                "howto_path": pre.get("howto_path"),
                "inventory_path": pre.get("inventory_path"),
                "gate_stopped_at": pre.get("gate_stopped_at"),
                "gates_passed": pre.get("gates_passed") or [],
                "gate_order": pre.get("gate_order"),
                "wipe_done": pre.get("wipe_done", False),
                "synthetic_profile": pre.get("synthetic_profile"),
                "killswitch_path": ks.conf_location(),
                "honest_copy": "selection saved · not protected",
            }

        self.kill_switch_armed = True
        self.zero_leak_verified = True

        suite_steps: dict[str, Any] = {
            "anti_forensics": (
                "ran" if pre.get("wipe_done") else "skipped_or_unavailable"
            ),
            "wipe_done": bool(pre.get("wipe_done")),
        }
        if self.suite:
            # Wipe already executed inside preflight gate when Suite available
            try:
                sb = self.suite.singbox_manager.SingBoxClientManager()
                config = self.suite.singbox_manager.CONFIG_DIR / f"{self.current_location}.json"
                if not config.exists():
                    # Demo config only — honest about placeholders
                    sb.generate_client_config(
                        self.current_location, "127.0.0.1", "demo-uuid", "demo", "demo"
                    )
                    suite_steps["singbox_config"] = "generated_demo_placeholder"
                else:
                    suite_steps["singbox_config"] = "existing"
                # Start tunnel only if not demo-only unless forced
                if os.environ.get("PCS_START_TUNNEL") == "1":
                    sb.start(self.current_location, config)
                    suite_steps["singbox"] = "started"
                else:
                    suite_steps["singbox"] = "skipped (set PCS_START_TUNNEL=1)"
            except Exception as e:
                suite_steps["singbox"] = f"error:{e}"

            try:
                if os.environ.get("PCS_LAUNCH_BROWSER") == "1":
                    self.suite.browser_launcher.launch_for_location(self.current_location)
                    suite_steps["browser"] = "launched"
                else:
                    suite_steps["browser"] = "skipped (set PCS_LAUNCH_BROWSER=1)"
            except Exception as e:
                suite_steps["browser"] = f"error:{e}"

        self.phantomcloak_active = True
        save_session(
            {
                "purpose": purpose,
                "country": self.selected_country,
                "location": self.current_location,
                "country_name": self.current_location.replace("_", " ").title(),
                "active": True,
                "protected": True,
                "killswitch": True,
                "tier": self.tier,
                "catalog_ip_id": ip_id,
                "residential_ip": self.selected_residential_ip,
                "configured_count": cfg,
                "server_filled_count": pre.get("server_filled_count"),
                "pending_ip_count": pre.get("pending_ip_count"),
                "preflight": pre.get("report"),
            },
            configured_count=cfg,
            protected=True,
            allow_protected_claim=True,
        )

        return {
            "status": "active",
            "protected": True,
            "message": "Protections active · verify recommended",
            "honest_copy": "protections active · verify recommended",
            "tier": self.tier,
            "purpose": purpose,
            "country": self.selected_country,
            "location": self.current_location,
            "ip_id": ip_id,
            "configured_count": cfg,
            "preflight": pre,
            "suite_steps": suite_steps,
            "wipe_done": bool(pre.get("wipe_done")),
            "synthetic_profile": pre.get("synthetic_profile"),
            "gate_order": pre.get("gate_order"),
            "gates_passed": pre.get("gates_passed") or [],
            "killswitch_path": ks.conf_location(),
            "note": "Suite modules imported only; no Suite files written.",
        }

    def deactivate(self) -> dict[str, Any]:
        from shared.pcs_killswitch_industrial_v20260802 import IndustrialKillSwitch
        from shared.pcs_session_resume_v20260802 import save_session

        steps = {}
        try:
            IndustrialKillSwitch().disarm()
            steps["killswitch"] = "disarmed"
        except Exception as e:
            steps["killswitch"] = str(e)
        if self.vault and self.google_hidden:
            try:
                self.vault.restore_google()
                self.google_hidden = False
                steps["tracker_vault"] = "restored"
            except Exception as e:
                steps["tracker_vault"] = str(e)
        self.phantomcloak_active = False
        self.kill_switch_armed = False
        self.zero_leak_verified = False
        catalog_id = None
        if isinstance(self.selected_residential_ip, dict):
            catalog_id = self.selected_residential_ip.get("id")
        save_session(
            {
                "purpose": self.current_purpose,
                "country": self.selected_country,
                "location": self.current_location,
                "country_name": self.current_location.replace("_", " ").title(),
                "active": False,
                "protected": False,
                "killswitch": False,
                "tier": self.tier,
                "catalog_ip_id": catalog_id,
                "residential_ip": self.selected_residential_ip,
                "configured_count": 0,  # re-checked on next protect; not a live claim
            },
            configured_count=0,
            protected=False,
            allow_protected_claim=False,
        )
        return {"status": "inactive", "steps": steps}

    def apply_resume_selection(self, session: dict[str, Any] | None = None) -> dict[str, Any]:
        """Restore purpose/country/tier/catalog into shell state (no protect claim)."""
        from shared.pcs_session_resume_v20260802 import extract_selection, load_session
        from shared.pcs_tier_catalog_v20260802 import normalize, label

        s = session if session is not None else load_session(honest=True)
        sel = extract_selection(s)
        self.current_purpose = sel.get("purpose") or "browsing"
        self.selected_country = (sel.get("country") or "CH").upper()
        self.current_location = sel.get("location") or "zurich"
        self.tier = normalize(sel.get("tier") or self.tier)
        self.tier_label = label(self.tier)
        catalog_id = sel.get("catalog_ip_id")
        if catalog_id:
            try:
                pool = self._get_residential_pool(self.selected_country)
                entry = pool.get_by_id(catalog_id)
                if entry:
                    self.selected_residential_ip = entry
            except Exception:
                # Catalog optional — selection id still retained for activate(ip_id=)
                self.selected_residential_ip = sel.get("residential_ip")
        elif sel.get("residential_ip"):
            self.selected_residential_ip = sel.get("residential_ip")
        # Never mark protected from disk
        self.phantomcloak_active = False
        self.zero_leak_verified = False
        return sel

    def resume_last(self, **kwargs) -> dict[str, Any]:
        """One-tap resume: restore selection, then re-run readiness+preflight via activate.

        Disk never authorizes protected=true. activate() always re-gates.
        """
        from shared.pcs_session_resume_v20260802 import (
            activate_kwargs_from_session,
            load_session,
            resume_label,
        )

        s = load_session(honest=True) or {
            "purpose": "browsing",
            "country": "CH",
            "location": "zurich",
            "country_name": "Zurich",
            "tier": self.tier,
        }
        selection = self.apply_resume_selection(s)
        act_kwargs = activate_kwargs_from_session(selection)
        # kwargs (CLI flags) override except we never skip preflight
        act_kwargs.update(kwargs)
        result = self.activate(**act_kwargs)
        return {
            "label": resume_label(selection),
            "selection": selection,
            "requires_preflight": True,
            "requires_readiness": True,
            "protected": bool(result.get("protected")),
            "result": result,
            "honest_copy": (
                "protections active · verify recommended"
                if result.get("protected")
                else "selection restored · preflight refused protected"
            ),
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PCS Industrial app shell")
    p.add_argument("--tier", default=os.environ.get("PCS_TIER", "core"), choices=["core", "pro"])
    p.add_argument("--status", action="store_true")
    p.add_argument("--features", action="store_true")
    p.add_argument("--activate", nargs=2, metavar=("PURPOSE", "COUNTRY"), help="e.g. browsing CH")
    p.add_argument("--resume", action="store_true", help="One-tap resume last session")
    p.add_argument("--deactivate", action="store_true")
    p.add_argument("--tracker-vault", action="store_true")
    p.add_argument("--force-pf", action="store_true")
    p.add_argument("--serve-payments", type=int, metavar="PORT", help="HTTP payment landing API")
    p.add_argument(
        "--serve-dashboard",
        type=int,
        nargs="?",
        const=8790,
        metavar="PORT",
        help="Serve industrial Command Center + /api/status (default port 8790)",
    )
    p.add_argument(
        "--open-dashboard",
        action="store_true",
        help="With --serve-dashboard, open browser to Command Center",
    )
    args = p.parse_args(argv)

    shell = PcsAppShell(tier=args.tier)

    if args.serve_dashboard is not None:
        from core_product.pcs_dashboard_server_v20260802 import serve as serve_dashboard

        serve_dashboard(
            args.serve_dashboard,
            tier=args.tier,
            open_browser=bool(args.open_dashboard),
        )
        return 0

    if args.serve_payments:
        from shared.pcs_payments_http_v20260802 import serve

        serve(args.serve_payments)
        return 0

    if args.status or (not args.activate and not args.resume and not args.deactivate and not args.features):
        print(json.dumps(shell.status(), indent=2, default=str))
    if args.features:
        print(json.dumps(shell.feature_inventory(), indent=2, default=str))
    if args.resume:
        print(json.dumps(shell.resume_last(
            tracker_vault=args.tracker_vault,
            force_pf=args.force_pf,
        ), indent=2, default=str))
    if args.activate:
        purpose, country = args.activate
        print(json.dumps(shell.activate(
            purpose, country,
            tracker_vault=args.tracker_vault,
            force_pf=args.force_pf,
        ), indent=2, default=str))
    if args.deactivate:
        print(json.dumps(shell.deactivate(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
