"""Tests for interactive UI detection."""

import pytest

from telebridge.interactive_ui import (
    InteractiveUIDetector,
    InteractiveUIManager,
    InteractiveUIState,
    UIType,
)


# --- Pattern Detection Tests ---


def test_detect_permission_prompt_yes_no():
    """Test detection of permission prompts with Yes/No options."""
    detector = InteractiveUIDetector()
    content = """
Allow Claude to read ~/.config/app.conf?

  Yes  No
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.PERMISSION
    assert "Yes" in state.options
    assert "No" in state.options


def test_detect_permission_prompt_approve_deny():
    """Test detection of permission prompts with Approve/Deny options."""
    detector = InteractiveUIDetector()
    content = """
Allow Claude to execute shell command?

  Approve  Deny
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.PERMISSION
    assert "Approve" in state.options
    assert "Deny" in state.options


def test_detect_tool_permission():
    """Test detection of tool permission prompts."""
    detector = InteractiveUIDetector()
    content = """
Allow tool Bash to execute: rm -rf /tmp/build?

  Approve  Deny
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.TOOL_PERMISSION
    assert len(state.options) >= 2


def test_detect_multi_choice():
    """Test detection of multi-choice questions."""
    detector = InteractiveUIDetector()
    content = """
Select a model:
  1. claude-3-5-sonnet
  2. claude-3-7
  3. claude-opus-4
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.MULTI_CHOICE
    assert len(state.options) == 3
    assert "claude-3-5-sonnet" in state.options


def test_detect_multi_choice_with_parens():
    """Test detection of multi-choice with parenthesis format."""
    detector = InteractiveUIDetector()
    content = """
Which approach would you prefer?
  1) Simple implementation
  2) Complex but flexible
  3) External library
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.MULTI_CHOICE
    assert len(state.options) == 3


def test_detect_model_select():
    """Test detection of model selection UI."""
    detector = InteractiveUIDetector()
    content = """
Available models:
  claude-3-5-sonnet
  claude-3-7
  claude-opus-4
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.MODEL_SELECT
    assert len(state.options) >= 1


def test_detect_plan_exit_proceed():
    """Test detection of plan exit with Proceed option."""
    detector = InteractiveUIDetector()
    content = """
Exit plan mode and proceed with implementation?

  Proceed  Cancel
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.PLAN_EXIT
    assert "Proceed" in state.options
    assert "Cancel" in state.options


def test_detect_plan_exit_ready():
    """Test detection of plan exit with Ready prompt."""
    detector = InteractiveUIDetector()
    content = """
Ready to implement the plan?

  Yes  No
"""
    state = detector.detect(content)
    assert state is not None
    assert state.ui_type == UIType.PLAN_EXIT


def test_no_ui_detected():
    """Test that regular content returns None."""
    detector = InteractiveUIDetector()
    content = "Regular terminal output without interactive elements"
    state = detector.detect(content)
    assert state is None


def test_no_ui_detected_empty():
    """Test that empty content returns None."""
    detector = InteractiveUIDetector()
    assert detector.detect("") is None
    assert detector.detect("   ") is None
    assert detector.detect("short") is None  # Less than 10 chars


# --- InteractiveUIState Tests ---


def test_state_generates_prompt_id():
    """Test that InteractiveUIState generates a prompt_id from content."""
    state = InteractiveUIState(
        ui_type=UIType.PERMISSION,
        content="Allow Claude to read files?",
        options=["Yes", "No"],
    )
    assert state.prompt_id != ""
    assert len(state.prompt_id) == 12  # MD5 hash truncated to 12 chars


def test_state_uses_provided_prompt_id():
    """Test that provided prompt_id is preserved."""
    state = InteractiveUIState(
        ui_type=UIType.PERMISSION,
        content="Allow?",
        prompt_id="custom-id-123",
    )
    assert state.prompt_id == "custom-id-123"


def test_state_cleans_ansi_codes():
    """Test that content is cleaned of ANSI codes."""
    state = InteractiveUIState(
        ui_type=UIType.PERMISSION,
        content="\x1B[32mAllow\x1B[0m \x1B[31maccess?\x1B[0m",
    )
    assert "\x1B" not in state.content
    assert "Allow access?" in state.content


# --- Change Detection Tests ---


def test_change_detection_new_ui():
    """Test that new UI is detected."""
    manager = InteractiveUIManager()
    content = "Allow access?\nYes No"

    state = manager.check_for_ui("pane1", content)
    assert state is not None


def test_change_detection_same_ui():
    """Test that same UI is not reported twice."""
    manager = InteractiveUIManager()
    content = "Allow access?\nYes No"

    # First detection
    state1 = manager.check_for_ui("pane1", content)
    assert state1 is not None

    # Same content - should return None (no change)
    state2 = manager.check_for_ui("pane1", content)
    assert state2 is None


def test_change_detection_different_ui():
    """Test that changed UI is detected."""
    manager = InteractiveUIManager()

    # First UI
    state1 = manager.check_for_ui("pane1", "Allow access?\nYes No")
    assert state1 is not None
    assert state1.ui_type == UIType.PERMISSION

    # Different UI content
    state2 = manager.check_for_ui(
        "pane1", "Select model:\n1. sonnet\n2. opus"
    )
    assert state2 is not None
    assert state2.ui_type == UIType.MULTI_CHOICE


def test_change_detection_different_panes():
    """Test that different panes track state independently."""
    manager = InteractiveUIManager()
    content = "Allow access?\nYes No"

    # Same content, different panes - both should detect
    state1 = manager.check_for_ui("pane1", content)
    state2 = manager.check_for_ui("pane2", content)

    assert state1 is not None
    assert state2 is not None


def test_clear_state():
    """Test clearing state allows redetection."""
    manager = InteractiveUIManager()
    content = "Allow access?\nYes No"

    state1 = manager.check_for_ui("pane1", content)
    assert state1 is not None

    manager.clear_state("pane1")

    state2 = manager.check_for_ui("pane1", content)
    assert state2 is not None  # Redetected after clear


def test_clear_state_nonexistent():
    """Test clearing state for nonexistent pane doesn't error."""
    manager = InteractiveUIManager()
    manager.clear_state("nonexistent")  # Should not raise


def test_no_ui_clears_previous_state():
    """Test that no UI detection clears previous state for pane."""
    manager = InteractiveUIManager()

    # First, detect a UI
    manager.check_for_ui("pane1", "Allow access?\nYes No")

    # Then, content without UI should clear state
    state = manager.check_for_ui("pane1", "Regular output without UI")
    assert state is None

    # Same UI content should now be detected as new
    state2 = manager.check_for_ui("pane1", "Allow access?\nYes No")
    assert state2 is not None


# --- Cache Tests ---


def test_get_cached_state():
    """Test retrieving cached state by prompt_id."""
    manager = InteractiveUIManager()
    content = "Allow access?\nYes No"

    state = manager.check_for_ui("pane1", content)
    assert state is not None

    cached = manager.get_cached_state(state.prompt_id)
    assert cached is not None
    assert cached.prompt_id == state.prompt_id


def test_get_cached_state_nonexistent():
    """Test retrieving nonexistent cached state."""
    manager = InteractiveUIManager()
    cached = manager.get_cached_state("nonexistent-id")
    assert cached is None


def test_clear_all():
    """Test clearing all cached state."""
    manager = InteractiveUIManager()

    # Create multiple states
    manager.check_for_ui("pane1", "Allow access?\nYes No")
    manager.check_for_ui("pane2", "Select:\n1. A\n2. B")

    manager.clear_all()

    # Both should be cleared
    assert manager.get_cached_state("pane1") is None


# --- Content Cleaning Tests ---


def test_clean_content_truncation():
    """Test that long content is truncated."""
    detector = InteractiveUIDetector()
    long_content = "Allow Claude to read files?\nYes No\n" + "x" * 2000

    state = detector.detect(long_content)
    assert state is not None
    assert len(state.content) <= 1003  # 1000 + "..."


def test_clean_content_preserves_short():
    """Test that short content is preserved."""
    detector = InteractiveUIDetector()
    content = "Allow Claude to proceed?\nYes No"

    state = detector.detect(content)
    assert state is not None
    assert "Allow" in state.content


# --- Option Extraction Tests ---


def test_extract_permission_options():
    """Test option extraction for permission prompts."""
    detector = InteractiveUIDetector()
    content = "Allow file read?\nYes No Approve Deny"

    state = detector.detect(content)
    assert state is not None
    assert "Yes" in state.options
    assert "No" in state.options


def test_extract_multi_choice_options():
    """Test option extraction for multi-choice prompts."""
    detector = InteractiveUIDetector()
    content = """
Choose an option:
  1. First choice
  2. Second choice
  3. Third choice
"""
    state = detector.detect(content)
    assert state is not None
    assert "First choice" in state.options
    assert "Second choice" in state.options
    assert "Third choice" in state.options


def test_extract_model_options():
    """Test option extraction for model selection."""
    detector = InteractiveUIDetector()
    content = """
Available models:
  claude-3-5-sonnet
  claude-3-7
  claude-opus-4
"""
    state = detector.detect(content)
    assert state is not None
    # Should extract model names
    assert len(state.options) >= 1


# --- LRU Cache Eviction Tests ---


def test_lru_eviction_removes_oldest():
    """Test that LRU eviction removes least recently accessed entries."""
    # Small cache to force eviction
    manager = InteractiveUIManager(max_size=3)

    # Add 3 entries to fill cache
    state1 = manager.check_for_ui("pane1", "Allow A?\nYes No")
    state2 = manager.check_for_ui("pane2", "Allow B?\nYes No")
    state3 = manager.check_for_ui("pane3", "Allow C?\nYes No")

    assert state1 is not None
    assert state2 is not None
    assert state3 is not None

    # Access state1 to make it recently used
    manager.get_cached_state(state1.prompt_id)

    # Add 4th entry - should evict state2 (least recently accessed)
    state4 = manager.check_for_ui("pane4", "Allow D?\nYes No")
    assert state4 is not None

    # state1 should still be cached (recently accessed)
    assert manager.get_cached_state(state1.prompt_id) is not None
    # state2 should be evicted (was least recently accessed)
    assert manager.get_cached_state(state2.prompt_id) is None


def test_lru_eviction_enforces_max_size():
    """Test that cache never exceeds max_size."""
    manager = InteractiveUIManager(max_size=5)

    # Add more entries than max_size
    for i in range(10):
        manager.check_for_ui(f"pane{i}", f"Allow {i}?\nYes No")

    # Check internal cache size
    assert len(manager._state_cache) <= 5


def test_lru_get_cached_updates_access_time():
    """Test that get_cached_state moves entry to end of OrderedDict for LRU tracking."""
    manager = InteractiveUIManager()
    state1 = manager.check_for_ui("pane1", "Allow A?\nYes No")
    state2 = manager.check_for_ui("pane2", "Allow B?\nYes No")
    assert state1 is not None
    assert state2 is not None

    # state1 was added first, so it should be at front
    keys = list(manager._state_cache.keys())
    assert keys[0] == state1.prompt_id
    assert keys[1] == state2.prompt_id

    # Access state1 - should move to end
    manager.get_cached_state(state1.prompt_id)

    # Now state1 should be at end (most recently used)
    keys = list(manager._state_cache.keys())
    assert keys[0] == state2.prompt_id
    assert keys[1] == state1.prompt_id


# --- TTL Cache Expiration Tests ---


def test_ttl_expiration_removes_old_entries():
    """Test that TTL removes entries older than ttl_seconds."""
    from unittest.mock import patch
    import time

    # Very short TTL for testing
    manager = InteractiveUIManager(max_size=100, ttl_seconds=1.0)

    # Add an entry at time 0
    with patch("time.time", return_value=0.0):
        state = manager.check_for_ui("pane1", "Allow A?\nYes No")
        assert state is not None
        prompt_id = state.prompt_id

    # Check it's cached
    assert manager.get_cached_state(prompt_id) is not None

    # Move time past TTL and add a new entry (triggers cleanup)
    with patch("time.time", return_value=2.0):
        new_state = manager.check_for_ui("pane2", "Allow B?\nYes No")
        assert new_state is not None

    # Old entry should be expired
    assert manager.get_cached_state(prompt_id) is None


def test_ttl_preserves_recent_entries():
    """Test that TTL doesn't remove entries within TTL window."""
    from unittest.mock import patch

    manager = InteractiveUIManager(max_size=100, ttl_seconds=60.0)

    # Add entry at time 0
    with patch("time.time", return_value=0.0):
        state = manager.check_for_ui("pane1", "Allow A?\nYes No")
        prompt_id = state.prompt_id

    # At time 30 (within TTL), add new entry
    with patch("time.time", return_value=30.0):
        manager.check_for_ui("pane2", "Allow B?\nYes No")

    # Original entry should still be cached
    assert manager.get_cached_state(prompt_id) is not None


def test_ttl_and_lru_work_together():
    """Test that TTL and LRU both apply during cleanup."""
    from unittest.mock import patch

    # Small cache with short TTL
    manager = InteractiveUIManager(max_size=3, ttl_seconds=10.0)

    # Add 3 entries at time 0
    with patch("time.time", return_value=0.0):
        s1 = manager.check_for_ui("p1", "Allow A?\nYes No")
        s2 = manager.check_for_ui("p2", "Allow B?\nYes No")
        s3 = manager.check_for_ui("p3", "Allow C?\nYes No")

    # At time 15 (past TTL), add new entry
    with patch("time.time", return_value=15.0):
        s4 = manager.check_for_ui("p4", "Allow D?\nYes No")

    # All old entries should be expired (TTL)
    assert manager.get_cached_state(s1.prompt_id) is None
    assert manager.get_cached_state(s2.prompt_id) is None
    assert manager.get_cached_state(s3.prompt_id) is None
    # New entry should be cached
    assert manager.get_cached_state(s4.prompt_id) is not None


def test_configurable_cache_parameters():
    """Test that cache parameters can be configured."""
    manager = InteractiveUIManager(max_size=50, ttl_seconds=300.0)

    assert manager._max_size == 50
    assert manager._ttl_seconds == 300.0


def test_default_cache_parameters():
    """Test that default cache parameters are reasonable."""
    from telebridge.interactive_ui import CACHE_MAX_SIZE, CACHE_TTL_SECONDS

    assert CACHE_MAX_SIZE == 100
    assert CACHE_TTL_SECONDS == 1800.0  # 30 minutes
