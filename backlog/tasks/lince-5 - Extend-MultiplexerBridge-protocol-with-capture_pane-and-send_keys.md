---
id: LINCE-5
title: Extend MultiplexerBridge protocol with capture_pane and send_keys
status: To Do
assignee: []
created_date: '2026-03-03 14:31'
labels:
  - telebridge
  - voxcode
  - multiplexer
milestone: m-0
dependencies: []
references:
  - voxcode/src/voxcode/multiplexer.py
  - voxcode/src/voxcode/zellij_bridge.py
  - voxcode/src/voxcode/tmux_bridge.py
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Extend the `MultiplexerBridge` protocol in `voxcode/src/voxcode/multiplexer.py` with two new methods needed by telebridge, and implement them in both bridge backends.

**Protocol extension:**
```python
class MultiplexerBridge(Protocol):
    # Existing:
    def validate(self) -> None: ...
    def get_target_pane(self) -> str: ...
    def send_text(self, text: str) -> None: ...
    
    # New:
    def capture_pane(self) -> str: ...
    def send_keys(self, keys: list[str]) -> None: ...
```

**ZellijBridge implementation** (`zellij_bridge.py`):
- `capture_pane()`: Focus target pane, run `zellij action dump-screen`, capture stdout, focus back. Note: `dump-screen` outputs plain text without ANSI codes by default. Test with `--full` flag for scrollback.
- `send_keys(keys)`: For each key in list, map to Zellij write byte codes. Mapping: `"Enter"` -> `write 13`, `"Escape"` -> `write 27`, `"Up"` -> `write 27 91 65`, `"Down"` -> `write 27 91 66`, `"Left"` -> `write 27 91 68`, `"Right"` -> `write 27 91 67`, `"Space"` -> `write 32`, `"Tab"` -> `write 9`. Focus target pane before sending, focus back after.

**TmuxBridge implementation** (`tmux_bridge.py`):
- `capture_pane()`: `tmux capture-pane -t {pane} -p` (prints to stdout). For ANSI colors: add `-e` flag.
- `send_keys(keys)`: `tmux send-keys -t {pane} {key}` for each key. tmux understands key names directly (Enter, Escape, Up, Down, Left, Right, Space, Tab).

**Important**: These additions must not break VoxCode's existing usage. The protocol uses structural subtyping (Protocol), so existing bridges that don't implement the new methods will only fail if the new methods are actually called. However, we should implement them in both bridges to keep the contract complete.

**Testing approach**: Manual test with both Zellij and tmux — verify capture_pane returns readable text, send_keys correctly sends arrow keys and Enter to Claude Code pane.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 MultiplexerBridge protocol includes capture_pane and send_keys
- [ ] #2 ZellijBridge.capture_pane() returns pane text via dump-screen
- [ ] #3 ZellijBridge.send_keys() sends special keys via write byte codes
- [ ] #4 TmuxBridge.capture_pane() returns pane text via capture-pane -p
- [ ] #5 TmuxBridge.send_keys() sends special keys via tmux send-keys
- [ ] #6 Existing VoxCode send_text functionality unaffected
- [ ] #7 Key mapping covers: Enter, Escape, Up, Down, Left, Right, Space, Tab
<!-- AC:END -->
