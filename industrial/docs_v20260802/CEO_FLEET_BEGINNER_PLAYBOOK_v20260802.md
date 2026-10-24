# CEO Fleet Beginner Playbook — Multi-IP Residential-class Exits

**Audience:** You (non-expert operator)  
**Goal:** Own real VPS/ISP IPs so PhantomCloak industrial protect can turn on.  
**Rule:** Only machines **you pay for and control**. Never paste scraped residential lists.

---

## What you are building

| Piece | Meaning |
|-------|---------|
| **Country pool** | 5–7 public IPs in the **same country** (backups + rotation) |
| **Use-case** | Streaming / Crypto / Browsing / Digital Nomad / Other |
| **MVP** | **5 countries × 5 IPs = 25 servers** (enough to prove the product) |

Software on your Mac is already prepared to accept pools. **You** create the servers and send the IPs.

---

## Part A — Do this first hour (prove the path with 1 server)

### A1. Mac prep

Open **Terminal**:

```bash
sing-box version || brew install sing-box
ssh -V

# SSH key (one time)
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "pcs-ceo" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

Copy the long line starting with `ssh-ed25519` — you will paste it into the VPS provider.

Optional (keeps secrets out of Time Machine):

```bash
sudo tmutil addexclusion ~/.pcs_industrial_20260802
```

### A2. Create ONE Ubuntu VPS

1. Sign up at **Vultr**, **Hetzner**, **DigitalOcean**, or similar.  
2. Create server:
   - **Ubuntu 22.04 or 24.04**
   - Smallest plan (1 vCPU / 1 GB)
   - Region: e.g. **Frankfurt** → product key `germany`
3. Add your **SSH public key**.  
4. Copy the **Public IPv4**.

### A3. Test login

```bash
ssh root@PASTE_YOUR_IP_HERE
# type yes if asked; then: exit
```

### A4. Register IP + materialize (Mac)

```bash
cd ~/Desktop/PCS_Industrial_20260802

python3 shared/pcs_inventory_wizard_v20260802.py \
  --set germany=PASTE_YOUR_IP_HERE \
  --rematerialize
```

Check:

```bash
python3 shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["status"], "configured=", d["configured_count"])'
```

You want **`configured_count` ≥ 1**.

### A5. Deploy sing-box to that VPS

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_one_v20260802.sh \
  root@PASTE_YOUR_IP_HERE germany
```

```bash
ssh root@PASTE_YOUR_IP_HERE 'sudo systemctl is-active sing-box'
# expect: active
```

**When this works, scale to fleets below.**

---

## Part B — MVP fleet (5 countries × 5 IPs)

### B1. Countries to buy first

| Country | Product key | Good for |
|---------|-------------|----------|
| United States | `us` (or `vancouver` until US slot exists) | Streaming |
| United Kingdom | `gb` | Streaming |
| Canada | `vancouver` | Streaming / browsing |
| Germany | `germany` | Streaming / EU / browsing |
| UAE (Dubai) | `dubai` | Crypto / other |

### B2. Per country: create 5 servers

Same OS/size. Same region. Name them `pcs-de-01` … `pcs-de-05`.

Keep a spreadsheet:

```text
country,slot,ip,ssh_user,product_key
DE,1,x.x.x.x,root,germany
DE,2,y.y.y.y,root,germany
...
```

### B3. Paste pools to Grok or use multi-set

When inventory v2 is active (agents ship this session):

```bash
# Example multi-IP (comma-separated)
python3 shared/pcs_inventory_wizard_v20260802.py \
  --set-pool germany=1.1.1.1,2.2.2.2,3.3.3.3,4.4.4.4,5.5.5.5 \
  --rematerialize
```

Until then, paste in chat:

```text
germany=a.b.c.d,e.f.g.h,...
dubai=...
```

### B4. Batch deploy

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_pool_v20260802.sh germany
```

---

## Part C — Use-case → top 5 countries (expand when budget allows)

| Use-case | Top 5 countries | 5–7 IPs each |
|----------|-----------------|--------------|
| **Streaming** | US, GB, CA, AU, DE | yes |
| **Crypto** | AE, SG, CH, HK, KY | yes |
| **Browsing** | IS, CH, NL, CA, DE | yes |
| **Digital Nomad** | PT, ES, TH, MX, CO | yes |
| **Other** | CA, CH, SG, DE, AE | yes |

**Plus 8–10 essentials (5–8 IPs each):** JP, FR, BR, IN, EE, BS, MU, SC, VN, MY/ID.

**Do not buy duplicates:** CA/DE/CH appear in many use-cases — **one pool per country**, shared across purposes.

### C1. Purpose routing ↔ MVP countries (Priority A)

Software maps each **purpose** (use-case) to preferred **location keys**. On inventory load, that map is written into `~/.pcs_industrial_20260802/vps_inventory.json` as `purpose_routing`.

**MVP Priority A (buy first):** US · GB · CA · DE · AE  
**Product keys:** `us` · `gb` · `vancouver` · `germany` · `dubai`

| Purpose | Covered by MVP already | Still need later (top-5 gap) | Why MVP is enough to start |
|---------|------------------------|-----------------------------|----------------------------|
| **Streaming** | US, GB, CA, DE (4/5) | AU | Most catalogs + EU already |
| **Crypto** | AE (1/5) | SG, CH, HK, KY | Dubai proves crypto path; expand Asia/finance next |
| **Browsing** | CA, DE (2/5) | IS, CH, NL | Privacy-leaning EU/CA exits exist |
| **Digital Nomad** | — (0/5) | PT, ES, TH, MX, CO | After MVP; Germany/Vancouver can proxy early tests |
| **Other** | CA, DE, AE (3/5) | CH, SG | General-purpose exits covered |

**CLI (industrial tree):**

```bash
cd ~/Desktop/PCS_Industrial_20260802

# List purposes
python3 shared/pcs_purpose_routing_v20260802.py --list-purposes

# Top 5 for streaming (codes + product location keys)
python3 shared/pcs_purpose_routing_v20260802.py --top5 streaming

# MVP coverage matrix + fleet math
python3 shared/pcs_purpose_routing_v20260802.py --mvp-coverage --fleet-estimate

# JSON for scripts / Grok
python3 shared/pcs_purpose_routing_v20260802.py --list-purposes --top5 streaming --json
```

After any inventory load/set, confirm routing is on disk:

```bash
python3 -c 'import json,pathlib; p=pathlib.Path.home()/".pcs_industrial_20260802"/"vps_inventory.json"; d=json.loads(p.read_text()); print("purpose_routing keys:", sorted((d.get("purpose_routing") or {}).keys()))'
```

---

## Part D — “Residential-class” vs cheap VPS

| Type | Pros | Cons |
|------|------|------|
| Cloud VPS ($3–8/mo) | Easy, cheap | Datacenter ASN — some sites detect VPN |
| Static ISP / residential product | Better “home” reputation | Costlier; still must be **your** circuit |

Hybrid: **1–2 sticky ISP** + **3–5 VPS** backups per streaming country.

---

## Part E — What success looks like

| Check | Good value |
|-------|------------|
| `configured_count` | ≥ number of real pool IPs registered |
| `sing-box` on each VPS | `active` |
| Protect activate | Not blocked by `servers_not_configured` |
| Verify bridge | Public IP matches chosen exit |

---

## Part F — Paste this to Grok when stuck

```text
STATUS: stuck | inventory_set | deploy_done
COUNTRY: germany
IPS: x.x.x.x, y.y.y.y
SSH_USER: root
ERROR:
(paste last lines)
```

---

## Related docs

- Detection surfaces: `DETECTION_SURFACE_CATALOG_v20260802.md`  
- Pre-marketing gate: `PRE_MARKETING_READINESS_REPORT_v20260802.md`  
- Swarm status: `SWARM_STATUS_BOARD_v20260802.md`  
- Suite HOWTO (read-only): `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md`  

---

## Start here for all 25 VPS

See **[CEO_GATHER_25_VPS_BEGINNER_GUIDE_v20260804.md](./CEO_GATHER_25_VPS_BEGINNER_GUIDE_v20260804.md)** for free vs paid paths, shopping list, and Core/Pro coverage.
