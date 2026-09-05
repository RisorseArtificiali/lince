#!/usr/bin/env bash
# bob-status-hook.sh — Bob (IBM bobshell) hook that reports agent status
# to the lince-dashboard Zellij plugin via pipe (primary) and file (fallback).
#
# Emits a minimal JSON contract: {"agent_id": "<id>", "event": "<native_name>"}
# Native event names are passed through verbatim — the dashboard's per-agent
# event_map (in agents-defaults.toml) maps them to canonical status values
# (running / input / permission / stopped). See LINCE-118 / LINCE-122.
#
# Bob's hook contract is Claude-Code-identical: JSON on stdin with at least
# hook_event_name. Events: SessionStart, UserPromptSubmit, PreToolUse,
# PostToolUse, Stop. Bob has NO Notification event, so the PERMISSION state
# is not detectable. Registered globally in ~/.bob/settings/settings.json
# by install-bob-hooks.sh.
#
# Environment:
#   LINCE_AGENT_ID   — set by the dashboard when spawning the agent
#   ZELLIJ           — set by Zellij when running inside a session
#   LINCE_STATUS_DIR — override for status file directory (default: /tmp/lince-dashboard)

set -euo pipefail

AGENT_ID="${LINCE_AGENT_ID:-}"
STATUS_DIR="${LINCE_STATUS_DIR:-/tmp/lince-dashboard}"
LOG_FILE="/tmp/lince-dashboard/hook-debug.log"

mkdir -p /tmp/lince-dashboard 2>/dev/null || true

# Not spawned by the dashboard — nothing to report.
if [ -z "$AGENT_ID" ]; then
    exit 0
fi

INPUT=""
if [ ! -t 0 ]; then
    INPUT=$(cat)
fi

HAS_JQ=false
command -v jq >/dev/null 2>&1 && HAS_JQ=true

extract_json_field() {
    local field="$1"
    if $HAS_JQ && [ -n "$INPUT" ]; then
        local val
        val=$(echo "$INPUT" | jq -r ".$field // empty" 2>/dev/null || true)
        if [ -n "$val" ]; then echo "$val"; return; fi
    fi
    if [ -n "$INPUT" ] && [[ "$INPUT" =~ \"${field}\"[[:space:]]*:[[:space:]]*\"([^\"]+)\" ]]; then
        echo "${BASH_REMATCH[1]}"
    fi
}

HOOK_EVENT=$(extract_json_field "hook_event_name")
if [ -z "$HOOK_EVENT" ]; then
    exit 0
fi

SESSION_ID=$(extract_json_field "session_id")

# Build JSON payload with optional session_id.
# Use jq when available for safe escaping of special characters.
if $HAS_JQ; then
    PAYLOAD=$(jq -n --arg aid "$AGENT_ID" --arg evt "$HOOK_EVENT" \
        --arg sid "${SESSION_ID:-}" \
        '{agent_id: $aid, event: $evt} +
         (if $sid != "" then {session_id: $sid} else {} end)')
else
    # Fallback: manual string concatenation (no escaping — safe for known values only)
    PAYLOAD="{\"agent_id\":\"${AGENT_ID}\",\"event\":\"${HOOK_EVENT}\""
    if [ -n "$SESSION_ID" ]; then
        PAYLOAD="${PAYLOAD},\"session_id\":\"${SESSION_ID}\""
    fi
    PAYLOAD="${PAYLOAD}}"
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) ${AGENT_ID} ${HOOK_EVENT}" >> "$LOG_FILE" 2>/dev/null || true

# Primary: send via zellij pipe (if inside a Zellij session).
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
    echo "$PAYLOAD" | _lince_send_pipe "lince-status" >/dev/null 2>&1 || true
fi

# Fallback: write status to file (always, as backup). The dashboard polls
# /tmp/lince-dashboard/*.state and matches the bare `{agent_id}` basename.
mkdir -p "${STATUS_DIR}" 2>/dev/null || true
echo "$HOOK_EVENT" > "${STATUS_DIR}/${AGENT_ID}.state" 2>/dev/null || true

exit 0
