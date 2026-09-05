#!/usr/bin/env bash
# install-hooks.sh — Backward-compatible wrapper for agent-platform hook installers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/install-claude-hooks.sh"
echo ""
bash "$SCRIPT_DIR/install-codex-hooks.sh"
echo ""
bash "$SCRIPT_DIR/install-bob-hooks.sh"
echo ""
bash "$SCRIPT_DIR/install-opencode-hooks.sh"
echo ""
bash "$SCRIPT_DIR/install-pi-hooks.sh"
