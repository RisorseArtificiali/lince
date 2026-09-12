#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=scripts/check-zellij.sh
source "$SCRIPT_DIR/../scripts/check-zellij.sh"

# Pick a backup path that never clobbers an earlier backup, even when two
# updates run within the same second (timestamp collision → -1, -2, ... suffix).
unique_backup_path() {
    local base candidate n
    base="$1.bak.$(date +%Y%m%d-%H%M%S)"
    candidate="$base"
    n=1
    while [ -e "$candidate" ]; do
        candidate="$base-$n"
        n=$((n + 1))
    done
    printf '%s' "$candidate"
}

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   LINCE Dashboard — Update${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Ensure rustup toolchain takes precedence
export PATH="$HOME/.cargo/bin:$PATH"

check_zellij_version || exit 1

# ── Build ──────────────────────────────────────────────────────────────
echo -e "${GREEN}[1/8] Building plugin...${NC}"
if ! "$SCRIPT_DIR/plugin/build.sh"; then
    echo -e "${RED}Build failed.${NC}"
    exit 1
fi
echo ""

# ── Plugin ─────────────────────────────────────────────────────────────
echo -e "${GREEN}[2/8] Updating plugin...${NC}"
PLUGIN_DIR="$HOME/.config/zellij/plugins"
mkdir -p "$PLUGIN_DIR"
cp "$SCRIPT_DIR/plugin/lince-dashboard.wasm" "$PLUGIN_DIR/lince-dashboard.wasm"
echo -e "${GREEN}  ✓ Plugin updated${NC}"
echo ""

# ── Layouts ────────────────────────────────────────────────────────────
echo -e "${GREEN}[3/8] Updating layouts...${NC}"
LAYOUT_DIR="$HOME/.config/zellij/layouts"
mkdir -p "$LAYOUT_DIR"
bash "$SCRIPT_DIR/install-ui.sh"
echo -e "${GREEN}  ✓ All layout variants and launcher updated${NC}"
echo ""

# ── Config ─────────────────────────────────────────────────────────────
echo -e "${GREEN}[4/8] Updating configuration...${NC}"
CONFIG_DIR="$HOME/.config/lince-dashboard"
CONFIG_DST="$CONFIG_DIR/config.toml"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DST" ]; then
    cp "$SCRIPT_DIR/config.toml" "$CONFIG_DST"
    echo -e "${GREEN}  ✓ Config installed${NC}"
elif [ "${LINCE_RESET_CONFIG:-0}" = "1" ]; then
    CONFIG_BAK="$(unique_backup_path "$CONFIG_DST")"
    cp "$CONFIG_DST" "$CONFIG_BAK"
    cp "$SCRIPT_DIR/config.toml" "$CONFIG_DST"
    echo -e "${YELLOW}  LINCE_RESET_CONFIG=1 — config reset to shipped defaults${NC}"
    echo -e "${YELLOW}  Previous config backed up → $(basename "$CONFIG_BAK")${NC}"
else
    # Merge new shipped defaults into the user config (user values win,
    # new upstream keys added, orphans preserved). Backs up as .bak.<ts>.
    MERGER="$SCRIPT_DIR/../scripts/config_merge.py"
    set +e
    # Existing installations without a preset retain the previous presentation.
    # User-selected presets still win in config_merge; fresh installs use minimal.
    UI_MERGE_DEFAULTS="$(mktemp)"
    sed 's/^preset = "minimal"$/preset = "classic"/' "$SCRIPT_DIR/config.toml" > "$UI_MERGE_DEFAULTS"
    python3 "$MERGER" "$CONFIG_DST" "$UI_MERGE_DEFAULTS"
    MERGE_RC=$?
    rm -f "$UI_MERGE_DEFAULTS"
    set -e
    if [ "$MERGE_RC" -eq 0 ]; then
        echo -e "${GREEN}  ✓ Config merged (user values preserved, new defaults added)${NC}"
    elif [ "$MERGE_RC" -eq 3 ]; then
        echo -e "${YELLOW}  ⚠ tomlkit not installed — existing config preserved unmerged.${NC}"
        echo -e "${YELLOW}    Install it (pip install --user tomlkit) and re-run update.sh,${NC}"
        echo -e "${YELLOW}    or diff against the sidecar: diff -u $CONFIG_DST.dist $CONFIG_DST${NC}"
    else
        echo -e "${YELLOW}  ⚠ Config merge failed (exit $MERGE_RC) — existing config preserved.${NC}"
    fi
fi
# Always refresh the shipped-defaults sidecar so users can diff against new
# upstream keys without losing their customizations:
#   diff -u "$CONFIG_DST.dist" "$CONFIG_DST"
cp "$SCRIPT_DIR/config.toml" "$CONFIG_DST.dist"
echo -e "${GREEN}  ✓ Upstream defaults available at config.toml.dist${NC}"
echo ""

# ── Hooks ──────────────────────────────────────────────────────────────
echo -e "${GREEN}[5/8] Updating agent platform hooks...${NC}"
if [ -f "$SCRIPT_DIR/hooks/update-hooks.sh" ]; then
    bash "$SCRIPT_DIR/hooks/update-hooks.sh"
else
    echo -e "${YELLOW}  ⚠ hooks/update-hooks.sh not found — run install.sh for first setup${NC}"
fi
echo ""

# ── Agent wrapper ─────────────────────────────────────────────────────
echo -e "${GREEN}[6/8] Updating agent wrapper...${NC}"
echo -e "${GREEN}  ✓ Managed by hooks/update-hooks.sh${NC}"
echo ""

# ── Agents defaults ──────────────────────────────────────────────────
echo -e "${GREEN}[7/8] Updating agent defaults...${NC}"
AGENTS_DEFAULTS_SRC="$SCRIPT_DIR/agents-defaults.toml"
AGENTS_DEFAULTS_DST="$CONFIG_DIR/agents-defaults.toml"

# lince-config is a runtime dependency since #202 (resolve --json). Refresh
# it from the sibling module so the plugin and resolver stay in step.
if [ -x "$SCRIPT_DIR/../lince-config/update.sh" ] && \
   { command -v lince-config >/dev/null 2>&1 || [ -x "$HOME/.local/bin/lince-config" ]; }; then
    bash "$SCRIPT_DIR/../lince-config/update.sh" >/dev/null \
        && echo -e "${GREEN}  ✓ lince-config updated${NC}" \
        || echo -e "${YELLOW}  ⚠ lince-config update failed — run ../lince-config/update.sh manually${NC}"
elif [ -x "$SCRIPT_DIR/../lince-config/install.sh" ]; then
    echo -e "${YELLOW}  lince-config not found — installing from ../lince-config${NC}"
    bash "$SCRIPT_DIR/../lince-config/install.sh" >/dev/null \
        && echo -e "${GREEN}  ✓ lince-config installed${NC}" \
        || echo -e "${YELLOW}  ⚠ lince-config install failed — dashboard will use built-in agent defaults${NC}"
fi

# Unified agent registry (Config v2, #204). Shipped data — always overwritten
# (#199); custom agents never live here. Also updated by sandbox/update.sh.
REGISTRY_SRC="$SCRIPT_DIR/../registry.d"
REGISTRY_DST="$HOME/.local/share/lince/registry.d"
if [ -d "$REGISTRY_SRC" ]; then
    mkdir -p "$REGISTRY_DST"
    count=0
    for entry in "$REGISTRY_SRC"/*.toml; do
        [ -f "$entry" ] || continue
        cp "$entry" "$REGISTRY_DST/"
        count=$((count + 1))
    done
    echo -e "${GREEN}  ✓ Agent registry updated: $count file(s) in $REGISTRY_DST${NC}"
fi

if [ -f "$AGENTS_DEFAULTS_SRC" ]; then
    # agents-defaults.toml is fully shipped data (#199) — always overwritten.
    # Fail-safe migration: if the old installed file differs from the shipped
    # one IN ANY WAY (custom [agents.*] keys, edited values of shipped entries,
    # quickstart-filtered subsets, even a malformed hand-edited file that no
    # parser can read), back it up before the unconditional overwrite below.
    # After the first overwrite DST == SRC, so later updates skip the backup.
    if [ -f "$AGENTS_DEFAULTS_DST" ] && ! cmp -s "$AGENTS_DEFAULTS_DST" "$AGENTS_DEFAULTS_SRC"; then
        AGENTS_BAK="$(unique_backup_path "$AGENTS_DEFAULTS_DST")"
        cp "$AGENTS_DEFAULTS_DST" "$AGENTS_BAK"
        # Best-effort detection of non-shipped agent keys for a targeted
        # warning; a parse failure just means we fall back to the generic one.
        EXTRA_KEYS="$(python3 - "$AGENTS_DEFAULTS_DST" "$AGENTS_DEFAULTS_SRC" << 'PYEOF'
import sys
import tomllib


def agent_keys(path):
    try:
        with open(path, "rb") as f:
            return set(tomllib.load(f).get("agents", {}))
    except Exception:
        return set()


print(" ".join(sorted(agent_keys(sys.argv[1]) - agent_keys(sys.argv[2]))))
PYEOF
)"
        if [ -n "$EXTRA_KEYS" ]; then
            echo -e "${YELLOW}  ⚠ Custom agents detected in agents-defaults.toml: $EXTRA_KEYS${NC}"
            echo -e "${YELLOW}    This file is shipped data and is now always overwritten on update.${NC}"
            echo -e "${YELLOW}    Backup saved → $(basename "$AGENTS_BAK")${NC}"
            echo -e "${YELLOW}    Move those [agents.<key>] blocks into $CONFIG_DIR/config.toml${NC}"
            echo -e "${YELLOW}    (each entry must be a COMPLETE definition — entries fully replace, no per-field merge).${NC}"
        else
            echo -e "${YELLOW}  ⚠ Your agents-defaults.toml differed from the shipped file and is now overwritten.${NC}"
            echo -e "${YELLOW}    Backup saved → $(basename "$AGENTS_BAK")${NC}"
            echo -e "${YELLOW}    If you had edited values of shipped entries, re-apply them as complete${NC}"
            echo -e "${YELLOW}    [agents.<key>] blocks in $CONFIG_DIR/config.toml (entries fully replace).${NC}"
        fi
    fi
    cp "$AGENTS_DEFAULTS_SRC" "$AGENTS_DEFAULTS_DST"
    echo -e "${GREEN}  ✓ Agent defaults updated (shipped file, always overwritten)${NC}"
fi
# The .dist sidecar is redundant now that the installed file always equals
# the shipped one — drop a stale sidecar if present.
if [ -f "$AGENTS_DEFAULTS_DST.dist" ]; then
    rm -f "$AGENTS_DEFAULTS_DST.dist"
    echo -e "${GREEN}  ✓ Removed stale agents-defaults.toml.dist sidecar${NC}"
fi
echo ""

# NOTE: config.toml is user-owned — new upstream keys are merged into it via
# scripts/config_merge.py (user values win; .bak + .dist sidecar kept; #108).
# agents-defaults.toml is shipped data and always overwritten (#199): custom
# agents belong in config.toml [agents.<key>] blocks.

# ── Lince-add-supported-agent skill ──────────────────────────────────
echo -e "${GREEN}[8/8] Updating lince-add-supported-agent skill...${NC}"
SKILL_SRC="$SCRIPT_DIR/skills/lince-add-supported-agent"
SKILL_DST="$HOME/.claude/skills/lince-add-supported-agent"

if [ -d "$SKILL_SRC" ]; then
    mkdir -p "$SKILL_DST"
    cp -r "$SKILL_SRC/." "$SKILL_DST/"
    echo -e "${GREEN}  ✓ Skill updated${NC}"
fi

# Cleanup: remove the old skill dir from the previous skill name.
OLD_SKILL_DST="$HOME/.claude/skills/lince-setup"
if [ -d "$OLD_SKILL_DST" ]; then
    rm -rf "$OLD_SKILL_DST"
    echo -e "${GREEN}  ✓ Removed legacy ~/.claude/skills/lince-setup/${NC}"
fi
echo ""

# ── Sandbox check (informational only) ─────────────────────────────────
SANDBOX_CONFIG="$HOME/.agent-sandbox/config.toml"
if [ -f "$SANDBOX_CONFIG" ]; then
    MISSING=false
    for var in ZELLIJ ZELLIJ_SESSION_NAME LINCE_AGENT_ID; do
        if ! python3 -c "
import tomllib, sys
with open(sys.argv[1], 'rb') as f:
    cfg = tomllib.load(f)
sys.exit(0 if sys.argv[2] in cfg.get('env', {}).get('passthrough', []) else 1)
" "$SANDBOX_CONFIG" "$var" 2>/dev/null; then
            MISSING=true
            break
        fi
    done
    if [ "$MISSING" = true ]; then
        echo -e "${YELLOW}NOTE: Sandbox env passthrough missing ZELLIJ/LINCE_AGENT_ID vars.${NC}"
        echo -e "${YELLOW}  Run: cd ../sandbox && ./update.sh${NC}"
        echo ""
    fi
elif [ ! -f "$HOME/.local/bin/agent-sandbox" ]; then
    true  # sandbox not installed, skip check
else
    echo -e "${YELLOW}NOTE: No sandbox config found. Run: cd ../sandbox && ./install.sh${NC}"
    echo ""
fi

echo -e "${GREEN}Update complete.${NC} Restart Zellij to load the new plugin."
echo ""
