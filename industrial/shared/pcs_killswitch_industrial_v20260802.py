#!/usr/bin/env python3
"""Industrial kill switch — pf rules under PCS state dir, NOT /tmp.

New file only. Does not modify Suite client/core/killswitch.py
(PF_CONF_PATH=/tmp/delphi_killswitch.pf.conf remains in legacy tree).

Default: dry_run=True. Real pf apply requires force_apply=True and sudo.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE = Path.home() / ".pcs_industrial_20260802"
RULES_DIR = STATE / "pf_rules"
PF_CONF_PATH = RULES_DIR / "pcs_killswitch_v20260802.pf.conf"
LOG_PATH = STATE / "killswitch_industrial.log"

STATE.mkdir(parents=True, exist_ok=True)
RULES_DIR.mkdir(parents=True, exist_ok=True)
try:
    STATE.chmod(0o700)
    RULES_DIR.chmod(0o700)
except OSError:
    pass

logger = logging.getLogger("pcs.killswitch.industrial")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_PATH)
    fh.setFormatter(logging.Formatter("%(asctime)s - [PCS-KS] %(levelname)s - %(message)s"))
    logger.addHandler(fh)
    try:
        LOG_PATH.chmod(0o600)
    except OSError:
        pass


class IndustrialKillSwitch:
    """Industrial killswitch. Conf path is always under STATE/pf_rules (never /tmp).

    Suite client/core/killswitch.py is untouched (legacy /tmp path stays there only).
    """

    # Process-wide latch: prevents concurrent double-arm races within one Python process.
    _arm_lock_held: bool = False

    def __init__(self) -> None:
        self.active = False
        self.vpn_interfaces: List[str] = []
        self.conf_path = PF_CONF_PATH

    def _detect_interfaces(self) -> List[str]:
        interfaces: List[str] = []
        try:
            result = subprocess.run(
                ["ifconfig"], capture_output=True, text=True, timeout=5, check=False
            )
            current = None
            for line in (result.stdout or "").splitlines():
                if line and not line.startswith("\t"):
                    current = line.split(":")[0].strip()
                if current and any(x in line for x in ("inet ", "utun", "tun", "wg")):
                    if current.startswith(("utun", "tun", "wg", "sing")):
                        if current not in interfaces:
                            interfaces.append(current)
        except Exception as e:
            logger.warning("Interface detection failed: %s", e)
        if not interfaces:
            interfaces = ["utun4", "utun5", "sing0"]
        self.vpn_interfaces = interfaces
        return interfaces

    def _generate_rules(self) -> str:
        ifaces = self._detect_interfaces()
        lines = [
            "# PCS Industrial killswitch — NOT stored in /tmp",
            f"# Generated: {datetime.now(timezone.utc).isoformat()}",
            f"# Path: {self.conf_path}",
            "block drop all",
            "pass quick on lo0 all",
            "pass quick proto udp from port 67 to port 68",
            "pass quick proto udp from port 68 to port 67",
        ]
        for iface in ifaces:
            lines.append(f"pass quick on {iface} all")
        lines.extend([
            "pass quick proto tcp to any port 443",
            "pass quick proto udp to any port 51820",
            "pass quick proto udp to any port 443",
            "block drop quick inet6 all",
        ])
        return "\n".join(lines) + "\n"

    def write_rules_file(self) -> Dict[str, Any]:
        rules = self._generate_rules()
        self.conf_path.write_text(rules)
        try:
            self.conf_path.chmod(0o600)
        except OSError:
            pass
        return {
            "status": "written",
            "path": str(self.conf_path),
            "interfaces": list(self.vpn_interfaces),
            "bytes": len(rules),
        }

    def arm(self, *, dry_run: bool = True, force_apply: bool = False) -> Dict[str, Any]:
        """Industry default for Activate: call with dry_run=False, force_apply=True when CEO confirms.

        Fail-closed path guarantees:
          - Conf always written under RULES_DIR (never /tmp)
          - Concurrent/re-entrant apply is latched (double-arm race → single apply)
          - Already-active + dry re-arm rewrites conf only (idempotent)
        """
        # Always ensure industrial conf exists first (safe rewrite).
        meta = self.write_rules_file()
        rules = self.conf_path.read_text()

        if dry_run and not force_apply:
            logger.info("DRY RUN — rules at %s not applied", self.conf_path)
            return {
                "status": "dry_run",
                "path": str(self.conf_path),
                "interfaces": meta["interfaces"],
                "rules_preview": rules[:400],
                "message": "Rules written under ~/.pcs_industrial_20260802/pf_rules/ (not /tmp).",
                "armed": False,
                "dry_run": True,
            }

        # Real apply path — latch against double-arm races
        if IndustrialKillSwitch._arm_lock_held and self.active:
            logger.info("Killswitch already armed (idempotent re-entry) path=%s", self.conf_path)
            return {
                "status": "armed",
                "path": str(self.conf_path),
                "interfaces": meta["interfaces"],
                "message": "Kill switch already active (idempotent; industrial conf path)",
                "armed": True,
                "idempotent": True,
            }

        IndustrialKillSwitch._arm_lock_held = True
        try:
            subprocess.run(["sudo", "pfctl", "-E"], capture_output=True, text=True, check=False)
            result = subprocess.run(
                ["sudo", "pfctl", "-f", str(self.conf_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                self.active = True
                logger.warning("KILL SWITCH ARMED via %s", self.conf_path)
                return {
                    "status": "armed",
                    "path": str(self.conf_path),
                    "interfaces": meta["interfaces"],
                    "message": "Kill switch active (industrial conf path)",
                    "armed": True,
                }
            IndustrialKillSwitch._arm_lock_held = False
            return {
                "status": "error",
                "message": result.stderr or result.stdout,
                "path": str(self.conf_path),
                "armed": False,
            }
        except Exception as e:
            IndustrialKillSwitch._arm_lock_held = False
            return {
                "status": "error",
                "message": str(e),
                "path": str(self.conf_path),
                "armed": False,
            }

    def disarm(self) -> Dict[str, Any]:
        try:
            subprocess.run(["sudo", "pfctl", "-d"], capture_output=True, check=False)
            subprocess.run(["sudo", "pfctl", "-F", "all"], capture_output=True, check=False)
            self.active = False
            IndustrialKillSwitch._arm_lock_held = False
            return {"status": "disarmed", "path": str(self.conf_path), "armed": False}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def conf_location(self) -> str:
        return str(self.conf_path)


def arm_for_activate(*, force_apply: bool = False) -> Dict[str, Any]:
    """Auto-on with Activate: always write conf; apply only if force_apply or PCS_FORCE_PF=1.

    Suite killswitch paths are never used. Industrial conf only under pf_rules/.
    """
    import os

    # Hard guarantee: industrial conf path never under /tmp
    if "/tmp" in str(PF_CONF_PATH) or str(PF_CONF_PATH).startswith("/tmp"):
        return {
            "status": "error",
            "message": "Refusing arm: industrial PF conf must not live under /tmp",
            "path": str(PF_CONF_PATH),
            "armed": False,
        }
    if RULES_DIR != STATE / "pf_rules":
        return {
            "status": "error",
            "message": "Refusing arm: RULES_DIR must be ~/.pcs_industrial_20260802/pf_rules",
            "path": str(RULES_DIR),
            "armed": False,
        }

    ks = IndustrialKillSwitch()
    apply = force_apply or os.environ.get("PCS_FORCE_PF") == "1"
    return ks.arm(dry_run=not apply, force_apply=apply)
