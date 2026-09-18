#!/usr/bin/env bash
# Install the Rust WASI target needed by run-plugin-tests.sh.
# This is an explicit developer setup command, never run by the dashboard.
set -euo pipefail
rustup toolchain install stable --profile minimal --component rustfmt --target wasm32-wasip1 --no-self-update
