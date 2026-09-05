#!/usr/bin/env bash
# install-bob-hooks.sh — Install the status hook into Bob's (IBM bobshell) config.
#
# What it does:
#   1. Copies the hook script to ~/.local/bin/
#   2. Updates ~/.bob/settings/settings.json with hook entries for
#      SessionStart, Stop, UserPromptSubmit, PreToolUse, PostToolUse
#      (Bob's hook contract is Claude-Code-identical, but has no
#      Notification event — the PERMISSION state is not detectable)
#   3. Prints sandbox env passthrough requirements
#
# Requirements:
#   - jq (for JSON manipulation)
#   - Bob installed (`bob` on PATH, or an existing ~/.bob/ directory).
#     Otherwise settings registration is skipped — re-run this script
#     after installing bob.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="$SCRIPT_DIR/bob-status-hook.sh"
HOOK_DEST="$HOME/.local/bin/bob-status-hook.sh"
SETTINGS_FILE="$HOME/.bob/settings/settings.json"

if ! command -v jq >/dev/null 2>&1; then
    echo -e "${RED}Error: jq is required but not installed.${NC}"
    echo "Install with: sudo dnf install jq  (or: sudo apt-get install jq)"
    exit 1
fi

if [ ! -f "$HOOK_SRC" ]; then
    echo -e "${RED}Error: Hook script not found at $HOOK_SRC${NC}"
    exit 1
fi

echo -e "${GREEN}[1/3] Installing Bob hook script...${NC}"
mkdir -p "$HOME/.local/bin"
cp "$HOOK_SRC" "$HOOK_DEST"
chmod +x "$HOOK_DEST"
echo -e "${GREEN}  Installed: $HOOK_DEST${NC}"

echo ""
echo -e "${GREEN}[2/3] Configuring Bob hooks...${NC}"

# Unlike claude, don't create ~/.bob for users who never installed bob —
# skip quietly and let a later re-run (or update.sh) pick it up.
if ! command -v bob >/dev/null 2>&1 && [ ! -d "$HOME/.bob" ]; then
    echo -e "${YELLOW}  Bob not detected (no 'bob' on PATH, no ~/.bob) — skipping settings registration.${NC}"
    echo -e "${YELLOW}  After installing bob, re-run: bash $SCRIPT_DIR/install-bob-hooks.sh${NC}"
else
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    if [ ! -f "$SETTINGS_FILE" ]; then
        echo '{}' > "$SETTINGS_FILE"
        echo "  Created $SETTINGS_FILE"
    fi

    HOOK_CMD="bob-status-hook.sh"
    HOOK_ENTRY='{"matcher": "", "hooks": [{"type": "command", "command": "'"$HOOK_CMD"'"}]}'

    MERGED=$(jq --arg cmd "$HOOK_CMD" --argjson entry "$HOOK_ENTRY" '
        .hooks //= {} |
        reduce ("SessionStart", "Stop", "UserPromptSubmit", "PreToolUse", "PostToolUse") as $event (.;
            .hooks[$event] = [.hooks[$event][]? | select(has("matcher"))] |
            if (.hooks[$event] | map(select(.hooks[]?.command == $cmd)) | length) == 0
            then .hooks[$event] = ((.hooks[$event] // []) + [$entry])
            else . end
        )
    ' "$SETTINGS_FILE")

    if [ -n "$MERGED" ]; then
        echo "$MERGED" > "$SETTINGS_FILE"
        echo -e "${GREEN}  ✓ Hooks configured: SessionStart, Stop, UserPromptSubmit, PreToolUse, PostToolUse${NC}"
    else
        echo -e "${YELLOW}  ⚠ Could not update settings.json — check jq version${NC}"
    fi
fi

echo ""
echo -e "${GREEN}[3/3] Sandbox configuration requirements${NC}"
echo ""
echo -e "${YELLOW}  IMPORTANT: For hooks to work inside agent-sandbox, you must${NC}"
echo -e "${YELLOW}  add these environment variables to your sandbox config passthrough:${NC}"
echo ""
echo "  In ~/.agent-sandbox/config.toml (or project-local .agent-sandbox/config.toml):"
echo ""
echo '  [env]'
echo '  passthrough = ["ZELLIJ", "ZELLIJ_SESSION_NAME", "LINCE_AGENT_ID"]'
echo ""
echo -e "${GREEN}Bob hook installation complete.${NC}"
echo ""
echo "Hook script: $HOOK_DEST"
echo "Settings:    $SETTINGS_FILE"
echo ""
echo "To verify:"
echo "  echo '{\"hook_event_name\":\"Stop\"}' | LINCE_AGENT_ID=test-1 bash $HOOK_DEST"
echo "  cat /tmp/lince-dashboard/test-1.state  # should show: Stop"
