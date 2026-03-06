---
id: LINCE-12
title: Implement session manager with topic-pane-session mapping
status: To Do
assignee: []
created_date: '2026-03-03 14:33'
labels:
  - telebridge
  - sessions
milestone: m-2
dependencies:
  - LINCE-6
  - LINCE-10
references:
  - ccbot src/ccbot/session.py pattern
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/session_manager.py` — manages the bidirectional mapping between Telegram forum topics, multiplexer panes, and Claude Code sessions with persistent state.

**Mapping chain:**
```
Telegram (user_id, thread_id) 
  -> thread_bindings[user_id][thread_id] 
  -> pane_key (mux_session:window_or_tab_id)
  -> window_states[pane_key].session_id 
  -> Claude JSONL file path
```

**Persisted state** (`~/.telebridge/state.json`):
```json
{
  "window_states": {
    "pane_key": {"session_id": "uuid", "cwd": "/path", "pane_name": "name"}
  },
  "thread_bindings": {
    "user_id": {"thread_id": "pane_key"}
  },
  "user_pane_offsets": {
    "user_id": {"pane_key": 48271}
  }
}
```

**Key operations:**
- `bind_thread(user_id, thread_id, pane_key)` — associate Telegram topic with multiplexer pane
- `unbind_thread(user_id, thread_id)` — detach topic from session
- `resolve_pane_for_thread(user_id, thread_id) -> pane_key | None` — find pane for a topic
- `resolve_session_for_pane(pane_key) -> SessionInfo | None` — find Claude session for a pane
- `load_session_map()` — read session_map.json (hook-written), update window_states
- `clear_pane_session(pane_key)` — empty session_id when /clear is invoked
- `list_active_sessions() -> list[SessionInfo]` — enumerate bound sessions

**Stale ID resolution** (on startup):
- Detect entries for panes that no longer exist in the multiplexer
- For tmux: query live windows via `tmux list-windows`
- For Zellij: query tabs via `zellij action query-tab-names`
- Remove orphaned entries from state
- Clean session_map.json of orphans

**Session metadata** (transient, not persisted):
- Summary: from "summary" JSONL entry or last user message (first 50 chars) or "Untitled"
- Message count: calculated on access from JSONL file

**Atomic persistence**: All state writes via tempfile + `os.replace()`. No explicit async locks needed — relies on single-threaded asyncio event loop, all mutations immediately save.

**Data classes:**
```python
@dataclass
class PaneState:
    session_id: str = ""
    cwd: str = ""
    pane_name: str = ""

@dataclass
class SessionInfo:
    session_id: str
    pane_key: str
    cwd: str
    summary: str = "Untitled"
    message_count: int = 0
    file_path: str = ""
```
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Thread-to-pane-to-session mapping chain works end-to-end
- [ ] #2 State persisted to ~/.telebridge/state.json with atomic writes
- [ ] #3 load_session_map() reads hook-written session_map.json
- [ ] #4 Stale pane detection and cleanup on startup for both tmux and Zellij
- [ ] #5 bind/unbind/resolve operations functional
- [ ] #6 Session metadata (summary, message_count) derived from JSONL
<!-- AC:END -->
