# PhantomCloak dashboard — professional & intuitive UX roadmap

**Sources:** Firecrawl competitive search (Mullvad / Surfshark / Proton-style desktop patterns, kill-switch UX), live dashboard review, deepcheck + code-review  
**Date:** 2026-07-22  

---

## What top VPN UIs do well (apply here)

| Pattern | Why it works | PhantomCloak now |
|---------|----------------|------------------|
| **One primary action** | Connect/Disconnect is unmistakable | **Added** Command Center primary button |
| **One status sentence** | “Protected” vs “Not protected” | **Added** `cc-headline` + green/warn dot |
| **Location always visible** | Reduces mistakes | **Added** Location / Purpose / Kill switch / Security metrics |
| **Kill switch tied to connect** | Industry default (PIA “auto”, Security.org) | Partial — still separate toggle; roadmap: arm with Activate |
| **Short onboarding** | Non-technical users | **Added** 4-step tip under command center |
| **Secondary tools buried** | Audit/verify not competing with Connect | Quick Settings → **More** menu |
| **Quiet polish** | Matte + clear type, not “hacker green rain” | Keep glass purple theme; hero is calmer hierarchy |

---

## Landed this session

1. **Command Center** card (hero): status + metrics + Activate / Turn off / Health+Audit  
2. **Onboarding tip** (how to use in one line)  
3. **LIVE badge** → STANDBY / PROTECTED based on real state  
4. Brand subtitle: “Command Center · Privacy & location protections”  

Restart PhantomCloak (or reload webview) to see UI changes.

---

## Suggested additions (next waves)

### A. Clarity (high value)

1. **Single power control** — while Protected, primary becomes “Change location”; secondary stays “Turn off & restore”  
2. **Confirm dialogs** — arm killswitch / wipe trackers / suite off (plain English risks)  
3. **Empty states** — if no VPS configured, show “Deploy servers” checklist (link to `docs/HOWTO_DEPLOY_AND_VERIFY.md`)  
4. **Last used** — one-tap “Resume Zurich · Browsing” from `last_session.json`  

### B. Professional look

5. **System-native window chrome** — traffic lights only; consistent 12–14pt type scale  
6. **Reduce competing purple CTAs** — one primary blue/green, secondary ghost  
7. **Map or flag + city** large (Mullvad-style) instead of dense badge soup  
8. **Activity toast** — “Kill switch armed”, “Tunnel connected” (2s, bottom)  
9. **Dark matte default** with optional “Quiet mode” (less blob animation for battery)  

### C. Intuitive flows

10. **Wizard progress stepper** with plain labels: Purpose → Country → Confirm protections → Start  
11. **Health strip** — 5 traffic lights only on main (DNS, WebRTC, Kill, Tunnel, IP), expand for Top 30  
12. **Content Platform gated** with illustration of lock → unlock (already partially done)  
13. **Keyboard** — `⌘.` cancel wizard, `⌘Return` activate  

### D. Trust / security UX

14. **Security score chip** in header from `run_audit()`  
15. **Leak test button** primary when Protected (Zero-Leak)  
16. **Never claim “undetectable”** in UI (honest: “protections active · verify recommended”)  

### E. Ops (VPS) surface

17. **Server readiness card** — templates vs configured IPs (green/yellow)  
18. **Pool health** — residential IP latency / reputation from session  

---

## Competitive positioning (honest)

| Product | Strength | PC differentiation |
|---------|----------|-------------------|
| Mullvad | Speed, stability, boring reliability | Purpose-based profiles + Camoufox + local vault |
| Proton / Surfshark | Polished multi-hop UI | Double Onion + tracker vault + Delphi integration |
| Generic VPN | One big Connect | Same, plus health harness & security audit |

PhantomCloak should **feel as simple as Connect/Disconnect** while keeping power tools one level down.

---

## Deepcheck notes for UI code

| Risk | Mitigation |
|------|------------|
| XSS via service names/URLs in `renderServiceCard` | Prefer textContent builders or strict escape |
| `onclick="openService('...')"` quote injection | Escape URLs; avoid string-built handlers |
| Stale LIVE badge | `updateCommandCenter` on every `refreshStatus` |

---

## Verification

```bash
# Restart app to pick up HTML/CSS/JS
open ~/Desktop/PhantomCloak.app
# Security
cd ~/Desktop/PhantomCloak && PYTHONPATH=. python3 -m client.core.security_audit
```
