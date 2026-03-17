#!/usr/bin/env bash
# Run linter/type checker with proper PYTHONPATH
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHONPATH=src python -m pyright src/telebridge "$@"
