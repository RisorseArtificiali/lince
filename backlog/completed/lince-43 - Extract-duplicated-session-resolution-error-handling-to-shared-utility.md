---
id: LINCE-43
title: Extract duplicated session resolution error handling to shared utility
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 12:19'
labels:
  - refactoring
  - code-quality
  - technical-debt
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
During code quality review, identified that session resolution with "no active session" error handling is duplicated across multiple handlers.

**Current Pattern:**
```python
session_info = await session_manager.resolve_session_for_thread_checked(
    update.effective_user.id, thread_id, bridge
)

if not session_info:
    await message.reply_text(
        "No active session. Use /bind to connect to a Claude Code session first."
    )
    return
```

**Found in:**
- handlers/messages.py (lines 111-118)
- handlers/media.py (lines 43-51)
- Potentially other handlers

**Proposed Solution:**
Create shared handler in `utils.py`:
```python
async def resolve_session_or_error(
    session_manager: SessionManager,
    user_id: int,
    thread_id: int,
    bridge: MultiplexerBridge,
    message: Message,
) -> SessionInfo | None:
    """Resolve session or send error message.
    
    Returns:
        SessionInfo if found, None otherwise (error already sent)
    """
    session_info = await session_manager.resolve_session_for_thread_checked(
        user_id, thread_id, bridge
    )
    
    if not session_info:
        await message.reply_text(
            "No active session. Use /bind to connect to a Claude Code session first."
        )
        return None
    
    return session_info
```

**Impact:**
- Consistent error handling across all handlers
- Single place to update error messages
- Reduces code duplication
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Not worth implementing - the duplication is minimal (3-4 occurrences) and each handler has slightly different context. The 4-line pattern is clear and self-documenting. Creating a shared utility would add complexity without meaningful benefit.
<!-- SECTION:FINAL_SUMMARY:END -->
