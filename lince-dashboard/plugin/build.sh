#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure rustup toolchain takes precedence over system Rust
export PATH="$HOME/.cargo/bin:$PATH"

TARGET="wasm32-wasip1"
OUTPUT="$SCRIPT_DIR/lince-dashboard.wasm"

# Resolve the actual cargo and rustc binaries via rustup — on macOS, bare
# `cargo`/`rustc` may resolve to Homebrew's standalone binaries which cannot
# see rustup-installed targets.  Using explicit paths + RUSTC env var
# guarantees the rustup-managed toolchain is used for both.
CARGO_BIN=""
RUSTC_BIN=""
if command -v rustup >/dev/null 2>&1; then
    CARGO_BIN="$(rustup which cargo 2>/dev/null || true)"
    RUSTC_BIN="$(rustup which rustc 2>/dev/null || true)"
fi

# On macOS, Homebrew provides standalone rustc/cargo that cannot see
# rustup-installed targets.  If rustup didn't resolve cargo, refuse to
# fall back to a potentially-Homebrew binary — fail with remediation
# steps instead of producing a cryptic "can't find crate for `core`".
if [ -z "$CARGO_BIN" ] || [ ! -x "$CARGO_BIN" ]; then
    if [ "$(uname -s)" = "Darwin" ]; then
        echo "ERROR: could not resolve a rustup-managed cargo." >&2
        echo "  Homebrew's standalone cargo cannot build wasm32-wasip1 targets." >&2
        echo "" >&2
        echo "  Fix: ensure the rustup toolchain is active:" >&2
        echo "    rustup default stable" >&2
        echo "    source ~/.cargo/env" >&2
        echo "" >&2
        echo "  Then verify: rustup which cargo" >&2
        exit 1
    fi
    # Linux: safe to fall back to PATH resolution (no Homebrew conflict)
    CARGO_BIN="$(command -v cargo 2>/dev/null || true)"
fi
if [ -z "$CARGO_BIN" ]; then
    echo "ERROR: cargo not found." >&2
    exit 1
fi
# Force cargo to use the rustup-managed rustc, not whatever is in PATH.
if [ -n "$RUSTC_BIN" ] && [ -x "$RUSTC_BIN" ]; then
    export RUSTC="$RUSTC_BIN"
fi

# Check target
if ! rustup target list --installed 2>/dev/null | grep -q "$TARGET"; then
    echo "Installing $TARGET target..."
    rustup target add "$TARGET"
    if ! rustup target list --installed 2>/dev/null | grep -q "$TARGET"; then
        echo "ERROR: failed to install $TARGET target." >&2
        exit 1
    fi
fi

echo "Building lince-dashboard plugin..."
echo "  Using cargo: $CARGO_BIN"
echo "  Using rustc: ${RUSTC:-$(command -v rustc)}"
"$CARGO_BIN" build --release --target "$TARGET"

# Binary target: output uses hyphens (lince-dashboard), not underscores
ARTIFACT="$SCRIPT_DIR/target/$TARGET/release/lince-dashboard.wasm"
if [ ! -f "$ARTIFACT" ]; then
    echo "ERROR: Build artifact not found at $ARTIFACT" >&2
    exit 1
fi

cp "$ARTIFACT" "$OUTPUT"
SIZE=$(stat --format=%s "$OUTPUT" 2>/dev/null || stat -f%z "$OUTPUT" 2>/dev/null)
echo "Built: $OUTPUT ($(( SIZE / 1024 )) KB)"
