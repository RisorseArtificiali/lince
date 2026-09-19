#!/usr/bin/env bash
# Install the dashboard WASM from a verified release asset or an explicit source build.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_BASE_URL="${LINCE_RELEASE_BASE_URL:-https://github.com/RisorseArtificiali/lince/releases/latest/download}"
PLUGIN_DIR="$HOME/.config/zellij/plugins"
PLUGIN_DST="$PLUGIN_DIR/lince-dashboard.wasm"
BUILD_FROM_SOURCE=false
WORK_DIR=""
STAGED=""

for arg in "$@"; do
    case "$arg" in
        --build-from-source) BUILD_FROM_SOURCE=true ;;
        --help|-h)
            echo "Usage: $0 [--build-from-source]"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

cleanup() {
    if [ -n "$WORK_DIR" ] && [ -d "$WORK_DIR" ]; then
        rm -rf "$WORK_DIR"
    fi
    if [ -n "$STAGED" ] && [ -f "$STAGED" ]; then
        rm -f "$STAGED"
    fi
}
trap cleanup EXIT

verify_checksum() {
    local artifact="$1"
    local expected="$2"
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s  %s\n' "$expected" "$artifact" | sha256sum --check --status -
    elif command -v shasum >/dev/null 2>&1; then
        printf '%s  %s\n' "$expected" "$artifact" | shasum -a 256 --check - >/dev/null
    else
        echo "ERROR: sha256sum or shasum is required to verify the dashboard plugin." >&2
        return 1
    fi
}

fetch_release_plugin() {
    local artifact="$1"
    local checksum_file expected
    checksum_file="$WORK_DIR/SHA256SUMS"

    echo "Downloading the latest prebuilt dashboard plugin..."
    curl --fail --location --silent --show-error \
        --output "$artifact" "$RELEASE_BASE_URL/lince-dashboard.wasm" || return 1
    curl --fail --location --silent --show-error \
        --output "$checksum_file" "$RELEASE_BASE_URL/SHA256SUMS" || return 1

    expected="$(awk '$2 == "lince-dashboard.wasm" || $2 == "*lince-dashboard.wasm" { print $1; exit }' "$checksum_file")"
    if [ "${#expected}" -ne 64 ] || ! printf '%s\n' "$expected" | grep -Eq '^[0-9a-fA-F]{64}$'; then
        echo "ERROR: SHA256SUMS has no valid checksum for lince-dashboard.wasm." >&2
        return 1
    fi
    if ! verify_checksum "$artifact" "$expected"; then
        echo "ERROR: checksum verification failed for lince-dashboard.wasm." >&2
        return 1
    fi
}

unique_backup_path() {
    local base candidate suffix
    base="$PLUGIN_DST.bak.$(date +%Y%m%d-%H%M%S)"
    candidate="$base"
    suffix=1
    while [ -e "$candidate" ]; do
        candidate="$base-$suffix"
        suffix=$((suffix + 1))
    done
    printf '%s\n' "$candidate"
}

if [ "$BUILD_FROM_SOURCE" = true ]; then
    echo "Building dashboard plugin from source..."
    if ! "$SCRIPT_DIR/plugin/build.sh"; then
        echo "ERROR: dashboard plugin source build failed." >&2
        exit 1
    fi
    PLUGIN_SRC="$SCRIPT_DIR/plugin/lince-dashboard.wasm"
else
    WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/lince-plugin.XXXXXX")"
    PLUGIN_SRC="$WORK_DIR/lince-dashboard.wasm"
    if ! fetch_release_plugin "$PLUGIN_SRC"; then
        echo "ERROR: could not install the prebuilt dashboard plugin." >&2
        echo "Retry later, or re-run the dashboard installer with: ./install.sh --build-from-source" >&2
        exit 1
    fi
fi

if [ ! -f "$PLUGIN_SRC" ]; then
    echo "ERROR: dashboard plugin artifact not found: $PLUGIN_SRC" >&2
    exit 1
fi

mkdir -p "$PLUGIN_DIR"
STAGED="$PLUGIN_DIR/.lince-dashboard.wasm.new.$$"
cp "$PLUGIN_SRC" "$STAGED"
if [ -f "$PLUGIN_DST" ]; then
    BACKUP="$(unique_backup_path)"
    cp "$PLUGIN_DST" "$BACKUP"
    echo "Existing plugin backed up to: $BACKUP"
fi
mv "$STAGED" "$PLUGIN_DST"
STAGED=""
echo "Installed dashboard plugin: $PLUGIN_DST"
