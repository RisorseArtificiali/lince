#!/usr/bin/env bash
set -euo pipefail
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
if [[ -L "$BIN/lince-msg" && "$(readlink "$BIN/lince-msg")" == "$DEST/lince-msg" ]]; then
    rm -- "$BIN/lince-msg"
fi
if [[ -L "$BIN/lince-msg-host" && "$(readlink "$BIN/lince-msg-host")" == "$DEST/lince-msg-host" ]]; then
    rm -- "$BIN/lince-msg-host"
fi
for file in protocol.py store.py service.py host.py instructions.md lince-msg lince-msg-host; do
    rm -f -- "$DEST/$file"
done
echo "Removed messaging executables; user settings and mailbox history preserved."
