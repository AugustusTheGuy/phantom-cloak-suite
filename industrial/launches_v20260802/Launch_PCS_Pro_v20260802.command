#!/bin/zsh
# New launcher — does not replace Suite Launch Suite (Pro demo).command
cd "$(dirname "$0")/.."
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export PCS_TIER=pro
export PHANTOMCLOAK_TIER=pro
exec python3 pro_product/pcs_pro_launcher_v20260802.py
