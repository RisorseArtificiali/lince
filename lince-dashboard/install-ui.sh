#!/usr/bin/env bash
# Shared by install.sh and update.sh: presentation assets have identical coverage.
set -euo pipefail
UI_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$HOME/.config/zellij/layouts" "$HOME/.config/lince-dashboard" "$HOME/.local/bin"
for layout in "$UI_SOURCE"/layouts/*.kdl; do
    cp "$layout" "$HOME/.config/zellij/layouts/"
done
cp "$UI_SOURCE/lince-dashboard-launch" "$HOME/.local/bin/lince-dashboard-launch"
chmod +x "$HOME/.local/bin/lince-dashboard-launch"
# The active session config is user-owned; refreshed defaults remain reviewable.
if [ ! -f "$HOME/.config/lince-dashboard/zellij.kdl" ]; then
    cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl"
fi
cp "$UI_SOURCE/zellij-config/config.kdl" "$HOME/.config/lince-dashboard/zellij.kdl.dist"
