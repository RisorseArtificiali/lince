---
id: LINCE-17
title: Implement terminal screenshot capture as PNG
status: To Do
assignee: []
created_date: '2026-03-03 14:34'
labels:
  - telebridge
  - media
  - screenshot
milestone: m-4
dependencies:
  - LINCE-5
  - LINCE-10
references:
  - ccbot src/ccbot/screenshot.py pattern
  - Pillow ImageDraw.text() API
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/screenshot.py` — captures the Claude Code terminal pane and renders it as a PNG image with ANSI color support.

**Capture flow:**
1. `MultiplexerBridge.capture_pane()` with ANSI color support
   - tmux: `tmux capture-pane -t {pane} -p -e` (the `-e` flag preserves ANSI escape sequences)
   - Zellij: investigate `dump-screen` ANSI support; may need alternative approach
2. Parse ANSI escape sequences from captured text
3. Render text to image with Pillow

**ANSI parsing** (from ccbot pattern):
- Parse standard ANSI escape codes: `\033[...m`
- Support 16 basic colors (standard + bright variants)
- Support 256-color palette mode
- Support true RGB color: `\033[38;2;R;G;Bm` (foreground), `\033[48;2;R;G;Bm` (background)
- Track foreground and background color state across segments

**Rendering with Pillow:**
- Use monospace font (bundle JetBrains Mono or use system monospace)
- Configurable font size (default 14)
- Split text into lines, parse ANSI per segment
- Measure max line width and total height
- Create image with calculated dimensions + padding
- Draw each text segment with its color attributes
- Dark background (terminal-like: #1e1e2e or configurable)
- Save as PNG bytes (BytesIO)

**Run async**: Image generation is CPU-intensive — run in `asyncio.to_thread()` to avoid blocking the event loop.

**Bot integration:**
- `/screenshot` command triggers capture + render + send as photo
- Screenshot refresh button on interactive UI keyboard
- `send_screenshot(bot, chat_id, thread_id)` helper function

**Fallback**: If ANSI capture not available (Zellij limitation), render plain text with default colors.

**Note on Zellij**: `zellij action dump-screen` may not preserve ANSI codes. If this is confirmed, the Zellij path renders with default monochrome styling. This is acceptable as v1 — ANSI support for Zellij can be enhanced later.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Captures pane content with ANSI codes (tmux -e flag)
- [ ] #2 Parses 16-color, 256-color, and RGB ANSI sequences
- [ ] #3 Renders to PNG with monospace font and terminal colors
- [ ] #4 Image generation runs in thread pool (non-blocking)
- [ ] #5 Sent as Telegram photo via bot.send_photo()
- [ ] #6 /screenshot command triggers capture-render-send
- [ ] #7 Graceful fallback for Zellij plain text capture
<!-- AC:END -->
