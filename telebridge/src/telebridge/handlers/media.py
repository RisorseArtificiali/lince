"""Photo and media forwarding handlers for Telegram to Claude Code."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

from telebridge.app import get_app

logger = logging.getLogger(__name__)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages from Telegram and forward to Claude Code.

    Supports both single photos and albums. Each photo is processed individually
    for simplicity and reliability.
    """
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    message = update.message
    if not message or not message.photo:
        return

    # Get instances
    bridge = app.bridge
    session_manager = app.session_manager

    # Resolve session with liveness check
    thread_id = message.message_thread_id or 0
    session_info = await session_manager.resolve_session_for_thread_checked(
        update.effective_user.id, thread_id, bridge
    )

    if not session_info:
        await message.reply_text(
            "No active session. Use /bind to connect to a Claude Code session first."
        )
        return

    # Download and forward (session_info is guaranteed non-None here)
    assert session_info is not None  # Type guard for pyright
    pane_key = session_info.pane_key
    cwd = session_info.cwd

    # Check if part of an album
    is_album = bool(message.media_group_id)

    timestamp = int(time.time())
    album_suffix = f"_album_{message.media_group_id[-8:]}" if is_album else ""
    filename = f"telegram_photo{album_suffix}_{timestamp}.jpg"
    file_path = Path(cwd) / filename

    try:
        # Download highest resolution photo
        file = await message.photo[-1].get_file()
        await file.download_to_drive(str(file_path))

        # Forward caption first (if exists)
        if message.caption:
            bridge.send_keys(pane_key, message.caption)

        # Register with media registry for cleanup
        if app.media_registry:
            app.media_registry.register(
                str(file_path), session_info.session_id, "photo"
            )

        # Confirmation
        album_note = " (album)" if is_album else ""
        await message.reply_text(
            f"📷 *Image received{album_note}*\n\nFile: `{filename}`\nLocation: {cwd}",
            parse_mode="Markdown"
        )

    except RuntimeError as e:
        await message.reply_text(f"Error processing image: {e}")
    except Exception as e:
        logger.exception("Failed to process photo")
        await message.reply_text(f"Failed: {e}")


# Maximum file size (50MB - Telegram Premium limit)
MAX_FILE_SIZE = 50 * 1024 * 1024


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document messages from Telegram and forward to Claude Code."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    message = update.message
    if not message or not message.document:
        return

    # Get instances
    bridge = app.bridge
    session_manager = app.session_manager

    # Resolve session with liveness check
    thread_id = message.message_thread_id or 0
    session_info = await session_manager.resolve_session_for_thread_checked(
        update.effective_user.id, thread_id, bridge
    )

    if not session_info:
        await message.reply_text(
            "No active session. Use /bind to connect to a Claude Code session first."
        )
        return

    # Validate file size (session_info is guaranteed non-None here)
    assert session_info is not None  # Type guard for pyright
    document = message.document
    file_size = document.file_size or 0
    max_size = MAX_FILE_SIZE

    if file_size > max_size:
        size_mb = file_size / (1024 * 1024)
        await message.reply_text(
            f"❌ File too large\n\n"
            f"File size: {size_mb:.1f}MB\n"
            f"Maximum: {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )
        return

    # Download and forward
    pane_key = session_info.pane_key
    cwd = session_info.cwd

    # Preserve original filename with timestamp prefix for uniqueness
    timestamp = int(time.time())
    original_name = document.file_name or f"document_{timestamp}"
    filename = f"{timestamp}_{original_name}"
    file_path = Path(cwd) / filename

    try:
        # Download document
        file = await document.get_file()
        await file.download_to_drive(str(file_path))

        # Forward caption first (if exists)
        if message.caption:
            bridge.send_keys(pane_key, message.caption)

        # Send file path to Claude Code
        bridge.send_keys(pane_key, str(file_path))

        # Register with media registry for cleanup
        if app.media_registry:
            app.media_registry.register(
                str(file_path), session_info.session_id, "document"
            )

        # Confirmation
        size_kb = file_size / 1024
        await message.reply_text(
            f"📄 *Document received*\n\n"
            f"File: `{original_name}`\n"
            f"Size: {size_kb:.1f}KB\n"
            f"Location: {cwd}",
            parse_mode="Markdown"
        )

    except RuntimeError as e:
        await message.reply_text(f"Error processing document: {e}")
    except Exception as e:
        logger.exception("Failed to process document")
        await message.reply_text(f"Failed: {e}")


async def unsupported_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle unsupported media types (videos, audio, stickers, etc.)."""
    app = get_app(context)

    if not update.effective_user or not app.is_user_allowed(update.effective_user.id):
        return

    message = update.message
    if not message:
        return

    await message.reply_text(
        "❌ Unsupported media type\n\n"
        "Supported types:\n"
        "• Photos (📷)\n"
        "• Documents (📄)\n\n"
        "Videos, audio, and stickers are not supported."
    )
