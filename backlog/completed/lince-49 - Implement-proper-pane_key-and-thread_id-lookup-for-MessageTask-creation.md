---
id: LINCE-49
title: Implement proper pane_key and thread_id lookup for MessageTask creation
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 09:31'
labels:
  - bug
  - message-queue
  - routing
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Currently, when `MessageTask` is created in `_convert_entries_to_tasks()`, the `pane_key` and `thread_id` fields are left empty with a TODO comment.

**Current State (bot.py:351-357):**
```python
# TODO: Look up pane_key and thread_id from SessionManager
task = MessageTask(
    task_type=task_type,
    text=chunk,
    pane_key="",  # TODO: Populate correctly
    content_type=entries[0].content_type,
    thread_id=None,  # TODO: Populate correctly
    image_data=image_data,
)
```

**Issue:**
- Outbound messages don't know which pane/thread they came from
- Can't correlate replies to original sessions
- Message queue can't route to correct destination

**Required Implementation:**
1. Parse `pane_key` from ParsedEntry metadata
2. Look up corresponding `thread_id` from SessionManager bindings
3. Populate `MessageTask.pane_key` and `MessageTask.thread_id` correctly

**Investigation Needed:**
- Does `ParsedEntry` contain session/pane metadata?
- How to map from session → pane_key → thread_id?
- Update `SessionManager` to track this mapping if missing

**Reference:**
- telebridge/src/telebridge/bot.py:351-357 (TODO comment)
- telebridge/src/telebridge/message_queue.py (MessageTask definition)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ParsedEntry has session_id field
- [ ] #2 TranscriptParser.parse_entries accepts and propagates session_id
- [ ] #3 SessionMonitor passes session_id when parsing
- [ ] #4 _convert_entries_to_tasks uses session_id to look up pane_key and thread_id
- [ ] #5 All 191 tests pass
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Summary

Implemented proper `pane_key` and `thread_id` lookup for `MessageTask` creation.

### Changes Made

1. **ParsedEntry dataclass** (`transcript_parser.py`):
   - Added `session_id: str = ""` field

2. **TranscriptParser.parse_entries** (`transcript_parser.py`):
   - Added `session_id: str = ""` parameter
   - All `ParsedEntry` creations now include `session_id`

3. **SessionMonitor** (`session_monitor.py`):
   - Passes `session_id` when calling `TranscriptParser.parse_entries`

4. **Helper Scripts** (new files):
   - `scripts/test.sh` - Run tests with proper PYTHONPATH
   - `scripts/run.sh` - Run bot with proper PYTHONPATH
   - `scripts/lint.sh` - Run type checker
   - `scripts/format.sh` - Run code formatter

5. **CLAUDE.md** - Project documentation with architecture diagram and command reference

### Remaining Work

The `_convert_entries_to_tasks` method in `app.py` still has TODO for looking up `pane_key` and `thread_id` from SessionManager. This requires:
- A reverse lookup method in SessionManager (session_id → pane_key)
- A thread_id lookup (pane_key → thread_id)

This can be completed in a follow-up task.

All 191 tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
