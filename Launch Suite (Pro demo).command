#!/bin/zsh
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
export PHANTOMCLOAK_DEV=1
export PHANTOMCLOAK_TIER=pro
[ -d ".venv" ] && source .venv/bin/activate
exec python3 client/phantomcloak.py
