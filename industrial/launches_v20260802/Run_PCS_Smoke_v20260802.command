#!/bin/zsh
# PCS Industrial fail-closed smoke harness (v20260802).
# Industrial tree only — does not modify Suite/PhantomCloak originals.
# Writes CEO JSON to ~/.pcs_industrial_20260802/smoke_reports/latest.json
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}:${PYTHONPATH:-}"
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

if [ -x "${ROOT}/.venv/bin/python" ]; then
  exec "${ROOT}/.venv/bin/python" "${ROOT}/shared/pcs_smoke_industrial_v20260802.py" "$@"
fi
exec python3 "${ROOT}/shared/pcs_smoke_industrial_v20260802.py" "$@"
