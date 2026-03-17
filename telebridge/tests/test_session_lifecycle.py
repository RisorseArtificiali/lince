"""Tests for session lifecycle management (LINCE-13)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telebridge.session_manager import (
    PaneState,
    SessionInfo,
    SessionManager,
    SessionManagerState,
)
from telebridge.handlers.claude_commands import _generate_callback_id


# --- Fixtures ---

@pytest.fixture
def mock_config():
    """Create a mock TelebridgeConfig."""
    config = MagicMock()
    config.state_dir = MagicMock()
    config.state_dir.mkdir = MagicMock()
    config.state_dir.exists = MagicMock(return_value=True)
    return config


@pytest.fixture
def mock_bridge():
    """Create a mock MultiplexerBridge."""
    bridge = MagicMock()
    bridge.list_panes = MagicMock(return_value=["session1", "session2"])
    return bridge


@pytest.fixture
def session_manager(mock_config):
    """Create a SessionManager instance."""
    manager = SessionManager(mock_config)
    manager.state = SessionManagerState()
    return manager


# --- Session Liveness Tests ---

@pytest.mark.asyncio
async def test_is_pane_live_with_valid_pane(session_manager, mock_bridge):
    """Test is_pane_live returns True for existing pane."""
    mock_bridge.list_panes = MagicMock(return_value=["session1", "session2"])

    result = await session_manager.is_pane_live("session1", mock_bridge)
    assert result is True


@pytest.mark.asyncio
async def test_is_pane_live_with_invalid_pane(session_manager, mock_bridge):
    """Test is_pane_live returns False for non-existent pane."""
    mock_bridge.list_panes = MagicMock(return_value=["session1", "session2"])

    result = await session_manager.is_pane_live("invalid", mock_bridge)
    assert result is False


@pytest.mark.asyncio
async def test_is_pane_live_with_bridge_error(session_manager, mock_bridge):
    """Test is_pane_live returns False when bridge raises RuntimeError."""
    mock_bridge.list_panes = MagicMock(side_effect=RuntimeError("Bridge error"))

    result = await session_manager.is_pane_live("session1", mock_bridge)
    assert result is False


@pytest.mark.asyncio
async def test_is_session_active_with_live_session(session_manager, mock_bridge):
    """Test is_session_active returns True for live session."""
    mock_bridge.list_panes = MagicMock(return_value=["session1"])

    # Set up session state
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )

    result = await session_manager.is_session_active("session1", mock_bridge)
    assert result is True


@pytest.mark.asyncio
async def test_is_session_active_with_dead_pane(session_manager, mock_bridge):
    """Test is_session_active returns False for dead pane."""
    mock_bridge.list_panes = MagicMock(return_value=[])  # No panes

    result = await session_manager.is_session_active("session1", mock_bridge)
    assert result is False


@pytest.mark.asyncio
async def test_is_session_active_with_no_session_id(session_manager, mock_bridge):
    """Test is_session_active returns False when pane has no session_id."""
    mock_bridge.list_panes = MagicMock(return_value=["session1"])

    # Set up pane state without session_id
    session_manager.state.window_states["session1"] = PaneState(
        session_id="", cwd="/tmp", pane_name="session1"
    )

    result = await session_manager.is_session_active("session1", mock_bridge)
    assert result is False


# --- Session Resolution Tests ---

@pytest.mark.asyncio
async def test_resolve_session_for_thread_checked_live(session_manager, mock_bridge):
    """Test resolve_session_for_thread_checked returns SessionInfo for live session."""
    mock_bridge.list_panes = MagicMock(return_value=["session1"])

    # Set up binding and state
    session_manager.bind_thread(123, 1, "session1")
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )

    result = await session_manager.resolve_session_for_thread_checked(123, 1, mock_bridge)
    assert result is not None
    assert result.session_id == "abc123"


@pytest.mark.asyncio
async def test_resolve_session_for_thread_checked_dead(session_manager, mock_bridge):
    """Test resolve_session_for_thread_checked returns None for dead session."""
    mock_bridge.list_panes = MagicMock(return_value=[])  # No panes

    # Set up binding but pane is dead
    session_manager.bind_thread(123, 1, "session1")

    result = await session_manager.resolve_session_for_thread_checked(123, 1, mock_bridge)
    assert result is None


@pytest.mark.asyncio
async def test_resolve_session_for_thread_checked_no_binding(session_manager, mock_bridge):
    """Test resolve_session_for_thread_checked returns None when no binding."""
    mock_bridge.list_panes = MagicMock(return_value=["session1"])

    result = await session_manager.resolve_session_for_thread_checked(123, 1, mock_bridge)
    assert result is None


# --- Binding Tests ---

def test_bind_thread_creates_binding(session_manager):
    """Test bind_thread creates a new binding."""
    session_manager.bind_thread(123, 1, "session1")

    assert session_manager.resolve_pane_for_thread(123, 1) == "session1"


def test_bind_thread_updates_existing(session_manager):
    """Test bind_thread updates existing binding."""
    session_manager.bind_thread(123, 1, "session1")
    session_manager.bind_thread(123, 1, "session2")

    assert session_manager.resolve_pane_for_thread(123, 1) == "session2"


def test_unbind_thread_removes_binding(session_manager):
    """Test unbind_thread removes binding."""
    session_manager.bind_thread(123, 1, "session1")
    session_manager.unbind_thread(123, 1)

    assert session_manager.resolve_pane_for_thread(123, 1) is None


def test_resolve_pane_for_thread_no_binding(session_manager):
    """Test resolve_pane_for_thread returns None when no binding."""
    result = session_manager.resolve_pane_for_thread(123, 1)
    assert result is None


# --- Session Resolution Tests ---

def test_resolve_session_for_pane_no_state(session_manager):
    """Test resolve_session_for_pane returns None when no state."""
    result = session_manager.resolve_session_for_pane("session1")
    assert result is None


def test_resolve_session_for_pane_no_session_id(session_manager):
    """Test resolve_session_for_pane returns None when no session_id."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="", cwd="/tmp", pane_name="session1"
    )

    result = session_manager.resolve_session_for_pane("session1")
    assert result is None


def test_resolve_session_for_pane_with_session(session_manager):
    """Test resolve_session_for_pane returns SessionInfo."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )

    result = session_manager.resolve_session_for_pane("session1")
    assert result is not None
    assert result.session_id == "abc123"
    assert result.pane_key == "session1"
    assert result.cwd == "/tmp"


# --- New Session Tests ---

def test_generate_callback_id():
    """Test callback ID generation is unique."""
    id1 = _generate_callback_id()
    id2 = _generate_callback_id()

    assert id1 != id2
    assert len(id1) == 12
    assert len(id2) == 12


@pytest.mark.asyncio
async def test_poll_for_new_session_timeout(session_manager):
    """Test poll_for_new_session returns None on timeout."""
    from telebridge.handlers.claude_commands import _poll_for_new_session

    result = await _poll_for_new_session(session_manager, "session1", timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_poll_for_new_session_finds_session(session_manager):
    """Test poll_for_new_session finds new session."""
    from telebridge.handlers.claude_commands import _poll_for_new_session

    # Simulate session appearing after 0.2 seconds
    async def add_session_later():
        import asyncio
        await asyncio.sleep(0.2)
        session_manager.state.window_states["session1"] = PaneState(
            session_id="new123", cwd="/tmp", pane_name="session1"
        )

    import asyncio
    task = asyncio.create_task(add_session_later())
    result = await _poll_for_new_session(session_manager, "session1", timeout=1.0)

    await task
    assert result == "new123"


# --- List Active Sessions Tests ---

def test_list_active_sessions_empty(session_manager):
    """Test list_active_sessions returns empty list."""
    result = session_manager.list_active_sessions()
    assert result == []


def test_list_active_sessions_with_sessions(session_manager):
    """Test list_active_sessions returns sessions."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )
    session_manager.state.window_states["session2"] = PaneState(
        session_id="def456", cwd="/home", pane_name="session2"
    )

    result = session_manager.list_active_sessions()
    assert len(result) == 2
    assert any(s.session_id == "abc123" for s in result)
    assert any(s.session_id == "def456" for s in result)


def test_list_active_sessions_excludes_empty(session_manager):
    """Test list_active_sessions excludes panes without session_id."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )
    session_manager.state.window_states["session2"] = PaneState(
        session_id="", cwd="/home", pane_name="session2"
    )

    result = session_manager.list_active_sessions()
    assert len(result) == 1
    assert result[0].session_id == "abc123"


# --- Clear Pane Session Tests ---

def test_clear_pane_session_removes_session_id(session_manager):
    """Test clear_pane_session removes session_id."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )

    session_manager.clear_pane_session("session1")

    assert session_manager.state.window_states["session1"].session_id == ""


def test_clear_pane_session_no_change_if_empty(session_manager):
    """Test clear_pane_session doesn't save if already empty."""
    session_manager.state.window_states["session1"] = PaneState(
        session_id="", cwd="/tmp", pane_name="session1"
    )

    # Mock save to track if it's called
    original_save = session_manager.save
    session_manager.save = MagicMock()

    session_manager.clear_pane_session("session1")

    # Save should not be called if session_id was already empty
    session_manager.save.assert_not_called()

    # Restore original
    session_manager.save = original_save


# --- Cleanup Stale Panes Tests ---

@pytest.mark.asyncio
async def test_cleanup_stale_panes_removes_dead_panes(session_manager, mock_bridge):
    """Test cleanup_stale_panes removes dead panes."""
    mock_bridge.list_panes = MagicMock(return_value=["session2"])

    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )
    session_manager.state.window_states["session2"] = PaneState(
        session_id="def456", cwd="/home", pane_name="session2"
    )

    await session_manager.cleanup_stale_panes(mock_bridge)

    assert "session1" not in session_manager.state.window_states
    assert "session2" in session_manager.state.window_states


@pytest.mark.asyncio
async def test_cleanup_stale_panes_cleans_bindings(session_manager, mock_bridge):
    """Test cleanup_stale_panes cleans thread bindings."""
    mock_bridge.list_panes = MagicMock(return_value=["session2"])

    # Set up window states (required for cleanup to detect stale panes)
    session_manager.state.window_states["session1"] = PaneState(
        session_id="abc123", cwd="/tmp", pane_name="session1"
    )
    session_manager.state.window_states["session2"] = PaneState(
        session_id="def456", cwd="/home", pane_name="session2"
    )

    # Set up bindings
    session_manager.bind_thread(123, 1, "session1")
    session_manager.bind_thread(123, 2, "session2")

    await session_manager.cleanup_stale_panes(mock_bridge)

    # Binding for session1 should be removed
    assert session_manager.resolve_pane_for_thread(123, 1) is None
    # Binding for session2 should remain
    assert session_manager.resolve_pane_for_thread(123, 2) == "session2"


@pytest.mark.asyncio
async def test_cleanup_stale_panes_handles_bridge_error(session_manager, mock_bridge):
    """Test cleanup_stale_panes handles bridge errors gracefully."""
    mock_bridge.list_panes = MagicMock(side_effect=RuntimeError("Bridge error"))

    # Should not raise exception
    await session_manager.cleanup_stale_panes(mock_bridge)

    # State should remain unchanged
    assert session_manager.state.window_states == {}


# --- Persistence Tests ---

def test_save_creates_atomic_write(session_manager, mock_config, tmp_path):
    """Test save creates atomic write with correct prefix."""
    import tempfile
    from pathlib import Path

    # Mock the state path
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        session_manager._state_path = state_path

        # Add some state
        session_manager.bind_thread(123, 1, "session1")

        # Save
        session_manager.save()

        # Check file was created
        assert state_path.exists()


def test_load_reads_state_correctly(session_manager, mock_config, tmp_path):
    """Test load reads state from disk."""
    import json
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.json"
        session_manager._state_path = state_path

        # Write test state
        test_data = {
            "window_states": {
                "session1": {"session_id": "abc123", "cwd": "/tmp", "pane_name": "session1"}
            },
            "thread_bindings": {"123": {"1": "session1"}},
            "user_pane_offsets": {},
        }

        with open(state_path, "w") as f:
            json.dump(test_data, f)

        # Load
        session_manager.load()

        # Verify state was loaded
        assert session_manager.state.window_states["session1"].session_id == "abc123"
        assert session_manager.resolve_pane_for_thread(123, 1) == "session1"


def test_load_handles_missing_file(session_manager, mock_config, tmp_path):
    """Test load handles missing file gracefully."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "nonexistent.json"
        session_manager._state_path = state_path

        # Should not raise exception
        session_manager.load()

        # State should remain empty
        assert session_manager.state.window_states == {}
