#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --sandbox-levels=... / LINCE_SANDBOX_LEVELS: extra levels beyond `normal`.
# Resolved interactively by quickstart.sh and forwarded to install.sh.
SANDBOX_LEVELS_OPT_SET=false
SANDBOX_LEVELS_OPT=""
for arg in "$@"; do
    case "$arg" in
        --sandbox-levels=*)
            SANDBOX_LEVELS_OPT="${arg#*=}"
            SANDBOX_LEVELS_OPT_SET=true
            ;;
        --help|-h)
            echo "Usage: $0 [--sandbox-levels=paranoid,permissive]"
            echo ""
            echo "  --sandbox-levels=LIST   Comma-separated list of extra sandbox"
            echo "                          levels (paranoid, permissive). Empty or"
            echo "                          unset = normal only."
            echo "                          Same as setting LINCE_SANDBOX_LEVELS."
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

# Detect clipboard backend (X11/Wayland/macOS) and uncomment the matching
# copy_command line in the installed Zellij config so Ctrl+Shift+C reaches
# the system clipboard even when the host terminal lacks OSC 52 support.
# Idempotent: re-running leaves an already-uncommented line untouched.
setup_clipboard_backend() {
    local config="$1"
    local os_name backend cmd_name pkg_hint install_hint
    os_name="$(uname -s)"

    if [ "$os_name" = "Darwin" ]; then
        backend="macOS"
        cmd_name="pbcopy"
        pkg_hint=""
        install_hint=""
    elif [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
        backend="Wayland"
        cmd_name="wl-copy"
        pkg_hint="wl-clipboard"
    else
        backend="X11"
        cmd_name="xclip"
        pkg_hint="xclip"
    fi

    echo -e "${GREEN}  Clipboard backend: $backend ($cmd_name)${NC}"

    if [ -n "$pkg_hint" ] && ! command -v "$cmd_name" >/dev/null 2>&1; then
        if command -v apt-get >/dev/null 2>&1; then
            install_hint="sudo apt-get install $pkg_hint"
        elif command -v dnf >/dev/null 2>&1; then
            install_hint="sudo dnf install $pkg_hint"
        elif command -v pacman >/dev/null 2>&1; then
            install_hint="sudo pacman -S $pkg_hint"
        elif command -v zypper >/dev/null 2>&1; then
            install_hint="sudo zypper install $pkg_hint"
        else
            install_hint="install '$pkg_hint' via your package manager"
        fi
        echo -e "${YELLOW}  ⚠ '$cmd_name' not found — copy will rely on terminal OSC 52.${NC}"
        echo -e "${YELLOW}    For reliable copy: $install_hint${NC}"
    fi

    case "$cmd_name" in
        xclip)
            sed -i.bak -E 's|^// (copy_command "xclip[^"]*"[[:space:]]*// x11)$|\1|' "$config"
            ;;
        wl-copy)
            sed -i.bak -E 's|^// (copy_command "wl-copy"[[:space:]]*// wayland)$|\1|' "$config"
            ;;
        pbcopy)
            sed -i.bak -E 's|^// (copy_command "pbcopy"[[:space:]]*// osx)$|\1|' "$config"
            ;;
    esac
    rm -f "${config}.bak"
    echo -e "${GREEN}  ✓ copy_command set for $backend${NC}"
}

# ── Step 1: Prerequisites ─────────────────────────────────────────────
echo -e "${GREEN}[1/14] Checking prerequisites...${NC}"

MISSING=()

if ! command -v zellij >/dev/null 2>&1; then
    MISSING+=("zellij (>= 0.40)")
else
    echo -e "${GREEN}  ✓ zellij $(zellij --version 2>/dev/null | awk '{print $2}')${NC}"
fi

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

# On macOS, detect the common case where Homebrew provides standalone
# rustc/cargo but rustup isn't installed or isn't the active toolchain.
# The WASM build requires rustup-managed Rust because only rustup can
# install the wasm32-wasip1 target.
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
    for m in "${MISSING[@]}"; do
        echo "  - $m"
    done
    echo ""
    echo "Install them first, then re-run this script."
    exit 1
fi
echo ""

# ── Step 2: WASM target ───────────────────────────────────────────────
echo -e "${GREEN}[2/14] Checking wasm32-wasip1 target...${NC}"

# Ensure rustup toolchain takes precedence
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
echo ""

# ── Step 3: Build plugin ──────────────────────────────────────────────
echo -e "${GREEN}[3/14] Building plugin...${NC}"

if ! "$SCRIPT_DIR/plugin/build.sh"; then
    echo -e "${RED}Build failed. Check errors above.${NC}"
    exit 1
fi
echo ""

# ── Step 4: Install WASM plugin ───────────────────────────────────────
echo -e "${GREEN}[4/14] Installing plugin...${NC}"

PLUGIN_DIR="$HOME/.config/zellij/plugins"
mkdir -p "$PLUGIN_DIR"

WASM_SRC="$SCRIPT_DIR/plugin/lince-dashboard.wasm"
WASM_DST="$PLUGIN_DIR/lince-dashboard.wasm"

if [ -f "$WASM_DST" ]; then
    echo -e "${YELLOW}  Existing plugin found, backing up...${NC}"
    cp "$WASM_DST" "${WASM_DST}.bak.$(date +%Y%m%d_%H%M%S)"
fi

cp "$WASM_SRC" "$WASM_DST"
echo -e "${GREEN}  ✓ Installed: $WASM_DST${NC}"

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

for layout in dashboard.kdl dashboard-vox.kdl dashboard-tiled.kdl dashboard-tiled-vox.kdl agent-single.kdl agent-multi.kdl; do
    SRC="$SCRIPT_DIR/layouts/$layout"
    DST="$LAYOUT_DIR/$layout"
    if [ -f "$SRC" ]; then
        cp "$SRC" "$DST"
        echo -e "${GREEN}  ✓ $layout${NC}"
    fi
done
echo ""

# ── Step 6: Zellij keybinding configuration ──────────────────────────
echo -e "${GREEN}[6/14] Zellij keybinding configuration...${NC}"

ZELLIJ_CONFIG="$HOME/.config/zellij/config.kdl"
LINCE_ZELLIJ_CONFIG="$SCRIPT_DIR/zellij-config/config.kdl"

if [ -f "$LINCE_ZELLIJ_CONFIG" ]; then
    if [ -f "$ZELLIJ_CONFIG" ]; then
        echo -e "${YELLOW}  Existing Zellij config found: $ZELLIJ_CONFIG${NC}"
        echo ""
        echo "  LINCE includes keybindings optimized for AI coding agents"
        echo "  (Ctrl+O disabled to avoid conflicts, custom mode bindings)."
        echo "  Your current config will be backed up."
        echo ""
        if confirm "  Install LINCE keybindings?"; then
            BACKUP="${ZELLIJ_CONFIG}.bak.$(date +%Y%m%d_%H%M%S)"
            cp "$ZELLIJ_CONFIG" "$BACKUP"
            echo -e "${GREEN}  ✓ Backup: $BACKUP${NC}"
            cp "$LINCE_ZELLIJ_CONFIG" "$ZELLIJ_CONFIG"
            echo -e "${GREEN}  ✓ LINCE keybindings installed${NC}"
            setup_clipboard_backend "$ZELLIJ_CONFIG"
        else
            echo -e "${YELLOW}  Skipped — keeping your existing config${NC}"
            echo -e "${YELLOW}  Note: some keybindings may conflict with AI coding agents${NC}"
        fi
    else
        echo "  No existing Zellij config found."
        if confirm "  Install LINCE keybindings? (Ctrl+O disabled for agent compatibility)"; then
            mkdir -p "$(dirname "$ZELLIJ_CONFIG")"
            cp "$LINCE_ZELLIJ_CONFIG" "$ZELLIJ_CONFIG"
            echo -e "${GREEN}  ✓ LINCE keybindings installed${NC}"
            setup_clipboard_backend "$ZELLIJ_CONFIG"
        else
            echo -e "${YELLOW}  Skipped${NC}"
        fi
    fi
else
    echo -e "${YELLOW}  ⚠ zellij-config/config.kdl not found — skipping${NC}"
fi
echo ""

# ── Step 7: Install config ────────────────────────────────────────────
echo -e "${GREEN}[7/14] Installing configuration...${NC}"

CONFIG_DIR="$HOME/.config/lince-dashboard"
CONFIG_DST="$CONFIG_DIR/config.toml"

mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_DST" ]; then
    BACKUP="${CONFIG_DST}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "$CONFIG_DST" "$BACKUP"
    echo -e "${YELLOW}  Existing config backed up → $(basename "$BACKUP")${NC}"
fi
cp "$SCRIPT_DIR/config.toml" "$CONFIG_DST"
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
USER_CONFIG="$CONFIG_DIR/config.toml"

if [ -f "$AGENTS_DEFAULTS_SRC" ]; then
    cp "$AGENTS_DEFAULTS_SRC" "$AGENTS_DEFAULTS_DST"
    echo -e "${GREEN}  ✓ Installed: $AGENTS_DEFAULTS_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ agents-defaults.toml not found — skipping${NC}"
fi

if [ -f "$AGENTS_TEMPLATE_SRC" ]; then
    cp "$AGENTS_TEMPLATE_SRC" "$AGENTS_TEMPLATE_DST"
    echo -e "${GREEN}  ✓ Installed: $AGENTS_TEMPLATE_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ agents-template.toml not found — skipping${NC}"
fi

# Resolve the level selection: explicit flag wins; else env var; else normal-only.
if [ "$SANDBOX_LEVELS_OPT_SET" = true ]; then
    SELECTED_LEVELS="$SANDBOX_LEVELS_OPT"
else
    SELECTED_LEVELS="${LINCE_SANDBOX_LEVELS:-}"
fi

if [ -n "$SELECTED_LEVELS" ] && [ -f "$AGENTS_TEMPLATE_DST" ]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${YELLOW}  ⚠ python3 not found — cannot apply --sandbox-levels; skipping${NC}"
    else
        added=$(python3 "$SCRIPT_DIR/scripts/apply-sandbox-levels.py" \
                    "$AGENTS_TEMPLATE_DST" "$USER_CONFIG" "$SELECTED_LEVELS")
        if [ -n "$added" ]; then
            echo -e "${GREEN}  ✓ Enabled levels in $USER_CONFIG:${NC}"
            echo "$added" | sed 's/^/      • /'
        else
            echo -e "${GREEN}  ✓ Sandbox levels already in $USER_CONFIG (nothing to do)${NC}"
        fi
    fi
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

ALIAS_LINES='alias lince="zellij --layout dashboard-tiled"
alias lince-floating="zellij --layout dashboard"
alias zd="zellij --layout dashboard-tiled"
alias z="zellij"
alias zn="zellij attach -c"'
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

# ── Step 14: VoxCode layout selection ─────────────────────────────────
echo -e "${GREEN}[14/14] VoxCode layout configuration...${NC}"

if command -v voxcode >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ voxcode detected${NC}"
    echo "  Setting dashboard-vox.kdl as default layout (includes VoxCode pane)."
    if [ -f "$LAYOUT_DIR/dashboard-vox.kdl" ]; then
        cp "$LAYOUT_DIR/dashboard-vox.kdl" "$LAYOUT_DIR/dashboard.kdl"
        echo -e "${GREEN}  ✓ Dashboard layout updated with VoxCode pane${NC}"
    fi
    # Also update tiled layout to VoxCode variant
    if [ -f "$LAYOUT_DIR/dashboard-tiled-vox.kdl" ]; then
        cp "$LAYOUT_DIR/dashboard-tiled-vox.kdl" "$LAYOUT_DIR/dashboard-tiled.kdl"
        echo -e "${GREEN}  ✓ Tiled layout updated with VoxCode pane${NC}"
    fi
else
    echo -e "${YELLOW}  VoxCode not found — using standard dashboard layout${NC}"
    echo "  For voice input, install VoxCode separately:"
    echo "    https://github.com/RisorseArtificiali/voxcode"
fi
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
echo "  Wrapper:  ~/.local/bin/lince-agent-wrapper"
echo "  Viewport: ~/.local/bin/lince-viewport-placeholder  (tiled layout)"
echo "  Defaults: ~/.config/lince-dashboard/agents-defaults.toml"
echo "  Template: ~/.config/lince-dashboard/agents-template.toml"
if [ -n "$SELECTED_LEVELS" ]; then
    echo "  Levels:   $SELECTED_LEVELS (added to ~/.config/lince-dashboard/config.toml)"
fi
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
