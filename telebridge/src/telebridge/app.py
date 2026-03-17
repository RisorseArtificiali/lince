"""TelebridgeApp - Encapsulates all application state and lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from telegram import Bot, BotCommand
from telegram.ext import (
    AIORateLimiter,
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from telebridge.config import TelebridgeConfig, get_state_dir
from telebridge.media_registry import MediaRegistry
from telebridge.message_queue import MessageQueue
from telebridge.multiplexer import MultiplexerBridge, create_bridge
from telebridge.session_manager import SessionManager
from telebridge.session_monitor import ParsedEntry, SessionMonitor

if TYPE_CHECKING:
    from telebridge.interactive_ui import InteractiveUIState

logger = logging.getLogger(__name__)


class TelebridgeApp:
    """Encapsulates all telebridge application state and lifecycle.

    This class consolidates all global state that was previously
    scattered across bot.py into a single cohesive unit, making the
    code more testable, maintainable, and easier to reason about.

    Usage:
        config = load_config(config_path)
        app = TelebridgeApp(config)
        await app.run()

    Or for testing:
        app = TelebridgeApp(config)
        app._bot = Bot(...)  # Mock the bot
        app._session_manager = SessionManager(...)  # Mock session manager
    """

    def __init__(self, config: TelebridgeConfig) -> None:
        self.config = config
        self._bot: Bot | None = None
        self._bridge: MultiplexerBridge | None = None
        self._session_manager: SessionManager | None = None
        self._message_queue: MessageQueue | None = None
        self._monitor: SessionMonitor | None = None
        self._media_registry: MediaRegistry | None = None
        self._target_chat_id: int | None = None

    @property
    def bridge(self) -> MultiplexerBridge:
        """Get the multiplexer bridge instance."""
        if self._bridge is None:
            raise RuntimeError("Bridge not initialized - call create_application() first")
        return self._bridge

    @property
    def session_manager(self) -> SessionManager:
        """Get the session manager instance."""
        if self._session_manager is None:
            raise RuntimeError("Session manager not initialized - call _post_init() first")
        return self._session_manager

    @property
    def message_queue(self) -> MessageQueue:
        """Get the message queue instance."""
        if self._message_queue is None:
            raise RuntimeError("Message queue not initialized - call _post_init() first")
        return self._message_queue

    @property
    def bot(self) -> Bot:
        """Get the bot instance."""
        if self._bot is None:
            raise RuntimeError("Bot not initialized - call _post_init() first")
        return self._bot

    @property
    def media_registry(self) -> MediaRegistry:
        """Get the media registry instance."""
        if self._media_registry is None:
            raise RuntimeError("Media registry not initialized - call _post_init() first")
        return self._media_registry

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if user is in the whitelist."""
        return user_id in self.config.telegram.allowed_users

    def get_target_chat_id(self) -> int | None:
        """Get the target chat ID for outbound messages."""
        return self._target_chat_id

    def set_target_chat_id(self, chat_id: int) -> None:
        """Set the target chat ID (called from first inbound message)."""
        self._target_chat_id = chat_id
        logger.info(f"Target chat ID set to: {chat_id}")

    async def create_application(self) -> Application:
        """Create and configure the Telegram Application."""
        # Create multiplexer bridge
        self._bridge = create_bridge(self.config)

        application = (
            Application.builder()
            .token(self.config.telegram.bot_token)
            .rate_limiter(AIORateLimiter(max_retries=5))
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )

        # Key: store app reference in bot_data for use handlers to access via context
        application.bot_data["app"] = self

        # Register handlers
        self._register_handlers(application)

        return application

    async def _post_init(self, application: Application) -> None:
        """Initialize background services after bot starts."""
        self._bot = application.bot

        await self._set_bot_commands(application)

        # Initialize target_chat_id from config if provided
        if self.config.telegram.target_chat_id:
            self.set_target_chat_id(self.config.telegram.target_chat_id)

        # Initialize media registry first (needed by session manager)
        state_dir = get_state_dir(self.config)
        self._media_registry = MediaRegistry(self.config.media, state_dir)
        self._media_registry.load()
        logger.info("Media registry initialized")

        # Initialize session manager with media registry reference
        self._session_manager = SessionManager(self.config, self._media_registry)
        self._session_manager.load()
        self._session_manager.update_from_session_map()

        # Cleanup stale panes
        if self._bridge:
            await self._session_manager.cleanup_stale_panes(self._bridge)

        logger.info("Session manager initialized")

        # Initialize message queue
        self._message_queue = MessageQueue(self.config)
        if self._bot:
            self._message_queue.set_bot(self._bot)
        logger.info("Message queue initialized")

        # Start session monitor for outbound messages
        self._monitor = SessionMonitor(self.config)
        self._monitor.set_message_callback(self._outbound_callback)
        self._monitor.set_ui_callback(self._ui_callback)
        if self._media_registry:
            self._monitor.set_media_registry(self._media_registry)
        self._monitor.start()
        logger.info("Session monitor started")

        logger.info("Telebridge bot initialized")

    async def _post_shutdown(self, application: Application) -> None:
        """Cleanup on shutdown."""
        logger.info("Telebridge bot shutting down")

        # Stop session monitor
        if self._monitor:
            self._monitor.stop()
            self._monitor = None

        # Shutdown message queue
        if self._message_queue:
            await self._message_queue.shutdown()
            self._message_queue = None

        # Save session manager state before shutdown
        if self._session_manager:
            self._session_manager.save()
            self._session_manager = None

        # Clear state
        self._bot = None
        self._bridge = None

    async def run(self) -> None:
        """Main entry point to run the bot."""
        if not self.config.telegram.bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not configured")
            return

        if not self.config.telegram.allowed_users:
            logger.warning("No allowed users configured - bot will reject all messages")

        application = await self.create_application()
        await application.run_polling()

    def _register_handlers(self, application: Application) -> None:
        """Register all handlers in priority order."""
        from telebridge.handlers.callbacks import CALLBACK_HANDLERS
        from telebridge.handlers.claude_commands import (
            help_command,
            memory_command,
            model_command,
            new_command,
        )
        from telebridge.handlers.commands import (
            clear_command,
            compact_command,
            cost_command,
            history_command,
            screenshot_command,
            start_command,
            usage_command,
        )
        from telebridge.handlers.media import (
            document_handler,
            photo_handler,
            unsupported_media_handler,
        )
        from telebridge.handlers.messages import text_handler
        from telebridge.handlers.session_commands import (
            bind_command,
            esc_command,
            sessions_command,
            unbind_command,
        )
        from telebridge.utils import CALLBACK_PREFIX_BIND, CALLBACK_PREFIX_UI

        # 1. Command handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("screenshot", screenshot_command))
        application.add_handler(CommandHandler("history", history_command))
        application.add_handler(CommandHandler("usage", usage_command))
        application.add_handler(CommandHandler("clear", clear_command))
        application.add_handler(CommandHandler("compact", compact_command))
        application.add_handler(CommandHandler("cost", cost_command))
        application.add_handler(CommandHandler("bind", bind_command))
        application.add_handler(CommandHandler("unbind", unbind_command))
        application.add_handler(CommandHandler("sessions", sessions_command))
        application.add_handler(CommandHandler("esc", esc_command))
        application.add_handler(CommandHandler("memory", memory_command))
        application.add_handler(CommandHandler("model", model_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("new", new_command))

        # 2. Callback handler for session binding
        application.add_handler(
            CallbackQueryHandler(
                pattern=f"^{CALLBACK_PREFIX_BIND}",
                callback=CALLBACK_HANDLERS["bind"],
            )
        )

        # 2.5. Callback handler for interactive UI keyboards
        application.add_handler(
            CallbackQueryHandler(
                pattern=f"^{CALLBACK_PREFIX_UI}",
                callback=CALLBACK_HANDLERS["ui"],
            )
        )

        # 3. Photo handler (before text to avoid conflicts)
        application.add_handler(
            MessageHandler(filters=filters.PHOTO, callback=photo_handler)
        )

        # 3.5. Document handler (after photo, before unsupported media)
        application.add_handler(
            MessageHandler(filters=filters.Document.ALL, callback=document_handler)
        )

        # 4. Unsupported media handler
        # Filter for unsupported media types (videos, audio, stickers, animations)
        # Note: Documents are handled by document_handler
        unsupported_media_filter = (
            filters.VIDEO
            | filters.AUDIO
            | filters.VOICE
            | filters.Sticker.ALL
            | filters.ANIMATION
        )
        application.add_handler(
            MessageHandler(
                filters=unsupported_media_filter,
                callback=unsupported_media_handler,
            )
        )

        # 5. Text message handler (non-command text -> Claude Code)
        application.add_handler(
            MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=text_handler)
        )

    async def _set_bot_commands(self, application: Application) -> None:
        """Set up the bot command menu."""
        commands = [
            BotCommand("start", "Start telebridge session"),
            BotCommand("screenshot", "Capture terminal screenshot"),
            BotCommand("history", "View conversation history"),
            BotCommand("usage", "Show token and cost statistics"),
            BotCommand("bind", "Bind topic to Claude Code session"),
            BotCommand("unbind", "Unbind topic from session"),
            BotCommand("sessions", "List active sessions"),
            BotCommand("new", "Create new Claude Code session"),
            BotCommand("memory", "Show session context window"),
            BotCommand("model", "Show/change Claude model"),
            BotCommand("clear", "Clear conversation"),
            BotCommand("compact", "Compact conversation"),
            BotCommand("cost", "Show cost breakdown"),
            BotCommand("help", "Show help information"),
            BotCommand("esc", "Send ESC key"),
        ]
        await application.bot.set_my_commands(commands)

    async def _outbound_callback(self, entries: list[ParsedEntry]) -> None:
        """Handle parsed entries from SessionMonitor and send to Telegram.

        New pipeline: entries -> convert_to_tasks -> enqueue -> worker loop -> send
        """
        if not entries:
            return

        # Check we have message queue and target chat
        if self._message_queue is None:
            logger.warning("Message queue not initialized - skipping outbound message")
            return

        chat_id = self.get_target_chat_id()
        if chat_id is None:
            logger.warning("No target chat ID - skipping outbound message")
            return

        try:
            # Convert entries to tasks and enqueue
            tasks = self._convert_entries_to_tasks(entries, chat_id)
            for task in tasks:
                await self._message_queue.enqueue(task, chat_id)

        except Exception as e:
            logger.exception(f"Failed to enqueue outbound message: {e}")

    def _convert_entries_to_tasks(
        self, entries: list[ParsedEntry], chat_id: int
    ) -> list["MessageTask"]:
        """Convert ParsedEntry to MessageTask for queue processing.

        First formats entries using response_formatter.format_entries,
        then converts to Telegram markdown and MessageTask objects.

        Args:
            entries: List of ParsedEntry from transcript parser
            chat_id: Telegram chat ID for target user

        Returns:
            List of MessageTask objects ready for enqueueing
        """
        from telebridge.message_queue import TASK_TYPE_CONTENT, TASK_TYPE_STATUS_UPDATE, MessageTask
        from telebridge.response_formatter import format_entries, split_message, to_telegram_markdown

        # Format entries to markdown text
        text = format_entries(entries)
        if not text:
            return []

        # Convert to Telegram MarkdownV2
        md_text = to_telegram_markdown(text)

        # Split into chunks if needed
        chunks = split_message(md_text)

        # Resolve pane_key and thread_id from session_id
        session_id = entries[0].session_id if entries else ""
        resolved = self.session_manager.resolve_thread_for_session(session_id)
        pane_key, thread_id = resolved if resolved else ("", None)

        tasks = []
        for chunk in chunks:
            # Determine task type from first entry
            task_type = TASK_TYPE_STATUS_UPDATE if entries[0].content_type == "thinking" else TASK_TYPE_CONTENT

            # Extract image data if present (from any entry)
            image_data = b""
            for entry in entries:
                if entry.image_data:
                    _, raw_bytes = entry.image_data[0]
                    image_data = raw_bytes
                    break

            task = MessageTask(
                task_type=task_type,
                text=chunk,
                pane_key=pane_key,
                content_type=entries[0].content_type,
                thread_id=thread_id,
                image_data=image_data,
            )
            tasks.append(task)

        return tasks

    async def _ui_callback(self, ui_state: "InteractiveUIState") -> None:
        """Handle detected interactive UI and send as inline keyboard.

        Args:
            ui_state: Detected interactive UI state from session monitor
        """
        from telebridge.interactive_ui import InteractiveUIState
        from telebridge.ui_keyboard import build_interactive_keyboard
        from telebridge.ui_message_tracker import get_ui_tracker

        if self._bot is None:
            logger.warning("Bot not initialized - skipping UI message")
            return

        chat_id = self.get_target_chat_id()
        if chat_id is None:
            logger.warning("No target chat ID - skipping UI message")
            return

        try:
            # Build inline keyboard
            keyboard = build_interactive_keyboard(ui_state)

            # Format message content
            from telebridge.utils import MAX_UI_CONTENT_LENGTH

            content = ui_state.content[:MAX_UI_CONTENT_LENGTH]  # Truncate for Telegram
            message_text = f"🤖 **Interactive Prompt**\n\n{content}"

            # Check if we have an existing message to edit
            tracker = get_ui_tracker()
            existing_msg_id = await tracker.get_message(chat_id, 0)  # thread_id=0 for main chat

            if existing_msg_id:
                # Edit existing message
                try:
                    await self._bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=existing_msg_id,
                        text=message_text,
                        reply_markup=keyboard,
                        parse_mode="Markdown",
                    )
                    logger.debug(f"Updated UI message {existing_msg_id}")
                except Exception as e:
                    logger.warning(f"Failed to edit UI message: {e}, sending new")
                    existing_msg_id = None

            if not existing_msg_id:
                # Send new message
                msg = await self._bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                # Track message for future edits
                await tracker.set_message(chat_id, 0, msg.message_id)
                logger.debug(f"Sent new UI message {msg.message_id}")

        except Exception as e:
            logger.exception(f"Failed to send UI message: {e}")


def get_app(context: ContextTypes.DEFAULT_TYPE) -> TelebridgeApp:
    """Get TelebridgeApp from Telegram context."""
    return context.application.bot_data["app"]
