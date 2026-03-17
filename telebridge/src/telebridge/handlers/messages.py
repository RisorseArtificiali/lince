"""Text message routing handler with liveness-aware session resolution."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.session_manager import SessionManager
from telebridge.utils import show_session_picker

if TYPE_CHECKING:
    from telebridge.multiplexer import MultiplexerBridge

logger = logging.getLogger(__name__)

# Claude commands that should be forwarded directly
CLAUDE_COMMANDS = {"/clear", "/compact", "/cost", "/doctor", "/init", "/logout", "/model", "/permissions", "/primes", "/resume", "/review", "/status", "/terminal-setup", "/usage"}


def _forward_claude_command(bridge, pane_key: str, command: str) -> None:
    """Forward a Claude command to the bridge."""
    bridge.send_keys(pane_key, command)


async def _handle_stale_session(
    update: Update,
    session_manager: "SessionManager",
    bridge: "MultiplexerBridge",
    user_id: int,
    thread_id: int,
) -> None:
    """Handle dead or missing session with recovery options.

    Args:
        update: Telegram update
        session_manager: Session manager instance
        bridge: Multiplexer bridge instance
        user_id: Telegram user ID
        thread_id: Telegram thread ID
    """
    # Check binding
    pane_key = session_manager.resolve_pane_for_thread(user_id, thread_id)

    if pane_key:
        # Binding exists but session is dead
        await update.message.reply_text(
            f"⚠️ Session for pane `{pane_key}` is no longer active.\n\n"
            f"Options:\n"
            f"• /bind - Reconnect to a different session\n"
            f"• /new - Create a new session\n"
            f"• /sessions - View all active sessions",
            parse_mode="Markdown",
        )
    else:
        # No binding exists
        await update.message.reply_text(
            "No session bound to this topic.\n\n"
            "Use /bind to connect to a Claude Code session.",
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route text messages to Claude Code with liveness-aware session resolution.

    Enhanced flow:
    1. Resolve session with liveness check
    2. If session dead: offer recovery options
    3. If session live: forward to pane
    """
    app = get_app(context)

    # Auth check
    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    message = update.message
    if not message:
        return

    # Auto-detect target chat ID from first inbound message
    chat_id = message.chat_id
    if app.get_target_chat_id() is None:
        app.set_target_chat_id(chat_id)

    text = message.text
    if not text:
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = message.message_thread_id or 0

    # Resolve session with liveness check
    session_info = await session_manager.resolve_session_for_thread_checked(
        update.effective_user.id, thread_id, bridge
    )

    if not session_info:
        # Session is dead or not bound - try auto-bind or show recovery
        pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

        if pane_key:
            # Binding exists but session is dead
            await _handle_stale_session(
                update, session_manager, bridge, update.effective_user.id, thread_id
            )
            return
        else:
            # No binding - try auto-bind or show picker
            config = app.config
            sessions = session_manager.list_active_sessions()

            # Get all bound panes for this user
            user_bindings = session_manager.state.thread_bindings.get(
                str(update.effective_user.id), {}
            )
            bound_panes = set(user_bindings.values())

            # Find unbound sessions
            unbound = [s for s in sessions if s.pane_key not in bound_panes]

            if len(unbound) == 1 and config.session.auto_bind:
                # Auto-bind single unbound session
                session_manager.bind_thread(update.effective_user.id, thread_id, unbound[0].pane_key)
                pane_key = unbound[0].pane_key
            elif unbound:
                # Show session picker
                await show_session_picker(update, unbound)
                return
            else:
                # No sessions available - prompt to create one
                await message.reply_text(
                    "No sessions available. Use /bind to select or create one."
                )
                return

    # Forward to bridge
    pane_key = session_info.pane_key
    try:
        # Handle Claude commands
        if text.startswith("/") and text in CLAUDE_COMMANDS:
            _forward_claude_command(bridge, pane_key, text)
        else:
            bridge.send_keys(pane_key, text)
        # Don't reply with "Sent" - outbound messages come via SessionMonitor
    except RuntimeError as e:
        await message.reply_text(f"Error: {e}")
    except Exception as e:
        logger.exception("Failed to send text")
        await message.reply_text(f"Failed: {e}")
