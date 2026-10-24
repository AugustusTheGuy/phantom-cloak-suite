# FEATURE TRUTH MATRIX — PCS Industrial v20260802

**Auditor role:** FTC-honest marketing + security product labeling  
**Date stamp:** 2026-08-02 / industrial tree `PCS_Industrial_20260802`  
**Code source of truth:** `shared/pcs_feature_matrix_v20260802.py`  
**Runtime gate source of truth:** `shared/pcs_server_readiness_v20260802.py` + `shared/pcs_preflight_obfuscation_gate_v20260802.py`

This document is the **customer-facing claim ceiling**. If copy exceeds this matrix, it is overselling.

---

## 1. Status vocabulary (only these four)

| Status | Meaning | Allowed marketing |
|--------|---------|-------------------|
| **implemented** | Code path works for the claimed *scope* in this industrial tree (may still fail-closed on runtime deps) | May describe as shipping **for that scope** |
| **config_needed** | Code exists; operator/runtime config required before customer claim | “Available when configured” / “needs your VPS” — **not** “live exits” |
| **scaffold** | Partial surface / stub | Roadmap only; never sell as ready |
| **not_started** | Planned; no product path yet | Do not mention as feature in ads |

**Deprecated vocabulary (do not use in new copy or UI):** `live` · `config` · `infra`.

---

## 2. Shell / readiness snapshot (audit time)

Observed from industrial shell + readiness (operator machine, no invented IPs):

| Signal | Value | Product implication |
|--------|-------|---------------------|
| `configured_count` | **0** | No client configs with real public VPS IPs |
| `server_filled_count` | **≥ 1** (package filled) | Server packages exist; still **not** customer-ready tunnels |
| `pending_ip_count` | **> 0** | Locations waiting for inventory IPs |
| `ok_for_protect` | **false** | Protect/activate must refuse |
| Status / dashboard / wizard | Allowed | Do not green-wash as “protected” |

Canonical rule:

```text
ok_for_protect  ⇔  configured_count > 0
protect session ⇔  ok_for_protect AND all required preflight layers pass
```

When `configured_count == 0`: **fail-closed** — blocked protect, killswitch path engaged, no false protected session. See `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md`, `CEO_VPS_RUNBOOK_v20260802.md`.

---

## 3. Hard product rules (non-negotiable)

1. **Industrial tree only** for industrial code/docs claims. Suite/legacy are import-only where noted.  
2. **Never claim live tunnel / multi-geo exits** when `configured_count == 0`.  
3. **Residential catalog ≠ residential proxy service.** Synthetic catalog IPs are UI metadata; they do **not** raise `configured_count` and are not tunnel endpoints.  
4. **Zero-leak / protect** = fail-closed until `configured_count > 0` **and** enabled layers pass. Honest limit: reduces leak risk; not mathematical impossibility of all side-channels.  
5. **No overselling** scaffolds, `not_started` items, or processor wiring as “live payments” without keys.

---

## 4. Residential pool — dual truth

| Surface | Status | What it is |
|---------|--------|------------|
| **Catalog UI** | **implemented** | Synthetic product catalog: 30–50 entries/country, ISP/latency/reputation fields, `not_a_tunnel_endpoint: true` |
| **Tunnel / proxy service** | **config_needed** | Requires owned VPS (or paid static/ISP **you control**) in `vps_inventory.json` + materialize |
| **Overall feature `residential_exit_pool`** | **config_needed** | Do not market as a live residential proxy network |

**Module:** `shared/pcs_residential_pool_industrial_v20260802.py`  
**Docs:** `RESIDENTIAL_CATALOG_v20260802.md`, `RESIDENTIAL_IP_VS_VPS_v20260802.md`  
**Honest label:** `residential_catalog_ui_ready__tunnel_needs_vps`

| Allowed copy | Forbidden copy |
|--------------|----------------|
| “Select from a residential-class catalog (metadata for UX); real egress needs your exits.” | “Residential proxies included / live residential pool online.” |
| “Server readiness shows pending IPs until you add VPS.” | “Connect via residential IP” using catalog addresses as endpoints |

API helper: `residential_truth()` in the feature matrix module.

---

## 5. Zero-leak / protect — fail-closed labeling

| Feature key | Status | Fail-closed | Notes |
|-------------|--------|-------------|-------|
| `zeroleak_preflight_gate` | implemented | **yes** | Blocks protect if servers not configured or any required layer fails |
| `dns_leak_guard` | implemented | **yes** (with gate) | Preflight DNS check |
| `persistent_protection_monitor` | implemented | **yes** | Layer map + trip on fail; continuous always-on stronger on Pro |
| `always_on_zeroleak_watchdog` | implemented (Pro) | **yes** | Still blocked when `configured_count==0` |
| `kill_switch_pf` | implemented | arms on activate | Real `pf` apply may need privilege / `PCS_FORCE_PF` |

**Substantiated claim (FTC):**  
“Before a session is marked protected, required on-device checks run; if any fail, killswitch logic is engaged and protected mode is refused.”

**Forbidden:** Absolute “zero data can ever leave under any OS bug” / “undetectable by all classifiers forever.”

Helpers: `protect_gate_truth()`, `fail_closed_protect_features()`.

---

## 6. Core feature matrix

| Feature | Status | One-line truth |
|---------|--------|----------------|
| `aes256_or_wireguard_tunnel` | **config_needed** | Packages ready; live exit needs owned VPS IPs |
| `no_logs_local_first` | **implemented** | Local state under `~/.pcs_industrial_20260802` |
| `kill_switch_pf` | **implemented** | Industrial pf rules path (not `/tmp`) |
| `dns_leak_guard` | **implemented** | Preflight DNS |
| `webrtc_leak_guard` | **config_needed** | Layer + verify guidance; full browser enforce needs config |
| `ipv6_leak_guard` | **config_needed** | Policy in KS path; confirm per OS before claim |
| `split_tunnel_policy` | **scaffold** | Surface only |
| `auto_connect_on_untrusted` | **scaffold** | Surface only |
| `purpose_wizard` | **implemented** | Purpose → location shell path |
| `zeroleak_preflight_gate` | **implemented** | Fail-closed; needs `configured_count>0` for protect |
| `obfuscation_layers_verify` | **implemented** | Method catalog + preflight; transport needs VPS |
| `tracker_vault_hide_restore` | **implemented** | Suite vault import; user hide/restore only |
| `dns_threat_blocklists` | **implemented** | Suite blocklists when Suite present |
| `multi_device_entitlement_core` | **config_needed** | Entitlement wiring incomplete |
| `honest_billing_display` | **implemented** | Pricing engine + payments surface |
| `speed_status_panel` | **scaffold** | Not shipping |
| `trust_center_docs` | **implemented** | In-tree docs |
| `streaming_resilience_profile` | **config_needed** | Needs working exits + validation |
| `auto_obfuscation_select` | **implemented** | Catalog auto-select logic |
| `port_forward_opt_in` | **scaffold** | Not shipping |
| `crypto_payment_option` | **config_needed** | Order path exists; processor addresses must be real |
| `anonymous_account_number` | **config_needed** | Not fully productized |
| `persistent_protection_monitor` | **implemented** | Fail-closed layer monitoring at preflight |

---

## 7. Pro-only feature matrix

| Feature | Status | One-line truth |
|---------|--------|----------------|
| `multi_hop_double_onion` | **config_needed** | Needs multi-node inventory |
| `dedicated_ip_option` | **not_started** | No product path yet |
| `residential_exit_pool` | **config_needed** | Catalog UI **implemented**; tunnel **config_needed** |
| `ip_health_rotator` | **config_needed** | Catalog refresh ≠ live farm rotation |
| `team_seats_rbac` | **implemented** | Suite RBAC when Suite present |
| `workspaces_audit_log` | **implemented** | Team audit surfaces |
| `adaptive_anti_dpi` | **scaffold** | Beyond catalog auto-select |
| `profile_cookie_import_export` | **scaffold** | Multilogin-class not shipping |
| `multi_window_profile_sync` | **scaffold** | Not shipping |
| `bulk_proxy_pipelines` | **scaffold** | Not a proxy farm |
| `public_rest_api` | **scaffold** | Not shipping |
| `cloud_profile_sync_opt_in` | **not_started** | — |
| `full_telemetry_self_host_opt_in` | **scaffold** | Opt-in only if ever enabled |
| `granular_roles` | **implemented** | With RBAC |
| `device_mesh` | **scaffold** | Zero Trust-class not shipping |
| `sso_scim_scaffold` | **not_started** | Enterprise identity not started |
| `compliance_export_scaffold` | **scaffold** | Packs not shipping |
| `always_on_zeroleak_watchdog` | **implemented** | Fail-closed; still needs configured servers for protect |

---

## 8. Pricing (authoritative product numbers)

**Source of truth for list pricing in industrial code:** `shared/pcs_pricing_engine_v20260802.py`  
(Report: `docs_v20260802/PhantomCloak_Pricing_Referral_Features_Report.md`)

| Plan | Monthly | Annual | Effective /mo annual |
|------|---------|--------|----------------------|
| Core | **$11.99** | **$59.88** | **$4.99** |
| Pro | **$39.00** founder | **$348.00** | **$29.00** |

Intro week (optional; display end date — FTC): Core first month **$4.99**, Pro first month **$29**.

**Note:** `PRICING_AND_CONVERSION_v20260802.md` contains an alternate conversion experiment ($8.99 / $24.99). That is **not** the engine default. Do not mix numbers in the same campaign asset without labeling which schedule applies.

Value surplus claims must only cite **implemented** differentiators (zero-leak preflight, tracker vault, KS auto-on, local-first) — not residential tunnels or multi-hop while those are `config_needed`.

---

## 9. Campaign / competitive copy gates

Aligned with `CAMPAIGN_POSTS_READY_v20260802.md` and `COMPETITIVE_INTEL_AND_TIERS_v20260802.md`:

| Theme | OK when | Block if |
|-------|---------|----------|
| Verify-before-send / fail-closed | Gate code is **implemented** (true now) | Claiming protect works without VPS |
| Tracker vault | **implemented** (Suite path) | Calling it “reinjection” or automatic |
| KS arms on Activate | **implemented** | Claiming OS-level always-on without privilege caveats |
| Residential / multi-hop | Only as **config_needed** + readiness UI | Selling as live network |
| Team RBAC | **implemented** (Pro) | Claiming SSO/SCIM (not_started) |
| Pricing | Engine numbers above | Fake testimonials / sock accounts |

---

## 10. Tier catalog alignment

`shared/pcs_tier_catalog_v20260802.py` defines **which** features belong to Core vs Pro.  
`shared/pcs_feature_matrix_v20260802.py` defines **status truth** for each feature.

| Tier | Label | Scope |
|------|-------|-------|
| `core` | PhantomCloak Core | Personal privacy / VPN-DSI class |
| `pro` | PhantomCloak Pro | Core + seats/RBAC + industrial roadmap |

---

## 11. How to re-audit (operator)

```bash
cd ~/Desktop/PCS_Industrial_20260802

# Feature statuses (new vocabulary)
.venv/bin/python -c "
from shared.pcs_feature_matrix_v20260802 import (
    status_counts, residential_truth, protect_gate_truth, as_truth_table
)
import json
print('counts', status_counts())
print('residential', residential_truth())
print('protect', protect_gate_truth()['ok_for_protect_rule'])
"

# Runtime protect gate (must stay fail-closed at configured_count 0)
.venv/bin/python core_product/pcs_app_shell_v20260802.py --status | head -80
.venv/bin/python -c "
from shared.pcs_server_readiness_v20260802 import scan_readiness, gate_snapshot
import json
r=scan_readiness(); g=gate_snapshot(r)
print(json.dumps({
  'status': r['status'],
  'configured_count': r['configured_count'],
  'ok_for_protect': g['ok_for_protect'],
}, indent=2))
"

# Dry-run protect path
.venv/bin/python -c "
from shared.pcs_preflight_obfuscation_gate_v20260802 import dry_run_fail_closed
import json; print(json.dumps(dry_run_fail_closed(), indent=2, default=str)[:1200])
"
```

Expect at baseline without VPS inventory IPs:

- `configured_count == 0`
- `ok_for_protect == false`
- dry-run / activate → `status: blocked`, `reason: servers_not_configured`

---

## 12. Change log (this audit)

| Item | Before | After |
|------|--------|-------|
| Status labels | `live` / `config` / `scaffold` / `infra` | `implemented` / `config_needed` / `scaffold` / `not_started` |
| `residential_exit_pool` | single `config` | overall `config_needed` + `catalog_ui=implemented` + `tunnel_service=config_needed` |
| Protect / zero-leak | partially documented | explicit `fail_closed` + `protect_requires_configured_count_gt_0` on gate features |
| `dedicated_ip` / cloud profiles / SSO | `infra` | `not_started` |
| Launcher print | “Live features” | “Implemented features” + protect + residential truth lines |
| FTC claims doc | old status words | new vocabulary + pointer to this matrix |

---

## 13. Related docs

| Doc | Role |
|-----|------|
| `FTC_HONEST_CLAIMS_v20260802.md` | Allowed / forbidden claims |
| `RESIDENTIAL_CATALOG_v20260802.md` | Catalog vs tunnel |
| `RESIDENTIAL_IP_VS_VPS_v20260802.md` | What raises `configured_count` |
| `VPS_MATERIALIZE_STATUS_v20260802.md` | Materialize snapshot |
| `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md` | Zero-config ops playbook |
| `CAMPAIGN_POSTS_READY_v20260802.md` | Grassroots copy (must stay under this ceiling) |
| `PRICING_AND_CONVERSION_v20260802.md` | Conversion experiments (label non-default prices) |

**No overselling. Catalog UI ≠ tunnel. Protect stays fail-closed until `configured_count > 0`.**
