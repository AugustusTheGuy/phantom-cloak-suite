# CEO Industrial Status Brief — PCS v20260802

**As-of:** 2026-08-03 (live scan)  
**Code tree:** `~/Desktop/PCS_Industrial_20260802/`  
**Runtime/secrets:** `~/.pcs_industrial_20260802/` (not in product tree)  
**Rule:** Owned VPS IPs only. Synthetic residential catalog is UX metadata — not tunnel endpoints.

---

## Executive snapshot

| Metric | Value | Meaning |
|--------|-------|---------|
| Readiness `status` | `server_package_ready_pending_client_ips` | Server crypto packages ready; no live client exits |
| `configured_count` | **0** | No production client configs with real IPs |
| `server_filled_count` | **10** | 8 location packages + 2 HY2 VPS path previews |
| `pending_ip_count` | **9** | 8 geos + `frankfurt` alias sidecar |
| `secrets_ok` / inventory | **8 / 0** | Keys exist for all 8; **zero** inventory IPs set |
| Catalog | **36 countries · 1,620 entries** | Synthetic product catalog (45/country) |
| Tests | **56 pass · 1 fail** | Fail: pending count 9 vs 8 (alias accounting) |
| Readiness self-test | **20/20** | IP classify / gate exit codes OK |
| Time Machine on state dir | **`[Included]`** | **Risk — secrets may be backed up unencrypted** |

**Bottom line:** Industrial software path is built and gated fail-closed. **Production tunnels are blocked solely on CEO-owned VPS public IPs** in inventory + deploy.

---

## 1. What is production-ready today

| Area | Status | Evidence / path |
|------|--------|-----------------|
| App shell (Core/Pro) + launchers | Ready (local) | `core_product/`, `launches_v20260802/` |
| Command Center UX v2 | Ready | `dashboards_v20260802/pcs_suite_command_center_v2_*` |
| Landing + payments HTTP | Ready (local) | XMR/BTC/ETH/SOL/CARD; Stripe when key set |
| Materialize (keys, server fill, deploy script gen) | Ready | `shared/pcs_materialize_singbox_v20260802.py` · last run `ok: true` |
| Filled server package (8 geos) | Ready to scp | `~/.pcs…/vps_server_package/sing-box-*-reality.json` |
| Deploy tooling | Ready | `deploy_filled_to_vps.sh`, `pcs_deploy_one_*.sh`, bootstrap + path rewrite |
| Secrets lifecycle | Ready | `location_keys.json` mode `0600`; dirs `0700`; fingerprint `f2c528299626e3a3` |
| HY2 certs (`dubai`, `hongkong`) | Ready | `secrets/hy2_certs/{dubai,hongkong}/` |
| Preflight / zero-leak gate | Ready (fail-closed) | `configured_count==0` **blocks** protect/activate |
| Verify bridge | Ready (offline dry-run) | Suite tools discovered 5/5; live verify needs tunnel |
| Kill-switch (pf industrial) | Ready (local rules) | `~/.pcs…/pf_rules/pcs_killswitch_v20260802.pf.conf` |
| Residential **catalog** (UX only) | Ready | 36 CC files · not tunnel endpoints |
| Operator docs | Ready | CEO runbook, checklist, incident zero-count, secrets, HOWTO link |

| VPS exit locations (package filled) | Reality :443 | HY2 :8443 |
|-------------------------------------|--------------|-----------|
| dubai, hongkong | yes | yes |
| vancouver, germany (+frankfurt alias), bahamas, cayman, mauritius, seychelles | yes | no |

---

## 2. What is blocked on CEO VPS IPs

| Blocker | Current | Unblocks |
|---------|---------|----------|
| `vps_inventory.json` IPs | All 8 empty | Set real **owned** public IPv4/hostname |
| Client `singbox/<loc>.json` | Only `*.pending.json` | Re-materialize after IP |
| `configured_count` | 0 | ≥1 real-IP client config |
| Preflight protect/activate | Fail-closed | Same |
| Live post-connect verify | Reports `NOT_RUN` | Tunnel up + expected IP |
| `deploy_filled_to_vps.sh` targets | `deployable_locations: 0` | IPs in inventory, then re-materialize |

**Forbidden (will not raise count / unsupported):** scraped residential lists, Tor exits, RFC1918, TEST-NET (`203.0.113.*` etc.), placeholders.

**Not a software bug:** `configured_count = 0` with filled servers is the designed baseline until you provision VPS.

---

## 3. Exact next 5 commands (after IPs available)

Assume one geo first (`dubai`). Put the real IP in inventory (or `export PCS_VPS_DUBAI=…`), then:

```bash
# 1) Materialize clients + refresh deploy script from inventory
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py

# 2) Confirm configured_count > 0
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], d["configured_count"], d.get("next_step"))'

# 3) Deploy filled package (scp + remote install; needs SSH to that IP)
bash ~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh

# 4) Remote health (replace with your VPS IP)
ssh root@YOUR.VPS.PUBLIC.IP 'sudo systemctl is-active sing-box && sudo ss -lntp | head'

# 5) Post-connect leak verify (after local sing-box/client tunnel is up)
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --location dubai
# (run from ~/Desktop/PCS_Industrial_20260802; set PCS_VERIFY_EXPECTED_IP if needed)
```

**Pass:** readiness `partial` or `ready`, `configured_count` ≥ 1, `singbox/dubai.json` exists, `sing-box` active on VPS, verify report not `NOT_RUN` fail-closed skip.

Deep path: `CEO_VPS_RUNBOOK_v20260802.md` · tick-list: `OPERATOR_CHECKLIST_v20260802.md`.

---

## 4. Risk register

| ID | Risk | Severity | State | Mitigation |
|----|------|----------|-------|------------|
| R1 | **Time Machine includes** `~/.pcs_industrial_20260802` (secrets + filled server keys) | **High** | Live: `[Included]` | `sudo tmutil addexclusion ~/.pcs_industrial_20260802` |
| R2 | Zero inventory IPs → no product exits | High (ops) | Open by design | Provision owned VPS; run §3 |
| R3 | Secrets on local disk if machine stolen / unlocked backup | High | Modes OK (`0700`/`0600`) | Exclusion + disk encryption; never commit Desktop tree |
| R4 | iCloud Desktop may sync **code** tree | Med | Secrets not in tree | Keep secrets only under `~/.pcs…` |
| R5 | pytest 1 fail (`pending_ip_count` 9≠8) | Low | Open | Frankfurt alias double-count; fix assert or dedupe |
| R6 | HY2 self-signed → client `tls.insecure=true` | Med (threat model) | By design | Document honestly; optional public CA later |
| R7 | TUN / kill-switch need admin/root on macOS | Med | Ops | Documented in materialize caveats |
| R8 | Stripe not set → CARD offline | Low | Optional | Set `STRIPE_SECRET_KEY` when ready |
| R9 | Key age / rotation | Low now (`age_days` ~0) | Fresh | Rotate 30–90d via `--rotate-keys` + redeploy |

---

## 5. Metrics board (discoverable)

| Domain | Count / detail |
|--------|----------------|
| VPS template geos | 8 |
| Server package filled files | 8 primary JSON (+ 2 path previews → readiness **10**) |
| Secrets locations OK | 8 |
| Inventory IPs set | 0 |
| Client configured | 0 |
| Pending client sidecars | 9 (`*.pending.json`) |
| Residential countries | 36 |
| Residential catalog entries | **1,620** (45 × 36; `not_a_tunnel_endpoint: true`) |
| Deploy scripts synced | 4 under package `scripts/` |
| Industrial pytest files | 3 modules · **57** collected (43 + 8 + 6) |
| Pytest run | **56 passed, 1 failed** (0.20s) |
| Readiness embedded self-test | **20/20** |
| Verify reports on disk | Several `*_NOT_RUN.json` (expected pre-tunnel) |
| Suite verify tools discovered | 5 present / 0 missing |

---

## 6. Decision for CEO

| If you want… | Do this |
|--------------|---------|
| **Live product exit this week** | Buy/attach ≥1 Ubuntu 22/24 VPS in a listed geo → set inventory IP → §3 five commands |
| **Ship marketing / pricing / UI only** | Already unblocked (catalog, landing, command center, crypto rails) — do **not** claim live multi-geo exits |
| **Security hygiene today (no VPS)** | Exclude state dir from Time Machine; confirm no PEMs under Desktop tree |

**Honest claim boundary:** Industrial is **package-ready and gate-honest**, not **fleet-online**, until owned VPS IPs land and verify goes green.

---

*Sources: live `pcs_server_readiness`, `materialize_meta.json`, `_catalog_meta.json`, pytest, `tmutil isexcluded`, industrial docs v20260802.*
