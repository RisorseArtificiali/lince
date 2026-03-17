"""Telegram command handlers for telebridge."""

from telegram import InputFile, Update
from telegram.ext import ContextTypes

from telebridge.app import get_app
from telebridge.screenshot import capture_and_render_terminal


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    Shows welcome message with bot capabilities, documentation link,
    and list of available commands.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.message.reply_text("Unauthorized")
        return

    welcome_text = """🤖 *Welcome to Telebridge*

Interact with Claude Code directly from Telegram.

*Session Management:*
`/bind` - Connect this topic to a Claude Code session
`/unbind` - Disconnect topic from session
`/sessions` - List all active sessions
`/new` - Create a new Claude Code session

*Claude Code Commands:*
`/memory` - Show session context window
`/model` - Show/change Claude model
`/history` - View conversation history (paginated)
`/usage` - Show token and cost statistics
`/clear` - Clear conversation
`/compact` - Compact conversation
`/cost` - Show cost breakdown

*Other:*
`/screenshot` - Capture terminal screenshot
`/help` - Show detailed help
`/esc` - Send ESC key

*Getting Started:*
1. Use `/bind` to connect to a session
2. Start chatting with Claude Code
3. Use `/screenshot` to see what's happening

For more information, see the documentation.
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def screenshot_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /screenshot command.

    Captures the current terminal pane and sends it as a PNG photo to the user.

    Args:
        update: The Telegram update object
        context: The Telegram context object
    """
    app = get_app(context)
    # Check user permissions
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    try:
        # Capture the terminal pane
        png_bytes = await capture_and_render_terminal()

        if png_bytes:
            # Send the screenshot as a photo
            photo = InputFile(png_bytes, filename="screenshot.png")
            await update.effective_message.reply_photo(
                photo=photo,
                caption="Terminal screenshot captured"
            )
        else:
            # No data returned - likely a rendering issue
            await update.effective_message.reply_text(
                "Failed to capture screenshot: no image data received"
            )

    except RuntimeError as e:
        await update.effective_message.reply_text(f"Error: {e}")
    except Exception as e:
        import logging
        logging.exception("Failed to capture screenshot")
        await update.effective_message.reply_text(f"Failed: {e}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /history command.

    Displays paginated conversation history from the bound session.

    Usage: /history [N]
    - N: Number of messages to show (default: 10)

    Shows newest-first with inline keyboard navigation.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.effective_message.reply_text(
            "No session bound to this topic. Use /bind first."
        )
        return

    # Parse limit argument
    limit = 10
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 50)  # Cap at 50

    # Read transcript and display history
    try:
        from telebridge.transcript_parser import parse_entries
        from telebridge.config import get_state_dir
        import json

        state_dir = get_state_dir(app.config)

        # Find transcript file for session
        pane_state = session_manager.state.window_states.get(pane_key)
        session_id = pane_state.session_id if pane_state else None

        if not session_id:
            await update.effective_message.reply_text("No session ID found for this pane")
            return

        transcript_file = state_dir / f"{session_id}.jsonl"

        if not transcript_file.exists():
            await update.effective_message.reply_text("No transcript found for this session")
            return

        # Parse transcript
        entries = []
        with open(transcript_file) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    parsed, _ = parse_entries([entry])
                    entries.extend(parsed)

        if not entries:
            await update.effective_message.reply_text("No messages in transcript")
            return

        # Show last N entries
        entries = entries[-limit:]

        # Format and send
        history_text = "📜 *Recent Conversation*\n\n"
        for entry in reversed(entries):
            role = "👤 User" if entry.role == "user" else "🤖 Assistant"
            content = entry.text[:100] + "..." if len(entry.text) > 100 else entry.text
            history_text += f"{role}: {content}\n\n"

        # Split if too long
        if len(history_text) > 4000:
            history_text = history_text[:4000] + "\n... (truncated)"

        await update.effective_message.reply_text(history_text, parse_mode="Markdown")

    except Exception as e:
        import logging
        logging.exception("Failed to fetch history")
        await update.effective_message.reply_text(f"Failed to fetch history: {e}")


async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /usage command.

    Displays token and cost statistics from the session transcript.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.effective_message.reply_text(
            "No session bound to this topic. Use /bind first."
        )
        return

    try:
        from telebridge.config import get_state_dir
        import json

        state_dir = get_state_dir(app.config)

        pane_state = session_manager.state.window_states.get(pane_key)
        session_id = pane_state.session_id if pane_state else None

        if not session_id:
            await update.effective_message.reply_text("No session ID found for this pane")
            return

        transcript_file = state_dir / f"{session_id}.jsonl"

        if not transcript_file.exists():
            await update.effective_message.reply_text("No transcript found for this session")
            return

        # Extract usage data
        total_input_tokens = 0
        total_output_tokens = 0
        message_count = 0

        with open(transcript_file) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    message_count += 1

                    if entry.get("type") == "assistant":
                        # Extract usage metadata if available
                        usage = entry.get("usage", {})
                        total_input_tokens += usage.get("input_tokens", 1)
                        total_output_tokens += usage.get("output_tokens", 1)

        if total_input_tokens == 0 and total_output_tokens == 0:
            await update.effective_message.reply_text(
                "Usage data not available for this session.\n"
                "(Token usage tracking requires Claude Code with usage metadata)"
            )
            return

        total_tokens = total_input_tokens + total_output_tokens
        # Rough cost estimate: $3/MT input, $15/MT output (Claude 3.5 Sonnet)
        estimated_cost = (
            (total_input_tokens / 1_000_000 * 3.0) +
            (total_output_tokens / 1_000_000 * 15.0)
        )

        usage_text = f"""📊 *Session Usage*

*Messages:* {message_count}
*Input Tokens:* {total_input_tokens:,}
*Output Tokens:* {total_output_tokens:,}
*Total Tokens:* {total_tokens:,}

*Estimated Cost:* ${estimated_cost:.4f}

💡 Cost estimates based on Claude 3.5 Sonnet pricing.
"""

        await update.effective_message.reply_text(usage_text, parse_mode="Markdown")

    except Exception as e:
        import logging
        logging.exception("Failed to fetch usage")
        await update.effective_message.reply_text(f"Failed to fetch usage: {e}")


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /clear command.

    Forwards to Claude Code and clears pane session state.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.effective_message.reply_text(
            "No session bound to this topic. Use /bind first."
        )
        return

    try:
        # Forward command to Claude Code
        bridge.send_keys(pane_key, "/clear\r")

        # Clear pane session state and reset monitor offset
        session_manager.clear_pane_session(pane_key)

        await update.effective_message.reply_text("✅ Cleared conversation")
    except Exception as e:
        import logging
        logging.exception("Failed to clear")
        await update.effective_message.reply_text(f"Failed: {e}")


async def compact_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /compact command.

    Forwards to Claude Code to compact conversation.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.effective_message.reply_text(
            "No session bound to this topic. Use /bind first."
        )
        return

    try:
        bridge.send_keys(pane_key, "/compact\r")
        await update.effective_message.reply_text("🔄 Compacting conversation...")
    except Exception as e:
        import logging
        logging.exception("Failed to compact")
        await update.effective_message.reply_text(f"Failed: {e}")


async def cost_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /cost command.

    Forwards to Claude Code to show cost breakdown.
    """
    app = get_app(context)
    if not app.is_user_allowed(update.effective_user.id):
        await update.effective_message.reply_text("Permission denied")
        return

    bridge = app.bridge
    session_manager = app.session_manager

    thread_id = update.message.message_thread_id or 0
    pane_key = session_manager.resolve_pane_for_thread(update.effective_user.id, thread_id)

    if not pane_key:
        await update.effective_message.reply_text(
            "No session bound to this topic. Use /bind first."
        )
        return

    try:
        bridge.send_keys(pane_key, "/cost\r")
        await update.effective_message.reply_text("🔄 Fetching cost breakdown...")
    except Exception as e:
        import logging
        logging.exception("Failed to fetch cost")
        await update.effective_message.reply_text(f"Failed: {e}")
