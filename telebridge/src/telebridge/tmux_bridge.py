"""Tmux multiplexer bridge implementation."""

import subprocess
from telebridge.config import TelebridgeConfig
from telebridge.multiplexer import MultiplexerBridge


class TmuxBridge:
    """Bridge for tmux terminal multiplexer.

    Provides methods to interact with tmux sessions, capturing pane content
    and sending keystrokes.
    """

    def __init__(self, config: TelebridgeConfig) -> None:
        """Initialize the tmux bridge.

        Args:
            config: Telebridge configuration containing tmux settings.
        """
        self.config = config

    def validate(self) -> None:
        """Validate that tmux is available and configured.

        Raises:
            RuntimeError: If tmux is not installed or the target pane doesn't exist.
        """
        # Check if tmux is installed
        try:
            subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise RuntimeError(
                "tmux is not installed or not accessible. "
                "Please install tmux to use the tmux bridge."
            ) from e

        # Check if tmux session exists by attempting to capture pane
        try:
            target_pane = self.config.tmux.target_pane
            if not target_pane:
                raise RuntimeError(
                    "tmux.target_pane is not configured. "
                    "Please set the target pane in your configuration."
                )

            subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", target_pane],
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"tmux pane '{target_pane}' does not exist or is not accessible. "
                "Please ensure tmux is running and the target pane is valid."
            ) from e

    def get_target_pane(self) -> str:
        """Get the target pane identifier.

        Returns:
            str: The tmux pane identifier (e.g., "session:window.pane").
        """
        return self.config.tmux.target_pane

    def capture_pane_ansi(self) -> str:
        """Capture terminal content with ANSI escape codes preserved.

        Uses 'tmux capture-pane -e -p -t {pane}' to capture content.
        The '-e' flag preserves ANSI escape sequences for colors/formatting.

        Returns:
            str: The terminal content including ANSI codes, or empty string on error.
        """
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-e", "-p", "-t", self.get_target_pane()],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def send_keys(self, pane_key: str, text: str) -> None:
        """Send keystrokes to a specific pane.

        Args:
            pane_key: The pane identifier (e.g., "session:0").
            text: The keystrokes to send.
        """
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", pane_key, text],
                capture_output=True,
                text=True,
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Silently fail on send errors

    def capture_pane(self) -> str:
        """Capture plain terminal content without ANSI codes.

        This is a legacy method for compatibility with older code.
        Uses 'tmux capture-pane -p -t {pane}' without the '-e' flag.

        Returns:
            str: The plain terminal content, or empty string on error.
        """
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-t", self.get_target_pane()],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def list_panes(self) -> list[str]:
        """List all tmux windows as pane keys.

        Returns:
            List of pane_key strings (e.g., ["session:0", "session:1"]).
        """
        try:
            result = subprocess.run(
                ["tmux", "list-windows", "-F", "#{session_name}:#{window_index}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
            return [line for line in result.stdout.strip().split("\n") if line]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return []

    def create_pane(self, name: str, command: str) -> str | None:
        """Create new tmux window running command. Returns 'session:window_index' or None."""
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "new-window",
                    "-P",
                    "-F",
                    "#{session_name}:#{window_index}",
                    "-n",
                    name,
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

    def send_special_key(self, key: str) -> None:
        """Send special key via tmux send-keys.

        Args:
            key: The key sequence (e.g., 'C-c', 'Escape').
        """
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", self.get_target_pane(), "-l", key],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass  # Silently fail on send errors
