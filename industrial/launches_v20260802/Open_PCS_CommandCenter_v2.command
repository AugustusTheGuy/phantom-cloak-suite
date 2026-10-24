#!/bin/zsh
# Industrial Command Center v2 — serves dashboards_v20260802 + /api/status
# Does not open or modify Suite dashboards.
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export PCS_TIER="${PCS_TIER:-core}"
PORT="${PCS_DASHBOARD_PORT:-8790}"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="python3"
fi

echo "PCS Industrial Command Center v2"
echo "  http://127.0.0.1:${PORT}/"
echo "  GET /api/status  (readiness · protect_gate · residential counts)"
echo "  Suite not required for status."
exec "$PY" core_product/pcs_dashboard_server_v20260802.py --port "$PORT" --open
