---
id: LINCE-13
title: 'Implement session lifecycle: create, resume, topic sync'
status: To Do
assignee: []
created_date: '2026-03-03 14:33'
labels:
  - telebridge
  - sessions
milestone: m-2
dependencies:
  - LINCE-11
  - LINCE-12
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Extend the bot and session manager to support full multi-session lifecycle tied to Telegram forum topics.

**Session creation flow:**
1. User sends message in an unbound topic
2. Bot detects no binding for this thread_id
3. If `auto_bind` is true and there's exactly one active unbound pane, bind automatically
4. Otherwise, present session picker: list active Claude Code sessions with inline keyboard
5. User selects session -> bind_thread()
6. Alternatively, user can start a new session (creates new multiplexer pane with `claude` command)

**Session resume flow:**
1. User sends message in a bound topic
2. Bot resolves pane_key -> session_id
3. If session is still active, forward message to pane
4. If session has ended (pane closed), notify user and offer to start new session

**New session creation:**
- Via MultiplexerBridge: create new pane/window running `claude` command
- Need to extend MultiplexerBridge or use direct subprocess for pane creation
- For tmux: `tmux new-window -t session_name "claude"`
- For Zellij: `zellij action new-tab` then write claude command
- Wait for hook callback to register session_id, then bind

**Topic lifecycle sync:**
- Handle Telegram topic closed event -> optionally kill multiplexer pane
- Handle Telegram topic reopened -> check if pane still exists
- Handle topic renamed -> optionally rename pane/window

**Bot commands for session management:**
- `/unbind` — detach current topic from session (pane keeps running)
- `/sessions` — list all active sessions with status
- `/bind` — manually pick a session to bind to current topic

**Claude commands forwarded:**
- `/clear`, `/compact`, `/cost`, `/help`, `/memory`, `/model` — sent as text to Claude Code pane via send_text()

**Interrupt:**
- `/esc` — send Ctrl+C to pane via send_keys(["Ctrl-C"]) — extend key mapping to include Ctrl-C
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Auto-bind works when single unbound session available
- [ ] #2 Session picker shows active sessions as inline keyboard
- [ ] #3 New session creation launches claude in new pane
- [ ] #4 Resume detects dead sessions and offers restart
- [ ] #5 Topic close/reopen handled gracefully
- [ ] #6 /unbind detaches topic from session
- [ ] #7 /esc sends Ctrl+C to pane
- [ ] #8 Claude commands (/clear, /compact, etc.) forwarded correctly
<!-- AC:END -->
