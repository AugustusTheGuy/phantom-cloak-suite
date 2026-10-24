# Eight UX features (industrial v2)

| # | Feature | Where |
|---|---------|--------|
| 1 | One-tap Resume Zurich · Browsing | `pcs_session_resume_v20260802.py` + dashboard v2 button |
| 2 | Confirm killswitch / tracker wipe | dashboard v2 modals |
| 3 | Server readiness card | `pcs_server_readiness_v20260802.py` + UI card |
| 4 | Kill switch auto-on with Activate | `pcs_preflight_obfuscation_gate` + industrial killswitch |
| 5 | Large city + flag hero | dashboard v2 city-hero |
| 6 | Security score chip | header chip + `run_full_audit` in Core shell |
| 7 | Honest copy | UI strings + FTC doc |
| 8 | VPS deploy wizard | modal → Suite HOWTO (read-only) + industrial link |

## Password hashing

- New: `shared/pcs_account_manager_argon2_v20260802.py` (Argon2id)
- Legacy Suite SHA-256 **unchanged**
- Accounts stored under `~/.pcs_industrial_20260802/accounts/`

## pf rules path

- New: `~/.pcs_industrial_20260802/pf_rules/pcs_killswitch_v20260802.pf.conf`
- Legacy Suite still uses `/tmp/delphi_killswitch.pf.conf` (not modified)
