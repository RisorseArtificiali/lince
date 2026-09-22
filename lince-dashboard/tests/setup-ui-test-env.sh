#!/usr/bin/env bash
# Optional terminal emulator for observing actual Zellij plugin rendering.
set -euo pipefail
if [[ $# != 1 ]]; then
    echo 'Usage: setup-ui-test-env.sh VENV_DIRECTORY' >&2
    exit 2
fi
python3 -m venv "$1"
"$1/bin/python" -m pip install 'pyte==0.8.2'
