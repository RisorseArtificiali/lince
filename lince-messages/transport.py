"""Deliver ordinary prompts to registered panes using existing dashboard status hooks."""
from pathlib import Path
import json
import os
import re
import subprocess
import time


class TerminalTransport:
    def __init__(self, session, zellij="zellij"):
        self.session = session
        self.zellij = zellij

    def action(self, *args):
        result = subprocess.run([self.zellij, "-s", self.session, "action", *args],
                                capture_output=True, text=True, timeout=2)
        if result.returncode:
            raise OSError("Terminal command failed")
        return result.stdout

    def ready(self, instance):
        return self.readiness(instance)[0]

    def readiness(self, instance):
        """Explain why intake is blocked instead of conflating missing/stale/busy."""
        status_id = instance["status_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", status_id):
            return False, "Recipient has no valid dashboard status ID; reopen its pane"
        directory = Path(instance["status_dir"])
        # Match dashboard polling: Claude's hook adds a prefix even when the
        # agent ID already starts with "claude-". Prefer this authoritative
        # hook file over the generic wrapper's file, including non-idle states.
        status = directory / ("claude-" + status_id + ".state")
        if not status.exists():
            status = directory / (status_id + ".state")
        try:
            info = status.stat()
            event = status.read_text().strip()
            if info.st_mtime < instance["created"]:
                return False, f"Status {status.name} predates this pane; waiting for a fresh agent hook"
            if info.st_mtime < instance["last_submit"]:
                return False, "Waiting for a new idle hook after the previous delivery"
            if event in {"SessionStart", "Stop", "idle_prompt", "turn_complete", "agent-turn-complete", "input",
                        "session_start", "agent_end", "agent_settled",
                        "session.created", "session.status.idle", "session.idle",
                        "bob.PromptReady", "gemini.SessionStart", "gemini.AfterAgent", "goose.SessionStart", "goose.Stop", "amp.idle"}:
                return True, "Idle hook received"
            return False, f"Waiting for idle: latest hook is {event[:80]!r}"
        except FileNotFoundError:
            return False, f"No status file {status.name}; waiting for the agent's first lifecycle hook"
        except OSError:
            return False, f"Cannot read status file {status.name}"

    def __call__(self, instance, prompt):
        if not self.ready(instance):
            return "pending", self.readiness(instance)[1]
        if not instance["pane_ref"].isdecimal() or not isinstance(instance["pid"], int):
            return "failed", "Recipient has no supervised terminal"
        try:
            os.kill(instance["pid"], 0)
            panes = json.loads(self.action("list-panes", "--json", "--all"))
            pane = next((p for p in panes if not p["is_plugin"]
                         and str(p["id"]) == instance["pane_ref"]), None)
            if pane is None or pane.get("exited") or pane.get("exit_status") is not None:
                return "failed", "Original terminal has closed"
            if not self.ready(instance):
                return "pending", "Recipient is no longer idle"
        except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired):
            return "failed", "Cannot verify recipient terminal"
        try:
            # Peer text cannot contain ESC/control characters. Bracketed paste keeps
            # newlines as prompt text; argv passing never evaluates a shell command.
            self.action("write-chars", "--pane-id", instance["pane_ref"], "--", "\x1b[200~" + prompt + "\x1b[201~")
            time.sleep(0.3)
            os.kill(instance["pid"], 0)
            self.action("write", "--pane-id", instance["pane_ref"], "13")
        except (OSError, subprocess.TimeoutExpired):
            return "uncertain", "Terminal write may be partial; inspect the pane before sending again"
        return "submitted", "Text and Enter sent; this is not confirmation of reading or completion"
