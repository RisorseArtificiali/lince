#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
case "${1:-}" in
    ""|--configure-all|--configure-claude|--configure-codex|--configure-bob) ;;
    --help|-h)
        echo "Usage: install.sh [--configure-all | --configure-claude [PATH] | --configure-codex [PATH] | --configure-bob [PATH]]"
        exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
esac
if [[ -f "$DEST/maintenance.py" ]]; then
    python3 "$DEST/maintenance.py"
fi
mkdir -p "$DEST" "$BIN"
for file in protocol.py store.py service.py host.py adapters.py hook_config.py maintenance.py instructions.md; do
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
    python3 "$DEST/hook_config.py" codex "${2:-${CODEX_HOME:-$HOME/.codex}/hooks.json}"
    echo "Codex: review the installed hooks with /hooks; LINCE does not bypass hook trust."
fi
if [[ "${1:-}" == "--configure-bob" ]]; then
    python3 "$DEST/hook_config.py" bob "${2:-$HOME/.bob/settings/settings.json}"
fi
if [[ "${1:-}" == "--configure-all" ]]; then
    if command -v claude >/dev/null 2>&1 || [[ -d "$HOME/.claude" ]]; then
        python3 "$DEST/hook_config.py" claude "$HOME/.claude/settings.json"
    fi
    if command -v codex >/dev/null 2>&1 || [[ -d "${CODEX_HOME:-$HOME/.codex}" ]]; then
        python3 "$DEST/hook_config.py" codex "${CODEX_HOME:-$HOME/.codex}/hooks.json"
        echo "Codex: review LINCE handlers with /hooks. Hook trust is preserved."
    fi
    if command -v bob >/dev/null 2>&1 || [[ -d "$HOME/.bob" ]]; then
        python3 "$DEST/hook_config.py" bob "$HOME/.bob/settings/settings.json"
    fi
fi
echo "Installed lince-msg. Agent instructions: $DEST/instructions.md"
