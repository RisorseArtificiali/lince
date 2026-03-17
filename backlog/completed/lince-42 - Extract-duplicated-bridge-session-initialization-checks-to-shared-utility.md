---
id: LINCE-42
title: Extract duplicated bridge/session initialization checks to shared utility
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 12:18'
labels:
  - refactoring
  - code-quality
  - technical-debt
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
During LINCE-18 implementation, the code quality review identified that bridge and session manager initialization checks are duplicated across 12+ handler files.

**Current Pattern (repeated 12+ times):**
```python
bridge = get_bridge()
if bridge is None:
    await message.reply_text("Bridge not initialized")
    return

session_manager = get_session_manager()
if session_manager is None:
    await message.reply_text("Session manager not initialized")
    return
```

**Found in:**
- handlers/messages.py
- handlers/commands.py (multiple commands)
- handlers/claude_commands.py
- handlers/session_commands.py
- handlers/media.py (LINCE-18)
- And 6+ more handler files

**Proposed Solution:**
Create shared utility in `utils.py`:
```python
async def ensure_initialized(message: Message) -> tuple[MultiplexerBridge, SessionManager] | None:
    """Ensure bridge and session manager are initialized.
    
    Returns:
        (bridge, session_manager) tuple or None if not initialized
    """
    bridge = get_bridge()
    if bridge is None:
        await message.reply_text("Bridge not initialized")
        return None
    
    session_manager = get_session_manager()
    if session_manager is None:
        await message.reply_text("Session manager not initialized")
        return None
    
    return bridge, session_manager
```

**Impact:**
- Reduces ~40 lines of duplicated code
- Single source of truth for initialization checks
- Easier to update error messages in one place
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Already resolved - the codebase was refactored to use `get_app(context)` pattern which returns a TelebridgeApp instance with bridge, session_manager, and other components as properties. This eliminates the need for separate initialization checks.
<!-- SECTION:FINAL_SUMMARY:END -->
