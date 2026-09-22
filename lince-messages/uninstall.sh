#!/usr/bin/env bash
set -euo pipefail
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
CUSTOM_AGENTS=()
CUSTOM_SETTINGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --help|-h)
            echo "Usage: uninstall.sh [--settings AGENT PATH]..."
            echo "Specify the custom settings paths used with install.sh --configure-AGENT PATH."
            exit 0 ;;
        --settings)
            if [[ $# -lt 3 || ! "$2" =~ ^(claude|codex|bob)$ || -z "$3" ]]; then
                echo "--settings requires claude|codex|bob and a settings path" >&2
                exit 2
            fi
            CUSTOM_AGENTS+=("$2")
            CUSTOM_SETTINGS+=("$3")
            shift 3 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done
if [[ -f "$DEST/maintenance.py" ]]; then
    python3 "$DEST/maintenance.py"
fi
if [[ -f "$DEST/skill_config.py" ]]; then
    python3 "$DEST/skill_config.py" --disable-all
fi
if [[ -f "$DEST/hook_config.py" ]]; then
    python3 "$DEST/hook_config.py" claude "$HOME/.claude/settings.json" --remove
    python3 "$DEST/hook_config.py" codex "${CODEX_HOME:-$HOME/.codex}/hooks.json" --remove
    python3 "$DEST/hook_config.py" bob "$HOME/.bob/settings/settings.json" --remove
    for index in "${!CUSTOM_AGENTS[@]}"; do
        python3 "$DEST/hook_config.py" "${CUSTOM_AGENTS[$index]}" "${CUSTOM_SETTINGS[$index]}" --remove
    done
fi
if [[ -L "$BIN/lince-msg" && "$(readlink "$BIN/lince-msg")" == "$DEST/lince-msg" ]]; then
    rm -- "$BIN/lince-msg"
fi
if [[ -L "$BIN/lince-msg-host" && "$(readlink "$BIN/lince-msg-host")" == "$DEST/lince-msg-host" ]]; then
    rm -- "$BIN/lince-msg-host"
fi
if [[ -L "$BIN/lince-msg-hook" && "$(readlink "$BIN/lince-msg-hook")" == "$DEST/lince-msg-hook" ]]; then
    rm -- "$BIN/lince-msg-hook"
fi
for file in transport.py skill_config.py protocol.py store.py service.py host.py adapters.py hook_config.py maintenance.py instructions.md lince-msg lince-msg-host lince-msg-hook; do
    rm -f -- "$DEST/$file"
done
rm -f "$DEST/skills/lince-converse/SKILL.md"
echo "Removed communication runtime and unmodified LINCE skills; user hooks and legacy history preserved."
