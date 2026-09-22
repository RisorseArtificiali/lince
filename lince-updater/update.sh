#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.local/bin/lince-update"
[ -x "$DEST" ] || { echo "lince-update is not installed; run install.sh first" >&2; exit 1; }
install -m 755 "$SCRIPT_DIR/lince-update" "$DEST"
echo "Updated LINCE updater: $DEST"
