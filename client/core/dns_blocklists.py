"""DNS blocklist manager — user-editable + community lists (Core).

Cheap, high-value privacy control. Stores lists under the Suite state dir,
merges community + user entries, dedupes, validates domains, and produces a
resolver-ready set. Community-list fetching is left to the host (network I/O).
"""
from __future__ import annotations
import re
from pathlib import Path

STATE = Path.home() / ".phantomcloak-suite" / "dns"
USER_LIST = STATE / "user_blocklist.txt"
COMMUNITY = STATE / "community_blocklist.txt"

_DOMAIN = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.[a-z0-9-]{1,63})+$", re.I)


def valid(domain: str) -> bool:
    return bool(_DOMAIN.match((domain or "").strip()))


def _read(p: Path):
    try:
        return [l.strip().lower() for l in p.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    except Exception:
        return []


def add_user(domain: str) -> bool:
    if not valid(domain):
        return False
    STATE.mkdir(parents=True, exist_ok=True)
    cur = set(_read(USER_LIST)); cur.add(domain.strip().lower())
    USER_LIST.write_text("\n".join(sorted(cur)))
    return True


def remove_user(domain: str) -> bool:
    cur = set(_read(USER_LIST)); d = (domain or "").strip().lower()
    if d in cur:
        cur.discard(d)
        USER_LIST.write_text("\n".join(sorted(cur)))
        return True
    return False


def set_community(domains) -> int:
    STATE.mkdir(parents=True, exist_ok=True)
    clean = sorted({d.strip().lower() for d in domains if valid(d)})
    COMMUNITY.write_text("\n".join(clean))
    return len(clean)


def effective_blockset() -> set:
    return set(_read(USER_LIST)) | set(_read(COMMUNITY))


def stats() -> dict:
    return {"user": len(_read(USER_LIST)),
            "community": len(_read(COMMUNITY)),
            "effective": len(effective_blockset())}
