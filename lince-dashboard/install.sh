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
source "$SCRIPT_DIR/../scripts/dashboard-preset.sh"

# Sandbox isolation levels (paranoid/normal/permissive) are no longer chosen at
# install time. Under Config v2 they are a dimension of each agent, offered by
# the dashboard's New Agent wizard at spawn time; the old install-time selection
# wrote legacy [agents.<base>-<level>] blocks into config.toml that both
# duplicated wizard rows and blocked the v2 policy switch (see #202 regression).
BUILD_FROM_SOURCE=false
for arg in "$@"; do
    case "$arg" in
        --build-from-source)
            BUILD_FROM_SOURCE=true
            ;;
        --help|-h)
            echo "Usage: $0 [--build-from-source]"
            echo ""
            echo "  Installs the lince-dashboard Zellij plugin and its config."
            echo "  Downloads a checksum-verified prebuilt plugin by default."
            echo "  --build-from-source requires a rustup toolchain and builds locally."
            echo "  Choose a dashboard preset interactively (default: minimal)."
            echo "  Set LINCE_DASHBOARD_PRESET=minimal|statusline|classic to skip that prompt."
            echo "  Sandbox isolation levels are offered per agent at spawn time"
            echo "  by the dashboard wizard — no install-time selection needed."
            exit 0 ;;
    esac
done

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   LINCE Dashboard — Installer${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

select_dashboard_preset

# ── Step 1: Prerequisites ─────────────────────────────────────────────
echo -e "${GREEN}[1/14] Checking prerequisites...${NC}"

check_zellij_version || exit 1
if [ "$BUILD_FROM_SOURCE" = true ]; then
    echo -e "${YELLOW}  Source build requested; rustup-managed Rust is required.${NC}"
    MISSING=()
    if ! command -v rustc >/dev/null 2>&1; then
        MISSING+=("rustc")
    else
        echo -e "${GREEN}  ✓ rustc $(rustc --version 2>/dev/null | awk '{print $2}')${NC}"
    fi
    if ! command -v cargo >/dev/null 2>&1; then
        MISSING+=("cargo")
    else
        echo -e "${GREEN}  ✓ cargo${NC}"
    fi

    # Homebrew's standalone Rust cannot provide rustup-managed WASM targets.
    if [ "$(uname -s)" = "Darwin" ]; then
        BREW_CARGO=""
        if [ -x "/opt/homebrew/bin/cargo" ]; then
            BREW_CARGO="/opt/homebrew/bin/cargo"
        elif [ -x "/usr/local/bin/cargo" ]; then
            BREW_CARGO="/usr/local/bin/cargo"
        fi
        if [ -n "$BREW_CARGO" ] && ! command -v rustup >/dev/null 2>&1; then
            MISSING+=("rustup (Homebrew Rust detected at $BREW_CARGO but rustup is missing)")
        elif [ -n "$BREW_CARGO" ] && ! rustup which rustc >/dev/null 2>&1; then
            MISSING+=("rustup toolchain (run: rustup default stable)")
        fi
    fi

    if [ ${#MISSING[@]} -gt 0 ]; then
        echo -e "${RED}Missing prerequisites:${NC}"
        for missing in "${MISSING[@]}"; do
            echo "  - $missing"
        done
        echo "Install them first, then re-run this script."
        exit 1
    fi

    export PATH="$HOME/.cargo/bin:$PATH"
    if command -v rustup >/dev/null 2>&1; then
        if ! rustup target list --installed 2>/dev/null | grep -q wasm32-wasip1; then
            echo "  Installing wasm32-wasip1 target..."
            rustup target add wasm32-wasip1
            if ! rustup target list --installed 2>/dev/null | grep -q wasm32-wasip1; then
                echo -e "${RED}  ✗ Failed to install wasm32-wasip1 target${NC}"
                exit 1
            fi
        fi
        echo -e "${GREEN}  ✓ wasm32-wasip1 target installed${NC}"
    else
        echo -e "${RED}  ✗ rustup not found — wasm32-wasip1 target cannot be installed${NC}"
        echo -e "${RED}    Install rustup: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh${NC}"
        exit 1
    fi
elif ! command -v curl >/dev/null 2>&1; then
    echo -e "${RED}  ✗ curl not found — required to download the release plugin${NC}"
    exit 1
else
    echo -e "${GREEN}  ✓ prebuilt release install (no Rust toolchain required)${NC}"
fi
echo ""

# ── Steps 2-4: Acquire, verify, and install WASM plugin ───────────────
echo -e "${GREEN}[2-4/14] Installing dashboard plugin...${NC}"
PLUGIN_ARGS=()
if [ "$BUILD_FROM_SOURCE" = true ]; then
    PLUGIN_ARGS+=("--build-from-source")
fi
if ! "$SCRIPT_DIR/install-plugin.sh" "${PLUGIN_ARGS[@]}"; then
    exit 1
fi
WASM_DST="$HOME/.config/zellij/plugins/lince-dashboard.wasm"

# Pre-grant Zellij permissions so the plugin works without interactive prompt.
# Zellij cache location differs by OS:
#   Linux: ~/.cache/zellij/permissions.kdl
#   macOS: ~/Library/Caches/org.Zellij-Contributors.Zellij/permissions.kdl
if [ "$(uname -s)" = "Darwin" ]; then
    PERMS_CACHE_DIR="$HOME/Library/Caches/org.Zellij-Contributors.Zellij"
else
    PERMS_CACHE_DIR="$HOME/.cache/zellij"
fi
PERMS_CACHE="$PERMS_CACHE_DIR/permissions.kdl"
mkdir -p "$PERMS_CACHE_DIR"
# Check that permissions are actually granted (not just an empty entry).
# Zellij may create the file with a plugin name but no permissions inside.
if [ -f "$PERMS_CACHE" ] && grep -q "lince-dashboard.wasm" "$PERMS_CACHE" 2>/dev/null \
   && grep -q "ReadApplicationState" "$PERMS_CACHE" 2>/dev/null; then
    echo -e "${GREEN}  ✓ Plugin permissions already cached${NC}"
else
    # Remove any stale empty entry before writing
    if [ -f "$PERMS_CACHE" ]; then
        sed -i.bak '/lince-dashboard\.wasm/,/^}/d' "$PERMS_CACHE"
        rm -f "${PERMS_CACHE}.bak"
    fi
    cat >> "$PERMS_CACHE" << PERMSEOF
"${WASM_DST}" {
    RunCommands
    ReadApplicationState
    ReadCliPipes
    WriteToStdin
    ChangeApplicationState
    OpenTerminalsOrPlugins
    MessageAndLaunchOtherPlugins
}
PERMSEOF
    echo -e "${GREEN}  ✓ Plugin permissions pre-granted${NC}"
fi
echo ""

# ── Step 5: Install layouts ───────────────────────────────────────────
echo -e "${GREEN}[5/14] Installing layouts...${NC}"

LAYOUT_DIR="$HOME/.config/zellij/layouts"
mkdir -p "$LAYOUT_DIR"

bash "$SCRIPT_DIR/install-ui.sh"
if [[ -t 0 ]]; then bash "$SCRIPT_DIR/../lince-messages/install.sh"; fi
echo -e "${GREEN}  ✓ Layouts and launcher installed${NC}"

# ── Step 6: Session-scoped Zellij configuration ─────────────────────────
echo -e "${GREEN}[6/14] LINCE session keybindings...${NC}"
LINCE_SESSION_CONFIG="$HOME/.config/lince-dashboard/zellij.kdl"
echo "  LINCE uses $LINCE_SESSION_CONFIG; your global Zellij config is unchanged."
echo ""

# ── Step 7: Install config ────────────────────────────────────────────
echo -e "${GREEN}[7/14] Installing configuration...${NC}"

CONFIG_DIR="$HOME/.config/lince-dashboard"
CONFIG_DST="$CONFIG_DIR/config.toml"

mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_DST" ]; then
    BACKUP="${CONFIG_DST}.bak.$(date +%Y%m%d-%H%M%S)"
    cp "$CONFIG_DST" "$BACKUP"
    echo -e "${YELLOW}  Existing config backed up → $(basename "$BACKUP")${NC}"
fi
write_dashboard_preset_config "$SCRIPT_DIR/config.toml" "$CONFIG_DST"
echo -e "${GREEN}  ✓ Installed: $CONFIG_DST${NC}"
echo ""

# ── Step 8: Install hooks ─────────────────────────────────────────────
echo -e "${GREEN}[8/14] Installing agent platform hooks...${NC}"

if [ -f "$SCRIPT_DIR/hooks/install-hooks.sh" ]; then
    bash "$SCRIPT_DIR/hooks/install-hooks.sh"
    # Install viewport placeholder for the tiled layout
    PLACEHOLDER_SRC="$SCRIPT_DIR/hooks/lince-viewport-placeholder"
    if [ -f "$PLACEHOLDER_SRC" ]; then
        cp "$PLACEHOLDER_SRC" "$HOME/.local/bin/lince-viewport-placeholder"
        chmod +x "$HOME/.local/bin/lince-viewport-placeholder"
        echo -e "${GREEN}  ✓ lince-viewport-placeholder${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ hooks/install-hooks.sh not found — skipping${NC}"
fi
echo ""

# ── Step 9: Install agents-defaults.toml + agents-template.toml ──────
echo -e "${GREEN}[9/14] Installing agent defaults and templates...${NC}"

AGENTS_DEFAULTS_SRC="$SCRIPT_DIR/agents-defaults.toml"
AGENTS_DEFAULTS_DST="$CONFIG_DIR/agents-defaults.toml"
AGENTS_TEMPLATE_SRC="$SCRIPT_DIR/agents-template.toml"
AGENTS_TEMPLATE_DST="$CONFIG_DIR/agents-template.toml"

# lince-config is a runtime dependency since #202: the plugin obtains agent
# types / providers / sandbox levels from `lince-config resolve --json`.
# Install it from the sibling module when missing (idempotent); without it
# the dashboard falls back to compiled-in shipped defaults.
if ! command -v lince-config >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/lince-config" ]; then
    if [ -x "$SCRIPT_DIR/../lince-config/install.sh" ]; then
        echo -e "${YELLOW}  lince-config not found — installing from ../lince-config${NC}"
        bash "$SCRIPT_DIR/../lince-config/install.sh" >/dev/null \
            && echo -e "${GREEN}  ✓ lince-config installed${NC}" \
            || echo -e "${YELLOW}  ⚠ lince-config install failed — dashboard will use built-in agent defaults${NC}"
    else
        echo -e "${YELLOW}  ⚠ lince-config not installed — dashboard will use built-in agent defaults.${NC}"
        echo -e "${YELLOW}    Install it: cd ../lince-config && ./install.sh${NC}"
    fi
fi

# Unified agent registry (Config v2, #204). Shipped data — always overwritten
# (#199); custom agents never live here. Also installed by sandbox/install.sh
# (same files, idempotent) so either module works standalone.
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
    echo -e "${GREEN}  ✓ Installed agent registry: $count file(s) in $REGISTRY_DST${NC}"
fi

if [ -f "$AGENTS_DEFAULTS_SRC" ]; then
    if [ -f "$AGENTS_DEFAULTS_DST" ]; then
        AGENTS_BACKUP="${AGENTS_DEFAULTS_DST}.bak.$(date +%Y%m%d-%H%M%S)"
        cp "$AGENTS_DEFAULTS_DST" "$AGENTS_BACKUP"
        echo -e "${YELLOW}  Existing agent defaults backed up → $(basename "$AGENTS_BACKUP")${NC}"
    fi
    cp "$AGENTS_DEFAULTS_SRC" "$AGENTS_DEFAULTS_DST"
    echo -e "${GREEN}  ✓ Installed: $AGENTS_DEFAULTS_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ agents-defaults.toml not found — skipping${NC}"
fi

# agents-template.toml ships as a human-readable reference of the per-level
# variant blocks. It is NOT loaded by the dashboard and is NOT merged into
# config.toml: under Config v2 levels are resolved dynamically (shipped trio +
# discovered customs), so there is no install-time level application step.
if [ -f "$AGENTS_TEMPLATE_SRC" ]; then
    cp "$AGENTS_TEMPLATE_SRC" "$AGENTS_TEMPLATE_DST"
    echo -e "${GREEN}  ✓ Installed (reference only): $AGENTS_TEMPLATE_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ agents-template.toml not found — skipping${NC}"
fi
echo ""

# ── Step 10: Install nono profiles (deprecated, kept for compatibility) ────
echo -e "${GREEN}[10/14] Installing sandbox profiles...${NC}"

# Seatbelt profiles (preferred on macOS)
SEATBELT_PROFILES_SRC="$SCRIPT_DIR/seatbelt-profiles"
SEATBELT_PROFILES_DST="$HOME/.agent-sandbox/seatbelt-profiles"

if [ -d "$SEATBELT_PROFILES_SRC" ]; then
    mkdir -p "$SEATBELT_PROFILES_DST"
    count=0
    for profile in "$SEATBELT_PROFILES_SRC"/lince-*.sb; do
        [ -f "$profile" ] || continue
        cp "$profile" "$SEATBELT_PROFILES_DST/"
        count=$((count + 1))
    done
    if [ "$count" -gt 0 ]; then
        echo -e "${GREEN}  ✓ Installed $count Seatbelt profiles to $SEATBELT_PROFILES_DST${NC}"
    fi
fi

# nono profiles (deprecated, installed for backward compatibility)
NONO_PROFILES_SRC="$SCRIPT_DIR/nono-profiles"
NONO_PROFILES_DST="$HOME/.config/nono/profiles"

if [ -d "$NONO_PROFILES_SRC" ]; then
    mkdir -p "$NONO_PROFILES_DST"
    count=0
    for profile in "$NONO_PROFILES_SRC"/lince-*.json; do
        [ -f "$profile" ] || continue
        cp "$profile" "$NONO_PROFILES_DST/"
        count=$((count + 1))
    done
    if [ "$count" -gt 0 ]; then
        echo -e "${GREEN}  ✓ Installed $count nono profiles to $NONO_PROFILES_DST (deprecated)${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ nono-profiles/ not found — skipping${NC}"
fi
echo ""

# ── Step 11: Install lince-add-supported-agent skill ──────────────────
echo -e "${GREEN}[11/14] Installing lince-add-supported-agent skill...${NC}"

SKILL_SRC="$SCRIPT_DIR/skills/lince-add-supported-agent"
SKILL_DST="$HOME/.claude/skills/lince-add-supported-agent"

if [ -d "$SKILL_SRC" ]; then
    mkdir -p "$SKILL_DST"
    cp -r "$SKILL_SRC/." "$SKILL_DST/"
    echo -e "${GREEN}  ✓ Installed: $SKILL_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ skills/lince-add-supported-agent/ not found — skipping${NC}"
fi
echo ""

# ── Step 12: Install lince-configure skill ────────────────────────────
echo -e "${GREEN}[12/14] Installing lince-configure skill...${NC}"

CONFIGURE_SKILL_SRC="$SCRIPT_DIR/skills/lince-configure"
CONFIGURE_SKILL_DST="$HOME/.claude/skills/lince-configure"

if [ -d "$CONFIGURE_SKILL_SRC" ]; then
    mkdir -p "$CONFIGURE_SKILL_DST"
    cp -r "$CONFIGURE_SKILL_SRC/." "$CONFIGURE_SKILL_DST/"
    echo -e "${GREEN}  ✓ Installed: $CONFIGURE_SKILL_DST${NC}"
    echo -e "  ${BLUE}  Requires lince-config CLI (installed by quickstart.sh).${NC}"
else
    echo -e "${YELLOW}  ⚠ skills/lince-configure/ not found — skipping${NC}"
fi
echo ""

# ── Step 13: Shell aliases ────────────────────────────────────────────
echo -e "${GREEN}[13/14] Setting up shell aliases...${NC}"

ALIAS_LINES="$(cat <<'ALIASES'
alias lince-classic="lince-dashboard-launch --preset classic"
alias lince-minimal="lince-dashboard-launch --preset minimal"
alias lince-statusline="lince-dashboard-launch --preset statusline"
alias lince='"$HOME/.local/bin/lince"'
alias lince-floating="lince-dashboard-launch --layout dashboard"
alias zd="lince-dashboard-launch"
alias z="zellij"
alias zn="zellij attach -c"
ALIASES
)"
ALIAS_COMMENT="# LINCE aliases"

for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$rc" ]; then
        if grep -q "# LINCE aliases" "$rc" 2>/dev/null; then
            echo -e "${YELLOW}  Updating LINCE aliases in $(basename $rc)${NC}"
            # Remove old LINCE alias block and re-add
            # BSD sed (macOS) requires -i '' — GNU sed uses -i alone
            _sed_inplace=(sed -i)
            if [ "$(uname -s)" = "Darwin" ]; then
                _sed_inplace=(sed -i "")
            fi
            "${_sed_inplace[@]}" '/# LINCE aliases/d' "$rc"
            "${_sed_inplace[@]}" '/alias lince=/d' "$rc"
            "${_sed_inplace[@]}" '/alias lince-floating=/d' "$rc"
            "${_sed_inplace[@]}" '/alias lince-classic=/d' "$rc"
            "${_sed_inplace[@]}" '/alias lince-minimal=/d' "$rc"
            "${_sed_inplace[@]}" '/alias lince-statusline=/d' "$rc"
            "${_sed_inplace[@]}" '/alias zd=/d' "$rc"
            "${_sed_inplace[@]}" '/alias z="zellij"/d' "$rc"
            "${_sed_inplace[@]}" '/alias zn=/d' "$rc"
        fi
        echo "" >> "$rc"
        echo "$ALIAS_COMMENT" >> "$rc"
        echo "$ALIAS_LINES" >> "$rc"
        echo -e "${GREEN}  ✓ Updated aliases (lince, lince-floating, zd, z, zn) in $(basename $rc)${NC}"
    fi
done
echo ""

# ── Step 14: Optional VoxCode integration ─────────────────────────────
echo -e "${GREEN}[14/14] VoxCode integration...${NC}"
if command -v voxcode >/dev/null 2>&1; then
    if [ -z "${LINCE_VOXCODE_ENABLED:-}" ]; then
        echo "  Alt+v opens voice settings; Alt+m mutes, Alt+t / Ctrl+Space toggles PTT. No permanent voice pane."
        read -r -p "  Enable VoxCode integration? [Y/n]: " VOICE_REPLY || VOICE_REPLY=""
        case "$VOICE_REPLY" in n|N|no|No) LINCE_VOXCODE_ENABLED=false ;; *) LINCE_VOXCODE_ENABLED=true ;; esac
    fi
else
    echo "  VoxCode not installed. Install it later: https://github.com/RisorseArtificiali/voxcode"
fi
case "${LINCE_VOXCODE_ENABLED:-true}" in
    true|false) ;;
    *) echo "LINCE_VOXCODE_ENABLED must be true or false" >&2; exit 1 ;;
esac
python3 - "$CONFIG_DST" "${LINCE_VOXCODE_ENABLED:-true}" <<'VOICEPY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
p.write_text(p.read_text().replace('voxcode_enabled = true', 'voxcode_enabled = ' + sys.argv[2]))
VOICEPY
echo "  Settings: Alt+v. Microphone stays off until you start VoxCode."
echo ""

# ── Sandbox backend check ─────────────────────────────────────────────
echo -e "${GREEN}[post] Checking sandbox backend...${NC}"

OS_NAME="$(uname -s)"
HAS_SANDBOX=false
HAS_NONO=false
HAS_SEATBELT=false
command -v agent-sandbox >/dev/null 2>&1 && HAS_SANDBOX=true
command -v nono >/dev/null 2>&1 && HAS_NONO=true
command -v sandbox-exec >/dev/null 2>&1 && HAS_SEATBELT=true

if [ "$OS_NAME" = "Darwin" ]; then
    if [ "$HAS_SEATBELT" = true ]; then
        echo -e "${GREEN}  ✓ macOS: Seatbelt (sandbox-exec) detected as sandbox backend${NC}"
    elif [ "$HAS_NONO" = true ]; then
        echo -e "${YELLOW}  ✓ macOS: nono detected (deprecated — consider using Seatbelt)${NC}"
    else
        echo -e "${YELLOW}  ⚠ macOS: no sandbox backend found.${NC}"
        echo -e "${YELLOW}    Seatbelt (sandbox-exec) is built into macOS.${NC}"
        echo -e "${YELLOW}    Alternatively, install nono (deprecated): brew install nono${NC}"
    fi
else
    if [ "$HAS_SANDBOX" = true ]; then
        echo -e "${GREEN}  ✓ agent-sandbox detected${NC}"
    fi
    if [ "$HAS_NONO" = true ]; then
        echo -e "${GREEN}  ✓ nono detected (deprecated alternative)${NC}"
    fi
    if [ "$HAS_SANDBOX" = false ] && [ "$HAS_NONO" = false ]; then
        echo -e "${YELLOW}  ⚠ No sandbox backend found. Install one:${NC}"
        echo "    agent-sandbox: cd ../sandbox && ./install.sh"
        echo "    nono:          cargo install nono-cli  (deprecated)"
    fi
fi
echo ""

# ── Summary ───────────────────────────────────────────────────────────
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Installation Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${GREEN}Installed:${NC}"
echo "  Plugin:   $WASM_DST"
echo "  Perms:    $PERMS_CACHE"
echo "  Layouts:  $LAYOUT_DIR/dashboard.kdl"
echo "  Config:   $CONFIG_DST"
echo "  Hooks:    ~/.local/bin/claude-status-hook.sh"
echo "            ~/.local/bin/codex-status-hook.sh"
echo "            ~/.local/bin/bob-status-hook.sh"
echo "  Wrapper:  ~/.local/bin/lince-agent-wrapper"
echo "  Viewport: ~/.local/bin/lince-viewport-placeholder  (tiled layout)"
echo "  Defaults: ~/.config/lince-dashboard/agents-defaults.toml"
echo "  Template: ~/.config/lince-dashboard/agents-template.toml  (reference only)"
echo "  Nono:     ~/.config/nono/profiles/lince-*.json  (deprecated)"
echo "  Skills:   ~/.claude/skills/lince-add-supported-agent/"
echo "            ~/.claude/skills/lince-configure/"
echo ""
echo -e "${GREEN}Sandbox backend:${NC}"
if [ "$OS_NAME" = "Darwin" ]; then
    echo "  macOS — Seatbelt (sandbox-exec, recommended) or nono (deprecated)"
    [ "$HAS_SEATBELT" = true ] && echo "  ✓ Seatbelt (sandbox-exec) available"
    [ "$HAS_NONO" = true ] && echo "  ✓ nono installed (deprecated)"
else
    echo "  Linux — agent-sandbox (recommended) or nono (deprecated)"
    [ "$HAS_SANDBOX" = true ] && echo "  ✓ agent-sandbox installed"
    [ "$HAS_NONO" = true ] && echo "  ✓ nono installed (deprecated)"
fi
echo ""
if [ "$HAS_NONO" = true ]; then
    echo -e "${GREEN}Sandbox levels (paranoid/normal/permissive):${NC}"
    echo "  Paranoid level with nono needs the Anthropic API key in nono's keystore so"
    echo "  the credential proxy can inject it at runtime. Populate it once:"
    if [ "$OS_NAME" = "Darwin" ]; then
        echo "    security add-generic-password -s nono -a anthropic_api_key -w 'sk-ant-...'"
    else
        echo "    secret-tool store --label 'nono anthropic' service nono account anthropic_api_key"
    fi
    echo "  See https://nono.sh/docs/cli/features/credential-injection.md for"
    echo "  1Password / Apple Passwords integration."
    echo ""
fi
echo -e "${GREEN}Usage:${NC}"
echo "  source ~/.bashrc   # reload aliases"
echo "  lince              # launch dashboard (tiled layout)"
echo "  lince-floating     # launch floating layout"
echo "  zd                 # legacy alias for lince"
echo ""
echo -e "${GREEN}Keybindings:${NC}"
echo "  n       Spawn new agent"
echo "  k       Kill selected agent"
echo "  f/Enter Focus (show) agent pane"
echo "  h/Esc   Hide focused agent pane"
echo "  j/Down  Select next agent"
echo "  Up      Select previous agent"
echo "  ]/[     Cycle focus between agents"
echo "  i       Input mode (type to agent)"
echo ""
