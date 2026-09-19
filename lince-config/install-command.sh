#!/usr/bin/env bash
# Install the lince-config command against the bootstrap-managed Python when present.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/lince-config"
DEST="$HOME/.local/bin/lince-config"
MANAGED_PYTHON="$HOME/.local/share/lince/python/bin/python3"
: "${LINCE_CONFIG_PYTHON:?LINCE_CONFIG_PYTHON must select the verified interpreter}"
: "${LINCE_CONFIG_USE_MANAGED:?LINCE_CONFIG_USE_MANAGED must describe the selected interpreter}"

mkdir -p "$(dirname "$DEST")"
DEST_NEW="${DEST}.new.$$"
PYTHON_SHIM_NEW=""

cleanup() {
    [ -z "$DEST_NEW" ] || rm -f "$DEST_NEW"
    [ -z "$PYTHON_SHIM_NEW" ] || rm -f "$PYTHON_SHIM_NEW"
}
trap cleanup EXIT

if [ "$LINCE_CONFIG_USE_MANAGED" = true ]; then
    PYTHON_SHIM="$HOME/.local/bin/lince-python"
    PYTHON_SHIM_NEW="${PYTHON_SHIM}.new.$$"
    cat > "$PYTHON_SHIM_NEW" <<'SHIM'
#!/bin/sh
# Managed by LINCE for the standalone bootstrap interpreter.
managed_python="$HOME/.local/share/lince/python/bin/python3"
if [ ! -x "$managed_python" ]; then
    echo "lince: managed Python is missing; re-run the LINCE installer" >&2
    exit 1
fi
export PATH="$HOME/.local/share/lince/python/bin:$PATH"
exec "$managed_python" "$@"
SHIM
    chmod 755 "$PYTHON_SHIM_NEW"
    mv "$PYTHON_SHIM_NEW" "$PYTHON_SHIM"
    PYTHON_SHIM_NEW=""

    {
        printf '%s\n' '#!/usr/bin/env lince-python'
        tail -n +2 "$SOURCE"
    } > "$DEST_NEW"
else
    cp "$SOURCE" "$DEST_NEW"
fi

chmod 755 "$DEST_NEW"
mv "$DEST_NEW" "$DEST"
DEST_NEW=""
trap - EXIT
