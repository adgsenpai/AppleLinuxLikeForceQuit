#!/usr/bin/env bash
# Install Force Quit for the current user and bind it to Super+Alt+Escape
# (the Linux equivalent of macOS's Command+Option+Escape).
#
#   ./install.sh                      # default shortcut
#   SHORTCUT='<Control><Alt>Delete' ./install.sh
set -euo pipefail

SHORTCUT="${SHORTCUT:-<Super><Alt>Escape}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/share/force-quit"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"

python3 - <<'PY' || { echo "Needs Python 3 with GTK 4 bindings: sudo apt install python3-gi gir1.2-gtk-4.0"; exit 1; }
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
PY

mkdir -p "$DEST" "$BIN" "$APPS"
rm -rf "$DEST/forcequit" "$DEST/bin"
cp -r "$SRC/forcequit" "$SRC/bin" "$DEST/"
find "$DEST" -name __pycache__ -prune -exec rm -rf {} +
chmod +x "$DEST/bin/force-quit"
ln -sf "$DEST/bin/force-quit" "$BIN/force-quit"
sed "s|^Exec=.*|Exec=$BIN/force-quit|" "$SRC/data/io.github.adgsenpai.ForceQuit.desktop" \
  > "$APPS/io.github.adgsenpai.ForceQuit.desktop"
update-desktop-database "$APPS" 2>/dev/null || true

if command -v gsettings >/dev/null && gsettings list-schemas | grep -qx org.gnome.settings-daemon.plugins.media-keys; then
  python3 - "$SHORTCUT" "$BIN/force-quit" <<'PY'
import ast, subprocess, sys

shortcut, command = sys.argv[1], sys.argv[2]
schema = "org.gnome.settings-daemon.plugins.media-keys"
path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/force-quit/"

out = subprocess.check_output(["gsettings", "get", schema, "custom-keybindings"], text=True).strip()
current = ast.literal_eval(out.removeprefix("@as ")) if out not in ("@as []", "[]") else []
if path not in current:
    current.append(path)
    subprocess.check_call(["gsettings", "set", schema, "custom-keybindings", str(current)])

rel = f"{schema}.custom-keybinding:{path}"
for key, value in (("name", "Force Quit Applications"), ("command", command), ("binding", shortcut)):
    subprocess.check_call(["gsettings", "set", rel, key, value])
PY
  echo "Shortcut $SHORTCUT -> force-quit registered in GNOME Settings › Keyboard › Custom Shortcuts."
else
  echo "GNOME not detected: bind '$BIN/force-quit' to $SHORTCUT in your desktop's keyboard settings."
fi

echo "Installed. Press Super+Alt+Escape (or run 'force-quit')."
