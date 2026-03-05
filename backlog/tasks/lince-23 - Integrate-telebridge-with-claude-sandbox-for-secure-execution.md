---
id: LINCE-23
title: Integrate telebridge with claude-sandbox for secure execution
status: To Do
assignee: []
created_date: '2026-03-03 14:36'
labels:
  - telebridge
  - sandbox
  - security
milestone: m-6
dependencies:
  - LINCE-13
references:
  - sandbox/claude-sandbox
  - sandbox security model
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add optional integration between telebridge and the LINCE sandbox module, allowing Claude Code sessions started from Telegram to run inside the Bubblewrap sandbox.

**Motivation**: When controlling Claude Code remotely via Telegram, the security argument for sandboxing is even stronger — the user has less visibility into what Claude Code is doing in real-time.

**Implementation:**
- Config option: `[session] use_sandbox = true` (default false)
- When `use_sandbox` is true and creating a new session pane:
  - Instead of running `claude`, run `claude-sandbox run`
  - Verify `claude-sandbox` is available in PATH
  - Pass appropriate flags (project dir as argument)
- When `use_sandbox` is false: run `claude` directly (current behavior)

**Security considerations for telebridge itself:**
- Telegram bot token must NOT be visible inside the sandbox
  - The env scrubbing in config.py already pops `TELEGRAM_BOT_TOKEN` from os.environ
  - Verify this works when sandbox inherits environment
- `~/.telebridge/` state directory should be outside sandbox scope
  - Sandbox whitelists specific directories; telebridge state should NOT be writable from inside
- Hook subprocess (`telebridge hook`) runs OUTSIDE the sandbox (called by Claude Code's hook system, which runs on the host)

**Verification:**
- Test that sessions started via Telegram with `use_sandbox=true` correctly run inside sandbox
- Test that bot token is not visible from within the sandbox
- Test that telebridge state files are not writable from sandbox

**Documentation**: Add a section to README explaining the sandbox integration and security model.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Config option use_sandbox toggles sandbox usage
- [ ] #2 New sessions use claude-sandbox run when enabled
- [ ] #3 claude-sandbox availability checked before session creation
- [ ] #4 Bot token not visible inside sandbox environment
- [ ] #5 Telebridge state files not writable from sandbox
- [ ] #6 Graceful fallback if claude-sandbox not installed
<!-- AC:END -->
