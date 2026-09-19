#!/usr/bin/env bash
set -e

INSTALL_DST="$HOME/.local/bin/lince-config"

if [ -f "$INSTALL_DST" ]; then
    rm "$INSTALL_DST"
    echo "Removed $INSTALL_DST"
else
    echo "lince-config is not installed."
fi

if [ ! -f "$HOME/.local/bin/lince-dashboard-launch" ] && \
   [ -f "$HOME/.local/bin/lince-python" ] && \
   grep -q "Managed by LINCE for the standalone bootstrap interpreter" "$HOME/.local/bin/lince-python"; then
    rm -f "$HOME/.local/bin/lince-python"
fi
