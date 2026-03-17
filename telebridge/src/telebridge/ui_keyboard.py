"""Inline keyboard builder for interactive UI prompts."""

from __future__ import annotations

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from telebridge.interactive_ui import InteractiveUIState, UIType
from telebridge.utils import CALLBACK_PREFIX_UI

logger = logging.getLogger(__name__)

# Constants for keyboard layout
# Telegram button text limit is 64 chars, but we reserve space for marker
MAX_BUTTON_TEXT_LENGTH = 30
# Telegram limits: 100 buttons per keyboard, practical UX limit is ~8-10
MAX_MULTI_CHOICE_OPTIONS = 8


def _nav_button(text: str, action: str) -> InlineKeyboardButton:
    """Create a navigation button with callback data.

    Args:
        text: Button text/emoji
        action: Action type (up, down, enter, esc, refresh)

    Returns:
        InlineKeyboardButton with callback data
    """
    return InlineKeyboardButton(text, callback_data=f"{CALLBACK_PREFIX_UI}{action}")


def _build_nav_row(include_left_right: bool) -> list[InlineKeyboardButton]:
    """Build navigation row with optional left/right arrows.

    Args:
        include_left_right: If True, adds left/right navigation buttons

    Returns:
        List of InlineKeyboardButton objects for navigation row
    """
    base = [
        _nav_button("⬆️", "up"),
        _nav_button("⬇️", "down"),
        _nav_button("✅", "enter"),
        _nav_button("❌", "esc"),
        _nav_button("🔄", "refresh"),
    ]
    if include_left_right:
        # Insert left/right before enter button
        base.insert(2, _nav_button("⬅️", "left"))
        base.insert(3, _nav_button("➡️", "right"))
    return base


def build_interactive_keyboard(state: InteractiveUIState) -> InlineKeyboardMarkup:
    """Build inline keyboard based on UI type.

    Args:
        state: Detected interactive UI state

    Returns:
        InlineKeyboardMarkup with appropriate buttons
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    if state.ui_type in (UIType.PERMISSION, UIType.TOOL_PERMISSION):
        keyboard = _build_permission_keyboard(state)
    elif state.ui_type == UIType.MULTI_CHOICE:
        keyboard = _build_multi_choice_keyboard(state)
    elif state.ui_type in (UIType.PLAN_EXIT, UIType.CHECKPOINT, UIType.MODEL_SELECT):
        keyboard = _build_navigation_keyboard(state)
    else:
        # Fallback for unknown types
        keyboard.append([_nav_button("🔄", "refresh")])

    return InlineKeyboardMarkup(keyboard)


def _build_permission_keyboard(state: InteractiveUIState) -> list[list[InlineKeyboardButton]]:
    """Build keyboard for permission prompts.

    Simple Allow/Deny buttons + refresh.
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    row = []

    # Convert to set for O(1) lookups instead of repeated O(n) scans
    options_set = set(state.options)

    # Check for approval-style options
    if "Yes" in options_set or "Approve" in options_set:
        row.append(_nav_button("✅ Allow", "enter"))
    if "No" in options_set or "Deny" in options_set:
        row.append(_nav_button("❌ Deny", "esc"))

    if not row:
        # Fallback if standard options not found
        row.append(_nav_button("✅ Yes", "enter"))
        row.append(_nav_button("❌ No", "esc"))

    keyboard.append(row)
    keyboard.append([_nav_button("🔄", "refresh")])
    return keyboard


def _build_multi_choice_keyboard(state: InteractiveUIState) -> list[list[InlineKeyboardButton]]:
    """Build keyboard for multi-choice questions.

    Shows options with selection indicator + navigation.
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    # Add option buttons (with configured limit)
    max_options = min(len(state.options), MAX_MULTI_CHOICE_OPTIONS)
    for i in range(max_options):
        option = state.options[i]
        # Only slice if necessary (minor optimization)
        if len(option) > MAX_BUTTON_TEXT_LENGTH:
            option = option[:MAX_BUTTON_TEXT_LENGTH]
        marker = "→ " if i == state.current_selection else ""
        keyboard.append([
            InlineKeyboardButton(
                f"{marker}{option}",
                callback_data=f"{CALLBACK_PREFIX_UI}sel:{i}"
            )
        ])

    # Navigation row using shared helper
    keyboard.append(_build_nav_row(include_left_right=False))
    return keyboard


def _build_navigation_keyboard(state: InteractiveUIState) -> list[list[InlineKeyboardButton]]:
    """Build keyboard for plan mode, checkpoint, and model selection.

    Checkpoints are vertical-only (no left/right arrows).
    Other types get full navigation including left/right.
    """
    # Checkpoints are vertical only - no left/right arrows
    include_left_right = state.ui_type != UIType.CHECKPOINT
    return [_build_nav_row(include_left_right)]
