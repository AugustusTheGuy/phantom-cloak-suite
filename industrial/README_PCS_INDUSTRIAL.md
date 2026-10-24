# PCS Industrial 20260802

**New location. New filenames. Does not overwrite**  
`~/Desktop/PhantomCloak` or `~/Desktop/PhantomCloak Suite`.

## Docs (start here)

| Priority | Doc | Role |
|----------|-----|------|
| **1 — SOURCE OF TRUTH map** | [`docs_v20260802/INDEX_v20260802.md`](docs_v20260802/INDEX_v20260802.md) | purpose → path → audience (control plane) |
| **2 — 5-minute orientation** | [`docs_v20260802/QUICKSTART_v20260802.md`](docs_v20260802/QUICKSTART_v20260802.md) | new operator / agent bootstrap |
| **Canonical deploy/verify (read-only)** | `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` | Suite HOWTO — do not edit from this tree |
| Industrial deploy bridge | [`docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md`](docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md) | industrial paths & commands only |

**State & secrets:** `~/.pcs_industrial_20260802/` (not this Desktop tree).  
See `docs_v20260802/STATE_NOTE_v20260802.md` and `docs_v20260802/SECURITY_SECRETS_v20260802.md`.  
Do not commit PEMs / `location_keys.json` — `.gitignore` enforces this.

## Quick start

```bash
# Use industrial venv (Argon2id)
# .venv already has argon2-cffi if setup was run

chmod +x launches_v20260802/*.command
./launches_v20260802/Launch_PCS_Core_v20260802.command   # Core shell: resume + KS auto-on + score
./launches_v20260802/Open_PCS_CommandCenter_v2.command  # UI v2 + live /api/status (port 8790)

# Status JSON (works when Suite missing/partial)
.venv/bin/python core_product/pcs_app_shell_v20260802.py --status

# Command Center HTTP (static dashboards + readiness API)
.venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-dashboard 8790 --open-dashboard
# → http://127.0.0.1:8790/  and  GET /api/status

# Security engine
.venv/bin/python -m shared.pcs_security_audit_engine_v20260802

# Argon2 accounts (industrial store only)
.venv/bin/python -m shared.pcs_account_manager_argon2_v20260802

# pf rules location (NOT /tmp)
ls ~/.pcs_industrial_20260802/pf_rules/
```

### UX v2 dashboard
`dashboards_v20260802/pcs_suite_command_center_v2_20260802.html`  
Live fields: `status`, `configured_count`, `server_filled_count`, `pending_ip_count`,
`next_actions`, `secrets_fingerprint` (public), `protect_gate.ok_for_protect`,
residential catalog **counts only** (not tunnels). CTAs: inventory path · wizard · HOWTO.

## Grok workflow

`/security_audit` — triad: Senior Designer + Pentester + Judge → report  
File: `~/.grok/workflows/security_audit.rhai`

## App shell (Suite import-only + industrial preflight)

```bash
.venv/bin/python core_product/pcs_app_shell_v20260802.py --status
.venv/bin/python core_product/pcs_app_shell_v20260802.py --resume
.venv/bin/python core_product/pcs_app_shell_v20260802.py --activate browsing CH
.venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
# Landing: http://127.0.0.1:8787/
```

Or: `./launches_v20260802/Serve_PCS_Landing_Payments_v20260802.command`

## Feature truth (FTC / no overselling)

Canonical statuses: **implemented | config_needed | scaffold | not_started**.  
See `docs_v20260802/FEATURE_TRUTH_MATRIX_v20260802.md` and `shared/pcs_feature_matrix_v20260802.py`.

- Protect is **fail-closed** until `configured_count > 0` (real VPS client configs).  
- Residential **catalog UI** is ready; catalog ≠ residential proxy / tunnel service.

## Pricing (product report)

- Core: **$11.99/mo** · **$59.88/yr** ($4.99/mo)  
- Pro: **$39/mo** founder · **$348/yr** ($29/mo)  

## Payments

XMR, BTC, ETH, SOL, CARD (Stripe when `STRIPE_SECRET_KEY` set).  
Industrial module: `shared/pcs_payments_industrial_v20260802.py`  
State: `~/.pcs_industrial_20260802/payments/`

### Serve landing + payments locally (no live charges without Stripe key)

```bash
cd ~/Desktop/PCS_Industrial_20260802
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"

# Preferred launcher (port 8787 default; pass port as $1)
./launches_v20260802/Serve_PCS_Landing_Payments_v20260802.command

# Or app shell / module
.venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
.venv/bin/python -m shared.pcs_payments_http_v20260802
# → http://127.0.0.1:8787/  (landing)  GET /api/pricing  POST /api/create_order
# Without STRIPE_SECRET_KEY: CARD uses pi_demo_; POST /api/confirm_demo mints access offline.
```

### Dry health (checkout reliability without charges)

```bash
.venv/bin/python -m shared.pcs_payments_landing_health_v20260802
.venv/bin/python -m shared.pcs_payments_landing_health_v20260802 --probe-serve --json
```

## Hosting / campaign

See `docs_v20260802/HOSTING_AND_CAMPAIGN_v20260802.md` and `docs_v20260802/CAMPAIGN_POSTS_READY_v20260802.md`.

## Post-connect leak verification (bridge)

Industrial wrapper discovers Suite verify tools **read-only** and writes CEO
pass/fail JSON under `~/.pcs_industrial_20260802/verify_reports/`.

**Does not connect to a VPS by itself** — run after tunnel is up, or dry-run
offline to see skip reasons (no tunnel / pending inventory IP).

```bash
# Discover Suite tools + env contract
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --discover-only

# Offline dry-run (auto when no utun/sing tunnel)
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --location dubai --dry-run

# After VPS IP in inventory + materialize + sing-box connected:
export PCS_VERIFY_LOCATION=dubai
# expected IP from inventory automatically, or:
export PCS_VERIFY_EXPECTED_IP=203.0.113.10
.venv/bin/python -m shared.pcs_verify_bridge_v20260802 --location dubai
```

| Env | Purpose |
|-----|---------|
| `PCS_VERIFY_LOCATION` | Exit key (`dubai`, `hongkong`, …) |
| `PCS_VERIFY_EXPECTED_IP` | Expected public IPv4 of exit VPS |
| `PCS_VPS_<LOC>` | Alternate expected IP (e.g. `PCS_VPS_DUBAI`) |
| `PCS_VERIFY_FORCE=1` | Force live IP probes without tunnel (**not recommended**) |

Checks: client config preflight → tunnel → ipify/ipinfo/ifconfig → DNS dig →
WebRTC guidance → Suite `scripts/verify/full_verification_suite.py` when present.

**Killswitch recommendation:** live IP mismatch (`ip_mismatch_possible_leak`) sets
`trip_killswitch_recommended=true` on the CEO report (top-level + `ceo.*`).
Dry-run / no-tunnel stays `overall=NOT_RUN` and **never** sets the flag.
Optional `killswitch_trip_fn` hook is recommend-default (does not arm pf alone).
See `docs_v20260802/HOWTO_DEPLOY_LINK_v20260802.md` § killswitch recommendation.

Reports: `~/.pcs_industrial_20260802/verify_reports/latest.json`

See also: Suite (read-only) `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md` § verification.

## Optional: open legacy Suite UI (read-only tree)

```bash
PCS_OPEN_SUITE_UI=1 ./launches_v20260802/Launch_PCS_Core_v20260802.command
```

Uses Suite `client/phantomcloak.py` without editing it.
