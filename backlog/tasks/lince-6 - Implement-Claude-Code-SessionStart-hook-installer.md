---
id: LINCE-6
title: Implement Claude Code SessionStart hook installer
status: To Do
assignee: []
created_date: '2026-03-03 14:31'
labels:
  - telebridge
  - hook
milestone: m-1
dependencies:
  - LINCE-3
  - LINCE-4
references:
  - ccbot src/ccbot/hook.py pattern
  - ~/.claude/settings.json hook format
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Create `telebridge/src/telebridge/hook.py` that installs a SessionStart hook in Claude Code's settings and handles the hook callback to map sessions.

**Hook installation** (`install_hook()`):
- Read `~/.claude/settings.json` (create if missing)
- Add a `SessionStart` hook entry: `{"type": "command", "command": "telebridge hook", "timeout": 5}`
- Must NOT overwrite existing hooks — append to the array
- Check if already installed before adding (search for "telebridge hook" in commands)
- Create `~/.claude/` directory if missing

**Hook callback** (`handle_hook()`):
- Called as `telebridge hook` by Claude Code when a session starts
- Receives JSON on stdin: `{"session_id": "...", "cwd": "...", "hook_event_name": "SessionStart"}`
- Determine current multiplexer context:
  - For tmux: shell out `tmux display-message -p "#{session_name}:#{window_id}:#{window_name}"`
  - For Zellij: read `$ZELLIJ_SESSION_NAME` + determine tab/pane ID via `zellij action query-tab-names` or env vars
- Write to `~/.telebridge/session_map.json`:
  ```json
  {
    "session_key": {
      "session_id": "uuid",
      "cwd": "/absolute/path",
      "pane_name": "display-name"
    }
  }
  ```
- Session key format: `{mux_session}:{window_or_tab_id}` for tmux, `{zellij_session}:{tab_index}` for Zellij
- Use file locking (`fcntl.flock()` exclusive lock on `~/.telebridge/session_map.lock`)
- Atomic write: tempfile + `os.replace()`
- Validate session_id (UUID format), validate cwd (absolute path)

**CLI integration**: The `telebridge` CLI must support `telebridge hook` subcommand that reads stdin and calls handle_hook(). Also `telebridge install-hook` to install the hook in Claude settings.

**Key difference from ccbot**: Must work with both tmux and Zellij context detection, not tmux-only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 install_hook() adds SessionStart hook to ~/.claude/settings.json without overwriting existing hooks
- [ ] #2 handle_hook() reads JSON from stdin and writes session_map.json
- [ ] #3 Works with tmux context (window_id extraction)
- [ ] #4 Works with Zellij context (tab/session detection)
- [ ] #5 File locking prevents concurrent write corruption
- [ ] #6 Atomic write via tempfile + os.replace()
- [ ] #7 telebridge hook CLI subcommand functional
- [ ] #8 telebridge install-hook CLI subcommand functional
<!-- AC:END -->
