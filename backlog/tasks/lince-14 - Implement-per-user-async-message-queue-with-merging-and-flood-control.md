---
id: LINCE-14
title: Implement per-user async message queue with merging and flood control
status: To Do
assignee: []
created_date: '2026-03-03 14:34'
updated_date: '2026-03-03 16:51'
labels:
  - telebridge
  - telegram
milestone: m-7
dependencies:
  - LINCE-11
references:
  - ccbot src/ccbot/handlers/message_queue.py pattern
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/handlers/message_queue.py` — per-user async message queuing system for sequential delivery with content merging and Telegram flood control.

**Architecture** (from ccbot's proven pattern):
```python
_message_queues: dict[int, asyncio.Queue[MessageTask]]   # user_id -> queue
_queue_workers: dict[int, asyncio.Task]                   # user_id -> worker task
_queue_locks: dict[int, asyncio.Lock]                     # user_id -> merge lock
```

**MessageTask dataclass:**
```python
@dataclass
class MessageTask:
    task_type: str          # "content" | "status_update" | "status_clear"
    text: str = ""
    pane_key: str = ""
    parts: list[str] = field(default_factory=list)
    tool_use_id: str = ""
    content_type: str = ""
    thread_id: int | None = None
    image_data: bytes = b""
```

**Content merging**: `_merge_content_tasks()` inspects queue for consecutive tasks with same `pane_key`, no tool_use/tool_result, total length <= 3800 chars. Drains queue under async lock, merges eligible, puts remainder back.

**Flood control**: Handle `RetryAfter` exceptions from Telegram:
- Extract retry_after seconds from exception
- If exceeds max wait (10 seconds), store ban expiry timestamp
- Status messages dropped during flood (ephemeral)
- Content messages wait until flood clears

**Status vs content distinction:**
- Status messages: ephemeral, edited in-place, dropped during flood, auto-deleted when content arrives
- Content messages: persistent, merged for efficiency, support tool_use message editing, carry image data

**Worker lifecycle:**
- One worker per user_id, created on first message
- Worker loops: dequeue -> merge eligible -> send -> handle errors
- Workers auto-stop after inactivity timeout

**Integration**: The outbound pipeline (LINCE-11) should enqueue MessageTasks instead of sending directly. This decouples message production from delivery and enables merging + flood control.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-user async queues with independent workers
- [ ] #2 Content merging reduces API calls for rapid messages
- [ ] #3 RetryAfter flood control with ban expiry tracking
- [ ] #4 Status messages dropped during flood
- [ ] #5 Content messages wait during flood
- [ ] #6 Workers auto-stop after inactivity
- [ ] #7 Integration with outbound pipeline via enqueue()
<!-- AC:END -->
