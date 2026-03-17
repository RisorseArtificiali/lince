#!/usr/bin/env bash
# Run the telebridge bot with proper PYTHONPATH
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=src python -m telebridge.cli "$@"
