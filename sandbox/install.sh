#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_CMD="$SCRIPT_DIR/agent-sandbox"
INSTALL_DST="$HOME/.local/bin/agent-sandbox"
CONFIG_DIR="$HOME/.agent-sandbox"
CONFIG_DST="$CONFIG_DIR/config.toml"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   agent-sandbox — Installer${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# ── Step 1: Prerequisites ──────────────────────────────────────────────
echo -e "${GREEN}[1/5] Checking prerequisites...${NC}"

OS_NAME="$(uname -s)"
HAS_BWRAP=false
HAS_NONO=false
HAS_SEATBELT=false

command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Missing: python3 (3.11+)${NC}"; exit 1; }

# Check python version
PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)" 2>/dev/null || echo 0)
if [ "$PY_OK" = "0" ]; then
    echo -e "${RED}Python 3.11+ required (for tomllib)${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ python3 $(python3 --version 2>&1 | awk '{print $2}')${NC}"

# Check sandbox backends
if command -v bwrap >/dev/null 2>&1; then
    HAS_BWRAP=true
    echo -e "${GREEN}  ✓ bwrap $(bwrap --version 2>/dev/null | awk '{print $2}')${NC}"
fi
if command -v sandbox-exec >/dev/null 2>&1; then
    HAS_SEATBELT=true
    echo -e "${GREEN}  ✓ sandbox-exec (Seatbelt, built-in)${NC}"
fi
if command -v nono >/dev/null 2>&1; then
    HAS_NONO=true
    echo -e "${YELLOW}  ✓ nono $(nono --version 2>/dev/null | head -1) (deprecated)${NC}"
fi

# socat is required for paranoid sandbox level on bwrap (it bridges
# TCP-localhost-in-sandbox -> bind-mounted unix socket -> host proxy).
# Not a hard prerequisite — paranoid is opt-in — but warn early so users
# don't hit it at run time.
if [ "$OS_NAME" != "Darwin" ] && [ "$HAS_BWRAP" = true ]; then
    if command -v socat >/dev/null 2>&1; then
        echo -e "${GREEN}  ✓ socat $(socat -V 2>&1 | head -1 | awk '{print $3}') (needed for paranoid sandbox level)${NC}"
    else
        echo -e "${YELLOW}  ⚠ socat not found — needed only if you use sandbox_level=\"paranoid\" with bwrap${NC}"
        echo -e "${YELLOW}    Install: dnf install socat   |   apt install socat   |   pacman -S socat${NC}"
    fi
fi

# Platform-specific checks
if [ "$OS_NAME" = "Darwin" ]; then
    # macOS: prefer seatbelt (built-in), fall back to nono (deprecated)
    if [ "$HAS_SEATBELT" = true ]; then
        echo -e "${GREEN}  ✓ macOS detected — using Seatbelt (sandbox-exec) as sandbox backend${NC}"
    elif [ "$HAS_NONO" = true ]; then
        echo -e "${YELLOW}  ⚠ macOS detected — Seatbelt (sandbox-exec) not found.${NC}"
        echo -e "${YELLOW}    Falling back to nono (deprecated). Consider using Seatbelt.${NC}"
    else
        echo ""
        echo -e "${RED}macOS detected — no sandbox backend found.${NC}"
        echo -e "${YELLOW}Seatbelt (sandbox-exec) is built into macOS and should be available.${NC}"
        echo -e "${YELLOW}Alternatively, install nono (deprecated): brew install nono${NC}"
        exit 1
    fi
else
    # Linux: need at least one backend
    if [ "$HAS_BWRAP" = false ] && [ "$HAS_NONO" = false ]; then
        echo -e "${RED}No sandbox backend found. Install one of:${NC}"
        echo "  - bubblewrap: sudo dnf install bubblewrap  (or: sudo apt install bubblewrap)"
        echo "  - nono:       cargo install nono-cli  (or: brew install nono)  (deprecated)"
        exit 1
    fi
fi
echo ""

# ── Step 2: Install command ────────────────────────────────────────────
echo -e "${GREEN}[2/5] Installing agent-sandbox command...${NC}"

mkdir -p "$HOME/.local/bin"
if [ -f "$INSTALL_DST" ]; then
    echo -e "${YELLOW}  Existing command found, backing up...${NC}"
    cp "$INSTALL_DST" "${INSTALL_DST}.bak.$(date +%Y%m%d_%H%M%S)"
fi
cp "$SANDBOX_CMD" "$INSTALL_DST"
chmod +x "$INSTALL_DST"
echo -e "${GREEN}  ✓ Installed: $INSTALL_DST${NC}"

# Install agents-defaults.toml in both search locations
DEFAULTS_SRC="$SCRIPT_DIR/agents-defaults.toml"
if [ -f "$DEFAULTS_SRC" ]; then
    mkdir -p "$CONFIG_DIR"
    cp "$DEFAULTS_SRC" "$CONFIG_DIR/agents-defaults.toml"
    echo -e "${GREEN}  ✓ Installed: $CONFIG_DIR/agents-defaults.toml${NC}"
    cp "$DEFAULTS_SRC" "$HOME/.local/bin/agents-defaults.toml"
    echo -e "${GREEN}  ✓ Installed: ~/.local/bin/agents-defaults.toml${NC}"
fi

# Install built-in sandbox-policy fragments (paranoid/normal/permissive +
# any custom-shipped ones). agent-sandbox loads these via --sandbox-level.
# Fragment search order in the script: ./.agent-sandbox/profiles → ~/.agent-sandbox/profiles → <script-dir>/profiles.
PROFILES_SRC="$SCRIPT_DIR/profiles"
PROFILES_DST="$CONFIG_DIR/profiles"
if [ -d "$PROFILES_SRC" ]; then
    mkdir -p "$PROFILES_DST"
    count=0
    for fragment in "$PROFILES_SRC"/*.toml; do
        [ -f "$fragment" ] || continue
        cp "$fragment" "$PROFILES_DST/"
        count=$((count + 1))
    done
    if [ "$count" -gt 0 ]; then
        echo -e "${GREEN}  ✓ Installed $count sandbox-policy fragment(s) to $PROFILES_DST${NC}"
    fi
fi
echo ""

# ── Step 3: Initialize config ──────────────────────────────────────────
echo -e "${GREEN}[3/5] Setting up configuration...${NC}"

if [ -f "$CONFIG_DST" ]; then
    echo -e "${YELLOW}  Config already exists: $CONFIG_DST${NC}"
    echo "  Run 'agent-sandbox init --force' to reinitialize."
else
    "$INSTALL_DST" init
    echo -e "${GREEN}  ✓ Initialized $CONFIG_DIR${NC}"
fi

# Migration from old claude-sandbox name
if [ -f "$HOME/.local/bin/claude-sandbox" ]; then
    echo -e "${YELLOW}  Removing old claude-sandbox binary...${NC}"
    rm -f "$HOME/.local/bin/claude-sandbox"
fi
if [ -d "$HOME/.claude-sandbox" ] && [ ! -d "$HOME/.agent-sandbox" ]; then
    echo -e "${YELLOW}  Migrating ~/.claude-sandbox/ → ~/.agent-sandbox/...${NC}"
    cp -r "$HOME/.claude-sandbox" "$HOME/.agent-sandbox"
    echo -e "${GREEN}  ✓ Config migrated. You can remove ~/.claude-sandbox/ when ready.${NC}"
fi
echo ""

# ── Step 4: Verify ─────────────────────────────────────────────────────
echo -e "${GREEN}[4/5] Verifying installation...${NC}"

if "$INSTALL_DST" --help >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ agent-sandbox works${NC}"
else
    echo -e "${RED}  ✗ agent-sandbox --help failed${NC}"
    exit 1
fi
echo ""

# ── Step 5: Backend integration ──────────────────────────────────────
echo -e "${GREEN}[5/5] Checking backend integration...${NC}"

# Seatbelt (macOS native)
if [ "$HAS_SEATBELT" = true ]; then
    echo -e "${GREEN}  Seatbelt detected — generating lince profiles...${NC}"
    if "$INSTALL_DST" seatbelt-sync 2>/dev/null; then
        echo -e "${GREEN}  ✓ Seatbelt profiles generated at ~/.agent-sandbox/seatbelt-profiles/lince-*.sb${NC}"
    else
        echo -e "${YELLOW}  ⚠ seatbelt-sync failed (config may not be initialized yet).${NC}"
        echo -e "${YELLOW}    Run 'agent-sandbox seatbelt-sync' after 'agent-sandbox init'.${NC}"
    fi
fi

# nono (deprecated, still supported)
if [ "$HAS_NONO" = true ]; then
    echo -e "${YELLOW}  nono detected (deprecated) — generating lince profiles...${NC}"
    if "$INSTALL_DST" nono-sync 2>/dev/null; then
        echo -e "${GREEN}  ✓ nono profiles generated at ~/.config/nono/profiles/lince-*.json${NC}"
    else
        echo -e "${YELLOW}  ⚠ nono-sync failed (config may not be initialized yet).${NC}"
        echo -e "${YELLOW}    Run 'agent-sandbox nono-sync' after 'agent-sandbox init'.${NC}"
    fi
fi

if [ "$HAS_SEATBELT" = true ]; then
    echo -e "${GREEN}  Backend set to auto (prefers seatbelt on macOS)${NC}"
elif [ "$HAS_BWRAP" = true ]; then
    echo -e "${GREEN}  Backend set to auto (prefers agent-sandbox on Linux)${NC}"
elif [ "$HAS_NONO" = true ]; then
    echo -e "${GREEN}  Backend set to nono (deprecated)${NC}"
else
    echo -e "${YELLOW}  No backend detected${NC}"
fi
echo ""

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Installation Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Command:  $INSTALL_DST"
echo "Config:   $CONFIG_DST"
if [ "$HAS_SEATBELT" = true ]; then
    echo "Backend:  seatbelt (macOS sandbox-exec)"
elif [ "$HAS_BWRAP" = true ]; then
    if [ "$HAS_NONO" = true ]; then
        echo "Backend:  auto (agent-sandbox + nono fallback)"
    else
        echo "Backend:  agent-sandbox (bwrap)"
    fi
elif [ "$HAS_NONO" = true ]; then
    echo "Backend:  nono (deprecated)"
else
    echo "Backend:  (none detected)"
fi
echo ""
echo "Usage:"
echo "  agent-sandbox run              # run with defaults"
echo "  agent-sandbox run -P vertex    # run with a profile"
echo "  agent-sandbox status           # show sandbox status"
if [ "$HAS_SEATBELT" = true ]; then
    echo "  agent-sandbox seatbelt-sync    # regenerate Seatbelt profiles"
fi
if [ "$HAS_NONO" = true ]; then
    echo "  agent-sandbox nono-sync        # regenerate nono profiles (deprecated)"
fi
echo ""
echo "Edit $CONFIG_DST to configure profiles, API keys, and env passthrough."
echo ""
