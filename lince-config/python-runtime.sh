#!/usr/bin/env bash
# Select one Python runtime for dependency checks, installation, and command binding.

python_runtime_is_compatible() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1
}

python_runtime_has_pip() {
    "$1" -m pip --version >/dev/null 2>&1
}

select_lince_config_python() {
    local managed_python="$HOME/.local/share/lince/python/bin/python3"
    local selected="${LINCE_PYTHON_CMD:-}"

    if [ -z "$selected" ] && [ -x "$managed_python" ] && \
       python_runtime_is_compatible "$managed_python" && python_runtime_has_pip "$managed_python"; then
        selected="$managed_python"
    elif [ -z "$selected" ]; then
        selected="$(command -v python3 2>/dev/null || true)"
    fi

    if [ -z "$selected" ] || [ ! -x "$selected" ]; then
        echo -e "${RED}Missing: python3 (3.11+)${NC}" >&2
        return 1
    fi
    if ! python_runtime_is_compatible "$selected"; then
        echo -e "${RED}Python 3.11+ required (for tomllib)${NC}" >&2
        return 1
    fi

    LINCE_CONFIG_PYTHON="$selected"
    LINCE_CONFIG_USE_MANAGED=false
    if [ "$selected" = "$managed_python" ]; then
        LINCE_CONFIG_USE_MANAGED=true
    fi
    export LINCE_CONFIG_PYTHON LINCE_CONFIG_USE_MANAGED
}
