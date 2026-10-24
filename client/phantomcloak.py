#!/usr/bin/env python3
"""
PhantomCloak — DSI/VPN Command Center
Rich HTML dashboard via pywebview + menubar fallback.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))


def _set_process_name(name: str = "PhantomCloak") -> None:
    """Show PhantomCloak in Dock / Cmd+Tab instead of Python."""
    try:
        from Foundation import NSProcessInfo
        NSProcessInfo.processInfo().setProcessName_(name)
    except Exception:
        pass
    try:
        import ctypes
        libc = ctypes.CDLL(None)
        if hasattr(libc, "setprogname"):
            libc.setprogname(name.encode())
    except Exception:
        pass


_set_process_name()

try:
    import webview
    HAS_WEBVIEW = True
except ImportError:
    HAS_WEBVIEW = False

try:
    import rumps
    HAS_RUMPS = True
except ImportError:
    HAS_RUMPS = False

from client.core.purpose_catalog import get_purposes, get_countries_for_purpose
from client.core.residential_pool import get_pool, COUNTRY_TO_LOCATION
from client.core.status_monitor import StatusMonitor
from client.core.tracker_vault import TrackerVault
from client.core.account_manager import AccountManager
from client.core.content_catalog import get_services_for_purpose
from client.core.translation_engine import TranslationEngine
from client.core.security_audit import run_audit
from client.core.health_harness import HealthHarness, run_harness
from client.core import tier as tier_mod
from client.core import entitlement as entitlement_mod
from client.core import zeroleak_verifier as zeroleak
from client.core import crypto_payments as crypto_payments_mod

STATE_DIR = Path.home() / ".phantomcloak-suite"  # Suite build: isolated app/session state
STATE_DIR.mkdir(parents=True, exist_ok=True)

_LAN_CACHE = {"ts": 0.0, "data": None}

WALLETS_FILE = STATE_DIR / "wallets.json"


def _load_wallets():
    """Public receive addresses per asset, operator-supplied via wallets.json.
    Defaults to empty strings so we never ship placeholder addresses that could
    misroute real funds. create_order still issues the per-order tag/payment-id;
    an unconfigured asset is flagged address_configured=False to the UI."""
    try:
        data = json.loads(WALLETS_FILE.read_text())
        return {k: str(data.get(k, "")) for k in crypto_payments_mod.ASSETS}
    except Exception:
        return {k: "" for k in crypto_payments_mod.ASSETS}
SESSION_FILE = STATE_DIR / "last_session.json"


class PhantomCloakAPI:
    """Bridge between dashboard UI and Python backend."""

    def __init__(self, app):
        self.app = app
        self.translator = TranslationEngine()
        self.monitor = StatusMonitor(app, self.translator)
        self.vault = TrackerVault()
        self.accounts = AccountManager()
        self.pre_state_file = STATE_DIR / "pre_phantomcloak_state.json"
        self.pre_state_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_session()

    def _load_session(self):
        if not SESSION_FILE.exists():
            return
        try:
            s = json.loads(SESSION_FILE.read_text())
            self.app.current_purpose = s.get("purpose")
            self.app.selected_country = s.get("country")
            self.app.current_location = s.get("location", self.app.current_location)
            self.app.selected_residential_ip = s.get("residential_ip")
            self.app.phantomcloak_active = s.get("active", False)
            self.app.kill_switch_armed = s.get("killswitch", False)
            self.app.google_hidden = s.get("google_hidden", False)
            self.app.all_trackers_hidden = s.get("all_trackers_hidden", False)
            self.app.double_onion_enabled = s.get("double_onion", False)
            self.app.local_network_access = s.get("local_network_access", True)
            lang = s.get("broadcast_language")
            if lang:
                self.translator.set_language(lang, s.get("auto_translate", True))
        except Exception:
            pass

    def _save_session(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps({
            "purpose": self.app.current_purpose,
            "country": self.app.selected_country,
            "location": self.app.current_location,
            "residential_ip": self.app.selected_residential_ip,
            "active": self.app.phantomcloak_active,
            "killswitch": self.app.kill_switch_armed,
            "google_hidden": self.app.google_hidden,
            "all_trackers_hidden": self.app.all_trackers_hidden,
            "double_onion": self.app.double_onion_enabled,
            "local_network_access": getattr(self.app, "local_network_access", True),
            "broadcast_language": self.translator.target_lang,
            "auto_translate": self.translator.auto_translate,
            "saved_at": datetime.now().isoformat(),
        }, indent=2))
        # deepcheck/security: session may include residential IP metadata — owner-only
        try:
            SESSION_FILE.chmod(0o600)
            STATE_DIR.chmod(0o700)
        except OSError:
            pass

    def get_status(self):
        return self.monitor.get_status()

    def get_entitlement(self):
        return entitlement_mod.check_entitlement().to_dict()

    def get_tier_info(self):
        e = entitlement_mod.check_entitlement()
        active_tier = tier_mod.resolve_tier(e.tier)
        return {
            "tier": active_tier,
            "label": tier_mod.tier_label(active_tier),
            "unlocked": entitlement_mod.is_unlocked(e),
            "features": tier_mod.feature_map(active_tier),
        }

    def run_zeroleak(self):
        def _on_fail(report):
            try:
                from client.core import killswitch
                if hasattr(killswitch, "engage"):
                    killswitch.engage()
            except Exception:
                pass
        return zeroleak.arm(on_failure=_on_fail).to_dict()

    def get_translation_config(self):
        return self.translator.get_config()

    def set_broadcast_language(self, lang_code: str, auto_translate: bool = True):
        result = self.translator.set_language(lang_code, auto_translate)
        if result.get("status") == "ok":
            self.translator.apply_browser_locale(self.app.current_location)
            self._save_session()
        return result

    def get_content_services(self, purpose: str = None):
        purpose = purpose or self.app.current_purpose or "other"
        catalog = get_services_for_purpose(purpose)
        if self.translator.auto_translate and self.translator.target_lang != "en":
            catalog = dict(catalog)
            catalog["title"] = self.translator.translate(catalog["title"])
            catalog["sections"] = [
                {
                    "label": self.translator.translate(sec["label"]),
                    "services": self.translator.translate_services(sec["services"]),
                }
                for sec in catalog["sections"]
            ]
        catalog["purpose"] = purpose
        catalog["protected"] = self.app.phantomcloak_active
        return catalog

    def open_service_url(self, url: str):
        from client.core import browser_launcher
        if not self.app.phantomcloak_active:
            return {"status": "error", "message": "Activate PhantomCloak first"}
        return browser_launcher.open_url(self.app.current_location, url)

    def get_purposes(self):
        purposes = get_purposes()
        if self.translator.auto_translate and self.translator.target_lang != "en":
            return {
                k: {
                    "label": self.translator.translate(v["label"]),
                    "icon": v["icon"],
                    "description": self.translator.translate(v["description"]),
                }
                for k, v in purposes.items()
            }
        return purposes

    def get_countries(self, purpose: str):
        return get_countries_for_purpose(purpose)

    def get_residential_ips(self, country_code: str, limit: int = 15):
        pool = get_pool(country_code)
        return pool.top_n(limit)

    def select_residential_ip(self, country_code: str, ip_id: str):
        pool = get_pool(country_code)
        entry = pool.get_by_id(ip_id)
        if entry:
            self.app.selected_residential_ip = entry
            self.app.selected_country = country_code
            loc = COUNTRY_TO_LOCATION.get(country_code.upper(), "vancouver")
            self.app.current_location = loc
            self._save_session()
            return {"status": "selected", "ip": entry}
        return {"status": "error", "message": "IP not found"}

    def _save_pre_state(self):
        state = {"saved_at": datetime.now().isoformat()}
        try:
            for service in ["Wi-Fi", "Ethernet"]:
                res = subprocess.run(
                    ["networksetup", "-getdnsservers", service],
                    capture_output=True, text=True, timeout=5,
                )
                if "there aren't any" not in res.stdout.lower():
                    state[f"dns_{service}"] = res.stdout.strip()
            pf_status = subprocess.run(["pfctl", "-s", "info"], capture_output=True, text=True)
            state["pf_enabled"] = "Enabled" in pf_status.stdout
            self.pre_state_file.write_text(json.dumps(state, indent=2))
        except Exception as e:
            state["partial_error"] = str(e)
            self.pre_state_file.write_text(json.dumps(state, indent=2))

    def _restore_pre_state(self):
        try:
            if self.pre_state_file.exists():
                state = json.loads(self.pre_state_file.read_text())
                for k, v in state.items():
                    if k.startswith("dns_"):
                        service = k.replace("dns_", "")
                        subprocess.run(
                            ["networksetup", "-setdnsservers", service] + v.split(),
                            check=False,
                        )
            from client.core import killswitch as ks
            ks.KillSwitch().disarm()
            subprocess.run(["pkill", "-f", "sing-box"], check=False)
            subprocess.run(["dscacheutil", "-flushcache"], check=False)
            return {"status": "restored", "message": "Pre-PhantomCloak settings restored"}
        except Exception as e:
            return {"status": "partial", "message": str(e)}

    def activate_phantomcloak(self, purpose: str, country_code: str, ip_id: str):
        self.app.current_purpose = purpose
        self.app.selected_country = country_code
        ip_result = self.select_residential_ip(country_code, ip_id)
        if ip_result.get("status") != "selected":
            return ip_result

        self._save_pre_state()
        from client.core import killswitch as ks_module, anti_forensics, singbox_manager

        ks = ks_module.KillSwitch()
        ks.arm(dry_run=False, force_apply=True)
        self.app.kill_switch_armed = True
        anti_forensics.deep_clean_on_start()

        sb = singbox_manager.SingBoxClientManager()
        config = singbox_manager.CONFIG_DIR / f"{self.app.current_location}.json"
        if not config.exists():
            sb.generate_client_config(self.app.current_location, "127.0.0.1", "demo-uuid", "demo", "demo")
        sb.start(self.app.current_location, config)

        from client.core import browser_launcher
        browser_launcher.launch_for_location(self.app.current_location)
        self.translator.apply_browser_locale(self.app.current_location)

        self.app.phantomcloak_active = True
        self.app.zero_leak_verified = True
        self._save_session()
        msg = self.translator.translate("PhantomCloak protection activated")
        return {
            "status": "active",
            "message": msg,
            "purpose": purpose,
            "navigate_content": True,
        }

    def deactivate_phantomcloak(self):
        self.app.phantomcloak_active = False
        self.app.zero_leak_verified = False
        result = self._restore_pre_state()
        if self.app.google_hidden:
            self.vault.restore_google()
            self.app.google_hidden = False
        if self.app.all_trackers_hidden:
            self.vault.restore_all_trackers()
            self.app.all_trackers_hidden = False
        self.app.kill_switch_armed = False
        self._save_session()
        return {"status": "inactive", "message": "PhantomCloak deactivated", "restore": result}

    def toggle_killswitch(self, enable: bool):
        from client.core import killswitch as ks_module
        ks = ks_module.KillSwitch()
        if enable:
            ks.arm(dry_run=False, force_apply=True)
            self.app.kill_switch_armed = True
        else:
            ks.disarm()
            self.app.kill_switch_armed = False
        self._save_session()
        return {"status": "armed" if enable else "disarmed"}

    def hide_google_trackers(self):
        result = self.vault.hide_google()
        self.app.google_hidden = True
        self.app.data_masked = True
        self._save_session()
        return result

    def restore_google_data(self):
        result = self.vault.restore_google()
        self.app.google_hidden = False
        self._save_session()
        return result

    def hide_all_trackers(self):
        result = self.vault.hide_all_trackers()
        self.app.all_trackers_hidden = True
        self.app.data_masked = True
        self._save_session()
        return result

    def restore_all_trackers(self):
        result = self.vault.restore_all_trackers()
        self.app.all_trackers_hidden = False
        self._save_session()
        return result

    def toggle_double_onion(self, enabled: bool):
        self.app.double_onion_enabled = enabled
        self._save_session()
        return {"enabled": enabled}

    def switch_location(self, country_code: str, ip_id: str = None):
        self.app.selected_country = country_code
        loc = COUNTRY_TO_LOCATION.get(country_code.upper(), "vancouver")
        self.app.current_location = loc
        if ip_id:
            self.select_residential_ip(country_code, ip_id)
        from client.core import singbox_manager
        sb = singbox_manager.SingBoxClientManager()
        sb.start(self.app.current_location)
        self._save_session()
        return {"location": loc, "country": country_code}

    def list_accounts(self):
        return self.accounts.list_accounts()

    def get_cloud_vault_status(self):
        return self.accounts.cloud_status()

    def run_security_audit(self):
        return run_audit(self.app)

    def get_health_panel(self):
        return HealthHarness(self.app).evaluate_all()

    def run_health_harness(self):
        return run_harness(self.app)

    def heal_technique(self, technique_id: str):
        return HealthHarness(self.app).heal(technique_id)

    def heal_all(self):
        return HealthHarness(self.app).heal_all()

    # ── Crypto payments: chain-watch -> mint access code -> entitlement ──
    def payment_assets(self):
        return crypto_payments_mod.supported_assets()

    def payment_quote(self):
        return {f"{t}|{term}": amt
                for (t, term), amt in crypto_payments_mod.TIER_TERMS.items()}

    def payment_create_order(self, tier, term, asset):
        try:
            order = crypto_payments_mod.create_order(tier, term, asset, _load_wallets())
            order["address_configured"] = bool(order.get("payment_target"))
            order["confirms_needed"] = crypto_payments_mod.ASSETS[asset]["confirms"]
            return order
        except Exception as e:
            return {"error": str(e)}

    def payment_status(self, order_id):
        o = crypto_payments_mod._load().get(order_id)
        if not o:
            return {"error": "unknown order"}
        return {"status": o.status, "tier": o.tier, "term": o.term,
                "access_code": o.access_code if o.status == "activated" else None}

    def payment_redeem(self, code):
        r = crypto_payments_mod.redeem_access_code((code or "").strip().upper())
        if not r.get("valid"):
            msg = ("This code was already redeemed." if r.get("reason") == "already_redeemed"
                   else "Invalid or unrecognized access code.")
            return {"ok": False, "message": msg}
        e = entitlement_mod.grant_from_purchase(r["tier"], r["term"], source="purchase")
        return {"ok": True, "tier": e.tier, "term": r["term"], "expires": e.expires}

    def payment_dev_confirm(self, order_id):
        """DEV ONLY: simulate on-chain confirmation so the redeem->entitlement
        flow is testable locally. Production confirmation is driven by a backend
        indexer/processor webhook calling confirm_payment server-side."""
        import os as _os
        if _os.environ.get("PHANTOMCLOAK_DEV") != "1":
            return {"error": "dev only"}
        o = crypto_payments_mod._load().get(order_id)
        if not o:
            return {"error": "unknown order"}
        need = crypto_payments_mod.ASSETS[o.asset]["confirms"]
        return crypto_payments_mod.confirm_payment(order_id, "DEV-LOCAL-TX", need, True)

    def save_account(self, name, purpose, country, country_name, ip_id, password=None):
        pool = get_pool(country)
        ip = pool.get_by_id(ip_id) or {}
        result = self.accounts.save_account(name, purpose, country, country_name, ip, password)
        if isinstance(result, dict) and result.get("id"):
            self.accounts.set_active(result["id"])
            result["active"] = result["id"]
        return result

    def load_account(self, account_id, password=None):
        result = self.accounts.load_account(account_id, password)
        if result.get("status") == "loaded":
            acct = result["account"]
            self.app.current_purpose = acct.get("purpose")
            self.app.selected_country = acct.get("country")
            self.app.selected_residential_ip = acct.get("residential_ip")
            loc = COUNTRY_TO_LOCATION.get(acct.get("country", "").upper(), "vancouver")
            self.app.current_location = loc
            self._save_session()
        return result

    def get_active_account(self):
        aid = self.accounts.get_active()
        if not aid:
            return {"active": None}
        for a in self.accounts.list_accounts():
            if a.get("id") == aid:
                return {"active": aid, "account": a}
        return {"active": aid}

    def logout_account(self):
        return self.accounts.logout()

    def killswitch_arm(self):
        from client.core import killswitch_privileged as kp
        return kp.arm(local_network=getattr(self.app, "local_network_access", True))

    def killswitch_disarm(self):
        from client.core import killswitch_privileged as kp
        return kp.disarm()

    def killswitch_status(self):
        from client.core import killswitch_privileged as kp
        return kp.status()

    def lan_gateway_check(self):
        """Live LAN health: find the default gateway and ping it once. Cached ~8s
        so it never pings on every status refresh. Returns gateway, reachable, ms."""
        import subprocess, re, time
        now = time.time()
        if _LAN_CACHE["data"] is not None and now - _LAN_CACHE["ts"] < 8:
            return _LAN_CACHE["data"]
        gw = None
        try:
            out = subprocess.run(["route", "-n", "get", "default"],
                                 capture_output=True, text=True, timeout=2).stdout
            for line in out.splitlines():
                ls = line.strip()
                if ls.startswith("gateway:"):
                    gw = ls.split(":", 1)[1].strip()
                    break
        except Exception:
            gw = None
        reachable, latency = False, None
        if gw:
            try:
                r = subprocess.run(["ping", "-c", "1", "-t", "2", gw],
                                   capture_output=True, text=True, timeout=3)
                reachable = (r.returncode == 0)
                m = re.search(r"time=([\d.]+)", r.stdout or "")
                if m:
                    latency = round(float(m.group(1)), 1)
            except Exception:
                reachable = False
        data = {"gateway": gw, "reachable": reachable, "latency_ms": latency}
        _LAN_CACHE["ts"], _LAN_CACHE["data"] = now, data
        return data

    def get_local_network_access(self):
        return {"enabled": bool(getattr(self.app, "local_network_access", True))}

    def set_local_network_access(self, enabled: bool):
        """Toggle the LAN exemption. If the kill switch is currently armed, the
        pf ruleset is rebuilt and re-applied immediately so casting/AirPlay start
        (or stop) working right away — no reconnect needed."""
        from client.core import killswitch_privileged as kp
        self.app.local_network_access = bool(enabled)
        self._save_session()
        rearmed = False
        st = kp.status()
        if st.get("armed"):
            kp.disarm()
            r = kp.arm(local_network=self.app.local_network_access)
            rearmed = bool(r.get("armed"))
        return {"enabled": self.app.local_network_access, "rearmed": rearmed}

    def safe_reconnect(self):
        from client.core import killswitch as ks_module
        return ks_module.KillSwitch().safe_reconnect()

    def run_verify(self):
        subprocess.Popen([sys.executable, str(BASE_DIR / "scripts" / "verify" / "full_verification_suite.py")])
        return {"status": "verification_started"}

    # Legacy aliases for compatibility
    def toggle_anti_detection_suite(self, enable: bool):
        return self.activate_phantomcloak(
            self.app.current_purpose or "other",
            self.app.selected_country or "CA",
            (self.app.selected_residential_ip or {}).get("id", ""),
        ) if enable else self.deactivate_phantomcloak()

    def return_to_pre_anti_detection_settings(self):
        return self.deactivate_phantomcloak()

    def start_protection(self):
        return self.activate_phantomcloak(
            self.app.current_purpose or "other",
            self.app.selected_country or "CA",
            (self.app.selected_residential_ip or {}).get("id", ""),
        )

    def stop_protection(self):
        return self.deactivate_phantomcloak()


class PhantomCloakApp:
    def __init__(self):
        self.current_location = "vancouver"
        self.current_purpose = None
        self.selected_country = None
        self.selected_residential_ip = None
        self.phantomcloak_active = False
        self.kill_switch_armed = False
        self.double_onion_enabled = False
        self.local_network_access = True  # allow LAN (AirPlay/cast/mDNS) by default
        self.zero_leak_verified = False
        self.google_hidden = False
        self.all_trackers_hidden = False
        self.data_masked = False

    def run_dashboard(self):
        if not HAS_WEBVIEW:
            print("Install pywebview: pip install pywebview")
            return
        html_path = BASE_DIR / "client" / "ui" / "dashboard.html"
        api = PhantomCloakAPI(self)
        webview.create_window(
            "PhantomCloak",
            str(html_path),
            js_api=api,
            width=1360,
            height=920,
            min_size=(1120, 760),
            resizable=True,
            background_color="#05040c",
        )
        webview.start(debug=False)

    def run(self):
        print("Starting PhantomCloak…")
        self.run_dashboard()


if __name__ == "__main__":
    PhantomCloakApp().run()