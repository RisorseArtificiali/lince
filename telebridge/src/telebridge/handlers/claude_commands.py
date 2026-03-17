"""Claude Code-specific commands for session management."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.config import get_state_dir
from telebridge.utils import generate_short_uuid, poll_with_timeout

if TYPE_CHECKING:
    from telebridge.session_manager import SessionManager

logger = logging.getLogger(__name__)


async def memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show session context window from Claude Code.

    Usage: /memory
    Displays the current context window, including recent messages
    and token usage. Useful for understanding what Claude sees.
    """
    if not update.effective_message or not update.effective_user:
        return

    app = get_app(context)
    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.message.reply_text("No session bound to this topic. Use /bind first.")
        return

    # Send Ctrl+Shift+C to Claude Code to capture context
    # (This is a placeholder - actual implementation depends on Claude Code's context capture mechanism)
    try:
        bridge.send_keys(pane_key, "\x1b\x43")  # Alt+C or similar shortcut
        await update.message.reply_text("🔄 Capturing context window...")
        # The actual context will be sent via the outbound pipeline
    except Exception as e:
        logger.error(f"Failed to capture context: {e}")
        await update.message.reply_text(f"Failed to capture context: {e}")


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show or change current Claude model.

    Usage: /model [model_name]
    - No args: Show current model
    - With arg: Switch to specified model

    Examples:
        /model              # Show current model
        /model claude-3-5-sonnet  # Switch to Sonnet
        /model claude-3-7   # Switch to Claude 3.7
    """
    if not update.effective_message or not update.effective_user:
        return

    app = get_app(context)
    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.message.reply_text("No session bound to this topic. Use /bind first.")
        return

    # Parse arguments
    args = context.args if context.args else []

    if args:
        # Change model
        model_name = args[0]
        try:
            # Send /model command to Claude Code
            bridge.send_keys(pane_key, f"/model {model_name}\r")
            await update.message.reply_text(f"🔄 Switching model to `{model_name}`...", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to switch model: {e}")
            await update.message.reply_text(f"Failed to switch model: {e}")
    else:
        # Show current model
        try:
            bridge.send_keys(pane_key, "/model\r")
            await update.message.reply_text("🔄 Querying current model...")
            # Response will come via outbound pipeline
        except Exception as e:
            logger.error(f"Failed to query model: {e}")
            await update.message.reply_text(f"Failed to query model: {e}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show Telebridge help information.

    Displays:
    - Available commands
    - Session management basics
    - Keyboard shortcuts (if any)
    """
    help_text = """*Telebridge Help*

*Session Management:*
/bind - Bind current topic to a Claude Code session
/unbind - Unbind topic from session
/sessions - List all active sessions

*Claude Code Commands:*
/memory - Show session context window
/model - Show/change Claude model
/new - Create a new Claude Code session

*Other:*
/screenshot - Capture terminal screenshot
/start - Start telebridge session
/esc - Send ESC key to Claude Code
"""
    if update.effective_message:
        await update.effective_message.reply_text(help_text, parse_mode="Markdown")


async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create a new Claude Code session.

    Flow:
    1. Generate unique hook callback file
    2. Send "Claude Code: New session" to bound pane
    3. Poll session_map.json for new session_id
    4. Bind new session to current thread
    5. Update topic name to session summary

    Usage: /new
    """
    if not update.effective_user or not update.effective_chat or not update.effective_message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id

    # Get current binding
    app = get_app(context)
    config = app.config
    session_manager = app.session_manager
    bridge = app.bridge

    pane_key = session_manager.resolve_pane_for_thread(user_id, thread_id or 0)
    if not pane_key:
        await update.message.reply_text(
            "No active session. Use /bind to connect to a session first."
        )
        return

    # Check if pane is live
    try:
        if not await session_manager.is_pane_live(pane_key, bridge):
            await update.message.reply_text(
                f"Pane `{pane_key}` is no longer active. Use /bind to reconnect.",
                parse_mode="Markdown",
            )
            return
    except Exception as e:
        logger.error(f"Failed to check pane liveness: {e}")
        await update.message.reply_text(f"Failed to check pane status: {e}")
        return

    # Generate hook callback file
    callback_id = _generate_callback_id()
    callback_file = get_state_dir(config) / f"new_session_{callback_id}.json"

    callback_data = {
        "trigger": "new_session",
        "thread_id": thread_id,
        "user_id": user_id,
        "chat_id": chat_id,
        "pane_key": pane_key,
    }

    try:
        with open(callback_file, "w") as f:
            json.dump(callback_data, f)
    except (OSError, TypeError) as e:
        logger.error(f"Failed to create callback file: {e}")
        await update.message.reply_text(f"Failed to initialize session creation: {e}")
        return

    # Send "Claude Code: New session" command to pane
    try:
        bridge.send_keys(pane_key, "Claude Code: New session\r")
    except Exception as e:
        logger.error(f"Failed to send new session command: {e}")
        await update.message.reply_text(f"Failed to create session: {e}")
        callback_file.unlink(missing_ok=True)
        return

    # Send status message
    status_msg = await update.message.reply_text(
        "🔄 Creating new session... This may take a few seconds."
    )

    # Poll for session_map.json update
    try:
        new_session_id = await _poll_for_new_session(
            session_manager, pane_key, timeout=15.0
        )

        if new_session_id:
            # Bind new session to thread (update existing binding)
            session_manager.bind_thread(user_id, thread_id or 0, pane_key)

            # Update topic name
            await _sync_topic_name(update, new_session_id, session_manager)

            await status_msg.edit_text(
                f"✅ New session created: `{new_session_id[:16]}...`",
                parse_mode="Markdown",
            )
        else:
            await status_msg.edit_text(
                "⚠️ Timed out waiting for new session. "
                "Check if Claude Code is running and try again."
            )

    except asyncio.TimeoutError:
        await status_msg.edit_text(
            "⚠️ Timed out waiting for new session. "
            "Check if Claude Code is running and try again."
        )
    except Exception as e:
        logger.exception("Failed to create new session")
        await status_msg.edit_text(f"Failed to create session: {e}")
    finally:
        # Cleanup callback file
        callback_file.unlink(missing_ok=True)


def _generate_callback_id() -> str:
    """Generate unique callback ID."""
    return generate_short_uuid()


async def _poll_for_new_session(
    session_manager: "SessionManager", pane_key: str, timeout: float = 15.0
) -> str | None:
    """Poll session_map.json for new session_id from pane.

    Args:
        session_manager: Session manager instance
        pane_key: Pane key to watch
        timeout: Maximum seconds to wait

    Returns:
        New session_id if found, None if timeout
    """
    pane_state = session_manager.state.window_states.get(pane_key)
    known_session_id = pane_state.session_id if pane_state else ""

    def check_new_session() -> bool:
        session_manager.update_from_session_map()
        current_state = session_manager.state.window_states.get(pane_key)
        return current_state and current_state.session_id != known_session_id

    if await poll_with_timeout(check_new_session, timeout=timeout):
        current_state = session_manager.state.window_states.get(pane_key)
        return current_state.session_id if current_state else None
    return None


async def _sync_topic_name(update: Update, session_id: str, session_manager: "SessionManager") -> None:
    """Update Telegram topic name to session summary.

    Args:
        update: Telegram update
        session_id: New session ID
        session_manager: Session manager instance
    """
    if not session_manager or not update.effective_chat:
        return

    # Find session info
    for session_info in session_manager.list_active_sessions():
        if session_info.session_id == session_id:
            # Update topic name
            topic_name = session_info.summary or "Untitled"
            thread_id = update.message.message_thread_id

            if thread_id:
                try:
                    await update.effective_chat.edit_forum_topic(
                        message_thread_id=thread_id,
                        name=topic_name[:50],  # Telegram limit
                    )
                    logger.info(f"Updated topic {thread_id} name to: {topic_name}")
                except Exception as e:
                    logger.warning(f"Failed to update topic name: {e}")

            break
