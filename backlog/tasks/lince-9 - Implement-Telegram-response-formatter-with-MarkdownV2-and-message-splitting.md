---
id: LINCE-9
title: Implement Telegram response formatter with MarkdownV2 and message splitting
status: To Do
assignee: []
created_date: '2026-03-03 14:32'
updated_date: '2026-03-03 16:51'
labels:
  - telebridge
  - telegram
milestone: m-7
dependencies:
  - LINCE-3
  - LINCE-8
references:
  - ccbot src/ccbot/handlers/response_builder.py
  - ccbot src/ccbot/telegram_sender.py
  - ccbot src/ccbot/markdown_v2.py
  - telegramify-markdown library
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/response_formatter.py` — converts parsed transcript entries into Telegram-ready messages with proper formatting and 4096-char splitting.

**Three-layer formatting pipeline** (from ccbot architecture):
1. `build_response_parts(entries)` -> structured text with sentinel tokens
2. `convert_markdown(text)` -> Telegram MarkdownV2
3. `split_message(text, max_length=4096)` -> list of message chunks

**Layer 1 — Response building:**
- User messages: prefix with "👤", truncate at 3000 chars
- Assistant text: pass through as markdown
- Thinking: prefix with "∴ Thinking…", truncate inner text at 500 chars
- Tool use: format as tool call summary (tool name + key input params)
- Tool result: formatted output (per-tool formatting from transcript_parser)
- Expandable quotes: maintain sentinel markers for downstream conversion

**Layer 2 — MarkdownV2 conversion:**
- Use `telegramify-markdown` library for bold/italic/link conversion
- Escape MarkdownV2 special chars: `_*[]()~>#+\-=|{}.!\\`
- Convert markdown tables to card-style key-value format (tables don't render in Telegram)
- Convert expandable quote sentinels to Telegram expandable blockquote syntax (`>...||`)
- Single conversion point — never double-escape

**Layer 3 — Message splitting:**
- Max 4096 chars per message (Telegram limit)
- Split on newline boundaries when possible
- Track code block state: if split occurs inside ` ```lang `, close with ` ``` ` at chunk end, reopen at next chunk start
- Lines exceeding max_length force-split into fixed-size pieces
- Add pagination markers `[1/N]` for multi-part responses

**Two-tier sending strategy** (for bot.py to use):
- Primary: send with MarkdownV2 parse_mode
- Fallback: if MarkdownV2 parsing fails, strip sentinels and send as plain text

**Key function signatures:**
```python
def format_entries(entries: list[ParsedEntry]) -> str
def to_telegram_markdown(text: str) -> str
def split_message(text: str, max_length: int = 4096) -> list[str]
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Formats user, assistant, thinking, tool_use, tool_result entries
- [ ] #2 MarkdownV2 conversion handles all special characters
- [ ] #3 Tables converted to card-style format
- [ ] #4 Expandable quotes converted to Telegram blockquote syntax
- [ ] #5 Message splitting respects 4096 char limit
- [ ] #6 Code block state preserved across splits
- [ ] #7 Pagination markers added for multi-part messages
- [ ] #8 Fallback to plain text when MarkdownV2 fails
<!-- AC:END -->
