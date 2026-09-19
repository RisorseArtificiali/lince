#!/usr/bin/env bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DST="$HOME/.local/bin/lince-config"

# shellcheck source=python-runtime.sh
source "$SCRIPT_DIR/python-runtime.sh"

echo "Updating lince-config..."

# Prerequisites — same checks as install.sh, so a Python downgrade or a missing
# tomlkit doesn't leave a broken install.
select_lince_config_python

"$LINCE_CONFIG_PYTHON" -c "import tomlkit" 2>/dev/null || {
    echo -e "${YELLOW}tomlkit not found. Installing...${NC}"
    if ! "$LINCE_CONFIG_PYTHON" -m pip install --user tomlkit 2>/dev/null &&
       ! "$LINCE_CONFIG_PYTHON" -m pip install --user --break-system-packages tomlkit 2>/dev/null; then
        echo -e "${RED}Failed to install tomlkit. Install manually:${NC}"
        echo -e "${RED}  $LINCE_CONFIG_PYTHON -m pip install --user tomlkit${NC}"
        exit 1
    fi
}

bash "$SCRIPT_DIR/install-command.sh"
echo -e "${GREEN}Done. Updated $INSTALL_DST${NC}"
