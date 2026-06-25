#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CLI_SRC="$SCRIPT_DIR/lince-lab"
PKG_SRC="$SCRIPT_DIR/lince_lab"
RECIPES_SRC="$SCRIPT_DIR/recipes"
TEMPLATES_SRC="$SCRIPT_DIR/templates"
SKILL_SRC="$SCRIPT_DIR/skills/lince-lab"

INSTALL_DST="$HOME/.local/bin/lince-lab"
SHARE_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/lince/lince-lab"
SKILL_DST="$HOME/.claude/skills/lince-lab"

echo "Updating lince-lab..."

# Prerequisites — same check as install.sh so an update never leaves a broken
# install behind a Python downgrade.
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Missing: python3 (3.11+)${NC}"; exit 1; }

PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)" 2>/dev/null || echo 0)
if [ "$PY_OK" = "0" ]; then
    echo -e "${RED}Python 3.11+ required (for tomllib)${NC}"
    exit 1
fi

# CLI
mkdir -p "$(dirname "$INSTALL_DST")"
cp "$CLI_SRC" "$INSTALL_DST"
chmod +x "$INSTALL_DST"
echo -e "${GREEN}  ✓ Updated $INSTALL_DST${NC}"

# Package + recipes + templates (config is NEVER overwritten by update).
mkdir -p "$SHARE_DIR"
rm -rf "$SHARE_DIR/lince_lab"
cp -r "$PKG_SRC" "$SHARE_DIR/lince_lab"
find "$SHARE_DIR/lince_lab" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo -e "${GREEN}  ✓ Updated $SHARE_DIR/lince_lab${NC}"

if [ -d "$RECIPES_SRC" ]; then
    rm -rf "$SHARE_DIR/recipes"
    cp -r "$RECIPES_SRC" "$SHARE_DIR/recipes"
    echo -e "${GREEN}  ✓ Updated $SHARE_DIR/recipes${NC}"
fi

if [ -d "$TEMPLATES_SRC" ]; then
    rm -rf "$SHARE_DIR/templates"
    cp -r "$TEMPLATES_SRC" "$SHARE_DIR/templates"
    echo -e "${GREEN}  ✓ Updated $SHARE_DIR/templates${NC}"
fi

# `ht` (headless terminal) ships HOST-SIDE and is copied into a guest on demand by
# the broker so terminal capture works on ANY guest. Download is idempotent (skip
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

# Skill
if [ -d "$SKILL_SRC" ]; then
    mkdir -p "$SKILL_DST"
    cp -r "$SKILL_SRC/." "$SKILL_DST/"
    echo -e "${GREEN}  ✓ Updated $SKILL_DST${NC}"
else
    echo -e "${YELLOW}  ⚠ skills/lince-lab not found — skill not updated${NC}"
fi

echo -e "${GREEN}Done. lince-lab updated (config left untouched).${NC}"
