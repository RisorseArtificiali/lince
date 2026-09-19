#!/usr/bin/env python3
"""Observational Gemini/Goose hooks; never return permission decisions."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    provider = sys.argv[1]
    # Gemini requires JSON; Goose requires empty output for a neutral result.
    if provider == "gemini":
        print("{}")
    agent_id = os.environ.get("LINCE_AGENT_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", agent_id):
        return
    try:
        data = json.load(sys.stdin)
        event = data.get("hook_event_name" if provider == "gemini" else "event")
        allowed = {
            "gemini": {"SessionStart", "SessionEnd", "BeforeAgent", "AfterAgent", "BeforeModel", "BeforeTool", "AfterTool", "Notification"},
            "goose": {"SessionStart", "SessionEnd", "UserPromptSubmit", "Stop", "PreToolUse", "PostToolUse", "PostToolUseFailure"},
        }
        if event not in allowed.get(provider, set()):
            return
        if event == "Notification":
            if data.get("notification_type") != "ToolPermission":
                return
            event = "ToolPermission"
        event = f"{provider}.{event}"
        directory = Path(os.environ.get("LINCE_STATUS_DIR", "/tmp/lince-dashboard"))
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{agent_id}.state").write_text(event)
        if os.environ.get("ZELLIJ"):
            subprocess.run(["zellij", "pipe", "--name", "lince-status"],
                           input=json.dumps({"agent_id": agent_id, "event": event}),
                           text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired):
        pass  # A dashboard failure must not affect the agent's turn.


if __name__ == "__main__":
    main()
