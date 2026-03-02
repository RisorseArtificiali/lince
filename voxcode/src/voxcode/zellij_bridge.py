"""Zellij integration for sending text to Claude Code pane."""

import os
import shutil
import subprocess


class ZellijBridge:
    """Sends text to a Zellij pane running Claude Code.

    Uses focus-based pane targeting (no plugin required):
    - Focus the Claude pane (next/previous)
    - Write text with write-chars
    - Optionally send Enter and focus back to VoxCode
    """

    def __init__(
        self,
        target_pane: str | None = None,
        auto_detect: bool = True,
        send_enter: bool = False,
    ):
        self.target_pane = target_pane  # "next" or "previous"
        self.auto_detect = auto_detect
        self.send_enter = send_enter

    def validate(self) -> None:
        """Check that Zellij is available and we are inside a session."""
        if not shutil.which("zellij"):
            raise RuntimeError("zellij is not installed. Install it from https://zellij.dev")
        if not os.environ.get("ZELLIJ") and not os.environ.get("ZELLIJ_SESSION_NAME"):
            raise RuntimeError(
                "Not inside a Zellij session. Start Zellij first, then run VoxCode inside it."
            )

    def get_target_pane(self) -> str:
        """Get the target pane direction.

        Returns "next" or "previous". For a 2-pane layout, "next" reaches
        the other pane regardless of current position.
        """
        if self.target_pane:
            return self.target_pane
        return "next"

    def send_text(self, text: str) -> None:
        """Send text to the Claude Code pane via Zellij focus-switch.

        When send_enter=False: focus Claude pane, write text, stay on Claude pane.
        When send_enter=True: focus Claude pane, write text, send Enter, focus back.
        """
        direction = self.get_target_pane()
        opposite = "previous" if direction == "next" else "next"

        # Focus the Claude pane
        subprocess.run(
            ["zellij", "action", f"focus-{direction}-pane"],
            check=True,
        )

        # Write the text
        subprocess.run(
            ["zellij", "action", "write-chars", text],
            check=True,
        )

        if self.send_enter:
            # Send Enter
            subprocess.run(
                ["zellij", "action", "write", "13"],
                check=True,
            )
            # Focus back to VoxCode pane
            subprocess.run(
                ["zellij", "action", f"focus-{opposite}-pane"],
                check=True,
            )
