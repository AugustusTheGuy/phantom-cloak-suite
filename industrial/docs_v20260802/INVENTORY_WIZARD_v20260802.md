# VPS inventory wizard — industrial operator CLI

**Script:** `shared/pcs_inventory_wizard_v20260802.py`  
**State file:** `~/.pcs_industrial_20260802/vps_inventory.json` (atomic write, mode `0600`)  
**Version:** v20260802

Operator-grade CLI (Stripe CLI / `gh` quality bar) for setting **owned VPS public IPs** only.

---

## Hard rules

| Rule | Behavior |
|------|----------|
| Industrial only | Writes only under `~/.pcs_industrial_20260802/` (or injected state/path). Never Suite / `~/.phantomcloak`. |
| No invented IPs | Empty stays empty. Wizard never fabricates addresses. |
| Dual validation | Every set must pass materialize `is_real_ip` **and** readiness `is_real_public_ip`. |
| Rejected classes | RFC1918, loopback, link-local, TEST-NET (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`), placeholders, `*.local`. |
| No secrets | Never writes UUID / Reality keys / HY2 passwords (those stay in `secrets/location_keys.json` via materialize). |
| Suite read-only | Materialize templates remain Suite-sourced copies; wizard does not touch Suite. |

Forbidden: scraped residential / proxy-list IPs. See `RESIDENTIAL_IP_VS_VPS_v20260802.md`.

---

## Locations

Canonical keys (match materialize):

`dubai` · `hongkong` · `vancouver` · `germany` · `bahamas` · `cayman` · `mauritius` · `seychelles`

Aliases accepted on CLI: `frankfurt`→`germany`, `hk`→`hongkong`, `dxb`/`uae`→`dubai`, `yvr`→`vancouver`, `de`→`germany`.

---

## Commands

### List

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py --list
```

Exit `1` if any **set** IP fails validation (empty is allowed).

### Non-interactive set

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=YOUR.REAL.VPS.IP \
  --set germany=YOUR.OTHER.VPS.IP
```

Repeatable `--set LOC=IP`. Optional `--ssh-user root`. Optional `--disable` (stores IP with `enabled=false`).

### Clear one location

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --clear-location dubai
```

### Validate only (no write)

Existing inventory:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py --validate-only
```

Dry-run proposed sets (must fail for private / TEST-NET / placeholders):

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=10.0.0.1 --validate-only
# → FAIL, wrote=false

python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=203.0.113.10 --validate-only
# → FAIL (TEST-NET documentation range)
```

### Set + rematerialize

After a successful write, optionally rebuild clients / server package:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --set dubai=YOUR.REAL.VPS.IP \
  --rematerialize
```

Calls `shared/pcs_materialize_singbox_v20260802.py` (industrial only).

### Interactive

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py
# or: --interactive
```

Per location: blank keeps current, `clear` unsets, `q` aborts without save. Confirm before write.

### Machine JSON

```bash
python3 …/pcs_inventory_wizard_v20260802.py --list --json
python3 …/pcs_inventory_wizard_v20260802.py --set dubai=10.0.0.1 --validate-only --json
```

---

## Path injection (tests / alternate state)

Never point tests at the live CEO inventory. Use:

| Mechanism | Effect |
|-----------|--------|
| `--inventory PATH` | Read/write that file only |
| `--state DIR` | Use `DIR/vps_inventory.json` |
| `PCS_INVENTORY_PATH` | Same as `--inventory` (flags win) |
| `PCS_STATE_DIR` or `PCS_INDUSTRIAL_STATE` | Same as `--state` |

Example hermetic dry-run:

```bash
TMP=$(mktemp -d)
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_inventory_wizard_v20260802.py \
  --inventory "$TMP/vps_inventory.json" \
  --set dubai=192.168.1.1 \
  --validate-only --json
# ok=false, wrote=false, TMP inventory not created for validate-only
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (list clean / write ok / validate ok) |
| `1` | Validation, write, or rematerialize failure |
| `2` | Usage / unknown location / interactive abort |

---

## Inventory schema

```json
{
  "version": 1,
  "ssh_user": "root",
  "note": "…operator note…",
  "locations": {
    "dubai": { "ip": "", "ssh_user": "", "enabled": true }
  },
  "updated_at": "ISO-8601",
  "updated_by": "pcs_inventory_wizard_v20260802"
}
```

File mode after every successful write: **`0600`**.

---

## Raise `configured_count` (wizard path)

1. Provision an owned VPS; record its **public** IPv4.  
2. Wizard `--set <loc>=<public-ip>` (or interactive).  
3. `--rematerialize` **or** run materialize separately.  
4. Readiness:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```

Pass: `configured_count` > 0.  
Deep deploy steps: `HOWTO_DEPLOY_LINK_v20260802.md`, `CEO_VPS_RUNBOOK_v20260802.md`.

---

## Related

| Doc | Role |
|-----|------|
| `HOWTO_DEPLOY_LINK_v20260802.md` | Full industrial deploy chain |
| `CEO_VPS_RUNBOOK_v20260802.md` | 15-minute CEO path |
| `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md` | Stuck at zero |
| `RESIDENTIAL_IP_VS_VPS_v20260802.md` | Owned VPS vs residential policy |
| Suite `docs/HOWTO_DEPLOY_AND_VERIFY.md` | Canonical (read-only) |
