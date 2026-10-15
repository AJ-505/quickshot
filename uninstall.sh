#!/usr/bin/env bash
# Remove Quickshot and restore the original Print behaviour.
set -euo pipefail

BINDIR="$HOME/.local/bin"
UNITDIR="$HOME/.config/systemd/user"
PREFIX="${QUICKSHOT_PREFIX:-$HOME/.local/share/quickshot}"

say() { printf '  %s\n' "$*"; }

if [ -f "$PREFIX/src/quickshot/bind.py" ]; then
  python3 "$PREFIX/src/quickshot/bind.py" uninstall || say "could not restore keybinding"
else
  say "no installed bind.py; keybinding left alone"
fi

systemctl --user disable --now quickshot.service >/dev/null 2>&1 || true
rm -f "$UNITDIR/quickshot.service"
systemctl --user daemon-reload || true
say "service removed"

rm -f "$BINDIR/quickshot" "$BINDIR/quickshot-py" "$BINDIR/quickshotd"
rm -rf "$PREFIX"
rm -rf "$HOME/.cache/quickshot"
say "files removed"

echo "Print is back to the GNOME screenshot UI."
