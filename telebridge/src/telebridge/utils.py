"""Common utilities for telebridge."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

if TYPE_CHECKING:
    from telebridge.session_manager import SessionInfo


logger = logging.getLogger(__name__)

# Callback data prefixes for inline keyboards
CALLBACK_PREFIX_BIND = "bind:"
CALLBACK_ACTION_NEW = "new"

# Interactive UI callback prefix and actions: up, down, enter, esc, refresh, sel:N
CALLBACK_PREFIX_UI = "iui:"

# Key mapping for send_keys (single string per action)
UI_KEY_MAP = {
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "enter": "Enter",
    "esc": "Escape",
}

# Constants for session liveness cache (seconds)
LIVENESS_CACHE_TTL = 60  # Cache pane liveness for 60 seconds

# Constants for cache bounds
MAX_SESSION_CACHE_SIZE = 100
MAX_METADATA_CACHE_SIZE = 500

# Constants for UI message formatting
MAX_UI_CONTENT_LENGTH = 500  # Truncate UI content for Telegram limits


def atomic_write_json(path: Path, data: Any, *, prefix: str = ".atomic.") -> None:
    """Atomically write JSON data to path using temp file + replace.

    Args:
        path: Destination file path
        data: JSON-serializable data
        prefix: Temp file prefix (default: ".atomic.")

    Raises:
        OSError: If write fails
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2)

    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=prefix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json_file(path: Path, default: dict | None = None) -> dict:
    """Load JSON file using EAFP pattern with error handling.

    This avoids TOCTOU race conditions by attempting to open the file
    directly instead of checking existence first.

    Args:
        path: Path to JSON file
        default: Default value if file not found (defaults to empty dict)

    Returns:
        Parsed JSON dict, or default if file doesn't exist or is invalid
    """
    if default is None:
        default = {}

    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load JSON from {path}: {e}")
        return default


def build_session_picker_keyboard(sessions: list[SessionInfo]) -> InlineKeyboardMarkup:
    """Build inline keyboard for session selection.

    Args:
        sessions: List of sessions to display

    Returns:
        InlineKeyboardMarkup with session buttons
    """
    keyboard = []
    for session in sessions:
        keyboard.append([
            InlineKeyboardButton(
                f"📋 {session.summary[:30]} ({session.message_count} msgs)",
                callback_data=f"{CALLBACK_PREFIX_BIND}{session.pane_key}"
            )
        ])
    keyboard.append([
        InlineKeyboardButton("➕ New Session", callback_data=f"{CALLBACK_PREFIX_BIND}{CALLBACK_ACTION_NEW}")
    ])
    return InlineKeyboardMarkup(keyboard)


async def show_session_picker(update: Update, sessions: list[SessionInfo]) -> None:
    """Display session picker inline keyboard.

    Args:
        update: Telegram update
        sessions: List of sessions to display
    """
    if not update.message:
        return

    keyboard = build_session_picker_keyboard(sessions)
    await update.message.reply_text(
        "Select a session to bind:",
        reply_markup=keyboard
    )


def generate_short_uuid(length: int = 12) -> str:
    """Generate short UUID string.

    Args:
        length: Length of UUID string (default: 12)

    Returns:
        Short UUID string
    """
    return uuid.uuid4().hex[:length]


async def poll_with_timeout(
    condition: callable[[], bool],
    timeout: float = 15.0,
    interval: float = 0.5,
) -> bool:
    """Poll until condition is True or timeout.

    Args:
        condition: Callable returning bool
        timeout: Maximum seconds to wait
        interval: Polling interval in seconds

    Returns:
        True if condition met, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition():
            return True
        import asyncio
        await asyncio.sleep(interval)
    return False
