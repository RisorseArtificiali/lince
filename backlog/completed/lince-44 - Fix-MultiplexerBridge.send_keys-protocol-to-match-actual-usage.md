---
id: LINCE-44
title: Fix MultiplexerBridge.send_keys protocol to match actual usage
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 08:29'
labels:
  - bug
  - type-safety
  - protocol
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `MultiplexerBridge` protocol defines `send_keys(self, text: str)` but all implementations and usage call it with TWO arguments: `send_keys(pane_key, text)`.

**Protocol Definition (multiplexer.py:48):**
```python
def send_keys(self, text: str) -> None:
```

**Actual Usage (throughout codebase):**
```python
bridge.send_keys(pane_key, text)
```

**Implementations:**
- tmux_bridge.py:92 - Only accepts `text`
- zellij_bridge.py:129 - Only accepts `text`

**Issue:**
- Protocol doesn't match implementation or usage
- Type hint mismatch causes linter errors
- LSP can't provide accurate completions

**Options:**
1. Update protocol to match reality: `send_keys(self, pane_key: str, text: str)`
2. Add pane tracking to bridge instances (remove pane_key parameter)
3. Create `send_to_pane()` method separate from `send_keys()`

**Reference:**
- telebridge/src/telebridge/multiplexer.py:48
- telebridge/src/telebridge/tmux_bridge.py:92
- telebridge/src/telebridge/zellij_bridge.py:129
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Protocol definition updated to send_keys(pane_key: str, text: str)
- [ ] #2 TmuxBridge implementation updated with pane_key parameter
- [ ] #3 ZellijBridge implementation updated with pane_key parameter
- [ ] #4 All callers updated to pass pane_key argument
- [ ] #5 All 176 tests pass
- [ ] #6 Type hints are consistent across protocol and implementations
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Summary

Fixed the `MultiplexerBridge.send_keys` protocol mismatch where the protocol defined `send_keys(text: str)` but callers were using `send_keys(pane_key, text)`.

### Changes Made

1. **Protocol (multiplexer.py:48)**: Updated signature to `send_keys(self, pane_key: str, text: str)`

2. **TmuxBridge (tmux_bridge.py:92)**: Updated to use `pane_key` parameter directly instead of `get_target_pane()`

3. **ZellijBridge (zellij_bridge.py:129)**: Updated to accept `pane_key` parameter (Zellij uses current session for now as it doesn't have per-pane targeting)

4. **Handler Updates**:
   - `handlers/messages.py`: Updated `_forward_claude_command` to accept `pane_key` parameter
   - `handlers/ui_callbacks.py`: Updated to resolve `pane_key` from session manager before calling `send_keys`

### Design Choice
Chose **Option 1** (update protocol to match reality) because:
- Handlers already have `pane_key` from session resolution
- Multi-pane support requires explicit targeting
- Aligns with tmux's native `-t pane` syntax

All 176 tests pass.
<!-- SECTION:FINAL_SUMMARY:END -->
