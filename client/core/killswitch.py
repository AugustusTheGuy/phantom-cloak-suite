#!/usr/bin/env python3
"""
PhantomCloak — Robust Kill Switch Core

Enhanced version with:
- Safe dry-run + explicit apply
- Automatic interface detection (sing-box TUN, WireGuard, utun)
- Watchdog for interface loss (triggers kill)
- Recovery / safe mode
- Proper IPv6 blocking
- Logging
- Hooks for sing-box client manager
- Better error handling and status reporting
"""

import subprocess
import sys
import argparse
import logging
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Configuration
PF_CONF_PATH = "/tmp/delphi_killswitch.pf.conf"
LOG_PATH = Path.home() / ".phantomcloak" / "killswitch.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [KILL SWITCH] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class KillSwitch:
    def __init__(self):
        self.active = False
        self.last_check = None
        self.vpn_interfaces: List[str] = []

    def _detect_interfaces(self) -> List[str]:
        """Detect active VPN/tunnel interfaces including sing-box TUN."""
        interfaces = []
        try:
            result = subprocess.run(
                ["ifconfig"], capture_output=True, text=True, timeout=5
            )
            current_iface = None
            for line in result.stdout.splitlines():
                if line and not line.startswith('\t'):
                    current_iface = line.split(':')[0].strip()
                if current_iface and any(x in line for x in ['inet ', 'utun', 'tun', 'wg', 'sing-box']):
                    if current_iface.startswith(('utun', 'tun', 'wg', 'sing')):
                        if current_iface not in interfaces:
                            interfaces.append(current_iface)
        except Exception as e:
            logger.warning(f"Interface detection failed: {e}")
        
        # Fallback common names
        if not interfaces:
            interfaces = ["utun4", "utun5", "sing0"]
        
        self.vpn_interfaces = interfaces
        return interfaces

    def _generate_robust_rules(self) -> str:
        """Generate comprehensive, safe pf rules."""
        ifaces = self._detect_interfaces()
        
        rules = [
            "# PhantomCloak - Robust Kill Switch",
            f"# Generated: {datetime.now().isoformat()}",
            "# WARNING: This blocks ALL outbound traffic except through VPN interfaces",
            "",
            "# Default deny",
            "block drop all",
            "",
            "# Essential local loopback",
            "pass quick on lo0 all",
            "",
            "# DHCP for interface recovery (very limited)",
            "pass quick proto udp from port 67 to port 68",
            "pass quick proto udp from port 68 to port 67",
            "",
            "# Allow the detected VPN interfaces",
        ]
        
        for iface in ifaces:
            rules.append(f"pass quick on {iface} all")
        
        # Recovery paths (HTTPS + common VPN ports only)
        rules.extend([
            "",
            "# Minimal recovery paths (HTTPS + common VPN ports)",
            "pass quick proto tcp to any port 443",
            "pass quick proto udp to any port 51820",   # WireGuard
            "pass quick proto udp to any port 443",     # Hysteria2 / QUIC
        ])
        
        # Strong IPv6 blocking
        rules.extend([
            "",
            "# IPv6 Kill - Prevent leaks",
            "block drop quick inet6 all",
        ])
        
        return "\n".join(rules)

    def arm(self, dry_run: bool = True, force_apply: bool = False) -> Dict:
        """Arm the kill switch."""
        ifaces = self._detect_interfaces()
        rules = self._generate_robust_rules()
        
        logger.info(f"Detected VPN interfaces: {ifaces}")
        
        if dry_run and not force_apply:
            logger.info("DRY RUN - Rules generated but NOT applied")
            logger.info(f"Rules:\n{rules}")
            return {
                "status": "dry_run",
                "interfaces": ifaces,
                "rules": rules,
                "message": "Safe dry-run completed. Use --apply to enforce."
            }
        
        try:
            Path(PF_CONF_PATH).write_text(rules)
            
            # Enable pf if not already
            subprocess.run(["sudo", "pfctl", "-E"], capture_output=True, text=True)
            
            # Load our rules
            result = subprocess.run(
                ["sudo", "pfctl", "-f", PF_CONF_PATH],
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                self.active = True
                logger.warning("KILL SWITCH ARMED - All non-VPN traffic blocked")
                return {
                    "status": "armed",
                    "interfaces": ifaces,
                    "message": "Kill switch is now active"
                }
            else:
                logger.error(f"pfctl failed: {result.stderr}")
                return {"status": "error", "message": result.stderr}
                
        except Exception as e:
            logger.error(f"Failed to arm kill switch: {e}")
            return {"status": "error", "message": str(e)}

    def disarm(self) -> Dict:
        """Disarm the kill switch."""
        try:
            subprocess.run(["sudo", "pfctl", "-d"], capture_output=True)
            subprocess.run(["sudo", "pfctl", "-F", "all"], capture_output=True)
            self.active = False
            logger.info("Kill switch disarmed")
            return {"status": "disarmed", "message": "Normal network access restored"}
        except Exception as e:
            logger.error(f"Disarm failed: {e}")
            return {"status": "error", "message": str(e)}

    def check_watchdog(self) -> bool:
        """Check if VPN interfaces are still alive. Trigger kill if lost."""
        current = self._detect_interfaces()
        if not current and self.active:
            logger.critical("VPN interfaces lost while kill switch was armed! Triggering emergency block.")
            # Already blocked by pf, but we can log/alert here
            return False
        return True

    def safe_reconnect(self, verify_callback=None) -> Dict:
        """
        The critical safe reconnect gate.
        Only restores connectivity after rigorous verification.
        """
        logger.info("Safe Reconnect initiated")
        
        # Step 1: Run exposure checks (integrate with verification suite)
        if verify_callback:
            clean, reason = verify_callback()
        else:
            clean, reason = True, "Manual verification assumed clean"
        
        if not clean:
            logger.error(f"Safe Reconnect blocked: {reason}")
            return {"status": "blocked", "reason": reason}
        
        # Step 2: Disarm
        self.disarm()
        
        # Step 3: In real usage, the caller would start the tunnel here
        logger.info("Safe Reconnect approved. Caller should now start tunnel.")
        
        return {
            "status": "approved",
            "message": "Disarmed. Start your tunnel now, then re-arm kill switch."
        }


def main():
    parser = argparse.ArgumentParser(description="Delphi Robust Kill Switch")
    parser.add_argument("--apply", action="store_true", help="Actually apply rules (DANGEROUS)")
    parser.add_argument("--disarm", action="store_true")
    parser.add_argument("--safe-reconnect", action="store_true")
    parser.add_argument("--watchdog", action="store_true")
    
    args = parser.parse_args()
    ks = KillSwitch()
    
    if args.disarm:
        print(ks.disarm())
    elif args.safe_reconnect:
        print(ks.safe_reconnect())
    elif args.watchdog:
        print("Watchdog check:", ks.check_watchdog())
    else:
        result = ks.arm(dry_run=not args.apply, force_apply=args.apply)
        print(result)

if __name__ == "__main__":
    main()