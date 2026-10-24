# Industrial state note

**Runtime state (secrets + generated configs) is outside the product tree:**

```text
~/.pcs_industrial_20260802/
  secrets/                 # location_keys.json, hy2_certs/  (0700 / 0600)
  vps_server_package/      # filled server JSON + certs for scp
  singbox/                 # client JSON + *.pending.json (public uuid/public_key only)
  vps_inventory.json       # VPS IPs (set by operator)
  materialize_meta.json    # paths/counts/fingerprint — no private keys
  accounts/ payments/ pf_rules/ …
```

**Product / code tree (safe to version with care):**

```text
~/Desktop/PCS_Industrial_20260802/
```

- Do **not** copy `secrets/` or filled `vps_server_package/` into the Desktop tree.  
- `.gitignore` blocks accidental secret commits.  
- Prefer Time Machine / cloud **exclusion** of `~/.pcs_industrial_20260802`.  
- Security detail: `SECURITY_SECRETS_v20260802.md`.
