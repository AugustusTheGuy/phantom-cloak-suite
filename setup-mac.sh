#!/bin/zsh
# Delphi Anti-Detection — macOS Setup Script (v1)
# Run this once after copying the folder to your Desktop

set -e

echo "=== Delphi Anti-Detection Setup ==="
echo "This will install the minimal Python dependencies for the dashboard skeleton."
echo ""

# Check for Homebrew
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found. Please install it first: https://brew.sh"
    exit 1
fi

echo "Installing recommended tools (wireguard-tools, sing-box optional later)..."
brew install wireguard-tools 2>/dev/null || true

# Create a clean venv inside the project (recommended)
VENV_PATH="$(dirname "$0")/.venv"
if [ ! -d "$VENV_PATH" ]; then
    echo "Creating dedicated venv at $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
fi

source "$VENV_PATH/bin/activate"

echo "Upgrading pip and installing core packages (rumps + pywebview for dashboard)..."
pip install --upgrade pip
pip install rumps pywebview

echo ""
echo "✅ Basic setup complete."
echo ""
echo "Next steps:"
echo "1. Run the launcher: ./Launch\ Delphi\ Anti-Detection.command"
echo "2. For full killswitch + sing-box power, also: brew install sing-box"
echo "3. Read README.md and SECURITY_METHODS.md"
echo ""
echo "The real implementation (pf killswitch, anti-forensics sweeper, Camoufox profiles, server deploys) continues in the coming sessions."
echo "Enjoy building the strongest desktop anti-detection system possible."