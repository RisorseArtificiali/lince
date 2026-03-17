"""Tests for TelebridgeApp class."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telebridge.app import TelebridgeApp, get_app
from telebridge.config import TelebridgeConfig, TelegramConfig, SessionConfig


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


class TestTelebridgeApp:
    """Tests for TelebridgeApp class."""

    def test_init(self, sample_config: TelebridgeConfig) -> None:
        """Test TelebridgeApp initialization."""
        app = TelebridgeApp(sample_config)

        assert app.config is sample_config
        assert app._bot is None
        assert app._bridge is None
        assert app._session_manager is None
        assert app._message_queue is None
        assert app._monitor is None
        assert app._target_chat_id is None

    def test_is_user_allowed(self, sample_config: TelebridgeConfig) -> None:
        """Test user whitelist checking."""
        app = TelebridgeApp(sample_config)

        assert app.is_user_allowed(123456789) is True
        assert app.is_user_allowed(999999999) is False

    def test_get_target_chat_id(self, sample_config: TelebridgeConfig) -> None:
        """Test target chat ID getter."""
        app = TelebridgeApp(sample_config)

        assert app.get_target_chat_id() is None

        app.set_target_chat_id(987654321)
        assert app.get_target_chat_id() == 987654321

    def test_set_target_chat_id(self, sample_config: TelebridgeConfig) -> None:
        """Test target chat ID setter."""
        app = TelebridgeApp(sample_config)

        app.set_target_chat_id(111222333)
        assert app._target_chat_id == 111222333

    def test_bridge_property_raises_before_init(self, sample_config: TelebridgeConfig) -> None:
        """Test bridge property raises RuntimeError before initialization."""
        app = TelebridgeApp(sample_config)

        with pytest.raises(RuntimeError, match="Bridge not initialized"):
            _ = app.bridge

    def test_session_manager_property_raises_before_init(self, sample_config: TelebridgeConfig) -> None:
        """Test session_manager property raises RuntimeError before initialization."""
        app = TelebridgeApp(sample_config)

        with pytest.raises(RuntimeError, match="Session manager not initialized"):
            _ = app.session_manager

    def test_message_queue_property_raises_before_init(self, sample_config: TelebridgeConfig) -> None:
        """Test message_queue property raises RuntimeError before initialization."""
        app = TelebridgeApp(sample_config)

        with pytest.raises(RuntimeError, match="Message queue not initialized"):
            _ = app.message_queue

    def test_bot_property_raises_before_init(self, sample_config: TelebridgeConfig) -> None:
        """Test bot property raises RuntimeError before initialization."""
        app = TelebridgeApp(sample_config)

        with pytest.raises(RuntimeError, match="Bot not initialized"):
            _ = app.bot

    @pytest.mark.asyncio
    async def test_create_application(self, sample_config: TelebridgeConfig) -> None:
        """Test create_application creates Telegram Application with bot_data."""
        app = TelebridgeApp(sample_config)

        with patch("telebridge.app.create_bridge") as mock_create_bridge:
            mock_bridge = MagicMock()
            mock_create_bridge.return_value = mock_bridge

            application = await app.create_application()

            assert application is not None
            assert application.bot_data["app"] is app
            mock_create_bridge.assert_called_once_with(sample_config)


class TestGetApp:
    """Tests for get_app helper function."""

    def test_get_app_returns_app_from_context(self, sample_config: TelebridgeConfig) -> None:
        """Test get_app retrieves TelebridgeApp from context."""
        app = TelebridgeApp(sample_config)

        # Create mock context
        mock_context = MagicMock()
        mock_context.application.bot_data = {"app": app}

        result = get_app(mock_context)

        assert result is app

    def test_get_app_with_different_apps(self, sample_config: TelebridgeConfig) -> None:
        """Test get_app returns correct app from context."""
        app1 = TelebridgeApp(sample_config)
        app2 = TelebridgeApp(sample_config)

        mock_context1 = MagicMock()
        mock_context1.application.bot_data = {"app": app1}

        mock_context2 = MagicMock()
        mock_context2.application.bot_data = {"app": app2}

        assert get_app(mock_context1) is app1
        assert get_app(mock_context2) is app2


class TestTelebridgeAppProperties:
    """Tests for TelebridgeApp property access after initialization."""

    @pytest.mark.asyncio
    async def test_properties_accessible_after_post_init(self, sample_config: TelebridgeConfig) -> None:
        """Test that properties are accessible after _post_init."""
        app = TelebridgeApp(sample_config)

        with patch("telebridge.app.create_bridge") as mock_create_bridge:
            mock_bridge = MagicMock()
            mock_create_bridge.return_value = mock_bridge

            application = await app.create_application()

            # Simulate post_init
            app._bot = MagicMock()

            # Now bot property should work
            assert app.bot is not None

    @pytest.mark.asyncio
    async def test_session_manager_accessible_after_init(self, sample_config: TelebridgeConfig) -> None:
        """Test session_manager is accessible after initialization."""
        app = TelebridgeApp(sample_config)

        with patch("telebridge.app.create_bridge") as mock_create_bridge:
            mock_bridge = MagicMock()
            mock_create_bridge.return_value = mock_bridge

            application = await app.create_application()

            # Simulate post_init setting session_manager
            from telebridge.session_manager import SessionManager
            app._session_manager = SessionManager(sample_config)

            # Now session_manager property should work
            assert app.session_manager is not None
