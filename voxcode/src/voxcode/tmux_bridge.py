"""tmux integration for sending text to Claude Code pane."""

import shutil
import subprocess


class TmuxBridge:
    """Detects and sends text to a tmux pane running Claude Code."""

    def __init__(self, target_pane: str | None = None, auto_detect: bool = True, send_enter: bool = False):
        self.target_pane = target_pane
        self.auto_detect = auto_detect
        self.send_enter = send_enter

    def validate(self):
        """Check that tmux is available and running."""
        if not shutil.which("tmux"):
            raise RuntimeError("tmux is not installed. VoxCode requires tmux.")
        result = subprocess.run(["tmux", "list-sessions"], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("No tmux sessions found. Start tmux first, then run VoxCode inside it.")

    def detect_claude_pane(self) -> str | None:
        """Find a tmux pane running a claude process."""
        result = subprocess.run(
            [
                "tmux",
                "list-panes",
                "-a",
                "-F",
                "#{session_name}:#{window_index}.#{pane_index} #{pane_current_command}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.strip().split("\n"):
            parts = line.split(" ", 1)
            if len(parts) == 2 and "claude" in parts[1].lower():
                return parts[0]
        return None

    def get_target_pane(self) -> str:
        """Get the target pane identifier, auto-detecting if needed."""
        if self.target_pane:
            return self.target_pane
        if self.auto_detect:
            pane = self.detect_claude_pane()
            if pane:
                return pane
        raise RuntimeError(
            "Could not find Claude Code pane in tmux. "
            "Start Claude Code in a tmux pane, or set target_pane in config."
        )

    def send_text(self, text: str):
        """Send text to Claude Code pane, optionally pressing Enter to submit."""
        pane = self.get_target_pane()
        # Send text literally (no key name interpretation)
        subprocess.run(
            ["tmux", "send-keys", "-t", pane, "-l", text],
            check=True,
        )
        if self.send_enter:
            subprocess.run(
                ["tmux", "send-keys", "-t", pane, "Enter"],
                check=True,
            )
