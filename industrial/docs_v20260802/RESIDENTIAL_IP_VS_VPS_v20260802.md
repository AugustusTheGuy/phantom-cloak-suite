# Residential IP catalog vs VPS tunnel endpoints

## What raises `configured_count`

Client configs under `~/.pcs_industrial_20260802/singbox/*.json` count as **configured** only when they contain a **real public IP (or hostname) of a machine you control** that will run the matching filled server config (VLESS Reality / optional Hysteria2).

That address must come from:

1. **Your VPS provider** (Vultr, Hetzner, Linode, Oracle, DigitalOcean, etc.) after you provision Ubuntu and deploy the filled package, **or**
2. **A commercial endpoint you pay for** with credentials (ISP/static residential product with a host you terminate on), **or**
3. Env/inventory you set explicitly: `vps_inventory.json` / `PCS_VPS_<LOC>`.

## What does **not** work

| Source | Why it fails |
|--------|----------------|
| Random residential IPs from the open web / “proxy lists” | You do not control them; they are not running your sing-box Reality private key |
| Tor exits / TorNet IP lists | Not your Reality servers; wrong protocol stack for this product |
| Demo/UI “residential pool” rows (e.g. Swisscom Fiber mock) | Product UX metadata — not deployable VPS endpoints |
| Your home Starlink IP | Single residential uplink, not multi-geo Reality exits |

Scraping or “farming” third-party residential IPs for tunnel exits is out of scope and not supported.

## Product “residential” story (honest architecture)

- **Exit authenticity** comes from **clean VPS (or purchased static/ISP) IPs in the target city** + Reality SNI mimicry + browser fingerprint — not from stealing residential addresses.
- Optional later: **paid** residential/static ISP providers with official APIs (integrate only with your own account keys).
- UI “residential class / reputation” fields can remain **catalog metadata** after a real exit is owned; they must not invent tunnel destinations.

## HOWTO path (canonical)

See Suite (canonical, read-only): `~/Desktop/PhantomCloak Suite/docs/HOWTO_DEPLOY_AND_VERIFY.md`

1. Provision VPS in target geos  
2. Deploy filled configs from `~/.pcs_industrial_20260802/vps_server_package/`  
3. Put those public IPs in `~/.pcs_industrial_20260802/vps_inventory.json`  
4. Re-run materialize → `configured_count` rises  
5. Verify with Suite verification scripts  

## Inventory template

```bash
nano ~/.pcs_industrial_20260802/vps_inventory.json
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py
```
