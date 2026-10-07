#!/usr/bin/env bash
set -euo pipefail

rm -rf "$HOME/.local/share/force-quit"
rm -f "$HOME/.local/bin/force-quit" "$HOME/.local/share/applications/io.github.adgsenpai.ForceQuit.desktop"

if command -v gsettings >/dev/null && gsettings list-schemas | grep -qx org.gnome.settings-daemon.plugins.media-keys; then
  python3 - <<'PY'
import ast, subprocess

schema = "org.gnome.settings-daemon.plugins.media-keys"
path = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/force-quit/"
out = subprocess.check_output(["gsettings", "get", schema, "custom-keybindings"], text=True).strip()
current = ast.literal_eval(out.removeprefix("@as ")) if out not in ("@as []", "[]") else []
if path in current:
    current.remove(path)
    subprocess.check_call(["gsettings", "set", schema, "custom-keybindings", str(current)])
subprocess.call(["gsettings", "reset-recursively", f"{schema}.custom-keybinding:{path}"])
PY
fi
echo "Force Quit removed."
