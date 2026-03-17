---
id: LINCE-12
title: Implement session manager with topic-pane-session mapping
status: Done
assignee: []
created_date: '2026-03-03 14:33'
updated_date: '2026-03-16 06:56'
labels:
  - telebridge
  - sessions
milestone: m-2
dependencies:
  - LINCE-6
  - LINCE-10
references:
  - ccbot src/ccbot/session.py pattern
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Part of LINCE-12 implementation:
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Thread-to-pane-to-session mapping chain works end-to-end
- [ ] #2 State persisted to ~/.telebridge/state.json with atomic writes
- [ ] #3 load_session_map() reads hook-written session_map.json
- [ ] #4 Stale pane detection and cleanup on startup for both tmux and Zellij
- [ ] #5 bind/unbind/resolve operations functional
- [ ] #6 Session metadata (summary, message_count) derived from JSONL
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
LINCE-12: Implement complete with liveness-aware session resolution, topic sync for auto-bind, and `/new` session creation flow with hook callback coordination.

- Bot command menu updated with `/memory`, `/model`/ `/help` commands
- Register handlers for `/esc` command
<!-- SECTION:FINAL_SUMMARY:END -->
