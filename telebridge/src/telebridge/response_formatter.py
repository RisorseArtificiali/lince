"""Markdown to Telegram MarkdownV2 formatter.

This module provides the second layer of the telebridge pipeline:
converting parsed transcript entries into Telegram-ready messages.

Pipeline: ParsedEntry → format_entries → to_telegram_markdown → split_message

Key features:
- Converts ParsedEntry objects to formatted markdown text
- Applies Telegram MarkdownV2 escaping via telegramify-markdown
- Handles expandable blockquotes with sentinel markers
- Splits messages at 4096-char boundaries with code block preservation
"""

import logging
import re
import textwrap
from dataclasses import dataclass, field

from telegramify_markdown import markdownify

from telebridge.transcript_parser import (
    EXPANDABLE_QUOTE_END,
    EXPANDABLE_QUOTE_START,
    ParsedEntry,
)

logger = logging.getLogger(__name__)

# Telegram message size limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# User message truncation limit
MAX_USER_MESSAGE_LENGTH = 3000

# Maximum length for pagination marker "[1/999] "
MAX_PAGINATION_MARKER_LENGTH = 8

# Length for closing/reopening code blocks "```\n```"
CODE_BLOCK_DELIMITER_LENGTH = 8

# Cached regex pattern for sentinel markers (compiled once at module load)
_SENTINEL_PATTERN = re.compile(
    re.escape(EXPANDABLE_QUOTE_START) + r"(.*?)" + re.escape(EXPANDABLE_QUOTE_END),
    re.DOTALL,
)

__all__ = [
    "format_entries",
    "to_telegram_markdown",
    "split_message",
    "strip_sentinels",
]


def format_entries(entries: list[ParsedEntry]) -> str:
    """Format a list of parsed entries into markdown text.

    Layer 1: Converts ParsedEntry objects to display-ready markdown.

    Entry handling:
    - user text: Prefix with 👤, truncate at 3000 chars
    - assistant text: Pass through unchanged
    - assistant thinking: Prefix with ∴ Thinking…
    - tool_use/result: Use entry.text (already formatted by parser)

    Args:
        entries: List of ParsedEntry objects from TranscriptParser

    Returns:
        Formatted markdown text ready for Telegram conversion
    """
    parts: list[str] = []

    for entry in entries:
        text = entry.text
        if not text:
            continue

        if entry.role == "user" and entry.content_type == "text":
            # User message: prefix with 👤 and truncate
            if len(text) > MAX_USER_MESSAGE_LENGTH:
                text = text[:MAX_USER_MESSAGE_LENGTH] + "…"
            parts.append(f"👤 {text}")
        elif entry.role == "assistant":
            if entry.content_type == "thinking":
                # Thinking: prefix with indicator
                parts.append(f"∴ Thinking…\n{text}")
            else:
                # Text, tool_use, tool_result: use as-is
                parts.append(text)
        # Skip unknown role/content_type combinations

    return "\n\n".join(parts)


# Placeholder format that won't be modified by markdownify
# Using uppercase letters and digits only (no special chars that get escaped)
_PLACEHOLDER_PREFIX = "BLOCKQUOTE"
_PLACEHOLDER_SUFFIX = "END"


def _extract_sentinels(text: str) -> tuple[str, dict[str, str]]:
    """Extract sentinel-marked content and replace with placeholders.

    Args:
        text: Text containing EXPANDABLE_QUOTE_START/END markers

    Returns:
        Tuple of (text with placeholders, dict of placeholder -> content)
    """
    placeholders: dict[str, str] = {}
    counter = 0

    def replace_sentinel(match: re.Match) -> str:
        nonlocal counter
        content = match.group(1)
        # Use a format that won't be modified by markdownify
        placeholder = f"{_PLACEHOLDER_PREFIX}{counter}{_PLACEHOLDER_SUFFIX}"
        placeholders[placeholder] = content
        counter += 1
        return placeholder

    # Use cached pattern compiled at module level
    result = _SENTINEL_PATTERN.sub(replace_sentinel, text)
    return result, placeholders


def _convert_tables_to_cards(text: str) -> str:
    """Convert markdown tables to card format (Key: Value).

    Telegram MarkdownV2 doesn't support tables well, so we convert
    them to a simple key-value format that's more readable.

    Args:
        text: Markdown text possibly containing tables

    Returns:
        Text with tables converted to card format
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    in_table = False
    table_lines: list[str] = []

    for line in lines:
        # Detect table rows
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(line)
        else:
            if in_table:
                # End of table, convert it
                cards = _table_to_cards(table_lines)
                result_lines.extend(cards)
                in_table = False
                table_lines = []
            result_lines.append(line)

    # Handle table at end of text
    if in_table:
        cards = _table_to_cards(table_lines)
        result_lines.extend(cards)

    return "\n".join(result_lines)


def _table_to_cards(table_lines: list[str]) -> list[str]:
    """Convert a markdown table to card format.

    Args:
        table_lines: Lines of a markdown table

    Returns:
        Lines in card format (Key: Value)
    """
    if len(table_lines) < 2:
        return table_lines

    # Parse header
    header_line = table_lines[0].strip()
    headers = [cell.strip() for cell in header_line.split("|")[1:-1]]

    # Skip separator line (index 1)
    cards: list[str] = []
    for row_line in table_lines[2:]:
        row_line = row_line.strip()
        if not row_line:
            continue
        cells = [cell.strip() for cell in row_line.split("|")[1:-1]]
        for i, cell in enumerate(cells):
            if i < len(headers) and cell:
                cards.append(f"**{headers[i]}**: {cell}")
        cards.append("")  # Empty line between rows

    return cards


def _restore_blockquotes(text: str, placeholders: dict[str, str]) -> str:
    """Restore placeholders as Telegram blockquotes.

    Telegram expandable blockquote syntax: **>content||
    - **> starts the expandable blockquote
    - || ends it

    Args:
        text: Text with placeholders
        placeholders: Dict of placeholder -> original content

    Returns:
        Text with placeholders replaced by blockquote syntax
    """
    for placeholder, content in placeholders.items():
        # Escape special characters for MarkdownV2 within blockquote
        escaped_content = _escape_blockquote_content(content)
        blockquote = f"**>{escaped_content}||"
        text = text.replace(placeholder, blockquote)
    return text


def _escape_blockquote_content(content: str) -> str:
    """Escape content for use inside Telegram blockquotes.

    Only escape characters that would break the blockquote syntax.

    Args:
        content: Raw content

    Returns:
        Content with minimal escaping
    """
    # Inside blockquotes, we mainly need to escape || to prevent early termination
    return content.replace("||", "\\|\\|")


def to_telegram_markdown(text: str) -> str:
    """Convert markdown text to Telegram MarkdownV2 format.

    Layer 2: Applies Telegram MarkdownV2 escaping and formatting.

    Pipeline:
    1. Extract sentinel-marked content → placeholders
    2. Convert markdown tables to card format
    3. Apply telegramify_markdown.markdownify()
    4. Restore placeholders as Telegram blockquotes

    Args:
        text: Markdown text (possibly with sentinel markers)

    Returns:
        Telegram MarkdownV2 formatted text
    """
    # Step 1: Extract sentinels to protect them from markdownify
    text, placeholders = _extract_sentinels(text)

    # Step 2: Convert tables to card format
    text = _convert_tables_to_cards(text)

    # Step 3: Apply telegramify-markdown for MarkdownV2 conversion
    try:
        text = markdownify(text)
    except Exception as e:
        logger.warning(f"markdownify failed, using fallback: {e}")
        # Fallback: just escape special characters
        text = _fallback_escape(text)

    # Step 4: Restore blockquotes
    text = _restore_blockquotes(text, placeholders)

    return text


# Characters that need escaping in Telegram MarkdownV2
_MARKDOWNV2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def _fallback_escape(text: str) -> str:
    """Fallback MarkdownV2 escaping when telegramify fails.

    Escapes special characters according to Telegram MarkdownV2 spec.
    """
    for char in _MARKDOWNV2_SPECIAL_CHARS:
        text = text.replace(char, f"\\{char}")
    return text


@dataclass
class _SplitState:
    """State tracker for message splitting."""

    in_code_block: bool = False
    code_lang: str = ""
    chunks: list[str] = field(default_factory=list)
    current: list[str] = field(default_factory=list)
    current_len: int = 0  # Tracked incrementally for O(1) access


def split_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks that fit within Telegram's message limit.

    Layer 3: Handles message size limits with code block preservation.

    Algorithm:
    1. Process line by line
    2. Track code block state (close/reopen at split boundaries)
    3. Force-split long lines at word boundaries
    4. Add [1/N] pagination markers for multi-part messages

    Note: Reserves space for pagination markers and code block delimiters
    to ensure final chunks don't exceed max_length.

    Args:
        text: Text to split
        max_length: Maximum length per chunk (default: 4096)

    Returns:
        List of text chunks, each <= max_length
    """
    if len(text) <= max_length:
        return [text]

    state = _SplitState()
    lines = text.split("\n")

    # Reserve space for pagination and code blocks
    effective_max = max_length - MAX_PAGINATION_MARKER_LENGTH - CODE_BLOCK_DELIMITER_LENGTH

    for line in lines:
        _process_line_for_split(state, line, effective_max)

    # Flush remaining content
    if state.current:
        _finalize_chunk(state)

    # Add pagination markers if multiple chunks
    if len(state.chunks) > 1:
        state.chunks = _add_pagination_markers(state.chunks, max_length)

    return state.chunks if state.chunks else [""]


def _process_line_for_split(state: _SplitState, line: str, max_length: int) -> None:
    """Process a single line for splitting.

    Args:
        state: Current split state
        line: Line to process
        max_length: Maximum chunk length
    """
    # Check for code block markers
    stripped = line.strip()
    if stripped.startswith("```"):
        if state.in_code_block:
            # Closing code block
            state.in_code_block = False
            state.code_lang = ""
        else:
            # Opening code block
            state.in_code_block = True
            state.code_lang = stripped[3:].strip()

    # Calculate line length with newline
    line_with_newline = line + "\n"
    line_len = len(line_with_newline)

    # Check if adding this line would exceed limit (O(1) using tracked length)
    if state.current_len + line_len > max_length:
        # Need to split
        if state.current:
            # Finalize current chunk
            _finalize_chunk(state)

        # Handle very long lines that exceed limit on their own
        if line_len > max_length:
            _split_long_line(state, line, max_length)
        else:
            state.current.append(line)
            state.current_len = line_len
    else:
        state.current.append(line)
        state.current_len += line_len


def _split_long_line(state: _SplitState, line: str, max_length: int) -> None:
    """Split a single long line at word boundaries using textwrap.

    Args:
        state: Current split state
        line: Line to split
        max_length: Maximum chunk length
    """
    # Use textwrap for robust word boundary handling
    # drop_whitespace=False preserves leading/trailing whitespace
    wrapped = textwrap.wrap(
        line,
        width=max_length,
        break_long_words=True,
        break_on_hyphens=True,
        drop_whitespace=False,
    )

    for segment in wrapped:
        seg_len = len(segment) + 1  # +1 for newline

        if seg_len > max_length:
            # Still too long (edge case), force split character by character
            for i in range(0, len(segment), max_length - 1):
                chunk = segment[i : i + max_length - 1]
                state.current.append(chunk)
                state.current_len = len(chunk)
                _finalize_chunk(state)
        elif state.current_len + seg_len > max_length:
            # Adding this segment would exceed limit, finalize first
            if state.current:
                _finalize_chunk(state)
            state.current.append(segment)
            state.current_len = seg_len
        else:
            state.current.append(segment)
            state.current_len += seg_len


def _finalize_chunk(state: _SplitState) -> None:
    """Finalize the current chunk and add to chunks list.

    Handles code block closure and reopening across chunk boundaries.

    Args:
        state: Current split state
    """
    if not state.current:
        return

    chunk_text = "\n".join(state.current)

    # Close code block if we're in one
    if state.in_code_block:
        chunk_text += "\n```"

    state.chunks.append(chunk_text)

    # Start new chunk with reopened code block if needed
    state.current = []
    state.current_len = 0
    if state.in_code_block:
        # Reopen code block in new chunk
        if state.code_lang:
            reopen = f"```{state.code_lang}"
        else:
            reopen = "```"
        state.current.append(reopen)
        state.current_len = len(reopen) + 1  # +1 for newline


def _add_pagination_markers(chunks: list[str], max_length: int) -> list[str]:
    """Add [1/N] pagination markers to chunks.

    Args:
        chunks: List of text chunks
        max_length: Maximum allowed length per chunk

    Returns:
        Chunks with pagination markers prepended, each <= max_length
    """
    total = len(chunks)
    result: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        marker = f"[{i}/{total}] "
        marked_chunk = marker + chunk

        # Safety check: if chunk still exceeds limit, truncate
        if len(marked_chunk) > max_length:
            # Truncate to fit, leaving room for ellipsis
            available = max_length - len(marker) - 1
            marked_chunk = marker + chunk[:available] + "…"

        result.append(marked_chunk)

    return result


def strip_sentinels(text: str) -> str:
    """Remove sentinel markers from text (fallback helper).

    Use this when you want to display text without the expandable
    blockquote formatting, or when Telegram formatting fails.

    Args:
        text: Text possibly containing sentinel markers

    Returns:
        Text with sentinel markers removed (content preserved)
    """
    # Use cached pattern compiled at module level
    return _SENTINEL_PATTERN.sub(r"\1", text)
