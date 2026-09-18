#!/usr/bin/env bash
set -euo pipefail
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
if [[ -L "$BIN/lince-msg" && "$(readlink "$BIN/lince-msg")" == "$DEST/lince-msg" ]]; then
    rm -- "$BIN/lince-msg"
fi
for file in protocol.py store.py service.py instructions.md lince-msg; do
    rm -f -- "$DEST/$file"
done
echo "Removed messaging executables; user settings and mailbox history preserved."
