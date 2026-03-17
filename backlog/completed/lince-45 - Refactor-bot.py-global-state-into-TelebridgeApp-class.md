---
id: LINCE-45
title: Refactor bot.py global state into TelebridgeApp class
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 08:50'
labels:
  - refactoring
  - architecture
  - testability
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `bot.py` file contains 7 global variables used across the module. This creates tight coupling and makes testing difficult.

**Current State:**
```python
_bot: Bot | None = None
_bridge: MultiplexerBridge | None = None
_config: TelebridgeConfig | None = None
_monitor: SessionMonitor | None = None
_session_manager: SessionManager | None = None
_message_queue: "MessageQueue | None" = None
_target_chat_id: int | None = None
```

**Issues:**
- Difficult to test (can't easily mock globals)
- Implicit dependencies (functions rely on hidden global state)
- Lifecycle management complexity

**Proposed Solution:**
Create a `TelebridgeApp` class:
```python
class TelebridgeApp:
    def __init__(self, config: TelebridgeConfig):
        self.config = config
        self.bridge = create_bridge(config)
        self.session_manager = SessionManager(config)
        self.message_queue = MessageQueue(config)
        self.monitor = SessionMonitor(config)
        self.target_chat_id: int | None = None
    
    async def create_application(self) -> Application:
        # Create and configure telegram app
        ...
    
    async def shutdown(self) -> None:
        # Cleanup all resources
        ...
```

**Benefits:**
- Explicit dependencies
- Easier to test (can mock the app instance)
- Clearer lifecycle management
- Better encapsulation

**Reference:**
- telebridge/src/telebridge/bot.py (entire file)
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 TelebridgeApp class exists in app.py with all state encapsulated
- [ ] #2 All handlers use get_app(context) from telebridge.app
- [ ] #3 bot.py marked as deprecated with proper warnings
- [ ] #4 No production code uses deprecated bot.py functions
- [ ] #5 All 176 tests pass
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Summary

This task was already completed in a previous session. The `TelebridgeApp` class in `app.py` encapsulates all application state:

- `self._bridge: MultiplexerBridge`
- `self._session_manager: SessionManager`
- `self._message_queue: MessageQueue`
- `self._bot: Bot`
- `self._media_registry: MediaRegistry`
- `self._target_chat_id: int | None`

All handlers use `get_app(context)` from `telebridge.app` to access the app instance. The `bot.py` module is marked deprecated with proper warnings and migration guide.

**Verification:**
- All 176 tests pass
- No production code uses deprecated `get_bridge()`, `get_session_manager()`, or `get_config()` functions
<!-- SECTION:FINAL_SUMMARY:END -->
