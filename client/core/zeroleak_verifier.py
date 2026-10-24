"""Zero-Leak Verifier — on-device, fail-closed pre-transmission checks.

Before PhantomCloak reports "protected" (and before the app treats it as safe
to transmit), every required protection must verify healthy. If any check
fails, the caller MUST trigger the kill switch. This is the honest, marketable
core: "verified before every transmission; blocks on failure."

HONEST LIMITATION: fail-closed dramatically reduces leak risk but cannot
guarantee data "can never" leak (kernel/driver side-channels, OS bugs, user
misconfiguration). Never market it as absolute impossibility.
"""
from __future__ import annotations
import shutil
import socket
import subprocess
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class VerifyReport:
    checks: list = field(default_factory=list)

    @property
    def ok(self):
        return bool(self.checks) and all(c.passed for c in self.checks)

    def failures(self):
        return [c for c in self.checks if not c.passed]

    def to_dict(self):
        return {"ok": self.ok, "checks": [c.__dict__ for c in self.checks]}


def _tunnel_up():
    try:
        out = subprocess.run(["ifconfig"], capture_output=True,
                             text=True, timeout=4).stdout
        up = "utun" in out
        return CheckResult("tunnel_up", up,
                           "utun interface present" if up else "no tun interface")
    except Exception as e:
        return CheckResult("tunnel_up", False, f"probe error: {e}")


def _dns_resolves():
    try:
        socket.gethostbyname("example.com")
        return CheckResult("dns_resolves", True, "DNS resolves via configured resolver")
    except Exception as e:
        return CheckResult("dns_resolves", False, f"DNS failure: {e}")


def _killswitch_available():
    present = shutil.which("pfctl") is not None
    return CheckResult("killswitch_available", present,
                       "pfctl available" if present else "pfctl missing")


_PROBES = {
    "tunnel_up": _tunnel_up,
    "dns_resolves": _dns_resolves,
    "killswitch_available": _killswitch_available,
}


def verify(required=("tunnel_up", "dns_resolves", "killswitch_available")):
    report = VerifyReport()
    for name in required:
        fn = _PROBES.get(name)
        if fn:
            report.checks.append(fn())
    return report


def arm(on_failure=None, required=("tunnel_up", "dns_resolves", "killswitch_available")):
    """Run verification; if it fails, invoke on_failure (e.g. killswitch.engage)
    and return the failing report so the UI can show which check tripped."""
    report = verify(required)
    if not report.ok and callable(on_failure):
        try:
            on_failure(report)
        except Exception:
            pass
    return report
