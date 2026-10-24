#!/usr/bin/env python3
"""
PhantomCloak — Persistent Health Monitoring Daemon

Watches Top 30 techniques, kill switch, and tunnel health via the health harness.
Intended to run via launchd (com.phantomcloak.monitor.plist).
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from client.core import killswitch
from client.core.health_harness import HealthHarness

STATE_DIR = Path.home() / ".phantomcloak"
HEALTH_LOG = STATE_DIR / "health_monitor.jsonl"
SESSION_FILE = STATE_DIR / "last_session.json"


def _load_app_state():
    """Minimal app-like object from persisted session."""
    class _App:
        phantomcloak_active = False
        kill_switch_armed = False
        double_onion_enabled = False
        current_location = "vancouver"
        google_hidden = False

    app = _App()
    if SESSION_FILE.exists():
        try:
            s = json.loads(SESSION_FILE.read_text())
            app.phantomcloak_active = s.get("active", False)
            app.kill_switch_armed = s.get("killswitch", False)
            app.double_onion_enabled = s.get("double_onion", False)
            app.current_location = s.get("location", "vancouver")
            app.google_hidden = s.get("google_hidden", False)
        except Exception:
            pass
    return app


def _log_panel(panel: dict):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "overall": panel.get("overall"),
        "counts": panel.get("counts"),
        "red_techniques": [
            t["id"] for t in panel.get("techniques", []) if t.get("status") == "red"
        ],
    }
    with HEALTH_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main_loop():
    ks = killswitch.KillSwitch()
    print("PhantomCloak Health Monitor started (Top 30 harness)...")
    while True:
        ks.check_watchdog()
        app = _load_app_state()
        panel = HealthHarness(app).evaluate_all()
        _log_panel(panel)
        reds = panel.get("counts", {}).get("red", 0)
        if reds and app.phantomcloak_active:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ALERT: {reds} technique(s) RED — {panel.get('overall')}")
        time.sleep(30)


if __name__ == "__main__":
    main_loop()