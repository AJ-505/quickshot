#!/usr/bin/env bash
# Install Quickshot for the current user. No root required.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${QUICKSHOT_PREFIX:-$HOME/.local/share/quickshot}"
BINDIR="$HOME/.local/bin"
UNITDIR="$HOME/.config/systemd/user"
# Hotkeys Quickshot answers to. Override by passing your own, e.g.
#   ./install.sh '<Super><Shift>s' '<Ctrl><Alt>s'
if [ "$#" -gt 0 ]; then
  BINDINGS=("$@")
else
  # Print is left on GNOME's own screenshot UI, so there is always a key that
  # takes a plain screenshot with no editor.
  BINDINGS=('<Super><Shift>s')
fi

say() { printf '  %s\n' "$*"; }

echo "Quickshot installer"
echo

# --- sanity: the pieces we actually depend on -------------------------------
missing=()
python3 - <<'PY' || missing+=("python3-gi (GTK 4)")
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Gdk, PangoCairo  # noqa: F401
PY
python3 - <<'PY' || missing+=("python3-cairo")
import cairo  # noqa: F401
PY
gsettings --version >/dev/null 2>&1 || missing+=("gsettings")
command -v wl-copy >/dev/null 2>&1 || missing+=("wl-clipboard")

if [ ${#missing[@]} -ne 0 ]; then
  echo "Missing dependencies:"
  for m in "${missing[@]}"; do say "- $m"; done
  echo
  echo "On Ubuntu/Debian:"
  echo "  sudo apt install python3-gi gir1.2-gtk-4.0 python3-cairo wl-clipboard xdg-desktop-portal-gnome"
  exit 1
fi
say "dependencies ok"
if [ "${XDG_SESSION_TYPE:-}" != "wayland" ] || [[ "${XDG_CURRENT_DESKTOP:-}" != *GNOME* ]]; then
  say "WARNING: Quickshot is built for GNOME on Wayland; this session is ${XDG_CURRENT_DESKTOP:-unknown}/${XDG_SESSION_TYPE:-unknown}"
fi

# --- files ------------------------------------------------------------------
mkdir -p "$PREFIX/src/quickshot" "$BINDIR" "$UNITDIR"
cp -r "$HERE/src/quickshot/." "$PREFIX/src/quickshot/"
find "$PREFIX" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
cp "$HERE/bin/quickshot"    "$BINDIR/quickshot"
cp "$HERE/bin/quickshot-py" "$BINDIR/quickshot-py"
cp "$HERE/bin/quickshotd"   "$BINDIR/quickshotd"
chmod +x "$BINDIR/quickshot" "$BINDIR/quickshot-py" "$BINDIR/quickshotd"
say "installed to $PREFIX"

# --- resident service -------------------------------------------------------
# Starts with the graphical session so the hotkey is instant, but also runs on
# demand if the service is not up yet.
cat > "$UNITDIR/quickshot.service" <<UNIT
[Unit]
Description=Quickshot screenshot editor
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart=$BINDIR/quickshotd
Restart=on-failure
RestartSec=2
Environment=PYTHONUNBUFFERED=1
Environment=QUICKSHOT_SRC=$PREFIX/src
NoNewPrivileges=true

[Install]
WantedBy=graphical-session.target
UNIT

systemctl --user daemon-reload
systemctl --user enable quickshot.service >/dev/null 2>&1 || true
# Restart, do not merely enable: the resident service holds the old code in
# memory, so copying new files has no effect until it is restarted.
if systemctl --user restart quickshot.service >/dev/null 2>&1; then
  say "resident service restarted (running the new code)"
else
  systemctl --user start quickshot.service >/dev/null 2>&1 || \
    say "could not start the user service; the hotkey will start it on demand"
fi

# Confirm it is actually listening, and that the keyboard-shortcut service
# survived: a malformed custom-keybinding array makes gsd-media-keys segfault,
# which silently kills every custom hotkey on the machine.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [ -S "${XDG_RUNTIME_DIR:-/tmp}/quickshot-$(id -u).sock" ] && break
  sleep 0.3
done
if systemctl --user is-active --quiet org.gnome.SettingsDaemon.MediaKeys.service; then
  say "keyboard shortcut service healthy"
else
  say "WARNING: org.gnome.SettingsDaemon.MediaKeys.service is not running."
  say "         Custom hotkeys will not work until it is restarted:"
  say "         systemctl --user restart org.gnome.SettingsDaemon.MediaKeys.target"
fi

# --- focus extension --------------------------------------------------------
EXT_UUID="quickshot-focus@aj-505.github.io"
mkdir -p "$HOME/.local/share/applications"
cp "$HERE/data/dev.quickshot.Quickshot.desktop" "$HOME/.local/share/applications/"
relogin=0
if command -v gnome-extensions >/dev/null 2>&1; then
  pack_dir=$(mktemp -d)
  gnome-extensions pack --force -o "$pack_dir" "$HERE/shell-extension" >/dev/null 2>&1
  gnome-extensions install --force "$pack_dir/$EXT_UUID.shell-extension.zip" >/dev/null 2>&1
  rm -rf "$pack_dir"
  if gnome-extensions enable "$EXT_UUID" >/dev/null 2>&1; then
    say "focus extension enabled"
  else
    enabled=$(gsettings get org.gnome.shell enabled-extensions)
    case "$enabled" in
      *"$EXT_UUID"*) ;;
      "@as []") gsettings set org.gnome.shell enabled-extensions "['$EXT_UUID']" ;;
      *) gsettings set org.gnome.shell enabled-extensions "${enabled%]}, '$EXT_UUID']" ;;
    esac
    relogin=1
    say "focus extension installed; GNOME loads it at your next login"
  fi
else
  say "WARNING: gnome-extensions not found; the editor may open behind other windows"
fi

# --- hotkeys ----------------------------------------------------------------
python3 "$PREFIX/src/quickshot/bind.py" install "${BINDINGS[@]}"
for b in "${BINDINGS[@]}"; do
  say "$(printf '%s' "$b" | tr -d '<>') bound to Quickshot"
done
say "capture still uses GNOME's native drag-to-select overlay"

echo
echo "Done. Press ${BINDINGS[0]}, drag a region, annotate, then Enter to copy."
echo "Revert with: $HERE/uninstall.sh"
if [ "$relogin" -eq 1 ]; then
  echo
  echo "Log out and back in once. Until then GNOME may open the editor behind your"
  echo "current window and show a \"Quickshot is ready\" banner instead."
fi
