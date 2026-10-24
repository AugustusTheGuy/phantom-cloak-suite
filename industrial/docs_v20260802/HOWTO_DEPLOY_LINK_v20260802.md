# VPS deploy link — industrial (does not overwrite Suite)

**Canonical guide (read-only):** `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md`  
**This page:** exact commands for the industrial scripts and paths as of v20260802.

**Current state:** filled server package ready; set real owned VPS IPs → re-materialize → `configured_count` > 0.  
**Forbidden:** scraped residential / proxy-list IPs. See `RESIDENTIAL_IP_VS_VPS_v20260802.md`.

---

## Automated materialize + readiness

```bash
# Generate/refresh filled server configs, secrets, deploy script; write clients when IPs set
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py

# Scan templates vs real client IPs; prints JSON including configured_count
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

Pretty one-liner for status fields:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print("status=",d["status"]); print("configured_count=",d["configured_count"]); print("server_filled=",d["server_filled_count"]); print("pending_ip=",d["pending_ip_count"]); print("inventory_ips_set=",d["inventory"].get("ips_set")); print("next=",d.get("next_step"))'
```

---

## Paths

| Path | Purpose |
|------|---------|
| `shared/pcs_inventory_wizard_v20260802.py` | **Preferred** inventory set/list/clear/validate (atomic, chmod 600) |
| `~/.pcs_industrial_20260802/vps_templates_source_copy/` | Copy of Suite `server/ready-for-vps/` |
| `~/Desktop/PCS_Industrial_20260802/server_vps_package_v20260802/templates_source_copy/` | Same mirror inside industrial tree |
| `~/.pcs_industrial_20260802/vps_server_package/` | **Filled** server configs (UUID + Reality private keys) ready to scp |
| `~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh` | Generated scp + remote install (only locations with real IPs) |
| `~/.pcs_industrial_20260802/vps_server_package/hy2_certs/<loc>/` | Self-signed HY2 certs for `dubai` / `hongkong` |
| `~/.pcs_industrial_20260802/singbox/` | Client configs when inventory has real IPs; else `*.pending.json` |
| `~/.pcs_industrial_20260802/vps_inventory.json` | **You set** public VPS IPs here |
| `~/.pcs_industrial_20260802/secrets/location_keys.json` | Private keys / UUID / passwords (chmod 600) |
| `~/.pcs_industrial_20260802/materialize_meta.json` | Last materialize result |
| `~/.pcs_industrial_20260802/pf_rules/pcs_killswitch_v20260802.pf.conf` | Industrial pf rules (not `/tmp/delphi_killswitch.pf.conf`) |

---

## Raise `configured_count`

Client files under `~/.pcs_industrial_20260802/singbox/*.json` count as configured only when they embed a **real public IP or hostname you control** (not placeholders, not private/TEST-NET ranges).

### 1. Inventory wizard (preferred)

Operator CLI validates with materialize `is_real_ip` + readiness `is_real_public_ip`, writes atomically (`chmod 600`), rejects RFC1918 / TEST-NET / placeholders. Full reference: **`INVENTORY_WIZARD_v20260802.md`**.

```bash
# List current inventory + validation status
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py --list

# Non-interactive set (repeatable --set); optional --rematerialize after write
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=YOUR.REAL.VPS.IP \
  --set germany=YOUR.OTHER.VPS.IP

# Dry-run validation (must fail for private/TEST-NET — no write)
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=10.0.0.1 --validate-only

# Clear one location
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --clear-location dubai

# Interactive prompts (default with no flags)
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py
```

### 2. Edit inventory manually (still supported)

```bash
nano ~/.pcs_industrial_20260802/vps_inventory.json
```

Example (one location):

```json
{
  "version": 1,
  "ssh_user": "root",
  "locations": {
    "dubai": { "ip": "YOUR.REAL.VPS.IP", "ssh_user": "root", "enabled": true },
    "hongkong": { "ip": "", "ssh_user": "", "enabled": true },
    "vancouver": { "ip": "", "ssh_user": "", "enabled": true },
    "germany": { "ip": "", "ssh_user": "", "enabled": true },
    "bahamas": { "ip": "", "ssh_user": "", "enabled": true },
    "cayman": { "ip": "", "ssh_user": "", "enabled": true },
    "mauritius": { "ip": "", "ssh_user": "", "enabled": true },
    "seychelles": { "ip": "", "ssh_user": "", "enabled": true }
  }
}
```

### 3. Or env overrides (applied on each materialize)

```bash
export PCS_VPS_DUBAI=x.x.x.x
export PCS_VPS_HONGKONG=x.x.x.x
export PCS_VPS_VANCOUVER=x.x.x.x
export PCS_VPS_GERMANY=x.x.x.x
export PCS_VPS_BAHAMAS=x.x.x.x
export PCS_VPS_CAYMAN=x.x.x.x
export PCS_VPS_MAURITIUS=x.x.x.x
export PCS_VPS_SEYCHELLES=x.x.x.x
```

### 4. Re-run materialize + readiness

```bash
# If you did not pass --rematerialize on the wizard:
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

Pass: `configured_count` > 0 and `status` is `partial` or `ready`.

---

## Deploy filled configs to VPS

### Generated helper (after IPs are in inventory and materialize re-run)

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh
```

What it does per location with a real IP:

1. `scp` filled `sing-box-<loc>-reality.json` (or rewritten VPS path JSON for HY2)
2. For `dubai` / `hongkong`: mkdir `/etc/sing-box/hy2_certs/<loc>`, scp certs, chmod 600
3. Rewrites Mac package cert paths → `/etc/sing-box/hy2_certs/<loc>/{fullchain,privkey}.pem`
4. `sudo cp` → `/etc/sing-box/config.json`
5. `sudo sing-box check -c /etc/sing-box/config.json`
6. `systemctl enable --now sing-box` + restart
7. `ufw allow` 443/tcp, 443/udp, 8443/udp

Requires passwordless or interactive SSH as inventory `ssh_user` (default `root`).

### Manual single-VPS (matches Suite HOWTO flow; uses industrial filled package)

```bash
# On VPS — install once
ssh root@YOUR_VPS_IP 'bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh)'

# From Mac — copy filled server config (replace dubai with your loc)
scp ~/.pcs_industrial_20260802/vps_server_package/sing-box-dubai-reality.json \
  root@YOUR_VPS_IP:/tmp/sing-box-config.json

ssh root@YOUR_VPS_IP 'sudo mkdir -p /etc/sing-box && \
  sudo cp /tmp/sing-box-config.json /etc/sing-box/config.json && \
  sudo sing-box check -c /etc/sing-box/config.json && \
  sudo systemctl enable --now sing-box && \
  sudo systemctl restart sing-box && \
  sudo ufw allow 22/tcp && \
  sudo ufw allow 443/tcp && sudo ufw allow 443/udp && \
  sudo ufw allow 8443/udp && \
  sudo ufw --force enable'
```

HY2 locations also need certs under `/etc/sing-box/hy2_certs/<loc>/` — prefer `deploy_filled_to_vps.sh` for those.

### Server filenames

| Location | Server package file |
|----------|---------------------|
| dubai | `sing-box-dubai-reality.json` |
| hongkong | `sing-box-hongkong-reality.json` |
| vancouver | `sing-box-vancouver-reality.json` |
| germany | `sing-box-germany-reality.json` |
| bahamas | `sing-box-bahamas-reality.json` |
| cayman | `sing-box-cayman-reality.json` |
| mauritius | `sing-box-mauritius-reality.json` |
| seychelles | `sing-box-seychelles-reality.json` |

---

## Readiness statuses (what you will see)

| `status` | Meaning |
|----------|---------|
| `templates_only` | No filled package / no pending sidecars yet |
| `materialized_pending_ips` | Pending sidecars; no filled server scan match |
| `server_package_ready_pending_client_ips` | Filled servers ready; clients wait on inventory IPs (**current default**) |
| `partial` | Some client configs with real IPs |
| `ready` | Configured clients and no remaining missing_real placeholders in scan logic |

---

## Post-connect leak verification (industrial bridge)

**Canonical Suite HOWTO (read-only):**  
`~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` §2–3 (IP/DNS/WebRTC)

Industrial bridge discovers Suite verify tools without modifying them, preflights
client config, and writes CEO pass/fail JSON:

```bash
cd ~/Desktop/PCS_Industrial_20260802

# Discover Suite tools + env contract
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --discover-only

# Offline dry-run (auto when no sing0 / sing-box process)
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --location dubai --dry-run
```

### When VPS + tunnel are ready

1. Inventory IPs set → materialize → `configured_count` > 0  
2. Deploy filled package to VPS  
3. Connect: `sing-box run -c ~/.pcs_industrial_20260802/singbox/<loc>.json`  
4. Verify:

```bash
export PCS_VERIFY_LOCATION=dubai
# expected IP from inventory, or:
export PCS_VERIFY_EXPECTED_IP=x.x.x.x
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --location dubai
```

| Path | Purpose |
|------|---------|
| `shared/pcs_verify_bridge_v20260802.py` | Bridge (ipify / DNS / WebRTC guidance + Suite suite) |
| `~/.pcs_industrial_20260802/verify_reports/` | CEO pass/fail JSON reports |
| `…/verify_reports/latest.json` | Most recent report |

Without a PCS tunnel the bridge **skips** live ipify/DNS/suite probes and records
clear skip reasons (`no_tunnel`, `client_pending_ip`, `expected_ip_unset`, …).
Overall is **`NOT_RUN`** (exit 0). Dry-run never sets killswitch flags.

### Killswitch recommendation (live IP mismatch only)

| Condition | `overall` | `trip_killswitch_recommended` |
|-----------|-----------|-------------------------------|
| Dry-run / no tunnel / offline preflight | `NOT_RUN` | `false` |
| Live checks: observed IP matches exit | `PASS` | `false` |
| Live checks: expected exit ≠ observed IP(s) | `FAIL` | **`true`** |
| Live checks: no expected IP / inconclusive | `WARN` | `false` |

- Report fields: top-level `trip_killswitch_recommended` and `ceo.trip_killswitch_recommended`
  (same boolean). Reason for the live fail is `ip_mismatch_possible_leak`.
- **Default is recommend-only.** The bridge does **not** arm industrial pf by itself.
- Optional hook for orchestrators / Command Center:

```python
from shared.pcs_verify_bridge_v20260802 import run_verification

def on_trip(report):
    # Wire to industrial killswitch / UI fail-closed — never auto-called unless provided
    return {"status": "queued", "reason": "ip_mismatch_possible_leak"}

report = run_verification(
    location="dubai",
    killswitch_trip_fn=on_trip,  # optional; dry-run never invokes
)
assert report["trip_killswitch_recommended"] in (True, False)
# hook metadata: report["killswitch_trip_hook"] → invoked / result / note
```

Manual WebRTC: open https://browserleaks.com/webrtc **inside** the protected browser profile.

---

## Industrial pf rules

```bash
ls ~/.pcs_industrial_20260802/pf_rules/
# pcs_killswitch_v20260802.pf.conf
```

**Not** `/tmp/delphi_killswitch.pf.conf` (legacy Suite path unchanged).

---

## Related ops docs

| Doc | Purpose |
|-----|---------|
| `INVENTORY_WIZARD_v20260802.md` | Inventory wizard CLI (set / list / clear / validate-only) |
| `CEO_VPS_RUNBOOK_v20260802.md` | 15-minute path to `configured_count` > 0 |
| `OPERATOR_CHECKLIST_v20260802.md` | Provision → deploy → verify → rotate |
| `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md` | Troubleshooting stuck at 0 |
| `VPS_MATERIALIZE_STATUS_v20260802.md` | Last materialize snapshot |
| `RESIDENTIAL_IP_VS_VPS_v20260802.md` | Owned VPS vs residential policy |
