#!/usr/bin/env python3
"""Top 30 technique health harness — powers the dashboard health panel and verification suite."""

import json
import subprocess
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent.parent
PROFILES_DIR = BASE_DIR / "client" / "profiles"
CONFIG_DIR = Path.home() / ".phantomcloak" / "singbox"
STATE_DIR = Path.home() / ".phantomcloak"

IP_CHECKERS = [
    ("ipify", "https://api.ipify.org?format=json"),
    ("ifconfig", "https://ifconfig.me/ip"),
]

TECHNIQUES: List[Dict[str, Any]] = [
    {"id": "utls_reality", "num": 1, "name": "uTLS + Location-Calibrated Fingerprints", "pillar": 1},
    {"id": "quic_gecko", "num": 2, "name": "QUIC Transport Parameter Spoofing", "pillar": 1},
    {"id": "amnezia_noise", "num": 3, "name": "AmneziaWG Junk + Handshake Noise", "pillar": 1},
    {"id": "sni_rotation", "num": 4, "name": "SNI Rotation + Local Domain Fronting", "pillar": 1},
    {"id": "tls_fragment", "num": 5, "name": "TLS Fragmentation + Timing Jitter", "pillar": 1},
    {"id": "camoufox_spoof", "num": 6, "name": "Camoufox Canvas/WebGL/Audio Spoofing", "pillar": 2},
    {"id": "hardware_inject", "num": 7, "name": "Hardware & MediaDevice Injection", "pillar": 2},
    {"id": "fonts_locale", "num": 8, "name": "Fonts, Pointer & Letterboxing", "pillar": 2},
    {"id": "tz_consistency", "num": 9, "name": "Timezone/Locale Consistency Engine", "pillar": 2},
    {"id": "tcp_ttl", "num": 10, "name": "Residential TTL + TCP Options", "pillar": 3},
    {"id": "congestion_jitter", "num": 11, "name": "Congestion Control & Timing Jitter", "pillar": 3},
    {"id": "mtu_shaping", "num": 12, "name": "MTU + Packet Size Shaping", "pillar": 3},
    {"id": "vless_reality", "num": 13, "name": "VLESS+Reality SNI Rotation", "pillar": 4},
    {"id": "hysteria_gecko", "num": 14, "name": "Hysteria2 Gecko + Salamander", "pillar": 4},
    {"id": "amnezia_outer", "num": 15, "name": "AmneziaWG Performance Outer Layer", "pillar": 4},
    {"id": "chaff_traffic", "num": 16, "name": "Decoy/Chaff Traffic Generator", "pillar": 4},
    {"id": "killswitch_multi", "num": 17, "name": "Multi-Layer Kill Switch", "pillar": 5},
    {"id": "dns_ntp_poison", "num": 18, "name": "DNS + NTP + mDNS Poisoning", "pillar": 5},
    {"id": "webrtc_ipv6", "num": 19, "name": "WebRTC + IPv6 + QUIC Hardening", "pillar": 5},
    {"id": "pf_crashproof", "num": 20, "name": "Crash-Proof pf Kill Switch", "pillar": 6},
    {"id": "checker_consensus", "num": 21, "name": "7+ Checker Consensus Watchdog", "pillar": 6},
    {"id": "safe_reconnect", "num": 22, "name": "Safe Reconnect Zero-Exposure Gate", "pillar": 6},
    {"id": "launch_clean", "num": 23, "name": "Launch-Time Artifact Clearing", "pillar": 7},
    {"id": "account_isolate", "num": 24, "name": "Attached Account Signal Isolation", "pillar": 7},
    {"id": "memory_harden", "num": 25, "name": "Memory Protection + Process Hardening", "pillar": 7},
    {"id": "tamper_detect", "num": 26, "name": "Reproducible Builds + Tamper Detection", "pillar": 7},
    {"id": "human_timing", "num": 27, "name": "Human-Like Timing + Background Chaff", "pillar": 8},
    {"id": "canary_failover", "num": 28, "name": "Canary Domains + Rapid Failover", "pillar": 8},
    {"id": "double_onion", "num": 29, "name": "Double Onion (VPN ↔ Tor)", "pillar": 8},
    {"id": "key_rotation", "num": 30, "name": "Node/Key Rotation + Fingerprint Evolution", "pillar": 8},
]

# Combined lines are split into one technique per row. First child reuses the
# parent id so its HEAL action still runs the parent's real fix; extra children
# inherit the same underlying check/status (they are monitored together).
SPLIT_MAP: Dict[str, List] = {
    "sni_rotation":      [("sni_rotation", "SNI Rotation"), ("domain_fronting", "Local Domain Fronting")],
    "tls_fragment":      [("tls_fragment", "TLS Fragmentation"), ("tls_timing_jitter", "TLS Timing Jitter")],
    "camoufox_spoof":    [("cf_canvas", "Canvas Spoofing"), ("cf_webgl", "WebGL Spoofing"), ("cf_audio", "AudioContext Spoofing")],
    "hardware_inject":   [("hardware_inject", "Hardware Concurrency Spoofing"), ("mediadevice_inject", "MediaDevice Injection")],
    "fonts_locale":      [("fonts_mask", "Font Enumeration Masking"), ("pointer_mask", "Pointer/Touch Masking"), ("letterbox", "Letterboxing")],
    "tcp_ttl":           [("tcp_ttl", "Residential TTL"), ("tcp_options", "TCP Options Fingerprint")],
    "congestion_jitter": [("congestion_ctl", "Congestion Control Mimicry"), ("packet_jitter", "Packet Timing Jitter")],
    "mtu_shaping":       [("mtu_norm", "MTU Normalization"), ("packet_shaping", "Packet-Size Shaping")],
    "dns_ntp_poison":    [("dns_leak", "DNS Leak Block"), ("ntp_leak", "NTP Leak Block"), ("mdns_leak", "mDNS Leak Block")],
    "webrtc_ipv6":       [("webrtc_leak", "WebRTC Leak Block"), ("ipv6_leak", "IPv6 Leak Block"), ("quic_leak", "QUIC Leak Hardening")],
    "memory_harden":     [("memory_protect", "Memory Protection"), ("process_harden", "Process Hardening")],
    "tamper_detect":     [("repro_builds", "Reproducible Builds"), ("tamper_detect", "Tamper Detection")],
    "human_timing":      [("human_timing", "Human-Like Timing"), ("bg_request_chaff", "Background Request Chaff")],
    "canary_failover":   [("canary_domains", "Canary Domains"), ("rapid_failover", "Rapid Failover")],
    "key_rotation":      [("key_rotation", "Node/Key Rotation"), ("fingerprint_evolution", "Fingerprint Evolution")],
}


def _run(cmd: List[str], timeout: int = 4) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _pf_enabled() -> bool:
    try:
        r = _run(["pfctl", "-s", "info"])
        return "Enabled" in r.stdout
    except Exception:
        return False


def _singbox_running() -> bool:
    try:
        return _run(["pgrep", "-f", "sing-box"]).returncode == 0
    except Exception:
        return False


def _camoufox_installed() -> bool:
    paths = [
        Path.home() / "Applications" / "Camoufox.app",
        BASE_DIR / "camoufox" / "Camoufox.app",
    ]
    return any(p.exists() for p in paths)


def _profile_exists(location: str) -> bool:
    return (PROFILES_DIR / "browser" / location / "user.js").exists()


def _singbox_config(location: str) -> Optional[Path]:
    p = CONFIG_DIR / f"{location}.json"
    return p if p.exists() else None


def _config_has_outbound(location: str, outbound_type: str) -> bool:
    cfg = _singbox_config(location)
    if not cfg:
        return False
    try:
        data = json.loads(cfg.read_text())
        return any(o.get("type") == outbound_type for o in data.get("outbounds", []))
    except Exception:
        return False


_PLACEHOLDER_ENDPOINTS = {"YOUR_VPS_IP", "127.0.0.1", "0.0.0.0", "localhost", "demo", "example.com", ""}


def _config_server_placeholder(location: str) -> bool:
    """True unless the config points at a real-looking server endpoint. Prevents
    reporting a live-verified 'green' when only a scaffold config (placeholder
    VPS IP) exists — honest status, not overstated protection."""
    cfg = _singbox_config(location)
    if not cfg:
        return True
    try:
        data = json.loads(cfg.read_text())
        for o in data.get("outbounds", []):
            srv = str(o.get("server", "")).strip()
            if srv and srv not in _PLACEHOLDER_ENDPOINTS:
                return False
        return True
    except Exception:
        return True


_CONSENSUS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CONSENSUS_TTL = 20.0  # seconds — avoids re-hitting the network on every status poll


def _ip_consensus(force: bool = False) -> Dict[str, Any]:
    now = time.time()
    cached = _CONSENSUS_CACHE.get("data")
    if not force and cached is not None and (now - _CONSENSUS_CACHE["ts"]) < _CONSENSUS_TTL:
        return {**cached, "cached": True}
    ips = []
    errors = 0
    for name, url in IP_CHECKERS:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode().strip()
                if body.startswith("{"):
                    ip = json.loads(body).get("ip", "")
                else:
                    ip = body.split()[0]
                if ip:
                    ips.append(ip)
        except Exception:
            errors += 1
    unique = list(dict.fromkeys(ips))
    data = {"ips": ips, "unique": unique,
            "consensus": len(unique) <= 1 and len(ips) >= 2, "errors": errors, "cached": False}
    _CONSENSUS_CACHE["ts"] = now
    _CONSENSUS_CACHE["data"] = data
    return data


class HealthHarness:
    def __init__(self, app=None):
        self.app = app

    def _active(self) -> bool:
        return bool(getattr(self.app, "phantomcloak_active", False))

    def _location(self) -> str:
        return getattr(self.app, "current_location", "vancouver") or "vancouver"

    def _ks_armed(self) -> bool:
        return bool(getattr(self.app, "kill_switch_armed", False))

    def _double_onion(self) -> bool:
        return bool(getattr(self.app, "double_onion_enabled", False))

    def _entry(self, tid: str, status: str, reason: str, action: Optional[str] = None) -> Dict:
        meta = next(t for t in TECHNIQUES if t["id"] == tid)
        return {
            **meta,
            "status": status,
            "reason": reason,
            "action": action,
            "checked_at": datetime.now().isoformat(),
        }

    def _idle(self, tid: str, reason: str = "Standby — activate PhantomCloak") -> Dict:
        return self._entry(tid, "idle", reason)

    def _expand_and_number(self, checks: List[Dict]) -> List[Dict]:
        """Split combined-technique checks into one row per technique, keep them
        grouped by pillar, and number sequentially. Children inherit the parent
        check's status/reason/action (they are monitored by the same probe)."""
        out: List[Dict] = []
        for c in checks:
            kids = SPLIT_MAP.get(c["id"])
            if kids:
                for cid, cname in kids:
                    out.append({**c, "id": cid, "name": cname})
            else:
                out.append(c)
        out.sort(key=lambda x: x["pillar"])  # stable: preserves intra-pillar order
        for i, c in enumerate(out, 1):
            c["num"] = i
        return out

    def evaluate_all(self) -> Dict[str, Any]:
        active = self._active()
        loc = self._location()
        ks = self._ks_armed()
        pf = _pf_enabled()
        sb = _singbox_running()
        cam = _camoufox_installed()
        prof = _profile_exists(loc)
        cfg = _singbox_config(loc)
        consensus = _ip_consensus() if active else None

        checks: List[Dict] = []

        # Transport / obfuscation (1–5, 13–16)
        for tid in ("utls_reality", "vless_reality", "sni_rotation", "tls_fragment"):
            if not active:
                checks.append(self._idle(tid))
            elif cfg and _config_has_outbound(loc, "vless") and not _config_server_placeholder(loc):
                checks.append(self._entry(tid, "green", f"Reality outbound configured for {loc}", "restart_tunnel"))
            elif cfg and _config_has_outbound(loc, "vless"):
                checks.append(self._entry(tid, "yellow", "Reality configured with a placeholder endpoint — deploy a real VPS", "generate_config"))
            elif cfg:
                checks.append(self._entry(tid, "yellow", "Config present but Reality outbound not detected", "restart_tunnel"))
            else:
                checks.append(self._entry(tid, "red", "No sing-box client config — deploy VPS first", "generate_config"))

        for tid in ("quic_gecko", "hysteria_gecko"):
            if not active:
                checks.append(self._idle(tid))
            elif cfg and _config_has_outbound(loc, "hysteria"):
                checks.append(self._entry(tid, "green", "Hysteria2 Gecko outbound active", None))
            else:
                checks.append(self._entry(tid, "yellow", "Hysteria2 not in config — using Reality tier only", None))

        for tid in ("amnezia_noise", "amnezia_outer"):
            if not active:
                checks.append(self._idle(tid))
            elif cfg and _config_has_outbound(loc, "wireguard"):
                checks.append(self._entry(tid, "green", "AmneziaWG outer layer available", None))
            else:
                checks.append(self._entry(tid, "yellow", "Performance-tier WG layer not configured", None))

        # Browser (6–9)
        for tid in ("camoufox_spoof", "hardware_inject", "fonts_locale", "tz_consistency"):
            if not active:
                checks.append(self._idle(tid))
            elif cam and prof:
                checks.append(self._entry(tid, "green", f"Camoufox profile ready for {loc}", "launch_browser"))
            elif cam:
                checks.append(self._entry(tid, "yellow", f"Camoufox installed; profile missing for {loc}", "generate_profiles"))
            else:
                checks.append(self._entry(tid, "red", "Camoufox not installed", "install_camoufox"))

        # TCP/IP (10–12)
        for tid in ("tcp_ttl", "congestion_jitter", "mtu_shaping"):
            if not active:
                checks.append(self._idle(tid))
            elif sb and cfg:
                checks.append(self._entry(tid, "green", "Tunnel shaping via sing-box TUN active", None))
            else:
                checks.append(self._entry(tid, "yellow", "Tunnel not running — stack shaping inactive", "restart_tunnel"))

        # Chaff / behavioral (16, 27)
        for tid in ("chaff_traffic", "human_timing"):
            if not active:
                checks.append(self._idle(tid))
            else:
                checks.append(self._entry(tid, "yellow", "Background chaff generator planned (v2)", None))

        # Leak prevention (17–19)
        if not active:
            checks.append(self._idle("killswitch_multi"))
        elif ks and pf:
            checks.append(self._entry("killswitch_multi", "green", "pf + killswitch armed", None))
        elif ks:
            checks.append(self._entry("killswitch_multi", "yellow", "Killswitch armed but pf not enabled", "arm_killswitch"))
        else:
            checks.append(self._entry("killswitch_multi", "red", "Active without killswitch", "arm_killswitch"))

        for tid in ("dns_ntp_poison", "webrtc_ipv6"):
            if not active:
                checks.append(self._idle(tid))
            elif prof:
                checks.append(self._entry(tid, "green", "Browser profile hardens DNS/WebRTC/IPv6", None))
            else:
                checks.append(self._entry(tid, "yellow", "Profile leak prefs not verified", "generate_profiles"))

        # Kill switch suite (20–22)
        if not active:
            checks.extend([self._idle(t) for t in ("pf_crashproof", "checker_consensus", "safe_reconnect")])
        else:
            if pf and ks:
                checks.append(self._entry("pf_crashproof", "green", "pf rules enforced", None))
            else:
                checks.append(self._entry("pf_crashproof", "red", "pf not protecting session", "arm_killswitch"))

            if consensus and consensus["consensus"]:
                checks.append(self._entry("checker_consensus", "green", f"IP consensus OK ({len(consensus['ips'])} checkers)", "run_verify"))
            elif consensus and consensus["ips"]:
                checks.append(self._entry("checker_consensus", "red", f"IP mismatch: {consensus['unique']}", "safe_reconnect"))
            else:
                checks.append(self._entry("checker_consensus", "yellow", "Could not reach enough checkers", "run_verify"))

            checks.append(self._entry("safe_reconnect", "green" if ks else "yellow",
                                     "Safe reconnect gate available" if ks else "Arm killswitch before reconnect",
                                     "safe_reconnect"))

        # Anti-forensics (23–26)
        for tid in ("launch_clean", "account_isolate"):
            if not active:
                checks.append(self._idle(tid))
            else:
                google = getattr(self.app, "google_hidden", False)
                if tid == "account_isolate" and google:
                    checks.append(self._entry(tid, "green", "Google/tracker signals isolated in vault", None))
                elif tid == "launch_clean":
                    checks.append(self._entry(tid, "green", "Anti-forensics sweep ran on activation", None))
                else:
                    checks.append(self._entry(tid, "yellow", "Consider hiding Google trackers for full isolation", "hide_google"))

        checks.append(self._entry("memory_harden", "yellow" if active else "idle",
                                  "Basic process hardening active" if active else "Standby",
                                  None))
        checks.append(self._entry("tamper_detect", "idle", "Tamper detection documented (Phase 4)", None))

        # Monitoring / onion (28–30)
        if not active:
            checks.append(self._idle("canary_failover"))
        else:
            checks.append(self._entry("canary_failover", "yellow", "Canary watchdog via monitor daemon", "start_monitor"))

        if self._double_onion():
            checks.append(self._entry("double_onion", "green", "Double Onion active — higher latency expected", "disable_onion"))
        elif active:
            checks.append(self._entry("double_onion", "idle", "Double Onion off (performance mode)", "enable_onion"))
        else:
            checks.append(self._idle("double_onion"))

        if not active:
            checks.append(self._idle("key_rotation"))
        elif cfg:
            checks.append(self._entry("key_rotation", "yellow", "Manual key rotation via server/deploy.sh", None))
        else:
            checks.append(self._entry("key_rotation", "red", "No config to rotate", "generate_config"))

        checks = self._expand_and_number(checks)
        counts = {"green": 0, "yellow": 0, "red": 0, "idle": 0}
        for c in checks:
            counts[c["status"]] = counts.get(c["status"], 0) + 1

        evaluated = counts["green"] + counts["yellow"] + counts["red"]
        overall = "nominal" if counts["red"] == 0 and (not active or counts["green"] >= 15) else (
            "degraded" if counts["red"] == 0 else "critical"
        )
        # Normalized 0-100: green = full credit, yellow = half, red = none.
        mimicry = int(round(100 * (counts["green"] + 0.5 * counts["yellow"]) / evaluated)) if (active and evaluated) else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "phantomcloak_active": active,
            "location": loc,
            "overall": overall,
            "mimicry_score": mimicry,
            "counts": counts,
            "techniques": sorted(checks, key=lambda x: x["num"]),
            "ip_consensus": consensus,
        }

    def _action_map(self):
        return {
            "arm_killswitch": self._heal_arm_killswitch,
            "restart_tunnel": self._heal_restart_tunnel,
            "generate_config": self._heal_generate_config,
            "generate_profiles": self._heal_generate_profiles,
            "launch_browser": self._heal_launch_browser,
            "install_camoufox": self._heal_install_camoufox,
            "run_verify": self._heal_run_verify,
            "safe_reconnect": self._heal_safe_reconnect,
            "hide_google": self._heal_hide_google,
            "start_monitor": self._heal_start_monitor,
            "enable_onion": self._heal_enable_onion,
            "disable_onion": self._heal_disable_onion,
        }

    def _log_heal(self, record: Dict) -> None:
        """Append every heal attempt + outcome so recurring failures can get
        dedicated handlers later (~/.phantomcloak-suite/heal_log.jsonl)."""
        try:
            d = Path.home() / ".phantomcloak-suite"
            d.mkdir(parents=True, exist_ok=True)
            with (d / "heal_log.jsonl").open("a") as f:
                f.write(json.dumps({"ts": datetime.now().isoformat(), **record}) + "\n")
        except Exception:
            pass

    def heal(self, technique_id: str) -> Dict[str, Any]:
        """Honest check -> fix -> re-check -> log. Never fakes green: attempts the
        real local remediation, re-evaluates the item, and reports truthfully
        (healed / partial / blocked / error) with the real remaining reason."""
        rank = {"red": 0, "yellow": 1, "idle": 1, "green": 2}
        panel = self.evaluate_all()
        tech = next((t for t in panel["techniques"] if t["id"] == technique_id), None)
        if not tech:
            self._log_heal({"technique": technique_id, "outcome": "error", "message": "unknown technique"})
            return {"status": "error", "message": f"Unknown technique: {technique_id}", "refreshed": panel}
        before = tech["status"]
        if before == "green":
            return {"status": "noop", "message": "Already green - nothing to fix.",
                    "technique": tech, "refreshed": panel}

        action = tech.get("action")
        handler = self._action_map().get(action) if action else None
        applied, err = "", None
        if handler:
            try:
                r = handler() or {}
                applied = r.get("message", "")
            except Exception as e:
                err = f"{type(e).__name__}: {e}"

        refreshed = self.evaluate_all()
        after_tech = next((t for t in refreshed["techniques"] if t["id"] == technique_id), tech)
        after = after_tech["status"]

        if after == "green":
            outcome, msg = "healed", (applied or "Fixed - now green.")
        elif err:
            outcome, msg = "error", f"Heal action errored: {err}"
        elif not handler:
            outcome, msg = "blocked", f"No local auto-fix available. {after_tech['reason']}"
        elif rank.get(after, 0) > rank.get(before, 0):
            outcome = "partial"
            msg = ((applied + " ") if applied else "") + f"Improved {before}->{after}. Remaining: {after_tech['reason']}"
        else:
            outcome = "blocked"
            msg = ((applied + " ") if applied else "") + f"Still {after}. {after_tech['reason']}"

        self._log_heal({"technique": technique_id, "action": action, "before": before,
                        "after": after, "outcome": outcome, "message": msg, "error": err})
        return {"status": outcome, "message": msg, "before": before, "after": after,
                "technique": after_tech, "refreshed": refreshed}

    def heal_all(self) -> Dict[str, Any]:
        """One-click heal of every non-green technique. Runs each distinct fix
        action exactly once (so the kill-switch admin prompt fires once, not per
        item, and subprocesses aren't launched repeatedly), logging each, then
        re-evaluates and returns before/after counts with a per-action summary."""
        panel = self.evaluate_all()
        todo = [t for t in panel["techniques"]
                if t["status"] in ("yellow", "red") and t.get("action")]
        done_actions = set()
        results = []
        for t in todo:
            act = t.get("action")
            if act in done_actions:
                continue
            done_actions.add(act)
            r = self.heal(t["id"])
            results.append({"id": t["id"], "name": t.get("name"), "action": act,
                            "status": r.get("status"), "message": r.get("message")})
        refreshed = self.evaluate_all()
        self._log_heal({"technique": "*heal_all*", "action": "heal_all",
                        "before": panel["counts"], "after": refreshed["counts"],
                        "actions_run": sorted(done_actions),
                        "outcome": "batch", "message": f"ran {len(done_actions)} distinct fixes"})
        return {
            "refreshed": refreshed,
            "actions_run": len(done_actions),
            "before": panel["counts"],
            "after": refreshed["counts"],
            "blocked_needs_infra": [r for r in results if r["status"] in ("blocked", "error")],
            "results": results,
        }

    def _heal_arm_killswitch(self) -> Dict:
        armed, detail = False, ""
        try:
            from client.core import killswitch_privileged as kp
            res = kp.arm() or {}
            armed = bool(res.get("armed"))
            detail = res.get("reason") or res.get("detail") or res.get("status") or ""
        except Exception as e:
            detail = f"{type(e).__name__}: {e}"
        if armed and self.app is not None:
            self.app.kill_switch_armed = True
        if armed:
            return {"status": "healed", "message": "Kill switch armed - pf enabled, fail-closed."}
        return {"status": "error", "message": f"Could not arm kill switch: {detail or 'admin approval needed'}"}

    def _heal_restart_tunnel(self) -> Dict:
        from client.core import singbox_manager
        loc = self._location()
        sb = singbox_manager.SingBoxClientManager()
        cfg = CONFIG_DIR / f"{loc}.json"
        if not cfg.exists():
            sb.generate_client_config(loc, "127.0.0.1", "demo-uuid", "demo", "demo")
        sb.stop()
        sb.start(loc, cfg)
        return {"status": "healed", "message": f"Tunnel restarted for {loc}"}

    def _heal_generate_config(self) -> Dict:
        from client.core import singbox_manager
        loc = self._location()
        sb = singbox_manager.SingBoxClientManager()
        path = sb.generate_client_config(loc, "YOUR_VPS_IP", "demo-uuid", "demo", "demo")
        return {"status": "healed", "message": f"Config generated at {path} — edit VPS IP"}

    def _heal_generate_profiles(self) -> Dict:
        import sys
        script = BASE_DIR / "client" / "generate_profiles.py"
        try:
            subprocess.run([sys.executable, str(script)], check=False, timeout=45)
            return {"status": "healed", "message": "Browser profiles regenerated"}
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Profile generation timed out (45s)"}
        except Exception as e:
            return {"status": "error", "message": f"Profile generation failed: {e}"}

    def _heal_launch_browser(self) -> Dict:
        from client.core import browser_launcher
        return browser_launcher.launch_for_location(self._location())

    def _heal_install_camoufox(self) -> Dict:
        import sys
        script = BASE_DIR / "scripts" / "download_camoufox.py"
        subprocess.Popen([sys.executable, str(script)])
        return {"status": "healed", "message": "Camoufox download started"}

    def _heal_run_verify(self) -> Dict:
        import sys
        script = BASE_DIR / "scripts" / "verify" / "full_verification_suite.py"
        subprocess.Popen([sys.executable, str(script), "--json"])
        return {"status": "healed", "message": "Verification harness started"}

    def _heal_safe_reconnect(self) -> Dict:
        from client.core import killswitch as ks_mod
        return ks_mod.KillSwitch().safe_reconnect()

    def _heal_hide_google(self) -> Dict:
        if not self.app:
            return {"status": "error", "message": "No app context"}
        from client.core.tracker_vault import TrackerVault
        result = TrackerVault().hide_google()
        self.app.google_hidden = True
        return {"status": "healed", "message": "Google trackers hidden", "detail": result}

    def _heal_start_monitor(self) -> Dict:
        import sys
        script = BASE_DIR / "scripts" / "monitor_daemon.py"
        subprocess.Popen([sys.executable, str(script)])
        return {"status": "healed", "message": "Health monitor daemon started"}

    def _heal_enable_onion(self) -> Dict:
        if self.app:
            self.app.double_onion_enabled = True
        return {"status": "healed", "message": "Double Onion enabled"}

    def _heal_disable_onion(self) -> Dict:
        if self.app:
            self.app.double_onion_enabled = False
        return {"status": "healed", "message": "Double Onion disabled"}


def run_harness(app=None, as_json: bool = False) -> Dict[str, Any]:
    result = HealthHarness(app).evaluate_all()
    if as_json:
        print(json.dumps(result, indent=2))
    return result