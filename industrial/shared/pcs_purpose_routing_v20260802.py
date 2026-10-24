#!/usr/bin/env python3
"""Purpose → country routing for industrial fleets (Suite purpose_catalog aligned).

Does not modify Suite files. Import-only reference of top-5 lists.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Top 5 per Suite purpose_catalog.py (read-only alignment)
PURPOSE_TOP5: Dict[str, List[Dict[str, Any]]] = {
    "streaming": [
        {"code": "US", "name": "United States", "location_keys": ["us", "vancouver"]},
        {"code": "GB", "name": "United Kingdom", "location_keys": ["gb", "uk"]},
        {"code": "CA", "name": "Canada", "location_keys": ["vancouver", "ca"]},
        {"code": "AU", "name": "Australia", "location_keys": ["au", "singapore"]},
        {"code": "DE", "name": "Germany", "location_keys": ["germany", "frankfurt"]},
    ],
    "crypto": [
        {"code": "AE", "name": "UAE (Dubai)", "location_keys": ["dubai"]},
        {"code": "SG", "name": "Singapore", "location_keys": ["singapore"]},
        {"code": "CH", "name": "Switzerland", "location_keys": ["zurich", "ch"]},
        {"code": "HK", "name": "Hong Kong", "location_keys": ["hongkong"]},
        {"code": "KY", "name": "Cayman Islands", "location_keys": ["cayman"]},
    ],
    "browsing": [
        {"code": "IS", "name": "Iceland", "location_keys": ["is", "zurich"]},
        {"code": "CH", "name": "Switzerland", "location_keys": ["zurich"]},
        {"code": "NL", "name": "Netherlands", "location_keys": ["nl", "germany"]},
        {"code": "CA", "name": "Canada", "location_keys": ["vancouver"]},
        {"code": "DE", "name": "Germany", "location_keys": ["germany", "frankfurt"]},
    ],
    "digital_nomad": [
        {"code": "PT", "name": "Portugal", "location_keys": ["pt", "germany"]},
        {"code": "ES", "name": "Spain", "location_keys": ["es", "germany"]},
        {"code": "TH", "name": "Thailand", "location_keys": ["th", "singapore"]},
        {"code": "MX", "name": "Mexico", "location_keys": ["mx", "bahamas"]},
        {"code": "CO", "name": "Colombia", "location_keys": ["co", "bahamas"]},
    ],
    "other": [
        {"code": "CA", "name": "Canada", "location_keys": ["vancouver"]},
        {"code": "CH", "name": "Switzerland", "location_keys": ["zurich"]},
        {"code": "SG", "name": "Singapore", "location_keys": ["singapore"]},
        {"code": "DE", "name": "Germany", "location_keys": ["germany", "frankfurt"]},
        {"code": "AE", "name": "UAE", "location_keys": ["dubai"]},
    ],
}

# Priority B essentials (5–8 IPs each when funded)
PRIORITY_B_COUNTRIES: List[Dict[str, Any]] = [
    {"code": "JP", "location_keys": ["jp", "hongkong"]},
    {"code": "FR", "location_keys": ["fr", "germany"]},
    {"code": "BR", "location_keys": ["br", "bahamas"]},
    {"code": "IN", "location_keys": ["in", "dubai"]},
    {"code": "EE", "location_keys": ["ee", "germany"]},
    {"code": "BS", "location_keys": ["bahamas"]},
    {"code": "MU", "location_keys": ["mauritius"]},
    {"code": "SC", "location_keys": ["seychelles"]},
    {"code": "VN", "location_keys": ["vn", "hongkong"]},
    {"code": "MY", "location_keys": ["my", "singapore"]},
]

# MVP Priority A
PRIORITY_A: List[str] = ["US", "GB", "CA", "DE", "AE"]

# Country code → preferred industrial location key for materialize
CODE_TO_LOCATION: Dict[str, str] = {
    "US": "us",
    "GB": "gb",
    "CA": "vancouver",
    "AU": "au",
    "DE": "germany",
    "AE": "dubai",
    "SG": "singapore",
    "CH": "zurich",
    "HK": "hongkong",
    "KY": "cayman",
    "IS": "is",
    "NL": "nl",
    "PT": "pt",
    "ES": "es",
    "TH": "th",
    "MX": "mx",
    "CO": "co",
    "JP": "jp",
    "FR": "fr",
    "BR": "br",
    "IN": "in",
    "EE": "ee",
    "BS": "bahamas",
    "MU": "mauritius",
    "SC": "seychelles",
    "VN": "vn",
    "MY": "my",
    "ID": "id",
}


def list_purposes() -> List[str]:
    return list(PURPOSE_TOP5.keys())


def top5_for_purpose(purpose: str) -> List[Dict[str, Any]]:
    return list(PURPOSE_TOP5.get(purpose, PURPOSE_TOP5["other"]))


def purpose_top5_summary() -> Dict[str, Any]:
    """Compact dashboard/API surface: top-5 countries per purpose + MVP fleet math.

    Offline-safe pure data (no inventory, no network). Safe to embed in /api/status
    even when Suite is missing.
    """
    by_purpose: Dict[str, List[Dict[str, str]]] = {}
    for purpose, rows in PURPOSE_TOP5.items():
        by_purpose[purpose] = [
            {
                "code": r["code"],
                "name": r.get("name") or r["code"],
                "location_key": location_key_for_code(r["code"]),
            }
            for r in rows
        ]
    est = fleet_size_estimate(5, include_priority_b=False)
    return {
        "purposes": list_purposes(),
        "by_purpose": by_purpose,
        "priority_a": list(PRIORITY_A),
        "mvp_countries": est["mvp_countries"],
        "mvp_ips": est["mvp_ips"],
        "use_case_union_countries": est["use_case_union_countries"],
        "use_case_union_ips": est["use_case_union_ips"],
        "note": (
            "Purpose → top-5 country preference for fleet planning. "
            "Not live tunnel endpoints — exits require owned VPS IPs in inventory."
        ),
    }


def location_key_for_code(code: str) -> str:
    return CODE_TO_LOCATION.get(code.upper(), code.lower())


def purpose_routing_template() -> Dict[str, List[str]]:
    """Map purpose → preferred location keys (first key per country)."""
    out: Dict[str, List[str]] = {}
    for purpose, rows in PURPOSE_TOP5.items():
        keys: List[str] = []
        for r in rows:
            keys.append(location_key_for_code(r["code"]))
        out[purpose] = keys
    return out


def union_top5_codes() -> List[str]:
    seen = set()
    ordered: List[str] = []
    for rows in PURPOSE_TOP5.values():
        for r in rows:
            c = r["code"].upper()
            if c not in seen:
                seen.add(c)
                ordered.append(c)
    return ordered


def fleet_size_estimate(ips_per_country: int = 5, include_priority_b: bool = False) -> Dict[str, Any]:
    a = list(PRIORITY_A)
    union = union_top5_codes()
    b = [x["code"] for x in PRIORITY_B_COUNTRIES]
    return {
        "mvp_countries": a,
        "mvp_ips": len(a) * ips_per_country,
        "use_case_union_countries": union,
        "use_case_union_ips": len(union) * ips_per_country,
        "priority_b_countries": b,
        "priority_b_ips": len(b) * ips_per_country if include_priority_b else 0,
        "full_ips": (len(union) + (len(b) if include_priority_b else 0)) * ips_per_country,
    }


def mvp_coverage_for_purpose(purpose: str) -> Dict[str, Any]:
    """Which top-5 codes for purpose are already covered by MVP Priority A."""
    top = top5_for_purpose(purpose)
    codes = [r["code"].upper() for r in top]
    covered = [c for c in codes if c in PRIORITY_A]
    missing = [c for c in codes if c not in PRIORITY_A]
    return {
        "purpose": purpose,
        "top5": codes,
        "mvp_covered": covered,
        "mvp_missing": missing,
        "mvp_coverage": f"{len(covered)}/{len(codes)}",
    }


def main() -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Purpose → country routing (Suite purpose_catalog aligned)"
    )
    ap.add_argument(
        "--list-purposes",
        action="store_true",
        help="List known purposes (streaming, crypto, browsing, digital_nomad, other)",
    )
    ap.add_argument(
        "--top5",
        metavar="PURPOSE",
        help="Print top-5 countries for a purpose (e.g. streaming)",
    )
    ap.add_argument(
        "--fleet-estimate",
        action="store_true",
        help="Print MVP / union / priority-B fleet size estimate",
    )
    ap.add_argument(
        "--mvp-coverage",
        metavar="PURPOSE",
        nargs="?",
        const="*",
        help="MVP Priority A coverage for PURPOSE (or all if omitted after flag)",
    )
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    if not any((args.list_purposes, args.top5, args.fleet_estimate, args.mvp_coverage is not None)):
        ap.print_help()
        return 2

    payload: Dict[str, Any] = {}

    if args.list_purposes:
        purposes = list_purposes()
        payload["purposes"] = purposes
        if not args.json:
            print("purposes:")
            for p in purposes:
                print(f"  {p}")

    if args.top5:
        purpose = args.top5.strip().lower()
        rows = top5_for_purpose(purpose)
        keys = purpose_routing_template().get(purpose) or [
            location_key_for_code(r["code"]) for r in rows
        ]
        payload["top5"] = {
            "purpose": purpose if purpose in PURPOSE_TOP5 else "other",
            "countries": rows,
            "location_keys": keys if purpose in PURPOSE_TOP5 else [
                location_key_for_code(r["code"]) for r in rows
            ],
        }
        if not args.json:
            label = purpose if purpose in PURPOSE_TOP5 else f"{purpose} (fallback: other)"
            print(f"top5 purpose={label}")
            for i, r in enumerate(rows, 1):
                loc = location_key_for_code(r["code"])
                print(f"  {i}. {r['code']:3}  {r['name']:<22}  location_key={loc}")

    if args.mvp_coverage is not None:
        if args.mvp_coverage == "*":
            cov = {p: mvp_coverage_for_purpose(p) for p in list_purposes()}
        else:
            cov = {args.mvp_coverage: mvp_coverage_for_purpose(args.mvp_coverage.strip().lower())}
        payload["mvp_coverage"] = cov
        payload["mvp_priority_a"] = list(PRIORITY_A)
        if not args.json:
            print(f"mvp_priority_a={','.join(PRIORITY_A)}")
            for p, c in cov.items():
                print(
                    f"  {p}: covered={','.join(c['mvp_covered']) or '-'} "
                    f"missing={','.join(c['mvp_missing']) or '-'} "
                    f"({c['mvp_coverage']})"
                )

    if args.fleet_estimate:
        est = fleet_size_estimate(5, include_priority_b=True)
        payload["fleet_estimate"] = est
        if not args.json:
            print(
                f"mvp_ips={est['mvp_ips']} "
                f"use_case_union_ips={est['use_case_union_ips']} "
                f"full_ips={est['full_ips']}"
            )
            print(f"  mvp_countries={','.join(est['mvp_countries'])}")

    if args.json:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
