"""Tests for media handlers (photo_handler, document_handler, unsupported_media_handler)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telebridge.config import TelebridgeConfig, TelegramConfig, SessionConfig
from telebridge.session_manager import SessionInfo


@pytest.fixture
def sample_config() -> TelebridgeConfig:
    """Create a sample config for testing."""
    return TelebridgeConfig(
        telegram=TelegramConfig(
            bot_token="test_token_123",
            allowed_users={123456789},
            target_chat_id=None,
        ),
        session=SessionConfig(
            auto_bind=True,
        ),
    )


@pytest.fixture
def mock_app(sample_config: TelebridgeConfig) -> MagicMock:
    """Create a mock TelebridgeApp."""
    app = MagicMock()
    app.config = sample_config
    app.is_user_allowed = MagicMock(return_value=True)
    app.bridge = MagicMock()
    app.bridge.send_keys = MagicMock()
    app.session_manager = MagicMock()
    app.media_registry = MagicMock()
    return app


@pytest.fixture
def mock_session_info() -> SessionInfo:
    """Create a mock SessionInfo."""
    return SessionInfo(
        session_id="test-session-123",
        pane_key="test:0",
        cwd="/tmp/test",
        summary="Test Session",
        message_count=5,
        file_path="/tmp/test-session.jsonl",
    )


@pytest.fixture
def mock_update() -> MagicMock:
    """Create a mock Update object for photo messages."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.message = MagicMock()
    update.message.message_thread_id = None
    update.message.media_group_id = None  # Not part of an album
    update.message.photo = [MagicMock(file_id="small"), MagicMock(file_id="large")]
    update.message.caption = None
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock context."""
    context = MagicMock()
    return context


class TestPhotoHandler:
    """Tests for photo_handler."""

    @pytest.mark.asyncio
    async def test_unauthorized_user_returns_early(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that unauthorized users are rejected."""
        mock_app.is_user_allowed.return_value = False

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import photo_handler
            await photo_handler(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_photo_returns_early(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that messages without photos return early."""
        mock_update.message.photo = None

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import photo_handler
            await photo_handler(mock_update, mock_context)

        mock_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_session_shows_bind_prompt(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that missing session shows bind prompt."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(return_value=None)

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import photo_handler
            await photo_handler(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "No active session" in call_args[0][0]
        assert "/bind" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_valid_photo_downloads_and_confirms(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that valid photo is downloaded and confirmation is sent."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )

        # Mock photo download
        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()

        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=mock_file)
        mock_update.message.photo[-1].get_file = mock_photo.get_file

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            with patch("telebridge.handlers.media.Path") as mock_path_class:
                mock_path = MagicMock()
                mock_path_class.return_value = mock_path

                from telebridge.handlers.media import photo_handler
                await photo_handler(mock_update, mock_context)

        # Verify confirmation message sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Image received" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_photo_with_caption_forwards_caption(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that photo caption is forwarded to bridge."""
        mock_update.message.caption = "Test caption"
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()

        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=mock_file)
        mock_update.message.photo[-1].get_file = mock_photo.get_file

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            with patch("telebridge.handlers.media.Path") as mock_path_class:
                mock_path = MagicMock()
                mock_path_class.return_value = mock_path

                from telebridge.handlers.media import photo_handler
                await photo_handler(mock_update, mock_context)

        # Verify caption was forwarded
        mock_app.bridge.send_keys.assert_called()
        call_args = mock_app.bridge.send_keys.call_args
        assert mock_session_info.pane_key in call_args[0]
        assert "Test caption" in call_args[0]

    @pytest.mark.asyncio
    async def test_download_error_shows_error_message(
        self, mock_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that download errors are reported to user."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock(side_effect=RuntimeError("Download failed"))

        mock_photo = MagicMock()
        mock_photo.get_file = AsyncMock(return_value=mock_file)
        mock_update.message.photo[-1].get_file = mock_photo.get_file

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            with patch("telebridge.handlers.media.Path") as mock_path_class:
                mock_path = MagicMock()
                mock_path_class.return_value = mock_path

                from telebridge.handlers.media import photo_handler
                await photo_handler(mock_update, mock_context)

        mock_update.message.reply_text.assert_called()
        call_args = mock_update.message.reply_text.call_args
        assert "Error" in call_args[0][0] or "Failed" in call_args[0][0]


class TestDocumentHandler:
    """Tests for document_handler."""

    @pytest.fixture
    def mock_document_update(self) -> MagicMock:
        """Create a mock Update object for document messages."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123456789
        update.message = MagicMock()
        update.message.message_thread_id = None
        update.message.document = MagicMock()
        update.message.document.file_id = "doc_123"
        update.message.document.file_name = "test.txt"
        update.message.document.file_size = 1024  # 1KB
        update.message.caption = None
        update.message.reply_text = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_unauthorized_user_returns_early(
        self, mock_document_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that unauthorized users are rejected for documents."""
        mock_app.is_user_allowed.return_value = False

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import document_handler
            await document_handler(mock_document_update, mock_context)

        mock_document_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_too_large_rejected(
        self, mock_document_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that files over 50MB are rejected."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )
        mock_document_update.message.document.file_size = 60 * 1024 * 1024  # 60MB

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import document_handler
            await document_handler(mock_document_update, mock_context)

        mock_document_update.message.reply_text.assert_called_once()
        call_args = mock_document_update.message.reply_text.call_args
        assert "too large" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_valid_document_downloads_and_confirms(
        self, mock_document_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that valid document is downloaded and confirmation is sent."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()

        mock_document_update.message.document.get_file = AsyncMock(return_value=mock_file)

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            with patch("telebridge.handlers.media.Path") as mock_path_class:
                mock_path = MagicMock()
                mock_path_class.return_value = mock_path

                from telebridge.handlers.media import document_handler
                await document_handler(mock_document_update, mock_context)

        mock_document_update.message.reply_text.assert_called_once()
        call_args = mock_document_update.message.reply_text.call_args
        assert "Document received" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_document_forwards_file_path(
        self, mock_document_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock,
        mock_session_info: SessionInfo
    ) -> None:
        """Test that document file path is sent to bridge."""
        mock_app.session_manager.resolve_session_for_thread_checked = AsyncMock(
            return_value=mock_session_info
        )

        mock_file = AsyncMock()
        mock_file.download_to_drive = AsyncMock()

        mock_document_update.message.document.get_file = AsyncMock(return_value=mock_file)

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            with patch("telebridge.handlers.media.Path") as mock_path_class:
                mock_path = MagicMock()
                mock_path.__str__ = lambda self: "/tmp/test/test.txt"
                mock_path_class.return_value = mock_path

                from telebridge.handlers.media import document_handler
                await document_handler(mock_document_update, mock_context)

        # Verify file path was sent to bridge
        calls = mock_app.bridge.send_keys.call_args_list
        # Should have at least one call with file path
        assert len(calls) >= 1


class TestUnsupportedMediaHandler:
    """Tests for unsupported_media_handler."""

    @pytest.fixture
    def mock_video_update(self) -> MagicMock:
        """Create a mock Update object for video messages."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123456789
        update.message = MagicMock()
        update.message.video = MagicMock()
        update.message.reply_text = AsyncMock()
        return update

    @pytest.fixture
    def mock_audio_update(self) -> MagicMock:
        """Create a mock Update object for audio messages."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123456789
        update.message = MagicMock()
        update.message.audio = MagicMock()
        update.message.reply_text = AsyncMock()
        return update

    @pytest.mark.asyncio
    async def test_unauthorized_user_returns_early(
        self, mock_video_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that unauthorized users are rejected."""
        mock_app.is_user_allowed.return_value = False

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import unsupported_media_handler
            await unsupported_media_handler(mock_video_update, mock_context)

        mock_video_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_video_shows_unsupported_message(
        self, mock_video_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that video shows unsupported media message."""
        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import unsupported_media_handler
            await unsupported_media_handler(mock_video_update, mock_context)

        mock_video_update.message.reply_text.assert_called_once()
        call_args = mock_video_update.message.reply_text.call_args
        assert "Unsupported media type" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_audio_shows_unsupported_message(
        self, mock_audio_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that audio shows unsupported media message."""
        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import unsupported_media_handler
            await unsupported_media_handler(mock_audio_update, mock_context)

        mock_audio_update.message.reply_text.assert_called_once()
        call_args = mock_audio_update.message.reply_text.call_args
        assert "Unsupported media type" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_message_lists_supported_types(
        self, mock_video_update: MagicMock, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that error message lists supported types."""
        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import unsupported_media_handler
            await unsupported_media_handler(mock_video_update, mock_context)

        call_args = mock_video_update.message.reply_text.call_args
        message = call_args[0][0]
        assert "Photos" in message
        assert "Documents" in message
        assert "Videos" in message and "not supported" in message.lower()

    @pytest.mark.asyncio
    async def test_no_message_returns_early(
        self, mock_context: MagicMock, mock_app: MagicMock
    ) -> None:
        """Test that missing message returns early."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 123456789
        update.message = None

        with patch("telebridge.handlers.media.get_app", return_value=mock_app):
            from telebridge.handlers.media import unsupported_media_handler
            await unsupported_media_handler(update, mock_context)

        # Should not raise and should not call reply_text
