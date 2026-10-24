"""Option A kill switch — real pfctl activation via ONE macOS admin prompt.

A pf ruleset persists at the OS level once applied, so arming once per app
session is enough: the switch stays active with no further prompts until you
disarm (one more prompt). arm() is idempotent within a session, and the
verified state is cached so periodic health checks never re-prompt.

No stored password and no root daemon: uses osascript "with administrator
privileges" (the native OS auth dialog); the app never sees your password.
Refuses to arm with no tunnel up (that would cut all traffic).
"""
import json
import subprocess
import time
from pathlib import Path

STATE = Path.home() / ".phantomcloak-suite"
RULES = STATE / "killswitch.pf.conf"
STATUS = STATE / "killswitch_status.json"

_session = {"armed": False, "verified": False}


def _tunnels():
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5).stdout
        return [l.split(":")[0] for l in out.splitlines() if l.startswith("utun")]
    except Exception:
        return []


def _write_status(d):
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        STATUS.write_text(json.dumps(d))
        STATUS.chmod(0o600)
    except OSError:
        pass


def _osa_admin(shell_cmd):
    osa = 'do shell script "%s" with administrator privileges' % (
        shell_cmd.replace("\\", "\\\\").replace('"', '\\"'))
    return subprocess.run(["osascript", "-e", osa], capture_output=True, text=True)


def status():
    """Read cached state WITHOUT prompting (safe for the periodic health loop).

    Honesty rule: pf rules do NOT survive a reboot, but this status file does.
    So we only report 'verified' for a switch armed in THIS process (in-memory
    session). State read from disk is reported armed-but-unverified, and clearly
    stale state (older than a day — almost certainly a reboot) is reported
    disarmed. A kill switch must never falsely claim it is protecting you."""
    if _session["armed"]:
        return {"armed": True, "verified": _session["verified"], "source": "session"}
    try:
        d = json.loads(STATUS.read_text())
        age = time.time() - float(d.get("ts", 0))
        if d.get("armed") and age > 86400:
            return {"armed": False, "verified": False, "source": "stale",
                    "note": "pf state is stale (likely rebooted) — re-arm to protect"}
        return {"armed": bool(d.get("armed")), "verified": False, "source": "file",
                "note": "unverified this session — re-arm to confirm" if d.get("armed") else None}
    except Exception:
        return {"armed": False, "verified": False, "source": "none"}


_LAN_V4 = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")


def _build_ruleset(tuns, local_network=True, server_ips=None):
    """Kill-switch pf ruleset. INTERNET only via the tunnel (leak protection),
    but the Wi-Fi lease and (optionally) the LAN stay reachable.

    ALWAYS allowed (so PCS never severs the Mac<->router link):
      DHCPv4, DHCPv6, and IPv6 neighbor discovery / router advertisements.
    Allowed only when local_network is True (the green 'Local Network Access'
    toggle): RFC-1918 + link-local ranges, plus mDNS/Bonjour/SSDP multicast and
    broadcast — this is what lets AirPlay, casting, and screen mirroring work.
    Nothing here opens an internet path off-tunnel: public destinations still
    hit the final `block all` and are dropped."""
    L = ["set block-policy drop", "set skip on lo0", "block all"]
    L += [
        "pass quick proto udp from any port 68 to any port 67",
        "pass quick proto udp from any port 67 to any port 68",
        "pass quick inet6 proto udp from any port 546 to any port 547",
        "pass quick inet6 proto udp from any port 547 to any port 546",
        "pass quick inet6 proto icmp6 all",
    ]
    for ip in (server_ips or []):        # keep the tunnel's outer link open
        if ip:
            L.append("pass quick proto tcp from any to %s" % ip)
            L.append("pass quick proto udp from any to %s" % ip)
    if local_network:
        for net in _LAN_V4:
            L.append("pass quick inet from any to %s" % net)
            L.append("pass quick inet from %s to any" % net)
        L += [
            "pass quick inet from any to 224.0.0.0/4",
            "pass quick inet from any to 255.255.255.255",
            "pass quick inet6 from any to fe80::/10",
            "pass quick inet6 from any to ff00::/8",
        ]
    for t in tuns:
        L.append("pass quick on %s all" % t)
    return "\n".join(L) + "\n"


def arm(local_network=True, server_ips=None):
    if _session["armed"]:
        return {"status": "already_armed", "armed": True,
                "verified": _session["verified"], "local_network": _session.get("local_network", True)}
    tuns = _tunnels()
    if not tuns:
        return {"status": "refused",
                "reason": "no tunnel up — arming would cut all traffic",
                "armed": False}
    STATE.mkdir(parents=True, exist_ok=True)
    rules = _build_ruleset(tuns, local_network=local_network, server_ips=server_ips)
    RULES.write_text(rules)
    # Parse-validate FIRST; only enable + load if the ruleset is well-formed, so
    # a bad ruleset can never leave pf half-applied.
    cmd = "pfctl -n -f '{r}' && pfctl -E && pfctl -f '{r}' && pfctl -s info".format(r=RULES)
    r = _osa_admin(cmd)
    ok = (r.returncode == 0) and ("Status: Enabled" in (r.stdout or ""))
    _session.update(armed=ok, verified=ok, local_network=local_network)
    _write_status({"armed": ok, "verified": ok, "local_network": local_network, "ts": time.time()})
    if ok:
        return {"status": "armed", "armed": True, "verified": True, "local_network": local_network}
    return {"status": "error", "armed": False,
            "detail": (r.stderr or r.stdout or "authorization cancelled").strip()}


def disarm():
    r = _osa_admin("pfctl -d; pfctl -F all")
    ok = (r.returncode == 0)
    _session.update(armed=False, verified=False)
    _write_status({"armed": False, "verified": False, "ts": time.time()})
    return {"status": "disarmed" if ok else "error", "armed": False,
            "detail": (r.stderr or r.stdout or "").strip()}
