# Incident: `configured_count` stuck at 0

**Symptom:** `pcs_server_readiness` reports `"configured_count": 0`.  
**Normal baseline (v20260802):** server package filled; inventory IPs empty → count stays 0 until real owned VPS IPs are set and materialize is re-run.  
**Not an incident if:** you have not provisioned any VPS yet — follow `CEO_VPS_RUNBOOK_v20260802.md`.

---

## 60-second check

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], "configured=",d["configured_count"], "server_filled=",d["server_filled_count"], "pending=",d["pending_ip_count"], "inv_ips=",d["inventory"].get("ips_set")); print(d.get("next_step"))'

cat ~/.pcs_industrial_20260802/vps_inventory.json
ls ~/.pcs_industrial_20260802/singbox/
```

| Observation | Meaning |
|-------------|---------|
| `server_filled` ≥ 1, `inv_ips` = 0, only `*.pending.json` | Expected — set owned VPS IPs |
| `inv_ips` ≥ 1 but still `configured` = 0 | IP rejected or materialize not re-run |
| `server_filled` = 0 | Materialize never succeeded / package missing |
| Clients exist but count 0 | Placeholders inside JSON or wrong directory |

---

## Decision tree

### A. Inventory empty or all `ip: ""`

**Fix:** Put a real public IP of a VPS **you own** into inventory (or env), then materialize.

```bash
nano ~/.pcs_industrial_20260802/vps_inventory.json
# e.g. "dubai": { "ip": "A.B.C.D", "enabled": true }

# or: export PCS_VPS_DUBAI=A.B.C.D

python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

**Pass:** `configured_count` > 0 and `singbox/dubai.json` (not only `dubai.pending.json`).

Do **not** paste scraped residential/proxy-list addresses. They will not run your Reality keys and are unsupported.

### B. Inventory has IP but materialize still writes `*.pending.json`

Materialize `is_real_ip()` rejects:

| Rejected | Why |
|----------|-----|
| Empty / whitespace | No address |
| `YOUR_VPS`, `pending`, `changeme`, `example.com`, `0.0.0.0` | Placeholders |
| `127.*`, `10.*`, `192.168.*`, `172.16–31.*` | Private / local |
| `169.254.*` | Link-local |
| `192.0.2.*`, `198.51.100.*`, `203.0.113.*` | Documentation TEST-NET |
| Invalid IPv4 octets | Parse fail |

**Fix:** Use the provider’s public IPv4 or a hostname you control (not `*.local`). Re-run materialize.

```bash
# Confirm env override is visible in the same shell
echo "$PCS_VPS_DUBAI"
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
ls -la ~/.pcs_industrial_20260802/singbox/
```

### C. Materialize fails (`sing-box generate` / missing binary)

```bash
which sing-box && sing-box version
sing-box generate uuid
sing-box generate reality-keypair
```

**Fix:** Install sing-box on Mac (`brew install sing-box` or put binary on `PATH`). Re-run materialize. UUID can fall back without sing-box; Reality keypair generation requires it.

### D. Client JSON exists but readiness still counts 0

Readiness counts a file as configured only if:

- under a scanned dir (includes `~/.pcs_industrial_20260802/singbox/`)
- not `*.pending.json`, not secrets/meta/inventory names
- text has no placeholder regex match
- looks like a real dotted IP (and not only `127.0.0.1` in early text)

**Fix:**

```bash
# Show why a client may be treated as placeholder
grep -nE 'YOUR_VPS|pending|127\.0\.0\.1|0\.0\.0\.0|example\.com|changeme' \
  ~/.pcs_industrial_20260802/singbox/*.json 2>/dev/null

# Must show public server field
python3 -c 'import json,pathlib; p=pathlib.Path.home()/".pcs_industrial_20260802/singbox";
[print(f.name, [(o.get("tag"), o.get("server")) for o in json.loads(f.read_text()).get("outbounds",[]) if o.get("server")]) for f in p.glob("*.json") if not f.name.endswith(".pending.json")]'
```

If server field wrong: fix inventory IP → re-materialize (overwrites client).

### E. Looking at wrong machine / wrong state dir

Industrial state is always:

| Dir | Path |
|-----|------|
| State root | `~/.pcs_industrial_20260802/` |
| Clients | `~/.pcs_industrial_20260802/singbox/` |
| Inventory | `~/.pcs_industrial_20260802/vps_inventory.json` |

Legacy `~/.phantomcloak/singbox` or Suite templates do **not** raise industrial `configured_count` when they still contain placeholders.

### F. `enabled: false` for the only location with an IP

**Fix:** set `"enabled": true` for that location, re-materialize.

---

## Restore known-good package (server side)

If `server_filled_count` dropped to 0:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
ls ~/.pcs_industrial_20260802/vps_server_package/sing-box-*-reality.json
```

Expect 8 files. Secrets persist in `secrets/location_keys.json` unless deleted.

---

## After count > 0 — still cannot connect?

That is a **deploy/runtime** issue, not readiness counting:

1. `ssh root@IP 'systemctl is-active sing-box && journalctl -u sing-box -n 50 --no-pager'`
2. `sing-box check -c /etc/sing-box/config.json` on VPS
3. Firewall / cloud SG: 443 (+ 8443/udp for dubai/hongkong)
4. Client UUID/public_key must match server private_key from same materialize generation
5. Re-deploy filled package after any key rotation

See `OPERATOR_CHECKLIST_v20260802.md` §§ 3–5.

---

## Escalate / handoff data

Collect and attach:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py > /tmp/pcs_readiness.json
python3 -c 'import json; from pathlib import Path; p=Path.home()/".pcs_industrial_20260802/vps_inventory.json"; d=json.loads(p.read_text()); print({k:{"ip_set":bool((v or {}).get("ip")),"enabled":(v or {}).get("enabled",True)} for k,v in (d.get("locations") or {}).items()})'
ls -la ~/.pcs_industrial_20260802/singbox/ ~/.pcs_industrial_20260802/vps_server_package/ | head -40
```

Redact public IPs if ticket is external. **Never** attach `secrets/location_keys.json` or filled server JSON with private keys.

---

## Related

| Doc | Role |
|-----|------|
| `CEO_VPS_RUNBOOK_v20260802.md` | Happy path 15 min |
| `HOWTO_DEPLOY_LINK_v20260802.md` | Exact commands |
| `OPERATOR_CHECKLIST_v20260802.md` | Full ops sequence |
| `RESIDENTIAL_IP_VS_VPS_v20260802.md` | Why residential scrapes do not count |
