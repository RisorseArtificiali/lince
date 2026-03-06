---
id: LINCE-21
title: 'Implement bot commands: /start, /history, /usage, /help'
status: To Do
assignee: []
created_date: '2026-03-03 14:35'
updated_date: '2026-03-03 16:51'
labels:
  - telebridge
  - commands
milestone: m-7
dependencies:
  - LINCE-13
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Implement the full set of bot commands in `telebridge/src/telebridge/handlers/commands.py`.

**Commands to implement:**

**`/start`**: Welcome message with usage instructions. Show bot capabilities, link to documentation, list available commands.

**`/history [N]`**: Paginated conversation history browsing.
- Read the JSONL transcript for the bound session
- Parse entries with TranscriptParser
- Display newest-first with pagination
- Default: last 10 messages
- Inline keyboard: [◀ Prev] [Next ▶] for pagination
- Show role (user/assistant), timestamp, truncated content

**`/usage`**: Token and cost statistics.
- Read JSONL transcript, extract usage data from assistant message metadata
- Display: total tokens (input/output), estimated cost, message count, session duration
- If usage data not available in JSONL, show "Usage data not available"

**`/help`**: List all available commands with descriptions.

**`/model`**: Forward to Claude Code (Claude Code has its own /model command).
- `bridge.send_text("/model")`

**`/clear`**, **`/compact`**, **`/cost`**, **`/memory`**: Forward to Claude Code.
- Send the command text directly via `bridge.send_text(command_text)`
- For `/clear`: also call `session_manager.clear_pane_session()` and reset monitor offset

**Command menu**: Set bot commands via `bot.set_my_commands()` in post_init so they appear in Telegram's command autocomplete.

**All commands require auth check** as first step.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 /start shows welcome message with capabilities
- [ ] #2 /history displays paginated conversation with inline keyboard navigation
- [ ] #3 /usage shows token/cost statistics from JSONL data
- [ ] #4 /help lists all commands
- [ ] #5 Claude commands (/clear, /compact, /cost, /memory, /model) forwarded correctly
- [ ] #6 Command menu set in Telegram autocomplete
- [ ] #7 All commands check auth
<!-- AC:END -->
