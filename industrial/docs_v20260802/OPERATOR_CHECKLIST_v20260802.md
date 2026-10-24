# Operator checklist — provision → materialize → scp → firewall → verify → rotate

**Version:** v20260802  
**Scope:** Industrial package only (`PCS_Industrial_20260802`). Suite HOWTO is canonical and read-only.  
**IP rule:** Owned VPS / controlled hostnames only. No scraped residential lists.

Tick each box in order. One location at a time is fine.

---

## Path table

| Item | Path |
|------|------|
| Repo | `~/Desktop/PCS_Industrial_20260802/` |
| Materialize | `shared/pcs_materialize_singbox_v20260802.py` |
| Readiness | `shared/pcs_server_readiness_v20260802.py` |
| Inventory | `~/.pcs_industrial_20260802/vps_inventory.json` |
| Server package | `~/.pcs_industrial_20260802/vps_server_package/` |
| Deploy script | `~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh` |
| Clients | `~/.pcs_industrial_20260802/singbox/` |
| Secrets | `~/.pcs_industrial_20260802/secrets/location_keys.json` |
| HY2 certs (local) | `~/.pcs_industrial_20260802/vps_server_package/hy2_certs/<loc>/` |
| Suite HOWTO (read-only) | `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` |

---

## 1. Provision

- [ ] Choose provider and region matching product geo
- [ ] Create Ubuntu 22.04/24.04 VPS you own
- [ ] Attach **your** SSH key; confirm login:

```bash
ssh root@VPS_IP 'whoami && cat /etc/os-release | head -3'
```

- [ ] Record public IPv4 (or controlled hostname)
- [ ] Confirm outbound HTTPS works on VPS (for sing-box install)

```bash
ssh root@VPS_IP 'curl -fsSL -o /dev/null -w "%{http_code}\n" https://sing-box.sagernet.org/ || true'
```

---

## 2. Materialize

- [ ] Mac has `sing-box` on PATH (`sing-box version`)
- [ ] Edit inventory IP for location(s):

```bash
nano ~/.pcs_industrial_20260802/vps_inventory.json
# "dubai": { "ip": "VPS_IP", "ssh_user": "root", "enabled": true }
```

Or:

```bash
export PCS_VPS_DUBAI=VPS_IP   # etc. PCS_VPS_<LOC>
```

- [ ] Run materialize:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
```

- [ ] Expect filled servers under `vps_server_package/sing-box-*-reality.json`
- [ ] Expect client `~/.pcs_industrial_20260802/singbox/<loc>.json` (not only `*.pending.json`)
- [ ] Confirm secrets file mode 600:

```bash
ls -la ~/.pcs_industrial_20260802/secrets/location_keys.json
# should show -rw------- 
```

---

## 3. SCP / install sing-box

### 3a Automated

- [ ] Re-materialize after IPs set (regenerates deploy script with scp targets)
- [ ] Run:

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh
```

### 3b Manual (single VPS)

- [ ] Install sing-box once:

```bash
ssh root@VPS_IP 'bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh)'
```

- [ ] SCP filled config:

```bash
scp ~/.pcs_industrial_20260802/vps_server_package/sing-box-LOC-reality.json \
  root@VPS_IP:/tmp/sing-box-config.json
```

- [ ] Place + validate + start:

```bash
ssh root@VPS_IP 'sudo mkdir -p /etc/sing-box && \
  sudo cp /tmp/sing-box-config.json /etc/sing-box/config.json && \
  sudo sing-box check -c /etc/sing-box/config.json && \
  sudo systemctl enable --now sing-box && \
  sudo systemctl restart sing-box'
```

### 3c HY2 locations only (`dubai`, `hongkong`)

- [ ] Copy certs:

```bash
ssh root@VPS_IP 'sudo mkdir -p /etc/sing-box/hy2_certs/LOC'
scp ~/.pcs_industrial_20260802/vps_server_package/hy2_certs/LOC/fullchain.pem \
    ~/.pcs_industrial_20260802/vps_server_package/hy2_certs/LOC/privkey.pem \
    root@VPS_IP:/tmp/
ssh root@VPS_IP 'sudo mv /tmp/fullchain.pem /tmp/privkey.pem /etc/sing-box/hy2_certs/LOC/ && \
  sudo chmod 600 /etc/sing-box/hy2_certs/LOC/*'
```

- [ ] Ensure server JSON on VPS uses:

| Key | Path |
|-----|------|
| `certificate_path` | `/etc/sing-box/hy2_certs/LOC/fullchain.pem` |
| `key_path` | `/etc/sing-box/hy2_certs/LOC/privkey.pem` |

(`deploy_filled_to_vps.sh` rewrites these from Mac package paths automatically.)

---

## 4. Firewall

- [ ] Allow SSH first (avoid lockout)
- [ ] Allow Reality + optional HY2:

```bash
ssh root@VPS_IP 'sudo ufw allow 22/tcp && \
  sudo ufw allow 443/tcp && sudo ufw allow 443/udp && \
  sudo ufw allow 8443/udp && \
  sudo ufw --force enable && sudo ufw status verbose'
```

| Port | Protocol | Purpose |
|------|----------|---------|
| 22 | TCP | SSH |
| 443 | TCP (+ UDP if used) | VLESS Reality |
| 8443 | UDP | Hysteria2 (`dubai`, `hongkong`) |

- [ ] Provider cloud firewall / security group matches ufw (if any)

---

## 5. Verify

- [ ] Service healthy:

```bash
ssh root@VPS_IP 'sudo systemctl is-active sing-box && \
  sudo journalctl -u sing-box -n 30 --no-pager'
```

- [ ] Listening:

```bash
ssh root@VPS_IP 'sudo ss -ulnp | grep -E ":443|:8443"; sudo ss -tlnp | grep 443'
```

- [ ] Readiness count:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

- [ ] Pass: `"configured_count":` **> 0**, status `partial` or `ready`
- [ ] Client file contains server public IP (not placeholder):

```bash
grep -E '"server"|pending|YOUR_VPS' ~/.pcs_industrial_20260802/singbox/LOC.json
```

- [ ] Optional: Suite verification suite per `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` after client connect
- [ ] Optional: industrial app shell status:

```bash
cd ~/Desktop/PCS_Industrial_20260802
.venv/bin/python core_product/pcs_app_shell_v20260802.py --status
```

---

## 6. Rotate keys

Do every **30–90 days**, or immediately after key leak / staff offboarding.

- [ ] Backup current secrets + package:

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p ~/.pcs_industrial_20260802/backups/$TS
cp -a ~/.pcs_industrial_20260802/secrets \
      ~/.pcs_industrial_20260802/vps_server_package \
      ~/.pcs_industrial_20260802/singbox \
      ~/.pcs_industrial_20260802/backups/$TS/
chmod -R go-rwx ~/.pcs_industrial_20260802/backups/$TS
```

- [ ] Remove location secrets so materialize regenerates UUID + Reality keypair + hy2 password:

```bash
# Edit secrets JSON: delete the locations.<loc> object for each geo to rotate
nano ~/.pcs_industrial_20260802/secrets/location_keys.json
```

Or move entire secrets file aside for full re-key:

```bash
mv ~/.pcs_industrial_20260802/secrets/location_keys.json \
   ~/.pcs_industrial_20260802/secrets/location_keys.json.bak-$TS
```

- [ ] Re-materialize (regenerates keys for missing locations):

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
```

- [ ] Re-deploy **all** affected VPS (old private keys stop working):

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/deploy_filled_to_vps.sh
# or manual scp path in §3b
```

- [ ] Re-verify readiness + client connect
- [ ] Destroy backup copies that leave the machine; shred offline export if any

**HY2 certs:** self-signed ~825 days under `secrets/hy2_certs/<loc>/`. To force reissue, delete that loc dir and re-materialize, then re-scp certs.

---

## Location ports / features

| LOC | Reality 443 | HY2 8443 | Client alias |
|-----|-------------|----------|--------------|
| dubai | yes | yes | — |
| hongkong | yes | yes | — |
| vancouver | yes | no | — |
| germany | yes | no | `frankfurt` |
| bahamas | yes | no | — |
| cayman | yes | no | — |
| mauritius | yes | no | — |
| seychelles | yes | no | — |

---

## Do not

| Don't | Why |
|-------|-----|
| Scrape residential IPs into inventory | Not your Reality servers; unsupported |
| Commit `secrets/` or filled configs | Credential leak |
| Edit Suite tree in place | Industrial is isolated; Suite is read-only |
| Use TEST-NET / private IPs in inventory | Materialize treats them as non-production |
| Skip `sing-box check` | Broken config → silent down |

---

## Related docs

| Doc | Use |
|-----|-----|
| `CEO_VPS_RUNBOOK_v20260802.md` | 15-minute CEO path |
| `HOWTO_DEPLOY_LINK_v20260802.md` | Exact industrial commands |
| `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md` | Count stuck at 0 |
| `RESIDENTIAL_IP_VS_VPS_v20260802.md` | IP policy |
| `VPS_MATERIALIZE_STATUS_v20260802.md` | Last materialize snapshot |
