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
if [[ -L "$BIN/lince-msg-hook" && "$(readlink "$BIN/lince-msg-hook")" == "$DEST/lince-msg-hook" ]]; then
    rm -- "$BIN/lince-msg-hook"
fi
if [[ -f "$DEST/hook_config.py" ]]; then
    python3 "$DEST/hook_config.py" claude "$HOME/.claude/settings.json" --remove
fi
for file in protocol.py store.py service.py host.py adapters.py hook_config.py instructions.md lince-msg lince-msg-host lince-msg-hook; do
    rm -f -- "$DEST/$file"
done
echo "Removed messaging executables; user settings and mailbox history preserved."
