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
CONFIG_DST="$HOME/.agent-sandbox/config.toml"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   agent-sandbox — Update${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# ── Step 1: Update command ─────────────────────────────────────────────
echo -e "${GREEN}[1/2] Updating agent-sandbox command...${NC}"

if [ ! -f "$INSTALL_DST" ]; then
    echo -e "${YELLOW}  Not installed — run install.sh first${NC}"
    exit 1
fi

cp "$SANDBOX_CMD" "$INSTALL_DST"
cp "$SCRIPT_DIR/mount_masking.py" "$HOME/.local/bin/mount_masking.py"
chmod +x "$INSTALL_DST"
echo -e "${GREEN}  ✓ Command updated${NC}"

# Update the unified agent registry (Config v2, #204). Shipped data —
# always overwritten (#199); custom agents never live here.
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

# Legacy agents-defaults.toml — kept during the Config v2 dual-read window so
# not-yet-updated consumers keep working; agent-sandbox itself now prefers
# the registry.
DEFAULTS_SRC="$SCRIPT_DIR/agents-defaults.toml"
if [ -f "$DEFAULTS_SRC" ]; then
    cp "$DEFAULTS_SRC" "$HOME/.agent-sandbox/agents-defaults.toml"
    echo -e "${GREEN}  ✓ Agent defaults updated: ~/.agent-sandbox/agents-defaults.toml (legacy)${NC}"
fi
# Remove the stale double-install location (#204).
if [ -f "$HOME/.local/bin/agents-defaults.toml" ]; then
    rm -f "$HOME/.local/bin/agents-defaults.toml"
    echo -e "${GREEN}  ✓ Removed stale ~/.local/bin/agents-defaults.toml${NC}"
fi

# Update built-in sandbox-policy fragments. New fragments shipped with this
# release land in ~/.agent-sandbox/profiles/ where agent-sandbox finds them
# via its --sandbox-level flag.
PROFILES_SRC="$SCRIPT_DIR/profiles"
PROFILES_DST="$HOME/.agent-sandbox/profiles"
if [ -d "$PROFILES_SRC" ]; then
    mkdir -p "$PROFILES_DST"
    count=0
    for fragment in "$PROFILES_SRC"/*.toml; do
        [ -f "$fragment" ] || continue
        cp "$fragment" "$PROFILES_DST/"
        count=$((count + 1))
    done
    if [ "$count" -gt 0 ]; then
        echo -e "${GREEN}  ✓ Sandbox-policy fragments updated: $count file(s) in $PROFILES_DST${NC}"
    fi
fi
echo ""

# ── Step 2: Ensure env passthrough ─────────────────────────────────────
echo -e "${GREEN}[2/3] Checking env passthrough...${NC}"

# Required vars for lince-dashboard integration and terminal tools
REQUIRED_VARS=("ZELLIJ" "ZELLIJ_SESSION_NAME" "LINCE_AGENT_ID")

if [ ! -f "$CONFIG_DST" ]; then
    echo -e "${YELLOW}  No config found — run install.sh first${NC}"
    echo ""
    echo -e "${GREEN}Update complete (command only).${NC}"
    exit 0
fi

# Check which vars are missing from passthrough
MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if ! python3 -c "
import tomllib, sys
with open(sys.argv[1], 'rb') as f:
    cfg = tomllib.load(f)
sys.exit(0 if sys.argv[2] in cfg.get('env', {}).get('passthrough', []) else 1)
" "$CONFIG_DST" "$var" 2>/dev/null; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -eq 0 ]; then
    echo -e "${GREEN}  ✓ Passthrough already configured${NC}"
else
    echo -e "${YELLOW}  Adding env passthrough for: ${MISSING_VARS[*]}${NC}"

    # Pass missing vars as arguments to Python
    python3 - "$CONFIG_DST" "${MISSING_VARS[@]}" << 'PYEOF'
import tomllib, sys, re

config_path = sys.argv[1]
missing = sys.argv[2:]

with open(config_path, "rb") as f:
    cfg = tomllib.load(f)

existing = list(cfg.get("env", {}).get("passthrough", []))
new_list = existing + [v for v in missing if v not in existing]
vals = ", ".join(f'"{v}"' for v in new_list)
new_line = f"passthrough = [{vals}]"

with open(config_path) as f:
    content = f.read()

if "passthrough" in content:
    content = re.sub(r'passthrough\s*=\s*\[.*?\]', new_line, content, flags=re.DOTALL)
elif "[env]" in content:
    content = content.replace("[env]", f"[env]\n{new_line}")
else:
    content += f"\n[env]\n{new_line}\n"

with open(config_path, "w") as f:
    f.write(content)
PYEOF

    echo -e "${GREEN}  ✓ Passthrough updated${NC}"
fi
echo ""

# ── Step 3: nono profile sync ─────────────────────────────────────────
echo -e "${GREEN}[3/3] Checking nono integration...${NC}"

if command -v nono >/dev/null 2>&1; then
    echo "  nono detected — regenerating lince profiles..."
    if "$INSTALL_DST" nono-sync 2>/dev/null; then
        echo -e "${GREEN}  ✓ nono profiles updated${NC}"
    else
        echo -e "${YELLOW}  ⚠ nono-sync failed (run manually: agent-sandbox nono-sync)${NC}"
    fi
    # macOS: check for nono updates
    if [ "$(uname -s)" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
        if brew outdated nono 2>/dev/null | grep -q nono; then
            echo -e "${YELLOW}  ⚠ nono update available: brew upgrade nono${NC}"
        fi
    fi
else
    echo -e "${YELLOW}  nono not installed — skipping profile sync${NC}"
fi
echo ""

echo -e "${GREEN}Update complete.${NC}"
echo ""
