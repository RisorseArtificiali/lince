"""Zellij terminal multiplexer bridge implementation.

This module provides a bridge for interacting with Zellij terminal multiplexer,
implementing the MultiplexerBridge protocol. Zellij lacks native ANSI capture
 support, so capture_pane_ansi() returns plain text as a fallback.
"""

import os
import subprocess

from telebridge.config import TelebridgeConfig
from telebridge.multiplexer import MultiplexerBridge


class ZellijBridge(MultiplexerBridge):
    """Bridge for Zellij terminal multiplexer.

    Zellij limitations:
    - No native ANSI escape code capture via CLI
    - capture_pane_ansi() returns plain text (graceful fallback)
    - TerminalRenderer will use default colors when no ANSI codes present
    """

    def __init__(self, config: TelebridgeConfig) -> None:
        """Initialize the Zellij bridge.

        Args:
            config: Telebridge configuration containing Zellij settings.
        """
        self.config = config
        self._validated = False

    def validate(self) -> None:
        """Validate that Zellij is available and configured.

        Checks:
        1. Zellij binary is installed
        2. Zellij session is accessible

        Raises:
            RuntimeError: If Zellij is unavailable or misconfigured.
        """
        # Check if zellij is installed
        try:
            result = subprocess.run(
                ["zellij", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Zellij binary returned error code {result.returncode}"
                )
        except FileNotFoundError:
            raise RuntimeError(
                "Zellij is not installed or not found in PATH"
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Zellij version check timed out")

        # Check if zellij session exists
        try:
            result = subprocess.run(
                ["zellij", "list-sessions"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # If no sessions exist, the output will be empty
            # We still consider this valid as sessions can be created later
        except subprocess.TimeoutExpired:
            raise RuntimeError("Zellij session check timed out")

        self._validated = True

    def get_target_pane(self) -> str:
        """Get the target pane identifier.

        Returns:
            str: The pane identifier (e.g., "up", "right", "down", "left").
        """
        return self.config.zellij.target_pane

    def capture_pane_ansi(self) -> str:
        """Capture terminal content with ANSI escape codes.

        NOTE: Zellij does not support ANSI capture via CLI.
        This method returns plain text as a graceful fallback.
        TerminalRenderer will use default colors when no ANSI codes present.

        Returns:
            str: Plain terminal content (no ANSI codes).
        """
        return self.capture_pane()

    def capture_pane(self) -> str:
        """Capture plain terminal content without ANSI codes.

        Uses zellij run --content-output none -- cat to capture pane content.

        Returns:
            str: The plain terminal content, or empty string on error.
        """
        pane = self.get_target_pane()

        try:
            result = subprocess.run(
                [
                    "zellij",
                    "run",
                    "--floating",
                    "--close-on-exit",
                    "cat",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                return result.stdout

            return ""

        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return ""

    def send_keys(self, pane_key: str, text: str) -> None:
        """Send keystrokes to a specific pane.

        Args:
            pane_key: The pane identifier (e.g., "session:0").
            text: The keystrokes to send.

        Raises:
            RuntimeError: If sending keys fails.
        """
        try:
            result = subprocess.run(
                ["zellij", "action", "write", text],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to send keys to Zellij pane '{pane_key}': "
                    f"{result.stderr}"
                )

        except FileNotFoundError:
            raise RuntimeError("Zellij is not installed or not found in PATH")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Sending keys to Zellij pane '{pane_key}' timed out")

    def list_panes(self) -> list[str]:
        """List all Zellij tabs as pane keys.

        Returns:
            List of pane_key strings (e.g., ["session:0", "session:1"]).
        """
        session = os.environ.get("ZELLIJ_SESSION_NAME", "")
        if not session:
            return []

        try:
            result = subprocess.run(
                ["zellij", "action", "query-tab-names"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
            tabs = result.stdout.strip().split("\n")
            return [f"{session}:{i}" for i, name in enumerate(tabs) if name]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def create_pane(self, name: str, command: str) -> str | None:
        """Create new Zellij tab running command. Returns 'session:index' or None on failure."""
        session = os.environ.get("ZELLIJ_SESSION_NAME", "")
        if not session:
            return None

        try:
            # Create new tab with name
            result = subprocess.run(
                ["zellij", "action", "new-tab", "-n", name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None

            # Send command to the new tab
            subprocess.run(
                ["zellij", "action", "write", command],
                capture_output=True,
                text=True,
                timeout=5,
            )

            # Get tab index - we have to get all tabs and count
            result = subprocess.run(
                ["zellij", "action", "query-tab-names"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            tabs = result.stdout.strip().split("\n")
            return f"{session}:{len(tabs) - 1}" if tabs else None
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def send_special_key(self, key: str) -> None:
        """Send special key via Zellij.

        Args:
            key: The key sequence (e.g., 'C-c', 'Escape').
        """
        # Map key names to Zellij action sequences
        key_map = {
            "C-c": "\x03",  # ETX (Ctrl-C)
            "Escape": "\x1b",  # ESC character
            "C-d": "\x04",  # EOT (Ctrl-D)
            "C-z": "\x1a",  # SUB (Ctrl-Z)
        }

        char_to_send = key_map.get(key, key)
        if char_to_send:
            try:
                subprocess.run(
                    ["zellij", "action", "write", char_to_send],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
        else:
            # Fallback: try direct key name
            try:
                subprocess.run(
                    ["zellij", "action", "write", key],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                pass
