"""Residential product catalog: size bounds, required fields, not tunnel endpoints."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.pcs_residential_pool_industrial_v20260802 import (  # noqa: E402
    CATALOG_KIND,
    COUNTRY_TO_LOCATION,
    POOL_DIR,
    ensure_full_catalog,
    generate_country_pool,
    get_pool,
)

REQUIRED_FIELDS = (
    "id",
    "ip",
    "country",
    "location",
    "isp",
    "latency_ms",
    "reputation_score",
    "mimicry_score",
    "residential_class",
    "healthy",
    "catalog_kind",
    "not_a_tunnel_endpoint",
    "source",
)


def _ensure_pools() -> None:
    """Idempotent: guarantee on-disk pools for every COUNTRY_TO_LOCATION key."""
    ensure_full_catalog(pool_size=45)


def test_every_country_has_30_to_50_entries():
    _ensure_pools()
    shortfalls = []
    for cc in COUNTRY_TO_LOCATION:
        path = POOL_DIR / f"{cc}.json"
        assert path.is_file(), f"missing pool file for {cc}"
        data = json.loads(path.read_text())
        assert isinstance(data, list), f"{cc} pool is not a list"
        n = len(data)
        if not (30 <= n <= 50):
            shortfalls.append((cc, n))
    assert not shortfalls, f"countries outside 30–50 entries: {shortfalls}"


def test_required_fields_and_not_a_tunnel_endpoint():
    _ensure_pools()
    for cc in COUNTRY_TO_LOCATION:
        data = json.loads((POOL_DIR / f"{cc}.json").read_text())
        assert data, f"empty pool {cc}"
        for entry in data:
            for field in REQUIRED_FIELDS:
                assert field in entry, f"{cc} entry missing field {field}: {entry.get('id')}"
            assert entry["not_a_tunnel_endpoint"] is True, (
                f"{cc}/{entry.get('id')} must set not_a_tunnel_endpoint=True"
            )
            assert entry["catalog_kind"] == CATALOG_KIND
            assert entry["country"] == cc
            assert entry["location"] == COUNTRY_TO_LOCATION[cc]
            assert isinstance(entry["ip"], str) and entry["ip"].count(".") == 3


def test_generate_country_pool_bounds_and_flags():
    pool = generate_country_pool("CH", 40)
    assert 30 <= len(pool) <= 50
    assert all(e.get("not_a_tunnel_endpoint") is True for e in pool)
    assert all(e.get("catalog_kind") == CATALOG_KIND for e in pool)


def test_get_pool_reads_industrial_dir():
    _ensure_pools()
    pool = get_pool("DE")
    tops = pool.top_n(5)
    assert len(tops) >= 1
    assert tops[0].get("not_a_tunnel_endpoint") is True
    assert pool.pool_file == POOL_DIR / "DE.json"


def test_catalog_does_not_claim_tunnel_readiness():
    """Catalog meta must declare synthetic-only; never a readiness signal."""
    _ensure_pools()
    meta_path = POOL_DIR / "_catalog_meta.json"
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text())
    assert meta.get("catalog_kind") == CATALOG_KIND
    assert "not VPS" in (meta.get("note") or "") or "not" in (meta.get("note") or "").lower()
    assert meta.get("countries") == len(COUNTRY_TO_LOCATION)
    assert 30 * len(COUNTRY_TO_LOCATION) <= meta.get("total_entries", 0) <= 50 * len(
        COUNTRY_TO_LOCATION
    )


def test_shell_prefers_industrial_get_pool():
    """App shell helper prefers industrial module when importable."""
    from core_product.pcs_app_shell_v20260802 import (  # type: ignore
        _import_industrial_residential_pool,
        PcsAppShell,
    )

    mod = _import_industrial_residential_pool()
    assert mod is not None
    assert hasattr(mod, "get_pool")
    shell = PcsAppShell(tier="core")
    assert shell._industrial_pool is not None
    pool = shell._get_residential_pool("CH")
    entry = pool.top_n(1)[0]
    assert entry.get("not_a_tunnel_endpoint") is True
