"""Track interactive UI messages for in-place editing."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

# Message entry age before cleanup (seconds)
MESSAGE_TTL = 300  # 5 minutes


@dataclass
class UIMessageTracker:
    """Tracks active interactive UI messages per thread.

    Enables editing messages in-place when UI state changes,
    rather than sending new messages.
    """

    # asyncio.Lock for async context (not threading.Lock)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # user_id -> (thread_id -> (message_id, timestamp))
    _messages: dict[int, dict[int, tuple[int, float]]] = field(default_factory=dict)

    async def set_message(self, user_id: int, thread_id: int, message_id: int) -> None:
        """Track an interactive UI message.

        Args:
            user_id: Telegram user ID
            thread_id: Telegram thread/topic ID
            message_id: Telegram message ID
        """
        async with self._lock:
            if user_id not in self._messages:
                self._messages[user_id] = {}
            self._messages[user_id][thread_id] = (message_id, time.time())

    async def get_message(self, user_id: int, thread_id: int) -> int | None:
        """Get tracked message ID.

        Args:
            user_id: Telegram user ID
            thread_id: Telegram thread/topic ID

        Returns:
            Message ID if tracked and not expired, None otherwise
        """
        async with self._lock:
            entry = self._messages.get(user_id, {}).get(thread_id)
            if entry:
                msg_id, timestamp = entry
                # Check if message has expired
                if time.time() - timestamp < MESSAGE_TTL:
                    return msg_id
                # Clean up expired entry
                del self._messages[user_id][thread_id]
            return None

    async def clear_message(self, user_id: int, thread_id: int) -> int | None:
        """Clear tracking and return the message ID.

        Args:
            user_id: Telegram user ID
            thread_id: Telegram thread/topic ID

        Returns:
            Message ID if it was tracked, None otherwise
        """
        async with self._lock:
            user_msgs = self._messages.get(user_id)
            if user_msgs and thread_id in user_msgs:
                return user_msgs.pop(thread_id)[0]
            return None

    async def clear_all(self, user_id: int) -> None:
        """Clear all tracked messages for a user.

        Args:
            user_id: Telegram user ID
        """
        async with self._lock:
            self._messages.pop(user_id, None)

    async def cleanup_expired(self) -> None:
        """Clean up expired message entries.

        Should be called periodically to prevent unbounded growth.
        """
        async with self._lock:
            now = time.time()
            for user_id in list(self._messages.keys()):
                user_msgs = self._messages[user_id]
                for thread_id in list(user_msgs.keys()):
                    _, timestamp = user_msgs[thread_id]
                    if now - timestamp > MESSAGE_TTL:
                        del user_msgs[thread_id]
                # Remove empty user entries
                if not user_msgs:
                    del self._messages[user_id]


# Global tracker instance
_tracker = UIMessageTracker()


def get_ui_tracker() -> UIMessageTracker:
    """Get the global UI message tracker.

    Returns:
        The singleton UIMessageTracker instance
    """
    return _tracker
