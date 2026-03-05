---
id: LINCE-7
title: Implement JSONL session monitor with offset tracking
status: To Do
assignee: []
created_date: '2026-03-03 14:32'
labels:
  - telebridge
  - core
milestone: m-1
dependencies:
  - LINCE-4
  - LINCE-6
references:
  - ccbot src/ccbot/session_monitor.py pattern
  - ~/.claude/projects/*/sessions-index.json format
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/session_monitor.py` — an async service that polls Claude Code's JSONL transcript files for new output and emits parsed messages via callback.

**Core mechanism** (from ccbot's proven pattern):
- Each tracked session maintains `last_byte_offset` into its JSONL file
- Polling loop runs every `config.session.poll_interval` seconds (default 2.0)
- Change detection uses BOTH mtime comparison AND file size check — skip only when both are unchanged
- Incremental read: `aiofiles` open -> seek to offset -> read new lines -> parse JSON -> advance offset only past complete lines

**Truncation detection**: If `last_byte_offset > current_file_size`, reset offset to 0 (handles Claude Code `/clear` command which rewrites the file)

**Corruption recovery**: If first char at offset is not `{`, call `readline()` to skip to next valid line start, update offset

**Session discovery**:
- Read `~/.telebridge/session_map.json` for hook-registered sessions
- Also scan `~/.claude/projects/*/sessions-index.json` for session metadata
- Extract `sessionId`, `fullPath` (to JSONL file) from index entries
- Filter: only track sessions whose cwd matches an active multiplexer pane

**New session initialization**: When a session first appears, set initial offset to current EOF (only monitor NEW content, don't replay history)

**State persistence**: Save `MonitorState` to `~/.telebridge/monitor_state.json` containing per-session `TrackedSession(session_id, file_path, last_byte_offset)`. Restore on restart.

**Callback system**: `set_message_callback(async_callback)` — the monitor calls `await callback(parsed_entries)` for each batch of new JSONL entries. Errors in callback are caught and logged, never crash the monitor.

**Tool pairing**: Maintain `pending_tools: dict[str, dict]` per session — `tool_use` blocks from assistant messages may arrive in a different poll cycle than their matching `tool_result`. Carry pending state across cycles.

**Data structures:**
```python
@dataclass
class TrackedSession:
    session_id: str
    file_path: str
    last_byte_offset: int = 0

@dataclass
class MonitorState:
    sessions: dict[str, TrackedSession]  # session_id -> TrackedSession
```

**Lifecycle**: `start()` launches async task, `stop()` cancels it. Must be restartable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Polls JSONL files at configurable interval
- [ ] #2 Byte-offset tracking reads only new content
- [ ] #3 Truncation detection resets offset on /clear
- [ ] #4 Corruption recovery skips to next valid JSON line
- [ ] #5 Discovers sessions from session_map.json and sessions-index.json
- [ ] #6 New sessions start monitoring from EOF (no history replay)
- [ ] #7 State persisted to monitor_state.json and restored on restart
- [ ] #8 Async callback invoked for each batch of new entries
- [ ] #9 pending_tools carried across poll cycles for tool pairing
- [ ] #10 start()/stop() lifecycle works correctly
<!-- AC:END -->
