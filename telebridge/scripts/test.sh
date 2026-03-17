#!/usr/bin/env bash
# Run tests with proper PYTHONPATH
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=src python -m pytest tests/ "$@"
