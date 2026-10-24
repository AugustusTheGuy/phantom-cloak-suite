#!/bin/bash
# Deploy all real pool IPs for a location (inventory v2).
# Portable: bash 3.2+ (macOS /bin/bash) — NO mapfile/readarray (bash 4+ only).
# Usage: pcs_deploy_pool_v20260802.sh [--dry-run] <location>
set -euo pipefail

DRY=0
if [ "${1:-}" = "--dry-run" ] || [ "${1:-}" = "-n" ]; then
  DRY=1
  shift
fi
LOC="${1:-}"
if [ -z "$LOC" ]; then
  echo "usage: $0 [--dry-run] <location>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Package root is parent of scripts/ (state package or industrial tree)
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ONE="$SCRIPT_DIR/pcs_deploy_one_v20260802.sh"
if [ ! -f "$ONE" ]; then
  # Fall back to industrial tree scripts
  IND_FALLBACK="${PCS_INDUSTRIAL_ROOT:-$HOME/Desktop/PCS_Industrial_20260802}"
  ONE="$IND_FALLBACK/server_vps_package_v20260802/scripts/pcs_deploy_one_v20260802.sh"
fi
if [ ! -f "$ONE" ]; then
  echo "pcs_deploy_one not found (looked under $SCRIPT_DIR and industrial tree)" >&2
  exit 1
fi

IND="${PCS_INDUSTRIAL_ROOT:-$HOME/Desktop/PCS_Industrial_20260802}"
export PYTHONPATH="$IND${PYTHONPATH:+:$PYTHONPATH}"

TMP_LIST="$(mktemp "${TMPDIR:-/tmp}/pcs_pool.XXXXXX")"
# shellcheck disable=SC2064
trap 'rm -f "$TMP_LIST"' EXIT HUP INT TERM

# List user@ip lines for this location (inventory v2 pool members only)
python3 - <<PY >"$TMP_LIST"
from shared.pcs_inventory_v2_v20260802 import load_inventory, iter_pool_members
loc = """$LOC"""
members = [m for m in iter_pool_members(load_inventory()) if m["location"] == loc]
for m in members:
    print("%s@%s" % (m["ssh_user"], m["ip"]))
PY

COUNT=0
# Portable line loop (bash 3.2): never use mapfile/readarray
while IFS= read -r target || [ -n "${target:-}" ]; do
  [ -z "${target:-}" ] && continue
  COUNT=$((COUNT + 1))
  echo "=== $target ==="
  if [ "$DRY" = "1" ]; then
    bash "$ONE" --dry-run "$target" "$LOC" || true
  else
    bash "$ONE" "$target" "$LOC"
  fi
done < "$TMP_LIST"

if [ "$COUNT" -eq 0 ]; then
  echo "No real pool IPs for location=$LOC — set inventory v2 pool first." >&2
  echo "  python3 shared/pcs_inventory_wizard_v20260802.py --set-pool ${LOC}=x.x.x.x,..." >&2
  exit 3
fi

echo "POOL_DEPLOY_DONE location=$LOC count=$COUNT dry=$DRY"
