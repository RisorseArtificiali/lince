"""Inline keyboard callback handlers for session binding and UI interactions."""

from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.handlers.ui_callbacks import ui_button_callback
from telebridge.utils import CALLBACK_ACTION_NEW, CALLBACK_PREFIX_BIND

logger = logging.getLogger(__name__)


async def session_bind_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle session selection from inline keyboard."""
    app = get_app(context)

    query = update.callback_query
    if not query or not query.from_user or not app.is_user_allowed(query.from_user.id):
        if query:
            await query.answer("Not authorized", show_alert=True)
        return

    await query.answer()

    data = query.data
    if not data or not data.startswith(CALLBACK_PREFIX_BIND):
        return

    session_manager = app.session_manager

    _, pane_key = data.split(":", 1)

    if pane_key == CALLBACK_ACTION_NEW:
        # Create new session
        bridge = app.bridge
        new_pane = bridge.create_pane("claude", "claude")
        if new_pane:
            pane_key = new_pane
        else:
            if query.message:
                await query.edit_message_text("Failed to create new session.")
            return

    # Get thread ID - handle forum topics
    message = query.message
    thread_id = None
    if message:
        thread_id = getattr(message, "message_thread_id", None)

    if thread_id is None:
        if query.message:
            await query.edit_message_text("Could not determine topic.")
        return

    # Bind thread to pane
    session_manager.bind_thread(query.from_user.id, thread_id, pane_key)
    if query.message:
        await query.edit_message_text(
            f"✅ Bound to session: `{pane_key}`",
            parse_mode="Markdown"
        )


CALLBACK_HANDLERS = {
    "bind": session_bind_callback,
    "ui": ui_button_callback,
}
