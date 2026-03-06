---
id: LINCE-1.2
title: Implement clipboard output backend
status: Done
assignee: []
created_date: '2026-03-03 10:35'
updated_date: '2026-03-05 17:52'
labels:
  - voxcode
  - feature
  - clipboard
dependencies: []
references:
  - voxcode/src/voxcode/multiplexer.py
  - voxcode/src/voxcode/config.py
  - voxcode/ROADMAP.md
parent_task_id: LINCE-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a clipboard output backend to voxcode that copies transcribed text to the system clipboard instead of sending it to a tmux/zellij pane.

**Context:**
Currently all transcribed text goes through `MultiplexerBridge.send_text()` to tmux or zellij. A new clipboard backend is needed so that the dual-PTT-key feature (LINCE-3's subtask) can route text to clipboard. The ROADMAP.md already mentions this as planned: "Clipboard mode: Copy transcription to clipboard via wl-copy (Wayland) or xclip (X11)".

**Architecture decision:**
Create a `ClipboardBridge` class in a new file `voxcode/src/voxcode/clipboard_bridge.py` that follows the same `MultiplexerBridge` protocol (has `send_text(text: str)` method). Internally it should:
- Detect Wayland vs X11 from `$WAYLAND_DISPLAY` / `$DISPLAY` env vars
- Use `wl-copy` on Wayland, `xclip -selection clipboard` on X11
- Raise a clear error if neither tool is available

This backend is NOT a replacement for the multiplexer bridge — it will be used in parallel by the dual-key PTT feature. It does not need to implement `get_target_pane()` or other multiplexer-specific methods.

**Key files:**
- New: `voxcode/src/voxcode/clipboard_bridge.py`
- `voxcode/src/voxcode/multiplexer.py` — reference for the `MultiplexerBridge` protocol pattern
- `voxcode/src/voxcode/config.py` — may need a `[clipboard]` config section
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 ClipboardBridge class exists in clipboard_bridge.py with a send_text(text: str) method
- [x] #2 Auto-detects Wayland vs X11 from WAYLAND_DISPLAY / DISPLAY env vars
- [x] #3 Uses wl-copy on Wayland and xclip -selection clipboard on X11
- [x] #4 Raises a descriptive error at init if neither wl-copy nor xclip is available on the system
- [x] #5 send_text() pipes the text to the clipboard tool via subprocess (not writing to temp files)
- [x] #6 Text copied to clipboard does NOT include trailing newline unless the transcription itself has one
- [x] #7 Unit tests verify Wayland detection logic and command construction (mocking subprocess)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Implementation Plan

### Step 1: Create clipboard_bridge.py
- Create `voxcode/src/voxcode/clipboard_bridge.py`
- Define `ClipboardBridge` class with `__init__` and `send_text(text: str)` methods

### Step 2: Implement display server detection
In `__init__`:
```
1. Check os.environ.get("WAYLAND_DISPLAY") → if set, use "wl-copy"
2. Else check os.environ.get("DISPLAY") → if set, use "xclip"
3. Else raise RuntimeError with descriptive message
4. Verify the chosen tool exists via shutil.which()
5. If tool not found, raise RuntimeError("wl-copy not found. Install with: sudo dnf install wl-clipboard")
```

### Step 3: Implement send_text
```python
def send_text(self, text: str) -> None:
    if self._backend == "wl-copy":
        subprocess.run(["wl-copy", "--", text], check=True)
    elif self._backend == "xclip":
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode(),
            check=True,
        )
```

Key details:
- `wl-copy --` ensures text starting with `-` is not misinterpreted as flags
- `xclip` reads from stdin, so use `input=` parameter
- No trailing newline added — text goes as-is

### Step 4: Add tests
- Create `voxcode/tests/test_clipboard_bridge.py`
- Test Wayland detection: mock `WAYLAND_DISPLAY` set → expects wl-copy
- Test X11 detection: mock only `DISPLAY` set → expects xclip
- Test neither available: mock both unset → expects RuntimeError
- Test send_text command construction: mock subprocess.run, verify correct args
- Test missing tool: mock shutil.which returning None → expects RuntimeError

### Estimated effort: Medium (1-2 hours)
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Created `voxcode/src/voxcode/clipboard_bridge.py` with `ClipboardBridge` class. Detects Wayland (WAYLAND_DISPLAY → wl-copy) vs X11 (DISPLAY → xclip), verifies tool availability at init, and pipes text via subprocess without adding trailing newlines. Created `voxcode/tests/test_clipboard_bridge.py` with 12 passing tests covering detection logic, error cases, and command construction.
<!-- SECTION:FINAL_SUMMARY:END -->
