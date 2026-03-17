"""Unit tests for message_queue.py.

Tests cover:
- MessageTask dataclass creation and methods
- FloodControlState ban management
- MessageQueue enqueue and worker creation
- Content merging logic
- Flood control handling
- Status message tracking and clearing
- Graceful shutdown
"""

import asyncio
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from telebridge.message_queue import (
    MessageTask,
    FloodControlState,
    StatusMessageTracker,
    MessageQueue,
    TASK_TYPE_CONTENT,
    TASK_TYPE_STATUS_UPDATE,
    TASK_TYPE_STATUS_CLEAR,
    _MAX_MERGED_LENGTH,
)


# --- MessageTask Tests ---


def test_message_task_creation() -> None:
    """Test MessageTask dataclass creation."""
    task = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Hello, world!",
        pane_key="session1",
        content_type="text",
    )

    assert task.task_type == TASK_TYPE_CONTENT
    assert task.text == "Hello, world!"
    assert task.pane_key == "session1"
    assert task.content_type == "text"


def test_message_task_is_content() -> None:
    """Test MessageTask.is_content() method."""
    content_task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test")
    status_task = MessageTask(task_type=TASK_TYPE_STATUS_UPDATE, text="thinking")

    assert content_task.is_content() is True
    assert status_task.is_content() is False


def test_message_task_is_status_update() -> None:
    """Test MessageTask.is_status_update() method."""
    status_task = MessageTask(task_type=TASK_TYPE_STATUS_UPDATE, text="thinking")
    content_task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test")

    assert status_task.is_status_update() is True
    assert content_task.is_status_update() is False


def test_message_task_is_status_clear() -> None:
    """Test MessageTask.is_status_clear() method."""
    clear_task = MessageTask(task_type=TASK_TYPE_STATUS_CLEAR, text="")
    content_task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test")

    assert clear_task.is_status_clear() is True
    assert content_task.is_status_clear() is False


def test_message_task_is_tool_entry() -> None:
    """Test MessageTask.is_tool_entry() method."""
    tool_use_task = MessageTask(
        task_type=TASK_TYPE_CONTENT, content_type="tool_use", text="**Read**(file.py)"
    )
    tool_result_task = MessageTask(
        task_type=TASK_TYPE_CONTENT, content_type="tool_result", text="result"
    )
    text_task = MessageTask(
        task_type=TASK_TYPE_CONTENT, content_type="text", text="hello"
    )

    assert tool_use_task.is_tool_entry() is True
    assert tool_result_task.is_tool_entry() is True
    assert text_task.is_tool_entry() is False


def test_message_task_combined_length() -> None:
    """Test MessageTask.combined_length() calculation."""
    task1 = MessageTask(task_type=TASK_TYPE_CONTENT, text="Hello")
    task2 = MessageTask(task_type=TASK_TYPE_CONTENT, text="World")

    # "Hello" (5) + "World" (5) + "\n\n" (2) = 12
    assert task1.combined_length(task2) == 12


# --- FloodControlState Tests ---


def test_flood_control_state_initial() -> None:
    """Test initial FloodControlState."""
    state = FloodControlState()

    assert state.banned_until == 0.0
    assert state.retry_after == 0
    assert state.last_error == ""
    assert state.is_banned(0.0) is False


def test_flood_control_state_is_banned() -> None:
    """Test FloodControlState.is_banned()."""
    state = FloodControlState()

    # Set ban for 10 seconds
    state.set_ban(10, "Test flood")

    now = time.time()
    assert state.is_banned(now) is True  # Should be banned
    assert state.is_banned(now + 15) is False  # Should be unbanned after 15s


def test_flood_control_state_get_wait_time() -> None:
    """Test FloodControlState.get_wait_time()."""
    state = FloodControlState()

    # Set ban for 10 seconds
    state.set_ban(10, "Test flood")

    now = time.time()
    wait_time = state.get_wait_time(now)

    # Wait time should be close to 10 seconds
    assert 9.0 < wait_time < 11.0


def test_flood_control_state_set_ban_with_int() -> None:
    """Test FloodControlState.set_ban() with int."""
    state = FloodControlState()

    state.set_ban(15, "Rate limit exceeded")

    now = time.time()
    assert state.banned_until > now
    assert state.retry_after == 15
    assert state.last_error == "Rate limit exceeded"


def test_flood_control_state_set_ban_with_timedelta() -> None:
    """Test FloodControlState.set_ban() with timedelta."""
    state = FloodControlState()

    state.set_ban(timedelta(seconds=20), "Rate limit exceeded")

    now = time.time()
    assert state.banned_until > now
    assert state.retry_after == 20
    assert state.last_error == "Rate limit exceeded"


def test_flood_control_state_clear() -> None:
    """Test FloodControlState.clear()."""
    state = FloodControlState()

    # Set a ban
    state.set_ban(10, "Test flood")
    assert state.is_banned(0) is True

    # Clear the ban
    state.clear()
    assert state.is_banned(0) is False
    assert state.banned_until == 0.0
    assert state.retry_after == 0
    assert state.last_error == ""


# --- StatusMessageTracker Tests ---


def test_status_message_tracker_set_get() -> None:
    """Test StatusMessageTracker.set() and get()."""
    tracker = StatusMessageTracker()

    tracker.set("session1", 123)
    assert tracker.get("session1") == 123
    assert tracker.get("session2") is None


def test_status_message_tracker_clear() -> None:
    """Test StatusMessageTracker.clear()."""
    tracker = StatusMessageTracker()

    tracker.set("session1", 123)
    assert tracker.get("session1") == 123

    tracker.clear("session1")
    assert tracker.get("session1") is None

    # Clearing non-existent key should not raise
    tracker.clear("session2")


# --- MessageQueue Tests ---


@pytest.fixture
def mock_bot() -> MagicMock:
    """Create a mock Telegram bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.delete_message = AsyncMock()
    return bot


@pytest.fixture
def message_queue(mock_bot: MagicMock) -> MessageQueue:
    """Create a MessageQueue instance with mock bot."""
    queue = MessageQueue()
    queue.set_bot(mock_bot)
    return queue


@pytest.mark.asyncio
async def test_message_queue_enqueue_creates_worker(message_queue: MessageQueue) -> None:
    """Test that enqueue creates a worker for a new user."""
    task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test")

    # Initially no queues
    assert len(message_queue._message_queues) == 0

    # Enqueue should create queue and worker
    await message_queue.enqueue(task, user_id=123)

    assert 123 in message_queue._message_queues
    assert 123 in message_queue._queue_workers
    assert 123 in message_queue._queue_locks
    assert 123 in message_queue._flood_state
    assert 123 in message_queue._status_messages


@pytest.mark.asyncio
async def test_message_queue_multiple_users(message_queue: MessageQueue) -> None:
    """Test that multiple users get separate queues."""
    task1 = MessageTask(task_type=TASK_TYPE_CONTENT, text="test1")
    task2 = MessageTask(task_type=TASK_TYPE_CONTENT, text="test2")

    await message_queue.enqueue(task1, user_id=111)
    await message_queue.enqueue(task2, user_id=222)

    assert len(message_queue._message_queues) == 2
    assert 111 in message_queue._message_queues
    assert 222 in message_queue._message_queues


@pytest.mark.asyncio
async def test_message_queue_shutdown(message_queue: MessageQueue) -> None:
    """Test MessageQueue.shutdown() cancels workers."""
    task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test")

    await message_queue.enqueue(task, user_id=123)

    # Worker should exist
    assert 123 in message_queue._queue_workers
    worker = message_queue._queue_workers[123]
    assert not worker.done()

    # Shutdown should cancel worker
    await message_queue.shutdown()

    # State should be cleared
    assert len(message_queue._message_queues) == 0
    assert len(message_queue._queue_workers) == 0


# --- Content Merging Tests ---


@pytest.mark.asyncio
async def test_merge_content_tasks_single_task(message_queue: MessageQueue) -> None:
    """Test _merge_content_tasks with a single unmergeable task."""
    status_task = MessageTask(
        task_type=TASK_TYPE_STATUS_UPDATE, text="thinking...", pane_key="session1"
    )

    result = await message_queue._merge_content_tasks(123, status_task)

    assert len(result) == 1
    assert result[0] == status_task


@pytest.mark.asyncio
async def test_merge_content_tasks_mergeable(message_queue: MessageQueue) -> None:
    """Test _merge_content_tasks with mergeable tasks."""
    # Enqueue first task
    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First message",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    # Enqueue mergeable tasks
    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Second message",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task3 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Third message",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    # Enqueue all tasks
    await message_queue.enqueue(task1, user_id=123)
    await message_queue.enqueue(task2, user_id=123)
    await message_queue.enqueue(task3, user_id=123)

    # Give worker time to process
    await asyncio.sleep(0.1)

    # The tasks should have been merged and sent
    # Check that bot.send_message was called with merged text
    # Note: This is a simplified test - real testing would need
    # to inspect the worker's actual behavior


def test_can_merge_both_content() -> None:
    """Test _can_merge with both content tasks."""
    queue = MessageQueue()

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Second",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    assert queue._can_merge(task1, task2) is True


def test_can_merge_different_types() -> None:
    """Test _can_merge with different task types."""
    queue = MessageQueue()

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_STATUS_UPDATE,
        text="thinking",
        pane_key="session1",
        content_type="thinking",
        thread_id=None,
    )

    assert queue._can_merge(task1, task2) is False


def test_can_merge_different_panes() -> None:
    """Test _can_merge with different pane_keys."""
    queue = MessageQueue()

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Second",
        pane_key="session2",
        content_type="text",
        thread_id=None,
    )

    assert queue._can_merge(task1, task2) is False


def test_can_merge_tool_entry() -> None:
    """Test _can_merge with tool_use entries."""
    queue = MessageQueue()

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First",
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="**Read**(file.py)",
        pane_key="session1",
        content_type="tool_use",
        thread_id=None,
    )

    assert queue._can_merge(task1, task2) is False


def test_can_merge_different_threads() -> None:
    """Test _can_merge with different thread_ids."""
    queue = MessageQueue()

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="First",
        pane_key="session1",
        content_type="text",
        thread_id=1,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text="Second",
        pane_key="session1",
        content_type="text",
        thread_id=2,
    )

    assert queue._can_merge(task1, task2) is False


def test_can_merge_length_limit() -> None:
    """Test _can_merge respects length limit."""
    queue = MessageQueue()

    # Create tasks that would exceed limit
    long_text = "x" * (_MAX_MERGED_LENGTH // 2)

    task1 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text=long_text,
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    task2 = MessageTask(
        task_type=TASK_TYPE_CONTENT,
        text=long_text,
        pane_key="session1",
        content_type="text",
        thread_id=None,
    )

    assert queue._can_merge(task1, task2) is False


# --- Flood Control Tests ---


@pytest.mark.asyncio
async def test_send_task_drops_status_during_flood(message_queue: MessageQueue) -> None:
    """Test that status messages are dropped during flood control."""
    # Set flood control
    flood_state = message_queue._flood_state[123] = FloodControlState()
    flood_state.set_ban(60, "Rate limited")

    status_task = MessageTask(
        task_type=TASK_TYPE_STATUS_UPDATE,
        text="thinking...",
        pane_key="session1",
    )

    # Should not raise, just drop the message
    await message_queue._send_task(123, status_task)

    # Bot should not have been called
    assert message_queue._bot.send_message.call_count == 0


@pytest.mark.asyncio
async def test_flood_control_short_retry(message_queue: MessageQueue) -> None:
    """Test flood control with short retry delay."""
    from telegram.error import RetryAfter

    # Mock bot to raise RetryAfter with short delay
    call_count = [0]

    async def send_message_with_retry(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RetryAfter(retry_after=5)
        return MagicMock(message_id=123)

    message_queue._bot.send_message = send_message_with_retry  # type: ignore

    task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test message")

    # Should retry and succeed
    await message_queue._send_task(123, task)

    assert call_count[0] == 2  # Initial call + retry


@pytest.mark.asyncio
async def test_flood_control_long_retry_sets_ban(message_queue: MessageQueue) -> None:
    """Test flood control with long retry delay sets ban."""
    from telegram.error import RetryAfter

    # Mock bot to raise RetryAfter with long delay
    async def send_message_with_long_retry(*args, **kwargs):
        raise RetryAfter(retry_after=30)

    message_queue._bot.send_message = send_message_with_long_retry  # type: ignore

    task = MessageTask(task_type=TASK_TYPE_CONTENT, text="test message")

    # Should set ban and raise
    with pytest.raises(RetryAfter):
        await message_queue._send_task(123, task)

    # Check flood state
    flood_state = message_queue._flood_state[123]
    assert flood_state.is_banned(0) is True
    assert flood_state.retry_after == 30


# --- Status Message Tests ---


@pytest.mark.asyncio
async def test_status_clear_deletes_message(message_queue: MessageQueue) -> None:
    """Test that status_clear deletes the previous status message."""
    # Initialize user state
    message_queue._flood_state[123] = FloodControlState()
    message_queue._status_messages[123] = StatusMessageTracker()

    # Set up status tracker with a message_id
    status_tracker = message_queue._status_messages[123]
    status_tracker.set("session1", 999)

    # Create status_clear task
    clear_task = MessageTask(
        task_type=TASK_TYPE_STATUS_CLEAR,
        text="",
        pane_key="session1",
    )

    # Send should delete the message
    await message_queue._send_task(123, clear_task)

    # delete_message should have been called
    message_queue._bot.delete_message.assert_called_once_with(
        chat_id=123, message_id=999
    )

    # Status tracker should be cleared
    assert status_tracker.get("session1") is None


@pytest.mark.asyncio
async def test_status_update_stores_message_id(message_queue: MessageQueue) -> None:
    """Test that status_update stores the message_id."""
    # Mock send_message to return a message with ID
    async def send_message(*args, **kwargs):
        result = MagicMock()
        result.message_id = 456
        return result

    message_queue._bot.send_message = send_message  # type: ignore

    # Create status_update task
    status_task = MessageTask(
        task_type=TASK_TYPE_STATUS_UPDATE,
        text="Thinking...",
        pane_key="session1",
    )

    # Send the task
    await message_queue._send_task(123, status_task)

    # Status tracker should have the message_id
    status_tracker = message_queue._status_messages[123]
    assert status_tracker.get("session1") == 456
