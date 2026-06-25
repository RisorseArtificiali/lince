#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLI_SRC="$SCRIPT_DIR/lince-lab"
PKG_SRC="$SCRIPT_DIR/lince_lab"
RECIPES_SRC="$SCRIPT_DIR/recipes"
TEMPLATES_SRC="$SCRIPT_DIR/templates"
SKILL_SRC="$SCRIPT_DIR/skills/lince-lab"

INSTALL_DST="$HOME/.local/bin/lince-lab"
BIN_DIR="$(dirname "$INSTALL_DST")"
SHARE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/lince/lince-lab"
SKILL_DST="$HOME/.claude/skills/lince-lab"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/lince-lab"
CONFIG_DST="$CONFIG_DIR/config.toml"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   lince-lab — Installer${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# ── Step 1: Prerequisites ──────────────────────────────────────────────
echo -e "${GREEN}[1/6] Checking prerequisites...${NC}"

command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Missing: python3 (3.11+)${NC}"; exit 1; }

PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)" 2>/dev/null || echo 0)
if [ "$PY_OK" = "0" ]; then
    echo -e "${RED}Python 3.11+ required (for tomllib)${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ python3 $(python3 --version 2>&1 | awk '{print $2}')${NC}"
echo ""

# ── Step 2: Install CLI ────────────────────────────────────────────────
echo -e "${GREEN}[2/6] Installing lince-lab command...${NC}"

mkdir -p "$BIN_DIR"
if [ -f "$INSTALL_DST" ]; then
    echo -e "${YELLOW}  Existing command found, backing up...${NC}"
    cp "$INSTALL_DST" "${INSTALL_DST}.bak.$(date +%Y%m%d-%H%M%S)"
fi
cp "$CLI_SRC" "$INSTALL_DST"
chmod +x "$INSTALL_DST"
echo -e "${GREEN}  ✓ Installed: $INSTALL_DST${NC}"
echo ""

# ── Step 3: Install package + recipes + templates ──────────────────────
echo -e "${GREEN}[3/6] Installing package, recipes, and templates...${NC}"

mkdir -p "$SHARE_DIR"

# Python package — replace cleanly so a removed module never lingers.
rm -rf "$SHARE_DIR/lince_lab"
cp -r "$PKG_SRC" "$SHARE_DIR/lince_lab"
# Drop any bytecode caches carried over from the source tree.
find "$SHARE_DIR/lince_lab" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo -e "${GREEN}  ✓ Package -> $SHARE_DIR/lince_lab${NC}"

if [ -d "$RECIPES_SRC" ]; then
    rm -rf "$SHARE_DIR/recipes"
    cp -r "$RECIPES_SRC" "$SHARE_DIR/recipes"
    echo -e "${GREEN}  ✓ Recipes -> $SHARE_DIR/recipes${NC}"
else
    echo -e "${YELLOW}  ⚠ recipes/ not found — skipping recipe library${NC}"
fi

if [ -d "$TEMPLATES_SRC" ]; then
    rm -rf "$SHARE_DIR/templates"
    cp -r "$TEMPLATES_SRC" "$SHARE_DIR/templates"
    echo -e "${GREEN}  ✓ Templates -> $SHARE_DIR/templates${NC}"
else
    echo -e "${YELLOW}  ⚠ templates/ not found — skipping templates${NC}"
fi

# `ht` (headless terminal) is shipped HOST-SIDE and copied into a guest on demand
# by the broker, so terminal capture (watch / wizard recipe) works on ANY guest —
# even a deny-locked one that cannot fetch it itself. Download is idempotent (skip
# if already present) and NON-FATAL (a failed download only warns).
HT_VER=v0.4.0
HT_URL="https://github.com/andyk/ht/releases/download/${HT_VER}/ht-$(uname -m)-unknown-linux-musl"
mkdir -p "$SHARE_DIR/bin"
if [ ! -x "$SHARE_DIR/bin/ht" ]; then
    if curl -fsSL -o "$SHARE_DIR/bin/ht" "$HT_URL" && chmod +x "$SHARE_DIR/bin/ht"; then
        echo -e "${GREEN}  ✓ ht -> $SHARE_DIR/bin/ht${NC}"
    else
        echo -e "${YELLOW}  ⚠ ht download failed; terminal capture (watch / wizard recipe) will be unavailable until ht is installed${NC}"
    fi
else
    echo -e "${GREEN}  ✓ ht already present -> $SHARE_DIR/bin/ht${NC}"
fi

# macOS/arm64 ht for the Tart (macOS-guest) backend — same role as the Linux ht,
# copied into a macOS guest on demand (Epic #268). Idempotent + non-fatal too.
HT_DARWIN_URL="https://github.com/andyk/ht/releases/download/${HT_VER}/ht-aarch64-apple-darwin"
if [ ! -x "$SHARE_DIR/bin/ht-darwin" ]; then
    if curl -fsSL -o "$SHARE_DIR/bin/ht-darwin" "$HT_DARWIN_URL" && chmod +x "$SHARE_DIR/bin/ht-darwin"; then
        echo -e "${GREEN}  ✓ ht (macOS/arm64) -> $SHARE_DIR/bin/ht-darwin${NC}"
    else
        echo -e "${YELLOW}  ⚠ ht (macOS/arm64) download failed; macOS-backend capture unavailable until present${NC}"
    fi
else
    echo -e "${GREEN}  ✓ ht (macOS/arm64) already present -> $SHARE_DIR/bin/ht-darwin${NC}"
fi
echo ""

# ── Step 4: Install skill ──────────────────────────────────────────────
echo -e "${GREEN}[4/6] Installing Claude skill...${NC}"

if [ -d "$SKILL_SRC" ]; then
    mkdir -p "$SKILL_DST"
    cp -r "$SKILL_SRC/." "$SKILL_DST/"
    echo -e "${GREEN}  ✓ Skill -> $SKILL_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ skills/lince-lab not found — skipping skill install${NC}"
fi
echo ""

# ── Step 5: Initialize config (only if absent) ─────────────────────────
echo -e "${GREEN}[5/6] Setting up configuration...${NC}"

if [ -f "$CONFIG_DST" ]; then
    echo -e "${YELLOW}  Config already exists: $CONFIG_DST (left untouched)${NC}"
else
    mkdir -p "$CONFIG_DIR"
    cat > "$CONFIG_DST" <<'EOF'
# lince-lab configuration (optional — sane defaults are baked into the CLI).
# Anything you set here overlays those defaults. The security invariants
# (no host mounts, no host-credential injection, lince-lab-* VM name prefix)
# live in the broker's policy layer, NOT here, and cannot be weakened.

# Host-side broker unix socket the CLI talks to.
socket_path = "~/.agent-sandbox/lince-lab.sock"

# Default terminal grid for capture/watch (cols x rows).
grid_size = "80x24"

# Keep disposable VMs around after a run for debugging (default: false).
keep_vm = false

# Headless-terminal capture tool driven inside the VM.
capture_tool = "ht"

[vm]
# Default resource caps; a recipe may request its own within policy.
cpus = 2
memory = "2GiB"
disk = "20GiB"

[network]
# Deny-by-default egress. A recipe must carry an explicit allowlist to fetch.
mode = "deny"
EOF
    echo -e "${GREEN}  ✓ Wrote default config: $CONFIG_DST${NC}"
fi
echo ""

# ── Step 6: PATH check + verify ────────────────────────────────────────
echo -e "${GREEN}[6/6] Checking PATH and verifying...${NC}"

case ":$PATH:" in
    *":$BIN_DIR:"*)
        echo -e "${GREEN}  ✓ $BIN_DIR is in PATH${NC}"
        ;;
    *)
        echo -e "${YELLOW}  ⚠ $BIN_DIR is not in PATH.${NC}"
        echo -e "${YELLOW}    Add it to your shell profile:${NC}"
        echo -e "${YELLOW}      export PATH=\"$BIN_DIR:\$PATH\"${NC}"
        ;;
esac

if "$INSTALL_DST" --help >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ lince-lab is working (installed-mode import resolved)${NC}"
else
    echo -e "${RED}  ✗ lince-lab --help failed${NC}"
    exit 1
fi
echo ""

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Installation Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Command:   $INSTALL_DST"
echo "Package:   $SHARE_DIR/lince_lab"
echo "Recipes:   $SHARE_DIR/recipes"
echo "Config:    $CONFIG_DST"
echo ""
echo "Get started:"
echo "  lince-lab --help"
echo "  lince-lab run presets"
echo ""
