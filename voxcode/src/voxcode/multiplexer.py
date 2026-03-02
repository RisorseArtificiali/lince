"""Multiplexer abstraction for terminal multiplexer backends."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from voxcode.config import VoxCodeConfig


class MultiplexerBridge(Protocol):
    """Protocol that both TmuxBridge and ZellijBridge implement."""

    def validate(self) -> None: ...
    def get_target_pane(self) -> str: ...
    def send_text(self, text: str) -> None: ...


def detect_multiplexer() -> str:
    """Detect which terminal multiplexer is active.

    Returns "zellij" or "tmux" based on environment variables.
    """
    if os.environ.get("ZELLIJ") or os.environ.get("ZELLIJ_SESSION_NAME"):
        return "zellij"
    if os.environ.get("TMUX"):
        return "tmux"
    raise RuntimeError(
        "Not running inside tmux or Zellij. "
        "Start VoxCode inside a terminal multiplexer, or use --launch."
    )


def create_bridge(config: VoxCodeConfig) -> MultiplexerBridge:
    """Create the appropriate multiplexer bridge based on config and environment."""
    from voxcode.tmux_bridge import TmuxBridge
    from voxcode.zellij_bridge import ZellijBridge

    backend = config.multiplexer.backend
    send_enter = config.multiplexer.send_enter

    if backend == "auto":
        backend = detect_multiplexer()

    if backend == "tmux":
        return TmuxBridge(
            target_pane=config.tmux.target_pane or None,
            auto_detect=config.tmux.auto_detect,
            send_enter=send_enter,
        )
    elif backend == "zellij":
        return ZellijBridge(
            target_pane=config.zellij.target_pane or None,
            auto_detect=config.zellij.auto_detect,
            send_enter=send_enter,
        )
    else:
        raise ValueError(f"Unknown multiplexer backend: {backend}")
