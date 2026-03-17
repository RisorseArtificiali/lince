"""Multiplexer abstraction for tmux and zellij integration.

This module provides a protocol-based abstraction over terminal multiplexers,
allowing telebridge to work with different backends (tmux, zellij) through
a common interface.
"""

from __future__ import annotations

import os
import subprocess
from typing import Protocol

from telebridge.config import TelebridgeConfig


class MultiplexerBridge(Protocol):
    """Protocol for terminal multiplexer bridges.

    A bridge provides methods to interact with a terminal multiplexer,
    capturing pane content and sending keystrokes.
    """

    def validate(self) -> None:
        """Validate that the multiplexer is available and configured.

        Raises:
            RuntimeError: If the multiplexer is unavailable or misconfigured.
        """
        ...

    def get_target_pane(self) -> str:
        """Get the target pane identifier.

        Returns:
            str: The pane identifier (format varies by multiplexer).
        """
        ...

    def capture_pane_ansi(self) -> str:
        """Capture terminal content with ANSI escape codes preserved.

        Returns:
            str: The terminal content including ANSI codes.
        """
        ...

    def send_keys(self, pane_key: str, text: str) -> None:
        """Send keystrokes to a specific pane.

        Args:
            pane_key: The pane identifier (e.g., "session:0", "main:1").
            text: The keystrokes to send.
        """
        ...

    def capture_pane(self) -> str:
        """Capture plain terminal content without ANSI codes.

        This is a legacy method for compatibility with older code.

        Returns:
            str: The plain terminal content.
        """
        ...

    def list_panes(self) -> list[str]:
        """List all available pane keys.

        Returns:
            List of pane_key strings (e.g., ["session:0", "main:1"]).
        """
        ...

    def create_pane(self, name: str, command: str) -> str | None:
        """Create new pane running command.

        Args:
            name: Name for the new pane/tab.
            command: Command to run in the new pane.

        Returns:
            Pane key string (e.g., "session:1") or None on failure.
        """
        ...

    def send_special_key(self, key: str) -> None:
        """Send special key to the target pane.

        Args:
            key: The key sequence (e.g., 'C-c', 'Escape', 'C-d').
        """
        ...


def detect_multiplexer() -> str:
    """Auto-detect the active terminal multiplexer.

    Checks for running multiplexers in priority order:
    1. tmux (via $TMUX environment variable)
    2. zellij (via running processes)
    3. none (no multiplexer detected)

    Returns:
        str: One of "tmux", "zellij", or "none".
    """
    # Check for tmux first
    if os.environ.get("TMUX"):
        return "tmux"

    # Check for zellij by looking for running sessions
    try:
        result = subprocess.run(
            ["zellij", "list-sessions"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        # If command succeeds and we get output, zellij is available
        if result.returncode == 0:
            return "zellij"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "none"


def create_bridge(
    config: TelebridgeConfig,
    session: dict | None = None,
) -> MultiplexerBridge:
    """Factory function to create a multiplexer bridge.

    Args:
        config: Telebridge configuration containing multiplexer settings.
        session: Optional session data with multiplexer information.
                 If provided, used to determine the multiplexer type.

    Returns:
        MultiplexerBridge: A bridge instance for the detected multiplexer.

    Raises:
        ValueError: If the specified backend is not supported.
    """
    # Determine backend type
    backend: str

    if session:
        # Extract backend from session data
        session_backend = session.get("multiplexer", {}).get("backend")
        if session_backend:
            backend = session_backend
        else:
            backend = config.multiplexer.backend
    else:
        backend = config.multiplexer.backend

    # Auto-detect if "auto"
    if backend == "auto":
        backend = detect_multiplexer()

    # Import and create appropriate bridge
    if backend == "tmux":
        from telebridge.tmux_bridge import TmuxBridge

        return TmuxBridge(config)
    elif backend == "zellij":
        from telebridge.zellij_bridge import ZellijBridge

        return ZellijBridge(config)
    else:
        raise ValueError(
            f"Unsupported multiplexer backend: {backend}. "
            f"Supported backends: tmux, zellij, auto"
        )
