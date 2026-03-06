---
id: LINCE-1.3
title: 'Add dual PTT key support: Space for pane, Tab for clipboard'
status: Done
assignee: []
created_date: '2026-03-03 10:35'
updated_date: '2026-03-05 17:52'
labels:
  - voxcode
  - feature
  - ptt
  - clipboard
dependencies:
  - LINCE-1.2
references:
  - voxcode/src/voxcode/cli.py
  - voxcode/src/voxcode/config.py
  - voxcode/src/voxcode/ui.py
  - voxcode/src/voxcode/clipboard_bridge.py
parent_task_id: LINCE-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add a second push-to-talk key that routes transcribed text to the system clipboard instead of the multiplexer pane, enabling the user to paste wherever they want.

**Context:**
Currently PTT uses only Space (hardcoded in `_handle_key` at cli.py:191). The user wants two PTT keys:
- **Space** — existing behavior: record → transcribe → send to tmux/zellij pane
- **Second key** — record → transcribe → copy to clipboard

**Key choice rationale:**
Tab (`\t`) is recommended because:
- It's easy to press, adjacent to typical hand position
- Not used for anything in voxcode currently
- Easily distinguishable in cbreak mode (`sys.stdin.read(1)` returns `\t`)
- Ctrl combinations are problematic in terminals (Ctrl+C = SIGINT, many others reserved)

The choice should be configurable via `config.ptt.clipboard_key` with Tab as default.

**Architecture:**
The core change is that `_process_ptt` and `_handle_key` need to track WHICH key initiated the recording, so `_check_results` knows where to route the transcription. Current flow:

```
Space toggle → ptt_active → accumulate frames → transcribe → buffer → _send_buffer → bridge
```

New flow:
```
Space toggle → ptt_active + target=pane → accumulate → transcribe → _send_buffer → bridge
Tab toggle   → ptt_active + target=clipboard → accumulate → transcribe → _send_to_clipboard → clipboard_bridge
```

**Implementation approach:**
1. Add `ptt_target` field to track routing ("pane" or "clipboard") set when PTT starts
2. In `_handle_key`: handle Tab like Space but set `ptt_target = "clipboard"`
3. In `_check_results` or `_send_buffer`: route based on `ptt_target`
4. Instantiate `ClipboardBridge` alongside the multiplexer bridge in `VoxCode.__init__`
5. Add config: `[ptt] clipboard_key = "tab"` and actually read it (fix the existing bug where config.ptt.key is ignored)
6. Update UI to show which mode (pane/clipboard) is active during recording

**Dependencies:**
- Requires clipboard backend from sibling subtask (ClipboardBridge)

**Key files:**
- `voxcode/src/voxcode/cli.py` — `_handle_key`, `_process_ptt`, `_check_results`, `_send_buffer`, `VoxCode.__init__`
- `voxcode/src/voxcode/config.py` — `PTTConfig` dataclass
- `voxcode/src/voxcode/clipboard_bridge.py` — from sibling task
- `voxcode/src/voxcode/ui.py` — status display updates
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Space toggles PTT recording and routes transcription to multiplexer pane (existing behavior preserved)
- [x] #2 Tab toggles PTT recording and routes transcription to system clipboard
- [x] #3 Only one PTT session can be active at a time (pressing Tab while Space-PTT is active is ignored, and vice versa)
- [x] #4 UI shows recording target during PTT: "recording → pane" or "recording → clipboard"
- [x] #5 config.ptt.key is actually read from config and used (fixing current bug where Space is hardcoded)
- [x] #6 config.ptt.clipboard_key is configurable with default "tab"
- [x] #7 Both keys work as toggles: first press starts recording, second press stops and routes
- [x] #8 When clipboard PTT completes, a brief UI confirmation shows the text was copied
- [x] #9 VAD mode is unaffected by these changes (dual-key only applies in PTT mode)
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Implementation Plan

### Step 1: Add config fields in config.py
- In `PTTConfig` dataclass, add: `clipboard_key: str = "tab"`
- Keep existing `key: str = "space"` field

### Step 2: Fix hardcoded key in _handle_key (cli.py)
Currently `_handle_key` checks `key == " "` hardcoded. Change to:
- Map config key names to actual characters: `{"space": " ", "tab": "\t"}`
- Read `self.config.ptt.key` and `self.config.ptt.clipboard_key` at init
- Store resolved characters as `self._ptt_key_char` and `self._ptt_clipboard_key_char`

### Step 3: Add ptt_target tracking
- Add `self.ptt_target: str | None = None` field to VoxCode class
- When PTT starts via Space: `self.ptt_target = "pane"`
- When PTT starts via Tab: `self.ptt_target = "clipboard"`
- When PTT stops: target is preserved until transcription is routed, then cleared

### Step 4: Modify _handle_key for dual-key support
```python
elif key == self._ptt_key_char and self.config.general.mode == "ptt":
    if self.ptt_active and self.ptt_target != "pane":
        return  # ignore: different PTT key is active
    self.ptt_active = not self.ptt_active
    if self.ptt_active:
        self.ptt_target = "pane"
        ptt_frames.clear()
        self.ui.update(status="recording", ptt_active=True, ptt_target="pane")
    else:
        self.ui.update(ptt_active=False)

elif key == self._ptt_clipboard_key_char and self.config.general.mode == "ptt":
    if self.ptt_active and self.ptt_target != "clipboard":
        return  # ignore: different PTT key is active
    self.ptt_active = not self.ptt_active
    if self.ptt_active:
        self.ptt_target = "clipboard"
        ptt_frames.clear()
        self.ui.update(status="recording", ptt_active=True, ptt_target="clipboard")
    else:
        self.ui.update(ptt_active=False)
```

### Step 5: Initialize ClipboardBridge in VoxCode.__init__
- Import ClipboardBridge
- Try to instantiate `self.clipboard_bridge = ClipboardBridge()`
- Catch RuntimeError → log warning, set `self.clipboard_bridge = None`
- If clipboard_bridge is None, Tab key should be ignored with UI warning

### Step 6: Route transcription based on ptt_target
In `_check_results` or `_send_buffer`, check `self.ptt_target`:
- `"pane"` → existing `self.bridge.send_text(text)` path
- `"clipboard"` → `self.clipboard_bridge.send_text(text)` + UI confirmation
- After routing, clear `self.ptt_target = None`

### Step 7: Update UI (ui.py)
- Accept `ptt_target` parameter in `update()`
- Display "recording → pane" or "recording → clipboard" during active PTT
- Show brief "copied to clipboard" confirmation (1-2 seconds) after clipboard send

### Step 8: Update example config.toml
```toml
[ptt]
key = "space"           # PTT key for sending to multiplexer pane
clipboard_key = "tab"   # PTT key for copying to clipboard
```

### Estimated effort: Medium-Large (2-4 hours)
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented dual PTT key support: Space→pane, Tab→clipboard. Added `clipboard_key: str = "tab"` to PTTConfig. Added `_KEY_MAP` for symbolic→char resolution (fixing the config.ptt.key bug). Added `ptt_target` field to VoxCode and VoxCodeUI. ClipboardBridge initialized at startup with graceful fallback if unavailable. `_handle_key` uses config-driven key chars with mutual-exclusion guard. Transcription routed in `_check_results` based on `ptt_target`. Added `_send_to_clipboard` method. UI shows "recording → pane" / "recording → clipboard" and updated keybindings hint. VAD mode unaffected.
<!-- SECTION:FINAL_SUMMARY:END -->
