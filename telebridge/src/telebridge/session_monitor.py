"""JSONL session monitor with offset tracking.

An async service that polls Claude Code's JSONL transcript files for new output
and emits parsed messages via callback.

Core mechanism:
- Each tracked session maintains last_byte_offset into its JSONL file
- Polling loop runs every config.session.poll_interval seconds (default 2.0)
- Change detection uses BOTH mtime comparison AND file size check
- Incremental read: seek to offset -> read new lines -> parse JSON -> advance offset

Truncation detection: If last_byte_offset > current_file_size, reset offset to 0
(handles Claude Code /clear command which rewrites the file)

Corruption recovery: If first char at offset is not {, skip to next valid line

Session discovery:
- Read ~/.telebridge/session_map.json for hook-registered sessions
- Scan ~/.claude/projects/*/sessions-index.json for session metadata
- Filter: only track sessions whose cwd matches active multiplexer panes
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable, TYPE_CHECKING

import aiofiles

from telebridge.config import TelebridgeConfig, get_claude_projects_path, get_state_dir
from telebridge.interactive_ui import InteractiveUIManager, InteractiveUIState
from telebridge.transcript_parser import (
    ParsedEntry,
    PendingToolInfo,
    TranscriptParser,
)
from telebridge.utils import atomic_write_json

if TYPE_CHECKING:
    from telebridge.media_registry import MediaRegistry
    from telebridge.multiplexer import MultiplexerBridge

logger = logging.getLogger(__name__)


@dataclass
class TrackedSession:
    """State for a tracked Claude Code session."""

    session_id: str
    file_path: str  # Path to .jsonl file
    last_byte_offset: int = 0  # Byte offset for incremental reading

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "session_id": self.session_id,
            "file_path": self.file_path,
            "last_byte_offset": self.last_byte_offset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TrackedSession":
        """Create from dict."""
        return cls(
            session_id=data.get("session_id", ""),
            file_path=data.get("file_path", ""),
            last_byte_offset=data.get("last_byte_offset", 0),
        )


@dataclass
class MonitorState:
    """Persistent state for the session monitor.

    Stores tracking information for all monitored sessions to prevent
    duplicate notifications after restarts.
    """

    state_file: Path
    tracked_sessions: dict[str, TrackedSession] = field(default_factory=dict)
    _dirty: bool = field(default=False, repr=False)

    def load(self) -> None:
        """Load state from file."""
        if not self.state_file.exists():
            logger.debug(f"State file does not exist: {self.state_file}")
            return

        try:
            data = json.loads(self.state_file.read_text())
            sessions = data.get("tracked_sessions", {})
            self.tracked_sessions = {
                k: TrackedSession.from_dict(v) for k, v in sessions.items()
            }
            logger.info(f"Loaded {len(self.tracked_sessions)} tracked sessions from state")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load state file: {e}")
            self.tracked_sessions = {}

    def save(self) -> None:
        """Save state to file atomically."""
        data = {
            "tracked_sessions": {
                k: v.to_dict() for k, v in self.tracked_sessions.items()
            }
        }

        try:
            atomic_write_json(self.state_file, data, prefix=".monitor_state.")
            self._dirty = False
            logger.debug(f"Saved {len(self.tracked_sessions)} tracked sessions to state")
        except OSError as e:
            logger.error(f"Failed to save state file: {e}")

    def get_session(self, session_id: str) -> TrackedSession | None:
        """Get tracked session by ID."""
        return self.tracked_sessions.get(session_id)

    def update_session(self, session: TrackedSession) -> None:
        """Update or add a tracked session."""
        self.tracked_sessions[session.session_id] = session
        self._dirty = True

    def remove_session(self, session_id: str) -> None:
        """Remove a tracked session."""
        if session_id in self.tracked_sessions:
            del self.tracked_sessions[session_id]
            self._dirty = True

    def save_if_dirty(self) -> None:
        """Save state only if it has been modified."""
        if self._dirty:
            self.save()


@dataclass
class SessionInfo:
    """Information about a Claude Code session."""

    session_id: str
    file_path: Path
    cwd: str


class SessionMonitor:
    """Monitors Claude Code sessions for new assistant messages.

    Uses simple async polling with aiofiles for non-blocking I/O.
    Emits parsed JSONL entries via callback.
    """

    def __init__(
        self,
        config: TelebridgeConfig | None = None,
        poll_interval: float | None = None,
    ):
        self.config = config or TelebridgeConfig()
        self.poll_interval = (
            poll_interval if poll_interval is not None else self.config.session.poll_interval
        )

        state_dir = get_state_dir(self.config)
        self.state = MonitorState(state_file=state_dir / "monitor_state.json")
        self.state.load()

        self._running = False
        self._task: asyncio.Task | None = None
        self._message_callback: Callable[[list["ParsedEntry"]], Awaitable[None]] | None = None
        # Per-session pending tool_use state carried across poll cycles
        # session_id -> tool_use_id -> PendingToolInfo
        # NOTE: If a tool_use never receives a tool_result (e.g., session crash),
        # these entries accumulate. Consider adding TTL or session-end cleanup.
        self._pending_tools: dict[str, dict[str, PendingToolInfo]] = {}
        # Track last known session_map for detecting changes
        self._last_session_map: dict[str, str] = {}  # pane_key -> session_id
        # In-memory mtime cache for quick file change detection (not persisted)
        self._file_mtimes: dict[str, float] = {}  # session_id -> last_seen_mtime
        # Projects path for session discovery
        self._projects_path = get_claude_projects_path()

        # Optional interactive UI detection
        self._ui_detector: InteractiveUIManager | None = None
        self._ui_callback: Callable[[InteractiveUIState], Awaitable[None]] | None = None
        self._bridge: "MultiplexerBridge | None" = None

        # Optional media registry for periodic cleanup
        self._media_registry: "MediaRegistry | None" = None
        self._last_cleanup_time: float = 0.0  # Timestamp of last cleanup
        self._cleanup_interval: float = 3600.0  # Run cleanup every hour

    def set_message_callback(
        self, callback: Callable[[list[ParsedEntry]], Awaitable[None]]
    ) -> None:
        """Set the callback function for new parsed entries."""
        self._message_callback = callback

    def set_ui_callback(
        self, callback: Callable[[InteractiveUIState], Awaitable[None]]
    ) -> None:
        """Set callback for interactive UI detection.

        When enabled, the monitor will check captured pane content for
        interactive UI prompts (permissions, multi-choice, model selection)
        and emit InteractiveUIState for rendering as inline keyboards.

        Args:
            callback: Async function to call when new UI is detected
        """
        self._ui_callback = callback
        if self._ui_detector is None:
            self._ui_detector = InteractiveUIManager()

    def set_bridge(self, bridge: "MultiplexerBridge") -> None:
        """Set the multiplexer bridge for pane capture.

        Required for interactive UI detection. The bridge is used to
        capture pane content for detecting interactive prompts.

        Args:
            bridge: MultiplexerBridge instance (tmux or zellij)
        """
        self._bridge = bridge

    def set_media_registry(self, media_registry: "MediaRegistry") -> None:
        """Set the media registry for periodic cleanup.

        When enabled, the monitor will periodically clean up expired
        media files based on the configured TTL.

        Args:
            media_registry: MediaRegistry instance for cleanup
        """
        self._media_registry = media_registry

    def _extract_session_ids(self, session_map: dict[str, dict[str, str]]) -> dict[str, str]:
        """Extract session_id from session_map, keyed by pane_key.
        
        Helper to avoid duplicating this transformation logic.
        """
        return {k: v.get("session_id", "") for k, v in session_map.items()}

    def _get_session_map_path(self) -> Path:
        """Get path to session map file."""
        state_dir = get_state_dir(self.config)
        return state_dir / "session_map.json"

    async def _load_session_map(self) -> dict[str, dict[str, str]]:
        """Load current session_map from hook system.

        Returns dict mapping pane_key to {session_id, cwd}.
        """
        session_map_path = self._get_session_map_path()
        session_map: dict[str, dict[str, str]] = {}

        try:
            async with aiofiles.open(session_map_path, "r") as f:
                content = await f.read()
            raw_map = json.loads(content)
            # Transform to expected format: pane_key -> {session_id, cwd}
            for pane_key, info in raw_map.items():
                if isinstance(info, dict):
                    session_map[pane_key] = {
                        "session_id": info.get("session_id", ""),
                        "cwd": info.get("cwd", ""),
                    }
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.debug(f"Error reading session map: {e}")

        return session_map

    async def _get_active_session_ids(self) -> set[str]:
        """Get set of session IDs currently active in session_map."""
        session_map = await self._load_session_map()
        return {info["session_id"] for info in session_map.values() if info.get("session_id")}

    async def _scan_sessions_index(self) -> list[SessionInfo]:
        """Scan ~/.claude/projects/*/sessions-index.json for session metadata.

        Returns list of SessionInfo with session_id, file_path, cwd.
        """
        sessions = []
        projects_path = self._projects_path

        if not projects_path.exists():
            return sessions

        for project_dir in projects_path.iterdir():
            if not project_dir.is_dir():
                continue

            index_file = project_dir / "sessions-index.json"
            try:
                async with aiofiles.open(index_file, "r") as f:
                    content = await f.read()
                index_data = json.loads(content)
                entries = index_data.get("entries", [])

                for entry in entries:
                    session_id = entry.get("sessionId", "")
                    full_path = entry.get("fullPath", "")
                    project_path = entry.get("projectPath", "")

                    if not session_id or not full_path:
                        continue

                    file_path = Path(full_path)
                    if file_path.exists():
                        sessions.append(
                            SessionInfo(
                                session_id=session_id,
                                file_path=file_path,
                                cwd=project_path,
                            )
                        )
            except (json.JSONDecodeError, OSError) as e:
                logger.debug(f"Error reading index {index_file}: {e}")

        return sessions

    async def _read_new_lines(
        self, session: TrackedSession, file_path: Path
    ) -> list[dict]:
        """Read new lines from a session file using byte offset for efficiency.

        Detects file truncation (e.g. after /clear) and resets offset.
        Recovers from corrupted offsets (mid-line) by scanning to next line.
        """
        new_entries = []
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                # Get file size to detect truncation
                await f.seek(0, 2)  # Seek to end
                file_size = await f.tell()

                # Detect file truncation: if offset is beyond file size, reset
                if session.last_byte_offset > file_size:
                    logger.info(
                        f"File truncated for session {session.session_id} "
                        f"(offset {session.last_byte_offset} > size {file_size}). Resetting."
                    )
                    session.last_byte_offset = 0

                # Seek to last read position for incremental reading
                await f.seek(session.last_byte_offset)

                # Detect corrupted offset: if we're mid-line (not at '{'),
                # scan forward to the next line start.
                if session.last_byte_offset > 0:
                    first_char = await f.read(1)
                    if first_char and first_char != "{":
                        logger.warning(
                            f"Corrupted offset {session.last_byte_offset} in session {session.session_id} "
                            f"(mid-line), scanning to next line"
                        )
                        await f.readline()  # Skip rest of partial line
                        session.last_byte_offset = await f.tell()
                        return []
                    await f.seek(session.last_byte_offset)  # Reset for normal read

                # Read only new lines from the offset.
                # Track safe_offset: only advance past lines that parsed
                # successfully. A non-empty line that fails JSON parsing is
                # likely a partial write; stop and retry next cycle.
                safe_offset = session.last_byte_offset
                async for line in f:
                    line = line.rstrip("\n\r")
                    if not line:
                        safe_offset = await f.tell()
                        continue

                    try:
                        data = json.loads(line)
                        new_entries.append(data)
                        safe_offset = await f.tell()
                    except json.JSONDecodeError:
                        # Partial JSONL line — don't advance offset past it
                        logger.warning(
                            f"Partial JSONL line in session {session.session_id}, "
                            f"will retry next cycle"
                        )
                        break

                session.last_byte_offset = safe_offset

        except OSError as e:
            logger.error(f"Error reading session file {file_path}: {e}")
        return new_entries

    async def check_for_updates(self, active_session_ids: set[str]) -> list[dict]:
        """Check all sessions for new JSONL entries.

        Reads from last byte offset. Returns list of new parsed entries.

        Args:
            active_session_ids: Set of session IDs currently in session_map
        """
        new_entries = []

        # Scan projects to get available session files
        sessions = await self._scan_sessions_index()

        # Only process sessions that are in session_map
        for session_info in sessions:
            if session_info.session_id not in active_session_ids:
                continue

            try:
                tracked = self.state.get_session(session_info.session_id)

                if tracked is None:
                    # For new sessions, initialize offset to end of file
                    # to avoid re-processing old messages
                    try:
                        stat_result = session_info.file_path.stat()
                        file_size = stat_result.st_size
                        current_mtime = stat_result.st_mtime
                    except OSError:
                        file_size = 0
                        current_mtime = 0.0

                    tracked = TrackedSession(
                        session_id=session_info.session_id,
                        file_path=str(session_info.file_path),
                        last_byte_offset=file_size,
                    )
                    self.state.update_session(tracked)
                    self._file_mtimes[session_info.session_id] = current_mtime
                    logger.info(f"Started tracking session: {session_info.session_id}")
                    continue

                # Check mtime + file size to see if file has changed
                try:
                    st = session_info.file_path.stat()
                    current_mtime = st.st_mtime
                    current_size = st.st_size
                except OSError:
                    continue

                last_mtime = self._file_mtimes.get(session_info.session_id, 0.0)
                if (
                    current_mtime <= last_mtime
                    and current_size <= tracked.last_byte_offset
                ):
                    # File hasn't changed, skip reading
                    continue

                # File changed, read new content from last offset
                entries = await self._read_new_lines(tracked, session_info.file_path)
                self._file_mtimes[session_info.session_id] = current_mtime

                if entries:
                    logger.debug(
                        f"Read {len(entries)} new entries for session {session_info.session_id}"
                    )

                new_entries.extend(entries)
                self.state.update_session(tracked)

            except OSError as e:
                logger.debug(f"Error processing session {session_info.session_id}: {e}")

        self.state.save_if_dirty()
        return new_entries

    async def _detect_and_cleanup_changes(self) -> set[str]:
        """Detect session_map changes and cleanup removed sessions.

        Returns set of active session IDs.
        """
        session_map = await self._load_session_map()
        current_session_ids: set[str] = set()

        for info in session_map.values():
            session_id = info.get("session_id", "")
            if session_id:
                current_session_ids.add(session_id)

        # Check for sessions that were in old map but not in current
        old_session_ids = set(self._last_session_map.values())
        removed_session_ids = old_session_ids - current_session_ids

        if removed_session_ids:
            logger.info(f"Removing {len(removed_session_ids)} stale sessions")
            for session_id in removed_session_ids:
                self.state.remove_session(session_id)
                self._file_mtimes.pop(session_id, None)
                self._pending_tools.pop(session_id, None)
            self.state.save_if_dirty()

        # Update last known map only if changed
        new_session_map = self._extract_session_ids(session_map)
        if new_session_map != self._last_session_map:
            self._last_session_map = new_session_map

        return current_session_ids

    async def _monitor_loop(self) -> None:
        """Background loop for checking session updates.

        Uses simple async polling with aiofiles for non-blocking I/O.
        """
        logger.info(f"Session monitor started, polling every {self.poll_interval}s")

        # Initialize last known session_map
        session_map = await self._load_session_map()
        self._last_session_map = self._extract_session_ids(session_map)

        while self._running:
            try:
                # Detect session_map changes and cleanup removed sessions
                active_session_ids = await self._detect_and_cleanup_changes()

                # Check for new messages (all I/O is async)
                new_entries = await self.check_for_updates(active_session_ids)

                if new_entries and self._message_callback:
                    try:
                        # Group entries by session_id for parsing with session-specific pending_tools
                        entries_by_session: defaultdict[str, list[dict]] = defaultdict(list)
                        for entry in new_entries:
                            session_id = entry.get("sessionId", "")
                            if session_id:
                                entries_by_session[session_id].append(entry)

                        # Parse each session's entries with its pending_tools state
                        all_parsed: list[ParsedEntry] = []
                        for session_id, session_entries in entries_by_session.items():
                            session_pending = self._pending_tools.get(session_id, {})
                            parsed, remaining_pending = TranscriptParser.parse_entries(
                                session_entries,
                                pending_tools=session_pending,
                                thinking_max_length=self.config.session.thinking_max_length,
                                session_id=session_id,
                            )
                            self._pending_tools[session_id] = remaining_pending
                            all_parsed.extend(parsed)

                        if all_parsed:
                            await self._message_callback(all_parsed)

                    except Exception as e:
                        logger.error(f"Message callback error: {e}")

                # Interactive UI detection (if bridge and callback are set)
                if self._bridge and self._ui_detector and self._ui_callback:
                    try:
                        await self._check_interactive_uis()
                    except Exception as e:
                        logger.error(f"UI detection error: {e}")

                # Periodic media cleanup (if media_registry is set)
                if self._media_registry:
                    import time
                    current_time = time.time()
                    if current_time - self._last_cleanup_time >= self._cleanup_interval:
                        try:
                            deleted = self._media_registry.cleanup_expired()
                            if deleted > 0:
                                logger.info(f"Periodic cleanup: removed {deleted} expired media file(s)")
                            self._last_cleanup_time = current_time
                        except Exception as e:
                            logger.error(f"Media cleanup error: {e}")

            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(self.poll_interval)

        logger.info("Session monitor stopped")

    async def _check_interactive_uis(self) -> None:
        """Check active panes for interactive UI prompts.

        Captures pane content from the multiplexer bridge and checks for
        interactive UI elements (permissions, multi-choice, model selection).
        If detected and changed, invokes the UI callback.
        """
        if not self._bridge or not self._ui_detector or not self._ui_callback:
            return

        # Get current session map to know which panes are active
        session_map = await self._load_session_map()

        for pane_key, _ in session_map.items():
            try:
                # Capture pane content (synchronous bridge call in async context)
                # Use timeout to prevent blocking the monitor loop
                pane_content = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, self._bridge.capture_pane_ansi
                    ),
                    timeout=0.5,  # 500ms timeout per pane
                )

                if not pane_content:
                    continue

                # Check for interactive UI with change detection
                ui_state = self._ui_detector.check_for_ui(pane_key, pane_content)

                if ui_state and self._ui_callback:
                    await self._ui_callback(ui_state)

            except asyncio.TimeoutError:
                logger.debug(f"UI check timeout for pane {pane_key}")
            except Exception as e:
                logger.debug(f"UI check failed for pane {pane_key}: {e}")

    def start(self) -> None:
        """Start the session monitor background loop."""
        if self._running:
            logger.warning("Monitor already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        """Stop the session monitor and save state."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        self.state.save()
        logger.info("Session monitor stopped and state saved")

    @property
    def pending_tools(self) -> dict[str, dict[str, PendingToolInfo]]:
        """Get pending tools state (for tool pairing across poll cycles)."""
        return self._pending_tools
