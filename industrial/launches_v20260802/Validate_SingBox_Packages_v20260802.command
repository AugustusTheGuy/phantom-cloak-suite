#!/bin/bash
# Validate all industrial sing-box package JSON + client shapes (sing-box check).
# Exits non-zero on any failure. Does not invent VPS IPs or modify Suite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
exec python3 "$ROOT/shared/pcs_validate_singbox_packages_v20260802.py" "$@"
