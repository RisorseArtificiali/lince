#!/usr/bin/env bash
# Format code with ruff
set -euo pipefail

cd "$(dirname "$0")/.."

ruff format src/
ruff check src/ --fix "$@"
