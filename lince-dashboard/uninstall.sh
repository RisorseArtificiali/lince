#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   LINCE Dashboard — Uninstaller${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# ── Plugin ─────────────────────────────────────────────────────────────
PLUGIN="$HOME/.config/zellij/plugins/lince-dashboard.wasm"
if [ -f "$PLUGIN" ]; then
    echo -e "${YELLOW}Found: $PLUGIN${NC}"
    if confirm "  Remove plugin?"; then
        rm -f "$PLUGIN" "${PLUGIN}.bak."* 2>/dev/null
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Plugin not found — skipping"
fi
echo ""

# ── Layouts ────────────────────────────────────────────────────────────
LAYOUT_DIR="$HOME/.config/zellij/layouts"
LAYOUTS=("dashboard.kdl" "agent-single.kdl" "agent-multi.kdl")
FOUND_LAYOUTS=()
for l in "${LAYOUTS[@]}"; do
    [ -f "$LAYOUT_DIR/$l" ] && FOUND_LAYOUTS+=("$l")
done

if [ ${#FOUND_LAYOUTS[@]} -gt 0 ]; then
    echo -e "${YELLOW}Found layouts: ${FOUND_LAYOUTS[*]}${NC}"
    if confirm "  Remove layouts?"; then
        for l in "${FOUND_LAYOUTS[@]}"; do
            rm -f "$LAYOUT_DIR/$l"
        done
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  No dashboard layouts found — skipping"
fi
echo ""

# ── Config ─────────────────────────────────────────────────────────────
CONFIG_DIR="$HOME/.config/lince-dashboard"
if [ -d "$CONFIG_DIR" ]; then
    echo -e "${YELLOW}Found: $CONFIG_DIR${NC}"
    if confirm "  Remove config directory?"; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Config directory not found — skipping"
fi
echo ""

# ── Hook scripts ───────────────────────────────────────────────────────
HOOKS=(
    "$HOME/.local/bin/claude-status-hook.sh"
    "$HOME/.local/bin/codex-status-hook.sh"
    "$HOME/.local/bin/bob-status-hook.sh"
)
FOUND_HOOKS=()
for hook in "${HOOKS[@]}"; do
    [ -f "$hook" ] && FOUND_HOOKS+=("$hook")
done

if [ ${#FOUND_HOOKS[@]} -gt 0 ]; then
    echo -e "${YELLOW}Found hook scripts:${NC}"
    for hook in "${FOUND_HOOKS[@]}"; do
        echo "  $hook"
    done
    if confirm "  Remove hook scripts?"; then
        rm -f "${FOUND_HOOKS[@]}"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Hook scripts not found — skipping"
fi
echo ""

# ── Agent wrapper ─────────────────────────────────────────────────────
WRAPPER="$HOME/.local/bin/lince-agent-wrapper"
if [ -f "$WRAPPER" ]; then
    echo -e "${YELLOW}Found: $WRAPPER${NC}"
    if confirm "  Remove agent wrapper?"; then
        rm -f "$WRAPPER"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Agent wrapper not found — skipping"
fi
echo ""

# ── Agent defaults ────────────────────────────────────────────────────
AGENTS_DEFAULTS="$HOME/.config/lince-dashboard/agents-defaults.toml"
if [ -f "$AGENTS_DEFAULTS" ]; then
    echo -e "${YELLOW}Found: $AGENTS_DEFAULTS${NC}"
    if confirm "  Remove agent defaults?"; then
        rm -f "$AGENTS_DEFAULTS"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Agent defaults not found — skipping"
fi
echo ""

# ── Unified agent registry (shared with agent-sandbox) ───────────────
REGISTRY_DST="$HOME/.local/share/lince/registry.d"
if [ -d "$REGISTRY_DST" ]; then
    if [ -f "$HOME/.local/bin/agent-sandbox" ]; then
        echo "  Agent registry kept (agent-sandbox still installed): $REGISTRY_DST"
    else
        echo -e "${YELLOW}Found: $REGISTRY_DST${NC}"
        if confirm "  Remove agent registry?"; then
            rm -rf "$REGISTRY_DST"
            echo -e "${GREEN}  ✓ Removed${NC}"
        fi
    fi
fi
echo ""

# ── Lince-add-supported-agent skill (+ legacy lince-setup cleanup) ───
SKILL_DIR="$HOME/.claude/skills/lince-add-supported-agent"
OLD_SKILL_DIR="$HOME/.claude/skills/lince-setup"
FOUND_SKILL_DIRS=()
[ -d "$SKILL_DIR" ] && FOUND_SKILL_DIRS+=("$SKILL_DIR")
[ -d "$OLD_SKILL_DIR" ] && FOUND_SKILL_DIRS+=("$OLD_SKILL_DIR")

if [ ${#FOUND_SKILL_DIRS[@]} -gt 0 ]; then
    echo -e "${YELLOW}Found skill directories:${NC}"
    for d in "${FOUND_SKILL_DIRS[@]}"; do
        echo "  $d"
    done
    if confirm "  Remove lince-add-supported-agent skill (and any legacy lince-setup)?"; then
        for d in "${FOUND_SKILL_DIRS[@]}"; do
            rm -rf "$d"
        done
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  lince-add-supported-agent skill not found — skipping"
fi
echo ""

# ── Claude Code hooks in settings.json ─────────────────────────────────
SETTINGS="$HOME/.claude/settings.json"
if [ -f "$SETTINGS" ] && command -v jq >/dev/null 2>&1; then
    if jq -e '.hooks.Stop[]? | select(.command == "claude-status-hook.sh")' "$SETTINGS" >/dev/null 2>&1; then
        echo -e "${YELLOW}Found dashboard hooks in $SETTINGS${NC}"
        if confirm "  Remove hook entries from Claude Code settings?"; then
            UPDATED=$(jq '
                .hooks.Stop = [.hooks.Stop[]? | select(.command != "claude-status-hook.sh")] |
                .hooks.PreToolUse = [.hooks.PreToolUse[]? | select(.command != "claude-status-hook.sh")] |
                .hooks.Notification = [.hooks.Notification[]? | select(.command != "claude-status-hook.sh")] |
                if .hooks.Stop == [] then del(.hooks.Stop) else . end |
                if .hooks.PreToolUse == [] then del(.hooks.PreToolUse) else . end |
                if .hooks.Notification == [] then del(.hooks.Notification) else . end |
                if .hooks == {} then del(.hooks) else . end
            ' "$SETTINGS")
            echo "$UPDATED" > "$SETTINGS"
            echo -e "${GREEN}  ✓ Removed hook entries${NC}"
        fi
    else
        echo "  No dashboard hooks in settings.json — skipping"
    fi
else
    echo "  Settings.json not found or jq missing — skipping hook cleanup"
fi
echo ""

# ── Bob hooks in settings/settings.json ────────────────────────────────
BOB_SETTINGS="$HOME/.bob/settings/settings.json"
if [ -f "$BOB_SETTINGS" ] && command -v jq >/dev/null 2>&1; then
    if jq -e '[.hooks[]?[]?.hooks[]?.command] | index("bob-status-hook.sh")' "$BOB_SETTINGS" >/dev/null 2>&1; then
        echo -e "${YELLOW}Found dashboard hooks in $BOB_SETTINGS${NC}"
        if confirm "  Remove hook entries from Bob settings?"; then
            UPDATED=$(jq '
                .hooks |= with_entries(
                    .value |= [.[] | select([.hooks[]?.command] | index("bob-status-hook.sh") | not)]
                ) |
                .hooks |= with_entries(select(.value != [])) |
                if .hooks == {} then del(.hooks) else . end
            ' "$BOB_SETTINGS")
            echo "$UPDATED" > "$BOB_SETTINGS"
            echo -e "${GREEN}  ✓ Removed hook entries${NC}"
        fi
    else
        echo "  No dashboard hooks in Bob settings — skipping"
    fi
else
    echo "  Bob settings not found or jq missing — skipping hook cleanup"
fi
echo ""

# ── Pi extension ───────────────────────────────────────────────────────
PI_EXTENSION="$HOME/.pi/agent/extensions/lince-pi-hook.ts"
if [ -f "$PI_EXTENSION" ]; then
    echo -e "${YELLOW}Found: $PI_EXTENSION${NC}"
    if confirm "  Remove Pi extension?"; then
        rm -f "$PI_EXTENSION"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Pi extension not found — skipping"
fi
echo ""

# ── Codex notify in config.toml ────────────────────────────────────────
CODEX_CONFIG="${CODEX_HOME:-$HOME/.codex}/config.toml"
CODEX_BLOCK_START="# >>> LINCE Dashboard Codex notify >>>"
CODEX_BLOCK_END="# <<< LINCE Dashboard Codex notify <<<"
if [ -f "$CODEX_CONFIG" ]; then
    if grep -Fq "$CODEX_BLOCK_START" "$CODEX_CONFIG"; then
        echo -e "${YELLOW}Found dashboard Codex notify block in $CODEX_CONFIG${NC}"
        if confirm "  Remove Codex notify block?"; then
            TMP_FILE="$(mktemp)"
            awk -v start="$CODEX_BLOCK_START" -v end="$CODEX_BLOCK_END" '
                $0 == start { skipping=1; next }
                $0 == end { skipping=0; next }
                !skipping { print }
            ' "$CODEX_CONFIG" > "$TMP_FILE"
            mv "$TMP_FILE" "$CODEX_CONFIG"
            echo -e "${GREEN}  ✓ Removed Codex notify block${NC}"
        fi
    else
        echo "  No dashboard Codex notify block found — skipping"
    fi
else
    echo "  Codex config not found — skipping notify cleanup"
fi
echo ""

CODEX_HOOKS="${CODEX_HOME:-$HOME/.codex}/hooks.json"
if [ -f "$CODEX_HOOKS" ] && grep -Fq 'codex-status-hook.sh' "$CODEX_HOOKS"; then
    if confirm "  Remove Lince Codex lifecycle handlers from $CODEX_HOOKS?"; then
        python3 "$SCRIPT_DIR/hooks/codex-hooks-config.py" "$CODEX_HOOKS" --remove
        echo -e "${GREEN}  ✓ Removed Lince handlers (other hooks preserved)${NC}"
    fi
fi

# ── Shell aliases ────────────────────────────────────────────────
ALIAS_REMOVED=false
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ] && grep -q '# LINCE aliases' "$rc" 2>/dev/null; then
        echo -e "${YELLOW}Found LINCE aliases in $(basename $rc)${NC}"
        if confirm "  Remove all LINCE aliases?"; then
            # Remove the LINCE aliases block (comment + all alias lines)
            sed -i '/# LINCE aliases/d' "$rc"
            sed -i '/alias lince=/d' "$rc"
            sed -i '/alias lince-floating=/d' "$rc"
            
            
            sed -i '/alias zd=/d' "$rc"
            sed -i '/alias z="zellij"/d' "$rc"
            sed -i '/alias zn=/d' "$rc"
            ALIAS_REMOVED=true
            echo -e "${GREEN}  ✓ Removed from $(basename $rc)${NC}"
        fi
    fi
done
if [ "$ALIAS_REMOVED" = false ]; then
    echo "  No LINCE aliases found — skipping"
fi
echo ""

# ── Status files ───────────────────────────────────────────────────────
STATUS_FILES=$(ls /tmp/claude-agent-*.state 2>/dev/null || true)
STATUS_DIR_EXISTS=false
[ -d "/tmp/lince-dashboard" ] && STATUS_DIR_EXISTS=true

if [ -n "$STATUS_FILES" ] || [ "$STATUS_DIR_EXISTS" = true ]; then
    echo -e "${YELLOW}Found status files in /tmp/${NC}"
    if confirm "  Remove status files?"; then
        rm -f /tmp/claude-agent-*.state
        rm -rf /tmp/lince-dashboard
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
fi
echo ""

# ── Done ───────────────────────────────────────────────────────────────
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Uninstall Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Source files in lince-dashboard/ were NOT removed."
echo "To reinstall later: cd lince-dashboard && ./install.sh"
echo ""
