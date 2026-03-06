---
id: LINCE-1
title: 'Enhance PTT mode: default behavior, dual-key support, clipboard output'
status: Done
assignee: []
created_date: '2026-03-03 10:34'
updated_date: '2026-03-05 18:10'
labels:
  - voxcode
  - feature
  - ptt
dependencies: []
references:
  - voxcode/src/voxcode/cli.py
  - voxcode/src/voxcode/config.py
  - voxcode/src/voxcode/multiplexer.py
  - voxcode/ROADMAP.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Enhance voxcode's Push-to-Talk mode with three improvements:

1. Make PTT the default operating mode (currently defaults to VAD)
2. Add a clipboard output backend using wl-copy (Wayland) or xclip (X11)
3. Support two PTT keys: Space sends to multiplexer pane (current behavior), a second key (Tab recommended) sends to system clipboard

This is a parent task grouping three sequential subtasks. The clipboard backend must exist before the dual-key routing can be implemented.

**Key files:**
- `voxcode/src/voxcode/cli.py` — main loop, `_handle_key`, `_process_ptt`, `_send_buffer`
- `voxcode/src/voxcode/config.py` — `VoxCodeConfig`, `GeneralConfig`, `PTTConfig`
- `voxcode/src/voxcode/multiplexer.py` — `MultiplexerBridge` protocol
- `voxcode/src/voxcode/tmux_bridge.py` / `zellij_bridge.py` — existing backends

**Current architecture notes:**
- PTT key is hardcoded as Space in `_handle_key` (config.ptt.key is parsed but ignored)
- `_process_ptt` accumulates frames while `ptt_active=True`, sends to transcription queue on toggle-off
- Transcription results go through `_check_results` → `buffer` → `_send_buffer` → `bridge.send_text()`
- No clipboard integration exists; ROADMAP.md mentions it as planned
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Tutti e tre i subtask completati: PTT come default, clipboard backend con wl-copy/xclip, dual PTT key (Space→pane, Tab→clipboard).
<!-- SECTION:FINAL_SUMMARY:END -->
