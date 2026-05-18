#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure rustup toolchain takes precedence over system Rust (e.g. Homebrew).
# ~/.cargo/bin holds the rustup proxy shims; if missing, rustup may not have
# been fully initialized (the shims are needed so cargo spawns the right rustc).
export PATH="$HOME/.cargo/bin:$PATH"

TARGET="wasm32-wasip1"
OUTPUT="$SCRIPT_DIR/lince-dashboard.wasm"

# Resolve the actual cargo binary via rustup — on macOS, bare `cargo` may
# resolve to Homebrew's standalone cargo which cannot see rustup-installed
# targets.  Using the explicit path guarantees the rustup-managed toolchain.
CARGO_BIN=""
if command -v rustup >/dev/null 2>&1; then
    CARGO_BIN="$(rustup which cargo 2>/dev/null || true)"
fi
if [ -z "$CARGO_BIN" ] || [ ! -x "$CARGO_BIN" ]; then
    # Fallback: try PATH resolution
    CARGO_BIN="$(command -v cargo 2>/dev/null || true)"
fi
if [ -z "$CARGO_BIN" ]; then
    echo "ERROR: cargo not found." >&2
    exit 1
fi

# On macOS, cargo spawns rustc as a subprocess.  If the rustup proxy shims
# are missing from ~/.cargo/bin, the child rustc resolves to Homebrew's copy
# which lacks the wasm32-wasip1 sysroot.  Detect this and bail early with a
# clear fix message.
if [ "$(uname -s)" = "Darwin" ] && [ -n "$CARGO_BIN" ]; then
    TOOLCHAIN_BIN="$(dirname "$CARGO_BIN")"
    # Prepend the toolchain's bin dir so cargo's child rustc invocations
    # pick up the correct (rustup-managed) rustc, even if ~/.cargo/bin
    # proxy shims are absent.
    export PATH="$TOOLCHAIN_BIN:$PATH"
fi

# Verify the resolved cargo is rustup-managed (Homebrew's standalone cargo
# cannot see wasm32-wasip1 targets).  The path itself is the most reliable
# indicator: `rustup which cargo` always resolves under ~/.rustup/toolchains/.
if [ "$(uname -s)" = "Darwin" ]; then
    if [ -n "$CARGO_BIN" ] && ! echo "$CARGO_BIN" | grep -q "rustup"; then
        echo "ERROR: resolved cargo ($CARGO_BIN) is not rustup-managed." >&2
        echo "  Homebrew's standalone cargo cannot build wasm32-wasip1 targets." >&2
        echo "" >&2
        echo "  Fix: ensure the rustup toolchain is active:" >&2
        echo "    rustup default stable" >&2
        echo "    source ~/.cargo/env" >&2
        echo "" >&2
        echo "  Then verify: rustup which cargo" >&2
        exit 1
    fi
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
