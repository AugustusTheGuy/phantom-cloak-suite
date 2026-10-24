# VPS materialize status

- Templates copied from Suite: 8
- Server package: `~/.pcs_industrial_20260802/vps_server_package`
- Client dir: `~/.pcs_industrial_20260802/singbox`
- Clients written (real IP, schema OK): 0
- Pending IP: dubai, hongkong, vancouver, germany, bahamas, cayman, mauritius, seychelles
- Schema failures: (none)
- Keys rotated: (none)
- short_id healed: (none)
- Inventory: `~/.pcs_industrial_20260802/vps_inventory.json`
- germany alias: frankfurt

## Client config caveats

- TUN inbound needs root/admin on macOS (interface create + auto_route/strict_route).
- Hysteria2 uses industrial self-signed certs: client tls.insecure=true (not public CA).
- clash_api disabled by default; enable only on loopback with a secret if needed.
- Private/LAN traffic bypasses proxy via route rule ip_is_private → direct.
- Kill-switch is separate (pf under ~/.pcs_industrial_20260802/pf_rules/), not sing-box alone.
- sing-box 1.12+: no geosite/geoip; sniff via route action, not inbound fields.

Re-run:

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py --check-only --json
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py --location dubai
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py --rotate-keys --location dubai
PCS_SINGBOX_CHECK=1 python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py --location dubai
python3 -c "from pcs_server_readiness_v20260802 import scan_readiness; import json; print(json.dumps(scan_readiness(), indent=2))"
```
