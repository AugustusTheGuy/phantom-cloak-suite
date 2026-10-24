# Detection Surface Catalog — PCS Industrial v20260802

**Living document.** Sources: Firecrawl research (Browserleaks, fingerprint technique surveys, Cloudflare residential-proxy ML, ASN/residential reputation notes) + Suite industrial controls.  
**Claim rule:** Fail-closed + defense-in-depth. **Never** market “undetectable by all systems.”

---

## Surfaces → controls

| ID | Surface | Attacker goal | PCS control | Fail-closed? | Owner module |
|----|---------|---------------|-------------|--------------|--------------|
| D01 | WebRTC real IP | Bypass VPN | Camoufox / no unprotected browser; verify guidance | Yes | browser + verify bridge |
| D02 | DNS leak | See ISP resolvers | DoH/DNS via proxy in client config | Yes | client singbox |
| D03 | IPv6 leak | Real IPv6 path | KS / tunnel policy | When required | killswitch |
| D04 | IP ≠ geo claim | Fraud signal | Exit pool in correct country | Ops | inventory v2 |
| D05 | Datacenter ASN / proxy lists | Flag VPN | Prefer ISP/static residential SKUs | Soft score | CEO fleet choice |
| D06 | TLS JA3/JA4 / ALPN | Stack fingerprint | uTLS chrome + Reality | Tune | materialize client |
| D07 | Canvas / WebGL / Audio | Browser FP | Camoufox profile | Profile gate | synthetic profile |
| D08 | Fonts / plugins | Browser FP | Camoufox | Profile gate | synthetic profile |
| D09 | Timezone vs IP | Mismatch | Location tz seed | Profile gate | synthetic profile |
| D10 | Locale / Accept-Language | Mismatch | Locale pack | Profile gate | synthetic profile |
| D11 | Geolocation API | True GPS | Deny/spoof metro | Profile gate | synthetic profile |
| D12 | Screen / HW concurrency | Device FP | Consistent seed | Profile gate | synthetic profile |
| D13 | Cookie / login graph | Link old identity | Wipe trackers before protect | Yes | anti_forensics + vault |
| D14 | Behavioral / residential ML | Bot score | Sticky IP, human pacing | Partial | ops + sticky pool |
| D15 | mDNS / local WebRTC | LAN leak | Hardened browser | Yes | browser |
| D16 | DoH outside tunnel | DNS side path | Force DNS via tunnel | Yes | client route |
| D17 | QUIC / HTTP3 bypass | Off-tunnel | Policy block/tunnel | Config | client |
| D18 | Non-Camoufox Chromium | Extension leaks | Protect path only Camoufox | Yes | app shell |
| D19 | OS STUN outside browser | Real IP | KS + protected apps only | Yes protect mode | killswitch |
| D20 | Bluetooth / AirDrop / LAN | Device adjacency | Hygiene policy (BT off) | Policy | CEO hygiene doc |
| D21 | HTTP/2 Akamai SETTINGS FP | Stack ≠ browser (SETTINGS / WINDOW_UPDATE / PRIORITY / pseudo-header order) | Real browser path only (Camoufox); no raw HTTP clients on protect route; keep H2 profile aligned with uTLS chrome | Yes protect path | browser + materialize client |
| D22 | JA4H HTTP client FP | Header order / method / cookie / Accept-* graph | Camoufox default header stack; synthetic locale packs must match; block non-browser clients | Soft → Yes high-stakes | synthetic profile + browser |
| D23 | UA ↔ TLS/H2 stack mismatch | Chrome UA over non-Chrome ClientHello/H2 | Single stack owner: Camoufox + uTLS chrome only; forbid mixed tooling | Yes | materialize client + app shell |
| D24 | JA4 inter-request signals | Population stats on JA4 (browser_ratio, h2h3_ratio, volume quantile) | Prefer sticky residential/ISP exit + human pacing; avoid rare JA4×IP burst patterns | Partial | ops + sticky pool + client |
| D25 | WebRTC ICE set + gather timing | Fingerprint beyond IP (candidate count/types, mDNS host, STUN RTT) | Disable or force non-leaking WebRTC policy in Camoufox; verify ICE empty/proxy-only; no OS STUN | Yes | browser + verify bridge + killswitch |

---

## Agent 7 delta (2026-08-04) — WebRTC + TLS/JA4 refresh

**Sources (Firecrawl):** `.firecrawl/search-webrtc-leak-2025-2026.json`, `.firecrawl/search-tls-fingerprint-2025-2026.json`, scrapes `blog.cloudflare.com-ja4-signals.md`, `browserless.io-blog-tls-…md`, `github.com-FoxIO-LLC-ja4.md`. Full note: `.firecrawl/AGENT7_WEBRTC_TLS_RESEARCH_v20260804.md`.

**Not appended (already covered or not industrial-new):** plain WebRTC public/local IP leak (D01), mDNS/local candidates (D15), bare JA3/JA4/ALPN (D06), QUIC/H3 off-tunnel (D17), residential behavioral ML (D14). JA3 alone is weakening under Chrome TLS extension-order randomization; keep D06 but treat **JA4 + H2 + UA consistency** as the live industrial bar.

---

## Session pipeline mapping

```
WIPE (D13) → BIND exit pool (D04/D05) → SYNTH profile (D07–D12, D22)
  → GATE leaks+score (D01–D03, D06, D16, D21, D23, D25) → RUN (D24 pacing)
  → VERIFY → on fail TRIP KS
```

---

## Mimicry score (industrial)

Weighted 0–100 (informative, not a warranty):

| Component | Weight |
|-----------|--------|
| Exit IP present + healthy | 25 |
| Profile tz/locale match country | 20 |
| Leak checks pass (IP/DNS/WebRTC policy) | 25 |
| ASN class (isp/residential > datacenter) | 15 |
| FP seed completeness | 15 |

**Threshold default for high-stakes purpose (crypto/streaming):** score ≥ 70 or fail-closed.  
**Browsing default:** score ≥ 55 or warn (configurable).

---

## Honest limits (industrial)

| Area | Limit |
|------|--------|
| Catalog | Defense-in-depth checklist — **not** a warranty of undetectability |
| D01/D15/D25 WebRTC | Full safety needs browser policy + OS UDP STUN control; verify-bridge alone cannot prove no leak if non-Camoufox apps run |
| D06 TLS JA3/JA4 | JA3 unstable under Chrome extension randomization; uTLS “chrome” can lag real Chrome major; edge CDNs retrain continuously |
| D21 HTTP/2 | Camoufox/real browser usually match; any automation/CDP proxy or custom Chromium flags can desync H2 SETTINGS vs marketed Chrome |
| D22 JA4H | Header/cookie graph also shaped by extensions, language packs, and prior cookies — wipe (D13) remains mandatory |
| D23 UA/stack match | Single-stack policy is enforceable in app shell; CEO-installed side browsers void the control |
| D24 JA4 Signals | Global population features (e.g. Cloudflare `browser_ratio_1h`, `h2h3_ratio_1h`) are **outside client control**; only reduce risk via sticky ISP/residential exit, realistic JA4, low burst rate |
| D14/D24 ML | No client can defeat all inter-request / residential fraud models; score is informative |
| Fail-closed | High-stakes purposes must prefer trip-KS over “best effort continue” |

---

## Refresh process

Agent 7 re-runs Firecrawl detection queries monthly or after major browser releases; append new rows; never delete IDs (deprecate with `status: retired`).  
**Last Agent 7 run:** 2026-08-04 — queries: WebRTC leak STUN/ICE 2025/2026; TLS JA3/JA4/JA4H/HTTP2 2025/2026. Catalog IDs through **D25**.
