"""Per-user async message queue with merging and flood control.

Decouples message production from delivery with:
- Per-user async queues with dedicated worker loops
- Content merging for consecutive same-pane messages
- Telegram flood control handling with RetryAfter support
- Status message tracking with ephemeral drop during floods

Architecture:
    SessionMonitor → _convert_entries_to_tasks() → MessageQueue.enqueue()
                                                       → Worker loop
                                                           → _merge_content_tasks()
                                                           → _send_task()
                                                               → Telegram API
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from datetime import timedelta

from telegram import Bot
from telegram.error import RetryAfter

if TYPE_CHECKING:
    pass  # No imports currently needed

logger = logging.getLogger(__name__)

# Task type constants
TASK_TYPE_CONTENT = "content"
TASK_TYPE_STATUS_UPDATE = "status_update"
TASK_TYPE_STATUS_CLEAR = "status_clear"

# Merge configuration
_MAX_MERGED_LENGTH = 3800  # Maximum combined length for merged content
_MERGE_CHECK_LIMIT = 10  # Maximum tasks to inspect for merging

# Flood control thresholds
_SHORT_RETRY_THRESHOLD = 10.0  # Seconds: wait for short delays

# Worker lifecycle
_INACTIVITY_TIMEOUT = 300  # Seconds: 5 minutes


@dataclass
class MessageTask:
    """A message to be sent to Telegram.

    Attributes:
        task_type: Type of task - "content" | "status_update" | "status_clear"
        text: Formatted text content to send
        pane_key: Multiplexer pane key for merge logic
        tool_use_id: Tool use ID for merge eligibility check
        content_type: Content type from ParsedEntry
        thread_id: Telegram thread ID for topic-based routing
        image_data: Optional image bytes from tool_result
        timestamp: Creation time for age tracking
    """

    task_type: str
    text: str = ""
    pane_key: str = ""
    tool_use_id: str = ""
    content_type: str = ""
    thread_id: int | None = None
    image_data: bytes = b""
    timestamp: float = field(default_factory=time.time)

    def is_content(self) -> bool:
        """Check if this is a content message (mergeable)."""
        return self.task_type == TASK_TYPE_CONTENT

    def is_status_update(self) -> bool:
        """Check if this is a status update message (ephemeral)."""
        return self.task_type == TASK_TYPE_STATUS_UPDATE

    def is_status_clear(self) -> bool:
        """Check if this clears a previous status message."""
        return self.task_type == TASK_TYPE_STATUS_CLEAR

    def is_tool_entry(self) -> bool:
        """Check if this is a tool_use or tool_result (not mergeable)."""
        return self.content_type in ("tool_use", "tool_result")

    def combined_length(self, other: "MessageTask") -> int:
        """Calculate combined text length with separator."""
        return len(self.text) + len(other.text) + 2  # +2 for "\n\n"


@dataclass
class FloodControlState:
    """Track flood control status per user.

    Attributes:
        banned_until: Timestamp when flood control expires
        retry_after: Seconds to wait from RetryAfter error
        last_error: Last error message for logging
    """

    banned_until: float = 0.0
    retry_after: int = 0
    last_error: str = ""

    def is_banned(self, now: float) -> bool:
        """Check if user is currently under flood control."""
        return now < self.banned_until

    def get_wait_time(self, now: float) -> float:
        """Get seconds to wait before next send."""
        return max(0.0, self.banned_until - now)

    def set_ban(self, retry_after: int | timedelta, error: str = "") -> None:
        """Set flood control ban from RetryAfter."""
        # Handle both int and timedelta types from telegram.error.RetryAfter
        if isinstance(retry_after, timedelta):
            retry_after_seconds = retry_after.total_seconds()
        else:
            retry_after_seconds = float(retry_after)

        self.banned_until = time.time() + retry_after_seconds
        self.retry_after = int(retry_after_seconds)
        self.last_error = error

    def clear(self) -> None:
        """Clear flood control state."""
        self.banned_until = 0.0
        self.retry_after = 0
        self.last_error = ""


@dataclass
class StatusMessageTracker:
    """Track status messages per user for deletion.

    Stores mapping of pane_key -> Telegram message_id for status
    messages that can be cleared by subsequent status_clear tasks.

    Attributes:
        message_ids: Dict mapping pane_key to message_id
    """

    message_ids: dict[str, int] = field(default_factory=dict)

    def set(self, pane_key: str, message_id: int) -> None:
        """Store status message ID for a pane."""
        self.message_ids[pane_key] = message_id

    def get(self, pane_key: str) -> int | None:
        """Get stored status message ID for a pane."""
        return self.message_ids.get(pane_key)

    def clear(self, pane_key: str) -> None:
        """Remove stored status message ID for a pane."""
        self.message_ids.pop(pane_key, None)


class MessageQueue:
    """Per-user async message queue with merging and flood control.

    Each user gets:
    - An asyncio.Queue for pending MessageTasks
    - A dedicated worker task for processing
    - An asyncio.Lock for merge operations
    - FloodControlState for rate limit handling
    - StatusMessageTracker for status message deletion

    Worker lifecycle:
    - Created on first enqueue for a user
    - Processes tasks with merge and flood control
    - Auto-exits after 5 minutes of inactivity
    """

    def __init__(self, config: Any | None = None):
        """Initialize the message queue.

        Args:
            config: Optional TelebridgeConfig for future customization
        """
        # Per-user queues and workers
        self._message_queues: dict[int, asyncio.Queue[MessageTask]] = {}
        self._queue_workers: dict[int, asyncio.Task] = {}
        self._queue_locks: dict[int, asyncio.Lock] = {}
        self._worker_last_activity: dict[int, float] = {}

        # Per-user state
        self._flood_state: dict[int, FloodControlState] = {}
        self._status_messages: dict[int, StatusMessageTracker] = {}

        # Bot instance (set via set_bot())
        self._bot: Bot | None = None

        # Configuration
        self._inactivity_timeout = _INACTIVITY_TIMEOUT

        logger.debug("MessageQueue initialized")

    def set_bot(self, bot: Bot) -> None:
        """Set the Telegram bot instance.

        Args:
            bot: Telegram bot instance for sending messages
        """
        self._bot = bot
        logger.debug("Bot instance set on MessageQueue")

    async def enqueue(self, task: MessageTask, user_id: int) -> None:
        """Enqueue a task, creating queue/worker if needed.

        Lazy initialization: creates user queue and worker on first enqueue.

        Args:
            task: MessageTask to enqueue
            user_id: Telegram user ID (chat_id)
        """
        if user_id not in self._message_queues:
            await self._create_user_queue(user_id)
            logger.debug(f"Created queue and worker for user {user_id}")

        # Handle full queue (backpressure)
        queue = self._message_queues[user_id]
        try:
            queue.put_nowait(task)
        except asyncio.QueueFull:
            logger.warning(f"Queue full for user {user_id}, waiting...")
            await queue.put(task)

    async def _create_user_queue(self, user_id: int) -> None:
        """Create queue, lock, state, and worker for a user.

        Args:
            user_id: Telegram user ID
        """
        # Create queue with size limit to prevent unbounded growth
        self._message_queues[user_id] = asyncio.Queue(maxsize=100)

        # Create lock for merge operations
        self._queue_locks[user_id] = asyncio.Lock()

        # Initialize state
        self._flood_state[user_id] = FloodControlState()
        self._status_messages[user_id] = StatusMessageTracker()
        self._worker_last_activity[user_id] = asyncio.get_event_loop().time()

        # Start worker task
        self._queue_workers[user_id] = asyncio.create_task(
            self._worker_loop(user_id),
            name=f"message_queue_worker_{user_id}",
        )

    async def _worker_loop(self, user_id: int) -> None:
        """Worker loop: dequeue → merge → send → repeat.

        Processing pipeline:
        1. Dequeue task with timeout
        2. Merge with consecutive tasks (if eligible)
        3. Send each merged task with flood control
        4. Exit after inactivity timeout

        Args:
            user_id: Telegram user ID for this worker
        """
        queue = self._message_queues[user_id]
        loop = asyncio.get_event_loop()
        worker_name = f"worker_{user_id}"

        logger.debug(f"{worker_name}: started")

        try:
            while True:
                try:
                    # Wait for task with timeout
                    task = await asyncio.wait_for(
                        queue.get(),
                        timeout=self._inactivity_timeout,
                    )

                    # Update activity timestamp
                    self._worker_last_activity[user_id] = loop.time()

                    # Merge this task with consecutive eligible tasks
                    merged_tasks = await self._merge_content_tasks(user_id, task)

                    # Send each merged task
                    for merged_task in merged_tasks:
                        await self._send_task(user_id, merged_task)

                except asyncio.TimeoutError:
                    # Check if we've been inactive long enough to exit
                    now = loop.time()
                    last_activity = self._worker_last_activity.get(user_id, 0)
                    if now - last_activity > self._inactivity_timeout:
                        logger.debug(f"{worker_name}: inactivity timeout, exiting")
                        break

        except asyncio.CancelledError:
            logger.debug(f"{worker_name}: cancelled")

        finally:
            logger.debug(f"{worker_name}: exited")

    async def _merge_content_tasks(
        self, user_id: int, first_task: MessageTask
    ) -> list[MessageTask]:
        """Merge consecutive content tasks with same pane_key.

        Merge eligibility rules:
        1. Both tasks are TASK_TYPE_CONTENT
        2. Same pane_key (same session)
        3. Neither is tool_use or tool_result
        4. Combined length ≤ _MAX_MERGED_LENGTH
        5. Same thread_id

        Args:
            user_id: Telegram user ID
            first_task: First task to merge (already dequeued)

        Returns:
            List of merged tasks (single task if no merge possible)
        """
        # Quick check: if first task isn't mergeable, return as-is
        if not first_task.is_content():
            return [first_task]

        queue = self._message_queues[user_id]
        lock = self._queue_locks[user_id]

        async with lock:
            # Build batch of mergeable tasks
            batch = [first_task]

            # Drain queue to inspect consecutive tasks
            checked = 0
            while checked < _MERGE_CHECK_LIMIT:
                try:
                    next_task = queue.get_nowait()
                    checked += 1

                    # Check if mergeable
                    if self._can_merge(batch[-1], next_task):
                        batch.append(next_task)
                    else:
                        # Not mergeable - put back and stop
                        await queue.put(next_task)
                        break
                except asyncio.QueueEmpty:
                    break

            # If only one task, return as-is
            if len(batch) == 1:
                return batch

            # Merge the batch
            merged_text = "\n\n".join(t.text for t in batch)
            merged_task = MessageTask(
                task_type=TASK_TYPE_CONTENT,
                text=merged_text,
                pane_key=batch[0].pane_key,
                content_type=batch[0].content_type,
                thread_id=batch[0].thread_id,
                timestamp=batch[0].timestamp,
            )

            logger.debug(
                f"Merged {len(batch)} tasks for user {user_id}, "
                f"combined length: {len(merged_text)}"
            )

            return [merged_task]

    def _can_merge(self, prev: MessageTask, curr: MessageTask) -> bool:
        """Check if two tasks can be merged.

        Args:
            prev: Previous task in batch
            curr: Current task to check

        Returns:
            True if tasks can be merged
        """
        # Both must be content type
        if not curr.is_content():
            return False

        # Must be from same pane (session)
        if prev.pane_key != curr.pane_key:
            return False

        # Tool entries are not mergeable
        if prev.is_tool_entry() or curr.is_tool_entry():
            return False

        # Must have same thread_id
        if prev.thread_id != curr.thread_id:
            return False

        # Check combined length
        new_len = prev.combined_length(curr)
        if new_len > _MAX_MERGED_LENGTH:
            return False

        return True

    async def _send_task(self, user_id: int, task: MessageTask) -> None:
        """Send task with flood control handling.

        Flood control strategy:
        - Check if user is banned (banned_until timestamp)
        - If banned and task is status_update: drop (ephemeral)
        - If banned and task is content: wait for flood to clear
        - Handle RetryAfter from telegram.error

        Args:
            user_id: Telegram user ID
            task: MessageTask to send
        """
        if self._bot is None:
            logger.warning("Bot not set, cannot send task")
            return

        # Ensure user state exists (for direct _send_task calls without enqueue)
        if user_id not in self._flood_state:
            self._flood_state[user_id] = FloodControlState()
        if user_id not in self._status_messages:
            self._status_messages[user_id] = StatusMessageTracker()

        flood_state = self._flood_state[user_id]
        status_tracker = self._status_messages[user_id]
        now = time.time()

        # Check flood control (single check, reuse result)
        is_banned = flood_state.is_banned(now)

        # Handle status_clear (delete previous status message)
        if task.is_status_clear():
            await self._clear_status_message(user_id, task, status_tracker)
            return

        # Check flood control
        if is_banned:
            wait_time = flood_state.get_wait_time(now)

            if task.is_status_update():
                # Drop status messages during flood (ephemeral)
                logger.debug(
                    f"User {user_id} under flood control ({wait_time:.1f}s remaining), "
                    f"dropping status message"
                )
                return

            # Content messages wait for flood to clear
            logger.info(
                f"User {user_id} under flood control, waiting {wait_time:.1f}s "
                f"before sending content"
            )
            await asyncio.sleep(wait_time)

        # Send the message
        try:
            await self._do_send(user_id, task, status_tracker)

            # Clear flood state on successful send
            if flood_state.is_banned(time.time()):
                logger.info(f"User {user_id} flood control cleared")
                flood_state.clear()

        except RetryAfter as e:
            # Handle Telegram flood control
            retry_after = e.retry_after

            # Convert timedelta to seconds for comparison
            if isinstance(retry_after, timedelta):
                retry_after_seconds = retry_after.total_seconds()
            else:
                retry_after_seconds = float(retry_after)

            if retry_after_seconds <= _SHORT_RETRY_THRESHOLD:
                # Short delay: wait and retry
                logger.info(
                    f"Hit Telegram rate limit for user {user_id}, "
                    f"waiting {retry_after_seconds}s before retry"
                )
                await asyncio.sleep(retry_after_seconds)

                # Retry once
                try:
                    await self._do_send(user_id, task, status_tracker)
                except Exception as retry_error:
                    logger.error(
                        f"Failed to send to user {user_id} after retry: {retry_error}"
                    )
            else:
                # Long delay: store banned_until and drop status messages
                logger.warning(
                    f"Hit Telegram rate limit for user {user_id}, "
                    f"banned for {retry_after_seconds}s"
                )
                flood_state.set_ban(retry_after, str(e))

                if task.is_status_update():
                    logger.debug(f"Dropped status message for user {user_id} (long flood)")
                    return  # Don't raise for status messages
                else:
                    # Content messages: raise for retry by worker loop
                    raise

        except Exception as e:
            logger.error(f"Failed to send task to user {user_id}: {e}")
            raise

    async def _do_send(
        self, user_id: int, task: MessageTask, status_tracker: StatusMessageTracker
    ) -> None:
        """Actually send the message via bot API.

        Args:
            user_id: Telegram user ID (chat_id)
            task: MessageTask to send
            status_tracker: Status message tracker for this user
        """
        from telegram import InputFile

        bot = self._bot
        if bot is None:
            return

        # Build send kwargs
        kwargs: dict[str, Any] = {
            "chat_id": user_id,
            "text": task.text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }

        # Add thread_id if specified
        if task.thread_id is not None:
            kwargs["message_thread_id"] = task.thread_id

        # Handle status messages (store message_id for later deletion)
        if task.is_status_update():
            result = await bot.send_message(**kwargs)
            status_tracker.set(task.pane_key, result.message_id)
            logger.debug(f"Stored status message {result.message_id} for pane {task.pane_key}")

        # Handle status_clear (delete previous status message)
        elif task.is_status_clear():
            await self._clear_status_message(user_id, task, status_tracker)

        # Handle content with images
        elif task.image_data:
            # Send as photo with caption
            ext = "png" if b"PNG" in task.image_data[:8] else "jpg"
            filename = f"image.{ext}"

            await bot.send_photo(
                chat_id=user_id,
                photo=InputFile(task.image_data, filename=filename),
                caption=task.text,
                parse_mode="MarkdownV2",
                message_thread_id=task.thread_id,
            )

        # Handle regular content
        else:
            await bot.send_message(**kwargs)

    async def _clear_status_message(
        self, user_id: int, task: MessageTask, status_tracker: StatusMessageTracker
    ) -> None:
        """Clear a previous status message.

        Args:
            user_id: Telegram user ID
            task: MessageTask with pane_key for status to clear
            status_tracker: Status message tracker for this user
        """
        bot = self._bot
        if bot is None:
            return

        # Single lookup with pop instead of get + clear
        message_id = status_tracker.message_ids.pop(task.pane_key, None)
        if message_id:
            try:
                await bot.delete_message(chat_id=user_id, message_id=message_id)
                logger.debug(f"Cleared status message {message_id} for pane {task.pane_key}")
            except Exception as e:
                logger.debug(f"Failed to clear status message {message_id}: {e}")

    async def shutdown(self) -> None:
        """Graceful shutdown of all workers.

        Cancels all worker tasks and waits for completion.
        """
        logger.info("Shutting down MessageQueue")

        # Cancel all workers
        for user_id, worker_task in self._queue_workers.items():
            if not worker_task.done():
                worker_task.cancel()
                logger.debug(f"Cancelled worker for user {user_id}")

        # Wait for all workers to finish
        if self._queue_workers:
            await asyncio.gather(*self._queue_workers.values(), return_exceptions=True)

        # Clear state
        self._message_queues.clear()
        self._queue_workers.clear()
        self._queue_locks.clear()
        self._worker_last_activity.clear()
        self._flood_state.clear()
        self._status_messages.clear()

        logger.info("MessageQueue shutdown complete")
