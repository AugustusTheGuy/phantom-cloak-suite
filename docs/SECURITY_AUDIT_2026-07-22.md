# PhantomCloak security audit — 2026-07-22

**Scope:** `~/Desktop/PhantomCloak` client + `~/.phantomcloak` state  
**Methods:** static review (subprocess, secrets, perms), live `run_audit()`, deepcheck patterns, competitive kill-switch research  
**Tools:** `/deepcheck`, `/code-review` lens, Firecrawl search (VPN kill-switch + macOS pf)

---

## Executive summary

| Grade (post-harden) | Notes |
|---------------------|--------|
| **A-range after permission harden** | Sensitive state files were world-readable (`0o644`); fixed to `0o600`, dir `0o700` |
| **No `shell=True` found** | Subprocess calls use argv lists (good) |
| **Residual medium risks** | SHA-256 account password hashes; `/tmp` killswitch conf; stale `active=true` in session |

Live audit auto-hardens permissions and re-checks.

---

## Findings

| Sev | Issue | Present? | Action |
|-----|--------|----------|--------|
| **Med** | `last_session.json` / account JSON at `0o644` | **Yes** | Auto-harden in `security_audit.harden_state_permissions()`; `_save_session` now `chmod 0o600` |
| **Med** | Account passwords: single-round SHA-256 | **Yes** | Documented; upgrade path = Argon2id/scrypt (not yet changed — breaking hash change needs migration) |
| **Med/Low** | Killswitch rules under `/tmp/delphi_killswitch.pf.conf` | **Yes** | Prefer `~/.phantomcloak/killswitch.pf.conf` with `0o600` (recommended next) |
| **High (conditional)** | Active without killswitch | **Logic present** | Audit flags if app reports active && !ks |
| **High (conditional)** | Active without pf Enabled | **Logic present** | Audit flags via `pfctl -s info` |
| **Med (conditional)** | Active without sing-box process | **Logic present** | Stale session risk |
| **Low** | Stale `active=true` in last_session while suite off | **Yes possible** | Audit finding; clear flag on clean exit (recommended) |
| **Info** | Cloud vault local fallback | Expected | OK for single-Mac |
| **OK** | No `shell=True` / no raw `eval` in client core | Verified | Keep |
| **OK** | Account saves already `chmod 0o600` | Verified | Keep |
| **OK** | Cloud vault uses PBKDF2 200k + Fernet when crypto available | Verified | Prefer always-available crypto lib pin |

---

## Competitive / industry notes (kill switch)

Research consensus (Security.org, Tom’s Guide, PrivacyGuides discussions, pf kill-switch guides):

1. Kill switch should **arm with connect** and **disarm with disconnect** (not a mysterious standalone default).  
2. UI must make **protected vs not** obvious in one glance (green/red + plain English).  
3. On macOS, **pf-based** kill switches are standard for self-hosted stacks; conf files should not live world-readable in `/tmp`.  
4. Users need a clear **Safe Reconnect** path after drops (already in Quick Settings).

---

## Code review (maintainability)

| Item | Note |
|------|------|
| Dual entrypoints | `phantomcloak.py` + `delphi_anti_detection.py` share patterns — long-term: one API module |
| `health_harness.py` ~423 LOC | OK for now; split “checks” vs “heal actions” if growing |
| Dashboard JS ~627 LOC | Command center added; next: module split (status / wizard / accounts) |
| Password hash | Upgrade to Argon2id with migration flag on next account write |

---

## Fixes landed this pass

1. `client/phantomcloak.py` — session save `chmod 0o600` + state dir `0o700`  
2. `client/core/security_audit.py` — expanded checks + **auto-harden** + CLI  
3. Live harden of existing `~/.phantomcloak` sensitive files  

---

## Recommended next security work (priority)

1. Move pf conf from `/tmp` → `~/.phantomcloak/`  
2. Upgrade account password hashing (Argon2id)  
3. On deactivate: force `active=false` in `last_session.json`  
4. Confirm dialog before killswitch arm (CEO safety)  
5. Pin Python deps + optional codesign of `PhantomCloak.app`  

---

## How to re-run

```bash
cd ~/Desktop/PhantomCloak
PYTHONPATH=. python3 -m client.core.security_audit
# or from dashboard: More → Security Audit
```
