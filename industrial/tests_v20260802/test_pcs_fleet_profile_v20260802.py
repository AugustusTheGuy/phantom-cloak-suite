"""Hermetic tests for inventory v2 pools + synthetic profile gates."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_set_pool_rejects_private_and_accepts_public(tmp_path, monkeypatch):
    import shared.pcs_inventory_v2_v20260802 as inv

    inv.INVENTORY_PATH = tmp_path / "vps_inventory.json"
    inv.STATE = tmp_path
    data, errs = inv.set_pool_ips(
        "germany",
        ["10.0.0.1", "8.8.4.4", "203.0.113.10", "1.1.1.1"],
        path=inv.INVENTORY_PATH,
    )
    assert any("10.0.0.1" in e for e in errs)
    assert any("203.0.113.10" in e for e in errs)
    members = inv.iter_pool_members(data)
    ips = {m["ip"] for m in members}
    assert "8.8.4.4" in ips or "1.1.1.1" in ips
    assert "10.0.0.1" not in ips


def test_migrate_v1_single_ip(tmp_path):
    import shared.pcs_inventory_v2_v20260802 as inv

    p = tmp_path / "vps_inventory.json"
    p.write_text(
        json.dumps(
            {
                "version": 1,
                "ssh_user": "root",
                "locations": {"dubai": {"ip": "1.1.1.1", "enabled": True}},
            }
        )
    )
    inv.INVENTORY_PATH = p
    data = inv.load_inventory(p)
    assert data["version"] == 2
    assert len(data["locations"]["dubai"]["pool"]) == 1
    assert data["locations"]["dubai"]["pool"][0]["ip"] == "1.1.1.1"
    # purpose_routing written into inventory v2 on load
    assert "purpose_routing" in data
    assert "streaming" in data["purpose_routing"]
    assert isinstance(data["purpose_routing"]["streaming"], list)
    assert len(data["purpose_routing"]["streaming"]) == 5
    on_disk = json.loads(p.read_text())
    assert on_disk.get("version") == 2
    assert "purpose_routing" in on_disk
    assert "streaming" in on_disk["purpose_routing"]


def test_materialize_resolve_primary_from_pool():
    """v1 client write uses primary; pool-only inventory still resolves."""
    from shared.pcs_materialize_singbox_v20260802 import resolve_location_primary

    ip, user, member = resolve_location_primary(
        {
            "ip": "",
            "ssh_user": "root",
            "pool": [
                {"id": "de-01", "ip": "8.8.8.8", "ssh_user": "deploy", "enabled": True},
                {"id": "de-02", "ip": "8.8.4.4", "enabled": True},
            ],
        }
    )
    assert ip == "8.8.8.8"
    assert user == "deploy"
    assert member.get("id") == "de-01"

    # Top-level primary still wins (v1 path)
    ip2, _, _ = resolve_location_primary(
        {"ip": "1.1.1.1", "pool": [{"ip": "8.8.8.8", "enabled": True}]}
    )
    assert ip2 == "1.1.1.1"


def test_purpose_routing_written_on_load_v2_missing_key(tmp_path):
    """Existing v2 inventory without purpose_routing gets it persisted on load."""
    import shared.pcs_inventory_v2_v20260802 as inv

    p = tmp_path / "vps_inventory.json"
    p.write_text(
        json.dumps(
            {
                "version": 2,
                "ssh_user": "root",
                "locations": {
                    "germany": {
                        "ip": "",
                        "enabled": True,
                        "pool": [],
                    }
                },
            }
        )
    )
    inv.INVENTORY_PATH = p
    data = inv.load_inventory(p)
    assert data["purpose_routing"]["crypto"]
    disk = json.loads(p.read_text())
    assert disk["purpose_routing"]["browsing"]
    # Second load must not wipe customizations if already present
    data["purpose_routing"]["streaming"] = ["us"]
    inv.save_inventory(data, p)
    data2 = inv.load_inventory(p)
    assert data2["purpose_routing"]["streaming"] == ["us"]


def test_purpose_top5_and_fleet_math():
    from shared.pcs_purpose_routing_v20260802 import (
        PURPOSE_TOP5,
        PRIORITY_A,
        fleet_size_estimate,
        list_purposes,
        mvp_coverage_for_purpose,
        purpose_routing_template,
        purpose_top5_summary,
        top5_for_purpose,
    )

    assert set(list_purposes()) >= {"streaming", "crypto", "browsing", "digital_nomad", "other"}
    assert len(top5_for_purpose("streaming")) == 5
    est = fleet_size_estimate(5, include_priority_b=True)
    assert est["mvp_ips"] == 25
    assert est["full_ips"] >= 25
    assert set(PRIORITY_A) == {"US", "GB", "CA", "DE", "AE"}
    tpl = purpose_routing_template()
    assert tpl["streaming"][0] == "us"
    cov = mvp_coverage_for_purpose("streaming")
    assert "US" in cov["mvp_covered"]
    assert cov["mvp_coverage"].startswith("4/")
    summary = purpose_top5_summary()
    assert len(summary["purposes"]) >= 5
    assert len(summary["by_purpose"]["streaming"]) == 5
    assert summary["mvp_ips"] == 25


def test_purpose_routing_cli_list_and_top5(capsys):
    from shared.pcs_purpose_routing_v20260802 import main
    import sys

    old = sys.argv
    try:
        sys.argv = ["pcs_purpose_routing", "--list-purposes"]
        assert main() == 0
        out = capsys.readouterr().out
        assert "streaming" in out
        assert "crypto" in out

        sys.argv = ["pcs_purpose_routing", "--top5", "streaming"]
        assert main() == 0
        out = capsys.readouterr().out
        assert "US" in out
        assert "location_key=" in out

        sys.argv = ["pcs_purpose_routing", "--list-purposes", "--top5", "streaming", "--json"]
        assert main() == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert "purposes" in payload
        assert payload["top5"]["purpose"] == "streaming"
        assert len(payload["top5"]["countries"]) == 5
    finally:
        sys.argv = old


def test_synthetic_profile_fail_closed_without_wipe_or_ip():
    from shared.pcs_synthetic_profile_v20260802 import build_profile_seed, gate_profile

    s = build_profile_seed("germany", exit_ip="", wipe_done=False, purpose="crypto")
    g = gate_profile(s)
    assert g["ok"] is False

    s2 = build_profile_seed(
        "germany",
        exit_ip="8.8.8.8",
        wipe_done=True,
        purpose="browsing",
        asn_class="isp",
        leak_checks_ok=True,
    )
    g2 = gate_profile(s2)
    assert s2["mimicry"]["score"] >= 55
    assert g2["ok"] is True


def test_locale_packs_for_core_locations():
    from shared.pcs_synthetic_profile_v20260802 import locale_for_location

    for loc in ("germany", "dubai", "vancouver", "hongkong"):
        p = locale_for_location(loc)
        assert p["tz"]
        assert p["locale"]


# Industrial codes required by Agent 6 locale expansion
REQUIRED_LOCALE_KEYS = (
    "us",
    "gb",
    "au",
    "pt",
    "es",
    "th",
    "mx",
    "co",
    "jp",
    "fr",
    "is",
    "nl",
    "ch",
    "sg",
)


def test_locale_packs_expanded_industrial_codes():
    from shared.pcs_synthetic_profile_v20260802 import LOCALE_PACKS, locale_for_location

    for key in REQUIRED_LOCALE_KEYS:
        assert key in LOCALE_PACKS, f"missing LOCALE_PACKS[{key!r}]"
        p = locale_for_location(key)
        assert p["tz"] and p["tz"] != "UTC", f"{key}: expected non-UTC tz, got {p['tz']}"
        assert p["locale"], f"{key}: empty locale"
        assert isinstance(p["languages"], list) and p["languages"], f"{key}: languages"
        geo = p["geo"]
        assert geo["city"] and geo["city"] != "Unknown"
        assert isinstance(geo["lat"], (int, float)) and isinstance(geo["lon"], (int, float))


def test_locale_pack_spot_checks():
    from shared.pcs_synthetic_profile_v20260802 import locale_for_location

    assert locale_for_location("jp")["tz"] == "Asia/Tokyo"
    assert locale_for_location("fr")["locale"] == "fr-FR"
    assert locale_for_location("is")["geo"]["city"] == "Reykjavik"
    assert locale_for_location("nl")["tz"] == "Europe/Amsterdam"
    assert locale_for_location("ch")["tz"] == "Europe/Zurich"
    assert locale_for_location("sg")["tz"] == "Asia/Singapore"
    assert locale_for_location("pt")["locale"] == "pt-PT"
    assert locale_for_location("th")["tz"] == "Asia/Bangkok"
    assert locale_for_location("mx")["locale"] == "es-MX"
    assert locale_for_location("co")["tz"] == "America/Bogota"
    # aliases
    assert locale_for_location("uk")["locale"] == "en-GB"
    assert locale_for_location("switzerland")["tz"] == "Europe/Zurich"


def test_purpose_aware_thresholds():
    from shared.pcs_synthetic_profile_v20260802 import (
        THRESHOLD_DEFAULT,
        THRESHOLD_HIGH_STAKES,
        build_profile_seed,
        threshold_for_purpose,
    )

    assert threshold_for_purpose("crypto") == THRESHOLD_HIGH_STAKES == 70
    assert threshold_for_purpose("streaming") == 70
    assert threshold_for_purpose("browsing") == THRESHOLD_DEFAULT == 55
    assert threshold_for_purpose("digital_nomad") == 55
    assert threshold_for_purpose("other") == 55

    high = build_profile_seed("sg", purpose="crypto", exit_ip="1.1.1.1", wipe_done=True)
    assert high["mimicry"]["threshold"] == 70
    low = build_profile_seed("nl", purpose="browsing", exit_ip="1.1.1.1", wipe_done=True)
    assert low["mimicry"]["threshold"] == 55


def test_seed_and_write_from_status_no_invented_ip(tmp_path, monkeypatch):
    import shared.pcs_synthetic_profile_v20260802 as syn

    monkeypatch.setattr(syn, "PROFILE_DIR", tmp_path / "synthetic_profiles")
    out = syn.seed_and_write_from_status(
        location="jp",
        purpose="browsing",
        exit_ip="",
        slot_id="status",
    )
    assert out["pass_gate"] is False  # no exit IP + no wipe
    assert out["exit_ip_present"] is False
    assert out["no_third_party_accounts"] is True
    path = tmp_path / "synthetic_profiles" / "jp" / "status.json"
    assert path.is_file()
    data = json.loads(path.read_text())
    assert data["locale"] == "ja-JP"
    assert "no Google" in data["seeded_artifacts"]["note"] or "no third-party" in data[
        "seeded_artifacts"
    ]["note"]
