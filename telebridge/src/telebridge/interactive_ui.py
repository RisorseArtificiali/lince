"""Interactive UI detection from terminal pane capture.

Detects Claude Code interactive prompts (permissions, multi-choice, model selection)
in terminal output and exposes them for rendering as Telegram inline keyboards.

Architecture:
    SessionMonitor (polling)
        → capture_pane_ansi()
        → InteractiveUIDetector.detect()
            → Pattern match for UI types
            → Extract options and selection
            → Return InteractiveUIState or None
        → If state changed → notify callback
"""

import hashlib
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class UIType(Enum):
    """Types of interactive UIs from Claude Code."""

    PERMISSION = "permission"  # "Allow X to Y?" Yes/No
    MULTI_CHOICE = "multi_choice"  # AskUserQuestion with numbered options
    PLAN_EXIT = "plan_exit"  # Plan mode exit confirmation
    CHECKPOINT = "checkpoint"  # Checkpoint restoration list
    MODEL_SELECT = "model_select"  # Model picker UI
    TOOL_PERMISSION = "tool_permission"  # "Allow tool_name?" approve/deny


# Detection patterns for Claude Code terminal UIs
# Each pattern is designed to match the visual output format including options
PATTERNS: dict[UIType, list[str]] = {
    UIType.PERMISSION: [
        # "Allow X to Y?" followed by Yes/No/Approve/Deny on same or next line
        r"(Allow\s+[^\n]+\?[\s\S]*?)(\b(?:Yes|No|Approve|Deny)\b[\s\S]*?)(\b(?:Yes|No|Approve|Deny)\b)",
        r"(Do you want\s+[^\n]+\?[\s\S]*?)(\bYes\b[\s\S]*?)(\bNo\b)",
        r"(Should I\s+[^\n]+\?[\s\S]*?)(\bYes\b[\s\S]*?)(\bNo\b)",
    ],
    UIType.MULTI_CHOICE: [
        # Numbered list with selection marker: "1. Option" or "1) Option"
        r"((?:^\s*[\d]+[).\]][\s*].+$\n?)+)",
        # Question followed by numbered options
        r"((?:Select|Choose|Pick|Which)[^\n]*:\s*\n(?:\s*[\d]+[).\]][\s]*.+\n?)+)",
    ],
    UIType.PLAN_EXIT: [
        r"(Exit plan mode[\s\S]*?)(\bProceed\b[\s\S]*?)(\bCancel\b)",
        r"(Ready to implement[\s\S]*?)(\bYes\b[\s\S]*?)(\bNo\b)",
        r"(Plan (?:review|complete)[\s\S]*?)(\bProceed\b[\s\S]*?)(\bCancel\b)",
    ],
    UIType.MODEL_SELECT: [
        r"((?:Select|Choose|Switch)\s+model[^:]*:\s*\n(?:\s*[-\w.]+\s*\n?)+)",
        r"(Available\s+models:\s*\n(?:\s*[-\w.]+\s*\n?)+)",
        r"((?:Current|Active)\s+model:[^\n]*\n(?:\s*[-\w.]+\s*\n?)+)",
    ],
    UIType.TOOL_PERMISSION: [
        r"(Allow\s+(?:tool|command|file|operation)[^\n]+\?[\s\S]*?)(\b(?:Approve|Deny|Yes|No)\b[\s\S]*?)(\b(?:Approve|Deny|Yes|No)\b)",
        r"(Permit\s+[^\n]+\?[\s\S]*?)(\b(?:Yes|No|Allow|Block)\b[\s\S]*?)(\b(?:Yes|No|Allow|Block)\b)",
    ],
    UIType.CHECKPOINT: [
        r"((?:Restore|Select)\s+checkpoint:\s*\n(?:\s*[-\w\d]+\s+[^\n]+\n?)+)",
        r"(Available\s+checkpoints:\s*\n(?:\s*[-\w\d]+\s+[^\n]+\n?)+)",
    ],
}

# Cache configuration for InteractiveUIManager
CACHE_MAX_SIZE = 100  # Maximum cached prompts
CACHE_TTL_SECONDS = 1800.0  # 30 minutes TTL

# Pre-compiled ANSI escape pattern for efficiency
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


@dataclass
class InteractiveUIState:
    """Detected interactive UI state from pane capture.

    Attributes:
        ui_type: Type of interactive UI detected
        content: Extracted display text for rendering
        options: Available choices (button labels)
        current_selection: Currently highlighted option index (0-based)
        raw_text: Full pane capture for debugging
        prompt_id: Unique identifier for this prompt (for callback tracking)
    """

    ui_type: UIType
    content: str
    options: list[str] = field(default_factory=list)
    current_selection: int = 0
    raw_text: str = ""
    prompt_id: str = ""

    def __post_init__(self) -> None:
        """Generate prompt_id and clean content if not provided."""
        # Clean ANSI codes from content
        if self.content and "\x1B" in self.content:
            self.content = _ANSI_ESCAPE_PATTERN.sub("", self.content)

        if not self.prompt_id and self.content:
            self.prompt_id = self._generate_prompt_id(self.content)

    @staticmethod
    def _generate_prompt_id(text: str) -> str:
        """Generate unique ID for this prompt using content hash."""
        return hashlib.md5(text.encode()).hexdigest()[:12]


@dataclass
class _CacheEntry:
    """Wrapper for cached state with TTL tracking.

    LRU eviction is handled by OrderedDict order (front = oldest).

    Attributes:
        state: The cached InteractiveUIState
        created_at: Timestamp when entry was created (for TTL)
    """

    state: InteractiveUIState
    created_at: float


class InteractiveUIDetector:
    """Detects interactive UIs in terminal pane captures.

    Usage:
        detector = InteractiveUIDetector()
        state = detector.detect(pane_content)
        if state:
            # Render as inline keyboard
    """

    def __init__(self) -> None:
        self._compiled_patterns: dict[UIType, list[re.Pattern]] = {}
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        for ui_type, patterns in PATTERNS.items():
            self._compiled_patterns[ui_type] = [
                re.compile(p, re.MULTILINE | re.IGNORECASE) for p in patterns
            ]

    def detect(self, pane_content: str) -> InteractiveUIState | None:
        """Detect interactive UI in pane content.

        Args:
            pane_content: Raw terminal content from capture_pane_ansi()

        Returns:
            InteractiveUIState if UI detected, None otherwise
        """
        if not pane_content or len(pane_content) < 10:
            return None

        # Try each UI type in priority order (most specific first)
        for ui_type in [
            UIType.TOOL_PERMISSION,  # Most specific
            UIType.PERMISSION,
            UIType.PLAN_EXIT,
            UIType.MULTI_CHOICE,
            UIType.MODEL_SELECT,
            UIType.CHECKPOINT,
        ]:
            state = self._try_detect_type(ui_type, pane_content)
            if state:
                return state

        return None

    def _try_detect_type(
        self, ui_type: UIType, content: str
    ) -> InteractiveUIState | None:
        """Try to detect a specific UI type.

        Args:
            ui_type: UI type to detect
            content: Pane content to analyze

        Returns:
            InteractiveUIState if detected, None otherwise
        """
        patterns = self._compiled_patterns.get(ui_type, [])

        for pattern in patterns:
            match = pattern.search(content)
            if match:
                return self._extract_state(ui_type, content, match)

        return None

    def _extract_state(
        self, ui_type: UIType, content: str, match: re.Match
    ) -> InteractiveUIState:
        """Extract InteractiveUIState from matched content.

        Args:
            ui_type: Detected UI type
            content: Full pane content
            match: Regex match object

        Returns:
            Populated InteractiveUIState
        """
        # Combine all capture groups for full content
        # Group 0 is the full match, groups 1+ are captures
        groups = [match.group(0)]
        if match.lastindex:
            groups = [match.group(i) for i in range(1, match.lastindex + 1) if match.group(i)]

        # Join groups for display content
        matched_text = " ".join(groups) if groups else match.group(0)

        # Extract options using the full pane content for better context
        options = self._extract_options(ui_type, content)

        # Generate prompt ID from content hash
        prompt_id = InteractiveUIState._generate_prompt_id(matched_text)

        # Clean content for display
        clean_content = self._clean_content(matched_text)

        return InteractiveUIState(
            ui_type=ui_type,
            content=clean_content,
            options=options,
            current_selection=0,
            raw_text=content,
            prompt_id=prompt_id,
        )

    def _extract_options(self, ui_type: UIType, text: str) -> list[str]:
        """Extract available options from UI text.

        Args:
            ui_type: UI type
            text: Matched text

        Returns:
            List of option labels
        """
        if ui_type in (UIType.PERMISSION, UIType.TOOL_PERMISSION):
            # Look for Yes/No, Approve/Deny patterns
            options = []
            if re.search(r"\bYes\b", text, re.IGNORECASE):
                options.append("Yes")
            if re.search(r"\bNo\b", text, re.IGNORECASE):
                options.append("No")
            if re.search(r"\bApprove\b", text, re.IGNORECASE):
                options.append("Approve")
            if re.search(r"\bDeny\b", text, re.IGNORECASE):
                options.append("Deny")
            if re.search(r"\bAllow\b", text, re.IGNORECASE) and "Allow" not in options:
                options.append("Allow")
            if re.search(r"\bBlock\b", text, re.IGNORECASE):
                options.append("Block")
            return options or ["Yes", "No"]

        elif ui_type == UIType.MULTI_CHOICE:
            # Extract numbered options: "1. Option text" or "1) Option text"
            options = []
            for line in text.split("\n"):
                # Match "1. Option", "1) Option", "1] Option"
                match = re.match(r"\s*(\d+)[).\]]\s*(.+)", line)
                if match:
                    options.append(match.group(2).strip())
            return options

        elif ui_type == UIType.MODEL_SELECT:
            # Extract model names (e.g., claude-3-5-sonnet, claude-opus-4)
            options = []
            for line in text.split("\n"):
                stripped = line.strip()
                # Match model names like "claude-3-5-sonnet", "claude-3-7", "claude-opus-4"
                match = re.match(r"^([-\w]+(?:\.\d+)?)\s*$", stripped)
                if match and "claude" in match.group(1).lower():
                    options.append(match.group(1))
            return options

        elif ui_type == UIType.PLAN_EXIT:
            # Standard plan exit options
            if "proceed" in text.lower():
                return ["Proceed", "Cancel"]
            return ["Yes", "No"]

        elif ui_type == UIType.CHECKPOINT:
            # Extract checkpoint IDs
            options = []
            for line in text.split("\n"):
                match = re.match(r"\s*([-\w\d]+)\s+", line)
                if match:
                    options.append(match.group(1))
            return options

        return []

    def _clean_content(self, text: str) -> str:
        """Clean extracted content for display.

        - Remove excessive whitespace
        - Strip ANSI codes (already done by capture_pane, but be safe)
        - Truncate to reasonable length
        """
        # Remove ANSI escape sequences using pre-compiled pattern
        text = _ANSI_ESCAPE_PATTERN.sub("", text)

        # Normalize whitespace
        text = text.strip()

        # Truncate if too long (preserve readability)
        if len(text) > 1000:
            text = text[:1000] + "..."

        return text


class InteractiveUIManager:
    """Manages interactive UI state with change detection and bounded cache.

    Prevents duplicate notifications for the same UI prompt.
    Designed to be integrated with SessionMonitor polling loop.

    Cache Management:
        - LRU eviction when cache exceeds max_size
        - TTL-based cleanup for stale entries
    """

    def __init__(
        self,
        detector: InteractiveUIDetector | None = None,
        max_size: int = CACHE_MAX_SIZE,
        ttl_seconds: float = CACHE_TTL_SECONDS,
    ) -> None:
        self._detector = detector or InteractiveUIDetector()
        self._last_state: dict[str, str] = {}  # pane_key -> prompt_id
        self._state_cache: OrderedDict[str, _CacheEntry] = OrderedDict()  # prompt_id -> cache entry (ordered by access)
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def check_for_ui(
        self, pane_key: str, pane_content: str
    ) -> InteractiveUIState | None:
        """Check pane content for interactive UI with change detection.

        Args:
            pane_key: Pane identifier (e.g., "tmux:session:window:pane")
            pane_content: Captured terminal content

        Returns:
            InteractiveUIState if new/different UI detected, None otherwise
        """
        state = self._detector.detect(pane_content)

        if state is None:
            # No UI detected - clear previous state for this pane
            self._last_state.pop(pane_key, None)
            return None

        # Check if this is a new or changed UI
        last_prompt_id = self._last_state.get(pane_key)

        if last_prompt_id == state.prompt_id:
            # Same UI as before - no change
            return None

        # New or changed UI - run cleanup before adding
        self._cleanup_if_needed()

        now = time.time()
        self._last_state[pane_key] = state.prompt_id
        self._state_cache[state.prompt_id] = _CacheEntry(
            state=state,
            created_at=now,
        )

        logger.debug(
            f"Detected new {state.ui_type.value} UI for pane {pane_key}: "
            f"{len(state.options)} options"
        )

        return state

    def clear_state(self, pane_key: str) -> None:
        """Clear UI state for a pane (e.g., after user responds).

        Args:
            pane_key: Pane to clear state for
        """
        self._last_state.pop(pane_key, None)

    def get_cached_state(self, prompt_id: str) -> InteractiveUIState | None:
        """Retrieve cached state by prompt ID with LRU tracking.

        Moves entry to end of OrderedDict for O(1) LRU eviction ordering.

        Args:
            prompt_id: Prompt identifier

        Returns:
            Cached InteractiveUIState or None
        """
        entry = self._state_cache.get(prompt_id)
        if entry:
            self._state_cache.move_to_end(prompt_id)  # O(1) LRU tracking
            return entry.state
        return None

    def _cleanup_if_needed(self) -> None:
        """Remove stale entries and enforce max size.

        Called before adding new entries to the cache.

        Cleanup strategy:
            1. TTL-based: Remove entries older than _ttl_seconds
            2. LRU eviction: Remove least recently accessed (front of OrderedDict)
        """
        now = time.time()

        # 1. Remove expired entries (TTL) - O(n) scan
        expired = [
            pid
            for pid, entry in self._state_cache.items()
            if now - entry.created_at > self._ttl_seconds
        ]
        for pid in expired:
            del self._state_cache[pid]

        # 2. Enforce max size (LRU eviction) - O(1) with OrderedDict
        while len(self._state_cache) >= self._max_size:
            self._state_cache.popitem(last=False)  # Remove oldest (front)

    def clear_all(self) -> None:
        """Clear all cached state (e.g., on session end)."""
        self._last_state.clear()
        self._state_cache.clear()
