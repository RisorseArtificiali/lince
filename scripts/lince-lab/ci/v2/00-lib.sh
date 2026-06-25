#!/usr/bin/env bash
#
# v2/00-lib.sh — shared library for the lince-lab v2 (macOS/Seatbelt) oracle chain.
#
# Sources the v1 lib for the assert helpers + start_broker + path resolution, and
# adds skip_if_not_macos: the v2 analogue of skip_if_no_kvm. VM-dependent v2
# oracles call it FIRST so the whole chain is green-or-skipped off a macOS host.
#
# This file is a library: it is meant to be *sourced*, not executed.

set -e

_V2_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../00-lib.sh
source "$_V2_DIR/../00-lib.sh"

# ── skip guard (the v2 analogue of skip_if_no_kvm) ───────────────────────────
# Skip cleanly unless we are on an Apple-Silicon macOS host with tart installed.
# Logs the exact phrase the epic mandates ("skipped: not macOS") and exits 0, so
# the v2 chain stays green-or-skipped on a Linux CI host (where v1 runs instead).
skip_if_not_macos() {
    local reason=""
    if [ "$(uname -s)" != "Darwin" ]; then
        reason="uname -s != Darwin"
    elif [ "$(uname -m)" != "arm64" ]; then
        reason="uname -m != arm64 (not Apple Silicon)"
    elif ! command -v tart >/dev/null 2>&1; then
        reason="tart not installed (macOS backend unavailable)"
    fi
    if [ -n "$reason" ]; then
        echo -e "${YELLOW}skipped: not macOS${NC} ($reason)"
        exit 0
    fi
    return 0
}
