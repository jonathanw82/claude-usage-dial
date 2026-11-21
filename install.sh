#!/usr/bin/env bash
# Install the Claude usage indicator for the current user (no sudo needed).
# Re-run after editing claude_usage.py to update the installed copy.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin/claude-usage"
APPS="$HOME/.local/share/applications"
AUTOSTART="$HOME/.config/autostart"

if ! python3 -c "import gi; gi.require_version('AyatanaAppIndicator3','0.1')" 2>/dev/null; then
  echo "Missing dependency. Run first:"
  echo "  sudo apt install gir1.2-ayatanaappindicator3-0.1"
  exit 1
fi

mkdir -p "$(dirname "$BIN")" "$APPS" "$AUTOSTART"
install -m 755 "$HERE/claude_usage.py" "$BIN"

DESKTOP="[Desktop Entry]
Type=Application
Name=Claude Usage
Comment=Show Claude session and weekly usage in the top bar
Exec=$BIN
Icon=utilities-system-monitor
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"
printf '%s' "$DESKTOP" > "$APPS/claude-usage.desktop"
printf '%s' "$DESKTOP" > "$AUTOSTART/claude-usage.desktop"

echo "Installed. Starting it now…"
pkill -f "$BIN" 2>/dev/null || true
nohup "$BIN" >/dev/null 2>&1 &
echo "Done. It will also start automatically when you log in."
