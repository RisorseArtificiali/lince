"""Session manager for topic-pane-session mapping."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from telebridge.config import TelebridgeConfig, get_claude_projects_path, get_state_dir
from telebridge.utils import LIVENESS_CACHE_TTL, MAX_METADATA_CACHE_SIZE, MAX_SESSION_CACHE_SIZE, atomic_write_json, load_json_file

if TYPE_CHECKING:
    from telebridge.media_registry import MediaRegistry
    from telebridge.multiplexer import MultiplexerBridge

logger = logging.getLogger(__name__)


@dataclass
class PaneState:
    """Persistent state for a multiplexer pane."""

    session_id: str = ""
    cwd: str = ""
    pane_name: str = ""


@dataclass
class SessionInfo:
    """Runtime session information with transient metadata."""

    session_id: str
    pane_key: str
    cwd: str
    summary: str = "Untitled"
    message_count: int = 0
    file_path: str = ""


@dataclass
class SessionManagerState:
    """Full persisted state structure."""

    window_states: dict[str, PaneState] = field(default_factory=dict)
    thread_bindings: dict[str, dict[str, str]] = field(default_factory=dict)
    user_pane_offsets: dict[str, dict[str, int]] = field(default_factory=dict)


class SessionManager:
    """Manages bidirectional mapping between Telegram threads, panes, and sessions."""

    def __init__(
        self, config: TelebridgeConfig, media_registry: MediaRegistry | None = None
    ) -> None:
        self.config = config
        self._media_registry = media_registry
        self.state = SessionManagerState()
        self._state_path = get_state_dir(config) / "state.json"
        self._session_map_path = get_state_dir(config) / "session_map.json"
        # Caches for expensive operations with bounds
        self._session_file_cache: OrderedDict[str, Path] = OrderedDict()
        self._metadata_cache: OrderedDict[str, tuple[float, str, int]] = OrderedDict()  # mtime -> (summary, count)
        # Liveness cache for hot path optimization (pane_key -> (timestamp, is_live))
        self._liveness_cache: dict[str, tuple[float, bool]] = {}

    # --- Binding operations ---

    def bind_thread(self, user_id: int, thread_id: int, pane_key: str) -> None:
        """Associate Telegram topic with multiplexer pane."""
        user_key = str(user_id)
        thread_key = str(thread_id)

        if user_key not in self.state.thread_bindings:
            self.state.thread_bindings[user_key] = {}

        # Only save if binding actually changed
        existing = self.state.thread_bindings[user_key].get(thread_key)
        if existing != pane_key:
            self.state.thread_bindings[user_key][thread_key] = pane_key
            self.save()

    def unbind_thread(self, user_id: int, thread_id: int) -> None:
        """Detach topic from session with optional media cleanup."""
        user_key = str(user_id)
        thread_key = str(thread_id)
        if user_key in self.state.thread_bindings:
            # Get session_id before unbinding
            pane_key = self.state.thread_bindings[user_key].get(thread_key)
            if pane_key:
                pane_state = self.state.window_states.get(pane_key)
                session_id = pane_state.session_id if pane_state else None

                # Cleanup media for this session if enabled
                if self._media_registry and session_id:
                    self._media_registry.cleanup_session(session_id)

            self.state.thread_bindings[user_key].pop(thread_key, None)
            self.save()

    def resolve_pane_for_thread(self, user_id: int, thread_id: int) -> str | None:
        """Find pane for a topic."""
        user_key = str(user_id)
        thread_key = str(thread_id)
        return self.state.thread_bindings.get(user_key, {}).get(thread_key)

    def resolve_thread_for_session(self, session_id: str) -> tuple[str, int] | None:
        """Find pane_key and thread_id for a Claude session.

        Used for routing outbound messages back to the correct Telegram thread.

        Args:
            session_id: Claude Code session ID

        Returns:
            (pane_key, thread_id) tuple or None if session not found
        """
        # Find pane_key with matching session_id
        pane_key = None
        for pk, state in self.state.window_states.items():
            if state.session_id == session_id:
                pane_key = pk
                break

        if not pane_key:
            return None

        # Find thread_id bound to this pane
        for user_id, threads in self.state.thread_bindings.items():
            for thread_id, bound_pane in threads.items():
                if bound_pane == pane_key:
                    return (pane_key, int(thread_id))

        # Pane found but no thread binding - use main chat
        return (pane_key, 0)

    # --- Session resolution ---

    def resolve_session_for_pane(self, pane_key: str) -> SessionInfo | None:
        """Find Claude session for a pane."""
        pane_state = self.state.window_states.get(pane_key)
        if not pane_state or not pane_state.session_id:
            return None

        # Derive metadata from JSONL
        file_path = self._resolve_session_file_path(pane_state.session_id)
        summary, message_count = self._derive_session_metadata(file_path)

        return SessionInfo(
            session_id=pane_state.session_id,
            pane_key=pane_key,
            cwd=pane_state.cwd,
            summary=summary,
            message_count=message_count,
            file_path=str(file_path),
        )

    # --- Session liveness detection (LINCE-13) ---

    async def is_pane_live(self, pane_key: str, bridge: MultiplexerBridge, use_cache: bool = True) -> bool:
        """Check if a pane still exists in the multiplexer.

        Args:
            pane_key: Pane key to check
            bridge: Multiplexer bridge instance
            use_cache: Whether to use cached liveness result (default: True)

        Returns:
            True if pane exists and is accessible
        """
        # Check cache first for hot path optimization
        if use_cache:
            cached = self._liveness_cache.get(pane_key)
            if cached:
                timestamp, is_live = cached
                if time.time() - timestamp < LIVENESS_CACHE_TTL:
                    return is_live

        # Actual liveness check
        try:
            panes = await asyncio.to_thread(bridge.list_panes)
            is_live = pane_key in panes

            # Update cache
            self._liveness_cache[pane_key] = (time.time(), is_live)
            return is_live
        except (RuntimeError, asyncio.TimeoutError):
            # Cache negative result for shorter time
            self._liveness_cache[pane_key] = (time.time(), False)
            return False

    async def is_session_active(self, pane_key: str, bridge: MultiplexerBridge) -> bool:
        """Check if pane is live AND has an active Claude Code session.

        Combines pane liveness with session_id presence.

        Args:
            pane_key: Pane key to check
            bridge: Multiplexer bridge instance

        Returns:
            True if pane exists and has a session_id
        """
        if not await self.is_pane_live(pane_key, bridge):
            return False

        pane_state = self.state.window_states.get(pane_key)
        return bool(pane_state and pane_state.session_id)

    async def resolve_session_for_thread_checked(
        self, user_id: int, thread_id: int, bridge: MultiplexerBridge
    ) -> SessionInfo | None:
        """Resolve session for thread with liveness validation.

        Returns None if:
        - No binding exists
        - Pane is dead
        - Session is empty (cleared)

        Args:
            user_id: Telegram user ID
            thread_id: Telegram thread ID
            bridge: Multiplexer bridge instance

        Returns:
            SessionInfo if live and valid, None otherwise
        """
        pane_key = self.resolve_pane_for_thread(user_id, thread_id)
        if not pane_key:
            return None

        # Check liveness before resolving
        if not await self.is_session_active(pane_key, bridge):
            return None

        return self.resolve_session_for_pane(pane_key)

    # --- Session map integration ---

    def load_session_map(self) -> dict[str, dict[str, str]]:
        """Read hook-written session_map.json using shared utility."""
        return load_json_file(self._session_map_path)

    def update_from_session_map(self) -> None:
        """Sync window_states from session_map.json.

        Only saves state if changes were actually made.
        """
        session_map = self.load_session_map()
        changes_made = False

        for pane_key, session_info in session_map.items():
            if pane_key not in self.state.window_states:
                self.state.window_states[pane_key] = PaneState()

            old_session_id = self.state.window_states[pane_key].session_id
            new_session_id = session_info.get("session_id", "")

            old_cwd = self.state.window_states[pane_key].cwd
            new_cwd = session_info.get("cwd", "")

            if old_session_id != new_session_id or old_cwd != new_cwd:
                self.state.window_states[pane_key].session_id = new_session_id
                self.state.window_states[pane_key].cwd = new_cwd
                changes_made = True

        if changes_made:
            self.save()

    # --- Session management ---

    def clear_pane_session(self, pane_key: str) -> None:
        """Empty session_id when /clear is invoked with optional media cleanup."""
        if pane_key in self.state.window_states:
            # Only save if session_id was actually set
            if self.state.window_states[pane_key].session_id != "":
                # Get session_id before clearing
                session_id = self.state.window_states[pane_key].session_id

                self.state.window_states[pane_key].session_id = ""
                # Cleanup media for this session if enabled
                if self._media_registry and session_id:
                    self._media_registry.cleanup_session(session_id)
                self.save()

    def list_active_sessions(self) -> list[SessionInfo]:
        """Enumerate bound sessions with metadata."""
        sessions = []
        for pane_key, pane_state in self.state.window_states.items():
            if pane_state.session_id:
                info = self.resolve_session_for_pane(pane_key)
                if info:
                    sessions.append(info)
        return sessions

    # --- Stale detection ---

    async def cleanup_stale_panes(self, bridge: MultiplexerBridge) -> None:
        """Remove entries for panes that no longer exist."""
        try:
            live_panes = set(bridge.list_panes())
        except (AttributeError, RuntimeError):
            return  # Bridge doesn't support list_panes

        stale = set(self.state.window_states.keys()) - live_panes

        for pane_key in stale:
            del self.state.window_states[pane_key]
            # Clean up caches for stale panes
            self._session_file_cache.pop(pane_key, None)
            self._liveness_cache.pop(pane_key, None)

        # Clean thread bindings for stale panes
        for user_id, threads in self.state.thread_bindings.items():
            self.state.thread_bindings[user_id] = {
                t: p for t, p in threads.items() if p not in stale
            }

        if stale:
            logger.info(f"Cleaned up {len(stale)} stale pane(s)")
            self.save()

    # --- Persistence ---

    def load(self) -> None:
        """Load state from disk using EAFP pattern."""
        try:
            with open(self._state_path, "r") as f:
                data = json.load(f)

            self.state.window_states = {
                k: PaneState(**v) for k, v in data.get("window_states", {}).items()
            }
            self.state.thread_bindings = data.get("thread_bindings", {})
            self.state.user_pane_offsets = data.get("user_pane_offsets", {})
        except (json.JSONDecodeError, OSError, TypeError) as e:
            logger.warning(f"Failed to load state: {e}")

    def save(self) -> None:
        """Save state to disk atomically."""
        data = {
            "window_states": {k: asdict(v) for k, v in self.state.window_states.items()},
            "thread_bindings": self.state.thread_bindings,
            "user_pane_offsets": self.state.user_pane_offsets,
        }
        atomic_write_json(self._state_path, data, prefix=".session_state.")

    # --- Private helpers ---

    def _resolve_session_file_path(self, session_id: str) -> Path:
        """Find JSONL file for session_id with LRU-cached bounds."""
        # Check cache first
        if session_id in self._session_file_cache:
            cached = self._session_file_cache[session_id]
            if cached.exists():
                # Move to end (most recently used)
                self._session_file_cache.move_to_end(session_id)
                return cached

        # Scan for file
        projects_path = get_claude_projects_path()
        for project_dir in projects_path.iterdir():
            if not project_dir.is_dir():
                continue
            for file in project_dir.glob("*.jsonl"):
                if session_id in file.name:
                    self._session_file_cache[session_id] = file
                    # Enforce cache bound
                    if len(self._session_file_cache) > MAX_SESSION_CACHE_SIZE:
                        self._session_file_cache.popitem(last=False)
                    return file
        return Path("")

    def _derive_session_metadata(self, file_path: Path) -> tuple[str, int]:
        """Derive summary and message_count from JSONL file with mtime-based caching."""
        if not file_path.exists():
            return "Untitled", 0

        # Check cache with mtime invalidation
        cache_key = str(file_path)
        mtime = 0.0
        try:
            mtime = file_path.stat().st_mtime
            if cache_key in self._metadata_cache:
                cached_mtime, summary, count = self._metadata_cache[cache_key]
                if cached_mtime == mtime:
                    return summary, count
        except OSError:
            pass

        # Parse file
        summary = "Untitled"
        message_count = 0

        try:
            with open(file_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "summary":
                            summary = entry.get("summary", summary)[:50]
                        if entry.get("type") in ("user", "assistant"):
                            message_count += 1
                    except json.JSONDecodeError:
                        continue
        except OSError:
            pass

        # Update cache with bounds enforcement
        if mtime > 0:
            self._metadata_cache[cache_key] = (mtime, summary, message_count)
            # Enforce cache bound
            if len(self._metadata_cache) > MAX_METADATA_CACHE_SIZE:
                self._metadata_cache.popitem(last=False)

        return summary, message_count
