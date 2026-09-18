"""Capabilities are version-specific and independent of dashboard badge maps."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sys
import uuid

from protocol import MAX_FRAME, ProtocolError, call
from store import digest


EVENTS = {
    "claude": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
               "Notification", "Stop", "SessionEnd"),
    "codex": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest",
              "PreCompact", "PostCompact", "Stop", "Interrupt", "SessionEnd"),
    "bob": ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact", "PostCompact", "Stop"),
}


def capabilities(agent, version):
    if agent == "bob" and version == "2.0.4":
        return {"version": version, "session_identity": True, "human_attribution": True,
                "context_events": [], "permission_detection": False, "question_detection": False,
                "idle_wakeup": False, "native_cancellation": False,
                "reason": "Bob Stop ignores hook output; explicit inbox only, no automatic wakeup"}
    if (agent, version) in {("claude", "2.1.272"), ("codex", "0.154.0")}:
        return {"version": version, "session_identity": True, "human_attribution": True,
                "context_events": ["Stop"], "permission_detection": True, "question_detection": False,
                "idle_wakeup": False, "native_cancellation": False,
                "reason": "Intake at native Stop only; an already idle agent needs an explicit inbox check"}
    return {"version": version, "session_identity": False, "context_events": [], "idle_wakeup": False,
            "reason": "Unverified agent/version: explicit inbox only; automatic intake disabled"}


def normalize(agent, payload):
    if agent not in EVENTS or not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    if agent == "bob" and not event:
        event = payload.get("event")
    session = payload.get("session_id")
    if event not in EVENTS[agent] or not isinstance(session, str) or not session:
        return None
    if payload.get("agent_id") or payload.get("agent_type"):
        # Inherited credentials must not let a provider subagent claim the root session.
        return None
    if event == "Notification":
        event = payload.get("notification_type", "unknown")
    if event == "PreToolUse" and payload.get("tool_name") in {"AskUserQuestion", "request_user_input"}:
        event = "Question"
    normalized = {"session": session, "event": event, "key": str(uuid.uuid4()),
                  "continuation": payload.get("stop_hook_active", False) is True}
    turn = payload.get("turn_id")
    if agent == "codex" and event in {"UserPromptSubmit", "Stop"} and isinstance(turn, str) and turn:
        # These events occur once per turn/continuation. Preserve the provider
        # identity across repeated hook invocations, including after resume.
        normalized["key"] = "codex-turn-" + digest(json.dumps(
            [session, event, turn, normalized["continuation"]], separators=(",", ":")))
    # Without a native event/turn identity, equal payloads can be distinct human
    # prompts. Do not collapse them by hashing their text or wall-clock buckets.
    if event == "UserPromptSubmit" and isinstance(payload.get("prompt"), str):
        normalized["prompt_hash"] = digest(payload["prompt"])
    return normalized


def invoke(agent, payload, endpoint, credential):
    normalized = normalize(agent, payload)
    if normalized is None:
        return None
    response = call(endpoint, Path(credential).read_text().strip(), "hook", normalized)
    event = normalized["event"]
    if response.get("reason"):
        return None
    if event == "SessionStart":
        instructions = Path(__file__).with_name("instructions.md").read_text()
        if agent == "bob":
            return instructions
        return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": instructions}}
    if event == "Stop" and response.get("context"):
        return {"decision": "block", "reason": response["context"]}
    return None


def main():
    endpoint, credential = os.environ.get("LINCE_MSG_ENDPOINT"), os.environ.get("LINCE_MSG_CREDENTIAL")
    if not endpoint or not credential or len(sys.argv) != 2:
        return 0

    def timeout(_signum, _frame):
        raise TimeoutError("Hook time budget exhausted")

    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, 2)
    try:
        raw = sys.stdin.buffer.read(MAX_FRAME + 1)
        if len(raw) > MAX_FRAME:
            return 0
        result = invoke(sys.argv[1], json.loads(raw), endpoint, credential)
        if result is not None:
            print(result if isinstance(result, str) else json.dumps(result, ensure_ascii=True))
    except (OSError, ValueError, ProtocolError, TypeError):
        # Fail open for normal agent use, closed for message delivery. Incomplete
        # delivery stays visible in the durable inbox; never emit a permission decision.
        return 0
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    return 0
