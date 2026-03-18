"""Session management commands: /bind, /unbind, /sessions, /esc."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.session_manager import SessionInfo
from telebridge.utils import CALLBACK_ACTION_NEW, CALLBACK_PREFIX_BIND

if TYPE_CHECKING:
    from telebridge.app import TelebridgeApp

logger = logging.getLogger(__name__)


async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show session picker to bind current topic."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    if not update.message:
        return

    bridge = app.bridge
    panes = bridge.list_panes()
    if not panes:
        await update.message.reply_text("No multiplexer panes found. Start tmux/zellij first.")
        return

    # Build inline keyboard from available panes
    keyboard = []
    for pane_key in panes:
        keyboard.append([
            InlineKeyboardButton(
                f"📋 {pane_key}",
                callback_data=f"{CALLBACK_PREFIX_BIND}{pane_key}"
            )
        ])
    keyboard.append([InlineKeyboardButton("➕ New Session", callback_data=f"{CALLBACK_PREFIX_BIND}{CALLBACK_ACTION_NEW}")])

    await update.message.reply_text(
        "Select a session to bind:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def unbind_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detach current topic from session."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    if not update.message:
        return

    session_manager = app.session_manager

    thread_id = update.message.message_thread_id
    if thread_id:
        session_manager.unbind_thread(update.effective_user.id, thread_id)
        await update.message.reply_text("Topic unbound. Use /bind to attach to a session.")


async def sessions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all active sessions with status."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    if not update.message:
        return

    session_manager = app.session_manager
    sessions = session_manager.list_active_sessions()
    if not sessions:
        await update.message.reply_text("No active sessions.")
        return

    lines = ["📋 **Active Sessions:**\n"]
    for s in sessions:
        lines.append(f"• `{s.pane_key}` - {s.summary[:40]} ({s.message_count} msgs)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def esc_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send Ctrl-C to current session."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    if not update.message:
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id
    pane_key = session_manager.resolve_pane_for_thread(
        update.effective_user.id, thread_id or 0
    )
    if not pane_key:
        await update.message.reply_text("No session bound to this topic.")
        return

    bridge.send_special_key("C-c")
    await update.message.reply_text("Sent Ctrl-C to session.")


async def show_session_picker_inline(update: Update, unbound: list[SessionInfo], app: "TelebridgeApp") -> None:
    """Show session picker when auto-bind not possible.

    Args:
        update: Telegram update
        unbound: List of unbound sessions to display
        app: TelebridgeApp instance (passed from caller)
    """
    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    if not update.message:
        return

    if not unbound:
        await update.message.reply_text("No sessions available. Use /start to create one.")
        return

    # Build inline keyboard
    keyboard = []
    for session in unbound:
        keyboard.append([
            InlineKeyboardButton(
                f"📋 {session.summary[:30]} ({session.message_count} msgs)",
                callback_data=f"{CALLBACK_PREFIX_BIND}{session.pane_key}"
            )
        ])
    keyboard.append([InlineKeyboardButton("➕ New Session", callback_data=f"{CALLBACK_PREFIX_BIND}{CALLBACK_ACTION_NEW}")])

    await update.message.reply_text(
        "Select a session to bind:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
