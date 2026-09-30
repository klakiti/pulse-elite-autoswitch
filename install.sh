#!/usr/bin/env bash
set -euo pipefail
if [[ $EUID -eq 0 ]]; then
  echo 'Run this script as your desktop user, not with sudo.' >&2
  exit 1
fi
project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for tool in python3 pw-dump wpctl systemctl; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/pulse-elite-autoswitch"
unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$HOME/.local/bin" "$unit_dir" "$config_dir"
install -m 0755 "$project_dir/pulse_elite_autoswitch.py" "$HOME/.local/bin/pulse-elite-autoswitch"
install -m 0644 "$project_dir/pulse-elite-autoswitch.service" "$unit_dir/"
if [[ ! -e "$config_dir/config.json" ]]; then
  install -m 0600 "$project_dir/config.example.json" "$config_dir/config.json"
fi
systemctl --user daemon-reload
printf 'Installed. Configure sink names in %s/config.json before starting.\n' "$config_dir"
printf 'List outputs: %s/.local/bin/pulse-elite-autoswitch --list-sinks\n' "$HOME"
printf 'Start: systemctl --user enable --now pulse-elite-autoswitch\n'
