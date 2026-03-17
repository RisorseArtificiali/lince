"""Terminal screenshot capture as PNG."""

import logging

from telebridge.config import TelebridgeConfig, get_session_map_path, load_config
from telebridge.multiplexer import create_bridge
from telebridge.terminal_renderer import TerminalRenderer
from telebridge.utils import load_json_file

logger = logging.getLogger(__name__)


def load_session_map(config: TelebridgeConfig) -> dict:
    """Load session map from disk.

    Args:
        config: Telebridge configuration

    Returns:
        Dict mapping pane_key to {session_id, cwd, multiplexer}
    """
    return load_json_file(get_session_map_path(config))


async def capture_and_render_terminal(session_id: str | None = None) -> bytes:
    """Capture terminal content and render to PNG.

    This function orchestrates terminal screenshot capture:
    1. Loads configuration
    2. Reads session_map.json to detect multiplexer type
    3. Creates appropriate bridge (tmux or zellij)
    4. Captures terminal content with ANSI codes
    5. Limits to configured max_lines
    6. Renders to PNG with TerminalRenderer
    7. Returns PNG bytes for sending via Telegram

    Args:
        session_id: Optional Claude Code session ID. If provided, used to
                   look up the correct pane from session_map.json.

    Returns:
        PNG image bytes, or empty bytes on error.

    Raises:
        RuntimeError: If the configured multiplexer is not available.
    """
    config = load_config()

    # Load session map to detect multiplexer context
    session_map = load_session_map(config)

    # If session_id provided, find the pane that maps to it
    target_session = None
    if session_id:
        for pane_key, session_info in session_map.items():
            if session_info.get("session_id") == session_id:
                target_session = session_info.copy()
                target_session["pane_key"] = pane_key
                break
    else:
        # No session_id provided, use first available session
        for pane_key, session_info in session_map.items():
            target_session = session_info.copy()
            target_session["pane_key"] = pane_key
            break

    if not target_session:
        logger.warning("No active session found in session_map.json")
        return b""

    # Create bridge with session info to detect multiplexer type
    try:
        bridge = create_bridge(config, session=target_session)
    except ValueError as e:
        logger.error(f"Failed to create multiplexer bridge: {e}")
        return b""

    # Validate that multiplexer is available
    try:
        bridge.validate()
    except RuntimeError as e:
        # Inform user that multiplexer is not available
        error_msg = f"Terminal multiplexer error: {e}"
        logger.warning(error_msg)
        # Return empty bytes to signal error to caller
        return b""

    # Capture terminal content with ANSI codes
    try:
        ansi_content = bridge.capture_pane_ansi()
    except Exception as e:
        logger.error(f"Failed to capture terminal content: {e}")
        return b""

    if not ansi_content:
        logger.warning("Captured empty terminal content")
        return b""

    # Limit content to max_lines (take last N lines)
    max_lines = config.screenshot.max_lines
    lines = ansi_content.split("\n")
    if len(lines) > max_lines:
        ansi_content = "\n".join(lines[-max_lines:])

    # Render to PNG
    renderer = TerminalRenderer()
    try:
        png_bytes = await renderer.render_to_png(
            ansi_content,
            font_size=config.screenshot.font_size,
        )
        return png_bytes
    except Exception as e:
        logger.error(f"Failed to render terminal to PNG: {e}")
        return b""
