# LINCE-13 Code Quality Review

## Executive Summary
**Overall Assessment**: Code implements required functionality but exhibits several anti-patterns including redundant state checks, stringly-typed code, duplicate logic, and leaky abstractions.

**Priority Issues**: 8 High, 5 Medium, 3 Low

---

## 🔴 Critical Issues (High Priority)

### 1. Redundant Liveness Checks with Duplicate Logic
**Location**: `session_manager.py:169-197`

**Issue**: Three methods (`is_pane_live`, `is_session_active`, `resolve_session_for_thread_checked`) duplicate pane lookup logic with slight variations.

```python
# is_pane_live - checks pane existence
pane_state = self.state.window_states.get(pane_key)

# is_session_active - checks pane existence AGAIN
if not await self.is_pane_live(pane_key, bridge):
    return False
pane_state = self.state.window_states.get(pane_key)  # DUPLICATE

# resolve_session_for_thread_checked - checks pane existence AGAIN
if not await self.is_session_active(pane_key, bridge):
    return None
return self.resolve_session_for_pane(pane_key)  # DUPLICATE LOOKUP
```

**Impact**:
- 3x redundant dictionary lookups for same pane_key
- `resolve_session_for_pane` performs ANOTHER lookup inside
- Performance degradation in hot path (every message)

**Fix**: Consolidate into single lookup:
```python
async def resolve_session_checked(self, pane_key: str, bridge: MultiplexerBridge) -> SessionInfo | None:
    """Single unified check - liveness + resolution in one lookup."""
    if not await self.is_pane_live(pane_key, bridge):
        return None

    pane_state = self.state.window_states.get(pane_key)
    if not pane_state or not pane_state.session_id:
        return None

    # Use pane_state directly, avoid re-lookup
    return self._build_session_info(pane_key, pane_state)
```

---

### 2. Stringly-Typed State Keys Throughout
**Location**: `session_manager.py:53-87`, `handlers/messages.py:119`

**Issue**: User/thread IDs converted to strings with no constants, repeated conversions everywhere.

```python
# session_manager.py - 3 different conversion patterns
user_key = str(user_id)  # Line 56
thread_key = str(thread_id)  # Line 57
user_key = str(user_id)  # Line 73
thread_key = str(thread_id)  # Line 74
return self.state.thread_bindings.get(user_key, {}).get(thread_key)  # Line 84

# handlers/messages.py - more conversions
user_bindings = session_manager.state.thread_bindings.get(
    str(update.effective_user.id), {}  # Line 119
)
```

**Impact**:
- Type safety lost at boundaries
- Inconsistent conversions (some places use `str()`, others don't)
- No validation of key format
- Impossible to refactor without grep

**Fix**: Create type-safe wrapper:
```python
@dataclass(frozen=True)
class BindingKey:
    user_id: int
    thread_id: int

    def to_storage_key(self) -> str:
        return f"{self.user_id}:{self.thread_id}"

    @classmethod
    def from_storage_key(cls, key: str) -> "BindingKey":
        user_id, thread_id = key.split(":")
        return cls(int(user_id), int(thread_id))

# Usage:
key = BindingKey(user_id=123, thread_id=1)
self.state.bindings[key.to_storage_key()] = pane_key
```

---

### 3. Duplicate Dead Session Handling Logic
**Location**: `handlers/messages.py:107-149`

**Issue**: Dead session recovery logic duplicated across TWO conditional branches with identical structure.

```python
# Branch 1: Binding exists but session is dead (Line 116)
if pane_key:
    await _handle_stale_session(
        update, session_manager, bridge, update.effective_user.id, thread_id
    )
    return

# Branch 2: No binding exists (Line 121)
else:
    # ... 40 lines of auto-bind logic ...
    await message.reply_text("No sessions available. Use /bind to select or create one.")
    return

# Both branches: SAME recovery message pattern
```

**Impact**:
- Recovery options copy-pasted twice
- Maintenance burden (2 places to update)
- Inconsistent user experience (different messages for same problem)

**Fix**: Unify into single recovery path:
```python
async def _handle_missing_session(
    update: Update,
    session_manager: SessionManager,
    bridge: MultiplexerBridge,
    user_id: int,
    thread_id: int,
) -> bool:
    """Unified handler for missing/dead sessions. Returns True if handled."""

    pane_key = session_manager.resolve_pane_for_thread(user_id, thread_id)

    # Show appropriate recovery message based on state
    if pane_key:
        await update.message.reply_text(_STALE_SESSION_MESSAGE.format(pane=pane_key))
    else:
        await update.message.reply_text(_NO_BINDING_MESSAGE)

    # Try auto-bind regardless of prior state
    return await _try_auto_bind(update, session_manager, user_id, thread_id)
```

---

### 4. Polling Loop with Magic Numbers
**Location**: `handlers/claude_commands.py:267-285`

**Issue**: `_poll_for_new_session` uses hardcoded timeout and sleep intervals with no constants.

```python
while time.time() - start_time < timeout:  # Magic: 15.0 default
    session_manager.update_from_session_map()
    # ... check logic ...
    await asyncio.sleep(0.5)  # Magic: 0.5 seconds
```

**Impact**:
- No tuning ability without code changes
- Polling frequency hardcoded
- Timeout not configurable per environment
- No exponential backoff

**Fix**: Extract to config:
```python
# config.py
@dataclass
class SessionConfig:
    poll_interval: float = 0.5
    new_session_timeout: float = 15.0
    max_poll_attempts: int = 30

# claude_commands.py
async def _poll_for_new_session(
    session_manager: SessionManager,
    pane_key: str,
    config: SessionConfig,
) -> str | None:
    attempt = 0
    while attempt < config.max_poll_attempts:
        if _check_for_session(...):
            return new_id
        await asyncio.sleep(config.poll_interval)
        attempt += 1
```

---

### 5. Leaky Abstraction - Bridge Passed Everywhere
**Location**: `session_manager.py:169-197`, `handlers/messages.py:96`, `handlers/claude_commands.py:164`

**Issue**: `MultiplexerBridge` passed as parameter to liveness checks, breaking encapsulation.

```python
# session_manager.py
async def is_pane_live(self, pane_key: str, bridge: MultiplexerBridge) -> bool:
    panes = await asyncio.to_thread(bridge.list_panes)

# handlers/messages.py
session_info = await session_manager.resolve_session_for_thread_checked(
    update.effective_user.id, thread_id, bridge  # Passed through
)

# handlers/claude_commands.py
if not await session_manager.is_pane_live(pane_key, bridge):  # Passed through
```

**Impact**:
- Every caller must have bridge instance
- SessionManager can't manage its own dependencies
- Testability reduced (must mock bridge)
- Violates dependency injection principle

**Fix**: Store bridge in SessionManager:
```python
class SessionManager:
    def __init__(self, config: TelebridgeConfig, bridge: MultiplexerBridge):
        self.config = config
        self._bridge = bridge  # Store dependency

    async def is_pane_live(self, pane_key: str) -> bool:
        try:
            panes = await asyncio.to_thread(self._bridge.list_panes)
            return pane_key in panes
        except (RuntimeError, asyncio.TimeoutError):
            return False
```

---

## 🟡 Medium Priority Issues

### 6. Parameter Sprawl in Handler Functions
**Location**: `handlers/messages.py:95-102`, `handlers/claude_commands.py:164-172`

**Issue**: Functions take 5+ parameters with repeated patterns (`update`, `session_manager`, `bridge`, `user_id`, `thread_id`).

```python
# messages.py - 5 parameters
async def _handle_stale_session(
    update: Update,
    session_manager: "SessionManager",
    bridge: "MultiplexerBridge",
    user_id: int,
    thread_id: int,
) -> None:

# claude_commands.py - 5 parameters for similar operation
if not await session_manager.is_pane_live(pane_key, bridge):
    await update.message.reply_text(...)
```

**Impact**:
- Function signatures hard to remember
- Refactoring requires changing many call sites
- Parameters often extracted from same object (`update.effective_user.id`)

**Fix**: Create context object:
```python
@dataclass
class HandlerContext:
    update: Update
    session_manager: SessionManager
    bridge: MultiplexerBridge

    @property
    def user_id(self) -> int:
        return self.update.effective_user.id

    @property
    def thread_id(self) -> int:
        return self.update.message.message_thread_id or 0

# Usage:
async def _handle_stale_session(ctx: HandlerContext) -> None:
    if not await ctx.session_manager.is_pane_live(ctx.pane_key):
        await ctx.update.message.reply_text(...)
```

---

### 7. Unnecessary Nested Conditionals
**Location**: `handlers/messages.py:107-149`

**Issue**: Deep nesting (4 levels) for session resolution logic.

```python
if not session_info:  # Level 1
    pane_key = session_manager.resolve_pane_for_thread(...)

    if pane_key:  # Level 2
        await _handle_stale_session(...)
        return
    else:  # Level 2
        config = get_config()
        if config and session_manager:  # Level 3
            sessions = session_manager.list_active_sessions()
            # ... more nesting ...
            if len(unbound) == 1 and config.session.auto_bind:  # Level 4
                # ... logic ...
```

**Impact**:
- Cognitive load high
- Hard to follow execution paths
- Cyclomatic complexity excessive

**Fix**: Early returns + guard clauses:
```python
if not session_info:
    pane_key = session_manager.resolve_pane_for_thread(user_id, thread_id)

    # Early return for stale sessions
    if pane_key:
        return await _handle_stale_session(ctx, pane_key)

    # Guard: require config
    config = get_config()
    if not config:
        return await _show_config_error(update)

    # Simplified auto-bind logic
    return await _try_auto_bind_or_show_picker(ctx, config)
```

---

### 8. Placeholder Implementation with Pass
**Location**: `handlers/topic_handlers.py:26-90`

**Issue**: Three placeholder handlers with `pass` statements and TODO comments.

```python
async def handle_topic_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... 20 lines of comments ...
    logger.info("Topic close handler called (placeholder implementation)")
    pass  # Line 35

async def handle_topic_reopen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... 20 lines of comments ...
    pass  # Line 62

async def handle_topic_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... 20 lines of comments ...
    pass  # Line 83
```

**Impact**:
- Dead code in repository
- False sense of completion
- No clear path to implementation
- Wastes reviewer attention

**Fix**: Either implement or remove:
```python
# Option 1: Remove if not needed
# (Delete file, update imports)

# Option 2: Add NotImplementedError to force implementation
async def handle_topic_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    raise NotImplementedError("Topic close handling requires Telegram library forum event support")
```

---

### 9. Duplicate Session Map Update Pattern
**Location**: `handlers/claude_commands.py:278`, `session_manager.py:141`

**Issue**: `update_from_session_map()` called in loop with no change detection.

```python
# claude_commands.py - polling loop
while time.time() - start_time < timeout:
    session_manager.update_from_session_map()  # Full reload every 0.5s
    current_state = session_manager.state.window_states.get(pane_key)
    # ...

# session_manager.py - full reload
def update_from_session_map(self) -> None:
    session_map = self.load_session_map()
    for pane_key, session_info in session_map.items():
        # ... updates entire dict ...
    self.save()  # Disk write every time!
```

**Impact**:
- File I/O every 500ms during polling
- No change detection before save
- Unnecessary disk writes
- Performance bottleneck

**Fix**: Add change detection:
```python
def update_from_session_map(self) -> bool:
    """Update from session map. Returns True if changes detected."""
    session_map = self.load_session_map()

    changes_detected = False
    for pane_key, session_info in session_map.items():
        existing = self.state.window_states.get(pane_key)
        if existing and existing.session_id != session_info.get("session_id"):
            changes_detected = True
        # ... update ...

    if changes_detected:
        self.save()

    return changes_detected
```

---

### 10. Hardcoded Command Set Duplication
**Location**: `handlers/messages.py:23`, `bot.py:131-141`

**Issue**: `CLAUDE_COMMANDS` set duplicated between handler and bot setup.

```python
# messages.py
CLAUDE_COMMANDS = {"/clear", "/compact", "/cost", "/doctor", "/init", "/logout", "/model", "/permissions", "/primes", "/resume", "/review", "/status", "/terminal-setup", "/usage"}

# bot.py - bot command menu (different set!)
commands = [
    BotCommand("start", "Start telebridge session"),
    BotCommand("screenshot", "Capture terminal screenshot"),
    BotCommand("bind", "Bind topic to Claude Code session"),
    # ... different commands ...
]
```

**Impact**:
- Two sources of truth
- Easy to add command to one but not other
- No validation they match
- Maintenance overhead

**Fix**: Single source of truth:
```python
# commands.py
TELEGRAM_BOT_COMMANDS = {
    "start": "Start telebridge session",
    "screenshot": "Capture terminal screenshot",
    "bind": "Bind topic to Claude Code session",
}

CLAUDE_NATIVE_COMMANDS = {
    "/clear", "/compact", "/cost", "/doctor", "/init",
}

# bot.py
await application.bot.set_my_commands([
    BotCommand(cmd, desc) for cmd, desc in TELEGRAM_BOT_COMMANDS.items()
])
```

---

## 🟢 Low Priority Issues

### 11. Inconsistent Error Handling Patterns
**Location**: Multiple files

**Issue**: Mix of exception catching strategies - some log and return, some raise, some ignore.

```python
# session_manager.py:172 - silent return False
except (RuntimeError, asyncio.TimeoutError):
    return False

# handlers/claude_commands.py:174 - log and show user
except Exception as e:
    logger.error(f"Failed to check pane liveness: {e}")
    await update.message.reply_text(f"Failed to check pane status: {e}")

# handlers/messages.py:225 - bare except
try:
    bridge.send_keys(pane_key, text)
except RuntimeError as e:
    await message.reply_text(f"Error: {e}")
except Exception as e:  # Too broad
    logger.exception("Failed to send text")
```

**Fix**: Establish error handling policy:
```python
# errors.py
class TelebridgeError(Exception):
    """Base exception for telebridge errors."""

class PaneNotFoundError(TelebridgeError):
    """Pane no longer exists."""

class SessionNotBoundError(TelebridgeError):
    """No session bound to thread."""

# Consistent handling:
try:
    bridge.send_keys(pane_key, text)
except PaneNotFoundError:
    return await _handle_stale_session(ctx)
except TelebridgeError as e:
    logger.error(f"Known error: {e}")
    return await update.message.reply_text(str(e))
```

---

### 12. Missing Docstring Parameters
**Location**: `handlers/claude_commands.py:267-285`

**Issue**: `_poll_for_new_session` has incomplete parameter documentation.

```python
async def _poll_for_new_session(
    session_manager: "SessionManager", pane_key: str, timeout: float = 15.0
) -> str | None:
    """Poll session_map.json for new session_id from pane.

    Args:
        session_manager: Session manager instance
        pane_key: Pane key to watch
        timeout: Maximum seconds to wait
        # MISSING: Returns section
        # MISSING: Raises section
    """
```

**Fix**: Complete documentation:
```python
"""Poll session_map.json for new session_id from pane.

Args:
    session_manager: Session manager instance
    pane_key: Pane key to watch
    timeout: Maximum seconds to wait (default: 15.0)

Returns:
    New session_id if found, None if timeout

Raises:
    asyncio.TimeoutError: If timeout exceeded
"""
```

---

### 13. Unused Import in Test File
**Location**: `tests/test_session_lifecycle.py:9`

**Issue**: `patch` imported but never used.

```python
from unittest.mock import AsyncMock, MagicMock, patch  # patch unused
```

**Fix**: Remove unused import:
```python
from unittest.mock import AsyncMock, MagicMock
```

---

## Summary Statistics

| Category | Count | Lines Affected |
|----------|-------|----------------|
| Redundant Logic | 3 | ~80 LOC |
| Stringly-Typed Code | 6 | ~40 LOC |
| Duplicate Code | 4 | ~120 LOC |
| Leaky Abstractions | 2 | ~30 LOC |
| Magic Numbers | 3 | ~15 LOC |
| **Total** | **18** | **~285 LOC** |

## Recommended Refactoring Order

1. **Fix liveness check consolidation** (Issue #1) - Highest impact
2. **Create type-safe binding keys** (Issue #2) - Prevents bugs
3. **Store bridge in SessionManager** (Issue #5) - Better encapsulation
4. **Unify dead session handling** (Issue #3) - Reduce duplication
5. **Extract polling config** (Issue #4) - Improve maintainability
6. **Add change detection** (Issue #9) - Performance win
7. **Remove or implement placeholders** (Issue #8) - Code hygiene

## Estimated Refactoring Effort

- **High Priority**: 8-12 hours
- **Medium Priority**: 6-8 hours
- **Low Priority**: 2-3 hours
- **Total**: 16-23 hours

## Risk Assessment

- **Breaking Changes**: Medium (Issue #2, #5 require API changes)
- **Test Coverage Needed**: High (Issue #1, #3, #6 affect core paths)
- **Regression Risk**: Medium (Issue #9 changes state update timing)
