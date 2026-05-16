#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD_SRC="$SCRIPT_DIR/lince-config"
INSTALL_DST="$HOME/.local/bin/lince-config"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   lince-config — Installer${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────

echo -e "${GREEN}[1/4] Checking prerequisites...${NC}"

command -v python3 >/dev/null 2>&1 || { echo -e "${RED}Missing: python3 (3.11+)${NC}"; exit 1; }

PY_OK=$(python3 -c "import sys; print(1 if sys.version_info >= (3, 11) else 0)" 2>/dev/null || echo 0)
if [ "$PY_OK" = "0" ]; then
    echo -e "${RED}Python 3.11+ required (for tomllib)${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ python3 $(python3 --version 2>&1 | awk '{print $2}')${NC}"

# Check/install tomlkit
python3 -c "import tomlkit" 2>/dev/null || {
    echo -e "${YELLOW}  tomlkit not found. Installing...${NC}"
    _installed=false
    for _pip in "python3 -m pip" pip pip3; do
        if $_pip install --user tomlkit 2>/dev/null; then
            _installed=true
            break
        fi
        if $_pip install --user --break-system-packages tomlkit 2>/dev/null; then
            _installed=true
            break
        fi
    done
    if [ "$_installed" = "false" ]; then
        echo -e "${RED}  All pip attempts failed. Last error:${NC}"
        python3 -m pip install --user --break-system-packages tomlkit || true
        echo "" >&2
        echo -e "${RED}  Install manually:${NC}" >&2
        echo -e "${RED}    python3 -m pip install --user --break-system-packages tomlkit${NC}" >&2
        exit 1
    fi
}
echo -e "${GREEN}  ✓ tomlkit$(python3 -c "import tomlkit; print(' ' + tomlkit.__version__)" 2>/dev/null)${NC}"

# ── Install binary ─────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}[2/4] Installing lince-config...${NC}"

mkdir -p "$(dirname "$INSTALL_DST")"
cp "$CMD_SRC" "$INSTALL_DST"
chmod +x "$INSTALL_DST"
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

if "$INSTALL_DST" --help >/dev/null 2>&1; then
    echo -e "${GREEN}  ✓ lince-config is working${NC}"
else
    echo -e "${RED}  ✗ lince-config --help failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Done! Run 'lince-config --help' to get started.${NC}"
