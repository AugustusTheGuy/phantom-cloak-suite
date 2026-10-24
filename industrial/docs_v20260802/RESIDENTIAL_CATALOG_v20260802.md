# Residential product catalog vs VPS tunnel endpoints

**Module:** `shared/pcs_residential_pool_industrial_v20260802.py`  
**On-disk pools:** `~/.pcs_industrial_20260802/residential_pools/`  
**Schema:** compatible with Suite `client/core/residential_pool.py` (do not overwrite Suite).

## What this catalog is

- A **synthetic product catalog** for UI selection, ranking demos, latency/ISP mimicry fields, and operator UX.
- Target size: **30–50 entries per country** in `COUNTRY_TO_LOCATION` (default **45**).
- Each entry is stamped with:
  - `catalog_kind`: `synthetic_product_catalog_v20260802`
  - `not_a_tunnel_endpoint`: `true`
  - `source`: `pcs_industrial_residential_catalog`
- IPs are **deterministic synthetic addresses** (region-seeded octets). They are **not** scraped residential proxies and **not** owned VPS public IPs.

## What this catalog is not

| Not this | Why |
|----------|-----|
| Live tunnel / sing-box endpoints | Reality/Hysteria exits need machines you control |
| Input to `configured_count` | Readiness only counts client configs with real inventory IPs |
| Proxy-list scrape / farm | Unsupported and out of product scope |
| Drop-in for `vps_inventory.json` | Inventory must list **your** VPS (or paid static/ISP) hosts |

**Do not** mark server readiness `configured_count` from residential catalog IPs.

## How it differs from VPS path

| Concern | Residential catalog | VPS / tunnel path |
|---------|---------------------|-------------------|
| Purpose | Product UX / selection metadata | Actual protected egress |
| Storage | `~/.pcs_industrial_20260802/residential_pools/*.json` | `vps_inventory.json` + `singbox/*.json` |
| Raises `configured_count`? | **No** | **Yes** (after materialize with real IPs) |
| Who owns the IP? | Nobody (synthetic) | You / your provider |

Canonical operator path for real tunnels:

1. Provision VPS in target geos  
2. Deploy filled packages from `~/.pcs_industrial_20260802/vps_server_package/`  
3. Set public IPs in `~/.pcs_industrial_20260802/vps_inventory.json`  
4. Run `shared/pcs_materialize_singbox_v20260802.py`  
5. Confirm with `shared/pcs_server_readiness_v20260802.py`  

See also: `RESIDENTIAL_IP_VS_VPS_v20260802.md`, `HOWTO_DEPLOY_LINK_v20260802.md`, `INCIDENT_CONFIGURED_COUNT_ZERO_v20260802.md`.

## Generate / refresh catalog

```bash
# Full catalog (all COUNTRY_TO_LOCATION keys), 45 entries each
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_residential_pool_industrial_v20260802.py --size 45 --json

# Subset
python3 .../pcs_residential_pool_industrial_v20260802.py --size 40 --countries CH DE AE
```

Writes:

- One `CC.json` per country (mode `0600`)
- `_catalog_meta.json` summary (`countries`, `total_entries`, note)

## Shell wiring (industrial app shell)

`core_product/pcs_app_shell_v20260802.py`:

- **Prefers** industrial `get_pool` / `COUNTRY_TO_LOCATION` when the industrial module imports cleanly.
- **Falls back** to Suite `client.core.residential_pool` if industrial is unavailable.
- Does **not** overwrite Suite `residential_pool.py`.
- Catalog selection failure does not block activate preflight (catalog is optional UX metadata).

## Honest product story

- **Exit authenticity** comes from clean VPS (or purchased static/ISP) IPs + Reality SNI mimicry + browser fingerprint — not from inventing residential destinations as tunnels.
- UI “residential class / reputation / ISP brand” fields are **catalog metadata** for product UX.
- Optional later: paid residential/static ISP providers via official APIs (your own account keys only).
