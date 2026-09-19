#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/bin/lince-update"
mkdir -p "$(dirname "$DEST")"
install -m 755 "$SCRIPT_DIR/lince-update" "$DEST"
echo "Installed LINCE updater: $DEST"
