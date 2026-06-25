#!/usr/bin/env bash
#
# v2/01-macos-guest.sh — sub-issue #263 oracle (Epic #268).
#
# macOS-guest adapter foundation. Asserts the real MacosBackend (Tart) glue
# against a live macOS guest: a VM can be created + started from the macos-sequoia
# image, `sw_vers` runs in the guest (proving it is macOS), the guest exit code
# propagates (the bisect signal), and the VM tears down. Skips cleanly (exit 0)
# off an Apple-Silicon macOS host so the Linux chain stays green.
#
# Exit 0 only on success → trigger oracle for #264 and #265.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=00-lib.sh
source "$SCRIPT_DIR/00-lib.sh"

oracle_header "v2/01 macos-guest (#263)"

# VM-dependent: skip cleanly off a macOS/Apple-Silicon host.
skip_if_not_macos

VM="lince-lab-v2ci01-$$"
SOCK="$LINCE_LAB_SOCK"

cleanup() {
    "$LINCE_LAB_BIN" --socket "$SOCK" vm rm "$VM" -f >/dev/null 2>&1 || true
    stop_broker "$SOCK"
}

# A live broker over the real MacosBackend is the seam the CLI drives.
LINCE_LAB_MACOS=1 start_broker "$SOCK"
# start_broker installs its own `trap stop_broker EXIT`; re-assert the full cleanup
# AFTER it so a mid-oracle assertion failure still tears the (heavier) Tart VM down.
trap cleanup EXIT

log "create + start a disposable macOS guest from the macos-sequoia image"
assert "$LINCE_LAB_BIN" --socket "$SOCK" vm up "$VM" --image macos-sequoia -- "vm up created and started $VM"

log "VM reports running"
STATUS_JSON="$("$LINCE_LAB_BIN" --socket "$SOCK" --json vm status "$VM")"
assert_contains "$STATUS_JSON" '"running"' "vm status reports running"

log "guest is macOS (sw_vers exits 0 and names macOS)"
assert_exit 0 "exec 'sw_vers' -> 0" -- "$LINCE_LAB_BIN" --socket "$SOCK" vm exec "$VM" -- sw_vers
SWVERS_OUT="$("$LINCE_LAB_BIN" --socket "$SOCK" vm exec "$VM" -- sw_vers)"
assert_contains "$SWVERS_OUT" "macOS" "sw_vers reports macOS"

log "guest exit code propagates (the bisect signal)"
assert_exit 7 "exec 'exit 7' -> 7" -- "$LINCE_LAB_BIN" --socket "$SOCK" vm exec "$VM" -- sh -c 'exit 7'

log "destroy the guest"
assert "$LINCE_LAB_BIN" --socket "$SOCK" vm rm "$VM" -f -- "vm rm tore down $VM"
# VM already gone; only the broker remains to clean up on exit.
trap 'stop_broker "$SOCK"' EXIT

ok "v2/01 macos-guest oracle passed"
exit 0
