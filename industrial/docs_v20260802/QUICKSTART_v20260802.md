# Quickstart — 5-minute orientation (v20260802)

**Audience:** CEO, new operator, agent/session bootstrap  
**Goal:** Know where you are, what is safe to edit, and the next three clicks  
**Source-of-truth map:** [`INDEX_v20260802.md`](INDEX_v20260802.md)

---

## Minute 0–1 — What this tree is

| Item | Path | Notes |
|------|------|-------|
| Industrial product tree | `~/Desktop/PCS_Industrial_20260802/` | New names; **does not overwrite** Suite / legacy |
| Docs control plane | `…/docs_v20260802/` | **Only** place for new industrial docs |
| Runtime state + secrets | `~/.pcs_industrial_20260802/` | Outside the Desktop tree; chmod-hardened |
| Suite (read-only for ops narrative) | `~/Desktop/PhantomCloak Suite/` | Import / discover only |
| **Canonical deploy/verify HOWTO (RO)** | `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` | **Do not edit** |

If you need the full purpose → path → audience table, open **INDEX** and stop guessing.

---

## Minute 1–2 — Mental model (two roots)

```text
CODE  ~/Desktop/PCS_Industrial_20260802/     # scripts, dashboards, docs (versionable)
STATE ~/.pcs_industrial_20260802/            # inventory, secrets, filled packages, clients
```

| You want… | Look in… |
|-----------|----------|
| Launch Core / Command Center | `launches_v20260802/*.command` or README after INDEX |
| Set VPS public IPs | `~/.pcs_industrial_20260802/vps_inventory.json` |
| Filled server JSON to scp | `~/.pcs_industrial_20260802/vps_server_package/` |
| Client sing-box configs | `~/.pcs_industrial_20260802/singbox/` |
| Secrets (UUID, Reality keys) | `~/.pcs_industrial_20260802/secrets/` |
| Docs map | `docs_v20260802/INDEX_v20260802.md` |

Details: [`STATE_NOTE_v20260802.md`](STATE_NOTE_v20260802.md) · [`SECURITY_SECRETS_v20260802.md`](SECURITY_SECRETS_v20260802.md)

---

## Minute 2–3 — One status check

From the industrial tree:

```bash
cd ~/Desktop/PCS_Industrial_20260802
python3 shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print("status=",d["status"]); print("configured_count=",d["configured_count"]); print("server_filled=",d["server_filled_count"]); print("pending_ip=",d["pending_ip_count"]); print("next=",d.get("next_step"))'
```

| Typical baseline (no owned VPS IPs yet) | Meaning |
|-----------------------------------------|---------|
| `server_filled` ≥ 1, `configured_count` = 0 | Package ready; **you** must set real IPs |
| Only `*.pending.json` under `singbox/` | Expected until inventory has owned IPs |

**Forbidden:** scraped residential / proxy-list IPs. See [`RESIDENTIAL_IP_VS_VPS_v20260802.md`](RESIDENTIAL_IP_VS_VPS_v20260802.md).

---

## Minute 3–4 — Next action by role

| Role | Do this next | Doc |
|------|--------------|-----|
| **CEO / owner** | Snapshot then one geo live | [`CEO_INDUSTRIAL_STATUS_BRIEF_v20260802.md`](CEO_INDUSTRIAL_STATUS_BRIEF_v20260802.md) → [`CEO_VPS_RUNBOOK_v20260802.md`](CEO_VPS_RUNBOOK_v20260802.md) |
| **Operator** | Tick provision → materialize → scp → firewall → verify → rotate | [`OPERATOR_CHECKLIST_v20260802.md`](OPERATOR_CHECKLIST_v20260802.md) |
| **Need exact industrial commands** | Materialize, deploy script, verify bridge | [`HOWTO_DEPLOY_LINK_v20260802.md`](HOWTO_DEPLOY_LINK_v20260802.md) |
| **Classic deploy/verify narrative** | Suite steps (templates, IP/DNS/WebRTC) | **RO** `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` |
| **Count stuck at 0** | Decision tree | [`INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md`](INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md) |
| **GTM / landing** | Hosting order + posts | [`HOSTING_AND_CAMPAIGN_v20260802.md`](HOSTING_AND_CAMPAIGN_v20260802.md) |
| **Claims language** | What you may / may not say | [`FTC_HONEST_CLAIMS_v20260802.md`](FTC_HONEST_CLAIMS_v20260802.md) |

---

## Minute 4–5 — Optional: local product surface

```bash
cd ~/Desktop/PCS_Industrial_20260802
chmod +x launches_v20260802/*.command
./launches_v20260802/Launch_PCS_Core_v20260802.command      # Core shell
./launches_v20260802/Open_PCS_CommandCenter_v2.command     # UX v2 (8 features)
# Landing + payments local:
# .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
```

UX map: [`UX_EIGHT_FEATURES_v20260802.md`](UX_EIGHT_FEATURES_v20260802.md)

---

## Rules worth memorizing

1. **Docs SoT** = this folder’s [`INDEX_v20260802.md`](INDEX_v20260802.md).  
2. **Suite HOWTO** = canonical **read-only** deploy/verify procedure.  
3. **Industrial HOWTO link** = industrial paths only (`HOWTO_DEPLOY_LINK_v20260802.md`).  
4. **Secrets never** in the Desktop git tree.  
5. **`configured_count`** only rises with **owned** VPS (or controlled host) IPs after materialize.

---

## After 5 minutes

→ Full map: [`INDEX_v20260802.md`](INDEX_v20260802.md)  
→ Repo launches/modules: [`../README_PCS_INDUSTRIAL.md`](../README_PCS_INDUSTRIAL.md)
