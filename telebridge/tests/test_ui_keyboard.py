"""Tests for UI keyboard builder."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telebridge.interactive_ui import InteractiveUIState, UIType
from telebridge.ui_keyboard import build_interactive_keyboard


def test_build_permission_keyboard():
    """Test keyboard for permission prompts."""
    state = InteractiveUIState(
        ui_type=UIType.PERMISSION,
        content="Allow Claude to read ~/.claude/config?",
        options=["Yes", "No"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert len(keyboard.inline_keyboard) == 2  # Options row + Refresh


def test_build_tool_permission_keyboard():
    """Test keyboard for tool permission prompts."""
    state = InteractiveUIState(
        ui_type=UIType.TOOL_PERMISSION,
        content="Allow tool Bash with command 'rm -rf /'?",
        options=["Approve", "Deny"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Should have Allow/Deny buttons
    assert len(keyboard.inline_keyboard) >= 1


def test_build_multi_choice_keyboard():
    """Test keyboard for multi-choice questions."""
    state = InteractiveUIState(
        ui_type=UIType.MULTI_CHOICE,
        content="Select a model:",
        options=["claude-3-5-sonnet", "claude-3-7", "claude-opus-4"],
        current_selection=1,  # Second option selected
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Should have option buttons + navigation row
    assert len(keyboard.inline_keyboard) == 4  # 3 options + 1 nav row


def test_build_plan_exit_keyboard():
    """Test keyboard for plan mode exit."""
    state = InteractiveUIState(
        ui_type=UIType.PLAN_EXIT,
        content="Exit plan mode?",
        options=["Proceed", "Cancel"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Plan mode has full navigation
    assert len(keyboard.inline_keyboard) >= 1


def test_build_checkpoint_keyboard():
    """Test keyboard for checkpoint selection (vertical only)."""
    state = InteractiveUIState(
        ui_type=UIType.CHECKPOINT,
        content="Select checkpoint:",
        options=["checkpoint-1", "checkpoint-2"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Checkpoints should NOT have left/right arrows
    # Find the navigation row and verify no left/right
    nav_row = keyboard.inline_keyboard[-1]
    callbacks = [btn.callback_data for btn in nav_row]
    # Check for absence of left/right
    assert not any("left" in cb for cb in callbacks)
    assert not any("right" in cb for cb in callbacks)


def test_build_model_select_keyboard():
    """Test keyboard for model selection."""
    state = InteractiveUIState(
        ui_type=UIType.MODEL_SELECT,
        content="Select model:",
        options=["claude-3-5-sonnet", "claude-opus-4"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    assert isinstance(keyboard, InlineKeyboardMarkup)
    # Model selection has full navigation
    assert len(keyboard.inline_keyboard) >= 1


def test_multi_choice_direct_selection():
    """Test that multi-choice has direct selection buttons."""
    state = InteractiveUIState(
        ui_type=UIType.MULTI_CHOICE,
        content="Which approach?",
        options=["Option A", "Option B", "Option C"],
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    # Check for sel:0, sel:1, sel:2 callback data
    all_callbacks = []
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.callback_data:
                all_callbacks.append(button.callback_data)

    # Should have selection callbacks for each option
    assert any("sel:0" in cb for cb in all_callbacks)
    assert any("sel:1" in cb for cb in all_callbacks)
    assert any("sel:2" in cb for cb in all_callbacks)


def test_permission_fallback():
    """Test permission keyboard with non-standard options."""
    state = InteractiveUIState(
        ui_type=UIType.PERMISSION,
        content="Do something?",
        options=["Maybe", "Later"],  # Non-standard
        current_selection=0,
    )
    keyboard = build_interactive_keyboard(state)

    # Should still have buttons (fallback to Yes/No)
    assert len(keyboard.inline_keyboard) >= 1
