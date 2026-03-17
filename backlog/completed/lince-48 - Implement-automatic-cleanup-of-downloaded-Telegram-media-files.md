---
id: LINCE-48
title: Implement automatic cleanup of downloaded Telegram media files
status: Done
assignee: []
created_date: '2026-03-16 13:48'
updated_date: '2026-03-17 09:53'
labels:
  - enhancement
  - cleanup
  - maintenance
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Downloaded photos and documents from Telegram accumulate in the project directory with no automatic cleanup.

**Current Behavior:**
- LINCE-18 downloads photos to `{session.cwd}/telegram_photo_{timestamp}.jpg`
- Files persist indefinitely
- No cleanup mechanism
- User must manually delete files

**Proposed Solutions (pick one or combination):**

1. **Time-based cleanup:** Delete files older than N hours
2. **Per-session quota:** Limit to N files per session
3. **Explicit cleanup command:** Add `/cleanup` command
4. **Cleanup on session end:** Delete files when user unbinds session
5. **Configurable policy:** Let user choose cleanup behavior

**Considerations:**
- Don't delete files user might want to keep
- Provide warning before cleanup
- Track which files were downloaded by telebridge vs user-created
- Config option for cleanup behavior

**Configuration Example:**
```toml
[media]
cleanup_policy = "on_unbind"  # never | on_unbind | time:N | quota:N
max_files_per_session = 50
file_retention_hours = 24
```

**Reference:**
- Files downloaded via LINCE-18 photo handler
- SessionManager for tracking session lifecycle
<!-- SECTION:DESCRIPTION:END -->
