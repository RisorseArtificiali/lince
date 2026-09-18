#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$DEST" "$BIN"
for file in protocol.py store.py service.py host.py adapters.py hook_config.py instructions.md; do
    install -m 644 "$SOURCE_DIR/$file" "$DEST/$file"
done
install -m 755 "$SOURCE_DIR/lince-msg" "$DEST/lince-msg"
ln -sfn "$DEST/lince-msg" "$BIN/lince-msg"
install -m 755 "$SOURCE_DIR/lince-msg-host" "$DEST/lince-msg-host"
ln -sfn "$DEST/lince-msg-host" "$BIN/lince-msg-host"
install -m 755 "$SOURCE_DIR/lince-msg-hook" "$DEST/lince-msg-hook"
ln -sfn "$DEST/lince-msg-hook" "$BIN/lince-msg-hook"
if [[ "${1:-}" == "--configure-claude" ]]; then
    python3 "$DEST/hook_config.py" claude "${2:-$HOME/.claude/settings.json}"
fi
if [[ "${1:-}" == "--configure-codex" ]]; then
    python3 "$DEST/hook_config.py" codex "${2:-$HOME/.codex/hooks.json}"
    echo "Codex: review the installed hooks with /hooks; LINCE does not bypass hook trust."
fi
if [[ "${1:-}" == "--configure-bob" ]]; then
    python3 "$DEST/hook_config.py" bob "${2:-$HOME/.bob/settings/settings.json}"
fi
echo "Installed lince-msg. Agent instructions: $DEST/instructions.md"
