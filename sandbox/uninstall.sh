#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DST="$HOME/.local/bin/agent-sandbox"
CONFIG_DIR="$HOME/.agent-sandbox"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   agent-sandbox — Uninstaller${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# ── Command ────────────────────────────────────────────────────────────
if [ -f "$INSTALL_DST" ]; then
    echo -e "${YELLOW}Found: $INSTALL_DST${NC}"
    if confirm "  Remove command?"; then
        rm -f "$INSTALL_DST" "${INSTALL_DST}.bak."*
        rm -f "$HOME/.local/bin/agents-defaults.toml"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Command not found — skipping"
fi

# ── Old claude-sandbox binary ─────────────────────────────────────────
if [ -f "$HOME/.local/bin/claude-sandbox" ]; then
    echo -e "${YELLOW}Found old binary: $HOME/.local/bin/claude-sandbox${NC}"
    if confirm "  Remove old claude-sandbox binary?"; then
        rm -f "$HOME/.local/bin/claude-sandbox"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
fi
echo ""

# ── Config directory ───────────────────────────────────────────────────
if [ -d "$CONFIG_DIR" ]; then
    echo -e "${YELLOW}Found: $CONFIG_DIR${NC}"
    echo -e "${RED}  WARNING: This contains your config and logs.${NC}"
    if confirm "  Remove entire config directory?"; then
        rm -rf "$CONFIG_DIR"
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  Config directory not found — skipping"
fi
echo ""

# ── nono profiles ─────────────────────────────────────────────────────
NONO_PROFILES=$(ls "$HOME/.config/nono/profiles/lince-"*.json 2>/dev/null || true)
if [ -n "$NONO_PROFILES" ]; then
    echo -e "${YELLOW}Found generated nono profiles:${NC}"
    for p in $NONO_PROFILES; do
        echo "  $p"
    done
    if confirm "  Remove generated lince-* nono profiles?"; then
        rm -f "$HOME/.config/nono/profiles/lince-"*.json
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
    echo ""
    echo -e "${YELLOW}NOTE: nono itself was NOT removed (you may use it independently).${NC}"
else
    echo "  No generated nono profiles found — skipping"
fi
echo ""

# ── Seatbelt profiles ─────────────────────────────────────────────────
SEATBELT_PROFILES=$(ls "$HOME/.agent-sandbox/seatbelt-profiles/lince-"*.sb 2>/dev/null || true)
if [ -n "$SEATBELT_PROFILES" ]; then
    echo -e "${YELLOW}Found generated Seatbelt profiles:${NC}"
    for p in $SEATBELT_PROFILES; do
        echo "  $p"
    done
    if confirm "  Remove generated lince-* Seatbelt profiles?"; then
        rm -f "$HOME/.agent-sandbox/seatbelt-profiles/lince-"*.sb
        echo -e "${GREEN}  ✓ Removed${NC}"
    fi
else
    echo "  No generated Seatbelt profiles found — skipping"
fi
echo ""

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Uninstall Complete${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo "Source files in sandbox/ were NOT removed."
echo "To reinstall later: cd sandbox && ./install.sh"
echo ""
