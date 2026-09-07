#!/usr/bin/env bash
# hook-contract.sh — Validate the LINCE-118 hook JSON contract.
#
# Each hook script must emit, per invocation, exactly one JSON object with:
#   - "agent_id": string (required)
#   - "event":    string (required)
# and optionally:
#   - "timestamp": string
#   - "error":     string
#
# Any extra top-level key is a contract violation. We drive each hook with a
# mocked input matching what the upstream agent would send, capture the JSON
# the hook would have piped to zellij, and validate shape with jq.
#
# Hooks send their payloads via `zellij pipe`. Tests run outside Zellij, so
# we substitute a stub `zellij` on PATH that just dumps stdin to a capture
# file. The status-file fallback is also exercised (LINCE_STATUS_DIR).
#
# Exit code:
#   0 — all hooks satisfy the contract
#   1 — at least one violation

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$(dirname "$SCRIPT_DIR")"
HOOKS_DIR="${DASHBOARD_DIR}/hooks"

WORK_DIR=$(mktemp -d -t lince-hook-contract.XXXXXX)
STUB_DIR="${WORK_DIR}/stub-bin"
CAPTURE_DIR="${WORK_DIR}/captures"
STATE_DIR="${WORK_DIR}/state"
mkdir -p "$STUB_DIR" "$CAPTURE_DIR" "$STATE_DIR"

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

# --- Stub zellij that dumps the piped payload into CAPTURE_DIR/<scenario>.json
cat > "${STUB_DIR}/zellij" <<'STUB'
#!/usr/bin/env bash
# Args look like:   pipe --name <pipe_name>
# We only care about capturing stdin per scenario, so dump it to $CAPTURE_FILE.
out="${CAPTURE_FILE:-/dev/null}"
cat > "$out"
STUB
chmod +x "${STUB_DIR}/zellij"

export PATH="${STUB_DIR}:${PATH}"
# Make hooks think they're inside a Zellij session so they actually call `zellij pipe`.
export ZELLIJ=1
export LINCE_STATUS_DIR="${STATE_DIR}"

ALLOWED_KEYS_JQ='["agent_id","event","timestamp","error"]'

FAIL=0

# Validate a captured JSON file against the contract.
# Args: <scenario> <expected_agent_id> <expected_event_regex>
validate_payload() {
    local scenario="$1"
    local expected_agent_id="$2"
    local expected_event_regex="$3"
    local path="${CAPTURE_DIR}/${scenario}.json"

    if [ ! -s "$path" ]; then
        echo "FAIL [$scenario] no payload captured at $path"
        FAIL=1
        return
    fi

    if ! jq -e . "$path" >/dev/null 2>&1; then
        echo "FAIL [$scenario] invalid JSON: $(cat "$path")"
        FAIL=1
        return
    fi

    local agent_id event keys extra_keys
    agent_id=$(jq -r '.agent_id // ""' "$path")
    event=$(jq -r '.event // ""' "$path")
    keys=$(jq -r 'keys_unsorted[]' "$path")

    if [ -z "$agent_id" ]; then
        echo "FAIL [$scenario] missing agent_id in $(cat "$path")"
        FAIL=1
    fi
    if [ -z "$event" ]; then
        echo "FAIL [$scenario] missing event in $(cat "$path")"
        FAIL=1
    fi

    if [ "$agent_id" != "$expected_agent_id" ]; then
        echo "FAIL [$scenario] agent_id mismatch: got='$agent_id' want='$expected_agent_id'"
        FAIL=1
    fi
    if ! echo "$event" | grep -Eq "$expected_event_regex"; then
        echo "FAIL [$scenario] event '$event' does not match regex '$expected_event_regex'"
        FAIL=1
    fi

    # Detect any unexpected top-level keys.
    extra_keys=$(jq -r --argjson allowed "$ALLOWED_KEYS_JQ" \
        '[keys_unsorted[] | select(. as $k | $allowed | index($k) | not)] | join(",")' \
        "$path")
    if [ -n "$extra_keys" ]; then
        echo "FAIL [$scenario] unexpected top-level keys: $extra_keys (allowed: agent_id, event, timestamp, error)"
        FAIL=1
    fi

    if [ "$FAIL" = "0" ]; then
        echo "OK   [$scenario] agent_id=$agent_id event=$event keys=$(echo "$keys" | tr '\n' ',' | sed 's/,$//')"
    fi
}

run_capture() {
    local scenario="$1"
    shift
    rm -f "${CAPTURE_DIR}/${scenario}.json"
    CAPTURE_FILE="${CAPTURE_DIR}/${scenario}.json" "$@"
}

# --- Sanity: jq must be available, hooks must exist ------------------------

if ! command -v jq >/dev/null 2>&1; then
    echo "FAIL: jq is required to validate JSON shape"
    exit 1
fi

for hook in claude-status-hook.sh codex-status-hook.sh bob-status-hook.sh opencode-status-hook.js lince-agent-wrapper; do
    if [ ! -f "${HOOKS_DIR}/${hook}" ]; then
        echo "FAIL: missing hook script ${HOOKS_DIR}/${hook}"
        FAIL=1
    fi
done

# --- claude-status-hook.sh: native event forwarded verbatim ----------------

export LINCE_AGENT_ID=test-claude
run_capture claude-pretooluse \
    bash -c 'echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"Bash\"}" \
        | bash "$0"' "${HOOKS_DIR}/claude-status-hook.sh"
validate_payload claude-pretooluse "test-claude" '^PreToolUse$'

run_capture claude-stop \
    bash -c 'echo "{\"hook_event_name\":\"Stop\"}" | bash "$0"' \
    "${HOOKS_DIR}/claude-status-hook.sh"
validate_payload claude-stop "test-claude" '^Stop$'

# Notification → notification_type ("idle_prompt" / "permission_prompt").
run_capture claude-notif-idle \
    bash -c 'echo "{\"hook_event_name\":\"Notification\",\"notification_type\":\"idle_prompt\"}" \
        | bash "$0"' "${HOOKS_DIR}/claude-status-hook.sh"
validate_payload claude-notif-idle "test-claude" '^idle_prompt$'

run_capture claude-notif-perm \
    bash -c 'echo "{\"hook_event_name\":\"Notification\",\"notification_type\":\"permission_prompt\"}" \
        | bash "$0"' "${HOOKS_DIR}/claude-status-hook.sh"
validate_payload claude-notif-perm "test-claude" '^permission_prompt$'

# --- codex-status-hook.sh: type field forwarded, fallback turn_complete ----

export LINCE_AGENT_ID=test-codex
run_capture codex-typed \
    bash -c 'echo "{\"type\":\"agent-turn-complete\"}" | bash "$0"' \
    "${HOOKS_DIR}/codex-status-hook.sh"
validate_payload codex-typed "test-codex" '^agent-turn-complete$'

run_capture codex-fallback \
    bash -c 'echo "{}" | bash "$0"' \
    "${HOOKS_DIR}/codex-status-hook.sh"
validate_payload codex-fallback "test-codex" '^turn_complete$'

# Lifecycle hooks use stdin and take precedence over the legacy notify type.
for event in SessionStart UserPromptSubmit PreToolUse PermissionRequest PostToolUse PreCompact PostCompact Stop Interrupt SessionEnd; do
    run_capture "codex-$event" \
        bash -c 'printf "{\"hook_event_name\":\"%s\",\"type\":\"agent-turn-complete\"}" "$1" | bash "$0"' \
        "${HOOKS_DIR}/codex-status-hook.sh" "$event"
    validate_payload "codex-$event" "test-codex" "^${event}$"
    if [ "$(cat "$STATE_DIR/test-codex.state")" != "$event" ]; then
        echo "FAIL [codex-$event] file fallback did not receive lifecycle event"
        FAIL=1
    fi
done

run_capture codex-argv \
    bash "${HOOKS_DIR}/codex-status-hook.sh" '{"type":"agent-turn-complete"}'
validate_payload codex-argv "test-codex" '^agent-turn-complete$'

# --- bob-status-hook.sh: hook_event_name forwarded verbatim ----------------
# Bob's contract is Claude-style (hook_event_name on stdin) but has no
# Notification event; missing hook_event_name must exit 0 with no payload.

export LINCE_AGENT_ID=test-bob
run_capture bob-pretooluse \
    bash -c 'echo "{\"hook_event_name\":\"PreToolUse\",\"tool_name\":\"execute_command\"}" \
        | bash "$0"' "${HOOKS_DIR}/bob-status-hook.sh"
validate_payload bob-pretooluse "test-bob" '^PreToolUse$'

run_capture bob-stop \
    bash -c 'echo "{\"hook_event_name\":\"Stop\"}" | bash "$0"' \
    "${HOOKS_DIR}/bob-status-hook.sh"
validate_payload bob-stop "test-bob" '^Stop$'

# --- lince-agent-wrapper: emits "stopped" on EXIT --------------------------
# The wrapper runs a child command then sends "stopped" via the EXIT trap.
# We invoke it with `true` as the child to exit immediately.

export LINCE_AGENT_ID=test-wrapper
run_capture wrapper-stopped \
    bash "${HOOKS_DIR}/lince-agent-wrapper" test-wrapper lince-status true
validate_payload wrapper-stopped "test-wrapper" '^stopped$'

# --- pi: TS hook, validated only when bun (or tsx) is available ----------
# The Pi hook is a TypeScript module imported by Pi at runtime; it does not
# read stdin like the shell hooks. We exercise it by stubbing the `pi` API
# surface (just .on()) and asserting it calls our zellij stub correctly.

if command -v bun >/dev/null 2>&1; then
    # Driver: feeds a fake pi-like object into the hook, triggers session_start,
    # then awaits a brief moment so the spawned `zellij` stub flushes stdin.
    DRIVER="${WORK_DIR}/pi-driver.ts"
    cat > "$DRIVER" <<'TS'
import hook from "../../hooks/pi/lince-pi-hook.ts";

const handlers: Record<string, (e: any) => void> = {};
const pi = {
    on(ev: string, fn: (e: any) => void) {
        handlers[ev] = fn;
    },
};

process.env.ZELLIJ_SESSION_NAME = "test-session";
hook(pi);

// Fire one event and wait for the spawned `zellij` to receive stdin.
handlers["session_start"]?.({});
await new Promise((r) => setTimeout(r, 250));
TS
    # bun resolves the relative import path relative to the driver file.
    cp "$DRIVER" "${WORK_DIR}/driver.ts"
    # Replace the relative path: place driver next to hooks dir.
    DRV2="${HOOKS_DIR}/../tests/.pi-driver.ts"
    cat > "$DRV2" <<TS
import hook from "../hooks/pi/lince-pi-hook.ts";
const handlers: Record<string, (e: any) => void> = {};
const pi = {
    on(ev: string, fn: (e: any) => void) { handlers[ev] = fn; },
};
process.env.ZELLIJ_SESSION_NAME = "test-session";
hook(pi as any);
handlers["session_start"]?.({});
await new Promise((r) => setTimeout(r, 250));
TS
    LINCE_AGENT_ID=test-pi run_capture pi-session-start bun run "$DRV2"
    rm -f "$DRV2"
    validate_payload pi-session-start "test-pi" '^session_start$'
else
    echo "SKIP [pi] bun/tsx not installed; cannot exercise lince-pi-hook.ts"
fi

# --- opencode: ESM Node hook; validated only when node>=18 is available ---

if command -v node >/dev/null 2>&1; then
    OPENCODE_DRV="${WORK_DIR}/opencode-driver.mjs"
    cat > "$OPENCODE_DRV" <<JS
import hook from "${HOOKS_DIR}/opencode-status-hook.js";
process.env.ZELLIJ = "1";
const factory = await hook({ directory: "/tmp" });
await factory.event({ event: { type: "session.created" } });
JS
    LINCE_AGENT_ID=test-opencode run_capture opencode-created node "$OPENCODE_DRV"
    validate_payload opencode-created "test-opencode" '^session\.created$'
else
    echo "SKIP [opencode] node not installed; cannot exercise opencode-status-hook.js"
fi

# --- Summary --------------------------------------------------------------

if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "All hook contract checks passed."
    exit 0
else
    echo ""
    echo "Hook contract check FAILED."
    exit 1
fi
