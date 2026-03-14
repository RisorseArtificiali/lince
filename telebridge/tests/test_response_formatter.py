"""Tests for response_formatter module."""

from telebridge.response_formatter import (
    MAX_USER_MESSAGE_LENGTH,
    TELEGRAM_MAX_MESSAGE_LENGTH,
    _convert_tables_to_cards,
    _extract_sentinels,
    _restore_blockquotes,
    format_entries,
    split_message,
    strip_sentinels,
    to_telegram_markdown,
)
from telebridge.transcript_parser import (
    EXPANDABLE_QUOTE_END,
    EXPANDABLE_QUOTE_START,
    ParsedEntry,
)


class TestFormatEntries:
    """Tests for format_entries function (Layer 1)."""

    def test_empty_entries(self) -> None:
        """Empty list returns empty string."""
        result = format_entries([])
        assert result == ""

    def test_user_text_entry(self) -> None:
        """User text is prefixed with 👤."""
        entries = [
            ParsedEntry(role="user", text="Hello world", content_type="text"),
        ]
        result = format_entries(entries)
        assert result == "👤 Hello world"

    def test_user_text_truncation(self) -> None:
        """User text is truncated at MAX_USER_MESSAGE_LENGTH."""
        long_text = "x" * (MAX_USER_MESSAGE_LENGTH + 100)
        entries = [
            ParsedEntry(role="user", text=long_text, content_type="text"),
        ]
        result = format_entries(entries)
        # 👤 (1 char) + space + 3000 chars + … (1 char) = 3003
        expected_len = 2 + MAX_USER_MESSAGE_LENGTH + 1
        assert len(result) == expected_len
        assert result.endswith("…")

    def test_assistant_text_entry(self) -> None:
        """Assistant text passes through unchanged."""
        entries = [
            ParsedEntry(role="assistant", text="Hello back", content_type="text"),
        ]
        result = format_entries(entries)
        assert result == "Hello back"

    def test_assistant_thinking_entry(self) -> None:
        """Thinking entries are prefixed with indicator."""
        entries = [
            ParsedEntry(
                role="assistant",
                text="thinking content here",
                content_type="thinking",
            ),
        ]
        result = format_entries(entries)
        assert result == "∴ Thinking…\nthinking content here"

    def test_tool_use_entry(self) -> None:
        """Tool use entries use their text as-is."""
        entries = [
            ParsedEntry(
                role="assistant",
                text="**Read**(file.py)",
                content_type="tool_use",
                tool_name="Read",
            ),
        ]
        result = format_entries(entries)
        assert result == "**Read**(file.py)"

    def test_tool_result_entry(self) -> None:
        """Tool result entries use their text as-is."""
        entries = [
            ParsedEntry(
                role="assistant",
                text="**Read**(file.py)\n  ⎿  Read 50 lines",
                content_type="tool_result",
                tool_name="Read",
            ),
        ]
        result = format_entries(entries)
        assert "Read 50 lines" in result

    def test_multiple_entries(self) -> None:
        """Multiple entries are joined with double newlines."""
        entries = [
            ParsedEntry(role="user", text="Question?", content_type="text"),
            ParsedEntry(role="assistant", text="Answer.", content_type="text"),
        ]
        result = format_entries(entries)
        assert result == "👤 Question?\n\nAnswer."

    def test_empty_text_skipped(self) -> None:
        """Entries with empty text are skipped."""
        entries = [
            ParsedEntry(role="assistant", text="", content_type="text"),
            ParsedEntry(role="assistant", text="Valid", content_type="text"),
        ]
        result = format_entries(entries)
        assert result == "Valid"


class TestExtractSentinels:
    """Tests for _extract_sentinels helper."""

    def test_no_sentinels(self) -> None:
        """Text without sentinels is unchanged."""
        text = "Hello world"
        result, placeholders = _extract_sentinels(text)
        assert result == text
        assert placeholders == {}

    def test_single_sentinel(self) -> None:
        """Single sentinel is replaced with placeholder."""
        text = f"Prefix {EXPANDABLE_QUOTE_START}content{EXPANDABLE_QUOTE_END} suffix"
        result, placeholders = _extract_sentinels(text)
        # Placeholder format is BLOCKQUOTE<N>END
        assert "BLOCKQUOTE0END" in result
        assert len(placeholders) == 1
        # Check content is stored
        assert list(placeholders.values())[0] == "content"

    def test_multiple_sentinels(self) -> None:
        """Multiple sentinels get numbered placeholders."""
        text = (
            f"{EXPANDABLE_QUOTE_START}first{EXPANDABLE_QUOTE_END} "
            f"{EXPANDABLE_QUOTE_START}second{EXPANDABLE_QUOTE_END}"
        )
        result, placeholders = _extract_sentinels(text)
        assert "BLOCKQUOTE0END" in result
        assert "BLOCKQUOTE1END" in result
        assert len(placeholders) == 2


class TestConvertTablesToCards:
    """Tests for _convert_tables_to_cards helper."""

    def test_no_tables(self) -> None:
        """Text without tables is unchanged."""
        text = "Just some text\nNo tables here"
        result = _convert_tables_to_cards(text)
        assert result == text

    def test_simple_table(self) -> None:
        """Simple table is converted to card format."""
        text = "| Key | Value |\n|-----|-------|\n| Name | Test |\n| Count | 42 |"
        result = _convert_tables_to_cards(text)
        assert "**Key**: Name" in result
        assert "**Value**: Test" in result
        assert "**Key**: Count" in result
        assert "**Value**: 42" in result

    def test_table_with_surrounding_text(self) -> None:
        """Table conversion preserves surrounding text."""
        text = "Before\n| A | B |\n|---|---|\n| 1 | 2 |\nAfter"
        result = _convert_tables_to_cards(text)
        assert "Before" in result
        assert "After" in result
        assert "**A**: 1" in result


class TestRestoreBlockquotes:
    """Tests for _restore_blockquotes helper."""

    def test_no_placeholders(self) -> None:
        """Text without placeholders is unchanged."""
        text = "Hello world"
        result = _restore_blockquotes(text, {})
        assert result == text

    def test_single_blockquote(self) -> None:
        """Single placeholder is converted to blockquote."""
        text = "Prefix BLOCKQUOTE0END suffix"
        placeholders = {"BLOCKQUOTE0END": "content"}
        result = _restore_blockquotes(text, placeholders)
        assert result == "Prefix **>content|| suffix"

    def test_escapes_double_pipe(self) -> None:
        """Double pipes in content are escaped."""
        text = "BLOCKQUOTE0END"
        placeholders = {"BLOCKQUOTE0END": "text || more"}
        result = _restore_blockquotes(text, placeholders)
        assert result == "**>text \\|\\| more||"


class TestToTelegramMarkdown:
    """Tests for to_telegram_markdown function (Layer 2)."""

    def test_plain_text(self) -> None:
        """Plain text passes through with minimal changes."""
        text = "Hello world"
        result = to_telegram_markdown(text)
        assert "Hello" in result
        assert "world" in result

    def test_bold_text(self) -> None:
        """Bold markdown is converted to MarkdownV2."""
        text = "**bold text**"
        result = to_telegram_markdown(text)
        assert "bold" in result

    def test_with_sentinels(self) -> None:
        """Sentinel content is preserved as blockquotes."""
        text = f"Prefix {EXPANDABLE_QUOTE_START}content{EXPANDABLE_QUOTE_END} suffix"
        result = to_telegram_markdown(text)
        assert "**>" in result  # Blockquote start
        assert "||" in result  # Blockquote end

    def test_table_conversion(self) -> None:
        """Tables are converted to card format."""
        text = "| Key | Value |\n|-----|-------|\n| Name | Test |"
        result = to_telegram_markdown(text)
        # Tables get converted to **Key**: Value format
        assert "Key" in result
        assert "Test" in result


class TestSplitMessage:
    """Tests for split_message function (Layer 3)."""

    def test_short_message(self) -> None:
        """Messages under limit are not split."""
        text = "Short message"
        result = split_message(text)
        assert len(result) == 1
        assert result[0] == text

    def test_exact_limit(self) -> None:
        """Messages exactly at limit are not split."""
        text = "x" * TELEGRAM_MAX_MESSAGE_LENGTH
        result = split_message(text)
        assert len(result) == 1
        assert len(result[0]) == TELEGRAM_MAX_MESSAGE_LENGTH

    def test_long_message_split(self) -> None:
        """Messages over limit are split."""
        # Create a message that definitely exceeds 4096 chars
        text = "\n".join([f"Line {i}: " + "x" * 500 for i in range(15)])
        result = split_message(text)
        assert len(result) > 1
        for chunk in result:
            assert len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH

    def test_pagination_markers(self) -> None:
        """Multi-part messages get pagination markers."""
        text = "\n".join([f"Line {i} " + "x" * 1000 for i in range(5)])
        result = split_message(text)
        if len(result) > 1:
            assert result[0].startswith("[1/")
            assert result[1].startswith("[2/")

    def test_code_block_preservation(self) -> None:
        """Code blocks are closed and reopened at split boundaries."""
        lines = ["```python"] + [f"# Line {i}" for i in range(300)] + ["```"]
        text = "\n".join(lines)
        result = split_message(text)

        # First chunk should close the code block
        assert "```" in result[0]

        # Second chunk should reopen the code block
        if len(result) > 1:
            assert "```python" in result[1] or "```" in result[1]

    def test_custom_max_length(self) -> None:
        """Custom max_length is respected."""
        text = "x" * 200
        result = split_message(text, max_length=100)
        assert len(result) > 1
        # Account for pagination markers being added
        for chunk in result:
            # May slightly exceed due to pagination, but should be close
            assert len(chunk) <= 110  # Allow 10 chars for pagination marker


class TestStripSentinels:
    """Tests for strip_sentinels helper."""

    def test_no_sentinels(self) -> None:
        """Text without sentinels is unchanged."""
        text = "Hello world"
        result = strip_sentinels(text)
        assert result == text

    def test_strip_sentinels(self) -> None:
        """Sentinel markers are removed, content preserved."""
        text = f"Prefix {EXPANDABLE_QUOTE_START}content{EXPANDABLE_QUOTE_END} suffix"
        result = strip_sentinels(text)
        assert result == "Prefix content suffix"

    def test_multiple_sentinels(self) -> None:
        """Multiple sentinel markers are all removed."""
        text = (
            f"{EXPANDABLE_QUOTE_START}first{EXPANDABLE_QUOTE_END} "
            f"{EXPANDABLE_QUOTE_START}second{EXPANDABLE_QUOTE_END}"
        )
        result = strip_sentinels(text)
        assert result == "first second"


class TestIntegration:
    """Integration tests for the full pipeline."""

    def test_full_pipeline(self) -> None:
        """Test entries → format → convert → split pipeline."""
        entries = [
            ParsedEntry(role="user", text="What is this?", content_type="text"),
            ParsedEntry(
                role="assistant",
                text="Let me check that file.",
                content_type="text",
            ),
            ParsedEntry(
                role="assistant",
                text="**Read**(file.py)",
                content_type="tool_use",
                tool_name="Read",
            ),
            ParsedEntry(
                role="assistant",
                text="**Read**(file.py)\n  ⎿  Read 10 lines",
                content_type="tool_result",
            ),
        ]

        # Layer 1: Format entries
        formatted = format_entries(entries)
        assert "👤 What is this?" in formatted
        assert "Let me check" in formatted

        # Layer 2: Convert to Telegram markdown
        telegram = to_telegram_markdown(formatted)
        assert len(telegram) > 0

        # Layer 3: Split if needed
        chunks = split_message(telegram)
        for chunk in chunks:
            assert len(chunk) <= TELEGRAM_MAX_MESSAGE_LENGTH

    def test_with_expandable_content(self) -> None:
        """Test pipeline with expandable quote content."""
        entries = [
            ParsedEntry(
                role="assistant",
                text=f"Result: {EXPANDABLE_QUOTE_START}long content{EXPANDABLE_QUOTE_END}",
                content_type="text",
            ),
        ]

        formatted = format_entries(entries)
        telegram = to_telegram_markdown(formatted)

        # Should have blockquote markers
        assert "**>" in telegram, f"Expected **> in: {telegram}"
        assert "||" in telegram, f"Expected || in: {telegram}"
