---
id: LINCE-50
title: Implement proper pane_key and thread_id lookup for MessageTask creation
status: Done
assignee: []
created_date: '2026-03-17 12:43'
updated_date: '2026-03-17 13:13'
labels:
  - enhancement
  - multi-session
  - routing
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two locations create `MessageTask` objects with empty `pane_key=""` and `thread_id=None` because the session lookup isn't implemented.

**Locations:**
1. `app.py:397-401` - `_convert_entries_to_tasks()` 
2. `message_queue.py:655` - `_outbound_callback()`

**Current behavior:**
```python
task = MessageTask(
    ...
    pane_key="",  # Should look up from SessionManager
    thread_id=None,  # Should look up from SessionManager
)
```

**Expected behavior:**
Look up the correct `pane_key` and `thread_id` based on the session_id from the `ParsedEntry` or current session context.

**Impact:**
- Outbound messages may not route correctly in multi-session scenarios
- Status messages may not appear in correct threads

**Implementation:**
Add method to SessionManager:
```python
def resolve_thread_for_session(self, session_id: str) -> tuple[str, int] | None:
    """Find thread binding for a session.
    
    Returns:
        (pane_key, thread_id) or None if not bound
    """
```
<!-- SECTION:DESCRIPTION:END -->
