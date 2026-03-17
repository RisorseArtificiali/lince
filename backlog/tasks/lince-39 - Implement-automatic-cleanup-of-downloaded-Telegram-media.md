---
id: LINCE-39
title: Implement automatic cleanup of downloaded Telegram media
status: To Do
assignee: []
created_date: '2026-03-16 13:23'
labels:
  - enhancement
  - cleanup
  - maintenance
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Downloaded photos and documents accumulate in the project directory. Implement automatic cleanup to prevent disk space issues.

**Options to consider:**
1. Time-based cleanup (delete files older than N hours)
2. Per-session quota (max N files per session)
3. Explicit cleanup command (/cleanup)
4. Cleanup on session unbind/end

**Requirements:**
- Track downloaded files per session
- Provide user control over cleanup policy
- Don't delete files that might be important to user
- Add config option for cleanup behavior

**References:**
- Files downloaded via LINCE-18 photo handler
- `SessionManager` for tracking session lifecycle
<!-- SECTION:DESCRIPTION:END -->
