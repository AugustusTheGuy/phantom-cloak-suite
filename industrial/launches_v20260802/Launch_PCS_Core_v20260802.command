#!/bin/zsh
# New launcher — does not replace Suite Launch Suite (Core demo).command
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export PCS_TIER=core
export PHANTOMCLOAK_TIER=core
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python core_product/pcs_core_app_shell_v20260802.py
fi
exec python3 core_product/pcs_core_app_shell_v20260802.py
