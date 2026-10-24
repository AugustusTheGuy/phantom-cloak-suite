# Gather Your First 25 VPS — Complete Beginner Guide (PhantomCloak)

**Who this is for:** You, setting up PhantomCloak / PCS Industrial for the first time.  
**What you will finish with:** **25 public IPv4 addresses you own**, in **5 countries**, ready to paste into this session and into industrial inventory.  
**Software on your Mac:** already prepared. **You** create the servers (providers will not do that for you).

**Related:**  
- Short deploy path after you have IPs: `CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md`  
- Spreadsheet: `CEO_FLEET_IP_SPREADSHEET_TEMPLATE.csv`  
- Do **not** use scraped “residential IP lists” or Tor exits — they will not run your Reality keys.

---

# Chapter 0 — Read this once (honest expectations)

## What “good enough” means for PhantomCloak

| Term | Simple meaning |
|------|----------------|
| **VPS** | A small rented Linux computer on the internet with a public IP |
| **Industrial quality** (for this stack) | You can log in with SSH as `root` (or sudo), OS is **Ubuntu 22.04 or 24.04**, IP is stable |
| **Residential-class** | IP looks like home ISP (cable/fiber) — **costs more**; not free |
| **Datacenter VPS** | Normal cloud IP — **cheapest professional option**; some streaming sites may flag it |

PhantomCloak **Core** and **Pro** both need at least one working exit.  
**25 servers** = **5 countries × 5 IPs** so **Pro** features (rotation, sticky primary, pool health) have real infrastructure—not a second product you must buy later.

## Can the first 25 be free?

| Path | Approx. monthly cost | Full 25? | Notes |
|------|----------------------|----------|--------|
| **A. Pure free forever** | $0 | **No (not reliably)** | Free tiers are limited and flaky |
| **B. Free-max hybrid** | $0–$30 | Partial | Oracle Always Free + trials; finish with paid |
| **C. Low-cost professional (recommended)** | **~$60–$130** | **Yes** | Best balance for industrial quality |
| **D. Static ISP / residential add-on** | **+$5–$50 per IP** | Only for a few | Use only if streaming/banks block Path C |

**Bottom line:** There is **no honest free path** to 25 professional residential IPs in five countries.  
**Recommended:** Path **C** for all 25. Optionally Path **D** later for 1 sticky IP in US/GB/DE if needed.

---

# Chapter 1 — Mac prep (do this first, ~10 minutes)

## 1.1 Open Terminal

1. Press **Command + Space** (Spotlight).  
2. Type **Terminal**.  
3. Press **Enter**.

## 1.2 Install / check tools

Copy each block, paste into Terminal, press Enter.

```bash
# Check Homebrew (Mac package helper). If missing, install from https://brew.sh
brew --version
```

```bash
# Install sing-box if needed (used later when connecting configs)
sing-box version || brew install sing-box
```

```bash
# SSH client (almost always already there)
ssh -V
```

## 1.3 Create your SSH key (one time forever)

```bash
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "pcs-ceo" -f ~/.ssh/id_ed25519 -N ""
```

- If it asks questions: press **Enter** for defaults.  
- Show the **public** key (safe to paste into websites):

```bash
cat ~/.ssh/id_ed25519.pub
```

You should see one long line starting with `ssh-ed25519`.  
**Select all of it, copy it.** You will paste it into every VPS provider.

## 1.4 Optional but smart — keep secrets out of Time Machine

```bash
sudo tmutil addexclusion ~/.pcs_industrial_20260802
```

Enter your Mac login password when asked (characters will not show—that is normal).

---

# Chapter 2 — Pick your money path

```text
┌─────────────────────────────────────┐
│ Do you need $0 only right now?      │
└─────────────────────────────────────┘
           │
     yes   │   no
           ▼
   Path B (Oracle free)     Path C (recommended)
   accept incomplete 25     full 25 professional
           │
           ▼ later if streaming fails
        Path D (ISP sticky for US/GB/DE only)
```

| If you want… | Choose |
|--------------|--------|
| Learn the process for free | **Path B** (1–few free VMs), then Path C |
| Full Core + Pro exit fleet ASAP | **Path C** |
| Netflix/bank still angry after C | **Path D** for a few sticky ISP IPs |

---

# Chapter 3 — Path B: Free-max (Oracle Always Free)

**Honesty first:** Oracle’s free tier is the best **$0** option, but:

- Capacity is often **full** (“out of capacity”).  
- Regions are **limited** (not “5 IPs in Dubai + 5 in Canada” for free).  
- You will usually get **a few** free instances, **not 25**.  
- IPs are still **datacenter**, not residential fiber.

Use Path B to practice SSH and one deploy, then buy Path C for the rest.

## 3.1 Create an Oracle Cloud account

1. Open: [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/)  
2. Click **Start for free** / **Sign up**.  
3. Use a real email and phone.  
4. They often ask for a **credit card** to verify you are human — Always Free should not charge if you only use free shapes (read the current Always Free page carefully).  
5. Pick a **Home Region** you will keep forever (example: a US or EU region). You cannot easily change it later.

## 3.2 Create one free Ubuntu instance (simplified)

Exact buttons change; the ideas stay the same:

1. Log into **Oracle Cloud Console**.  
2. Menu (☰) → **Compute** → **Instances** → **Create instance**.  
3. **Name:** `pcs-free-01`  
4. **Image:** Canonical **Ubuntu 22.04** (or 24.04 if listed).  
5. **Shape:** Always Free eligible (often **Ampere A1** flexible, or micro AMD if offered).  
   - Keep CPU/RAM inside Always Free limits shown on screen.  
6. **Networking:** create / use a VCN; ensure a **public IP** is assigned.  
7. **SSH keys:** paste your `ssh-ed25519 …` public key.  
8. Create. Wait until state is **Running**.  
9. Copy the **Public IP address**.

## 3.3 Open firewall ports (Oracle)

1. Find the instance’s **Subnet** → **Security List** (or Network Security Group).  
2. Add **Ingress** rules:
   - TCP **22** (SSH)  
   - TCP **443**  
   - UDP **443**  
   - UDP **8443** (for Hy2 on some locations)  
3. Source can be `0.0.0.0/0` for learning (lock down later if you want).

## 3.4 Test SSH

Oracle Ubuntu often uses user **`ubuntu`**, not `root`:

```bash
ssh ubuntu@PASTE_PUBLIC_IP
```

First time: type `yes` then Enter.  
If it works, type `exit`.

## 3.5 Register this free IP with PhantomCloak (practice)

Germany key only if the VM is actually in Europe; otherwise use a key that matches region (e.g. `us` for US home region).

```bash
cd ~/Desktop/PCS_Industrial_20260802

# Example if your free VM is in a US region:
python3 shared/pcs_inventory_wizard_v20260802.py \
  --set us=PASTE_PUBLIC_IP \
  --rematerialize
```

Then deploy (user may be `ubuntu` — deploy script expects `user@ip`):

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_one_v20260802.sh \
  ubuntu@PASTE_PUBLIC_IP us
```

If deploy assumes root and fails, SSH in and either enable root SSH (advanced) or re-create with a provider that gives root (Path C is easier).

## 3.6 After Path B

Write down every free IP you got.  
**Then switch to Path C** to complete all 25 countries/slots.

---

# Chapter 4 — Path C: Low-cost professional 25 (recommended)

This is the path that makes both **Core** and **Pro** feel complete for exits.

## 4.1 The shopping list (exactly 25)

| Slots | Country | Product key | Where to click in the console | Why |
|------:|---------|-------------|-------------------------------|-----|
| 1–5 | Germany | `germany` | Frankfurt / Falkenstein / Nuremberg | EU streaming, browsing, general |
| 6–10 | Canada | `vancouver` | Toronto / Vancouver / Montreal | Streaming + browsing |
| 11–15 | United States | `us` | New York / New Jersey / Los Angeles | Streaming #1 |
| 16–20 | United Kingdom | `gb` | London | Streaming #2 |
| 21–25 | UAE | `dubai` | Dubai (or nearest ME) | Crypto purpose |

**Hostnames to use (easy tracking):**

```text
pcs-de-01 … pcs-de-05
pcs-ca-01 … pcs-ca-05
pcs-us-01 … pcs-us-05
pcs-gb-01 … pcs-gb-05
pcs-ae-01 … pcs-ae-05
```

## 4.2 Which provider for which country

| Country | Provider suggestion | Why |
|---------|---------------------|-----|
| Germany | **Hetzner** | Usually cheapest solid EU VPS |
| US, UK, Canada | **Vultr** or **DigitalOcean** | Simple UI, many cities |
| UAE | **Vultr** / **Linode** / **DO** if Dubai exists | If no Dubai: buy later; do not fake AE with US IP |

You can use **one provider for everything** if they have all five geos (simplest for beginners). Vultr often has the widest city list for first-timers.

## 4.3 Budget worksheet (fill with live prices)

```text
Price per small VPS (example): $____ / month
× 25 servers                    = $____ / month
```

Rule of thumb: **~$2.50–$6** each → **~$65–$150/month** for 25.  
That is normal for a private multi-country industrial fleet—not a scam.

## 4.4 Create accounts (once per provider)

1. Sign up with email.  
2. Verify email.  
3. Add a **payment method**.  
4. In **Settings → SSH Keys**, click **Add**, paste your Mac public key, save as `mac-pcs`.

## 4.5 Create ONE server — full click path (then repeat 24 times)

Do Germany first so you can test deploy before spending on all 25.

### Settings checklist (every server)

| Setting | Choose |
|---------|--------|
| Image / OS | **Ubuntu 22.04 LTS** or **24.04 LTS** |
| Plan | Smallest: **1 vCPU, 0.5–1 GB RAM**, ~10–25 GB disk |
| Location | Match the country row above |
| SSH key | Your `mac-pcs` key (disable password-only if offered) |
| IPv4 | **Enabled** (public) |
| Hostname | e.g. `pcs-de-01` |

### After create

1. Wait until status is **Running**.  
2. Copy **IPv4**.  
3. Paste into spreadsheet (`CEO_FLEET_IP_SPREADSHEET_TEMPLATE.csv`) for that row.  
4. Test:

```bash
ssh root@PASTE_IP
# or: ssh ubuntu@PASTE_IP
```

Type `yes` if asked. Then `exit`.

### Firewall (if the provider has a “Firewall” product)

Allow inbound:

- **22/tcp**  
- **443/tcp**  
- **443/udp**  
- **8443/udp**  

Attach the firewall to each new VPS.

## 4.6 Shopping order (reduce overwhelm)

| Day | Buy | Test |
|-----|-----|------|
| Day 1 | **germany × 1** only | Full PhantomCloak deploy (Chapter 7) |
| Day 1–2 | **germany × 4 more** (total 5) | `deploy_pool germany` |
| Day 2 | **vancouver × 5** | pool deploy |
| Day 3 | **us × 5** | pool deploy |
| Day 4 | **gb × 5** | pool deploy |
| Day 5 | **dubai × 5** | pool deploy |

**Do not** buy Cayman/Seychelles/etc. until these 25 work.

## 4.7 If a country is missing in the console

| Missing region | Temporary action |
|----------------|------------------|
| No Dubai | Skip AE slots for now; still run DE/CA/US/GB (20 IPs). Add AE later. |
| No Canada | Use US East for learning only if needed—but **label honestly** (do not call it Canada in purpose UI). Better: pick another provider. |
| Account blocked | Try second provider; complete ID verification calmly. |

---

# Chapter 5 — Path D: Optional “residential-class” upgrade (later)

Use **only after** Path C works and something important still fails (e.g. streaming).

## What to buy

- **Static ISP** or **dedicated residential** IPs from a **legitimate paid** provider.  
- Prefer products where **you still control a server** (or a clear long-lived endpoint).  

## What not to buy for first 25

- “Unlimited rotating residential” dumps  
- Random GitHub “free proxy lists”  
- Anything you cannot SSH into or cleanly integrate  

## Smart upgrade pattern (money-saving)

| Keep Path C VPS | Add Path D sticky |
|-----------------|-------------------|
| 4 rotate IPs per country | 1 ISP sticky for US, GB, DE, CA |

That keeps Pro rotation + one “home-like” IP for hard sites—without paying residential prices for all 25.

**Note:** Pure HTTP/SOCKS residential proxies are a **different** Pro pipeline (`bulk_proxy` class). Reality/sing-box wants **your** VPS. If a seller only gives SOCKS, do not force it into Reality private-key deploy without engineering help in a later session.

---

# Chapter 6 — Fill the spreadsheet

1. Open:  
   `~/Desktop/PCS_Industrial_20260802/docs_v20260802/CEO_FLEET_IP_SPREADSHEET_TEMPLATE.csv`  
2. In Numbers/Excel/Google Sheets, paste each public IP into the **ip** column.  
3. Leave empty rows empty until bought.  
4. **ssh_user** is usually `root` (Hetzner/Vultr) or `ubuntu` (some images).  
5. Save a copy on your Desktop: `pcs-25-ips.csv`.

### Example row (fake IP shown as pattern only)

```text
DE,1,203.0.113.10,root,germany,primary sticky
```

Use **your** real IP from the provider—not documentation examples.

---

# Chapter 7 — Connect the 25 to PhantomCloak (Mac)

Do this when you have **at least 1** IP working; then expand to pools of 5.

## 7.1 Single IP (first success)

```bash
cd ~/Desktop/PCS_Industrial_20260802

python3 shared/pcs_inventory_wizard_v20260802.py \
  --set germany=YOUR.REAL.IP.HERE \
  --rematerialize
```

Check:

```bash
python3 shared/pcs_server_readiness_v20260802.py | \
  python3 -c 'import sys,json; d=json.load(sys.stdin); print("configured=", d.get("configured_count")); print("status=", d.get("status"))'
```

You want **`configured=` at least 1**.

Deploy:

```bash
bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_one_v20260802.sh \
  root@YOUR.REAL.IP.HERE germany
```

Confirm on server:

```bash
ssh root@YOUR.REAL.IP.HERE 'sudo systemctl is-active sing-box'
# expect: active
```

## 7.2 Full country pool (5 IPs)

```bash
python3 shared/pcs_inventory_wizard_v20260802.py \
  --set-pool germany=IP1,IP2,IP3,IP4,IP5 \
  --rematerialize

bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_pool_v20260802.sh germany
```

Repeat for: `vancouver`, `us`, `gb`, `dubai`.

## 7.3 All at once (when spreadsheet is full)

```bash
python3 shared/pcs_inventory_wizard_v20260802.py \
  --set-pool germany=... \
  --set-pool vancouver=... \
  --set-pool us=... \
  --set-pool gb=... \
  --set-pool dubai=... \
  --rematerialize
```

Then deploy each pool:

```bash
for loc in germany vancouver us gb dubai; do
  bash ~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_pool_v20260802.sh "$loc"
done
```

## 7.4 Command Center check

```bash
./launches_v20260802/Open_PCS_CommandCenter_v2.command
```

Look for **pool real IPs** rising and protect gate still honest until configs exist.

---

# Chapter 8 — Core vs Pro: you are not “missing half the product”

| Need | Core | Pro | Covered by this 25-VPS plan? |
|------|------|-----|------------------------------|
| Kill-switch + fail-closed protect | Yes | Yes | Yes (software + ≥1 exit) |
| Purpose modes (streaming, crypto, browsing, nomad, other) | Yes | Yes | Yes (5 countries hit top use-cases) |
| Multi-country exits | Yes | Yes | Yes |
| 5-way rotation / failover per country | Nice | Yes | Yes (5 IPs each) |
| Sticky “dedicated” IP | Soft | Yes | Yes (slot 01 primary) |
| Residential **catalog** UI | Yes | Yes | Already on Mac (synthetic catalog) |
| True residential ASN | Optional | Optional | Path D later if needed |
| Team seats / RBAC / API | No | Software | **Not** a VPS shopping problem |
| Always-on watchdog | Soft | Pro software | Software feature, not extra VPS brand |

**You do not need a different “Pro VPS brand.”**  
Path **C** 25 IPs = complete **network** backbone for personal Core and prosumer Pro.  
Pro software features unlock with tier license—not by buying a second fleet.

---

# Chapter 9 — Troubleshooting (first-time)

| Problem | What to try |
|---------|-------------|
| Oracle “out of capacity” | Retry other ADs/shapes; accept Path C |
| `Permission denied (publickey)` | Re-paste SSH public key; use correct user (`root` vs `ubuntu`) |
| SSH timeout | Open port 22 in provider firewall; wait 2 minutes after create |
| Deploy fails | Confirm Ubuntu, public IP, SSH works first |
| No Dubai region | Skip AE; run 20 IPs; add later |
| Card declined | Contact bank; try smaller first purchase |
| “VPN forbidden” ToS anxiety | You are running **your** private encrypted endpoint on **your** VPS—secure the box, don’t abuse third-party networks |
| Streaming still blocked | Path C works but ASN is datacenter → Path D sticky for that country |

---

# Chapter 10 — Paste this back into the Grok session

When you have IPs (even one):

```text
STATUS: gathering | inventory_set | deploy_done | stuck
PROVIDER: Vultr | Hetzner | Oracle | other
COUNTRY: germany
PRODUCT_KEY: germany
SSH_USER: root
IPS: 1.2.3.4, 5.6.7.8, 9.9.9.9, 10.0.0.1, 11.0.0.1
ERROR: (paste last lines if stuck)
```

Agents will materialize, deploy, and re-scan readiness.  
**Do not invent IPs.** Only paste addresses shown in the provider console.

---

# Quick start card (print / pin)

1. Mac: SSH key + Terminal ready.  
2. Buy **1× Germany** Ubuntu VPS (Path C).  
3. `ssh root@IP` works.  
4. Wizard `--set germany=IP --rematerialize` + `deploy_one`.  
5. `configured_count ≥ 1`.  
6. Buy remaining **4 Germany**, then other countries to **25**.  
7. `--set-pool` + `deploy_pool` per country.  
8. Optional Path D only if streaming needs it.  

**File locations**

| Item | Path |
|------|------|
| This guide | `docs_v20260802/CEO_GATHER_25_VPS_BEGINNER_GUIDE_v20260804.md` |
| Spreadsheet | `docs_v20260802/CEO_FLEET_IP_SPREADSHEET_TEMPLATE.csv` |
| After-IP deploy | `docs_v20260802/CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md` |
| Inventory file | `~/.pcs_industrial_20260802/vps_inventory.json` |

---

*Industrial tree only. No PhantomCloak Suite source edits. No scraped residential lists.*
