#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$DEST" "$BIN"
for file in protocol.py store.py service.py host.py instructions.md; do
    install -m 644 "$SOURCE_DIR/$file" "$DEST/$file"
done
install -m 755 "$SOURCE_DIR/lince-msg" "$DEST/lince-msg"
ln -sfn "$DEST/lince-msg" "$BIN/lince-msg"
install -m 755 "$SOURCE_DIR/lince-msg-host" "$DEST/lince-msg-host"
ln -sfn "$DEST/lince-msg-host" "$BIN/lince-msg-host"
echo "Installed lince-msg. Agent instructions: $DEST/instructions.md"
