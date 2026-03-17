"""Callback handlers for interactive UI inline keyboards."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest, ChatMigrated
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.utils import (
    CALLBACK_PREFIX_UI,
    UI_KEY_MAP,
)

logger = logging.getLogger(__name__)


async def ui_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle interactive UI button presses.

    Callback data format: "iui:action" or "iui:sel:N"

    Actions:
        - up/down/left/right: Navigate options
        - enter: Select current option
        - esc: Cancel/dismiss
        - refresh: Re-capture pane and update message
        - sel:N: Direct selection of option N
    """
    app = get_app(context)

    query = update.callback_query
    if not query or not query.from_user or not app.is_user_allowed(query.from_user.id):
        if query:
            await query.answer("Not authorized", show_alert=True)
        return

    await query.answer()

    data = query.data
    if not data or not data.startswith(CALLBACK_PREFIX_UI):
        return

    # Parse action: "iui:up" or "iui:sel:0"
    action_part = data[len(CALLBACK_PREFIX_UI) :]

    bridge = app.bridge
    session_manager = app.session_manager

    # Resolve pane_key from user's session binding
    # Use thread_id from the callback message if available
    thread_id = 0
    if query.message and hasattr(query.message, "message_thread_id") and query.message.message_thread_id:
        thread_id = query.message.message_thread_id

    pane_key = session_manager.resolve_pane_for_thread(query.from_user.id, thread_id)
    if not pane_key:
        logger.warning(f"No pane bound for user {query.from_user.id} thread {thread_id}")
        if query.message:
            await query.edit_message_text("⚠️ Session no longer bound. Use /bind to reconnect.")
        return

    # Handle direct selection (sel:0, sel:1, etc.)
    if action_part.startswith("sel:"):
        try:
            index = int(action_part.split(":")[1])
            # Validate index bounds (1-100 to prevent abuse)
            if index < 0 or index > 99:
                logger.warning(f"Invalid selection index (out of range): {action_part}")
                if query.message:
                    await query.answer("Invalid selection", show_alert=True)
                return
            # Send the number directly (1-indexed for Claude Code)
            bridge.send_keys(pane_key, str(index + 1))
            bridge.send_keys(pane_key, UI_KEY_MAP["enter"])
        except (ValueError, IndexError) as e:
            logger.warning(f"Invalid selection callback: {action_part} - {e}")
            return
    elif action_part == "refresh":
        # Refresh handled by re-capturing pane - just acknowledge
        if query.message:
            await query.edit_message_text("Refreshing...")
        return
    elif action_part in UI_KEY_MAP:
        # Standard navigation action
        bridge.send_keys(pane_key, UI_KEY_MAP[action_part])

    # Edit message to show response
    if query.message:
        try:
            await query.edit_message_text(
                f"✓ Sent: {action_part}",
                reply_markup=None
            )
        except (BadRequest, ChatMigrated) as e:
            # Message was deleted or chat migrated - expected
            logger.debug(f"Message not editable (deleted?): {e}")
        except Exception as e:
            # Unexpected error - log at warning level
            logger.warning(f"Unexpected error editing message: {e}")
