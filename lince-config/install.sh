#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DST="$HOME/.local/bin/lince-config"

# shellcheck source=python-runtime.sh
source "$SCRIPT_DIR/python-runtime.sh"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   lince-config — Installer${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────

echo -e "${GREEN}[1/4] Checking prerequisites...${NC}"

select_lince_config_python
echo -e "${GREEN}  ✓ python3 $("$LINCE_CONFIG_PYTHON" --version 2>&1 | awk '{print $2}')${NC}"

# Check/install tomlkit
"$LINCE_CONFIG_PYTHON" -c "import tomlkit" 2>/dev/null || {
    echo -e "${YELLOW}  tomlkit not found. Installing...${NC}"
    if ! "$LINCE_CONFIG_PYTHON" -m pip install --user tomlkit 2>/dev/null &&
       ! "$LINCE_CONFIG_PYTHON" -m pip install --user --break-system-packages tomlkit 2>/dev/null; then
        echo -e "${RED}  Failed to install tomlkit. Install manually:${NC}"
        echo -e "${RED}    $LINCE_CONFIG_PYTHON -m pip install --user tomlkit${NC}"
        exit 1
    fi
}
echo -e "${GREEN}  ✓ tomlkit$("$LINCE_CONFIG_PYTHON" -c "import tomlkit; print(' ' + tomlkit.__version__)" 2>/dev/null)${NC}"

# ── Install binary ─────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}[2/4] Installing lince-config...${NC}"

bash "$SCRIPT_DIR/install-command.sh"
echo -e "${GREEN}  ✓ Installed to $INSTALL_DST${NC}"

# ── PATH check ─────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}[3/4] Checking PATH...${NC}"

BIN_DIR="$(dirname "$INSTALL_DST")"
case ":$PATH:" in
    *":$BIN_DIR:"*) echo -e "${GREEN}  ✓ $BIN_DIR is in PATH${NC}" ;;
    *)
        echo -e "${YELLOW}  $BIN_DIR is not in PATH.${NC}"
        echo -e "${YELLOW}  Add it to your shell profile:${NC}"
        echo -e "${YELLOW}    export PATH=\"$BIN_DIR:\$PATH\"${NC}"
        ;;
esac

# ── Verify ─────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}[4/4] Verifying...${NC}"

if PATH="$HOME/.local/bin:$PATH" "$INSTALL_DST" --help >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ lince-config is working${NC}"
else
    echo -e "${RED}  ✗ lince-config --help failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Done! Run 'lince-config --help' to get started.${NC}"
