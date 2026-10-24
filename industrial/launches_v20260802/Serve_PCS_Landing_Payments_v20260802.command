#!/bin/zsh
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
PORT="${1:-8787}"
echo "Landing + payments: http://127.0.0.1:${PORT}/"
if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments "$PORT"
fi
exec python3 core_product/pcs_app_shell_v20260802.py --serve-payments "$PORT"
