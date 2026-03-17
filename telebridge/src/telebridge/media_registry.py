"""Media registry for tracking and cleanup of downloaded Telegram files."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from telebridge.config import MediaConfig, get_state_dir
from telebridge.utils import atomic_write_json, load_json_file

logger = logging.getLogger(__name__)


@dataclass
class MediaEntry:
    """Tracked media file entry."""

    file_path: str  # Absolute path to downloaded file
    session_id: str  # Claude session ID this file belongs to
    created_at: float  # Unix timestamp when file was created
    file_type: str  # "photo" or "document"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "file_path": self.file_path,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "file_type": self.file_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaEntry":
        """Create from dict."""
        return cls(
            file_path=data.get("file_path", ""),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", 0.0),
            file_type=data.get("file_type", ""),
        )


@dataclass
class MediaRegistryState:
    """Full persisted state structure."""

    entries: dict[str, MediaEntry] = field(default_factory=dict)  # file_path -> entry


    session_files: dict[str, set[str]] = field(default_factory=dict)  # session_id -> file_paths


class MediaRegistry:
    """Tracks and cleans up downloaded media files.

    Files are registered when downloaded via photo_handler or document_handler.
    Cleanup happens based on:
    - TTL: Files older than file_ttl_hours are deleted
    - Session lifecycle: Files are deleted when session unbinds or clears

    State is persisted to media_registry.json in the state directory.
    """

    def __init__(self, config: MediaConfig, state_dir: Path | None = None) -> None:
        self.config = config
        self._state_dir = state_dir
        self._state_path = (
            state_dir / "media_registry.json" if state_dir else Path.home() / ".telebridge" / "media_registry.json"
        )
        self.state = MediaRegistryState()

    def register(self, file_path: str, session_id: str, file_type: str) -> None:
        """Register a newly downloaded file.

        Args:
            file_path: Absolute path to the downloaded file
            session_id: Claude session ID this file belongs to
            file_type: Type of media ("photo" or "document")
        """
        if not self.config.cleanup_enabled:
            return  # Cleanup disabled, don't track

        entry = MediaEntry(
            file_path=file_path,
            session_id=session_id,
            created_at=time.time(),
            file_type=file_type,
        )

        # Track by file path
        self.state.entries[file_path] = entry

        # Track by session
        if session_id not in self.state.session_files:
            self.state.session_files[session_id] = set()
        self.state.session_files[session_id].add(file_path)

        logger.debug(f"Registered media file: {file_path} for session {session_id}")

    def cleanup_session(self, session_id: str) -> int:
        """Remove all files for a session.

        Called when session unbinds or clears.
        Returns count of deleted files.

        Args:
            session_id: Claude session ID to cleanup

        Returns:
            Number of files deleted
        """
        if not self.config.cleanup_enabled:
            return 0

        file_paths = self.state.session_files.get(session_id, set())
        if not file_paths:
            return 0

        deleted_count = 0
        for file_path in list(file_paths):  # Copy to avoid modification during iteration
            if self._delete_file(file_path):
                deleted_count += 1

        # Session tracking is already cleaned up by _delete_file when set becomes empty
        # But ensure it's removed if there were any files that couldn't be deleted
        if session_id in self.state.session_files and not self.state.session_files[session_id]:
            del self.state.session_files[session_id]

        logger.info(f"Cleaned up {deleted_count} media file(s) for session {session_id}")
        self.save()

        return deleted_count

    def cleanup_expired(self, ttl_hours: float | None = None) -> int:
        """Remove files older than TTL.

        Called periodically by background cleanup task.
        Returns count of deleted files.

        Args:
            ttl_hours: Time-to-live in hours (uses config default if None)

        Returns:
            Number of files deleted
        """
        if not self.config.cleanup_enabled:
            return 0

        if ttl_hours is None:
            ttl_hours = self.config.file_ttl_hours

        ttl_seconds = ttl_hours * 3600
        current_time = time.time()
        deleted_count = 0

        # Find expired entries
        expired_paths = []
        for file_path in list(self.state.entries.keys()):  # Copy to avoid modification during iteration
            entry = self.state.entries[file_path]
            age = current_time - entry.created_at
            if age > ttl_seconds:
                expired_paths.append(file_path)

        # Delete expired files
        for file_path in expired_paths:
            if self._delete_file(file_path):
                deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired media file(s) (TTL: {ttl_hours}h)")
            self.save()

        return deleted_count

    def _delete_file(self, file_path: str) -> bool:
        """Delete a file and remove from tracking.

        Args:
            file_path: Path to file to delete

        Returns:
            True if file was deleted, False otherwise
        """
        # Remove from entries
        entry = self.state.entries.pop(file_path, None)
        if entry:
            # Remove from session_files index
            session_files = self.state.session_files.get(entry.session_id)
            if session_files:
                session_files.discard(file_path)
                if not session_files:
                    del self.state.session_files[entry.session_id]

        # Delete actual file
        try:
            Path(file_path).unlink()
            logger.debug(f"Deleted media file: {file_path}")
            return True
        except OSError as e:
            logger.warning(f"Failed to delete media file {file_path}: {e}")
            return False

    def load(self) -> None:
        """Load state from disk."""
        data = load_json_file(self._state_path)
        if not data:
            return

        # Load entries
        entries_data = data.get("entries", {})
        self.state.entries = {
            k: MediaEntry.from_dict(v) for k, v in entries_data.items()
        }

        # Load session_files index
        session_files_data = data.get("session_files", {})
        self.state.session_files = {
            k: set(v) for k, v in session_files_data.items() if isinstance(v, list)
        }

        # Verify tracked files still exist, remove stale entries
        self._verify_entries()

        logger.info(f"Loaded {len(self.state.entries)} media entries from registry")

    def save(self) -> None:
        """Save state to disk atomically."""
        data = {
            "entries": {k: v.to_dict() for k, v in self.state.entries.items()},
            "session_files": {k: list(v) for k, v in self.state.session_files.items()},
        }

        try:
            atomic_write_json(self._state_path, data, prefix=".media_registry.")
            logger.debug(f"Saved {len(self.state.entries)} media entries to registry")
        except OSError as e:
            logger.error(f"Failed to save media registry: {e}")

    def _verify_entries(self) -> None:
        """Verify tracked files still exist, remove entries for missing files."""
        stale_paths = []

        for file_path, entry in self.state.entries.items():
            if not Path(file_path).exists():
                stale_paths.append(file_path)

        for file_path in stale_paths:
            entry = self.state.entries.pop(file_path, None)
            if entry:
                # Remove from session_files index
                session_files = self.state.session_files.get(entry.session_id)
                if session_files:
                    session_files.discard(file_path)
                    if not session_files:
                        del self.state.session_files[entry.session_id]
                logger.debug(f"Removed stale entry for missing file: {file_path}")

        if stale_paths:
            logger.info(f"Removed {len(stale_paths)} stale entries for missing files")

    def get_session_file_count(self, session_id: str) -> int:
        """Get count of tracked files for a session.

        Args:
            session_id: Claude session ID

        Returns:
            Number of tracked files for the session
        """
        return len(self.state.session_files.get(session_id, set()))

    def get_total_file_count(self) -> int:
        """Get total count of tracked files.

        Returns:
            Total number of tracked files
        """
        return len(self.state.entries)
