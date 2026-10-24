#!/bin/zsh
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export PCS_TIER="${PCS_TIER:-core}"
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python core_product/pcs_app_shell_v20260802.py --status
fi
exec python3 core_product/pcs_app_shell_v20260802.py --status
