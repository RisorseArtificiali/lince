---
id: LINCE-8
title: Implement Claude Code transcript parser
status: To Do
assignee: []
created_date: '2026-03-03 14:32'
labels:
  - telebridge
  - core
milestone: m-1
dependencies:
  - LINCE-3
references:
  - ccbot src/ccbot/transcript_parser.py pattern
  - Claude Code JSONL format documentation
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/transcript_parser.py` — parses Claude Code's JSONL entries into structured messages suitable for Telegram display.

**JSONL entry format** (as produced by Claude Code):
```json
{
  "type": "user" | "assistant" | "summary",
  "message": {
    "content": [/* array of content blocks */]
  },
  "sessionId": "...",
  "timestamp": "ISO-8601"
}
```

**Content block types to handle:**
- `{"type": "text", "text": "content"}` — plain text or markdown
- `{"type": "tool_use", "id": "toolu_xxx", "name": "Bash", "input": {"command": "ls"}}` — tool invocations
- `{"type": "tool_result", "tool_use_id": "toolu_xxx", "content": [...], "is_error": bool}` — tool output
- `{"type": "thinking", "thinking": "internal reasoning"}` — thinking blocks
- `{"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}` — images

**Data classes:**
```python
@dataclass
class ParsedEntry:
    role: str              # "user" or "assistant"
    content_type: str      # "text", "tool_use", "tool_result", "thinking", "image"
    text: str              # formatted display text
    tool_name: str = ""    # e.g. "Bash", "Read", "Edit"
    tool_use_id: str = ""  # for pairing tool_use with tool_result
    image_data: bytes = b""  # decoded image if present
    timestamp: str = ""
```

**Tool result formatting by tool type** (from ccbot patterns):
| Tool | Format |
|------|--------|
| Read/Write | Filename + line count summary |
| Bash | Command + output line count, full output in expandable section |
| Grep/Glob | Match/file count summary |
| Edit | Unified diff with +N/-M line statistics |
| WebFetch/WebSearch | Content length or result count |

**Tool pairing**: `parse_entries(entries, pending_tools)` returns `(list[ParsedEntry], updated_pending_tools)`. `tool_use` in assistant messages creates pending entries; `tool_result` in user messages resolves them by `tool_use_id`.

**Thinking blocks**: Truncate to configurable max length (default 500 chars), prefix with indicator.

**Expandable content**: Wrap long tool output with sentinel markers (`EXPANDABLE_QUOTE_START` / `EXPANDABLE_QUOTE_END`) for downstream formatting.

**ANSI stripping**: Remove ANSI escape sequences from tool output text.

**Summary entries**: `"type": "summary"` entries contain conversation summaries — extract for session metadata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Parses all content block types: text, tool_use, tool_result, thinking, image
- [ ] #2 Tool pairing via tool_use_id works across parse calls
- [ ] #3 Tool results formatted per-tool-type (Bash, Read, Edit, Grep, etc.)
- [ ] #4 Thinking blocks truncated to configurable max length
- [ ] #5 ANSI escape sequences stripped from output
- [ ] #6 Expandable content markers applied to long output
- [ ] #7 Image data decoded from base64 when present
- [ ] #8 Summary entries extracted for metadata
<!-- AC:END -->
