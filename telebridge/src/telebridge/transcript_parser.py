"""Claude Code transcript parser.

Parses Claude Code session JSONL files and extracts structured messages.
Handles: text, thinking, tool_use, tool_result, and user messages.

Tool pairing: tool_use blocks in assistant messages are matched with
tool_result blocks in subsequent user messages via tool_use_id.

Shared by both session history and real-time monitoring.
"""

import base64
import difflib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Sentinel markers for expandable quotes
EXPANDABLE_QUOTE_START = "\x02EXPQUOTE_START\x02"
EXPANDABLE_QUOTE_END = "\x02EXPQUOTE_END\x02"

# Constants
_MAX_SUMMARY_LENGTH = 200
_NO_CONTENT_PLACEHOLDER = "(no content)"
_INTERRUPTED_TEXT = "[Request interrupted by user for tool use]"

# Regex patterns
_RE_COMMAND_NAME = re.compile(r"<command-name>(.*?)</command-name>")
_RE_LOCAL_STDOUT = re.compile(
    r"<local-command-stdout>(.*?)</local-command-stdout>", re.DOTALL
)
_RE_SYSTEM_TAGS = re.compile(
    r"<(bash-input|bash-stdout|bash-stderr|local-command-caveat|system-reminder)>"
)


@dataclass
class PendingToolInfo:
    """Information about a pending tool_use waiting for its tool_result."""

    summary: str  # Formatted tool summary (e.g. "**Read**(file.py)")
    tool_name: str  # Tool name (e.g. "Read", "Edit")
    input_data: Any = None  # Tool input parameters (for Edit to generate diff)


@dataclass
class ParsedEntry:
    """A parsed entry ready for display or Telegram formatting.

    Attributes:
        role: Message role - "user" | "assistant"
        text: Formatted display text (may contain expandable quote markers)
        content_type: Type of content - "text" | "thinking" | "tool_use" | "tool_result"
        tool_use_id: ID for pairing tool_use with tool_result
        timestamp: ISO timestamp from JSONL entry
        tool_name: Tool name for tool_use entries
        image_data: List of (media_type, raw_bytes) for tool_result images
    """

    role: str
    text: str
    content_type: str
    tool_use_id: str | None = None
    timestamp: str | None = None
    tool_name: str | None = None
    image_data: list[tuple[str, bytes]] | None = None


class TranscriptParser:
    """Parser for Claude Code JSONL session files.

    Expected JSONL entry structure:
    - type: "user" | "assistant" | "summary" | "file-history-snapshot" | ...
    - message.content: list of blocks (text, tool_use, tool_result, thinking)
    - sessionId, cwd, timestamp, uuid: metadata fields

    Tool pairing model: tool_use blocks appear in assistant messages,
    matching tool_result blocks appear in the next user message (keyed by tool_use_id).

    Usage:
        entries = [json.loads(line) for line in jsonl_lines]
        parsed, pending = TranscriptParser.parse_entries(entries)
    """

    @staticmethod
    def parse_line(line: str) -> dict | None:
        """Parse a single JSONL line.

        Args:
            line: A single line from the JSONL file

        Returns:
            Parsed dict or None if line is empty/invalid
        """
        line = line.strip()
        if not line:
            return None

        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _format_expandable_quote(text: str) -> str:
        """Format text as a Telegram expandable blockquote.

        Wraps text with sentinel markers. The actual MarkdownV2 formatting
        (> prefix, || suffix, escaping) is done downstream after
        telegramify processes the surrounding content.

        Args:
            text: Content to wrap

        Returns:
            Text wrapped with sentinel markers
        """
        return f"{EXPANDABLE_QUOTE_START}{text}{EXPANDABLE_QUOTE_END}"

    @classmethod
    def _format_edit_diff(cls, old_string: str, new_string: str) -> str:
        """Generate a compact unified diff between old_string and new_string.

        Args:
            old_string: Original content
            new_string: New content

        Returns:
            Unified diff string without header lines
        """
        old_lines = old_string.splitlines(keepends=True)
        new_lines = new_string.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, lineterm="")

        # Skip the --- / +++ header lines
        result_lines: list[str] = []
        for line in diff:
            if line.startswith("---") or line.startswith("+++"):
                continue
            # Strip trailing newline for clean display
            result_lines.append(line.rstrip("\n"))
        return "\n".join(result_lines)

    @classmethod
    def format_tool_use_summary(cls, name: str, input_data: dict | Any) -> str:
        """Format a tool_use block into a brief summary line.

        Args:
            name: Tool name (e.g. "Read", "Write", "Bash")
            input_data: The tool input dict

        Returns:
            Formatted string like "**Read**(file.py)"
        """
        if not isinstance(input_data, dict):
            return f"**{name}**"

        # Pick a meaningful short summary based on tool name
        summary = ""
        if name in ("Read", "Glob"):
            summary = input_data.get("file_path") or input_data.get("pattern", "")
        elif name == "Write":
            summary = input_data.get("file_path", "")
        elif name in ("Edit", "NotebookEdit"):
            summary = input_data.get("file_path") or input_data.get("notebook_path", "")
        elif name == "Bash":
            summary = input_data.get("command", "")
        elif name == "Grep":
            summary = input_data.get("pattern", "")
        elif name == "Task":
            summary = input_data.get("description", "")
        elif name == "WebFetch":
            summary = input_data.get("url", "")
        elif name == "WebSearch":
            summary = input_data.get("query", "")
        elif name == "TodoWrite":
            todos = input_data.get("todos", [])
            if isinstance(todos, list):
                summary = f"{len(todos)} item(s)"
        elif name == "AskUserQuestion":
            questions = input_data.get("questions", [])
            if isinstance(questions, list) and questions:
                q = questions[0]
                if isinstance(q, dict):
                    summary = q.get("question", "")
        elif name == "Skill":
            summary = input_data.get("skill", "")
        else:
            # Generic: show first string value
            for v in input_data.values():
                if isinstance(v, str) and v:
                    summary = v
                    break

        if summary:
            if len(summary) > _MAX_SUMMARY_LENGTH:
                summary = summary[:_MAX_SUMMARY_LENGTH] + "…"
            return f"**{name}**({summary})"
        return f"**{name}**"

    @staticmethod
    def extract_tool_result_text(content: list | Any) -> str:
        """Extract text from a tool_result content block.

        Args:
            content: tool_result content (string or list of dicts)

        Returns:
            Extracted text content
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    t = item.get("text", "")
                    if t:
                        parts.append(t)
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        return ""

    @staticmethod
    def extract_tool_result_images(
        content: list | Any,
    ) -> list[tuple[str, bytes]] | None:
        """Extract base64-encoded images from a tool_result content block.

        Args:
            content: tool_result content list

        Returns:
            List of (media_type, raw_bytes) tuples, or None if no images found
        """
        if not isinstance(content, list):
            return None
        images: list[tuple[str, bytes]] = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image":
                continue
            source = item.get("source")
            if not isinstance(source, dict) or source.get("type") != "base64":
                continue
            media_type = source.get("media_type", "image/png")
            data_str = source.get("data", "")
            if not data_str:
                continue
            try:
                raw_bytes = base64.b64decode(data_str)
                images.append((media_type, raw_bytes))
            except Exception:
                logger.debug("Failed to decode base64 image in tool_result")
        return images if images else None

    @staticmethod
    def _count_nonempty_lines(text: str) -> int:
        """Count non-empty lines in text.

        Helper to avoid repeated split() operations.
        """
        return len([line for line in text.split("\n") if line.strip()])

    @classmethod
    def _format_tool_result_text(
        cls, text: str, tool_name: str | None = None
    ) -> str:
        """Format tool result text with statistics summary.

        Shows relevant statistics for each tool type, with expandable
        quote for full content. No truncation here — per project principles,
        truncation is handled only at the send layer.

        Args:
            text: Tool result text
            tool_name: Name of the tool for formatting

        Returns:
            Formatted string with stats and expandable content
        """
        if not text:
            return ""

        line_count = text.count("\n") + 1 if text else 0

        # Tool-specific statistics
        if tool_name == "Read":
            return f"  ⎿  Read {line_count} lines"

        elif tool_name == "Write":
            return f"  ⎿  Wrote {line_count} lines"

        elif tool_name == "Bash":
            if line_count > 0:
                stats = f"  ⎿  Output {line_count} lines"
                return stats + "\n" + cls._format_expandable_quote(text)
            return cls._format_expandable_quote(text)

        elif tool_name == "Grep":
            matches = cls._count_nonempty_lines(text)
            stats = f"  ⎿  Found {matches} matches"
            return stats + "\n" + cls._format_expandable_quote(text)

        elif tool_name == "Glob":
            files = cls._count_nonempty_lines(text)
            stats = f"  ⎿  Found {files} files"
            return stats + "\n" + cls._format_expandable_quote(text)

        elif tool_name == "Task":
            if line_count > 0:
                stats = f"  ⎿  Agent output {line_count} lines"
                return stats + "\n" + cls._format_expandable_quote(text)
            return cls._format_expandable_quote(text)

        elif tool_name == "WebFetch":
            char_count = len(text)
            stats = f"  ⎿  Fetched {char_count} characters"
            return stats + "\n" + cls._format_expandable_quote(text)

        elif tool_name == "WebSearch":
            results = text.count("\n\n") + 1 if text else 0
            stats = f"  ⎿  {results} search results"
            return stats + "\n" + cls._format_expandable_quote(text)

        # Default: expandable quote without stats
        return cls._format_expandable_quote(text)

    @classmethod
    def _format_thinking_content(cls, text: str, max_length: int) -> str:
        """Format thinking content with truncation.

        Args:
            text: Thinking content
            max_length: Maximum length before truncation

        Returns:
            Formatted thinking text, possibly truncated
        """
        if not text:
            return "(thinking)"

        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length] + "…"
            return cls._format_expandable_quote(text)
        return cls._format_expandable_quote(text)

    @classmethod
    def parse_entries(
        cls,
        entries: list[dict],
        pending_tools: dict[str, PendingToolInfo] | None = None,
        thinking_max_length: int = 500,
    ) -> tuple[list[ParsedEntry], dict[str, PendingToolInfo]]:
        """Parse a list of JSONL entries into display-ready messages.

        This is the main entry point for parsing. Handles tool pairing
        across message boundaries and formats all content types.

        Args:
            entries: List of parsed JSONL dicts
            pending_tools: Optional carry-over pending tool_use state from
                a previous call (tool_use_id -> PendingToolInfo). Used by
                the monitor to handle tool_use and tool_result arriving in
                separate poll cycles.
            thinking_max_length: Maximum length for thinking content

        Returns:
            Tuple of (parsed entries, remaining pending_tools state)
        """
        result: list[ParsedEntry] = []

        # Initialize pending_tools if None
        if pending_tools is None:
            pending_tools = {}

        for data in entries:
            msg_type = data.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            entry_timestamp = data.get("timestamp")
            message = data.get("message")
            if not isinstance(message, dict):
                continue

            content = message.get("content", "")
            if not isinstance(content, list):
                content = (
                    [{"type": "text", "text": str(content)}] if content else []
                )

            if msg_type == "assistant":
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")

                    if btype == "text":
                        t = block.get("text", "").strip()
                        if t and t != _NO_CONTENT_PLACEHOLDER:
                            result.append(
                                ParsedEntry(
                                    role="assistant",
                                    text=t,
                                    content_type="text",
                                    timestamp=entry_timestamp,
                                )
                            )

                    elif btype == "tool_use":
                        tool_id = block.get("id", "")
                        name = block.get("name", "unknown")
                        inp = block.get("input", {})
                        summary = cls.format_tool_use_summary(name, inp)

                        # ExitPlanMode: emit plan content as text before tool_use entry
                        if name == "ExitPlanMode" and isinstance(inp, dict):
                            plan = inp.get("plan", "")
                            if plan:
                                result.append(
                                    ParsedEntry(
                                        role="assistant",
                                        text=plan,
                                        content_type="text",
                                        timestamp=entry_timestamp,
                                    )
                                )

                        # Store tool info for later tool_result formatting
                        input_data = inp if name in ("Edit", "NotebookEdit") else None
                        if tool_id:
                            pending_tools[tool_id] = PendingToolInfo(
                                summary=summary,
                                tool_name=name,
                                input_data=input_data,
                            )

                        result.append(
                            ParsedEntry(
                                role="assistant",
                                text=summary,
                                content_type="tool_use",
                                tool_use_id=tool_id or None,
                                timestamp=entry_timestamp,
                                tool_name=name,
                            )
                        )

                    elif btype == "thinking":
                        thinking_text = block.get("thinking", "")
                        formatted = cls._format_thinking_content(
                            thinking_text, thinking_max_length
                        )
                        result.append(
                            ParsedEntry(
                                role="assistant",
                                text=formatted,
                                content_type="thinking",
                                timestamp=entry_timestamp,
                            )
                        )

            elif msg_type == "user":
                # Check for tool_result blocks and merge with pending tools
                user_text_parts: list[str] = []

                for block in content:
                    if not isinstance(block, dict):
                        if isinstance(block, str) and block.strip():
                            user_text_parts.append(block.strip())
                        continue

                    btype = block.get("type", "")

                    if btype == "tool_result":
                        tool_use_id = block.get("tool_use_id", "")
                        result_content = block.get("content", "")
                        result_text = cls.extract_tool_result_text(result_content)
                        result_images = cls.extract_tool_result_images(result_content)
                        is_error = block.get("is_error", False)
                        is_interrupted = result_text == _INTERRUPTED_TEXT

                        tool_info = pending_tools.pop(tool_use_id, None)
                        _tuid = tool_use_id or None

                        # Extract tool info from PendingToolInfo
                        if tool_info is None:
                            tool_summary = None
                            tool_name = None
                            tool_input_data = None
                        else:
                            tool_summary = tool_info.summary
                            tool_name = tool_info.tool_name
                            tool_input_data = tool_info.input_data

                        if is_interrupted:
                            entry_text = tool_summary or ""
                            if entry_text:
                                entry_text += "\n⏹ Interrupted"
                            else:
                                entry_text = "⏹ Interrupted"
                            result.append(
                                ParsedEntry(
                                    role="assistant",
                                    text=entry_text,
                                    content_type="tool_result",
                                    tool_use_id=_tuid,
                                    timestamp=entry_timestamp,
                                )
                            )
                        elif is_error:
                            if tool_summary:
                                entry_text = tool_summary
                            else:
                                entry_text = "**Error**"
                            if result_text:
                                error_summary = result_text.split("\n")[0]
                                if len(error_summary) > 100:
                                    error_summary = error_summary[:100] + "…"
                                entry_text += f"\n  ⎿  Error: {error_summary}"
                                if "\n" in result_text:
                                    entry_text += "\n" + cls._format_expandable_quote(
                                        result_text
                                    )
                            else:
                                entry_text += "\n  ⎿  Error"
                            result.append(
                                ParsedEntry(
                                    role="assistant",
                                    text=entry_text,
                                    content_type="tool_result",
                                    tool_use_id=_tuid,
                                    timestamp=entry_timestamp,
                                    image_data=result_images,
                                )
                            )
                        elif tool_summary:
                            entry_text = tool_summary

                            # For Edit tool, generate diff stats and expandable quote
                            if (
                                tool_name == "Edit"
                                and tool_input_data
                                and result_text
                            ):
                                old_s = tool_input_data.get("old_string", "")
                                new_s = tool_input_data.get("new_string", "")
                                if old_s and new_s:
                                    diff_text = cls._format_edit_diff(old_s, new_s)
                                    if diff_text:
                                        added = sum(
                                            1
                                            for line in diff_text.split("\n")
                                            if line.startswith("+")
                                            and not line.startswith("+++")
                                        )
                                        removed = sum(
                                            1
                                            for line in diff_text.split("\n")
                                            if line.startswith("-")
                                            and not line.startswith("---")
                                        )
                                        stats = (
                                            f"  ⎿  Added {added} lines, "
                                            f"removed {removed} lines"
                                        )
                                        entry_text += (
                                            "\n"
                                            + stats
                                            + "\n"
                                            + cls._format_expandable_quote(diff_text)
                                        )

                            # For other tools, append formatted result text
                            elif result_text and EXPANDABLE_QUOTE_START not in tool_summary:
                                entry_text += "\n" + cls._format_tool_result_text(
                                    result_text, tool_name
                                )

                            result.append(
                                ParsedEntry(
                                    role="assistant",
                                    text=entry_text,
                                    content_type="tool_result",
                                    tool_use_id=_tuid,
                                    timestamp=entry_timestamp,
                                    image_data=result_images,
                                )
                            )
                        elif result_text or result_images:
                            result.append(
                                ParsedEntry(
                                    role="assistant",
                                    text=cls._format_tool_result_text(result_text, tool_name)
                                    if result_text
                                    else (tool_summary or ""),
                                    content_type="tool_result",
                                    tool_use_id=_tuid,
                                    timestamp=entry_timestamp,
                                    image_data=result_images,
                                )
                            )

                    elif btype == "text":
                        t = block.get("text", "").strip()
                        if t and not _RE_SYSTEM_TAGS.search(t):
                            user_text_parts.append(t)

                # Add user text if present
                if user_text_parts:
                    combined = "\n".join(user_text_parts)
                    # Skip if it looks like local command XML
                    if not _RE_LOCAL_STDOUT.search(combined) and not _RE_COMMAND_NAME.search(
                        combined
                    ):
                        result.append(
                            ParsedEntry(
                                role="user",
                                text=combined.strip(),
                                content_type="text",
                                timestamp=entry_timestamp,
                            )
                        )

        return result, pending_tools
