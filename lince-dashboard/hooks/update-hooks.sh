#!/usr/bin/env bash
# update-hooks.sh — Refresh all agent-platform hook integrations.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/update-claude-hooks.sh"
echo ""
bash "$SCRIPT_DIR/update-codex-hooks.sh"
echo ""
bash "$SCRIPT_DIR/update-bob-hooks.sh"
echo ""
bash "$SCRIPT_DIR/update-opencode-hooks.sh"
echo ""
bash "$SCRIPT_DIR/update-pi-hooks.sh"
