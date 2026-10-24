#!/bin/zsh
# Re-loadable checkpoint reload script for Delphi Anti-Detection
# Run this after untarring the main checkpoint tarball (if needed) to verify/prepare for a new prompt instance.

cd "$(dirname "$0")"
echo "=== Reloading Delphi Anti-Detection from CHECKPOINT ==="
echo "Project root: $(pwd)"

# Quick self-check
if [ ! -f "CHECKPOINT.md" ]; then
  echo "ERROR: CHECKPOINT.md not found. Make sure you are in the untarred folder."
  exit 1
fi

echo "CHECKPOINT.md found. Key resume info:"
head -20 CHECKPOINT.md

# Ensure launcher is executable
chmod +x "Launch Delphi Anti-Detection.command" 2>/dev/null || true

# Optional: create venv if not present (for pywebview etc.)
if [ ! -d ".venv" ]; then
  echo "Creating .venv for dependencies (pywebview, etc.)..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install pywebview rumps 2>/dev/null || pip install --break-system-packages pywebview rumps
else
  echo ".venv exists."
fi

echo ""
echo "To launch: double-click 'Launch Delphi Anti-Detection.command' or 'python3 client/delphi_anti_detection.py'"
echo "See CHECKPOINT.md for full details on buttons, deploy, verification, and resuming in a NEW PROMPT INSTANCE."
echo "=== READY ==="
