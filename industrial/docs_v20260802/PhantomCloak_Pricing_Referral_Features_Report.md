# PhantomCloak — Pricing, Referral & Feature-Build Report (Fable 5 pass)

## 1. Pricing (updated as requested)
- **Pro: $39/mo** founder rate (frame as rising to $59+ as cloud/RPA ship).
- **Pro annual: $29/mo billed yearly (~26% off)** — deliberately a *shallower* discount than Core's (~58% off), because business buyers are less price-elastic and pay for reliability, not discounts.
- **Core unchanged:** $4.99/mo annual, $11.99 monthly.
- Week-one math at $39: **~26 Pro sales = $1,000**.

**Verification — do businesses pay more?** Yes: current sources confirm B2B "willingness to pay premium prices for tools that save time and reduce risk," and that **security specifically commands premium pricing** because a breach dwarfs prevention cost. So a shallow annual discount on Pro sacrifices little conversion while protecting margin and the price anchor.

**Verification — is PhantomCloak the "most expansive"?** **Not today** — the gap analysis shows it currently lacks several competitor features. **With the roadmap, yes it becomes uniquely broad** — very few products combine a full consumer VPN + prosumer antidetect/workspace toolkit + honest billing + verified kill switch in one. Market this as the vision/roadmap, **not** as a present-day fact.

## 2. Referral — re-proposed with the low-LTV problem solved (now coded)
The fix that converts the con into a benefit: **gate the reward on RETENTION, not signup.** Implemented in `referrals.py` and verified:
- Reward releases only after **(a)** the friend's first successful charge, **(b)** the refund window closes, and **(c)** the friend is still active at day 8. → You only ever pay for referrals that became **real, retained, paying** customers. This structurally eliminates low-LTV payouts.
- **Account credit, not cash** (kills cash-out rings); **fixed 1-month credit, not a perpetual discount** (protects the anchor); friend gets **30% off month one** (lifts conversion); **per-account monthly cap (10)**; **device/payment fingerprint** blocks self-referral.
- **Con → benefit:** because payout requires retention, the program *selects for* high-LTV customers and rewards your best users for bringing similar ones — the referral budget becomes a retention-quality filter. Verified: refunded / in-window / churned referrals are correctly denied.

## 3. What was coded this pass + verification
| Module | Tier | Status | Verified |
|---|---|---|---|
| `feature_registry.py` (authority: 20 features) | — | live | ✅ 5 live / 5 config / 7 scaffold / 3 infra |
| `tier.py` (extended keys) | both | live | ✅ gating correct (cookie_import Pro-only) |
| `referrals.py` | Core | **live** | ✅ eligibility/refund/hold logic |
| `dns_blocklists.py` | Core | **live** | ✅ add/remove/stats |
| `rbac.py` (Team Workspaces & Roles) | Pro | **live** | ✅ deny-by-default, per-workspace |
| `obfuscation.py` (auto-select surface) | Core | config | ✅ DPI→REALITY, blocked→QUIC |

**Honest status of every requested feature** lives in `feature_registry.py`:
- **Live now:** kill switch, entitlement gate, DNS blocklists, referrals, RBAC roles.
- **Config (interface ready, needs backend):** auto-obfuscation, anonymous signup, crypto payments, multi-hop, residential pool.
- **Scaffold (interface, core impl to build):** port forwarding, speed accelerator, adaptive anti-DPI, cookie import, multi-window sync, bulk pipelines, public API.
- **Infra (server/funded, not code-only):** GPS spoofing (mobile), no-code RPA, cloud profiles.

## 4. "sing-box supports Reality/obfs — surface + auto-select + QUIC" explained
Your VPN backend is **sing-box**, which already speaks several stealth transports: **REALITY** (disguises traffic as normal HTTPS to a real site), **QUIC/HTTP-3**, **ShadowTLS**, **WebSocket-over-TLS**, and **obfs** scrambling. "**Surface**" = expose these in the UI and show which is active (transparency competitors hide). "**Auto-select**" = pick the best for current network (`obfuscation.py`: DPI→REALITY, blocked→QUIC). "**QUIC**" = add HTTP/3 so traffic blends with modern web. That's the honest version of "adaptive anti-DPI": config + auto-select now; a true ML-adaptive detector is the scaffolded upgrade.

## 5. AWS exit-server capacity — honest estimate
WireGuard is very efficient; capacity is **bandwidth-bound, not connection-bound**. Planning ballpark (assumptions, not a benchmark):
- A modest instance (t3.small/medium) holds thousands of idle/light connections; the real limit is concurrent *active* throughput.
- If an active user pulls ~2–5 Mbps and the instance NIC does ~1–5 Gbps, one instance serves ~**200–1,000 concurrently-active** users. Since typical concurrency is 5–15%, that's roughly **~1,000–5,000 subscribers per modest instance** ($30–70/mo), scaling horizontally behind a load balancer beyond that.
- **Caveat:** real numbers require load-testing your actual sing-box config — I can't measure it here. Also note: obfuscation runs **on-device (client)**, but VPN **exit servers are cloud** — those are the capacity constraint.

## 6. Diskless / RAM-only — legitimate interim path
Verified viable now: run the exit-server OS **read-only with tmpfs (RAM) for all writable paths + overlayfs, no swap, remote logging off** — precedent: **Tor-ramdisk**, **Mullvad stboot**. Gives a real "nothing persists to disk" property as an interim measure before a full diskless-boot build. It's **server ops (image build), not client code.** Until actually deployed, **do not claim RAM-only on the landing page.**

## 7. On naming the feature "Multilogin" — I recommend against it
Naming your own feature after a competitor's brand ("Multilogin") misuses a likely trademark: infringement exposure, ad/app-store rejection risk, and it trains users to associate your value with *their* name. The legitimate way to capture that search intent: a **"PhantomCloak vs Multilogin" comparison page** targeting the keyword in content/meta — ranks for their brand searches without misusing the mark. Internally the feature is **"Team Workspaces & Roles."**

## 8. Landing-claims guardrail (flag for Batch 2)
The landing page lists Pro features (multi-hop, obfuscation, residential IP, workspaces) as available, but per the registry only some are `live`. Before launch, gate the page's feature list to `live` status or label roadmap items "coming soon." I'll fix this in the Batch 2 copy polish so nothing overclaims.
