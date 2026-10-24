# Protect / Activate Gate Order (PCS Industrial v20260802)

**Fail-closed bar:** Signal/WireGuard ops rigor. Never claim `protected=True` if any gate fails.  
**Scope:** Industrial tree only. Suite killswitch paths (`/tmp/delphi_killswitch.pf.conf`) are **unchanged** and **unused** by this pipeline.  
**PF rules:** always under `~/.pcs_industrial_20260802/pf_rules/` — never `/tmp`.

---

## Canonical order

```
                    PROTECT / ACTIVATE ENTRY
                              │
                              ▼
              ┌───────────────────────────────┐
              │ 1. readiness_servers          │
              │    require_configured_servers │
              │    ok_for_protect ⇔           │
              │      configured_count > 0     │
              └───────────────┬───────────────┘
                              │
                 fail ────────┤──────── success
                    │         │
                    ▼         ▼
           BLOCKED            ┌───────────────────────────────┐
           reason=            │ 2. optional_wipe              │
           servers_not_       │    wipe_fn if Suite           │
           configured         │    anti_forensics available   │
           arm_result=None    │    else wipe_done=False       │
           gate_stopped_at=   │    wipe error → wipe_failed   │
           readiness_servers  └───────────────┬───────────────┘
                                              │
                                 fail ────────┤──────── success (recorded)
                                    │         │
                                    ▼         ▼
                           BLOCKED            ┌───────────────────────────────┐
                           reason=            │ 3. synthetic_profile          │
                           wipe_failed        │    if exit_ip known AND       │
                           gate_stopped_at=   │    score/gate fails → block   │
                           optional_wipe      │    if exit_ip unknown → skip  │
                                              └───────────────┬───────────────┘
                                                              │
                                                 fail ────────┤──────── success
                                                    │         │
                                                    ▼         ▼
                                           BLOCKED            ┌───────────────────────────────┐
                                           reason=            │ 4. obfuscation_preflight      │
                                           synthetic_         │    method select + zeroleak   │
                                           profile_gate_      │    layers (no killswitch arm) │
                                           failed             │    vault / DNS / webrtc / …   │
                                           gate_stopped_at=   └───────────────┬───────────────┘
                                           synthetic_profile                  │
                                                                 fail ────────┤──────── success
                                                                    │         │
                                                                    ▼         ▼
                                                           BLOCKED            ┌───────────────────────────────┐
                                                           reason=            │ 5. killswitch_arm             │
                                                           preflight_failed   │    single arm only            │
                                                           arm_result=None    │    industrial pf_rules conf   │
                                                           gate_stopped_at=   │    dry_run | armed            │
                                                           obfuscation_       └───────────────┬───────────────┘
                                                           preflight                          │
                                                                                 fail ────────┤──────── success
                                                                                    │         │
                                                                                    ▼         ▼
                                                                           BLOCKED            ┌───────────────────────────────┐
                                                                           reason=            │ 6. final_layer_verify         │
                                                                           killswitch_        │    layers include             │
                                                                           arm_failed         │    killswitch_armed=True      │
                                                                           gate_stopped_at=   └───────────────┬───────────────┘
                                                                           killswitch_arm                     │
                                                                                                 fail ────────┤──────── success
                                                                                                    │         │
                                                                                                    ▼         ▼
                                                                                           BLOCKED         PROTECTED
                                                                                           reason=         status=protected
                                                                                           preflight_      protected=True
                                                                                           failed          all gates_passed
```

### Phase literals (code + tests)

| Phase | `gate_stopped_at` / `gates_passed` value |
|-------|------------------------------------------|
| 1 | `readiness_servers` |
| 2 | `optional_wipe` |
| 3 | `synthetic_profile` |
| 4 | `obfuscation_preflight` |
| 5 | `killswitch_arm` |
| 6 | `final_layer_verify` |

Module: `shared/pcs_preflight_obfuscation_gate_v20260802.py`  
Constants: `CANONICAL_GATE_ORDER`, `GATE_READINESS`, `GATE_WIPE`, `GATE_SYNTHETIC`, `GATE_OBFUSCATION`, `GATE_KILLSWITCH`, `GATE_FINAL`.

Synthetic profile: `shared/pcs_synthetic_profile_v20260802.py` (`build_profile_seed` / `gate_profile` / `score_mimicry`).

---

## Rules (non-negotiable)

1. **Readiness first**  
   `require_configured_servers=True` (default) on every real activate entrypoint.  
   `ok_for_protect` is true only when `configured_count > 0` (live scan or explicit `readiness_override` for tests).  
   No invented production IPs. Wipe / synthetic / arm **must not run** when readiness blocks.

2. **Optional wipe**  
   Call `wipe_fn` when Suite `anti_forensics` is available (app shell injects `deep_clean_on_start`).  
   If not available → record `wipe_done=False` and continue (not a hard error by itself).  
   If wipe_fn is provided and raises / reports `ok=False` → `reason=wipe_failed` (fail-closed).

3. **Synthetic profile gate**  
   If `exit_ip` is **known** and mimicry `pass_gate` fails (score/threshold/wipe/exit) → block protect  
   (`reason=synthetic_profile_gate_failed`).  
   If `exit_ip` is **unknown** → do **not** block on this gate (skip applied; telemetry only).

4. **Obfuscation preflight before arm**  
   Method selection + `enforce_or_kill` layer map **without** `killswitch_armed`.  
   If this fails → `arm_result is None` (killswitch is **not** armed for this activate).

5. **Killswitch arm once**  
   Either `killswitch_arm_fn` **or** `auto_arm_killswitch` industrial path — never both.  
   App shell sets `auto_arm_killswitch=False` when providing `killswitch_arm_fn`.  
   Industrial conf: `~/.pcs_industrial_20260802/pf_rules/pcs_killswitch_v20260802.pf.conf`.  
   `interpret_arm_result` is fail-closed (`error` / missing armed signal → not protected).

6. **Never claim protected if any fail**  
   All blocked payloads share: `status=blocked`, `protected=False`, `reason`, `message`,  
   `gate_order`, `gates_passed`, `gate_stopped_at`, readiness counts, `wipe_done`.

7. **Status / dashboard / wizard**  
   Always allowed. Only **protect/activate** is gated.

---

## Entrypoints (must keep order)

| Entrypoint | Notes |
|------------|--------|
| `core_product/pcs_app_shell_v20260802.py` → `activate()` | `require_configured_servers=True`, wipe_fn from Suite, single arm via `arm_for_activate` |
| `core_product/pcs_core_app_shell_v20260802.py` | `require_configured_servers=True` |
| `core_product/pcs_core_launcher_v20260802.py` | demo arm fn + servers gate |
| `pro_product/pcs_pro_launcher_v20260802.py` | same gate; pro tier layers |

---

## Modules

| Module | Role |
|--------|------|
| `pcs_server_readiness_v20260802` | `scan_readiness` / `gate_snapshot` / `ok_for_protect` |
| `pcs_preflight_obfuscation_gate_v20260802` | ordered activate pipeline |
| `pcs_synthetic_profile_v20260802` | seed + mimicry score + `gate_profile` |
| `pcs_zeroleak_gate_v20260802` | `run_preflight` / `enforce_or_kill` |
| `pcs_killswitch_industrial_v20260802` | arm/disarm; `pf_rules/` only |

---

## Tests

```bash
cd ~/Desktop/PCS_Industrial_20260802
.venv/bin/python -m pytest tests_v20260802/test_pcs_preflight_gate_v20260802.py -v
```

Coverage includes:

- readiness fail → no wipe, no arm, `gate_stopped_at=readiness_servers`
- wipe fail → no arm, `gate_stopped_at=optional_wipe`
- exit_ip known + score fail → `gate_stopped_at=synthetic_profile`, no arm
- exit_ip unknown → synthetic does not block
- obfuscation fail after readiness/wipe/synth → no arm, `gate_stopped_at=obfuscation_preflight`
- arm error → not protected, `gate_stopped_at=killswitch_arm`
- industrial PF path never under `/tmp`
- live `configured_count==0` → fail-closed without inventing IPs

---

## Operator note

When blocked with `servers_not_configured`: fill owned VPS public IPs in  
`~/.pcs_industrial_20260802/vps_inventory.json`, re-run materialize, re-check readiness.  
See `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md` and `CEO_VPS_RUNBOOK_v20260802.md`.
