# Code review + security audit — PCS Industrial 20260802

**Scope:** New tree only (`~/Desktop/PCS_Industrial_20260802`) + **read-only** glance at Suite.  
**Originals not modified:** `~/Desktop/PhantomCloak`, `~/Desktop/PhantomCloak Suite`.  
**Workflow:** `/security_audit` → `~/.grok/workflows/security_audit.rhai` (designer + pentester + judge).

---

## Executive summary

| Item | Result |
|------|--------|
| New industrial modules | Fail-closed preflight + killswitch trip on any failed enabled layer |
| Legacy activate risk | Suite still can set “verified” optimistically — **do not use for production claims** until wired to Industrial gate |
| Demo credentials | Suite generates placeholder sing-box configs — **ops blocker** |
| State isolation | Industrial uses `~/.pcs_industrial_20260802/` |
| Grade (engine scan) | Run `python3 -m shared.pcs_security_audit_engine_v20260802` |

---

## High / medium findings (designer + pentester)

| Sev | Finding | Fix in Industrial tree |
|-----|---------|-------------------------|
| High | Broadcast before full layer verify (legacy) | `pcs_preflight_obfuscation_gate_v20260802` arms KS first, then verifies |
| High | Marketing absolute “zero leak forever” | FTC doc + honest UI copy |
| Med | SHA-256 account passwords in Suite | Keep Suite; plan Argon2id in future *new* hash module only |
| Med | pf conf under `/tmp` in Suite killswitch | Recommend new conf path in future `pcs_killswitch_conf_v*` (not written over) |
| Med | `rm -rf` anti_forensics | Confirm dialogs; dry-run default |
| Med | Dual trees (phantomcloak + delphi_anti_detection) | Industrial single pipeline API |
| Low | Stale session active flags | Core/Pro launchers don’t restore “active” without preflight |

---

## Deepcheck on new activation path

1. Arm killswitch  
2. Select obfuscation method  
3. Verify **all enabled** layers (incl. tracker vault if user enabled)  
4. On fail → trip killswitch; `protected=false`  
5. On pass → `protected=true` + continue monitor  

Tests: `tests_v20260802/test_pcs_preflight_gate_v20260802.py`

---

## How to re-run triad workflow

```
/security_audit
```
or workflow tool with `name: security_audit` and optional  
`args: { industrial_root, suite_root }`
