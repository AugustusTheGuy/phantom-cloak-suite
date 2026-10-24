"""Last-session resume for one-tap «Resume Zurich · Browsing» (industrial only).

Honesty contract (fail-closed):
  - Resume restores *selection* only: purpose / country / location / tier / catalog.
  - Disk never authorizes a live protected session.
  - protected=true / active=true are never restored when configured_count==0.
  - Before any protected claim, readiness + preflight must re-run (live).
  - last_session lives under ~/.pcs_industrial_20260802/ only.
  - Do not claim an active tunnel without live checks.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# ---------------------------------------------------------------------------
# Paths (industrial state only; configure_paths for hermetic tests)
# ---------------------------------------------------------------------------

STATE = Path.home() / ".pcs_industrial_20260802"
SESSION_FILE = STATE / "last_session_industrial.json"

# Seed from legacy preference if industrial empty (read-only copy, never write legacy)
LEGACY_SESSION = Path.home() / ".phantomcloak" / "last_session.json"

FLAGS = {
    "CH": "🇨🇭",
    "CA": "🇨🇦",
    "AE": "🇦🇪",
    "SG": "🇸🇬",
    "DE": "🇩🇪",
    "HK": "🇭🇰",
    "US": "🇺🇸",
    "GB": "🇬🇧",
    "FR": "🇫🇷",
    "JP": "🇯🇵",
    "AU": "🇦🇺",
    "NL": "🇳🇱",
    "BS": "🇧🇸",
    "KY": "🇰🇾",
    "MU": "🇲🇺",
    "SC": "🇸🇨",
    "EE": "🇪🇪",
}

# Selection fields restored on resume (UX prefs — not protection state)
SELECTION_KEYS = (
    "purpose",
    "country",
    "location",
    "country_name",
    "tier",
    "catalog_ip_id",
    "residential_ip",
)

# Runtime/protection fields — never trusted from disk alone
RUNTIME_CLAIM_KEYS = (
    "active",
    "protected",
    "killswitch",
    "zero_leak_verified",
    "tunnel_active",
    "preflight",
    "configured_count",
    "server_filled_count",
    "pending_ip_count",
)


def configure_paths(
    *,
    state: Optional[Path] = None,
    session_file: Optional[Path] = None,
    legacy_session: Optional[Path] = None,
) -> None:
    """Rebind path globals for hermetic tests (production defaults unchanged)."""
    global STATE, SESSION_FILE, LEGACY_SESSION
    if state is not None:
        STATE = Path(state)
        if session_file is None:
            SESSION_FILE = STATE / "last_session_industrial.json"
    if session_file is not None:
        SESSION_FILE = Path(session_file)
    if legacy_session is not None:
        LEGACY_SESSION = Path(legacy_session)


def _ensure() -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    try:
        STATE.chmod(0o700)
    except OSError:
        pass


def _normalize_tier(tier: Any) -> str:
    t = str(tier or "core").strip().lower()
    return t if t in ("core", "pro") else "core"


def _catalog_id_from_residential(entry: Any) -> Optional[str]:
    if isinstance(entry, dict):
        cid = entry.get("id") or entry.get("catalog_ip_id")
        if cid:
            return str(cid)
    return None


def extract_selection(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Pull purpose/country/tier/catalog selection only (no protection claims)."""
    s = data or {}
    purpose = str(s.get("purpose") or "browsing").strip().lower() or "browsing"
    country = str(s.get("country") or "CH").strip().upper() or "CH"
    location = str(s.get("location") or "zurich").strip().lower() or "zurich"
    country_name = s.get("country_name")
    if not country_name:
        country_name = location.replace("_", " ").title()
    tier = _normalize_tier(s.get("tier"))
    residential = s.get("residential_ip")
    catalog_ip_id = s.get("catalog_ip_id") or s.get("ip_id") or _catalog_id_from_residential(
        residential
    )
    out: Dict[str, Any] = {
        "purpose": purpose,
        "country": country,
        "location": location,
        "country_name": str(country_name),
        "tier": tier,
    }
    if catalog_ip_id:
        out["catalog_ip_id"] = str(catalog_ip_id)
    if isinstance(residential, dict):
        # Keep catalog metadata only (id/city/isp labels) — never a tunnel claim
        meta = {
            k: residential.get(k)
            for k in ("id", "city", "isp", "country", "label", "region")
            if residential.get(k) is not None
        }
        if meta:
            out["residential_ip"] = meta
    return out


def honesty_strip_protection_claims(
    data: Optional[Dict[str, Any]],
    *,
    configured_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Force protected/active false when not allowed; keep selection.

    Rules:
      - Disk restore never yields protected=true / active=true without a live gate.
      - configured_count==0 → protected and active MUST be false.
      - tunnel_active / zero_leak_verified never restored as true from disk alone.
    """
    raw = dict(data or {})
    selection = extract_selection(raw)
    out = dict(selection)

    # Preserve non-claim metadata useful for operators (not UX protected state)
    if raw.get("saved_at"):
        out["saved_at"] = raw["saved_at"]
    if raw.get("from_legacy"):
        out["from_legacy"] = True
    if "preflight" in raw and isinstance(raw.get("preflight"), dict):
        # Historical report only — not a live pass
        out["last_preflight"] = raw["preflight"]

    cfg = configured_count
    if cfg is None:
        try:
            cfg = int(raw.get("configured_count") if raw.get("configured_count") is not None else 0)
        except (TypeError, ValueError):
            cfg = 0
    out["configured_count"] = int(cfg)

    # HARD: never restore protected/active when no real client configs
    if int(cfg) <= 0:
        out["protected"] = False
        out["active"] = False
        out["tunnel_active"] = False
        out["zero_leak_verified"] = False
        # Killswitch may have been armed on fail-closed; do not claim "protected"
        out["killswitch"] = bool(raw.get("killswitch"))
        out["honesty"] = {
            "restored_selection_only": True,
            "protection_from_disk": False,
            "reason": "configured_count==0 — protected/active cleared",
        }
        return out

    # Even with configs on disk snapshot, do NOT restore live protection claims.
    # Selection is restored; protection requires re-run readiness + preflight.
    out["protected"] = False
    out["active"] = False
    out["tunnel_active"] = False
    out["zero_leak_verified"] = False
    out["killswitch"] = False
    out["honesty"] = {
        "restored_selection_only": True,
        "protection_from_disk": False,
        "reason": "resume restores selection only; re-run readiness+preflight before protected",
        "disk_had_active": bool(raw.get("active") or raw.get("protected")),
    }
    return out


def save_session(
    data: Dict[str, Any],
    *,
    configured_count: Optional[int] = None,
    protected: Optional[bool] = None,
    allow_protected_claim: bool = False,
) -> Dict[str, Any]:
    """Persist session under industrial state with honesty enforcement.

    If configured_count==0 (or resolved as 0), protected/active are forced false
    even if the caller passed true. allow_protected_claim=True only after a live
    activate_protected_session success with configured_count>0.
    """
    _ensure()
    selection = extract_selection(data)
    payload: Dict[str, Any] = dict(selection)

    # Resolve configured_count (default 0 — fail closed on missing)
    cfg = configured_count
    if cfg is None and data.get("configured_count") is not None:
        try:
            cfg = int(data["configured_count"])
        except (TypeError, ValueError):
            cfg = 0
    if cfg is None:
        cfg = 0
    cfg = int(cfg)
    payload["configured_count"] = cfg

    for k in ("server_filled_count", "pending_ip_count"):
        if data.get(k) is not None:
            payload[k] = data[k]

    # Caller intent for protected
    if protected is not None:
        intent_protected = bool(protected)
    else:
        intent_protected = bool(data.get("protected") or data.get("active"))

    # Honesty gates (order matters):
    # 1) configured_count==0 → never protected
    # 2) allow_protected_claim required to persist protected=true
    # 3) otherwise selection-only / blocked save
    want_protected = False
    if cfg > 0 and allow_protected_claim and intent_protected:
        want_protected = True

    payload["protected"] = want_protected
    payload["active"] = want_protected

    # Killswitch may be armed on fail-closed without a protected claim
    if data.get("killswitch") is not None:
        payload["killswitch"] = bool(data.get("killswitch"))
    else:
        payload["killswitch"] = want_protected

    if isinstance(data.get("preflight"), dict):
        payload["preflight"] = data["preflight"]
    if data.get("reason"):
        payload["reason"] = data["reason"]

    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    payload["honesty"] = {
        "selection_persisted": True,
        "protected_claim_allowed": bool(allow_protected_claim and want_protected),
        "configured_count": cfg,
    }

    SESSION_FILE.write_text(json.dumps(payload, indent=2))
    try:
        SESSION_FILE.chmod(0o600)
    except OSError:
        pass
    return payload


def load_session(*, honest: bool = True) -> Optional[Dict[str, Any]]:
    """Load last session. With honest=True (default), strip false protection claims."""
    _ensure()
    raw: Optional[Dict[str, Any]] = None
    if SESSION_FILE.exists():
        try:
            raw = json.loads(SESSION_FILE.read_text())
        except Exception:
            raw = None
    if raw is None and LEGACY_SESSION.exists():
        try:
            s = json.loads(LEGACY_SESSION.read_text())
            # Normalize into industrial shape without writing legacy
            raw = {
                "purpose": s.get("purpose") or "browsing",
                "country": s.get("country") or "CH",
                "location": s.get("location") or "zurich",
                "country_name": (
                    "Zurich"
                    if (s.get("location") or "").lower() == "zurich"
                    else s.get("country")
                ),
                "tier": s.get("tier") or "core",
                "from_legacy": True,
                "saved_at": s.get("saved_at"),
                # Never import legacy active/protected as live claims
                "active": False,
                "protected": False,
            }
        except Exception:
            raw = None
    if raw is None:
        return None
    if not honest:
        return raw
    return honesty_strip_protection_claims(raw)


def resume_label(session: Optional[Dict[str, Any]] = None) -> str:
    s = session if session is not None else load_session()
    if not s:
        return "No previous session"
    loc = (s.get("location") or s.get("country_name") or s.get("country") or "—").replace(
        "_", " "
    )
    purpose = (s.get("purpose") or "browsing").replace("_", " ")
    city = loc.title() if loc else "—"
    purpose_l = purpose.title()
    flag = FLAGS.get((s.get("country") or "").upper(), "🛡️")
    return f"Resume {flag} {city} · {purpose_l}"


def resume_payload() -> Dict[str, Any]:
    """Dashboard / shell status helper — selection only; never claims live protect."""
    s = load_session(honest=True)
    selection = extract_selection(s) if s else {
        "purpose": "browsing",
        "country": "CH",
        "location": "zurich",
        "country_name": "Zurich",
        "tier": "core",
    }
    return {
        "available": bool(s),
        "label": resume_label(s),
        "session": s,
        "selection": selection,
        "flag": FLAGS.get((selection.get("country") or "").upper(), "🛡️"),
        "city": (selection.get("location") or "zurich").replace("_", " ").title(),
        "purpose": selection.get("purpose") or "browsing",
        "country": selection.get("country") or "CH",
        "location": selection.get("location") or "zurich",
        "tier": selection.get("tier") or "core",
        "catalog_ip_id": selection.get("catalog_ip_id"),
        # Explicit honesty surface for UI / status
        "protected": False,
        "active": False,
        "requires_preflight": True,
        "requires_readiness": True,
        "honest_copy": "selection restored · re-run readiness + preflight before protected",
    }


def activate_kwargs_from_session(session: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map honest selection → activate(purpose=, country_code=, ip_id=) kwargs."""
    s = session if session is not None else load_session(honest=True)
    sel = extract_selection(s)
    kwargs: Dict[str, Any] = {
        "purpose": sel.get("purpose") or "browsing",
        "country_code": sel.get("country") or "CH",
    }
    ip_id = sel.get("catalog_ip_id")
    if ip_id:
        kwargs["ip_id"] = ip_id
    return kwargs


def resume_and_protect(
    *,
    tier: Optional[str] = None,
    activate_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    readiness_scan_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    require_configured_servers: bool = True,
    tracker_vault_enabled: bool = False,
    force_pf: bool = False,
    **activate_extra: Any,
) -> Dict[str, Any]:
    """Full honest resume path:

      1) Load selection (purpose/country/tier/catalog)
      2) Live readiness scan
      3) If configured_count==0 → refuse protected, persist selection only
      4) Else run preflight/activate (caller injects or industrial gate)
      5) Persist result; protected only if live gate says so AND count>0
    """
    session = load_session(honest=True) or {
        "purpose": "browsing",
        "country": "CH",
        "location": "zurich",
        "country_name": "Zurich",
        "tier": "core",
    }
    selection = extract_selection(session)
    effective_tier = _normalize_tier(tier or selection.get("tier") or "core")
    selection["tier"] = effective_tier

    # Step 2: live readiness (never trust disk configured_count alone for protect)
    if readiness_scan_fn is None:
        try:
            from .pcs_server_readiness_v20260802 import scan_readiness
        except ImportError:
            from shared.pcs_server_readiness_v20260802 import scan_readiness  # type: ignore

        readiness_scan_fn = scan_readiness

    readiness = readiness_scan_fn()
    try:
        cfg = int(readiness.get("configured_count") or 0)
    except (TypeError, ValueError):
        cfg = 0

    label = resume_label(selection)
    base = {
        "label": label,
        "selection": selection,
        "readiness": readiness,
        "configured_count": cfg,
        "requires_preflight": True,
    }

    if require_configured_servers and cfg <= 0:
        saved = save_session(
            {
                **selection,
                "active": False,
                "protected": False,
                "killswitch": True,
                "configured_count": 0,
                "server_filled_count": readiness.get("server_filled_count"),
                "pending_ip_count": readiness.get("pending_ip_count"),
                "reason": "servers_not_configured",
                "preflight": {
                    "ok": False,
                    "failures": ["servers_configured"],
                    "tier": effective_tier,
                },
            },
            configured_count=0,
            protected=False,
            allow_protected_claim=False,
        )
        return {
            **base,
            "status": "blocked",
            "protected": False,
            "active": False,
            "reason": "servers_not_configured",
            "message": (
                "Resume restored selection only. Protected browsing blocked — "
                "configured_count=0. Fill VPS inventory + materialize, then retry."
            ),
            "session_saved": saved,
            "honest_copy": "selection restored · not protected (no configured servers)",
        }

    # Step 4: preflight + protect via injected activate or industrial gate
    if activate_fn is not None:
        result = activate_fn(
            purpose=selection.get("purpose") or "browsing",
            country_code=selection.get("country") or "CH",
            ip_id=selection.get("catalog_ip_id"),
            tier=effective_tier,
            **activate_extra,
        )
    else:
        try:
            from .pcs_preflight_obfuscation_gate_v20260802 import activate_protected_session
        except ImportError:
            from shared.pcs_preflight_obfuscation_gate_v20260802 import (  # type: ignore
                activate_protected_session,
            )

        result = activate_protected_session(
            tier=effective_tier,
            tracker_vault_enabled=tracker_vault_enabled,
            require_tunnel=False,
            require_configured_servers=require_configured_servers,
            force_pf_apply=force_pf,
            auto_arm_killswitch=True,
        )
        # Annotate with selection for callers
        result = {
            **result,
            "purpose": selection.get("purpose"),
            "country": selection.get("country"),
            "location": selection.get("location"),
            "catalog_ip_id": selection.get("catalog_ip_id"),
        }

    live_protected = bool(result.get("protected"))
    result_cfg = result.get("configured_count")
    if result_cfg is None:
        result_cfg = cfg
    try:
        result_cfg = int(result_cfg)
    except (TypeError, ValueError):
        result_cfg = cfg

    # HARD: never persist protected if count==0
    if result_cfg <= 0:
        live_protected = False

    saved = save_session(
        {
            **selection,
            "active": live_protected,
            "protected": live_protected,
            "killswitch": bool(
                live_protected or result.get("killswitch_tripped") or result.get("killswitch")
            ),
            "configured_count": result_cfg,
            "server_filled_count": result.get("server_filled_count"),
            "pending_ip_count": result.get("pending_ip_count"),
            "preflight": result.get("report") or result.get("preflight"),
            "reason": result.get("reason"),
            "residential_ip": selection.get("residential_ip"),
            "catalog_ip_id": selection.get("catalog_ip_id"),
        },
        configured_count=result_cfg,
        protected=live_protected,
        allow_protected_claim=live_protected and result_cfg > 0,
    )

    return {
        **base,
        "status": "protected" if live_protected else result.get("status") or "blocked",
        "protected": live_protected,
        "active": live_protected,
        "reason": result.get("reason"),
        "message": result.get("message"),
        "result": result,
        "session_saved": saved,
        "honest_copy": (
            "protections active · verify recommended"
            if live_protected
            else "selection restored · preflight refused protected"
        ),
    }
