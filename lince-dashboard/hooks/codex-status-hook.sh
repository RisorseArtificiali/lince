#!/usr/bin/env bash
# codex-status-hook.sh — Codex lifecycle/notify hook that reports agent status
# to the lince-dashboard Zellij plugin via pipe (primary) and file (fallback).
#
# Emits a minimal JSON contract: {"agent_id": "<id>", "event": "<native_name>"}
# Native event names are passed through verbatim — the dashboard's per-agent
# event_map (in agents-defaults.toml) maps them to canonical status values.
# See LINCE-118 / LINCE-122.
#
# Codex notify runs an external program and appends a JSON payload as an argv
# item; lifecycle hooks deliver JSON on stdin using `hook_event_name`.
# Prefer that field, then the legacy notify `type` field.
# If `type` is missing, we synthesize "turn_complete" to preserve historical
# semantics (codex notify fires on turn completion).
#
# Environment:
#   LINCE_AGENT_ID   — set by the dashboard when spawning the agent
#   ZELLIJ           — set by Zellij when running inside a session
#   LINCE_STATUS_DIR — override for status file directory (default: /tmp/lince-dashboard)

set -euo pipefail

AGENT_ID="${LINCE_AGENT_ID:-}"
STATUS_DIR="${LINCE_STATUS_DIR:-/tmp/lince-dashboard}"
LOG_FILE="/tmp/lince-dashboard/codex-hook-debug.log"

mkdir -p /tmp/lince-dashboard 2>/dev/null || true

if [ -z "$AGENT_ID" ]; then
    exit 0
fi

INPUT="${1:-}"
if [ -z "$INPUT" ] && [ ! -t 0 ]; then
    INPUT=$(cat)
fi

HAS_JQ=false
command -v jq >/dev/null 2>&1 && HAS_JQ=true

extract_json_field() {
    local field="$1"
    if $HAS_JQ && [ -n "$INPUT" ]; then
        local val
        val=$(printf '%s' "$INPUT" | jq -r --arg field "$field" '.[$field] // empty' 2>/dev/null || true)
        if [ -n "$val" ]; then echo "$val"; return; fi
    fi
    if [ -n "$INPUT" ] && [[ "$INPUT" =~ \"${field}\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
        echo "${BASH_REMATCH[1]}"
    fi
}

NATIVE_EVENT=$(extract_json_field "hook_event_name")
if [ -z "$NATIVE_EVENT" ]; then
    EVENT_TYPE=$(extract_json_field "type")
    NATIVE_EVENT="${EVENT_TYPE:-turn_complete}"
fi

PAYLOAD="{\"agent_id\":\"${AGENT_ID}\",\"event\":\"${NATIVE_EVENT}\"}"

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ${AGENT_ID} ${NATIVE_EVENT}" >> "$LOG_FILE" 2>/dev/null || true

# Use whatever `timeout` is available (GNU `timeout` on Linux, `gtimeout` on
# macOS with `brew install coreutils`); fall back to running zellij directly
# when neither exists — macOS ships without `timeout` by default.
_lince_send_pipe() {
    if command -v timeout >/dev/null 2>&1; then
        timeout 2 zellij pipe --name "$1"
    elif command -v gtimeout >/dev/null 2>&1; then
        gtimeout 2 zellij pipe --name "$1"
    else
        zellij pipe --name "$1"
    fi
}
if [ -n "${ZELLIJ:-}" ] && command -v zellij >/dev/null 2>&1; then
    printf '%s' "$PAYLOAD" | _lince_send_pipe "lince-status" >/dev/null 2>&1 || true
fi

mkdir -p "${STATUS_DIR}" 2>/dev/null || true
echo "$NATIVE_EVENT" > "${STATUS_DIR}/${AGENT_ID}.state" 2>/dev/null || true

exit 0
