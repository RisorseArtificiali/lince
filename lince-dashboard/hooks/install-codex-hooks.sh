#!/usr/bin/env bash
# install-codex-hooks.sh — Install Codex lifecycle and notify integration.
#
# What it does:
#   1. Copies the Codex notify hook to ~/.local/bin/
#   2. Copies the shared agent wrapper to ~/.local/bin/
#   3. Inserts a managed top-level notify entry into ~/.codex/config.toml
#      unless the user already has a different notify command configured
#   4. Merges lifecycle handlers into Codex hooks.json (preserving user hooks)
#   5. Prints sandbox env passthrough requirements and hook trust instructions
#
# Notes:
#   - Legacy notify reports completion only; lifecycle hooks also report work.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SRC="$SCRIPT_DIR/codex-status-hook.sh"
HOOK_DEST="$HOME/.local/bin/codex-status-hook.sh"
WRAPPER_SRC="$SCRIPT_DIR/lince-agent-wrapper"
WRAPPER_DEST="$HOME/.local/bin/lince-agent-wrapper"
CONFIG_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG_FILE="$CONFIG_DIR/config.toml"
BLOCK_START="# >>> LINCE Dashboard Codex notify >>>"
BLOCK_END="# <<< LINCE Dashboard Codex notify <<<"
HOOK_CMD="codex-status-hook.sh"
HOOK_LINE='notify = ["codex-status-hook.sh"]'

if [ ! -f "$HOOK_SRC" ]; then
    echo -e "${RED}Error: Hook script not found at $HOOK_SRC${NC}"
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}Error: python3 is required but not installed.${NC}"
    exit 1
fi

echo -e "${GREEN}[1/5] Installing Codex status hook...${NC}"
mkdir -p "$HOME/.local/bin"
cp "$HOOK_SRC" "$HOOK_DEST"
chmod +x "$HOOK_DEST"
echo -e "${GREEN}  Installed: $HOOK_DEST${NC}"

echo ""
echo -e "${GREEN}[2/5] Installing shared agent wrapper...${NC}"
if [ -f "$WRAPPER_SRC" ]; then
    cp "$WRAPPER_SRC" "$WRAPPER_DEST"
    chmod +x "$WRAPPER_DEST"
    echo -e "${GREEN}  Installed: $WRAPPER_DEST${NC}"
else
    echo -e "${YELLOW}  ⚠ lince-agent-wrapper not found at $WRAPPER_SRC — skipping${NC}"
fi

echo ""
echo -e "${GREEN}[3/5] Configuring Codex notify...${NC}"

mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_FILE" ]; then
    : > "$CONFIG_FILE"
    echo "  Created $CONFIG_FILE"
fi

MANAGED_BLOCK="${BLOCK_START}
${HOOK_LINE}
${BLOCK_END}"

OTHER_NOTIFY=$(python3 - "$CONFIG_FILE" "$HOOK_CMD" <<'PY'
import pathlib
import sys
import tomllib

path = pathlib.Path(sys.argv[1])
hook = sys.argv[2]
raw = path.read_text() if path.exists() else ""
for line in raw.splitlines():
    stripped = line.strip()
    if stripped.startswith("#"):
        continue
    if stripped.startswith("notify"):
        try:
            cfg = tomllib.loads(raw or "")
        except Exception:
            print("PARSE_ERROR")
            sys.exit(0)
        notify = cfg.get("notify")
        if notify == [hook]:
            print("OURS")
        elif notify is None:
            print("")
        else:
            print("OTHER")
        sys.exit(0)
print("")
PY
)

if [ "$OTHER_NOTIFY" = "PARSE_ERROR" ]; then
    echo -e "${YELLOW}  ⚠ Could not parse $CONFIG_FILE — leaving notify unchanged${NC}"
elif [ "$OTHER_NOTIFY" = "OTHER" ]; then
    echo -e "${YELLOW}  ⚠ Existing Codex notify setting found in $CONFIG_FILE — leaving it unchanged${NC}"
    echo -e "${YELLOW}    Add this manually if you want LINCE idle updates:${NC}"
    echo "    $HOOK_LINE"
elif [ "$OTHER_NOTIFY" = "OURS" ]; then
    echo -e "${GREEN}  ✓ Notify already configured${NC}"
else
    TMP_FILE="$(mktemp)"
    awk -v start="$BLOCK_START" -v end="$BLOCK_END" '
        $0 == start { skipping=1; next }
        $0 == end { skipping=0; next }
        !skipping { print }
    ' "$CONFIG_FILE" > "$TMP_FILE"

    INSERTED=false
    {
        while IFS= read -r line || [ -n "$line" ]; do
            if [ "$INSERTED" = false ] && [[ "$line" =~ ^[[:space:]]*\[ ]]; then
                printf '%s\n' "$MANAGED_BLOCK"
                printf '\n'
                INSERTED=true
            fi
            printf '%s\n' "$line"
        done < "$TMP_FILE"
        if [ "$INSERTED" = false ]; then
            if [ -s "$TMP_FILE" ]; then
                printf '\n'
            fi
            printf '%s\n' "$MANAGED_BLOCK"
        fi
    } > "${TMP_FILE}.new"

    mv "${TMP_FILE}.new" "$CONFIG_FILE"
    rm -f "$TMP_FILE"
    echo -e "${GREEN}  ✓ Notify configured via managed block in $CONFIG_FILE${NC}"
fi

echo ""
echo -e "${GREEN}[4/5] Configuring Codex lifecycle hooks...${NC}"
python3 "$SCRIPT_DIR/codex-hooks-config.py" "$CONFIG_DIR/hooks.json"
echo "  Hooks: $CONFIG_DIR/hooks.json"
echo "  In Codex, open /hooks and review/trust the codex-status-hook.sh handlers."
echo "  Codex skips new or changed hooks until trusted. Then start a new session."

echo ""
echo -e "${GREEN}[5/5] Sandbox configuration requirements${NC}"
echo ""
echo -e "${YELLOW}  IMPORTANT: For Codex status updates to work inside agent-sandbox, you must${NC}"
echo -e "${YELLOW}  add these environment variables to your sandbox config passthrough:${NC}"
echo ""
echo "  In ~/.agent-sandbox/config.toml (or project-local .agent-sandbox/config.toml):"
echo ""
echo '  [env]'
echo '  passthrough = ["ZELLIJ", "ZELLIJ_SESSION_NAME", "LINCE_AGENT_ID"]'
echo ""
echo -e "${GREEN}Codex hook installation complete.${NC}"
echo ""
echo "Hook script: $HOOK_DEST"
echo "Config:      $CONFIG_FILE"
echo ""
echo "To verify:"
echo "  LINCE_AGENT_ID=test-1 bash $HOOK_DEST '{\"type\":\"agent-turn-complete\"}'"
echo "  cat /tmp/lince-dashboard/test-1.state  # should show: agent-turn-complete"
