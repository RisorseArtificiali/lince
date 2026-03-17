"""Unit tests for MediaRegistry."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from telebridge.config import MediaConfig
from telebridge.media_registry import MediaEntry, MediaRegistry, MediaRegistryState


class TestMediaEntry:
    """Tests for MediaEntry dataclass."""

    def test_create_entry(self):
        """Test creating a media entry."""
        entry = MediaEntry(
            file_path="/tmp/test.jpg",
            session_id="session-123",
            created_at=1234567890.0,
            file_type="photo",
        )
        assert entry.file_path == "/tmp/test.jpg"
        assert entry.session_id == "session-123"
        assert entry.created_at == 1234567890.0
        assert entry.file_type == "photo"

    def test_to_dict(self):
        """Test serializing entry to dict."""
        entry = MediaEntry(
            file_path="/tmp/test.jpg",
            session_id="session-123",
            created_at=1234567890.0,
            file_type="photo",
        )
        data = entry.to_dict()
        assert data["file_path"] == "/tmp/test.jpg"
        assert data["session_id"] == "session-123"
        assert data["created_at"] == 1234567890.0
        assert data["file_type"] == "photo"

    def test_from_dict(self):
        """Test deserializing entry from dict."""
        data = {
            "file_path": "/tmp/test.jpg",
            "session_id": "session-123",
            "created_at": 1234567890.0,
            "file_type": "document",
        }
        entry = MediaEntry.from_dict(data)
        assert entry.file_path == "/tmp/test.jpg"
        assert entry.session_id == "session-123"
        assert entry.created_at == 1234567890.0
        assert entry.file_type == "document"

    def test_from_dict_defaults(self):
        """Test deserializing with missing fields uses defaults."""
        data = {}
        entry = MediaEntry.from_dict(data)
        assert entry.file_path == ""
        assert entry.session_id == ""
        assert entry.created_at == 0.0
        assert entry.file_type == ""


class TestMediaRegistryState:
    """Tests for MediaRegistryState dataclass."""

    def test_default_state(self):
        """Test default state is empty."""
        state = MediaRegistryState()
        assert state.entries == {}
        assert state.session_files == {}

    def test_state_with_entries(self):
        """Test state with entries."""
        entry = MediaEntry(
            file_path="/tmp/test.jpg",
            session_id="session-123",
            created_at=1234567890.0,
            file_type="photo",
        )
        state = MediaRegistryState()
        state.entries["/tmp/test.jpg"] = entry
        state.session_files["session-123"] = {"/tmp/test.jpg"}

        assert len(state.entries) == 1
        assert len(state.session_files) == 1


class TestMediaRegistry:
    """Tests for MediaRegistry class."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return MediaConfig(
            cleanup_enabled=True,
            file_ttl_hours=24.0,
            cleanup_on_unbind=True,
        )

    @pytest.fixture
    def temp_state_dir(self, tmp_path):
        """Create a temporary state directory."""
        return tmp_path / "state"

    @pytest.fixture
    def registry(self, config, temp_state_dir):
        """Create a test registry."""
        temp_state_dir.mkdir(parents=True, exist_ok=True)
        return MediaRegistry(config, temp_state_dir)

    def test_init(self, config, temp_state_dir):
        """Test registry initialization."""
        registry = MediaRegistry(config, temp_state_dir)
        assert registry.config == config
        assert registry.state.entries == {}

    def test_register_disabled(self, tmp_path):
        """Test register does nothing when cleanup is disabled."""
        config = MediaConfig(cleanup_enabled=False)
        registry = MediaRegistry(config, tmp_path)
        registry.register("/tmp/test.jpg", "session-123", "photo")
        assert len(registry.state.entries) == 0

    def test_register_photo(self, registry):
        """Test registering a photo file."""
        registry.register("/tmp/test.jpg", "session-123", "photo")
        assert len(registry.state.entries) == 1
        assert "/tmp/test.jpg" in registry.state.entries
        assert registry.state.entries["/tmp/test.jpg"].file_type == "photo"
        assert registry.state.entries["/tmp/test.jpg"].session_id == "session-123"
        assert "session-123" in registry.state.session_files

    def test_register_document(self, registry):
        """Test registering a document file."""
        registry.register("/tmp/test.pdf", "session-456", "document")
        assert len(registry.state.entries) == 1
        assert registry.state.entries["/tmp/test.pdf"].file_type == "document"

    def test_register_multiple_files_same_session(self, registry):
        """Test registering multiple files for the same session."""
        registry.register("/tmp/test1.jpg", "session-123", "photo")
        registry.register("/tmp/test2.pdf", "session-123", "document")
        assert len(registry.state.entries) == 2
        assert len(registry.state.session_files["session-123"]) == 2

    def test_cleanup_session_disabled(self, tmp_path):
        """Test cleanup_session returns 0 when cleanup is disabled."""
        config = MediaConfig(cleanup_enabled=False)
        registry = MediaRegistry(config, tmp_path)
        # Even with entries, cleanup should do nothing
        registry.state.entries["/tmp/test.jpg"] = MediaEntry(
            file_path="/tmp/test.jpg",
            session_id="session-123",
            created_at=time.time(),
            file_type="photo",
        )
        deleted = registry.cleanup_session("session-123")
        assert deleted == 0

    def test_cleanup_session_no_files(self, registry):
        """Test cleanup_session returns 0 when no files for session."""
        deleted = registry.cleanup_session("nonexistent-session")
        assert deleted == 0

    def test_cleanup_session_deletes_files(self, registry, tmp_path):
        """Test cleanup_session deletes tracked files."""
        # Create a real temp file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test content")

        registry.register(str(test_file), "session-123", "photo")
        assert len(registry.state.entries) == 1

        deleted = registry.cleanup_session("session-123")
        assert deleted == 1
        assert not test_file.exists()
        assert len(registry.state.entries) == 0
        assert "session-123" not in registry.state.session_files

    def test_cleanup_session_handles_missing_file(self, registry):
        """Test cleanup_session handles files that no longer exist."""
        # Register a file that doesn't exist
        registry.state.entries["/nonexistent/test.jpg"] = MediaEntry(
            file_path="/nonexistent/test.jpg",
            session_id="session-123",
            created_at=time.time(),
            file_type="photo",
        )
        registry.state.session_files["session-123"] = {"/nonexistent/test.jpg"}

        deleted = registry.cleanup_session("session-123")
        # Should return 0 since file couldn't be deleted
        assert deleted == 0
        # Entry should be removed from entries (but not deleted from disk)
        assert len(registry.state.entries) == 0
        # Session tracking should be cleaned up if empty
        assert "session-123" not in registry.state.session_files

    def test_cleanup_expired_disabled(self, tmp_path):
        """Test cleanup_expired returns 0 when cleanup is disabled."""
        config = MediaConfig(cleanup_enabled=False)
        registry = MediaRegistry(config, tmp_path)
        deleted = registry.cleanup_expired()
        assert deleted == 0

    def test_cleanup_expired_no_files(self, registry):
        """Test cleanup_expired returns 0 when no expired files."""
        deleted = registry.cleanup_expired()
        assert deleted == 0

    def test_cleanup_expired_deletes_old_files(self, registry, tmp_path):
        """Test cleanup_expired deletes files older than TTL."""
        # Create a real temp file
        test_file = tmp_path / "old.jpg"
        test_file.write_text("test content")

        # Register with old timestamp (25 hours ago)
        old_time = time.time() - (25 * 3600)
        entry = MediaEntry(
            file_path=str(test_file),
            session_id="session-123",
            created_at=old_time,
            file_type="photo",
        )
        registry.state.entries[str(test_file)] = entry
        registry.state.session_files["session-123"] = {str(test_file)}

        # TTL is 24 hours, so this should be deleted
        deleted = registry.cleanup_expired()
        assert deleted == 1
        assert not test_file.exists()

    def test_cleanup_expired_keeps_new_files(self, registry, tmp_path):
        """Test cleanup_expired keeps files newer than TTL."""
        # Create a real temp file
        test_file = tmp_path / "new.jpg"
        test_file.write_text("test content")

        # Register with current timestamp
        registry.register(str(test_file), "session-123", "photo")

        # TTL is 24 hours, so this should NOT be deleted
        deleted = registry.cleanup_expired()
        assert deleted == 0
        assert test_file.exists()

    def test_cleanup_expired_custom_ttl(self, registry, tmp_path):
        """Test cleanup_expired with custom TTL."""
        # Create a real temp file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test content")

        # Register with timestamp 2 hours ago
        old_time = time.time() - (2 * 3600)
        entry = MediaEntry(
            file_path=str(test_file),
            session_id="session-123",
            created_at=old_time,
            file_type="photo",
        )
        registry.state.entries[str(test_file)] = entry

        # With TTL of 1 hour, this should be deleted
        deleted = registry.cleanup_expired(ttl_hours=1.0)
        assert deleted == 1
        assert not test_file.exists()

    def test_get_session_file_count(self, registry):
        """Test getting file count for a session."""
        assert registry.get_session_file_count("session-123") == 0

        registry.register("/tmp/test1.jpg", "session-123", "photo")
        registry.register("/tmp/test2.pdf", "session-123", "document")
        assert registry.get_session_file_count("session-123") == 2

    def test_get_total_file_count(self, registry):
        """Test getting total file count."""
        assert registry.get_total_file_count() == 0

        registry.register("/tmp/test1.jpg", "session-123", "photo")
        registry.register("/tmp/test2.pdf", "session-456", "document")
        assert registry.get_total_file_count() == 2

    def test_save_and_load(self, registry, temp_state_dir, tmp_path):
        """Test saving and loading registry state."""
        # Create actual files that will exist when loading
        test_file1 = tmp_path / "test1.jpg"
        test_file1.write_text("test content 1")
        test_file2 = tmp_path / "test2.pdf"
        test_file2.write_text("test content 2")

        # Register the files
        registry.register(str(test_file1), "session-123", "photo")
        registry.register(str(test_file2), "session-456", "document")
        registry.save()

        # Create a new registry and load state
        new_registry = MediaRegistry(registry.config, temp_state_dir)
        new_registry.load()

        assert len(new_registry.state.entries) == 2
        assert str(test_file1) in new_registry.state.entries
        assert str(test_file2) in new_registry.state.entries
        assert new_registry.state.session_files["session-123"] == {str(test_file1)}
        assert new_registry.state.session_files["session-456"] == {str(test_file2)}

    def test_load_removes_stale_entries(self, registry, temp_state_dir):
        """Test that load removes entries for files that no longer exist."""
        # Register and save
        registry.register("/tmp/nonexistent.jpg", "session-123", "photo")
        registry.save()

        # Load in new registry - should remove stale entry
        new_registry = MediaRegistry(registry.config, temp_state_dir)
        new_registry.load()

        assert len(new_registry.state.entries) == 0
        assert "session-123" not in new_registry.state.session_files

    def test_load_handles_missing_file(self, config, temp_state_dir):
        """Test load handles missing state file gracefully."""
        registry = MediaRegistry(config, temp_state_dir)
        # Should not raise, just return empty state
        registry.load()
        assert len(registry.state.entries) == 0

    def test_load_handles_invalid_json(self, config, temp_state_dir):
        """Test load handles invalid JSON gracefully."""
        temp_state_dir.mkdir(parents=True, exist_ok=True)
        state_file = temp_state_dir / "media_registry.json"
        state_file.write_text("not valid json")
        registry = MediaRegistry(config, temp_state_dir)
        # Should not raise, just return empty state
        registry.load()
        assert len(registry.state.entries) == 0
