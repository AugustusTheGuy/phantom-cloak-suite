# Security: secret storage & VPN credential lifecycle

**Build:** PCS Industrial `20260802`  
**Scope:** macOS developer machine + industrial state under `~/.pcs_industrial_20260802/`  
**Code tree:** `~/Desktop/PCS_Industrial_20260802` (no secrets in git)

---

## Where secrets live (source of truth)

| Path | Contents | Expected mode |
|------|----------|---------------|
| `~/.pcs_industrial_20260802/` | Industrial runtime state root | `0700` |
| `…/secrets/location_keys.json` | Per-location UUID, Reality **private**/public keys, hy2/obfs passwords | file `0600`, parent dirs `0700` |
| `…/secrets/hy2_certs/<loc>/` | Self-signed TLS `fullchain.pem` + `privkey.pem` for Hysteria2 | files `0600`, dirs `0700` |
| `…/vps_server_package/` | **Filled** server configs (embed Reality private key + hy2 passwords) + cert copies | dirs `0700`, files `0600` |
| `…/singbox/<loc>.json` | Client configs (uuid, public_key, hy2 password when IP set) | `0600`, dir `0700` |
| `…/singbox/<loc>.pending.json` | **Public only** (hard allowlist; includes `schema_version`) — never `private_key` / `hy2_password` / `password` | `0600` |
| `…/vps_inventory.json` | VPS IPs / ssh user (not crypto keys; still sensitive ops data) | `0600` |
| `…/materialize_meta.json` | Paths, counts, `secrets_fingerprint` — **no private key values** | `0600` |

**Never store** `location_keys.json`, filled server packages, or PEMs inside the Desktop industrial git tree.

---

## Permission policy

On every materialize run, `harden_secret_paths()` enforces:

- State root, `secrets/`, `hy2_certs/**`, `vps_server_package/**` → directories `0700`
- Secret-bearing files → `0600`
- Deploy script → `0700`

Manual repair:

```bash
chmod 700 ~/.pcs_industrial_20260802
chmod -R go-rwx ~/.pcs_industrial_20260802/secrets
chmod -R go-rwx ~/.pcs_industrial_20260802/vps_server_package
find ~/.pcs_industrial_20260802/secrets -type f -exec chmod 600 {} \;
find ~/.pcs_industrial_20260802/vps_server_package -type f -exec chmod 600 {} \;
```

---

## Backup & sync risk (macOS)

| Risk | Observation | Mitigation |
|------|-------------|------------|
| **Time Machine** | State under `~/.pcs_industrial_20260802` is often **Included** by default | `sudo tmutil addexclusion ~/.pcs_industrial_20260802` (or exclude `secrets` + `vps_server_package`) |
| **iCloud Desktop** | Industrial **code** on Desktop may sync; secrets should **not** live there | Keep secrets only under `~/.pcs_industrial_…`; never copy PEMs into Desktop tree |
| **Local snapshots / cloud backup tools** | Third-party backup can copy `~` wholesale | Exclude state dir; prefer encrypted volume for ops secrets |
| **World-readable parent dirs** | `secrets/` once `0755` allows listing even if files are `0600` | Materializer locks dirs to `0700` |

---

## Logging / stdout rules

| Surface | Allowed | Forbidden |
|---------|---------|-----------|
| Materialize stdout / `materialize_meta.json` | paths, counts, `secrets_fingerprint`, public inventory status | `private_key`, `hy2_password`, `obfs_password`, PEM bodies |
| Readiness `scan_readiness()` / CLI | summary, counts, pending uuid/public_key, fingerprint, age | raw private keys, passwords, file body dumps of server JSON |
| Exceptions | short type/message | sing-box keypair stdout, openssl PEM text |
| `*.pending.json` | allowlist below (must include `schema_version`) | `private_key`, `hy2_password`, `password`, any secret |

### `*.pending.json` public allowlist (`PENDING_PUBLIC_KEYS`)

Canonical definition: `shared/pcs_client_singbox_v20260802.py`.

| Key | Notes |
|-----|--------|
| `schema` | `"pcs.client.pending"` |
| `schema_version` | int — documents pending sidecar shape (currently `2`) |
| `location`, `aliases`, `status`, `configured` | ops identity |
| `uuid`, `public_key`, `short_id`, `sni` | client-public Reality material |
| `hy2`, `transport_http`, `flow`, `ports`, `client_shape` | shape flags (not secrets) |
| `inventory_path`, `skip_reason`, `hint`, `caveats` | operator guidance |
| `not_a_singbox_config`, `written_as`, `alias_of`, `schema_errors` | sidecar meta |

**Forbidden in pending:** `private_key`, `hy2_password`, `obfs_password`, `password`, and any `*_password` / `*_private_key`.

Writers: `build_pending_sidecar` → `filter_pending_public` → `pending_public_only` → `write_pending_json`.  
Sanitize: `sanitize_pending_sidecars()` (also via `harden_secret_paths()`).  
Readiness: `_pending_public_meta` surfaces only public subset (includes `schema_version`).  
**Multi-IP:** `filter_pending_public` deep-scrubs nested dicts under allowlisted parents (e.g. `client_shape`, `ports`) so pool payloads cannot smuggle `private_key` / `*_password`. Full client JSON never embeds Reality `private_key` (public_key only). Inventory v2 `save_inventory` is atomic mode `0600`.

Implementation:

- `shared/pcs_client_singbox_v20260802.py` — `PENDING_PUBLIC_KEYS`, `filter_pending_public`, `build_pending_sidecar`
- `shared/pcs_materialize_singbox_v20260802.py` — `pending_public_only`, `write_pending_json`, `sanitize_pending_sidecars`, `redact_secrets`
- `shared/pcs_server_readiness_v20260802.py` — `_redact_for_stdout`, `_pending_public_meta`

---

## `secrets_fingerprint` (inventory debugging)

Public-material hash for comparing machines / detecting unexpected rotation **without** exposing private keys.

- **Algorithm:** SHA-256  
- **Hashed fields (per location, sorted):** `uuid`, `public_key`, `short_id`, `sni`  
- **Not hashed:** `private_key`, `hy2_password`, `obfs_password`  
- **Outputs:** `secrets_fingerprint` (16 hex chars) and `secrets_fingerprint_full` (64 hex)

```bash
python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_materialize_singbox_v20260802.py --check-only --json \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('secrets_fingerprint'), d.get('secrets_age'))"

python3 ~/Desktop/PCS_Industrial_20260802/shared/pcs_server_readiness_v20260802.py \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['summary'])"
```

---

## Optional secrets age check

`secrets_age` reports age of `location_keys.json` from `created_at` (fallback: mtime).

- Default `max_days=365` → `stale: true` when older  
- Rotation:  
  `python3 …/pcs_materialize_singbox_v20260802.py --rotate-keys`  
  (optionally `--location dubai`)

After rotation, redeploy **server** packages and refresh **client** configs for affected locations.

---

## Credential lifecycle

1. **Create** — first materialize generates Reality keypairs + hy2 passwords; writes `location_keys.json` (`0600`).  
2. **Preserve** — re-runs keep keys unless `--rotate-keys`.  
3. **Materialize server** — private keys written only into `vps_server_package/` (local, mode-locked).  
4. **Client** — written only when inventory has a real public IP; pending sidecars stay public-only.  
5. **Deploy** — `deploy_filled_to_vps.sh` scp’s filled configs over SSH; fix remote perms (`chmod 600` certs).  
6. **Rotate** — `--rotate-keys` → new uuid/keypair/hy2 password → re-materialize → re-scp → update clients.  
7. **Retire** — shred/delete location entry + VPS package files + remote `/etc/sing-box` config; rotate remaining sites if shared.

---

## Git / tree hygiene

- `.gitignore` at industrial root ignores secrets patterns, PEMs, inventories, pending JSON, and accidental `.pcs_industrial_*` dumps.  
- Templates under `server_vps_package_v20260802/templates_source_copy/` may contain **placeholders only** (`REPLACE_*`) — never filled keys.  
- If a secret is ever committed: rotate all affected keys immediately; purge git history; treat as compromised.

---

## State note

See also: `STATE_NOTE_v20260802.md` in this docs folder (runtime path, do-not-commit, backup exclusions).

---

## Audit checklist (operator)

- [ ] `ls -la ~/.pcs_industrial_20260802/secrets` → dir `drwx------`, `location_keys.json` `-rw-------`  
- [ ] `tmutil isexcluded ~/.pcs_industrial_20260802` → prefer `[Excluded]`  
- [ ] Materialize / readiness stdout has **no** long base64 private keys or hy2 passwords  
- [ ] `*.pending.json` keys ⊆ `PENDING_PUBLIC_KEYS` (includes `schema_version`); no `private_key` / `hy2_password` / `password`  
- [ ] `secrets_fingerprint` present and stable across no-op re-runs  
- [ ] Industrial tree has no `*.pem` / `location_keys.json` under Desktop path  
- [ ] `.gitignore` present before any `git init` / remote push  

---

## Related modules

- `shared/pcs_materialize_singbox_v20260802.py`  
- `shared/pcs_server_readiness_v20260802.py`  
- `HOWTO_DEPLOY_LINK_v20260802.md` (same folder)  
- `VPS_MATERIALIZE_STATUS_v20260802.md` (same folder)  
- `INDEX_v20260802.md` (docs control plane SoT map)  
