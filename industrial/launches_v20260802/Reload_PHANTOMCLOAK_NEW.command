#!/bin/bash
# Reload PHANTOMCLOAK NEW industrial session only (not Cumulous / full DHC).
set -euo pipefail

SESSION_ID="019f66e5-e60c-7052-9e1d-e3f07031e549"
TITLE="PHANTOMCLOAK NEW"
INDUSTRIAL="${HOME}/Desktop/PCS_Industrial_20260802"
HANDOFF="${INDUSTRIAL}/PHANTOMCLOAK_NEW_SESSION.md"
CWD="${HOME}"

cd "$CWD"
export PCS_INDUSTRIAL_ROOT="$INDUSTRIAL"
export PHANTOMCLOAK_NEW_SESSION_ID="$SESSION_ID"

echo "=============================================="
echo "  PHANTOMCLOAK NEW — session reload"
echo "=============================================="
echo "Title:     $TITLE"
echo "Session:   $SESSION_ID"
echo "Industrial:$INDUSTRIAL"
echo "Handoff:   $HANDOFF"
echo ""
echo "In Grok Build:  /PCSNEW   or   reload PHANTOMCLOAK NEW"
echo "CLI:            grok --resume $SESSION_ID"
echo "                grok --resume \"$TITLE\""
echo ""

if [[ -f "$HANDOFF" ]]; then
  head -n 40 "$HANDOFF"
  echo "..."
fi

if command -v grok >/dev/null 2>&1; then
  exec grok --cwd "$CWD" --resume "$SESSION_ID"
else
  echo "Open Grok Build from home → welcome list → PHANTOMCLOAK NEW"
  echo "or type /PCSNEW in a Grok session."
  if [[ -t 0 ]]; then read -r -p "Press Enter..."; fi
fi
