---
id: LINCE-7
title: Implement JSONL session monitor with offset tracking
status: Done
assignee: []
created_date: '2026-03-03 14:32'
updated_date: '2026-03-14 10:52'
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
- [x] #1 Polls JSONL files at configurable interval
- [x] #2 Byte-offset tracking reads only new content
- [x] #3 Truncation detection resets offset on /clear
- [x] #4 Corruption recovery skips to next valid JSON line
- [x] #5 Discovers sessions from session_map.json and sessions-index.json
- [x] #6 New sessions start monitoring from EOF (no history replay)
- [x] #7 State persisted to monitor_state.json and restored on restart
- [x] #8 Async callback invoked for each batch of new entries
- [x] #9 pending_tools carried across poll cycles for tool pairing
- [x] #10 start()/stop() lifecycle works correctly
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented JSONL session monitor with full offset tracking and async polling:

**Core features implemented:**
- Byte-offset tracking for incremental reading (no re-processing old content)
- Dual change detection (mtime + file size) for efficiency
- Truncation detection handles /clear command (resets offset)
- Corruption recovery skips to next valid JSON line
- Session discovery from session_map.json and sessions-index.json
- New sessions start at EOF (no history replay)
- Atomic state persistence to monitor_state.json
- Async callback system with error isolation
- Pending tools tracking across poll cycles
- Clean start()/stop() lifecycle

**Key classes:**
- `TrackedSession`: Per-session tracking (session_id, file_path, last_byte_offset)
- `MonitorState`: Persistent state with atomic save/load
- `SessionMonitor`: Main async polling service
- `ParsedEntry`: Minimal entry structure (full parsing in LINCE-8)

**Note:** The monitor emits raw JSONL data via callback. LINCE-8 will implement the full TranscriptParser that extracts text, tool_use, and thinking content.
<!-- SECTION:FINAL_SUMMARY:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Implementation complete with all acceptance criteria verified
- [ ] #2 Code follows ruff linting standards
- [ ] #3 Module imports successfully
<!-- DOD:END -->
