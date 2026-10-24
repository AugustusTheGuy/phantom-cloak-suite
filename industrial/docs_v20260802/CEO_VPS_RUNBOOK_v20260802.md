# CEO VPS runbook — zero → `configured_count` > 0

**Audience:** CEO / owner operator  
**Time:** ~15 minutes after one Ubuntu VPS is provisioned  
**Rule:** Only **owned** VPS public IPs (or hostnames you control). Do not use scraped residential lists, Tor exits, or demo pool rows.

**Canonical deep guide (read-only):** `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md`  
**Current industrial state:** server package filled (8 locations); inventory IPs empty → `configured_count` = 0.

---

## Goal

| Metric | Before | After success |
|--------|--------|----------------|
| Inventory IPs set | 0 | ≥ 1 |
| Client configs with real IP | 0 (`*.pending.json` only) | ≥ 1 (`~.pcs…/singbox/<loc>.json`) |
| `configured_count` | 0 | **> 0** |
| Readiness `status` | `server_package_ready_pending_client_ips` | `partial` or `ready` |

---

## Path map (memorize these)

| Role | Path |
|------|------|
| Industrial tree | `~/Desktop/PCS_Industrial_20260802/` |
| Materialize script | `…/shared/pcs_materialize_singbox_v20260802.py` |
| Readiness script | `…/shared/pcs_server_readiness_v20260802.py` |
| Inventory (you edit) | `~/.pcs_industrial_20260802/vps_inventory.json` |
| Filled server package | `~/.pcs_industrial_20260802/vps_server_package/` |
| Deploy helper | `~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh` |
| Client configs | `~/.pcs_industrial_20260802/singbox/` |
| Secrets (chmod 600) | `~/.pcs_industrial_20260802/secrets/location_keys.json` |
| Meta / status | `~/.pcs_industrial_20260802/materialize_meta.json` |

---

## 15-minute path (one geo first)

Use **one** location (example: `dubai`). Repeat for more geos later.

### Minute 0–3 — Prerequisites on Mac

```bash
# sing-box required for key/UUID generation
sing-box version

# SSH key that can reach the VPS as root (or your ssh_user)
ssh -o BatchMode=yes -o ConnectTimeout=10 root@YOUR.VPS.PUBLIC.IP 'uname -a'
```

If `sing-box` missing: install via Homebrew (`brew install sing-box`) or Suite/local binary on `PATH`.

### Minute 3–6 — Provision VPS (provider console)

| Setting | Value |
|---------|--------|
| Provider | Any you own (Hetzner, Vultr, Linode, DO, Oracle, etc.) |
| OS | Ubuntu 22.04 or 24.04 |
| Spec | 1 vCPU / 1 GB RAM is enough for sing-box |
| Geo | Match product location (e.g. Dubai, HK, Frankfurt, Vancouver) |
| Access | Root or sudo user + **your** SSH key |
| Record | Public **IPv4** (or stable hostname you control) |

You must control this host. Third-party proxy lists do not work with Reality private keys.

### Minute 6–8 — Put IP in inventory (or env)

**Option A — inventory file (recommended):**

```bash
nano ~/.pcs_industrial_20260802/vps_inventory.json
```

Set one location (example):

```json
{
  "version": 1,
  "ssh_user": "root",
  "locations": {
    "dubai": { "ip": "YOUR.REAL.PUBLIC.IP", "ssh_user": "root", "enabled": true }
  }
}
```

**Option B — env override (session only):**

```bash
export PCS_VPS_DUBAI=YOUR.REAL.PUBLIC.IP
```

Env keys: `PCS_VPS_DUBAI`, `PCS_VPS_HONGKONG`, `PCS_VPS_VANCOUVER`, `PCS_VPS_GERMANY`, `PCS_VPS_BAHAMAS`, `PCS_VPS_CAYMAN`, `PCS_VPS_MAURITIUS`, `PCS_VPS_SEYCHELLES`.

**Rejected as “real IP” by materialize:** `127.*`, `10.*`, `192.168.*`, `172.16–31.*`, `0.*`, `169.254.*`, TEST-NET docs ranges (`192.0.2.*`, `198.51.100.*`, `203.0.113.*`), placeholders (`YOUR_VPS`, `example.com`, `pending`).

### Minute 8–10 — Materialize (writes client config when IP is real)

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

**Pass criteria:**

```text
"configured_count": 1   # or more
"status": "partial"     # or "ready"
```

Also expect: `~/.pcs_industrial_20260802/singbox/dubai.json` (not only `dubai.pending.json`).

`germany` also writes alias `frankfurt.json` when IP is set.

### Minute 10–14 — Deploy filled server config to VPS

**Automated (after IPs set + re-materialize):**

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh
```

**Manual single host (always valid):**

```bash
# 1) Install sing-box on VPS (once)
ssh root@YOUR.VPS.PUBLIC.IP 'bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh)'

# 2) Copy filled server config (not Suite template placeholders)
scp ~/.pcs_industrial_20260802/vps_server_package/sing-box-dubai-reality.json \
  root@YOUR.VPS.PUBLIC.IP:/tmp/sing-box-config.json

# 3) Install + check + start
ssh root@YOUR.VPS.PUBLIC.IP 'sudo mkdir -p /etc/sing-box && \
  sudo cp /tmp/sing-box-config.json /etc/sing-box/config.json && \
  sudo sing-box check -c /etc/sing-box/config.json && \
  sudo systemctl enable --now sing-box && \
  sudo systemctl restart sing-box && \
  sudo systemctl --no-pager status sing-box'

# 4) Firewall (keep SSH)
ssh root@YOUR.VPS.PUBLIC.IP 'sudo ufw allow 22/tcp && \
  sudo ufw allow 443/tcp && sudo ufw allow 443/udp && \
  sudo ufw allow 8443/udp && \
  sudo ufw --force enable && sudo ufw status'
```

| Location | Ports | Extra |
|----------|-------|--------|
| All | TCP/UDP **443** (VLESS Reality) | — |
| `dubai`, `hongkong` | UDP **8443** (Hysteria2) | Deploy also copies `hy2_certs/<loc>/` → `/etc/sing-box/hy2_certs/<loc>/` |

If you use the generated `deploy_filled_to_vps.sh` for hy2 locations, it rewrites Mac cert paths to `/etc/sing-box/hy2_certs/<loc>/` before install. For pure manual hy2 deploy, copy certs and set those paths in server JSON.

### Minute 14–15 — Verify count + service

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['configured_count'], d.get('next_step'))"

ls -la ~/.pcs_industrial_20260802/singbox/*.json | grep -v pending
ssh root@YOUR.VPS.PUBLIC.IP 'sudo systemctl is-active sing-box && sudo ss -lntp | head'
```

Optional Suite verification (read-only Suite tree): follow `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` §2 after client tunnel is up.

---

## Location cheat sheet

| Inventory key | Server file | Client file | HY2 |
|---------------|-------------|-------------|-----|
| `dubai` | `sing-box-dubai-reality.json` | `dubai.json` | yes |
| `hongkong` | `sing-box-hongkong-reality.json` | `hongkong.json` | yes |
| `vancouver` | `sing-box-vancouver-reality.json` | `vancouver.json` | no |
| `germany` | `sing-box-germany-reality.json` | `germany.json` + `frankfurt.json` | no |
| `bahamas` | `sing-box-bahamas-reality.json` | `bahamas.json` | no |
| `cayman` | `sing-box-cayman-reality.json` | `cayman.json` | no |
| `mauritius` | `sing-box-mauritius-reality.json` | `mauritius.json` | no |
| `seychelles` | `sing-box-seychelles-reality.json` | `seychelles.json` | no |

---

## What raises `configured_count` (and what does not)

| Action | Raises count? |
|--------|----------------|
| Own VPS IP in inventory + re-run materialize | **Yes** |
| `export PCS_VPS_<LOC>=public-ip` + materialize | **Yes** |
| Fill server package only (already done) | No (server ready, clients still pending) |
| Scraped residential / proxy-list IPs | **No / forbidden** — you do not run Reality there |
| UI residential catalog metadata | No |
| Placeholder or private/TEST-NET IP | No |

Details: `RESIDENTIAL_IP_VS_VPS_v20260802.md`.

---

## If stuck at 0

Open one-pager: **`INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md`**.

Operator tick-list: **`OPERATOR_CHECKLIST_v20260802.md`**.

Commands reference: **`HOWTO_DEPLOY_LINK_v20260802.md`**.

---

## Security notes (non-negotiable)

1. Secrets live only under `~/.pcs_industrial_20260802/secrets/` (mode 600). Do not commit.
2. Industrial tree never overwrites Suite or `~/.phantomcloak` / `~/.delphi` originals.
3. Rotate Reality keys every 30–90 days (see operator checklist § rotate).
4. Never publish filled server configs or `location_keys.json`.
