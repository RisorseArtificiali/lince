---
id: LINCE-1.1
title: Make PTT the default operating mode
status: Done
assignee: []
created_date: '2026-03-03 10:35'
updated_date: '2026-03-05 17:52'
labels:
  - voxcode
  - ptt
  - config
dependencies: []
references:
  - voxcode/src/voxcode/config.py
  - voxcode/src/voxcode/cli.py
  - voxcode/config.toml
parent_task_id: LINCE-1
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Change voxcode's default mode from VAD to PTT so that push-to-talk is the out-of-box experience.

**Context:**
Currently `GeneralConfig.mode` defaults to `"vad"` in `config.py:18`. Users must explicitly set `mode = "ptt"` in config.toml. The user wants PTT as the default because it's the primary usage pattern.

**Key files:**
- `voxcode/src/voxcode/config.py` — `GeneralConfig` dataclass, `mode` field default value
- `voxcode/src/voxcode/cli.py` — references to `self.config.general.mode`
- `voxcode/config.toml` — example config file
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GeneralConfig.mode defaults to "ptt" in config.py (no config.toml needed for PTT)
- [x] #2 VAD mode still works when explicitly set via mode = "vad" in config.toml
- [x] #3 Example config.toml is updated to document the new default and show how to switch to VAD
- [x] #4 Application starts in PTT mode when no config.toml exists
- [x] #5 UI correctly shows PTT-related status on startup with default config
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
## Implementation Plan

### Step 1: Change default in config.py
- Open `voxcode/src/voxcode/config.py`
- In `GeneralConfig` dataclass, change `mode: str = "vad"` to `mode: str = "ptt"`

### Step 2: Update example config.toml
- Open `voxcode/config.toml`
- Change `mode = "ptt"` (or comment it out since it's now default)
- Add a comment: `# mode = "vad"  # uncomment to use voice activity detection instead of push-to-talk`

### Step 3: Verify CLI behavior
- Run `python -m voxcode` without config.toml → should start in PTT mode
- Run with `mode = "vad"` in config.toml → should start in VAD mode
- Verify UI shows correct status for each mode on startup

### Estimated effort: Small (< 30 min)
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Changed `GeneralConfig.mode` default from `"vad"` to `"ptt"` in config.py. Updated config.toml to comment out the mode line (since PTT is now default) and document how to switch back to VAD.
<!-- SECTION:FINAL_SUMMARY:END -->
