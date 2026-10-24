# Swarm Audit Note — Principal Engineering Auditor (Agent 12)

**Date:** 2026-08-04  
**Scope:** Industrial only — `Desktop/PCS_Industrial_20260802`  
**Board under review:** `SWARM_STATUS_BOARD_v20260802.md`  
**Method:** Disk + live readiness probe + module presence + hermetic pytest. No invented IPs. No Suite overwrite.

---

## Verdict (PM accuracy)

| Gate | Result | Summary |
|------|--------|---------|
| **PM accuracy on `configured_count` / inventory truth** | **PASS** | Live scan matches board: `configured_count = 0`, no real IPs, protect must stay fail-closed. |
| **PM accuracy on “modules exist / fleet build in flight”** | **PASS with caveats** | Core modules and scripts are on disk; several agent rows still say `in_progress` after v1 delivery — status labels lag code. |
| **Tests exist and pass** | **PASS** | `tests_v20260802/`: **144 passed** in 0.71s (ephemeral clean venv). |
| **Oversell in board** | **MINOR FAIL (label lag, not product lie)** | Board understates delivery of inventory v2 / batch deploy; does **not** claim live tunnels or `configured_count > 0`. |
| **Oversell in other new docs** | **FAIL (campaign hook only)** | `CAMPAIGN_WEEK1_GRASSROOTS_v20260802.md` uses absolute-ish mimicry/masking copy. See §Oversell. |
| **Scrape risk (product code + ops docs)** | **PASS (policy) / CONDITIONAL (enforcement)** | Scrapes forbidden everywhere that matters; code rejects private/TEST-NET, **not** “ownership of public IP.” |
| **Absolute undetectability claims** | **REJECTED** | Forbidden in truth matrix / FTC / detection catalog / UI. Campaign week-1 hook is non-compliant and must not ship as-is. |
| **CEO playbook beginner-usable** | **PASS with fixes recommended** | Part A is walkable for a non-expert; Part B product keys and “v2 not yet active” wording need tightening. |

**Overall board truthfulness for CEO decisions: PASS.**  
**Overall marketing honesty across `docs_v20260802`: CONDITIONAL FAIL until campaign hook is rewritten.**

---

## 1. Live verification (disk / runtime)

### 1.1 `configured_count`

Command (industrial tree):

```bash
python3 shared/pcs_server_readiness_v20260802.py
```

| Field | Live value | Board claim | Match? |
|-------|------------|-------------|--------|
| `status` | `server_package_ready_pending_client_ips` | (implied not ready) | yes |
| `configured_count` | **0** | **0 until CEO IPs** | **yes** |
| `server_filled_count` | 10 | n/a on board | n/a |
| `pending_ip_count` | 9 | n/a | n/a |
| inventory `ips_set` | **0** | CEO blockers 1–2 | **yes** |
| inventory path | `~/.pcs_industrial_20260802/vps_inventory.json` | — | exists, version **2**, all `pool: []` |

Client tree under `~/.pcs_industrial_20260802/singbox/`: **only `*.pending.json`** (bahamas, cayman, dubai, frankfurt, germany, hongkong, mauritius, seychelles, vancouver). No live client configs with real exit IPs.

**Auditor conclusion:** Board global signal on `configured_count` is **accurate**. Protect must remain fail-closed. No evidence of invented IPs on disk.

### 1.2 Modules claimed by swarm ownership

| Expected capability | Path | On disk? |
|---------------------|------|----------|
| Inventory v2 multi-IP | `shared/pcs_inventory_v2_v20260802.py` | **yes** (242 lines) |
| Wizard `--set` / `--set-pool` | `shared/pcs_inventory_wizard_v20260802.py` | **yes** (`--set-pool` wired) |
| Readiness | `shared/pcs_server_readiness_v20260802.py` | **yes** |
| Materialize | `shared/pcs_materialize_singbox_v20260802.py` | **yes** |
| Client sing-box (selector/urltest) | `shared/pcs_client_singbox_v20260802.py` | **yes** (urltest for multi-**transport**) |
| Synthetic profile + score | `shared/pcs_synthetic_profile_v20260802.py` | **yes** |
| Preflight / KS gate | `shared/pcs_preflight_obfuscation_gate_v20260802.py` | **yes** |
| Purpose routing | `shared/pcs_purpose_routing_v20260802.py` | **yes** |
| Verify bridge | `shared/pcs_verify_bridge_v20260802.py` | **yes** |
| Deploy one / pool | `server_vps_package_v20260802/scripts/pcs_deploy_{one,pool}_v20260802.sh` | **yes** (+ mirrored under state `vps_server_package/scripts/`) |
| CEO beginner playbook | `docs_v20260802/CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md` | **yes** |
| Detection catalog | `docs_v20260802/DETECTION_SURFACE_CATALOG_v20260802.md` | **yes** |

### 1.3 Tests

| Check | Result |
|-------|--------|
| Test package present | `tests_v20260802/` — 8 test modules + `conftest.py` |
| Approx. test functions (source count) | 116 defs (classes expand collection) |
| Hermetic run (clean venv, 2026-08-04) | **`144 passed` in 0.71s** |
| Host default `python3 -m pytest` | **Unavailable** (no pytest on brew 3.14; delphi env pytest 4.6 breaks on modern AST) — **ops note**, not a product fail |

Coverage of swarm-critical paths (present in suite): readiness fail-closed, materialize pending-only, preflight gate, deploy dry-run, residential catalog honesty, inventory v2 pools, synthetic profile fail-closed, session-resume honesty, integration regression.

---

## 2. Agent row audit (devil’s advocate on PM statuses)

Board rule: serialize shared files; CEO vs AGENT blockers labeled. That structure is sound.

| Agent | Board status | Disk truth | Auditor status correction |
|-------|--------------|------------|---------------------------|
| 1 Fleet SRE | `in_progress` | inventory v2 + deploy_pool + deploy_one present | **partial_delivered** — remaining: multi-slot materialize (TODO in materialize), ops polish |
| 2 Readiness pool counting | `in_progress` | `_inventory_status()` counts **top-level `ip` only**; no pool-size field in readiness summary; `configured_count` still client-file based | **still open** (accurate) |
| 3 Client net multi-outbound | `in_progress` | selector + urltest for Reality+Hy2; **multi-pool-member client JSON explicitly TODO** | **partial** — do not claim pool failover live |
| 4 Appsec | `standby` | secrets/pending paths exist from prior industrial | standby OK |
| 5 Preflight/KS wipe + score | `in_progress` | preflight gate live; **synthetic `gate_profile` not imported into preflight/zeroleak path** | **still open** (accurate) |
| 6 Synthetic profile | `in_progress` | module + tests exist; score is informative, not warranty | **v1 delivered; wire-up open** |
| 7 Detection research | `delivered v1` | catalog present; honest claim rule | **PASS** |
| 8 Purpose routing | `in_progress` | module + inventory `purpose_routing` keys present | **v1 delivered** |
| 9 Command Center | `pending` | v2 UI has purpose **session display**; not full pool ops UI | **pending** OK |
| 10 Verify | `pending` | bridge module large/present; live tunnel verify blocked by count=0 | **pending/blocked on CEO IPs** |
| 11 PM | `active` | board exists | OK |
| 12 Auditor | `active` | this note | OK |

**AGENT blockers on board:**

1. “Inventory v2 code path” — **stale as a pure blocker.** Path exists and inventory file is already `version: 2`. Remaining work is multi-client emit + readiness pool metrics, not “invent v2.”  
2. “Synthetic profile gate wiring” — **still valid.**  
3. “Batch deploy script” — **stale.** `pcs_deploy_pool_v20260802.sh` exists in repo and state package.

**CEO blockers on board:** **accurate** (owned IPs, paste inventory, later landing/Stripe). Aligns with `PRE_MARKETING_READINESS_REPORT_v20260802.md`.

---

## 3. Oversell findings

### 3.1 Board itself

| Claim class | Finding |
|-------------|---------|
| Live product / multi-geo ready | **Not claimed** — good |
| `configured_count > 0` | **Not claimed** — good |
| Perfect undetectability | **Explicitly rejected** in cycle notes — good |
| Agent progress | **Slight under-report of delivery** (v2/deploy exist) — mild PM lag, not customer-facing oversell |

### 3.2 Campaign / marketing docs (must fix)

**REJECT — absolute / quasi-absolute performance claims:**

From `CAMPAIGN_WEEK1_GRASSROOTS_v20260802.md`:

> “100% On-Device Signal Masking … 98-99% Mimicry Scores”

**Why this fails industrial honesty gates:**

- Mimicry score in code/docs is a **weighted 0–100 heuristic** (`pcs_synthetic_profile_v20260802.py`, `DETECTION_SURFACE_CATALOG_v20260802.md`), **not** a lab-measured 98–99% evasion rate.  
- “100% … masking” is absolute language; conflicts with `FEATURE_TRUTH_MATRIX`, `FTC_HONEST_CLAIMS`, detection catalog claim rule.  
- At `configured_count = 0`, any campaign implying live protected sessions is product-false.

**Contrast (acceptable):** `CAMPAIGN_POSTS_READY_v20260802.md` uses “Not magic anonymity — protections active, verify recommended” and ties Pro residential language to catalog metadata / VPS exits. Prefer that tone exclusively.

### 3.3 Absolute undetectability — formal rejection

Auditor **rejects** any of the following if they reappear in industrial docs, UI, or posts:

- “Undetectable by all systems / classifiers / forever”
- “Zero data can ever leave under any OS bug”
- Guaranteed 98–99% mimicry or 100% signal masking as product fact
- “Connected” / “protected” green state while `configured_count == 0`

**Present state:** Truth docs and Command Center copy correctly say **never “undetectable”**. Campaign week-1 hook is the sole critical oversell hit in new docs sampled.

---

## 4. Scrape risk

| Layer | Assessment |
|-------|------------|
| Docs (CEO playbook, runbook, incident, residential vs VPS, operator checklist, inventory wizard) | **Consistent forbid** of scraped residential / proxy-list IPs |
| Residential catalog module | Synthetic region-seeded UX; **not** tunnel endpoints; documented as such |
| Inventory accept path | Accepts any **public-looking** IPv4/hostname after rejecting RFC1918 / TEST-NET / placeholders |
| Ownership proof | **None automated** — scraped public residential IPs *could* be pasted if operator ignores policy |
| Product scrape tooling | **None found** in industrial tree that harvests proxy lists |

**Scrape risk rating:** **LOW in code intent**, **MEDIUM if a careless operator pastes lists** (policy-only control). Board cycle note (“reject any PR/agent output that scrapes residential IPs”) is correct and should remain a hard CI/review rule.

**Not scrape, but related residual risk:** materialize currently uses **primary / first pool member** only for client config; batch deploy can push multiple servers while client selector does not yet span pool members — ops can over-claim “fleet rotation” before Agent 3 TODO is closed.

---

## 5. CEO Fleet Beginner Playbook — usability

**File:** `docs_v20260802/CEO_FLEET_BEGINNER_PLAYBOOK_v20260802.md`

### Pass criteria for “beginner-usable”

| Criterion | Result |
|-----------|--------|
| Non-expert audience stated | **yes** |
| One-server first-hour path (Part A) | **yes** — brew/ssh key → one VPS → wizard → readiness → deploy → systemd check |
| Explicit anti-scrape rule | **yes** |
| Success metrics (`configured_count`, sing-box active) | **yes** |
| Stuck paste template for Grok | **yes** (Part F) |
| Deploy script path exists on this machine | **yes** — `~/.pcs_industrial_20260802/vps_server_package/scripts/pcs_deploy_one_v20260802.sh` |

### Beginner friction (fix recommended, not full fail)

1. **Product keys `us` / `gb`** in Part B are **not** in readiness `CANONICAL_LOCS` (`dubai, hongkong, vancouver, germany, bahamas, cayman, mauritius, seychelles`). Beginner who buys “US/UK” and uses `us`/`gb` may hit inventory/materialize gaps. Playbook admits `vancouver` until US slot exists — still easy to mis-key.  
2. **“When inventory v2 is active (agents ship this session)”** is **stale**: live inventory is already `version: 2` and wizard supports `--set-pool` **now**.  
3. **MVP 5×5 = 25 VPS** is cost-shocking if read before Part A; keep Part A as the only “must do today,” demote MVP to “after first green protect.”  
4. Optional: one line pointing at Desktop package as alternate root if state package scripts are missing on a fresh machine.

**Auditor call:** **Beginner-usable for Part A (PASS).** Part B needs key/wording cleanup before CEO scales spend.

---

## 6. Integration honesty (what is *not* done yet)

Do not let PM or marketing collapse these into “done”:

1. **`configured_count > 0`** — blocked on CEO owned IPs + rematerialize + successful client configs.  
2. **Readiness pool metrics** — inventory may hold N pool IPs; readiness summary still centers single `ip` / client file counts.  
3. **Multi-IP client selector across pool members** — TODO in `pcs_materialize_singbox_v20260802.py` (Agent 3).  
4. **Synthetic score in protect preflight** — module exists; not fully wired into `activate_protected_session` path.  
5. **Public landing + live Stripe** — still CEO/product GTM; pre-marketing report correctly **FAIL** for full-product ads.

---

## 7. Pass / fail scorecard (executive)

| # | Item | Pass/Fail |
|---|------|-----------|
| 1 | Board `configured_count = 0` matches disk | **PASS** |
| 2 | Modules listed for fleet/mimicry swarm exist | **PASS** |
| 3 | Automated tests exist and pass | **PASS** (144) |
| 4 | Board invents readiness or IPs | **PASS** (does not) |
| 5 | Board agent statuses fully current | **FAIL (minor)** — update blockers 1 & 3 |
| 6 | Absolute undetectability in truth docs / UI | **PASS** (rejected) |
| 7 | Absolute/quasi-absolute claims in campaign week-1 | **FAIL** — rewrite hook |
| 8 | Scrape-as-feature or scrape tooling | **PASS** (absent) |
| 9 | Scrape paste fully code-blocked | **FAIL (by design limit)** — policy + public-IP syntax only |
| 10 | CEO beginner playbook usable for first VPS | **PASS** |

---

## 8. Required actions (ordered)

1. **PM:** Refresh `SWARM_STATUS_BOARD` agent statuses and AGENT blockers (inventory v2 path + batch deploy are not pure blockers).  
2. **PM / marketing:** Rewrite or delete `CAMPAIGN_WEEK1` hook claiming 100% masking / 98–99% mimicry; align with `CAMPAIGN_POSTS_READY` + `FTC_HONEST_CLAIMS`.  
3. **CEO:** Follow playbook **Part A only** until `configured_count ≥ 1` and `sing-box` active; then scale.  
4. **Agents 2/3/5:** Close pool counting, multi-member client outbounds, synthetic score gate wiring — without claiming undetectability.  
5. **Docs:** Fix playbook product keys (`us`/`gb`) and “v2 not active yet” sentence.

---

## 9. Auditor sign-off

- **Board is safe for CEO operational decisions** (count is zero; blockers are human IP ownership).  
- **Board is not a green light for full-product marketing.**  
- **Any absolute undetectability claim is rejected** regardless of agent pedigree.  
- **CEO playbook is beginner-usable for the single-server proof path.**

— Agent 12 · Principal Engineering Auditor · industrial-only · 2026-08-04
