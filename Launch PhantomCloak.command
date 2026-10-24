#!/bin/zsh
cd "$(dirname "$0")"
echo "=== Launching PhantomCloak (restoring last session) ==="
export PYTHONPATH="$(pwd):${PYTHONPATH:-}"
if [ -d ".venv" ]; then source .venv/bin/activate
elif [ -d "$HOME/.phantomcloak_venv" ]; then source "$HOME/.phantomcloak_venv/bin/activate"; fi
exec -a PhantomCloak python3 client/phantomcloak.py
