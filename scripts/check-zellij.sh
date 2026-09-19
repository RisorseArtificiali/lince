#!/usr/bin/env bash
# Minimum supported runtime: includes the Codex scrollback fixes (#4941, #5357).
# Keep this check in sync with the standalone bootstrap in docs/install.
check_zellij_version() {
    local detected
    detected=$(zellij --version 2>/dev/null) || detected="unavailable"
    if printf '%s\n' "$detected" | awk '
        /^zellij [0-9]+\.[0-9]+\.[0-9]+$/ {
            split($2, v, ".")
            ok = (v[1] > 0 || v[2] > 45 || (v[2] == 45 && v[3] >= 1))
        }
        END { exit !ok }
    '; then
        printf '%s\n' "$detected"
        return 0
    fi
    printf 'Zellij >= 0.45.1 required for reliable Codex scrollback (found: %s).\n' "$detected" >&2
    printf 'Install/upgrade: https://github.com/zellij-org/zellij/releases (then restart Zellij).\n' >&2
    return 1
}
