#!/bin/zsh
# Delphi Anti-Detection Launcher (checkpoint-aware)
cd "$(dirname "$0")"
echo "=== Launching Delphi Anti-Detection (from CHECKPOINT) ==="
echo "See CHECKPOINT.md for resume instructions, full status, and how to use in a new prompt instance."

# Prefer project venv if present
if [ -d ".venv" ]; then
  source .venv/bin/activate
  echo "Using project .venv"
elif [ -d "$HOME/.delphi_venv" ]; then
  source "$HOME/.delphi_venv/bin/activate"
  echo "Using ~/.delphi_venv"
fi

# Launch the main app (rich dashboard GUI)
python3 client/delphi_anti_detection.py
