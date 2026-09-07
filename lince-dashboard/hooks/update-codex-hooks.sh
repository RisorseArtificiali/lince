#!/usr/bin/env bash
# update-codex-hooks.sh — Refresh Codex lifecycle and notify integration.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "$SCRIPT_DIR/install-codex-hooks.sh"
