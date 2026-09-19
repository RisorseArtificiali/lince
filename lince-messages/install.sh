#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEST="${LINCE_MESSAGES_INSTALL_DIR:-$HOME/.local/lib/lince-messages}"
BIN="${LINCE_MESSAGES_BIN_DIR:-$HOME/.local/bin}"
read -r -a AGENTS <<< "$(python3 "$SOURCE_DIR/skill_config.py" --list)"
case "${1:-}" in
    --help|-h)
        echo "Usage: install.sh [--enable AGENT... | --disable AGENT... | --runtime-only]"
        echo "Agents: ${AGENTS[*]}"
        echo "Communication is optional. --enable installs the lince-converse skill for each selected agent."
        echo "No messaging hooks are installed. Existing opt-ins are preserved on update."
        exit 0 ;;
    ""|--runtime-only) [[ $# -le 1 ]] ;;
    --enable|--disable)
        [[ $# -ge 2 ]] || { echo 'Select at least one agent' >&2; exit 2; }
        for agent in "${@:2}"; do
            [[ " ${AGENTS[*]} " == *" $agent "* ]] || { echo "Unsupported agent: $agent" >&2; exit 2; }
        done ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 2 ;;
esac
if [[ -f "$DEST/maintenance.py" ]]; then python3 "$DEST/maintenance.py"; fi
mkdir -p "$DEST/skills/lince-converse" "$BIN"
for file in protocol.py store.py service.py host.py transport.py skill_config.py hook_config.py maintenance.py; do
    install -m 644 "$SOURCE_DIR/$file" "$DEST/$file"
done
install -m 644 "$SOURCE_DIR/skills/lince-converse/SKILL.md" "$DEST/skills/lince-converse/SKILL.md"
for file in lince-msg lince-msg-host; do
    install -m 755 "$SOURCE_DIR/$file" "$DEST/$file"
    ln -sfn "$DEST/$file" "$BIN/$file"
done
# The old mailbox hooks must not continue offering task instructions.
python3 "$DEST/hook_config.py" claude "$HOME/.claude/settings.json" --remove
python3 "$DEST/hook_config.py" codex "${CODEX_HOME:-$HOME/.codex}/hooks.json" --remove
python3 "$DEST/hook_config.py" bob "$HOME/.bob/settings/settings.json" --remove
if [[ -L "$BIN/lince-msg-hook" && "$(readlink "$BIN/lince-msg-hook")" == "$DEST/lince-msg-hook" ]]; then rm "$BIN/lince-msg-hook"; fi
rm -f "$DEST/lince-msg-hook" "$DEST/adapters.py" "$DEST/instructions.md"
if [[ "${1:-}" != --disable ]]; then python3 "$DEST/skill_config.py" --refresh; fi
if [[ "${1:-}" == --enable || "${1:-}" == --disable ]]; then
    python3 "$DEST/skill_config.py" "$@"
elif [[ $# == 0 && -t 0 ]]; then
    echo "Optional agent communication installs the lince-converse skill and permits text + Enter between enabled panes."
    echo "No messaging hooks, groups or task setup. Existing dashboard status hooks are used for delivery."
    for agent in "${AGENTS[@]}"; do
        read -r -p "Enable communication and install the skill for $agent? [y/N] " answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then python3 "$DEST/skill_config.py" --enable "$agent"; fi
    done
fi
echo "Communication runtime installed. Start fresh agent panes after changing opt-ins."
