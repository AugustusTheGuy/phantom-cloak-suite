# Competitive intel, audiences, Core vs Pro

## Target audiences (highest conversion)

### Tier 1 — PhantomCloak Core (personal)
| Segment | Pain points (forums/X/privacy communities) | PCS answer |
|---------|---------------------------------------------|------------|
| **Privacy-first individuals** | DNS/WebRTC leaks; “VPN connected but browser still leaks” | Preflight gate + leak guards + killswitch |
| **Streaming / travel users** | Streaming blocks; public Wi-Fi risk | Purpose wizard + streaming profile + auto-connect scaffold |
| **Crypto / self-custody users** | Trackers, clearnet IP on drop | Killswitch + tracker vault hide/restore |
| **Journalists / activists (lawful)** | Opsec basics, kill switch, honest no-logs | Local-first + trust docs + fail-closed |

### Tier 2 — PhantomCloak Pro (teams / multi-profile)
| Segment | Pain points | PCS answer |
|---------|-------------|------------|
| **Agencies / multi-client ops** | Multilogin cost; profile isolation | Pro seats, RBAC, profile tools (scaffold→live roadmap) |
| **SMB security / remote staff** | Business VPN + audit | Workspaces, audit log, SSO scaffold |
| **Power freelancers** | Need multi-hop, dedicated IP, automation | Multi-hop, residential pool config, API scaffold |

**Note on marketing ethics:** Use brand/founder voice and education. Do **not** fake “customer” sock accounts (platform ToS + FTC). Provide reply templates for real users.

---

## Competitor feature coverage (matrix)

See `shared/pcs_feature_matrix_v20260802.py` and `FEATURE_TRUTH_MATRIX_v20260802.md` for full status (`implemented` | `config_needed` | `scaffold` | `not_started`).

### Personal (Core targets)
NordVPN, Proton VPN Free/Plus, Mullvad, Surfshark, ExpressVPN  
→ tunnels, kill switch, leak protection, threat DNS, multi-device, multi-hop (Pro), obfuscated servers (Core auto-obf), port forward, crypto pay, anonymous signup.

### Industrial (Pro targets)
Multilogin / GoLogin-class multi-profile, Proton Business, generic business VPN / Zero Trust (Cloudflare ZT, Zscaler-class **scaffolds** only)  
→ seats, RBAC, audit, residential pools, cookie/profile import, bulk pipelines, public API, cloud profiles (infra).

---

## FTC-honest product claims

**Allowed:** “Verifies enabled protection layers before marking protected; fails closed with killswitch if a required layer fails.”  
**Not allowed without lab proof:** “100% of data can never leak in any form” as absolute.
