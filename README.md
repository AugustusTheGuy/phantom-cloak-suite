# PhantomCloak Suite

A self-hosted, privacy-first VPN and network-hardening suite for macOS. It provisions your own sing-box (VLESS + Reality / Hysteria2) exit servers, generates matching client configs, enforces a pf-based kill switch, and gives you a local command-center dashboard showing exactly what is configured, what is protected and what still needs attention.

The repo has two layers:

- **Suite (root)**: the original client, server templates, dashboard UI and macOS launchers.
- **`industrial/`**: a hardened "industrial" rewrite with strict secret-handling rules, a preflight protect gate, Argon2id account storage, a readiness API and a pytest suite of **183 tests (179 passing, 4 skipped)**.

## Highlights

- **Secret hygiene by design**: server private keys and Hysteria2 passwords are written only into the server package. Client "pending" configs go through a hard public-field allowlist with deep scrubbing of nested data. Stdout, metadata and the dashboard only ever show a public-material fingerprint, never key material.
- **Preflight protect gate**: kill switch, DNS, zero-leak and obfuscation checks have to pass in order before the tunnel is reported as "protected". If arming fails, the status is never "protected" (this is covered by tests).
- **pf kill switch** with privileged/unprivileged split, rule files kept out of `/tmp`, and automatic restoration of the previous network state.
- **Multi-location server materialization**: per-location sing-box templates, UUID/key generation, path rewriting and package validation, plus a dry-run deploy.
- **Command Center** (local HTTP on :8790): static dashboard plus `GET /api/status`, returning configured, filled and pending counts, next actions and gate status.
- **Accounts, tiers and payments**: Argon2id account manager, tier and feature matrix, pricing engine, payments health checks and RBAC.
- **Security audit engine** that turns a configuration into a scored findings report.

## Architecture

```
 macOS client (Python)                       Your VPS fleet
 ┌───────────────────────────────┐           ┌────────────────────────┐
 │ Command Center UI  (:8790)    │           │ sing-box server        │
 │   └─ /api/status  ◄─ app shell│           │  VLESS+Reality / Hy2   │
 │ Preflight gate ─► kill switch │  tunnel   │ (filled from templates)│
 │   (pf) ─► DNS ─► zero-leak    │ ════════► └────────────────────────┘
 │ sing-box client (public cfg)  │                    ▲
 │ Inventory wizard ─► materialize ──── server package ┘ (private keys stay here)
 │ Argon2id accounts · tiers · audit engine           │
 └───────────────────────────────┘
```

## Project tree

```
phantom-cloak-suite/
├── client/
│   ├── core/
│   │   └── … 26 files
│   ├── profiles/
│   │   ├── browser/
│   │   └── … 1 files
│   ├── ui/
│   │   └── … 5 files
│   └── … 3 files
├── docs/
│   └── … 5 files
├── industrial/
│   ├── core_product/
│   │   └── … 4 files
│   ├── dashboards_v20260802/
│   │   └── … 6 files
│   ├── docs_v20260802/
│   │   └── … 31 files
│   ├── landing_v20260802/
│   │   └── … 1 files
│   ├── launches_v20260802/
│   │   └── … 8 files
│   ├── pro_product/
│   │   └── … 1 files
│   ├── server_vps_package_v20260802/
│   │   ├── scripts/
│   │   └── templates_source_copy/
│   ├── shared/
│   │   └── … 25 files
│   ├── tests_v20260802/
│   │   └── … 11 files
│   └── … 4 files
├── landing/
│   └── … 1 files
├── launchd/
│   └── … 1 files
├── scripts/
│   ├── verify/
│   │   └── … 1 files
│   └── … 5 files
├── server/
│   ├── ready-for-vps/
│   │   └── … 8 files
│   ├── templates/
│   │   └── … 8 files
│   └── … 2 files
├── Launch Delphi Anti-Detection.command
├── Launch PhantomCloak.command
├── Launch Suite (Core demo).command
├── Launch Suite (Pro demo).command
├── SECURITY_METHODS.md
├── VERSION
├── reload_from_checkpoint.sh
└── setup-mac.sh
```

## Setup

```bash
# Suite (macOS)
./setup-mac.sh
./"Launch PhantomCloak.command"

# Industrial layer
cd industrial
python3 -m venv .venv && .venv/bin/pip install -r requirements_pcs_industrial_v20260802.txt pytest
.venv/bin/python core_product/pcs_app_shell_v20260802.py --status
.venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-dashboard 8790 --open-dashboard
.venv/bin/python -m shared.pcs_security_audit_engine_v20260802
.venv/bin/pytest -q tests_v20260802
```

Server templates in `server/ready-for-vps/` contain `REPLACE_*` placeholders only. Real keys are generated locally into `~/.pcs_industrial_20260802/`, which is gitignored and never part of this repo.

## Tech stack

Python 3.11+ · sing-box (VLESS/Reality, Hysteria2) · macOS pf · Argon2id (argon2-cffi) · vanilla HTML/CSS/JS dashboard · pytest · launchd · Bash

## Responsible use

This is a privacy tool for protecting your own traffic on infrastructure you control. Follow the laws and terms of service that apply to you.

## License

MIT, see [LICENSE](LICENSE).
