#!/usr/bin/env python3
"""Industrial residential IP **product catalog** (not live tunnel endpoints).

Writes pools under ~/.pcs_industrial_20260802/residential_pools/
Schema compatible with Suite client/core/residential_pool.py.

IMPORTANT:
- Entries are synthetic catalog metadata for UI / selection / health demo.
- They are NOT scraped residential proxies and NOT sing-box VPS server IPs.
- Tunnel endpoints still require owned VPS via vps_inventory.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE = Path.home() / ".pcs_industrial_20260802"
POOL_DIR = STATE / "residential_pools"
POOL_DIR.mkdir(parents=True, exist_ok=True)

# Align with Suite COUNTRY_TO_LOCATION + industrial exits
COUNTRY_TO_LOCATION = {
    "CA": "vancouver",
    "AE": "dubai",
    "SG": "singapore",
    "CH": "zurich",
    "HK": "hongkong",
    "DE": "frankfurt",
    "EE": "tallinn",
    "BS": "bahamas",
    "KY": "cayman",
    "MU": "mauritius",
    "SC": "seychelles",
    "US": "vancouver",
    "GB": "vancouver",
    "AU": "singapore",
    "FR": "frankfurt",
    "JP": "hongkong",
    "BR": "bahamas",
    "IN": "dubai",
    "NL": "frankfurt",
    "IS": "zurich",
    "SE": "zurich",
    "PT": "frankfurt",
    "RO": "frankfurt",
    "ES": "frankfurt",
    "TH": "singapore",
    "MX": "bahamas",
    "CO": "bahamas",
    "GE": "frankfurt",
    "CR": "bahamas",
    "MY": "singapore",
    "ID": "singapore",
    "VN": "hongkong",
    "CZ": "frankfurt",
    "PL": "frankfurt",
    "HR": "frankfurt",
    "GR": "frankfurt",
}

# Region-accurate ISP brands for product UX (public brand names only)
COUNTRY_ISPS: Dict[str, List[str]] = {
    "CA": ["Rogers Home", "Bell Fibe", "Shaw Residential", "Telus PureFibre", "Videotron"],
    "US": ["Comcast Xfinity", "Spectrum Residential", "AT&T Fiber Home", "Verizon Fios", "Cox Residential"],
    "GB": ["BT Consumer", "Virgin Media Home", "Sky Broadband", "TalkTalk Home", "EE Home"],
    "AE": ["Etisalat Home", "du Home", "e& Home Fiber"],
    "IN": ["Jio Fiber", "Airtel Xstream Fiber", "ACT Fibernet", "BSNL FTTH"],
    "SG": ["Singtel Home", "StarHub Residential", "M1 Fibre Home", "MyRepublic Home"],
    "AU": ["Telstra NBN", "Optus Home", "TPG Residential", "Aussie Broadband"],
    "TH": ["AIS Fibre", "TRUE Online", "3BB Home"],
    "MY": ["Unifi Home", "TIME Fibre", "Maxis Home Fibre"],
    "ID": ["IndiHome", "Biznet Home", "First Media"],
    "CH": ["Swisscom Fiber", "Sunrise Home", "Salt Fiber", "Init7 Fiber"],
    "IS": ["Siminn Home", "Vodafone Iceland Home", "Nova Fiber"],
    "SE": ["Telia Home", "Telenor SE Home", "Bahnhof Fiber", "Com Hem"],
    "HK": ["HKT Residential", "PCCW Home", "HKBN Fiber", "i-CABLE Home"],
    "JP": ["NTT FLET'S", "KDDI au Hikari", "SoftBank Hikari", "JCOM Home"],
    "VN": ["VNPT Fiber", "FPT Telecom Home", "Viettel Home"],
    "DE": ["Deutsche Telekom Home", "Vodafone DE Cable", "O2 Home", "1&1 Versatel"],
    "FR": ["Orange Fibre", "Freebox Home", "SFR Fibre", "Bouygues Home"],
    "NL": ["KPN Home", "Ziggo Residential", "Odido Home", "Delta Fiber"],
    "PT": ["MEO Home", "NOS Fiber", "Vodafone PT Home"],
    "RO": ["Digi Romania Home", "Orange RO Home", "Telekom RO"],
    "ES": ["Movistar Fiber", "Vodafone ES Home", "Orange ES", "MásMóvil"],
    "GE": ["MagtiCom Home", "Silknet Fiber", "Beeline GE"],
    "CZ": ["O2 CZ Home", "T-Mobile CZ", "Vodafone CZ"],
    "PL": ["Orange PL Home", "Play Next", "UPC PL", "T-Mobile PL"],
    "HR": ["Hrvatski Telekom", "A1 Hrvatska", "Telemach HR"],
    "GR": ["Cosmote Home", "Vodafone GR", "Nova GR"],
    "EE": ["Telia EE Home", "Elisa EE", "Tele2 EE"],
    "BS": ["BTC Bahamas Home", "Cable Bahamas", "Aliv Home"],
    "KY": ["Logic Cayman Home", "Digicel Cayman", "C3 Home"],
    "MU": ["Mauritius Telecom Home", "Emtel Fiber", "Canal+ Mauritius"],
    "SC": ["Cable & Wireless Seychelles", "Airtel Seychelles Home"],
    "BR": ["Claro Residencial", "Vivo Fibra", "TIM Live", "Oi Fibra"],
    "MX": ["Telmex Infinitum", "Izzi Home", "Totalplay Residencial", "Megacable"],
    "CO": ["Claro Colombia Hogar", "Movistar Hogar", "Tigo UNE"],
    "CR": ["Kolbi Home", "Liberty Costa Rica", "Telecable CR"],
}

# Optional mono-ISP lock (empty = multi-brand mix from COUNTRY_ISPS).
# Flagship brands are listed first in COUNTRY_ISPS for rotation priority.
COUNTRY_PRIMARY_ISP: Dict[str, str] = {}

# Rough RTT bands (ms) for catalog realism vs typical EU/US operator view
LATENCY_BAND: Dict[str, tuple] = {
    "vancouver": (18, 55),
    "dubai": (90, 160),
    "singapore": (140, 220),
    "zurich": (15, 45),
    "hongkong": (150, 230),
    "frankfurt": (12, 40),
    "tallinn": (20, 50),
    "bahamas": (40, 90),
    "cayman": (45, 95),
    "mauritius": (160, 260),
    "seychelles": (170, 280),
}

# Synthetic first-octet pools per region (catalog-only; not claimed as owned ASN)
OCTET_SEEDS: Dict[str, List[int]] = {
    "vancouver": [24, 50, 64, 70, 99, 104, 142, 173, 184, 206],
    "dubai": [5, 31, 37, 86, 91, 94, 185, 188, 213],
    "singapore": [27, 42, 49, 58, 103, 110, 119, 175, 202],
    "zurich": [46, 77, 85, 90, 128, 178, 195, 212],
    "hongkong": [14, 43, 58, 61, 112, 119, 123, 202, 218],
    "frankfurt": [37, 46, 78, 84, 91, 176, 185, 188, 217],
    "tallinn": [46, 90, 91, 185, 194, 213],
    "bahamas": [24, 64, 65, 104, 162, 192, 199],
    "cayman": [64, 65, 104, 162, 192, 199],
    "mauritius": [41, 102, 105, 197, 202],
    "seychelles": [41, 102, 154, 197],
}

CATALOG_KIND = "synthetic_product_catalog_v20260802"
DEFAULT_SIZE = 45  # mid of 30–50


def _sort_key(x: Dict[str, Any]):
    return (
        x.get("latency_ms", 999.0),
        -x.get("mimicry_score", 0),
        -x.get("reputation_score", 0),
    )


def _rng(country: str, salt: str = "") -> random.Random:
    h = hashlib.sha256(f"pcs-resip-{country}-{salt}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _synth_ip(rng: random.Random, location: str, index: int) -> str:
    seeds = OCTET_SEEDS.get(location) or OCTET_SEEDS["frankfurt"]
    a = seeds[index % len(seeds)]
    # Deterministic but varied; avoid .0/.255 on last octet
    b = 1 + (rng.randint(0, 250) + index * 7) % 250
    c = 1 + (rng.randint(0, 250) + index * 13) % 250
    d = 2 + (rng.randint(0, 250) + index * 17) % 252
    return f"{a}.{b}.{c}.{d}"


def generate_country_pool(
    country_code: str,
    pool_size: int = DEFAULT_SIZE,
    *,
    now: Optional[str] = None,
) -> List[Dict[str, Any]]:
    cc = country_code.upper()
    loc = COUNTRY_TO_LOCATION.get(cc, "frankfurt")
    isps = list(COUNTRY_ISPS.get(cc) or ["Regional Fiber Home", "National Broadband"])
    primary = COUNTRY_PRIMARY_ISP.get(cc)
    if primary:
        # Optional mono lock only when explicitly configured
        isps = [primary]
    lo, hi = LATENCY_BAND.get(loc, (25, 120))
    rng = _rng(cc, f"size={pool_size}|isp={primary or 'mix'}")
    ts = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    pool: List[Dict[str, Any]] = []
    for i in range(pool_size):
        base_lat = rng.uniform(lo, hi)
        # Prefer healthier head of list after sort: slightly better metrics for lower i
        quality = 1.0 - (i / max(pool_size, 1)) * 0.25
        entry = {
            "id": f"{cc}-{i+1:03d}",
            "ip": _synth_ip(rng, loc, i),
            "country": cc,
            "location": loc,
            "city_hint": loc,
            "isp": isps[i % len(isps)],
            "latency_ms": round(base_lat * (1.05 - quality * 0.08), 1),
            "jitter_ms": round(rng.uniform(0.4, 9.5) * (1.2 - quality * 0.3), 1),
            "packet_loss_pct": round(rng.uniform(0.0, 0.9) * (1.1 - quality * 0.4), 2),
            "reputation_score": int(rng.randint(78, 99) * quality + (1 - quality) * 72),
            "mimicry_score": int(rng.randint(82, 99) * quality + (1 - quality) * 75),
            "residential_class": "verified_residential",
            "healthy": True,
            "last_check": ts,
            "catalog_kind": CATALOG_KIND,
            "not_a_tunnel_endpoint": True,
            "source": "pcs_industrial_residential_catalog",
        }
        entry["reputation_score"] = max(70, min(99, entry["reputation_score"]))
        entry["mimicry_score"] = max(70, min(99, entry["mimicry_score"]))
        pool.append(entry)
    pool.sort(key=_sort_key)
    # Re-number ids stably after sort for display consistency? Keep generation ids.
    return pool


def write_pool(country_code: str, pool: List[Dict[str, Any]]) -> Path:
    cc = country_code.upper()
    path = POOL_DIR / f"{cc}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pool, indent=2) + "\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    return path


def ensure_full_catalog(
    pool_size: int = DEFAULT_SIZE,
    countries: Optional[List[str]] = None,
) -> Dict[str, Any]:
    codes = [c.upper() for c in (countries or list(COUNTRY_TO_LOCATION.keys()))]
    written = []
    for cc in codes:
        n = max(30, min(50, pool_size))
        pool = generate_country_pool(cc, n)
        path = write_pool(cc, pool)
        written.append({"country": cc, "count": len(pool), "path": str(path), "location": COUNTRY_TO_LOCATION.get(cc)})
    meta = {
        "version": 1,
        "catalog_kind": CATALOG_KIND,
        "pool_size_target": pool_size,
        "countries": len(written),
        "total_entries": sum(w["count"] for w in written),
        "pool_dir": str(POOL_DIR),
        "note": "Synthetic product catalog only — not VPS tunnel endpoints.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "detail": written,
    }
    meta_path = POOL_DIR / "_catalog_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


class IndustrialResidentialPool:
    """Suite-compatible pool object reading industrial dir."""

    def __init__(self, country_code: str, pool_size: int = DEFAULT_SIZE):
        self.country_code = country_code.upper()
        self.pool_size = pool_size
        self.pool_file = POOL_DIR / f"{self.country_code}.json"
        self._lock = threading.Lock()
        self.ips: List[Dict] = []
        self._load_or_generate()

    def _load_or_generate(self):
        # Industrial path only (~/.pcs_industrial_20260802). Never write Suite
        # legacy ~/.phantomcloak pools. Empty/corrupt/short files regenerate here.
        if self.pool_file.exists():
            try:
                raw = self.pool_file.read_text().strip()
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, list) and len(data) >= 30:
                        self.ips = data
                        return
            except Exception:
                pass
        self.ips = generate_country_pool(self.country_code, self.pool_size)
        write_pool(self.country_code, self.ips)

    def top_n(self, n: int = 15) -> List[Dict]:
        with self._lock:
            healthy = [ip for ip in self.ips if ip.get("healthy", True)]
            return sorted(healthy, key=_sort_key)[:n]

    def get_by_id(self, ip_id: str) -> Optional[Dict]:
        for e in self.ips:
            if e.get("id") == ip_id:
                return e
        return None

    def refresh_all(self):
        # Catalog refresh: re-stamp last_check; keep synthetic IPs stable
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        with self._lock:
            for e in self.ips:
                e["last_check"] = ts
                e["healthy"] = True
            write_pool(self.country_code, self.ips)


_pools: Dict[str, IndustrialResidentialPool] = {}


def get_pool(country_code: str, pool_size: int = DEFAULT_SIZE) -> IndustrialResidentialPool:
    code = country_code.upper()
    if code not in _pools:
        _pools[code] = IndustrialResidentialPool(code, pool_size=pool_size)
    return _pools[code]


def catalog_summary() -> Dict[str, Any]:
    """Counts-only residential catalog surface for dashboards.

    Never claims tunnel readiness. Does not invent VPS endpoints.
    Safe when pools are missing (returns zeros + note).
    """
    countries_on_disk = 0
    total_entries = 0
    sample_countries: List[str] = []
    meta: Optional[Dict[str, Any]] = None
    meta_path = POOL_DIR / "_catalog_meta.json"
    if meta_path.is_file():
        try:
            raw = json.loads(meta_path.read_text())
            if isinstance(raw, dict):
                meta = raw
        except Exception:
            meta = None

    try:
        pool_files = sorted(POOL_DIR.glob("*.json"))
    except Exception:
        pool_files = []

    for p in pool_files:
        if p.name.startswith("_"):
            continue
        try:
            data = json.loads(p.read_text())
            if not isinstance(data, list):
                continue
            n = len(data)
            countries_on_disk += 1
            total_entries += n
            if len(sample_countries) < 8:
                sample_countries.append(p.stem.upper())
        except Exception:
            continue

    return {
        "catalog_kind": CATALOG_KIND,
        "countries_count": countries_on_disk,
        "countries_catalogued": len(COUNTRY_TO_LOCATION),
        "total_entries": total_entries,
        "sample_countries": sample_countries,
        "pool_dir": str(POOL_DIR),
        "has_meta": meta is not None,
        "meta_total_entries": (meta or {}).get("total_entries") if meta else None,
        "meta_countries": (meta or {}).get("countries") if meta else None,
        "note": "Synthetic product catalog only — not VPS tunnel endpoints.",
        "not_a_tunnel_endpoint": True,
        "claims_tunnel_readiness": False,
        "source": "pcs_industrial_residential_catalog",
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Generate industrial residential IP catalog")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help="30–50 per country")
    ap.add_argument("--countries", nargs="*", help="Subset of country codes")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    size = max(30, min(50, args.size))
    meta = ensure_full_catalog(pool_size=size, countries=args.countries)
    if args.json:
        print(json.dumps(meta, indent=2))
    else:
        print(
            f"Wrote {meta['total_entries']} catalog entries across {meta['countries']} countries → {meta['pool_dir']}"
        )
        print("NOTE:", meta["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
